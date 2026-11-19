"""Deterministic language and script detection for English, Hindi, Roman Hindi, and Hinglish."""

import re
from typing import Dict, Any, List, Tuple
from .roman_hindi import is_roman_hindi_word
from .gaming_terms import is_gaming_term

# Common English function words and vocabulary
COMMON_ENGLISH_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not",
    "on", "with", "he", "as", "you", "do", "at", "this", "but", "his", "by", "from",
    "they", "we", "say", "her", "she", "or", "an", "will", "my", "one", "all", "would",
    "there", "their", "what", "so", "up", "out", "if", "about", "who", "get", "which",
    "go", "me", "when", "make", "can", "like", "time", "no", "just", "him", "know",
    "take", "people", "into", "year", "your", "good", "some", "could", "them", "see",
    "other", "than", "then", "now", "look", "only", "come", "its", "over", "think",
    "also", "back", "after", "use", "two", "how", "our", "work", "first", "well",
    "way", "even", "new", "want", "because", "any", "these", "give", "day", "most",
    "us", "is", "was", "are", "were", "been", "has", "had", "did", "got", "wait",
    "bro", "man", "insane", "literally", "crazy", "dude", "nice", "omg", "oh", "god",
    "dead", "kill", "left", "right", "behind", "front", "here", "there", "where",
}

# Devanagari Unicode regex pattern
DEVANAGARI_PATTERN = re.compile(r'[\u0900-\u097F]')


def detect_language(text: str) -> Dict[str, Any]:
    """
    Deterministically detects whether text is english, hindi (Devanagari),
    roman_hindi, or hinglish (mixed Roman Hindi + English/Gaming).

    Returns:
        {
            "language": "english" | "hindi" | "roman_hindi" | "hinglish" | "unknown",
            "confidence": float (0.0 to 1.0),
            "counts": {
                "english": int,
                "roman_hindi": int,
                "gaming": int,
                "total": int
            }
        }
    """
    if not text or not text.strip():
        return {
            "language": "unknown",
            "confidence": 0.0,
            "counts": {"english": 0, "roman_hindi": 0, "gaming": 0, "total": 0},
        }

    raw_text = text.strip()

    # 1. Check for Devanagari Hindi script
    if DEVANAGARI_PATTERN.search(raw_text):
        devanagari_chars = len(DEVANAGARI_PATTERN.findall(raw_text))
        total_chars = max(1, len(re.sub(r'\s+', '', raw_text)))
        conf = min(1.0, max(0.60, devanagari_chars / total_chars))
        return {
            "language": "hindi",
            "confidence": round(conf, 2),
            "counts": {"english": 0, "roman_hindi": 0, "gaming": 0, "total": total_chars},
        }

    # 2. Tokenize Latin-script words
    words = re.findall(r"[A-Za-z0-9_:-]+", raw_text.lower())
    if not words:
        return {
            "language": "unknown",
            "confidence": 0.0,
            "counts": {"english": 0, "roman_hindi": 0, "gaming": 0, "total": 0},
        }

    rh_count = 0
    en_count = 0
    gaming_count = 0
    total = len(words)

    for w in words:
        is_rh = is_roman_hindi_word(w)
        is_game = is_gaming_term(w)
        is_en = (w in COMMON_ENGLISH_WORDS) or is_game

        if is_rh:
            rh_count += 1
        elif is_game:
            gaming_count += 1
        elif is_en:
            en_count += 1

    # 3. Categorization logic
    recognized_tokens = rh_count + en_count + gaming_count
    token_confidence = min(0.98, max(0.50, recognized_tokens / max(1, total)))

    # Both Roman Hindi and English/Gaming vocabulary present -> Hinglish
    if rh_count > 0 and (en_count > 0 or gaming_count > 0):
        return {
            "language": "hinglish",
            "confidence": round(token_confidence, 2),
            "counts": {"english": en_count, "roman_hindi": rh_count, "gaming": gaming_count, "total": total},
        }

    # Only Roman Hindi markers present
    if rh_count > 0 and en_count == 0 and gaming_count == 0:
        return {
            "language": "roman_hindi",
            "confidence": round(token_confidence, 2),
            "counts": {"english": en_count, "roman_hindi": rh_count, "gaming": gaming_count, "total": total},
        }

    # Only English words present
    if en_count > 0 and rh_count == 0:
        return {
            "language": "english",
            "confidence": round(token_confidence, 2),
            "counts": {"english": en_count, "roman_hindi": rh_count, "gaming": gaming_count, "total": total},
        }

    # Only gaming terms
    if gaming_count > 0 and rh_count == 0 and en_count == 0:
        return {
            "language": "english",
            "confidence": round(token_confidence, 2),
            "counts": {"english": en_count, "roman_hindi": rh_count, "gaming": gaming_count, "total": total},
        }

    return {
        "language": "unknown",
        "confidence": 0.40,
        "counts": {"english": en_count, "roman_hindi": rh_count, "gaming": gaming_count, "total": total},
    }
