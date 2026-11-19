"""Unit and Integration Tests for Phase 7A API Contract & Project Manager."""

import json
import tempfile
import unittest
from pathlib import Path
from starlette.testclient import TestClient

from backend.app.server import app
from backend.app.services.project_manager import ProjectManager


class TestPhase7AAPIServer(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["phase"], "7A")

    def test_spa_root_served(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])

    def test_list_projects(self):
        resp = self.client.get("/api/projects")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        # Should include cached EdtUDpqjltA if present in output/
        video_ids = [p["video_id"] for p in data]
        if "EdtUDpqjltA" in video_ids:
            edt = next(p for p in data if p["video_id"] == "EdtUDpqjltA")
            self.assertEqual(edt["status"], "completed")
            self.assertGreaterEqual(edt["shorts_count"], 1)

    def test_project_lifecycle(self):
        # 1. Create project
        create_payload = {
            "url": "https://www.youtube.com/watch?v=TESTING1234",
            "settings": {
                "min_duration": 20,
                "max_duration": 60,
                "num_shorts": 3,
                "subtitle_language": "hinglish",
            },
        }
        resp = self.client.post("/api/projects", json=create_payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        proj_id = data["id"]
        self.assertEqual(data["video_id"], "TESTING1234")
        self.assertEqual(data["settings"]["subtitle_language"], "hinglish")
        self.assertEqual(data["status"], "queued")

        # 2. Get project detail
        resp_get = self.client.get(f"/api/projects/{proj_id}")
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.json()["id"], proj_id)

        # 3. Get status snapshot
        resp_stat = self.client.get(f"/api/projects/{proj_id}/status")
        self.assertEqual(resp_stat.status_code, 200)
        self.assertEqual(resp_stat.json()["status"], "queued")

        # 4. Update candidate selection
        sel_payload = {"candidate_ids": [1, 2, 3]}
        resp_sel = self.client.post(f"/api/projects/{proj_id}/select-candidates", json=sel_payload)
        self.assertEqual(resp_sel.status_code, 200)
        self.assertEqual(resp_sel.json()["selected_candidate_ids"], [1, 2, 3])

        # 5. Delete project
        resp_del = self.client.delete(f"/api/projects/{proj_id}")
        self.assertEqual(resp_del.status_code, 200)

        # Verify not found after delete
        resp_del_get = self.client.get(f"/api/projects/{proj_id}")
        self.assertEqual(resp_del_get.status_code, 404)

    def test_metadata_update_and_download(self):
        # Test against cached EdtUDpqjltA
        resp = self.client.get("/api/projects/EdtUDpqjltA")
        if resp.status_code == 200:
            # Test getting outputs
            out_resp = self.client.get("/api/projects/EdtUDpqjltA/outputs")
            self.assertEqual(out_resp.status_code, 200)
            self.assertGreaterEqual(out_resp.json()["total_packages"], 1)

            # Test updating metadata on Candidate 1
            patch_payload = {
                "candidate_id": 1,
                "title": "Updated Custom Creator Title 💀",
            }
            patch_resp = self.client.patch("/api/projects/EdtUDpqjltA/metadata", json=patch_payload)
            self.assertEqual(patch_resp.status_code, 200)

            # Test package zip download endpoint
            zip_resp = self.client.get("/api/projects/EdtUDpqjltA/package?candidate_id=1")
            self.assertEqual(zip_resp.status_code, 200)
            self.assertEqual(zip_resp.headers["content-type"], "application/zip")
            self.assertGreater(len(zip_resp.content), 100)


class TestProjectManagerUnit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mgr = ProjectManager(base_output_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_and_progress(self):
        proj = self.mgr.create_project("https://www.youtube.com/watch?v=abc123xyz89")
        self.assertEqual(proj["status"], "queued")

        # Test progress update
        received_events = []
        def listener(ev):
            received_events.append(ev)

        self.mgr.add_event_listener(proj["id"], listener)
        self.mgr.update_project_progress(
            project_id=proj["id"],
            step=2,
            total_steps=5,
            stage="Whisper",
            message="Transcribing audio...",
        )

        p_updated = self.mgr.get_project(proj["id"])
        self.assertEqual(p_updated["progress"]["step"], 2)
        self.assertEqual(p_updated["progress"]["percent"], 40)
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0]["stage"], "Whisper")


if __name__ == "__main__":
    unittest.main()
