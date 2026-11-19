"""Unit tests for CaptionEngine: word extraction, relative timestamps, and grouping."""

import unittest
from backend.app.pipeline.caption_engine import CaptionEngine, CaptionWord, CaptionGroup


class TestCaptionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = CaptionEngine()
        self.sample_transcript = {
            "language": "en",
            "duration": 200.0,
            "segments": [
                {
                    "start": 10.0,
                    "end": 14.5,
                    "text": "What a clutch! That was insane.",
                    "words": [
                        {"start": 10.0, "end": 10.4, "word": "What"},
                        {"start": 10.4, "end": 10.6, "word": "a"},
                        {"start": 10.6, "end": 11.2, "word": "clutch!"},
                        {"start": 12.0, "end": 12.5, "word": "That"},
                        {"start": 12.5, "end": 13.0, "word": "was"},
                        {"start": 13.0, "end": 13.8, "word": "insane."},
                    ],
                },
                {
                    "start": 14.8,
                    "end": 18.0,
                    "text": "Are you serious right now?",
                    "words": [
                        {"start": 14.8, "end": 15.1, "word": "Are"},
                        {"start": 15.1, "end": 15.3, "word": "you"},
                        {"start": 15.3, "end": 15.9, "word": "serious"},
                        {"start": 16.0, "end": 16.3, "word": "right"},
                        {"start": 16.3, "end": 16.8, "word": "now?"},
                    ],
                },
            ],
        }

    def test_word_extraction_relative_timing(self):
        """Words are converted to relative timestamps starting from 0.0."""
        clip_start = 10.0
        clip_end = 18.0
        words = self.engine.extract_words(
            self.sample_transcript,
            clip_start=clip_start,
            clip_end=clip_end,
            clip_duration=8.0,
        )
        self.assertEqual(len(words), 11)
        # First word should start at 0.0
        self.assertAlmostEqual(words[0].start, 0.0, places=2)
        self.assertEqual(words[0].text, "What")
        # Global start preserved
        self.assertAlmostEqual(words[0].global_start, 10.0, places=2)
        # All relative timestamps non-negative
        for w in words:
            self.assertGreaterEqual(w.start, 0.0)
            self.assertGreater(w.end, w.start)
            self.assertLessEqual(w.end, 8.0)

    def test_grouping_respects_max_words(self):
        """Groups do not exceed max_words (4) unless merging trailing orphan."""
        words = self.engine.extract_words(
            self.sample_transcript,
            clip_start=10.0,
            clip_end=18.0,
        )
        groups = self.engine.group_words(words)
        self.assertGreater(len(groups), 0)
        for g in groups:
            self.assertLessEqual(len(g.words), 4)

    def test_grouping_splits_on_punctuation(self):
        """Punctuation marks (. ! ?) trigger natural group boundaries."""
        words = self.engine.extract_words(
            self.sample_transcript,
            clip_start=10.0,
            clip_end=18.0,
        )
        groups = self.engine.group_words(words)
        # 'What a clutch!' should be its own group because of '!'
        self.assertEqual(groups[0].text, "What a clutch!")

    def test_grouping_splits_on_pause(self):
        """A pause >= 0.4s triggers a new group."""
        words = [
            CaptionWord(text="Hello", start=0.0, end=0.5, index=0, global_start=10.0, global_end=10.5),
            CaptionWord(text="world", start=0.6, end=1.0, index=1, global_start=10.6, global_end=11.0),
            CaptionWord(text="after", start=1.8, end=2.2, index=2, global_start=11.8, global_end=12.2),  # 0.8s pause
            CaptionWord(text="pause", start=2.3, end=2.7, index=3, global_start=12.3, global_end=12.7),
        ]
        groups = self.engine.group_words(words)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].text, "Hello world")
        self.assertEqual(groups[1].text, "after pause")

    def test_variable_duration_support_15s_and_180s(self):
        """Supports short clips (15s) and extended 3-minute clips (180s)."""
        # Test 15s clip
        groups_15 = self.engine.process_candidate(
            transcript_data=self.sample_transcript,
            candidate_start=10.0,
            candidate_end=25.0,
            clip_duration=15.0,
        )
        self.assertGreater(len(groups_15), 0)
        self.assertLessEqual(groups_15[-1].end, 15.0)

        # Test 180s clip
        long_transcript = {
            "segments": [
                {
                    "start": float(i * 5),
                    "end": float(i * 5 + 4),
                    "text": f"Moment {i}",
                    "words": [
                        {"start": float(i * 5), "end": float(i * 5 + 0.8), "word": "Moment"},
                        {"start": float(i * 5 + 0.9), "end": float(i * 5 + 1.8), "word": str(i)},
                    ],
                }
                for i in range(36)  # 36 * 5 = 180s
            ]
        }
        groups_180 = self.engine.process_candidate(
            transcript_data=long_transcript,
            candidate_start=0.0,
            candidate_end=180.0,
            clip_duration=180.0,
        )
        self.assertEqual(len(groups_180), 36)
        self.assertAlmostEqual(groups_180[0].start, 0.0, places=1)
        self.assertLessEqual(groups_180[-1].end, 180.0)


if __name__ == "__main__":
    unittest.main()
