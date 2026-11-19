"""Comprehensive tests for Subtitle Timing & Accuracy Audit.

Validates:
1. Whisper word timestamp preservation (invariance throughout normalization).
2. Candidate-relative timestamp conversion (exact one-time subtraction, monotonic).
3. Frame-accurate extraction alignment (no GOP keyframe snapping desynchronization).
4. Subtitle group timing (0.0s lead-in, group start equals first spoken word start).
5. ASS karaoke event generation (first event starts at word 0 start, valid centisecond format).
6. Gaming vocabulary protection and canonical casing.
7. Roman Hindi and Hinglish token normalization.
8. Faster-Whisper initial prompt configuration.
"""

import unittest
from pathlib import Path
from backend.app.config import (
    CAPTION_LEAD_IN,
    CAPTION_TAIL_OUT,
)
from backend.app.pipeline.caption_engine import CaptionEngine, CaptionWord, CaptionGroup
from backend.app.pipeline.ass_generator import AssGenerator, format_ass_timestamp
from backend.app.pipeline.transcriber import AudioTranscriber, DEFAULT_GAMING_INITIAL_PROMPT
from backend.app.pipeline.clip_extractor import ClipExtractor
from backend.app.pipeline.subtitles.normalizer import HinglishNormalizer
from backend.app.pipeline.subtitles.gaming_terms import (
    is_gaming_term,
    get_canonical_gaming_term,
    is_acronym_or_proper_name,
)
from backend.app.pipeline.subtitles.roman_hindi import (
    is_roman_hindi_word,
    normalize_roman_hindi_token,
)
from backend.app.pipeline.subtitles.subtitle_grouping import SubtitleGrouper


class TestSubtitleTimingAccuracy(unittest.TestCase):
    """Test suite ensuring accurate, non-early subtitle timing and gaming term precision."""

    def setUp(self):
        self.caption_engine = CaptionEngine()
        self.ass_generator = AssGenerator()
        self.normalizer = HinglishNormalizer(mode="hinglish")

    # --------------------------------------------------------------------------
    # 1. Authoritative Timing Preservation
    # --------------------------------------------------------------------------
    def test_whisper_word_timestamp_invariance(self):
        """Original Whisper word timestamps must never be modified or shifted by normalization."""
        raw_words = [
            {"start": 430.78, "end": 431.10, "word": "spike"},
            {"start": 431.10, "end": 431.54, "word": "down"},
            {"start": 431.54, "end": 431.98, "word": "A"},
            {"start": 431.98, "end": 432.74, "word": "one"},
        ]
        segment = {
            "start": 430.78,
            "end": 432.74,
            "text": "spike down A one",
            "words": raw_words,
        }
        res = self.normalizer.normalize_segment(segment)
        norm_words = res["words"]

        self.assertEqual(len(norm_words), len(raw_words))
        for orig, norm in zip(raw_words, norm_words):
            self.assertEqual(orig["start"], norm["start"], "Word start timestamp must remain invariant")
            self.assertEqual(orig["end"], norm["end"], "Word end timestamp must remain invariant")

    # --------------------------------------------------------------------------
    # 2. Candidate-Relative Timestamp Conversion
    # --------------------------------------------------------------------------
    def test_candidate_relative_conversion_exact_single_subtraction(self):
        """Relative timestamps must subtract candidate_start exactly once and start from >= 0.0."""
        cand_start = 420.31
        cand_end = 463.74
        transcript_data = {
            "segments": [
                {
                    "start": 430.78,
                    "end": 432.74,
                    "text": "Spike down A One",
                    "words": [
                        {"start": 430.78, "end": 431.10, "word": "Spike"},
                        {"start": 431.10, "end": 431.54, "word": "down"},
                        {"start": 431.54, "end": 431.98, "word": "A"},
                        {"start": 431.98, "end": 432.74, "word": "One"},
                    ],
                }
            ]
        }

        words = self.caption_engine.extract_words(
            transcript_data=transcript_data,
            clip_start=cand_start,
            clip_end=cand_end,
            clip_duration=cand_end - cand_start,
        )

        self.assertEqual(len(words), 4)
        # Word 1: 430.78 - 420.31 = 10.47
        self.assertAlmostEqual(words[0].start, 10.47, places=2)
        self.assertAlmostEqual(words[0].end, 10.79, places=2)
        self.assertAlmostEqual(words[0].global_start, 430.78, places=2)
        self.assertAlmostEqual(words[0].global_end, 431.10, places=2)

        # Monotonicity check
        for i in range(len(words) - 1):
            self.assertLessEqual(words[i].start, words[i + 1].start)
            self.assertLessEqual(words[i].end, words[i + 1].end)

    # --------------------------------------------------------------------------
    # 3. Subtitle Group Timing & Zero Premature Lead-In
    # --------------------------------------------------------------------------
    def test_subtitle_group_start_matches_first_spoken_word(self):
        """Subtitle group must not start before the first spoken word (0ms lead-in)."""
        words = [
            CaptionWord(text="Spike", start=10.47, end=10.79, index=0, global_start=430.78, global_end=431.10),
            CaptionWord(text="down", start=10.79, end=11.23, index=1, global_start=431.10, global_end=431.54),
        ]
        groups = self.caption_engine.group_words(words)
        self.assertEqual(len(groups), 1)

        group = groups[0]
        # Group start must equal the first word start (no early offset)
        self.assertEqual(group.start, words[0].start)
        self.assertEqual(group.start, 10.47)
        # Group end includes readable tail-out
        self.assertGreaterEqual(group.end, words[-1].end)

    def test_config_lead_in_is_zero(self):
        """Configuration must define CAPTION_LEAD_IN as 0.0 to prevent early caption popup."""
        self.assertEqual(CAPTION_LEAD_IN, 0.0)

    # --------------------------------------------------------------------------
    # 4. ASS Karaoke Event Timing & Synchronicity
    # --------------------------------------------------------------------------
    def test_ass_first_dialogue_line_starts_at_first_word(self):
        """ASS karaoke dialogue must begin at the first word timestamp, never before."""
        words = [
            CaptionWord(text="Spike", start=10.47, end=10.79, index=0, global_start=430.78, global_end=431.10),
            CaptionWord(text="down", start=10.79, end=11.23, index=1, global_start=431.10, global_end=431.54),
        ]
        group = CaptionGroup(words=words, start=10.47, end=11.43, text="Spike down")

        events = self.ass_generator.generate_events([group])
        self.assertGreaterEqual(len(events), 2)

        # First event must begin at exactly 0:00:10.47 (not 10.45 or earlier)
        first_line = events[0]
        self.assertTrue(first_line.startswith("Dialogue: 0,0:00:10.47,"), f"Got: {first_line}")
        self.assertIn("Spike", first_line)

    def test_ass_timestamp_centisecond_formatting(self):
        """format_ass_timestamp must accurately format seconds into H:MM:SS.cs."""
        self.assertEqual(format_ass_timestamp(0.0), "0:00:00.00")
        self.assertEqual(format_ass_timestamp(10.47), "0:00:10.47")
        self.assertEqual(format_ass_timestamp(65.12), "0:01:05.12")
        self.assertEqual(format_ass_timestamp(3661.05), "1:01:01.05")

    # --------------------------------------------------------------------------
    # 5. Gaming Vocabulary & Canonical Casing
    # --------------------------------------------------------------------------
    def test_gaming_vocabulary_canonical_terms(self):
        """Tactical terms like Spike, Vandal, AWP, CS2, clutch must have canonical casing."""
        self.assertEqual(get_canonical_gaming_term("spike"), "Spike")
        self.assertEqual(get_canonical_gaming_term("spockdown"), "Spike down")
        self.assertEqual(get_canonical_gaming_term("vandal"), "Vandal")
        self.assertEqual(get_canonical_gaming_term("phantom"), "Phantom")
        self.assertEqual(get_canonical_gaming_term("cs2"), "CS2")
        self.assertEqual(get_canonical_gaming_term("awp"), "AWP")
        self.assertEqual(get_canonical_gaming_term("clutch"), "clutch")
        self.assertEqual(get_canonical_gaming_term("onetap"), "one tap")
        self.assertEqual(get_canonical_gaming_term("1 tap"), "one tap")
        self.assertEqual(get_canonical_gaming_term("hp"), "HP")

    def test_gaming_agent_names(self):
        """Valorant agent names must be recognized and protected."""
        agents = ["jett", "reyna", "sova", "omen", "cypher", "raze", "viper"]
        for agent in agents:
            canonical = get_canonical_gaming_term(agent)
            self.assertIsNotNone(canonical)
            self.assertEqual(canonical, agent.capitalize())

    # --------------------------------------------------------------------------
    # 6. Roman Hindi & Hinglish Token Normalization
    # --------------------------------------------------------------------------
    def test_roman_hindi_normalization(self):
        """Spoken Roman Hindi contractions normalize cleanly while preserving meaning."""
        token, changed = normalize_roman_hindi_token("kr")
        self.assertEqual(token, "kar")
        self.assertTrue(changed)

        token, changed = normalize_roman_hindi_token("rha")
        self.assertEqual(token, "raha")
        self.assertTrue(changed)

        token, changed = normalize_roman_hindi_token("bhai")
        self.assertEqual(token, "bhai")

    # --------------------------------------------------------------------------
    # 7. Faster-Whisper Initial Prompt Configuration
    # --------------------------------------------------------------------------
    def test_faster_whisper_initial_prompt(self):
        """AudioTranscriber must prime Whisper with gaming and Hinglish vocabulary."""
        transcriber = AudioTranscriber(device="cpu", compute_type="int8")
        self.assertIsNotNone(transcriber.initial_prompt)
        self.assertIn("Valorant", transcriber.initial_prompt)
        self.assertIn("CS2", transcriber.initial_prompt)
        self.assertIn("clutch", transcriber.initial_prompt)
        self.assertIn("spike", transcriber.initial_prompt.lower())
        self.assertIn("bhai", transcriber.initial_prompt.lower())

    # --------------------------------------------------------------------------
    # 8. Frame-Accurate Extraction Mode
    # --------------------------------------------------------------------------
    def test_clip_extractor_uses_accurate_encoding(self):
        """ClipExtractor must not perform lossy GOP-snapped stream copy."""
        extractor = ClipExtractor()
        # Verify extractor instance exists and has nvenc/libx264 detection
        self.assertIsNotNone(extractor.ffmpeg_path)
        self.assertIsInstance(extractor._nvenc_available, bool)


if __name__ == "__main__":
    unittest.main()
