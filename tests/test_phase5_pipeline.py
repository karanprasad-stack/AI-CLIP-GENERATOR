"""Integration and end-to-end tests for Phase 5 Visual Effects Pipeline."""

import unittest
import tempfile
from pathlib import Path

from backend.app.config import EFFECT_SUBTLE_ZOOM, EFFECT_PUNCH_ZOOM
from backend.app.pipeline.effect_engine import EffectEngine, EffectEvent, EffectTimeline
from backend.app.pipeline.effect_renderer import EffectRenderer
from backend.app.pipeline.effect_validator import EffectValidator


class TestPhase5Pipeline(unittest.TestCase):
    def setUp(self):
        self.engine = EffectEngine()
        self.renderer = EffectRenderer()
        self.validator = EffectValidator()

    def test_pipeline_timeline_generation_and_validation(self):
        """Generates timeline and validates structural schema."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            timeline_file = Path(tmp_dir) / "test_timeline.json"
            cand = {
                "candidate_start": 0.0,
                "candidate_end": 45.0,
                "extraction_duration": 45.0,
                "detected_signals": ["clutch@12.5s", "fail@25.0s", "phrase:no way@12.7s"],
            }
            audio_peaks = [{"timestamp": 12.6, "z_score": 2.5}]
            tl = self.engine.generate_timeline(1, cand, audio_peaks=audio_peaks)
            self.assertGreater(len(tl.effects), 0)

            self.engine.write_timeline_file(timeline_file, tl)
            self.assertTrue(timeline_file.exists())

            val_res = self.validator.validate_timeline(timeline_file, candidate_duration=45.0)
            self.assertTrue(val_res["valid"], f"Validation failed: {val_res.get('errors')}")
            self.assertEqual(val_res["status"], "PASS")

    def test_variable_duration_15s_and_180s(self):
        """Verifies Phase 5 works correctly with both 15s and 180s clips."""
        # 15s quick clip
        cand_15 = {
            "candidate_start": 0.0,
            "candidate_end": 15.0,
            "extraction_duration": 15.0,
            "detected_signals": ["clutch@5.0s"],
        }
        tl_15 = self.engine.generate_timeline(1, cand_15)
        self.assertLessEqual(len(tl_15.effects), 3)
        for e in tl_15.effects:
            self.assertLessEqual(e.end, 15.0)

        # 180s extended clip
        cand_180 = {
            "candidate_start": 0.0,
            "candidate_end": 180.0,
            "extraction_duration": 180.0,
            "detected_signals": [f"headshot@{t}s" for t in [20, 60, 100, 150]],
        }
        tl_180 = self.engine.generate_timeline(2, cand_180)
        self.assertGreater(len(tl_180.effects), 0)
        for e in tl_180.effects:
            self.assertLessEqual(e.end, 180.0)


if __name__ == "__main__":
    unittest.main()
