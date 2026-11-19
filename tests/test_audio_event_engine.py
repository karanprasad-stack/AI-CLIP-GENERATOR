import unittest
from backend.app.config import (
    SFX_WHOOSH,
    SFX_MAJOR_IMPACT,
    SFX_MINOR_IMPACT,
    SFX_REACTION_ACCENT,
    EFFECT_SUBTLE_ZOOM,
    EFFECT_PUNCH_ZOOM,
    EFFECT_IMPACT_ZOOM,
    EFFECT_MICRO_SHAKE,
    EFFECT_IMPACT_SHAKE,
    MAX_SFX_PER_30_SECONDS,
)
from backend.app.pipeline.audio_event_engine import AudioEvent, AudioTimeline, AudioEventEngine
from backend.app.pipeline.sfx_library import SfxLibrary


class TestAudioEventEngine(unittest.TestCase):
    def setUp(self):
        self.library = SfxLibrary()
        self.engine = AudioEventEngine(sfx_library=self.library)

    def test_whoosh_for_punch_zoom(self):
        candidate = {
            "candidate_id": 1,
            "extraction_start": 10.0,
            "extraction_end": 40.0,
            "extraction_duration": 30.0,
        }
        effect_timeline = {
            "candidate_id": 1,
            "candidate_duration": 30.0,
            "effects": [
                {
                    "effect_type": EFFECT_PUNCH_ZOOM,
                    "start_time": 5.0,
                    "end_time": 5.4,
                    "intensity": 0.8,
                    "confidence": 0.9,
                    "coinciding_signals": ["kill", "headshot"],
                }
            ],
        }

        timeline = self.engine.build_audio_timeline(
            candidate=candidate,
            effect_timeline=effect_timeline,
            gameplay_signals=[],
            transcript_data={"segments": []},
        )

        whooshes = [ev for ev in timeline.audio_events if ev.event_type == SFX_WHOOSH]
        self.assertGreaterEqual(len(whooshes), 1)
        # SFX should lead slightly for anticipation (-0.06s)
        self.assertAlmostEqual(whooshes[0].timestamp, 4.94, places=2)
        self.assertEqual(whooshes[0].visual_effect, EFFECT_PUNCH_ZOOM)

    def test_impact_for_combat_and_shake(self):
        candidate = {
            "candidate_id": 2,
            "extraction_start": 0.0,
            "extraction_end": 30.0,
            "extraction_duration": 30.0,
        }
        effect_timeline = {
            "candidate_id": 2,
            "candidate_duration": 30.0,
            "effects": [
                {
                    "effect_type": EFFECT_IMPACT_SHAKE,
                    "start_time": 8.0,
                    "end_time": 8.4,
                    "intensity": 0.9,
                    "confidence": 0.95,
                    "coinciding_signals": ["explosion"],
                }
            ],
        }

        timeline = self.engine.build_audio_timeline(
            candidate=candidate,
            effect_timeline=effect_timeline,
            gameplay_signals=[],
            transcript_data={"segments": []},
        )

        impacts = [ev for ev in timeline.audio_events if ev.event_type == SFX_MAJOR_IMPACT]
        self.assertGreaterEqual(len(impacts), 1)
        self.assertEqual(impacts[0].timestamp, 8.0)

    def test_no_whoosh_for_subtle_zoom(self):
        candidate = {
            "candidate_id": 3,
            "extraction_start": 0.0,
            "extraction_end": 30.0,
            "extraction_duration": 30.0,
        }
        effect_timeline = {
            "candidate_id": 3,
            "candidate_duration": 30.0,
            "effects": [
                {
                    "effect_type": EFFECT_SUBTLE_ZOOM,
                    "start_time": 4.0,
                    "end_time": 4.5,
                    "intensity": 0.4,
                    "confidence": 0.6,
                },
                {
                    "effect_type": EFFECT_MICRO_SHAKE,
                    "start_time": 12.0,
                    "end_time": 12.3,
                    "intensity": 0.3,
                    "confidence": 0.5,
                },
            ],
        }

        timeline = self.engine.build_audio_timeline(
            candidate=candidate,
            effect_timeline=effect_timeline,
            gameplay_signals=[],
            transcript_data={"segments": []},
        )

        whooshes = [ev for ev in timeline.audio_events if ev.event_type == SFX_WHOOSH]
        self.assertEqual(len(whooshes), 0, "Subtle zoom must NOT trigger whoosh SFX")

    def test_cooldown_enforcement(self):
        candidate = {
            "candidate_id": 4,
            "extraction_start": 0.0,
            "extraction_end": 30.0,
            "extraction_duration": 30.0,
        }
        # Two punch zooms 0.3s apart - second should be suppressed due to cooldown
        effect_timeline = {
            "candidate_id": 4,
            "candidate_duration": 30.0,
            "effects": [
                {
                    "effect_type": EFFECT_PUNCH_ZOOM,
                    "start_time": 5.0,
                    "end_time": 5.4,
                    "intensity": 0.8,
                    "confidence": 0.9,
                },
                {
                    "effect_type": EFFECT_PUNCH_ZOOM,
                    "start_time": 5.3,
                    "end_time": 5.7,
                    "intensity": 0.8,
                    "confidence": 0.9,
                },
            ],
        }

        timeline = self.engine.build_audio_timeline(
            candidate=candidate,
            effect_timeline=effect_timeline,
            gameplay_signals=[],
            transcript_data={"segments": []},
        )

        whooshes = [ev for ev in timeline.audio_events if ev.event_type == SFX_WHOOSH]
        self.assertEqual(len(whooshes), 1, "Rapid succession whoosh must be rate-limited by cooldown")
        self.assertGreaterEqual(len(timeline.suppressed_events), 1)

    def test_density_limit_per_30s(self):
        candidate = {
            "candidate_id": 5,
            "extraction_start": 0.0,
            "extraction_end": 30.0,
            "extraction_duration": 30.0,
        }
        # Create 15 punch zooms separated by 1.8s
        effects = []
        for i in range(15):
            effects.append({
                "effect_type": EFFECT_PUNCH_ZOOM,
                "start_time": 1.0 + i * 1.8,
                "end_time": 1.4 + i * 1.8,
                "intensity": 0.8,
                "confidence": 0.9,
            })

        effect_timeline = {
            "candidate_id": 5,
            "candidate_duration": 30.0,
            "effects": effects,
        }

        timeline = self.engine.build_audio_timeline(
            candidate=candidate,
            effect_timeline=effect_timeline,
            gameplay_signals=[],
            transcript_data={"segments": []},
        )

        self.assertLessEqual(len(timeline.audio_events), MAX_SFX_PER_30_SECONDS)

    def test_variable_duration_scaling(self):
        # 180s clip can accommodate proportionally more SFX than 30s
        for dur in [15.0, 60.0, 120.0, 180.0]:
            candidate = {
                "candidate_id": 6,
                "extraction_start": 0.0,
                "extraction_end": dur,
                "extraction_duration": dur,
            }
            effect_timeline = {"candidate_id": 6, "candidate_duration": dur, "effects": []}
            timeline = self.engine.build_audio_timeline(
                candidate=candidate,
                effect_timeline=effect_timeline,
                gameplay_signals=[],
                transcript_data={"segments": []},
            )
            self.assertEqual(timeline.candidate_duration, dur)
            self.assertIsInstance(timeline.to_dict(), dict)

    def test_timeline_serialization(self):
        timeline = AudioTimeline(
            candidate_id=1,
            candidate_duration=30.0,
            audio_events=[
                AudioEvent(
                    timestamp=5.1234,
                    event_type=SFX_WHOOSH,
                    asset_name="whoosh_soft.wav",
                    gain_db=-18.0,
                    intensity=0.8,
                    confidence=0.9,
                    source="visual_effect",
                    visual_effect=EFFECT_PUNCH_ZOOM,
                    reason="Test event",
                )
            ],
            ducking_summary={"enabled": True},
        )
        d = timeline.to_dict()
        self.assertEqual(d["candidate_id"], 1)
        self.assertEqual(d["total_sfx"], 1)
        self.assertEqual(d["sfx_counts"][SFX_WHOOSH], 1)
        self.assertEqual(d["audio_events"][0]["timestamp"], 5.123)
        self.assertTrue(d["ducking"]["enabled"])


if __name__ == "__main__":
    unittest.main()
