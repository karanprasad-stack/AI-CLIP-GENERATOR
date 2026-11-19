import unittest
from backend.app.pipeline.clip_summary_engine import ClipSummaryEngine, ClipSummary


class TestClipSummaryEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ClipSummaryEngine()

    def test_detect_game_from_title(self):
        meta1 = {"title": "3 IN A WEEK?? CSGO Funny Moments and Clutches #256 - CAFM"}
        self.assertEqual(self.engine.detect_game(meta1), "CS:GO")

        meta2 = {"title": "Insane Valorant Ace on Ascent"}
        self.assertEqual(self.engine.detect_game(meta2), "Valorant")

        meta3 = {"title": "Apex Legends Season 20 Win"}
        self.assertEqual(self.engine.detect_game(meta3), "Apex Legends")

        meta4 = {"title": "Random clip without game title"}
        self.assertEqual(self.engine.detect_game(meta4), "Gaming")

    def test_extract_gameplay_events_and_reaction(self):
        candidate = {
            "candidate_id": 1,
            "candidate_start": 160.0,
            "candidate_end": 203.0,
            "candidate_duration": 43.0,
            "final_score": 85.9,
            "detected_signals": [
                "shot@175.92s",
                "timing@178.61s",
                "phrase:talk about timing@178.25s",
                "audio_peak_z=2.38@168.50s",
            ],
            "gameplay_event_breakdown": {
                "gaming_lexical": {
                    "signals": ["shot@175.92s", "timing@178.61s"]
                },
                "reaction_lexical": {
                    "signals": ["phrase:talk about timing@178.25s"]
                },
            },
            "layout": "facecam_gameplay",
        }
        metadata = {"title": "CSGO Funny Moments"}

        summary = self.engine.summarize_candidate(candidate, video_metadata=metadata)

        self.assertEqual(summary.candidate_id, 1)
        self.assertEqual(summary.game, "CS:GO")
        self.assertIn(summary.primary_event, ["timing", "shot"])
        self.assertEqual(summary.strongest_reaction, "talk about timing")
        self.assertTrue(summary.has_facecam)
        self.assertAlmostEqual(summary.duration, 43.0, places=1)
        self.assertGreater(summary.intensity, 0.8)

    def test_variable_duration_support(self):
        for dur in [15.0, 30.0, 60.0, 90.0, 120.0, 150.0, 180.0]:
            candidate = {
                "candidate_id": 2,
                "candidate_start": 0.0,
                "candidate_end": dur,
                "candidate_duration": dur,
                "final_score": 75.0,
                "detected_signals": ["kill@10.0s"],
            }
            summary = self.engine.summarize_candidate(candidate)
            self.assertEqual(summary.duration, dur)
            self.assertLessEqual(summary.climax_timestamp, dur)

    def test_missing_optional_metadata_handling(self):
        candidate = {
            "candidate_id": 3,
            "candidate_start": 10.0,
            "candidate_end": 40.0,
            "candidate_duration": 30.0,
        }
        summary = self.engine.summarize_candidate(candidate, video_metadata=None)
        self.assertEqual(summary.game, "Gaming")
        self.assertEqual(summary.strongest_reaction, "unknown")
        self.assertFalse(summary.has_facecam)
        d = summary.to_dict()
        self.assertIn("candidate_id", d)
        self.assertIn("climax_timestamp", d)


if __name__ == "__main__":
    unittest.main()
