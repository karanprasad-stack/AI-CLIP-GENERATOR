"""Base game profile abstraction defining game-specific HUD coordinates, vocabulary, and rules."""

from typing import Dict, Any, List, Tuple
from pydantic import BaseModel, Field


class BaseGameProfile(BaseModel):
    """Abstract profile defining UI geometry, callout vocabulary, and detection rules for a competitive game."""
    name: str = "generic"
    display_name: str = "Generic Game"
    aliases: List[str] = Field(default_factory=list)
    event_vocabulary: List[str] = Field(default_factory=list)
    reaction_vocabulary: List[str] = Field(default_factory=list)

    # Relative normalized coordinates: (ymin, xmin, ymax, xmax) in [0.0, 1.0]
    hud_regions: Dict[str, Tuple[float, float, float, float]] = Field(default_factory=dict)
    kill_feed_region: Tuple[float, float, float, float] = (0.05, 0.70, 0.35, 0.98)
    round_state_region: Tuple[float, float, float, float] = (0.01, 0.40, 0.10, 0.60)
    health_region: Tuple[float, float, float, float] = (0.85, 0.15, 0.99, 0.35)
    center_banner_region: Tuple[float, float, float, float] = (0.20, 0.30, 0.45, 0.70)

    # UI patterns & color markers (HSV / BGR ranges)
    known_ui_patterns: Dict[str, Any] = Field(default_factory=dict)

    # Temporal limits and thresholds
    detection_config: Dict[str, Any] = Field(default_factory=dict)

    # Suggested candidate highlight duration windows: (min_sec, max_sec)
    candidate_duration_hints: Dict[str, Tuple[float, float]] = Field(
        default_factory=lambda: {
            "kill": (15.0, 25.0),
            "2k": (15.0, 30.0),
            "3k": (20.0, 35.0),
            "4k": (25.0, 45.0),
            "ace": (30.0, 60.0),
            "clutch": (35.0, 60.0),
            "narrative": (60.0, 180.0),
        }
    )
