"""Unit test suite for Multi-Genre Game Intelligence Layer:
Story/Open-World (GTA, RDR2, Elden Ring, Cyberpunk),
Horror/Survival (Resident Evil, Phasmophobia, Lethal Company),
Competitive FPS (Valorant, CS2, Apex, CoD),
and UI Game Intelligence Selector.
"""

import unittest
from typing import Dict, Any, List

from backend.app.config import (
    STORY_OPEN_WORLD_SCORING_WEIGHTS,
    HORROR_SURVIVAL_SCORING_WEIGHTS,
    COMPETITIVE_FPS_SCORING_WEIGHTS,
    GAME_AWARE_SCORING_WEIGHTS,
    EFFECT_PUNCH_ZOOM,
    EFFECT_IMPACT_ZOOM,
    EFFECT_MICRO_SHAKE,
    EFFECT_IMPACT_SHAKE,
    EFFECT_EMPHASIS_FLASH,
)
from backend.app.pipeline.games.models import (
    GameplayEvent,
    EventType,
    EventStatus,
    EvidenceBreakdown,
)
from backend.app.pipeline.games.timeline import GameplayTimeline
from backend.app.pipeline.games.detector import GameDetector
from backend.app.pipeline.games.profiles.story_open_world import StoryOpenWorldProfile
from backend.app.pipeline.games.profiles.horror_survival import HorrorSurvivalProfile
from backend.app.pipeline.games.profiles.competitive_fps import CompetitiveFPSProfile
from backend.app.pipeline.games.profiles.valorant import ValorantGameProfile
from backend.app.pipeline.games.archetypes.story_detector import StoryDetector
from backend.app.pipeline.games.archetypes.horror_detector import HorrorDetector
from backend.app.pipeline.games.archetypes.fps_detector import FPSDetector
from backend.app.pipeline.candidate_generator import CandidateGenerator
from backend.app.pipeline.candidate_ranker import CandidateRanker
from backend.app.pipeline.transcript_analyzer import TranscriptAnalyzer
from backend.app.pipeline.effect_engine import EffectEngine
from backend.app.pipeline.emoji_engine import EmojiEngine
from backend.app.pipeline.clip_summary_engine import ClipSummaryEngine
from backend.app.pipeline.description_engine import DescriptionEngine
from backend.app.pipeline.hashtag_engine import HashtagEngine


def make_dummy_transcript(words: List[Dict[str, Any]]) -> Dict[str, Any]:
    text = " ".join(w["word"] for w in words)
    duration = words[-1]["end"] if words else 0.0
    return {
        "language": "en",
        "duration": duration,
        "segments": [{
            "start": words[0]["start"] if words else 0.0,
            "end": duration,
            "text": text,
            "words": words,
        }],
    }


class TestGameDetector(unittest.TestCase):
    """Test game detection and profile selection across multiple genres."""

    def setUp(self):
        self.detector = GameDetector()

    def test_detect_story_open_world_titles(self):
        # GTA VI
        p = self.detector.detect_game(metadata={"title": "GTA VI - Vice City Official Gameplay Walkthrough"})
        self.assertIsInstance(p, StoryOpenWorldProfile)
        self.assertEqual(p.archetype, "story_open_world")
        self.assertEqual(p.detected_title, "GTA VI")

        # GTA V
        p = self.detector.detect_game(metadata={"title": "GTA V Police Chase Chaos 5 Stars Escaped"})
        self.assertIsInstance(p, StoryOpenWorldProfile)
        self.assertEqual(p.detected_title, "GTA V")

        # Red Dead Redemption 2
        p = self.detector.detect_game(metadata={"title": "RDR2 Arthur Morgan Emotional Last Ride Scene"})
        self.assertIsInstance(p, StoryOpenWorldProfile)
        self.assertEqual(p.detected_title, "Red Dead Redemption 2")

        # Elden Ring
        p = self.detector.detect_game(metadata={"title": "Elden Ring Malenia Blade of Miquella No Hit Boss Fight"})
        self.assertIsInstance(p, StoryOpenWorldProfile)
        self.assertEqual(p.detected_title, "Elden Ring")

    def test_detect_horror_survival_titles(self):
        # Resident Evil
        p = self.detector.detect_game(metadata={"title": "Resident Evil 4 Remake Chainsaw Village Attack"})
        self.assertIsInstance(p, HorrorSurvivalProfile)
        self.assertEqual(p.archetype, "horror_survival")
        self.assertEqual(p.detected_title, "Resident Evil")

        # Phasmophobia
        p = self.detector.detect_game(metadata={"title": "Phasmophobia Demon Hunting Us in Sunny Meadows Nightmare"})
        self.assertIsInstance(p, HorrorSurvivalProfile)
        self.assertEqual(p.detected_title, "Phasmophobia")

        # Lethal Company
        p = self.detector.detect_game(metadata={"title": "Lethal Company Funniest Jester Moments with Friends"})
        self.assertIsInstance(p, HorrorSurvivalProfile)
        self.assertEqual(p.detected_title, "Lethal Company")

    def test_detect_fps_titles(self):
        # CS2
        p = self.detector.detect_game(metadata={"title": "CS2 Mirage 1v4 Clutch Inferno Highlights"})
        self.assertIsInstance(p, CompetitiveFPSProfile)
        self.assertEqual(p.archetype, "competitive_fps")
        self.assertEqual(p.detected_title, "Counter-Strike 2")

        # Valorant
        p = self.detector.detect_game(metadata={"title": "Valorant Radiant 1v5 Ace with Vandal"})
        self.assertIsInstance(p, ValorantGameProfile)
        self.assertEqual(p.name, "valorant")
        self.assertEqual(p.archetype, "competitive_fps")

    def test_manual_mode_override_settings(self):
        # Override to story_open_world even if title says Valorant
        p = self.detector.detect_game(
            metadata={"title": "Valorant Clip"},
            settings={"game_mode": "story_open_world"},
        )
        self.assertIsInstance(p, StoryOpenWorldProfile)

        # Override to horror_survival
        p = self.detector.detect_game(
            metadata={"title": "Generic Stream"},
            settings={"game_mode": "horror_survival"},
        )
        self.assertIsInstance(p, HorrorSurvivalProfile)

        # Override to generic
        p = self.detector.detect_game(
            metadata={"title": "GTA VI Walkthrough"},
            settings={"game_mode": "generic"},
        )
        self.assertEqual(p.name, "generic")


class TestStoryDetector(unittest.TestCase):
    """Test Story/Open-World event detection logic."""

    def setUp(self):
        self.detector = StoryDetector(profile=StoryOpenWorldProfile())

    def test_detect_comedic_moment(self):
        transcript_data = {
            "segments": [
                {
                    "start": 10.0,
                    "end": 18.0,
                    "text": "hahaha oh my god bro that was hilarious look at the car flying fail",
                    "words": [
                        {"word": "hahaha", "start": 10.0, "end": 11.0},
                        {"word": "bro", "start": 11.2, "end": 11.8},
                        {"word": "hilarious", "start": 12.0, "end": 13.0},
                        {"word": "fail", "start": 14.0, "end": 15.0},
                    ],
                }
            ]
        }
        audio_analysis = {
            "peaks": [{"timestamp": 12.5, "intensity": 0.85, "volume_db": -8.0}]
        }
        events = self.detector.detect_events(audio_analysis=audio_analysis, transcript_data=transcript_data, duration=60.0)
        comedy_events = [e for e in events if e.event_type == EventType.COMEDIC_MOMENT]
        self.assertGreaterEqual(len(comedy_events), 1)
        self.assertAlmostEqual(comedy_events[0].timestamp, 12.5, delta=2.0)

    def test_detect_story_climax_and_boss_fight(self):
        transcript_data = {
            "segments": [
                {
                    "start": 20.0,
                    "end": 35.0,
                    "text": "this is the end of the line Arthur we are in the endgame now",
                    "words": [
                        {"word": "end", "start": 20.0, "end": 21.0},
                        {"word": "line", "start": 21.2, "end": 22.0},
                        {"word": "endgame", "start": 23.0, "end": 24.5},
                    ],
                },
                {
                    "start": 40.0,
                    "end": 55.0,
                    "text": "dodge the boss attack phase two final hit",
                    "words": [
                        {"word": "dodge", "start": 40.0, "end": 41.0},
                        {"word": "boss", "start": 41.5, "end": 42.2},
                        {"word": "phase", "start": 42.5, "end": 43.0},
                    ],
                }
            ]
        }
        audio_analysis = {
            "peaks": [
                {"timestamp": 23.0, "intensity": 0.8, "volume_db": -10.0},
                {"timestamp": 42.0, "intensity": 0.9, "volume_db": -6.0},
            ]
        }
        events = self.detector.detect_events(audio_analysis=audio_analysis, transcript_data=transcript_data, duration=90.0)
        story_events = [e for e in events if e.event_type == EventType.STORY_CLIMAX]
        boss_events = [e for e in events if e.event_type == EventType.BOSS_FIGHT_CLIMAX]
        self.assertGreaterEqual(len(story_events), 1)
        self.assertGreaterEqual(len(boss_events), 1)


class TestHorrorDetector(unittest.TestCase):
    """Test Horror/Survival event detection (jumpscares & panic escapes)."""

    def setUp(self):
        self.detector = HorrorDetector(profile=HorrorSurvivalProfile())

    def test_detect_silence_to_scream_jumpscare(self):
        # Audio with a quiet period followed by a massive scream spike
        audio_analysis = {
            "rms_series": [
                (20.0, 0.04),
                (21.0, 0.05),
                (22.0, 0.03),
                (23.0, 0.04),
                (24.0, 0.78),  # Massive contrast (> 15x quiet baseline)
                (25.0, 0.65),
            ],
            "peaks": [
                {"timestamp": 24.0, "intensity": 0.95, "volume_db": -3.0}
            ],
        }
        transcript_data = {
            "segments": [
                {
                    "start": 23.8,
                    "end": 26.0,
                    "text": "AHHH what is that holy shit",
                    "words": [
                        {"word": "AHHH", "start": 23.9, "end": 24.5},
                        {"word": "what", "start": 24.6, "end": 25.0},
                    ],
                }
            ]
        }
        events = self.detector.detect_events(audio_analysis=audio_analysis, transcript_data=transcript_data, duration=60.0)
        jumpscares = [e for e in events if e.event_type == EventType.JUMPSCARE]
        self.assertGreaterEqual(len(jumpscares), 1)
        self.assertAlmostEqual(jumpscares[0].timestamp, 24.0, delta=1.0)
        self.assertIn("jumpscare", jumpscares[0].explanation.lower())

    def test_detect_panic_escape(self):
        transcript_data = {
            "segments": [
                {
                    "start": 15.0,
                    "end": 25.0,
                    "text": "run run run don't look back close the door he's right behind us",
                    "words": [
                        {"word": "run", "start": 15.0, "end": 15.5},
                        {"word": "door", "start": 17.0, "end": 18.0},
                        {"word": "behind", "start": 19.0, "end": 20.0},
                    ],
                }
            ]
        }
        audio_analysis = {
            "peaks": [{"timestamp": 18.0, "intensity": 0.75, "volume_db": -9.0}]
        }
        events = self.detector.detect_events(audio_analysis=audio_analysis, transcript_data=transcript_data, duration=60.0)
        escapes = [e for e in events if e.event_type == EventType.PANIC_ESCAPE]
        self.assertGreaterEqual(len(escapes), 1)


class TestCandidateRankerMultiGenre(unittest.TestCase):
    """Test ranking with archetype-specific weights and weighted-sum consistency."""

    def setUp(self):
        self.ranker = CandidateRanker()

    def test_story_open_world_scoring_and_weights(self):
        story_profile = StoryOpenWorldProfile()
        story_profile.detected_title = "GTA VI"

        event = GameplayEvent(
            id="story_climax_1",
            event_type=EventType.STORY_CLIMAX,
            timestamp=45.0,
            start_time=43.0,
            end_time=47.0,
            confidence=0.9,
            evidence=EvidenceBreakdown(lexical_keyword="climax", audio_signal="speech_surge"),
        )
        timeline = GameplayTimeline(game="story_open_world", events=[event])

        words = [
            {"word": "Arthur", "start": 30.0, "end": 31.0},
            {"word": "unbelievable", "start": 44.0, "end": 45.5},
            {"word": "insane", "start": 45.8, "end": 46.5},
        ]
        transcript_data = make_dummy_transcript(words)
        ta = TranscriptAnalyzer(transcript_data)
        audio_analysis = {
            "peaks": [{"timestamp": 45.0, "intensity": 0.85, "volume_db": -7.0}],
            "rms_series": [(t, 0.2) for t in range(0, 70)],
        }

        candidates = [(25.0, 55.0)]

        ranked = self.ranker.rank_candidates(
            candidates=candidates,
            audio_analysis=audio_analysis,
            transcript_analyzer=ta,
            video_id="gta_test",
            video_duration=70.0,
            gameplay_timeline=timeline,
            game_profile=story_profile,
        )

        c = ranked["candidates"][0]
        self.assertEqual(c["game_archetype"], "story_open_world")
        self.assertEqual(c["detected_game_title"], "GTA VI")
        self.assertEqual(c["effect_style"], "cinematic_comedy")

        # Weighted-sum consistency assertion (strictly <= 0.15)
        scores = c["component_scores"]
        weights = STORY_OPEN_WORLD_SCORING_WEIGHTS
        expected_sum = (
            weights["gameplay_event"] * scores["gameplay_event"]
            + weights["audio"] * scores["audio"]
            + weights["transcript"] * scores["transcript"]
            + weights["context"] * scores["context"]
            + weights["boundary"] * scores["boundary"]
        )
        self.assertAlmostEqual(c["final_score"], expected_sum, delta=0.15)

    def test_horror_survival_scoring_and_weights(self):
        horror_profile = HorrorSurvivalProfile()
        horror_profile.detected_title = "Resident Evil"

        event = GameplayEvent(
            id="jumpscare_1",
            event_type=EventType.JUMPSCARE,
            timestamp=25.0,
            start_time=24.0,
            end_time=26.0,
            confidence=0.95,
            evidence=EvidenceBreakdown(audio_signal="silence_to_scream"),
        )
        timeline = GameplayTimeline(game="horror_survival", events=[event])

        words = [
            {"word": "listen", "start": 20.0, "end": 21.0},
            {"word": "AHHH", "start": 25.0, "end": 26.0},
        ]
        transcript_data = make_dummy_transcript(words)
        ta = TranscriptAnalyzer(transcript_data)
        audio_analysis = {
            "peaks": [{"timestamp": 25.0, "intensity": 0.95, "volume_db": -4.0}],
            "rms_series": [(t, 0.05 if t < 25 else 0.8) for t in range(0, 50)],
        }

        candidates = [(15.0, 35.0)]

        ranked = self.ranker.rank_candidates(
            candidates=candidates,
            audio_analysis=audio_analysis,
            transcript_analyzer=ta,
            video_id="horror_test",
            video_duration=50.0,
            gameplay_timeline=timeline,
            game_profile=horror_profile,
        )

        c = ranked["candidates"][0]
        self.assertEqual(c["game_archetype"], "horror_survival")
        self.assertEqual(c["detected_game_title"], "Resident Evil")
        self.assertEqual(c["effect_style"], "horror_tension")

        scores = c["component_scores"]
        weights = HORROR_SURVIVAL_SCORING_WEIGHTS
        expected_sum = (
            weights["gameplay_event"] * scores["gameplay_event"]
            + weights["audio"] * scores["audio"]
            + weights["transcript"] * scores["transcript"]
            + weights["context"] * scores["context"]
            + weights["boundary"] * scores["boundary"]
        )
        self.assertAlmostEqual(c["final_score"], expected_sum, delta=0.15)


class TestEffectAndEmojiEngineMultiGenre(unittest.TestCase):
    """Test archetype-specific visual effects and emoji mappings."""

    def test_cinematic_comedy_effect_budget(self):
        engine = EffectEngine()
        # Candidate with comedy & story events
        candidate = {
            "start": 10.0,
            "end": 50.0,
            "duration": 40.0,
            "effect_style": "cinematic_comedy",
            "max_effects_per_minute": 6,
            "gameplay_events": [
                {
                    "event_type": "comedic_moment",
                    "timestamp": 25.0,
                    "confidence": 0.9,
                },
                {
                    "event_type": "story_climax",
                    "timestamp": 40.0,
                    "confidence": 0.85,
                }
            ],
            "subtitle_timings": [
                {"start": 15.0, "end": 17.0, "text": "talking normally bro"},
                {"start": 30.0, "end": 32.0, "text": "dialogue here"},
            ]
        }

        timeline = engine.generate_timeline(
            candidate_id=1,
            candidate=candidate,
            phase4_data=candidate,
            audio_peaks=[{"timestamp": 25.0, "intensity": 0.85}],
            facecam_info={"facecam_detected": False},
        )

        # Max allowed effects for 40s at 6/min = ceil(6 * 40/60) = 4
        self.assertLessEqual(len(timeline.effects), 4)

        # In cinematic_comedy, we should NOT have micro-shake on ordinary speech
        types = [e.type for e in timeline.effects]
        self.assertNotIn(EFFECT_IMPACT_SHAKE, types)

    def test_horror_tension_jumpscare_effects(self):
        engine = EffectEngine()
        candidate = {
            "start": 10.0,
            "end": 35.0,
            "duration": 25.0,
            "effect_style": "horror_tension",
            "max_effects_per_minute": 8,
            "gameplay_events": [
                {
                    "event_type": "jumpscare",
                    "timestamp": 22.0,
                    "confidence": 0.95,
                }
            ],
            "subtitle_timings": []
        }

        timeline = engine.generate_timeline(
            candidate_id=1,
            candidate=candidate,
            phase4_data=candidate,
            audio_peaks=[{"timestamp": 22.0, "intensity": 0.95}],
            facecam_info={"facecam_detected": False},
        )

        types = [e.type for e in timeline.effects]
        # Jumpscare should trigger punch/impact zoom, impact shake, and flash
        self.assertTrue(any(t in (EFFECT_PUNCH_ZOOM, EFFECT_IMPACT_ZOOM) for t in types))
        self.assertIn(EFFECT_IMPACT_SHAKE, types)
        self.assertIn(EFFECT_EMPHASIS_FLASH, types)

    def test_emoji_engine_multi_genre_mapping(self):
        engine = EmojiEngine()
        dummy_transcript = {"segments": []}

        # Jumpscare
        emojis_horror = engine.detect_emojis(
            transcript_data=dummy_transcript,
            clip_start=0.0,
            clip_end=30.0,
            gameplay_events=[{"event_type": "jumpscare", "timestamp": 12.0}],
        )
        self.assertTrue(any(e["emoji"] == "😱" for e in emojis_horror))

        # Comedy
        emojis_comedy = engine.detect_emojis(
            transcript_data=dummy_transcript,
            clip_start=0.0,
            clip_end=30.0,
            gameplay_events=[{"event_type": "comedic_moment", "timestamp": 15.0}],
        )
        self.assertTrue(any(e["emoji"] == "😂" for e in emojis_comedy))

        # Story climax
        emojis_story = engine.detect_emojis(
            transcript_data=dummy_transcript,
            clip_start=0.0,
            clip_end=30.0,
            gameplay_events=[{"event_type": "story_climax", "timestamp": 20.0}],
        )
        self.assertTrue(any(e["emoji"] == "🤯" for e in emojis_story))


class TestPublishingEnginesMultiGenre(unittest.TestCase):
    """Test summary, description, and hashtag generation for multi-genre games."""

    def test_clip_summary_and_title_preservation(self):
        summary_engine = ClipSummaryEngine()
        candidate = {
            "rank": 1,
            "candidate_start": 10.0,
            "candidate_end": 45.0,
            "detected_game_title": "GTA VI",
            "game_archetype": "story_open_world",
            "gameplay_events": [
                {"event_type": "story_climax", "timestamp": 40.0},
                {"event_type": "comedic_moment", "timestamp": 25.0},
            ]
        }
        summary = summary_engine.summarize_candidate(candidate)
        self.assertEqual(summary.game, "GTA VI")
        self.assertEqual(summary.primary_event.lower(), "story climax")
        self.assertIn("comedy", [s.lower() for s in summary.secondary_events])
        self.assertEqual(summary.gameplay_stats["comedic_moments"], 1)
        self.assertEqual(summary.gameplay_stats["story_climaxes"], 1)

    def test_description_hooks_story_and_horror(self):
        summary_engine = ClipSummaryEngine()
        desc_engine = DescriptionEngine()

        # Story candidate
        cand_story = {
            "rank": 1,
            "candidate_start": 10.0,
            "candidate_end": 50.0,
            "detected_game_title": "GTA VI",
            "gameplay_events": [{"event_type": "story_climax", "timestamp": 35.0}]
        }
        sum_story = summary_engine.summarize_candidate(cand_story)
        hooks_story = desc_engine.generate_candidate_hooks(sum_story)
        self.assertTrue(any("GTA VI" in h and "story" in h.lower() for h in hooks_story))

        # Horror candidate
        cand_horror = {
            "rank": 2,
            "candidate_start": 5.0,
            "candidate_end": 35.0,
            "detected_game_title": "Phasmophobia",
            "gameplay_events": [{"event_type": "jumpscare", "timestamp": 20.0}]
        }
        sum_horror = summary_engine.summarize_candidate(cand_horror)
        hooks_horror = desc_engine.generate_candidate_hooks(sum_horror)
        self.assertTrue(any("jumpscare" in h.lower() for h in hooks_horror))

    def test_hashtag_engine_no_fps_spam(self):
        summary_engine = ClipSummaryEngine()
        tag_engine = HashtagEngine()

        # GTA VI should have #GTAVI, #StoryMode, and NOT #FPS
        cand_gta = {
            "rank": 1,
            "candidate_start": 0.0,
            "candidate_end": 40.0,
            "detected_game_title": "GTA VI",
            "gameplay_events": [{"event_type": "story_climax", "timestamp": 20.0}]
        }
        sum_gta = summary_engine.summarize_candidate(cand_gta)
        tags_gta = tag_engine.generate_hashtags(sum_gta)
        self.assertIn("#GTAVI", tags_gta)
        self.assertIn("#StoryMode", tags_gta)
        self.assertNotIn("#FPS", tags_gta)

        # Horror candidate should have #HorrorGaming, #Jumpscare
        cand_horror = {
            "rank": 2,
            "candidate_start": 0.0,
            "candidate_end": 30.0,
            "detected_game_title": "Resident Evil",
            "gameplay_events": [{"event_type": "jumpscare", "timestamp": 15.0}]
        }
        sum_horror = summary_engine.summarize_candidate(cand_horror)
        tags_horror = tag_engine.generate_hashtags(sum_horror)
        self.assertIn("#ResidentEvil", tags_horror)
        self.assertIn("#Jumpscare", tags_horror)
        self.assertNotIn("#FPS", tags_horror)


if __name__ == "__main__":
    unittest.main()
