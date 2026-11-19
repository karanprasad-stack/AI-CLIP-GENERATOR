"""Audio Event Engine: generates deterministic, synchronized SFX events from visual effects and gameplay signals."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from backend.app.config import (
    SFX_WHOOSH,
    SFX_MAJOR_IMPACT,
    SFX_MINOR_IMPACT,
    SFX_REACTION_ACCENT,
    SFX_TRANSITION,
    ALL_SFX_TYPES,
    WHOOSH_GAIN_DB,
    WHOOSH_STRONG_GAIN_DB,
    IMPACT_MAJOR_GAIN_DB,
    IMPACT_MINOR_GAIN_DB,
    REACTION_GAIN_DB,
    TRANSITION_GAIN_DB,
    MIN_SFX_GAP,
    MIN_IMPACT_GAP,
    MIN_WHOOSH_GAP,
    MIN_REACTION_GAP,
    MAX_SFX_PER_30_SECONDS,
    EFFECT_SUBTLE_ZOOM,
    EFFECT_PUNCH_ZOOM,
    EFFECT_IMPACT_ZOOM,
    EFFECT_MICRO_SHAKE,
    EFFECT_IMPACT_SHAKE,
    REACTION_PHRASES,
    REACTION_WORDS,
)
from backend.app.pipeline.sfx_library import SfxLibrary, SFX_ASSET_NAMES


@dataclass
class AudioEvent:
    """Represents a discrete sound effect placed on the audio timeline."""
    timestamp: float                    # Timestamp in seconds relative to candidate start
    event_type: str                     # From ALL_SFX_TYPES
    asset_name: str                     # Actual filename in assets/sfx/
    gain_db: float                      # Relative volume in dB
    intensity: float                    # 0.0 to 1.0
    confidence: float                   # 0.0 to 1.0
    source: str                         # "visual_effect", "gameplay_event", "reaction", "audio_peak"
    visual_effect: Optional[str] = None # Coinciding Phase 5 visual effect
    reason: str = ""                    # Auditable explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": round(self.timestamp, 3),
            "event_type": self.event_type,
            "asset_name": self.asset_name,
            "gain_db": round(self.gain_db, 2),
            "intensity": round(self.intensity, 3),
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "visual_effect": self.visual_effect,
            "reason": self.reason,
        }


@dataclass
class AudioTimeline:
    """Structured audio timeline containing SFX placements and ducking metadata."""
    candidate_id: int
    candidate_duration: float
    audio_events: List[AudioEvent] = field(default_factory=list)
    suppressed_events: List[Dict[str, Any]] = field(default_factory=list)
    ducking_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for ev in self.audio_events:
            counts[ev.event_type] = counts.get(ev.event_type, 0) + 1

        return {
            "candidate_id": self.candidate_id,
            "candidate_duration": round(self.candidate_duration, 3),
            "total_sfx": len(self.audio_events),
            "sfx_counts": counts,
            "audio_events": [e.to_dict() for e in self.audio_events],
            "suppressed_events": self.suppressed_events,
            "ducking": self.ducking_summary,
        }


class AudioEventEngine:
    """Derives context-aware, synchronized SFX events from visual effects and gameplay intelligence."""

    def __init__(
        self,
        sfx_library: Optional[SfxLibrary] = None,
        min_sfx_gap: float = MIN_SFX_GAP,
        min_impact_gap: float = MIN_IMPACT_GAP,
        min_whoosh_gap: float = MIN_WHOOSH_GAP,
        min_reaction_gap: float = MIN_REACTION_GAP,
        max_density_per_30s: int = MAX_SFX_PER_30_SECONDS,
    ):
        self.sfx_library = sfx_library or SfxLibrary()
        self.min_sfx_gap = min_sfx_gap
        self.min_impact_gap = min_impact_gap
        self.min_whoosh_gap = min_whoosh_gap
        self.min_reaction_gap = min_reaction_gap
        self.max_density_per_30s = max_density_per_30s

    def generate_raw_events(
        self,
        candidate: Dict[str, Any],
        phase5_timeline: Optional[Dict[str, Any]] = None,
        phase4_data: Optional[Dict[str, Any]] = None,
        audio_peaks: Optional[List[Dict[str, Any]]] = None,
        clip_duration: float = 60.0,
    ) -> List[AudioEvent]:
        """
        Creates raw candidate audio events by cross-referencing visual effects,
        gameplay climax signals, and vocal reactions.
        """
        raw_events: List[AudioEvent] = []
        clip_start = float(candidate.get("extraction_start", candidate.get("candidate_start", 0.0)))
        clip_end = float(candidate.get("extraction_end", candidate.get("candidate_end", 60.0)))

        # 1. Audiovisual Synchronization with Phase 5 Visual Effects
        p5_effects = []
        if phase5_timeline:
            p5_effects = phase5_timeline.get("effects", [])
        elif "timeline_data" in candidate:
            p5_effects = candidate["timeline_data"].get("effects", [])

        for v_eff in p5_effects:
            v_type = v_eff.get("type") or v_eff.get("effect_type", "")
            v_start = float(v_eff.get("start") if v_eff.get("start") is not None else v_eff.get("start_time", 0.0))
            v_intensity = float(v_eff.get("intensity", 0.7))
            v_conf = float(v_eff.get("confidence", 0.8))

            # A. Punch Zoom -> Whoosh
            if v_type == EFFECT_PUNCH_ZOOM:
                w_time = max(0.0, v_start - 0.06)
                gain = WHOOSH_STRONG_GAIN_DB if v_intensity >= 0.75 else WHOOSH_GAIN_DB
                asset = SFX_ASSET_NAMES["whoosh_strong"] if v_intensity >= 0.75 else SFX_ASSET_NAMES["whoosh_soft"]
                raw_events.append(
                    AudioEvent(
                        timestamp=w_time,
                        event_type=SFX_WHOOSH,
                        asset_name=asset,
                        gain_db=gain,
                        intensity=v_intensity,
                        confidence=v_conf,
                        source="visual_effect",
                        visual_effect=v_type,
                        reason=f"Coincides with {v_type} zoom accent",
                    )
                )

            # B. Impact Zoom -> Whoosh Strong + Major Impact
            elif v_type == EFFECT_IMPACT_ZOOM:
                w_time = max(0.0, v_start - 0.06)
                raw_events.append(
                    AudioEvent(
                        timestamp=w_time,
                        event_type=SFX_WHOOSH,
                        asset_name=SFX_ASSET_NAMES["whoosh_strong"],
                        gain_db=WHOOSH_STRONG_GAIN_DB,
                        intensity=v_intensity,
                        confidence=v_conf,
                        source="visual_effect",
                        visual_effect=v_type,
                        reason="Impact zoom high-energy whoosh",
                    )
                )
                raw_events.append(
                    AudioEvent(
                        timestamp=v_start,
                        event_type=SFX_MAJOR_IMPACT,
                        asset_name=SFX_ASSET_NAMES["impact_strong"],
                        gain_db=IMPACT_MAJOR_GAIN_DB,
                        intensity=v_intensity,
                        confidence=v_conf,
                        source="visual_effect",
                        visual_effect=v_type,
                        reason="Impact zoom bass hit",
                    )
                )

            # C. Impact Shake -> Impact SFX
            elif v_type == EFFECT_IMPACT_SHAKE:
                raw_events.append(
                    AudioEvent(
                        timestamp=v_start,
                        event_type=SFX_MAJOR_IMPACT,
                        asset_name=SFX_ASSET_NAMES["impact_strong"],
                        gain_db=IMPACT_MAJOR_GAIN_DB,
                        intensity=v_intensity,
                        confidence=v_conf,
                        source="visual_effect",
                        visual_effect=v_type,
                        reason="Impact shake bass hit",
                    )
                )

            # D. Subtle Zoom & Micro Shake -> NO WHOOSH / NO SFX (Per Section 5 rules)

        # 2. Gameplay Events (Combat Climaxes from Phase 2.1.1)
        signals = candidate.get("detected_signals", [])
        for sig_str in signals:
            import re
            m = re.search(r'(?:([^@:]+):)?([^@]+)@([\d\.]+)s?', sig_str)
            if not m:
                continue

            category = m.group(1) or "gameplay"
            word = m.group(2).strip().lower()
            t_glob = float(m.group(3))

            if clip_start <= t_glob <= clip_end:
                rel_t = max(0.0, min(clip_duration, t_glob - clip_start))

                # High-impact combat signals
                clean_word = re.sub(r'[^a-z0-9]', '', word)
                if any(w in clean_word for w in ["clutch", "ace", "headshot", "1v1", "eliminated"]):
                    raw_events.append(
                        AudioEvent(
                            timestamp=rel_t,
                            event_type=SFX_MAJOR_IMPACT,
                            asset_name=SFX_ASSET_NAMES["impact_strong"],
                            gain_db=IMPACT_MAJOR_GAIN_DB,
                            intensity=0.90,
                            confidence=0.88,
                            source="gameplay_event",
                            reason=f"Major gameplay climax: '{word}'",
                        )
                    )
                elif any(w in clean_word for w in ["kill", "fight", "shot", "weapon"]):
                    raw_events.append(
                        AudioEvent(
                            timestamp=rel_t,
                            event_type=SFX_MINOR_IMPACT,
                            asset_name=SFX_ASSET_NAMES["impact_medium"],
                            gain_db=IMPACT_MINOR_GAIN_DB,
                            intensity=0.68,
                            confidence=0.75,
                            source="gameplay_event",
                            reason=f"Combat action: '{word}'",
                        )
                    )

                # Viral Reaction Phrases
                elif "phrase" in category or any(p in word for p in REACTION_PHRASES):
                    raw_events.append(
                        AudioEvent(
                            timestamp=rel_t,
                            event_type=SFX_REACTION_ACCENT,
                            asset_name=SFX_ASSET_NAMES["pop"],
                            gain_db=REACTION_GAIN_DB,
                            intensity=0.70,
                            confidence=0.80,
                            source="reaction",
                            reason=f"Reaction phrase accent: '{word}'",
                        )
                    )

        return raw_events

    def resolve_cooldowns_and_conflicts(
        self,
        raw_events: List[AudioEvent],
        clip_duration: float,
    ) -> Tuple[List[AudioEvent], List[Dict[str, Any]]]:
        """
        Enforces cooldowns, eliminates duplicates, and caps maximum density
        so audio remains clean, punchy, and controlled.
        """
        if not raw_events:
            return [], []

        # Sort chronologically by timestamp, then by priority (major_impact > whoosh > minor_impact > reaction)
        type_priority = {
            SFX_MAJOR_IMPACT: 4,
            SFX_WHOOSH: 3,
            SFX_MINOR_IMPACT: 2,
            SFX_TRANSITION: 2,
            SFX_REACTION_ACCENT: 1,
        }

        # Filter out timestamps past clip duration
        valid_raw = [e for e in raw_events if 0.0 <= e.timestamp <= clip_duration]
        valid_raw.sort(key=lambda e: (e.timestamp, -type_priority.get(e.event_type, 0)))

        accepted: List[AudioEvent] = []
        suppressed: List[Dict[str, Any]] = []

        for candidate_ev in valid_raw:
            t = candidate_ev.timestamp
            ev_type = candidate_ev.event_type
            p_cand = type_priority.get(ev_type, 0)

            # Check conflict with existing accepted events
            conflict = False
            for prev in accepted:
                dt = abs(t - prev.timestamp)

                # Rule 1: Same event type cooldown
                if prev.event_type == ev_type and dt < self.min_sfx_gap:
                    conflict = True
                    break

                # Rule 2: Major impact cooldown
                if (prev.event_type == SFX_MAJOR_IMPACT or ev_type == SFX_MAJOR_IMPACT) and dt < self.min_impact_gap:
                    # Keep major_impact over minor_impact or duplicate major
                    if ev_type == SFX_MAJOR_IMPACT and prev.event_type != SFX_MAJOR_IMPACT:
                        # Replace previous weaker event
                        accepted.remove(prev)
                        suppressed.append({
                            "event_type": prev.event_type,
                            "timestamp": prev.timestamp,
                            "reason": f"Replaced by higher-priority {ev_type} at {t:.2f}s within impact gap",
                        })
                    else:
                        conflict = True
                        break

                # Rule 3: Whoosh cooldown
                if prev.event_type == SFX_WHOOSH and ev_type == SFX_WHOOSH and dt < self.min_whoosh_gap:
                    conflict = True
                    break

                # Rule 4: Reaction accent suppressed if major impact occurs within 0.8s
                if ev_type == SFX_REACTION_ACCENT and prev.event_type == SFX_MAJOR_IMPACT and dt < 0.8:
                    conflict = True
                    break
                if prev.event_type == SFX_REACTION_ACCENT and ev_type == SFX_MAJOR_IMPACT and dt < 0.8:
                    accepted.remove(prev)
                    suppressed.append({
                        "event_type": prev.event_type,
                        "timestamp": prev.timestamp,
                        "reason": f"Reaction accent removed due to coinciding major impact at {t:.2f}s",
                    })

            if not conflict:
                accepted.append(candidate_ev)
            else:
                suppressed.append({
                    "event_type": ev_type,
                    "timestamp": t,
                    "reason": f"Suppressed by cooldown/conflict policy near {t:.2f}s",
                })

        # Rule 5: Density Cap (scales naturally with clip duration)
        # e.g., max 6 per 30 seconds -> 12 for 60s, 36 for 180s
        max_allowed_sfx = max(3, int(round((clip_duration / 30.0) * self.max_density_per_30s)))
        if len(accepted) > max_allowed_sfx:
            # Sort by intensity * confidence descending, keep top N
            accepted.sort(key=lambda e: e.intensity * e.confidence, reverse=True)
            for dropped in accepted[max_allowed_sfx:]:
                suppressed.append({
                    "event_type": dropped.event_type,
                    "timestamp": dropped.timestamp,
                    "reason": f"Dropped due to density cap ({len(accepted)} > max {max_allowed_sfx})",
                })
            accepted = accepted[:max_allowed_sfx]

        # Final chronological sort
        accepted.sort(key=lambda e: e.timestamp)
        return accepted, suppressed

    def generate_timeline(
        self,
        candidate_id: int,
        candidate: Dict[str, Any],
        phase5_timeline: Optional[Dict[str, Any]] = None,
        phase4_data: Optional[Dict[str, Any]] = None,
        audio_peaks: Optional[List[Dict[str, Any]]] = None,
        ducking_summary: Optional[Dict[str, Any]] = None,
    ) -> AudioTimeline:
        """
        End-to-end audio event generation producing the structured AudioTimeline.
        """
        clip_start = float(candidate.get("extraction_start", candidate.get("candidate_start", 0.0)))
        clip_end = float(candidate.get("extraction_end", candidate.get("candidate_end", 60.0)))
        clip_duration = float(candidate.get("extraction_duration", clip_end - clip_start))

        # 1. Generate raw candidate events
        raw_events = self.generate_raw_events(
            candidate=candidate,
            phase5_timeline=phase5_timeline,
            phase4_data=phase4_data,
            audio_peaks=audio_peaks,
            clip_duration=clip_duration,
        )

        # 2. Enforce cooldowns, priorities, and anti-spam limits
        final_events, suppressed = self.resolve_cooldowns_and_conflicts(
            raw_events=raw_events,
            clip_duration=clip_duration,
        )

        return AudioTimeline(
            candidate_id=candidate_id,
            candidate_duration=clip_duration,
            audio_events=final_events,
            suppressed_events=suppressed,
            ducking_summary=ducking_summary or {},
        )

    def build_audio_timeline(
        self,
        candidate: Dict[str, Any],
        effect_timeline: Optional[Dict[str, Any]] = None,
        gameplay_signals: Optional[List[str]] = None,
        transcript_data: Optional[Dict[str, Any]] = None,
        ducking_summary: Optional[Dict[str, Any]] = None,
        audio_peaks: Optional[List[Dict[str, Any]]] = None,
    ) -> AudioTimeline:
        """Helper alias for generate_timeline supporting direct candidate testing."""
        cand_id = candidate.get("candidate_id", 1)
        phase4_data = {"gameplay_signals": gameplay_signals} if gameplay_signals else None
        return self.generate_timeline(
            candidate_id=cand_id,
            candidate=candidate,
            phase5_timeline=effect_timeline,
            phase4_data=phase4_data,
            audio_peaks=audio_peaks,
            ducking_summary=ducking_summary,
        )

    def write_timeline_file(self, output_path: Path, timeline: AudioTimeline) -> Path:
        """Writes the AudioTimeline to a JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(timeline.to_dict(), f, indent=2, ensure_ascii=False)
        return output_path
