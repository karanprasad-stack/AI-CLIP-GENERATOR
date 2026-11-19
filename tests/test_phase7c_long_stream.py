"""Tests for Phase 7C: Long-Stream Intelligence Engine.

Covers:
- Long stream classification
- Chunk planning & boundary overlap handling
- Trailing partial chunk merging
- Local-to-global timestamp conversion (transcript & audio)
- Global candidate aggregation & ranking
- Temporal deduplication (IoU, overlap threshold, nested candidate resolution)
- Temporal and narrative diversity selection
- Quality gating (Auto mode, Custom mode, score cliffs, transparent reasons)
- Chunk store persistence, resumability, and checkpointing
- Disk safety and bounded resource rules
"""

import tempfile
import unittest
from pathlib import Path

from backend.app.config import (
    LONG_STREAM_THRESHOLD_SEC,
    CHUNK_DURATION_SEC,
    CHUNK_OVERLAP_SEC,
)
from backend.app.pipeline.long_stream.chunk_planner import (
    ChunkPlan,
    ChunkPlanner,
    is_long_stream,
    plan_chunks,
)
from backend.app.pipeline.long_stream.chunk_processor import (
    convert_transcript_to_global_time,
    convert_audio_analysis_to_global_time,
    check_disk_space,
    DiskSpaceError,
)
from backend.app.pipeline.long_stream.chunk_store import ChunkStore
from backend.app.pipeline.long_stream.global_ranker import GlobalRanker
from backend.app.pipeline.long_stream.temporal_deduper import (
    TemporalDeduper,
    compute_overlap,
    is_nested,
)
from backend.app.pipeline.long_stream.diversity_selector import DiversitySelector
from backend.app.pipeline.long_stream.quality_gate import QualityGate, find_natural_score_gap


class TestPhase7CLongStream(unittest.TestCase):
    """Unit test suite for Phase 7C Long-Stream Intelligence."""

    # --------------------------------------------------------------------------
    # 1. Long Stream Detection & Classification
    # --------------------------------------------------------------------------
    def test_long_stream_detection(self):
        """Validates configurable duration threshold classification."""
        self.assertFalse(is_long_stream(500.0))
        self.assertFalse(is_long_stream(1799.9))
        self.assertTrue(is_long_stream(1800.0))
        self.assertTrue(is_long_stream(18000.0))  # 5 hours

        # Custom threshold override
        self.assertTrue(is_long_stream(600.0, threshold=600.0))
        self.assertFalse(is_long_stream(599.0, threshold=600.0))

    # --------------------------------------------------------------------------
    # 2. Chunk Planning & Temporal Boundaries
    # --------------------------------------------------------------------------
    def test_chunk_planner_short_video(self):
        """Short video under chunk_duration results in a single non-overlapping chunk."""
        chunks = plan_chunks(source_duration=350.0, chunk_duration=600.0)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "chunk_0001")
        self.assertEqual(chunks[0].source_start, 0.0)
        self.assertEqual(chunks[0].source_end, 350.0)
        self.assertEqual(chunks[0].duration, 350.0)

    def test_chunk_planner_multi_hour_stream(self):
        """5-hour stream (18,000s) partitions into correctly overlapping chunks."""
        duration = 18000.0  # 5 hours
        chunks = plan_chunks(source_duration=duration, chunk_duration=600.0, overlap=45.0)

        self.assertGreater(len(chunks), 25)
        # Verify first chunk
        self.assertEqual(chunks[0].source_start, 0.0)
        self.assertEqual(chunks[0].source_end, 600.0)
        self.assertEqual(chunks[0].overlap_start, 0.0)
        self.assertEqual(chunks[0].overlap_end, 45.0)

        # Verify second chunk overlaps by 45s
        self.assertEqual(chunks[1].source_start, 555.0)  # 600 - 45
        self.assertEqual(chunks[1].overlap_start, 45.0)

        # Verify last chunk covers exact source_duration
        self.assertEqual(chunks[-1].source_end, duration)
        for c in chunks:
            self.assertGreater(c.source_end, c.source_start)
            self.assertLessEqual(c.source_end, duration)

    def test_chunk_planner_trailing_partial_chunk(self):
        """Avoids creating tiny stub chunks at the end of a video."""
        # 630s with 600s chunk duration leaves a 30s remainder (< 60s min_chunk_duration)
        chunks = plan_chunks(source_duration=630.0, chunk_duration=600.0, overlap=45.0, min_chunk_duration=60.0)
        # Should merge remainder into chunk 1 rather than creating a 30s stub
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].source_end, 630.0)
        self.assertEqual(chunks[0].duration, 630.0)

    # --------------------------------------------------------------------------
    # 3. Local-to-Global Timestamp Conversion
    # --------------------------------------------------------------------------
    def test_convert_transcript_to_global_time(self):
        """Verifies local chunk word and segment timestamps shift accurately to global source time."""
        raw_transcript = {
            "language": "en",
            "duration": 600.0,
            "segments": [
                {
                    "start": 10.5,
                    "end": 14.2,
                    "text": "Look at this clutch!",
                    "words": [
                        {"start": 10.5, "end": 11.2, "word": "Look"},
                        {"start": 11.3, "end": 12.0, "word": "at"},
                        {"start": 12.1, "end": 14.2, "word": "clutch!"},
                    ],
                }
            ],
        }

        # Chunk starts at 1 hour in (3600.0s)
        global_trans = convert_transcript_to_global_time(raw_transcript, offset_sec=3600.0)

        self.assertEqual(global_trans["segments"][0]["start"], 3610.5)
        self.assertEqual(global_trans["segments"][0]["end"], 3614.2)
        self.assertEqual(global_trans["segments"][0]["words"][0]["start"], 3610.5)
        self.assertEqual(global_trans["segments"][0]["words"][2]["word"], "clutch!")
        self.assertEqual(global_trans["segments"][0]["words"][2]["start"], 3612.1)
        self.assertEqual(global_trans["segments"][0]["words"][2]["end"], 3614.2)

    def test_convert_audio_analysis_to_global_time(self):
        """Verifies audio peaks and timeline shift accurately to global source time."""
        raw_audio = {
            "duration": 600.0,
            "global_mean_rms": 0.05,
            "global_std_rms": 0.02,
            "peaks": [
                {"timestamp": 25.4, "rms": 0.18, "z_score": 3.4},
            ],
            "timeline": [
                {"t": 0.0, "rms": 0.01},
                {"t": 0.5, "rms": 0.03},
            ],
            "silence_intervals": [
                (5.0, 8.0),
            ],
        }

        global_audio = convert_audio_analysis_to_global_time(raw_audio, offset_sec=7200.0)

        self.assertEqual(global_audio["peaks"][0]["timestamp"], 7225.4)
        self.assertEqual(global_audio["timeline"][1]["t"], 7200.5)
        self.assertEqual(global_audio["silence_intervals"][0], (7205.0, 7208.0))

    # --------------------------------------------------------------------------
    # 4. Global Ranking & Score Normalization
    # --------------------------------------------------------------------------
    def test_global_ranking_transparent_invariants(self):
        """Verifies cross-chunk global ranking maintains transparent score invariants."""
        ranker = GlobalRanker()

        candidates = [
            {
                "candidate_id": 1,
                "chunk_id": "chunk_0001",
                "start": 100.0,
                "end": 145.0,
                "duration": 45.0,
                "component_scores": {
                    "audio": 80.0,
                    "transcript": 70.0,
                    "gameplay_event": 90.0,
                    "context": 85.0,
                    "boundary": 75.0,
                },
            },
            {
                "candidate_id": 2,
                "chunk_id": "chunk_0012",
                "start": 7250.0,
                "end": 7295.0,
                "duration": 45.0,
                "component_scores": {
                    "audio": 95.0,
                    "transcript": 85.0,
                    "gameplay_event": 95.0,
                    "context": 90.0,
                    "boundary": 85.0,
                },
            },
        ]

        ranked = ranker.calibrate_and_rank(candidates)

        # Higher scoring candidate from chunk_0012 must take rank 1
        self.assertEqual(ranked[0]["chunk_id"], "chunk_0012")
        self.assertEqual(ranked[0]["global_rank"], 1)
        self.assertGreater(ranked[0]["final_score"], ranked[1]["final_score"])

        # Check invariant: final_score = weighted sum
        for c in ranked:
            scores = c["component_scores"]
            expected = round(
                0.25 * scores["audio"]
                + 0.20 * scores["transcript"]
                + 0.25 * scores["gameplay_event"]
                + 0.20 * scores["context"]
                + 0.10 * scores["boundary"],
                1,
            )
            self.assertAlmostEqual(c["final_score"], expected, places=1)

    # --------------------------------------------------------------------------
    # 5. Temporal Deduplication & Nested Candidates
    # --------------------------------------------------------------------------
    def test_temporal_overlap_and_deduplication(self):
        """Identical or heavily overlapping candidates from adjacent chunks are merged."""
        deduper = TemporalDeduper(iou_threshold=0.50, max_overlap_sec=18.0)

        # Cand 1 from chunk 1 (550 -> 595s)
        # Cand 2 from chunk 2 (555 -> 598s) (near-identical moment across overlap)
        cand1 = {"start": 550.0, "end": 595.0, "duration": 45.0, "final_score": 88.0}
        cand2 = {"start": 555.0, "end": 598.0, "duration": 43.0, "final_score": 82.0}

        inter, union, iou = compute_overlap(cand1, cand2)
        self.assertGreater(iou, 0.70)
        self.assertGreater(inter, 35.0)

        deduped = deduper.deduplicate([cand1, cand2])
        self.assertEqual(len(deduped), 1)
        # Higher scoring candidate retained
        self.assertEqual(deduped[0]["final_score"], 88.0)

    def test_distinct_nearby_events_not_pruned(self):
        """Distinct moments that happen near each other with low overlap are preserved."""
        deduper = TemporalDeduper(iou_threshold=0.50, max_overlap_sec=18.0)

        cand1 = {"start": 1000.0, "end": 1040.0, "duration": 40.0, "final_score": 85.0}
        cand2 = {"start": 1045.0, "end": 1085.0, "duration": 40.0, "final_score": 82.0}

        deduped = deduper.deduplicate([cand1, cand2])
        self.assertEqual(len(deduped), 2)

    def test_nested_candidate_resolution(self):
        """Tests intelligent nested candidate resolution."""
        deduper = TemporalDeduper()

        # Wide candidate (100 -> 160s, 60s) vs tight candidate (115 -> 145s, 30s)
        wide = {
            "start": 100.0,
            "end": 160.0,
            "duration": 60.0,
            "final_score": 78.0,
            "component_scores": {"context": 60.0},
        }
        tight = {
            "start": 115.0,
            "end": 145.0,
            "duration": 30.0,
            "final_score": 86.0,
            "component_scores": {"context": 62.0},
        }

        is_nest, outer, inner = is_nested(wide, tight)
        self.assertTrue(is_nest)
        self.assertEqual(outer, wide)
        self.assertEqual(inner, tight)

        deduped = deduper.deduplicate([wide, tight])
        self.assertEqual(len(deduped), 1)
        # Tighter, higher scoring moment preferred
        self.assertEqual(deduped[0]["final_score"], 86.0)

    # --------------------------------------------------------------------------
    # 6. Diversity Selection
    # --------------------------------------------------------------------------
    def test_temporal_diversity_selection(self):
        """Prevents clustering all recommended Shorts into one tiny time section."""
        selector = DiversitySelector(min_temporal_gap_sec=90.0)

        # 4 high-scoring moments clustered between 100s and 180s
        # 1 moment at 3600s, 1 moment at 7200s
        candidates = [
            {"candidate_id": 1, "start": 100.0, "final_score": 88.0, "gameplay_event": "clutch"},
            {"candidate_id": 2, "start": 115.0, "final_score": 87.0, "gameplay_event": "clutch"},
            {"candidate_id": 3, "start": 130.0, "final_score": 86.0, "gameplay_event": "clutch"},
            {"candidate_id": 4, "start": 145.0, "final_score": 85.0, "gameplay_event": "clutch"},
            {"candidate_id": 5, "start": 3600.0, "final_score": 82.0, "gameplay_event": "funny fail"},
            {"candidate_id": 6, "start": 7200.0, "final_score": 80.0, "gameplay_event": "ace"},
        ]

        selected = selector.select_diverse(candidates, target_count=3)
        self.assertEqual(len(selected), 3)

        # Must pick top moment from first cluster (id=1), then pick diverse moments from 3600s and 7200s
        starts = [s["start"] for s in selected]
        self.assertIn(100.0, starts)
        self.assertIn(3600.0, starts)
        self.assertIn(7200.0, starts)

    # --------------------------------------------------------------------------
    # 7. Quality Gate (Auto & Custom Mode)
    # --------------------------------------------------------------------------
    def test_quality_gate_score_cliff_auto_mode(self):
        """Auto mode cuts off at a natural quality cliff rather than returning weak moments."""
        qgate = QualityGate(min_score=55.0, strong_score=70.0, score_gap_threshold=8.0)

        candidates = [
            {"rank": 1, "final_score": 92.0},
            {"rank": 2, "final_score": 89.0},
            {"rank": 3, "final_score": 86.0},
            {"rank": 4, "final_score": 84.0},
            {"rank": 5, "final_score": 62.0},  # Huge drop from 84 to 62 (22 pt gap!)
            {"rank": 6, "final_score": 58.0},
            {"rank": 7, "final_score": 56.0},
        ]

        scores = [c["final_score"] for c in candidates]
        gap_idx = find_natural_score_gap(scores, min_index=3, threshold=8.0)
        self.assertEqual(gap_idx, 4)

        recommended, explanation = qgate.evaluate(candidates, num_shorts_mode="auto")
        self.assertEqual(len(recommended), 4)
        for r in recommended:
            self.assertGreaterEqual(r["final_score"], 80.0)

    def test_quality_gate_custom_mode_ceiling(self):
        """Custom mode treats requested count as maximum and refuses to manufacture weak Shorts."""
        qgate = QualityGate(min_score=60.0, strong_score=70.0)

        # User asks for 8 Shorts, but only 3 pass quality threshold
        candidates = [
            {"rank": 1, "final_score": 88.0},
            {"rank": 2, "final_score": 78.0},
            {"rank": 3, "final_score": 65.0},
            {"rank": 4, "final_score": 45.0},  # Weak
            {"rank": 5, "final_score": 38.0},  # Weak
        ]

        recommended, explanation = qgate.evaluate(
            candidates, num_shorts_mode="custom", requested_count=8
        )

        self.assertEqual(len(recommended), 3)
        self.assertIn("3 Shorts (out of 8 requested)", explanation)

    # --------------------------------------------------------------------------
    # 8. Chunk Store Persistence & Checkpoint Resumability
    # --------------------------------------------------------------------------
    def test_chunk_store_resumability(self):
        """Validates that completed chunks are loaded from disk and skipped on resume."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)
            store = ChunkStore(project_dir)

            plans = [
                ChunkPlan("chunk_0001", 1, 0.0, 600.0, 600.0),
                ChunkPlan("chunk_0002", 2, 555.0, 1155.0, 600.0),
                ChunkPlan("chunk_0003", 3, 1110.0, 1710.0, 600.0),
            ]

            manifest = store.init_manifest(plans, "test_vid", 1710.0, 600.0, 45.0)
            self.assertEqual(manifest["total_chunks"], 3)

            # Simulate completing chunk 1
            chunk1_result = {
                "chunk_id": "chunk_0001",
                "status": "completed",
                "source_start": 0.0,
                "source_end": 600.0,
                "candidates": [{"candidate_id": 101, "final_score": 85.0}],
            }
            store.save_chunk_result("chunk_0001", chunk1_result)

            # Check that chunk 1 is detected as completed
            self.assertTrue(store.is_chunk_completed("chunk_0001"))
            self.assertFalse(store.is_chunk_completed("chunk_0002"))

            # Resume plan
            reconciled, reused = store.get_resumable_plan(plans)
            self.assertEqual(reused, 1)
            self.assertEqual(reconciled[0].status, "completed")
            self.assertEqual(reconciled[1].status, "pending")

            # Collect candidates
            cands = store.collect_all_candidates()
            self.assertEqual(len(cands), 1)
            self.assertEqual(cands[0]["candidate_id"], 101)

    # --------------------------------------------------------------------------
    # 9. Storage Safety Checks
    # --------------------------------------------------------------------------
    def test_disk_space_guard(self):
        """Validates that check_disk_space raises DiskSpaceError if limits are breached."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            p = Path(tmp_dir)
            # Normal check succeeds
            check_disk_space(p, min_free_gb=0.01, max_usage_pct=99.9)

            # Unreasonable requirement fails gracefully
            with self.assertRaises(DiskSpaceError):
                check_disk_space(p, min_free_gb=9999999.0)


if __name__ == "__main__":
    unittest.main()
