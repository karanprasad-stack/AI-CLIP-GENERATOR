"""Candidate scoring and ranking engine with granular, auditable GameplayEventScore breakdowns."""

from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
import json
import numpy as np

from backend.app.config import (
    DEFAULT_SCORING_WEIGHTS,
    GAME_AWARE_SCORING_WEIGHTS,
    CONCRETE_GAMEPLAY_EVENT_BONUSES,
    GAMEPLAY_INTERNAL_WEIGHTS,
    IOU_DEDUPLICATION_THRESHOLD,
    MAX_OVERLAP_SECONDS,
    EVENT_CLUSTER_WINDOW,
    HIGH_IMPACT_GAMING_WORDS,
    get_duration_tier,
    get_narrative_structure,
)
from backend.app.pipeline.games.models import EventStatus
from .audio_analyzer import AudioAnalyzer
from .transcript_analyzer import TranscriptAnalyzer


class CandidateRanker:
    """Scores candidate moments using decoupled scoring modules, temporal clustering, and deduplication."""

    def __init__(self, weights: Dict[str, float] = None):
        self.custom_weights = (weights is not None)
        self.raw_weights = weights or dict(DEFAULT_SCORING_WEIGHTS)
        self.weights = self._normalize_weights(self.raw_weights)
        self.internal_weights = dict(GAMEPLAY_INTERNAL_WEIGHTS)
        self.audio_analyzer = AudioAnalyzer()

    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Normalize active weights so they dynamically sum to 1.0."""
        active = {k: max(0.0, float(v)) for k, v in weights.items() if v > 0.0}
        total = sum(active.values())
        if total <= 0:
            return dict(DEFAULT_SCORING_WEIGHTS)
        return {k: round(v / total, 4) for k, v in active.items()}

    def calculate_concrete_gameplay_score(
        self,
        start_sec: float,
        end_sec: float,
        gameplay_timeline: Any,
    ) -> Tuple[float, List[str], str, Dict[str, Any]]:
        """
        Evaluates concrete, verified Phase 12A gameplay combat and objective events in the window.
        Returns:
            concrete_score: float (0.0 to 100.0)
            concrete_signals: list[str]
            concrete_explanation: str
            concrete_metrics: dict
        """
        if not gameplay_timeline or not hasattr(gameplay_timeline, "get_events_in_range"):
            return 0.0, [], "No concrete gameplay events detected.", {}

        w_events = gameplay_timeline.get_events_in_range(start_sec, end_sec)
        if not w_events:
            return 0.0, [], "No concrete gameplay events detected.", {}

        # False-positive protection: Strictly filter out supporting-only events and pure exclamations
        qualifying_events = [
            e for e in w_events
            if getattr(e, "status", "") != EventStatus.SUPPORTING.value
            and getattr(e, "event_type", "") not in {"reaction", "audio_spike"}
        ]

        if not qualifying_events:
            return 0.0, [], "No verified combat events in window (reactions only).", {}

        has_ace = False
        ace_conf = 0.0
        has_ace_cand = False
        ace_cand_conf = 0.0
        has_4k = False
        four_k_conf = 0.0
        has_3k = False
        three_k_conf = 0.0
        has_2k = False
        two_k_conf = 0.0
        has_rapid = False
        rapid_conf = 0.0
        has_clutch = False
        clutch_conf = 0.0
        round_win = False
        defuse_conf = 0.0
        plant_conf = 0.0

        kill_events = []
        headshot_count = 0
        spectated_kills_count = 0

        for ev in qualifying_events:
            etype = getattr(ev, "event_type", "")
            meta = getattr(ev, "metadata", {}) or {}
            subtype = meta.get("subtype", etype)
            conf = getattr(ev, "confidence", 0.5)
            status = getattr(ev, "status", "")

            # Weight confidence factor
            conf_factor = (0.7 + 0.3 * conf) if status == EventStatus.CONFIRMED.value else (0.5 + 0.3 * conf)

            if etype == "ace" or subtype == "ace":
                has_ace = True
                ace_conf = max(ace_conf, conf_factor)
            elif etype == "ace_candidate" or subtype == "ace_candidate":
                has_ace_cand = True
                ace_cand_conf = max(ace_cand_conf, conf_factor)
            elif subtype == "4k":
                has_4k = True
                four_k_conf = max(four_k_conf, conf_factor)
            elif subtype == "3k":
                has_3k = True
                three_k_conf = max(three_k_conf, conf_factor)
            elif subtype == "2k":
                has_2k = True
                two_k_conf = max(two_k_conf, conf_factor)
            elif etype == "rapid_kill_sequence":
                has_rapid = True
                rapid_conf = max(rapid_conf, conf_factor)

            if etype in {"clutch_candidate", "1vx_candidate"}:
                has_clutch = True
                clutch_conf = max(clutch_conf, conf_factor)

            if etype == "kill":
                kill_events.append(ev)
                if meta.get("headshot", False):
                    headshot_count += 1
                if meta.get("is_spectated_player", False) or meta.get("killer") == "spectated_player":
                    spectated_kills_count += 1

            if etype == "headshot":
                headshot_count += 1

            if etype == "round_win":
                round_win = True
            elif etype == "spike_defused":
                defuse_conf = max(defuse_conf, conf_factor)
            elif etype == "spike_planted":
                plant_conf = max(plant_conf, conf_factor)

        # Map to calibrated hierarchy score [0.0 - 100.0]
        if has_ace:
            base = 90.0 + min(6.0, ace_conf * 6.0)
            hs_add = min(3.0, headshot_count * 1.5)
            spec_add = min(2.0, spectated_kills_count * 0.5)
            score = min(100.0, max(92.0, base + hs_add + spec_add))
            explanation = f"Ace sequence confirmed ({len(kill_events)} kills, conf {ace_conf:.2f})"
        elif has_ace_cand:
            base = 82.0 + min(6.0, ace_cand_conf * 6.0)
            hs_add = min(4.0, headshot_count * 1.5)
            score = min(92.0, max(80.0, base + hs_add))
            explanation = f"Ace candidate sequence ({len(kill_events)} kills, conf {ace_cand_conf:.2f})"
        elif has_4k:
            base = 78.0 + min(6.0, four_k_conf * 6.0)
            hs_add = min(4.0, headshot_count * 1.5)
            clutch_add = 4.0 if has_clutch else 0.0
            score = min(92.0, max(75.0, base + hs_add + clutch_add))
            explanation = f"4K multi-kill confirmed (conf {four_k_conf:.2f})"
        elif has_clutch:
            base = 76.0 + min(6.0, clutch_conf * 6.0)
            k_add = min(6.0, len(kill_events) * 2.0)
            hs_add = min(4.0, headshot_count * 1.5)
            score = min(92.0, max(75.0, base + k_add + hs_add))
            explanation = f"Clutch candidate secured (conf {clutch_conf:.2f})"
        elif has_3k:
            base = 62.0 + min(6.0, three_k_conf * 6.0)
            hs_add = min(4.0, headshot_count * 1.5)
            rw_add = 3.0 if round_win else 0.0
            score = min(75.0, max(60.0, base + hs_add + rw_add))
            explanation = f"3K multi-kill confirmed (conf {three_k_conf:.2f})"
        elif has_rapid:
            base = 56.0 + min(5.0, rapid_conf * 5.0)
            score = min(72.0, max(55.0, base))
            explanation = f"Rapid kill sequence confirmed (conf {rapid_conf:.2f})"
        elif has_2k:
            base = 42.0 + min(5.0, two_k_conf * 5.0)
            hs_add = min(4.0, headshot_count * 2.0)
            rw_add = 3.0 if round_win else 0.0
            score = min(55.0, max(40.0, base + hs_add + rw_add))
            explanation = f"2K multi-kill confirmed (conf {two_k_conf:.2f})"
        elif len(kill_events) >= 1:
            k_cnt = len(kill_events)
            avg_k_conf = sum(getattr(k, "confidence", 0.5) for k in kill_events) / float(k_cnt)
            base = 22.0 + min(5.0, avg_k_conf * 5.0)
            hs_add = min(5.0, headshot_count * 2.5)
            rw_add = 3.0 if round_win else 0.0
            score = min(38.0, max(20.0, base + hs_add + rw_add))
            explanation = f"{k_cnt} elimination(s) confirmed (conf {avg_k_conf:.2f})"
        elif round_win or defuse_conf > 0 or plant_conf > 0:
            base = 15.0 + (5.0 if round_win else 0.0) + (4.0 if defuse_conf > 0 else 0.0) + (3.0 if plant_conf > 0 else 0.0)
            score = min(30.0, max(12.0, base))
            explanation = "Objective gameplay event (round win/spike)"
        else:
            return 0.0, [], "No concrete gameplay events detected.", {}

        signals = [f"event:{e.event_type}@{e.start_time:.1f}s" for e in qualifying_events]
        metrics = {
            "kills": len(kill_events),
            "headshots": headshot_count,
            "spectated_kills": spectated_kills_count,
            "has_ace": has_ace,
            "has_4k": has_4k,
            "has_3k": has_3k,
            "has_2k": has_2k,
            "has_clutch": has_clutch,
        }

        return round(score, 1), signals, explanation, metrics

    def calculate_gameplay_event_score(
        self,
        start_sec: float,
        end_sec: float,
        audio_analysis: Dict[str, Any],
        transcript_analyzer: TranscriptAnalyzer,
        gameplay_timeline: Optional[Any] = None,
    ) -> Tuple[float, Dict[str, Any], List[str], Dict[str, Any]]:
        """
        Evaluates temporal clustering of gaming terminology, vocal reactions, and audio peaks.
        Returns:
            gameplay_score: float (0-100)
            metrics: dict
            reasons: list[str]
            breakdown: dict of {component: {score, signals, explanation}}
        """
        cluster_window = EVENT_CLUSTER_WINDOW  # 8.0 seconds
        duration = max(1.0, end_sec - start_sec)

        # 1. Gather all timestamped signals
        lexical_signals = transcript_analyzer.get_timestamped_signals(start_sec, end_sec)
        audio_peaks = [
            p for p in audio_analysis.get("peaks", [])
            if start_sec <= p["timestamp"] <= end_sec
        ]

        gaming_signals = [s for s in lexical_signals if s["type"] == "gaming"]
        reaction_phrase_signals = [s for s in lexical_signals if s["type"] == "reaction_phrase"]
        reaction_word_signals = [s for s in lexical_signals if s["type"] in ["reaction_word", "laughter"]]

        # Combine into unified event stream for clustering
        event_stream: List[Dict[str, Any]] = []
        for s in lexical_signals:
            event_stream.append({
                "t": s["t"],
                "cat": s["type"],
                "term": s["term"],
                "weight": s["weight"],
            })
        for p in audio_peaks:
            event_stream.append({
                "t": p["timestamp"],
                "cat": "audio_peak",
                "term": f"Z={p['z_score']}",
                "weight": min(3.0, p["z_score"]),
            })
        event_stream.sort(key=lambda x: x["t"])

        # -------------------------------------------------------------
        # Component 1: gaming_lexical (Weight: 25%)
        # -------------------------------------------------------------
        gaming_signals_repr = [f"{s['term']}@{s['t']:.2f}s" for s in gaming_signals]
        if not gaming_signals:
            gaming_score = 0.0
            gaming_expl = "No gaming vocabulary detected."
        else:
            base_g = 60.0 if len(gaming_signals) == 1 else (85.0 if len(gaming_signals) == 2 else 95.0)
            has_high_impact = any(s["term"] in HIGH_IMPACT_GAMING_WORDS or s["term"] in ["kill", "headshot", "clutch", "ace", "1v1"] for s in gaming_signals)
            if has_high_impact:
                base_g = min(100.0, base_g + 15.0)
            gaming_score = float(min(100.0, base_g))
            unique_terms = sorted(list(set(s["term"] for s in gaming_signals)))
            gaming_expl = f"Detected {len(gaming_signals)} gaming term(s): {', '.join(unique_terms)}."

        # -------------------------------------------------------------
        # Component 2: reaction_lexical (Weight: 20%)
        # -------------------------------------------------------------
        reaction_signals_repr = (
            [f"phrase:{s['term']}@{s['t']:.2f}s" for s in reaction_phrase_signals]
            + [f"word:{s['term']}@{s['t']:.2f}s" for s in reaction_word_signals]
        )
        if not reaction_signals_repr:
            reaction_score = 0.0
            reaction_expl = "No reaction phrases or reaction words detected."
        else:
            r_pts = (len(reaction_phrase_signals) * 55.0) + (len(reaction_word_signals) * 20.0)
            reaction_score = float(min(100.0, r_pts))
            reaction_expl = (
                f"Detected {len(reaction_phrase_signals)} reaction phrase(s) "
                f"and {len(reaction_word_signals)} reaction word(s)."
            )

        # -------------------------------------------------------------
        # Component 3: audio_event_alignment (Weight: 20%)
        # -------------------------------------------------------------
        audio_signals_repr = [f"audio_peak_z={p['z_score']}@{p['timestamp']:.2f}s" for p in audio_peaks]
        if not audio_peaks:
            audio_align_score = 0.0
            audio_align_expl = "No significant audio volume peaks detected."
        else:
            max_z = max(p["z_score"] for p in audio_peaks)
            # Check temporal alignment with speech / lexical tokens
            aligned_peaks = 0
            for p in audio_peaks:
                t_peak = p["timestamp"]
                # Is there speech within +- 3.5s?
                near_lex = any(abs(s["t"] - t_peak) <= 3.5 for s in lexical_signals)
                near_words = any(abs(w["start"] - t_peak) <= 3.5 for w in transcript_analyzer.words)
                if near_lex or near_words:
                    aligned_peaks += 1

            align_ratio = aligned_peaks / len(audio_peaks)
            z_pts = min(60.0, max_z * 18.0)
            align_pts = align_ratio * 40.0
            audio_align_score = float(min(100.0, z_pts + align_pts))

            if aligned_peaks > 0:
                audio_align_expl = f"Strong audio surge (Z={max_z:.1f}) aligned with speech activity ({aligned_peaks}/{len(audio_peaks)} peaks aligned)."
            else:
                audio_align_expl = f"Audio peaks detected (Z={max_z:.1f}) without aligned vocal reaction."

        # -------------------------------------------------------------
        # Component 4: signal_diversity (Weight: 15%)
        # -------------------------------------------------------------
        # Analyze category co-occurrence within 8s sliding clusters
        best_diversity_cats: List[str] = []
        best_diversity_score = 0.0

        for ev in event_stream:
            t_min = ev["t"]
            t_max = t_min + cluster_window
            cl = [e for e in event_stream if t_min <= e["t"] <= t_max]
            cats = set(e["cat"] for e in cl)

            has_g = "gaming" in cats
            has_a = "audio_peak" in cats
            has_r = ("reaction_phrase" in cats) or ("reaction_word" in cats) or ("laughter" in cats)

            if has_g and has_a and has_r:
                score_d = 100.0
                active_cats = ["gaming", "audio_peak", "reaction"]
            elif (has_g and has_a) or (has_g and has_r) or (has_a and has_r):
                score_d = 65.0
                active_cats = sorted(list(cats))
            elif cats:
                score_d = 25.0
                active_cats = sorted(list(cats))
            else:
                score_d = 0.0
                active_cats = []

            if score_d > best_diversity_score:
                best_diversity_score = score_d
                best_diversity_cats = active_cats

        diversity_score = float(best_diversity_score)
        if diversity_score >= 100.0:
            diversity_expl = "High signal diversity: concurrent gaming action, audio surge, and vocal reaction within 8s."
        elif diversity_score >= 65.0:
            diversity_expl = f"Moderate signal diversity: co-occurrence of {', '.join(best_diversity_cats)}."
        elif diversity_score > 0.0:
            diversity_expl = f"Low signal diversity: isolated {', '.join(best_diversity_cats)}."
        else:
            diversity_expl = "No co-occurring signals detected."

        # -------------------------------------------------------------
        # Component 5: causal_progression (Weight: 10%)
        # -------------------------------------------------------------
        causal_signals: List[str] = []
        best_causal_score = 0.0
        best_causal_expl = "No causal progression detected."

        if event_stream:
            for j in range(len(event_stream) - 1):
                ev1 = event_stream[j]
                ev2 = event_stream[j + 1]
                gap = ev2["t"] - ev1["t"]

                if gap <= 4.0:
                    c1 = ev1["cat"]
                    c2 = ev2["cat"]
                    is_r2 = c2 in ["reaction_phrase", "reaction_word", "laughter"]

                    if c1 == "gaming" and is_r2:
                        score_c = 75.0
                        sig_str = f"{ev1['term']}@{ev1['t']:.2f}s->{ev2['term']}@{ev2['t']:.2f}s"
                        expl_str = "Gameplay action directly followed by verbal reaction."
                    elif c1 == "audio_peak" and is_r2:
                        score_c = 70.0
                        sig_str = f"audio_peak@{ev1['t']:.2f}s->{ev2['term']}@{ev2['t']:.2f}s"
                        expl_str = "Audio intensity surge immediately followed by vocal reaction."
                    elif c1 == "gaming" and c2 == "audio_peak":
                        score_c = 65.0
                        sig_str = f"{ev1['term']}@{ev1['t']:.2f}s->audio_peak@{ev2['t']:.2f}s"
                        expl_str = "Gameplay action aligned with audio surge."
                    else:
                        score_c = 20.0
                        sig_str = f"{c1}->{c2}"
                        expl_str = "Signals present without clear causal progression."

                    if score_c > best_causal_score:
                        best_causal_score = score_c
                        causal_signals = [sig_str]
                        best_causal_expl = expl_str

        # Check for 3-stage sequence: gaming -> audio -> reaction
        for j in range(len(event_stream) - 2):
            ev1, ev2, ev3 = event_stream[j], event_stream[j + 1], event_stream[j + 2]
            if (ev3["t"] - ev1["t"]) <= 7.0:
                is_r3 = ev3["cat"] in ["reaction_phrase", "reaction_word", "laughter"]
                if ev1["cat"] == "gaming" and ev2["cat"] == "audio_peak" and is_r3:
                    best_causal_score = 100.0
                    causal_signals = [f"{ev1['term']}->audio_peak->{ev3['term']}"]
                    best_causal_expl = "Complete causal sequence: gameplay event triggered audio surge and vocal reaction."
                    break

        causal_score = float(best_causal_score)

        # -------------------------------------------------------------
        # Component 6: density (Weight: 10%)
        # -------------------------------------------------------------
        total_events_count = len(event_stream)
        rate_per_10s = (total_events_count / duration) * 10.0
        density_score = float(min(100.0, rate_per_10s * 35.0))
        density_signals = [f"{total_events_count} events across {duration:.1f}s ({rate_per_10s:.2f} events/10s)"]
        density_expl = f"Signal density: {rate_per_10s:.2f} events per 10 seconds."

        # -------------------------------------------------------------
        # Aggregate GameplayEventScore using internal weights
        # -------------------------------------------------------------
        iw = self.internal_weights
        final_gameplay_score = (
            (iw["gaming_lexical"] * gaming_score)
            + (iw["reaction_lexical"] * reaction_score)
            + (iw["audio_event_alignment"] * audio_align_score)
            + (iw["signal_diversity"] * diversity_score)
            + (iw["causal_progression"] * causal_score)
            + (iw["density"] * density_score)
        )
        final_gameplay_score = float(np.clip(round(final_gameplay_score, 1), 0.0, 100.0))

        breakdown = {
            "gaming_lexical": {
                "score": round(gaming_score, 1),
                "signals": gaming_signals_repr,
                "explanation": gaming_expl,
            },
            "reaction_lexical": {
                "score": round(reaction_score, 1),
                "signals": reaction_signals_repr,
                "explanation": reaction_expl,
            },
            "audio_event_alignment": {
                "score": round(audio_align_score, 1),
                "signals": audio_signals_repr,
                "explanation": audio_align_expl,
            },
            "signal_diversity": {
                "score": round(diversity_score, 1),
                "signals": best_diversity_cats,
                "explanation": diversity_expl,
            },
            "causal_progression": {
                "score": round(causal_score, 1),
                "signals": causal_signals,
                "explanation": best_causal_expl,
            },
            "density": {
                "score": round(density_score, 1),
                "signals": density_signals,
                "explanation": density_expl,
            },
        }

        # Reasons list based on factual components
        reasons: List[str] = []
        if gaming_score >= 60.0:
            reasons.append(gaming_expl)
        if reaction_score >= 40.0:
            reasons.append(reaction_expl)
        if audio_align_score >= 60.0:
            reasons.append(audio_align_expl)
        if causal_score >= 65.0:
            reasons.append(best_causal_expl)
        if diversity_score >= 65.0:
            reasons.append(diversity_expl)

        metrics = {
            "gaming_terms": len(gaming_signals),
            "reaction_phrases": len(reaction_phrase_signals),
            "reaction_words": len(reaction_word_signals),
            "audio_peaks": len(audio_peaks),
            "total_events": total_events_count,
        }

        # Phase 12B: Concrete Gameplay Event Scoring Integration
        if gameplay_timeline and hasattr(gameplay_timeline, "get_events_in_range"):
            concrete_score, concrete_signals, concrete_expl, concrete_metrics = self.calculate_concrete_gameplay_score(
                start_sec, end_sec, gameplay_timeline
            )
            if concrete_score > 0.0:
                legacy_score = final_gameplay_score
                combined = round(0.75 * concrete_score + 0.25 * legacy_score, 1)
                final_gameplay_score = float(np.clip(combined, 0.0, 100.0))
                if concrete_score >= 70.0:
                    final_gameplay_score = max(final_gameplay_score, concrete_score)

                breakdown["concrete_gameplay_events"] = {
                    "score": round(concrete_score, 1),
                    "signals": concrete_signals,
                    "explanation": concrete_expl,
                }
                if concrete_expl and concrete_expl not in reasons:
                    reasons.insert(0, concrete_expl)

                metrics["concrete_score"] = concrete_score
                metrics.update(concrete_metrics)

        return final_gameplay_score, metrics, reasons, breakdown

    def calculate_boundary_score(
        self,
        start_sec: float,
        end_sec: float,
        transcript_analyzer: TranscriptAnalyzer
    ) -> Tuple[float, Dict[str, Any], List[str], List[str]]:
        """
        Evaluates cut points. Returns (score, metrics, reasons, penalties).
        """
        score = 40.0
        reasons: List[str] = []
        penalties: List[str] = []
        words = transcript_analyzer.words

        clean_start = False
        for s in transcript_analyzer.sentences:
            if abs(s["start"] - start_sec) <= 0.4:
                clean_start = True
                break

        if clean_start:
            score += 25.0
            reasons.append("starts cleanly at beginning of sentence")
        else:
            for i in range(len(words) - 1):
                if abs(words[i + 1]["start"] - start_sec) <= 0.4 and (words[i + 1]["start"] - words[i]["end"] >= 0.4):
                    clean_start = True
                    score += 18.0
                    reasons.append("starts immediately after conversational pause")
                    break
            if not clean_start:
                penalties.append("start boundary cut mid-sentence")

        clean_end = False
        for s in transcript_analyzer.sentences:
            if abs(s["end"] - end_sec) <= 0.4:
                clean_end = True
                break

        if clean_end:
            score += 25.0
            reasons.append("ends cleanly at sentence completion")
        else:
            for i in range(len(words) - 1):
                if abs(words[i]["end"] - end_sec) <= 0.4 and (words[i + 1]["start"] - words[i]["end"] >= 0.4):
                    clean_end = True
                    score += 18.0
                    reasons.append("ends naturally during speech pause")
                    break
            if not clean_end:
                penalties.append("end boundary cut mid-sentence")

        duration = end_sec - start_sec
        if 38.0 <= duration <= 52.0:
            score += 10.0
            reasons.append("ideal 40-50s duration for mobile shorts pacing")
        elif 15.0 <= duration <= 30.0:
            score += 10.0
            reasons.append("ideal 15-30s quick clip pacing")
        elif 30.0 <= duration <= 90.0:
            score += 8.0
            reasons.append("ideal standard clip pacing")
        elif 90.0 < duration <= 180.0:
            score += 10.0 if duration <= 150.0 else 7.0
            reasons.append("ideal extended story pacing")

        final_boundary_score = min(100.0, max(10.0, score))
        metrics = {
            "clean_start": clean_start,
            "clean_end": clean_end,
            "duration": round(duration, 2),
        }
        return round(final_boundary_score, 1), metrics, reasons, penalties

    def calculate_context_score(
        self,
        start_sec: float,
        end_sec: float,
        audio_analysis: Dict[str, Any],
        transcript_analyzer: TranscriptAnalyzer
    ) -> Tuple[float, Dict[str, Any], List[str], List[str]]:
        """
        Flexible narrative structure model: Setup -> Tension/Buildup -> Gameplay Event -> Reaction/Payoff.
        Returns (score, metrics, reasons, penalties).
        """
        duration = max(1.0, end_sec - start_sec)
        timeline = audio_analysis.get("timeline", [])
        reasons: List[str] = []
        penalties: List[str] = []

        window_points = [p for p in timeline if start_sec <= p["t"] <= end_sec]
        if not window_points:
            return 50.0, {"peak_position_ratio": 0.5}, ["standard context structure"], []

        peak_point = max(window_points, key=lambda p: p["rms"])
        peak_time = peak_point["t"]
        peak_ratio = (peak_time - start_sec) / duration

        score = 50.0

        if 0.30 <= peak_ratio <= 0.75:
            score += 30.0
            reasons.append("well-balanced event with clear setup and reaction payoff")
        elif 0.15 <= peak_ratio < 0.30:
            score += 24.0
            reasons.append("early hook leading into sustained gameplay aftermath")
        elif 0.75 < peak_ratio <= 0.88:
            score += 24.0
            reasons.append("rising tension and build-up culminating in climax")
        elif 0.08 <= peak_ratio < 0.15:
            score += 12.0
            reasons.append("immediate action hook")
        else:
            score -= 10.0
            penalties.append("event falls very close to clip cut point")

        pre_event_points = [p["rms"] for p in window_points if p["t"] < peak_time]
        climax_points = [p["rms"] for p in window_points if abs(p["t"] - peak_time) <= 2.5]

        if pre_event_points and climax_points:
            setup_rms = float(np.mean(pre_event_points))
            climax_rms = float(np.mean(climax_points))
            if climax_rms >= (setup_rms * 1.25):
                score += 15.0
                reasons.append("measurable dynamic tension build-up leading to climax")

        words_after_peak = [w for w in transcript_analyzer.words if peak_time <= w["start"] <= end_sec]
        if len(words_after_peak) >= 4:
            score += 15.0
            reasons.append("sustained vocal reaction and dialogue following event")

        final_context_score = min(100.0, max(20.0, score))
        metrics = {
            "peak_time": round(peak_time, 2),
            "peak_position_ratio": round(peak_ratio, 2),
            "words_after_peak": len(words_after_peak),
        }
        return round(final_context_score, 1), metrics, reasons, penalties

    def rank_candidates(
        self,
        candidates: List[Tuple[float, float]],
        audio_analysis: Dict[str, Any],
        transcript_analyzer: TranscriptAnalyzer,
        video_id: str,
        video_duration: float,
        top_k: int = 10,
        gameplay_timeline: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Scores candidate windows, computes granular signals, deduplicates, and ranks.
        Enforces internal assertion that final_score equals weighted sum of component_scores.
        Integrates Phase 12A concrete gameplay events and sequence timelines.
        """
        scored_candidates: List[Dict[str, Any]] = []

        # Phase 12B: Detect if game-aware scoring weights should be used
        has_concrete_timeline = False
        if gameplay_timeline and hasattr(gameplay_timeline, "events") and getattr(gameplay_timeline, "game", "generic") != "generic":
            non_supporting = [
                e for e in gameplay_timeline.events
                if getattr(e, "status", "") != EventStatus.SUPPORTING.value
                and getattr(e, "event_type", "") not in {"reaction", "audio_spike"}
            ]
            if non_supporting:
                has_concrete_timeline = True

        if not self.custom_weights and has_concrete_timeline:
            active_weights = self._normalize_weights(GAME_AWARE_SCORING_WEIGHTS)
        else:
            active_weights = self.weights

        for start_sec, end_sec in candidates:
            dur = round(end_sec - start_sec, 2)
            if dur <= 0:
                continue

            # Module 1: Audio Score
            audio_score, audio_metrics, audio_reasons = self.audio_analyzer.score_interval(
                audio_analysis, start_sec, end_sec
            )

            # Module 2: Transcript Score
            trans_score, trans_metrics, trans_reasons = transcript_analyzer.score_interval(
                start_sec, end_sec
            )

            # Module 3: Gameplay Event Score with granular breakdown (integrates Phase 12B concrete game events)
            event_score, event_metrics, event_reasons, event_breakdown = self.calculate_gameplay_event_score(
                start_sec, end_sec, audio_analysis, transcript_analyzer, gameplay_timeline=gameplay_timeline
            )

            # Module 4: Context Score
            context_score, context_metrics, context_reasons, context_penalties = self.calculate_context_score(
                start_sec, end_sec, audio_analysis, transcript_analyzer
            )

            # Module 5: Boundary Score
            bound_score, bound_metrics, bound_reasons, bound_penalties = self.calculate_boundary_score(
                start_sec, end_sec, transcript_analyzer
            )

            # Calculate composite score using normalized active weights
            w = active_weights
            composite_score = (
                (w.get("audio", 0.25) * audio_score)
                + (w.get("transcript", 0.20) * trans_score)
                + (w.get("gameplay_event", 0.25) * event_score)
                + (w.get("context", 0.20) * context_score)
                + (w.get("boundary", 0.10) * bound_score)
            )
            composite_score = round(composite_score, 1)

            # Internal consistency assertion
            comp_scores = {
                "audio": audio_score,
                "transcript": trans_score,
                "gameplay_event": event_score,
                "context": context_score,
                "boundary": bound_score,
            }
            expected_final = sum(w[k] * comp_scores[k] for k in w if k in comp_scores)
            assert abs(composite_score - round(expected_final, 1)) <= 0.15, (
                f"Score calculation mismatch for window {start_sec}-{end_sec}: "
                f"got {composite_score}, expected {expected_final:.2f}"
            )

            all_penalties = context_penalties + bound_penalties

            # Extract distinct signals detected
            detected_signals = list(dict.fromkeys(
                event_breakdown["gaming_lexical"]["signals"]
                + event_breakdown["reaction_lexical"]["signals"]
                + event_breakdown["audio_event_alignment"]["signals"]
            ))

            ranking_reasons = list(dict.fromkeys(
                event_reasons[:2] + audio_reasons[:1] + trans_reasons[:1] + context_reasons[:1] + bound_reasons[:1]
            ))
            if not ranking_reasons:
                ranking_reasons.append("balanced audio and speech continuity")

            # Phase 12A: Attach concrete gameplay events & sequences if timeline is provided
            gp_events_list = []
            gp_seqs_list = []
            if gameplay_timeline and hasattr(gameplay_timeline, "get_events_in_range"):
                w_events = gameplay_timeline.get_events_in_range(start_sec, end_sec)
                gp_events_list = [e.to_dict() for e in w_events]
                gp_seqs_list = [
                    e.to_dict() for e in w_events
                    if e.event_type in ["multi_kill", "ace", "ace_candidate", "rapid_kill_sequence", "clutch_candidate"]
                ]
                # Prepend high-signal event explanations to ranking reasons
                high_sig = [e for e in w_events if e.status == "confirmed" or e.confidence >= 0.75]
                for h in reversed(high_sig[:2]):
                    if h.explanation and h.explanation not in ranking_reasons:
                        ranking_reasons.insert(0, h.explanation)

            tier = get_duration_tier(dur)
            narrative = get_narrative_structure(tier)

            candidate_obj = {
                "start": start_sec,
                "end": end_sec,
                "duration": dur,
                "duration_tier": tier,
                "narrative_structure": narrative,
                "score": composite_score,
                "final_score": composite_score,
                "active_weights": active_weights,
                "scores": comp_scores,
                "component_scores": comp_scores,
                "gameplay_event_breakdown": event_breakdown,
                "gameplay_events": gp_events_list,
                "gameplay_sequences": gp_seqs_list,
                "gameplay_event_score": comp_scores.get("gameplay_event", 0.0),
                "signals": {
                    "audio_peaks": audio_metrics.get("peak_count", 0),
                    "reaction_phrases": trans_metrics.get("reaction_phrases", 0),
                    "gaming_terms": event_metrics.get("gaming_terms", 0),
                    "speech_density": trans_metrics.get("speech_density", 0.0),
                },
                "detected_signals": detected_signals,
                "ranking_reasons": ranking_reasons,
                "reasons": ranking_reasons,
                "penalties": all_penalties,
            }
            scored_candidates.append(candidate_obj)

        # Sort all candidates by score descending
        scored_candidates.sort(key=lambda c: c["final_score"], reverse=True)

        # Deduplicate overlapping candidates using IoU & overlap duration
        deduplicated: List[Dict[str, Any]] = []
        for cand in scored_candidates:
            is_duplicate = False
            for accepted in deduplicated:
                inter_start = max(cand["start"], accepted["start"])
                inter_end = min(cand["end"], accepted["end"])
                inter = max(0.0, inter_end - inter_start)

                union = (
                    (cand["end"] - cand["start"])
                    + (accepted["end"] - accepted["start"])
                    - inter
                )
                iou = inter / union if union > 0 else 0.0

                if iou >= IOU_DEDUPLICATION_THRESHOLD or inter >= MAX_OVERLAP_SECONDS:
                    is_duplicate = True
                    break

            if not is_duplicate:
                deduplicated.append(cand)
            if len(deduplicated) >= top_k:
                break

        # Assign ranks
        for idx, item in enumerate(deduplicated, start=1):
            item["rank"] = idx

        return {
            "video_id": video_id,
            "duration": round(video_duration, 2),
            "scoring_version": "phase12b-game-aware" if has_concrete_timeline else "phase2.1.1-v1",
            "active_weights": active_weights,
            "weights": active_weights,
            "candidates": deduplicated,
        }
