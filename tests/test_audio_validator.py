import unittest
from pathlib import Path
from backend.app.pipeline.audio_validator import AudioValidator
from backend.app.pipeline.audio_event_engine import AudioTimeline, AudioEvent


class TestAudioValidator(unittest.TestCase):
    def setUp(self):
        self.validator = AudioValidator()

    def test_valid_timeline_passes(self):
        timeline = AudioTimeline(
            candidate_id=1,
            candidate_duration=30.0,
            audio_events=[
                AudioEvent(
                    timestamp=5.0,
                    event_type="whoosh",
                    asset_name="whoosh_soft.wav",
                    gain_db=-18.0,
                    intensity=0.8,
                    confidence=0.9,
                    source="visual_effect",
                )
            ],
        )

        res = self.validator.validate_audio_timeline(timeline, candidate_duration=30.0)
        self.assertTrue(res["valid"])
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(len(res["errors"]), 0)

    def test_negative_timestamp_fails(self):
        timeline = AudioTimeline(
            candidate_id=2,
            candidate_duration=30.0,
            audio_events=[
                AudioEvent(
                    timestamp=-0.5,
                    event_type="whoosh",
                    asset_name="whoosh_soft.wav",
                    gain_db=-18.0,
                    intensity=0.8,
                    confidence=0.9,
                    source="visual_effect",
                )
            ],
        )

        res = self.validator.validate_audio_timeline(timeline, candidate_duration=30.0)
        self.assertFalse(res["valid"])
        self.assertEqual(res["status"], "FAIL")
        self.assertIn("Negative SFX timestamp", res["errors"][0])

    def test_timestamp_exceeds_duration_fails(self):
        timeline = AudioTimeline(
            candidate_id=3,
            candidate_duration=30.0,
            audio_events=[
                AudioEvent(
                    timestamp=35.0,
                    event_type="major_impact",
                    asset_name="impact_medium.wav",
                    gain_db=-12.0,
                    intensity=0.8,
                    confidence=0.9,
                    source="visual_effect",
                )
            ],
        )

        res = self.validator.validate_audio_timeline(timeline, candidate_duration=30.0)
        self.assertFalse(res["valid"])
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("exceeds candidate duration" in e for e in res["errors"]))

    def test_density_exceeded_fails(self):
        events = []
        for i in range(20):
            events.append(
                AudioEvent(
                    timestamp=1.0 + i * 1.0,
                    event_type="whoosh",
                    asset_name="whoosh_soft.wav",
                    gain_db=-18.0,
                    intensity=0.8,
                    confidence=0.9,
                    source="visual_effect",
                )
            )

        timeline = AudioTimeline(
            candidate_id=4,
            candidate_duration=30.0,
            audio_events=events,
        )

        res = self.validator.validate_audio_timeline(timeline, candidate_duration=30.0)
        self.assertFalse(res["valid"])
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("SFX density exceeded" in e for e in res["errors"]))


if __name__ == "__main__":
    unittest.main()
