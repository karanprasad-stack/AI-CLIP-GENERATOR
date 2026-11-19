"""Persistent, queryable Gameplay Event Timeline supporting global stream timestamps and deduplication."""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from .models import GameplayEvent, EventType, EventStatus


class GameplayTimeline:
    """Persistent container for structured gameplay events and sequences across full videos, chunks, or live sessions."""

    def __init__(
        self,
        game: str = "generic",
        events: Optional[List[GameplayEvent]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.game = game
        self.events: List[GameplayEvent] = events or []
        self.metadata: Dict[str, Any] = metadata or {}

    def add_event(self, event: GameplayEvent) -> None:
        """Appends a new event and keeps the timeline sorted by start_time."""
        self.events.append(event)
        self.events.sort(key=lambda e: (e.start_time, e.end_time))

    def get_events_in_range(self, start_sec: float, end_sec: float) -> List[GameplayEvent]:
        """Returns all events overlapping the [start_sec, end_sec] interval."""
        return [
            e for e in self.events
            if e.start_time < end_sec and e.end_time > start_sec
        ]

    def get_events_by_type(self, event_type: str) -> List[GameplayEvent]:
        """Filters events by EventType value."""
        return [e for e in self.events if e.event_type == event_type]

    def summary(self) -> Dict[str, Any]:
        """Computes executive summary statistics across the event timeline."""
        kills = [e for e in self.events if e.event_type == EventType.KILL.value]
        headshots = [e for e in self.events if e.event_type == EventType.HEADSHOT.value or e.metadata.get("headshot")]
        two_ks = [e for e in self.events if e.metadata.get("subtype") == "2k"]
        three_ks = [e for e in self.events if e.metadata.get("subtype") == "3k"]
        four_ks = [e for e in self.events if e.metadata.get("subtype") == "4k"]
        aces = [e for e in self.events if e.event_type == EventType.ACE.value]
        ace_candidates = [e for e in self.events if e.event_type == EventType.ACE_CANDIDATE.value]
        clutches = [e for e in self.events if e.event_type == EventType.CLUTCH_CANDIDATE.value]
        round_wins = [e for e in self.events if e.event_type == EventType.ROUND_WIN.value]
        spike_events = [e for e in self.events if e.event_type in [EventType.SPIKE_PLANTED.value, EventType.SPIKE_DEFUSED.value]]

        return {
            "game": self.game,
            "total_events": len(self.events),
            "kills_count": len(kills),
            "headshots_count": len(headshots),
            "two_k_count": len(two_ks),
            "three_k_count": len(three_ks),
            "four_k_count": len(four_ks),
            "aces_count": len(aces),
            "ace_candidates_count": len(ace_candidates),
            "clutches_count": len(clutches),
            "round_wins_count": len(round_wins),
            "spike_events_count": len(spike_events),
        }

    def deduplicate(self, tolerance_sec: float = 0.60) -> "GameplayTimeline":
        """
        Deduplicates identical events from overlapping stream chunks (Phase 7C / Phase 9).
        Matches events of identical event_type whose start times are within tolerance_sec.
        """
        if not self.events:
            return self

        sorted_events = sorted(self.events, key=lambda e: (e.start_time, -e.confidence))
        deduped: List[GameplayEvent] = []

        for ev in sorted_events:
            is_dup = False
            for accepted in deduped:
                if ev.event_type == accepted.event_type and abs(ev.start_time - accepted.start_time) <= tolerance_sec:
                    # If this duplicate has higher confidence, update the accepted event
                    if ev.confidence > accepted.confidence:
                        accepted.confidence = ev.confidence
                        accepted.source_evidence = ev.source_evidence
                        accepted.explanation = ev.explanation
                    is_dup = True
                    break

            if not is_dup:
                deduped.append(ev)

        self.events = sorted(deduped, key=lambda e: (e.start_time, e.end_time))
        return self

    def shift_timestamps(self, offset_sec: float) -> "GameplayTimeline":
        """Converts chunk-local timestamps into global stream timestamps."""
        for ev in self.events:
            ev.start_time = round(ev.start_time + offset_sec, 3)
            ev.end_time = round(ev.end_time + offset_sec, 3)
        return self

    def save(self, path: Path) -> Path:
        """Persists timeline to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "game": self.game,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": self.summary(),
            "metadata": self.metadata,
            "events": [e.to_dict() for e in self.events],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    @classmethod
    def load(cls, path: Path) -> "GameplayTimeline":
        """Loads timeline from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_events = data.get("events", [])
        events = [GameplayEvent.from_dict(d) for d in raw_events]
        return cls(
            game=data.get("game", "generic"),
            events=events,
            metadata=data.get("metadata", {}),
        )
