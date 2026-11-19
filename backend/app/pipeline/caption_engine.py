"""Word-level caption extraction, timing refinement, and chunk grouping."""

import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

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


@dataclass
class CaptionWord:
    """Represents a single timestamped word relative to clip start."""
    text: str
    start: float           # Relative start timestamp (seconds)
    end: float             # Relative end timestamp (seconds)
    index: int             # Sequential word index within the clip
    global_start: float    # Absolute timestamp in source video (seconds)
    global_end: float      # Absolute timestamp in source video (seconds)

    def duration(self) -> float:
        return max(0.01, self.end - self.start)


@dataclass
class CaptionGroup:
    """A natural grouping of 1-4 words displayed together as a single subtitle line."""
    words: List[CaptionWord] = field(default_factory=list)
    start: float = 0.0     # Group start timestamp (seconds, relative to clip)
    end: float = 0.0       # Group end timestamp (seconds, relative to clip)
    text: str = ""         # Combined text representation

    def duration(self) -> float:
        return max(0.01, self.end - self.start)


class CaptionEngine:
    """Extracts words from existing transcript and groups them into Shorts-style captions."""

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

    def extract_words(
        self,
        transcript_data: Dict[str, Any],
        clip_start: float,
        clip_end: float,
        clip_duration: Optional[float] = None,
    ) -> List[CaptionWord]:
        """
        Extracts words overlapping [clip_start, clip_end] and converts timestamps
        to candidate-relative seconds starting at 0.0.
        """
        raw_words: List[CaptionWord] = []
        segments = transcript_data.get("segments", [])
        word_idx = 0

        effective_max = clip_duration if clip_duration is not None else (clip_end - clip_start)

        for seg in segments:
            seg_words = seg.get("words", [])
            for w in seg_words:
                w_start = float(w.get("start", 0.0))
                w_end = float(w.get("end", 0.0))
                w_text = str(w.get("word", "")).strip()

                if not w_text:
                    continue

                # Check overlap with candidate window
                if w_start < clip_end and w_end > clip_start:
                    rel_start = max(0.0, w_start - clip_start)
                    rel_end = w_end - clip_start

                    if effective_max > 0:
                        rel_end = min(effective_max, rel_end)

                    # Ensure valid monotonic duration
                    if rel_end <= rel_start:
                        rel_end = rel_start + 0.10

                    raw_words.append(
                        CaptionWord(
                            text=w_text,
                            start=round(rel_start, 3),
                            end=round(rel_end, 3),
                            index=word_idx,
                            global_start=round(w_start, 3),
                            global_end=round(w_end, 3),
                        )
                    )
                    word_idx += 1

        return raw_words

    def group_words(
        self,
        words: List[CaptionWord],
        clip_duration: Optional[float] = None,
    ) -> List[CaptionGroup]:
        """
        Groups words into rhythmic 1-4 word chunks respecting pauses, punctuation,
        duration limits, and safe-zone boundaries.
        """
        if not words:
            return []

        groups: List[CaptionGroup] = []
        current_chunk: List[CaptionWord] = []

        for i, word in enumerate(words):
            if not current_chunk:
                current_chunk.append(word)
                continue

            prev_word = current_chunk[-1]
            pause = word.start - prev_word.end
            chunk_dur = word.end - current_chunk[0].start
            chunk_chars = sum(len(w.text) for w in current_chunk) + len(word.text) + len(current_chunk)

            # Strong boundary signals
            is_sentence_end = bool(re.search(r'[.!?]$', prev_word.text))
            is_pause = pause >= self.pause_threshold
            exceeds_words = len(current_chunk) >= self.max_words
            exceeds_duration = chunk_dur > self.max_duration
            exceeds_chars = chunk_chars > self.max_chars

            if is_sentence_end or is_pause or exceeds_words or exceeds_duration or exceeds_chars:
                # Avoid orphan single trailing word (Rule A)
                remaining_words = len(words) - i
                if remaining_words == 1 and len(current_chunk) < self.max_words and not is_sentence_end:
                    # Merge if duration allows
                    if (words[-1].end - current_chunk[0].start) <= (self.max_duration * 1.25):
                        current_chunk.append(word)
                        continue

                # Finalize current group
                groups.append(self._finalize_group(current_chunk, clip_duration))
                current_chunk = [word]
            else:
                current_chunk.append(word)

        if current_chunk:
            groups.append(self._finalize_group(current_chunk, clip_duration))

        return groups

    def _finalize_group(
        self,
        words: List[CaptionWord],
        clip_duration: Optional[float] = None,
    ) -> CaptionGroup:
        """Applies lead-in/tail-out timing and constructs CaptionGroup."""
        g_start = max(0.0, words[0].start - self.lead_in)
        g_end = words[-1].end + self.tail_out

        # Enforce minimum display duration for legibility
        if (g_end - g_start) < self.min_duration:
            g_end = g_start + self.min_duration

        if clip_duration is not None and clip_duration > 0:
            g_end = min(clip_duration, g_end)
            g_start = min(g_start, max(0.0, g_end - 0.05))

        group_text = " ".join(w.text for w in words)
        return CaptionGroup(
            words=words,
            start=round(g_start, 3),
            end=round(g_end, 3),
            text=group_text,
        )

    def process_candidate(
        self,
        transcript_data: Dict[str, Any],
        candidate_start: float,
        candidate_end: float,
        clip_duration: Optional[float] = None,
    ) -> List[CaptionGroup]:
        """Convenience method running extraction and grouping end-to-end."""
        words = self.extract_words(
            transcript_data=transcript_data,
            clip_start=candidate_start,
            clip_end=candidate_end,
            clip_duration=clip_duration,
        )
        return self.group_words(words=words, clip_duration=clip_duration)
