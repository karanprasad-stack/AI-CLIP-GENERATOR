"""Local, royalty-free SFX Asset Library with deterministic synthesis fallback."""

import math
import struct
import wave
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np

from backend.app.config import (
    SFX_WHOOSH,
    SFX_MAJOR_IMPACT,
    SFX_MINOR_IMPACT,
    SFX_REACTION_ACCENT,
    SFX_TRANSITION,
)

# Standard SFX asset filenames in assets/sfx/
SFX_ASSET_NAMES = {
    "whoosh_soft": "whoosh_soft.wav",
    "whoosh_strong": "whoosh_strong.wav",
    "impact_soft": "impact_soft.wav",
    "impact_medium": "impact_medium.wav",
    "impact_strong": "impact_strong.wav",
    "pop": "pop.wav",
    "transition": "transition.wav",
}


def synthesize_wav_asset(asset_name: str, output_path: Path, sample_rate: int = 48000) -> Path:
    """
    Deterministically synthesizes clean, royalty-free procedural sound effects
    using mathematical wave generation. Ensures self-contained zero-dependency assets.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if asset_name == "whoosh_soft":
        # Smooth bandpass noise swoosh (duration: 0.35s)
        dur = 0.35
        n_samples = int(sample_rate * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        np.random.seed(42)
        noise = np.random.uniform(-0.5, 0.5, n_samples)
        # Center-weighted bell envelope
        envelope = np.sin(np.pi * (t / dur)) ** 2
        # Gentle frequency modulation via pitch sweep sine overlay
        sweep = 0.3 * np.sin(2 * np.pi * (250 + 400 * np.sin(np.pi * t / dur)) * t)
        signal = (noise * 0.7 + sweep) * envelope * 0.65

    elif asset_name == "whoosh_strong":
        # Dynamic high-energy whoosh (duration: 0.45s)
        dur = 0.45
        n_samples = int(sample_rate * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        np.random.seed(1337)
        noise = np.random.uniform(-0.6, 0.6, n_samples)
        envelope = np.sin(np.pi * (t / dur)) ** 1.8
        sweep = 0.45 * np.sin(2 * np.pi * (180 + 750 * (t / dur)) * t)
        signal = (noise * 0.65 + sweep) * envelope * 0.85

    elif asset_name == "impact_soft":
        # Soft low-frequency thump (duration: 0.35s)
        dur = 0.35
        n_samples = int(sample_rate * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        # Pitch drops 120Hz -> 45Hz
        freq = 120 * np.exp(-6.0 * t) + 45
        phase = 2 * np.pi * np.cumsum(freq) / sample_rate
        decay = np.exp(-10.0 * t)
        signal = np.sin(phase) * decay * 0.75

    elif asset_name == "impact_medium":
        # Punchy combat impact with click transient and sub bass (duration: 0.45s)
        dur = 0.45
        n_samples = int(sample_rate * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        freq = 160 * np.exp(-8.0 * t) + 40
        phase = 2 * np.pi * np.cumsum(freq) / sample_rate
        decay = np.exp(-7.5 * t)
        # Transient click at start
        click = np.sin(2 * np.pi * 800 * t) * np.exp(-60.0 * t) * 0.4
        signal = (np.sin(phase) * decay + click) * 0.85

    elif asset_name == "impact_strong":
        # Deep cinematic sub-bass punch (duration: 0.55s)
        dur = 0.55
        n_samples = int(sample_rate * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        freq = 190 * np.exp(-7.0 * t) + 35
        phase = 2 * np.pi * np.cumsum(freq) / sample_rate
        sub_phase = 2 * np.pi * 50 * t
        decay = np.exp(-5.5 * t)
        transient = np.sin(2 * np.pi * 1200 * t) * np.exp(-70.0 * t) * 0.5
        signal = (np.sin(phase) * 0.7 + np.sin(sub_phase) * 0.3 + transient) * decay * 0.95

    elif asset_name == "pop":
        # Clean subtle bubble/pop accent (duration: 0.08s)
        dur = 0.08
        n_samples = int(sample_rate * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        freq = 450 + 600 * (t / dur)
        phase = 2 * np.pi * np.cumsum(freq) / sample_rate
        decay = np.exp(-28.0 * t)
        signal = np.sin(phase) * decay * 0.70

    elif asset_name == "transition":
        # Shimmering riser accent (duration: 0.40s)
        dur = 0.40
        n_samples = int(sample_rate * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        freq = 300 + 700 * (t / dur) ** 2
        phase = 2 * np.pi * np.cumsum(freq) / sample_rate
        envelope = (t / dur) * (1.0 - (t / dur) ** 4) * 2.0
        signal = np.sin(phase) * envelope * 0.65

    else:
        # Generic neutral accent click
        dur = 0.10
        n_samples = int(sample_rate * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        signal = np.sin(2 * np.pi * 440 * t) * np.exp(-20.0 * t) * 0.5

    # Peak normalization to -1.0 dBFS
    max_amp = np.max(np.abs(signal))
    if max_amp > 1e-6:
        signal = (signal / max_amp) * 0.89  # -1.0 dBFS

    # Convert to 16-bit PCM stereo
    int16_mono = np.int16(signal * 32767)
    int16_stereo = np.column_stack((int16_mono, int16_mono))

    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(int16_stereo.tobytes())

    return output_path


class SfxLibrary:
    """Manages local SFX assets and provides graceful fallbacks for missing assets."""

    def __init__(self, sfx_dir: Optional[Path] = None):
        if sfx_dir:
            self.sfx_dir = Path(sfx_dir)
        else:
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.sfx_dir = project_root / "assets" / "sfx"

        self.sfx_dir.mkdir(parents=True, exist_ok=True)
        self.ensure_default_assets()

    def ensure_default_assets(self) -> None:
        """Verifies or synthesizes all standard default SFX assets."""
        for key, filename in SFX_ASSET_NAMES.items():
            target_path = self.sfx_dir / filename
            if not target_path.exists() or target_path.stat().st_size == 0:
                synthesize_wav_asset(key, target_path)

    def ensure_library_assets(self) -> Dict[str, Path]:
        """Verifies or synthesizes all standard default SFX assets and returns path mapping."""
        self.ensure_default_assets()
        return {k: self.sfx_dir / fname for k, fname in SFX_ASSET_NAMES.items()}

    def get_asset_path(self, sfx_type: str, intensity: float = 0.5) -> Optional[Path]:
        """
        Maps an audio event type and intensity to the best matching asset.
        Returns None if asset cannot be resolved or is missing.
        """
        key: Optional[str] = None

        if sfx_type == SFX_WHOOSH:
            key = "whoosh_strong" if intensity >= 0.72 else "whoosh_soft"
        elif sfx_type == SFX_MAJOR_IMPACT:
            key = "impact_strong"
        elif sfx_type == SFX_MINOR_IMPACT:
            key = "impact_medium" if intensity >= 0.55 else "impact_soft"
        elif sfx_type == SFX_REACTION_ACCENT:
            key = "pop"
        elif sfx_type == SFX_TRANSITION:
            key = "transition"

        if not key or key not in SFX_ASSET_NAMES:
            return None

        asset_file = self.sfx_dir / SFX_ASSET_NAMES[key]
        if asset_file.exists() and asset_file.stat().st_size > 0:
            return asset_file

        # Attempt on-the-fly regeneration
        try:
            synthesize_wav_asset(key, asset_file)
            return asset_file
        except Exception:
            return None

    def list_available_assets(self) -> Dict[str, str]:
        """Returns mapping of available asset keys to file paths."""
        available = {}
        for key, fname in SFX_ASSET_NAMES.items():
            p = self.sfx_dir / fname
            if p.exists() and p.stat().st_size > 0:
                available[key] = str(p)
        return available
