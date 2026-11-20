"""Global Ranker: aggregates, calibrates, and ranks candidates across all stream chunks."""

from typing import List, Dict, Any, Optional
import numpy as np


class GlobalRanker:
    """Aggregates candidates from all chunks and establishes global score normalization."""

    def __init__(self, weights: Dict[str, float] = None):
        self.weights = weights or {
            "audio": 0.25,
            "transcript": 0.20,
            "gameplay_event": 0.25,
            "context": 0.20,
            "boundary": 0.10,
        }

    def calibrate_and_rank(
        self,
        raw_candidates: List[Dict[str, Any]],
        gameplay_timeline: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Calibrates candidates from all chunks and ranks them globally.
        Preserves transparent scoring invariants and assigns global ranks.
        """
        if not raw_candidates:
            return []

        candidates = [dict(c) for c in raw_candidates]

        timeline_weights = None
        if gameplay_timeline and hasattr(gameplay_timeline, "metadata"):
            timeline_weights = gameplay_timeline.metadata.get("scoring_weights")

        # Verify component score consistency and recompute transparent composite score
        for c in candidates:
            scores = c.get("component_scores") or c.get("scores") or {}
            w = c.get("active_weights") or timeline_weights or self.weights
            if scores:
                composite = sum(
                    w.get(k, 0.0) * float(scores.get(k, 0.0))
                    for k in w
                )
                c["final_score"] = round(composite, 1)
                c["score"] = c["final_score"]
            else:
                c["final_score"] = round(float(c.get("final_score", c.get("score", 50.0))), 1)
                c["score"] = c["final_score"]

        # Sort candidates globally by final_score descending
        # Deterministic tie-breaker: score -> duration -> start timestamp -> chunk_id
        candidates.sort(
            key=lambda c: (
                -c["final_score"],
                -c.get("duration", 0.0),
                c.get("start", 0.0),
                c.get("chunk_id", ""),
            )
        )

        for idx, cand in enumerate(candidates, start=1):
            cand["global_rank"] = idx

        return candidates
