"""Pydantic models and data contracts for Phase 9 Live Stream Session & Candidate Ingestion."""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class LiveSessionStatus:
    STARTING = "starting"
    CONNECTING = "connecting"
    LIVE = "live"
    RECONNECTING = "reconnecting"
    PROCESSING = "processing"
    STOPPING = "stopping"
    ENDED = "ended"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LiveCandidateStatus:
    DETECTED = "detected"
    EVALUATING = "evaluating"
    REVIEW = "review"
    PUBLISH_READY = "publish_ready"
    REJECTED = "rejected"
    RENDERING = "rendering"
    COMPLETED = "completed"


class LiveSegment(BaseModel):
    """Represents a discrete rolling captured media segment from a live stream."""
    segment_id: int
    local_start: float = 0.0
    local_end: float
    global_start: float
    global_end: float
    duration: float
    video_file: str
    audio_file: Optional[str] = None
    transcript_file: Optional[str] = None
    status: str = "captured"  # captured, analyzing, analyzed, cleanup_safe, expired, deleted
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    file_size_bytes: int = 0
    required_by_candidates: List[int] = Field(default_factory=list)


class LiveCandidate(BaseModel):
    """Represents a gaming moment detected in the live candidate pool with global timeline references."""
    candidate_id: int
    global_start: float
    global_end: float
    duration: float
    score: float
    publishability: Optional[Dict[str, Any]] = None
    status: str = LiveCandidateStatus.DETECTED
    source_segments: List[int] = Field(default_factory=list)
    event: Optional[str] = None
    secondary_events: List[str] = Field(default_factory=list)
    reaction: Optional[str] = None
    tone: Optional[str] = None
    signals: Any = Field(default_factory=list)
    detected_signals: List[str] = Field(default_factory=list)
    score_breakdown: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_candidate_dict(self) -> Dict[str, Any]:
        """Converts to standard candidate dictionary compatible with Phases 2-8."""
        return {
            "candidate_id": self.candidate_id,
            "rank": self.candidate_id,
            "start": round(self.global_start, 2),
            "end": round(self.global_end, 2),
            "duration": round(self.duration, 2),
            "final_score": round(self.score, 1),
            "score_breakdown": self.score_breakdown,
            "gameplay_event": self.event or "gameplay_moment",
            "secondary_events": self.secondary_events,
            "strongest_reaction": self.reaction,
            "tone": self.tone or "neutral",
            "signals": self.signals,
            "detected_signals": self.detected_signals,
            "selected": self.status in (LiveCandidateStatus.PUBLISH_READY, LiveCandidateStatus.REVIEW),
            "status": self.status,
            "source_position_str": f"{int(self.global_start // 60):02d}:{int(self.global_start % 60):02d} → {int(self.global_end // 60):02d}:{int(self.global_end % 60):02d}",
            "publishability": self.publishability,
            "source_segments": self.source_segments,
        }


class LiveActivityEvent(BaseModel):
    """Timeline event in the live session activity log."""
    id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    time_str: str = Field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    event_type: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class LiveSession(BaseModel):
    """Durable state model for an active or completed live streaming session."""
    session_id: str
    project_id: str
    source_url: str
    source_video_id: str
    source_type: str = "live_stream"
    status: str = LiveSessionStatus.STARTING
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: Optional[str] = None
    last_heartbeat: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_segment_id: int = 0
    total_segments: int = 0
    segments_processed: int = 0
    candidates_detected: int = 0
    candidates_ready: int = 0
    reconnect_count: int = 0
    storage_used: int = 0  # bytes
    error: Optional[Dict[str, Any]] = None
    active_manifest: Dict[str, Any] = Field(default_factory=dict)
