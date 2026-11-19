import unittest
from pathlib import Path
from backend.app.config import TARGET_LUFS, TRUE_PEAK_LIMIT
from backend.app.pipeline.audio_event_engine import AudioTimeline, AudioEvent
from backend.app.pipeline.audio_renderer import AudioRenderer, AudioRenderError
from backend.app.pipeline.sfx_library import SfxLibrary


class TestAudioRenderer(unittest.TestCase):
    def setUp(self):
        self.library = SfxLibrary()
        self.renderer = AudioRenderer(sfx_library=self.library)

    def test_build_filtergraph_with_sfx(self):
        timeline = AudioTimeline(candidate_id=1, candidate_duration=30.0)
        ducking_expr = "max(0.40,1.0-(0.332*(if(between(t,1.0,2.0),1.0,0))))"
        active_sfx = [
            {"timestamp": 5.0, "event_type": "whoosh", "gain_db": -18.0, "asset_path": "whoosh.wav"},
            {"timestamp": 12.5, "event_type": "major_impact", "gain_db": -12.0, "asset_path": "impact.wav"},
        ]

        filtergraph = self.renderer.build_audio_filtergraph(timeline, ducking_expr, active_sfx)

        self.assertIn("[0:a]volume=eval=frame:volume=", filtergraph)
        self.assertIn("[1:a]adelay=5000:all=1,volume=-18.0dB", filtergraph)
        self.assertIn("[2:a]adelay=12500:all=1,volume=-12.0dB", filtergraph)
        self.assertIn("amix=inputs=3:duration=first:normalize=0[mixed]", filtergraph)
        self.assertIn(f"loudnorm=I={TARGET_LUFS:.1f}:TP={TRUE_PEAK_LIMIT:.1f}", filtergraph)
        self.assertIn(f"alimiter=limit={TRUE_PEAK_LIMIT:.1f}dB", filtergraph)

    def test_build_filtergraph_no_sfx(self):
        timeline = AudioTimeline(candidate_id=1, candidate_duration=30.0)
        ducking_expr = "1.0"
        active_sfx = []

        filtergraph = self.renderer.build_audio_filtergraph(timeline, ducking_expr, active_sfx)

        self.assertIn("[0:a]volume=eval=frame:volume='1.0'", filtergraph)
        self.assertNotIn("amix=", filtergraph)
        self.assertIn(f"[main_ducked]loudnorm=I={TARGET_LUFS:.1f}:TP={TRUE_PEAK_LIMIT:.1f}", filtergraph)
        self.assertIn(f"alimiter=limit={TRUE_PEAK_LIMIT:.1f}dB", filtergraph)

    def test_missing_input_raises_error(self):
        timeline = AudioTimeline(candidate_id=1, candidate_duration=30.0)
        non_existent = Path("non_existent_file.mp4")
        with self.assertRaises(AudioRenderError):
            self.renderer.render_audio(
                input_video_path=non_existent,
                timeline=timeline,
                ducking_summary={"enabled": False},
                output_video_path=Path("output.mp4"),
            )


if __name__ == "__main__":
    unittest.main()
