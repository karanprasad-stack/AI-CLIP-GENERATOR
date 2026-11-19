import unittest
from pathlib import Path
from backend.app.pipeline.sfx_library import SfxLibrary, SFX_ASSET_NAMES
from backend.app.pipeline.audio_event_engine import AudioEventEngine
from backend.app.pipeline.ducking_engine import DuckingEngine
from backend.app.pipeline.audio_validator import AudioValidator


class TestPhase6APipeline(unittest.TestCase):
    def setUp(self):
        self.sfx_library = SfxLibrary()
        self.audio_event_engine = AudioEventEngine(sfx_library=self.sfx_library)
        self.ducking_engine = DuckingEngine()
        self.validator = AudioValidator()

    def test_sfx_library_assets_exist_or_synthesizable(self):
        assets = self.sfx_library.ensure_library_assets()
        self.assertGreaterEqual(len(assets), 5)
        for name, p in assets.items():
            self.assertTrue(p.exists(), f"Asset {name} does not exist at {p}")
            self.assertGreater(p.stat().st_size, 100, f"Asset {name} is unexpectedly empty")

    def test_end_to_end_candidate_audio_plan(self):
        candidate = {
            "candidate_id": 1,
            "extraction_start": 30.0,
            "extraction_end": 60.0,
            "extraction_duration": 30.0,
        }
        transcript_data = {
            "segments": [
                {
                    "words": [
                        {"start": 32.0, "end": 35.0, "word": "Oh my god no way"},
                        {"start": 40.0, "end": 44.0, "word": "He is clutching the round"},
                    ]
                }
            ]
        }
        effect_timeline = {
            "candidate_id": 1,
            "candidate_duration": 30.0,
            "effects": [
                {
                    "effect_type": "punch_zoom",
                    "start_time": 4.0,
                    "end_time": 4.4,
                    "intensity": 0.8,
                    "confidence": 0.9,
                    "coinciding_signals": ["kill"],
                },
                {
                    "effect_type": "impact_shake",
                    "start_time": 12.0,
                    "end_time": 12.4,
                    "intensity": 0.85,
                    "confidence": 0.9,
                    "coinciding_signals": ["headshot"],
                },
            ],
        }

        # Step 1: Ducking Plan
        ducking_plan = self.ducking_engine.compute_ducking_plan(
            transcript_data=transcript_data,
            candidate=candidate,
        )
        self.assertTrue(ducking_plan["enabled"])
        self.assertEqual(len(ducking_plan["intervals"]), 2)

        # Step 2: Audio Event Timeline
        timeline = self.audio_event_engine.build_audio_timeline(
            candidate=candidate,
            effect_timeline=effect_timeline,
            gameplay_signals=["kill", "headshot"],
            transcript_data=transcript_data,
            ducking_summary=ducking_plan,
        )
        self.assertEqual(timeline.candidate_id, 1)
        self.assertGreaterEqual(len(timeline.audio_events), 2)

        # Step 3: Validate Timeline
        val_res = self.validator.validate_audio_timeline(timeline, candidate_duration=30.0)
        self.assertTrue(val_res["valid"])
        self.assertEqual(val_res["status"], "PASS")

        # Step 4: Validate Dictionary output structure
        d = timeline.to_dict()
        self.assertIn("audio_events", d)
        self.assertIn("ducking", d)
        self.assertIn("sfx_counts", d)


if __name__ == "__main__":
    unittest.main()
