"""Automatic game profile detection from video metadata, settings, and transcript vocabulary."""

import re
from typing import Dict, Any, Optional
from .profiles import (
    BaseGameProfile,
    ValorantGameProfile,
    GenericGameProfile,
    StoryOpenWorldProfile,
    HorrorSurvivalProfile,
    CompetitiveFPSProfile,
    get_game_profile,
)


class GameDetector:
    """Infers the appropriate game profile and archetype from explicit settings, metadata, or speech lexicon."""

    def __init__(self):
        self.valorant_profile = ValorantGameProfile()
        self.story_profile = StoryOpenWorldProfile()
        self.horror_profile = HorrorSurvivalProfile()
        self.fps_profile = CompetitiveFPSProfile()
        self.generic_profile = GenericGameProfile()

    def detect_game(
        self,
        metadata: Optional[Dict[str, Any]] = None,
        transcript_data: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> BaseGameProfile:
        """
        Determines the GameProfile using:
        1. Explicit user setting ('game_mode' / 'game_profile' / 'game')
        2. Video title, uploader, tags, or description
        3. Spoken transcript game-specific terminology
        """
        # 1. User setting override
        if settings:
            explicit = settings.get("game_mode") or settings.get("game_profile") or settings.get("game")
            if explicit and str(explicit).lower().strip() not in ["auto", ""]:
                key = str(explicit).lower().strip()
                if key in ["valorant", "val"]:
                    return ValorantGameProfile()
                elif key in ["story_open_world", "story", "open_world", "rpg"]:
                    return StoryOpenWorldProfile()
                elif key in ["horror_survival", "horror", "survival_horror"]:
                    return HorrorSurvivalProfile()
                elif key in ["competitive_fps", "fps", "shooter"]:
                    return CompetitiveFPSProfile()
                elif key in ["generic", "variety"]:
                    return GenericGameProfile()
                return get_game_profile(key)

        # 2. Metadata textual matching
        if metadata:
            text_corpus = " ".join([
                str(metadata.get("title", "")),
                str(metadata.get("description", "")),
                str(metadata.get("uploader", "")),
                " ".join(str(t) for t in metadata.get("tags", [])),
            ]).lower()

            # 2a. Valorant (highest priority for competitive FPS deep HUD)
            for alias in self.valorant_profile.aliases:
                if re.search(r'\b' + re.escape(alias) + r'\b', text_corpus):
                    return ValorantGameProfile()

            # 2b. Story / Open-World titles
            story_title_map = [
                (r"\b(gta\s*vi|gta\s*6)\b", "GTA VI"),
                (r"\b(gta\s*v|gta\s*5|grand\s+theft\s+auto)\b", "GTA V"),
                (r"\b(rdr2|rdr\s*2|red\s+dead(\s+redemption)?(\s*2)?)\b", "Red Dead Redemption 2"),
                (r"\b(cyberpunk(\s*2077)?)\b", "Cyberpunk 2077"),
                (r"\b(elden\s+ring)\b", "Elden Ring"),
                (r"\b(god\s+of\s+war|gow\s+ragnarok)\b", "God of War"),
                (r"\b(the\s+last\s+of\s+us|last\s+of\s+us|tlou)\b", "The Last of Us"),
                (r"\b(spider-?man(\s*2)?)\b", "Spider-Man"),
                (r"\b(witcher\s*3|the\s+witcher)\b", "The Witcher 3"),
                (r"\b(skyrim|elder\s+scrolls)\b", "Skyrim"),
                (r"\b(hogwarts\s+legacy)\b", "Hogwarts Legacy"),
                (r"\b(starfield)\b", "Starfield"),
                (r"\b(fallout(\s*[4v])?)\b", "Fallout"),
                (r"\b(ghost\s+of\s+tsushima)\b", "Ghost of Tsushima"),
            ]
            for pat, title in story_title_map:
                if re.search(pat, text_corpus):
                    p = StoryOpenWorldProfile()
                    p.detected_title = title
                    return p

            # Generic story/open-world aliases
            for alias in self.story_profile.aliases:
                if re.search(r'\b' + re.escape(alias) + r'\b', text_corpus):
                    return StoryOpenWorldProfile()

            # 2c. Horror / Survival titles
            horror_title_map = [
                (r"\b(resident\s+evil(\s*[0-9]|re[0-9]|village)?|re4|re2|re7|re8)\b", "Resident Evil"),
                (r"\b(phasmophobia|phasmo)\b", "Phasmophobia"),
                (r"\b(outlast(\s*[12]|trials)?)\b", "Outlast"),
                (r"\b(lethal\s+company)\b", "Lethal Company"),
                (r"\b(silent\s+hill(\s*[0-9])?)\b", "Silent Hill"),
                (r"\b(dead\s+by\s+daylight|dbd)\b", "Dead by Daylight"),
                (r"\b(fnaf|five\s+nights(\s+at\s+freddy'?s)?)\b", "Five Nights at Freddy's"),
                (r"\b(amnesia|alien\s+isolation|sons\s+of\s+the\s+forest)\b", "Horror Game"),
            ]
            for pat, title in horror_title_map:
                if re.search(pat, text_corpus):
                    p = HorrorSurvivalProfile()
                    p.detected_title = title
                    return p

            for alias in self.horror_profile.aliases:
                if re.search(r'\b' + re.escape(alias) + r'\b', text_corpus):
                    return HorrorSurvivalProfile()

            # 2d. Competitive FPS titles (CS2, Apex, COD, BGMI, Fortnite)
            fps_title_map = [
                (r"\b(cs:?go|cs2|counter-?strike(\s*2)?)\b", "Counter-Strike 2"),
                (r"\b(apex(\s+legends)?)\b", "Apex Legends"),
                (r"\b(warzone|call\s+of\s+duty|cod|modern\s+warfare)\b", "Call of Duty"),
                (r"\b(fortnite)\b", "Fortnite"),
                (r"\b(overwatch(\s*2)?|ow2?)\b", "Overwatch 2"),
                (r"\b(rainbow\s+six|r6(\s+siege)?)\b", "Rainbow Six Siege"),
                (r"\b(pubg|bgmi|battlegrounds)\b", "PUBG"),
            ]
            for pat, title in fps_title_map:
                if re.search(pat, text_corpus):
                    p = CompetitiveFPSProfile()
                    p.detected_title = title
                    return p

            for alias in self.fps_profile.aliases:
                if re.search(r'\b' + re.escape(alias) + r'\b', text_corpus):
                    return CompetitiveFPSProfile()

        # 3. Transcript vocabulary density
        if transcript_data:
            words = transcript_data.get("words", [])
            if not words and "segments" in transcript_data:
                words = [w for s in transcript_data["segments"] for w in s.get("words", [])]

            transcript_tokens = set(str(w.get("word", "")).lower().strip(".,!?:;\"'()") for w in words)

            # Valorant
            val_terms = {"spike", "vandal", "phantom", "valorant", "defuse", "retake"}
            if len(transcript_tokens.intersection(val_terms)) >= 2 or "spike" in transcript_tokens:
                return ValorantGameProfile()

            # Horror
            horror_terms = {"phasmophobia", "spirit box", "emf", "crucifix", "jumpscare", "monster", "ghost"}
            if len(transcript_tokens.intersection(horror_terms)) >= 2:
                return HorrorSurvivalProfile()

            # Story / Open-World
            story_terms = {"cutscene", "mission passed", "quest", "heist", "dialogue", "cops", "police"}
            if len(transcript_tokens.intersection(story_terms)) >= 2:
                return StoryOpenWorldProfile()

            # General FPS
            fps_terms = {"squad wipe", "knocked", "downed", "clutch", "headshot"}
            if len(transcript_tokens.intersection(fps_terms)) >= 2:
                return CompetitiveFPSProfile()

        # Fallback to Generic
        return GenericGameProfile()
