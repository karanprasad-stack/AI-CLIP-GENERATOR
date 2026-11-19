"""Live Stream Session Orchestrator: manages rolling capture, candidate analysis, SSE events, and storage."""

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from backend.app.config import (
    LIVE_SEGMENT_DURATION_SEC,
    LIVE_SEGMENT_OVERLAP_SEC,
    LIVE_RECONNECT_MAX_ATTEMPTS,
)
from backend.app.pipeline.live.models import (
    LiveSession,
    LiveSegment,
    LiveCandidate,
    LiveSessionStatus,
    LiveCandidateStatus,
)
from backend.app.pipeline.live.live_store import LiveStore
from backend.app.pipeline.live.capture_engine import LiveCaptureEngine, CaptureError
from backend.app.pipeline.live.candidate_engine import LiveCandidateEngine


class LiveOrchestrator:
    """Coordinates the continuous rolling capture and candidate analysis pipeline for a live stream."""

    def __init__(
        self,
        project_dir: Path,
        project_id: str,
        source_url: str,
        source_video_id: str,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        segment_duration: float = LIVE_SEGMENT_DURATION_SEC,
        segment_overlap: float = LIVE_SEGMENT_OVERLAP_SEC,
        simulation_source: Optional[Path] = None,
    ):
        self.project_dir = project_dir
        self.project_id = project_id
        self.source_url = source_url
        self.source_video_id = source_video_id
        self.event_callback = event_callback
        self.simulation_source = simulation_source

        self.store = LiveStore(project_dir)
        self.capture_engine = LiveCaptureEngine(
            live_dir=self.store.live_dir,
            segment_duration=segment_duration,
            segment_overlap=segment_overlap,
        )
        self.candidate_engine = LiveCandidateEngine()

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._is_paused = False
        self._worker_thread: Optional[threading.Thread] = None

        # Load or initialize session state
        existing_session = self.store.load_session()
        if existing_session and existing_session.status not in (LiveSessionStatus.ENDED, LiveSessionStatus.FAILED, LiveSessionStatus.CANCELLED):
            self.session = existing_session
        else:
            self.session = LiveSession(
                session_id=f"live_{source_video_id}_{int(time.time())}",
                project_id=project_id,
                source_url=source_url,
                source_video_id=source_video_id,
                status=LiveSessionStatus.STARTING,
            )
            self.store.save_session(self.session)

        self.segments: List[LiveSegment] = self.store.load_manifest()
        self.candidates: List[LiveCandidate] = self.store.load_candidates()

    def emit_event(self, event_type: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Broadcasts a live SSE event and logs to the activity feed."""
        data = {
            "project_id": self.project_id,
            "session_id": self.session.session_id,
            "event_type": event_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "time_str": datetime.now().strftime("%H:%M:%S"),
            "session_status": self.session.status,
            "segments_processed": self.session.segments_processed,
            "candidates_detected": self.session.candidates_detected,
            "candidates_ready": self.session.candidates_ready,
        }
        if payload:
            data.update(payload)

        self.store.log_activity(event_type, message, payload)
        if self.event_callback:
            try:
                self.event_callback(data)
            except Exception:
                pass

    def start(self) -> None:
        """Launches the rolling live capture and analysis loop in a background thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()
        self._pause_event.clear()
        self._is_paused = False
        self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._worker_thread.start()

    def stop(self) -> None:
        """Signals the live session to stop gracefully."""
        self._stop_event.set()
        self.session.status = LiveSessionStatus.STOPPING
        self.store.save_session(self.session)
        self.emit_event("live_session_stopped", "Live stream capture stop requested.")

    def pause(self) -> None:
        """Pauses the rolling capture loop."""
        self._is_paused = True
        self._pause_event.set()
        self.emit_event("live_session_paused", "Live stream processing paused.")

    def resume(self) -> None:
        """Resumes a paused rolling capture loop."""
        self._is_paused = False
        self._pause_event.clear()
        self.emit_event("live_session_resumed", "Live stream processing resumed.")

    def _run_loop(self) -> None:
        """Continuous execution loop processing rolling segments until stream end or cancellation."""
        self.session.status = LiveSessionStatus.CONNECTING
        self.store.save_session(self.session)
        self.emit_event("live_connecting", f"Connecting to live source stream: {self.source_video_id}")

        time.sleep(0.5)
        self.session.status = LiveSessionStatus.LIVE
        self.store.save_session(self.session)
        self.emit_event("live_connected", f"Connected to live stream. Rolling capture active.")

        segment_id = self.session.last_segment_id + 1
        consecutive_failures = 0

        # Optional duration check for simulation source
        sim_duration = None
        if self.simulation_source and self.simulation_source.exists():
            try:
                from backend.app.pipeline.video_downloader import VideoSourceDownloader
                probe = VideoSourceDownloader().probe_video(self.simulation_source)
                sim_duration = probe.get("duration")
            except Exception:
                pass

        while not self._stop_event.is_set():
            if self._is_paused:
                time.sleep(1.0)
                continue

            # Disk safety check before capturing next segment
            is_safe, warning_msg = self.store.check_disk_safety()
            if warning_msg:
                self.emit_event("live_storage_warning", warning_msg)
            if not is_safe:
                self.session.status = LiveSessionStatus.FAILED
                self.session.error = {"summary": "Disk Space Exhausted", "details": warning_msg}
                self.store.save_session(self.session)
                self.emit_event("live_session_failed", f"Aborted capture due to storage protection: {warning_msg}")
                break

            self.emit_event(
                "live_segment_started",
                f"Capturing Segment #{segment_id} ({self.capture_engine.segment_duration:.0f}s window)...",
                {"segment_id": segment_id},
            )

            try:
                if self.simulation_source:
                    segment = self.capture_engine.capture_segment_simulated(
                        source_video=self.simulation_source,
                        segment_id=segment_id,
                        source_duration=sim_duration,
                    )
                else:
                    segment = self.capture_engine.capture_segment_live(
                        stream_url=self.source_url,
                        segment_id=segment_id,
                    )

                if segment is None:
                    # Stream completed / ended
                    self.emit_event("live_stream_ended", "Source live stream completed.")
                    break

                consecutive_failures = 0
                self.segments.append(segment)
                self.session.total_segments += 1
                self.session.last_segment_id = segment_id
                self.store.save_manifest(self.segments)
                self.store.save_session(self.session)

                self.emit_event(
                    "live_segment_completed",
                    f"Segment #{segment_id} captured ({segment.duration:.1f}s, {segment.file_size_bytes / (1024*1024):.1f}MB). Analyzing moments...",
                    {"segment_id": segment_id, "duration": segment.duration},
                )

                # Analyze segment for gaming climax moments
                raw_cands, transcript_data = self.candidate_engine.analyze_segment(segment)
                segment.status = "analyzed"
                if transcript_data:
                    t_path = self.store.save_segment_transcript(segment.segment_id, transcript_data)
                    segment.transcript_file = str(t_path)

                # Cross-segment boundary merging & candidate pool update
                self.candidates, logs = self.candidate_engine.merge_and_update_candidates(
                    existing_pool=self.candidates,
                    new_candidates=raw_cands,
                    segment=segment,
                )

                # Update segment candidate references
                for c in self.candidates:
                    if segment.segment_id in c.source_segments:
                        if c.candidate_id not in segment.required_by_candidates:
                            segment.required_by_candidates.append(c.candidate_id)

                self.session.segments_processed += 1
                self.session.candidates_detected = len(self.candidates)
                self.session.candidates_ready = sum(
                    1 for c in self.candidates if c.status == LiveCandidateStatus.PUBLISH_READY
                )

                self.store.save_manifest(self.segments)
                self.store.save_candidates(self.candidates)
                self.store.save_session(self.session)

                # Broadcast analysis events & merge logs
                for log_msg in logs:
                    if "merged" in log_msg.lower():
                        self.emit_event("live_candidate_merged", log_msg)
                    elif "detected" in log_msg.lower():
                        self.emit_event("live_candidate_detected", log_msg)

                self.emit_event(
                    "live_segment_analyzed",
                    f"Segment #{segment_id} analyzed: {len(raw_cands)} raw moments found. Total candidates: {len(self.candidates)} ({self.session.candidates_ready} publish-ready).",
                    {"segment_id": segment_id, "candidates_count": len(self.candidates)},
                )

                # Cleanup non-required safe segments to maintain bounded disk footprint
                deleted = self.store.cleanup_safe_segments(self.segments, self.candidates)
                if deleted:
                    self.store.save_manifest(self.segments)

                segment_id += 1

            except CaptureError as ce:
                consecutive_failures += 1
                if consecutive_failures > LIVE_RECONNECT_MAX_ATTEMPTS:
                    self.session.status = LiveSessionStatus.FAILED
                    self.session.error = {"summary": "Capture Failed", "details": str(ce)}
                    self.store.save_session(self.session)
                    self.emit_event("live_session_failed", f"Live capture failed permanently: {ce}")
                    break

                backoff = self.capture_engine.calculate_backoff_delay(consecutive_failures)
                self.session.status = LiveSessionStatus.RECONNECTING
                self.session.reconnect_count += 1
                self.store.save_session(self.session)
                self.emit_event(
                    "live_reconnecting",
                    f"Temporary capture drop ({ce}). Reconnecting in {backoff:.1f}s (Attempt {consecutive_failures}/{LIVE_RECONNECT_MAX_ATTEMPTS})...",
                    {"attempt": consecutive_failures, "backoff": backoff},
                )
                time.sleep(backoff)

            except Exception as e:
                self.session.status = LiveSessionStatus.FAILED
                self.session.error = {"summary": "Unexpected Error", "details": str(e)}
                self.store.save_session(self.session)
                self.emit_event("live_session_failed", f"Unexpected error in live orchestrator: {e}")
                break

        # Finalize live session
        if self.session.status != LiveSessionStatus.FAILED:
            self.session.status = LiveSessionStatus.ENDED
            self.session.ended_at = datetime.now(timezone.utc).isoformat()
            self.store.save_session(self.session)
            self.emit_event(
                "live_stream_ended",
                f"Live session finalized: {self.session.segments_processed} segments processed, {len(self.candidates)} candidates ready.",
            )
