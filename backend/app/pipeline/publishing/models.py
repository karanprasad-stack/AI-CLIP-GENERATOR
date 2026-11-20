"""Data models and schemas for social media publishing layer."""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field

PlatformType = Literal["youtube", "tiktok", "instagram"]
PrivacyStatus = Literal["private", "unlisted", "public"]
PublishStatus = Literal["published", "scheduled", "dry_run", "failed"]


class PublishRequest(BaseModel):
    """Request payload to publish a candidate package to a target platform."""
    project_id: str
    candidate_id: int
    platform: str = "youtube"
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = ""
    hashtags: Optional[List[str]] = Field(default_factory=list)
    privacy: str = Field(default="private", description="private, unlisted, public")
    scheduled_publish_at: Optional[str] = Field(default=None, description="ISO 8601 UTC timestamp")
    upload_thumbnail: bool = True
    dry_run: bool = False
    aspect_ratio: str = "9:16"
    extra_params: Optional[Dict[str, Any]] = None


class PublishResult(BaseModel):
    """Result of publishing or simulating a social media upload."""
    success: bool
    platform: str
    status: str = Field(..., description="published, scheduled, dry_run, failed")
    remote_id: Optional[str] = None
    remote_url: Optional[str] = None
    message: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dry_run: bool = False
    details: Optional[Dict[str, Any]] = None


class PlatformStatus(BaseModel):
    """Live connection, configuration, and SDK availability state for a platform."""
    platform: str
    display_name: str
    connected: bool = False
    configured: bool = False
    sdk_installed: bool = True
    account_name: Optional[str] = None
    setup_hint: str = ""
    supported_privacy: List[str] = Field(default_factory=lambda: ["private", "unlisted", "public"])
    supports_scheduling: bool = True
    supports_thumbnails: bool = True
