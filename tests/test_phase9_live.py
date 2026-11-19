"""Unit tests for Phase 9: Dual Source + Live Stream Clipping."""

import unittest
import tempfile
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

from backend.app.config import (
    SOURCE_TYPE_NORMAL,
    SOURCE_TYPE_LIVE,
    LIVE_SEGMENT_DURATION_SEC,
    LIVE_SEGMENT_OVERLAP_SEC,
    MAX_CANDIDATE_DURATION,
)
from backend.app.pipeline.live.models import (
    LiveSession,
    LiveSegment,
    LiveCandidate,
    LiveSessionStatus,
    LiveCandidateStatus,
    LiveActivityEvent,
)
from backend.app.pipeline.live.live_store import LiveStore
from backend.app.pipeline.live.capture_engine import LiveCaptureEngine
from backend.app.pipeline.live.candidate_engine import LiveCandidateEngine
from backend.app.pipeline.live.source_resolver import LiveSourceResolver
from backend.app.services.project_manager import ProjectManager


class TestSourceSelection(unittest.TestCase):
    """Test project source selection: normal video vs live stream."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.pm = ProjectManager(base_output_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normal_video_project_creation(self):
        proj = self.pm.create_project(
            url="https://www.youtube.com/watch?v=EdtUDpqjltA",
            source_type=SOURCE_TYPE_NORMAL,
        )
        self.assertEqual(proj["source_type"], SOURCE_TYPE_NORMAL)
        self.assertEqual(proj["status"], "queued")
        self.assertIsNone(proj.get("live_session_info"))

    def test_live_stream_project_creation(self):
        proj = self.pm.create_project(
            url="https://www.youtube.com/watch?v=liveStream01",
            source_type=SOURCE_TYPE_LIVE,
            title="Active Tournament Stream",
        )
        self.assertEqual(proj["source_type"], SOURCE_TYPE_LIVE)
        self.assertEqual(proj["status"], "idle")
        self.assertIsNotNone(proj.get("live_session_info"))
        self.assertEqual(proj["live_session_info"]["status"], "idle")


class TestLiveSegmentationAndTimestamps(unittest.TestCase):
    """Test rolling segmentation math and local-to-global timestamp conversion."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = LiveCaptureEngine(
            live_dir=self.temp_dir,
            segment_duration=90.0,
            segment_overlap=30.0,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_segment_timestamp_calculation(self):
        # Step size = 90 - 30 = 60s
        g_start1, g_end1, dur1 = self.engine.compute_segment_timestamps(1)
        self.assertEqual(g_start1, 0.0)
        self.assertEqual(g_end1, 90.0)
        self.assertEqual(dur1, 90.0)

        g_start2, g_end2, dur2 = self.engine.compute_segment_timestamps(2)
        self.assertEqual(g_start2, 60.0)
        self.assertEqual(g_end2, 150.0)
        self.assertEqual(dur2, 90.0)

        g_start3, g_end3, dur3 = self.engine.compute_segment_timestamps(3)
        self.assertEqual(g_start3, 120.0)
        self.assertEqual(g_end3, 210.0)
        self.assertEqual(dur3, 90.0)

    def test_reconnect_backoff_calculation(self):
        delay1 = self.engine.calculate_backoff_delay(1)
        delay2 = self.engine.calculate_backoff_delay(2)
        delay3 = self.engine.calculate_backoff_delay(3)
        self.assertTrue(1.0 <= delay1 <= 3.0)
        self.assertTrue(delay2 > delay1)
        self.assertTrue(delay3 > delay2)


class TestCrossSegmentCandidateMerging(unittest.TestCase):
    """Test boundary merging for candidates spanning across rolling segments."""

    def setUp(self):
        self.candidate_engine = LiveCandidateEngine()

    def test_cross_segment_merge(self):
        existing_candidate = LiveCandidate(
            candidate_id=1,
            global_start=45.0,
            global_end=85.0,
            duration=40.0,
            score=82.0,
            status=LiveCandidateStatus.DETECTED,
            source_segments=[1],
            event="clutch_setup",
            signals=["volume_spike"],
        )

        # Segment 2 spans 60.0s -> 150.0s (overlap region is 60.0s -> 90.0s)
        seg2 = LiveSegment(
            segment_id=2,
            local_start=0.0,
            local_end=90.0,
            global_start=60.0,
            global_end=150.0,
            duration=90.0,
            video_file="dummy2.mp4",
        )

        # Incoming candidate in Segment 2 that continues the climax (local 20s -> 50s = global 80s -> 110s)
        incoming_candidate = {
            "start": 80.0,
            "end": 110.0,
            "duration": 30.0,
            "final_score": 88.5,
            "gameplay_event": "headshot_kill",
            "strongest_reaction": "insane timing",
            "signals": ["cheering", "headshot"],
            "source_segments": [2],
        }

        updated_pool, logs = self.candidate_engine.merge_and_update_candidates(
            existing_pool=[existing_candidate],
            new_candidates=[incoming_candidate],
            segment=seg2,
        )

        # Candidate should have been merged rather than duplicated
        self.assertEqual(len(updated_pool), 1)
        merged = updated_pool[0]
        self.assertEqual(merged.candidate_id, 1)
        self.assertEqual(merged.global_start, 50.0)  # clamped to 60s max short window
        self.assertEqual(merged.global_end, 110.0)
        self.assertEqual(merged.duration, 60.0)
        self.assertEqual(merged.source_segments, [1, 2])
        self.assertIn("clutch_setup", [merged.event, incoming_candidate.get("gameplay_event")])
        self.assertEqual(merged.reaction, "insane timing")
        self.assertTrue(any("merged" in log.lower() for log in logs))

    def test_non_overlapping_candidates_remain_distinct(self):
        cand1 = LiveCandidate(
            candidate_id=1,
            global_start=10.0,
            global_end=45.0,
            duration=35.0,
            score=80.0,
            source_segments=[1],
        )

        seg3 = LiveSegment(
            segment_id=3,
            local_start=0.0,
            local_end=90.0,
            global_start=120.0,
            global_end=210.0,
            duration=90.0,
            video_file="dummy3.mp4",
        )

        cand2 = {
            "start": 140.0,
            "end": 175.0,
            "duration": 35.0,
            "final_score": 78.0,
            "source_segments": [3],
        }

        updated_pool, logs = self.candidate_engine.merge_and_update_candidates(
            existing_pool=[cand1],
            new_candidates=[cand2],
            segment=seg3,
        )

        self.assertEqual(len(updated_pool), 2)
        self.assertEqual(updated_pool[0].candidate_id, 1)
        self.assertEqual(updated_pool[1].candidate_id, 2)


class TestLivePersistenceAndStorage(unittest.TestCase):
    """Test disk persistence, manifest tracking, and bounded safe storage cleanup."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = LiveStore(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_session_persistence_and_reload(self):
        session = LiveSession(
            session_id="live_test_01",
            project_id="proj_01",
            source_url="https://youtube.com/live/xyz",
            source_video_id="xyz",
            status=LiveSessionStatus.LIVE,
            total_segments=5,
            segments_processed=4,
        )
        self.store.save_session(session)

        reloaded = self.store.load_session()
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.session_id, "live_test_01")
        self.assertEqual(reloaded.status, LiveSessionStatus.LIVE)
        self.assertEqual(reloaded.segments_processed, 4)

    def test_safe_cleanup_preserves_candidate_segments(self):
        # Create dummy segment files
        seg1_file = self.store.segments_dir / "seg1.mp4"
        seg2_file = self.store.segments_dir / "seg2.mp4"
        seg1_file.write_bytes(b"A" * 1024)
        seg2_file.write_bytes(b"B" * 1024)

        seg1 = LiveSegment(
            segment_id=1,
            local_start=0.0,
            local_end=90.0,
            global_start=0.0,
            global_end=90.0,
            duration=90.0,
            video_file=str(seg1_file),
            status="analyzed",
        )
        seg2 = LiveSegment(
            segment_id=2,
            local_start=0.0,
            local_end=90.0,
            global_start=60.0,
            global_end=150.0,
            duration=90.0,
            video_file=str(seg2_file),
            status="analyzed",
        )

        # Candidate requires segment 2
        cand = LiveCandidate(
            candidate_id=1,
            global_start=70.0,
            global_end=110.0,
            duration=40.0,
            score=85.0,
            status=LiveCandidateStatus.PUBLISH_READY,
            source_segments=[2],
        )

        # Seg 2 must NOT be deleted even if cleanup runs
        deleted = self.store.cleanup_safe_segments(
            segments=[seg1, seg2],
            candidates=[cand],
            force_budget=False,
        )
        self.assertNotIn(2, deleted)
        self.assertTrue(seg2_file.exists())

    def test_activity_logging(self):
        evt = self.store.log_activity("live_candidate_detected", "Candidate #1 found")
        self.assertEqual(evt.event_type, "live_candidate_detected")

        activities = self.store.load_activity()
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0].message, "Candidate #1 found")


class TestLiveQualityGating(unittest.TestCase):
    """Test that weak moments are rejected and strong moments are marked publish_ready."""

    def setUp(self):
        self.candidate_engine = LiveCandidateEngine()

    def test_quality_gating_classification(self):
        strong_cand = LiveCandidate(
            candidate_id=1,
            global_start=20.0,
            global_end=55.0,
            duration=35.0,
            score=86.0,
            status=LiveCandidateStatus.DETECTED,
            event="ace_clutch",
            reaction="unbelievable",
            signals=["volume_peak", "headshot"],
        )
        weak_cand = LiveCandidate(
            candidate_id=2,
            global_start=120.0,
            global_end=155.0,
            duration=35.0,
            score=38.0,
            status=LiveCandidateStatus.DETECTED,
            event=None,
            reaction=None,
            signals=[],
        )

        self.candidate_engine._evaluate_quality_gating([strong_cand, weak_cand])

        # Strong candidate should be ready or review
        self.assertIn(strong_cand.status, [LiveCandidateStatus.PUBLISH_READY, LiveCandidateStatus.REVIEW])
        self.assertIsNotNone(strong_cand.publishability)
        self.assertIn(strong_cand.publishability.get("recommendation"), ["publish", "review"])

        # Weak candidate should be rejected
        self.assertEqual(weak_cand.status, LiveCandidateStatus.REJECTED)
        self.assertEqual(weak_cand.publishability.get("recommendation"), "reject")


class TestSourceResolverRangeMatching(unittest.TestCase):
    """Test source resolver segment identification and range intersection."""

    def setUp(self):
        self.resolver = LiveSourceResolver()
        self.segments = [
            LiveSegment(
                segment_id=1,
                local_start=0.0,
                local_end=90.0,
                global_start=0.0,
                global_end=90.0,
                duration=90.0,
                video_file="seg1.mp4",
                status="analyzed",
            ),
            LiveSegment(
                segment_id=2,
                local_start=0.0,
                local_end=90.0,
                global_start=60.0,
                global_end=150.0,
                duration=90.0,
                video_file="seg2.mp4",
                status="analyzed",
            ),
            LiveSegment(
                segment_id=3,
                local_start=0.0,
                local_end=90.0,
                global_start=120.0,
                global_end=210.0,
                duration=90.0,
                video_file="seg3.mp4",
                status="analyzed",
            ),
        ]

    def test_find_segments_single(self):
        matching = self.resolver.find_segments_for_range(20.0, 50.0, self.segments)
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].segment_id, 1)

    def test_find_segments_crossing(self):
        # 75.0 to 135.0 spans segment 1, 2, and 3
        matching = self.resolver.find_segments_for_range(75.0, 135.0, self.segments)
        self.assertTrue(len(matching) >= 2)
        matched_ids = [s.segment_id for s in matching]
        self.assertIn(1, matched_ids)
        self.assertIn(2, matched_ids)


class TestLiveSessionOrchestration(unittest.TestCase):
    """Test live orchestrator controls, event callbacks, and status transitions."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.pm = ProjectManager(base_output_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_live_session_controls_and_status(self):
        proj = self.pm.create_project(
            url="https://www.youtube.com/watch?v=liveStream99",
            source_type=SOURCE_TYPE_LIVE,
        )
        pid = proj["id"]

        status_init = self.pm.get_live_status(pid)
        self.assertEqual(status_init["project_id"], pid)
        self.assertEqual(status_init["candidates_count"], 0)

        # Pause and resume
        res_pause = self.pm.pause_live_session(pid)
        self.assertIn(res_pause["status"], ["paused", "not_active"])

        # Stop
        res_stop = self.pm.stop_live_session(pid)
        self.assertIn(res_stop["status"], ["stopping", "stopped"])
        self.assertEqual(self.pm.get_project(pid)["status"], "ended")


class TestLiveTimelineHardeningAndTrackPreservation(unittest.TestCase):
    """Test Phase 9.1 track preservation, quality stale invalidation, and complete EDL synthesis."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.pm = ProjectManager(base_output_dir=self.temp_dir)
        self.proj = self.pm.create_project(
            url="https://www.youtube.com/watch?v=liveStreamHarden",
            source_type=SOURCE_TYPE_LIVE,
        )
        self.pid = self.proj["id"]
        self.proj_dir = self.temp_dir / self.pid

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_track_preservation_on_subtitle_edit(self):
        # Create initial candidate with quality info
        cand_dict = {
            "candidate_id": 1,
            "rank": 1,
            "start": 0.0,
            "end": 45.0,
            "duration": 45.0,
            "final_score": 85.0,
            "gameplay_event": "clutch_kill",
            "strongest_reaction": "insane",
            "signals": {"audio_peaks": 2, "gaming_terms": 3},
            "detected_signals": ["headshot@12.5s", "clutch@34.0s"],
            "publishability": {
                "score": 85.0,
                "level": "strong",
                "recommendation": "publish",
                "quality_stale": False,
            },
        }
        self.pm._projects[self.pid]["candidates"] = [cand_dict]
        self.pm._save_projects()

        # Build initial multi-track timeline data
        from backend.app.pipeline.timeline import (
            TimelineEDL, TimelineBoundaries, TimelineVideoTrack,
            SubtitleItem, SubtitleWordItem, EffectItem, SfxItem, DuckingItem,
            TimelineMetadata, TimelineStore
        )

        initial_edl = TimelineEDL(
            project_id=self.pid,
            candidate_id=1,
            version=1,
            duration=45.0,
            boundaries=TimelineBoundaries(source_in=0.0, source_out=45.0, duration=45.0),
            video_track=TimelineVideoTrack(source_file="source.mp4", layout="smart_crop", resolution="1080x1920", fps=60),
            subtitles_track=[
                SubtitleItem(id=f"sub_{i:02d}", start=float(i*6), end=float(i*6+4), text=f"Subtitle line {i}", words=[SubtitleWordItem(word="Line", start=float(i*6), end=float(i*6+2))], language="en")
                for i in range(1, 6)
            ],
            effects_track=[
                EffectItem(id=f"eff_{i:02d}", type="subtle_zoom", start=float(i*10), end=float(i*10+2), intensity=0.5)
                for i in range(1, 4)
            ],
            sfx_track=[
                SfxItem(id=f"sfx_{i:02d}", timestamp=float(i*12), event_type="whoosh", asset_name="whoosh_soft.wav")
                for i in range(1, 3)
            ],
            ducking_track=[
                DuckingItem(id=f"duck_{i:02d}", start=float(i*8), end=float(i*8+3), attenuation_db=-3.5)
                for i in range(1, 5)
            ],
            metadata=TimelineMetadata(created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z", source="ai", dirty_tracks=[]),
        )

        tl_store = TimelineStore()
        tl_store.save_timeline(self.proj_dir, initial_edl, increment_version=False)

        # Verify initial counts: 5 subtitles, 3 effects, 2 sfx, 4 ducking
        edl_loaded = self.pm.get_timeline(self.pid, 1)
        self.assertEqual(len(edl_loaded["subtitles_track"]), 5)
        self.assertEqual(len(edl_loaded["effects_track"]), 3)
        self.assertEqual(len(edl_loaded["sfx_track"]), 2)
        self.assertEqual(len(edl_loaded["ducking_track"]), 4)

        # Perform single-track human edit on subtitle #2
        edl_loaded["subtitles_track"][1]["text"] = "THAT TIMING WAS INSANE! 🔥"

        saved = self.pm.save_timeline(self.pid, 1, edl_loaded)

        # Assert track preservation
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["metadata"]["dirty_tracks"], ["subtitles"])
        self.assertEqual(saved["subtitles_track"][1]["text"], "THAT TIMING WAS INSANE! 🔥")
        # Unrelated tracks remain intact
        self.assertEqual(len(saved["subtitles_track"]), 5)
        self.assertEqual(len(saved["effects_track"]), 3)
        self.assertEqual(len(saved["sfx_track"]), 2)
        self.assertEqual(len(saved["ducking_track"]), 4)
        self.assertEqual([e["id"] for e in saved["effects_track"]], ["eff_01", "eff_02", "eff_03"])
        self.assertEqual([s["id"] for s in saved["sfx_track"]], ["sfx_01", "sfx_02"])
        self.assertEqual([d["id"] for d in saved["ducking_track"]], ["duck_01", "duck_02", "duck_03", "duck_04"])

        # Assert Creator Quality was marked stale and flagged for review
        fresh_proj = self.pm.get_project(self.pid)
        cand_after = fresh_proj["candidates"][0]
        self.assertTrue(cand_after["publishability"]["quality_stale"])
        self.assertEqual(cand_after["publishability"]["recommendation"], "review")

    def test_live_transcript_compilation_from_segments(self):
        # Create segment transcripts in live store
        from backend.app.pipeline.live.live_store import LiveStore
        from backend.app.pipeline.live.models import LiveSegment
        l_store = LiveStore(self.proj_dir)

        seg1 = LiveSegment(segment_id=1, local_start=0.0, local_end=45.0, global_start=0.0, global_end=45.0, duration=45.0, video_file="seg1.mp4")
        seg2 = LiveSegment(segment_id=2, local_start=0.0, local_end=45.0, global_start=30.0, global_end=75.0, duration=45.0, video_file="seg2.mp4")

        # Save segment transcripts
        t1 = {
            "language": "en",
            "segments": [{
                "start": 10.0, "end": 15.0, "text": "talk about timing",
                "words": [
                    {"word": "talk", "start": 10.0, "end": 11.0},
                    {"word": "about", "start": 11.0, "end": 12.0},
                    {"word": "timing", "start": 12.0, "end": 13.5},
                ]
            }]
        }
        t2 = {
            "language": "en",
            "segments": [{
                "start": 10.0, "end": 16.0, "text": "that was insane",
                "words": [
                    {"word": "that", "start": 10.0, "end": 11.5},
                    {"word": "was", "start": 11.5, "end": 12.5},
                    {"word": "insane", "start": 12.5, "end": 14.0},
                ]
            }]
        }
        l_store.save_segment_transcript(1, t1)
        l_store.save_segment_transcript(2, t2)

        # Candidate covering 5.0s to 50.0s (spans seg 1 and seg 2)
        cand = {"start": 5.0, "end": 50.0, "duration": 45.0, "source_segments": [1, 2]}
        compiled = l_store.compile_candidate_transcript(cand, [seg1, seg2])

        self.assertEqual(compiled["language"], "en")
        self.assertTrue(len(compiled["words"]) >= 3)
        # Words should be offset relative to candidate start (5.0s)
        # "talk" was at 10.0s global, so rel_start should be 10.0 - 5.0 = 5.0s
        talk_word = next((w for w in compiled["words"] if w["word"] == "talk"), None)
        self.assertIsNotNone(talk_word)
        self.assertEqual(talk_word["start"], 5.0)


if __name__ == "__main__":
    unittest.main()
