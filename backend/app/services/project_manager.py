"""Project Manager: state persistence, job coordination, and artifact management."""

import json
import os
import re
import shutil
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Generator, Callable

from backend.app.config import (
    TOP_N_CANDIDATES,
    LAYOUT_AUTO,
    MIN_CLIP_DURATION,
    MAX_CLIP_DURATION,
)
from backend.app.pipeline.clip_summary_engine import ClipSummaryEngine
from backend.app.pipeline.title_engine import TitleEngine
from backend.app.pipeline.description_engine import DescriptionEngine
from backend.app.pipeline.hashtag_engine import HashtagEngine


def extract_youtube_id(url: Optional[str]) -> Optional[str]:
    """Extract 11-char YouTube ID from common URL formats or raw 11-char ID string."""
    if not url or not isinstance(url, str):
        return None
    cleaned = url.strip()
    if re.match(r'^[0-9A-Za-z_-]{11}$', cleaned):
        return cleaned
    match = re.search(r'(?:v=|\/|youtu\.be\/|embed\/|v\/|shorts\/)([0-9A-Za-z_-]{11})', cleaned)
    return match.group(1) if match else None


class ProjectManager:
    """Manages project state, local history, and execution coordination."""

    def __init__(self, base_output_dir: Optional[Path] = None):
        self.root_dir = Path(__file__).resolve().parent.parent.parent.parent
        self.output_dir = base_output_dir or (self.root_dir / "output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.projects_db_file = self.output_dir / "projects.json"

        self._lock = threading.Lock()
        self._projects: Dict[str, Dict[str, Any]] = {}
        self._event_queues: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._active_threads: Dict[str, threading.Thread] = {}
        self._cancel_flags: Dict[str, threading.Event] = {}
        self._live_orchestrators: Dict[str, Any] = {}

        self._load_projects()
        self._reconcile_interrupted_projects()
        self._auto_discover_existing_outputs()

    def _load_projects(self) -> None:
        """Loads projects registry from disk."""
        if self.projects_db_file.exists():
            try:
                with open(self.projects_db_file, "r", encoding="utf-8") as f:
                    self._projects = json.load(f)
            except Exception:
                self._projects = {}

    def _reconcile_interrupted_projects(self) -> None:
        """Reconciles transient project states (analyzing, rendering, connecting) on startup."""
        dirty = False
        for pid, p in self._projects.items():
            st = p.get("status")
            if st in ("analyzing", "queued", "starting"):
                p["status"] = "failed"
                p["error"] = {
                    "code": "SERVER_RESTARTED",
                    "summary": "Analysis was interrupted by server restart. You can safely restart analysis.",
                    "recoverable": True,
                }
                p["progress"]["stage"] = "Interrupted"
                p["progress"]["message"] = "Analysis interrupted by server restart."
                dirty = True
            elif st in ("rendering", "cancelling"):
                p["status"] = "recoverable" if p.get("candidates") else "failed"
                p["error"] = {
                    "code": "SERVER_RESTARTED",
                    "summary": "Rendering was interrupted by server restart. You can safely re-render.",
                    "recoverable": True,
                }
                p["progress"]["stage"] = "Interrupted"
                p["progress"]["message"] = "Rendering interrupted by server restart."
                dirty = True
            elif st in ("connecting", "capturing", "live"):
                p["status"] = "ended"
                if p.get("live_session_info"):
                    p["live_session_info"]["status"] = "interrupted"
                p["error"] = {
                    "code": "SERVER_RESTARTED",
                    "summary": "Live stream session was interrupted by server restart.",
                    "recoverable": False,
                }
                dirty = True
        if dirty:
            self._save_projects()

    def _save_projects(self) -> None:
        """Persists projects registry to disk atomically."""
        temp_file = self.projects_db_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(self._projects, f, indent=2, ensure_ascii=False)
        temp_file.replace(self.projects_db_file)

    def _auto_discover_existing_outputs(self) -> None:
        """Auto-indexes previously processed video outputs (e.g. EdtUDpqjltA) into projects."""
        for item in self.output_dir.iterdir():
            if item.is_dir() and len(item.name) == 11:
                vid_id = item.name
                manifest_file = item / "publishing" / "publishing_manifest.json"

                if vid_id in self._projects:
                    # Sync publishing packages if manifest exists on disk
                    if manifest_file.exists():
                        try:
                            if not self._projects[vid_id].get("published_packages"):
                                with open(manifest_file, "r", encoding="utf-8") as mf:
                                    m_data = json.load(mf)
                                    self._projects[vid_id]["published_packages"] = m_data.get("packages", [])
                            self._projects[vid_id]["status"] = "completed"
                        except Exception:
                            pass
                    continue

                meta_file = item / "metadata.json"
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)

                        # Check if candidates exist
                        cand_file = item / "candidates.json"
                        cands = []
                        if cand_file.exists():
                            with open(cand_file, "r", encoding="utf-8") as cf:
                                c_data = json.load(cf)
                                cands = c_data.get("candidates", [])

                        # Check if publishing manifest exists
                        manifest_file = item / "publishing" / "publishing_manifest.json"
                        packages = []
                        status = "completed" if manifest_file.exists() else "candidates_ready"
                        if manifest_file.exists():
                            with open(manifest_file, "r", encoding="utf-8") as mf:
                                m_data = json.load(mf)
                                packages = m_data.get("packages", [])

                        proj_id = vid_id
                        self._projects[proj_id] = {
                            "id": proj_id,
                            "video_id": vid_id,
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                            "title": meta.get("title", f"Video {vid_id}"),
                            "uploader": meta.get("uploader", "Unknown Creator"),
                            "duration": meta.get("duration", 0.0),
                            "language": meta.get("language", "en"),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "status": status,
                            "settings": self.get_default_settings(),
                            "long_stream_info": {
                                "source_duration": meta.get("duration", 0.0),
                                "chunks_processed": 1,
                                "total_chunks": 1,
                                "chunks_failed": 0,
                                "chunks_reused": 0,
                                "candidates_detected": len(cands),
                                "deduplicated_candidates": len(cands),
                                "strong_moments": sum(1 for c in cands if c.get("final_score", 0) >= 70),
                                "recommended_shorts": min(len(cands), 5),
                                "selected_candidates": min(len(cands), 5),
                                "quality_gate_reason": None,
                            },
                            "candidates": cands,
                            "selected_candidate_ids": [c.get("rank", idx) for idx, c in enumerate(cands[:5], 1)],
                            "published_packages": packages,
                            "progress": {
                                "step": 23 if status == "completed" else 5,
                                "total_steps": 23,
                                "percent": 100 if status == "completed" else 25,
                                "stage": "Completed" if status == "completed" else "Moments Ready",
                                "message": "All processing complete" if status == "completed" else "Analysis complete",
                                "current_candidate": 0,
                                "logs": ["Indexed from local cache."],
                            },
                            "error": None,
                        }
                    except Exception:
                        pass
        self._save_projects()

    def get_default_settings(self) -> Dict[str, Any]:
        """Provides default processing settings."""
        return {
            "duration_mode": "auto",
            "min_duration": MIN_CLIP_DURATION,
            "max_duration": MAX_CLIP_DURATION,
            "num_shorts_mode": "auto",
            "num_shorts": TOP_N_CANDIDATES,
            "layout": LAYOUT_AUTO,
            "captions": True,
            "subtitle_language": "auto",  # auto, original, english, hindi, hinglish
            "word_highlighting": True,
            "emoji": True,
            "effects": True,
            "effects_mode": "smart",
            "audio": True,
            "sfx": True,
            "ducking": True,
            "thumbnail": True,
            "metadata_enabled": True,
            "llm": False,
            "quality_preset": "High",
            "resolution": "1080x1920",
            "fps": 60,
            "target_lufs": -14.0,
            "true_peak": -1.0,
        }

    def _validate_project_id(self, project_id: str) -> None:
        """Ensures project ID is alphanumeric/dash/underscore to prevent path traversal."""
        if not project_id or not re.match(r"^[a-zA-Z0-9_\-]+$", project_id):
            raise ValueError(f"Invalid project ID format: {project_id}")

    def _decorate_project(self, proj: Dict[str, Any]) -> None:
        """Decorates project and candidates with output file presence, URLs, and rendered status."""
        if not proj:
            return
        video_id = proj.get("video_id", proj.get("id"))
        base_dir = self.output_dir / video_id
        pub_dir = base_dir / "publishing"

        # Check source video file
        source_mp4 = base_dir / "source.mp4"
        has_source = bool(source_mp4.exists() and source_mp4.is_file() and source_mp4.stat().st_size > 0)
        if not has_source:
            custom_path = proj.get("source_video_file") or proj.get("source_video_path")
            if custom_path and Path(custom_path).exists() and Path(custom_path).is_file():
                has_source = True
        proj["has_source_video"] = has_source
        proj["source_video_url"] = f"/api/projects/{proj['id']}/source-video" if has_source else None

        # Check audio track
        audio_file = base_dir / "audio.wav"
        has_audio = bool(audio_file.exists() and audio_file.is_file() and audio_file.stat().st_size > 0)
        if not has_audio:
            audio_file = base_dir / "audio.mp3"
            has_audio = bool(audio_file.exists() and audio_file.is_file() and audio_file.stat().st_size > 0)
        proj["has_audio"] = has_audio
        proj["audio_url"] = f"/api/projects/{proj['id']}/audio" if has_audio else None

        # YouTube video ID resolution from ALL possible sources
        yt_id = (
            extract_youtube_id(proj.get("youtube_video_id"))
            or extract_youtube_id(proj.get("url"))
            or extract_youtube_id(proj.get("source_url"))
            or extract_youtube_id(video_id)
            or extract_youtube_id(proj.get("id"))
        )
        if not yt_id and base_dir.exists():
            meta_path = base_dir / "metadata.json"
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as mf:
                        m = json.load(mf)
                        yt_id = (
                            extract_youtube_id(m.get("video_id"))
                            or extract_youtube_id(m.get("id"))
                            or extract_youtube_id(m.get("url"))
                            or extract_youtube_id(m.get("webpage_url"))
                        )
                except Exception:
                    pass

        proj["youtube_video_id"] = yt_id
        if "source_url" not in proj or not proj["source_url"]:
            proj["source_url"] = proj.get("url", "")

        # Auto-load candidates if list is empty but candidates.json exists on disk
        if not proj.get("candidates"):
            cand_file = base_dir / "candidates.json"
            if cand_file.exists():
                try:
                    with open(cand_file, "r", encoding="utf-8") as cf:
                        c_data = json.load(cf)
                        proj["candidates"] = c_data if isinstance(c_data, list) else c_data.get("candidates", [])
                except Exception:
                    pass

        # Sync published_packages if publishing_manifest.json exists
        manifest_file = pub_dir / "publishing_manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as mf:
                    m_data = json.load(mf)
                    pkgs = m_data.get("packages", [])
                    if pkgs:
                        # Ensure each package in manifest has description, hashtags, and keywords
                        for p in pkgs:
                            cid = p.get("candidate_id")
                            if cid and ("description" not in p or not p.get("description") or "hashtags" not in p or "keywords" not in p):
                                c_meta_file = pub_dir / f"candidate_{cid:02d}" / "metadata.json"
                                if c_meta_file.exists():
                                    try:
                                        with open(c_meta_file, "r", encoding="utf-8") as cmf:
                                            cm_data = json.load(cmf)
                                        if not p.get("description"):
                                            p["description"] = cm_data.get("description", "")
                                        if not p.get("hashtags"):
                                            p["hashtags"] = cm_data.get("hashtags", [])
                                        if not p.get("keywords"):
                                            p["keywords"] = cm_data.get("keywords", [])
                                    except Exception:
                                        pass
                                desc_txt_file = pub_dir / f"candidate_{cid:02d}" / "description.txt"
                                if not p.get("description") and desc_txt_file.exists():
                                    try:
                                        p["description"] = desc_txt_file.read_text(encoding="utf-8").strip()
                                    except Exception:
                                        pass
                        proj["published_packages"] = pkgs
            except Exception:
                pass

        # Backfill any missing description/tags on existing published_packages
        for p in proj.get("published_packages", []):
            cid = p.get("candidate_id")
            if cid and (not p.get("description") or "hashtags" not in p or "keywords" not in p):
                c_meta_file = pub_dir / f"candidate_{cid:02d}" / "metadata.json"
                if c_meta_file.exists():
                    try:
                        with open(c_meta_file, "r", encoding="utf-8") as cmf:
                            cm_data = json.load(cmf)
                        if not p.get("description"):
                            p["description"] = cm_data.get("description", "")
                        if not p.get("hashtags"):
                            p["hashtags"] = cm_data.get("hashtags", [])
                        if not p.get("keywords"):
                            p["keywords"] = cm_data.get("keywords", [])
                    except Exception:
                        pass
                desc_txt_file = pub_dir / f"candidate_{cid:02d}" / "description.txt"
                if not p.get("description") and desc_txt_file.exists():
                    try:
                        p["description"] = desc_txt_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass

        cands = proj.get("candidates", [])
        rendered_count = 0
        pkgs_by_cid = {p.get("candidate_id"): p for p in proj.get("published_packages", []) if p.get("candidate_id")}

        # Load transcript for candidate excerpts if available
        transcript_file = base_dir / "transcript.json"
        transcript_segments = []
        if transcript_file.exists():
            try:
                with open(transcript_file, "r", encoding="utf-8") as tf:
                    t_data = json.load(tf)
                    transcript_segments = t_data.get("segments", [])
            except Exception:
                pass

        for idx, cand in enumerate(cands, 1):
            cid = cand.get("candidate_id") or cand.get("rank", idx)
            cand["candidate_id"] = cid

            # Populate transcript excerpt if missing
            if not cand.get("transcript_excerpt"):
                c_start = float(cand.get("start", 0.0))
                c_end = float(cand.get("end", 0.0))
                matched_texts = []
                for seg in transcript_segments:
                    s_start = float(seg.get("start", 0.0))
                    s_end = float(seg.get("end", 0.0))
                    if s_end >= c_start and s_start <= c_end:
                        text = seg.get("text", "").strip()
                        if text:
                            matched_texts.append(text)
                cand["transcript_excerpt"] = " ".join(matched_texts).strip()
            cand_dir = pub_dir / f"candidate_{cid:02d}"
            final_mp4 = cand_dir / "final.mp4"
            thumb_jpg = cand_dir / "thumbnail.jpg"

            is_rendered = final_mp4.exists() and final_mp4.is_file() and final_mp4.stat().st_size > 0
            cand["rendered"] = is_rendered
            if is_rendered:
                rendered_count += 1
                cand["output"] = {
                    "video_url": f"/api/projects/{proj['id']}/files/publishing/candidate_{cid:02d}/final.mp4",
                    "filename": "final.mp4",
                    "size_bytes": final_mp4.stat().st_size,
                    "thumbnail_url": f"/api/projects/{proj['id']}/files/publishing/candidate_{cid:02d}/thumbnail.jpg" if thumb_jpg.exists() else None,
                    "duration": cand.get("duration", 0.0),
                }
                if cid not in pkgs_by_cid:
                    meta_file = cand_dir / "metadata.json"
                    cand_meta = {}
                    if meta_file.exists():
                        try:
                            with open(meta_file, "r", encoding="utf-8") as mf:
                                cand_meta = json.load(mf)
                        except Exception:
                            pass
                    new_pkg = {
                        "candidate_id": cid,
                        "package_dir": str(cand_dir),
                        "title": cand_meta.get("title", {}).get("selected", cand.get("title", f"Short #{cid}")),
                        "description": cand_meta.get("description", ""),
                        "hashtags": cand_meta.get("hashtags", []),
                        "keywords": cand_meta.get("keywords", []),
                        "thumbnail": str(thumb_jpg) if thumb_jpg.exists() else "",
                        "thumbnail_score": cand_meta.get("thumbnail", {}).get("score", 85.0),
                        "thumbnail_timestamp": cand.get("start", 0.0),
                        "quality_score": cand.get("final_score", 80.0),
                        "status": "PASS",
                        "publishability": cand_meta.get("publishability", cand.get("publishability")),
                    }
                    if not new_pkg["description"]:
                        desc_txt = cand_dir / "description.txt"
                        if desc_txt.exists():
                            try:
                                new_pkg["description"] = desc_txt.read_text(encoding="utf-8").strip()
                            except Exception:
                                pass
                    proj.setdefault("published_packages", []).append(new_pkg)
                    pkgs_by_cid[cid] = new_pkg
            else:
                cand["output"] = None

        if manifest_file.exists() and rendered_count > 0:
            if proj.get("status") not in ("rendering", "failed", "cancelled"):
                proj["status"] = "completed"

    def list_projects(self) -> List[Dict[str, Any]]:
        """Returns summary list of all projects sorted newest first."""
        with self._lock:
            projs = list(self._projects.values())
            for p in projs:
                self._decorate_project(p)
            projs.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
            return projs

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves single project by ID."""
        self._validate_project_id(project_id)
        with self._lock:
            proj = self._projects.get(project_id)
            if proj:
                self._decorate_project(proj)
            return proj

    def create_project(
        self,
        url: str,
        settings: Optional[Dict[str, Any]] = None,
        title: Optional[str] = None,
        source_type: Optional[str] = "normal_video",
    ) -> Dict[str, Any]:
        """Creates a new project entry initialized in queued status."""
        vid_id = extract_youtube_id(url)
        if not vid_id:
            vid_id = f"custom_{int(time.time())}"

        proj_id = vid_id
        resolved_source_type = source_type or "normal_video"
        merged_settings = self.get_default_settings()
        if settings:
            merged_settings.update(settings)

        project_title = title.strip() if title and title.strip() else (
            f"Live Stream ({vid_id})" if resolved_source_type == "live_stream" else f"YouTube Video ({vid_id})"
        )

        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            # If already exists and completed, return existing
            if proj_id in self._projects and self._projects[proj_id].get("status") == "completed":
                return self._projects[proj_id]

            proj = {
                "id": proj_id,
                "video_id": vid_id,
                "url": url,
                "title": project_title,
                "uploader": "Unknown Creator",
                "duration": 0.0,
                "language": "en",
                "created_at": now,
                "updated_at": now,
                "status": "idle" if resolved_source_type == "live_stream" else "queued",
                "source_type": resolved_source_type,
                "live_session_info": {
                    "session_id": None,
                    "status": "idle",
                    "total_segments": 0,
                    "segments_processed": 0,
                    "candidates_detected": 0,
                    "candidates_ready": 0,
                    "storage_used": 0,
                } if resolved_source_type == "live_stream" else None,
                "settings": merged_settings,
                "long_stream_info": {
                    "source_duration": 0.0,
                    "chunks_processed": 0,
                    "total_chunks": 1,
                    "chunks_failed": 0,
                    "chunks_reused": 0,
                    "candidates_detected": 0,
                    "deduplicated_candidates": 0,
                    "strong_moments": 0,
                    "recommended_shorts": 0,
                    "selected_candidates": 0,
                    "quality_gate_reason": None,
                },
                "candidates": [],
                "selected_candidate_ids": [],
                "published_packages": [],
                "progress": {
                    "step": 0,
                    "total_steps": 23,
                    "percent": 0,
                    "stage": "Queued",
                    "message": "Waiting to start analysis...",
                    "current_candidate": 0,
                    "logs": ["Project created."],
                },
                "error": None,
            }
            self._projects[proj_id] = proj
            self._save_projects()
            return proj

    def delete_project(self, project_id: str) -> bool:
        """Removes a project from registry and disk."""
        self._validate_project_id(project_id)
        with self._lock:
            if project_id in self._projects:
                proj = self._projects.pop(project_id)
                self._save_projects()
                vid_id = proj.get("video_id") or project_id
                proj_dir = (self.output_dir / vid_id).resolve()
                if str(proj_dir).startswith(str(self.output_dir.resolve())) and proj_dir.exists():
                    shutil.rmtree(proj_dir, ignore_errors=True)
                return True
            return False

    def update_project_progress(
        self,
        project_id: str,
        step: int,
        total_steps: int,
        stage: str,
        message: str,
        current_candidate: int = 0,
    ) -> None:
        """Updates progress state and broadcasts to active SSE listeners."""
        with self._lock:
            proj = self._projects.get(project_id)
            if not proj:
                return

            percent = int((step / total_steps) * 100) if total_steps > 0 else 0
            percent = min(100, max(0, percent))

            proj["progress"]["step"] = step
            proj["progress"]["total_steps"] = total_steps
            proj["progress"]["percent"] = percent
            proj["progress"]["stage"] = stage
            proj["progress"]["message"] = message
            proj["progress"]["current_candidate"] = current_candidate
            proj["progress"]["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
            if len(proj["progress"]["logs"]) > 200:
                proj["progress"]["logs"] = proj["progress"]["logs"][-200:]

            proj["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_projects()

            event_data = {
                "project_id": project_id,
                "step": step,
                "total_steps": total_steps,
                "percent": percent,
                "stage": stage,
                "message": message,
                "current_candidate": current_candidate,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            listeners = self._event_queues.get(project_id, [])
            for callback in listeners:
                try:
                    callback(event_data)
                except Exception:
                    pass

    def add_event_listener(self, project_id: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a listener for SSE events."""
        with self._lock:
            if project_id not in self._event_queues:
                self._event_queues[project_id] = []
            self._event_queues[project_id].append(callback)

    def remove_event_listener(self, project_id: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Unregisters an SSE listener."""
        with self._lock:
            if project_id in self._event_queues and callback in self._event_queues[project_id]:
                self._event_queues[project_id].remove(callback)

    def cancel_job(self, project_id: str) -> bool:
        """Signals active job to terminate, stops live sessions, and terminates child processes."""
        with self._lock:
            cancelled = False
            if project_id in self._cancel_flags:
                self._cancel_flags[project_id].set()
                cancelled = True

            # Stop live orchestrator if active
            if project_id in self._live_orchestrators:
                try:
                    self._live_orchestrators[project_id].stop()
                    cancelled = True
                except Exception:
                    pass

            from backend.app.services.process_tracker import ProcessTracker
            ProcessTracker.kill_project_processes(project_id)

            if project_id in self._projects:
                p = self._projects[project_id]
                p["status"] = "cancelled"
                p["progress"]["stage"] = "Cancelled"
                p["progress"]["message"] = "Job cancelled by user."
                p["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_projects()
                cancelled = True

            return cancelled

    def update_selected_candidates(self, project_id: str, selected_ids: List[int]) -> bool:
        """Sets which candidates are queued for rendering."""
        with self._lock:
            proj = self._projects.get(project_id)
            if not proj:
                return False
            proj["selected_candidate_ids"] = selected_ids
            proj["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_projects()
            return True

    def update_metadata(
        self,
        project_id: str,
        candidate_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        hashtags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Edits metadata for a candidate on disk and updates manifest/database."""
        self._validate_project_id(project_id)
        with self._lock:
            proj = self._projects.get(project_id)
            if not proj:
                raise ValueError("Project not found")

            cand_dir = self.output_dir / proj["video_id"] / "publishing" / f"candidate_{candidate_id:02d}"
            if not cand_dir.exists():
                raise FileNotFoundError(f"Candidate publishing directory not found: {cand_dir}")

            meta_file = cand_dir / "metadata.json"
            meta_data = {}
            if meta_file.exists():
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)

            if title is not None:
                (cand_dir / "title.txt").write_text(title, encoding="utf-8")
                if "title" in meta_data:
                    meta_data["title"]["selected"] = title

            if description is not None:
                (cand_dir / "description.txt").write_text(description, encoding="utf-8")
                meta_data["description"] = description

            if hashtags is not None:
                (cand_dir / "hashtags.txt").write_text(" ".join(hashtags), encoding="utf-8")
                meta_data["hashtags"] = hashtags

            if keywords is not None:
                (cand_dir / "keywords.txt").write_text(", ".join(keywords), encoding="utf-8")
                meta_data["keywords"] = keywords

            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2, ensure_ascii=False)

            # Update project cached packages
            for pkg in proj.get("published_packages", []):
                if pkg.get("candidate_id") == candidate_id:
                    if title is not None:
                        pkg["title"] = title
                    if description is not None:
                        pkg["description"] = description
                    break

            proj["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_projects()
            return meta_data

    def regenerate_metadata(self, project_id: str, candidate_id: int) -> Dict[str, Any]:
        """Regenerates fresh, grounded title, description, and hashtags without re-rendering video."""
        self._validate_project_id(project_id)
        with self._lock:
            proj = self._projects.get(project_id)
            if not proj:
                raise ValueError("Project not found")

            cand_dir = self.output_dir / proj["video_id"] / "publishing" / f"candidate_{candidate_id:02d}"
            meta_file = cand_dir / "metadata.json"
            if not meta_file.exists():
                raise FileNotFoundError(f"Candidate metadata not found: {meta_file}")

            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            summary_data = meta.get("summary", {})
            from backend.app.pipeline.clip_summary_engine import ClipSummary
            summary = ClipSummary(
                candidate_id=candidate_id,
                duration=summary_data.get("duration", 30.0),
                game=summary_data.get("game", "Gaming"),
                primary_event=summary_data.get("primary_event", "highlight"),
                secondary_events=summary_data.get("secondary_events", []),
                strongest_reaction=summary_data.get("strongest_reaction", "unknown"),
                climax_timestamp=summary_data.get("climax_timestamp", 0.0),
                intensity=summary_data.get("intensity", 0.8),
                tone=summary_data.get("tone", "funny/chaotic"),
                has_facecam=summary_data.get("has_facecam", False),
                visual_effect_count=summary_data.get("visual_effect_count", 0),
                sfx_count=summary_data.get("sfx_count", 0),
                source_signals=summary_data.get("source_signals", []),
            )

            title_engine = TitleEngine(ollama_enabled=False)
            desc_engine = DescriptionEngine()
            tag_engine = HashtagEngine()

            # Existing titles and descriptions in bundle
            existing_t = [p.get("title", "") for p in proj.get("published_packages", []) if p.get("candidate_id") != candidate_id]
            existing_d = [p.get("description", "") for p in proj.get("published_packages", []) if p.get("candidate_id") != candidate_id]

            title_res = title_engine.generate_and_rank_titles(summary, existing_titles=existing_t)
            new_title = title_res["selected_title"]

            tags = tag_engine.generate_hashtags(summary)
            kws = tag_engine.generate_keywords(summary)

            src_meta = {"uploader": proj.get("uploader", ""), "title": proj.get("title", "")}
            new_desc = desc_engine.generate_description(
                summary=summary,
                selected_title=new_title,
                hashtags=tags,
                source_metadata=src_meta,
                existing_descriptions=existing_d,
            )

            q_score = title_engine.compute_metadata_quality(
                title=new_title,
                summary=summary,
                description=new_desc,
                hashtags=tags,
                existing_titles=existing_t,
                existing_descriptions=existing_d,
            )

            # Write to disk
            (cand_dir / "title.txt").write_text(new_title, encoding="utf-8")
            (cand_dir / "description.txt").write_text(new_desc, encoding="utf-8")
            (cand_dir / "hashtags.txt").write_text(" ".join(tags), encoding="utf-8")
            (cand_dir / "keywords.txt").write_text(", ".join(kws), encoding="utf-8")

            meta["title"] = {
                "selected": new_title,
                "score": title_res["selected_score"],
                "alternatives": title_res["alternatives"],
                "generation_mode": "rule_based",
                "model": "rule_engine_v1",
            }
            meta["description"] = new_desc
            meta["hashtags"] = tags
            meta["keywords"] = kws
            meta["metadata_quality"] = q_score

            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            # Update cached packages
            for pkg in proj.get("published_packages", []):
                if pkg.get("candidate_id") == candidate_id:
                    pkg["title"] = new_title
                    pkg["description"] = new_desc
                    pkg["quality_score"] = q_score["overall"]
                    break

            proj["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_projects()
            return meta

    def create_package_zip(self, project_id: str, candidate_id: Optional[int] = None) -> Path:
        """Creates a downloadable ZIP of publishing packages."""
        proj = self.get_project(project_id)
        if not proj:
            raise ValueError("Project not found")

        pub_dir = self.output_dir / proj["video_id"] / "publishing"
        if not pub_dir.exists():
            raise FileNotFoundError(f"Publishing directory does not exist: {pub_dir}")

        zip_name = f"publishing_{proj['video_id']}.zip" if candidate_id is None else f"candidate_{candidate_id:02d}_{proj['video_id']}.zip"
        zip_path = self.output_dir / proj["video_id"] / zip_name

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
            if candidate_id is not None:
                cand_dir = pub_dir / f"candidate_{candidate_id:02d}"
                if cand_dir.exists():
                    for file_item in cand_dir.iterdir():
                        if file_item.is_file():
                            zip_out.write(file_item, arcname=f"candidate_{candidate_id:02d}/{file_item.name}")
            else:
                for root, _, files in os.walk(pub_dir):
                    for f in files:
                        full_f = Path(root) / f
                        rel_path = full_f.relative_to(pub_dir)
                        zip_out.write(full_f, arcname=str(rel_path))

        return zip_path

    def get_timeline(self, project_id: str, candidate_id: int) -> Dict[str, Any]:
        """Loads or synthesizes TimelineEDL for the requested candidate."""
        self._validate_project_id(project_id)
        with self._lock:
            proj = self._projects.get(project_id)
            if not proj:
                raise ValueError("Project not found")
            project_dir = self.output_dir / proj["video_id"]

        from backend.app.pipeline.timeline import TimelineStore, TimelineEdlGenerator
        tl_store = TimelineStore()
        timeline = tl_store.get_timeline(project_dir, candidate_id)

        if timeline is None:
            # Auto-synthesize on-demand if not already generated
            candidates = proj.get("candidates", [])
            candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id or c.get("rank") == candidate_id), None)
            if not candidate and candidates:
                candidate = candidates[candidate_id - 1] if 0 < candidate_id <= len(candidates) else candidates[0]
            if not candidate:
                candidate = {"start": 0.0, "end": 45.0, "duration": 45.0}

            # Check for transcript
            transcript_file = project_dir / "transcript.json"
            transcript_data = None
            if transcript_file.exists():
                try:
                    with open(transcript_file, "r", encoding="utf-8") as tf:
                        transcript_data = json.load(tf)
                except Exception:
                    pass

            # Check for phase 5 and 6a timelines
            p5_tl_file = project_dir / "effects" / f"candidate_{candidate_id:02d}_effect_timeline.json"
            p5_tl = None
            if p5_tl_file.exists():
                try:
                    with open(p5_tl_file, "r", encoding="utf-8") as f:
                        p5_tl = json.load(f)
                except Exception:
                    pass

            p6a_tl_file = project_dir / "audio" / f"candidate_{candidate_id:02d}_audio_timeline.json"
            p6a_tl = None
            if p6a_tl_file.exists():
                try:
                    with open(p6a_tl_file, "r", encoding="utf-8") as f:
                        p6a_tl = json.load(f)
                except Exception:
                    pass

            source_video_path = project_dir / "source.mp4"
            is_live = proj.get("source_type") == "live_stream" or not source_video_path.exists()
            cand_source_clip = None

            if is_live:
                from backend.app.pipeline.live import LiveSourceResolver, LiveStore
                l_store = LiveStore(project_dir)
                manifest = l_store.load_manifest()
                cand_source_clip = project_dir / "publishing" / f"candidate_{candidate_id:02d}" / "source.mp4"
                if not cand_source_clip.exists():
                    resolver = LiveSourceResolver()
                    resolver.resolve_source_clip(
                        global_start=candidate.get("start", 0.0),
                        global_end=candidate.get("end", 60.0),
                        segments=manifest,
                        output_clip_path=cand_source_clip,
                    )
                source_video_path = cand_source_clip

                # Check for live candidate transcript
                if not transcript_data:
                    transcript_data = l_store.compile_candidate_transcript(candidate, manifest)

                if (not transcript_data or not transcript_data.get("words")) and cand_source_clip.exists():
                    try:
                        from backend.app.pipeline.downloader import VideoDownloader
                        from backend.app.pipeline.transcriber import AudioTranscriber
                        import subprocess
                        temp_wav = cand_source_clip.with_suffix(".wav")
                        if not temp_wav.exists():
                            ffmpeg_bin = VideoDownloader().ffmpeg_path
                            subprocess.run([
                                ffmpeg_bin, "-y", "-nostats", "-loglevel", "error",
                                "-i", str(cand_source_clip), "-ac", "1", "-ar", "16000", "-vn", str(temp_wav)
                            ], check=True, timeout=60)
                        transcript_data = AudioTranscriber().transcribe(temp_wav)
                    except Exception:
                        pass

            # If phase 5 effect timeline is missing, synthesize on-demand
            if not p5_tl:
                from backend.app.pipeline.effect_engine import EffectEngine
                eff_engine = EffectEngine()
                eff_tl = eff_engine.generate_timeline(
                    candidate_id=candidate_id,
                    candidate=candidate,
                    audio_peaks=candidate.get("score_breakdown", {}).get("audio", {}).get("peaks", []),
                    facecam_info={"facecam_detected": False},
                )
                p5_tl = eff_tl.to_dict() if hasattr(eff_tl, "to_dict") else (eff_tl.model_dump() if hasattr(eff_tl, "model_dump") else eff_tl.__dict__)
                if not p5_tl.get("effects") and (eff_tl.impact_scores or eff_tl.suppressed_events):
                    candidates_moments = sorted(
                        eff_tl.impact_scores or eff_tl.suppressed_events,
                        key=lambda m: m.get("impact_score", m.get("score", 0.0)),
                        reverse=True
                    )
                    if candidates_moments:
                        best_m = candidates_moments[0]
                        t_anchor = float(best_m.get("time", best_m.get("anchor_time", 15.0)))
                        p5_tl["effects"].append({
                            "type": "punch_zoom",
                            "start": round(max(0.0, t_anchor - 0.4), 2),
                            "end": round(min(candidate.get("duration", 60.0), t_anchor + 1.2), 2),
                            "intensity": 0.75,
                            "confidence": 0.85,
                            "reason": f"Climax gaming punch-in at {t_anchor:.1f}s",
                            "source_events": ["gameplay_climax"],
                            "focal_point": [0.5, 0.65],
                        })

            # If phase 6a audio/SFX timeline is missing, synthesize on-demand
            if not p6a_tl:
                from backend.app.pipeline.audio_event_engine import AudioEventEngine
                aud_engine = AudioEventEngine()
                aud_tl = aud_engine.generate_timeline(
                    candidate_id=candidate_id,
                    candidate=candidate,
                    phase5_timeline=p5_tl,
                    audio_peaks=candidate.get("score_breakdown", {}).get("audio", {}).get("peaks", []),
                )
                p6a_tl = aud_tl.to_dict() if hasattr(aud_tl, "to_dict") else (aud_tl.model_dump() if hasattr(aud_tl, "model_dump") else aud_tl.__dict__)
                if not p6a_tl.get("audio_events") and p5_tl and p5_tl.get("effects"):
                    eff0 = p5_tl["effects"][0]
                    p6a_tl["audio_events"].append({
                        "timestamp": eff0.get("start", 10.0),
                        "event_type": "whoosh",
                        "asset_name": "whoosh_soft.wav",
                        "gain_db": -14.0,
                        "intensity": 0.7,
                        "confidence": 0.8,
                        "source": "visual_effect",
                        "reason": "Climax punch-in whoosh transition",
                    })

            edl_candidate = dict(candidate)
            if is_live and cand_source_clip and source_video_path == cand_source_clip:
                edl_candidate["start"] = 0.0
                edl_candidate["end"] = candidate.get("duration", 60.0)
                edl_candidate["candidate_start"] = 0.0
                edl_candidate["candidate_end"] = candidate.get("duration", 60.0)
                edl_candidate["candidate_duration"] = candidate.get("duration", 60.0)

            edl_gen = TimelineEdlGenerator()
            timeline = edl_gen.generate_edl(
                project_id=proj["video_id"],
                candidate_id=candidate_id,
                candidate=edl_candidate,
                transcript_data=transcript_data,
                phase5_timeline=p5_tl,
                phase6a_timeline=p6a_tl,
                source_video_path=str(source_video_path),
            )
            tl_store.save_timeline(project_dir, timeline, increment_version=False)

        return timeline.model_dump() if hasattr(timeline, "model_dump") else timeline.dict()

    def save_timeline(self, project_id: str, candidate_id: int, timeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validates, tracks dirty changes, and saves TimelineEDL to disk."""
        self._validate_project_id(project_id)
        with self._lock:
            proj = self._projects.get(project_id)
            if not proj:
                raise ValueError("Project not found")
            project_dir = self.output_dir / proj["video_id"]

        from backend.app.pipeline.timeline import TimelineEDL, TimelineValidator, DirtyTracker, TimelineStore
        new_timeline = TimelineEDL(**timeline_data)

        # Shift/trim dependent tracks and disable items outside new boundary duration
        max_dur = new_timeline.boundaries.duration
        for sub in new_timeline.subtitles_track:
            if sub.start >= max_dur:
                sub.enabled = False
            elif sub.end > max_dur:
                sub.end = max_dur
        for emo in new_timeline.emoji_track:
            if emo.timestamp > max_dur:
                emo.enabled = False
        for eff in new_timeline.effects_track:
            if eff.start >= max_dur:
                eff.enabled = False
            elif eff.end > max_dur:
                eff.end = max_dur
        for sfx in new_timeline.sfx_track:
            if sfx.timestamp > max_dur:
                sfx.enabled = False
        for duck in new_timeline.ducking_track:
            if duck.start >= max_dur:
                duck.enabled = False
            elif duck.end > max_dur:
                duck.end = max_dur

        # Validate
        validator = TimelineValidator()
        is_valid, errors = validator.validate(new_timeline)
        if not is_valid:
            raise ValueError(f"Timeline validation failed: {'; '.join(errors)}")

        # Detect dirty tracks against previous version
        tl_store = TimelineStore()
        old_timeline = tl_store.get_timeline(project_dir, candidate_id)
        DirtyTracker.detect_dirty_tracks(old_timeline, new_timeline)

        # Invalidate Creator Quality if dirty tracks present
        if new_timeline.metadata.dirty_tracks:
            new_timeline.metadata.edit_summary = f"User edited tracks: {', '.join(new_timeline.metadata.dirty_tracks)}"
            with self._lock:
                for c in proj.get("candidates", []):
                    if c.get("candidate_id") == candidate_id or c.get("rank") == candidate_id:
                        if "publishability" in c and isinstance(c["publishability"], dict):
                            c["publishability"]["quality_stale"] = True
                            c["publishability"]["recommendation"] = "review"

        saved_tl = tl_store.save_timeline(project_dir, new_timeline, increment_version=True)
        return saved_tl.model_dump() if hasattr(saved_tl, "model_dump") else saved_tl.dict()

    def render_timeline(self, project_id: str, candidate_id: int) -> Dict[str, Any]:
        """Renders final video from the candidate's active TimelineEDL."""
        self._validate_project_id(project_id)
        with self._lock:
            proj = self._projects.get(project_id)
            if not proj:
                raise ValueError("Project not found")
            project_dir = self.output_dir / proj["video_id"]

        from backend.app.pipeline.timeline import TimelineStore, TimelineRenderer
        tl_store = TimelineStore()
        timeline = tl_store.get_timeline(project_dir, candidate_id)
        if not timeline:
            raise FileNotFoundError(f"No timeline found for candidate {candidate_id}")

        renderer = TimelineRenderer()
        render_res = renderer.render_from_timeline(project_dir, timeline)

        # Update project cache with refreshed package and publishability
        with self._lock:
            for pkg in proj.get("published_packages", []):
                if pkg.get("candidate_id") == candidate_id:
                    pkg["publishability"] = render_res["publishability"]
                    break

            for c in proj.get("candidates", []):
                if c.get("candidate_id") == candidate_id or c.get("rank") == candidate_id:
                    c["publishability"] = render_res["publishability"]
                    break

            self._decorate_project(proj)
            proj["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_projects()

        return render_res

    def start_live_session(self, project_id: str, simulation_source: Optional[Path] = None) -> Dict[str, Any]:
        """Initiates rolling capture & analysis for a live stream project."""
        self._validate_project_id(project_id)
        with self._lock:
            proj = self._projects.get(project_id)
            if not proj:
                raise ValueError("Project not found")
            project_dir = self.output_dir / proj["video_id"]
            proj["status"] = "connecting"
            self._save_projects()

        from backend.app.pipeline.live import LiveOrchestrator, LiveStore

        def live_event_handler(event_data: Dict[str, Any]):
            with self._lock:
                p = self._projects.get(project_id)
                if p:
                    p["status"] = event_data.get("session_status", p["status"])
                    if not p.get("live_session_info"):
                        p["live_session_info"] = {}
                    p["live_session_info"].update({
                        "session_id": event_data.get("session_id"),
                        "status": event_data.get("session_status"),
                        "segments_processed": event_data.get("segments_processed", 0),
                        "candidates_detected": event_data.get("candidates_detected", 0),
                        "candidates_ready": event_data.get("candidates_ready", 0),
                    })
                    msg = event_data.get("message", "")
                    if msg:
                        p["progress"]["message"] = msg
                        p["progress"]["stage"] = "Live Capture & Analysis"
                        p["progress"]["logs"].append(f"[{event_data.get('time_str', '')}] {msg}")
                        if len(p["progress"]["logs"]) > 200:
                            p["progress"]["logs"] = p["progress"]["logs"][-200:]
                    p["updated_at"] = datetime.now(timezone.utc).isoformat()

                    # Keep project candidates synced from live store
                    l_store = LiveStore(project_dir)
                    cands = l_store.load_candidates()
                    if cands:
                        p["candidates"] = [c.to_candidate_dict() for c in cands]
                        p["selected_candidate_ids"] = [
                            c.candidate_id for c in cands if c.status in ("publish_ready", "review")
                        ]
                    self._save_projects()

            listeners = self._event_queues.get(project_id, [])
            for cb in listeners:
                try:
                    cb(event_data)
                except Exception:
                    pass

        orchestrator = LiveOrchestrator(
            project_dir=project_dir,
            project_id=project_id,
            source_url=proj["url"],
            source_video_id=proj["video_id"],
            event_callback=live_event_handler,
            simulation_source=simulation_source,
        )
        self._live_orchestrators[project_id] = orchestrator
        orchestrator.start()
        return {"status": "started", "session_id": orchestrator.session.session_id}

    def stop_live_session(self, project_id: str) -> Dict[str, Any]:
        """Stops the active live stream session."""
        orchestrator = self._live_orchestrators.get(project_id)
        if orchestrator:
            orchestrator.stop()
            return {"status": "stopping", "project_id": project_id}
        with self._lock:
            p = self._projects.get(project_id)
            if p:
                p["status"] = "ended"
                self._save_projects()
        return {"status": "stopped", "project_id": project_id}

    def pause_live_session(self, project_id: str) -> Dict[str, Any]:
        """Pauses rolling capture for the live stream."""
        orchestrator = self._live_orchestrators.get(project_id)
        if orchestrator:
            orchestrator.pause()
            return {"status": "paused", "project_id": project_id}
        return {"status": "not_active", "project_id": project_id}

    def resume_live_session(self, project_id: str) -> Dict[str, Any]:
        """Resumes rolling capture for the live stream."""
        orchestrator = self._live_orchestrators.get(project_id)
        if orchestrator:
            orchestrator.resume()
            return {"status": "resumed", "project_id": project_id}
        return self.start_live_session(project_id)

    def get_live_status(self, project_id: str) -> Dict[str, Any]:
        """Retrieves real-time status and telemetry for the live session."""
        self._validate_project_id(project_id)
        with self._lock:
            p = self._projects.get(project_id)
            if not p:
                raise ValueError("Project not found")
            project_dir = self.output_dir / p["video_id"]

        from backend.app.pipeline.live import LiveStore
        l_store = LiveStore(project_dir)
        session = l_store.load_session()
        candidates = l_store.load_candidates()
        activity = l_store.load_activity()

        return {
            "project_id": project_id,
            "session": session.model_dump() if session and hasattr(session, "model_dump") else (session.dict() if session else None),
            "candidates_count": len(candidates),
            "publish_ready_count": sum(1 for c in candidates if c.status == "publish_ready"),
            "activity_recent": [a.model_dump() if hasattr(a, "model_dump") else a.dict() for a in activity[-15:]],
            "storage_used_bytes": l_store.compute_storage_used(),
        }

    def get_live_candidates(self, project_id: str) -> List[Dict[str, Any]]:
        """Retrieves all detected live candidates with global coordinates."""
        self._validate_project_id(project_id)
        with self._lock:
            p = self._projects.get(project_id)
            if not p:
                raise ValueError("Project not found")
            project_dir = self.output_dir / p["video_id"]

        from backend.app.pipeline.live import LiveStore
        l_store = LiveStore(project_dir)
        cands = l_store.load_candidates()
        return [c.to_candidate_dict() for c in cands]

    def get_live_activity(self, project_id: str) -> List[Dict[str, Any]]:
        """Retrieves historical activity log events for the live session."""
        self._validate_project_id(project_id)
        with self._lock:
            p = self._projects.get(project_id)
            if not p:
                raise ValueError("Project not found")
            project_dir = self.output_dir / p["video_id"]

        from backend.app.pipeline.live import LiveStore
        l_store = LiveStore(project_dir)
        events = l_store.load_activity()
        return [e.model_dump() if hasattr(e, "model_dump") else e.dict() for e in events]


