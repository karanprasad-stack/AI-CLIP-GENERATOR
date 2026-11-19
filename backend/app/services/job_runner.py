"""Job Runner: executes pipeline phases in background threads with real-time SSE progress reporting."""

import threading
import traceback
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from backend.app.pipeline.pipeline import run_pipeline, PipelineError
from backend.app.services.project_manager import ProjectManager


def run_analysis_task(
    project_id: str,
    project_manager: ProjectManager,
    settings: Optional[Dict[str, Any]] = None,
) -> None:
    """Executes Phase 1 & 2 analysis to discover and rank gaming candidates."""
    proj = project_manager.get_project(project_id)
    if not proj:
        return

    url = proj["url"]
    merged_settings = proj.get("settings", {})
    if settings:
        merged_settings.update(settings)

    # 5 steps in Phase 2
    TOTAL_ANALYSIS_STEPS = 5

    def progress_cb(step: int, message: str) -> None:
        if step > TOTAL_ANALYSIS_STEPS:
            return
        stage_map = {
            1: "Downloading Metadata",
            2: "Audio Extraction",
            3: "Whisper Transcription",
            4: "Signal Analysis",
            5: "Candidate Ranking",
        }
        stage = stage_map.get(step, "Analyzing Video")
        project_manager.update_project_progress(
            project_id=project_id,
            step=step,
            total_steps=TOTAL_ANALYSIS_STEPS,
            stage=stage,
            message=message,
        )

    cancel_event = threading.Event()
    with project_manager._lock:
        project_manager._cancel_flags[project_id] = cancel_event

    try:
        project_manager.update_project_progress(
            project_id=project_id,
            step=1,
            total_steps=TOTAL_ANALYSIS_STEPS,
            stage="Initializing",
            message="Starting video analysis...",
        )
        with project_manager._lock:
            if project_id in project_manager._projects:
                project_manager._projects[project_id]["status"] = "analyzing"
                project_manager._projects[project_id]["error"] = None
                project_manager._save_projects()

        def ls_event_cb(evt: Dict[str, Any]) -> None:
            stage = evt.get("stage", "Long-Stream Intelligence")
            msg = evt.get("message", "")
            ls_data = evt.get("long_stream_info")

            with project_manager._lock:
                proj_ref = project_manager._projects.get(project_id)
                if proj_ref:
                    if ls_data:
                        proj_ref["long_stream_info"].update(ls_data)
                    elif "total_chunks" in evt:
                        proj_ref["long_stream_info"]["total_chunks"] = evt.get("total_chunks", 1)
                        if "index" in evt:
                            proj_ref["long_stream_info"]["chunks_processed"] = evt.get("index", 1)

            project_manager.update_project_progress(
                project_id=project_id,
                step=4,
                total_steps=TOTAL_ANALYSIS_STEPS,
                stage=stage,
                message=msg,
            )

        result = run_pipeline(
            url=url,
            phase=2,
            progress_callback=progress_cb,
            settings=merged_settings,
            long_stream_event_callback=ls_event_cb,
            cancel_event=cancel_event,
        )

        candidates = result.get("candidates", [])
        duration = float(result.get("duration", 0.0))
        is_long = result.get("long_stream", False)

        if is_long and result.get("long_stream_info"):
            ls_info = result["long_stream_info"]
            top_ids = result.get("selected_candidate_ids", [c.get("rank", idx) for idx, c in enumerate(candidates[:5], 1)])
            summary_msg = result.get("quality_gate_reason") or f"Detected {len(candidates)} candidates across {ls_info.get('total_chunks', 1)} chunks."
        else:
            from backend.app.pipeline.creator_quality import CreatorQualityEvaluator
            evaluator = CreatorQualityEvaluator()
            for cand in candidates:
                if "publishability" not in cand:
                    cand["publishability"] = evaluator.evaluate(cand, all_candidates=candidates)

            publishable_cands = [c for c in candidates if c.get("publishability", {}).get("recommendation") == "publish"]
            strong_moments = sum(1 for c in candidates if c.get("final_score", 0) >= 70)
            recommended = min(len(publishable_cands) if publishable_cands else len(candidates), 5)
            top_ids = [c.get("rank", idx) for idx, c in enumerate(publishable_cands[:recommended] if publishable_cands else candidates[:recommended], 1)]
            ls_info = {
                "source_duration": duration,
                "chunks_processed": 1,
                "total_chunks": 1,
                "candidates_detected": len(candidates),
                "strong_moments": strong_moments,
                "recommended_shorts": recommended,
            }
            summary_msg = f"Detected {len(candidates)} candidates ({len(publishable_cands)} ready to publish, {strong_moments} strong climaxes)."

        with project_manager._lock:
            p = project_manager._projects.get(project_id)
            if p:
                p["status"] = "candidates_ready"
                p["title"] = result.get("title", p["title"])
                p["uploader"] = result.get("uploader", p["uploader"])
                p["duration"] = duration
                p["language"] = result.get("language", "en")
                p["candidates"] = candidates
                p["selected_candidate_ids"] = top_ids
                p["long_stream_info"] = ls_info
                project_manager._decorate_project(p)
                p["progress"]["step"] = TOTAL_ANALYSIS_STEPS
                p["progress"]["percent"] = 100
                p["progress"]["stage"] = "Analysis Complete"
                p["progress"]["message"] = summary_msg
                p["updated_at"] = datetime.now(timezone.utc).isoformat()
                project_manager._save_projects()

        project_manager.update_project_progress(
            project_id=project_id,
            step=TOTAL_ANALYSIS_STEPS,
            total_steps=TOTAL_ANALYSIS_STEPS,
            stage="Analysis Complete",
            message=summary_msg,
        )

    except Exception as e:
        err_msg = str(e)
        stack = traceback.format_exc()
        is_cancelled = cancel_event.is_set() or "cancelled" in err_msg.lower()

        with project_manager._lock:
            p = project_manager._projects.get(project_id)
            if p:
                p["status"] = "cancelled" if is_cancelled else "failed"
                p["error"] = None if is_cancelled else {
                    "code": "ANALYSIS_FAILED",
                    "summary": f"Video analysis failed: {err_msg}",
                    "details": stack,
                    "recoverable": True,
                }
                p["updated_at"] = datetime.now(timezone.utc).isoformat()
                project_manager._save_projects()

        project_manager.update_project_progress(
            project_id=project_id,
            step=0,
            total_steps=TOTAL_ANALYSIS_STEPS,
            stage="Cancelled" if is_cancelled else "Failed",
            message="Job was cancelled by user." if is_cancelled else f"Analysis failed: {err_msg}",
        )
    finally:
        with project_manager._lock:
            project_manager._cancel_flags.pop(project_id, None)


def run_render_task(
    project_id: str,
    project_manager: ProjectManager,
    selected_candidate_ids: Optional[List[int]] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> None:
    """Executes full rendering pipeline (Phases 3-6B) on selected candidates."""
    proj = project_manager.get_project(project_id)
    if not proj:
        return

    url = proj["url"]
    merged_settings = proj.get("settings", {})
    if settings:
        merged_settings.update(settings)

    if selected_candidate_ids:
        project_manager.update_selected_candidates(project_id, selected_candidate_ids)

    sel_ids = proj.get("selected_candidate_ids", [])
    top_n = len(sel_ids) if sel_ids else merged_settings.get("num_shorts", 5)

    TOTAL_RENDER_STEPS = 23

    def progress_cb(step: int, message: str) -> None:
        stage = "Rendering Shorts"
        if step <= 5:
            stage = "Validating Analysis"
        elif step <= 9:
            stage = "Vertical 9:16 Cropping"
        elif step <= 12:
            stage = "Burning Subtitles & Emojis"
        elif step <= 15:
            stage = "Applying Visual Effects"
        elif step <= 19:
            stage = "Polishing Audio & SFX"
        elif step <= 22:
            stage = "Packaging & Thumbnails"
        else:
            stage = "Finalizing"

        current_cand = 0
        if "candidate " in message.lower():
            try:
                remainder = message.lower().split("candidate ")[1]
                cand_str = remainder.split("/")[0].split(" ")[0]
                current_cand = int(cand_str)
            except Exception:
                pass

        project_manager.update_project_progress(
            project_id=project_id,
            step=step,
            total_steps=TOTAL_RENDER_STEPS,
            stage=stage,
            message=message,
            current_candidate=current_cand,
        )

    cancel_event = threading.Event()
    with project_manager._lock:
        project_manager._cancel_flags[project_id] = cancel_event

    try:
        with project_manager._lock:
            if project_id in project_manager._projects:
                project_manager._projects[project_id]["status"] = "rendering"
                project_manager._projects[project_id]["error"] = None
                project_manager._save_projects()

        result = run_pipeline(
            url=url,
            phase="6b",
            top_n=top_n,
            layout=merged_settings.get("layout", "auto"),
            captions=merged_settings.get("captions", True),
            emoji=merged_settings.get("emoji", True),
            effects=merged_settings.get("effects", True),
            audio=merged_settings.get("audio", True),
            sfx=merged_settings.get("sfx", True),
            ducking=merged_settings.get("ducking", True),
            thumbnail=merged_settings.get("thumbnail", True),
            metadata_enabled=merged_settings.get("metadata_enabled", True),
            llm=merged_settings.get("llm", False),
            settings=merged_settings,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
        )

        packages = result.get("published_packages", [])

        with project_manager._lock:
            p = project_manager._projects.get(project_id)
            if p:
                p["status"] = "completed"
                p["published_packages"] = packages
                project_manager._decorate_project(p)
                p["progress"]["step"] = TOTAL_RENDER_STEPS
                p["progress"]["percent"] = 100
                p["progress"]["stage"] = "Completed"
                p["progress"]["message"] = f"Successfully generated {len(packages)} YouTube Shorts!"
                p["updated_at"] = datetime.now(timezone.utc).isoformat()
                project_manager._save_projects()

        project_manager.update_project_progress(
            project_id=project_id,
            step=TOTAL_RENDER_STEPS,
            total_steps=TOTAL_RENDER_STEPS,
            stage="Completed",
            message=f"All {len(packages)} publishing packages generated successfully.",
        )

    except Exception as e:
        err_msg = str(e)
        stack = traceback.format_exc()
        is_cancelled = cancel_event.is_set() or "cancelled" in err_msg.lower()

        with project_manager._lock:
            p = project_manager._projects.get(project_id)
            if p:
                p["status"] = "cancelled" if is_cancelled else "failed"
                p["error"] = None if is_cancelled else {
                    "code": "RENDER_FAILED",
                    "summary": f"Video rendering failed: {err_msg}",
                    "details": stack,
                    "recoverable": True,
                }
                p["updated_at"] = datetime.now(timezone.utc).isoformat()
                project_manager._save_projects()

        project_manager.update_project_progress(
            project_id=project_id,
            step=0,
            total_steps=TOTAL_RENDER_STEPS,
            stage="Cancelled" if is_cancelled else "Failed",
            message="Job was cancelled by user." if is_cancelled else f"Rendering failed: {err_msg}",
        )
    finally:
        with project_manager._lock:
            project_manager._cancel_flags.pop(project_id, None)
