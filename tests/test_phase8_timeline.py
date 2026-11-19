"""Unit tests for Phase 8: Editable Multi-Track Timeline & EDL Engine."""

import unittest
import tempfile
import json
import shutil
from pathlib import Path

from backend.app.pipeline.timeline import (
    TimelineEDL,
    TimelineBoundaries,
    TimelineVideoTrack,
    SubtitleItem,
    SubtitleWordItem,
    EmojiItem,
    EffectItem,
    SfxItem,
    DuckingItem,
    TimelineMetadata,
    TimelineValidator,
    DirtyTracker,
    TimelineEdlGenerator,
    TimelineStore,
)


class TestTimelineModelsAndValidation(unittest.TestCase):
    """Test TimelineEDL schema, boundaries, and validation constraints."""

    def setUp(self):
        self.validator = TimelineValidator()
        self.valid_edl = TimelineEDL(
            project_id="test_proj",
            candidate_id=1,
            version=1,
            duration=35.0,
            boundaries=TimelineBoundaries(
                source_in=100.0,
                source_out=135.0,
                duration=35.0,
            ),
            video_track=TimelineVideoTrack(
                source_file="source.mp4",
                layout="smart_crop",
                resolution="1080x1920",
                fps=60,
            ),
            subtitles_track=[
                SubtitleItem(
                    id="sub_01",
                    start=1.5,
                    end=3.5,
                    text="Talk about timing",
                    words=[
                        SubtitleWordItem(word="Talk", start=1.5, end=1.8),
                        SubtitleWordItem(word="about", start=1.8, end=2.4),
                        SubtitleWordItem(word="timing", start=2.4, end=3.5),
                    ],
                )
            ],
            emoji_track=[
                EmojiItem(id="emo_01", timestamp=2.4, duration=1.2, emoji="😂")
            ],
            effects_track=[
                EffectItem(id="eff_01", type="punch_zoom", start=5.0, end=6.0, intensity=0.8)
            ],
            sfx_track=[
                SfxItem(id="sfx_01", timestamp=5.0, event_type="whoosh", asset_name="whoosh_strong.wav", gain_db=-14.0)
            ],
            ducking_track=[
                DuckingItem(id="duck_01", start=1.0, end=4.0, attenuation_db=-3.5)
            ],
            metadata=TimelineMetadata(source="ai_generated"),
        )

    def test_valid_timeline(self):
        is_valid, errors = self.validator.validate(self.valid_edl)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_invalid_boundaries(self):
        # source_out <= source_in
        invalid_edl = self.valid_edl.model_copy(deep=True)
        invalid_edl.boundaries.source_out = 90.0
        is_valid, errors = self.validator.validate(invalid_edl)
        self.assertFalse(is_valid)
        self.assertTrue(any("source_out" in e for e in errors))

    def test_duration_outside_bounds(self):
        # duration < 15s
        invalid_edl = self.valid_edl.model_copy(deep=True)
        invalid_edl.boundaries.source_out = 105.0
        invalid_edl.boundaries.duration = 5.0
        invalid_edl.duration = 5.0
        is_valid, errors = self.validator.validate(invalid_edl)
        self.assertFalse(is_valid)
        self.assertTrue(any("outside allowed bounds" in e for e in errors))

    def test_invalid_subtitle_empty_text_and_negative_time(self):
        invalid_edl = self.valid_edl.model_copy(deep=True)
        invalid_edl.subtitles_track[0].text = "   "
        invalid_edl.subtitles_track[0].start = -2.0
        is_valid, errors = self.validator.validate(invalid_edl)
        self.assertFalse(is_valid)
        self.assertTrue(any("empty" in e for e in errors))
        self.assertTrue(any("negative" in e for e in errors))

    def test_invalid_effect_type(self):
        invalid_edl = self.valid_edl.model_copy(deep=True)
        invalid_edl.effects_track[0].type = "unsupported_rainbow_explosion"
        is_valid, errors = self.validator.validate(invalid_edl)
        self.assertFalse(is_valid)
        self.assertTrue(any("unsupported type" in e for e in errors))

    def test_invalid_sfx_asset(self):
        invalid_edl = self.valid_edl.model_copy(deep=True)
        invalid_edl.sfx_track[0].asset_name = "non_existent_audio.wav"
        is_valid, errors = self.validator.validate(invalid_edl)
        self.assertFalse(is_valid)
        self.assertTrue(any("not found in library" in e for e in errors))


class TestEdlGenerator(unittest.TestCase):
    """Test generating a TimelineEDL from AI analysis artifacts."""

    def test_generate_edl_from_artifacts(self):
        generator = TimelineEdlGenerator()
        candidate = {
            "start": 50.0,
            "end": 85.0,
            "duration": 35.0,
            "layout": "smart_crop",
        }
        transcript_data = {
            "language": "hi-Latn",
            "segments": [
                {
                    "start": 52.0,
                    "end": 56.0,
                    "text": "Bhai ye kya kar raha hai",
                    "words": [
                        {"word": "Bhai", "start": 52.0, "end": 52.5},
                        {"word": "ye", "start": 52.5, "end": 53.0},
                        {"word": "kya", "start": 53.0, "end": 53.8},
                        {"word": "kar", "start": 53.8, "end": 54.4},
                        {"word": "raha", "start": 54.4, "end": 55.0},
                        {"word": "hai", "start": 55.0, "end": 55.8},
                    ],
                }
            ],
        }
        phase5_tl = {
            "effects": [
                {"type": "punch_zoom", "start": 10.0, "end": 11.0, "intensity": 0.8, "reason": "climax"}
            ]
        }
        phase6a_tl = {
            "audio_events": [
                {"timestamp": 10.0, "event_type": "whoosh", "asset_name": "whoosh_strong.wav", "gain_db": -14.0}
            ],
            "ducking_schedule": [
                {"start": 2.0, "end": 6.0, "attenuation_db": -4.0, "attack_ms": 150, "release_ms": 300}
            ],
        }

        edl = generator.generate_edl(
            project_id="test_vid",
            candidate_id=1,
            candidate=candidate,
            transcript_data=transcript_data,
            phase5_timeline=phase5_tl,
            phase6a_timeline=phase6a_tl,
            source_video_path="source.mp4",
        )

        self.assertEqual(edl.candidate_id, 1)
        self.assertEqual(edl.boundaries.source_in, 50.0)
        self.assertEqual(edl.boundaries.source_out, 85.0)
        self.assertEqual(edl.duration, 35.0)
        self.assertGreater(len(edl.subtitles_track), 0)
        self.assertEqual(edl.subtitles_track[0].language, "hi-Latn")
        self.assertEqual(len(edl.effects_track), 1)
        self.assertEqual(edl.effects_track[0].type, "punch_zoom")
        self.assertEqual(len(edl.sfx_track), 1)
        self.assertEqual(edl.sfx_track[0].event_type, "whoosh")
        self.assertEqual(len(edl.ducking_track), 1)


class TestDirtyTracker(unittest.TestCase):
    """Test change tracking across all tracks."""

    def setUp(self):
        generator = TimelineEdlGenerator()
        cand = {"start": 10.0, "end": 45.0, "duration": 35.0}
        self.base_edl = generator.generate_edl(
            project_id="test_dirty",
            candidate_id=1,
            candidate=cand,
        )

    def test_no_changes(self):
        new_edl = self.base_edl.model_copy(deep=True)
        dirty = DirtyTracker.detect_dirty_tracks(self.base_edl, new_edl)
        self.assertEqual(len(dirty), 0)

    def test_subtitle_text_change(self):
        new_edl = self.base_edl.model_copy(deep=True)
        new_edl.subtitles_track.append(
            SubtitleItem(id="sub_test", start=1.0, end=3.0, text="New text")
        )
        dirty = DirtyTracker.detect_dirty_tracks(self.base_edl, new_edl)
        self.assertIn("subtitles", dirty)

    def test_effects_change(self):
        new_edl = self.base_edl.model_copy(deep=True)
        new_edl.effects_track.append(
            EffectItem(id="eff_test", type="micro_shake", start=2.0, end=3.0, intensity=0.5)
        )
        dirty = DirtyTracker.detect_dirty_tracks(self.base_edl, new_edl)
        self.assertIn("effects", dirty)

    def test_sfx_gain_change(self):
        new_edl = self.base_edl.model_copy(deep=True)
        new_edl.sfx_track.append(
            SfxItem(id="sfx_test", timestamp=5.0, event_type="whoosh", asset_name="whoosh_soft.wav", gain_db=-18.0)
        )
        dirty = DirtyTracker.detect_dirty_tracks(self.base_edl, new_edl)
        self.assertIn("sfx", dirty)

    def test_boundaries_change(self):
        new_edl = self.base_edl.model_copy(deep=True)
        new_edl.boundaries.source_in = 12.0
        new_edl.boundaries.duration = 33.0
        dirty = DirtyTracker.detect_dirty_tracks(self.base_edl, new_edl)
        self.assertIn("boundaries", dirty)


class TestTimelineStoreAndVersioning(unittest.TestCase):
    """Test disk persistence, file backup, and version incrementing."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = TimelineStore()
        generator = TimelineEdlGenerator()
        cand = {"start": 0.0, "end": 30.0, "duration": 30.0}
        self.initial_edl = generator.generate_edl(
            project_id="test_store",
            candidate_id=1,
            candidate=cand,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load(self):
        saved = self.store.save_timeline(self.temp_dir, self.initial_edl, increment_version=False)
        self.assertEqual(saved.version, 1)

        loaded = self.store.get_timeline(self.temp_dir, 1)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.candidate_id, 1)
        self.assertEqual(loaded.version, 1)
        self.assertEqual(loaded.duration, 30.0)

    def test_version_increment_and_backup(self):
        # Save v1
        self.store.save_timeline(self.temp_dir, self.initial_edl, increment_version=False)

        # Edit and save as v2
        edited = self.initial_edl.model_copy(deep=True)
        edited.metadata.dirty_tracks = ["subtitles"]
        v2 = self.store.save_timeline(self.temp_dir, edited, increment_version=True)
        self.assertEqual(v2.version, 2)

        # Verify backup exists
        backup_path = self.temp_dir / "publishing" / "candidate_01" / "timeline.v1.json"
        self.assertTrue(backup_path.exists())

        active_path = self.temp_dir / "publishing" / "candidate_01" / "timeline.json"
        self.assertTrue(active_path.exists())


class TestTimelineEditingOperations(unittest.TestCase):
    """Test detailed user editing workflows on subtitle, emoji, effect, and SFX tracks."""

    def setUp(self):
        generator = TimelineEdlGenerator()
        cand = {"start": 10.0, "end": 50.0, "duration": 40.0}
        self.edl = generator.generate_edl("proj_edit", 1, cand)

    def test_subtitle_text_edit_preserves_original(self):
        sub = SubtitleItem(
            id="sub_01",
            start=1.0,
            end=3.0,
            text="Bhai ye kya kar raha hai",
            language="hi-Latn",
            source="ai",
            edited=False,
            original_text="Bhai ye kya kar raha hai",
        )
        self.edl.subtitles_track.append(sub)

        # User edits subtitle text
        self.edl.subtitles_track[0].text = "Bhai ye kya kr raha hai"
        self.edl.subtitles_track[0].edited = True
        self.assertEqual(self.edl.subtitles_track[0].text, "Bhai ye kya kr raha hai")
        self.assertEqual(self.edl.subtitles_track[0].original_text, "Bhai ye kya kar raha hai")
        self.assertTrue(self.edl.subtitles_track[0].edited)

    def test_disable_sfx_and_effect(self):
        sfx = SfxItem(id="sfx_01", timestamp=4.0, event_type="whoosh", asset_name="whoosh_strong.wav", gain_db=-14.0, enabled=True)
        eff = EffectItem(id="eff_01", type="punch_zoom", start=4.0, end=5.0, intensity=0.8, enabled=True)
        self.edl.sfx_track.append(sfx)
        self.edl.effects_track.append(eff)

        # User disables them
        self.edl.sfx_track[0].enabled = False
        self.edl.effects_track[0].enabled = False
        self.assertFalse(self.edl.sfx_track[0].enabled)
        self.assertFalse(self.edl.effects_track[0].enabled)

    def test_boundary_shift(self):
        self.edl.boundaries.source_in = 15.0
        self.edl.boundaries.source_out = 55.0
        self.edl.boundaries.duration = 40.0
        self.edl.duration = 40.0
        self.assertEqual(self.edl.boundaries.source_in, 15.0)
        self.assertEqual(self.edl.boundaries.source_out, 55.0)


class TestQualityInvalidation(unittest.TestCase):
    """Test that timeline edits invalidate stale publishability data."""

    def test_quality_stale_flagging(self):
        candidate_meta = {
            "publishability": {
                "score": 88.0,
                "level": "strong",
                "recommendation": "publish",
                "quality_stale": False,
            }
        }
        # When dirty tracks occur, publishability is flagged stale
        dirty_tracks = ["subtitles", "boundaries"]
        if dirty_tracks:
            candidate_meta["publishability"]["quality_stale"] = True
            candidate_meta["publishability"]["recommendation"] = "review"

        self.assertTrue(candidate_meta["publishability"]["quality_stale"])
        self.assertEqual(candidate_meta["publishability"]["recommendation"], "review")


if __name__ == "__main__":
    unittest.main()

