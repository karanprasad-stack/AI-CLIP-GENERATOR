"""Valorant game profile with calibrated HUD regions, agent/weapon lexicons, and detection rules."""

from typing import List, Dict, Any, Tuple
from pydantic import Field
from .base import BaseGameProfile
from backend.app.config import GAME_AWARE_SCORING_WEIGHTS


class ValorantGameProfile(BaseGameProfile):
    """Calibrated profile for Riot Games' Valorant (16:9 standard layout)."""
    name: str = "valorant"
    display_name: str = "Valorant"
    archetype: str = "competitive_fps"
    scoring_weights: Dict[str, float] = Field(default_factory=lambda: dict(GAME_AWARE_SCORING_WEIGHTS))
    preferred_duration_tiers: List[str] = Field(default_factory=lambda: ["quick", "standard"])
    effect_style: str = "fps_hype"
    max_effects_per_minute: int = 12
    default_hashtags: List[str] = Field(default_factory=lambda: ["#Valorant", "#ValorantClips", "#Shorts"])
    aliases: List[str] = [
        "valorant", "val", "vct", "radiant", "immortal",
        "riot valorant", "val clips", "valorant highlights"
    ]

    event_vocabulary: List[str] = [
        # Objective & Tactics
        "spike", "spike planted", "spike down", "spike defused", "defuse", "plant", "retake",
        # Weapons & Abilities
        "vandal", "phantom", "operator", "op", "sheriff", "ghost", "spectre", "marshal",
        "ares", "odin", "judge", "bucky", "classic", "frenzy",
        # Mechanics & Combat
        "one tap", "headshot", "clutch", "ace", "thrifty", "flawless", "dink", "dinked",
        "whiff", "lineup", "eco", "force buy", "retaking", "diff", "wallbang",
        # Agents
        "jett", "reyna", "sova", "omen", "cypher", "killjoy", "viper", "phoenix",
        "brimstone", "sage", "raze", "breach", "skye", "yoru", "astra", "kayo",
        "chamber", "neon", "fade", "harbor", "gekko", "deadlock", "iso", "clove", "vyse",
    ]

    reaction_vocabulary: List[str] = [
        "nice", "nice shot", "let's go", "clutch god", "ace ace", "no way", "holy",
        "insane", "bhai", "sheesh", "what a shot", "last one", "one enemy", "he's low"
    ]

    # Normalized bounding boxes (ymin, xmin, ymax, xmax) for 16:9 gameplay:
    kill_feed_region: Tuple[float, float, float, float] = (0.04, 0.74, 0.32, 0.985)
    round_state_region: Tuple[float, float, float, float] = (0.01, 0.44, 0.08, 0.56)
    health_region: Tuple[float, float, float, float] = (0.90, 0.16, 0.99, 0.28)
    center_banner_region: Tuple[float, float, float, float] = (0.20, 0.28, 0.45, 0.72)
    bottom_center_skull_region: Tuple[float, float, float, float] = (0.76, 0.44, 0.88, 0.56)

    known_ui_patterns: Dict[str, Any] = {
        # Valorant Enemy Red: RGB around [255, 70, 85] (#FF4655)
        "enemy_red_hsv_lower": (170, 120, 140),
        "enemy_red_hsv_upper": (180, 255, 255),
        "enemy_red_hsv_lower2": (0, 120, 140),
        "enemy_red_hsv_upper2": (10, 255, 255),

        # Ally Cyan/Teal: RGB around [0, 229, 180] (#00E5B4)
        "ally_teal_hsv_lower": (75, 120, 140),
        "ally_teal_hsv_upper": (95, 255, 255),

        # Victory Banner Cyan: RGB around [0, 220, 230]
        "victory_cyan_hsv_lower": (80, 100, 150),
        "victory_cyan_hsv_upper": (100, 255, 255),

        # Defeat Banner Red
        "defeat_red_hsv_lower": (170, 100, 140),
        "defeat_red_hsv_upper": (180, 255, 255),

        # Spike Red Flashing Marker
        "spike_red_hsv_lower": (170, 150, 160),
        "spike_red_hsv_upper": (180, 255, 255),
    }

    detection_config: Dict[str, Any] = {
        "kill_feed_enabled": True,
        "round_state_enabled": True,
        "sample_fps": 2.0,                  # Sample every 0.5s for lightweight, fast frame diffing
        "kill_banner_cooldown_sec": 0.80,    # Debounce successive visual changes in same row
        "kill_persistence_sec": 3.80,        # Valorant kill banners persist ~4 seconds
        "multi_kill_window_sec": 9.0,        # Max duration between kills to continue a sequence
        "clutch_window_sec": 30.0,           # Max duration preceding round win for clutch evaluation
        "min_kill_confidence": 0.70,
        "audio_peak_proximity_sec": 1.20,
        "transcript_proximity_sec": 3.0,
    }
