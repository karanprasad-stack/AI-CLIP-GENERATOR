"""Publishability Gate: enforces creator quality gating, Auto vs Custom quota semantics, and transparent explanations."""

from typing import List, Dict, Any, Tuple, Optional
from backend.app.config import CREATOR_GATE_PASS_SCORE, CREATOR_GATE_REVIEW_SCORE
from .evaluator import CreatorQualityEvaluator


class PublishabilityGate:
    """Evaluates candidates or packages against creator quality standards."""

    def __init__(
        self,
        evaluator: Optional[CreatorQualityEvaluator] = None,
        pass_score: float = CREATOR_GATE_PASS_SCORE,
        review_score: float = CREATOR_GATE_REVIEW_SCORE,
    ):
        self.evaluator = evaluator or CreatorQualityEvaluator()
        self.pass_score = pass_score
        self.review_score = review_score

    def filter_candidates(
        self,
        candidates: List[Dict[str, Any]],
        num_shorts_mode: str = "auto",
        requested_count: int = 5,
        transcript_words: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Filters candidates based on Creator Quality standards.

        Args:
            candidates: Detected candidate list.
            num_shorts_mode: 'auto' or 'custom'.
            requested_count: User ceiling in custom mode.
            transcript_words: Optional word-level transcript for narrative checks.

        Returns:
            (selected_candidates, transparent_explanation)
        """
        if not candidates:
            return [], "No candidate moments discovered."

        # Evaluate publishability for each candidate if not already present
        evaluated_candidates = []
        for c in candidates:
            cand_copy = dict(c)
            if "publishability" not in cand_copy:
                cand_copy["publishability"] = self.evaluator.evaluate(
                    cand_copy,
                    transcript_words=transcript_words,
                    all_candidates=candidates,
                )
            evaluated_candidates.append(cand_copy)

        # Categorize by recommendation
        publish_pool = [c for c in evaluated_candidates if c["publishability"]["recommendation"] == "publish"]
        review_pool = [c for c in evaluated_candidates if c["publishability"]["recommendation"] == "review"]
        reject_pool = [c for c in evaluated_candidates if c["publishability"]["recommendation"] == "reject"]

        if num_shorts_mode == "auto":
            # Auto mode: only pick publish-ready candidates
            if publish_pool:
                selected = publish_pool
                explanation = (
                    f"Creator Gate Auto: {len(selected)} Shorts passed all 6 creator dimensions "
                    f"({len(review_pool)} need creator review, {len(reject_pool)} rejected)."
                )
            elif review_pool:
                # If none cleanly publishable, offer the best review candidate
                selected = [review_pool[0]]
                selected[0]["selection_reason"] = "Borderline candidate requiring creator review before publishing"
                explanation = "No candidates achieved instant 'Publish' rating. Recommended top 1 candidate for creator review."
            else:
                top_cand = evaluated_candidates[0]
                top_cand["selection_reason"] = "Highest available moment (flagged for review)"
                selected = [top_cand]
                explanation = "All moments scored below creator publishing threshold. Returning 1 best candidate."

        else:
            # Custom mode: requested_count is an upper ceiling
            target_ceiling = min(requested_count, len(evaluated_candidates))

            # Prioritize publish pool, then review pool, never auto-select hard rejects
            candidate_ladder = publish_pool + review_pool
            selected = candidate_ladder[:target_ceiling]

            if len(selected) < requested_count:
                explanation = (
                    f"Creator Gate Custom: Selected {len(selected)} Shorts meeting quality criteria "
                    f"(out of {requested_count} requested). System declined to manufacture {requested_count - len(selected)} weak Shorts."
                )
            else:
                explanation = (
                    f"Creator Gate Custom: Selected {len(selected)} Shorts meeting quality criteria."
                )

        return selected, explanation
