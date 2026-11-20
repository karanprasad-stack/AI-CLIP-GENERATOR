"""Pydantic schemas and data contracts for Dashboard REST & SSE APIs."""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class ProcessingSettingsSchema(BaseModel):
    duration_mode: str = Field(default="auto", description="auto, 15_30, 30_60, 60_180, custom")
    min_duration: int = Field(default=15, ge=15, le=180)
    max_duration: int = Field(default=180, ge=15, le=180)
    num_shorts_mode: str = Field(default="auto", description="auto or custom")
    num_shorts: int = Field(default=5, ge=1, le=50)
    layout: str = Field(default="auto", description="auto, smart_crop, blurred_background, facecam_gameplay")
    captions: bool = Field(default=True)
    subtitle_language: str = Field(default="auto", description="auto, original, english, hindi, hinglish")
    word_highlighting: bool = Field(default=True)
    emoji: bool = Field(default=True)
    effects: bool = Field(default=True)
    effects_mode: str = Field(default="smart", description="smart, custom")
    audio: bool = Field(default=True)
    sfx: bool = Field(default=True)
    ducking: bool = Field(default=True)
    thumbnail: bool = Field(default=True)
    metadata_enabled: bool = Field(default=True)
    llm: bool = Field(default=False)
    semantic_reranker: bool = Field(default=True, description="Enable local LLM semantic reranking if Ollama is running")
    quality_preset: str = Field(default="High", description="Standard, High, Very High, Custom")
    aspect_ratio: str = Field(default="9:16", description="9:16 or 1:1")
    kill_feed_overlay: str = Field(default="auto", description="auto, on, off")
    game_mode: str = Field(default="auto", description="auto, valorant, competitive_fps, story_open_world, horror_survival, generic")
    resolution: str = Field(default="1080x1920")
    fps: int = Field(default=60)
    target_lufs: float = Field(default=-14.0)
    true_peak: float = Field(default=-1.0)


class ProjectCreateRequest(BaseModel):
    url: str
    title: Optional[str] = Field(default=None, description="Optional custom project name")
    source_type: Optional[str] = Field(default="normal_video", description="normal_video or live_stream")
    settings: Optional[ProcessingSettingsSchema] = None


class CandidateSelectionRequest(BaseModel):
    candidate_ids: List[int]


class MetadataUpdateRequest(BaseModel):
    candidate_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    hashtags: Optional[List[str]] = None
    keywords: Optional[List[str]] = None


class LongStreamInfoSchema(BaseModel):
    source_duration: float = 0.0
    chunks_processed: int = 1
    total_chunks: int = 1
    candidates_detected: int = 0
    strong_moments: int = 0
    recommended_shorts: int = 0
    chunks_failed: int = 0
    chunks_reused: int = 0
    deduplicated_candidates: int = 0
    selected_candidates: int = 0
    quality_gate_reason: Optional[str] = None


class ProgressStateSchema(BaseModel):
    step: int = 0
    total_steps: int = 23
    percent: int = 0
    stage: str = "Queued"
    message: str = ""
    current_candidate: int = 0
    logs: List[str] = []


class PublishabilityDimensionsSchema(BaseModel):
    moment: float = 0.0
    narrative: float = 0.0
    presentation: float = 0.0
    publishing: float = 0.0
    technical: float = 0.0
    diversity: float = 0.0


class PublishabilitySchema(BaseModel):
    score: float
    level: str = "strong"  # excellent, strong, review, weak, reject
    recommendation: str = "publish"  # publish, review, reject
    dimensions: Dict[str, float] = Field(default_factory=dict)
    reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    blocking_issues: List[str] = Field(default_factory=list)


class CandidateOutputSchema(BaseModel):
    video_url: str
    filename: str
    size_bytes: int = 0
    thumbnail_url: Optional[str] = None
    duration: Optional[float] = None


class CandidateSchema(BaseModel):
    candidate_id: int
    rank: int
    start: float
    end: float
    duration: float
    final_score: float
    score_breakdown: Optional[Dict[str, Any]] = None
    gameplay_event: Optional[str] = None
    secondary_events: Optional[List[str]] = None
    strongest_reaction: Optional[str] = None
    tone: Optional[str] = None
    signals: Optional[List[str]] = None
    selected: bool = False
    status: str = "detected"
    global_rank: Optional[int] = None
    chunk_id: Optional[str] = None
    quality_gate_status: Optional[str] = None
    duplicate_group: Optional[str] = None
    diversity_group: Optional[str] = None
    selection_reason: Optional[str] = None
    source_position_str: Optional[str] = None
    publishability: Optional[PublishabilitySchema] = None
    rendered: bool = False
    output: Optional[CandidateOutputSchema] = None


class OutputPackageSchema(BaseModel):
    candidate_id: int
    package_dir: str
    title: str
    description: Optional[str] = None
    thumbnail: str
    thumbnail_score: float
    thumbnail_timestamp: float
    quality_score: float
    status: str
    publishability: Optional[PublishabilitySchema] = None



class LiveSessionInfoSchema(BaseModel):
    session_id: Optional[str] = None
    status: str = "idle"
    total_segments: int = 0
    segments_processed: int = 0
    candidates_detected: int = 0
    candidates_ready: int = 0
    storage_used: int = 0


class ProjectDetailResponse(BaseModel):
    id: str
    video_id: str
    url: str
    title: str
    uploader: str
    duration: float
    language: str
    created_at: str
    updated_at: str
    status: str
    source_type: str = "normal_video"
    live_session_info: Optional[LiveSessionInfoSchema] = None
    settings: Dict[str, Any]
    long_stream_info: LongStreamInfoSchema
    candidates: List[Dict[str, Any]] = []
    selected_candidate_ids: List[int] = []
    published_packages: List[Dict[str, Any]] = []
    progress: ProgressStateSchema
    error: Optional[Dict[str, Any]] = None
    has_source_video: bool = False
    source_video_url: Optional[str] = None
    youtube_video_id: Optional[str] = None
    has_audio: bool = False
    audio_url: Optional[str] = None
    source_url: Optional[str] = None


class ProjectSummaryResponse(BaseModel):
    id: str
    video_id: str
    url: str
    title: str
    uploader: str
    duration: float
    status: str
    source_type: str = "normal_video"
    created_at: str
    updated_at: str
    candidates_count: int = 0
    shorts_count: int = 0
    percent: int = 0
