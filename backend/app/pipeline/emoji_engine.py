"""Contextual reaction and gameplay emoji engine based on transcript and audio signals."""

import re
from typing import Dict, Any, List, Optional

from backend.app.config import (
    REACTION_PHRASES,
    REACTION_WORDS,
    HIGH_IMPACT_GAMING_WORDS,
    GAMEPLAY_WORDS,
    LAUGHTER_WORDS,
    EMOJI_MIN_CONFIDENCE,
    EMOJI_MIN_INTERVAL,
    EMOJI_DEFAULT_DURATION,
)


# Semantic emoji mapping table based on detected gaming / reaction signal categories
EMOJI_CATEGORY_MAP = {
    # Extreme shock / surprise / mind-blown
    "shock": ["😱", "🤯"],
    # Victory / clutch / fire plays
    "fire": ["🔥", "🏆"],
    # Hilarious / funny / laughter
    "funny": ["😂", "💀"],
    # Facepalm / fail / disbelief / bad timing
    "disbelief": ["💀", "😭"],
    # Precision / skill / headshot
    "skill": ["🎯", "⚡"],
}


class EmojiEngine:
    """Detects situational emoji events strictly anchored to genuine reactions and audio events."""

    def __init__(
        self,
        min_confidence: float = EMOJI_MIN_CONFIDENCE,
        min_interval: float = EMOJI_MIN_INTERVAL,
        default_duration: float = EMOJI_DEFAULT_DURATION,
    ):
        self.min_confidence = min_confidence
        self.min_interval = min_interval
        self.default_duration = default_duration

    def detect_emojis(
        self,
        transcript_data: Dict[str, Any],
        clip_start: float,
        clip_end: float,
        audio_peaks: Optional[List[Dict[str, Any]]] = None,
        clip_duration: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scans words and phrases in [clip_start, clip_end] for reaction signals,
        computes confidence based on audio alignment and signal strength,
        and returns non-overlapping contextual emoji events.
        """
        effective_duration = clip_duration if clip_duration is not None else (clip_end - clip_start)
        raw_events: List[Dict[str, Any]] = []

        # Gather words and text within the clip
        words_in_clip: List[Dict[str, Any]] = []
        full_clip_text_parts: List[str] = []

        for seg in transcript_data.get("segments", []):
            for w in seg.get("words", []):
                ws = float(w.get("start", 0.0))
                we = float(w.get("end", 0.0))
                wt = str(w.get("word", "")).strip().lower()
                if ws < clip_end and we > clip_start and wt:
                    words_in_clip.append({
                        "word": wt,
                        "clean_word": re.sub(r'[^a-z0-9]', '', wt),
                        "start": ws,
                        "end": we,
                    })
                    full_clip_text_parts.append(wt)

        full_clip_text = " ".join(full_clip_text_parts)

        # Helper to check if an audio peak aligns with a timestamp (within 2.5 seconds)
        def has_aligned_audio_peak(timestamp: float) -> bool:
            if not audio_peaks:
                return False
            return any(abs(float(p.get("timestamp", 0.0)) - timestamp) <= 2.5 for p in audio_peaks)

        # 1. Match multi-word reaction phrases
        for phrase in REACTION_PHRASES:
            if phrase in full_clip_text:
                phrase_tokens = phrase.split()
                # Locate the phrase timestamp among words
                for idx in range(len(words_in_clip) - len(phrase_tokens) + 1):
                    window = [w["clean_word"] for w in words_in_clip[idx:idx + len(phrase_tokens)]]
                    if window == [re.sub(r'[^a-z0-9]', '', t) for t in phrase_tokens]:
                        p_start = words_in_clip[idx]["start"]
                        aligned_audio = has_aligned_audio_peak(p_start)
                        conf = 0.78 + (0.13 if aligned_audio else 0.0)

                        # Determine emoji
                        if any(k in phrase for k in ["timing", "fail", "serious", "kidding", "hell", "heck", "bro"]):
                            emoji_char = "💀"
                            category = "disbelief"
                        elif any(k in phrase for k in ["let's go", "lets go", "got him", "watch this"]):
                            emoji_char = "🔥"
                            category = "fire"
                        else:
                            emoji_char = "🤯"
                            category = "shock"

                        raw_events.append({
                            "global_time": p_start,
                            "emoji": emoji_char,
                            "category": category,
                            "confidence": round(min(1.0, conf), 2),
                            "reason": f"reaction_phrase: '{phrase}'" + (" + audio_peak" if aligned_audio else ""),
                            "source_signal": phrase,
                        })

        # 2. Match single-word high-impact reactions and gameplay signals
        for w in words_in_clip:
            cw = w["clean_word"]
            t = w["start"]
            aligned_audio = has_aligned_audio_peak(t)

            # Laughter words
            if cw in LAUGHTER_WORDS:
                conf = 0.70 + (0.15 if aligned_audio else 0.0)
                raw_events.append({
                    "global_time": t,
                    "emoji": "😂",
                    "category": "funny",
                    "confidence": round(min(1.0, conf), 2),
                    "reason": f"laughter: '{cw}'" + (" + audio_peak" if aligned_audio else ""),
                    "source_signal": cw,
                })

            # High-impact combat terms (clutch, headshot, ace)
            elif cw in HIGH_IMPACT_GAMING_WORDS:
                conf = 0.75 + (0.15 if aligned_audio else 0.0)
                emoji_char = "🔥" if cw in ["clutch", "ace", "1v1", "1v2", "1v3"] else "🎯"
                raw_events.append({
                    "global_time": t,
                    "emoji": emoji_char,
                    "category": "fire" if emoji_char == "🔥" else "skill",
                    "confidence": round(min(1.0, conf), 2),
                    "reason": f"high_impact_gameplay: '{cw}'" + (" + audio_peak" if aligned_audio else ""),
                    "source_signal": cw,
                })

            # Reaction words (wow, whoa, crazy, insane, bruh, etc.)
            elif cw in REACTION_WORDS:
                # Require aligned audio peak or high-value word to prevent noise
                if aligned_audio or cw in ["wow", "whoa", "bruh", "insane", "omg"]:
                    conf = 0.65 + (0.15 if aligned_audio else 0.05)
                    emoji_char = "💀" if cw in ["bruh", "damn", "clown"] else ("🤯" if cw in ["whoa", "wow", "insane", "crazy"] else "😱")
                    raw_events.append({
                        "global_time": t,
                        "emoji": emoji_char,
                        "category": "shock",
                        "confidence": round(min(1.0, conf), 2),
                        "reason": f"reaction_word: '{cw}'" + (" + audio_peak" if aligned_audio else ""),
                        "source_signal": cw,
                    })

            # Specific CSGO / tactical terms (fail, timing, flash)
            elif cw in ["fail", "timing", "flash"]:
                if aligned_audio or cw in ["fail", "timing"]:
                    conf = 0.70 + (0.12 if aligned_audio else 0.0)
                    raw_events.append({
                        "global_time": t,
                        "emoji": "💀",
                        "category": "disbelief",
                        "confidence": round(min(1.0, conf), 2),
                        "reason": f"gameplay_event: '{cw}'" + (" + audio_peak" if aligned_audio else ""),
                        "source_signal": cw,
                    })

        # 3. Filter by minimum confidence threshold
        qualified = [e for e in raw_events if e["confidence"] >= self.min_confidence]

        # 4. Sort by confidence descending and apply spacing (non-overlapping)
        qualified.sort(key=lambda x: x["confidence"], reverse=True)

        selected_events: List[Dict[str, Any]] = []
        for cand in qualified:
            cand_time = cand["global_time"]
            # Enforce minimum temporal interval between emojis
            if any(abs(cand_time - s["global_time"]) < self.min_interval for s in selected_events):
                continue
            selected_events.append(cand)

        # 5. Sort chronologically and convert to candidate-relative timestamps
        selected_events.sort(key=lambda x: x["global_time"])

        final_events: List[Dict[str, Any]] = []
        for ev in selected_events:
            rel_start = max(0.0, ev["global_time"] - clip_start)
            rel_end = rel_start + self.default_duration

            if effective_duration > 0:
                rel_end = min(effective_duration, rel_end)
                if rel_start >= effective_duration:
                    continue

            final_events.append({
                "emoji": ev["emoji"],
                "start": round(rel_start, 3),
                "end": round(rel_end, 3),
                "confidence": ev["confidence"],
                "category": ev["category"],
                "reason": ev["reason"],
                "source_signal": ev["source_signal"],
            })

        return final_events
