"""Live candidate discovery, cross-segment boundary merging, and Creator Quality gating."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from backend.app.config import (
    MIN_CANDIDATE_DURATION,
    MAX_CANDIDATE_DURATION,
    CREATOR_GATE_PASS_SCORE,
    CREATOR_GATE_REVIEW_SCORE,
)
from backend.app.pipeline.transcriber import AudioTranscriber
from backend.app.pipeline.audio_analyzer import AudioAnalyzer
from backend.app.pipeline.transcript_analyzer import TranscriptAnalyzer
from backend.app.pipeline.candidate_generator import CandidateGenerator
from backend.app.pipeline.candidate_ranker import CandidateRanker
from backend.app.pipeline.creator_quality import CreatorQualityEvaluator
from backend.app.pipeline.long_stream.temporal_deduper import TemporalDeduper, compute_overlap
from backend.app.pipeline.live.models import (
    LiveSegment,
    LiveCandidate,
    LiveCandidateStatus,
)


class LiveCandidateEngine:
    """Processes live segments, discovers gaming moments, and merges cross-segment candidates."""

    def __init__(self):
        self.transcriber = AudioTranscriber()
        self.audio_analyzer = AudioAnalyzer()
        self.candidate_generator = CandidateGenerator(
            min_duration=MIN_CANDIDATE_DURATION,
            max_duration=MAX_CANDIDATE_DURATION,
        )
        self.candidate_ranker = CandidateRanker()
        self.creator_evaluator = CreatorQualityEvaluator()
        self.temporal_deduper = TemporalDeduper()

    def analyze_segment(
        self,
        segment: LiveSegment,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Runs speech-to-text, audio volume analysis, and event scoring on a single rolling segment.
        Returns (detected_candidates_with_global_timestamps, transcript_data).
        """
        wav_path = Path(segment.audio_file)
        if not wav_path.exists():
            return [], {}

        # 1. Transcribe audio segment
        transcript_data = self.transcriber.transcribe(wav_path)

        # 2. Analyze audio intensity & volume peaks
        audio_analysis = self.audio_analyzer.analyze(wav_path)
        transcript_analyzer = TranscriptAnalyzer(transcript_data)

        # 3. Candidate boundary generation & ranking
        effective_dur = segment.duration if segment.duration > 0 else audio_analysis.get("duration", 0.0)
        raw_candidates = self.candidate_generator.generate_candidates(
            video_duration=effective_dur,
            audio_analysis=audio_analysis,
            transcript_analyzer=transcript_analyzer,
        )

        ranked = self.candidate_ranker.rank_candidates(
            candidates=raw_candidates,
            audio_analysis=audio_analysis,
            transcript_analyzer=transcript_analyzer,
            video_id=f"seg_{segment.segment_id}",
            video_duration=effective_dur,
            top_k=8,
        )

        candidates = ranked.get("candidates", [])

        # 4. Map local segment coordinates to stable global session timestamps
        global_candidates: List[Dict[str, Any]] = []
        for c in candidates:
            l_start = float(c.get("start", 0.0))
            l_end = float(c.get("end", effective_dur))
            g_start = round(segment.global_start + l_start, 2)
            g_end = round(segment.global_start + l_end, 2)
            dur = round(g_end - g_start, 2)

            global_candidates.append({
                "start": g_start,
                "end": g_end,
                "duration": dur,
                "final_score": float(c.get("final_score", 50.0)),
                "score_breakdown": c.get("score_breakdown", {}),
                "gameplay_event": c.get("gameplay_event"),
                "secondary_events": c.get("secondary_events", []),
                "strongest_reaction": c.get("strongest_reaction"),
                "tone": c.get("tone"),
                "signals": c.get("signals", {}),
                "detected_signals": c.get("detected_signals", []),
                "source_segments": [segment.segment_id],
                "local_start": l_start,
                "local_end": l_end,
            })

        return global_candidates, transcript_data

    def merge_and_update_candidates(
        self,
        existing_pool: List[LiveCandidate],
        new_candidates: List[Dict[str, Any]],
        segment: LiveSegment,
    ) -> Tuple[List[LiveCandidate], List[str]]:
        """
        Merges cross-segment candidates spanning boundary overlaps and deduplicates overlapping moments.
        Returns (updated_candidate_pool, list_of_event_logs).
        """
        events_logged: List[str] = []
        pool: List[LiveCandidate] = list(existing_pool)
        next_cid = max([c.candidate_id for c in pool], default=0) + 1

        for new_c in new_candidates:
            merged = False

            # Check for cross-segment narrative continuity with existing candidates
            for ex in pool:
                if ex.status == LiveCandidateStatus.REJECTED:
                    continue

                inter, union, iou = compute_overlap(
                    {"start": ex.global_start, "end": ex.global_end},
                    {"start": new_c["start"], "end": new_c["end"]},
                )

                # Boundary connection condition:
                # If existing candidate ends within the overlap region and new candidate starts in the overlap region
                is_boundary_connected = (
                    abs(ex.global_end - new_c["start"]) <= 8.0 or
                    (ex.global_end >= segment.global_start and new_c["start"] <= ex.global_end + 5.0)
                )

                if iou >= 0.35 or inter >= 12.0 or is_boundary_connected:
                    # Same candidate event spanning segments: merge boundaries
                    old_dur = ex.duration
                    merged_start = min(ex.global_start, new_c["start"])
                    merged_end = max(ex.global_end, new_c["end"])
                    merged_dur = round(merged_end - merged_start, 2)

                    # Clamp merged duration to max allowed Short duration (default 60s)
                    if merged_dur > MAX_CANDIDATE_DURATION:
                        # Anchor to the climax / highest score end
                        if new_c["final_score"] >= ex.score:
                            merged_start = max(merged_start, merged_end - MAX_CANDIDATE_DURATION)
                        else:
                            merged_end = min(merged_end, merged_start + MAX_CANDIDATE_DURATION)
                        merged_dur = round(merged_end - merged_start, 2)

                    ex.global_start = round(merged_start, 2)
                    ex.global_end = round(merged_end, 2)
                    ex.duration = merged_dur
                    ex.score = max(ex.score, new_c["final_score"])
                    if segment.segment_id not in ex.source_segments:
                        ex.source_segments.append(segment.segment_id)
                        ex.source_segments.sort()

                    if new_c.get("gameplay_event") and not ex.event:
                        ex.event = new_c["gameplay_event"]
                    if new_c.get("strongest_reaction") and not ex.reaction:
                        ex.reaction = new_c["strongest_reaction"]
                    sigs = new_c.get("signals")
                    if isinstance(sigs, list) and isinstance(ex.signals, list):
                        for sig in sigs:
                            if sig not in ex.signals:
                                ex.signals.append(sig)
                    elif isinstance(sigs, dict):
                        ex.signals = sigs
                    for d_sig in new_c.get("detected_signals", []):
                        if d_sig not in ex.detected_signals:
                            ex.detected_signals.append(d_sig)

                    ex.updated_at = datetime.now(timezone.utc).isoformat()
                    merged = True
                    events_logged.append(
                        f"Candidate #{ex.candidate_id} merged across Segment {segment.segment_id} (Duration: {old_dur:.1f}s → {merged_dur:.1f}s, Score: {ex.score:.1f})"
                    )
                    break

            if not merged:
                # Fresh candidate discovered
                cand_item = LiveCandidate(
                    candidate_id=next_cid,
                    global_start=new_c["start"],
                    global_end=new_c["end"],
                    duration=new_c["duration"],
                    score=new_c["final_score"],
                    status=LiveCandidateStatus.DETECTED,
                    source_segments=new_c["source_segments"],
                    event=new_c.get("gameplay_event"),
                    secondary_events=new_c.get("secondary_events", []),
                    reaction=new_c.get("strongest_reaction"),
                    tone=new_c.get("tone"),
                    signals=new_c.get("signals", {}),
                    detected_signals=new_c.get("detected_signals", []),
                    score_breakdown=new_c.get("score_breakdown", {}),
                )
                pool.append(cand_item)
                next_cid += 1
                events_logged.append(
                    f"New candidate #{cand_item.candidate_id} detected in Segment {segment.segment_id} at {int(cand_item.global_start // 60):02d}:{int(cand_item.global_start % 60):02d} (Score: {cand_item.score:.1f})"
                )

        # Evaluate Creator Quality and Quality Gating across active pool
        self._evaluate_quality_gating(pool)

        return pool, events_logged

    def _evaluate_quality_gating(self, candidates: List[LiveCandidate]) -> None:
        """Applies Phase 7E Creator Quality evaluation and sets candidate readiness."""
        cand_dicts = [c.to_candidate_dict() for c in candidates]

        for idx, cand in enumerate(candidates):
            if cand.status in (LiveCandidateStatus.RENDERING, LiveCandidateStatus.COMPLETED):
                continue

            pub_eval = self.creator_evaluator.evaluate(
                candidate=cand_dicts[idx],
                all_candidates=cand_dicts,
            )
            cand.publishability = pub_eval

            rec = pub_eval.get("recommendation", "review")
            score = pub_eval.get("score", cand.score)

            if rec == "reject" or score < CREATOR_GATE_REVIEW_SCORE:
                cand.status = LiveCandidateStatus.REJECTED
            elif rec == "publish" and score >= CREATOR_GATE_PASS_SCORE:
                cand.status = LiveCandidateStatus.PUBLISH_READY
            else:
                cand.status = LiveCandidateStatus.REVIEW
