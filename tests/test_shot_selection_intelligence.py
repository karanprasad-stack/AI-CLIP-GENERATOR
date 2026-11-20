"""Unit tests for Shot Selection Intelligence:
- Stricter FPS attribution & ambient kill-feed down-weighting
- Meta-chatter / stream filler penalty & invariant consistency
- SceneAnalyzer static screen detection and hard-cut snapping
- SemanticReranker local Ollama offline fallback and score blending
- Long-stream chunk gameplay event aggregation & timeline integration
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import numpy as np

from backend.app.pipeline.candidate_ranker import CandidateRanker
from backend.app.pipeline.games import (
    GameplayTimeline,
    GameplayEvent,
    EventType,
    EventStatus,
    ValorantGameProfile,
)
from backend.app.pipeline.transcript_analyzer import TranscriptAnalyzer
from backend.app.pipeline.scene_analyzer import SceneAnalyzer
from backend.app.pipeline.semantic_reranker import SemanticReranker
from backend.app.pipeline.long_stream.orchestrator import LongStreamOrchestrator
from backend.app.pipeline.long_stream.chunk_planner import ChunkPlan


class TestShotSelectionIntelligence(unittest.TestCase):
    def setUp(self):
        self.ranker = CandidateRanker()

    # -------------------------------------------------------------------------
    # 1. Stricter FPS Attribution & Ambient Kill-feed down-weighting
    # -------------------------------------------------------------------------
    def test_spectated_kill_outranks_ambient_teammate_kills(self):
        """A single spectated kill (or 3K) must decisively outrank multiple ambient non-spectated killfeed trades."""
        # 4 ambient kills (teammates/enemies trading in killfeed)
        ambient_timeline = GameplayTimeline(game="valorant")
        for i in range(4):
            ambient_timeline.add_event(GameplayEvent(
                id=f"amb_{i}",
                game="valorant",
                event_type=EventType.KILL.value,
                start_time=10.0 + i * 2.0,
                end_time=11.0 + i * 2.0,
                confidence=0.8,
                status=EventStatus.CONFIRMED.value,
                metadata={"ambient": True, "killer": "teammate"}
            ))
        score_ambient, _, exp_amb, metrics_amb = self.ranker.calculate_concrete_gameplay_score(
            5.0, 30.0, ambient_timeline
        )
        self.assertLessEqual(score_ambient, 10.0)
        self.assertIn("ambient", exp_amb.lower())
        self.assertEqual(metrics_amb.get("spectated_kills"), 0)

        # 1 spectated kill with headshot
        spectated_timeline = GameplayTimeline(game="valorant")
        spectated_timeline.add_event(GameplayEvent(
            id="spec_1",
            game="valorant",
            event_type=EventType.KILL.value,
            start_time=12.0,
            end_time=13.0,
            confidence=0.85,
            status=EventStatus.CONFIRMED.value,
            metadata={"is_spectated_player": True, "headshot": True}
        ))
        score_spectated, _, exp_spec, metrics_spec = self.ranker.calculate_concrete_gameplay_score(
            5.0, 30.0, spectated_timeline
        )
        self.assertGreaterEqual(score_spectated, 20.0)
        self.assertGreater(score_spectated, score_ambient)
        self.assertEqual(metrics_spec.get("spectated_kills"), 1)

    # -------------------------------------------------------------------------
    # 2. Deterministic Meta-Chatter Penalty & Invariant Check
    # -------------------------------------------------------------------------
    def test_meta_chatter_penalty_and_invariant_preserved(self):
        """Candidates dominated by stream meta-chatter without gameplay events receive penalty and satisfy the composite score invariant."""
        # Transcript with meta-chatter: 'thanks for the sub', 'drop a like', 'chat'
        transcript_data = {
            "segments": [
                {"id": 1, "start": 10.0, "end": 14.0, "text": "thanks for the sub chat, don't forget to drop a like and subscribe", "words": []},
                {"id": 2, "start": 14.5, "end": 18.0, "text": "read the chat, check out the sponsor in the link below", "words": []},
            ]
        }
        analyzer = TranscriptAnalyzer(transcript_data)
        audio_analysis = {
            "duration": 60.0,
            "overall_loudness": -20.0,
            "speech_segments": [{"start": 10.0, "end": 18.0}],
            "peaks": [{"timestamp": 12.0, "z_score": 1.5}],
            "transcription": transcript_data,
        }
        raw_candidates = [(10.0, 25.0)]

        empty_timeline = GameplayTimeline(game="generic")
        res = self.ranker.rank_candidates(
            candidates=raw_candidates,
            audio_analysis=audio_analysis,
            transcript_analyzer=analyzer,
            video_id="test_vid",
            video_duration=60.0,
            gameplay_timeline=empty_timeline,
        )

        cand = res["candidates"][0]
        self.assertIn("reasons", cand)
        # Should detect meta chatter penalty
        has_meta_penalty = any("meta" in r.lower() or "filler" in r.lower() for r in cand.get("ranking_reasons", []))
        self.assertTrue(has_meta_penalty)

        # Invariant: composite_score must match weighted sum of component scores within 0.15
        weights = cand["active_weights"]
        comp = cand["scores"]
        expected_sum = (
            comp["audio"] * weights.get("audio", 0.0) +
            comp["transcript"] * weights.get("transcript", 0.0) +
            comp["gameplay_event"] * weights.get("gameplay_event", 0.0) +
            comp["context"] * weights.get("context", 0.0) +
            comp["boundary"] * weights.get("boundary", 0.0)
        )
        self.assertAlmostEqual(cand["final_score"], expected_sum, delta=0.15)

    # -------------------------------------------------------------------------
    # 3. SceneAnalyzer: Static Screen & Scene Cut Snapping
    # -------------------------------------------------------------------------
    def test_scene_analyzer_static_screen_and_cut_snapping(self):
        """SceneAnalyzer flags static screens and snaps hard cuts in first/last 20% of duration."""
        analyzer = SceneAnalyzer(static_threshold=0.60, scene_cut_threshold=0.45)

        # Without video path, should return graceful neutral dict
        res_no_video = analyzer.analyze_candidate(None, 10.0, 30.0)
        self.assertFalse(res_no_video["is_static_screen"])
        self.assertEqual(res_no_video["adjusted_start"], 10.0)
        self.assertEqual(res_no_video["adjusted_end"], 30.0)

        # Mocking cv2.VideoCapture and Path.exists to simulate a static screen
        with patch.object(Path, "exists", return_value=True), patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap_cls.return_value = mock_cap
            mock_cap.isOpened.return_value = True
            mock_cap.get.side_effect = lambda prop: 30.0 if prop == 5 else 300.0  # 30 fps, 300 frames

            # Static frame (all zeros)
            dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
            mock_cap.read.return_value = (True, dummy_frame)

            res = analyzer.analyze_candidate(Path("mock.mp4"), 0.0, 8.0, has_high_speech_peak=False)
            self.assertTrue(res["is_static_screen"])
            self.assertGreaterEqual(res["static_ratio"], 0.60)

    # -------------------------------------------------------------------------
    # 4. SemanticReranker: Offline Fallback & Mocked Local LLM Scoring
    # -------------------------------------------------------------------------
    def test_semantic_reranker_offline_fallback(self):
        """When local Ollama is offline, SemanticReranker leaves candidates untouched and marks audit disabled."""
        reranker = SemanticReranker(host="http://localhost:9999")  # non-existent port
        candidates = [
            {"candidate_id": 1, "final_score": 80.0, "rank": 1, "start": 0.0, "end": 20.0, "duration": 20.0},
            {"candidate_id": 2, "final_score": 70.0, "rank": 2, "start": 30.0, "end": 50.0, "duration": 20.0},
        ]
        res = reranker.rerank(candidates)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["candidate_id"], 1)
        self.assertEqual(res[0]["final_score"], 80.0)
        self.assertFalse(res[0]["semantic_audit"]["enabled"])

    def test_semantic_reranker_mocked_scoring_and_filler_demotion(self):
        """When Ollama returns a verdict, blends 70% composite + 30% semantic and demotes filler."""
        reranker = SemanticReranker()
        reranker.is_available = MagicMock(return_value=True)

        # Mock evaluations: candidate 1 is filler, candidate 2 is high-entertainment payoff
        def mock_eval(cand, **kwargs):
            if cand["candidate_id"] == 1:
                return {
                    "enabled": True,
                    "score": 30.0,
                    "is_filler": True,
                    "verdict": "Lobby talk with no gameplay payoff",
                    "hook_score": 25.0,
                    "entertainment_score": 20.0,
                }
            else:
                return {
                    "enabled": True,
                    "score": 90.0,
                    "is_filler": False,
                    "verdict": "Intense clutch with strong vocal hook",
                    "hook_score": 92.0,
                    "entertainment_score": 90.0,
                }

        reranker.evaluate_candidate = MagicMock(side_effect=mock_eval)

        candidates = [
            {"candidate_id": 1, "final_score": 75.0, "rank": 1},
            {"candidate_id": 2, "final_score": 74.0, "rank": 2},
        ]

        reranked = reranker.rerank(candidates)

        # Candidate 2: base 74.0 * 0.70 + 90.0 * 0.30 = 51.8 + 27.0 = 78.8
        # Candidate 1: base 75.0 * 0.70 + 30.0 * 0.30 = 52.5 + 9.0 = 61.5
        # Candidate 2 should now be ranked #1
        self.assertEqual(reranked[0]["candidate_id"], 2)
        self.assertEqual(reranked[0]["rank"], 1)
        self.assertAlmostEqual(reranked[0]["final_score"], 78.8, places=1)

        self.assertEqual(reranked[1]["candidate_id"], 1)
        self.assertEqual(reranked[1]["rank"], 2)
        self.assertAlmostEqual(reranked[1]["final_score"], 61.5, places=1)
        self.assertTrue(reranked[1]["semantic_audit"]["is_filler"])

    # -------------------------------------------------------------------------
    # 5. Long Stream Visual Event Wiring & Timeline Aggregation
    # -------------------------------------------------------------------------
    def test_long_stream_orchestrator_timeline_aggregation(self):
        """Orchestrator collects chunk gameplay events, deduplicates them, and populates master GameplayTimeline."""
        orchestrator = LongStreamOrchestrator()

        # Mock chunk processor to return concrete events
        ev1 = GameplayEvent(
            id="ev1", game="valorant", event_type="kill",
            start_time=15.0, end_time=16.0, confidence=0.9,
            status=EventStatus.CONFIRMED.value, metadata={"headshot": True}
        )
        # Duplicate of ev1 in overlap region (15.5s)
        ev1_dup = GameplayEvent(
            id="ev1_dup", game="valorant", event_type="kill",
            start_time=15.5, end_time=16.5, confidence=0.85,
            status=EventStatus.CONFIRMED.value, metadata={"headshot": True}
        )
        ev2 = GameplayEvent(
            id="ev2", game="valorant", event_type="ace",
            start_time=45.0, end_time=48.0, confidence=0.95,
            status=EventStatus.CONFIRMED.value
        )

        with patch.object(orchestrator.processor, "process_chunk") as mock_proc, \
             patch("backend.app.pipeline.long_stream.orchestrator.check_disk_space"), \
             patch("backend.app.pipeline.long_stream.orchestrator.ChunkStore") as mock_store_cls:

            mock_store = MagicMock()
            mock_store_cls.return_value = mock_store
            mock_plan1 = ChunkPlan(chunk_id="chk_001", index=1, source_start=0.0, source_end=30.0, duration=30.0, status="pending")
            mock_plan2 = ChunkPlan(chunk_id="chk_002", index=2, source_start=20.0, source_end=50.0, duration=30.0, status="pending")

            orchestrator.planner.plan = MagicMock(return_value=[mock_plan1, mock_plan2])
            mock_store.get_resumable_plan.return_value = ([mock_plan1, mock_plan2], 0)

            # Chunk results
            mock_proc.side_effect = [
                {"candidates": [], "gameplay_events": [ev1.to_dict()]},
                {"candidates": [], "gameplay_events": [ev1_dup.to_dict(), ev2.to_dict()]},
            ]

            mock_store.load_chunk_result.side_effect = lambda cid: (
                {"gameplay_events": [ev1.to_dict()]} if cid == "chk_001" else {"gameplay_events": [ev1_dup.to_dict(), ev2.to_dict()]}
            )
            mock_store.collect_all_candidates.return_value = []
            mock_store.get_merged_transcript.return_value = {"segments": [], "words": []}

            import tempfile
            with tempfile.TemporaryDirectory() as td:
                tpath = Path(td)
                game_prof = ValorantGameProfile()
                res = orchestrator.process(
                    video_id="test_long",
                    source_media=Path("dummy_audio.wav"),
                    source_duration=50.0,
                    project_dir=tpath,
                    temp_dir=tpath / "temp",
                    game_profile=game_prof,
                )

                self.assertIn("gameplay_timeline", res)
                timeline = res["gameplay_timeline"]
                self.assertEqual(len(timeline.events), 2)  # ev1_dup was deduplicated
                event_types = [e.event_type for e in timeline.events]
                self.assertIn("kill", event_types)
                self.assertIn("ace", event_types)


if __name__ == "__main__":
    unittest.main()
