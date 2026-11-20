"""Phase 13 Publishing Layer Tests:
- PublisherRegistry multi-platform registration and status discovery
- YouTubePublisher metadata formatting, Shorts constraints & dry_run payload simulation
- YouTubePublisher mocked live resumable upload & thumbnail handling
- TikTokPublisher & InstagramPublisher payload validation & dry-run simulation
- PublishHistoryStore atomic persistence & duplicate-publish detection
- FastAPI endpoints for platform status, connect/disconnect, publishing & history
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from starlette.testclient import TestClient

from backend.app.server import app
from backend.app.pipeline.publishing import (
    PublisherRegistry,
    PublishHistoryStore,
    PublishRequest,
    PublishResult,
    YouTubePublisher,
    TikTokPublisher,
    InstagramPublisher,
)


class TestPhase13Publishing(unittest.TestCase):
    def setUp(self):
        t_base = Path(__file__).resolve().parent.parent / "temp"
        t_base.mkdir(parents=True, exist_ok=True)
        self.test_dir = Path(tempfile.mkdtemp(prefix="pub_test_", dir=t_base))
        self.output_dir = self.test_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.credentials_dir = self.test_dir / "credentials"
        self.credentials_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy video and thumbnail files
        self.dummy_video = self.test_dir / "final.mp4"
        self.dummy_video.write_bytes(b"0" * 5000)

        self.dummy_thumb = self.test_dir / "thumbnail.jpg"
        self.dummy_thumb.write_bytes(b"0" * 3000)

        self.client = TestClient(app)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 1. Publisher Registry & Multi-Platform Status Discovery
    # --------------------------------------------------------------------------
    def test_publisher_registry_lists_all_platforms_cleanly(self):
        """PublisherRegistry lists youtube, tiktok, and instagram cleanly with no credentials or optional SDKs."""
        registry = PublisherRegistry()
        statuses = registry.list_platform_statuses()
        platforms = [s.platform for s in statuses]

        self.assertIn("youtube", platforms)
        self.assertIn("tiktok", platforms)
        self.assertIn("instagram", platforms)

        for s in statuses:
            self.assertIsInstance(s.connected, bool)
            self.assertIsInstance(s.setup_hint, str)
            self.assertGreater(len(s.supported_privacy), 0)

        # Invalid platform check
        with self.assertRaises(ValueError):
            registry.get_publisher("non_existent_platform")

    # --------------------------------------------------------------------------
    # 2. YouTubePublisher: Metadata formatting & Dry-Run Simulation
    # --------------------------------------------------------------------------
    def test_youtube_publisher_dry_run_formatting_and_validation(self):
        """YouTubePublisher enforces <= 100 char title, adds #Shorts for 9:16, sets Gaming category, and returns dry_run."""
        pub = YouTubePublisher(
            client_secrets_file=self.credentials_dir / "youtube_client_secrets.json",
            token_file=self.credentials_dir / "youtube_token.json",
        )

        long_title = "INSANE Valorant 1v5 Clutch Ace By Pro Player That Completely Broke The Entire Competitive Lobby Today"
        req = PublishRequest(
            project_id="test_p1",
            candidate_id=1,
            platform="youtube",
            title=long_title,
            description="Subscribe for more daily gaming clips!",
            hashtags=["#valorant", "#clutch", "#ace"],
            privacy="private",
            aspect_ratio="9:16",
            dry_run=True,
        )

        res = pub.publish(video_path=self.dummy_video, thumbnail_path=self.dummy_thumb, req=req)

        self.assertTrue(res.success)
        self.assertEqual(res.status, "dry_run")
        self.assertTrue(res.dry_run)
        self.assertIn("youtube.com/shorts", res.remote_url)

        # Check payload formatting
        payload = res.details["payload"]
        snippet = payload["snippet"]
        status = payload["status"]

        self.assertLessEqual(len(snippet["title"]), 100)
        self.assertIn("#Shorts", snippet["description"])
        self.assertEqual(snippet["categoryId"], "20")  # Gaming category
        self.assertEqual(status["privacyStatus"], "private")

    def test_youtube_publisher_scheduled_publish_forces_private(self):
        """Scheduled publish on YouTube forces privacyStatus: 'private' and populates publishAt."""
        pub = YouTubePublisher(
            client_secrets_file=self.credentials_dir / "youtube_client_secrets.json",
            token_file=self.credentials_dir / "youtube_token.json",
        )

        future_iso = "2029-12-01T15:00:00Z"
        req = PublishRequest(
            project_id="test_p1",
            candidate_id=1,
            platform="youtube",
            title="Scheduled Valorant Short",
            privacy="public",  # should be forced to private when scheduled
            scheduled_publish_at=future_iso,
            dry_run=True,
        )

        res = pub.publish(video_path=self.dummy_video, thumbnail_path=None, req=req)
        self.assertTrue(res.success)
        payload = res.details["payload"]
        self.assertEqual(payload["status"]["privacyStatus"], "private")
        self.assertEqual(payload["status"]["publishAt"], future_iso)

    # --------------------------------------------------------------------------
    # 3. YouTubePublisher: Mocked Live Upload & Thumbnail Handling
    # --------------------------------------------------------------------------
    def test_youtube_publisher_mocked_live_upload(self):
        """Mocked live YouTube upload performs resumable chunked upload and returns published status."""
        pub = YouTubePublisher(
            client_secrets_file=self.credentials_dir / "youtube_client_secrets.json",
            token_file=self.credentials_dir / "youtube_token.json",
        )

        # Mock token file
        with open(pub.token_file, "w", encoding="utf-8") as f:
            json.dump({"token": "fake_token", "refresh_token": "fake_refresh", "channel_title": "Test Channel"}, f)

        req = PublishRequest(
            project_id="test_p1",
            candidate_id=1,
            platform="youtube",
            title="Epic Headshot",
            privacy="unlisted",
            dry_run=False,
        )

        # Mock google API client
        mock_youtube = MagicMock()
        mock_videos = MagicMock()
        mock_insert = MagicMock()
        mock_insert.next_chunk.return_value = (None, {"id": "YT_REAL_12345", "status": {"privacyStatus": "unlisted"}})
        mock_videos.insert.return_value = mock_insert
        mock_youtube.videos.return_value = mock_videos

        mock_thumbs = MagicMock()
        mock_thumbs_set = MagicMock()
        mock_thumbs.set.return_value = mock_thumbs_set
        mock_youtube.thumbnails.return_value = mock_thumbs

        mock_creds_mod = MagicMock()
        mock_discovery_mod = MagicMock()
        mock_http_mod = MagicMock()
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds_mod.Credentials.return_value = mock_creds
        mock_discovery_mod.build.return_value = mock_youtube

        modules_patch = {
            "google": MagicMock(),
            "google.oauth2": MagicMock(),
            "google.oauth2.credentials": mock_creds_mod,
            "google.auth": MagicMock(),
            "google.auth.transport": MagicMock(),
            "google.auth.transport.requests": MagicMock(),
            "googleapiclient": MagicMock(),
            "googleapiclient.discovery": mock_discovery_mod,
            "googleapiclient.http": mock_http_mod,
            "google_auth_oauthlib": MagicMock(),
            "google_auth_oauthlib.flow": MagicMock(),
        }

        with patch.dict("sys.modules", modules_patch), \
             patch.object(pub, "_is_sdk_installed", return_value=True):

            res = pub.publish(video_path=self.dummy_video, thumbnail_path=self.dummy_thumb, req=req)

            self.assertTrue(res.success)
            self.assertEqual(res.status, "published")
            self.assertEqual(res.remote_id, "YT_REAL_12345")
            self.assertEqual(res.remote_url, "https://youtube.com/shorts/YT_REAL_12345")
            self.assertFalse(res.dry_run)
            mock_thumbs_set.execute.assert_called_once()

    # --------------------------------------------------------------------------
    # 4. TikTokPublisher & InstagramPublisher: Validation & Dry-Run
    # --------------------------------------------------------------------------
    def test_tiktok_and_instagram_publishers_dry_run(self):
        """TikTok and Instagram publishers format platform-specific payloads and simulate cleanly."""
        tt = TikTokPublisher(token_file=self.credentials_dir / "tiktok_token.json")
        ig = InstagramPublisher(token_file=self.credentials_dir / "instagram_token.json")

        req_tt = PublishRequest(
            project_id="p1", candidate_id=1, platform="tiktok",
            title="Crazy Physics Fail #gaming", privacy="public", dry_run=True
        )
        res_tt = tt.publish(video_path=self.dummy_video, thumbnail_path=None, req=req_tt)
        self.assertTrue(res_tt.success)
        self.assertEqual(res_tt.status, "dry_run")
        self.assertEqual(res_tt.details["payload"]["post_info"]["privacy_level"], "PUBLIC_TO_EVERYONE")

        req_ig = PublishRequest(
            project_id="p1", candidate_id=1, platform="instagram",
            title="GTA VI Stunt Jump", privacy="public", dry_run=True
        )
        res_ig = ig.publish(video_path=self.dummy_video, thumbnail_path=None, req=req_ig)
        self.assertTrue(res_ig.success)
        self.assertEqual(res_ig.status, "dry_run")
        self.assertEqual(res_ig.details["payload"]["media_type"], "REELS")

    # --------------------------------------------------------------------------
    # 5. PublishHistoryStore: Atomic Persistence & Duplicate Detection
    # --------------------------------------------------------------------------
    def test_publish_history_store_atomic_persistence_and_duplicate_check(self):
        """PublishHistoryStore records attempts and correctly detects duplicate non-dry-run uploads."""
        store = PublishHistoryStore(base_output_dir=self.output_dir)
        proj_id = "proj_hist_test"

        # Initially empty
        self.assertEqual(len(store.get_history(proj_id)), 0)
        self.assertFalse(store.already_published(proj_id, 1, "youtube"))

        # 1. Record dry run
        req_dry = PublishRequest(project_id=proj_id, candidate_id=1, platform="youtube", title="Dry Run Clip", dry_run=True)
        res_dry = PublishResult(success=True, platform="youtube", status="dry_run", message="simulated", dry_run=True)
        store.record_publish(proj_id, res_dry, req_dry)

        # Dry run should NOT trigger already_published
        self.assertEqual(len(store.get_history(proj_id)), 1)
        self.assertFalse(store.already_published(proj_id, 1, "youtube"))

        # 2. Record live publish
        req_live = PublishRequest(project_id=proj_id, candidate_id=1, platform="youtube", title="Live Clip", dry_run=False)
        res_live = PublishResult(success=True, platform="youtube", status="published", remote_id="LIVE_123", remote_url="https://youtube.com/shorts/LIVE_123", message="published", dry_run=False)
        store.record_publish(proj_id, res_live, req_live)

        # Now already_published should return True
        self.assertEqual(len(store.get_history(proj_id)), 2)
        self.assertTrue(store.already_published(proj_id, 1, "youtube"))
        self.assertFalse(store.already_published(proj_id, 2, "youtube"))  # different candidate
        self.assertFalse(store.already_published(proj_id, 1, "tiktok"))   # different platform

    # --------------------------------------------------------------------------
    # 6. FastAPI REST Endpoints Integration
    # --------------------------------------------------------------------------
    def test_api_publishing_endpoints(self):
        """GET /api/publishing/platforms and POST publish (dry_run) return structured 200 responses."""
        # 1. Platform status endpoint
        resp = self.client.get("/api/publishing/platforms")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 3)

        # 2. Publish endpoint with dry_run=True on a real or mock project
        from backend.app.api.router import project_manager
        proj = project_manager.create_project(url="https://youtube.com/watch?v=TEST_PUB_123", title="Pub Test")
        proj_id = proj["id"]

        # Place dummy final.mp4 in publishing folder
        cand_dir = project_manager.output_dir / proj_id / "publishing" / "candidate_01"
        cand_dir.mkdir(parents=True, exist_ok=True)
        (cand_dir / "final.mp4").write_bytes(b"0" * 4000)

        pub_payload = {
            "platform": "youtube",
            "title": "API Test Shorts Title",
            "description": "API Test description",
            "hashtags": ["#shorts", "#api"],
            "privacy": "private",
            "dry_run": True,
        }

        pub_resp = self.client.post(f"/api/projects/{proj_id}/candidates/1/publish", json=pub_payload)
        self.assertEqual(pub_resp.status_code, 200)
        pub_data = pub_resp.json()
        self.assertTrue(pub_data["success"])
        self.assertEqual(pub_data["status"], "dry_run")
        self.assertTrue(pub_data["dry_run"])

        # 3. Publish history endpoint
        hist_resp = self.client.get(f"/api/projects/{proj_id}/publish-history")
        self.assertEqual(hist_resp.status_code, 200)
        hist_data = hist_resp.json()
        self.assertEqual(len(hist_data), 1)
        self.assertEqual(hist_data[0]["candidate_id"], 1)
        self.assertEqual(hist_data[0]["status"], "dry_run")

        # Clean up created project
        project_manager.delete_project(proj_id)


if __name__ == "__main__":
    unittest.main()
