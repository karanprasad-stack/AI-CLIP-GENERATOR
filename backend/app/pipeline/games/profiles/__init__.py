"""Game profile registry and factory."""

from typing import Dict, Type
from .base import BaseGameProfile
from .generic import GenericGameProfile
from .valorant import ValorantGameProfile

REGISTERED_PROFILES: Dict[str, Type[BaseGameProfile]] = {
    "generic": GenericGameProfile,
    "valorant": ValorantGameProfile,
}


def get_game_profile(game_name: str) -> BaseGameProfile:
    """Retrieve profile instance by game name (defaults to GenericGameProfile)."""
    norm = (game_name or "generic").strip().lower()
    profile_cls = REGISTERED_PROFILES.get(norm, GenericGameProfile)
    return profile_cls()
