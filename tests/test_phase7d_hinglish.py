"""Tests for Phase 7D: Hinglish Subtitle Intelligence Engine.

Covers:
- Language & script detection (English, Hindi, Roman Hindi, Hinglish)
- Roman Hindi spelling normalization (kr rha -> kar raha, etc.)
- Gaming vocabulary protection (clutch, rush, one tap, headshot)
- Proper names & game title protection (Valorant, CS:GO, GTA, Minecraft)
- Acronym protection (HP, FPS, RTX, GPU, CPU, AWP, AK)
- Word-level timestamp preservation (start, end invariance)
- Confidence evaluation and low-confidence fallback to original text
- ASS karaoke rendering compatibility
- Auto mode vs Hinglish mode vs Original mode
- Long-stream chunk timestamp preservation
"""

import unittest
from backend.app.pipeline.subtitles.language_detector import detect_language
from backend.app.pipeline.subtitles.gaming_terms import (
    is_gaming_term,
    get_canonical_gaming_term,
    is_acronym_or_proper_name,
)
from backend.app.pipeline.subtitles.roman_hindi import (
    is_roman_hindi_word,
    normalize_roman_hindi_token,
)
from backend.app.pipeline.subtitles.normalizer import HinglishNormalizer
from backend.app.pipeline.subtitles.confidence import ConfidenceEvaluator
from backend.app.pipeline.caption_engine import CaptionEngine
from backend.app.pipeline.ass_generator import AssGenerator


class TestPhase7DHinglish(unittest.TestCase):
    """Unit test suite for Phase 7D Hinglish Subtitle Intelligence."""

    # --------------------------------------------------------------------------
    # 1. Language & Script Detection
    # --------------------------------------------------------------------------
    def test_language_detection_english(self):
        """Pure English gaming sentence is detected as English."""
        res = detect_language("bro that was insane")
        self.assertEqual(res["language"], "english")
        self.assertGreaterEqual(res["confidence"], 0.70)

    def test_language_detection_roman_hindi(self):
        """Roman Hindi sentence is detected as Roman Hindi."""
        res = detect_language("bhai ye kya ho gaya")
        self.assertEqual(res["language"], "roman_hindi")
        self.assertGreaterEqual(res["confidence"], 0.70)

    def test_language_detection_hinglish(self):
        """Mixed English and Roman Hindi is detected as Hinglish."""
        res = detect_language("bhai that was insane kya")
        self.assertEqual(res["language"], "hinglish")
        self.assertGreaterEqual(res["confidence"], 0.70)

    def test_language_detection_unicode_hindi(self):
        """Devanagari text is detected as Hindi."""
        res = detect_language("भाई क्या हो गया")
        self.assertEqual(res["language"], "hindi")
        self.assertGreaterEqual(res["confidence"], 0.80)

    # --------------------------------------------------------------------------
    # 2. Gaming Vocabulary Protection
    # --------------------------------------------------------------------------
    def test_gaming_vocabulary_protection(self):
        """Gaming terms like 'one tap', 'clutch', 'rush', 'headshot' are protected."""
        normalizer = HinglishNormalizer(mode="hinglish")
        segment = {
            "start": 10.0,
            "end": 14.0,
            "text": "bhai one tap ho gaya",
            "words": [
                {"start": 10.0, "end": 10.5, "word": "bhai"},
                {"start": 10.6, "end": 11.2, "word": "one"},
                {"start": 11.3, "end": 12.0, "word": "tap"},
                {"start": 12.1, "end": 12.8, "word": "ho"},
                {"start": 12.9, "end": 14.0, "word": "gaya"},
            ],
        }
        res = normalizer.normalize_segment(segment)
        norm_text = res["normalized_text"]

        # 'one tap' must remain preserved as English gaming term, not translated
        self.assertIn("one tap", norm_text.lower())
        self.assertEqual(norm_text, "Bhai one tap ho gaya")
        # Original text preserved
        self.assertEqual(res["original_text"], "bhai one tap ho gaya")

    # --------------------------------------------------------------------------
    # 3. Spelling & Contraction Normalization
    # --------------------------------------------------------------------------
    def test_spelling_normalization(self):
        """Informal contractions like 'kr rha' normalize to 'kar raha'."""
        normalizer = HinglishNormalizer(mode="hinglish")
        segment = {
            "start": 5.0,
            "end": 8.5,
            "text": "bhai kya kr rha hai",
            "words": [
                {"start": 5.0, "end": 5.5, "word": "bhai"},
                {"start": 5.6, "end": 6.2, "word": "kya"},
                {"start": 6.3, "end": 7.0, "word": "kr"},
                {"start": 7.1, "end": 7.8, "word": "rha"},
                {"start": 7.9, "end": 8.5, "word": "hai"},
            ],
        }
        res = normalizer.normalize_segment(segment)
        self.assertEqual(res["normalized_text"], "Bhai kya kar raha hai")
        self.assertEqual(res["original_text"], "bhai kya kr rha hai")
        self.assertTrue(res["normalization"]["changed"])

    # --------------------------------------------------------------------------
    # 4. Proper Name & Game Title Protection
    # --------------------------------------------------------------------------
    def test_proper_name_protection(self):
        """Game titles like Valorant, CS:GO, GTA, Minecraft are preserved with canonical casing."""
        normalizer = HinglishNormalizer(mode="hinglish")
        segment = {
            "start": 20.0,
            "end": 24.0,
            "text": "bhai valorant me kya ho gaya",
            "words": [
                {"start": 20.0, "end": 20.6, "word": "bhai"},
                {"start": 20.7, "end": 21.6, "word": "valorant"},
                {"start": 21.7, "end": 22.2, "word": "me"},
                {"start": 22.3, "end": 22.8, "word": "kya"},
                {"start": 22.9, "end": 23.4, "word": "ho"},
                {"start": 23.5, "end": 24.0, "word": "gaya"},
            ],
        }
        res = normalizer.normalize_segment(segment)
        self.assertIn("Valorant", res["normalized_text"])
        self.assertEqual(res["normalized_text"], "Bhai Valorant me kya ho gaya")

    # --------------------------------------------------------------------------
    # 5. Acronym Protection
    # --------------------------------------------------------------------------
    def test_acronym_protection(self):
        """Technical and gaming acronyms like HP, FPS, RTX, AWP are capitalized and protected."""
        normalizer = HinglishNormalizer(mode="hinglish")
        segment = {
            "start": 1.0,
            "end": 4.0,
            "text": "mera hp one tha",
            "words": [
                {"start": 1.0, "end": 1.6, "word": "mera"},
                {"start": 1.7, "end": 2.3, "word": "hp"},
                {"start": 2.4, "end": 3.0, "word": "one"},
                {"start": 3.1, "end": 4.0, "word": "tha"},
            ],
        }
        res = normalizer.normalize_segment(segment)
        self.assertIn("HP", res["normalized_text"])
        self.assertEqual(res["normalized_text"], "Mera HP one tha")

    # --------------------------------------------------------------------------
    # 6. Word-Level Timestamp Invariance
    # --------------------------------------------------------------------------
    def test_word_timestamp_invariance(self):
        """Normalization must not alter word start or end timestamps."""
        normalizer = HinglishNormalizer(mode="hinglish")
        raw_words = [
            {"start": 10.21, "end": 10.52, "word": "bhai"},
            {"start": 10.53, "end": 10.81, "word": "ye"},
            {"start": 10.82, "end": 11.15, "word": "kya"},
            {"start": 11.16, "end": 11.45, "word": "kr"},
            {"start": 11.46, "end": 11.90, "word": "rha"},
            {"start": 11.91, "end": 12.30, "word": "hai"},
        ]
        segment = {
            "start": 10.21,
            "end": 12.30,
            "text": "bhai ye kya kr rha hai",
            "words": raw_words,
        }

        res = normalizer.normalize_segment(segment)
        norm_words = res["words"]

        # Word count must match
        self.assertEqual(len(norm_words), len(raw_words))

        # Check every timestamp strictly preserved
        for orig, norm in zip(raw_words, norm_words):
            self.assertEqual(norm["start"], orig["start"])
            self.assertEqual(norm["end"], orig["end"])
            self.assertEqual(norm["original"], orig["word"])

    # --------------------------------------------------------------------------
    # 7. Confidence & Fallback to Original Transcript
    # --------------------------------------------------------------------------
    def test_low_confidence_fallback(self):
        """Unknown or unconfident text falls back safely to original text."""
        evaluator = ConfidenceEvaluator(threshold=0.60)
        self.assertTrue(evaluator.should_fallback(0.45))
        self.assertFalse(evaluator.should_fallback(0.85))

        normalizer = HinglishNormalizer(mode="hinglish", confidence_threshold=0.99)
        # Even with high threshold, original words are guaranteed to be returned
        segment = {
            "start": 1.0,
            "end": 3.0,
            "text": "xyzzy qwerty",
            "words": [
                {"start": 1.0, "end": 2.0, "word": "xyzzy"},
                {"start": 2.0, "end": 3.0, "word": "qwerty"},
            ],
        }
        res = normalizer.normalize_segment(segment)
        # Safe fallback
        self.assertEqual(res["normalized_text"], "xyzzy qwerty")

    # --------------------------------------------------------------------------
    # 8. ASS Karaoke Generator Compatibility
    # --------------------------------------------------------------------------
    def test_karaoke_ass_compatibility(self):
        """Normalized transcript feeds smoothly into CaptionEngine and AssGenerator."""
        normalizer = HinglishNormalizer(mode="hinglish")
        transcript_data = {
            "language": "hi-Latn",
            "duration": 20.0,
            "segments": [
                {
                    "start": 2.0,
                    "end": 5.0,
                    "text": "bhai clutch ho gaya",
                    "words": [
                        {"start": 2.0, "end": 2.6, "word": "bhai"},
                        {"start": 2.7, "end": 3.4, "word": "clutch"},
                        {"start": 3.5, "end": 4.1, "word": "ho"},
                        {"start": 4.2, "end": 5.0, "word": "gaya"},
                    ],
                }
            ],
        }

        normalized = normalizer.normalize_transcript(transcript_data)
        caption_engine = CaptionEngine()
        ass_generator = AssGenerator()

        groups = caption_engine.process_candidate(
            transcript_data=normalized,
            candidate_start=0.0,
            candidate_end=10.0,
            clip_duration=10.0,
        )

        self.assertGreater(len(groups), 0)
        ass_content = ass_generator.generate_ass(caption_groups=groups)

        self.assertIn("[Script Info]", ass_content)
        self.assertIn("[V4+ Styles]", ass_content)
        self.assertIn("Dialogue: 0,", ass_content)
        # Active word highlight tags must be present
        self.assertIn("\\c&H", ass_content)
        self.assertIn("Bhai", ass_content)
        self.assertIn("clutch", ass_content)

    # --------------------------------------------------------------------------
    # 9. Auto Mode Behavior
    # --------------------------------------------------------------------------
    def test_auto_mode_preserves_pure_english(self):
        """In Auto mode, English text is not mistakenly converted or corrupted."""
        normalizer = HinglishNormalizer(mode="auto")
        segment = {
            "start": 0.0,
            "end": 3.0,
            "text": "bro that was an insane headshot",
            "words": [
                {"start": 0.0, "end": 0.5, "word": "bro"},
                {"start": 0.6, "end": 1.0, "word": "that"},
                {"start": 1.1, "end": 1.4, "word": "was"},
                {"start": 1.5, "end": 1.7, "word": "an"},
                {"start": 1.8, "end": 2.3, "word": "insane"},
                {"start": 2.4, "end": 3.0, "word": "headshot"},
            ],
        }
        res = normalizer.normalize_segment(segment)
        self.assertEqual(res["language"], "en")
        self.assertEqual(res["normalized_text"], "Bro that was an insane headshot")

    # --------------------------------------------------------------------------
    # 10. Spoken Fillers Handling
    # --------------------------------------------------------------------------
    def test_filler_cleanup(self):
        """Leading hesitation fillers like 'umm' are safely pruned."""
        normalizer = HinglishNormalizer(mode="hinglish")
        segment = {
            "start": 1.0,
            "end": 4.0,
            "text": "umm bhai ye kya ho gaya",
            "words": [
                {"start": 1.0, "end": 1.4, "word": "umm"},
                {"start": 1.5, "end": 2.0, "word": "bhai"},
                {"start": 2.1, "end": 2.5, "word": "ye"},
                {"start": 2.6, "end": 3.0, "word": "kya"},
                {"start": 3.1, "end": 3.5, "word": "ho"},
                {"start": 3.6, "end": 4.0, "word": "gaya"},
            ],
        }
        res = normalizer.normalize_segment(segment)
        self.assertEqual(res["normalized_text"], "Bhai ye kya ho gaya")

    # --------------------------------------------------------------------------
    # 11. Complex Multi-Term Hinglish Gaming Sentences
    # --------------------------------------------------------------------------
    def test_complex_gaming_proper_names_and_acronyms(self):
        """Preserves multiple protected gaming terms and acronyms in a single sentence."""
        normalizer = HinglishNormalizer(mode="hinglish")
        segment = {
            "start": 10.0,
            "end": 14.5,
            "text": "bhai CS:GO me AWP drop kar",
            "words": [
                {"start": 10.0, "end": 10.5, "word": "bhai"},
                {"start": 10.6, "end": 11.5, "word": "cs:go"},
                {"start": 11.6, "end": 12.0, "word": "me"},
                {"start": 12.1, "end": 12.8, "word": "awp"},
                {"start": 12.9, "end": 13.5, "word": "drop"},
                {"start": 13.6, "end": 14.5, "word": "kar"},
            ],
        }
        res = normalizer.normalize_segment(segment)
        self.assertEqual(res["normalized_text"], "Bhai CS:GO me AWP drop kar")

    # --------------------------------------------------------------------------
    # 12. Long-Stream Chunk Timestamps Compatibility
    # --------------------------------------------------------------------------
    def test_long_stream_chunk_timestamp_preservation(self):
        """Verifies global multi-hour timestamps are untouched by normalization."""
        normalizer = HinglishNormalizer(mode="hinglish")
        # Chunk 12 starting at 2 hours (7200.0s)
        segment = {
            "start": 7210.5,
            "end": 7214.2,
            "text": "bhai clutch ho gaya",
            "words": [
                {"start": 7210.5, "end": 7211.2, "word": "bhai"},
                {"start": 7211.3, "end": 7212.5, "word": "clutch"},
                {"start": 7212.6, "end": 7213.2, "word": "ho"},
                {"start": 7213.3, "end": 7214.2, "word": "gaya"},
            ],
        }
        res = normalizer.normalize_segment(segment)
        self.assertEqual(res["words"][0]["start"], 7210.5)
        self.assertEqual(res["words"][-1]["end"], 7214.2)
        self.assertEqual(res["normalized_text"], "Bhai clutch ho gaya")


if __name__ == "__main__":
    unittest.main()
