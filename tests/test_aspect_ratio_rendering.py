"""Unit tests for selectable frame aspect ratio (9:16 vs 1:1) across rendering, subtitles, effects, validators, and EDL."""

import unittest
from pathlib import Path

from backend.app.config import (
    ASPECT_RATIO_9_16,
    ASPECT_RATIO_1_1,
    DEFAULT_ASPECT_RATIO,
    SUPPORTED_ASPECT_RATIOS,
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
    LAYOUT_SMART_CROP,
    LAYOUT_BLURRED_BG,
    LAYOUT_FACECAM,
    get_output_dimensions,
)
from backend.app.pipeline.vertical_renderer import VerticalRenderer
from backend.app.pipeline.ass_generator import AssGenerator
from backend.app.pipeline.caption_engine import CaptionGroup, CaptionWord
from backend.app.pipeline.effect_renderer import EffectRenderer
from backend.app.pipeline.effect_engine import EffectEvent
from backend.app.pipeline.video_validator import VideoValidator
from backend.app.pipeline.subtitle_validator import SubtitleValidator
from backend.app.pipeline.timeline.edl_generator import TimelineEdlGenerator
from backend.app.pipeline.timeline.models import TimelineVideoTrack


class TestAspectRatioRendering(unittest.TestCase):
    """Test suite for 1:1 vs 9:16 frame aspect ratios."""

    def test_dimensions_resolution(self):
        """Verify get_output_dimensions returns proper (width, height) tuples."""
        self.assertEqual(get_output_dimensions("9:16"), (1080, 1920))
        self.assertEqual(get_output_dimensions("1:1"), (1080, 1080))
        with self.assertRaises(ValueError):
            get_output_dimensions("invalid")

    def test_vertical_renderer_smart_crop_filtergraphs(self):
        """Verify smart crop filtergraph differs appropriately for 9:16 vs 1:1."""
        renderer = VerticalRenderer()

        fg_916 = renderer.build_filtergraph(
            layout=LAYOUT_SMART_CROP,
            aspect_ratio="9:16",
            output_width=1080,
            output_height=1920,
        )
        self.assertIn("crop=ih*9/16:ih:", fg_916)
        self.assertIn("scale=1080:1920", fg_916)

        fg_11 = renderer.build_filtergraph(
            layout=LAYOUT_SMART_CROP,
            aspect_ratio="1:1",
            output_width=1080,
            output_height=1080,
        )
        self.assertIn("crop=ih:ih:", fg_11)
        self.assertIn("scale=1080:1080", fg_11)

    def test_vertical_renderer_blurred_bg_filtergraphs(self):
        """Verify blurred background filtergraph scales to target dimensions."""
        renderer = VerticalRenderer()

        fg_916 = renderer.build_filtergraph(
            layout=LAYOUT_BLURRED_BG,
            aspect_ratio="9:16",
            output_width=1080,
            output_height=1920,
        )
        self.assertIn("crop=1080:1920", fg_916)
        self.assertIn("scale=1080:-2", fg_916)

        fg_11 = renderer.build_filtergraph(
            layout=LAYOUT_BLURRED_BG,
            aspect_ratio="1:1",
            output_width=1080,
            output_height=1080,
        )
        self.assertIn("crop=1080:1080", fg_11)
        self.assertIn("scale=1080:-2", fg_11)

    def test_vertical_renderer_facecam_filtergraphs(self):
        """Verify facecam layout splits correctly for 1:1."""
        renderer = VerticalRenderer()

        fg_11 = renderer.build_filtergraph(
            layout=LAYOUT_FACECAM,
            aspect_ratio="1:1",
            output_width=1080,
            output_height=1080,
        )
        self.assertIn("scale=1080:", fg_11)
        self.assertIn("vstack=inputs=2", fg_11)

    def test_ass_generator_resolution_and_margins(self):
        """Verify AssGenerator sets PlayRes and scales margins for 1:1 square canvas."""
        # Default 9:16
        ass_gen_916 = AssGenerator(aspect_ratio="9:16")
        header_916 = ass_gen_916.build_header()
        self.assertIn("PlayResX: 1080", header_916)
        self.assertIn("PlayResY: 1920", header_916)
        self.assertEqual(ass_gen_916.margin_v, 320)
        self.assertEqual(ass_gen_916.font_size, 68)

        # 1:1 Square
        ass_gen_11 = AssGenerator(aspect_ratio="1:1")
        header_11 = ass_gen_11.build_header()
        self.assertIn("PlayResX: 1080", header_11)
        self.assertIn("PlayResY: 1080", header_11)
        self.assertEqual(ass_gen_11.margin_v, 180)
        self.assertEqual(ass_gen_11.font_size, 54)
        self.assertEqual(ass_gen_11.emoji_margin_v, 247)

    def test_ass_generator_content_generation_1_1(self):
        """Verify ASS content generation generates valid events for 1:1."""
        ass_gen = AssGenerator(aspect_ratio="1:1")
        words = [
            CaptionWord(text="UNBELIEVABLE", start=1.0, end=1.5, index=0, global_start=1.0, global_end=1.5),
            CaptionWord(text="CLUTCH", start=1.5, end=2.0, index=1, global_start=1.5, global_end=2.0),
        ]
        groups = [CaptionGroup(words=words, start=1.0, end=2.0, text="UNBELIEVABLE CLUTCH")]
        content = ass_gen.generate_ass(groups)

        self.assertIn("PlayResX: 1080", content)
        self.assertIn("PlayResY: 1080", content)
        self.assertIn("Dialogue:", content)
        self.assertIn("UNBELIEVABLE", content)

    def test_subtitle_validator_1_1(self, tmp_path_factory=None):
        """Verify SubtitleValidator verifies 1080x1080 PlayRes when aspect_ratio='1:1'."""
        import tempfile
        ass_gen = AssGenerator(aspect_ratio="1:1")
        words = [
            CaptionWord(text="NICE", start=0.5, end=1.0, index=0, global_start=0.5, global_end=1.0),
        ]
        groups = [CaptionGroup(words=words, start=0.5, end=1.0, text="NICE")]
        content = ass_gen.generate_ass(groups)

        with tempfile.TemporaryDirectory() as tmp_dir:
            ass_file = Path(tmp_dir) / "test_1_1.ass"
            ass_file.write_text(content, encoding="utf-8")

            validator = SubtitleValidator()
            # Validates against 1:1
            res_11 = validator.validate_ass(ass_file, clip_duration=2.0, aspect_ratio="1:1")
            self.assertTrue(res_11["valid"], f"Validation failed: {res_11['errors']}")
            self.assertTrue(res_11["checks"]["target_resolution_1080x1920"])

            # Should fail if validated expecting 9:16 (1920)
            res_916 = validator.validate_ass(ass_file, clip_duration=2.0, aspect_ratio="9:16")
            self.assertFalse(res_916["valid"])

    def test_effect_renderer_filtergraph_1_1(self):
        """Verify EffectRenderer targets 1080x1080 in zoompan and shake crop for 1:1."""
        renderer = EffectRenderer()
        effects = [
            EffectEvent(type="subtle_zoom", start=1.0, end=2.0, intensity=1.0, confidence=1.0, reason="test", source_events=["test"]),
            EffectEvent(type="micro_shake", start=1.5, end=2.0, intensity=1.0, confidence=1.0, reason="test", source_events=["test"]),
        ]
        fg_11 = renderer.build_filtergraph(effects, source_fps=60.0, aspect_ratio="1:1")
        self.assertIsNotNone(fg_11)
        self.assertIn("s=1080x1080", fg_11)
        self.assertIn("crop=1080:1080", fg_11)

    def test_timeline_edl_generator_aspect_ratio(self):
        """Verify TimelineEdlGenerator sets resolution and aspect_ratio properly."""
        generator = TimelineEdlGenerator()
        cand = {
            "candidate_id": 1,
            "start": 10.0,
            "end": 40.0,
            "duration": 30.0,
            "aspect_ratio": "1:1",
            "layout": "smart_crop",
        }
        edl = generator.generate_edl(
            project_id="test_proj",
            candidate_id=1,
            candidate=cand,
        )
        self.assertEqual(edl.video_track.aspect_ratio, "1:1")
        self.assertEqual(edl.video_track.resolution, "1080x1080")


if __name__ == "__main__":
    unittest.main()
