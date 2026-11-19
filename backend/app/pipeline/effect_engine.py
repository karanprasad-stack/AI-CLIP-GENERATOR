"""Context-Aware Visual Effects Engine: impact scoring, event clustering, cooldowns, and timeline generation."""

import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from backend.app.config import (
    EFFECT_SUBTLE_ZOOM,
    EFFECT_PUNCH_ZOOM,
    EFFECT_IMPACT_ZOOM,
    EFFECT_MICRO_SHAKE,
    EFFECT_IMPACT_SHAKE,
    EFFECT_EMPHASIS_FLASH,
    ALL_EFFECT_TYPES,
    SUBTLE_ZOOM_SCALE,
    SUBTLE_ZOOM_DURATION,
    PUNCH_ZOOM_SCALE,
    PUNCH_ZOOM_DURATION,
    IMPACT_ZOOM_SCALE,
    IMPACT_ZOOM_DURATION,
    MICRO_SHAKE_DURATION,
    IMPACT_SHAKE_DURATION,
    FLASH_DURATION,
    MIN_ZOOM_GAP,
    MIN_SHAKE_GAP,
    MIN_FLASH_GAP,
    IMPACT_ZOOM_CONFIDENCE_THRESHOLD,
    IMPACT_ZOOM_SCORE_THRESHOLD,
    PUNCH_ZOOM_CONFIDENCE_THRESHOLD,
    PUNCH_ZOOM_SCORE_THRESHOLD,
    SUBTLE_ZOOM_CONFIDENCE_THRESHOLD,
    SUBTLE_ZOOM_SCORE_THRESHOLD,
    IMPACT_SHAKE_SCORE_THRESHOLD,
    MICRO_SHAKE_SCORE_THRESHOLD,
    FLASH_SCORE_THRESHOLD,
    HIGH_IMPACT_GAMING_WORDS,
    REACTION_PHRASES,
    REACTION_WORDS,
    LAUGHTER_WORDS,
)


@dataclass
class EffectEvent:
    """Represents a discrete visual effect placed on the video timeline."""
    type: str                                    # Effect type from ALL_EFFECT_TYPES
    start: float                                 # Start timestamp (seconds, relative to clip)
    end: float                                   # End timestamp (seconds, relative to clip)
    intensity: float                             # Normalized intensity (0.0 to 1.0)
    confidence: float                            # Event confidence (0.0 to 1.0)
    reason: str                                  # Explainable audit justification
    source_events: List[str]                     # Signal types that contributed
    impact_breakdown: Optional[Dict[str, float]] = None
    focal_point: Optional[Tuple[float, float]] = None  # (focal_x, focal_y)

    def duration(self) -> float:
        return max(0.01, self.end - self.start)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "type": self.type,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration(), 3),
            "intensity": round(self.intensity, 3),
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "source_events": self.source_events,
        }
        if self.impact_breakdown:
            data["impact_breakdown"] = self.impact_breakdown
        if self.focal_point:
            data["focal_point"] = [round(self.focal_point[0], 2), round(self.focal_point[1], 2)]
        return data


@dataclass
class EffectTimeline:
    """Complete structured timeline for candidate video rendering."""
    candidate_id: int
    candidate_duration: float
    effects: List[EffectEvent] = field(default_factory=list)
    suppressed_events: List[Dict[str, Any]] = field(default_factory=list)
    impact_scores: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for eff in self.effects:
            counts[eff.type] = counts.get(eff.type, 0) + 1

        return {
            "candidate_id": self.candidate_id,
            "candidate_duration": round(self.candidate_duration, 3),
            "total_effects": len(self.effects),
            "effect_counts": counts,
            "effects": [e.to_dict() for e in self.effects],
            "suppressed_events": self.suppressed_events,
            "impact_scores": self.impact_scores,
        }


class EffectEngine:
    """Identifies climax moments, computes transparent impact scores, and builds effect timelines."""

    def __init__(
        self,
        min_zoom_gap: float = MIN_ZOOM_GAP,
        min_shake_gap: float = MIN_SHAKE_GAP,
        min_flash_gap: float = MIN_FLASH_GAP,
        impact_zoom_threshold: float = IMPACT_ZOOM_SCORE_THRESHOLD,
        impact_zoom_conf: float = IMPACT_ZOOM_CONFIDENCE_THRESHOLD,
        punch_zoom_threshold: float = PUNCH_ZOOM_SCORE_THRESHOLD,
        punch_zoom_conf: float = PUNCH_ZOOM_CONFIDENCE_THRESHOLD,
        subtle_zoom_threshold: float = SUBTLE_ZOOM_SCORE_THRESHOLD,
        subtle_zoom_conf: float = SUBTLE_ZOOM_CONFIDENCE_THRESHOLD,
        impact_shake_threshold: float = IMPACT_SHAKE_SCORE_THRESHOLD,
        micro_shake_threshold: float = MICRO_SHAKE_SCORE_THRESHOLD,
        flash_threshold: float = FLASH_SCORE_THRESHOLD,
    ):
        self.min_zoom_gap = min_zoom_gap
        self.min_shake_gap = min_shake_gap
        self.min_flash_gap = min_flash_gap
        self.impact_zoom_threshold = impact_zoom_threshold
        self.impact_zoom_conf = impact_zoom_conf
        self.punch_zoom_threshold = punch_zoom_threshold
        self.punch_zoom_conf = punch_zoom_conf
        self.subtle_zoom_threshold = subtle_zoom_threshold
        self.subtle_zoom_conf = subtle_zoom_conf
        self.impact_shake_threshold = impact_shake_threshold
        self.micro_shake_threshold = micro_shake_threshold
        self.flash_threshold = flash_threshold

    def calculate_impact(
        self,
        gameplay_signals: List[Dict[str, Any]],
        audio_peaks: List[Dict[str, Any]],
        reaction_signals: List[Dict[str, Any]],
        anchor_timestamp: float,
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        Computes the normalized EffectImpact (0.0 to 1.0) and overall event confidence.
        EffectImpact = 0.30*gameplay + 0.25*audio + 0.25*reaction + 0.20*alignment
        """
        # 1. Gameplay impact component (0.0 to 1.0)
        gameplay_score = 0.0
        if gameplay_signals:
            for s in gameplay_signals:
                text = str(s.get("signal", "")).lower()
                clean = re.sub(r'[^a-z0-9]', '', text)
                if any(w in clean for w in ["clutch", "ace", "headshot", "1v1", "1v2", "eliminated"]):
                    gameplay_score = max(gameplay_score, 0.95)
                elif any(w in clean for w in ["kill", "fight", "weapon", "shoot", "shot"]):
                    gameplay_score = max(gameplay_score, 0.85)
                elif any(w in clean for w in ["fail", "timing", "flash", "defuse"]):
                    gameplay_score = max(gameplay_score, 0.75)
                else:
                    gameplay_score = max(gameplay_score, 0.60)
        else:
            gameplay_score = 0.20

        # 2. Audio impact component (0.0 to 1.0)
        audio_score = 0.20
        if audio_peaks:
            for p in audio_peaks:
                z = float(p.get("z_score", p.get("z", 1.0)))
                if z >= 2.5:
                    audio_score = max(audio_score, 0.95)
                elif z >= 2.0:
                    audio_score = max(audio_score, 0.85)
                elif z >= 1.5:
                    audio_score = max(audio_score, 0.70)
                else:
                    audio_score = max(audio_score, 0.50)

        # 3. Reaction impact component (0.0 to 1.0)
        reaction_score = 0.20
        if reaction_signals:
            for r in reaction_signals:
                r_type = r.get("type", "")
                r_text = str(r.get("text", "")).lower()
                if r_type == "phrase" or any(p in r_text for p in REACTION_PHRASES):
                    reaction_score = max(reaction_score, 0.95)
                elif any(w in r_text for w in ["wow", "insane", "crazy", "omg", "whoa"]):
                    reaction_score = max(reaction_score, 0.85)
                elif r_type == "laughter" or any(w in r_text for w in LAUGHTER_WORDS):
                    reaction_score = max(reaction_score, 0.78)
                else:
                    reaction_score = max(reaction_score, 0.65)

        # 4. Temporal alignment component (0.0 to 1.0)
        all_times: List[float] = []
        for s in gameplay_signals:
            all_times.append(float(s.get("time", anchor_timestamp)))
        for p in audio_peaks:
            all_times.append(float(p.get("time", anchor_timestamp)))
        for r in reaction_signals:
            all_times.append(float(r.get("time", anchor_timestamp)))

        if len(all_times) > 1:
            max_delta = max(all_times) - min(all_times)
            if max_delta <= 0.6:
                alignment_score = 1.0
            elif max_delta <= 1.2:
                alignment_score = 0.85
            elif max_delta <= 2.0:
                alignment_score = 0.70
            else:
                alignment_score = 0.45
        else:
            alignment_score = 0.50

        # Weighted combination
        impact_score = (
            0.30 * gameplay_score +
            0.25 * audio_score +
            0.25 * reaction_score +
            0.20 * alignment_score
        )
        impact_score = round(min(1.0, max(0.0, impact_score)), 3)

        # Confidence calculation based on multi-signal convergence
        signals_present = sum([
            1 if gameplay_signals else 0,
            1 if audio_peaks else 0,
            1 if reaction_signals else 0,
        ])

        if signals_present >= 3:
            confidence = min(1.0, 0.88 + 0.10 * alignment_score)
        elif signals_present == 2:
            confidence = min(1.0, 0.75 + 0.10 * alignment_score)
        else:
            confidence = 0.60

        confidence = round(confidence, 3)

        breakdown = {
            "gameplay": round(gameplay_score, 2),
            "audio": round(audio_score, 2),
            "reaction": round(reaction_score, 2),
            "alignment": round(alignment_score, 2),
            "impact_score": impact_score,
        }

        return impact_score, confidence, breakdown

    def cluster_events(
        self,
        candidate: Dict[str, Any],
        phase4_data: Optional[Dict[str, Any]] = None,
        audio_peaks: Optional[List[Dict[str, Any]]] = None,
        clip_start: float = 0.0,
        clip_end: float = 60.0,
        clip_duration: float = 60.0,
        cluster_window: float = 2.0,
    ) -> List[Dict[str, Any]]:
        """
        Gathers signals from Phase 2.1.1, Phase 4 emojis/captions, and audio peaks,
        converting global timestamps to candidate-relative timestamps and clustering
        correlated events into discrete impact moments.
        """
        raw_signals: List[Dict[str, Any]] = []

        # 1. Signals from candidate metadata (detected_signals or gameplay_breakdown)
        signals_list = candidate.get("detected_signals", [])
        for sig_str in signals_list:
            # Pattern: type:word@timestamp or word@timestamp
            m = re.search(r'(?:([^@:]+):)?([^@]+)@([\d\.]+)s?', sig_str)
            if m:
                category_hint = m.group(1) or "gameplay"
                sig_word = m.group(2).strip()
                t_global = float(m.group(3))
                if clip_start <= t_global <= clip_end:
                    rel_t = max(0.0, min(clip_duration, t_global - clip_start))
                    is_reaction = ("phrase" in category_hint or "word" in category_hint or
                                   sig_word in REACTION_WORDS or any(p in sig_word for p in REACTION_PHRASES))
                    is_audio = "audio" in category_hint or "peak" in sig_word
                    raw_signals.append({
                        "kind": "reaction" if is_reaction else ("audio" if is_audio else "gameplay"),
                        "signal": sig_word,
                        "time": rel_t,
                        "global_time": t_global,
                    })

        # 2. Audio peaks
        if audio_peaks:
            for p in audio_peaks:
                t_glob = float(p.get("timestamp", 0.0))
                if clip_start <= t_glob <= clip_end:
                    rel_t = max(0.0, min(clip_duration, t_glob - clip_start))
                    raw_signals.append({
                        "kind": "audio",
                        "signal": f"peak_z={p.get('z_score', 2.0)}",
                        "time": rel_t,
                        "global_time": t_glob,
                        "z_score": float(p.get("z_score", 2.0)),
                    })

        # 3. Phase 4 Emojis (already relative or converted)
        emojis_detected = (phase4_data.get("emojis_detected", []) if phase4_data
                           else candidate.get("emojis_detected", []))
        for em in emojis_detected:
            e_time = float(em.get("start", 0.0))
            if 0.0 <= e_time <= clip_duration:
                raw_signals.append({
                    "kind": "reaction",
                    "signal": f"emoji:{em.get('emoji', '')}",
                    "time": e_time,
                    "global_time": clip_start + e_time,
                    "confidence": float(em.get("confidence", 0.8)),
                })

        # 4. Phase 12A/12B Confirmed Gameplay Events
        gameplay_events = candidate.get("gameplay_events", [])
        for ev in gameplay_events:
            ev_dict = ev if isinstance(ev, dict) else (ev.to_dict() if hasattr(ev, "to_dict") else vars(ev))
            if ev_dict.get("status") == "supporting":
                continue
            ev_t = float(ev_dict.get("timestamp", 0.0))
            if clip_start <= ev_t <= clip_end:
                rel_t = max(0.0, min(clip_duration, ev_t - clip_start))
                raw_signals.append({
                    "kind": "gameplay",
                    "signal": str(ev_dict.get("event_type", "gameplay_event")),
                    "time": rel_t,
                    "global_time": ev_t,
                    "confidence": float(ev_dict.get("confidence", 0.85)),
                })

        if not raw_signals:
            return []

        # Sort chronologically by relative timestamp
        raw_signals.sort(key=lambda s: s["time"])

        # Cluster temporally within cluster_window
        clusters: List[List[Dict[str, Any]]] = []
        for s in raw_signals:
            if not clusters:
                clusters.append([s])
            else:
                last_cluster = clusters[-1]
                if (s["time"] - last_cluster[0]["time"]) <= cluster_window:
                    last_cluster.append(s)
                else:
                    clusters.append([s])

        # Convert each cluster into an impact moment
        moments: List[Dict[str, Any]] = []
        for cl in clusters:
            gp = [x for x in cl if x["kind"] == "gameplay"]
            ap = [x for x in cl if x["kind"] == "audio"]
            rx = [x for x in cl if x["kind"] == "reaction"]

            # Anchor timestamp prioritizes audio peak or center of action
            if ap:
                anchor_t = ap[0]["time"]
            elif gp:
                anchor_t = gp[0]["time"]
            else:
                anchor_t = cl[0]["time"]

            impact_score, confidence, breakdown = self.calculate_impact(
                gameplay_signals=gp,
                audio_peaks=ap,
                reaction_signals=rx,
                anchor_timestamp=anchor_t,
            )

            moments.append({
                "anchor_time": round(anchor_t, 3),
                "impact_score": impact_score,
                "confidence": confidence,
                "breakdown": breakdown,
                "gameplay_signals": gp,
                "audio_signals": ap,
                "reaction_signals": rx,
                "signal_count": len(cl),
            })

        return moments

    def generate_raw_effects(
        self,
        moments: List[Dict[str, Any]],
        clip_duration: float,
        facecam_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[EffectEvent], List[Dict[str, Any]]]:
        """
        Translates impact moments into candidate effect events (zooms, shakes, flashes)
        prioritizing high-impact gameplay climaxes.
        """
        raw_effects: List[EffectEvent] = []
        suppressed_events: List[Dict[str, Any]] = []

        # Determine smart focal point if facecam is present
        # In facecam layout (top 35% is facecam, bottom 65% is gameplay), focus on gameplay (y ~ 0.65)
        has_facecam = facecam_info and facecam_info.get("facecam_detected", False)
        focal_point = (0.50, 0.65) if has_facecam else (0.50, 0.50)

        for m in moments:
            t = m["anchor_time"]
            score = m["impact_score"]
            conf = m["confidence"]
            breakdown = m["breakdown"]

            source_names = []
            if m["gameplay_signals"]:
                source_names.append("gameplay_event")
            if m["audio_signals"]:
                source_names.append("audio_peak")
            if m["reaction_signals"]:
                source_names.append("reaction")

            reason_str = " + ".join(source_names) or "impact_climax"

            # 1. Very High Impact Climax: Impact Zoom + Impact Shake (+ Optional Flash)
            if score >= self.impact_zoom_threshold and conf >= self.impact_zoom_conf:
                dur_z = IMPACT_ZOOM_DURATION
                dur_s = IMPACT_SHAKE_DURATION
                z_start = max(0.0, t - dur_z * 0.3)
                z_end = min(clip_duration, z_start + dur_z)

                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_IMPACT_ZOOM,
                        start=z_start,
                        end=z_end,
                        intensity=round(score, 2),
                        confidence=conf,
                        reason=reason_str,
                        source_events=source_names,
                        impact_breakdown=breakdown,
                        focal_point=focal_point,
                    )
                )

                s_start = max(0.0, t - dur_s * 0.2)
                s_end = min(clip_duration, s_start + dur_s)
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_IMPACT_SHAKE,
                        start=s_start,
                        end=s_end,
                        intensity=round(score, 2),
                        confidence=conf,
                        reason=f"{reason_str} (impact_shake)",
                        source_events=source_names,
                        impact_breakdown=breakdown,
                    )
                )

                if score >= self.flash_threshold:
                    f_start = max(0.0, t - FLASH_DURATION * 0.2)
                    f_end = min(clip_duration, f_start + FLASH_DURATION)
                    raw_effects.append(
                        EffectEvent(
                            type=EFFECT_EMPHASIS_FLASH,
                            start=f_start,
                            end=f_end,
                            intensity=0.85,
                            confidence=conf,
                            reason=f"{reason_str} (flash_accent)",
                            source_events=source_names,
                            impact_breakdown=breakdown,
                        )
                    )

            # 2. Strong Gaming Moment: Punch Zoom + Micro Shake
            elif score >= self.punch_zoom_threshold and conf >= self.punch_zoom_conf:
                dur_z = PUNCH_ZOOM_DURATION
                dur_s = MICRO_SHAKE_DURATION
                z_start = max(0.0, t - dur_z * 0.35)
                z_end = min(clip_duration, z_start + dur_z)

                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_PUNCH_ZOOM,
                        start=z_start,
                        end=z_end,
                        intensity=round(score, 2),
                        confidence=conf,
                        reason=reason_str,
                        source_events=source_names,
                        impact_breakdown=breakdown,
                        focal_point=focal_point,
                    )
                )

                s_start = max(0.0, t - dur_s * 0.25)
                s_end = min(clip_duration, s_start + dur_s)
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_MICRO_SHAKE,
                        start=s_start,
                        end=s_end,
                        intensity=round(score, 2),
                        confidence=conf,
                        reason=f"{reason_str} (micro_shake)",
                        source_events=source_names,
                        impact_breakdown=breakdown,
                    )
                )

            # 3. Moderate Interest Moment: Subtle Zoom
            elif score >= self.subtle_zoom_threshold and conf >= self.subtle_zoom_conf:
                dur_z = SUBTLE_ZOOM_DURATION
                z_start = max(0.0, t - dur_z * 0.4)
                z_end = min(clip_duration, z_start + dur_z)

                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_SUBTLE_ZOOM,
                        start=z_start,
                        end=z_end,
                        intensity=round(score, 2),
                        confidence=conf,
                        reason=reason_str,
                        source_events=source_names,
                        impact_breakdown=breakdown,
                        focal_point=focal_point,
                    )
                )

            # 4. Low Confidence / Ambient Dialogue: Suppressed
            else:
                suppressed_events.append({
                    "anchor_time": t,
                    "impact_score": score,
                    "confidence": conf,
                    "reason": f"Below thresholds (impact={score:.2f} < {self.subtle_zoom_threshold}, conf={conf:.2f} < {self.subtle_zoom_conf})",
                })

        return raw_effects, suppressed_events

    def resolve_conflicts_and_cooldowns(
        self,
        raw_effects: List[EffectEvent],
        clip_duration: float,
        max_effects_per_min: int = 12,
    ) -> Tuple[List[EffectEvent], List[Dict[str, Any]]]:
        """
        Enforces effect priority hierarchy and minimum spacing (cooldowns) to avoid chaotic spam.
        Priority:
          Zooms: impact_zoom > punch_zoom > subtle_zoom
          Shakes: impact_shake > micro_shake
        """
        if not raw_effects:
            return [], []

        zoom_priority = {
            EFFECT_IMPACT_ZOOM: 3,
            EFFECT_PUNCH_ZOOM: 2,
            EFFECT_SUBTLE_ZOOM: 1,
        }
        shake_priority = {
            EFFECT_IMPACT_SHAKE: 2,
            EFFECT_MICRO_SHAKE: 1,
        }

        # Partition by effect family
        zooms = [e for e in raw_effects if e.type in zoom_priority]
        shakes = [e for e in raw_effects if e.type in shake_priority]
        flashes = [e for e in raw_effects if e.type == EFFECT_EMPHASIS_FLASH]

        accepted: List[EffectEvent] = []
        suppressed: List[Dict[str, Any]] = []

        # 1. Resolve Zooms with cooldown
        zooms.sort(key=lambda e: e.start)
        last_zoom: Optional[EffectEvent] = None

        for z in zooms:
            if last_zoom is None:
                accepted.append(z)
                last_zoom = z
            else:
                gap = z.start - last_zoom.end
                if gap < self.min_zoom_gap:
                    # In conflict: compare priority
                    p_new = zoom_priority.get(z.type, 0)
                    p_old = zoom_priority.get(last_zoom.type, 0)
                    if p_new > p_old or (p_new == p_old and z.intensity > last_zoom.intensity):
                        # Replace previous weaker zoom
                        accepted.remove(last_zoom)
                        suppressed.append({
                            "type": last_zoom.type,
                            "start": last_zoom.start,
                            "reason": f"Replaced by higher-priority {z.type} at {z.start:.2f}s within zoom gap ({gap:.2f}s < {self.min_zoom_gap}s)",
                        })
                        accepted.append(z)
                        last_zoom = z
                    else:
                        suppressed.append({
                            "type": z.type,
                            "start": z.start,
                            "reason": f"Suppressed by earlier {last_zoom.type} at {last_zoom.start:.2f}s within zoom gap ({gap:.2f}s < {self.min_zoom_gap}s)",
                        })
                else:
                    accepted.append(z)
                    last_zoom = z

        # 2. Resolve Shakes with cooldown
        shakes.sort(key=lambda e: e.start)
        last_shake: Optional[EffectEvent] = None

        for s in shakes:
            if last_shake is None:
                accepted.append(s)
                last_shake = s
            else:
                gap = s.start - last_shake.end
                if gap < self.min_shake_gap:
                    p_new = shake_priority.get(s.type, 0)
                    p_old = shake_priority.get(last_shake.type, 0)
                    if p_new > p_old or (p_new == p_old and s.intensity > last_shake.intensity):
                        accepted.remove(last_shake)
                        suppressed.append({
                            "type": last_shake.type,
                            "start": last_shake.start,
                            "reason": f"Replaced by higher-priority {s.type} within shake gap",
                        })
                        accepted.append(s)
                        last_shake = s
                    else:
                        suppressed.append({
                            "type": s.type,
                            "start": s.start,
                            "reason": f"Suppressed by earlier {last_shake.type} within shake gap",
                        })
                else:
                    accepted.append(s)
                    last_shake = s

        # 3. Resolve Flashes with cooldown
        flashes.sort(key=lambda e: e.start)
        last_flash: Optional[EffectEvent] = None

        for f in flashes:
            if last_flash is None:
                accepted.append(f)
                last_flash = f
            else:
                gap = f.start - last_flash.end
                if gap < self.min_flash_gap:
                    suppressed.append({
                        "type": f.type,
                        "start": f.start,
                        "reason": f"Suppressed by earlier flash within flash gap",
                    })
                else:
                    accepted.append(f)
                    last_flash = f

        # 4. Enforce maximum effects per minute cap to prevent excessive density
        if clip_duration > 0:
            max_allowed = max(4, int(round((clip_duration / 60.0) * max_effects_per_min)))
            if len(accepted) > max_allowed:
                type_rank = {
                    EFFECT_IMPACT_ZOOM: 5,
                    EFFECT_IMPACT_SHAKE: 4,
                    EFFECT_EMPHASIS_FLASH: 3,
                    EFFECT_PUNCH_ZOOM: 2,
                    EFFECT_MICRO_SHAKE: 1,
                    EFFECT_SUBTLE_ZOOM: 0,
                }
                ranked = sorted(
                    accepted,
                    key=lambda e: (type_rank.get(e.type, 0), e.intensity, e.confidence),
                    reverse=True,
                )
                kept = ranked[:max_allowed]
                dropped = ranked[max_allowed:]
                for d in dropped:
                    suppressed.append({
                        "type": d.type,
                        "start": d.start,
                        "reason": f"Suppressed by max effects per minute cap ({max_allowed} max for {clip_duration:.1f}s)",
                    })
                accepted = kept

        # Final sort chronologically
        accepted.sort(key=lambda e: (e.start, e.type))
        return accepted, suppressed

    def generate_timeline(
        self,
        candidate_id: int,
        candidate: Dict[str, Any],
        phase4_data: Optional[Dict[str, Any]] = None,
        audio_peaks: Optional[List[Dict[str, Any]]] = None,
        facecam_info: Optional[Dict[str, Any]] = None,
    ) -> EffectTimeline:
        """
        End-to-end decision engine generating the complete, validated effect timeline.
        """
        clip_start = float(candidate.get("extraction_start", candidate.get("candidate_start", 0.0)))
        clip_end = float(candidate.get("extraction_end", candidate.get("candidate_end", 60.0)))
        clip_duration = float(candidate.get("extraction_duration", clip_end - clip_start))

        # 1. Cluster events & score impact
        moments = self.cluster_events(
            candidate=candidate,
            phase4_data=phase4_data,
            audio_peaks=audio_peaks,
            clip_start=clip_start,
            clip_end=clip_end,
            clip_duration=clip_duration,
        )

        # 2. Generate raw effects from multi-signal clustering
        raw_effects, initial_suppressed = self.generate_raw_effects(
            moments=moments,
            clip_duration=clip_duration,
            facecam_info=facecam_info,
        )

        # 2b. Direct event-driven effect generation for confirmed gameplay events
        has_facecam = facecam_info and facecam_info.get("facecam_detected", False)
        focal_point = (0.50, 0.65) if has_facecam else (0.50, 0.50)

        effect_style = candidate.get("effect_style", "balanced")
        max_effects_per_min = candidate.get("max_effects_per_minute", 10)
        if effect_style == "cinematic_comedy":
            max_effects_per_min = min(max_effects_per_min, 6)

        gameplay_events = candidate.get("gameplay_events", [])
        for ev in gameplay_events:
            ev_dict = ev if isinstance(ev, dict) else (ev.to_dict() if hasattr(ev, "to_dict") else vars(ev))
            if ev_dict.get("status") == "supporting":
                continue
            ev_t = float(ev_dict.get("timestamp", 0.0))
            if not (clip_start <= ev_t <= clip_end):
                continue

            rel_t = max(0.0, min(clip_duration, ev_t - clip_start))
            ev_type = str(ev_dict.get("event_type", "")).lower()
            ev_conf = float(ev_dict.get("confidence", 0.85))

            if ev_type in ("kill", "headshot"):
                dur_z = PUNCH_ZOOM_DURATION
                dur_s = MICRO_SHAKE_DURATION
                z_start = max(0.0, rel_t - dur_z * 0.35)
                z_end = min(clip_duration, z_start + dur_z)
                s_start = max(0.0, rel_t - dur_s * 0.25)
                s_end = min(clip_duration, s_start + dur_s)

                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_PUNCH_ZOOM,
                        start=z_start,
                        end=z_end,
                        intensity=0.85,
                        confidence=ev_conf,
                        reason=f"gameplay_event:{ev_type}",
                        source_events=["gameplay_event"],
                        focal_point=focal_point,
                    )
                )
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_MICRO_SHAKE,
                        start=s_start,
                        end=s_end,
                        intensity=0.75,
                        confidence=ev_conf,
                        reason=f"gameplay_event:{ev_type} (micro_shake)",
                        source_events=["gameplay_event"],
                    )
                )
            elif ev_type in ("ace", "ace_candidate", "clutch", "clutch_candidate", "multi_kill", "round_win"):
                dur_z = IMPACT_ZOOM_DURATION
                dur_s = IMPACT_SHAKE_DURATION
                dur_f = FLASH_DURATION
                z_start = max(0.0, rel_t - dur_z * 0.30)
                z_end = min(clip_duration, z_start + dur_z)
                s_start = max(0.0, rel_t - dur_s * 0.20)
                s_end = min(clip_duration, s_start + dur_s)
                f_start = max(0.0, rel_t - dur_f * 0.20)
                f_end = min(clip_duration, f_start + dur_f)

                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_IMPACT_ZOOM,
                        start=z_start,
                        end=z_end,
                        intensity=0.95,
                        confidence=ev_conf,
                        reason=f"gameplay_climax:{ev_type}",
                        source_events=["gameplay_climax"],
                        focal_point=focal_point,
                    )
                )
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_IMPACT_SHAKE,
                        start=s_start,
                        end=s_end,
                        intensity=0.90,
                        confidence=ev_conf,
                        reason=f"gameplay_climax:{ev_type} (impact_shake)",
                        source_events=["gameplay_climax"],
                    )
                )
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_EMPHASIS_FLASH,
                        start=f_start,
                        end=f_end,
                        intensity=0.85,
                        confidence=ev_conf,
                        reason=f"gameplay_climax:{ev_type} (emphasis_flash)",
                        source_events=["gameplay_climax"],
                    )
                )
            elif ev_type == "jumpscare":
                dur_z = IMPACT_ZOOM_DURATION
                dur_s = IMPACT_SHAKE_DURATION
                dur_f = FLASH_DURATION
                z_start = max(0.0, rel_t - dur_z * 0.25)
                z_end = min(clip_duration, z_start + dur_z)
                s_start = max(0.0, rel_t - dur_s * 0.15)
                s_end = min(clip_duration, s_start + dur_s)
                f_start = max(0.0, rel_t - dur_f * 0.15)
                f_end = min(clip_duration, f_start + dur_f)

                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_IMPACT_ZOOM,
                        start=z_start,
                        end=z_end,
                        intensity=0.98,
                        confidence=ev_conf,
                        reason="horror:jumpscare_zoom",
                        source_events=["jumpscare"],
                        focal_point=focal_point,
                    )
                )
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_IMPACT_SHAKE,
                        start=s_start,
                        end=s_end,
                        intensity=0.95,
                        confidence=ev_conf,
                        reason="horror:jumpscare_shake",
                        source_events=["jumpscare"],
                    )
                )
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_EMPHASIS_FLASH,
                        start=f_start,
                        end=f_end,
                        intensity=0.90,
                        confidence=ev_conf,
                        reason="horror:jumpscare_flash",
                        source_events=["jumpscare"],
                    )
                )
            elif ev_type == "panic_escape":
                dur_s = MICRO_SHAKE_DURATION
                s_start = max(0.0, rel_t - dur_s * 0.25)
                s_end = min(clip_duration, s_start + dur_s)
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_MICRO_SHAKE,
                        start=s_start,
                        end=s_end,
                        intensity=0.80,
                        confidence=ev_conf,
                        reason="horror:panic_escape",
                        source_events=["panic_escape"],
                    )
                )
            elif ev_type in ("story_climax", "comedic_moment"):
                # Clean cinematic subtle punch zoom — NO aggressive shake on dialogue
                dur_z = PUNCH_ZOOM_DURATION
                z_start = max(0.0, rel_t - dur_z * 0.35)
                z_end = min(clip_duration, z_start + dur_z)
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_PUNCH_ZOOM,
                        start=z_start,
                        end=z_end,
                        intensity=0.75,
                        confidence=ev_conf,
                        reason=f"story:{ev_type}",
                        source_events=[ev_type],
                        focal_point=focal_point,
                    )
                )
            elif ev_type in ("chaos_burst", "boss_fight_climax"):
                dur_z = IMPACT_ZOOM_DURATION
                dur_s = MICRO_SHAKE_DURATION
                z_start = max(0.0, rel_t - dur_z * 0.30)
                z_end = min(clip_duration, z_start + dur_z)
                s_start = max(0.0, rel_t - dur_s * 0.20)
                s_end = min(clip_duration, s_start + dur_s)
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_IMPACT_ZOOM,
                        start=z_start,
                        end=z_end,
                        intensity=0.90,
                        confidence=ev_conf,
                        reason=f"story:{ev_type}",
                        source_events=[ev_type],
                        focal_point=focal_point,
                    )
                )
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_MICRO_SHAKE,
                        start=s_start,
                        end=s_end,
                        intensity=0.80,
                        confidence=ev_conf,
                        reason=f"story:{ev_type} (micro_shake)",
                        source_events=[ev_type],
                    )
                )

        # Direct sequence climaxes if available
        gameplay_sequences = candidate.get("gameplay_sequences", [])
        for seq in gameplay_sequences:
            seq_dict = seq if isinstance(seq, dict) else (seq.to_dict() if hasattr(seq, "to_dict") else vars(seq))
            climax_t = float(seq_dict.get("climax_timestamp", seq_dict.get("end_time", 0.0)))
            seq_type = str(seq_dict.get("sequence_type", "climax")).lower()
            if clip_start <= climax_t <= clip_end:
                rel_t = max(0.0, min(clip_duration, climax_t - clip_start))
                dur_z = IMPACT_ZOOM_DURATION
                dur_s = IMPACT_SHAKE_DURATION
                z_start = max(0.0, rel_t - dur_z * 0.30)
                z_end = min(clip_duration, z_start + dur_z)
                s_start = max(0.0, rel_t - dur_s * 0.20)
                s_end = min(clip_duration, s_start + dur_s)
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_IMPACT_ZOOM,
                        start=z_start,
                        end=z_end,
                        intensity=0.95,
                        confidence=0.90,
                        reason=f"gameplay_sequence:{seq_type}",
                        source_events=["gameplay_sequence"],
                        focal_point=focal_point,
                    )
                )
                raw_effects.append(
                    EffectEvent(
                        type=EFFECT_IMPACT_SHAKE,
                        start=s_start,
                        end=s_end,
                        intensity=0.90,
                        confidence=0.90,
                        reason=f"gameplay_sequence:{seq_type} (impact_shake)",
                        source_events=["gameplay_sequence"],
                    )
                )

        # 3. Resolve cooldowns and overlaps
        final_effects, cooldown_suppressed = self.resolve_conflicts_and_cooldowns(
            raw_effects=raw_effects,
            clip_duration=clip_duration,
            max_effects_per_min=max_effects_per_min,
        )

        all_suppressed = initial_suppressed + cooldown_suppressed
        impact_summaries = [
            {
                "time": m["anchor_time"],
                "score": m["impact_score"],
                "confidence": m["confidence"],
                "breakdown": m["breakdown"],
            }
            for m in moments
        ]

        return EffectTimeline(
            candidate_id=candidate_id,
            candidate_duration=clip_duration,
            effects=final_effects,
            suppressed_events=all_suppressed,
            impact_scores=impact_summaries,
        )

    def write_timeline_file(self, output_path: Path, timeline: EffectTimeline) -> Path:
        """Writes the EffectTimeline to a JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(timeline.to_dict(), f, indent=2, ensure_ascii=False)
        return output_path
