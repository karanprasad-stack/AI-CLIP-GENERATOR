"""Shorts-optimized subtitle grouping and line-breaking for mobile viewports."""

import re
from typing import List, Optional
from backend.app.config import (
    MIN_WORDS_PER_GROUP,
    MAX_WORDS_PER_GROUP,
    MIN_GROUP_DURATION,
    MAX_GROUP_DURATION,
    MAX_GROUP_CHARS,
    PAUSE_THRESHOLD_SEC,
    CAPTION_LEAD_IN,
    CAPTION_TAIL_OUT,
)
from backend.app.pipeline.caption_engine import CaptionWord, CaptionGroup


class SubtitleGrouper:
    """Groups words into fast-scanning 1-4 word subtitle units for mobile Shorts."""

    def __init__(
        self,
        min_words: int = MIN_WORDS_PER_GROUP,
        max_words: int = MAX_WORDS_PER_GROUP,
        min_duration: float = MIN_GROUP_DURATION,
        max_duration: float = MAX_GROUP_DURATION,
        max_chars: int = MAX_GROUP_CHARS,
        pause_threshold: float = PAUSE_THRESHOLD_SEC,
        lead_in: float = CAPTION_LEAD_IN,
        tail_out: float = CAPTION_TAIL_OUT,
    ):
        self.min_words = min_words
        self.max_words = max_words
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.max_chars = max_chars
        self.pause_threshold = pause_threshold
        self.lead_in = lead_in
        self.tail_out = tail_out

    def group_words(
        self,
        words: List[CaptionWord],
        clip_duration: Optional[float] = None,
    ) -> List[CaptionGroup]:
        """Groups words into short, rhythmic groups with safe timing boundaries."""
        if not words:
            return []

        groups: List[CaptionGroup] = []
        current: List[CaptionWord] = []

        for i, word in enumerate(words):
            if not current:
                current.append(word)
                continue

            prev = current[-1]
            pause = word.start - prev.end
            dur = word.end - current[0].start
            chars = sum(len(w.text) for w in current) + len(word.text) + len(current)

            is_sentence_end = bool(re.search(r'[.!?]$', prev.text))
            is_pause = pause >= self.pause_threshold
            exceeds_words = len(current) >= self.max_words
            exceeds_duration = dur > self.max_duration
            exceeds_chars = chars > self.max_chars

            if is_sentence_end or is_pause or exceeds_words or exceeds_duration or exceeds_chars:
                # Avoid orphan single word trailing if merge is feasible
                if (len(words) - i) == 1 and len(current) < self.max_words and not is_sentence_end:
                    if (words[-1].end - current[0].start) <= (self.max_duration * 1.25):
                        current.append(word)
                        continue

                groups.append(self._build_group(current, clip_duration))
                current = [word]
            else:
                current.append(word)

        if current:
            groups.append(self._build_group(current, clip_duration))

        return groups

    def _build_group(self, words: List[CaptionWord], clip_duration: Optional[float]) -> CaptionGroup:
        g_start = max(0.0, words[0].start - self.lead_in)
        g_end = words[-1].end + self.tail_out

        if (g_end - g_start) < self.min_duration:
            g_end = g_start + self.min_duration

        if clip_duration is not None and clip_duration > 0:
            g_end = min(clip_duration, g_end)
            g_start = min(g_start, max(0.0, g_end - 0.05))

        return CaptionGroup(
            words=words,
            start=round(g_start, 3),
            end=round(g_end, 3),
            text=" ".join(w.text for w in words),
        )
