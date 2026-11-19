"""Story, Open-World & RPG event detector: comedic moments, narrative twists, chaos bursts, boss climaxes."""

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


class StoryDetector:
    """Detects narrative climaxes, comedy/fails, open-world chaos, and boss fights."""

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
        if audio_analysis:
            audio_peaks = audio_analysis.get("rms_peaks", audio_analysis.get("peaks", []))
            audio_timeline = audio_analysis.get("timeline", [])

        # ----------------------------------------------------------------------
        # 1. Comedic Moments (Laughter, absurd fails, hilarious glitches)
        # ----------------------------------------------------------------------
        comedy_keywords = {
            "haha", "hahaha", "lmao", "lol", "bruh", "fail", "glitch", "wasted",
            "busted", "dead", "ded", "funny", "timing", "kya", "bhai", "bro what",
            "no way", "what the hell", "are you serious", "comedy", "hilarious"
        }

        comedy_matches: List[Dict[str, Any]] = []
        for w in words:
            cleaned = re.sub(r"[^a-zA-Z]", "", str(w.get("word", "")).lower())
            if cleaned in comedy_keywords:
                t = float(w.get("start", 0.0))
                comedy_matches.append({"time": t, "word": cleaned})

        # Cluster comedy matches within 4.0s
        if comedy_matches:
            comedy_clusters: List[List[Dict[str, Any]]] = []
            for m in comedy_matches:
                if not comedy_clusters or (m["time"] - comedy_clusters[-1][-1]["time"] > 4.0):
                    comedy_clusters.append([m])
                else:
                    comedy_clusters[-1].append(m)

            for cluster in comedy_clusters:
                c_start = cluster[0]["time"]
                c_end = cluster[-1]["time"] + 1.5
                c_words = [x["word"] for x in cluster]

                # Check if aligned with an audio surge / laughter volume
                aligned_peak = any(abs(float(p.get("timestamp", 0.0)) - c_start) <= 3.0 for p in audio_peaks)
                conf = 0.90 if (aligned_peak or len(cluster) >= 2) else 0.78

                ev_id += 1
                events.append(
                    GameplayEvent(
                        id=f"story_comedy_{ev_id}",
                        game=self.profile.name,
                        event_type=EventType.COMEDIC_MOMENT.value,
                        start_time=max(0.0, c_start - 2.0),
                        end_time=min(duration, c_end + 3.0),
                        confidence=conf,
                        status=EventStatus.CONFIRMED.value if conf >= 0.85 else EventStatus.CANDIDATE.value,
                        source_evidence={"transcript": conf, "audio": 0.85 if aligned_peak else 0.50},
                        evidence_breakdown=EvidenceBreakdown(
                            transcript=conf,
                            audio=0.85 if aligned_peak else 0.50,
                            raw_signals={"words": c_words, "aligned_peak": aligned_peak},
                        ),
                        metadata={"subtype": "comedy", "keywords": c_words},
                        explanation=f"Comedic reaction/fail burst ({', '.join(c_words[:4])})",
                    )
                )

        # ----------------------------------------------------------------------
        # 2. Story Climax (Dramatic dialogue reveals, plot twists, cutscene peaks)
        # ----------------------------------------------------------------------
        story_keywords = {
            "reveal", "betray", "betrayal", "plot", "secret", "truth", "ending", "endgame",
            "save", "who are you", "why did you", "goodbye", "kill him", "died",
            "promise", "listen to me", "wait wait", "chills", "unbelievable",
            "heist", "dialogue", "choice", "mission passed"
        }

        story_matches = [
            w for w in words
            if re.sub(r"[^a-zA-Z]", "", str(w.get("word", "")).lower()) in story_keywords
        ]

        if story_matches:
            story_clusters: List[List[Dict[str, Any]]] = []
            for w in story_matches:
                t = float(w.get("start", 0.0))
                if not story_clusters or (t - story_clusters[-1][-1].get("start", 0.0) > 6.0):
                    story_clusters.append([w])
                else:
                    story_clusters[-1].append(w)

            for s_cluster in story_clusters:
                s_start = float(s_cluster[0].get("start", 0.0))
                s_end = float(s_cluster[-1].get("end", s_start + 2.0))
                s_words = [str(x.get("word", "")) for x in s_cluster]

                # Check audio peak nearby
                nearby_peak = any(abs(float(p.get("timestamp", 0.0)) - s_start) <= 4.0 for p in audio_peaks)
                conf = 0.92 if nearby_peak else 0.82

                ev_id += 1
                events.append(
                    GameplayEvent(
                        id=f"story_climax_{ev_id}",
                        game=self.profile.name,
                        event_type=EventType.STORY_CLIMAX.value,
                        start_time=max(0.0, s_start - 3.0),
                        end_time=min(duration, s_end + 4.0),
                        confidence=conf,
                        status=EventStatus.CONFIRMED.value,
                        source_evidence={"transcript": conf, "audio": 0.85 if nearby_peak else 0.60},
                        evidence_breakdown=EvidenceBreakdown(
                            transcript=conf,
                            audio=0.85 if nearby_peak else 0.60,
                            raw_signals={"dialogue_cues": s_words},
                        ),
                        metadata={"subtype": "story_climax", "dialogue_cues": s_words},
                        explanation=f"Narrative climax dialogue moment ({', '.join(s_words)})",
                    )
                )

        # ----------------------------------------------------------------------
        # 3. Boss Fight Climax (Encounter, phase 2, triumph, defeat)
        # ----------------------------------------------------------------------
        boss_keywords = {
            "boss", "phase", "defeat", "victory", "died", "slain", "fell",
            "dragon", "god", "beast", "parry", "dodge", "flawless"
        }

        for w in words:
            cleaned = re.sub(r"[^a-zA-Z]", "", str(w.get("word", "")).lower())
            if cleaned in boss_keywords:
                t = float(w.get("start", 0.0))
                # Check for accompanying audio peak
                for p in audio_peaks:
                    p_t = float(p.get("timestamp", 0.0))
                    if abs(p_t - t) <= 3.0:
                        ev_id += 1
                        events.append(
                            GameplayEvent(
                                id=f"story_boss_{ev_id}",
                                game=self.profile.name,
                                event_type=EventType.BOSS_FIGHT_CLIMAX.value,
                                start_time=max(0.0, min(t, p_t) - 4.0),
                                end_time=min(duration, max(t, p_t) + 5.0),
                                confidence=0.91,
                                status=EventStatus.CONFIRMED.value,
                                source_evidence={"transcript": 0.90, "audio": 0.92},
                                evidence_breakdown=EvidenceBreakdown(
                                    transcript=0.90,
                                    audio=0.92,
                                    raw_signals={"keyword": cleaned, "peak_z": float(p.get("z_score", 2.0))},
                                ),
                                metadata={"subtype": "boss_fight", "keyword": cleaned},
                                explanation=f"Boss fight climax ({cleaned}) with aligned audio peak",
                            )
                        )
                        break

        # ----------------------------------------------------------------------
        # 4. Chaos Burst (Action, chase, explosions, ragdoll motion)
        # ----------------------------------------------------------------------
        chaos_events = self._detect_chaos_bursts(
            video_path=video_path,
            audio_peaks=audio_peaks,
            words=words,
            duration=duration,
        )
        for ce in chaos_events:
            ev_id += 1
            ce.id = f"story_chaos_{ev_id}"
            ce.game = self.profile.name
            events.append(ce)

        events.sort(key=lambda e: (e.start_time, e.end_time))
        return events

    def _detect_chaos_bursts(
        self,
        video_path: Optional[Path],
        audio_peaks: List[Dict[str, Any]],
        words: List[Dict[str, Any]],
        duration: float,
    ) -> List[GameplayEvent]:
        """Detects visual motion bursts corroborated by audio peaks, with audio-only fallback."""
        chaos_events: List[GameplayEvent] = []

        # Try fast OpenCV motion diff if video_path exists and is readable
        visual_motion_times: List[float] = []
        if cv2 and video_path and video_path.exists():
            try:
                cap = cv2.VideoCapture(str(video_path))
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                step_frames = max(1, int(fps * 0.5))  # 2 FPS sample
                prev_gray = None
                frame_idx = 0

                while cap.isOpened() and (frame_idx / fps) <= duration:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if frame_idx % step_frames == 0:
                        small = cv2.resize(frame, (160, 90))
                        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                        if prev_gray is not None:
                            diff = cv2.absdiff(prev_gray, gray)
                            motion_val = float(np.mean(diff) / 255.0)
                            if motion_val >= 0.14:  # significant visual motion delta
                                visual_motion_times.append(frame_idx / fps)
                        prev_gray = gray
                    frame_idx += 1
                cap.release()
            except Exception:
                visual_motion_times = []

        action_words = {
            "cops", "police", "wanted", "chase", "crash", "explosion", "flying",
            "car", "tank", "helicopter", "speed", "run", "omg", "holy", "jump"
        }

        # Check visual motion aligned with audio peaks
        if visual_motion_times:
            for mt in visual_motion_times:
                for p in audio_peaks:
                    pt = float(p.get("timestamp", 0.0))
                    if abs(pt - mt) <= 2.0:
                        chaos_events.append(
                            GameplayEvent(
                                id="chaos_pending",
                                game=self.profile.name,
                                event_type=EventType.CHAOS_BURST.value,
                                start_time=max(0.0, min(mt, pt) - 2.5),
                                end_time=min(duration, max(mt, pt) + 3.5),
                                confidence=0.88,
                                status=EventStatus.CONFIRMED.value,
                                source_evidence={"visual": 0.85, "audio": 0.88},
                                evidence_breakdown=EvidenceBreakdown(visual=0.85, audio=0.88),
                                metadata={"subtype": "motion_audio_chaos"},
                                explanation="High visual motion burst aligned with audio surge",
                            )
                        )
                        break

        # Fallback to action words + strong audio peak if no visual motion detected
        if not chaos_events and audio_peaks:
            for p in audio_peaks:
                pt = float(p.get("timestamp", 0.0))
                z = float(p.get("z_score", 1.0))
                if z >= 2.2:
                    nearby_action_words = [
                        str(w.get("word", "")).lower()
                        for w in words
                        if abs(float(w.get("start", 0.0)) - pt) <= 3.0
                        and re.sub(r"[^a-zA-Z]", "", str(w.get("word", "")).lower()) in action_words
                    ]
                    if nearby_action_words:
                        chaos_events.append(
                            GameplayEvent(
                                id="chaos_pending",
                                game=self.profile.name,
                                event_type=EventType.CHAOS_BURST.value,
                                start_time=max(0.0, pt - 2.5),
                                end_time=min(duration, pt + 3.5),
                                confidence=0.82,
                                status=EventStatus.CONFIRMED.value,
                                source_evidence={"transcript": 0.80, "audio": 0.85},
                                evidence_breakdown=EvidenceBreakdown(transcript=0.80, audio=0.85),
                                metadata={"subtype": "audio_lexical_chaos", "words": nearby_action_words},
                                explanation=f"Open-world chaos action surge ({', '.join(nearby_action_words)})",
                            )
                        )

        # Deduplicate chaos events within 4.0s
        deduped: List[GameplayEvent] = []
        for ce in chaos_events:
            if not deduped or (ce.start_time - deduped[-1].end_time >= 4.0):
                deduped.append(ce)

        return deduped
