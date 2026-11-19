"""Automatic game profile detection from video metadata, settings, and transcript vocabulary."""

import re
from typing import Dict, Any, Optional
from .profiles import BaseGameProfile, ValorantGameProfile, GenericGameProfile, get_game_profile


class GameDetector:
    """Infers the appropriate game profile from explicit settings, title/description, or speech lexicon."""

    def __init__(self):
        self.valorant_profile = ValorantGameProfile()
        self.generic_profile = GenericGameProfile()

    def detect_game(
        self,
        metadata: Optional[Dict[str, Any]] = None,
        transcript_data: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> BaseGameProfile:
        """
        Determines the GameProfile using:
        1. Explicit user setting ('game': 'valorant' | 'generic')
        2. Video title, uploader, tags, or description
        3. Spoken transcript game-specific terminology
        """
        # 1. User setting override
        if settings and settings.get("game"):
            explicit_game = str(settings["game"]).strip().lower()
            if explicit_game in ["val", "valorant"]:
                return ValorantGameProfile()
            return get_game_profile(explicit_game)

        # 2. Metadata textual matching
        if metadata:
            text_corpus = " ".join([
                str(metadata.get("title", "")),
                str(metadata.get("description", "")),
                str(metadata.get("uploader", "")),
                " ".join(str(t) for t in metadata.get("tags", [])),
            ]).lower()

            for alias in self.valorant_profile.aliases:
                if re.search(r'\b' + re.escape(alias) + r'\b', text_corpus):
                    return ValorantGameProfile()

        # 3. Transcript vocabulary density
        if transcript_data:
            words = transcript_data.get("words", [])
            if not words and "segments" in transcript_data:
                words = [w for s in transcript_data["segments"] for w in s.get("words", [])]

            transcript_tokens = set(str(w.get("word", "")).lower().strip(".,!?:;\"'()") for w in words)
            high_signal_val_terms = {"spike", "vandal", "phantom", "valorant", "defuse", "retake"}
            matching_terms = transcript_tokens.intersection(high_signal_val_terms)

            if len(matching_terms) >= 2 or "spike" in transcript_tokens:
                return ValorantGameProfile()

        # Fallback to Generic
        return GenericGameProfile()
