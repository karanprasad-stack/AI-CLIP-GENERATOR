"""Unit tests for Phase 10: Production Hardening & Release Readiness."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from backend.app.services.health import HealthChecker
from backend.app.services.process_tracker import ProcessTracker
from backend.app.services.project_manager import ProjectManager
from backend.app.pipeline.downloader import classify_download_error
from backend.app.pipeline.timeline.validator import TimelineValidator
from backend.app.pipeline.timeline.models import (
    TimelineEDL,
    TimelineMetadata,
    TimelineBoundaries,
    TimelineVideoTrack,
    SubtitleItem,
    SubtitleWordItem,
    EmojiItem,
    EffectItem,
    SfxItem,
    DuckingItem,
)
from backend.app.pipeline.timeline.timeline_store import TimelineStore
from backend.app.pipeline.live.live_store import LiveStore
from backend.app.pipeline.live.models import LiveSession, LiveSegment, LiveCandidate
from backend.app.pipeline.transcriber import AudioTranscriber


class TestPhase10Hardening(TestCase):
    """Verifies all Phase 10 reliability, recovery, atomicity, and diagnostics safeguards."""

    def setUp(self):
        t_base = Path(__file__).resolve().parent.parent / "temp"
        t_base.mkdir(parents=True, exist_ok=True)
        self.test_dir = Path(tempfile.mkdtemp(prefix="phase10_test_", dir=t_base))
        self.output_dir = self.test_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 1. HealthChecker & System Diagnostics
    # --------------------------------------------------------------------------
    def test_health_checker_structure(self):
        """HealthChecker must return all diagnostic sections with valid types."""
        health = HealthChecker.get_full_health(self.output_dir)
        self.assertIn(health["status"], ["ok", "degraded"])
        self.assertIn("ffmpeg", health)
        self.assertIn("gpu", health)
        self.assertIn("storage", health)
        self.assertIn("memory", health)

        # Storage checks
        storage = health["storage"]
        self.assertTrue(storage["writable"])
        self.assertGreater(storage["total_gb"], 0.0)
        self.assertGreater(storage["free_gb"], 0.0)
        self.assertIsInstance(storage["sufficient_space"], bool)

        # Memory checks
        mem = health["memory"]
        self.assertGreater(mem["total_gb"], 0.0)
        self.assertGreater(mem["available_gb"], 0.0)
        self.assertTrue(0 <= mem["percent_used"] <= 100)

        # FFmpeg checks
        self.assertIsInstance(health["ffmpeg"]["available"], bool)

    # --------------------------------------------------------------------------
    # 2. Startup Recovery & State Reconciliation
    # --------------------------------------------------------------------------
    def test_startup_reconciliation_cleans_interrupted_projects(self):
        """Server crash/restart must reconcile transient analyzing/rendering states."""
        db_file = self.output_dir / "projects.json"
        stale_data = {
            "proj_analyzing": {
                "id": "proj_analyzing",
                "video_id": "vid1",
                "status": "analyzing",
                "progress": {"stage": "Transcribing audio"},
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "proj_rendering": {
                "id": "proj_rendering",
                "video_id": "vid2",
                "status": "rendering",
                "progress": {"stage": "Applying visual effects"},
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "proj_capturing": {
                "id": "proj_capturing",
                "video_id": "vid3",
                "status": "capturing",
                "source_type": "live_stream",
                "progress": {"stage": "Rolling capture"},
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "proj_completed": {
                "id": "proj_completed",
                "video_id": "vid4",
                "status": "completed",
                "progress": {"stage": "Done"},
                "updated_at": "2026-01-01T00:00:00Z",
            },
        }
        with open(db_file, "w", encoding="utf-8") as f:
            json.dump(stale_data, f)

        # Initialize ProjectManager, triggering _reconcile_interrupted_projects()
        pm = ProjectManager(base_output_dir=self.output_dir)

        p1 = pm.get_project("proj_analyzing")
        self.assertEqual(p1["status"], "failed")
        self.assertEqual(p1["error"]["code"], "SERVER_RESTARTED")

        p2 = pm.get_project("proj_rendering")
        self.assertEqual(p2["status"], "failed")
        self.assertEqual(p2["error"]["code"], "SERVER_RESTARTED")

        p3 = pm.get_project("proj_capturing")
        self.assertEqual(p3["status"], "ended")
        self.assertEqual(p3["error"]["code"], "SERVER_RESTARTED")

        # Completed project must NOT be altered
        p4 = pm.get_project("proj_completed")
        self.assertEqual(p4["status"], "completed")

    # --------------------------------------------------------------------------
    # 3. ProcessTracker & Cancellation Subprocess Cleanup
    # --------------------------------------------------------------------------
    def test_process_tracker_lifecycle(self):
        """ProcessTracker registers and cleanly terminates subprocess trees."""
        pid = "test_proj_proc"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Process running

        ProcessTracker.register_process(pid, mock_proc)
        self.assertIn(pid, ProcessTracker._active_processes)
        self.assertEqual(len(ProcessTracker._active_processes[pid]), 1)

        ProcessTracker.unregister_process(pid, mock_proc)
        self.assertEqual(len(ProcessTracker._active_processes[pid]), 0)

    # --------------------------------------------------------------------------
    # 4. Atomic File Operations
    # --------------------------------------------------------------------------
    def test_atomic_timeline_store_write(self):
        """TimelineStore.save_timeline writes atomically via .tmp and persists cleanly."""
        tl_store = TimelineStore()
        proj_dir = self.output_dir / "test_proj_tl"
        proj_dir.mkdir(parents=True, exist_ok=True)

        timeline = TimelineEDL(
            schema_version="1.0.0",
            project_id="test_proj_tl",
            candidate_id=1,
            version=1,
            duration=20.0,
            boundaries=TimelineBoundaries(source_in=10.0, source_out=30.0, duration=20.0),
            video_track=TimelineVideoTrack(layout="smart_crop"),
            metadata=TimelineMetadata(edit_summary="Initial"),
        )

        saved = tl_store.save_timeline(proj_dir, timeline)
        self.assertEqual(saved.version, 2)

        tl_file = proj_dir / "publishing" / "candidate_01" / "timeline.json"
        self.assertTrue(tl_file.exists())

        # Verify no .tmp file left behind
        tmp_files = list(proj_dir.glob("**/*.tmp"))
        self.assertEqual(len(tmp_files), 0)

    def test_atomic_live_store_write(self):
        """LiveStore writes session and manifest atomically."""
        proj_dir = self.output_dir / "test_live_atomic"
        l_store = LiveStore(proj_dir)

        session = LiveSession(
            session_id="sess_atomic",
            project_id="test_live_atomic",
            source_video_id="vid_atomic",
            source_url="http://stream",
            status="active",
        )
        l_store.save_session(session)
        loaded_sess = l_store.load_session()
        self.assertIsNotNone(loaded_sess)
        self.assertEqual(loaded_sess.session_id, "sess_atomic")
        self.assertTrue((proj_dir / "live" / "session.json").exists())

        # Verify no .tmp left behind
        tmp_files = list(proj_dir.glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)

    # --------------------------------------------------------------------------
    # 5. Timeline / EDL Validator Hardening
    # --------------------------------------------------------------------------
    def test_timeline_validator_duplicate_id_detection(self):
        """TimelineValidator detects and rejects duplicate IDs in subtitle tracks."""
        validator = TimelineValidator()
        timeline = TimelineEDL(
            project_id="test_val",
            candidate_id=1,
            version=1,
            duration=15.0,
            boundaries=TimelineBoundaries(source_in=0.0, source_out=15.0, duration=15.0),
            video_track=TimelineVideoTrack(layout="smart_crop"),
            subtitles_track=[
                SubtitleItem(id="sub_01", start=0.0, end=2.0, text="First subtitle"),
                SubtitleItem(id="sub_01", start=2.5, end=4.0, text="Duplicate ID subtitle"),
            ],
            metadata=TimelineMetadata(),
        )

        valid, errors = validator.validate(timeline)
        self.assertFalse(valid)
        self.assertTrue(any("Duplicate subtitle ID" in e for e in errors))

    def test_timeline_validator_boundary_and_layout_checks(self):
        """TimelineValidator rejects negative source_in and invalid video layouts."""
        validator = TimelineValidator()

        # Negative source_in
        t1 = TimelineEDL(
            project_id="test_val2",
            candidate_id=1,
            version=1,
            duration=20.0,
            boundaries=TimelineBoundaries(source_in=-5.0, source_out=15.0, duration=20.0),
            video_track=TimelineVideoTrack(layout="smart_crop"),
            metadata=TimelineMetadata(),
        )
        valid, errors = validator.validate(t1)
        self.assertFalse(valid)
        self.assertTrue(any("cannot be negative" in e for e in errors))

        # Unsupported layout
        t2 = TimelineEDL(
            project_id="test_val3",
            candidate_id=1,
            version=1,
            duration=15.0,
            boundaries=TimelineBoundaries(source_in=0.0, source_out=15.0, duration=15.0),
            video_track=TimelineVideoTrack(layout="unsupported_3d_vr_layout"),
            metadata=TimelineMetadata(),
        )
        valid, errors = validator.validate(t2)
        self.assertFalse(valid)
        self.assertTrue(any("unsupported layout" in e.lower() for e in errors))

    # --------------------------------------------------------------------------
    # 6. Download Error Classification
    # --------------------------------------------------------------------------
    def test_classify_download_error(self):
        """classify_download_error maps cryptic errors into user-friendly diagnostic messages."""
        e_private = Exception("This video is private and cannot be viewed.")
        self.assertIn("private", classify_download_error(e_private).lower())

        e_deleted = Exception("Video unavailable. This video has been removed by the user.")
        self.assertIn("deleted or unavailable", classify_download_error(e_deleted).lower())

        e_geo = Exception("The uploader has not made this video available in your country.")
        self.assertIn("geo-restricted", classify_download_error(e_geo).lower())

        e_live = Exception("This is an ongoing live stream.")
        self.assertIn("live stream", classify_download_error(e_live).lower())

        e_net = Exception("Connection timed out. Unable to reach host.")
        self.assertIn("network", classify_download_error(e_net).lower())

    # --------------------------------------------------------------------------
    # 7. Project ID Path Traversal Protection
    # --------------------------------------------------------------------------
    def test_project_id_path_traversal_rejection(self):
        """ProjectManager and validate_project_id reject malicious directory traversal strings."""
        pm = ProjectManager(base_output_dir=self.output_dir)

        malicious_ids = [
            "../../etc/passwd",
            "..\\..\\windows\\system32",
            "proj/subfolder",
            "proj;rm -rf /",
            "proj id with spaces",
            "proj<test>",
        ]

        for bad_id in malicious_ids:
            with self.assertRaises(ValueError):
                pm.get_project(bad_id)

            with self.assertRaises(ValueError):
                pm.delete_project(bad_id)

    # --------------------------------------------------------------------------
    # 8. Transcriber Memory / VRAM Safety
    # --------------------------------------------------------------------------
    def test_transcriber_unload_model(self):
        """AudioTranscriber.unload_model safely frees Whisper model from RAM/VRAM."""
        transcriber = AudioTranscriber()
        # Mock model instance
        transcriber.model = MagicMock()
        self.assertIsNotNone(transcriber.model)

        transcriber.unload_model()
        self.assertIsNone(transcriber.model)

        # Context manager support
        with AudioTranscriber() as t:
            t.model = MagicMock()
        self.assertIsNone(t.model)
