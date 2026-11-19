"""CPU-based streaming audio analysis for energy, peak, variance, and silence detection."""

from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import soundfile as sf


class AudioAnalyzerError(Exception):
    """Raised when audio analysis fails."""
    pass


class AudioAnalyzer:
    """Performs streaming signal analysis on WAV audio files without exhausting system RAM."""

    def __init__(self, bucket_duration: float = 0.5):
        self.bucket_duration = bucket_duration  # 0.5s windows for fine temporal granularity

    def analyze(self, audio_path: Path) -> Dict[str, Any]:
        """
        Analyzes the audio file by reading blocks in a stream.
        Computes RMS energy, dynamic variance, moving Z-scores, and silence intervals.
        """
        if not audio_path.exists():
            raise AudioAnalyzerError(f"Audio file does not exist: {audio_path}")

        rms_values: List[float] = []
        timestamps: List[float] = []

        try:
            with sf.SoundFile(str(audio_path)) as f:
                sr = f.samplerate
                block_size = int(sr * self.bucket_duration)
                total_frames = len(f)
                duration = total_frames / sr
                time_cursor = 0.0

                while f.tell() < total_frames:
                    data = f.read(block_size, dtype="float32")
                    if len(data) == 0:
                        break

                    # Convert to mono if multichannel
                    if data.ndim > 1:
                        data = np.mean(data, axis=1)

                    rms = float(np.sqrt(np.mean(data ** 2) + 1e-12))
                    rms_values.append(rms)
                    timestamps.append(round(time_cursor, 2))
                    time_cursor += self.bucket_duration

        except Exception as e:
            raise AudioAnalyzerError(f"Error reading audio file {audio_path}: {e}") from e

        if not rms_values:
            return {
                "duration": 0.0,
                "global_mean_rms": 0.0,
                "global_std_rms": 0.0,
                "timeline": [],
                "peaks": [],
                "silence_intervals": [],
            }

        rms_arr = np.array(rms_values, dtype=np.float32)
        global_mean = float(np.mean(rms_arr))
        global_std = float(np.std(rms_arr)) + 1e-8

        # Compute moving baseline over 10-second windows (20 buckets of 0.5s)
        window_size = int(10.0 / self.bucket_duration)
        half_w = window_size // 2

        timeline: List[Dict[str, Any]] = []
        peaks: List[Dict[str, Any]] = []
        silence_intervals: List[Tuple[float, float]] = []

        current_silence_start = None
        silence_threshold = max(0.005, global_mean * 0.20)

        for idx, (t, rms_val) in enumerate(zip(timestamps, rms_values)):
            start_idx = max(0, idx - half_w)
            end_idx = min(len(rms_values), idx + half_w + 1)
            local_window = rms_arr[start_idx:end_idx]

            local_mean = float(np.mean(local_window))
            local_std = float(np.std(local_window)) + 1e-8
            z_score = float((rms_val - local_mean) / local_std)

            # Local peak detection: must be a local maximum within +- 2 buckets
            is_local_max = True
            left_bound = max(0, idx - 2)
            right_bound = min(len(rms_values), idx + 3)
            for neighbor_idx in range(left_bound, right_bound):
                if neighbor_idx != idx and rms_arr[neighbor_idx] > rms_val:
                    is_local_max = False
                    break

            is_peak = bool(is_local_max and z_score >= 1.8 and rms_val >= (global_mean * 1.3))
            is_silent = bool(rms_val <= silence_threshold)

            # Track silence regions
            if is_silent:
                if current_silence_start is None:
                    current_silence_start = t
            else:
                if current_silence_start is not None:
                    silence_dur = t - current_silence_start
                    if silence_dur >= 0.4:
                        silence_intervals.append((current_silence_start, t))
                    current_silence_start = None

            point = {
                "t": t,
                "rms": round(rms_val, 5),
                "z": round(z_score, 2),
                "is_peak": is_peak,
                "is_silent": is_silent,
            }
            timeline.append(point)

            if is_peak:
                peaks.append({
                    "timestamp": t,
                    "rms": round(rms_val, 5),
                    "z_score": round(z_score, 2),
                })

        # Close any open silence interval at the end
        if current_silence_start is not None and len(timestamps) > 0:
            silence_intervals.append((current_silence_start, timestamps[-1]))

        return {
            "duration": round(duration, 2),
            "global_mean_rms": round(global_mean, 5),
            "global_std_rms": round(global_std, 5),
            "timeline": timeline,
            "peaks": peaks,
            "silence_intervals": silence_intervals,
        }

    def score_interval(
        self,
        analysis: Dict[str, Any],
        start_sec: float,
        end_sec: float
    ) -> Tuple[float, Dict[str, Any], List[str]]:
        """
        Calculates normalized AudioEnergyScore (0-100) for a candidate interval [start_sec, end_sec].
        Returns: (score, metrics, reasons)
        """
        timeline = analysis.get("timeline", [])
        global_mean = analysis.get("global_mean_rms", 1e-4)

        buckets_in_range = [b for b in timeline if start_sec <= b["t"] <= end_sec]
        if not buckets_in_range:
            return 50.0, {"avg_rms": 0.0, "max_z": 0.0, "peak_count": 0}, ["insufficient audio data"]

        rms_in_range = [b["rms"] for b in buckets_in_range]
        z_in_range = [b["z"] for b in buckets_in_range]
        peak_buckets = [b for b in buckets_in_range if b["is_peak"]]
        silent_buckets = [b for b in buckets_in_range if b["is_silent"]]

        avg_rms = float(np.mean(rms_in_range))
        max_z = float(np.max(z_in_range)) if z_in_range else 0.0
        rms_variance = float(np.var(rms_in_range))
        silence_ratio = len(silent_buckets) / len(buckets_in_range)
        peak_count = len(peak_buckets)

        # 1. Energy level relative to global mean (0 - 35 pts)
        energy_ratio = avg_rms / (global_mean + 1e-8)
        energy_pts = min(35.0, energy_ratio * 20.0)

        # 2. Peak intensity score (0 - 35 pts)
        # Z-scores typically range 0 to 4+
        peak_pts = min(35.0, max(0.0, max_z * 8.5) + min(10.0, peak_count * 2.5))

        # 3. Dynamic variance score (0 - 20 pts)
        # Rewarding active dynamic range over steady hum or silence
        var_norm = min(1.0, rms_variance / (global_mean**2 + 1e-8))
        variance_pts = var_norm * 20.0

        # 4. Silence penalty / sustained engagement (0 - 10 pts)
        # Slight silence is natural, but >50% dead silence is heavily penalized
        silence_penalty = max(0.0, (silence_ratio - 0.25) * 20.0)
        sustained_pts = max(0.0, 10.0 - silence_penalty)

        final_audio_score = float(np.clip(energy_pts + peak_pts + variance_pts + sustained_pts, 0.0, 100.0))

        reasons = []
        if energy_ratio >= 1.25:
            reasons.append("elevated audio energy above average")
        if max_z >= 2.0:
            reasons.append(f"significant audio volume spike (Z={max_z:.1f})")
        if peak_count >= 2:
            reasons.append(f"multiple dynamic audio peaks ({peak_count} detected)")
        if variance_pts >= 12.0:
            reasons.append("high audio dynamic activity")
        if silence_ratio <= 0.15:
            reasons.append("continuous audio engagement with minimal dead air")

        metrics = {
            "avg_rms": round(avg_rms, 5),
            "max_z": round(max_z, 2),
            "peak_count": peak_count,
            "silence_ratio": round(silence_ratio, 3),
            "rms_variance": round(rms_variance, 6),
        }

        return round(final_audio_score, 1), metrics, reasons
