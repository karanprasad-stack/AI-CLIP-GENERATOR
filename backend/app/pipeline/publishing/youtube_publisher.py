"""YouTube Shorts publisher adapter using local OAuth 2.0 with resumable uploads."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from backend.app.config import (
    CREDENTIALS_DIR,
    YOUTUBE_CLIENT_SECRETS_FILE,
    YOUTUBE_TOKEN_FILE,
    YOUTUBE_DEFAULT_CATEGORY_ID,
    MAX_YOUTUBE_SHORTS_TITLE_LEN,
)
from .base import BasePublisher
from .models import PlatformStatus, PublishRequest, PublishResult

logger = logging.getLogger(__name__)

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class YouTubePublisher(BasePublisher):
    """Adapter for publishing YouTube Shorts using official Google APIs."""

    platform_name: str = "youtube"
    display_name: str = "YouTube Shorts"

    def __init__(
        self,
        client_secrets_file: Optional[Path] = None,
        token_file: Optional[Path] = None,
    ):
        self.credentials_dir = CREDENTIALS_DIR
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        self.client_secrets_file = Path(client_secrets_file) if client_secrets_file else YOUTUBE_CLIENT_SECRETS_FILE
        self.token_file = Path(token_file) if token_file else YOUTUBE_TOKEN_FILE

    @staticmethod
    def _is_sdk_installed() -> bool:
        """Checks if optional Google client libraries are installed in the Python environment."""
        try:
            import googleapiclient.discovery  # noqa: F401
            import googleapiclient.http  # noqa: F401
            import google_auth_oauthlib.flow  # noqa: F401
            import google.oauth2.credentials  # noqa: F401
            return True
        except ImportError:
            return False

    def get_status(self) -> PlatformStatus:
        """Evaluates live readiness, connection state, and local credentials."""
        sdk_ok = self._is_sdk_installed()
        configured = self.client_secrets_file.exists()
        connected = False
        account_name = None

        if self.token_file.exists():
            try:
                with open(self.token_file, "r", encoding="utf-8") as f:
                    token_data = json.load(f)
                if token_data.get("token") or token_data.get("refresh_token"):
                    connected = True
                    account_name = token_data.get("channel_title") or token_data.get("account_name") or "Connected YouTube Channel"
            except Exception:
                connected = False

        if not sdk_ok:
            setup_hint = "Install Google API client: pip install google-api-python-client google-auth-oauthlib"
        elif not configured:
            setup_hint = f"Place your OAuth client secrets JSON at {self.client_secrets_file.name} in config/credentials/"
        elif not connected:
            setup_hint = "Click Connect to authorize your YouTube channel via Google OAuth."
        else:
            setup_hint = f"Connected as {account_name}. Ready to publish YouTube Shorts."

        return PlatformStatus(
            platform=self.platform_name,
            display_name=self.display_name,
            connected=connected,
            configured=configured,
            sdk_installed=sdk_ok,
            account_name=account_name,
            setup_hint=setup_hint,
            supported_privacy=["private", "unlisted", "public"],
            supports_scheduling=True,
            supports_thumbnails=True,
        )

    def validate_package(
        self,
        video_path: Path,
        req: PublishRequest,
        thumbnail_path: Optional[Path] = None,
    ) -> List[str]:
        """Validates YouTube Shorts constraints (existence, format, duration <= 180s)."""
        errors = super().validate_package(video_path, req, thumbnail_path)
        return errors

    def format_metadata(self, req: PublishRequest) -> Dict[str, Any]:
        """Constructs YouTube API resource metadata dict adhering to Shorts requirements."""
        title = req.title.strip()
        if len(title) > MAX_YOUTUBE_SHORTS_TITLE_LEN:
            title = title[:MAX_YOUTUBE_SHORTS_TITLE_LEN - 3].rstrip() + "..."

        desc = req.description.strip() if req.description else ""
        tags = [t.lstrip("#") for t in (req.hashtags or []) if t.strip()]

        # Ensure #Shorts is present in title or description for vertical 9:16 videos
        has_shorts_tag = "#shorts" in title.lower() or "#shorts" in desc.lower()
        if not has_shorts_tag and req.aspect_ratio == "9:16":
            if desc:
                desc = f"{desc}\n\n#Shorts"
            else:
                desc = "#Shorts"

        # Format hashtags section into description if not already there
        if req.hashtags:
            hash_str = " ".join(f"#{t.lstrip('#')}" for t in req.hashtags if t.strip())
            if hash_str and hash_str not in desc:
                desc = f"{desc}\n\n{hash_str}".strip()

        privacy = req.privacy if req.privacy in ("private", "unlisted", "public") else "private"
        publish_at = None

        if req.scheduled_publish_at:
            # YouTube requires privacyStatus to be "private" when scheduling
            privacy = "private"
            publish_at = req.scheduled_publish_at

        status_dict: Dict[str, Any] = {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        }
        if publish_at:
            status_dict["publishAt"] = publish_at

        return {
            "snippet": {
                "title": title,
                "description": desc,
                "tags": tags[:30],
                "categoryId": YOUTUBE_DEFAULT_CATEGORY_ID,
            },
            "status": status_dict,
            "publish_at": publish_at,
            "final_title": title,
            "final_desc": desc,
        }

    def publish(
        self,
        video_path: Path,
        thumbnail_path: Optional[Path],
        req: PublishRequest,
    ) -> PublishResult:
        """Executes YouTube Shorts upload (or simulation if dry_run=True)."""
        validation_errors = self.validate_package(video_path, req, thumbnail_path)
        if validation_errors:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                status="failed",
                message=f"Validation failed: {'; '.join(validation_errors)}",
                dry_run=req.dry_run,
                details={"errors": validation_errors},
            )

        formatted = self.format_metadata(req)
        body = {
            "snippet": formatted["snippet"],
            "status": formatted["status"],
        }
        publish_at = formatted["publish_at"]

        # Dry Run Mode: Return payload without touching Google network
        if req.dry_run:
            dry_id = "DRY_RUN_YT_SHORTS"
            return PublishResult(
                success=True,
                platform=self.platform_name,
                status="dry_run",
                remote_id=dry_id,
                remote_url=f"https://youtube.com/shorts/{dry_id}",
                message=f"[DRY RUN] YouTube Shorts package validated. Ready to publish as '{formatted['final_title']}' ({formatted['status']['privacyStatus']}).",
                dry_run=True,
                details={
                    "payload": body,
                    "video_path": str(video_path),
                    "thumbnail_path": str(thumbnail_path) if thumbnail_path else None,
                    "scheduled_publish_at": publish_at,
                },
            )

        # Real Network Upload Flow
        if not self._is_sdk_installed():
            return PublishResult(
                success=False,
                platform=self.platform_name,
                status="failed",
                message="Google client libraries missing. Run 'pip install google-api-python-client google-auth-oauthlib'.",
                dry_run=False,
            )

        status = self.get_status()
        if not status.connected:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                status="failed",
                message="YouTube account not connected. Please connect your channel first or test with dry_run=True.",
                dry_run=False,
            )

        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request as GoogleRequest

            with open(self.token_file, "r", encoding="utf-8") as f:
                token_data = json.load(f)

            creds = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes", YOUTUBE_SCOPES),
            )

            if creds.expired and creds.refresh_token:
                creds.refresh(GoogleRequest())
                with open(self.token_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "token": creds.token,
                        "refresh_token": creds.refresh_token,
                        "token_uri": creds.token_uri,
                        "client_id": creds.client_id,
                        "client_secret": creds.client_secret,
                        "scopes": creds.scopes,
                        "channel_title": status.account_name,
                    }, f, indent=2)

            youtube = build("youtube", "v3", credentials=creds)

            # Resumable video upload
            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024 * 4,
            )

            insert_request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            resp = None
            while resp is None:
                _, resp = insert_request.next_chunk()

            video_id = resp.get("id")
            if not video_id:
                return PublishResult(
                    success=False,
                    platform=self.platform_name,
                    status="failed",
                    message="Upload completed but YouTube returned no video ID.",
                    dry_run=False,
                    details=resp,
                )

            # Upload custom thumbnail if requested and available
            thumb_warning = None
            if req.upload_thumbnail and thumbnail_path and Path(thumbnail_path).exists():
                try:
                    thumb_media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
                    youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
                except Exception as e:
                    thumb_warning = f"Custom thumbnail upload skipped: {e} (channel requires phone verification for custom thumbnails)"
                    logger.warning(thumb_warning)

            msg = f"Published to YouTube Shorts: https://youtube.com/shorts/{video_id}"
            if thumb_warning:
                msg += f" ({thumb_warning})"

            return PublishResult(
                success=True,
                platform=self.platform_name,
                status="scheduled" if publish_at else "published",
                remote_id=video_id,
                remote_url=f"https://youtube.com/shorts/{video_id}",
                message=msg,
                dry_run=False,
                details=resp,
            )

        except Exception as e:
            logger.exception("YouTube upload failed")
            return PublishResult(
                success=False,
                platform=self.platform_name,
                status="failed",
                message=f"YouTube upload failed: {str(e)}",
                dry_run=False,
            )

    def connect(self, auth_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Initiates or finishes Google OAuth 2.0 connection.
        If auth_data provides a token or auth_code, stores it.
        Otherwise creates an InstalledAppFlow if running locally.
        """
        if not self._is_sdk_installed():
            raise RuntimeError("Google API client SDK not installed. Run 'pip install google-api-python-client google-auth-oauthlib'.")

        if not self.client_secrets_file.exists():
            raise FileNotFoundError(f"OAuth client secrets not found at {self.client_secrets_file}. Download OAuth 2.0 Client Secrets from Google Cloud Console.")

        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        # If token data directly passed:
        if auth_data and "token" in auth_data:
            with open(self.token_file, "w", encoding="utf-8") as f:
                json.dump(auth_data, f, indent=2)
            return {"status": "connected", "channel": auth_data.get("channel_title", "Connected Channel")}

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.client_secrets_file),
            scopes=YOUTUBE_SCOPES,
        )

        creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

        # Fetch channel snippet to display channel title
        channel_title = "Connected YouTube Channel"
        try:
            youtube = build("youtube", "v3", credentials=creds)
            ch_resp = youtube.channels().list(part="snippet", mine=True).execute()
            items = ch_resp.get("items", [])
            if items:
                channel_title = items[0]["snippet"].get("title", channel_title)
        except Exception:
            pass

        token_dict = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
            "channel_title": channel_title,
        }

        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(token_dict, f, indent=2)

        return {"status": "connected", "channel": channel_title}

    def disconnect(self) -> bool:
        """Removes local stored YouTube OAuth token."""
        if self.token_file.exists():
            try:
                self.token_file.unlink()
                return True
            except Exception:
                return False
        return True
