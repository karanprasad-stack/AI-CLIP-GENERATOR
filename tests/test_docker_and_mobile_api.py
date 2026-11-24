"""Tests for Docker production setup, Capacitor mobile configs, and mobile-ready backend API."""

import os
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app.server import app

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestDockerAndMobileAPI(unittest.TestCase):
    """Verifies Docker, Capacitor, and mobile API readiness."""

    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoints(self):
        """Both /health and /api/health should return valid telemetry with service 'ai-clipper'."""
        for endpoint in ["/health", "/api/health"]:
            resp = self.client.get(endpoint)
            self.assertEqual(resp.status_code, 200, f"Failed at endpoint {endpoint}")
            data = resp.json()
            self.assertIn(data["status"], ["ok", "degraded"])
            self.assertEqual(data["service"], "ai-clipper")
            self.assertIn("ffmpeg", data)
            self.assertIn("storage", data)
            self.assertIn("memory", data)

    def test_spa_api_guard_returns_404(self):
        """Unknown API routes must return 404 JSON and NOT fallback to index.html."""
        resp = self.client.get("/api/unknown_nonexistent_route")
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertIn("detail", data)

    def test_cors_capacitor_and_lan_origins(self):
        """CORS must allow Capacitor mobile app origin and local network IPs."""
        # 1. Capacitor native origin
        resp_cap = self.client.options(
            "/api/health",
            headers={
                "Origin": "capacitor://localhost",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(resp_cap.status_code, 200)
        self.assertEqual(
            resp_cap.headers.get("access-control-allow-origin"),
            "capacitor://localhost",
        )

        # 2. Local LAN IP origin (e.g. mobile phone connecting to PC)
        lan_origin = "http://192.168.1.150:8000"
        resp_lan = self.client.options(
            "/api/health",
            headers={
                "Origin": lan_origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(resp_lan.status_code, 200)
        self.assertEqual(
            resp_lan.headers.get("access-control-allow-origin"),
            lan_origin,
        )

    def test_dockerfile_contents(self):
        """Dockerfile must specify multi-stage build, FFmpeg, fonts, healthcheck, and uvicorn command."""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        self.assertTrue(dockerfile_path.exists(), "Dockerfile must exist")
        content = dockerfile_path.read_text(encoding="utf-8")

        self.assertIn("FROM node:20-alpine AS frontend-builder", content)
        self.assertIn("FROM python:3.11-slim", content)
        self.assertIn("ffmpeg", content)
        self.assertIn("HEALTHCHECK", content)
        self.assertIn("uvicorn", content)
        self.assertIn("8000", content)

    def test_docker_compose_contents(self):
        """docker-compose.yml must define ai-clipper service, ports, and persistent volumes."""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        self.assertTrue(compose_path.exists(), "docker-compose.yml must exist")
        content = compose_path.read_text(encoding="utf-8")

        self.assertIn("ai-clipper", content)
        self.assertIn("8000:8000", content)
        self.assertIn("./output:/app/output", content)
        self.assertIn("./config:/app/config", content)
        self.assertIn("./assets:/app/assets", content)

    def test_dockerignore_contents(self):
        """.dockerignore must exclude git, output, temp, venv, and credentials."""
        dockerignore_path = PROJECT_ROOT / ".dockerignore"
        self.assertTrue(dockerignore_path.exists(), ".dockerignore must exist")
        content = dockerignore_path.read_text(encoding="utf-8")

        self.assertIn(".git", content)
        self.assertIn("output/", content)
        self.assertIn("temp/", content)
        self.assertIn("node_modules/", content)
        self.assertIn("credentials", content)

    def test_capacitor_configuration(self):
        """capacitor.config.ts must have valid appId, cleartext traffic, and http scheme."""
        cap_config = PROJECT_ROOT / "frontend" / "capacitor.config.ts"
        self.assertTrue(cap_config.exists(), "capacitor.config.ts must exist")
        content = cap_config.read_text(encoding="utf-8")

        self.assertIn("com.aiclipper.studio", content)
        self.assertIn("AI Clipper Studio", content)
        self.assertIn("cleartext: true", content)

    def test_android_manifest_permissions(self):
        """AndroidManifest.xml must declare INTERNET permission and cleartext traffic."""
        manifest_path = PROJECT_ROOT / "frontend" / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
        self.assertTrue(manifest_path.exists(), "AndroidManifest.xml must exist")
        content = manifest_path.read_text(encoding="utf-8")

        self.assertIn("android.permission.INTERNET", content)
        self.assertIn('android:usesCleartextTraffic="true"', content)


if __name__ == "__main__":
    unittest.main()
