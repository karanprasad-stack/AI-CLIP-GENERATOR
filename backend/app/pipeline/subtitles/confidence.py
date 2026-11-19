"""Confidence scoring and fallback evaluation for Hinglish subtitle normalization."""

from typing import List, Dict, Any

# Minimum confidence required to accept a normalized subtitle segment
MIN_NORMALIZATION_CONFIDENCE = 0.60


class ConfidenceEvaluator:
    """Evaluates normalization confidence and protects against hallucination."""

    def __init__(self, threshold: float = MIN_NORMALIZATION_CONFIDENCE):
        self.threshold = threshold

    def evaluate_segment_confidence(
        self,
        original_words: List[Dict[str, Any]],
        normalized_words: List[Dict[str, Any]],
        language_info: Dict[str, Any],
        substitutions_made: int = 0,
    ) -> float:
        """
        Calculates a confidence score between 0.0 and 1.0.

        Factors:
        1. Language detection confidence.
        2. Proportional changes: modest spelling corrections boost confidence;
           massive alterations lower confidence.
        3. Word counts alignment.
        """
        base_conf = float(language_info.get("confidence", 0.80))
        total_words = max(1, len(original_words))

        # If no changes were made, confidence is high (original is inherently faithful)
        if substitutions_made == 0:
            return min(1.0, max(0.85, base_conf))

        # Check word count stability
        word_count_ratio = min(len(normalized_words), total_words) / max(len(normalized_words), total_words)
        if word_count_ratio < 0.70:
            # Drastic word count change -> drop confidence
            return round(base_conf * 0.50, 2)

        # Substitution ratio (normalizing 1-2 words in a 6-word sentence is normal;
        # replacing 100% of tokens without high language confidence is risky)
        sub_ratio = substitutions_made / total_words
        if sub_ratio > 0.80 and base_conf < 0.75:
            return round(base_conf * 0.70, 2)

        final_conf = (base_conf * 0.70) + (word_count_ratio * 0.30)
        return round(min(0.98, max(0.40, final_conf)), 2)

    def should_fallback(self, confidence: float) -> bool:
        """Returns True if confidence is below the safety threshold."""
        return confidence < self.threshold
