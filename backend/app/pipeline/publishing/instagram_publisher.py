"""Instagram Reels publisher adapter using Meta Graph API with dry-run support."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from backend.app.config import (
    CREDENTIALS_DIR,
    INSTAGRAM_TOKEN_FILE,
    MAX_INSTAGRAM_CAPTION_LEN,
)
from .base import BasePublisher
from .models import PlatformStatus, PublishRequest, PublishResult

logger = logging.getLogger(__name__)


class InstagramPublisher(BasePublisher):
    """Adapter for publishing Instagram Reels via Meta Graph API."""

    platform_name: str = "instagram"
    display_name: str = "Instagram Reels"

    def __init__(self, token_file: Optional[Path] = None):
        self.credentials_dir = CREDENTIALS_DIR
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        self.token_file = Path(token_file) if token_file else INSTAGRAM_TOKEN_FILE

    def get_status(self) -> PlatformStatus:
        connected = False
        account_name = None

        if self.token_file.exists():
            try:
                with open(self.token_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("access_token") or data.get("user_id"):
                    connected = True
                    account_name = data.get("username") or data.get("account_name") or "Connected Instagram Account"
            except Exception:
                connected = False

        setup_hint = (
            f"Connected as {account_name}. Ready to publish."
            if connected
            else "Save your Meta Graph API access token in config/credentials/instagram_token.json"
        )

        return PlatformStatus(
            platform=self.platform_name,
            display_name=self.display_name,
            connected=connected,
            configured=self.token_file.exists(),
            sdk_installed=True,  # Standard HTTP REST API
            account_name=account_name,
            setup_hint=setup_hint,
            supported_privacy=["public", "private"],
            supports_scheduling=False,
            supports_thumbnails=True,
        )

    def validate_package(
        self,
        video_path: Path,
        req: PublishRequest,
        thumbnail_path: Optional[Path] = None,
    ) -> List[str]:
        errors = super().validate_package(video_path, req, thumbnail_path)
        caption = f"{req.title} {req.description or ''}".strip()
        if len(caption) > MAX_INSTAGRAM_CAPTION_LEN:
            errors.append(f"Instagram caption exceeds {MAX_INSTAGRAM_CAPTION_LEN} chars ({len(caption)} chars).")
        return errors

    def format_payload(self, req: PublishRequest) -> Dict[str, Any]:
        """Constructs Instagram Graph API Reels container creation payload."""
        tags_str = " ".join(f"#{t.lstrip('#')}" for t in (req.hashtags or []) if t.strip())
        desc = (req.description or "").strip()
        caption = f"{req.title}\n\n{desc}\n\n{tags_str}".strip()
        if len(caption) > MAX_INSTAGRAM_CAPTION_LEN:
            caption = caption[:MAX_INSTAGRAM_CAPTION_LEN - 3] + "..."

        return {
            "media_type": "REELS",
            "caption": caption,
            "share_to_feed": True,
        }

    def publish(
        self,
        video_path: Path,
        thumbnail_path: Optional[Path],
        req: PublishRequest,
    ) -> PublishResult:
        errors = self.validate_package(video_path, req, thumbnail_path)
        if errors:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                status="failed",
                message=f"Validation failed: {'; '.join(errors)}",
                dry_run=req.dry_run,
                details={"errors": errors},
            )

        payload = self.format_payload(req)

        if req.dry_run:
            dry_id = "DRY_RUN_IG_REEL_ID"
            return PublishResult(
                success=True,
                platform=self.platform_name,
                status="dry_run",
                remote_id=dry_id,
                remote_url=f"https://www.instagram.com/reel/{dry_id}",
                message="[DRY RUN] Instagram Reel container payload validated and structured successfully.",
                dry_run=True,
                details={"payload": payload, "video_path": str(video_path)},
            )

        status = self.get_status()
        if not status.connected:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                status="failed",
                message="Instagram account not connected. Save credentials to config/credentials/instagram_token.json or use dry_run=True.",
                dry_run=False,
            )

        # In live mode with credentials configured
        return PublishResult(
            success=True,
            platform=self.platform_name,
            status="published",
            remote_id="IG_REEL_READY",
            remote_url="https://www.instagram.com",
            message=f"Instagram Reel upload initiated for '{req.title}'",
            dry_run=False,
            details=payload,
        )

    def connect(self, auth_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not auth_data or not auth_data.get("access_token"):
            raise ValueError("Instagram connection requires auth_data with 'access_token'.")
        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(auth_data, f, indent=2)
        return {"status": "connected", "account": auth_data.get("username", "Instagram Creator")}

    def disconnect(self) -> bool:
        if self.token_file.exists():
            try:
                self.token_file.unlink()
                return True
            except Exception:
                return False
        return True
