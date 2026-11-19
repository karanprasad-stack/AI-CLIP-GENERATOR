"""Horror & Survival event detector: silence-to-scream jumpscares and frantic panic escapes."""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

from backend.app.pipeline.games.models import (
    GameplayEvent,
    EventType,
    EventStatus,
    EvidenceBreakdown,
)
from backend.app.pipeline.games.profiles.base import BaseGameProfile


class HorrorDetector:
    """Detects jumpscares (silence-to-scream contrast) and panic escapes."""

    def __init__(self, profile: BaseGameProfile):
        self.profile = profile

    def detect_events(
        self,
        video_path: Optional[Path] = None,
        audio_analysis: Optional[Dict[str, Any]] = None,
        transcript_data: Optional[Dict[str, Any]] = None,
        duration: float = 0.0,
        start_sec: float = 0.0,
    ) -> List[GameplayEvent]:
        events: List[GameplayEvent] = []
        ev_id = 0

        # Parse transcript words
        words: List[Dict[str, Any]] = []
        if transcript_data:
            if "words" in transcript_data:
                words = transcript_data["words"]
            elif "segments" in transcript_data:
                words = [w for s in transcript_data["segments"] for w in s.get("words", [])]

        # Extract audio peaks & timeline
        audio_peaks: List[Dict[str, Any]] = []
        audio_timeline: List[Dict[str, Any]] = []
        global_mean_rms = 0.05
        if audio_analysis:
            audio_peaks = audio_analysis.get("rms_peaks", audio_analysis.get("peaks", []))
            audio_timeline = audio_analysis.get("timeline", [])
            if not audio_timeline and "rms_series" in audio_analysis:
                audio_timeline = [
                    {"t": item[0], "rms": item[1]} if isinstance(item, (list, tuple)) else item
                    for item in audio_analysis["rms_series"]
                ]
            global_mean_rms = float(audio_analysis.get("global_mean_rms", audio_analysis.get("mean_rms", 0.05)))

        # ----------------------------------------------------------------------
        # 1. Jumpscares (Silence-to-Scream Contrast)
        # ----------------------------------------------------------------------
        # Look for audio peaks with Z >= 2.3 and RMS >= 0.20 preceded by a quiet/silent buffer
        for p in audio_peaks:
            pt = float(p.get("timestamp", 0.0))
            z = float(p.get("z_score", p.get("intensity", 0.0) * 3.0 if "intensity" in p else 2.5))
            peak_rms = float(p.get("rms", p.get("intensity", 0.3)))

            if z >= 2.3 and peak_rms >= 0.18:
                # Inspect 3.0s to 7.0s window before peak
                pre_window_start = max(0.0, pt - 6.0)
                pre_window_end = max(0.0, pt - 0.5)

                prior_rms_samples = [
                    float(pt_item.get("rms", global_mean_rms))
                    for pt_item in audio_timeline
                    if pre_window_start <= float(pt_item.get("t", pt_item.get("timestamp", 0.0))) <= pre_window_end
                ]

                mean_prior = float(np.mean(prior_rms_samples)) if prior_rms_samples else global_mean_rms

                # Jumpscare contrast ratio: peak compared to prior silence
                contrast_ratio = peak_rms / max(0.01, mean_prior)

                if contrast_ratio >= 2.2 or mean_prior <= 0.12:
                    conf = min(0.98, max(0.85, 0.70 + 0.05 * contrast_ratio))
                    ev_id += 1
                    events.append(
                        GameplayEvent(
                            id=f"horror_jumpscare_{ev_id}",
                            game=self.profile.name,
                            event_type=EventType.JUMPSCARE.value,
                            start_time=max(0.0, pt - 4.0),  # include preceding tense silence
                            end_time=min(duration, pt + 4.0),    # include vocal scream / reaction
                            confidence=round(conf, 2),
                            status=EventStatus.CONFIRMED.value,
                            source_evidence={"audio": conf},
                            evidence_breakdown=EvidenceBreakdown(
                                audio=conf,
                                raw_signals={
                                    "peak_z": z,
                                    "peak_rms": round(peak_rms, 3),
                                    "mean_prior_rms": round(mean_prior, 3),
                                    "contrast_ratio": round(contrast_ratio, 2),
                                },
                            ),
                            metadata={
                                "subtype": "jumpscare",
                                "contrast_ratio": round(contrast_ratio, 2),
                                "climax_timestamp": pt,
                            },
                            explanation=f"Silence-to-scream jumpscare (contrast ratio: {contrast_ratio:.1f}x)",
                        )
                    )

        # ----------------------------------------------------------------------
        # 2. Panic Escape (Frantic speech + sustained high audio energy)
        # ----------------------------------------------------------------------
        panic_keywords = {
            "run", "hide", "it's here", "behind you", "hurry", "get out", "help",
            "door", "locked", "flashlight", "monster", "ghost", "screaming",
            "no no no", "darr", "phat", "got me", "dead", "died", "screamer"
        }

        panic_matches = [
            w for w in words
            if re.sub(r"[^a-zA-Z]", "", str(w.get("word", "")).lower()) in panic_keywords
        ]

        if panic_matches:
            panic_clusters: List[List[Dict[str, Any]]] = []
            for w in panic_matches:
                t = float(w.get("start", 0.0))
                if not panic_clusters or (t - panic_clusters[-1][-1].get("start", 0.0) > 5.0):
                    panic_clusters.append([w])
                else:
                    panic_clusters[-1].append(w)

            for p_cluster in panic_clusters:
                p_start = float(p_cluster[0].get("start", 0.0))
                p_end = float(p_cluster[-1].get("end", p_start + 2.0))
                p_words = [str(x.get("word", "")) for x in p_cluster]

                # Check sustained audio energy
                aligned_peaks = [
                    p for p in audio_peaks
                    if p_start - 2.0 <= float(p.get("timestamp", 0.0)) <= p_end + 3.0
                ]

                if aligned_peaks or len(p_cluster) >= 2:
                    conf = 0.88 if aligned_peaks else 0.78
                    ev_id += 1
                    events.append(
                        GameplayEvent(
                            id=f"horror_panic_{ev_id}",
                            game=self.profile.name,
                            event_type=EventType.PANIC_ESCAPE.value,
                            start_time=max(0.0, p_start - 3.0),
                            end_time=min(duration, p_end + 4.0),
                            confidence=conf,
                            status=EventStatus.CONFIRMED.value if conf >= 0.85 else EventStatus.CANDIDATE.value,
                            source_evidence={"transcript": conf, "audio": 0.85 if aligned_peaks else 0.50},
                            evidence_breakdown=EvidenceBreakdown(
                                transcript=conf,
                                audio=0.85 if aligned_peaks else 0.50,
                                raw_signals={"panic_words": p_words, "peaks_count": len(aligned_peaks)},
                            ),
                            metadata={"subtype": "panic_escape", "panic_words": p_words},
                            explanation=f"Frantic panic escape ({', '.join(p_words[:4])})",
                        )
                    )

        # Deduplicate overlapping events
        deduped: List[GameplayEvent] = []
        events.sort(key=lambda e: (e.start_time, e.end_time))
        for ev in events:
            if not deduped or (ev.start_time - deduped[-1].end_time >= 3.0):
                deduped.append(ev)
            elif ev.event_type == EventType.JUMPSCARE.value and deduped[-1].event_type != EventType.JUMPSCARE.value:
                # Replace weaker event with jumpscare
                deduped[-1] = ev

        return deduped
