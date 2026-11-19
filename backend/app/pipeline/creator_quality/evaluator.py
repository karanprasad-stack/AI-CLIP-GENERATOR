"""Creator Quality Evaluator: orchestrates 6-dimension evaluation and generates publishability score and audit."""

from typing import Dict, Any, List, Optional
from backend.app.config import (
    PUBLISHABILITY_THRESHOLDS,
    PUBLISHABILITY_DIMENSION_WEIGHTS,
    CREATOR_GATE_PASS_SCORE,
    CREATOR_GATE_REVIEW_SCORE,
)
from .dimensions import (
    evaluate_moment_quality,
    evaluate_narrative_quality,
    evaluate_presentation_quality,
    evaluate_publishing_quality,
    evaluate_technical_quality,
    evaluate_diversity_quality,
)


class CreatorQualityEvaluator:
    """Evaluates candidates and completed publishing packages across all 6 creator dimensions."""

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        thresholds: Optional[Dict[str, float]] = None,
    ):
        self.weights = weights or dict(PUBLISHABILITY_DIMENSION_WEIGHTS)
        self.thresholds = thresholds or dict(PUBLISHABILITY_THRESHOLDS)

    def evaluate(
        self,
        candidate: Dict[str, Any],
        package_info: Optional[Dict[str, Any]] = None,
        transcript_words: Optional[List[Dict[str, Any]]] = None,
        subtitles_info: Optional[Dict[str, Any]] = None,
        effects_info: Optional[Dict[str, Any]] = None,
        audio_info: Optional[Dict[str, Any]] = None,
        all_candidates: Optional[List[Dict[str, Any]]] = None,
        selected_candidates: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Runs comprehensive evaluation across all 6 dimensions.
        Returns publishability block with score, level, recommendation, breakdown, and audit notes.
        """
        dim_moment = evaluate_moment_quality(candidate)
        dim_narrative = evaluate_narrative_quality(candidate, transcript_words=transcript_words)
        dim_presentation = evaluate_presentation_quality(
            candidate,
            subtitles_info=subtitles_info,
            effects_info=effects_info,
            audio_info=audio_info,
        )
        dim_publishing = evaluate_publishing_quality(candidate, package_info=package_info)
        dim_technical = evaluate_technical_quality(candidate, package_info=package_info)
        dim_diversity = evaluate_diversity_quality(
            candidate,
            all_candidates=all_candidates,
            selected_candidates=selected_candidates,
        )

        dimension_scores = {
            "moment": dim_moment["score"],
            "narrative": dim_narrative["score"],
            "presentation": dim_presentation["score"],
            "publishing": dim_publishing["score"],
            "technical": dim_technical["score"],
            "diversity": dim_diversity["score"],
        }

        # Calculate weighted composite publishability score
        composite_score = sum(
            dimension_scores[k] * self.weights.get(k, 0.0)
            for k in dimension_scores
        )
        composite_score = round(max(0.0, min(100.0, composite_score)), 1)

        # Collect explanations, warnings, and blocking issues
        reasons: List[str] = []
        warnings: List[str] = []
        blocking_issues: List[str] = []

        for dim in (dim_moment, dim_narrative, dim_presentation, dim_publishing, dim_technical, dim_diversity):
            reasons.extend(dim.get("reasons", []))
            warnings.extend(dim.get("warnings", []))
            blocking_issues.extend(dim.get("blocking_issues", []))

        # Determine Quality Level
        if composite_score >= self.thresholds.get("excellent", 90.0):
            level = "excellent"
        elif composite_score >= self.thresholds.get("strong", 80.0):
            level = "strong"
        elif composite_score >= self.thresholds.get("review", 65.0):
            level = "review"
        elif composite_score >= self.thresholds.get("weak", 50.0):
            level = "weak"
        else:
            level = "reject"

        # Determine Recommendation
        raw_final = float(candidate.get("final_score", 0.0))
        if blocking_issues:
            recommendation = "reject"
            if level in ("excellent", "strong"):
                level = "review"
        elif composite_score >= CREATOR_GATE_PASS_SCORE and dimension_scores["moment"] >= 70.0 and raw_final >= 65.0:
            recommendation = "publish"
        elif composite_score >= CREATOR_GATE_REVIEW_SCORE:
            recommendation = "review"
        else:
            recommendation = "reject"

        return {
            "score": composite_score,
            "level": level,
            "recommendation": recommendation,
            "dimensions": dimension_scores,
            "reasons": reasons[:6],  # Top prominent reasons
            "warnings": warnings,
            "blocking_issues": blocking_issues,
        }
