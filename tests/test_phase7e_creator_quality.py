"""Unit tests for Phase 7E: Creator Quality & Final Output Intelligence Engine."""

import unittest
from backend.app.pipeline.creator_quality import (
    CreatorQualityEvaluator,
    PublishabilityGate,
    evaluate_moment_quality,
    evaluate_narrative_quality,
    evaluate_presentation_quality,
    evaluate_publishing_quality,
    evaluate_technical_quality,
    evaluate_diversity_quality,
)
from backend.app.api.schemas import CandidateSchema, OutputPackageSchema, PublishabilitySchema


class TestCreatorQualityDimensions(unittest.TestCase):
    """Test individual creator quality dimension evaluators."""

    def test_moment_quality_strong_clutch(self):
        cand = {
            "final_score": 88.5,
            "gameplay_event": "clutch_headshot",
            "strongest_reaction": "no way",
            "score_breakdown": {
                "gameplay_event_score": 85.0,
                "audio_score": 82.0,
                "reaction_score": 80.0,
            },
        }
        res = evaluate_moment_quality(cand)
        self.assertGreaterEqual(res["score"], 85.0)
        self.assertEqual(len(res["blocking_issues"]), 0)
        self.assertTrue(any("clutch" in r.lower() for r in res["reasons"]))
        self.assertTrue(any("no way" in r.lower() for r in res["reasons"]))

    def test_moment_quality_weak(self):
        cand = {
            "final_score": 40.0,
            "gameplay_event": "movement",
            "strongest_reaction": "unknown",
            "score_breakdown": {},
        }
        res = evaluate_moment_quality(cand)
        self.assertLess(res["score"], 60.0)
        self.assertIn("Raw moment score below minimum acceptable threshold", res["blocking_issues"])

    def test_narrative_quality_optimal_arc(self):
        cand = {
            "start": 10.0,
            "end": 45.0,
            "duration": 35.0,
            "climax_timestamp": 30.0,  # ~57% into clip
        }
        words = [
            {"word": "watch", "start": 11.0, "end": 11.5},
            {"word": "this", "start": 11.6, "end": 12.0},
            {"word": "clutch", "start": 30.0, "end": 30.8},
            {"word": "done", "start": 43.0, "end": 43.5},  # 1.5s buffer before end
        ]
        res = evaluate_narrative_quality(cand, transcript_words=words)
        self.assertGreaterEqual(res["score"], 80.0)
        self.assertEqual(len(res["blocking_issues"]), 0)
        self.assertTrue(any("hook" in r.lower() for r in res["reasons"]))

    def test_narrative_quality_dead_air_and_cutoff(self):
        cand = {
            "start": 0.0,
            "end": 30.0,
            "duration": 30.0,
            "climax_timestamp": 29.5,  # Very late climax
        }
        words = [
            {"word": "hello", "start": 5.0, "end": 5.5},  # 5s dead air opening
            {"word": "cutoff", "start": 29.2, "end": 29.9},  # 0.1s buffer before end
        ]
        res = evaluate_narrative_quality(cand, transcript_words=words)
        self.assertLess(res["score"], 70.0)
        self.assertTrue(any("dead air" in w.lower() or "slow opening hook" in w.lower() for w in res["warnings"]))
        self.assertTrue(any("cutoff" in w.lower() or "abrupt" in w.lower() for w in res["warnings"]))

    def test_presentation_quality(self):
        cand = {"duration": 30.0}
        sub_info = {"words_per_second": 3.2, "emojis_aligned": True}
        eff_info = {"total_effects": 3}
        audio_info = {"ducking_applied": True, "sfx_applied": 2}

        res = evaluate_presentation_quality(cand, sub_info, eff_info, audio_info)
        self.assertGreaterEqual(res["score"], 80.0)
        self.assertTrue(any("ducking" in r.lower() for r in res["reasons"]))
        self.assertTrue(any("sfx" in r.lower() for r in res["reasons"]))

    def test_publishing_quality_good(self):
        cand = {}
        pkg = {
            "thumbnail_score": 88.0,
            "thumbnail_path": "thumbnail.jpg",
            "title": "INSANE 1v3 Clutch In Final Circle!",
            "description": "Watch this unreal clutch play during ranked endgame. Source: Streamer (ID: 12345). #gaming",
            "hashtags": ["#gaming", "#clutch", "#shorts", "#gamer"],
        }
        res = evaluate_publishing_quality(cand, pkg)
        self.assertGreaterEqual(res["score"], 80.0)
        self.assertEqual(len(res["blocking_issues"]), 0)

    def test_publishing_quality_reaction_only_title(self):
        cand = {}
        pkg = {
            "thumbnail_score": 40.0,
            "title": '"Whoa" 💀',
            "description": "Short clip",
            "hashtags": [],
        }
        res = evaluate_publishing_quality(cand, pkg)
        self.assertLess(res["score"], 65.0)
        self.assertTrue(any("reaction-only" in w.lower() for w in res["warnings"]))

    def test_technical_quality_pass_and_fail(self):
        cand = {}
        pkg_pass = {"validation": {"status": "PASS", "errors": []}}
        res_pass = evaluate_technical_quality(cand, pkg_pass)
        self.assertEqual(res_pass["score"], 100.0)
        self.assertEqual(len(res_pass["blocking_issues"]), 0)

        pkg_fail = {"validation": {"status": "FAIL", "errors": ["Corrupted audio stream"]}}
        res_fail = evaluate_technical_quality(cand, pkg_fail)
        self.assertLessEqual(res_fail["score"], 50.0)
        self.assertGreater(len(res_fail["blocking_issues"]), 0)

    def test_diversity_quality_spread_vs_stacked(self):
        cand = {"start": 300.0, "gameplay_event": "clutch", "strongest_reaction": "no way"}
        selected_spread = [
            {"start": 100.0, "gameplay_event": "sniper_shot", "strongest_reaction": "let's go"},
        ]
        res_spread = evaluate_diversity_quality(cand, selected_candidates=selected_spread)
        self.assertGreaterEqual(res_spread["score"], 85.0)

        selected_stacked = [
            {"start": 315.0, "gameplay_event": "clutch", "strongest_reaction": "no way"},
            {"start": 320.0, "gameplay_event": "clutch", "strongest_reaction": "no way"},
        ]
        res_stacked = evaluate_diversity_quality(cand, selected_candidates=selected_stacked)
        self.assertLess(res_stacked["score"], 70.0)
        self.assertTrue(any("proximity" in w.lower() for w in res_stacked["warnings"]))


class TestCreatorQualityEvaluator(unittest.TestCase):
    """Test composite publishability scoring and level assignment."""

    def setUp(self):
        self.evaluator = CreatorQualityEvaluator()

    def test_strong_publishable_candidate(self):
        cand = {
            "candidate_id": 1,
            "final_score": 87.0,
            "start": 50.0,
            "end": 85.0,
            "duration": 35.0,
            "climax_timestamp": 72.0,
            "gameplay_event": "clutch_headshot",
            "strongest_reaction": "holy crap",
            "score_breakdown": {
                "gameplay_event_score": 88.0,
                "audio_score": 84.0,
                "reaction_score": 82.0,
            },
        }
        pkg = {
            "thumbnail_score": 85.0,
            "thumbnail_path": "thumb.jpg",
            "title": "Unreal 1v3 Clutch Play To Win!",
            "description": "Full gameplay highlight. Source credit: Creator. #gaming #shorts",
            "hashtags": ["#gaming", "#shorts", "#clutch", "#viral"],
            "validation": {"status": "PASS", "errors": []},
        }
        words = [
            {"word": "yo", "start": 51.0, "end": 51.5},
            {"word": "clutch", "start": 72.0, "end": 72.8},
            {"word": "gg", "start": 82.0, "end": 82.6},
        ]

        result = self.evaluator.evaluate(
            candidate=cand,
            package_info=pkg,
            transcript_words=words,
        )

        self.assertGreaterEqual(result["score"], 80.0)
        self.assertIn(result["level"], ("excellent", "strong"))
        self.assertEqual(result["recommendation"], "publish")
        self.assertIn("moment", result["dimensions"])
        self.assertIn("narrative", result["dimensions"])
        self.assertIn("presentation", result["dimensions"])
        self.assertIn("publishing", result["dimensions"])
        self.assertIn("technical", result["dimensions"])
        self.assertIn("diversity", result["dimensions"])
        self.assertEqual(len(result["blocking_issues"]), 0)

    def test_candidate_with_blocking_issue(self):
        cand = {
            "candidate_id": 2,
            "final_score": 35.0,
            "start": 0.0,
            "end": 20.0,
            "duration": 20.0,
            "gameplay_event": "idle",
            "strongest_reaction": "none",
        }
        pkg = {
            "validation": {"status": "FAIL", "errors": ["Missing final.mp4"]},
        }

        result = self.evaluator.evaluate(candidate=cand, package_info=pkg)
        self.assertEqual(result["recommendation"], "reject")
        self.assertGreater(len(result["blocking_issues"]), 0)


class TestPublishabilityGate(unittest.TestCase):
    """Test Quality Gate Auto vs Custom quota semantics."""

    def setUp(self):
        self.gate = PublishabilityGate()
        self.candidates = [
            {
                "candidate_id": 1,
                "rank": 1,
                "final_score": 90.0,
                "start": 20.0,
                "end": 60.0,
                "duration": 40.0,
                "climax_timestamp": 45.0,
                "gameplay_event": "clutch",
                "strongest_reaction": "lets go",
                "score_breakdown": {"gameplay_event_score": 90.0, "audio_score": 85.0},
            },
            {
                "candidate_id": 2,
                "rank": 2,
                "final_score": 82.0,
                "start": 120.0,
                "end": 155.0,
                "duration": 35.0,
                "climax_timestamp": 140.0,
                "gameplay_event": "ace",
                "strongest_reaction": "no way",
                "score_breakdown": {"gameplay_event_score": 80.0, "audio_score": 80.0},
            },
            {
                "candidate_id": 3,
                "rank": 3,
                "final_score": 58.0,
                "start": 250.0,
                "end": 280.0,
                "duration": 30.0,
                "gameplay_event": "combat",
                "strongest_reaction": "unknown",
                "score_breakdown": {"gameplay_event_score": 55.0, "audio_score": 55.0},
            },
            {
                "candidate_id": 4,
                "rank": 4,
                "final_score": 35.0,
                "start": 400.0,
                "end": 430.0,
                "duration": 30.0,
                "gameplay_event": "none",
                "strongest_reaction": "none",
                "score_breakdown": {},
            },
        ]

    def test_auto_mode_selects_only_publish_ready(self):
        selected, explanation = self.gate.filter_candidates(
            candidates=self.candidates,
            num_shorts_mode="auto",
        )
        # Should pick the 2 strong publishable candidates (ids 1 and 2), not weak ones
        self.assertEqual(len(selected), 2)
        selected_ids = [c["candidate_id"] for c in selected]
        self.assertIn(1, selected_ids)
        self.assertIn(2, selected_ids)
        self.assertIn("Auto", explanation)

    def test_custom_mode_ceiling_prevents_manufacturing_weak(self):
        # User requested 4, but only 2 or 3 qualify (candidate 4 is rejected)
        selected, explanation = self.gate.filter_candidates(
            candidates=self.candidates,
            num_shorts_mode="custom",
            requested_count=4,
        )
        self.assertLessEqual(len(selected), 3)
        self.assertNotIn(4, [c["candidate_id"] for c in selected])
        self.assertTrue("declined to manufacture" in explanation or "meeting quality" in explanation)


class TestPublishabilitySchemas(unittest.TestCase):
    """Test API schema serialization and backward compatibility."""

    def test_candidate_schema_with_publishability(self):
        data = {
            "candidate_id": 1,
            "rank": 1,
            "start": 10.0,
            "end": 40.0,
            "duration": 30.0,
            "final_score": 85.0,
            "publishability": {
                "score": 86.5,
                "level": "strong",
                "recommendation": "publish",
                "dimensions": {
                    "moment": 90.0,
                    "narrative": 85.0,
                    "presentation": 85.0,
                    "publishing": 80.0,
                    "technical": 100.0,
                    "diversity": 85.0,
                },
                "reasons": ["High intensity clutch"],
                "warnings": [],
                "blocking_issues": [],
            },
        }
        cand = CandidateSchema(**data)
        self.assertIsNotNone(cand.publishability)
        self.assertEqual(cand.publishability.score, 86.5)
        self.assertEqual(cand.publishability.level, "strong")

    def test_candidate_schema_backward_compatibility(self):
        # Without publishability (Phase 7A-7D legacy structure)
        data = {
            "candidate_id": 1,
            "rank": 1,
            "start": 10.0,
            "end": 40.0,
            "duration": 30.0,
            "final_score": 85.0,
        }
        cand = CandidateSchema(**data)
        self.assertIsNone(cand.publishability)
        self.assertEqual(cand.final_score, 85.0)


if __name__ == "__main__":
    unittest.main()
