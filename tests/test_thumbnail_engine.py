import unittest
from pathlib import Path
import numpy as np
import cv2

from backend.app.pipeline.clip_summary_engine import ClipSummary
from backend.app.pipeline.thumbnail_engine import ThumbnailEngine


class TestThumbnailEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ThumbnailEngine()

    def test_sample_timestamps_stay_within_duration(self):
        dur = 45.0
        climax_t = 22.0
        samples = self.engine.generate_sample_timestamps(
            clip_duration=dur,
            climax_t=climax_t,
            event_times=[10.0, 20.0],
            peak_times=[15.0],
            visual_times=[22.0],
        )

        self.assertGreater(len(samples), 10)
        for t in samples:
            self.assertGreaterEqual(t, 0.5)
            self.assertLessEqual(t, dur - 0.5)

    def test_black_frame_rejection(self):
        # Frame with zero intensity
        black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        score, bd = self.engine.score_frame(
            frame=black_frame,
            rel_t=10.0,
            climax_t=10.0,
            event_times=[10.0],
            peak_times=[10.0],
            visual_times=[10.0],
            has_facecam=False,
        )
        self.assertEqual(score, -1.0)
        self.assertEqual(bd.get("rejection"), "black_frame")

    def test_frame_scoring_with_valid_image(self):
        # Frame with textures
        np.random.seed(42)
        valid_frame = np.random.randint(60, 200, (720, 1280, 3), dtype=np.uint8)
        score, bd = self.engine.score_frame(
            frame=valid_frame,
            rel_t=10.0,
            climax_t=10.0,
            event_times=[10.0],
            peak_times=[10.0],
            visual_times=[10.0],
            has_facecam=True,
        )
        self.assertGreater(score, 0.5)
        self.assertIn("climax_prox", bd)
        self.assertIn("sharpness", bd)

    def test_compose_thumbnail_resolution(self):
        # 16:9 frame
        test_frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 128
        out = self.engine.compose_thumbnail(test_frame, text="INSANE CLUTCH", has_facecam=False)
        self.assertEqual(out.shape[0], 720)
        self.assertEqual(out.shape[1], 1280)

        # 9:16 frame
        vertical_frame = np.ones((1920, 1080, 3), dtype=np.uint8) * 128
        out_v = self.engine.compose_thumbnail(vertical_frame, text=None, has_facecam=True)
        self.assertEqual(out_v.shape[0], 720)
        self.assertEqual(out_v.shape[1], 1280)

    def test_choose_thumbnail_text_derived_from_summary(self):
        summary = ClipSummary(
            candidate_id=1,
            duration=30.0,
            game="CS:GO",
            primary_event="clutch",
            secondary_events=[],
            strongest_reaction="talk about timing",
            climax_timestamp=15.0,
            intensity=0.9,
            tone="high-energy",
            has_facecam=True,
            visual_effect_count=3,
            sfx_count=2,
        )
        text = self.engine.choose_thumbnail_text(summary)
        self.assertIsNotNone(text)
        self.assertIn("TIMING", text.upper())


if __name__ == "__main__":
    unittest.main()
