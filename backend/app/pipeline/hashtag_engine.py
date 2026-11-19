"""Hashtag & Keyword Engine: generates relevant hashtags and SEO tags for YouTube Shorts."""

import re
from typing import Dict, Any, List, Set, Tuple
from backend.app.config import MIN_HASHTAGS, MAX_HASHTAGS
from backend.app.pipeline.clip_summary_engine import ClipSummary


class HashtagEngine:
    """Generates 4-8 targeted hashtags and SEO keywords without spam or unrelated trends."""

    def __init__(
        self,
        min_tags: int = MIN_HASHTAGS,
        max_tags: int = MAX_HASHTAGS,
    ):
        self.min_tags = min_tags
        self.max_tags = max_tags

    def generate_hashtags(self, summary: ClipSummary) -> List[str]:
        """Generates 4-8 deduplicated, high-relevance hashtags."""
        raw_tags: List[str] = []

        # 1. Essential Platform Tag
        raw_tags.append("#Shorts")

        # 2. Game-Specific Tag
        clean_game = re.sub(r"[^a-zA-Z0-9]", "", summary.game)
        if clean_game:
            raw_tags.append(f"#{clean_game}")
            if clean_game.lower() == "csgo":
                raw_tags.append("#CounterStrike")

        # 2b. Verified Gameplay Event Tags (Phase 12C + Multi-Genre)
        ev = summary.primary_event.strip().lower()
        gp_stats = getattr(summary, "gameplay_stats", {}) or {}
        if gp_stats.get("aces", 0) > 0:
            raw_tags.extend([f"#{clean_game}Ace", "#AceClip", "#Ace"])
        if gp_stats.get("clutches", 0) > 0:
            raw_tags.extend([f"#{clean_game}Clutch", "#ClutchClip", "#Clutch"])
        if gp_stats.get("multi_kills", 0) > 0 or gp_stats.get("kills", 0) >= 3:
            raw_tags.extend(["#MultiKill", "#CleanKills"])
        if gp_stats.get("headshots", 0) > 0:
            raw_tags.extend(["#Headshot", "#OneTap"])
        if gp_stats.get("jumpscares", 0) > 0 or "jumpscare" in ev:
            raw_tags.extend(["#HorrorGaming", "#Jumpscare", "#ScaryMoments"])
        if gp_stats.get("panic_escapes", 0) > 0 or "panic escape" in ev:
            raw_tags.extend(["#CloseCall", "#EscapeMoment"])
        if gp_stats.get("story_climaxes", 0) > 0 or "story" in ev:
            raw_tags.extend(["#StoryMode", "#GamingStory", "#Cinematic"])
        if gp_stats.get("comedic_moments", 0) > 0 or "comedy" in ev:
            raw_tags.extend(["#FunnyGaming", "#GamingComedy", "#GamingFails"])
        if gp_stats.get("chaos_bursts", 0) > 0:
            raw_tags.extend(["#OpenWorld", "#GamingChaos", "#OnlyInGaming"])
        if gp_stats.get("boss_fights", 0) > 0:
            raw_tags.extend(["#BossFight", "#EpicGaming"])

        # 3. Candidate-Specific Event Tag
        ev = summary.primary_event.strip().lower()
        if ev and ev not in ["gameplay highlight", "reaction", "shock"]:
            if ev == "fail":
                raw_tags.append("#GamingFails")
            elif ev == "timing":
                raw_tags.append("#PerfectTiming")
            else:
                clean_ev = re.sub(r"[^a-zA-Z0-9]", "", ev).capitalize()
                if clean_ev:
                    raw_tags.append(f"#{clean_ev}")

        for sec in summary.secondary_events:
            clean_sec = re.sub(r"[^a-zA-Z0-9]", "", sec).capitalize()
            if clean_sec and len(clean_sec) > 2 and clean_sec.lower() not in ["gameplay", "audio", "reaction"]:
                raw_tags.append(f"#{clean_sec}")

        # 4. Tone & Genre Tags
        if "funny" in summary.tone or "chaotic" in summary.tone:
            raw_tags.append("#FunnyMoments")
        elif "clutch" in summary.tone or "clutch" in ev:
            raw_tags.append("#ClutchMoments")

        # 5. Core Discovery Tags
        raw_tags.extend(["#Gaming", "#GamingShorts"])
        if any(w in summary.game.lower() for w in ["valorant", "cs", "cod", "apex", "overwatch", "fortnite", "bgmi", "shooter", "fps"]):
            raw_tags.append("#FPS")
        elif "horror" in summary.tone or gp_stats.get("jumpscares", 0) > 0:
            raw_tags.append("#Horror")
        elif gp_stats.get("story_climaxes", 0) > 0 or gp_stats.get("chaos_bursts", 0) > 0:
            raw_tags.append("#OpenWorld")

        # Deduplicate case-insensitively
        seen_lower: Set[str] = set()
        final_tags: List[str] = []
        for tag in raw_tags:
            tag_clean = tag.strip()
            if not tag_clean.startswith("#"):
                tag_clean = f"#{tag_clean}"
            low = tag_clean.lower()
            if low not in seen_lower:
                seen_lower.add(low)
                final_tags.append(tag_clean)
            if len(final_tags) >= self.max_tags:
                break

        return final_tags

    def generate_keywords(self, summary: ClipSummary) -> List[str]:
        """Generates SEO keywords/tags for YouTube upload metadata."""
        keywords: List[str] = []
        game = summary.game
        ev = summary.primary_event.lower()

        keywords.append(game)
        if game.lower() == "cs:go":
            keywords.extend(["Counter Strike", "CSGO", "CS2", "Counter Strike Global Offensive"])

        if ev and ev not in ["gameplay highlight"]:
            keywords.append(f"{game} {ev}")
            keywords.append(f"{ev}")

        for sec in summary.secondary_events:
            if sec and sec not in ["audio surge"]:
                keywords.append(f"{game} {sec}")

        if "funny" in summary.tone or "chaotic" in summary.tone:
            keywords.append(f"{game} funny moments")
            keywords.append("gaming funny moments")
        elif "clutch" in summary.tone or "clutch" in ev:
            keywords.append(f"{game} clutch")
            keywords.append("gaming clutches")
        else:
            keywords.append(f"{game} highlights")

        gp_stats = getattr(summary, "gameplay_stats", {}) or {}
        if gp_stats.get("aces", 0) > 0:
            keywords.extend([f"{game} ace", f"{game} 5k", "ace highlight"])
        if gp_stats.get("clutches", 0) > 0:
            keywords.extend([f"{game} 1vX clutch", "insane clutch"])
        if gp_stats.get("headshots", 0) > 0:
            keywords.extend([f"{game} headshots", "one tap"])

        keywords.extend(["gaming", "gaming shorts", "youtube shorts", "FPS highlights"])

        # Deduplicate
        seen: Set[str] = set()
        final_kw: List[str] = []
        for kw in keywords:
            low = kw.lower().strip()
            if low and low not in seen:
                seen.add(low)
                final_kw.append(kw.strip())

        return final_kw
