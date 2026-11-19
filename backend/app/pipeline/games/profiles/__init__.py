"""Game profile registry and factory."""

from typing import Dict, Type
from .base import BaseGameProfile
from .generic import GenericGameProfile
from .valorant import ValorantGameProfile
from .story_open_world import StoryOpenWorldProfile
from .horror_survival import HorrorSurvivalProfile
from .competitive_fps import CompetitiveFPSProfile

REGISTERED_PROFILES: Dict[str, Type[BaseGameProfile]] = {
    "generic": GenericGameProfile,
    "valorant": ValorantGameProfile,
    "story_open_world": StoryOpenWorldProfile,
    "story": StoryOpenWorldProfile,
    "open_world": StoryOpenWorldProfile,
    "horror_survival": HorrorSurvivalProfile,
    "horror": HorrorSurvivalProfile,
    "competitive_fps": CompetitiveFPSProfile,
    "fps": CompetitiveFPSProfile,
}


def get_game_profile(game_name: str) -> BaseGameProfile:
    """Retrieve profile instance by game name (defaults to GenericGameProfile)."""
    norm = (game_name or "generic").strip().lower()
    profile_cls = REGISTERED_PROFILES.get(norm, GenericGameProfile)
    return profile_cls()
