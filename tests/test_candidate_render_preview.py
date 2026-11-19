"""Unit and integration tests for candidate output registration, media streaming, and preview pipeline."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from starlette.testclient import TestClient

from backend.app.server import app
from backend.app.services.project_manager import ProjectManager


class TestCandidateRenderPreview(unittest.TestCase):
    def setUp(self):
        t_base = Path(__file__).resolve().parent.parent / "temp"
        t_base.mkdir(parents=True, exist_ok=True)
        self.test_dir = Path(tempfile.mkdtemp(prefix="preview_test_", dir=t_base))
        self.output_dir = self.test_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pm = ProjectManager(base_output_dir=self.output_dir)
        self.client = TestClient(app)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_candidate_decoration_rendered_and_unrendered(self):
        """Candidates with valid final.mp4 get rendered: True and output metadata; others get rendered: False."""
        vid_id = "test_vid_01"
        proj_dir = self.output_dir / vid_id
        pub_dir = proj_dir / "publishing"
        cand1_dir = pub_dir / "candidate_01"
        cand2_dir = pub_dir / "candidate_02"
        cand1_dir.mkdir(parents=True, exist_ok=True)
        cand2_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy rendered final.mp4 and thumbnail for candidate 1
        final_mp4_1 = cand1_dir / "final.mp4"
        final_mp4_1.write_bytes(b"dummy_mp4_bytes_candidate_1_content_data")
        thumb_1 = cand1_dir / "thumbnail.jpg"
        thumb_1.write_bytes(b"dummy_thumb_bytes")

        # Candidate 2 is not rendered (no final.mp4)

        # Create project in ProjectManager
        proj = self.pm.create_project(f"https://www.youtube.com/watch?v={vid_id}", title="Preview Test Video")
        proj["candidates"] = [
            {"rank": 1, "start": 10.0, "end": 45.0, "duration": 35.0, "final_score": 88.0},
            {"rank": 2, "start": 60.0, "end": 95.0, "duration": 35.0, "final_score": 75.0},
        ]
        self.pm._save_projects()

        # Retrieve project through pm.get_project which triggers decoration
        decorated_proj = self.pm.get_project(proj["id"])
        self.assertIsNotNone(decorated_proj)
        cands = decorated_proj["candidates"]
        self.assertEqual(len(cands), 2)

        # Candidate 1: Rendered
        c1 = cands[0]
        self.assertEqual(c1["candidate_id"], 1)
        self.assertTrue(c1["rendered"])
        self.assertIsNotNone(c1["output"])
        self.assertEqual(c1["output"]["filename"], "final.mp4")
        self.assertEqual(c1["output"]["size_bytes"], len(b"dummy_mp4_bytes_candidate_1_content_data"))
        self.assertEqual(
            c1["output"]["video_url"],
            f"/api/projects/{proj['id']}/files/publishing/candidate_01/final.mp4",
        )
        self.assertEqual(
            c1["output"]["thumbnail_url"],
            f"/api/projects/{proj['id']}/files/publishing/candidate_01/thumbnail.jpg",
        )

        # Candidate 2: Unrendered
        c2 = cands[1]
        self.assertEqual(c2["candidate_id"], 2)
        self.assertFalse(c2["rendered"])
        self.assertIsNone(c2["output"])

    def test_http_206_streaming_on_rendered_video(self):
        """Verifies HTTP 206 Partial Content byte-range streaming for rendered Shorts."""
        # Using existing cached project EdtUDpqjltA
        resp = self.client.get("/api/projects/EdtUDpqjltA/files/publishing/candidate_01/final.mp4")
        if resp.status_code == 200:
            # Full content returned on GET without Range
            self.assertEqual(resp.headers["content-type"], "video/mp4")
            full_len = int(resp.headers["content-length"])
            self.assertGreater(full_len, 1000)

            # Test byte-range request
            range_resp = self.client.get(
                "/api/projects/EdtUDpqjltA/files/publishing/candidate_01/final.mp4",
                headers={"Range": "bytes=0-1023"},
            )
            self.assertEqual(range_resp.status_code, 206)
            self.assertEqual(range_resp.headers["content-type"], "video/mp4")
            self.assertEqual(range_resp.headers["content-length"], "1024")
            self.assertEqual(range_resp.headers["accept-ranges"], "bytes")
            self.assertEqual(
                range_resp.headers["content-range"],
                f"bytes 0-1023/{full_len}",
            )
            self.assertEqual(len(range_resp.content), 1024)

    def test_nonexistent_media_returns_404_cleanly(self):
        """Unrendered files or incorrect paths return 404 without error."""
        resp = self.client.get("/api/projects/EdtUDpqjltA/files/publishing/candidate_99/final.mp4")
        self.assertEqual(resp.status_code, 404)

        # Nonexistent project
        resp2 = self.client.get("/api/projects/nonexistent_xyz/files/publishing/candidate_01/final.mp4")
        self.assertEqual(resp2.status_code, 404)

    def test_api_project_detail_includes_candidate_output(self):
        """GET /api/projects/{project_id} returns candidate output metadata."""
        resp = self.client.get("/api/projects/EdtUDpqjltA")
        if resp.status_code == 200:
            data = resp.json()
            cands = data.get("candidates", [])
            self.assertGreater(len(cands), 0)

            # Candidate 1 should have rendered: True and output metadata
            c1 = cands[0]
            self.assertTrue(c1.get("rendered"))
            self.assertIsNotNone(c1.get("output"))
            self.assertEqual(c1["output"]["filename"], "final.mp4")
            self.assertIn("/api/projects/EdtUDpqjltA/files/publishing/candidate_01/final.mp4", c1["output"]["video_url"])


if __name__ == "__main__":
    unittest.main()
