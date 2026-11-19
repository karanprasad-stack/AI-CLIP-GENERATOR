"""Unit tests for EffectEngine: impact scoring, event clustering, cooldowns, and timeline generation."""

import unittest
from backend.app.config import (
    EFFECT_SUBTLE_ZOOM,
    EFFECT_PUNCH_ZOOM,
    EFFECT_IMPACT_ZOOM,
    EFFECT_MICRO_SHAKE,
    EFFECT_IMPACT_SHAKE,
    EFFECT_EMPHASIS_FLASH,
)
from backend.app.pipeline.effect_engine import EffectEngine, EffectEvent


class TestEffectEngine(unittest.TestCase):
    def setUp(self):
        self.engine = EffectEngine()

    def test_a_high_confidence_clutch_event(self):
        """Test A: High-confidence clutch event triggers punch_zoom or impact_zoom."""
        gp = [{"signal": "clutch", "time": 10.0}]
        ap = [{"z": 2.2, "time": 10.2}]
        rx = [{"type": "phrase", "text": "let's go", "time": 10.3}]

        impact, conf, breakdown = self.engine.calculate_impact(gp, ap, rx, anchor_timestamp=10.0)
        self.assertGreaterEqual(impact, 0.70)
        self.assertGreaterEqual(conf, 0.85)

        cand = {
            "candidate_start": 0.0,
            "candidate_end": 30.0,
            "extraction_duration": 30.0,
            "detected_signals": ["clutch@10.0s", "phrase:let's go@10.3s"],
        }
        audio_peaks = [{"timestamp": 10.2, "z_score": 2.2}]
        tl = self.engine.generate_timeline(1, cand, audio_peaks=audio_peaks)
        zoom_effects = [e for e in tl.effects if "zoom" in e.type]
        self.assertGreaterEqual(len(zoom_effects), 1)
        self.assertIn(zoom_effects[0].type, [EFFECT_PUNCH_ZOOM, EFFECT_IMPACT_ZOOM])

    def test_b_very_high_impact_event(self):
        """Test B: Maximum impact event triggers impact_zoom + impact_shake."""
        gp = [{"signal": "clutch", "time": 15.0}, {"signal": "headshot", "time": 15.1}]
        ap = [{"z": 2.8, "time": 15.1}]
        rx = [{"type": "phrase", "text": "oh my god", "time": 15.2}]

        impact, conf, breakdown = self.engine.calculate_impact(gp, ap, rx, anchor_timestamp=15.1)
        self.assertGreaterEqual(impact, 0.85)
        self.assertGreaterEqual(conf, 0.90)

        cand = {
            "candidate_start": 0.0,
            "candidate_end": 30.0,
            "extraction_duration": 30.0,
            "detected_signals": ["clutch@15.0s", "headshot@15.1s", "phrase:oh my god@15.2s"],
        }
        audio_peaks = [{"timestamp": 15.1, "z_score": 2.8}]
        tl = self.engine.generate_timeline(1, cand, audio_peaks=audio_peaks)
        types = [e.type for e in tl.effects]
        self.assertIn(EFFECT_IMPACT_ZOOM, types)
        self.assertIn(EFFECT_IMPACT_SHAKE, types)

    def test_c_medium_event(self):
        """Test C: Moderate reaction or combat event triggers subtle_zoom."""
        gp = [{"signal": "defuse", "time": 8.0}]
        ap = []
        rx = [{"type": "word", "text": "look", "time": 8.3}]

        impact, conf, breakdown = self.engine.calculate_impact(gp, ap, rx, anchor_timestamp=8.0)
        self.assertGreaterEqual(impact, 0.50)
        self.assertLess(impact, 0.70)

        cand = {
            "candidate_start": 0.0,
            "candidate_end": 20.0,
            "extraction_duration": 20.0,
            "detected_signals": ["defuse@8.0s", "word:look@8.3s"],
        }
        tl = self.engine.generate_timeline(1, cand)
        types = [e.type for e in tl.effects]
        self.assertIn(EFFECT_SUBTLE_ZOOM, types)
        self.assertNotIn(EFFECT_IMPACT_ZOOM, types)

    def test_d_low_confidence_event(self):
        """Test D: Ambient speech without gaming action or audio spike triggers no effect."""
        cand = {
            "candidate_start": 0.0,
            "candidate_end": 20.0,
            "extraction_duration": 20.0,
            "detected_signals": [],
        }
        tl = self.engine.generate_timeline(1, cand)
        self.assertEqual(len(tl.effects), 0)

    def test_e_cooldown_and_merging(self):
        """Test E: Two zoom events closer than min_zoom_gap (1.2s) enforce cooldown."""
        raw = [
            EffectEvent(
                type=EFFECT_SUBTLE_ZOOM,
                start=5.0,
                end=5.8,
                intensity=0.55,
                confidence=0.60,
                reason="test1",
                source_events=["gameplay"],
            ),
            EffectEvent(
                type=EFFECT_PUNCH_ZOOM,
                start=6.1,  # 0.3s after first ends (< 1.2s gap)
                end=6.7,
                intensity=0.75,
                confidence=0.85,
                reason="test2",
                source_events=["clutch"],
            ),
        ]
        accepted, suppressed = self.engine.resolve_conflicts_and_cooldowns(raw, clip_duration=20.0)
        # Should keep the higher priority punch_zoom and suppress subtle_zoom
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].type, EFFECT_PUNCH_ZOOM)
        self.assertEqual(len(suppressed), 1)

    def test_f_multi_signal_alignment_boost(self):
        """Test F: Coincident audio spike + gameplay event + reaction phrase boosts impact score."""
        gp_alone = [{"signal": "shot", "time": 10.0}]
        impact_solo, _, _ = self.engine.calculate_impact(gp_alone, [], [], anchor_timestamp=10.0)

        # Multi-signal
        ap = [{"z": 2.4, "time": 10.1}]
        rx = [{"type": "phrase", "text": "talk about timing", "time": 10.2}]
        impact_combined, conf_comb, _ = self.engine.calculate_impact(gp_alone, ap, rx, anchor_timestamp=10.0)

        self.assertGreater(impact_combined, impact_solo)
        self.assertGreaterEqual(conf_comb, 0.85)

    def test_g_variable_duration_180s_timeline(self):
        """Test G: 180-second extended clip generates prioritized effects without flooding."""
        signals = [
            f"kill@{t:.1f}s" for t in [10.0, 50.0, 90.0, 140.0, 175.0]
        ]
        cand = {
            "candidate_start": 0.0,
            "candidate_end": 180.0,
            "extraction_duration": 180.0,
            "detected_signals": signals,
        }
        tl = self.engine.generate_timeline(1, cand)
        self.assertGreater(len(tl.effects), 0)
        self.assertLessEqual(len(tl.effects), 12)  # Controlled density, not 50 effects
        self.assertLessEqual(tl.effects[-1].end, 180.0)

    def test_h_conflict_resolution_priority(self):
        """Test H: Simultaneous overlapping zoom hierarchy resolves cleanly."""
        raw = [
            EffectEvent(type=EFFECT_SUBTLE_ZOOM, start=12.0, end=12.8, intensity=0.6, confidence=0.6, reason="", source_events=[]),
            EffectEvent(type=EFFECT_IMPACT_ZOOM, start=12.2, end=12.6, intensity=0.9, confidence=0.9, reason="", source_events=[]),
        ]
        accepted, suppressed = self.engine.resolve_conflicts_and_cooldowns(raw, clip_duration=30.0)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].type, EFFECT_IMPACT_ZOOM)


if __name__ == "__main__":
    unittest.main()
