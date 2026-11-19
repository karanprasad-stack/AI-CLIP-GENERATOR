"""Audio Renderer: mixes SFX, automates speech ducking, normalizes loudness, and encodes polished AAC audio."""

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from backend.app.config import (
    TARGET_LUFS,
    TRUE_PEAK_LIMIT,
    LOUDNESS_LRA,
    AUDIO_BITRATE,
    AUDIO_CODEC,
)
from backend.app.pipeline.sfx_library import SfxLibrary
from backend.app.pipeline.audio_event_engine import AudioEvent, AudioTimeline
from backend.app.pipeline.ducking_engine import DuckingEngine


class AudioRenderError(Exception):
    """Raised when audio mixing or rendering fails."""
    pass


class AudioRenderer:
    """Renders final polished audio mix (SFX + ducking + loudness normalization + limiter) onto Shorts."""

    def __init__(
        self,
        ffmpeg_path: Optional[str] = None,
        sfx_library: Optional[SfxLibrary] = None,
        ducking_engine: Optional[DuckingEngine] = None,
    ):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        self.sfx_library = sfx_library or SfxLibrary()
        self.ducking_engine = ducking_engine or DuckingEngine()

    def build_audio_filtergraph(
        self,
        timeline: AudioTimeline,
        ducking_expr: str,
        active_sfx_inputs: List[Dict[str, Any]],
    ) -> str:
        """
        Constructs the complete FFmpeg audio filtergraph:
        [0:a] main -> ducking -> [main_ducked]
        [1:a] sfx0 -> adelay -> volume -> [sfx0]
        ...
        [main_ducked][sfx0]... -> amix -> loudnorm -> alimiter -> [outa]
        """
        filter_parts: List[str] = []

        # 1. Main audio speech ducking
        filter_parts.append(
            f"[0:a]volume=eval=frame:volume='{ducking_expr}',"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[main_ducked]"
        )

        mix_inputs = ["[main_ducked]"]

        # 2. SFX Delay, Volume, and Formatting
        for idx, sfx_item in enumerate(active_sfx_inputs):
            inp_index = idx + 1
            delay_ms = max(0, int(round(sfx_item["timestamp"] * 1000)))
            gain_db = sfx_item["gain_db"]
            out_label = f"sfx{idx}"

            filter_parts.append(
                f"[{inp_index}:a]adelay={delay_ms}:all=1,"
                f"volume={gain_db:.1f}dB,"
                f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[{out_label}]"
            )
            mix_inputs.append(f"[{out_label}]")

        # 3. Mixing and Loudness Normalization / Limiting
        total_inputs = len(mix_inputs)
        mix_str = "".join(mix_inputs)

        if total_inputs > 1:
            filter_parts.append(
                f"{mix_str}amix=inputs={total_inputs}:duration=first:normalize=0[mixed]"
            )
            stage_in = "[mixed]"
        else:
            stage_in = "[main_ducked]"

        # 4. EBU R128 Loudnorm + Brickwall Peak Limiter (Clipping Protection)
        filter_parts.append(
            f"{stage_in}loudnorm=I={TARGET_LUFS:.1f}:TP={TRUE_PEAK_LIMIT:.1f}:LRA={LOUDNESS_LRA:.1f}:print_format=json,"
            f"alimiter=limit={TRUE_PEAK_LIMIT:.1f}dB:attack=5:release=50:asc=1[outa]"
        )

        return ";".join(filter_parts)

    def render_audio(
        self,
        input_video_path: Path,
        timeline: AudioTimeline,
        ducking_summary: Dict[str, Any],
        output_video_path: Path,
    ) -> Dict[str, Any]:
        """
        Renders the final audio mix into the target video using lossless video stream copy.
        """
        if not input_video_path.exists():
            raise AudioRenderError(f"Input video not found: {input_video_path}")

        output_video_path.parent.mkdir(parents=True, exist_ok=True)
        start_time = time.perf_counter()

        # Resolve assets for audio events
        active_sfx: List[Dict[str, Any]] = []
        input_args: List[str] = [
            self.ffmpeg_path,
            "-y",
            "-nostats",
            "-loglevel", "info",  # Info level to capture loudnorm JSON
            "-i", str(input_video_path.resolve()),
        ]

        for ev in timeline.audio_events:
            asset_path = self.sfx_library.get_asset_path(ev.event_type, ev.intensity)
            if asset_path and asset_path.exists():
                input_args.extend(["-i", str(asset_path.resolve())])
                active_sfx.append({
                    "timestamp": ev.timestamp,
                    "event_type": ev.event_type,
                    "gain_db": ev.gain_db,
                    "asset_path": str(asset_path),
                })

        ducking_expr = self.ducking_engine.build_ffmpeg_volume_expression(ducking_summary)
        filtergraph = self.build_audio_filtergraph(
            timeline=timeline,
            ducking_expr=ducking_expr,
            active_sfx_inputs=active_sfx,
        )

        cmd = list(input_args)
        cmd.extend([
            "-filter_complex", filtergraph,
            "-map", "0:v",
            "-map", "[outa]",
            "-c:v", "copy",            # Lossless stream copy of 1080x1920 video
            "-c:a", AUDIO_CODEC,
            "-b:a", AUDIO_BITRATE,
            "-ar", "48000",
            "-shortest",
            str(output_video_path.resolve()),
        ])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
            if res.returncode != 0:
                raise AudioRenderError(f"FFmpeg audio render failed: {res.stderr}")

        except subprocess.TimeoutExpired as e:
            raise AudioRenderError(f"FFmpeg audio render timed out after 300s: {e}") from e
        except Exception as e:
            if not isinstance(e, AudioRenderError):
                raise AudioRenderError(f"Exception during audio render: {e}")
            raise

        render_time = round(time.perf_counter() - start_time, 2)
        file_size = output_video_path.stat().st_size if output_video_path.exists() else 0

        # Parse loudnorm metrics from stderr
        measured_lufs = TARGET_LUFS
        measured_tp = TRUE_PEAK_LIMIT
        try:
            # Find the JSON block printed by loudnorm
            m = re.findall(r'\{[^{}]*"output_i"[^{}]*\}', res.stderr)
            if m:
                loud_data = json.loads(m[-1])
                measured_lufs = float(loud_data.get("output_i", TARGET_LUFS))
                measured_tp = float(loud_data.get("output_tp", TRUE_PEAK_LIMIT))
        except Exception:
            pass

        return {
            "output_video_path": str(output_video_path),
            "render_time_sec": render_time,
            "file_size_bytes": file_size,
            "measured_lufs": measured_lufs,
            "measured_tp": measured_tp,
            "sfx_applied_count": len(active_sfx),
            "ducking_applied": ducking_summary.get("enabled", False),
            "status": "success",
        }
