"""Unit tests for pre-render video preview, audio HTTP 206 streaming, and candidate metadata decoration."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from starlette.testclient import TestClient

from backend.app.server import app
from backend.app.services.project_manager import ProjectManager
import backend.app.api.router as router_module


class TestPreRenderPreview(unittest.TestCase):
    def setUp(self):
        t_base = Path(__file__).resolve().parent.parent / "temp"
        t_base.mkdir(parents=True, exist_ok=True)
        self.test_dir = Path(tempfile.mkdtemp(prefix="prerender_test_", dir=t_base))
        self.output_dir = self.test_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pm = ProjectManager(base_output_dir=self.output_dir)

        # Temporarily point router's project_manager to self.pm for API route tests
        self._orig_pm = router_module.project_manager
        router_module.project_manager = self.pm
        self.client = TestClient(app)

    def tearDown(self):
        router_module.project_manager = self._orig_pm
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_project_decoration_source_video_and_youtube_id(self):
        """Verifies that has_source_video, source_video_url, has_audio, audio_url, and youtube_video_id are set."""
        vid_id = "prerend0001"
        proj_dir = self.output_dir / vid_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        source_mp4 = proj_dir / "source.mp4"
        source_mp4.write_bytes(b"A" * 500)
        audio_wav = proj_dir / "audio.wav"
        audio_wav.write_bytes(b"B" * 300)

        transcript_data = {
            "segments": [
                {"start": 0.0, "end": 10.0, "text": "Intro talking here."},
                {"start": 12.0, "end": 28.0, "text": "Incredible clutch play right now!"},
                {"start": 30.0, "end": 45.0, "text": "He got the ace!"},
            ]
        }
        (proj_dir / "transcript.json").write_text(json.dumps(transcript_data), encoding="utf-8")

        proj = self.pm.create_project(
            f"https://www.youtube.com/watch?v={vid_id}",
            title="Valorant Stream Match",
        )
        proj["candidates"] = [
            {"rank": 1, "start": 11.0, "end": 35.0, "duration": 24.0, "final_score": 92.0},
            {"rank": 2, "start": 50.0, "end": 75.0, "duration": 25.0, "final_score": 60.0},
        ]
        self.pm._save_projects()

        decorated = self.pm.get_project(proj["id"])
        self.assertIsNotNone(decorated)
        self.assertTrue(decorated["has_source_video"])
        self.assertEqual(decorated["source_video_url"], f"/api/projects/{proj['id']}/source-video")
        self.assertTrue(decorated["has_audio"])
        self.assertEqual(decorated["audio_url"], f"/api/projects/{proj['id']}/audio")
        self.assertEqual(decorated["youtube_video_id"], vid_id)

        # Check transcript excerpt extraction
        c1 = decorated["candidates"][0]
        self.assertIn("Incredible clutch play right now!", c1["transcript_excerpt"])
        self.assertIn("He got the ace!", c1["transcript_excerpt"])

        c2 = decorated["candidates"][1]
        self.assertEqual(c2["transcript_excerpt"], "")

        # Verify that GET /api/projects/{id} via FastAPI TestClient preserves all preview fields (not stripped by Pydantic)
        api_resp = self.client.get(f"/api/projects/{proj['id']}")
        self.assertEqual(api_resp.status_code, 200)
        api_data = api_resp.json()
        self.assertTrue(api_data.get("has_source_video"))
        self.assertEqual(api_data.get("source_video_url"), f"/api/projects/{proj['id']}/source-video")
        self.assertTrue(api_data.get("has_audio"))
        self.assertEqual(api_data.get("audio_url"), f"/api/projects/{proj['id']}/audio")
        self.assertEqual(api_data.get("youtube_video_id"), vid_id)
        self.assertIn("Incredible clutch play right now!", api_data["candidates"][0]["transcript_excerpt"])

    def test_youtube_video_id_extraction_all_sources(self):
        """Verifies youtube_video_id extraction from raw 11-char ID, metadata.json, and shorts/urls without source.mp4."""
        vid_id = "testraw11ch"
        proj_dir = self.output_dir / vid_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        # Write metadata.json and audio.wav (no source.mp4)
        meta = {
            "id": vid_id,
            "title": "Raw 11-Char Video",
            "url": f"https://www.youtube.com/shorts/{vid_id}",
        }
        (proj_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        (proj_dir / "audio.wav").write_bytes(b"AUDIO" * 20)

        proj = self.pm.create_project(
            f"https://www.youtube.com/shorts/{vid_id}",
            title="Shorts Test",
        )
        api_resp = self.client.get(f"/api/projects/{proj['id']}")
        self.assertEqual(api_resp.status_code, 200)
        api_data = api_resp.json()

        self.assertFalse(api_data.get("has_source_video"))
        self.assertIsNone(api_data.get("source_video_url"))
        self.assertTrue(api_data.get("has_audio"))
        self.assertEqual(api_data.get("youtube_video_id"), vid_id)

    def test_source_video_http_206_streaming(self):
        """Tests GET /api/projects/{id}/source-video with full and byte-range requests."""
        vid_id = "stream00001"
        proj_dir = self.output_dir / vid_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        video_bytes = b"X" * 2048
        (proj_dir / "source.mp4").write_bytes(video_bytes)

        proj = self.pm.create_project(f"https://www.youtube.com/watch?v={vid_id}", title="Test Video Stream")

        # Full GET
        resp_full = self.client.get(f"/api/projects/{proj['id']}/source-video")
        self.assertEqual(resp_full.status_code, 200)
        self.assertEqual(resp_full.headers["content-type"], "video/mp4")
        self.assertEqual(resp_full.headers["accept-ranges"], "bytes")
        self.assertEqual(int(resp_full.headers["content-length"]), 2048)

        # Partial GET (bytes=0-99)
        resp_part = self.client.get(
            f"/api/projects/{proj['id']}/source-video",
            headers={"Range": "bytes=0-99"},
        )
        self.assertEqual(resp_part.status_code, 206)
        self.assertEqual(resp_part.headers["content-type"], "video/mp4")
        self.assertEqual(resp_part.headers["accept-ranges"], "bytes")
        self.assertEqual(resp_part.headers["content-range"], "bytes 0-99/2048")
        self.assertEqual(resp_part.headers["content-length"], "100")
        self.assertEqual(len(resp_part.content), 100)

    def test_audio_http_206_streaming_and_seekability(self):
        """Tests that audio endpoint and files/audio.wav return HTTP 206 with range headers for seeking."""
        vid_id = "audio000001"
        proj_dir = self.output_dir / vid_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        audio_bytes = b"AUDIO_DATA" * 100  # 1000 bytes
        (proj_dir / "audio.wav").write_bytes(audio_bytes)

        proj = self.pm.create_project(f"https://www.youtube.com/watch?v={vid_id}", title="Test Audio Stream")

        # GET /api/projects/{id}/audio with Range
        resp_audio_range = self.client.get(
            f"/api/projects/{proj['id']}/audio",
            headers={"Range": "bytes=50-149"},
        )
        self.assertEqual(resp_audio_range.status_code, 206)
        self.assertEqual(resp_audio_range.headers["content-type"], "audio/wav")
        self.assertEqual(resp_audio_range.headers["accept-ranges"], "bytes")
        self.assertEqual(resp_audio_range.headers["content-range"], "bytes 50-149/1000")
        self.assertEqual(resp_audio_range.headers["content-length"], "100")
        self.assertEqual(len(resp_audio_range.content), 100)

        # GET /api/projects/{id}/files/audio.wav with Range
        resp_file_range = self.client.get(
            f"/api/projects/{proj['id']}/files/audio.wav",
            headers={"Range": "bytes=0-99"},
        )
        self.assertEqual(resp_file_range.status_code, 206)
        self.assertEqual(resp_file_range.headers["content-type"], "audio/wav")
        self.assertEqual(resp_file_range.headers["accept-ranges"], "bytes")
        self.assertEqual(resp_file_range.headers["content-range"], "bytes 0-99/1000")

    def test_nonexistent_source_video_or_audio_returns_404(self):
        """Missing files return 404 rather than raising an unhandled 500 error."""
        vid_id = "missing0001"
        proj_dir = self.output_dir / vid_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        proj = self.pm.create_project(f"https://www.youtube.com/watch?v={vid_id}", title="Missing Media")

        resp_v = self.client.get(f"/api/projects/{proj['id']}/source-video")
        self.assertEqual(resp_v.status_code, 404)

        resp_a = self.client.get(f"/api/projects/{proj['id']}/audio")
        self.assertEqual(resp_a.status_code, 404)


if __name__ == "__main__":
    unittest.main()
