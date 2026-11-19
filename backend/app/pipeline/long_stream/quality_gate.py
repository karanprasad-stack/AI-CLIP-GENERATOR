"""Quality Gate: enforces quality-based Shorts recommendations and score cliff detection."""

from typing import List, Dict, Any, Tuple, Optional
from backend.app.config import (
    QUALITY_GATE_MIN_SCORE,
    QUALITY_GATE_STRONG_SCORE,
    SCORE_GAP_THRESHOLD,
    MAX_AUTO_SHORTS_RECOMMENDED,
    MIN_AUTO_SHORTS_RECOMMENDED,
)


def find_natural_score_gap(scores: List[float], min_index: int = 3, threshold: float = SCORE_GAP_THRESHOLD) -> Optional[int]:
    """
    Identifies a significant cliff in a descending score list.
    Returns the index cutoff where the drop occurs (e.g., between score[i-1] and score[i]).
    """
    for i in range(min_index, len(scores)):
        gap = scores[i - 1] - scores[i]
        if gap >= threshold:
            return i
    return None


class QualityGate:
    """Evaluates candidate quality, score distribution, and determines recommended Shorts quota."""

    def __init__(
        self,
        min_score: float = QUALITY_GATE_MIN_SCORE,
        strong_score: float = QUALITY_GATE_STRONG_SCORE,
        score_gap_threshold: float = SCORE_GAP_THRESHOLD,
        min_auto_recommend: int = MIN_AUTO_SHORTS_RECOMMENDED,
        max_auto_recommend: int = MAX_AUTO_SHORTS_RECOMMENDED,
    ):
        self.min_score = min_score
        self.strong_score = strong_score
        self.score_gap_threshold = score_gap_threshold
        self.min_auto_recommend = min_auto_recommend
        self.max_auto_recommend = max_auto_recommend

    def evaluate(
        self,
        candidates: List[Dict[str, Any]],
        num_shorts_mode: str = "auto",
        requested_count: int = 5,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Filters candidates through the quality gate and provides a transparent explanation.

        Args:
            candidates: Deduplicated, diverse candidate list sorted by score.
            num_shorts_mode: 'auto' or 'custom'.
            requested_count: User-requested count (used as ceiling in custom mode).

        Returns:
            (recommended_candidates, explanation_message)
        """
        if not candidates:
            return [], "No candidate moments discovered in source video."

        # Annotate candidates with quality status
        for c in candidates:
            score = float(c.get("final_score", 0.0))
            if score >= self.strong_score:
                c["quality_gate_status"] = "strong"
            elif score >= self.min_score:
                c["quality_gate_status"] = "acceptable"
            else:
                c["quality_gate_status"] = "weak"

        scores = [float(c.get("final_score", 0.0)) for c in candidates]
        strong_moments = sum(1 for s in scores if s >= self.strong_score)
        acceptable_candidates = [c for c in candidates if c["quality_gate_status"] in ("strong", "acceptable")]

        if not acceptable_candidates:
            # Fall back to top candidate if all are below floor, but explicitly flag
            top_cand = candidates[0]
            top_cand["selection_reason"] = "Highest available moment (below standard quality threshold)"
            return [top_cand], "No moments met the quality threshold. Returning 1 best candidate."

        # Detect natural score cliff
        gap_idx = find_natural_score_gap(scores, min_index=self.min_auto_recommend, threshold=self.score_gap_threshold)

        if num_shorts_mode == "auto":
            # Auto mode: select based on strong moments and natural score gap
            if gap_idx is not None:
                target_count = min(gap_idx, self.max_auto_recommend)
                target_count = max(self.min_auto_recommend, target_count)
            elif strong_moments >= self.min_auto_recommend:
                target_count = min(strong_moments, self.max_auto_recommend)
            else:
                target_count = min(len(acceptable_candidates), self.min_auto_recommend)

            target_count = min(target_count, len(acceptable_candidates))
            recommended = acceptable_candidates[:target_count]

            explanation = (
                f"Auto-selected {len(recommended)} high-quality Shorts from {len(candidates)} raw moments "
                f"({strong_moments} strong climaxes, natural score cutoff applied)."
            )

        else:
            # Custom mode: requested_count is the upper ceiling
            target_ceiling = min(requested_count, len(candidates))

            # Only accept candidates meeting minimum quality
            qualified = [c for c in candidates[:target_ceiling] if c["quality_gate_status"] in ("strong", "acceptable")]

            if len(qualified) < target_ceiling:
                recommended = qualified
                explanation = (
                    f"Recommended {len(recommended)} Shorts (out of {requested_count} requested). "
                    f"Remaining candidates did not meet the quality threshold ({self.min_score}+)."
                )
            else:
                recommended = qualified
                explanation = f"Recommended {len(recommended)} Shorts meeting all quality criteria."

        # Annotate selection reasons
        for rank, c in enumerate(recommended, start=1):
            c["selected"] = True
            q_status = c.get("quality_gate_status", "acceptable")
            c["selection_reason"] = f"Rank #{rank} - {q_status.capitalize()} climax (score: {c.get('final_score')})"

        return recommended, explanation
