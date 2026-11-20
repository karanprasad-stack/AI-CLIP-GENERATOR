"""API Router for AI Gaming Shorts Generator Dashboard."""

import asyncio
import json
import os
import re
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Response
from fastapi.responses import StreamingResponse, FileResponse
from starlette.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_404_NOT_FOUND

from backend.app.api.schemas import (
    ProjectCreateRequest,
    ProcessingSettingsSchema,
    CandidateSelectionRequest,
    MetadataUpdateRequest,
    ProjectDetailResponse,
    ProjectSummaryResponse,
    PlatformConnectRequest,
    PublishRequestSchema,
    PublishResultResponse,
    PlatformStatusResponse,
    PublishHistoryEntryResponse,
)
from backend.app.pipeline.publishing import (
    PublisherRegistry,
    PublishHistoryStore,
    PublishRequest,
)
from backend.app.services.project_manager import ProjectManager
from backend.app.services.job_runner import run_analysis_task, run_render_task
from backend.app.services.health import HealthChecker

router = APIRouter(prefix="/api")
project_manager = ProjectManager()
publisher_registry = PublisherRegistry()
publish_history_store = PublishHistoryStore(base_output_dir=project_manager.output_dir)

PROJECT_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


def validate_pid(project_id: str) -> None:
    """Validate project ID against path traversal or malicious characters."""
    if not project_id or not PROJECT_ID_REGEX.match(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID format")


@router.get("/health")
def api_health():
    """System health check endpoint."""
    return HealthChecker.get_full_health(project_manager.output_dir)


@router.get("/projects", response_model=List[ProjectSummaryResponse])
def list_projects():
    """Returns summary list of all projects in local history."""
    projs = project_manager.list_projects()
    summaries = []
    for p in projs:
        summaries.append(
            ProjectSummaryResponse(
                id=p["id"],
                video_id=p["video_id"],
                url=p["url"],
                title=p["title"],
                uploader=p["uploader"],
                duration=p["duration"],
                status=p["status"],
                source_type=p.get("source_type", "normal_video"),
                created_at=p["created_at"],
                updated_at=p["updated_at"],
                candidates_count=len(p.get("candidates", [])),
                shorts_count=len(p.get("published_packages", [])),
                percent=p.get("progress", {}).get("percent", 0),
            )
        )
    return summaries


@router.post("/projects", response_model=ProjectDetailResponse, status_code=HTTP_201_CREATED)
def create_project(req: ProjectCreateRequest):
    """Creates a new project record initialized with settings."""
    settings_dict = (
        req.settings.model_dump()
        if hasattr(req.settings, "model_dump")
        else req.settings.dict()
    ) if req.settings else None
    proj = project_manager.create_project(
        url=req.url,
        settings=settings_dict,
        title=req.title,
        source_type=req.source_type or "normal_video",
    )
    return proj


@router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
def get_project(project_id: str):
    """Returns complete state for a specific project."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    return proj


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    """Deletes project from registry and local disk."""
    validate_pid(project_id)
    success = project_manager.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    return {"status": "deleted", "project_id": project_id}


@router.post("/projects/{project_id}/analyze")
def start_analysis(
    project_id: str,
    background_tasks: BackgroundTasks,
    settings: Optional[ProcessingSettingsSchema] = None,
):
    """Starts Phase 1 & 2 analysis in background thread."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    settings_dict = (
        settings.model_dump()
        if hasattr(settings, "model_dump")
        else settings.dict()
    ) if settings else None
    t = threading.Thread(
        target=run_analysis_task,
        args=(project_id, project_manager, settings_dict),
        daemon=True,
    )
    t.start()
    return {"status": "started", "project_id": project_id, "action": "analyze"}


@router.get("/projects/{project_id}/status")
def get_project_status(project_id: str):
    """Returns current execution status and progress snapshot."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    return {
        "status": proj["status"],
        "progress": proj["progress"],
        "error": proj.get("error"),
        "updated_at": proj["updated_at"],
    }


@router.get("/projects/{project_id}/events")
async def stream_project_events(project_id: str, request: Request):
    """SSE streaming endpoint providing real-time progress, stage updates, and logs."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def listener(data: Dict[str, Any]):
            loop.call_soon_threadsafe(queue.put_nowait, data)

        project_manager.add_event_listener(project_id, listener)

        # Send initial status snapshot immediately
        initial_event = {
            "project_id": project_id,
            "step": proj["progress"]["step"],
            "total_steps": proj["progress"]["total_steps"],
            "percent": proj["progress"]["percent"],
            "stage": proj["progress"]["stage"],
            "message": proj["progress"]["message"],
            "current_candidate": proj["progress"].get("current_candidate", 0),
            "status": proj["status"],
        }
        yield f"data: {json.dumps(initial_event)}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat ping
                    yield ": ping\n\n"
        finally:
            project_manager.remove_event_listener(project_id, listener)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/projects/{project_id}/candidates")
def get_candidates(project_id: str):
    """Returns detected candidates with ranking scores and breakdowns."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    return {
        "candidates": proj.get("candidates", []),
        "selected_candidate_ids": proj.get("selected_candidate_ids", []),
        "long_stream_info": proj.get("long_stream_info", {}),
    }


@router.get("/projects/{project_id}/candidates/{candidate_id}")
def get_candidate_detail(project_id: str, candidate_id: int):
    """Returns detailed information for a single candidate."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    for c in proj.get("candidates", []):
        if c.get("rank") == candidate_id or c.get("candidate_id") == candidate_id:
            return c
    raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Candidate not found")


@router.post("/projects/{project_id}/select-candidates")
def select_candidates(project_id: str, req: CandidateSelectionRequest):
    """Updates candidate selection for rendering."""
    validate_pid(project_id)
    success = project_manager.update_selected_candidates(project_id, req.candidate_ids)
    if not success:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    return {"status": "updated", "selected_candidate_ids": req.candidate_ids}


@router.post("/projects/{project_id}/render")
def start_rendering(
    project_id: str,
    req: Optional[CandidateSelectionRequest] = None,
    settings: Optional[ProcessingSettingsSchema] = None,
):
    """Starts Phases 3-6B rendering pipeline in background thread."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    sel_ids = req.candidate_ids if req else None
    settings_dict = (
        settings.model_dump()
        if hasattr(settings, "model_dump")
        else settings.dict()
    ) if settings else None

    t = threading.Thread(
        target=run_render_task,
        args=(project_id, project_manager, sel_ids, settings_dict),
        daemon=True,
    )
    t.start()
    return {"status": "started", "project_id": project_id, "action": "render"}


@router.post("/projects/{project_id}/cancel")
def cancel_job(project_id: str):
    """Signals running job to cancel."""
    validate_pid(project_id)
    success = project_manager.cancel_job(project_id)
    return {"status": "cancelled" if success else "no_active_job", "project_id": project_id}


@router.get("/projects/{project_id}/outputs")
def get_outputs(project_id: str):
    """Returns generated publishing packages and manifest data."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    return {
        "published_packages": proj.get("published_packages", []),
        "total_packages": len(proj.get("published_packages", [])),
    }


@router.get("/projects/{project_id}/outputs/{candidate_id}")
def get_output_detail(project_id: str, candidate_id: int):
    """Returns detailed package data for a single rendered Short."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    cand_dir = project_manager.output_dir / proj["video_id"] / "publishing" / f"candidate_{candidate_id:02d}"
    meta_file = cand_dir / "metadata.json"
    if not meta_file.exists():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Package metadata not found")

    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return meta


@router.patch("/projects/{project_id}/metadata")
def update_metadata(project_id: str, req: MetadataUpdateRequest):
    """Edits title, description, hashtags, or keywords on disk."""
    validate_pid(project_id)
    try:
        updated = project_manager.update_metadata(
            project_id=project_id,
            candidate_id=req.candidate_id,
            title=req.title,
            description=req.description,
            hashtags=req.hashtags,
            keywords=req.keywords,
        )
        return {"status": "updated", "metadata": updated}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/metadata/regenerate")
def regenerate_metadata(project_id: str, req: MetadataUpdateRequest):
    """Regenerates fresh grounded metadata without re-rendering video."""
    validate_pid(project_id)
    try:
        meta = project_manager.regenerate_metadata(
            project_id=project_id,
            candidate_id=req.candidate_id,
        )
        return {"status": "regenerated", "metadata": meta}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/candidates/{candidate_id}/timeline")
def get_candidate_timeline(project_id: str, candidate_id: int):
    """Retrieves the active Multi-Track TimelineEDL for the requested candidate."""
    validate_pid(project_id)
    try:
        timeline = project_manager.get_timeline(project_id, candidate_id)
        return timeline
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/candidates/{candidate_id}/timeline")
def save_candidate_timeline(project_id: str, candidate_id: int, timeline: Dict[str, Any]):
    """Saves user modifications to TimelineEDL, tracks dirty tracks, and increments version."""
    validate_pid(project_id)
    try:
        saved = project_manager.save_timeline(project_id, candidate_id, timeline)
        return {"status": "saved", "timeline": saved}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/candidates/{candidate_id}/timeline/render")
def render_candidate_timeline(project_id: str, candidate_id: int):
    """Triggers selective re-rendering of the Short from its current TimelineEDL."""
    validate_pid(project_id)
    try:
        res = project_manager.render_timeline(project_id, candidate_id)
        return {"status": "rendered", "result": res}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/projects/{project_id}/package")
def download_package(project_id: str, candidate_id: Optional[int] = None):
    """Downloads ZIP archive of publishing packages."""
    validate_pid(project_id)
    try:
        zip_path = project_manager.create_package_zip(project_id, candidate_id)
        return FileResponse(
            path=str(zip_path),
            filename=zip_path.name,
            media_type="application/zip",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def stream_file_partial(target_file: Path, media_type: str, request: Request):
    """Serves media assets with HTTP 206 Partial Content byte-range support for video and audio seeking."""
    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"File not found: {target_file.name}")

    file_size = target_file.stat().st_size
    range_header = request.headers.get("Range")

    if range_header:
        byte1, byte2 = 0, None
        match = re.search(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            g1, g2 = match.groups()
            byte1 = int(g1)
            if g2:
                byte2 = int(g2)

        byte1 = max(0, min(byte1, file_size - 1)) if file_size > 0 else 0
        if byte2 is not None:
            byte2 = min(byte2, file_size - 1)

        length = file_size - byte1 if byte2 is None else byte2 - byte1 + 1
        content_range = f"bytes {byte1}-{byte1 + length - 1}/{file_size}"

        def iterfile():
            with open(target_file, "rb") as f:
                f.seek(byte1)
                remaining = length
                chunk_size = 1024 * 512
                while remaining > 0:
                    read_len = min(remaining, chunk_size)
                    chunk = f.read(read_len)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": content_range,
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        }
        return StreamingResponse(iterfile(), status_code=206, headers=headers, media_type=media_type)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
    }
    return FileResponse(path=str(target_file), media_type=media_type, headers=headers)


@router.get("/projects/{project_id}/source-video")
def get_source_video(project_id: str, request: Request):
    """Streams the source video file (source.mp4) using HTTP 206 Partial Content."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    base_dir = project_manager.output_dir / proj["video_id"]
    source_file = base_dir / "source.mp4"
    if not source_file.exists():
        custom_path = proj.get("source_video_file") or proj.get("source_video_path")
        if custom_path and Path(custom_path).exists():
            source_file = Path(custom_path)
        else:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source video not found")

    return stream_file_partial(source_file, "video/mp4", request)


@router.get("/projects/{project_id}/audio")
def get_project_audio(project_id: str, request: Request):
    """Streams the project audio track (audio.wav or audio.mp3) with HTTP 206 Partial Content."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    base_dir = project_manager.output_dir / proj["video_id"]
    audio_file = base_dir / "audio.wav"
    media_type = "audio/wav"
    if not audio_file.exists():
        audio_file = base_dir / "audio.mp3"
        media_type = "audio/mpeg"

    if not audio_file.exists():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Audio file not found")

    return stream_file_partial(audio_file, media_type, request)


@router.get("/projects/{project_id}/files/{file_path:path}")
def serve_project_file(project_id: str, file_path: str, request: Request):
    """Serves media assets (MP4, JPG, WAV) with byte-range support for browser video seeking."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    base_dir = project_manager.output_dir / proj["video_id"]
    target_file = (base_dir / file_path).resolve()

    # Prevent directory traversal
    if not str(target_file).startswith(str(base_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"File not found: {file_path}")

    # Determine media type
    ext = target_file.suffix.lower()
    media_types = {
        ".mp4": "video/mp4",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".json": "application/json",
        ".txt": "text/plain",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return stream_file_partial(target_file, media_type, request)


# ==============================================================================
# Phase 9: Live Stream Session Endpoints
# ==============================================================================

@router.post("/projects/{project_id}/live/start")
def start_live_stream(project_id: str):
    """Starts rolling capture and candidate analysis for a live stream project."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        res = project_manager.start_live_session(project_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to start live stream session: {e}")


@router.post("/projects/{project_id}/live/stop")
def stop_live_stream(project_id: str):
    """Stops the active live stream capture and finalizes candidates."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    return project_manager.stop_live_session(project_id)


@router.post("/projects/{project_id}/live/pause")
def pause_live_stream(project_id: str):
    """Pauses rolling capture for the live stream session."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    return project_manager.pause_live_session(project_id)


@router.post("/projects/{project_id}/live/resume")
def resume_live_stream(project_id: str):
    """Resumes rolling capture for a paused live stream session."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    return project_manager.resume_live_session(project_id)


@router.get("/projects/{project_id}/live/status")
def get_live_stream_status(project_id: str):
    """Returns current live session telemetry, processed segments, and candidates count."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        return project_manager.get_live_status(project_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/live/candidates")
def get_live_stream_candidates(project_id: str):
    """Returns all gaming candidates discovered in the live stream candidate pool."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        return {"candidates": project_manager.get_live_candidates(project_id)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/live/activity")
def get_live_stream_activity(project_id: str):
    """Returns the persistent event activity log for the live stream."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        return {"events": project_manager.get_live_activity(project_id)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==============================================================================
# Phase 13 Social Media Publishing Endpoints
# ==============================================================================

@router.get("/publishing/platforms", response_model=List[PlatformStatusResponse])
def get_publishing_platforms():
    """Returns status, connection readiness, and setup hints for all supported publishing platforms."""
    statuses = publisher_registry.list_platform_statuses()
    return [s.model_dump() if hasattr(s, "model_dump") else s.dict() for s in statuses]


@router.post("/publishing/{platform}/connect")
def connect_platform(platform: str, req: Optional[PlatformConnectRequest] = None):
    """Initiates or completes OAuth authentication for a publishing platform."""
    try:
        publisher = publisher_registry.get_publisher(platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        auth_data = req.auth_data if req else None
        res = publisher.connect(auth_data=auth_data)
        return res
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")


@router.post("/publishing/{platform}/disconnect")
def disconnect_platform(platform: str):
    """Disconnects and safely clears local credentials for a publishing platform."""
    try:
        publisher = publisher_registry.get_publisher(platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ok = publisher.disconnect()
    return {"success": ok, "platform": platform, "status": "disconnected"}


@router.post("/projects/{project_id}/candidates/{candidate_id}/publish", response_model=PublishResultResponse)
def publish_candidate(project_id: str, candidate_id: int, req: PublishRequestSchema):
    """Publishes a rendered candidate Short (or runs a dry-run payload simulation) to target platform."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        publisher = publisher_registry.get_publisher(req.platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    output_dir = project_manager.output_dir / project_id
    package_dir = output_dir / "publishing" / f"candidate_{candidate_id:02d}"
    video_path = package_dir / "final.mp4"
    thumbnail_path = package_dir / "thumbnail.jpg"

    # Fallback paths if final.mp4 is not in package_dir
    if not video_path.exists():
        clip_path = output_dir / "clips" / f"candidate_{candidate_id:02d}_final.mp4"
        if clip_path.exists():
            video_path = clip_path
        else:
            cand = next((c for c in proj.get("candidates", []) if (c.get("rank") == candidate_id or c.get("candidate_id") == candidate_id)), None)
            if cand:
                clip_prop = cand.get("audio_polished_clip") or cand.get("final_clip") or cand.get("short_clip")
                if clip_prop and Path(clip_prop).exists():
                    video_path = Path(clip_prop)

    if not thumbnail_path.exists():
        clip_thumb = output_dir / "clips" / f"candidate_{candidate_id:02d}_thumb.jpg"
        if clip_thumb.exists():
            thumbnail_path = clip_thumb

    pub_req = PublishRequest(
        project_id=project_id,
        candidate_id=candidate_id,
        platform=req.platform,
        title=req.title,
        description=req.description,
        hashtags=req.hashtags,
        privacy=req.privacy,
        scheduled_publish_at=req.scheduled_publish_at,
        upload_thumbnail=req.upload_thumbnail,
        dry_run=req.dry_run,
        aspect_ratio=req.aspect_ratio,
        extra_params=req.extra_params,
    )

    result = publisher.publish(
        video_path=video_path,
        thumbnail_path=thumbnail_path if thumbnail_path.exists() else None,
        req=pub_req,
    )

    publish_history_store.record_publish(project_id=project_id, result=result, req=pub_req)
    return result


@router.get("/projects/{project_id}/publish-history", response_model=List[PublishHistoryEntryResponse])
def get_project_publish_history(project_id: str):
    """Returns all publishing attempts and simulation history for the project."""
    validate_pid(project_id)
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    return publish_history_store.get_history(project_id)


@router.get("/projects/{project_id}/candidates/{candidate_id}/publish-history", response_model=List[PublishHistoryEntryResponse])
def get_candidate_publish_history(project_id: str, candidate_id: int):
    """Returns publishing history for a specific candidate."""
    validate_pid(project_id)
    return publish_history_store.get_candidate_history(project_id, candidate_id)


