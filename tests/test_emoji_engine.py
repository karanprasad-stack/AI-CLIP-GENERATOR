"""Unit tests for EmojiEngine: signal detection, confidence scoring, and anti-spam spacing."""

import unittest
from backend.app.pipeline.emoji_engine import EmojiEngine


class TestEmojiEngine(unittest.TestCase):
    def setUp(self):
        self.engine = EmojiEngine()

    def test_reaction_phrase_detection(self):
        """Multi-word reaction phrases are detected and mapped to appropriate emoji."""
        transcript = {
            "segments": [
                {
                    "start": 5.0,
                    "end": 8.0,
                    "text": "Talk about timing! That was crazy.",
                    "words": [
                        {"start": 5.0, "end": 5.4, "word": "Talk"},
                        {"start": 5.4, "end": 5.7, "word": "about"},
                        {"start": 5.7, "end": 6.2, "word": "timing!"},
                    ],
                }
            ]
        }
        emojis = self.engine.detect_emojis(
            transcript_data=transcript,
            clip_start=0.0,
            clip_end=15.0,
        )
        self.assertEqual(len(emojis), 1)
        self.assertEqual(emojis[0]["emoji"], "💀")
        self.assertEqual(emojis[0]["category"], "disbelief")
        self.assertGreaterEqual(emojis[0]["confidence"], 0.70)
        self.assertAlmostEqual(emojis[0]["start"], 5.0, places=1)

    def test_high_impact_gameplay_clutch(self):
        """Clutch signal triggers fire emoji with high confidence."""
        transcript = {
            "segments": [
                {
                    "start": 20.0,
                    "end": 22.0,
                    "text": "What a clutch!",
                    "words": [
                        {"start": 20.0, "end": 20.5, "word": "What"},
                        {"start": 20.5, "end": 20.7, "word": "a"},
                        {"start": 20.7, "end": 21.5, "word": "clutch!"},
                    ],
                }
            ]
        }
        audio_peaks = [{"timestamp": 21.0, "rms": 0.35, "z_score": 2.5}]
        emojis = self.engine.detect_emojis(
            transcript_data=transcript,
            clip_start=15.0,
            clip_end=35.0,
            audio_peaks=audio_peaks,
        )
        self.assertEqual(len(emojis), 1)
        self.assertEqual(emojis[0]["emoji"], "🔥")
        # Relative to clip_start (15.0): 20.7 - 15.0 = 5.7s
        self.assertAlmostEqual(emojis[0]["start"], 5.7, places=1)
        self.assertGreaterEqual(emojis[0]["confidence"], 0.85)

    def test_anti_spam_spacing(self):
        """Events within 2.0s are deduplicated/spaced out to avoid emoji clutter."""
        transcript = {
            "segments": [
                {
                    "start": 10.0,
                    "end": 12.0,
                    "text": "Wow holy insane!",
                    "words": [
                        {"start": 10.0, "end": 10.3, "word": "Wow"},
                        {"start": 10.4, "end": 10.7, "word": "holy"},
                        {"start": 10.8, "end": 11.2, "word": "insane!"},
                    ],
                }
            ]
        }
        emojis = self.engine.detect_emojis(
            transcript_data=transcript,
            clip_start=0.0,
            clip_end=20.0,
        )
        # Should only select at most 1 emoji in this 1.2s burst
        self.assertEqual(len(emojis), 1)

    def test_variable_duration_emojis_180s(self):
        """Emojis are placed throughout a long 180s clip with proper bounds."""
        transcript = {
            "segments": [
                {
                    "start": 10.0,
                    "end": 11.0,
                    "text": "clutch",
                    "words": [{"start": 10.0, "end": 10.5, "word": "clutch"}],
                },
                {
                    "start": 100.0,
                    "end": 101.0,
                    "text": "headshot",
                    "words": [{"start": 100.0, "end": 100.5, "word": "headshot"}],
                },
                {
                    "start": 175.0,
                    "end": 176.0,
                    "text": "insane",
                    "words": [{"start": 175.0, "end": 175.5, "word": "insane"}],
                },
            ]
        }
        emojis = self.engine.detect_emojis(
            transcript_data=transcript,
            clip_start=0.0,
            clip_end=180.0,
            clip_duration=180.0,
        )
        self.assertEqual(len(emojis), 3)
        self.assertLessEqual(emojis[-1]["end"], 180.0)


if __name__ == "__main__":
    unittest.main()
