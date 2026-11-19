"""Phase 7D: Hinglish Subtitle Intelligence Engine."""

from .language_detector import detect_language
from .gaming_terms import is_gaming_term, get_canonical_gaming_term, is_acronym_or_proper_name, PROTECTED_GAMING_TERMS
from .roman_hindi import is_roman_hindi_word, normalize_roman_hindi_token, ROMAN_HINDI_MARKERS, ROMAN_HINDI_SPELLINGS
from .confidence import ConfidenceEvaluator, MIN_NORMALIZATION_CONFIDENCE
from .normalizer import HinglishNormalizer
from .subtitle_grouping import SubtitleGrouper

__all__ = [
    "detect_language",
    "is_gaming_term",
    "get_canonical_gaming_term",
    "is_acronym_or_proper_name",
    "PROTECTED_GAMING_TERMS",
    "is_roman_hindi_word",
    "normalize_roman_hindi_token",
    "ROMAN_HINDI_MARKERS",
    "ROMAN_HINDI_SPELLINGS",
    "ConfidenceEvaluator",
    "MIN_NORMALIZATION_CONFIDENCE",
    "HinglishNormalizer",
    "SubtitleGrouper",
]
