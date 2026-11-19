"""Unit test suite for Phase 12C: Variable Duration (15–180s), Round-Aware Context Expansion,
and Event-Driven Auto-Editing (Effects, Emojis, Descriptions, Hashtags).
"""

import unittest
from typing import Dict, Any, List

from backend.app.config import (
    get_duration_tier,
    get_narrative_structure,
    DURATION_TIERS,
    EFFECT_PUNCH_ZOOM,
    EFFECT_IMPACT_ZOOM,
    EFFECT_MICRO_SHAKE,
    EFFECT_IMPACT_SHAKE,
    EFFECT_EMPHASIS_FLASH,
)
from backend.app.pipeline.candidate_generator import CandidateGenerator
from backend.app.pipeline.candidate_ranker import CandidateRanker
from backend.app.pipeline.transcript_analyzer import TranscriptAnalyzer
from backend.app.pipeline.creator_quality.dimensions import evaluate_narrative_quality
from backend.app.pipeline.emoji_engine import EmojiEngine
from backend.app.pipeline.effect_engine import EffectEngine
from backend.app.pipeline.clip_summary_engine import ClipSummaryEngine, ClipSummary
from backend.app.pipeline.description_engine import DescriptionEngine
from backend.app.pipeline.hashtag_engine import HashtagEngine
from backend.app.pipeline.games.models import (
    GameplayEvent,
    EventType,
    EventStatus,
    EvidenceBreakdown,
)
from backend.app.pipeline.games.timeline import GameplayTimeline


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


def make_dummy_audio(duration: float, peaks: List[Dict[str, Any]]) -> Dict[str, Any]:
    timeline = []
    t = 0.0
    peak_times = {round(p["timestamp"], 1): p for p in peaks}
    while t <= duration:
        pk = peak_times.get(round(t, 1))
        if pk:
            timeline.append({
                "t": round(t, 2),
                "rms": pk["rms"],
                "z": pk["z_score"],
                "is_peak": True,
                "is_silent": False,
            })
        else:
            timeline.append({
                "t": round(t, 2),
                "rms": 0.05,
                "z": 0.2,
                "is_peak": False,
                "is_silent": False,
            })
        t += 0.5

    return {
        "duration": duration,
        "rms_peaks": peaks,
        "timeline": timeline,
        "mean_rms": 0.05,
        "std_rms": 0.02,
    }


class TestPhase12CVariableDurationAndAutoEdit(unittest.TestCase):

    def test_01_duration_tiers_and_narrative_stages(self):
        """Test duration classification and narrative structure lookup."""
        self.assertEqual(get_duration_tier(15.0), "quick")
        self.assertEqual(get_duration_tier(25.0), "quick")
        self.assertEqual(get_duration_tier(30.0), "quick")
        self.assertEqual(get_duration_tier(31.0), "standard")
        self.assertEqual(get_duration_tier(60.0), "standard")
        self.assertEqual(get_duration_tier(90.0), "standard")
        self.assertEqual(get_duration_tier(91.0), "extended")
        self.assertEqual(get_duration_tier(150.0), "extended")
        self.assertEqual(get_duration_tier(180.0), "extended")

        quick_stages = get_narrative_structure("quick")
        self.assertEqual(len(quick_stages), 3)
        self.assertEqual(quick_stages[0], "Hook")
        self.assertEqual(quick_stages[1], "Action")
        self.assertEqual(quick_stages[2], "Payoff")

        std_stages = get_narrative_structure("standard")
        self.assertEqual(len(std_stages), 4)
        self.assertEqual(std_stages[0], "Setup")
        self.assertEqual(std_stages[2], "Major Event")

        ext_stages = get_narrative_structure("extended")
        self.assertEqual(len(ext_stages), 8)
        self.assertEqual(ext_stages[0], "Context")
        self.assertEqual(ext_stages[-1], "Reaction")

    def test_02_candidate_generator_round_aware_context_expansion(self):
        """Test that round-aware context expansion captures opening kill to round win."""
        words = [
            {"word": "Round", "start": 5.0, "end": 5.5},
            {"word": "starts", "start": 5.6, "end": 6.0},
            {"word": "First", "start": 15.0, "end": 15.4},
            {"word": "blood", "start": 15.5, "end": 16.0},
            {"word": "He", "start": 40.0, "end": 40.3},
            {"word": "clutched", "start": 40.4, "end": 40.8},
            {"word": "it", "start": 40.9, "end": 41.2},
            {"word": "Round", "start": 55.0, "end": 55.4},
            {"word": "won", "start": 55.5, "end": 56.0},
        ]
        transcript = make_dummy_transcript(words)
        audio = make_dummy_audio(80.0, [
            {"timestamp": 15.5, "rms": 0.35, "z_score": 2.6},
            {"timestamp": 40.8, "rms": 0.45, "z_score": 3.2},
            {"timestamp": 55.8, "rms": 0.38, "z_score": 2.8},
        ])

        # Timeline with opening kill at 15s, clutch anchor at 40s, round win at 56s
        ev_open = GameplayEvent(
            id="ev_01",
            game="valorant",
            event_type="opening_kill",
            start_time=15.0,
            end_time=16.0,
            confidence=0.90,
            status="confirmed",
            round_number=1,
        )
        ev_clutch = GameplayEvent(
            id="ev_02",
            game="valorant",
            event_type="clutch",
            start_time=40.0,
            end_time=42.0,
            confidence=0.95,
            status="confirmed",
            round_number=1,
        )
        ev_win = GameplayEvent(
            id="ev_03",
            game="valorant",
            event_type="round_win",
            start_time=56.0,
            end_time=58.0,
            confidence=0.92,
            status="confirmed",
            round_number=1,
        )
        timeline = GameplayTimeline(
            game="valorant",
            events=[ev_open, ev_clutch, ev_win],
        )

        gen = CandidateGenerator(duration_mode="auto")
        cand_analyzer = TranscriptAnalyzer(transcript)
        candidates = gen.generate_candidates(
            video_duration=80.0,
            audio_analysis=audio,
            transcript_analyzer=cand_analyzer,
            gameplay_timeline=timeline,
        )

        self.assertGreater(len(candidates), 0)
        # Check that we have a round-expanded candidate spanning from before 15.5 to after 56.0
        expanded_candidates = [(s, e) for s, e in candidates if s <= 15.5 and e >= 56.0]
        self.assertGreater(len(expanded_candidates), 0)
        exp_start, exp_end = expanded_candidates[0]
        exp_dur = exp_end - exp_start
        self.assertGreaterEqual(exp_dur, 40.0)
        self.assertLessEqual(exp_dur, 180.0)

    def test_03_candidate_ranker_duration_fairness_and_narrative_tagging(self):
        """Test that CandidateRanker scores 15-180s clips fairly and tags narrative metadata."""
        ranker = CandidateRanker()
        dummy_transcript = make_dummy_transcript([
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.6, "end": 1.0},
        ])
        analyzer = TranscriptAnalyzer(dummy_transcript)

        # Quick candidate (22s)
        score_q, _, reasons_q, _ = ranker.calculate_boundary_score(0.0, 22.0, analyzer)
        self.assertIn("ideal 15-30s quick clip pacing", reasons_q)

        # Standard candidate (45s)
        score_s, _, reasons_s, _ = ranker.calculate_boundary_score(0.0, 45.0, analyzer)
        self.assertIn("ideal 40-50s duration for mobile shorts pacing", reasons_s)

        # Extended candidate (120s)
        score_e, _, reasons_e, _ = ranker.calculate_boundary_score(0.0, 120.0, analyzer)
        self.assertIn("ideal extended story pacing", reasons_e)

        # Build candidate object with ranker
        words = [
            {"word": "Ace", "start": 10.0, "end": 10.5},
            {"word": "play", "start": 10.6, "end": 11.0},
        ]
        transcript = make_dummy_transcript(words)
        audio = make_dummy_audio(30.0, [{"timestamp": 10.5, "rms": 0.4, "z_score": 3.0}])
        cand_analyzer = TranscriptAnalyzer(transcript)

        cand_raw = CandidateGenerator().generate_candidates(
            video_duration=30.0,
            audio_analysis=audio,
            transcript_analyzer=cand_analyzer,
        )
        ranked = ranker.rank_candidates(
            candidates=cand_raw,
            audio_analysis=audio,
            transcript_analyzer=cand_analyzer,
            video_id="test_vid",
            video_duration=30.0,
        )
        self.assertGreater(len(ranked), 0)
        top = ranked["candidates"][0]
        self.assertIn("duration_tier", top)
        self.assertIn("narrative_structure", top)
        self.assertIn(top["duration_tier"], ["quick", "standard", "extended"])
        self.assertIsInstance(top["narrative_structure"], list)

    def test_04_creator_quality_narrative_acceptance(self):
        """Test that Creator Quality evaluate_narrative_quality welcomes quick and extended formats."""
        cand_quick = {"start": 0.0, "end": 22.0, "duration": 22.0}
        res_quick = evaluate_narrative_quality(cand_quick, [{"start": 1.0, "end": 20.0, "word": "nice"}])
        self.assertGreaterEqual(res_quick["score"], 80.0)
        self.assertTrue(any("balanced narrative arc" in r for r in res_quick["reasons"]))

        cand_ext = {"start": 0.0, "end": 110.0, "duration": 110.0}
        res_ext = evaluate_narrative_quality(cand_ext, [{"start": 1.0, "end": 100.0, "word": "clutch"}])
        self.assertGreaterEqual(res_ext["score"], 80.0)
        self.assertTrue(any("balanced narrative arc" in r for r in res_ext["reasons"]))

    def test_05_event_driven_emoji_generation(self):
        """Test that EmojiEngine produces game-aligned emojis from confirmed events."""
        engine = EmojiEngine()

        gameplay_events = [
            {"event_type": "ace", "timestamp": 10.0, "confidence": 0.95, "status": "confirmed"},
            {"event_type": "clutch", "timestamp": 16.0, "confidence": 0.90, "status": "confirmed"},
            {"event_type": "multi_kill", "timestamp": 22.0, "confidence": 0.88, "status": "confirmed"},
            {"event_type": "headshot", "timestamp": 28.0, "confidence": 0.85, "status": "confirmed"},
            {"event_type": "kill", "timestamp": 34.0, "confidence": 0.80, "status": "confirmed"},
            {"event_type": "round_win", "timestamp": 40.0, "confidence": 0.92, "status": "confirmed"},
            {"event_type": "kill", "timestamp": 42.0, "confidence": 0.70, "status": "supporting"},  # should be ignored
        ]

        emojis = engine.detect_emojis(
            transcript_data={"words": []},
            clip_start=0.0,
            clip_end=50.0,
            gameplay_events=gameplay_events,
        )

        detected_emojis = [e["emoji"] for e in emojis]
        self.assertIn("👑", detected_emojis)  # Ace
        self.assertIn("🥶", detected_emojis)  # Clutch
        self.assertIn("🔥", detected_emojis)  # Multi-kill
        self.assertIn("🎯", detected_emojis)  # Headshot
        self.assertIn("💀", detected_emojis)  # Kill
        self.assertIn("🏆", detected_emojis)  # Round win

    def test_06_event_driven_visual_effects_generation(self):
        """Test that EffectEngine generates punch zooms on kills and impact climaxes on Aces/Clutches."""
        engine = EffectEngine()

        candidate = {
            "candidate_id": 1,
            "candidate_start": 0.0,
            "candidate_end": 60.0,
            "candidate_duration": 60.0,
            "gameplay_events": [
                {"event_type": "headshot", "timestamp": 12.0, "confidence": 0.90, "status": "confirmed"},
                {"event_type": "ace", "timestamp": 25.0, "confidence": 0.98, "status": "confirmed"},
            ],
            "detected_signals": [],
        }

        timeline = engine.generate_timeline(candidate_id=1, candidate=candidate)
        effect_types = [e.type for e in timeline.effects]

        # Headshot triggers punch zoom and micro shake
        self.assertIn(EFFECT_PUNCH_ZOOM, effect_types)
        self.assertIn(EFFECT_MICRO_SHAKE, effect_types)

        # Ace triggers impact zoom, impact shake, and flash
        self.assertIn(EFFECT_IMPACT_ZOOM, effect_types)
        self.assertIn(EFFECT_IMPACT_SHAKE, effect_types)
        self.assertIn(EFFECT_EMPHASIS_FLASH, effect_types)

    def test_07_event_aware_summary_description_and_hashtags(self):
        """Test that ClipSummary, DescriptionEngine, and HashtagEngine produce grounded copy."""
        summary_engine = ClipSummaryEngine()
        desc_engine = DescriptionEngine()
        tag_engine = HashtagEngine()

        candidate = {
            "candidate_id": 1,
            "candidate_start": 0.0,
            "candidate_end": 45.0,
            "candidate_duration": 45.0,
            "duration_tier": "standard",
            "gameplay_events": [
                {"event_type": "kill", "timestamp": 10.0, "confidence": 0.90, "status": "confirmed"},
                {"event_type": "kill", "timestamp": 14.0, "confidence": 0.90, "status": "confirmed"},
                {"event_type": "headshot", "timestamp": 18.0, "confidence": 0.92, "status": "confirmed", "event_metadata": {"headshot": True}},
                {"event_type": "clutch", "timestamp": 25.0, "confidence": 0.95, "status": "confirmed"},
                {"event_type": "round_win", "timestamp": 28.0, "confidence": 0.91, "status": "confirmed"},
            ],
            "detected_signals": [],
        }

        summary = summary_engine.summarize_candidate(
            candidate=candidate,
            video_metadata={"title": "Valorant Ranked Highlights", "uploader": "ProGamer"},
        )

        self.assertEqual(summary.game, "Valorant")
        self.assertEqual(summary.primary_event, "clutch")
        self.assertEqual(summary.gameplay_stats["clutches"], 1)
        self.assertEqual(summary.gameplay_stats["headshots"], 1)
        self.assertGreaterEqual(summary.gameplay_stats["kills"], 3)

        # Test Description Engine
        desc = desc_engine.generate_description(
            summary=summary,
            selected_title="INSANE 1v3 CLUTCH in VALORANT!",
            hashtags=["#Valorant", "#Shorts"],
            source_metadata={"title": "Valorant Ranked", "uploader": "ProGamer"},
        )
        self.assertIn("clutch", desc.lower())
        self.assertIn("valorant", desc.lower())

        # Test Hashtag Engine
        tags = tag_engine.generate_hashtags(summary)
        tag_str = " ".join(tags)
        self.assertIn("#ValorantClutch", tag_str)
        self.assertIn("#Clutch", tag_str)


if __name__ == "__main__":
    unittest.main()
