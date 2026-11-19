"""Generates boundary-aware 30-60 second candidate intervals for short video clips."""

from typing import List, Tuple, Dict, Any, Optional
from backend.app.config import (
    MIN_CANDIDATE_DURATION,
    MAX_CANDIDATE_DURATION,
    TARGET_CANDIDATE_DURATION,
    GAMEPLAY_WORDS,
    REACTION_WORDS,
    REACTION_PHRASES,
)
from .transcript_analyzer import TranscriptAnalyzer


class CandidateGenerator:
    """Generates candidate 30-60 second clip windows anchored around meaningful audio/transcript events."""

    def __init__(
        self,
        min_duration: float = MIN_CANDIDATE_DURATION,
        max_duration: float = MAX_CANDIDATE_DURATION,
        target_duration: float = TARGET_CANDIDATE_DURATION,
    ):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.target_duration = target_duration

    def generate_candidates(
        self,
        video_duration: float,
        audio_analysis: Dict[str, Any],
        transcript_analyzer: TranscriptAnalyzer,
        gameplay_timeline: Optional[Any] = None,
    ) -> List[Tuple[float, float]]:
        """
        Generates candidate (start, end) timestamp intervals.
        Handles short videos (<30s, 30-60s) and standard videos (>60s).
        Integrates Phase 12A concrete gameplay event anchors when provided.
        """
        # Edge Case 1: Video shorter than min_duration (e.g. 19s)
        if video_duration < self.min_duration:
            return [(0.0, round(video_duration, 2))]

        # Edge Case 2: Video between min and max duration (30s - 60s)
        if video_duration <= self.max_duration:
            candidates = [(0.0, round(video_duration, 2))]
            if transcript_analyzer.sentences:
                s_start = transcript_analyzer.sentences[0]["start"]
                s_end = transcript_analyzer.sentences[-1]["end"]
                if (s_end - s_start) >= self.min_duration:
                    candidates.append((round(s_start, 2), round(s_end, 2)))
            return list(set(candidates))

        # Standard Case: Video > 60s
        anchors: List[float] = []

        # Anchor Source A: Audio volume / Z-score peaks
        peaks = audio_analysis.get("peaks", [])
        for p in peaks:
            anchors.append(p["timestamp"])

        # Anchor Source B: Transcript gaming & reaction signals
        for s in transcript_analyzer.sentences:
            text_lower = s["text"].lower()
            has_gaming = any(gw in text_lower for gw in GAMEPLAY_WORDS)
            has_reaction = any(rw in text_lower for rw in REACTION_WORDS) or any(rp in text_lower for rp in REACTION_PHRASES)
            has_punct = "!" in s["text"] or "?" in s["text"]

            if has_gaming or has_reaction or has_punct:
                anchors.append(s["start"] + ((s["end"] - s["start"]) / 2.0))

        # Anchor Source C: Concrete Phase 12A Gameplay Events
        if gameplay_timeline and hasattr(gameplay_timeline, "events"):
            for ev in gameplay_timeline.events:
                if getattr(ev, "confidence", 0.0) >= 0.70 or getattr(ev, "status", "") == "confirmed":
                    midpoint = ev.start_time + ((ev.end_time - ev.start_time) / 2.0)
                    anchors.append(midpoint)

        # Anchor Source D: Regular interval grid across the video
        step_size = max(25.0, self.target_duration * 0.6)
        curr_t = step_size
        while curr_t < (video_duration - 20.0):
            anchors.append(curr_t)
            curr_t += step_size

        # Deduplicate and cluster anchors within 10 seconds of each other
        anchors = sorted(list(set(round(a, 1) for a in anchors)))
        clustered_anchors: List[float] = []
        for a in anchors:
            if not clustered_anchors or (a - clustered_anchors[-1] >= 10.0):
                clustered_anchors.append(a)

        candidates_set = set()

        # Step 2: For each anchor event, build Hook -> Event -> Payoff windows
        for anchor in clustered_anchors:
            for lead_in in [12.0, 18.0, 24.0]:
                target_start = max(0.0, anchor - lead_in)
                snapped_start = transcript_analyzer.find_nearest_sentence_start(target_start)

                if snapped_start >= anchor:
                    snapped_start = target_start

                for dur_target in [36.0, 44.0, 52.0]:
                    target_end = min(video_duration, snapped_start + dur_target)
                    snapped_end = transcript_analyzer.find_nearest_sentence_end(target_end)

                    duration = snapped_end - snapped_start
                    if self.min_duration <= duration <= self.max_duration:
                        candidates_set.add((round(snapped_start, 2), round(snapped_end, 2)))
                    elif duration < self.min_duration:
                        extended_end = min(video_duration, snapped_start + self.min_duration)
                        extended_end = transcript_analyzer.find_nearest_sentence_end(extended_end)
                        if self.min_duration <= (extended_end - snapped_start) <= self.max_duration:
                            candidates_set.add((round(snapped_start, 2), round(extended_end, 2)))

        # Also add sentence-aligned windows directly from transcript
        sentences = transcript_analyzer.sentences
        for i in range(len(sentences)):
            start_t = sentences[i]["start"]
            for j in range(i, len(sentences)):
                end_t = sentences[j]["end"]
                dur = end_t - start_t
                if self.min_duration <= dur <= self.max_duration:
                    candidates_set.add((round(start_t, 2), round(end_t, 2)))
                elif dur > self.max_duration:
                    break

        candidates_list = sorted(list(candidates_set))
        return candidates_list
