"""Speech-aware audio ducking engine: computes transparent gain automation curves from transcript timings."""

import math
from typing import Dict, Any, List, Optional, Tuple

from backend.app.config import (
    DUCKING_DB,
    STRONG_SPEECH_DUCKING_DB,
    DUCK_ATTACK_MS,
    DUCK_RELEASE_MS,
)


class DuckingEngine:
    """Computes conservative speech-aware gain automation curves based on Whisper transcript timestamps."""

    def __init__(
        self,
        ducking_db: float = DUCKING_DB,
        strong_speech_db: float = STRONG_SPEECH_DUCKING_DB,
        attack_ms: int = DUCK_ATTACK_MS,
        release_ms: int = DUCK_RELEASE_MS,
        pause_merge_sec: float = 0.35,
    ):
        self.ducking_db = ducking_db
        self.strong_speech_db = strong_speech_db
        self.attack_sec = attack_ms / 1000.0
        self.release_sec = release_ms / 1000.0
        self.pause_merge_sec = pause_merge_sec

    def extract_speech_intervals(
        self,
        transcript_data: Dict[str, Any],
        clip_start: float,
        clip_end: float,
        clip_duration: float,
    ) -> List[Dict[str, float]]:
        """
        Extracts speech intervals within the candidate window and merges words
        separated by short pauses into natural continuous speech segments.
        """
        raw_words: List[Tuple[float, float]] = []

        segments = transcript_data.get("segments", [])
        for seg in segments:
            for w in seg.get("words", []):
                ws = float(w.get("start", 0.0))
                we = float(w.get("end", 0.0))
                if ws < clip_end and we > clip_start:
                    rel_s = max(0.0, ws - clip_start)
                    rel_e = min(clip_duration, we - clip_start)
                    if rel_e > rel_s:
                        raw_words.append((rel_s, rel_e))

        if not raw_words:
            return []

        raw_words.sort(key=lambda x: x[0])

        merged: List[Dict[str, float]] = []
        cur_start, cur_end = raw_words[0]

        for s, e in raw_words[1:]:
            if (s - cur_end) <= self.pause_merge_sec:
                cur_end = max(cur_end, e)
            else:
                merged.append({"start": round(cur_start, 3), "end": round(cur_end, 3)})
                cur_start, cur_end = s, e

        merged.append({"start": round(cur_start, 3), "end": round(cur_end, 3)})
        return merged

    def compute_ducking_plan(
        self,
        transcript_data: Dict[str, Any],
        candidate: Dict[str, Any],
        impact_events: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Builds the complete ducking schedule and metadata, relaxing ducking
        around key gameplay impact moments to preserve gunshot/explosion impact.
        """
        clip_start = float(candidate.get("extraction_start", candidate.get("candidate_start", 0.0)))
        clip_end = float(candidate.get("extraction_end", candidate.get("candidate_end", 60.0)))
        clip_duration = float(candidate.get("extraction_duration", clip_end - clip_start))

        raw_intervals = self.extract_speech_intervals(
            transcript_data=transcript_data,
            clip_start=clip_start,
            clip_end=clip_end,
            clip_duration=clip_duration,
        )

        impact_times = []
        if impact_events:
            for ev in impact_events:
                impact_times.append(float(ev.get("timestamp", 0.0)))

        adjusted_intervals: List[Dict[str, Any]] = []

        for iv in raw_intervals:
            s = iv["start"]
            e = iv["end"]
            dur = e - s

            # Dense, prolonged speech gets slightly deeper ducking (-4.5dB vs -3.5dB)
            is_dense = dur > 2.0
            duck_db = self.strong_speech_db if is_dense else self.ducking_db
            duck_ratio = round(10.0 ** (duck_db / 20.0), 3)

            # Check if a major impact occurs inside this speech block
            has_impact = any((s <= it <= e) for it in impact_times)
            if has_impact:
                # Relax ducking by 1.5dB so impact punches through
                relaxed_db = min(-1.5, duck_db + 1.5)
                duck_ratio = round(10.0 ** (relaxed_db / 20.0), 3)

            adjusted_intervals.append({
                "start": s,
                "end": e,
                "duration": round(dur, 3),
                "ducking_db": duck_db,
                "gain_ratio": duck_ratio,
                "impact_exempted": has_impact,
            })

        max_reduction = abs(min([iv["ducking_db"] for iv in adjusted_intervals], default=0.0))

        summary = {
            "enabled": len(adjusted_intervals) > 0,
            "speech_intervals_count": len(adjusted_intervals),
            "max_reduction_db": round(max_reduction, 2),
            "attack_ms": int(self.attack_sec * 1000),
            "release_ms": int(self.release_sec * 1000),
            "intervals": adjusted_intervals,
        }

        return summary

    def build_ffmpeg_volume_expression(self, ducking_summary: Dict[str, Any]) -> str:
        """
        Constructs an FFmpeg volume expression for `volume=eval=frame:volume='...'`
        with smooth linear attack and release ramps.
        """
        intervals = ducking_summary.get("intervals", [])
        if not intervals:
            return "1.0"

        terms: List[str] = []
        for iv in intervals:
            s = iv["start"]
            e = iv["end"]
            target_gain = iv["gain_ratio"]
            delta = round(1.0 - target_gain, 3)

            att_start = max(0.0, s - self.attack_sec)
            rel_end = e + self.release_sec

            # Smooth envelope:
            # - Attack ramp: 1.0 down to target_gain over [att_start, s]
            # - Plateau: target_gain over [s, e]
            # - Release ramp: target_gain up to 1.0 over [e, rel_end]
            # Formulated as: 1.0 - delta * envelope
            term = (
                f"{delta}*("
                f"if(between(t,{att_start:.3f},{s:.3f}),(t-{att_start:.3f})/{self.attack_sec:.3f},"
                f"if(between(t,{s:.3f},{e:.3f}),1.0,"
                f"if(between(t,{e:.3f},{rel_end:.3f}),1.0-(t-{e:.3f})/{self.release_sec:.3f},0)"
                f")))"
            )
            terms.append(term)

        # Total gain = 1.0 - max(terms) (clamped between min_gain and 1.0)
        # In practice, with non-overlapping speech blocks, sum of non-zero terms is exact:
        subtractions = "+".join(terms)
        return f"max(0.40,1.0-({subtractions}))"
