"""Story / Open-World / RPG Game Profile for rich narrative, comedic fails, and open-world chaos."""

from typing import List, Dict, Any, Tuple
from pydantic import Field
from .base import BaseGameProfile
from backend.app.config import STORY_OPEN_WORLD_SCORING_WEIGHTS


class StoryOpenWorldProfile(BaseGameProfile):
    """Profile tuned for GTA VI, GTA V, RDR2, Cyberpunk 2077, Elden Ring, God of War, etc."""
    name: str = "story_open_world"
    display_name: str = "Story / Open-World"
    archetype: str = "story_open_world"
    scoring_weights: Dict[str, float] = Field(default_factory=lambda: dict(STORY_OPEN_WORLD_SCORING_WEIGHTS))
    preferred_duration_tiers: List[str] = Field(default_factory=lambda: ["standard", "extended"])
    effect_style: str = "cinematic_comedy"
    max_effects_per_minute: int = 6
    default_hashtags: List[str] = Field(default_factory=lambda: ["#StoryMode", "#OpenWorld", "#GamingShorts"])

    aliases: List[str] = [
        "story", "open world", "open_world", "rpg", "story_open_world",
        "gta", "gta vi", "gta 6", "gta v", "gta 5", "grand theft auto",
        "rdr2", "rdr", "red dead", "red dead redemption",
        "cyberpunk", "cyberpunk 2077", "elden ring", "god of war", "gow",
        "last of us", "the last of us", "tlou", "spider-man", "spiderman",
        "witcher", "witcher 3", "skyrim", "hogwarts legacy", "starfield",
        "fallout", "zelda", "ghost of tsushima", "horizon"
    ]

    event_vocabulary: List[str] = [
        # Narrative & Mission cues
        "mission", "cutscene", "ending", "reveal", "betrayal", "plot", "secret", "truth",
        "story", "quest", "heist", "dialogue", "choice",
        # Open World Chaos & Police/Fails
        "cops", "police", "wanted", "chase", "crash", "explosion", "physics", "glitch",
        "fail", "wasted", "busted", "flying", "car", "tank", "helicopter", "stunt",
        # Boss Fight & High Action
        "boss", "phase 2", "defeat", "victory", "you died", "slain", "fell", "dragon",
        "parry", "dodge", "combo"
    ]

    reaction_vocabulary: List[str] = [
        # Humor & Laughter (English & Hinglish)
        "haha", "hahaha", "lmao", "lol", "bruh", "bhai kya hua", "kya tha ye", "arre bhai",
        "ded", "dead", "no way", "what the hell", "are you serious", "bro what",
        # Story Emotion & Shock
        "oh my god", "holy", "wait what", "no no no", "unbelievable", "insane", "chills"
    ]

    detection_config: Dict[str, Any] = {
        "kill_feed_enabled": False,
        "round_state_enabled": False,
        "motion_analysis_enabled": True,
        "laughter_threshold": 0.70,
        "story_climax_threshold": 0.75,
    }

    candidate_duration_hints: Dict[str, Tuple[float, float]] = Field(
        default_factory=lambda: {
            "comedic_moment": (25.0, 60.0),
            "story_climax": (35.0, 120.0),
            "chaos_burst": (20.0, 50.0),
            "boss_fight_climax": (40.0, 150.0),
            "narrative": (60.0, 180.0),
        }
    )
