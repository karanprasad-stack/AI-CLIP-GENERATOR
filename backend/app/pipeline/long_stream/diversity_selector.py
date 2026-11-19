"""Diversity Selector: enforces temporal distribution and narrative event diversity across multi-hour streams."""

from typing import List, Dict, Any
from backend.app.config import (
    TEMPORAL_DIVERSITY_MIN_GAP_SEC,
    DIVERSITY_BONUS,
    DIVERSITY_PENALTY,
)


def extract_event_category(candidate: Dict[str, Any]) -> str:
    """Categorizes candidate into broad gameplay/reaction buckets."""
    event = str(candidate.get("gameplay_event", "")).lower()
    reaction = str(candidate.get("strongest_reaction", "")).lower()
    signals = [s.lower() for s in candidate.get("detected_signals", [])]

    # Check for clutch / ace / multi-kill
    if any(k in event or any(k in s for s in signals) for k in ["clutch", "ace", "1v", "kill", "headshot"]):
        return "clutch_combat"

    # Check for fail / death / wasted
    if any(k in event or any(k in s for s in signals) for k in ["fail", "wasted", "busted", "died", "loss"]):
        return "fail_blunder"

    # Check for funny / laughter / banter
    if any(k in event or any(k in s for s in signals) for k in ["funny", "laugh", "troll", "joke", "chaos"]):
        return "funny_chaos"

    # Check for reaction / shock / rage
    if any(k in reaction or any(k in s for s in signals) for k in ["rage", "omg", "screaming", "shock", "surprise"]):
        return "reaction_hype"

    return "highlight_moment"


class DiversitySelector:
    """Selects candidates that maximize temporal spread and narrative variety."""

    def __init__(
        self,
        min_temporal_gap_sec: float = TEMPORAL_DIVERSITY_MIN_GAP_SEC,
        diversity_bonus: float = DIVERSITY_BONUS,
        diversity_penalty: float = DIVERSITY_PENALTY,
    ):
        self.min_temporal_gap_sec = min_temporal_gap_sec
        self.diversity_bonus = diversity_bonus
        self.diversity_penalty = diversity_penalty

    def select_diverse(
        self,
        candidates: List[Dict[str, Any]],
        target_count: int,
    ) -> List[Dict[str, Any]]:
        """
        Picks up to target_count candidates balancing high score with temporal and event diversity.
        """
        if not candidates or target_count <= 0:
            return []

        remaining = [dict(c) for c in candidates]
        selected: List[Dict[str, Any]] = []
        category_counts: Dict[str, int] = {}

        while len(selected) < target_count and remaining:
            # Score each candidate in context of currently selected set
            best_idx = -1
            best_adjusted_score = -9999.0

            for i, cand in enumerate(remaining):
                base_score = float(cand.get("final_score", 50.0))
                cat = extract_event_category(cand)

                # 1. Temporal proximity penalty
                temp_penalty = 0.0
                cand_start = cand.get("start", 0.0)
                for sel in selected:
                    sel_start = sel.get("start", 0.0)
                    dist = abs(cand_start - sel_start)
                    if dist < self.min_temporal_gap_sec:
                        ratio = (self.min_temporal_gap_sec - dist) / self.min_temporal_gap_sec
                        # Scale proximity penalty up to 25 points when directly adjacent
                        temp_penalty = max(temp_penalty, ratio * 25.0)

                # 2. Event category diversity penalty/bonus
                cat_count = category_counts.get(cat, 0)
                if cat_count == 0:
                    cat_adjust = self.diversity_bonus
                else:
                    cat_adjust = - (cat_count * self.diversity_penalty)

                adjusted_score = base_score - temp_penalty + cat_adjust

                if adjusted_score > best_adjusted_score:
                    best_adjusted_score = adjusted_score
                    best_idx = i

            if best_idx < 0:
                break

            chosen = remaining.pop(best_idx)
            chosen_cat = extract_event_category(chosen)
            category_counts[chosen_cat] = category_counts.get(chosen_cat, 0) + 1
            chosen["diversity_group"] = chosen_cat
            selected.append(chosen)

        # Sort selected by global_rank / final_score
        selected.sort(key=lambda c: (-c.get("final_score", 0.0), c.get("start", 0.0)))
        return selected
