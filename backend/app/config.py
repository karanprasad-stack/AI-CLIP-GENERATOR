"""Configuration for Phase 2.1.1 candidate detection, gaming signals, and scoring transparency."""

from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT_DIR: Path = PROJECT_ROOT / "output"
DEFAULT_TEMP_DIR: Path = PROJECT_ROOT / "temp"

# Primary Scoring Weights (Normalized dynamically across active components)
DEFAULT_SCORING_WEIGHTS: Dict[str, float] = {
    "audio": 0.25,
    "transcript": 0.20,
    "gameplay_event": 0.25,
    "context": 0.20,
    "boundary": 0.10,
    # Future extensibility hooks (disabled in Phase 2.1.1)
    "llm": 0.0,
    "visual": 0.0,
}

# Phase 12B Game-Aware Scoring Weights (When concrete gameplay events are present)
GAME_AWARE_SCORING_WEIGHTS: Dict[str, float] = {
    "audio": 0.18,
    "transcript": 0.12,
    "gameplay_event": 0.45,
    "context": 0.15,
    "boundary": 0.10,
}

# Concrete Gameplay Event Bonuses (Phase 12B)
CONCRETE_GAMEPLAY_EVENT_BONUSES: Dict[str, float] = {
    "ace": 45.0,
    "ace_candidate": 34.0,
    "4k": 28.0,
    "clutch_candidate": 25.0,
    "3k": 20.0,
    "rapid_kill_sequence": 18.0,
    "2k": 12.0,
    "round_win": 8.0,
    "round_ending_kill": 8.0,
    "spike_defused": 8.0,
    "spike_planted": 6.0,
    "spectated_kill": 6.0,
    "kill": 3.5,
    "headshot": 5.0,
}

# Sub-component weights for GameplayEventScore (Must sum to 1.0)
GAMEPLAY_INTERNAL_WEIGHTS: Dict[str, float] = {
    "gaming_lexical": 0.25,
    "reaction_lexical": 0.20,
    "audio_event_alignment": 0.20,
    "signal_diversity": 0.15,
    "causal_progression": 0.10,
    "density": 0.10,
}

# Duration Constraints (in seconds)
MIN_CANDIDATE_DURATION: float = 30.0
MAX_CANDIDATE_DURATION: float = 60.0
TARGET_CANDIDATE_DURATION: float = 45.0

# Deduplication Thresholds
IOU_DEDUPLICATION_THRESHOLD: float = 0.55
MAX_OVERLAP_SECONDS: float = 20.0

# Temporal Clustering Window (in seconds)
EVENT_CLUSTER_WINDOW: float = 8.0

# High-impact gaming terms that indicate intense gameplay climax
HIGH_IMPACT_GAMING_WORDS: List[str] = [
    "clutch",
    "headshot",
    "ace",
    "1v1",
    "1v2",
    "1v3",
    "1v4",
    "1v5",
    "wasted",
    "busted",
    "eliminated",
]

# Reaction Phrases (High viral signal)
REACTION_PHRASES: List[str] = [
    "oh my god",
    "no way",
    "what the hell",
    "what the heck",
    "are you serious",
    "are you kidding",
    "holy shit",
    "holy crap",
    "i can't believe",
    "what was that",
    "look at that",
    "let's go",
    "lets go",
    "get out of here",
    "did you see that",
    "what just happened",
    "check this out",
    "watch this",
    "unbelievable",
    "how did he",
    "how did that happen",
    "no freakin way",
    "you gotta be kidding me",
    "no shot",
    "talk about timing",
]

# Reaction & Surprise Words
REACTION_WORDS: List[str] = [
    "what",
    "wait",
    "look",
    "bro",
    "damn",
    "crazy",
    "insane",
    "holy",
    "dude",
    "omg",
    "yoo",
    "whoa",
    "wow",
    "bruh",
    "nah",
    "sheesh",
    "yo",
    "unreal",
    "clown",
]

# Comprehensive Gameplay Event Vocabulary
GAMEPLAY_WORDS: List[str] = [
    # Combat & Eliminations
    "clutch",
    "kill",
    "killed",
    "killing",
    "kills",
    "headshot",
    "eliminated",
    "knocked",
    "downed",
    "revive",
    "revived",
    "reviving",
    "ace",
    "frag",
    "snipe",
    "sniped",
    "shot",
    "shooting",
    "weapon",
    "gun",
    "fight",
    "fighting",
    "1v1",
    "1v2",
    "1v3",
    "1v4",
    "1v5",
    # Outcomes & Survival
    "win",
    "won",
    "winning",
    "lose",
    "lost",
    "losing",
    "victory",
    "defeat",
    "survive",
    "survived",
    "death",
    "died",
    "dead",
    "wasted",
    "busted",
    "spawn",
    "respawn",
    # Tactical, Squad & World Actions
    "squad",
    "team",
    "enemy",
    "opponent",
    "escape",
    "escaped",
    "chase",
    "chasing",
    "police",
    "cops",
    "explosion",
    "explode",
    "crash",
    "crashed",
    "steal",
    "stole",
    "drift",
    "stunt",
    "heist",
    "ambush",
    "glitch",
    "bug",
    "hack",
    "npc",
    "wanted",
    "mission",
    "flash",
    "timing",
    "fail",
]

# Laughter & Humor Signals
LAUGHTER_WORDS: List[str] = [
    "haha",
    "hahaha",
    "hahahaha",
    "lol",
    "lmao",
    "rofl",
    "lmfao",
]

# ==============================================================================
# Phase 3 Configuration — Video Acquisition, Extraction & 9:16 Rendering
# ==============================================================================

# Video Acquisition
MAX_SOURCE_HEIGHT: int = 1080

# Candidate Selection
TOP_N_CANDIDATES: int = 5

# Clip Extraction Padding (in seconds)
PRE_ROLL_SECONDS: float = 0.5
POST_ROLL_SECONDS: float = 0.5

# Selectable Aspect Ratios & Dimension Resolver
ASPECT_RATIO_9_16: str = "9:16"
ASPECT_RATIO_1_1: str = "1:1"
DEFAULT_ASPECT_RATIO: str = ASPECT_RATIO_9_16

SUPPORTED_ASPECT_RATIOS: Dict[str, Tuple[int, int]] = {
    ASPECT_RATIO_9_16: (1080, 1920),
    ASPECT_RATIO_1_1: (1080, 1080),
}


def get_output_dimensions(aspect_ratio: str = DEFAULT_ASPECT_RATIO) -> Tuple[int, int]:
    """Resolves (width, height) pixel dimensions for supported aspect ratios."""
    clean = str(aspect_ratio).strip()
    if clean in SUPPORTED_ASPECT_RATIOS:
        return SUPPORTED_ASPECT_RATIOS[clean]
    raise ValueError(
        f"Unsupported aspect ratio: '{aspect_ratio}'. "
        f"Supported ratios: {list(SUPPORTED_ASPECT_RATIOS.keys())}"
    )


# Rendering Output Dimensions & Target
OUTPUT_WIDTH: int = 1080
OUTPUT_HEIGHT: int = 1920
OUTPUT_FPS_FALLBACK: int = 30

# Video Encoder Settings
VIDEO_CODEC_HARDWARE: str = "h264_nvenc"
VIDEO_CODEC_CPU: str = "libx264"
VIDEO_BITRATE: str = "6M"
NVENC_PRESET: str = "p5"
NVENC_BITRATE: str = "6M"
CPU_PRESET: str = "medium"
CPU_CRF: int = 19
CPU_THREADS: int = 4

# Audio Settings
AUDIO_CODEC: str = "aac"
AUDIO_BITRATE: str = "192k"

# Layout Modes
LAYOUT_AUTO: str = "auto"
LAYOUT_SMART_CROP: str = "smart_crop"
LAYOUT_BLURRED_BG: str = "blurred_background"
LAYOUT_FACECAM: str = "facecam_gameplay"

# Smart Crop Focal Position (0.0 to 1.0)
VERTICAL_FOCAL_X: float = 0.50
VERTICAL_FOCAL_Y: float = 0.50

# Facecam Detection Parameters
FACECAM_SAMPLE_INTERVAL_SEC: float = 2.0
FACECAM_MIN_SAMPLES: int = 6
FACECAM_MAX_SAMPLES: int = 40
FACECAM_PERSISTENCE_THRESHOLD: float = 0.25
FACECAM_REGION_TOLERANCE: float = 0.15
FACECAM_TOP_HEIGHT_RATIO: float = 0.35

# ==============================================================================
# Phase 4 Configuration — Subtitles, Karaoke Captions & Contextual Emojis
# ==============================================================================

# Variable Duration Support (15s to 180s)
MIN_CLIP_DURATION: float = 15.0
MAX_CLIP_DURATION: float = 180.0
MIN_CLIP_DURATION_V2: float = 15.0
MAX_CLIP_DURATION_V2: float = 180.0

DURATION_TIERS: Dict[str, Tuple[float, float]] = {
    "quick": (15.0, 30.0),      # Hook -> Action -> Payoff
    "standard": (30.0, 90.0),   # Setup -> Escalation -> Major Event -> Reaction / Payoff
    "extended": (90.0, 180.0),  # Context -> Situation -> Pressure -> First Engagement -> Escalation -> Major Event -> Resolution -> Reaction
}

DURATION_TIER_NARRATIVE_STAGES: Dict[str, List[str]] = {
    "quick": ["Hook", "Action", "Payoff"],
    "standard": ["Setup", "Escalation", "Major Event", "Reaction / Payoff"],
    "extended": ["Context", "Situation", "Pressure", "First Engagement", "Escalation", "Major Event", "Resolution", "Reaction"],
}


def get_duration_tier(duration: float) -> str:
    """Classifies duration into quick (15-30s), standard (30-90s), or extended (90-180s)."""
    if duration <= 30.0:
        return "quick"
    elif duration <= 90.0:
        return "standard"
    return "extended"


def get_narrative_structure(tier_or_duration: Any) -> List[str]:
    """Returns narrative stage list corresponding to a tier name or numeric duration."""
    if isinstance(tier_or_duration, (int, float)):
        tier = get_duration_tier(float(tier_or_duration))
    else:
        tier = str(tier_or_duration).lower().strip()
    return DURATION_TIER_NARRATIVE_STAGES.get(tier, DURATION_TIER_NARRATIVE_STAGES["standard"])

# Caption Word Grouping Constraints
MIN_WORDS_PER_GROUP: int = 1
MAX_WORDS_PER_GROUP: int = 4
MIN_GROUP_DURATION: float = 0.35
MAX_GROUP_DURATION: float = 2.2
MAX_GROUP_CHARS: int = 24
PAUSE_THRESHOLD_SEC: float = 0.40

# Caption Timing Safety Adjustments (seconds)
CAPTION_LEAD_IN: float = 0.0        # Subtitles appear at exact word start (0ms lead-in)
CAPTION_TAIL_OUT: float = 0.05

# Visual Typography & Safe-Zone Positioning (for 1080x1920)
CAPTION_FONT_NAME: str = "Segoe UI Black"
CAPTION_FONT_SIZE: int = 68
CAPTION_BASE_COLOR: str = "&H00FFFFFF&"        # Pure white
CAPTION_ACTIVE_COLOR: str = "&H00D7FF&"      # Vibrant gold/yellow for karaoke focus
CAPTION_OUTLINE_COLOR: str = "&H00000000&"     # Deep black outline
CAPTION_SHADOW_COLOR: str = "&H80000000&"      # Soft black drop shadow
CAPTION_OUTLINE_WIDTH: int = 5
CAPTION_SHADOW_DEPTH: int = 3
CAPTION_ALIGNMENT: int = 2                     # Centered
CAPTION_MARGIN_V: int = 320                    # Safe lower-middle region (~83% height)

# Contextual Emoji Engine Configuration
EMOJI_FONT_NAME: str = "Segoe UI Emoji"
EMOJI_FONT_SIZE: int = 80
EMOJI_MARGIN_V: int = 440                      # Positioned directly above active captions
EMOJI_MIN_CONFIDENCE: float = 0.65             # Threshold to prevent spam
EMOJI_MIN_INTERVAL: float = 2.0                # Minimum seconds between emoji appearances
EMOJI_DEFAULT_DURATION: float = 1.0            # Display duration in seconds

# ==============================================================================
# Phase 5 Configuration — Context-Aware Visual Effects Engine
# ==============================================================================

# Effect Type Names
EFFECT_SUBTLE_ZOOM: str = "subtle_zoom"
EFFECT_PUNCH_ZOOM: str = "punch_zoom"
EFFECT_IMPACT_ZOOM: str = "impact_zoom"
EFFECT_MICRO_SHAKE: str = "micro_shake"
EFFECT_IMPACT_SHAKE: str = "impact_shake"
EFFECT_EMPHASIS_FLASH: str = "emphasis_flash"

ALL_EFFECT_TYPES: List[str] = [
    EFFECT_SUBTLE_ZOOM,
    EFFECT_PUNCH_ZOOM,
    EFFECT_IMPACT_ZOOM,
    EFFECT_MICRO_SHAKE,
    EFFECT_IMPACT_SHAKE,
    EFFECT_EMPHASIS_FLASH,
]

# Zoom Effect Scales & Durations
SUBTLE_ZOOM_SCALE: float = 1.06
SUBTLE_ZOOM_DURATION: float = 0.90
PUNCH_ZOOM_SCALE: float = 1.12
PUNCH_ZOOM_DURATION: float = 0.55
IMPACT_ZOOM_SCALE: float = 1.15
IMPACT_ZOOM_DURATION: float = 0.35

# Shake Effect Parameters
MICRO_SHAKE_AMPLITUDE: int = 3                 # pixels (+-3px)
MICRO_SHAKE_DURATION: float = 0.45             # seconds
MICRO_SHAKE_FREQ: float = 14.0                 # Hz
IMPACT_SHAKE_AMPLITUDE: int = 7                # pixels (+-7px)
IMPACT_SHAKE_DURATION: float = 0.35            # seconds
IMPACT_SHAKE_FREQ: float = 18.0                # Hz

# Flash Accent Parameters
FLASH_BRIGHTNESS: float = 0.12                 # Brightness increment (0.0 to 1.0)
FLASH_DURATION: float = 0.12                   # seconds (short editor accent)

# Cooldown / Anti-Spam Intervals (seconds)
MIN_ZOOM_GAP: float = 1.2
MIN_SHAKE_GAP: float = 0.8
MIN_FLASH_GAP: float = 1.0

# Effect Decision Thresholds
IMPACT_ZOOM_CONFIDENCE_THRESHOLD: float = 0.85
IMPACT_ZOOM_SCORE_THRESHOLD: float = 0.82
PUNCH_ZOOM_CONFIDENCE_THRESHOLD: float = 0.72
PUNCH_ZOOM_SCORE_THRESHOLD: float = 0.68
SUBTLE_ZOOM_CONFIDENCE_THRESHOLD: float = 0.55
SUBTLE_ZOOM_SCORE_THRESHOLD: float = 0.45

IMPACT_SHAKE_SCORE_THRESHOLD: float = 0.80
MICRO_SHAKE_SCORE_THRESHOLD: float = 0.62
FLASH_SCORE_THRESHOLD: float = 0.85

# ==============================================================================
# Phase 6A Configuration — Audio Polish & SFX Engine
# ==============================================================================

# Master Feature Flags
AUDIO_ENABLED: bool = True
SFX_ENABLED: bool = True
DUCKING_ENABLED: bool = True

# Loudness & True Peak Targets (EBU R128 / YouTube Shorts standards)
TARGET_LUFS: float = -14.0
TRUE_PEAK_LIMIT: float = -1.0
LOUDNESS_LRA: float = 11.0

# SFX Event Type Names
SFX_WHOOSH: str = "whoosh"
SFX_MAJOR_IMPACT: str = "major_impact"
SFX_MINOR_IMPACT: str = "minor_impact"
SFX_REACTION_ACCENT: str = "reaction_accent"
SFX_TRANSITION: str = "transition"

ALL_SFX_TYPES: List[str] = [
    SFX_WHOOSH,
    SFX_MAJOR_IMPACT,
    SFX_MINOR_IMPACT,
    SFX_REACTION_ACCENT,
    SFX_TRANSITION,
]

# SFX Relative Mixing Levels (in dB relative to full-scale / main audio)
WHOOSH_GAIN_DB: float = -16.0               # -18 to -14 dB
WHOOSH_STRONG_GAIN_DB: float = -14.0
IMPACT_MAJOR_GAIN_DB: float = -13.0         # -16 to -11 dB
IMPACT_MINOR_GAIN_DB: float = -18.0         # -20 to -16 dB
REACTION_GAIN_DB: float = -20.0             # -22 to -18 dB
TRANSITION_GAIN_DB: float = -18.0

# Speech-Aware Ducking Parameters
DUCKING_DB: float = -3.5                    # Standard speech ducking: -2.5 to -4.0 dB
STRONG_SPEECH_DUCKING_DB: float = -5.0      # When speech is loud/dense
DUCK_ATTACK_MS: int = 100                   # 80 to 150 ms
DUCK_RELEASE_MS: int = 350                  # 250 to 500 ms

# SFX Cooldown / Anti-Spam Intervals (seconds)
MIN_SFX_GAP: float = 0.7
MIN_IMPACT_GAP: float = 0.8
MIN_WHOOSH_GAP: float = 0.6
MIN_REACTION_GAP: float = 1.0
MAX_SFX_PER_30_SECONDS: int = 6

# ==============================================================================
# Phase 6B Configuration — Metadata, Thumbnail & Publishing Package Engine
# ==============================================================================

# Master Flags
PUBLISHING_ENABLED: bool = True
THUMBNAIL_ENABLED: bool = True
METADATA_ENABLED: bool = True
OLLAMA_ENABLED: bool = False
OLLAMA_HOST: str = "http://localhost:11434"
OLLAMA_MODEL: str = "qwen2.5:3b"
OLLAMA_TIMEOUT_SEC: float = 2.0

# Thumbnail Frame Scoring & Composition
THUMBNAIL_WIDTH: int = 1280
THUMBNAIL_HEIGHT: int = 720
THUMBNAIL_WEIGHT_GAMEPLAY: float = 0.30
THUMBNAIL_WEIGHT_CLIMAX: float = 0.25
THUMBNAIL_WEIGHT_AUDIO_PEAK: float = 0.15
THUMBNAIL_WEIGHT_VISUAL: float = 0.15
THUMBNAIL_WEIGHT_FACECAM: float = 0.10
THUMBNAIL_WEIGHT_SHARPNESS: float = 0.05
THUMBNAIL_TEXT_ENABLED: bool = True
MIN_FRAME_BRIGHTNESS: float = 18.0
MIN_FRAME_SHARPNESS: float = 25.0

# Title Ranking Weights
TITLE_WEIGHT_RELEVANCE: float = 0.30
TITLE_WEIGHT_SPECIFICITY: float = 0.20
TITLE_WEIGHT_EMOTIONAL: float = 0.15
TITLE_WEIGHT_BREVITY: float = 0.15
TITLE_WEIGHT_KEYWORD: float = 0.10
TITLE_WEIGHT_NATURALNESS: float = 0.10
MAX_TITLE_LENGTH: int = 90

# Description & Hashtags
MIN_DESCRIPTION_LENGTH: int = 40
MAX_DESCRIPTION_LENGTH: int = 500
MIN_HASHTAGS: int = 4
MAX_HASHTAGS: int = 8

# Rights & Attribution
DEFAULT_RIGHTS_NOTE: str = "Source rights not automatically verified. Packaging for creator review."

# ==============================================================================
# Phase 7C Configuration — Long-Stream Intelligence Engine
# ==============================================================================

# Long-Stream Classification Threshold (in seconds)
# Videos >= this threshold are processed in intelligent chunks (default 1800s / 30 mins)
LONG_STREAM_THRESHOLD_SEC: float = 1800.0

# Chunking Parameters (in seconds)
CHUNK_DURATION_SEC: float = 600.0            # 10 minutes per chunk
CHUNK_OVERLAP_SEC: float = 45.0              # 45 seconds overlap to preserve boundary climaxes
MIN_CHUNK_DURATION_SEC: float = 60.0         # Minimum chunk duration

# Temporal & Narrative Diversity Parameters
TEMPORAL_DIVERSITY_MIN_GAP_SEC: float = 90.0 # Preferred temporal separation between clips
MAX_CLUSTERING_PER_10_MINUTES: int = 2       # Max clips within any 10-minute window
DIVERSITY_BONUS: float = 2.0                 # Score bonus for unrepresented event categories
DIVERSITY_PENALTY: float = 3.0               # Soft penalty for over-represented categories

# Quality Gating Parameters
QUALITY_GATE_MIN_SCORE: float = 55.0         # Absolute minimum acceptable quality floor
QUALITY_GATE_STRONG_SCORE: float = 70.0      # Threshold for strong climax moments
SCORE_GAP_THRESHOLD: float = 8.0             # Significant score drop indicating natural quality cutoff
MAX_AUTO_SHORTS_RECOMMENDED: int = 12        # Maximum recommended Shorts in auto mode
MIN_AUTO_SHORTS_RECOMMENDED: int = 3         # Minimum recommended Shorts in auto mode

# Hardware & Storage Protection
MAX_DISK_USAGE_PCT: float = 90.0             # Abort processing if disk usage exceeds 90%
MIN_FREE_DISK_GB: float = 5.0                # Minimum free storage required (GB)
CLEANUP_CHUNK_AUDIO_IMMEDIATELY: bool = True # Delete chunk WAV files immediately after analysis

# ==============================================================================
# Phase 7E Configuration — Creator Quality & Final Output Intelligence
# ==============================================================================

# Publishability Quality Level Thresholds
PUBLISHABILITY_THRESHOLDS: Dict[str, float] = {
    "excellent": 90.0,
    "strong": 80.0,
    "review": 65.0,
    "weak": 50.0,
}

# Dimension Weights (Must sum to 1.0)
PUBLISHABILITY_DIMENSION_WEIGHTS: Dict[str, float] = {
    "moment": 0.25,
    "narrative": 0.20,
    "presentation": 0.20,
    "publishing": 0.15,
    "technical": 0.10,
    "diversity": 0.10,
}

# Quality Gate Thresholds
CREATOR_GATE_PASS_SCORE: float = 75.0
CREATOR_GATE_REVIEW_SCORE: float = 60.0

# Narrative Constraints (in seconds)
MAX_HOOK_SILENCE_SEC: float = 3.0            # More than 3s dead air at start triggers warning/penalty
MIN_PAYOFF_DURATION_SEC: float = 2.5         # Climax must not cut off within 2.5s of ending
MAX_WORDS_PER_SECOND_CAPTION: float = 4.5     # Subtitle density ceiling for readability

# ==============================================================================
# Phase 9 Configuration — Dual Source + Live Stream Clipping
# ==============================================================================
SOURCE_TYPE_NORMAL: str = "normal_video"
SOURCE_TYPE_LIVE: str = "live_stream"
DEFAULT_SOURCE_TYPE: str = SOURCE_TYPE_NORMAL

# Rolling Capture & Segmentation (in seconds)
LIVE_SEGMENT_DURATION_SEC: float = 90.0      # Default duration of each rolling live capture segment
LIVE_SEGMENT_OVERLAP_SEC: float = 30.0       # Boundary overlap between adjacent segments
LIVE_MIN_SEGMENT_DURATION_SEC: float = 15.0  # Minimum duration to consider a partial final segment

# Storage & Bounded Disk Management
LIVE_MAX_STORAGE_MB: float = 10240.0         # 10 GB storage budget for live segments
LIVE_STORAGE_WARNING_PCT: float = 85.0       # Warning threshold percentage
LIVE_MAX_RETAINED_SAFE_SEGMENTS: int = 4     # Number of non-candidate segments to retain before expiring

# Reconnection & Resilience
LIVE_RECONNECT_MAX_ATTEMPTS: int = 5
LIVE_RECONNECT_INITIAL_DELAY_SEC: float = 2.0
LIVE_RECONNECT_BACKOFF_FACTOR: float = 2.0
LIVE_RECONNECT_MAX_DELAY_SEC: float = 30.0

