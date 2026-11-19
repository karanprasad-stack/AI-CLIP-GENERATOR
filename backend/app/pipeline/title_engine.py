"""Title Engine: multi-style candidate generation, deterministic scoring, deduplication, and optional local LLM enhancement."""

import json
import re
import urllib.request
from typing import Dict, Any, List, Optional, Tuple, Set

from backend.app.config import (
    TITLE_WEIGHT_RELEVANCE,
    TITLE_WEIGHT_SPECIFICITY,
    TITLE_WEIGHT_EMOTIONAL,
    TITLE_WEIGHT_BREVITY,
    TITLE_WEIGHT_KEYWORD,
    TITLE_WEIGHT_NATURALNESS,
    MAX_TITLE_LENGTH,
    OLLAMA_ENABLED,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SEC,
)
from backend.app.pipeline.clip_summary_engine import ClipSummary
from backend.app.pipeline.description_engine import compute_description_similarity

GENERIC_PHRASES = [
    "gameplay highlight",
    "gameplay moment",
    "epic gameplay",
    "insane gaming",
    "ends unexpectedly",
    "best gaming moment",
    "gaming highlight",
    "amazing gaming",
]

STOP_WORDS = {
    "the", "a", "an", "that", "this", "was", "is", "in", "of", "and",
    "to", "for", "he", "his", "it", "at", "with", "from", "on", "by", "or",
}


def compute_title_similarity(title1: str, title2: str) -> float:
    """Calculates normalized token Jaccard similarity excluding stop words and emojis."""
    t1_tokens = set(re.findall(r"\b[a-z0-9]+\b", title1.lower())) - STOP_WORDS
    t2_tokens = set(re.findall(r"\b[a-z0-9]+\b", title2.lower())) - STOP_WORDS

    if not t1_tokens or not t2_tokens:
        return 1.0 if t1_tokens == t2_tokens else 0.0

    intersection = t1_tokens.intersection(t2_tokens)
    union = t1_tokens.union(t2_tokens)
    return len(intersection) / len(union)


class TitleEngine:
    """Generates, scores, ranks, and validates YouTube Shorts titles."""

    def __init__(
        self,
        ollama_enabled: bool = OLLAMA_ENABLED,
        ollama_host: str = OLLAMA_HOST,
        ollama_model: str = OLLAMA_MODEL,
        max_length: int = MAX_TITLE_LENGTH,
    ):
        self.ollama_enabled = ollama_enabled
        self.ollama_host = ollama_host
        self.ollama_model = ollama_model
        self.max_length = max_length

    def validate_title(self, title: str, summary: ClipSummary) -> Tuple[bool, str]:
        """Validates that a title is within boundaries, non-empty, and avoids robotic grammar or clickbait hallucinations."""
        t = title.strip().strip('"\'')
        if not t:
            return False, "Title is empty"

        if len(t) > self.max_length:
            return False, f"Title length ({len(t)}) exceeds max {self.max_length}"

        # Reject excessive repeated punctuation (e.g. "????", "!!!!")
        if re.search(r"([!?]){3,}", t):
            return False, "Excessive repeated punctuation"

        # Reject titles with more than 2 hashtags embedded
        if len(re.findall(r"#\w+", t)) > 2:
            return False, "Too many hashtags in title"

        # Reject all-caps titles longer than 15 chars
        words = t.split()
        if len(t) > 15 and all(w.isupper() for w in words if len(w) > 1 and w.isalpha()):
            return False, "Title is entirely uppercase"

        # Reject robotic awkward grammar patterns (e.g., "...with Fail Ends Unexpectedly")
        t_low = t.lower()
        if "with fail" in t_low or "with timing" in t_low or "with flash ends" in t_low:
            return False, "Robotic grammar structure detected"

        # Reject claims unsupported by summary (e.g., claiming 1v5 clutch when clutch is not in signals)
        if "1v5" in t_low and "1v5" not in [s.lower() for s in summary.source_signals]:
            return False, "Unsupported 1v5 gameplay claim"

        return True, ""

    def score_title(
        self,
        title: str,
        summary: ClipSummary,
        existing_titles: Optional[List[str]] = None,
    ) -> Tuple[float, Dict[str, float]]:
        """Computes transparent, auditable quality score with candidate specificity and generic penalties."""
        t_clean = title.strip().strip('"\'')
        t_lower = t_clean.lower()
        length = len(t_clean)

        # 1. Relevance: Mentions game, primary event, or concrete secondary action
        game_kw = summary.game.lower().replace(":", "").replace("-", "")
        ev_kw = summary.primary_event.lower()
        rel_points = 0.0
        if game_kw in t_lower or "gaming" in t_lower or summary.game.lower() in t_lower:
            rel_points += 0.5
        if ev_kw in t_lower or any(sec in t_lower for sec in summary.secondary_events):
            rel_points += 0.5
        score_relevance = min(1.0, rel_points)

        # 2. Specificity: Has detailed action word rather than purely generic filler
        is_generic = any(g in t_lower for g in GENERIC_PHRASES)
        has_specific_signal = (
            ev_kw in t_lower
            or any(sec in t_lower for sec in summary.secondary_events)
            or (summary.strongest_reaction != "unknown" and summary.strongest_reaction.lower() in t_lower)
        )
        score_specificity = 0.1 if is_generic else (0.95 if has_specific_signal else 0.5)

        # 3. Emotional Impact: Contains reaction word or expressive emoji
        emojis = ["💀", "🔥", "😭", "😱", "😳", "👀", "🎯", "😂", "🥶"]
        has_emoji = any(e in t_clean for e in emojis)
        has_rx = (summary.strongest_reaction.lower() in t_lower) if summary.strongest_reaction != "unknown" else False
        score_emotional = 1.0 if (has_emoji and has_rx) else (0.85 if (has_emoji or has_rx) else 0.4)

        # 4. Brevity: Ideal YouTube Shorts title length is 28 to 62 characters
        if 28 <= length <= 62:
            score_brevity = 1.0
        elif 20 <= length < 28 or 62 < length <= 80:
            score_brevity = 0.8
        elif 15 <= length < 20:
            score_brevity = 0.4
        else:
            score_brevity = 0.2

        # 5. Keyword Coverage: Captures secondary events or tone
        coverage_hits = sum(1 for sec in summary.secondary_events if sec in t_lower)
        score_keyword = min(1.0, 0.5 + 0.25 * coverage_hits)

        # 6. Naturalness: Human phrasing, active verb, proper grammar
        score_natural = 1.0
        if is_generic:
            score_natural -= 0.35
        if t_clean.startswith('"') and t_clean.endswith('"'):
            score_natural -= 0.05
        if t_clean.count("?") > 2 or t_clean.count("!") > 2:
            score_natural -= 0.3
        score_natural = max(0.1, score_natural)

        base_score = (
            TITLE_WEIGHT_RELEVANCE * score_relevance
            + TITLE_WEIGHT_SPECIFICITY * score_specificity
            + TITLE_WEIGHT_EMOTIONAL * score_emotional
            + TITLE_WEIGHT_BREVITY * score_brevity
            + TITLE_WEIGHT_KEYWORD * score_keyword
            + TITLE_WEIGHT_NATURALNESS * score_natural
        )

        # Generic title penalty
        if is_generic:
            base_score = max(0.1, base_score - 0.35)

        # Cross-candidate similarity penalty
        sim_penalty = 0.0
        if existing_titles:
            max_sim = max([compute_title_similarity(title, prev) for prev in existing_titles], default=0.0)
            if max_sim >= 0.50:
                sim_penalty = round(max_sim * 0.40, 3)
                base_score = max(0.1, base_score - sim_penalty)

        total_score = round(base_score, 3)

        breakdown = {
            "relevance": round(score_relevance, 2),
            "specificity": round(score_specificity, 2),
            "emotional_impact": round(score_emotional, 2),
            "brevity": round(score_brevity, 2),
            "keyword_coverage": round(score_keyword, 2),
            "naturalness": round(score_natural, 2),
            "similarity_penalty": sim_penalty,
            "total_score": total_score,
        }

        return total_score, breakdown

    def generate_rule_based_titles(
        self,
        summary: ClipSummary,
        existing_titles: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Deterministically generates diverse, authentic title concepts tailored specifically
        to the candidate's verified narrative events and reaction signals.
        """
        game = summary.game
        ev = summary.primary_event.lower()
        secs = [s.lower() for s in summary.secondary_events]
        rx = summary.strongest_reaction.title() if summary.strongest_reaction != "unknown" else ""

        titles: List[str] = []

        # 1. Reaction Concepts (Anchor to genuine vocal reactions)
        if rx:
            clean_rx = rx.replace("Phrase:", "").replace("Word:", "").strip()
            if len(clean_rx.split()) <= 4:
                short_cand = f'"{clean_rx}" 💀'
                if len(short_cand) >= 20:
                    titles.append(short_cand)
                else:
                    titles.append(f'That "{clean_rx}" Says Everything 💀')
                    titles.append(f'Bro Really Said "{clean_rx}" 💀')
                    titles.append(f'The "{clean_rx}" Says Everything 😂')
                titles.append(f"He Said \"{clean_rx}\" For A Reason 😂")
            if any(w in clean_rx.lower() for w in ["whoa", "what", "wow", "holy", "insane"]):
                titles.append(f"Bro Was Completely Speechless 😳")
                titles.append(f"His Reaction Says Everything 😂")

        # 2. Timing Concepts
        if "timing" in ev or "timing" in secs or "timing" in rx.lower():
            titles.append(f"That Timing Was WAY Too Perfect 💀")
            titles.append(f"The Worst Possible Timing In {game} 😂")
            titles.append(f"When The Timing Hits At The Worst Second 😭")
            titles.append(f"The Craziest {game} Timing 🔥")

        # 3. Fail / Blunder Concepts
        if "fail" in ev or "fail" in secs or "funny" in summary.tone:
            titles.append(f"The Fail At The End Makes This 10x Better 😂")
            titles.append(f"Bro Really Thought He Had That 💀")
            titles.append(f"How Did This Go So Horribly Wrong? 😭")
            titles.append(f"The Most Painful {game} Fail Ever 💀")

        # 4. Flash / Utility Concepts
        if "flash" in ev or "flash" in secs:
            titles.append(f"He Did NOT See That Flash Coming 😭")
            titles.append(f"The Most Unlucky Flash In {game} History 💀")
            titles.append(f"Blinded At The WORST Possible Moment 😂")

        # 5. Shot / Gunplay Concepts
        if any(w in ev for w in ["shot", "headshot", "kill"]) or any(w in secs for w in ["shot", "headshot", "kill"]):
            titles.append(f"The Shot That Completely Changed The Round 🎯")
            titles.append(f"How Did That Shot Even Connect?! 😱")
            titles.append(f"That Shot Was Actually Disgusting 🔥")

        # 6. Clutch / High-Stakes Concepts
        if "clutch" in ev or "clutch" in secs or "clutch" in summary.tone:
            titles.append(f"The Clutch Nobody Saw Coming 🔥")
            titles.append(f"Ice In His Veins For This {game} Clutch 🥶")
            titles.append(f"The Most Intense Clutch Of The Day 🎯")

        # 7. Chaos / Disbelief Concepts
        if summary.tone == "shock/disbelief" or "shock" in ev or "chaos" in ev:
            titles.append(f"Bro Was Speechless After This Play 😳")
            titles.append(f"Nobody Saw That Coming 💀")
            titles.append(f"Pure {game} Chaos From Start To Finish 😂")
            titles.append(f"What Actually Just Happened Here?! 😱")

        # 8. High-Energy / Climax Fallback
        if not titles:
            titles.append(f"The Play That Left Everyone Speechless 💀")
            titles.append(f"Pure {game} Chaos From Start To Finish 😂")
            titles.append(f"How Did He Even Pull This Off?! 🔥")

        # Always ensure at least one title includes the specific game name
        if not any(game in t for t in titles):
            titles.append(f"The Craziest {game} Moment You'll See Today 🔥")

        # Deduplicate, score, and return top 5 diverse titles
        scored_unique: List[Tuple[str, float]] = []
        seen = set()
        for t in titles:
            clean = t.strip()
            if clean and clean not in seen:
                seen.add(clean)
                valid, _ = self.validate_title(clean, summary)
                if valid:
                    sc, _ = self.score_title(clean, summary, existing_titles=existing_titles)
                    scored_unique.append((clean, sc))

        scored_unique.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in scored_unique[:5]]

    def try_ollama_titles(self, summary: ClipSummary) -> Optional[List[str]]:
        """Attempts to query local Ollama model with strict guardrails."""
        if not self.ollama_enabled:
            return None

        prompt = (
            f"You are a top YouTube Shorts creator. Write 3 short, high-performing gaming titles (28-60 chars) "
            f"strictly grounded in this clip:\n"
            f"- Game: {summary.game}\n"
            f"- Event: {summary.primary_event}\n"
            f"- Secondary: {', '.join(summary.secondary_events)}\n"
            f"- Reaction: {summary.strongest_reaction}\n"
            f"- Tone: {summary.tone}\n\n"
            f"RULES:\n"
            f"1. Natural creator phrasing. No robotic 'CS:GO X with Y' templates.\n"
            f"2. Only describe events present in this summary. Do not invent players or fake actions.\n"
            f"3. Return ONLY a JSON list of 3 strings. Example: [\"Title 1 💀\", \"Title 2 🔥\", \"Title 3 😭\"]\n"
        )

        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            req = urllib.request.Request(
                f"{self.ollama_host}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_SEC) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                response_text = result.get("response", "")
                parsed = json.loads(response_text)
                if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                    return [p.strip().strip('"\'') for p in parsed]
        except Exception:
            return None

        return None

    def refine_short_title(self, title: str, summary: ClipSummary) -> str:
        """
        Expands an extremely short title (< 20 chars) into a natural, grounded
        YouTube Shorts title using candidate context (reaction, event, game).
        Returns title unchanged if >= 20 chars or if insufficient context exists.
        """
        clean_t = title.strip()
        if len(clean_t) >= 20:
            return title

        # Check if contextual information exists to justify expansion
        has_rx = bool(summary.strongest_reaction and summary.strongest_reaction != "unknown")
        has_ev = bool(summary.primary_event and summary.primary_event.lower() not in ["", "gameplay highlight", "reaction", "shock"])
        has_game = bool(summary.game and summary.game.lower() not in ["", "unknown"])

        if not has_rx and not has_ev and not has_game:
            # Insufficient context to expand without hallucinating
            return title

        # Extract reaction quote or clean reaction string
        clean_rx = ""
        if '"' in clean_t:
            parts = clean_t.split('"')
            if len(parts) >= 3 and parts[1].strip():
                clean_rx = parts[1].strip()
        if not clean_rx and has_rx:
            clean_rx = summary.strongest_reaction.replace("Phrase:", "").replace("Word:", "").strip()

        # Determine emoji
        emojis = ["💀", "😂", "😱", "😳", "🔥", "🎯"]
        emoji = "💀"
        for e in emojis:
            if e in clean_t:
                emoji = e
                break

        # Build grounded expansion
        if clean_rx:
            rx_cap = clean_rx.title()
            if "whoa" in clean_rx.lower() or "what" in clean_rx.lower() or "wow" in clean_rx.lower() or len(clean_rx.split()) <= 2:
                expanded = f'That "{rx_cap}" Says Everything {emoji}'
            else:
                expanded = f'He Said "{rx_cap}" For A Reason {emoji}'
        elif has_ev and has_game:
            expanded = f'The Craziest {summary.game} {summary.primary_event.title()} {emoji}'
        elif has_game:
            expanded = f'That {summary.game} Play Said It All {emoji}'
        else:
            expanded = f'That Reaction Says It All {emoji}'

        if len(expanded) >= 20:
            return expanded
        return title

    def generate_and_rank_titles(
        self,
        summary: ClipSummary,
        existing_titles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generates title candidates, ranks them deterministically, and selects the best candidate-unique title."""
        mode = "rule_based"
        candidates = self.generate_rule_based_titles(summary, existing_titles=existing_titles)

        # Attempt optional Ollama enhancement
        ollama_cands = self.try_ollama_titles(summary)
        if ollama_cands:
            mode = "ollama_enhanced"
            for oc in ollama_cands:
                valid, _ = self.validate_title(oc, summary)
                if valid and oc not in candidates:
                    candidates.append(oc)

        # Score and rank all candidate titles
        scored: List[Dict[str, Any]] = []
        for cand in candidates:
            score, bd = self.score_title(cand, summary, existing_titles=existing_titles)
            scored.append({
                "title": cand,
                "score": score,
                "breakdown": bd,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        # Pick top candidate that isn't a duplicate of existing titles
        selected_title = ""
        for item in scored:
            cand_t = item["title"]
            if existing_titles:
                max_sim = max([compute_title_similarity(cand_t, prev) for prev in existing_titles], default=0.0)
                if max_sim >= 0.70:
                    continue
            selected_title = cand_t
            break

        if not selected_title:
            selected_title = scored[0]["title"] if scored else f"The Craziest {summary.game} Moment 🔥"

        # Expand extremely short reaction titles (< 20 chars) if context exists
        if len(selected_title) < 20:
            selected_title = self.refine_short_title(selected_title, summary)

        alternatives = [s["title"] for s in scored if s["title"] != selected_title][:4]

        return {
            "selected_title": selected_title,
            "selected_score": scored[0]["score"] if scored else 0.5,
            "alternatives": alternatives,
            "ranked_candidates": scored,
            "generation_mode": mode,
            "model": self.ollama_model if mode == "ollama_enhanced" else "rule_engine_v1",
        }

    def compute_metadata_quality(
        self,
        title: str,
        summary: ClipSummary,
        description: str,
        hashtags: List[str],
        existing_titles: Optional[List[str]] = None,
        existing_descriptions: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """Computes a transparent, diagnostic quality breakdown for the generated metadata bundle."""
        # 1. Relevance
        t_low = title.lower()
        d_low = description.lower()
        game_kw = summary.game.lower().replace(":", "")
        has_game = (game_kw in t_low or game_kw in d_low)
        has_event = (summary.primary_event.lower() in t_low or summary.primary_event.lower() in d_low)
        relevance = 1.0 if (has_game and has_event) else (0.85 if (has_game or has_event) else 0.6)

        # 2. Specificity
        is_generic = any(g in t_low for g in GENERIC_PHRASES) or any(g in d_low for g in GENERIC_PHRASES)
        specificity = 0.4 if is_generic else (0.92 if (summary.primary_event != "gameplay highlight") else 0.75)

        # 3. Naturalness
        naturalness = 0.95
        if "with fail" in t_low or "ends unexpectedly" in t_low:
            naturalness -= 0.35
        if len(title) > 75:
            naturalness -= 0.15
        elif len(title) < 20:
            naturalness -= 0.20

        # 4. Uniqueness
        max_sims = []
        if existing_titles:
            max_sims.append(max([compute_title_similarity(title, prev) for prev in existing_titles], default=0.0))
        if existing_descriptions:
            max_sims.append(max([compute_description_similarity(description, prev) for prev in existing_descriptions], default=0.0))

        if max_sims:
            uniqueness = round(max(0.2, 1.0 - max(max_sims)), 2)
        else:
            uniqueness = 1.0

        # 5. Grounding (strictly supported events)
        grounding = 1.0
        if "1v5" in t_low and "1v5" not in [s.lower() for s in summary.source_signals]:
            grounding = 0.2

        overall = round(
            0.25 * relevance
            + 0.25 * specificity
            + 0.20 * naturalness
            + 0.15 * uniqueness
            + 0.15 * grounding,
            3,
        )

        return {
            "overall": overall,
            "relevance": round(relevance, 2),
            "specificity": round(specificity, 2),
            "naturalness": round(naturalness, 2),
            "uniqueness": round(uniqueness, 2),
            "grounding": round(grounding, 2),
        }
