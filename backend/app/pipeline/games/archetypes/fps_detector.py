"""Competitive FPS event detector: kills, headshots, multi-kills, and clutches for non-Valorant shooters."""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional

from backend.app.pipeline.games.models import (
    GameplayEvent,
    EventType,
    EventStatus,
    EvidenceBreakdown,
)
from backend.app.pipeline.games.profiles.base import BaseGameProfile


class FPSDetector:
    """Detects combat kills, headshots, clutches, and squad wipes for general competitive shooters."""

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

        # Extract audio peaks
        audio_peaks: List[Dict[str, Any]] = []
        if audio_analysis:
            audio_peaks = audio_analysis.get("rms_peaks", audio_analysis.get("peaks", []))

        combat_keywords = {
            "kill", "killed", "headshot", "clutch", "ace", "multi kill", "multikill",
            "knocked", "knock", "downed", "wipe", "squad wipe", "team wipe", "sniper",
            "one tap", "one shot", "dead", "beamed", "cracked", "fried"
        }

        # Track combat matches
        combat_matches: List[Dict[str, Any]] = []
        for w in words:
            cleaned = re.sub(r"[^a-zA-Z]", "", str(w.get("word", "")).lower())
            if cleaned in combat_keywords:
                combat_matches.append({
                    "word": cleaned,
                    "time": float(w.get("start", 0.0)),
                })

        # Generate events for combat moments aligned with audio peaks
        for m in combat_matches:
            mt = m["time"]
            m_word = m["word"]

            # Corroborate with nearest audio peak
            aligned_peak = None
            for p in audio_peaks:
                pt = float(p.get("timestamp", 0.0))
                if abs(pt - mt) <= 2.5:
                    aligned_peak = p
                    break

            ev_type = EventType.KILL.value
            is_hs = False
            if m_word in ["headshot", "onetap"]:
                ev_type = EventType.HEADSHOT.value
                is_hs = True
            elif m_word in ["clutch"]:
                ev_type = EventType.CLUTCH_CANDIDATE.value
            elif m_word in ["ace"]:
                ev_type = EventType.ACE_CANDIDATE.value
            elif m_word in ["wipe", "squad wipe", "team wipe", "multikill", "multi kill"]:
                ev_type = EventType.MULTI_KILL.value

            conf = 0.88 if aligned_peak else 0.72
            ev_id += 1
            events.append(
                GameplayEvent(
                    id=f"fps_{ev_id}",
                    game=self.profile.name,
                    event_type=ev_type,
                    start_time=max(0.0, mt - 2.0),
                    end_time=min(duration, mt + 3.0),
                    confidence=conf,
                    status=EventStatus.CONFIRMED.value if conf >= 0.85 else EventStatus.CANDIDATE.value,
                    source_evidence={"transcript": conf, "audio": 0.85 if aligned_peak else 0.40},
                    evidence_breakdown=EvidenceBreakdown(
                        transcript=conf,
                        audio=0.85 if aligned_peak else 0.40,
                        raw_signals={"callout": m_word},
                    ),
                    metadata={"subtype": m_word, "headshot": is_hs},
                    explanation=f"FPS combat engagement ({m_word})",
                )
            )

        events.sort(key=lambda e: (e.start_time, e.end_time))
        return events
