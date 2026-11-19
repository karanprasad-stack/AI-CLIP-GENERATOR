"""Generates boundary-aware 30-60 second candidate intervals for short video clips."""

from typing import List, Tuple, Dict, Any, Optional
from backend.app.config import (
    MIN_CANDIDATE_DURATION,
    MAX_CANDIDATE_DURATION,
    TARGET_CANDIDATE_DURATION,
    MIN_CLIP_DURATION_V2,
    MAX_CLIP_DURATION_V2,
    GAMEPLAY_WORDS,
    REACTION_WORDS,
    REACTION_PHRASES,
)
from .transcript_analyzer import TranscriptAnalyzer


class CandidateGenerator:
    """Generates candidate 15-180 second clip windows anchored around meaningful audio/transcript/gameplay events."""

    def __init__(
        self,
        min_duration: float = MIN_CANDIDATE_DURATION,
        max_duration: float = MAX_CANDIDATE_DURATION,
        target_duration: float = TARGET_CANDIDATE_DURATION,
        duration_mode: str = "auto",
        preferred_duration_range: Optional[Tuple[float, float]] = None,
    ):
        self.duration_mode = duration_mode
        self.preferred_duration_range = preferred_duration_range

        if preferred_duration_range:
            self.min_duration = float(preferred_duration_range[0])
            self.max_duration = float(preferred_duration_range[1])
        elif duration_mode == "quick":
            self.min_duration = 15.0
            self.max_duration = 30.0
        elif duration_mode == "standard":
            self.min_duration = 30.0
            self.max_duration = 90.0
        elif duration_mode == "extended":
            self.min_duration = 90.0
            self.max_duration = 180.0
        else:
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
        generic_anchors: List[float] = []

        # Anchor Source A: Audio volume / Z-score peaks
        peaks = audio_analysis.get("peaks", [])
        for p in peaks:
            generic_anchors.append(p["timestamp"])

        # Anchor Source B: Transcript gaming & reaction signals
        for s in transcript_analyzer.sentences:
            text_lower = s["text"].lower()
            has_gaming = any(gw in text_lower for gw in GAMEPLAY_WORDS)
            has_reaction = any(rw in text_lower for rw in REACTION_WORDS) or any(rp in text_lower for rp in REACTION_PHRASES)
            has_punct = "!" in s["text"] or "?" in s["text"]

            if has_gaming or has_reaction or has_punct:
                generic_anchors.append(s["start"] + ((s["end"] - s["start"]) / 2.0))

        # Anchor Source D: Regular interval grid across the video
        step_size = max(25.0, self.target_duration * 0.6)
        curr_t = step_size
        while curr_t < (video_duration - 20.0):
            generic_anchors.append(curr_t)
            curr_t += step_size

        # Cluster generic anchors within 10 seconds of each other
        generic_anchors = sorted(list(set(round(a, 1) for a in generic_anchors)))
        clustered_generic: List[float] = []
        for a in generic_anchors:
            if not clustered_generic or (a - clustered_generic[-1] >= 10.0):
                clustered_generic.append(a)

        # Anchor Source C: Priority Phase 12A/12B Gameplay Events
        priority_events = []
        priority_anchors: List[float] = []
        if gameplay_timeline and hasattr(gameplay_timeline, "events"):
            for ev in gameplay_timeline.events:
                status = getattr(ev, "status", "")
                conf = getattr(ev, "confidence", 0.0)
                etype = getattr(ev, "event_type", "")
                is_high_val = etype in {
                    "ace", "ace_candidate", "multi_kill", "rapid_kill_sequence",
                    "clutch_candidate", "1vx_candidate", "round_win",
                    # Multi-genre high-value gameplay events
                    "story_climax", "comedic_moment", "chaos_burst",
                    "boss_fight_climax", "jumpscare", "panic_escape",
                } or (etype == "kill" and (status == "confirmed" or conf >= 0.75))

                if is_high_val and (status == "confirmed" or conf >= 0.70):
                    priority_events.append(ev)
                    midpoint = ev.start_time + ((ev.end_time - ev.start_time) / 2.0)
                    priority_anchors.append(midpoint)

        # Cluster priority anchors separately within 6 seconds so none are swallowed by generic anchors
        priority_anchors = sorted(list(set(round(a, 1) for a in priority_anchors)))
        clustered_priority: List[float] = []
        for pa in priority_anchors:
            if not clustered_priority or (pa - clustered_priority[-1] >= 6.0):
                clustered_priority.append(pa)

        # Combined anchor set (priority anchors ALWAYS preserved)
        all_anchors = sorted(list(set(clustered_generic + clustered_priority)))

        candidates_set = set()

        # Step 2: Multi-Tier Duration Targets (15s to 180s)
        dur_targets = []
        if self.min_duration <= 25.0:
            dur_targets.extend([18.0, 24.0, 28.0])
        dur_targets.extend([36.0, 44.0, 52.0])
        if self.max_duration >= 70.0:
            dur_targets.extend([68.0, 80.0])
        if self.max_duration >= 110.0:
            dur_targets.extend([105.0, 130.0, 160.0])

        dur_targets = sorted(list(set([d for d in dur_targets if self.min_duration <= d <= self.max_duration])))
        if not dur_targets:
            dur_targets = [self.min_duration, (self.min_duration + self.max_duration) / 2.0, self.max_duration]

        lead_ins = [4.0, 8.0, 12.0, 18.0, 24.0]

        # For each anchor event, build Hook -> Event -> Payoff windows across tiers
        for anchor in all_anchors:
            for lead_in in lead_ins:
                if lead_in >= self.max_duration * 0.6:
                    continue
                target_start = max(0.0, anchor - lead_in)
                snapped_start = transcript_analyzer.find_nearest_sentence_start(target_start)

                if snapped_start >= anchor:
                    snapped_start = target_start

                for dur_target in dur_targets:
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

        # Step 2.5: For priority combat events, explicitly frame the full [start_time, end_time] span
        for ev in priority_events:
            ev_start = max(0.0, float(ev.start_time))
            ev_end = min(video_duration, float(ev.end_time))
            ev_len = ev_end - ev_start

            if ev_len <= self.max_duration:
                etype = getattr(ev, "event_type", "")
                if etype in {"story_climax", "comedic_moment", "boss_fight_climax"}:
                    combat_lead_ins = [8.0, 16.0, 24.0, 32.0]
                    combat_lead_outs = [4.0, 8.0, 14.0]
                else:
                    combat_lead_ins = [4.0, 8.0, 12.0, 16.0]
                    combat_lead_outs = [4.0, 6.0, 10.0, 14.0]
                for lead_in in combat_lead_ins:
                    for lead_out in combat_lead_outs:
                        target_start = max(0.0, ev_start - lead_in)
                        snapped_start = transcript_analyzer.find_nearest_sentence_start(target_start)
                        if snapped_start > ev_start:
                            snapped_start = target_start

                        target_end = min(video_duration, ev_end + lead_out)
                        snapped_end = transcript_analyzer.find_nearest_sentence_end(target_end)
                        if snapped_end < ev_end:
                            snapped_end = target_end

                        dur = snapped_end - snapped_start
                        if dur < self.min_duration:
                            needed = self.min_duration - dur
                            if (snapped_end + needed) <= video_duration:
                                snapped_end += needed
                            else:
                                snapped_start = max(0.0, snapped_start - (needed - (video_duration - snapped_end)))
                                snapped_end = video_duration
                            dur = snapped_end - snapped_start
                        elif dur > self.max_duration:
                            excess = dur - self.max_duration
                            can_trim_start = min(excess, ev_start - snapped_start)
                            snapped_start += can_trim_start
                            excess -= can_trim_start
                            if excess > 0:
                                snapped_end -= excess
                            dur = snapped_end - snapped_start

                        if self.min_duration <= dur <= self.max_duration and snapped_start <= ev_start and snapped_end >= ev_end:
                            candidates_set.add((round(snapped_start, 2), round(snapped_end, 2)))

        # Step 2.6: Phase 12C Round-Aware Context Expansion
        # Connect setup (opening kill / spike plant) -> climax (multi-kill / clutch) -> resolution (defuse / round win)
        if gameplay_timeline and hasattr(gameplay_timeline, "events"):
            all_events = getattr(gameplay_timeline, "events", [])
            round_end_events = [
                e for e in all_events
                if getattr(e, "event_type", "") in {"round_win", "round_loss", "round_ending_kill"}
            ]

            for ev in priority_events:
                # Find round floor (prior round conclusion or 0)
                prior_round_ends = [e.end_time for e in round_end_events if e.end_time < (ev.start_time - 5.0)]
                round_floor = max(prior_round_ends) if prior_round_ends else 0.0

                # Find resolution of current round
                curr_round_ends = [e for e in round_end_events if round_floor <= e.start_time and e.end_time >= ev.start_time]
                curr_resolution = curr_round_ends[0] if curr_round_ends else None

                # Find ceiling (subsequent round boundary or video_duration)
                if curr_resolution:
                    subsequent_bounds = [e.start_time for e in round_end_events if e.start_time > (curr_resolution.end_time + 10.0)]
                else:
                    subsequent_bounds = [e.start_time for e in round_end_events if e.start_time > (ev.end_time + 10.0)]
                round_ceil = min(subsequent_bounds) if subsequent_bounds else video_duration

                # Preceding round events in same round
                earlier_events = [
                    e for e in all_events
                    if round_floor <= e.start_time < ev.start_time
                    and getattr(e, "event_type", "") in {"opening_kill", "first_blood", "spike_planted", "kill"}
                    and getattr(e, "status", "") != "supporting"
                ]

                # Subsequent round events in same round
                later_events = [
                    e for e in all_events
                    if ev.end_time < e.end_time <= round_ceil
                    and getattr(e, "event_type", "") in {"round_win", "spike_defused", "spike_denied", "round_ending_kill"}
                    and getattr(e, "status", "") != "supporting"
                ]

                if earlier_events or later_events:
                    first_ev_start = min([e.start_time for e in earlier_events] + [ev.start_time])
                    last_ev_end = max([e.end_time for e in later_events] + [ev.end_time])

                    # Include natural 4-8s pre-engagement lead-in and post-round celebration tail
                    exp_start = max(round_floor, max(0.0, first_ev_start - 6.0))
                    exp_end = min(round_ceil, min(video_duration, last_ev_end + 6.0))

                    snapped_exp_start = transcript_analyzer.find_nearest_sentence_start(exp_start)
                    if snapped_exp_start > first_ev_start:
                        snapped_exp_start = exp_start
                    snapped_exp_start = max(round_floor, max(0.0, snapped_exp_start))

                    snapped_exp_end = transcript_analyzer.find_nearest_sentence_end(exp_end)
                    if snapped_exp_end < last_ev_end:
                        snapped_exp_end = exp_end
                    snapped_exp_end = min(round_ceil, min(video_duration, snapped_exp_end))

                    exp_dur = snapped_exp_end - snapped_exp_start
                    if self.min_duration <= exp_dur <= self.max_duration:
                        candidates_set.add((round(snapped_exp_start, 2), round(snapped_exp_end, 2)))

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
