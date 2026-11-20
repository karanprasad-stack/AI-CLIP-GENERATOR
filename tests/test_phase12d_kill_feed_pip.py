"""Phase 12D: 9:16 Kill-Feed Picture-in-Picture (PIP) Overlay Tests."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from backend.app.config import (
    DEFAULT_KILL_FEED_OVERLAY,
    KILL_FEED_PIP_WIDTH,
    KILL_FEED_PIP_MARGIN_X,
    KILL_FEED_PIP_MARGIN_Y,
    KILL_FEED_PIP_ALPHA,
    LAYOUT_SMART_CROP,
    LAYOUT_BLURRED_BG,
    LAYOUT_FACECAM,
)
from backend.app.pipeline.vertical_renderer import VerticalRenderer
from backend.app.pipeline.games.profiles.valorant import ValorantGameProfile
from backend.app.pipeline.games.profiles.competitive_fps import CompetitiveFPSProfile
from backend.app.pipeline.games.profiles.story_open_world import StoryOpenWorldProfile
from backend.app.pipeline.games.profiles.horror_survival import HorrorSurvivalProfile
from backend.app.pipeline.games.profiles.generic import GenericGameProfile
from backend.app.pipeline.timeline.models import TimelineVideoTrack, TimelineEDL, TimelineBoundaries, TimelineMetadata
from backend.app.pipeline.timeline.edl_generator import TimelineEdlGenerator


class TestPhase12DKillFeedPIP(unittest.TestCase):
    def setUp(self):
        self.renderer = VerticalRenderer()
        self.val_roi = (0.74, 0.04, 0.985, 0.30)
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_game_profiles_kill_feed_roi(self):
        """Valorant profile defines calibrated ROI, other profiles default to None."""
        val_profile = ValorantGameProfile()
        self.assertIsNotNone(val_profile.kill_feed_roi)
        self.assertEqual(len(val_profile.kill_feed_roi), 4)
        x1, y1, x2, y2 = val_profile.kill_feed_roi
        self.assertGreater(x2, x1)
        self.assertGreater(y2, y1)
        self.assertTrue(0.0 <= x1 <= 1.0 and 0.0 <= x2 <= 1.0)
        self.assertTrue(0.0 <= y1 <= 1.0 and 0.0 <= y2 <= 1.0)

        # Other profiles must NEVER auto-provide kill_feed_roi
        self.assertIsNone(CompetitiveFPSProfile().kill_feed_roi)
        self.assertIsNone(StoryOpenWorldProfile().kill_feed_roi)
        self.assertIsNone(HorrorSurvivalProfile().kill_feed_roi)
        self.assertIsNone(GenericGameProfile().kill_feed_roi)

    def test_build_filtergraph_with_pip_overlay(self):
        """Builds composite split + crop + scale + overlay graph when enabled for 9:16 smart_crop."""
        fg = self.renderer.build_filtergraph(
            layout=LAYOUT_SMART_CROP,
            aspect_ratio="9:16",
            output_width=1080,
            output_height=1920,
            kill_feed_overlay=True,
            kill_feed_roi=self.val_roi,
        )

        self.assertIn("split=2[main_src][kf_src]", fg)
        self.assertIn("[kf_src]crop=", fg)
        self.assertIn(f"scale={KILL_FEED_PIP_WIDTH}:-2", fg)
        self.assertIn(f"aa={KILL_FEED_PIP_ALPHA}", fg)
        self.assertIn(f"overlay=W-w-{KILL_FEED_PIP_MARGIN_X}:{KILL_FEED_PIP_MARGIN_Y}", fg)
        self.assertIn("format=yuv420p,setsar=1[outv]", fg)

    def test_pip_overlay_disabled_scenarios(self):
        """PIP must be bypassed when square 1:1, blurred_bg, facecam, overlay=False, or roi=None."""
        # 1. 1:1 Square aspect ratio
        fg_square = self.renderer.build_filtergraph(
            layout=LAYOUT_SMART_CROP,
            aspect_ratio="1:1",
            output_width=1080,
            output_height=1080,
            kill_feed_overlay=True,
            kill_feed_roi=self.val_roi,
        )
        self.assertNotIn("split=2", fg_square)
        self.assertNotIn("kf_pip", fg_square)

        # 2. Blurred background layout (full 16:9 already visible)
        fg_blurred = self.renderer.build_filtergraph(
            layout=LAYOUT_BLURRED_BG,
            aspect_ratio="9:16",
            kill_feed_overlay=True,
            kill_feed_roi=self.val_roi,
        )
        self.assertNotIn("kf_src", fg_blurred)
        self.assertNotIn("kf_pip", fg_blurred)

        # 3. Facecam layout
        fg_facecam = self.renderer.build_filtergraph(
            layout=LAYOUT_FACECAM,
            aspect_ratio="9:16",
            kill_feed_overlay=True,
            kill_feed_roi=self.val_roi,
        )
        self.assertNotIn("kf_src", fg_facecam)
        self.assertNotIn("kf_pip", fg_facecam)

        # 4. Explicitly kill_feed_overlay=False
        fg_disabled = self.renderer.build_filtergraph(
            layout=LAYOUT_SMART_CROP,
            aspect_ratio="9:16",
            kill_feed_overlay=False,
            kill_feed_roi=self.val_roi,
        )
        self.assertNotIn("split=2", fg_disabled)
        self.assertNotIn("kf_pip", fg_disabled)

        # 5. kill_feed_roi=None (e.g. story or generic game profile)
        fg_no_roi = self.renderer.build_filtergraph(
            layout=LAYOUT_SMART_CROP,
            aspect_ratio="9:16",
            kill_feed_overlay=True,
            kill_feed_roi=None,
        )
        self.assertNotIn("split=2", fg_no_roi)
        self.assertNotIn("kf_pip", fg_no_roi)

    def test_timeline_models_and_edl_preservation(self):
        """TimelineVideoTrack and EDL generator correctly preserve kill_feed_overlay and ROI."""
        vt = TimelineVideoTrack(
            source_file="source.mp4",
            layout="smart_crop",
            resolution="1080x1920",
            aspect_ratio="9:16",
            kill_feed_overlay=True,
            kill_feed_roi=[0.74, 0.04, 0.985, 0.30],
        )
        vt_dict = vt.model_dump()
        self.assertTrue(vt_dict["kill_feed_overlay"])
        self.assertEqual(vt_dict["kill_feed_roi"], [0.74, 0.04, 0.985, 0.30])

        # Test EDL Generator population
        edl_gen = TimelineEdlGenerator()
        cand = {
            "start": 10.0,
            "end": 35.0,
            "layout": "smart_crop",
            "aspect_ratio": "9:16",
            "kill_feed_overlay": True,
            "kill_feed_roi": [0.74, 0.04, 0.985, 0.30],
        }
        edl = edl_gen.generate_edl(
            project_id="test_proj",
            candidate_id=1,
            candidate=cand,
        )
        self.assertTrue(edl.video_track.kill_feed_overlay)
        self.assertEqual(edl.video_track.kill_feed_roi, [0.74, 0.04, 0.985, 0.30])

    def test_synthetic_ffmpeg_render_with_kill_feed_pip(self):
        """Executes a 1-second synthetic render with PIP overlay to verify FFmpeg exit code 0."""
        import subprocess

        # 1. Generate 1s test source video
        src_path = self.test_path / "test_input.mp4"
        cmd_src = [
            self.renderer.ffmpeg_path,
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=duration=1:size=1920x1080:rate=30",
            "-f", "lavfi",
            "-i", "anullsrc=r=48000:cl=stereo",
            "-shortest",
            "-c:v", "libx264",
            "-c:a", "aac",
            str(src_path),
        ]
        proc_src = subprocess.run(cmd_src, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(proc_src.returncode, 0)
        self.assertTrue(src_path.exists())

        # 2. Render Short with kill-feed PIP overlay enabled (forcing CPU for universal test stability)
        out_path = self.test_path / "test_pip_short.mp4"
        res = self.renderer.render_short(
            input_clip_path=src_path,
            output_short_path=out_path,
            layout=LAYOUT_SMART_CROP,
            force_cpu=True,
            aspect_ratio="9:16",
            kill_feed_overlay=True,
            kill_feed_roi=self.val_roi,
        )

        self.assertTrue(out_path.exists())
        self.assertGreater(out_path.stat().st_size, 1000)
        self.assertTrue(res["kill_feed_overlay"])
        self.assertEqual(res["output_resolution"]["width"], 1080)
        self.assertEqual(res["output_resolution"]["height"], 1920)


if __name__ == "__main__":
    unittest.main()
