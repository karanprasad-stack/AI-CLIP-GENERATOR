"""Horror / Survival Game Profile tuned for jumpscares, panic escapes, and atmospheric tension."""

from typing import List, Dict, Any, Tuple
from pydantic import Field
from .base import BaseGameProfile
from backend.app.config import HORROR_SURVIVAL_SCORING_WEIGHTS


class HorrorSurvivalProfile(BaseGameProfile):
    """Profile tuned for Resident Evil, Phasmophobia, Outlast, Lethal Company, Silent Hill, etc."""
    name: str = "horror_survival"
    display_name: str = "Horror / Survival"
    archetype: str = "horror_survival"
    scoring_weights: Dict[str, float] = Field(default_factory=lambda: dict(HORROR_SURVIVAL_SCORING_WEIGHTS))
    preferred_duration_tiers: List[str] = Field(default_factory=lambda: ["quick", "standard"])
    effect_style: str = "horror_tension"
    max_effects_per_minute: int = 8
    default_hashtags: List[str] = Field(default_factory=lambda: ["#HorrorGaming", "#Jumpscare", "#GamingShorts"])

    aliases: List[str] = [
        "horror", "horror_survival", "survival_horror", "scary",
        "resident evil", "re4", "re2", "re7", "re8", "resident evil 4",
        "phasmophobia", "phasmo", "outlast", "outlast 2", "trials",
        "lethal company", "silent hill", "dead by daylight", "dbd",
        "fnaf", "five nights at freddys", "amnesia", "alien isolation",
        "sons of the forest", "the forest", "slender", "poppy playtime"
    ]

    event_vocabulary: List[str] = [
        # Horror Mechanics & Entities
        "monster", "ghost", "creature", "entity", "demon", "zombie", "chased",
        "door", "locked", "light", "flashlight", "generator", "hiding", "closet",
        # Action & Panic
        "run", "hide", "it's here", "behind you", "hurry", "get out", "help",
        "died", "grabbed", "got me", "dead", "screamer", "jumpscare"
    ]

    reaction_vocabulary: List[str] = [
        # Screams, Shocks & Panics
        "holy shit", "oh my god", "what was that", "screaming", "no no no",
        "get away", "bhai bhabhi", "darr lag gaya", "meri phat gayi", "heart attack",
        "jesus", "whoa", "jumped", "i jumped", "scared me"
    ]

    detection_config: Dict[str, Any] = {
        "kill_feed_enabled": False,
        "round_state_enabled": False,
        "silence_contrast_window_sec": 5.0,
        "scream_z_threshold": 2.4,
        "pre_scream_silence_threshold": 0.12,
    }

    candidate_duration_hints: Dict[str, Tuple[float, float]] = Field(
        default_factory=lambda: {
            "jumpscare": (15.0, 35.0),
            "panic_escape": (20.0, 50.0),
            "narrative": (30.0, 80.0),
        }
    )
