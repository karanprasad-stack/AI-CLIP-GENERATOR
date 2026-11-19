import unittest
from backend.app.pipeline.ducking_engine import DuckingEngine


class TestDuckingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DuckingEngine()

    def test_speech_interval_extraction_and_merging(self):
        # Two words 0.2s apart (should merge) and a third word 1.5s later (separate)
        transcript_data = {
            "segments": [
                {
                    "words": [
                        {"start": 10.0, "end": 10.5, "word": "Hello"},
                        {"start": 10.7, "end": 11.2, "word": "world"},
                        {"start": 13.0, "end": 13.8, "word": "again"},
                    ]
                }
            ]
        }
        intervals = self.engine.extract_speech_intervals(
            transcript_data=transcript_data,
            clip_start=10.0,
            clip_end=20.0,
            clip_duration=10.0,
        )

        self.assertEqual(len(intervals), 2)
        # First interval should be merged: 0.0 to 1.2
        self.assertAlmostEqual(intervals[0]["start"], 0.0, places=2)
        self.assertAlmostEqual(intervals[0]["end"], 1.2, places=2)
        # Second interval: 3.0 to 3.8
        self.assertAlmostEqual(intervals[1]["start"], 3.0, places=2)
        self.assertAlmostEqual(intervals[1]["end"], 3.8, places=2)

    def test_ducking_db_calculation(self):
        # Short speech (<2s) gets standard ducking (-3.5dB)
        # Long speech (>2s) gets stronger ducking (-4.5dB)
        transcript_data = {
            "segments": [
                {
                    "words": [
                        {"start": 1.0, "end": 1.5, "word": "Short"},
                        {"start": 5.0, "end": 7.5, "word": "Long speech block"},
                    ]
                }
            ]
        }
        candidate = {
            "candidate_id": 1,
            "extraction_start": 0.0,
            "extraction_end": 15.0,
            "extraction_duration": 15.0,
        }

        plan = self.engine.compute_ducking_plan(transcript_data, candidate)
        self.assertTrue(plan["enabled"])
        self.assertEqual(len(plan["intervals"]), 2)
        self.assertEqual(plan["intervals"][0]["ducking_db"], -3.5)
        self.assertEqual(plan["intervals"][1]["ducking_db"], -5.0)

    def test_impact_exemption(self):
        # When a gameplay impact occurs during speech, ducking is relaxed by 1.5 dB
        transcript_data = {
            "segments": [
                {
                    "words": [
                        {"start": 2.0, "end": 4.5, "word": "Shooting enemy right now"},
                    ]
                }
            ]
        }
        candidate = {
            "candidate_id": 1,
            "extraction_start": 0.0,
            "extraction_end": 10.0,
            "extraction_duration": 10.0,
        }
        impact_events = [{"timestamp": 3.0, "type": "major_impact"}]

        plan = self.engine.compute_ducking_plan(transcript_data, candidate, impact_events=impact_events)
        self.assertEqual(len(plan["intervals"]), 1)
        self.assertTrue(plan["intervals"][0]["impact_exempted"])
        # Expected relaxed gain: -5.0 + 1.5 = -3.5 dB
        self.assertAlmostEqual(plan["intervals"][0]["gain_ratio"], 10.0 ** (-3.5 / 20.0), places=2)

    def test_empty_transcript_handling(self):
        candidate = {
            "candidate_id": 1,
            "extraction_start": 0.0,
            "extraction_end": 15.0,
            "extraction_duration": 15.0,
        }
        plan = self.engine.compute_ducking_plan({"segments": []}, candidate)
        self.assertFalse(plan["enabled"])
        self.assertEqual(plan["speech_intervals_count"], 0)

        expr = self.engine.build_ffmpeg_volume_expression(plan)
        self.assertEqual(expr, "1.0")

    def test_ffmpeg_volume_expression_syntax(self):
        ducking_summary = {
            "intervals": [
                {
                    "start": 2.0,
                    "end": 4.0,
                    "gain_ratio": 0.668,
                }
            ]
        }
        expr = self.engine.build_ffmpeg_volume_expression(ducking_summary)
        self.assertIn("between(t,", expr)
        self.assertIn("max(0.40,", expr)
        self.assertIn("1.0-(", expr)


if __name__ == "__main__":
    unittest.main()
