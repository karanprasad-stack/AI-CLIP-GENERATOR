import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np

from backend.app.pipeline.clip_summary_engine import ClipSummaryEngine
from backend.app.pipeline.thumbnail_engine import ThumbnailEngine
from backend.app.pipeline.title_engine import TitleEngine
from backend.app.pipeline.description_engine import DescriptionEngine
from backend.app.pipeline.hashtag_engine import HashtagEngine
from backend.app.pipeline.publishing_package import PublishingPackageManager


class TestPhase6BPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.publishing_dir = self.base_dir / "publishing"
        self.publishing_dir.mkdir(parents=True, exist_ok=True)

        # Create a mock source mp4
        self.mock_video = self.base_dir / "mock_video.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(self.mock_video), fourcc, 30.0, (1280, 720))
        for _ in range(60):
            frame = np.ones((720, 1280, 3), dtype=np.uint8) * 120
            out.write(frame)
        out.release()

        self.manager = PublishingPackageManager(
            summary_engine=ClipSummaryEngine(),
            thumbnail_engine=ThumbnailEngine(),
            title_engine=TitleEngine(ollama_enabled=False),
            description_engine=DescriptionEngine(),
            hashtag_engine=HashtagEngine(),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_end_to_end_candidate_publishing_package(self):
        candidate = {
            "candidate_id": 1,
            "candidate_start": 0.0,
            "candidate_end": 2.0,
            "candidate_duration": 2.0,
            "audio_polished_clip": str(self.mock_video),
            "final_score": 85.0,
            "detected_signals": ["clutch@1.0s", "phrase:insane clutch@1.2s"],
            "gameplay_event_breakdown": {
                "gaming_lexical": {"signals": ["clutch@1.0s"]},
                "reaction_lexical": {"signals": ["phrase:insane clutch@1.2s"]},
            },
        }
        metadata = {"id": "test_vid", "title": "CSGO Highlights", "uploader": "ProGamer"}

        pkg_info = self.manager.build_candidate_package(
            candidate_idx=1,
            candidate=candidate,
            publishing_dir=self.publishing_dir,
            source_video_path=self.mock_video,
            source_metadata=metadata,
        )

        self.assertEqual(pkg_info["candidate_id"], 1)
        self.assertTrue(Path(pkg_info["video_path"]).exists())
        self.assertTrue(Path(pkg_info["thumbnail_path"]).exists())
        self.assertTrue(Path(pkg_info["package_dir"], "title.txt").exists())
        self.assertTrue(Path(pkg_info["package_dir"], "description.txt").exists())
        self.assertTrue(Path(pkg_info["package_dir"], "hashtags.txt").exists())
        self.assertTrue(Path(pkg_info["package_dir"], "keywords.txt").exists())
        self.assertTrue(Path(pkg_info["package_dir"], "metadata.json").exists())

        # Validate package
        self.assertEqual(pkg_info["validation"]["status"], "PASS")

        # Generate manifest
        manifest_path = self.manager.generate_publishing_manifest(
            publishing_dir=self.publishing_dir,
            packages=[pkg_info],
            source_metadata=metadata,
        )
        self.assertTrue(manifest_path.exists())


if __name__ == "__main__":
    unittest.main()
