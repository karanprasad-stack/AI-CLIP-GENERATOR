"""Regression and calibration test suite for Phase 2.1.1 GameplayEventScore."""

import unittest
from pathlib import Path
from typing import Dict, Any, List

from backend.app.pipeline.candidate_ranker import CandidateRanker
from backend.app.pipeline.transcript_analyzer import TranscriptAnalyzer
from backend.app.pipeline.audio_analyzer import AudioAnalyzer


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


class TestGameplayEventScore(unittest.TestCase):
    def setUp(self):
        self.ranker = CandidateRanker()

    def test_a_gaming_event_causal_progression(self):
        """
        Test A: kill -> audio spike -> 'NO WAY!'
        Expected: strong gameplay event score (>=70) and causal progression sequence detected.
        """
        words = [
            {"word": "Watch", "start": 10.0, "end": 10.4},
            {"word": "me", "start": 10.5, "end": 10.8},
            {"word": "kill", "start": 11.0, "end": 11.5},  # Gaming word at 11.0s
            {"word": "this", "start": 11.6, "end": 11.9},
            {"word": "guy.", "start": 12.0, "end": 12.5},
            {"word": "Oh", "start": 14.0, "end": 14.3},
            {"word": "no", "start": 14.4, "end": 14.7},     # Reaction phrase 'no way' at 14.4s
            {"word": "way!", "start": 14.8, "end": 15.3},
        ]
        t_data = make_dummy_transcript(words)
        ta = TranscriptAnalyzer(t_data)

        # Audio peak at 12.5s (directly between 'kill' and 'no way')
        peaks = [{"timestamp": 12.5, "rms": 0.25, "z_score": 3.4}]
        aa = make_dummy_audio_analysis(40.0, peaks)

        score, metrics, reasons, breakdown = self.ranker.calculate_gameplay_event_score(
            start_sec=5.0, end_sec=35.0, audio_analysis=aa, transcript_analyzer=ta
        )

        self.assertGreaterEqual(score, 70.0, f"Expected strong event score >= 70, got {score}")
        self.assertGreaterEqual(breakdown["gaming_lexical"]["score"], 40.0)
        self.assertGreaterEqual(breakdown["reaction_lexical"]["score"], 35.0)
        self.assertGreaterEqual(breakdown["causal_progression"]["score"], 65.0)
        self.assertEqual(breakdown["signal_diversity"]["score"], 100.0)

    def test_b_loud_introduction_no_gaming_or_reaction(self):
        """
        Test B: Loud introduction with high speech density, but NO gameplay vocabulary and NO reaction.
        Expected: GameplayEventScore must NOT be artificially high (<= 45.0).
        """
        # Rapid speech about regular non-gaming topics
        words = []
        cur_t = 5.0
        sample_words = "welcome back everybody today we are discussing the latest update and how things work in the community".split()
        for w in sample_words:
            words.append({"word": w, "start": cur_t, "end": cur_t + 0.3})
            cur_t += 0.35

        t_data = make_dummy_transcript(words)
        ta = TranscriptAnalyzer(t_data)

        # Loud audio peak (speaker was loud in intro)
        peaks = [{"timestamp": 8.0, "rms": 0.22, "z_score": 2.8}]
        aa = make_dummy_audio_analysis(40.0, peaks)

        score, metrics, reasons, breakdown = self.ranker.calculate_gameplay_event_score(
            start_sec=0.0, end_sec=35.0, audio_analysis=aa, transcript_analyzer=ta
        )

        self.assertEqual(breakdown["gaming_lexical"]["score"], 0.0)
        self.assertEqual(breakdown["reaction_lexical"]["score"], 0.0)
        self.assertLessEqual(score, 45.0, f"Loud intro should not receive inflated gameplay score, got {score}")
        self.assertIn("No gaming vocabulary detected", breakdown["gaming_lexical"]["explanation"])

    def test_c_reaction_without_gaming_vocabulary(self):
        """
        Test C: 'WHAT?! NO WAY!' without gaming vocabulary.
        Expected: reaction score increases, but gaming lexical score is 0.0 and no fake gaming action is claimed.
        """
        words = [
            {"word": "Wait,", "start": 10.0, "end": 10.4},
            {"word": "what?!", "start": 10.5, "end": 11.0},
            {"word": "No", "start": 11.2, "end": 11.5},
            {"word": "way!", "start": 11.6, "end": 12.0},
        ]
        t_data = make_dummy_transcript(words)
        ta = TranscriptAnalyzer(t_data)

        peaks = [{"timestamp": 11.0, "rms": 0.20, "z_score": 2.5}]
        aa = make_dummy_audio_analysis(40.0, peaks)

        score, metrics, reasons, breakdown = self.ranker.calculate_gameplay_event_score(
            start_sec=5.0, end_sec=35.0, audio_analysis=aa, transcript_analyzer=ta
        )

        self.assertEqual(breakdown["gaming_lexical"]["score"], 0.0)
        self.assertGreaterEqual(breakdown["reaction_lexical"]["score"], 45.0)
        self.assertIn("No gaming vocabulary detected", breakdown["gaming_lexical"]["explanation"])
        self.assertIn("audio_peak", breakdown["signal_diversity"]["signals"])

    def test_d_gameplay_without_speech(self):
        """
        Test D: Pure audio gameplay event (huge explosion peak) without spoken reactions.
        Expected: scores positively on audio alignment and density, while reaction and gaming lexical are 0.
        """
        # Empty speech
        t_data = {"language": "en", "duration": 40.0, "segments": []}
        ta = TranscriptAnalyzer(t_data)

        # Huge explosion peak
        peaks = [
            {"timestamp": 15.0, "rms": 0.35, "z_score": 3.8},
            {"timestamp": 22.0, "rms": 0.28, "z_score": 3.1},
        ]
        aa = make_dummy_audio_analysis(40.0, peaks)

        score, metrics, reasons, breakdown = self.ranker.calculate_gameplay_event_score(
            start_sec=5.0, end_sec=35.0, audio_analysis=aa, transcript_analyzer=ta
        )

        self.assertEqual(breakdown["gaming_lexical"]["score"], 0.0)
        self.assertEqual(breakdown["reaction_lexical"]["score"], 0.0)
        self.assertGreater(breakdown["audio_event_alignment"]["score"], 40.0)
        self.assertIn("Audio peaks detected", breakdown["audio_event_alignment"]["explanation"])

    def test_e_determinism_and_score_consistency(self):
        """
        Test E: Determinism and Score Consistency.
        Multiple runs must produce exact identical timestamps, component scores, and final scores.
        Also asserts final_score == weighted sum of component_scores.
        """
        words = [
            {"word": "Enemy", "start": 10.0, "end": 10.5},
            {"word": "spotted.", "start": 10.6, "end": 11.0},
            {"word": "He's", "start": 11.2, "end": 11.5},
            {"word": "dead!", "start": 11.6, "end": 12.0},
            {"word": "Let's", "start": 12.2, "end": 12.5},
            {"word": "go!", "start": 12.6, "end": 13.0},
        ]
        t_data = make_dummy_transcript(words)
        ta = TranscriptAnalyzer(t_data)
        peaks = [{"timestamp": 11.8, "rms": 0.30, "z_score": 3.2}]
        aa = make_dummy_audio_analysis(45.0, peaks)

        cands = [(0.0, 40.0)]
        res1 = self.ranker.rank_candidates(cands, aa, ta, "test_det", 45.0)
        res2 = self.ranker.rank_candidates(cands, aa, ta, "test_det", 45.0)

        c1 = res1["candidates"][0]
        c2 = res2["candidates"][0]

        self.assertEqual(c1["final_score"], c2["final_score"])
        self.assertEqual(c1["component_scores"], c2["component_scores"])
        self.assertEqual(c1["gameplay_event_breakdown"], c2["gameplay_event_breakdown"])

        # Score consistency assertion: final_score == weighted sum of component_scores
        w = c1["active_weights"]
        comp = c1["component_scores"]
        expected = round(sum(w[k] * comp[k] for k in w), 1)
        self.assertAlmostEqual(c1["final_score"], expected, delta=0.15)


if __name__ == "__main__":
    unittest.main()
