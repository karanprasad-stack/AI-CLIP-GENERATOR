"""Unit tests for EffectValidator: timeline structure, bounds, and video technical checks."""

import unittest
from backend.app.config import EFFECT_SUBTLE_ZOOM, EFFECT_PUNCH_ZOOM
from backend.app.pipeline.effect_engine import EffectEvent, EffectTimeline
from backend.app.pipeline.effect_validator import EffectValidator


class TestEffectValidator(unittest.TestCase):
    def setUp(self):
        self.validator = EffectValidator()

    def test_valid_timeline_passes(self):
        """Standard valid timeline passes structural validation."""
        eff = [
            EffectEvent(
                type=EFFECT_PUNCH_ZOOM,
                start=5.0,
                end=5.6,
                intensity=0.75,
                confidence=0.85,
                reason="clutch",
                source_events=["clutch"],
            )
        ]
        tl = EffectTimeline(candidate_id=1, candidate_duration=30.0, effects=eff)
        res = self.validator.validate_timeline(tl, candidate_duration=30.0)
        self.assertTrue(res["valid"])
        self.assertEqual(res["status"], "PASS")

    def test_invalid_effect_type_fails(self):
        """Unknown effect type fails validation."""
        bad_eff = {"type": "laser_eyes_3000", "start": 1.0, "end": 2.0, "intensity": 0.5, "confidence": 0.8}
        tl_dict = {"candidate_id": 1, "candidate_duration": 10.0, "effects": [bad_eff]}
        res = self.validator.validate_timeline(tl_dict)
        self.assertFalse(res["valid"])
        self.assertIn("invalid type", res["errors"][0])

    def test_negative_timestamp_fails(self):
        """Negative start timestamp is rejected."""
        bad_eff = {"type": EFFECT_SUBTLE_ZOOM, "start": -1.0, "end": 2.0, "intensity": 0.5, "confidence": 0.8}
        tl_dict = {"candidate_id": 1, "candidate_duration": 10.0, "effects": [bad_eff]}
        res = self.validator.validate_timeline(tl_dict)
        self.assertFalse(res["valid"])
        self.assertIn("negative timestamp", res["errors"][0])

    def test_end_before_start_fails(self):
        """End timestamp before start timestamp is rejected."""
        bad_eff = {"type": EFFECT_SUBTLE_ZOOM, "start": 5.0, "end": 3.0, "intensity": 0.5, "confidence": 0.8}
        tl_dict = {"candidate_id": 1, "candidate_duration": 10.0, "effects": [bad_eff]}
        res = self.validator.validate_timeline(tl_dict)
        self.assertFalse(res["valid"])
        self.assertIn("end (3.0) <= start (5.0)", res["errors"][0])

    def test_exceeds_clip_duration_fails(self):
        """Effect running past clip duration fails."""
        bad_eff = {"type": EFFECT_SUBTLE_ZOOM, "start": 28.0, "end": 35.0, "intensity": 0.5, "confidence": 0.8}
        tl_dict = {"candidate_id": 1, "candidate_duration": 30.0, "effects": [bad_eff]}
        res = self.validator.validate_timeline(tl_dict, candidate_duration=30.0)
        self.assertFalse(res["valid"])
        self.assertIn("exceeds candidate duration", res["errors"][0])

    def test_overlapping_zooms_fail(self):
        """Simultaneous overlapping zoom effects are rejected."""
        e1 = {"type": EFFECT_SUBTLE_ZOOM, "start": 10.0, "end": 12.0, "intensity": 0.5, "confidence": 0.8}
        e2 = {"type": EFFECT_PUNCH_ZOOM, "start": 11.0, "end": 13.0, "intensity": 0.8, "confidence": 0.8}
        tl_dict = {"candidate_id": 1, "candidate_duration": 30.0, "effects": [e1, e2]}
        res = self.validator.validate_timeline(tl_dict)
        self.assertFalse(res["valid"])
        self.assertIn("Overlapping zoom effects", res["errors"][0])


if __name__ == "__main__":
    unittest.main()
