"""Unit tests for EffectRenderer: filtergraph construction, zoompan syntax, and hardware probe."""

import unittest
from backend.app.config import (
    EFFECT_SUBTLE_ZOOM,
    EFFECT_PUNCH_ZOOM,
    EFFECT_IMPACT_ZOOM,
    EFFECT_MICRO_SHAKE,
    EFFECT_IMPACT_SHAKE,
    EFFECT_EMPHASIS_FLASH,
)
from backend.app.pipeline.effect_engine import EffectEvent
from backend.app.pipeline.effect_renderer import EffectRenderer


class TestEffectRenderer(unittest.TestCase):
    def setUp(self):
        self.renderer = EffectRenderer()

    def test_zoom_filtergraph_syntax(self):
        """Zoompan filtergraph includes smooth sinusoidal curve and 1080x1920 target."""
        eff = [
            EffectEvent(
                type=EFFECT_PUNCH_ZOOM,
                start=2.0,
                end=2.6,
                intensity=0.75,
                confidence=0.85,
                reason="punch",
                source_events=["clutch"],
            )
        ]
        fg = self.renderer.build_filtergraph(eff, source_fps=60.0, focal_x=0.5, focal_y=0.5)
        self.assertIsNotNone(fg)
        self.assertIn("zoompan=z=", fg)
        self.assertIn("s=1080x1920", fg)
        self.assertIn("fps=60.0", fg)
        self.assertIn("d=1", fg)
        self.assertIn("between(it,2.0,2.6)", fg)
        self.assertIn("setsar=1", fg)

    def test_shake_filtergraph_syntax(self):
        """Camera shake uses overscale + dynamic crop with sinusoidal oscillation."""
        eff = [
            EffectEvent(
                type=EFFECT_MICRO_SHAKE,
                start=5.0,
                end=5.5,
                intensity=0.65,
                confidence=0.80,
                reason="shake",
                source_events=["audio_peak"],
            )
        ]
        fg = self.renderer.build_filtergraph(eff, source_fps=60.0)
        self.assertIsNotNone(fg)
        self.assertIn("scale=", fg)
        self.assertIn("crop=1080:1920:", fg)
        self.assertIn("sin(2*PI*14.0*t)", fg)
        self.assertIn("between(t,5.0,5.5)", fg)

    def test_flash_filtergraph_syntax(self):
        """Emphasis flash applies eq brightness accent."""
        eff = [
            EffectEvent(
                type=EFFECT_EMPHASIS_FLASH,
                start=8.0,
                end=8.15,
                intensity=0.90,
                confidence=0.92,
                reason="flash",
                source_events=["kill"],
            )
        ]
        fg = self.renderer.build_filtergraph(eff, source_fps=60.0)
        self.assertIsNotNone(fg)
        self.assertIn("eq=brightness=", fg)
        self.assertIn("between(t,8.0,8.15)", fg)

    def test_facecam_focal_preservation(self):
        """In facecam mode, zoompan vertical anchor shifts to preserve gameplay area."""
        eff = [EffectEvent(type=EFFECT_SUBTLE_ZOOM, start=1.0, end=1.8, intensity=0.5, confidence=0.6, reason="", source_events=[])]
        fg = self.renderer.build_filtergraph(eff, source_fps=60.0, focal_y=0.65)
        self.assertIn("0.65", fg)

    def test_empty_effects_returns_none(self):
        """Empty effect list produces None filtergraph."""
        fg = self.renderer.build_filtergraph([])
        self.assertIsNone(fg)


if __name__ == "__main__":
    unittest.main()
