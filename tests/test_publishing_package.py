import json
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np

from backend.app.pipeline.publishing_package import PublishingPackageManager


class TestPublishingPackage(unittest.TestCase):
    def setUp(self):
        self.manager = PublishingPackageManager()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pkg_dir = Path(self.temp_dir.name) / "candidate_01"
        self.pkg_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_package_validation_passes_when_all_assets_present(self):
        # Create mock final.mp4
        video_path = self.pkg_dir / "final.mp4"
        video_path.write_bytes(b"dummy mp4 data" * 100)

        # Create valid 1280x720 thumbnail
        thumb_path = self.pkg_dir / "thumbnail.jpg"
        img = np.ones((720, 1280, 3), dtype=np.uint8) * 150
        cv2.imwrite(str(thumb_path), img)

        # Create text files
        (self.pkg_dir / "title.txt").write_text("The Craziest CS:GO Clutch 🔥", encoding="utf-8")
        (self.pkg_dir / "description.txt").write_text("An insane CS:GO clutch play that caught everyone off guard.\n\n#CSGO #Shorts", encoding="utf-8")
        (self.pkg_dir / "hashtags.txt").write_text("#CSGO #Gaming #Shorts #Clutch", encoding="utf-8")
        (self.pkg_dir / "keywords.txt").write_text("CSGO, gaming, clutch, shorts", encoding="utf-8")

        # Create metadata.json
        meta = {
            "phase": "6B",
            "candidate_id": 1,
            "video": {"path": "final.mp4"},
            "title": {"selected": "The Craziest CS:GO Clutch 🔥"},
        }
        with open(self.pkg_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f)

        res = self.manager.validate_package(self.pkg_dir)
        self.assertTrue(res["valid"])
        self.assertEqual(res["status"], "PASS")

    def test_package_validation_fails_when_asset_missing(self):
        # Empty package dir
        res = self.manager.validate_package(self.pkg_dir)
        self.assertFalse(res["valid"])
        self.assertEqual(res["status"], "FAIL")
        self.assertGreater(len(res["errors"]), 0)

    def test_publishing_manifest_generation(self):
        publishing_dir = Path(self.temp_dir.name)
        packages = [
            {
                "candidate_id": 1,
                "package_dir": str(self.pkg_dir),
                "title": "The Craziest CS:GO Clutch 🔥",
                "thumbnail_path": str(self.pkg_dir / "thumbnail.jpg"),
                "thumbnail_score": 0.89,
                "thumbnail_timestamp": 18.5,
                "validation": {"status": "PASS"},
            }
        ]
        manifest_path = self.manager.generate_publishing_manifest(
            publishing_dir=publishing_dir,
            packages=packages,
            source_metadata={"id": "test_id", "title": "Test Title"},
        )
        self.assertTrue(manifest_path.exists())
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["phase"], "6B")
        self.assertEqual(data["total_packages"], 1)
        self.assertEqual(data["packages"][0]["candidate_id"], 1)


if __name__ == "__main__":
    unittest.main()
