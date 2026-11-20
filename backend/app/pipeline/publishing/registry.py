"""Registry and historical audit store for social media publishers."""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from backend.app.config import DEFAULT_OUTPUT_DIR
from .base import BasePublisher
from .models import PlatformStatus, PublishRequest, PublishResult
from .youtube_publisher import YouTubePublisher
from .tiktok_publisher import TikTokPublisher
from .instagram_publisher import InstagramPublisher


class PublisherRegistry:
    """Central registry and lookup for social media platform publishing adapters."""

    def __init__(self):
        self._publishers: Dict[str, BasePublisher] = {
            "youtube": YouTubePublisher(),
            "tiktok": TikTokPublisher(),
            "instagram": InstagramPublisher(),
        }

    def register(self, platform: str, publisher: BasePublisher) -> None:
        self._publishers[platform.lower()] = publisher

    def get_publisher(self, platform: str) -> BasePublisher:
        norm = platform.lower()
        if norm not in self._publishers:
            supported = ", ".join(self._publishers.keys())
            raise ValueError(f"Unsupported publishing platform '{platform}'. Supported: {supported}")
        return self._publishers[norm]

    def list_platform_statuses(self) -> List[PlatformStatus]:
        return [pub.get_status() for pub in self._publishers.values()]


class PublishHistoryStore:
    """Atomically records and audits all publishing events per project."""

    def __init__(self, base_output_dir: Optional[Path] = None):
        self.base_output_dir = Path(base_output_dir) if base_output_dir else DEFAULT_OUTPUT_DIR

    def _get_history_file(self, project_id: str) -> Path:
        proj_dir = self.base_output_dir / project_id / "publishing"
        proj_dir.mkdir(parents=True, exist_ok=True)
        return proj_dir / "publish_history.json"

    def get_history(self, project_id: str) -> List[Dict[str, Any]]:
        history_file = self._get_history_file(project_id)
        if not history_file.exists():
            return []
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return sorted(data, key=lambda x: x.get("timestamp", ""), reverse=True)
        except Exception:
            return []

    def get_candidate_history(self, project_id: str, candidate_id: int) -> List[Dict[str, Any]]:
        all_hist = self.get_history(project_id)
        return [h for h in all_hist if h.get("candidate_id") == candidate_id]

    def already_published(self, project_id: str, candidate_id: int, platform: str) -> bool:
        """Checks if a candidate has already been successfully published or scheduled to a platform (non-dry-run)."""
        cand_hist = self.get_candidate_history(project_id, candidate_id)
        for h in cand_hist:
            if (
                h.get("platform", "").lower() == platform.lower()
                and h.get("success") is True
                and h.get("dry_run") is False
                and h.get("status") in ("published", "scheduled")
            ):
                return True
        return False

    def record_publish(
        self,
        project_id: str,
        result: PublishResult,
        req: PublishRequest,
    ) -> Dict[str, Any]:
        """Atomically persists a publish or dry-run execution record."""
        history_file = self._get_history_file(project_id)
        history_dir = history_file.parent
        history_dir.mkdir(parents=True, exist_ok=True)

        existing = []
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        entry = {
            "project_id": project_id,
            "candidate_id": req.candidate_id,
            "platform": result.platform,
            "status": result.status,
            "success": result.success,
            "remote_id": result.remote_id,
            "remote_url": result.remote_url,
            "message": result.message,
            "timestamp": result.timestamp,
            "dry_run": result.dry_run,
            "title": req.title,
            "privacy": req.privacy,
            "scheduled_publish_at": req.scheduled_publish_at,
            "upload_thumbnail": req.upload_thumbnail,
        }

        existing.append(entry)

        # Atomic file write using temp file and replace in same folder
        fd, temp_path = tempfile.mkstemp(prefix="pub_hist_", suffix=".tmp", dir=str(history_dir))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        os.replace(temp_path, history_file)
        return entry
