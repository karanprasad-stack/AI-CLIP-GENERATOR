"""Competitive FPS Game Profile for fast-paced shooters without specialized per-game HUD parsers."""

from typing import List, Dict, Any, Tuple
from pydantic import Field
from .base import BaseGameProfile
from backend.app.config import COMPETITIVE_FPS_SCORING_WEIGHTS


class CompetitiveFPSProfile(BaseGameProfile):
    """Profile tuned for CS2, Apex Legends, Call of Duty / Warzone, Fortnite, Overwatch, PUBG, BGMI, etc."""
    name: str = "competitive_fps"
    display_name: str = "Competitive FPS"
    archetype: str = "competitive_fps"
    scoring_weights: Dict[str, float] = Field(default_factory=lambda: dict(COMPETITIVE_FPS_SCORING_WEIGHTS))
    preferred_duration_tiers: List[str] = Field(default_factory=lambda: ["quick", "standard"])
    effect_style: str = "fps_hype"
    max_effects_per_minute: int = 12
    default_hashtags: List[str] = Field(default_factory=lambda: ["#FPS", "#GamingShorts", "#Highlights"])

    aliases: List[str] = [
        "fps", "competitive_fps", "shooter", "tactical_fps",
        "cs2", "cs:go", "csgo", "counter-strike", "counter strike",
        "apex", "apex legends", "cod", "call of duty", "warzone", "modern warfare",
        "fortnite", "overwatch", "ow2", "rainbow six", "r6", "siege",
        "pubg", "bgmi", "battlegrounds", "battlefield"
    ]

    event_vocabulary: List[str] = [
        "kill", "headshot", "clutch", "ace", "multi kill", "multikill", "knocked", "knock",
        "downed", "wipe", "squad wipe", "team wipe", "sniper", "flick", "spray",
        "one shot", "one tap", "whiff", "defuse", "bomb", "round win", "victory"
    ]

    reaction_vocabulary: List[str] = [
        "nice", "let's go", "sheesh", "clutch", "no way", "holy", "insane", "beam",
        "beamed", "fried", "cracked", "bhai kya mara", "clean", "aimbot"
    ]

    detection_config: Dict[str, Any] = {
        "kill_feed_enabled": False,
        "round_state_enabled": False,
        "audio_weight": 0.45,
        "transcript_weight": 0.45,
        "min_kill_confidence": 0.65,
        "multi_kill_window_sec": 8.0,
    }

    candidate_duration_hints: Dict[str, Tuple[float, float]] = Field(
        default_factory=lambda: {
            "kill": (15.0, 25.0),
            "multi_kill": (18.0, 35.0),
            "clutch": (25.0, 50.0),
            "ace": (30.0, 60.0),
            "narrative": (40.0, 90.0),
        }
    )
