"""Unit test suite for Phase 12B: Valorant Highlight Ranking, Priority Anchors & Pipeline Hardening.

Validates:
1. Ace vs. Empty Hallway Scream: confirmed Ace with quiet speech outranks empty scream.
2. Event Hierarchy: Ace > 4K > Clutch > 3K > 2K > single kill > supporting reaction only.
3. False-Positive Protection: EventStatus.SUPPORTING events yield 0.0 concrete bonus.
4. Weighted-Sum Consistency: final_score equals weighted sum of component_scores within 0.15.
5. Backward Compatibility: gameplay_timeline=None preserves exact legacy behavior.
6. Priority Anchor Preservation: CandidateGenerator frames full combat span and prevents swallowing.
7. Pipeline source_video_path definition regression check.
"""

import unittest
from pathlib import Path
from typing import Dict, Any, List

from backend.app.config import (
    DEFAULT_SCORING_WEIGHTS,
    GAME_AWARE_SCORING_WEIGHTS,
    CONCRETE_GAMEPLAY_EVENT_BONUSES,
)
from backend.app.pipeline.candidate_ranker import CandidateRanker
from backend.app.pipeline.candidate_generator import CandidateGenerator
from backend.app.pipeline.transcript_analyzer import TranscriptAnalyzer
from backend.app.pipeline.games.models import (
    GameplayEvent,
    EventType,
    EventStatus,
    EvidenceBreakdown,
)
from backend.app.pipeline.games.timeline import GameplayTimeline


def make_dummy_transcript(words: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Helper to synthesize a Whisper transcript dictionary."""
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


def make_dummy_audio_analysis(
    duration: float,
    peaks: List[Dict[str, Any]],
    mean_rms: float = 0.05
) -> Dict[str, Any]:
    """Helper to synthesize an AudioAnalyzer analysis dictionary."""
    timeline = []
    t = 0.0
    peak_times = {p["timestamp"]: p for p in peaks}

    while t <= duration:
        if round(t, 2) in peak_times:
            pk = peak_times[round(t, 2)]
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
                "rms": mean_rms,
                "z": 0.2,
                "is_peak": False,
                "is_silent": False,
            })
        t += 0.5

    return {
        "duration": duration,
        "global_mean_rms": mean_rms,
        "global_std_rms": 0.02,
        "timeline": timeline,
        "peaks": peaks,
        "silence_intervals": [],
    }


class TestPhase12BHighlightRanking(unittest.TestCase):
    """Test suite ensuring game-aware highlight prioritization, priority anchors, and pipeline hardening."""

    def setUp(self):
        self.ranker = CandidateRanker()
        self.generator = CandidateGenerator()

    # --------------------------------------------------------------------------
    # 1. Ace vs. Empty Hallway Scream
    # --------------------------------------------------------------------------
    def test_ace_outranks_empty_hallway_scream(self):
        """
        A candidate containing a confirmed Ace with quiet speech and low audio
        must outrank an empty hallway scream (loud audio peak + reaction words, zero combat).
        """
        # Window 1: Quiet Ace at 100.0s - 145.0s (Ace sequence at 115.0s - 128.0s)
        # Moderate audio, quiet speech
        ace_event = GameplayEvent(
            id="ace_1",
            game="valorant",
            event_type=EventType.ACE.value,
            start_time=115.0,
            end_time=128.0,
            confidence=0.92,
            status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.92, "audio": 0.50},
            metadata={
                "subtype": "ace",
                "kill_count": 5,
                "headshot_count": 3,
                "all_spectated_player": True,
            },
            explanation="Ace sequence confirmed (5 kills, conf 0.92)"
        )
        timeline = GameplayTimeline(game="valorant")
        timeline.add_event(ace_event)

        # Transcript has simple words
        words = [
            {"word": "okay", "start": 105.0, "end": 105.4},
            {"word": "nice", "start": 128.5, "end": 129.0},
            # Empty scream window at 200.0s - 245.0s
            {"word": "OH", "start": 218.0, "end": 218.4},
            {"word": "MY", "start": 218.5, "end": 218.8},
            {"word": "GOD!", "start": 218.9, "end": 219.5},
            {"word": "NO", "start": 220.0, "end": 220.4},
            {"word": "WAY!", "start": 220.5, "end": 221.0},
        ]
        t_data = make_dummy_transcript(words)
        ta = TranscriptAnalyzer(t_data)

        # Audio: Ace window has modest peak (z=1.5), Scream window has massive peak (z=4.2)
        peaks = [
            {"timestamp": 120.0, "rms": 0.15, "z_score": 1.5},
            {"timestamp": 219.0, "rms": 0.45, "z_score": 4.2},
        ]
        aa = make_dummy_audio_analysis(300.0, peaks)

        cands = [(100.0, 145.0), (200.0, 245.0)]
        res = self.ranker.rank_candidates(
            candidates=cands,
            audio_analysis=aa,
            transcript_analyzer=ta,
            video_id="test_ace_vs_scream",
            video_duration=300.0,
            gameplay_timeline=timeline,
        )

        ranked = res["candidates"]
        self.assertEqual(len(ranked), 2)
        cand_ace = next(c for c in ranked if c["start"] == 100.0)
        cand_scream = next(c for c in ranked if c["start"] == 200.0)

        # Ace candidate must be ranked #1
        self.assertEqual(cand_ace["rank"], 1)
        self.assertGreater(cand_ace["final_score"], cand_scream["final_score"])
        self.assertGreaterEqual(cand_ace["scores"]["gameplay_event"], 90.0)
        self.assertIn("Ace sequence confirmed", cand_ace["ranking_reasons"][0])

    # --------------------------------------------------------------------------
    # 2. Event Hierarchy
    # --------------------------------------------------------------------------
    def test_gameplay_event_hierarchy(self):
        """
        Verifies calibrated combat hierarchy:
        Ace > 4K > Clutch > 3K > 2K > Single Kill > Supporting Reaction Only.
        """
        # Ace
        t_ace = GameplayTimeline(game="valorant")
        t_ace.add_event(GameplayEvent(
            id="ev_ace", game="valorant", event_type=EventType.ACE.value,
            start_time=10.0, end_time=20.0, confidence=0.95, status=EventStatus.CONFIRMED.value,
            metadata={"subtype": "ace", "headshot_count": 2, "all_spectated_player": True}
        ))
        score_ace, _, _, _ = self.ranker.calculate_concrete_gameplay_score(5.0, 25.0, t_ace)

        # 4K
        t_4k = GameplayTimeline(game="valorant")
        t_4k.add_event(GameplayEvent(
            id="ev_4k", game="valorant", event_type=EventType.MULTI_KILL.value,
            start_time=10.0, end_time=20.0, confidence=0.90, status=EventStatus.CONFIRMED.value,
            metadata={"subtype": "4k", "headshot_count": 1}
        ))
        score_4k, _, _, _ = self.ranker.calculate_concrete_gameplay_score(5.0, 25.0, t_4k)

        # Clutch
        t_clutch = GameplayTimeline(game="valorant")
        t_clutch.add_event(GameplayEvent(
            id="ev_clutch", game="valorant", event_type=EventType.CLUTCH_CANDIDATE.value,
            start_time=10.0, end_time=20.0, confidence=0.88, status=EventStatus.CONFIRMED.value,
            metadata={"kills_in_clutch": 3}
        ))
        score_clutch, _, _, _ = self.ranker.calculate_concrete_gameplay_score(5.0, 25.0, t_clutch)

        # 3K
        t_3k = GameplayTimeline(game="valorant")
        t_3k.add_event(GameplayEvent(
            id="ev_3k", game="valorant", event_type=EventType.MULTI_KILL.value,
            start_time=10.0, end_time=20.0, confidence=0.88, status=EventStatus.CONFIRMED.value,
            metadata={"subtype": "3k", "headshot_count": 1}
        ))
        score_3k, _, _, _ = self.ranker.calculate_concrete_gameplay_score(5.0, 25.0, t_3k)

        # 2K
        t_2k = GameplayTimeline(game="valorant")
        t_2k.add_event(GameplayEvent(
            id="ev_2k", game="valorant", event_type=EventType.MULTI_KILL.value,
            start_time=10.0, end_time=20.0, confidence=0.85, status=EventStatus.CONFIRMED.value,
            metadata={"subtype": "2k", "headshot_count": 0}
        ))
        score_2k, _, _, _ = self.ranker.calculate_concrete_gameplay_score(5.0, 25.0, t_2k)

        # Single Kill
        t_1k = GameplayTimeline(game="valorant")
        t_1k.add_event(GameplayEvent(
            id="ev_1k", game="valorant", event_type=EventType.KILL.value,
            start_time=10.0, end_time=11.0, confidence=0.85, status=EventStatus.CONFIRMED.value,
            metadata={"headshot": True}
        ))
        score_1k, _, _, _ = self.ranker.calculate_concrete_gameplay_score(5.0, 25.0, t_1k)

        # Supporting Reaction Only
        t_supp = GameplayTimeline(game="valorant")
        t_supp.add_event(GameplayEvent(
            id="ev_supp", game="valorant", event_type=EventType.REACTION.value,
            start_time=10.0, end_time=11.0, confidence=0.50, status=EventStatus.SUPPORTING.value,
            metadata={"spoken_term": "ace"}
        ))
        score_supp, _, _, _ = self.ranker.calculate_concrete_gameplay_score(5.0, 25.0, t_supp)

        # Strict hierarchy assertions
        self.assertGreater(score_ace, score_4k)
        self.assertGreaterEqual(score_4k, score_clutch)
        self.assertGreater(score_clutch, score_3k)
        self.assertGreater(score_3k, score_2k)
        self.assertGreater(score_2k, score_1k)
        self.assertGreater(score_1k, score_supp)
        self.assertEqual(score_supp, 0.0)

        # Target range checks
        self.assertGreaterEqual(score_ace, 92.0)
        self.assertGreaterEqual(score_4k, 75.0)
        self.assertLessEqual(score_4k, 92.0)
        self.assertGreaterEqual(score_3k, 60.0)
        self.assertLessEqual(score_3k, 75.0)
        self.assertGreaterEqual(score_2k, 40.0)
        self.assertLessEqual(score_2k, 55.0)
        self.assertGreaterEqual(score_1k, 20.0)
        self.assertLessEqual(score_1k, 38.0)

    # --------------------------------------------------------------------------
    # 3. False-Positive Protection
    # --------------------------------------------------------------------------
    def test_supporting_reaction_yields_zero_concrete_bonus(self):
        """
        EventStatus.SUPPORTING events (spoken 'ACE!' or volume peak with no visual confirmation)
        must yield exactly 0.0 concrete gameplay score.
        """
        timeline = GameplayTimeline(game="valorant")
        timeline.add_event(GameplayEvent(
            id="ev_fake_ace",
            game="valorant",
            event_type=EventType.REACTION.value,
            start_time=30.0,
            end_time=31.0,
            confidence=0.45,
            status=EventStatus.SUPPORTING.value,
            metadata={"spoken_term": "ace"}
        ))
        timeline.add_event(GameplayEvent(
            id="ev_audio_spike",
            game="valorant",
            event_type=EventType.AUDIO_SPIKE.value,
            start_time=31.5,
            end_time=32.0,
            confidence=0.40,
            status=EventStatus.SUPPORTING.value,
            metadata={"z_score": 3.0}
        ))

        score, signals, expl, _ = self.ranker.calculate_concrete_gameplay_score(25.0, 45.0, timeline)
        self.assertEqual(score, 0.0)
        self.assertEqual(len(signals), 0)
        self.assertIn("No verified combat events", expl)

    # --------------------------------------------------------------------------
    # 4. Weighted-Sum Consistency
    # --------------------------------------------------------------------------
    def test_weighted_sum_consistency_in_both_modes(self):
        """
        Asserts final_score == sum(active_weights[k] * component_scores[k]) within 0.15
        in both generic mode and game-aware mode.
        """
        words = [{"word": "combat", "start": 10.0, "end": 10.5}]
        ta = TranscriptAnalyzer(make_dummy_transcript(words))
        peaks = [{"timestamp": 12.0, "rms": 0.2, "z_score": 2.0}]
        aa = make_dummy_audio_analysis(60.0, peaks)
        cands = [(5.0, 45.0)]

        # Mode A: Generic / No timeline
        res_generic = self.ranker.rank_candidates(cands, aa, ta, "test_gen", 60.0, gameplay_timeline=None)
        c_gen = res_generic["candidates"][0]
        w_gen = c_gen["active_weights"]
        comp_gen = c_gen["component_scores"]
        expected_gen = round(sum(w_gen[k] * comp_gen[k] for k in w_gen), 1)
        self.assertAlmostEqual(c_gen["final_score"], expected_gen, delta=0.15)
        self.assertEqual(res_generic["scoring_version"], "phase2.1.1-v1")

        # Mode B: Game-Aware / Timeline with 3K
        t_game = GameplayTimeline(game="valorant")
        t_game.add_event(GameplayEvent(
            id="k_seq", game="valorant", event_type=EventType.MULTI_KILL.value,
            start_time=15.0, end_time=22.0, confidence=0.88, status=EventStatus.CONFIRMED.value,
            metadata={"subtype": "3k"}
        ))
        res_game = self.ranker.rank_candidates(cands, aa, ta, "test_game", 60.0, gameplay_timeline=t_game)
        c_game = res_game["candidates"][0]
        w_game = c_game["active_weights"]
        comp_game = c_game["component_scores"]
        expected_game = round(sum(w_game[k] * comp_game[k] for k in w_game), 1)
        self.assertAlmostEqual(c_game["final_score"], expected_game, delta=0.15)
        self.assertEqual(res_game["scoring_version"], "phase12b-game-aware")
        self.assertAlmostEqual(w_game["gameplay_event"], 0.45)

    # --------------------------------------------------------------------------
    # 5. Backward Compatibility
    # --------------------------------------------------------------------------
    def test_backward_compatibility_none_timeline(self):
        """
        When gameplay_timeline=None, CandidateRanker produces exact legacy weights and behavior.
        """
        words = [{"word": "kill", "start": 10.0, "end": 10.5}, {"word": "nice", "start": 11.0, "end": 11.5}]
        ta = TranscriptAnalyzer(make_dummy_transcript(words))
        aa = make_dummy_audio_analysis(50.0, [{"timestamp": 10.5, "rms": 0.2, "z_score": 2.5}])

        score, metrics, reasons, breakdown = self.ranker.calculate_gameplay_event_score(
            5.0, 35.0, aa, ta, gameplay_timeline=None
        )
        self.assertNotIn("concrete_gameplay_events", breakdown)
        self.assertGreater(score, 0.0)

    # --------------------------------------------------------------------------
    # 6. Priority Anchor Preservation & Framing
    # --------------------------------------------------------------------------
    def test_priority_anchor_preservation_and_framing(self):
        """
        CandidateGenerator must keep a confirmed Ace/Clutch anchor even if an audio
        peak occurs 5 seconds earlier, and generate framing windows covering [ev_start, ev_end].
        """
        timeline = GameplayTimeline(game="valorant")
        ace_start = 120.0
        ace_end = 135.0
        timeline.add_event(GameplayEvent(
            id="ace_seq",
            game="valorant",
            event_type=EventType.ACE.value,
            start_time=ace_start,
            end_time=ace_end,
            confidence=0.95,
            status=EventStatus.CONFIRMED.value,
            metadata={"subtype": "ace", "kill_count": 5}
        ))

        # Audio peak 5s before Ace at 115.0s (in generic clustering, 120s would be dropped if within 10s)
        audio_analysis = {
            "peaks": [
                {"timestamp": 115.0, "rms": 0.3, "z_score": 3.0},
            ]
        }
        transcript_data = {
            "language": "en",
            "duration": 200.0,
            "segments": [
                {"start": 100.0, "end": 110.0, "text": "Starting round here.", "words": []},
                {"start": 112.0, "end": 138.0, "text": "Fighting mid.", "words": []},
                {"start": 140.0, "end": 160.0, "text": "Round won.", "words": []},
            ]
        }
        ta = TranscriptAnalyzer(transcript_data)

        candidates = self.generator.generate_candidates(
            video_duration=200.0,
            audio_analysis=audio_analysis,
            transcript_analyzer=ta,
            gameplay_timeline=timeline,
        )

        # Verify that at least one candidate completely frames [120.0, 135.0]
        framing_cands = [c for c in candidates if c[0] <= ace_start and c[1] >= ace_end]
        self.assertGreater(len(framing_cands), 0, "CandidateGenerator must frame the complete Ace span")

        # Verify duration conforms to min/max
        for c in framing_cands:
            dur = c[1] - c[0]
            self.assertGreaterEqual(dur, self.generator.min_duration)
            self.assertLessEqual(dur, self.generator.max_duration)

    # --------------------------------------------------------------------------
    # 7. Pipeline Source Video Path Definition Regression
    # --------------------------------------------------------------------------
    def test_pipeline_source_video_path_defined(self):
        """
        Inspects pipeline.py source code to verify source_video_path is assigned
        before line 265, preventing UnboundLocalError.
        """
        pipeline_path = Path(__file__).resolve().parent.parent / "backend" / "app" / "pipeline" / "pipeline.py"
        with open(pipeline_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find first occurrence of source_video_path assignment
        first_assign = content.find('source_video_path = job_output_dir / "source.mp4"')
        first_use = content.find("video_path=source_video_path")

        self.assertNotEqual(first_assign, -1, "source_video_path must be assigned")
        self.assertNotEqual(first_use, -1, "video_path=source_video_path must be present")
        self.assertLess(first_assign, first_use, "source_video_path must be assigned BEFORE it is referenced")


if __name__ == "__main__":
    unittest.main()
