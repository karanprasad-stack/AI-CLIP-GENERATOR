"""Evidence Fusion Engine combining visual, audio, transcript, and temporal corroboration."""

import uuid
from typing import Dict, Any, List, Optional, Tuple

from .models import GameplayEvent, EventType, EventStatus, EvidenceBreakdown
from .profiles.base import BaseGameProfile
from .evidence.audio import AudioEvidenceExtractor
from .evidence.transcript import TranscriptEvidenceExtractor
from .valorant.kill_feed import KillFeedSignal
from .valorant.round_state import RoundStateSignal
from .valorant.hud import HudSignal


class EvidenceFusionEngine:
    """Fuses multi-modal evidence with weighted scoring and cross-source agreement."""

    def __init__(self, profile: BaseGameProfile):
        self.profile = profile
        self.game_name = profile.name
        self.detection_cfg = profile.detection_config

    def fuse_events(
        self,
        visual_signals: Dict[str, List[Any]],
        audio_extractor: AudioEvidenceExtractor,
        transcript_extractor: TranscriptEvidenceExtractor,
        duration: float,
    ) -> List[GameplayEvent]:
        """Fuses all raw evidence streams into structured, typed GameplayEvent instances."""
        events: List[GameplayEvent] = []

        kill_signals: List[KillFeedSignal] = visual_signals.get("kill_feed", [])
        round_signals: List[RoundStateSignal] = visual_signals.get("round_state", [])
        hud_signals: List[HudSignal] = visual_signals.get("hud", [])

        # -------------------------------------------------------------
        # 1. Fuse Kill Events from Kill Feed + Audio + Transcript
        # -------------------------------------------------------------
        for kf in kill_signals:
            t = kf.timestamp
            v_conf = kf.confidence

            # Audio evidence query
            a_conf, matching_peak = audio_extractor.query_evidence(t, window=1.20)

            # Transcript evidence query
            tr_conf, matched_terms, tr_meta = transcript_extractor.query_evidence(t, pre_window=1.0, post_window=3.5)

            # HUD skull confirmation
            matching_skull = next(
                (h for h in hud_signals if h.signal_type == "local_kill_skull" and abs(h.timestamp - t) <= 1.0),
                None
            )
            is_local = kf.is_spectated_player or (matching_skull is not None)

            # Cross-source agreement bonus
            sources_agree = (1.0 if v_conf >= 0.70 else 0.0) + (1.0 if a_conf >= 0.50 else 0.0) + (1.0 if tr_conf >= 0.40 else 0.0)
            agreement_factor = min(1.0, sources_agree / 3.0)

            # Fused confidence: Visual is primary baseline; audio, transcript, and local player attribution provide boosts
            fused_conf = v_conf * 0.82
            if a_conf >= 0.40:
                fused_conf += min(0.10, a_conf * 0.12)
            if tr_conf >= 0.35:
                fused_conf += min(0.08, tr_conf * 0.10)
            if is_local:
                fused_conf += 0.05
            if agreement_factor >= 0.60:
                fused_conf += 0.04
            fused_conf = min(0.99, max(0.10, round(fused_conf, 3)))

            # Determine status: confirmed vs candidate
            if v_conf >= 0.75 and (a_conf >= 0.40 or tr_conf >= 0.35 or is_local):
                status = EventStatus.CONFIRMED.value
            elif v_conf >= 0.65 or (a_conf >= 0.75 and tr_conf >= 0.60):
                status = EventStatus.CANDIDATE.value
            else:
                status = EventStatus.SUPPORTING.value

            # Headshot corroboration
            is_hs = kf.is_headshot or any(term in ["headshot", "one tap", "1 tap"] for term in matched_terms)

            # Explainable text summary
            reasons = [f"Kill-feed detected banner (conf {v_conf:.2f})"]
            if a_conf > 0.40:
                reasons.append(f"Corroborating audio peak (conf {a_conf:.2f})")
            if matched_terms:
                reasons.append(f"Speech callouts: {', '.join(matched_terms[:3])}")
            if is_local:
                reasons.append("Spectated player kill attribution")

            breakdown = EvidenceBreakdown(
                visual=v_conf,
                kill_feed=v_conf,
                audio=a_conf,
                transcript=tr_conf,
                temporal_consistency=0.95,
                cross_source_agreement=round(agreement_factor, 2),
                raw_signals={
                    "kill_feed_evidence": kf.raw_evidence,
                    "matched_audio_peak": matching_peak,
                    "matched_transcript_terms": matched_terms,
                }
            )

            metadata: Dict[str, Any] = {
                "headshot": is_hs,
                "is_spectated_player": is_local,
                "killer": "spectated_player" if is_local else "unknown",
                "victim": "unknown",
                "row_index": kf.row_index,
            }

            event_id = f"evt_kill_{uuid.uuid4().hex[:8]}"
            kill_event = GameplayEvent(
                id=event_id,
                game=self.game_name,
                event_type=EventType.KILL.value,
                start_time=round(max(0.0, t - 0.5), 3),
                end_time=round(min(duration, t + 0.5), 3),
                confidence=fused_conf,
                status=status,
                source_evidence={
                    "visual": v_conf,
                    "kill_feed": v_conf,
                    "audio": a_conf,
                    "transcript": tr_conf,
                },
                evidence_breakdown=breakdown,
                metadata=metadata,
                explanation="; ".join(reasons),
            )
            events.append(kill_event)

            # If headshot is confirmed, also emit high-value HEADSHOT event
            if is_hs:
                events.append(
                    GameplayEvent(
                        id=f"evt_hs_{uuid.uuid4().hex[:8]}",
                        game=self.game_name,
                        event_type=EventType.HEADSHOT.value,
                        start_time=kill_event.start_time,
                        end_time=kill_event.end_time,
                        confidence=min(0.99, fused_conf + 0.02),
                        status=status,
                        source_evidence=kill_event.source_evidence,
                        evidence_breakdown=breakdown,
                        metadata={"associated_kill_id": event_id},
                        explanation=f"Headshot elimination ({kill_event.explanation})",
                    )
                )

        # -------------------------------------------------------------
        # 2. Fuse Round State Events (Round Win, Spike)
        # -------------------------------------------------------------
        for rs in round_signals:
            t = rs.timestamp
            a_conf, _ = audio_extractor.query_evidence(t, window=2.0)
            tr_conf, tr_terms, _ = transcript_extractor.query_evidence(t, pre_window=1.5, post_window=4.0)

            fused_conf = min(0.98, round(0.60 * rs.confidence + 0.25 * a_conf + 0.15 * tr_conf, 3))
            status = EventStatus.CONFIRMED.value if rs.confidence >= 0.80 else EventStatus.CANDIDATE.value

            if rs.event_type == "round_win":
                events.append(
                    GameplayEvent(
                        id=f"evt_rwin_{uuid.uuid4().hex[:8]}",
                        game=self.game_name,
                        event_type=EventType.ROUND_WIN.value,
                        start_time=round(max(0.0, t - 1.0), 3),
                        end_time=round(min(duration, t + 2.0), 3),
                        confidence=fused_conf,
                        status=status,
                        source_evidence={"visual": rs.confidence, "audio": a_conf, "transcript": tr_conf},
                        metadata=rs.details,
                        explanation=f"Round victory confirmed by center screen victory banner (conf {rs.confidence:.2f})",
                    )
                )
            elif rs.event_type == "spike_planted":
                events.append(
                    GameplayEvent(
                        id=f"evt_spk_plant_{uuid.uuid4().hex[:8]}",
                        game=self.game_name,
                        event_type=EventType.SPIKE_PLANTED.value,
                        start_time=round(max(0.0, t - 1.0), 3),
                        end_time=round(min(duration, t + 1.5), 3),
                        confidence=fused_conf,
                        status=status,
                        source_evidence={"visual": rs.confidence, "audio": a_conf, "transcript": tr_conf},
                        metadata=rs.details,
                        explanation="Spike planted confirmed by top-center UI marker",
                    )
                )

        # -------------------------------------------------------------
        # 3. Audio & Transcript-only Signals (Guaranteed Non-Kill False Positive Protection)
        # -------------------------------------------------------------
        # Any intense speech or audio peak with NO visual kill feed is emitted strictly
        # as a supporting event (e.g. 'reaction' or 'audio_spike'), NEVER as a kill!
        for word in transcript_extractor.words:
            w_text = str(word.get("word", "")).lower().strip(".,!?:;\"'()")
            w_t = float(word.get("start", 0.0))
            if w_text in ["clutch", "ace"]:
                # Check if there is already a nearby visual event
                has_nearby_visual = any(abs(e.start_time - w_t) <= 3.0 for e in events)
                if not has_nearby_visual:
                    # Pure vocal exclamation without visual proof -> supporting reaction
                    events.append(
                        GameplayEvent(
                            id=f"evt_voc_{uuid.uuid4().hex[:8]}",
                            game=self.game_name,
                            event_type=EventType.REACTION.value,
                            start_time=round(w_t, 3),
                            end_time=round(float(word.get("end", w_t + 0.5)), 3),
                            confidence=0.45,
                            status=EventStatus.SUPPORTING.value,
                            source_evidence={"transcript": 0.60, "visual": 0.0},
                            metadata={"spoken_term": w_text},
                            explanation=f"Spoken exclamation '{w_text}' detected without visual kill verification",
                        )
                    )

        # Sort all events chronologically
        events.sort(key=lambda e: e.start_time)
        return events
