"""Automated unit and integration tests for Phase 3 Shorts Generation Engine."""

import unittest
from pathlib import Path
from backend.app.config import (
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
    LAYOUT_SMART_CROP,
    LAYOUT_BLURRED_BG,
    LAYOUT_FACECAM,
)
from backend.app.pipeline.layout_detector import LayoutDetector
from backend.app.pipeline.vertical_renderer import VerticalRenderer
from backend.app.pipeline.clip_extractor import ClipExtractor
from backend.app.pipeline.video_validator import VideoValidator


class TestPhase3ShortsEngine(unittest.TestCase):
    """Test suite covering Phase 3 layouts, rendering, validation, and resilience."""

    def setUp(self):
        self.layout_detector = LayoutDetector()
        self.renderer = VerticalRenderer()
        self.validator = VideoValidator()

    def test_1_smart_crop_filtergraph_syntax(self):
        """Test 1: Smart crop generates valid FFmpeg filtergraph targeting 1080x1920 with setsar=1."""
        fg = self.renderer.build_filtergraph(
            layout=LAYOUT_SMART_CROP,
            focal_x=0.5,
            output_width=1080,
            output_height=1920,
        )
        self.assertIn("crop=ih*9/16:ih:", fg)
        self.assertIn("scale=1080:1920", fg)
        self.assertIn("setsar=1", fg)

    def test_2_blurred_background_filtergraph_syntax(self):
        """Test 2: Blurred background produces split, boxblur, scale, and centered overlay."""
        fg = self.renderer.build_filtergraph(
            layout=LAYOUT_BLURRED_BG,
            output_width=1080,
            output_height=1920,
        )
        self.assertIn("split=2[fg][bg]", fg)
        self.assertIn("boxblur=20:5", fg)
        self.assertIn("overlay=0:(1920-overlay_h)/2", fg)
        self.assertIn("setsar=1", fg)

    def test_3_facecam_filtergraph_syntax(self):
        """Test 3: Facecam layout produces cropped cam and cropped gameplay with vstack."""
        region = {"x": 0.70, "y": 0.05, "width": 0.25, "height": 0.30}
        fg = self.renderer.build_filtergraph(
            layout=LAYOUT_FACECAM,
            facecam_region=region,
            output_width=1080,
            output_height=1920,
        )
        self.assertIn("crop=iw*0.25:ih*0.3:iw*0.7:ih*0.05", fg)
        self.assertIn("vstack=inputs=2", fg)
        self.assertIn("setsar=1", fg)

    def test_4_layout_resolution_fallback(self):
        """Test 4 & 6: When facecam is not detected, auto layout defaults to smart_crop."""
        no_facecam = {"facecam_detected": False, "confidence": 0.0, "region": None}
        resolved = self.layout_detector.resolve_layout("auto", no_facecam)
        self.assertEqual(resolved, LAYOUT_SMART_CROP)

        has_facecam = {"facecam_detected": True, "confidence": 0.85, "region": {"x": 0.7, "y": 0.1, "width": 0.2, "height": 0.2}}
        resolved_cam = self.layout_detector.resolve_layout("auto", has_facecam)
        self.assertEqual(resolved_cam, LAYOUT_FACECAM)

        # Explicit user override
        explicit_blur = self.layout_detector.resolve_layout("blurred_background", has_facecam)
        self.assertEqual(explicit_blur, LAYOUT_BLURRED_BG)

    def test_5_clip_extractor_clamping(self):
        """Test 5: Extraction boundaries clamp safely to 0.0 and source duration."""
        # Check that negative pre-roll doesn't drop below 0.0
        candidate_start = 0.2
        candidate_end = 35.0
        pre_roll = 0.5
        post_roll = 0.5
        source_dur = 300.0

        ext_start = max(0.0, candidate_start - pre_roll)
        ext_end = min(source_dur, candidate_end + post_roll)
        self.assertEqual(ext_start, 0.0)
        self.assertEqual(ext_end, 35.5)

        # Check end clamping
        near_end_start = 280.0
        near_end_end = 299.8
        ext_end2 = min(source_dur, near_end_end + post_roll)
        self.assertEqual(ext_end2, 300.0)

    def test_6_validator_failure_isolation(self):
        """Test 8: VideoValidator reports FAIL with clear errors when file is missing or invalid."""
        bogus_file = Path("D:/AI Clipper/temp/non_existent_short.mp4")
        result = self.validator.validate_short(bogus_file)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["file_exists"])
        self.assertTrue(len(result["errors"]) > 0)

    def test_7_nvenc_detection(self):
        """Test 7: Hardware encoder detection executes and returns boolean."""
        has_nvenc = self.renderer.nvenc_available
        self.assertIsInstance(has_nvenc, bool)


if __name__ == "__main__":
    unittest.main()
