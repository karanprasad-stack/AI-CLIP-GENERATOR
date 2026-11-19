"""Generic fallback game profile for games without specialized HUD parsers."""

from typing import List, Dict, Any, Tuple
from .base import BaseGameProfile


class GenericGameProfile(BaseGameProfile):
    """Fallback profile relying primarily on audio energy and generic gaming vocabulary."""
    name: str = "generic"
    display_name: str = "Generic Competitive Game"
    aliases: List[str] = ["generic", "fps", "battle_royale", "esports"]
    event_vocabulary: List[str] = [
        "kill", "headshot", "clutch", "ace", "knock", "elimination",
        "downed", "sniper", "win", "round", "game"
    ]
    reaction_vocabulary: List[str] = [
        "nice", "let's go", "omg", "no way", "holy", "insane", "what"
    ]
    detection_config: Dict[str, Any] = {
        "kill_feed_enabled": False,
        "round_state_enabled": False,
        "audio_weight": 0.50,
        "transcript_weight": 0.50,
        "min_kill_confidence": 0.65,
        "sequence_window_sec": 8.0,
    }
