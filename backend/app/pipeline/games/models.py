"""Structured models for gameplay event detection, evidence breakdowns, and sequences."""

from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    # Tier 1 — Critical
    KILL = "kill"
    MULTI_KILL = "multi_kill"
    ROUND_WIN = "round_win"
    ACE = "ace"
    ACE_CANDIDATE = "ace_candidate"

    # Tier 2 — High Value
    HEADSHOT = "headshot"
    OPENING_KILL = "opening_kill"
    RAPID_KILL_SEQUENCE = "rapid_kill_sequence"
    CLUTCH_CANDIDATE = "clutch_candidate"
    LOW_HP_EVENT = "low_hp_event"
    ONE_V_X_CANDIDATE = "1vx_candidate"
    RETAKE_CANDIDATE = "retake_candidate"
    SPIKE_PLANTED = "spike_planted"
    SPIKE_DEFUSED = "spike_defused"
    ROUND_ENDING_KILL = "round_ending_kill"

    # Tier 3 — Supporting
    ABILITY_USAGE = "ability_usage"
    SNIPER_KILL = "sniper_kill"
    WALLBANG = "wallbang"
    REACTION = "reaction"
    AUDIO_SPIKE = "audio_spike"


class EventStatus(str, Enum):
    CONFIRMED = "confirmed"      # High-confidence cross-verified event (e.g. visual killfeed + audio/temporal)
    CANDIDATE = "candidate"      # Plausible event from partial evidence (e.g. strong audio burst + callout)
    SUPPORTING = "supporting"    # Supporting clue or context signal (e.g. single spoken word or volume peak)


class EvidenceBreakdown(BaseModel):
    """Transparent multi-modal evidence breakdown explaining event confidence."""
    visual: float = Field(default=0.0, ge=0.0, le=1.0)
    kill_feed: float = Field(default=0.0, ge=0.0, le=1.0)
    audio: float = Field(default=0.0, ge=0.0, le=1.0)
    transcript: float = Field(default=0.0, ge=0.0, le=1.0)
    temporal_consistency: float = Field(default=0.0, ge=0.0, le=1.0)
    cross_source_agreement: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_signals: Dict[str, Any] = Field(default_factory=dict)


class GameplayEvent(BaseModel):
    """Standardized representation of a single concrete gameplay event."""
    id: str
    game: str = "generic"
    event_type: str
    start_time: float
    end_time: float
    confidence: float = Field(ge=0.0, le=1.0)
    status: str = EventStatus.CANDIDATE.value
    source_evidence: Dict[str, float] = Field(default_factory=dict)
    evidence_breakdown: Optional[EvidenceBreakdown] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to clean dictionary."""
        data = self.model_dump()
        # Flatten evidence breakdown if present for easy JSON inspection
        if self.evidence_breakdown:
            data["evidence_breakdown"] = self.evidence_breakdown.model_dump()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameplayEvent":
        """Reconstruct event from dictionary."""
        ev_breakdown = None
        if "evidence_breakdown" in data and isinstance(data["evidence_breakdown"], dict):
            ev_breakdown = EvidenceBreakdown(**data["evidence_breakdown"])
        
        return cls(
            id=str(data["id"]),
            game=str(data.get("game", "generic")),
            event_type=str(data["event_type"]),
            start_time=float(data["start_time"]),
            end_time=float(data["end_time"]),
            confidence=float(data.get("confidence", 0.5)),
            status=str(data.get("status", EventStatus.CANDIDATE.value)),
            source_evidence=dict(data.get("source_evidence", {})),
            evidence_breakdown=ev_breakdown,
            metadata=dict(data.get("metadata", {})),
            explanation=str(data.get("explanation", "")),
        )
