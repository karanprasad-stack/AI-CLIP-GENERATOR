"""Persistent storage, manifest management, and disk safety for live streaming sessions."""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from backend.app.config import (
    LIVE_MAX_STORAGE_MB,
    LIVE_STORAGE_WARNING_PCT,
    LIVE_MAX_RETAINED_SAFE_SEGMENTS,
    MIN_FREE_DISK_GB,
)
from backend.app.pipeline.live.models import (
    LiveSession,
    LiveSegment,
    LiveCandidate,
    LiveActivityEvent,
    LiveCandidateStatus,
)


class LiveStore:
    """Manages disk-backed persistence, manifest tracking, and storage cleanup for live sessions."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.live_dir = project_dir / "live"
        self.segments_dir = self.live_dir / "segments"
        self.transcripts_dir = self.live_dir / "transcripts"
        self.session_file = self.live_dir / "session.json"
        self.manifest_file = self.live_dir / "manifest.json"
        self.candidates_file = self.live_dir / "candidates.json"
        self.activity_file = self.live_dir / "activity.json"

        self.segments_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session: LiveSession) -> None:
        """Persists LiveSession state to disk atomically."""
        session.last_heartbeat = datetime.now(timezone.utc).isoformat()
        session.storage_used = self.compute_storage_used()
        data = session.model_dump() if hasattr(session, "model_dump") else session.dict()
        temp_file = self.session_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(self.session_file)

    def load_session(self) -> Optional[LiveSession]:
        """Loads persisted LiveSession from disk if present."""
        if not self.session_file.exists():
            return None
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return LiveSession(**data)
        except Exception:
            return None

    def save_manifest(self, segments: List[LiveSegment]) -> None:
        """Persists segment manifest atomically."""
        data = [
            s.model_dump() if hasattr(s, "model_dump") else s.dict()
            for s in segments
        ]
        temp_file = self.manifest_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(self.manifest_file)

    def load_manifest(self) -> List[LiveSegment]:
        """Loads segment manifest from disk."""
        if not self.manifest_file.exists():
            return []
        try:
            with open(self.manifest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [LiveSegment(**item) for item in data]
        except Exception:
            return []

    def save_candidates(self, candidates: List[LiveCandidate]) -> None:
        """Persists live candidates to disk atomically."""
        data = [
            c.model_dump() if hasattr(c, "model_dump") else c.dict()
            for c in candidates
        ]
        temp_file = self.candidates_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(self.candidates_file)

    def save_segment_transcript(self, segment_id: int, transcript_data: Dict[str, Any]) -> Path:
        """Saves transcript data for a specific rolling live segment atomically."""
        t_path = self.transcripts_dir / f"segment_{segment_id:04d}.json"
        temp_file = t_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)
        temp_file.replace(t_path)
        return t_path

    def load_segment_transcript(self, segment_id: int) -> Optional[Dict[str, Any]]:
        """Loads transcript data for a segment from disk if available."""
        t_path = self.transcripts_dir / f"segment_{segment_id:04d}.json"
        if not t_path.exists():
            return None
        try:
            with open(t_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def compile_candidate_transcript(
        self,
        candidate: Dict[str, Any],
        segments: List[LiveSegment],
    ) -> Dict[str, Any]:
        """
        Compiles word-level timestamps and subtitle sentences for a candidate spanning live segments.
        Maps global timestamps into coordinates relative to candidate start (0.0 to candidate duration).
        """
        cand_start = float(candidate.get("start", candidate.get("global_start", 0.0)))
        cand_end = float(candidate.get("end", candidate.get("global_end", cand_start + 45.0)))
        cand_dur = max(0.1, cand_end - cand_start)

        source_seg_ids = candidate.get("source_segments", [])
        if not source_seg_ids:
            source_seg_ids = [s.segment_id for s in segments if max(cand_start, s.global_start) < min(cand_end, s.global_end)]

        compiled_words = []
        lang = "en"

        for seg_id in sorted(source_seg_ids):
            seg = next((s for s in segments if s.segment_id == seg_id), None)
            if not seg:
                continue
            seg_trans = self.load_segment_transcript(seg_id)
            if not seg_trans:
                continue

            lang = seg_trans.get("language", lang)
            seg_global_start = seg.global_start

            for s_item in seg_trans.get("segments", []):
                for w in s_item.get("words", []):
                    w_text = w.get("word", "").strip()
                    if not w_text:
                        continue
                    w_g_start = seg_global_start + float(w.get("start", 0.0))
                    w_g_end = seg_global_start + float(w.get("end", 0.0))

                    if w_g_end >= cand_start and w_g_start <= cand_end:
                        rel_s = round(max(0.0, w_g_start - cand_start), 3)
                        rel_e = round(min(cand_dur, w_g_end - cand_start), 3)
                        if rel_e > rel_s:
                            compiled_words.append({
                                "word": w_text,
                                "start": rel_s,
                                "end": rel_e,
                                "confidence": float(w.get("confidence", 0.95)),
                            })

        # Deduplicate overlapping words by start timestamp
        unique_words = []
        seen_keys = set()
        for w in sorted(compiled_words, key=lambda x: (x["start"], x["end"])):
            key = (round(w["start"], 1), w["word"].lower())
            if key not in seen_keys:
                seen_keys.add(key)
                unique_words.append(w)

        return {
            "language": lang,
            "duration": round(cand_dur, 2),
            "words": unique_words,
            "segments": [
                {
                    "start": 0.0,
                    "end": round(cand_dur, 2),
                    "text": " ".join(w["word"] for w in unique_words),
                    "words": unique_words,
                }
            ] if unique_words else [],
        }

    def load_candidates(self) -> List[LiveCandidate]:
        """Loads live candidates from disk."""
        if not self.candidates_file.exists():
            return []
        try:
            with open(self.candidates_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [LiveCandidate(**item) for item in data]
        except Exception:
            return []

    def log_activity(
        self,
        event_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> LiveActivityEvent:
        """Appends an event to the persistent live activity feed."""
        events = self.load_activity()
        evt = LiveActivityEvent(
            id=f"act_{len(events) + 1:04d}",
            event_type=event_type,
            message=message,
            details=details or {},
        )
        events.append(evt)
        # Keep last 500 events
        if len(events) > 500:
            events = events[-500:]

        data = [
            e.model_dump() if hasattr(e, "model_dump") else e.dict()
            for e in events
        ]
        temp_file = self.activity_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(self.activity_file)
        return evt

    def load_activity(self) -> List[LiveActivityEvent]:
        """Loads persistent activity logs."""
        if not self.activity_file.exists():
            return []
        try:
            with open(self.activity_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [LiveActivityEvent(**item) for item in data]
        except Exception:
            return []

    def compute_storage_used(self) -> int:
        """Computes total storage in bytes currently consumed by the live directory."""
        if not self.live_dir.exists():
            return 0
        total = 0
        for root, _, files in os.walk(self.live_dir):
            for f in files:
                fp = Path(root) / f
                try:
                    total += fp.stat().st_size
                except OSError:
                    pass
        return total

    def check_disk_safety(self) -> Tuple[bool, Optional[str]]:
        """
        Validates available free disk space on the partition hosting the live directory.
        Returns (is_safe, warning_message).
        """
        try:
            total, used, free = shutil.disk_usage(self.live_dir)
            free_gb = free / (1024 ** 3)
            if free_gb < MIN_FREE_DISK_GB:
                return False, f"Low disk space: {free_gb:.1f} GB available (minimum {MIN_FREE_DISK_GB} GB required)"

            storage_used_mb = self.compute_storage_used() / (1024 ** 2)
            if storage_used_mb >= LIVE_MAX_STORAGE_MB:
                return False, f"Live storage limit reached: {storage_used_mb:.1f} MB used (budget {LIVE_MAX_STORAGE_MB} MB)"

            if (storage_used_mb / LIVE_MAX_STORAGE_MB) * 100 >= LIVE_STORAGE_WARNING_PCT:
                return True, f"Storage warning: {storage_used_mb:.1f} MB used ({((storage_used_mb / LIVE_MAX_STORAGE_MB) * 100):.1f}% of budget)"

            return True, None
        except Exception as e:
            return True, None

    def cleanup_safe_segments(
        self,
        segments: List[LiveSegment],
        candidates: List[LiveCandidate],
        force_budget: bool = False,
    ) -> List[int]:
        """
        Identifies and cleans up segments that are NOT required by any active or candidate moments.
        Never deletes segments referenced by candidate_id or required for rendering.
        Returns list of deleted segment_ids.
        """
        # Determine all segment IDs required by non-rejected candidates
        required_segment_ids = set()
        for cand in candidates:
            if cand.status != LiveCandidateStatus.REJECTED:
                required_segment_ids.update(cand.source_segments)

        deleted_ids: List[int] = []
        unreferenced_segments: List[LiveSegment] = []

        for seg in segments:
            if seg.segment_id in required_segment_ids or seg.status == "analyzing":
                continue
            if seg.status in ("analyzed", "cleanup_safe"):
                unreferenced_segments.append(seg)

        # Retain latest N safe segments for narrative continuity; clean older unreferenced ones
        storage_mb = self.compute_storage_used() / (1024 ** 2)
        should_clean = force_budget or (storage_mb > LIVE_MAX_STORAGE_MB * 0.8) or (len(unreferenced_segments) > LIVE_MAX_RETAINED_SAFE_SEGMENTS)

        if should_clean and len(unreferenced_segments) > LIVE_MAX_RETAINED_SAFE_SEGMENTS:
            to_remove = unreferenced_segments[:-LIVE_MAX_RETAINED_SAFE_SEGMENTS]
            for seg in to_remove:
                # Remove media files on disk
                for fpath_str in [seg.video_file, seg.audio_file, seg.transcript_file]:
                    if fpath_str:
                        p = Path(fpath_str)
                        if p.exists() and p.is_file():
                            try:
                                p.unlink(missing_ok=True)
                            except OSError:
                                pass
                seg.status = "deleted"
                deleted_ids.append(seg.segment_id)

        return deleted_ids
