"""Pydantic models for Phase 8 Multi-Track Timeline & Edit Decision List (EDL)."""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class TimelineBoundaries(BaseModel):
    """Source video extraction boundaries (in seconds)."""
    source_in: float = Field(..., description="Start timestamp in source video (seconds)")
    source_out: float = Field(..., description="End timestamp in source video (seconds)")
    duration: float = Field(..., description="Duration of the candidate clip (seconds)")
    min_allowed: float = Field(default=15.0, description="Minimum allowed duration (seconds)")
    max_allowed: float = Field(default=180.0, description="Maximum allowed duration (seconds)")


class TimelineVideoTrack(BaseModel):
    """Configuration for video layout and dimensions."""
    source_file: str = "source.mp4"
    layout: str = "smart_crop"  # smart_crop, blurred_background, facecam_gameplay
    resolution: str = "1080x1920"
    aspect_ratio: str = "9:16"
    fps: int = 60
    enabled: bool = True
    kill_feed_overlay: bool = False
    kill_feed_roi: Optional[List[float]] = None


class SubtitleWordItem(BaseModel):
    """A single word timestamped relative to the clip start (seconds)."""
    word: str
    start: float
    end: float


class SubtitleItem(BaseModel):
    """A subtitle phrase or line displayed on the video."""
    id: str
    start: float
    end: float
    text: str
    words: List[SubtitleWordItem] = Field(default_factory=list)
    language: str = "en"
    confidence: float = 1.0
    enabled: bool = True
    source: str = "ai"  # "ai" or "user"
    edited: bool = False
    original_text: Optional[str] = None


class EmojiItem(BaseModel):
    """A contextual emoji displayed at an emotional or gameplay peak."""
    id: str
    timestamp: float
    duration: float = 1.2
    emoji: str
    animation: str = "pop"  # pop, bounce, fade
    position: str = "top"   # top, center, bottom
    enabled: bool = True
    source: str = "ai"
    edited: bool = False


class EffectItem(BaseModel):
    """A context-aware visual effect (zoom, shake, flash)."""
    id: str
    type: str  # subtle_zoom, punch_zoom, impact_zoom, micro_shake, impact_shake, emphasis_flash
    start: float
    end: float
    intensity: float = 0.5
    focal_point: Optional[List[float]] = Field(default_factory=lambda: [0.5, 0.65])
    reason: Optional[str] = None
    enabled: bool = True
    source: str = "ai"
    edited: bool = False


class SfxItem(BaseModel):
    """A synchronized sound effect placed on the audio timeline."""
    id: str
    timestamp: float
    event_type: str  # whoosh, major_impact, minor_impact, reaction_accent, transition
    asset_name: str  # e.g. whoosh_strong.wav, impact_medium.wav, pop.wav
    gain_db: float = -14.0
    reason: Optional[str] = None
    enabled: bool = True
    source: str = "ai"
    edited: bool = False


class DuckingItem(BaseModel):
    """A speech-aware audio ducking region attenuating background audio."""
    id: str
    start: float
    end: float
    attenuation_db: float = -3.5
    attack_ms: int = 150
    release_ms: int = 300
    enabled: bool = True
    source: str = "ai"
    edited: bool = False


class TimelineMetadata(BaseModel):
    """Metadata regarding timeline creation, updates, and dirty tracks."""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "ai_generated"  # "ai_generated" or "user_edited"
    edit_summary: Optional[str] = None
    dirty_tracks: List[str] = Field(default_factory=list)


class TimelineEDL(BaseModel):
    """The authoritative Multi-Track Edit Decision List (EDL) for a candidate Short."""
    project_id: str
    candidate_id: int
    version: int = 1
    duration: float
    boundaries: TimelineBoundaries
    video_track: TimelineVideoTrack
    subtitles_track: List[SubtitleItem] = Field(default_factory=list)
    emoji_track: List[EmojiItem] = Field(default_factory=list)
    effects_track: List[EffectItem] = Field(default_factory=list)
    sfx_track: List[SfxItem] = Field(default_factory=list)
    ducking_track: List[DuckingItem] = Field(default_factory=list)
    metadata: TimelineMetadata = Field(default_factory=TimelineMetadata)
