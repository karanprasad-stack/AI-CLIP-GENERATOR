"""Temporal Deduplication: merges overlapping candidates and resolves nested moments."""

from typing import List, Dict, Any, Tuple, Optional
from backend.app.config import (
    IOU_DEDUPLICATION_THRESHOLD,
    MAX_OVERLAP_SECONDS,
)


def compute_overlap(cand1: Dict[str, Any], cand2: Dict[str, Any]) -> Tuple[float, float, float]:
    """
    Computes (intersection_sec, union_sec, iou) between two candidates.
    """
    s1, e1 = cand1["start"], cand1["end"]
    s2, e2 = cand2["start"], cand2["end"]

    inter_start = max(s1, s2)
    inter_end = min(e1, e2)
    inter = max(0.0, inter_end - inter_start)

    union = (e1 - s1) + (e2 - s2) - inter
    iou = inter / union if union > 0.0 else 0.0

    return round(inter, 2), round(union, 2), round(iou, 3)


def is_nested(cand1: Dict[str, Any], cand2: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Checks if one candidate is substantially nested inside another.
    Returns (is_nested, outer_candidate, inner_candidate).
    """
    s1, e1 = cand1["start"], cand1["end"]
    s2, e2 = cand2["start"], cand2["end"]

    # cand2 is nested inside cand1
    if s1 <= s2 + 3.0 and e1 >= e2 - 3.0:
        return True, cand1, cand2

    # cand1 is nested inside cand2
    if s2 <= s1 + 3.0 and e2 >= e1 - 3.0:
        return True, cand2, cand1

    return False, None, None


class TemporalDeduper:
    """Performs temporal deduplication and intelligent nested candidate resolution."""

    def __init__(
        self,
        iou_threshold: float = IOU_DEDUPLICATION_THRESHOLD,
        max_overlap_sec: float = MAX_OVERLAP_SECONDS,
    ):
        self.iou_threshold = iou_threshold
        self.max_overlap_sec = max_overlap_sec

    def deduplicate(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicates a list of globally ranked candidates.
        Resolves nested moments based on score, narrative context, and event tightness.
        """
        if not candidates:
            return []

        # Sort candidates by final_score descending
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (-c.get("final_score", 0.0), c.get("start", 0.0))
        )

        accepted: List[Dict[str, Any]] = []
        dup_group_id = 1

        for candidate in sorted_candidates:
            is_dup = False
            best_accepted_idx = -1

            for idx, existing in enumerate(accepted):
                inter, union, iou = compute_overlap(candidate, existing)

                # Check overlap criteria
                if iou >= self.iou_threshold or inter >= self.max_overlap_sec:
                    is_dup = True
                    best_accepted_idx = idx
                    break

                # Check nested candidate criteria
                nested, outer, inner = is_nested(candidate, existing)
                if nested and inner is not None and outer is not None:
                    # If inner covers the essential climax with higher density or tighter duration:
                    # Compare context scores
                    outer_ctx = (outer.get("component_scores") or {}).get("context", 50.0)
                    inner_ctx = (inner.get("component_scores") or {}).get("context", 50.0)
                    outer_score = outer.get("final_score", 0.0)
                    inner_score = inner.get("final_score", 0.0)

                    # If outer has a significantly better full Hook->Payoff structure (+8 pts), retain outer
                    if outer_ctx >= inner_ctx + 8.0 and outer_score >= inner_score - 2.0:
                        chosen = outer
                        pruned = inner
                    else:
                        # Otherwise prefer tighter, higher-scoring candidate
                        chosen = inner if inner_score >= outer_score else outer
                        pruned = outer if chosen is inner else inner

                    is_dup = True
                    # If candidate was the chosen one over existing, replace existing in accepted list
                    if chosen is candidate and existing in accepted:
                        accepted[idx] = candidate
                        candidate["duplicate_group"] = f"dup_group_{dup_group_id}"
                        candidate["dedup_reason"] = "Retained over wider/looser nested moment"
                    break

            if not is_dup:
                accepted.append(candidate)
            else:
                candidate["duplicate_group"] = f"dup_group_{dup_group_id}"
                dup_group_id += 1

        # Re-sort accepted by score
        accepted.sort(key=lambda c: (-c.get("final_score", 0.0), c.get("start", 0.0)))

        for rank, c in enumerate(accepted, start=1):
            c["global_rank"] = rank

        return accepted
