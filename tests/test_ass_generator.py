"""Unit tests for AssGenerator: header formatting, style tags, and karaoke events."""

import unittest
from backend.app.pipeline.caption_engine import CaptionWord, CaptionGroup
from backend.app.pipeline.ass_generator import AssGenerator, format_ass_timestamp, escape_ass_text


class TestAssGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = AssGenerator()

    def test_timestamp_formatting(self):
        """Seconds convert to ASS H:MM:SS.cs correctly."""
        self.assertEqual(format_ass_timestamp(0.0), "0:00:00.00")
        self.assertEqual(format_ass_timestamp(1.5), "0:00:01.50")
        self.assertEqual(format_ass_timestamp(65.25), "0:01:05.25")
        self.assertEqual(format_ass_timestamp(3661.05), "1:01:01.05")

    def test_text_escaping(self):
        """ASS override control chars like { and } are safely escaped."""
        escaped = escape_ass_text("Watch {this} play!")
        self.assertEqual(escaped, "Watch (this) play!")

    def test_ass_header_validity(self):
        """Header contains 1080x1920 PlayRes and both Default and Emoji styles."""
        header = self.generator.build_header()
        self.assertIn("[Script Info]", header)
        self.assertIn("PlayResX: 1080", header)
        self.assertIn("PlayResY: 1920", header)
        self.assertIn("[V4+ Styles]", header)
        self.assertIn("Style: Default", header)
        self.assertIn("Style: Emoji", header)
        self.assertIn("[Events]", header)

    def test_karaoke_dialogue_active_highlighting(self):
        """Each word in a group gets a corresponding dialogue line with active highlighting."""
        words = [
            CaptionWord(text="WHAT", start=1.0, end=1.5, index=0, global_start=10.0, global_end=10.5),
            CaptionWord(text="A", start=1.5, end=1.8, index=1, global_start=10.5, global_end=10.8),
            CaptionWord(text="PLAY!", start=1.8, end=2.4, index=2, global_start=10.8, global_end=11.4),
        ]
        group = CaptionGroup(words=words, start=0.98, end=2.45, text="WHAT A PLAY!")
        dialogue = self.generator.generate_events([group])

        # Expect at least 3 active word lines (+ optional lead-in)
        self.assertGreaterEqual(len(dialogue), 3)

        # Check that active color tag is present
        has_active_color = any(self.generator.active_color in line for line in dialogue)
        self.assertTrue(has_active_color)

        # Check that scale pop is present
        has_scale_pop = any(r"\fscx108" in line for line in dialogue)
        self.assertTrue(has_scale_pop)

    def test_emoji_dialogue_line(self):
        """Emoji events are emitted on Layer 1 with bounce animation."""
        group = CaptionGroup(
            words=[CaptionWord(text="WOW", start=0.5, end=1.0, index=0, global_start=5.0, global_end=5.5)],
            start=0.5,
            end=1.0,
            text="WOW",
        )
        emojis = [{
            "emoji": "🔥",
            "start": 0.5,
            "end": 1.5,
            "confidence": 0.9,
            "category": "fire",
        }]
        dialogue = self.generator.generate_events([group], emojis)
        emoji_lines = [line for line in dialogue if "Emoji" in line]
        self.assertEqual(len(emoji_lines), 1)
        self.assertIn("🔥", emoji_lines[0])
        self.assertIn(r"\fscx120", emoji_lines[0])


if __name__ == "__main__":
    unittest.main()
