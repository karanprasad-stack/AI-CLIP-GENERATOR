"""Description Engine: generates natural, candidate-specific YouTube Shorts descriptions."""

import re
from typing import Dict, Any, List, Optional
from backend.app.config import MIN_DESCRIPTION_LENGTH, MAX_DESCRIPTION_LENGTH
from backend.app.pipeline.clip_summary_engine import ClipSummary


def compute_description_similarity(d1: str, d2: str) -> float:
    """
    Computes token-level Jaccard similarity between narrative portions of two descriptions,
    excluding common boilerplate lines like attribution and hashtags.
    """
    def extract_narrative(text: str) -> str:
        paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
        narrative_parts = []
        for p in paragraphs:
            low = p.lower()
            if low.startswith("original footage:") or p.startswith("#"):
                continue
            narrative_parts.append(p)
        return " ".join(narrative_parts) if narrative_parts else text

    n1 = extract_narrative(d1)
    n2 = extract_narrative(d2)
    tokens1 = set(re.findall(r"\b[a-zA-Z0-9]+\b", n1.lower()))
    tokens2 = set(re.findall(r"\b[a-zA-Z0-9]+\b", n2.lower()))
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return round(len(intersection) / len(union), 3)


class DescriptionEngine:
    """Creates truthful, engaging 1-3 sentence descriptions with attribution and tags."""

    def __init__(
        self,
        min_length: int = MIN_DESCRIPTION_LENGTH,
        max_length: int = MAX_DESCRIPTION_LENGTH,
        similarity_threshold: float = 0.50,
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.similarity_threshold = similarity_threshold

    def generate_candidate_hooks(self, summary: ClipSummary) -> List[str]:
        """
        Derives diverse, grounded narrative hooks from the candidate summary signals:
        - Timing angle
        - Fail angle
        - Flash / Utility angle
        - Shot / Gunplay angle
        - Reaction / Vocal angle
        - Shock / Disbelief angle
        - Chaos angle
        - Clutch angle
        - High-energy / Payoff angle
        """
        game = summary.game
        ev = summary.primary_event.lower()
        secs = [s.lower() for s in summary.secondary_events]
        rx = summary.strongest_reaction
        clean_rx = rx.replace("Phrase:", "").replace("Word:", "").strip() if rx and rx != "unknown" else ""

        hooks: List[str] = []

        # 0. High-Priority Verified Gameplay Hooks (Phase 12C)
        gp_stats = getattr(summary, "gameplay_stats", {}) or {}
        aces = gp_stats.get("aces", 0)
        clutches = gp_stats.get("clutches", 0)
        multi_kills = gp_stats.get("multi_kills", 0)
        kills = gp_stats.get("kills", 0)
        headshots = gp_stats.get("headshots", 0)
        round_wins = gp_stats.get("round_wins", 0)

        if aces > 0:
            hooks.append(f"An unbelievable ACE in {game}—taking down all 5 enemies to secure the round.")
            hooks.append(f"Absolute dominance in {game}! Watch this full 5K Ace round from start to finish.")
        if clutches > 0:
            hooks.append(f"Ice in the veins under maximum pressure: an insane {game} clutch when everything was on the line.")
            hooks.append(f"Impossible 1vX situation in {game} turned into a masterclass clutch play.")
        if multi_kills > 0 or kills >= 3:
            k_num = max(kills, 3)
            hooks.append(f"Rapid {k_num}K sequence in {game} with crisp gunplay and clinical positioning.")
            hooks.append(f"Clean multikill round in {game} wiping out the enemy push.")
        if headshots > 0:
            hooks.append(f"Pure precision: lethal headshots in {game} shutting down the site push instantly.")
        if round_wins > 0:
            hooks.append(f"A high-stakes round win in {game} decided in the final split second.")

        # 1. Event-specific hooks
        if "timing" in ev or "timing" in secs or (clean_rx and "timing" in clean_rx.lower()):
            hooks.append(f"When the timing lines up like this in {game}, you just have to laugh. The entire round fell apart in seconds.")
            hooks.append(f"The timing on this {game} play could not have been worse. One split-second decision spiraled out of control.")
            hooks.append(f"Unlucky timing in {game} strikes at the exact moment you least expect it.")

        if "fail" in ev or "fail" in secs or "funny" in summary.tone:
            hooks.append(f"The confidence was there, but everything went sideways immediately in {game}. One of the most painful fails you will see.")
            hooks.append(f"A simple {game} play quickly turned into complete disaster when everything that could go wrong did.")
            hooks.append(f"You could not script a worse blunder in {game}—from complete control to total collapse.")

        if "flash" in ev or "flash" in secs:
            hooks.append(f"An unexpected flash grenade in {game} completely altered the outcome of the round.")
            hooks.append(f"Blinded at the worst possible second, this {game} play turned into pure survival mode.")
            hooks.append(f"That flash grenade turned this {game} round into absolute pandemonium.")

        if any(w in ev for w in ["shot", "headshot", "kill"]) or any(w in secs for w in ["shot", "headshot", "kill"]):
            hooks.append(f"That shot connected right when it mattered most in {game}, completely flipping the round on its head.")
            hooks.append(f"A high-stakes {game} gunfight where crisp aim decided who walked away.")

        # 2. Reaction-specific hooks
        if clean_rx:
            hooks.append(f"Nobody in the lobby saw this coming in {game}. The reaction says it all: '{clean_rx}'.")
            hooks.append(f"The comms went wild after this {game} moment: '{clean_rx}'.")
            hooks.append(f"That reaction in {game} is priceless: '{clean_rx}'.")

        # 3. Tone & Atmosphere hooks
        if summary.tone == "shock/disbelief" or "shock" in ev:
            hooks.append(f"A jaw-dropping {game} moment that left everyone in the match completely speechless.")
            hooks.append(f"An unbelievable {game} sequence that caught the entire lobby completely off guard.")

        if summary.tone == "funny/chaotic" or "chaos" in ev:
            hooks.append(f"Pure {game} chaos from start to finish where absolutely nothing went according to plan.")
            hooks.append(f"Total mayhem in {game} as multiple mistakes collided in the span of a few seconds.")

        if summary.tone == "intense/clutch" or "clutch" in ev:
            hooks.append(f"Ice in the veins under maximum pressure. A high-stakes {game} clutch where positioning decided everything.")
            hooks.append(f"Down to the wire in {game}—an intense clutch scenario where every single movement mattered.")

        # 4. Fallback / General payoff hooks
        if summary.climax_timestamp > 0 or summary.intensity >= 0.7:
            hooks.append(f"A wild sequence in {game} building up to an unforgettable finish.")

        hooks.append(f"Non-stop high-energy action from the opening push to the final second of this {game} round.")

        # Deduplicate while preserving order
        unique_hooks = []
        for h in hooks:
            if h not in unique_hooks:
                unique_hooks.append(h)

        return unique_hooks

    def generate_description(
        self,
        summary: ClipSummary,
        selected_title: str,
        hashtags: List[str],
        source_metadata: Optional[Dict[str, Any]] = None,
        existing_descriptions: Optional[List[str]] = None,
    ) -> str:
        """Constructs a candidate-specific description with narrative hook diversity and deduplication."""
        game = summary.game
        rx = summary.strongest_reaction
        clean_rx = rx.replace("Phrase:", "").replace("Word:", "").strip() if rx and rx != "unknown" else ""

        # Attribution line (preserved)
        attr_line = ""
        if source_metadata:
            uploader = source_metadata.get("uploader", "")
            title = source_metadata.get("title", "")
            if uploader:
                attr_line = f"Original footage: {uploader} ('{title}')"

        # Hashtag line
        tag_str = " ".join(hashtags) if hashtags else f"#{game.replace(':', '')} #Gaming #Shorts"

        # Generate candidate narrative hooks grounded in signals
        candidate_hooks = self.generate_candidate_hooks(summary)

        # Assemble full description candidates
        desc_candidates: List[str] = []
        for hook in candidate_hooks:
            narrative_lines = [hook]
            if clean_rx and clean_rx not in hook and "reaction" not in hook.lower():
                narrative_lines.append(f"Wait for the reaction at the end: '{clean_rx}'.")

            parts = [" ".join(narrative_lines)]
            if attr_line:
                parts.append(attr_line)
            parts.append(tag_str)

            full_desc = "\n\n".join(parts)
            # Enforce max length constraint
            if len(full_desc) > self.max_length:
                trimmed_parts = [hook]
                if attr_line:
                    trimmed_parts.append(attr_line)
                trimmed_parts.append(tag_str)
                full_desc = "\n\n".join(trimmed_parts)

            if len(full_desc) >= self.min_length and len(full_desc) <= self.max_length:
                desc_candidates.append(full_desc.strip())

        if not desc_candidates:
            # Fallback safe description
            base_narrative = f"Highlight moment from {game}."
            parts = [base_narrative]
            if attr_line:
                parts.append(attr_line)
            parts.append(tag_str)
            return "\n\n".join(parts).strip()

        # Deduplication against existing descriptions
        if not existing_descriptions:
            return desc_candidates[0]

        best_desc = desc_candidates[0]
        min_max_sim = 1.0

        for cand_desc in desc_candidates:
            max_sim = max([compute_description_similarity(cand_desc, prev) for prev in existing_descriptions], default=0.0)
            if max_sim < self.similarity_threshold:
                return cand_desc
            if max_sim < min_max_sim:
                min_max_sim = max_sim
                best_desc = cand_desc

        return best_desc
