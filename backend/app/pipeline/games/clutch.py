"""Conservative clutch candidate detector based on eliminations, round wins, and disadvantaged context."""

import uuid
from typing import List, Dict, Any, Optional

from .models import GameplayEvent, EventType, EventStatus, EvidenceBreakdown


class ClutchDetector:
    """Detects conservative clutch candidates requiring multiple eliminations followed by a round win."""

    def __init__(self, clutch_window_sec: float = 28.0):
        self.clutch_window_sec = clutch_window_sec

    def detect_clutches(self, events: List[GameplayEvent]) -> List[GameplayEvent]:
        """
        Scans for round_win events, inspects preceding kills in the round window,
        and evaluates whether a clutch occurred.
        """
        round_wins = [e for e in events if e.event_type == EventType.ROUND_WIN.value]
        if not round_wins:
            return events

        clutch_events: List[GameplayEvent] = []

        for rw in round_wins:
            rw_t = rw.start_time
            window_start = max(0.0, rw_t - self.clutch_window_sec)

            # Find all kills occurring in the lead-up window
            window_kills = [
                e for e in events
                if e.event_type == EventType.KILL.value and window_start <= e.start_time <= rw_t
            ]

            if not window_kills:
                continue

            # Check vocal/transcript context for disadvantage clues
            clutch_vocal_events = [
                e for e in events
                if e.event_type == EventType.REACTION.value
                and window_start <= e.start_time <= (rw_t + 2.0)
                and any(term in str(e.metadata.get("spoken_term", "")).lower() for term in ["clutch", "1v", "last one", "bhai"])
            ]

            # Require at least 2 kills in the window (e.g. 1v2 or 1v3)
            # OR 1 kill + explicit 'clutch' vocal reaction followed immediately by round win
            kills_count = len(window_kills)
            has_clutch_vocal = bool(clutch_vocal_events)

            is_clutch_candidate = (kills_count >= 2) or (kills_count >= 1 and has_clutch_vocal)

            if is_clutch_candidate:
                first_kill_t = window_kills[0].start_time
                clutch_start = first_kill_t
                clutch_end = rw.end_time
                dur = round(clutch_end - clutch_start, 2)

                # Confidence calculation
                base_conf = 0.70
                if kills_count >= 2:
                    base_conf += 0.12
                if kills_count >= 3:
                    base_conf += 0.08
                if has_clutch_vocal:
                    base_conf += 0.06

                final_conf = min(0.96, round(base_conf, 3))
                status = EventStatus.CONFIRMED.value if (kills_count >= 2 and final_conf >= 0.80) else EventStatus.CANDIDATE.value

                est_opponents = max(2, kills_count)
                clutch_title = f"1v{est_opponents} Clutch Candidate" if kills_count >= 2 else "Clutch Candidate"

                meta = {
                    "estimated_opponents": est_opponents,
                    "kills_in_clutch": kills_count,
                    "associated_round_win_id": rw.id,
                    "associated_kill_ids": [k.id for k in window_kills],
                    "has_vocal_callout": has_clutch_vocal,
                }

                clutch_ev = GameplayEvent(
                    id=f"clutch_{uuid.uuid4().hex[:8]}",
                    game=rw.game,
                    event_type=EventType.CLUTCH_CANDIDATE.value,
                    start_time=clutch_start,
                    end_time=clutch_end,
                    confidence=final_conf,
                    status=status,
                    source_evidence={
                        "round_win": rw.confidence,
                        "kills_confidence": sum(k.confidence for k in window_kills) / float(len(window_kills)),
                        "transcript": 0.80 if has_clutch_vocal else 0.40,
                    },
                    metadata=meta,
                    explanation=f"{clutch_title}: {kills_count} elimination(s) secured in {dur:.1f}s followed by confirmed round win",
                )
                clutch_events.append(clutch_ev)

        combined = list(events) + clutch_events
        combined.sort(key=lambda e: (e.start_time, e.end_time))
        return combined
