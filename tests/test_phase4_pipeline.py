"""Integration and validation unit tests for Phase 4 subtitle and captioned video engine."""

import unittest
import tempfile
from pathlib import Path

from backend.app.pipeline.caption_engine import CaptionEngine, CaptionWord, CaptionGroup
from backend.app.pipeline.ass_generator import AssGenerator
from backend.app.pipeline.emoji_engine import EmojiEngine
from backend.app.pipeline.subtitle_validator import SubtitleValidator


class TestPhase4Pipeline(unittest.TestCase):
    def setUp(self):
        self.caption_engine = CaptionEngine()
        self.ass_generator = AssGenerator()
        self.emoji_engine = EmojiEngine()
        self.validator = SubtitleValidator()

    def test_ass_generation_and_validation_pass(self):
        """End-to-end ASS generation creates fully valid 1080x1920 subtitle file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ass_path = Path(tmp_dir) / "test_candidate.ass"
            words = [
                CaptionWord(text="LETS", start=0.5, end=0.8, index=0, global_start=1.5, global_end=1.8),
                CaptionWord(text="GO!", start=0.8, end=1.4, index=1, global_start=1.8, global_end=2.4),
            ]
            group = CaptionGroup(words=words, start=0.48, end=1.45, text="LETS GO!")
            emojis = [{
                "emoji": "🔥",
                "start": 0.5,
                "end": 1.5,
                "confidence": 0.95,
                "category": "fire",
            }]

            self.ass_generator.write_ass_file(ass_path, [group], emojis)
            self.assertTrue(ass_path.exists())

            val_res = self.validator.validate_ass(ass_path, clip_duration=10.0)
            self.assertTrue(val_res["valid"], f"Validation failed: {val_res.get('errors')}")
            self.assertGreaterEqual(val_res["dialogue_count"], 2)
            self.assertEqual(val_res["emoji_count"], 1)
            self.assertTrue(val_res["checks"]["target_resolution_1080x1920"])
            self.assertTrue(val_res["checks"]["no_negative_timestamps"])

    def test_validator_detects_malformed_ass(self):
        """Validator properly catches missing sections and negative timestamps."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_ass = Path(tmp_dir) / "bad.ass"

            # Missing headers
            bad_ass.write_text("Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hello\n", encoding="utf-8")
            res = self.validator.validate_ass(bad_ass)
            self.assertFalse(res["valid"])
            self.assertIn("Missing [Script Info] section", res["errors"])

            # Negative timestamp or backward duration
            bad_content = (
                "[Script Info]\nPlayResX: 1080\nPlayResY: 1920\n"
                "[V4+ Styles]\nStyle: Default,Arial,20\n"
                "[Events]\n"
                "Dialogue: 0,0:00:05.00,0:00:02.00,Default,,0,0,0,,Backwards\n"
            )
            bad_ass.write_text(bad_content, encoding="utf-8")
            res2 = self.validator.validate_ass(bad_ass)
            self.assertFalse(res2["valid"])

    def test_validator_detects_duration_exceeded(self):
        """Validator flags timestamps that exceed clip duration beyond tolerance."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ass_path = Path(tmp_dir) / "exceeded.ass"
            content = (
                "[Script Info]\nPlayResX: 1080\nPlayResY: 1920\n"
                "[V4+ Styles]\nStyle: Default,Arial,20\n"
                "[Events]\n"
                "Dialogue: 0,0:00:01.00,0:00:30.00,Default,,0,0,0,,Over duration\n"
            )
            ass_path.write_text(content, encoding="utf-8")
            # If clip is only 15 seconds, 30s timestamp should fail
            res = self.validator.validate_ass(ass_path, clip_duration=15.0)
            self.assertFalse(res["valid"])
            self.assertIn("exceeds clip duration", res["errors"][0])


if __name__ == "__main__":
    unittest.main()
