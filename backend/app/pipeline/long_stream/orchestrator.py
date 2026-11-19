"""Long Stream Orchestrator: coordinates chunking, resume, global ranking, dedup, and quality gating."""

import gc
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from backend.app.config import (
    LONG_STREAM_THRESHOLD_SEC,
    CHUNK_DURATION_SEC,
    CHUNK_OVERLAP_SEC,
    MIN_CHUNK_DURATION_SEC,
    QUALITY_GATE_MIN_SCORE,
    QUALITY_GATE_STRONG_SCORE,
)
from .chunk_planner import ChunkPlanner, ChunkPlan, is_long_stream
from .chunk_store import ChunkStore
from .chunk_processor import ChunkProcessor, check_disk_space
from .global_ranker import GlobalRanker
from .temporal_deduper import TemporalDeduper
from .diversity_selector import DiversitySelector
from .quality_gate import QualityGate


def format_source_position(seconds: float) -> str:
    """Formats seconds into HH:MM:SS string."""
    s = int(seconds)
    m = s // 60
    rem_s = s % 60
    h = m // 60
    rem_m = m % 60
    if h > 0:
        return f"{h:02d}:{rem_m:02d}:{rem_s:02d}"
    return f"{rem_m:02d}:{rem_s:02d}"


class LongStreamOrchestrator:
    """Coordinates end-to-end processing of multi-hour streams."""

    def __init__(
        self,
        threshold: float = LONG_STREAM_THRESHOLD_SEC,
        chunk_duration: float = CHUNK_DURATION_SEC,
        overlap: float = CHUNK_OVERLAP_SEC,
        min_chunk_duration: float = MIN_CHUNK_DURATION_SEC,
    ):
        self.planner = ChunkPlanner(
            threshold=threshold,
            chunk_duration=chunk_duration,
            overlap=overlap,
            min_chunk_duration=min_chunk_duration,
        )
        self.processor = ChunkProcessor()
        self.global_ranker = GlobalRanker()
        self.deduper = TemporalDeduper()
        self.diversity_selector = DiversitySelector()
        self.quality_gate = QualityGate()

    def process(
        self,
        video_id: str,
        source_media: Path,
        source_duration: float,
        project_dir: Path,
        temp_dir: Path,
        settings: Optional[Dict[str, Any]] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Executes full staged long-stream intelligence pipeline."""
        settings = settings or {}
        num_shorts_mode = settings.get("num_shorts_mode", "auto")
        requested_count = int(settings.get("num_shorts", 5))

        def emit_event(event_type: str, data: Dict[str, Any]) -> None:
            if event_callback:
                payload = dict(data)
                payload["event"] = event_type
                payload["video_id"] = video_id
                event_callback(payload)

        # 1. Storage & Disk Space Check
        check_disk_space(temp_dir)
        store = ChunkStore(project_dir)

        # 2. Chunk Planning
        plans = self.planner.plan(source_duration)
        total_chunks = len(plans)

        store.init_manifest(
            plans=plans,
            video_id=video_id,
            source_duration=source_duration,
            chunk_duration=self.planner.chunk_duration,
            overlap=self.planner.overlap,
        )

        reconciled_plans, reused_count = store.get_resumable_plan(plans)

        emit_event("long_stream_started", {
            "source_duration": source_duration,
            "total_chunks": total_chunks,
            "chunks_reused": reused_count,
            "chunks_to_process": total_chunks - reused_count,
            "stage": "Long-Stream Chunking",
            "message": f"Planned {total_chunks} stream chunks ({reused_count} already cached).",
        })

        # 3. Sequential Chunk Processing
        for idx, plan in enumerate(reconciled_plans, start=1):
            if plan.status == "completed":
                emit_event("chunk_completed", {
                    "chunk_id": plan.chunk_id,
                    "index": idx,
                    "total_chunks": total_chunks,
                    "reused": True,
                    "stage": "Chunk Analysis",
                    "message": f"Reused cached results for {plan.chunk_id} ({idx}/{total_chunks}).",
                })
                continue

            emit_event("chunk_started", {
                "chunk_id": plan.chunk_id,
                "index": idx,
                "total_chunks": total_chunks,
                "source_start": plan.source_start,
                "source_end": plan.source_end,
                "stage": f"Analyzing Chunk {idx}/{total_chunks}",
                "message": f"Processing {plan.chunk_id} [{format_source_position(plan.source_start)} - {format_source_position(plan.source_end)}]",
            })

            try:
                result = self.processor.process_chunk(
                    source_media=source_media,
                    plan=plan,
                    temp_dir=temp_dir,
                    video_id=video_id,
                )
                store.save_chunk_result(plan.chunk_id, result)
                plan.status = "completed"

                emit_event("chunk_completed", {
                    "chunk_id": plan.chunk_id,
                    "index": idx,
                    "total_chunks": total_chunks,
                    "candidates_in_chunk": len(result.get("candidates", [])),
                    "stage": "Chunk Completed",
                    "message": f"Finished {plan.chunk_id}: {len(result.get('candidates', []))} moments found.",
                })

            except Exception as e:
                store.mark_chunk_failed(plan.chunk_id, str(e))
                plan.status = "failed"
                emit_event("chunk_failed", {
                    "chunk_id": plan.chunk_id,
                    "index": idx,
                    "total_chunks": total_chunks,
                    "error": str(e),
                    "stage": "Chunk Warning",
                    "message": f"Chunk {plan.chunk_id} failed: {str(e)}",
                })

            gc.collect()

        # 4. Global Candidate Aggregation
        raw_candidates = store.collect_all_candidates()

        emit_event("global_ranking_started", {
            "total_raw_candidates": len(raw_candidates),
            "stage": "Global Ranking",
            "message": f"Ranking {len(raw_candidates)} candidate moments across all stream chunks...",
        })

        # 5. Global Ranking & Score Normalization
        ranked = self.global_ranker.calibrate_and_rank(raw_candidates)

        # 6. Temporal Deduplication
        emit_event("deduplication_started", {
            "stage": "Deduplication",
            "message": "Deduplicating overlapping chunk boundaries and nested moments...",
        })
        deduped = self.deduper.deduplicate(ranked)

        # 7. Diversity Selection
        emit_event("diversity_selection_started", {
            "stage": "Diversity Balancing",
            "message": "Balancing temporal distribution and narrative event categories...",
        })
        target_diversity_pool = max(requested_count * 4, 25)
        diverse_pool = self.diversity_selector.select_diverse(deduped, target_diversity_pool)

        # 8. Quality Gate
        emit_event("quality_gate_started", {
            "stage": "Quality Gating",
            "message": "Evaluating climax score gaps and filtering quality-gated recommendations...",
        })
        recommended_shorts, explanation = self.quality_gate.evaluate(
            candidates=diverse_pool,
            num_shorts_mode=num_shorts_mode,
            requested_count=requested_count,
        )

        # Annotate candidates with source position strings and final rank
        from backend.app.pipeline.creator_quality import CreatorQualityEvaluator
        creator_evaluator = CreatorQualityEvaluator()

        for idx, c in enumerate(diverse_pool, start=1):
            c["rank"] = idx
            c["global_rank"] = idx
            c["source_position_str"] = format_source_position(c["start"])
            c["selected"] = c in recommended_shorts
            if "publishability" not in c:
                c["publishability"] = creator_evaluator.evaluate(c, all_candidates=diverse_pool)

        manifest = store.load_manifest() or {}
        completed_chunks_count = sum(1 for c in manifest.get("chunks", []) if c.get("status") == "completed")
        failed_chunks_count = sum(1 for c in manifest.get("chunks", []) if c.get("status") == "failed")
        strong_count = sum(1 for c in diverse_pool if c.get("final_score", 0) >= QUALITY_GATE_STRONG_SCORE)

        long_stream_info = {
            "source_duration": round(source_duration, 2),
            "chunks_processed": completed_chunks_count,
            "total_chunks": total_chunks,
            "chunks_reused": reused_count,
            "chunks_failed": failed_chunks_count,
            "candidates_detected": len(raw_candidates),
            "deduplicated_candidates": len(deduped),
            "strong_moments": strong_count,
            "recommended_shorts": len(recommended_shorts),
            "quality_gate_reason": explanation,
        }

        emit_event("candidates_ready", {
            "stage": "Analysis Complete",
            "message": explanation,
            "long_stream_info": long_stream_info,
        })

        return {
            "status": "candidates_ready",
            "duration": round(source_duration, 2),
            "long_stream": True,
            "long_stream_info": long_stream_info,
            "candidates": diverse_pool,
            "selected_candidate_ids": [c["rank"] for c in recommended_shorts],
            "quality_gate_reason": explanation,
        }
