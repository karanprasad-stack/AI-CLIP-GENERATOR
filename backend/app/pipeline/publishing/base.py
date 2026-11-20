"""Base abstract publisher interface for all social platform adapters."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from .models import PlatformStatus, PublishRequest, PublishResult


class BasePublisher(ABC):
    """Abstract base class for social media publishing adapters."""

    platform_name: str = "base"
    display_name: str = "Base Publisher"

    @abstractmethod
    def get_status(self) -> PlatformStatus:
        """Returns the current connection, SDK, and configuration status."""
        pass

    def validate_package(
        self,
        video_path: Path,
        req: PublishRequest,
        thumbnail_path: Optional[Path] = None,
    ) -> List[str]:
        """
        Validates package assets and metadata constraints before upload.
        Returns a list of error strings (empty if completely valid).
        """
        errors: List[str] = []

        if not video_path:
            errors.append("Video path not specified.")
        elif not Path(video_path).exists():
            errors.append(f"Rendered video file not found at {video_path}")
        elif Path(video_path).stat().st_size < 1000:
            errors.append(f"Video file is empty or corrupted ({video_path})")

        if not req.title or not req.title.strip():
            errors.append("Title cannot be empty.")

        if req.privacy not in ("private", "unlisted", "public"):
            errors.append(f"Invalid privacy level: {req.privacy}. Must be private, unlisted, or public.")

        if req.scheduled_publish_at:
            try:
                # Parse timestamp and check it is in the future
                dt = datetime.fromisoformat(req.scheduled_publish_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if dt <= now:
                    errors.append("Scheduled publish time must be in the future.")
            except Exception as e:
                errors.append(f"Invalid scheduled_publish_at timestamp: {e}")

        if req.upload_thumbnail and thumbnail_path:
            tpath = Path(thumbnail_path)
            if not tpath.exists() or tpath.stat().st_size < 100:
                # Warning rather than blocker
                pass

        return errors

    @abstractmethod
    def publish(
        self,
        video_path: Path,
        thumbnail_path: Optional[Path],
        req: PublishRequest,
    ) -> PublishResult:
        """Executes publishing (or simulation if dry_run=True)."""
        pass

    @abstractmethod
    def connect(self, auth_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Initiates or completes OAuth authorization flow."""
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """Removes local stored credentials / tokens for this platform."""
        pass
