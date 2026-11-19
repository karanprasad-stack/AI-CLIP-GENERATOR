"""Visual Effects Renderer applying context-aware zoom, shake, and flash via FFmpeg NVENC."""

import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from backend.app.config import (
    VIDEO_BITRATE,
    NVENC_PRESET,
    CPU_PRESET,
    CPU_CRF,
    CPU_THREADS,
    AUDIO_CODEC,
    AUDIO_BITRATE,
    EFFECT_SUBTLE_ZOOM,
    EFFECT_PUNCH_ZOOM,
    EFFECT_IMPACT_ZOOM,
    EFFECT_MICRO_SHAKE,
    EFFECT_IMPACT_SHAKE,
    EFFECT_EMPHASIS_FLASH,
    SUBTLE_ZOOM_SCALE,
    PUNCH_ZOOM_SCALE,
    IMPACT_ZOOM_SCALE,
    MICRO_SHAKE_AMPLITUDE,
    MICRO_SHAKE_FREQ,
    IMPACT_SHAKE_AMPLITUDE,
    IMPACT_SHAKE_FREQ,
    FLASH_BRIGHTNESS,
)
from backend.app.pipeline.effect_engine import EffectEvent, EffectTimeline


class EffectRenderError(Exception):
    """Raised when visual effects rendering fails."""
    pass


class EffectRenderer:
    """Renders deterministic, context-aware visual effects onto captioned vertical Shorts."""

    def __init__(self, ffmpeg_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        self._nvenc_available = self._detect_nvenc()

    def _detect_nvenc(self) -> bool:
        """Check if h264_nvenc encoder is operational."""
        cmd = [
            self.ffmpeg_path,
            "-f", "lavfi",
            "-i", "testsrc=duration=0.1:size=256x256:rate=30",
            "-c:v", "h264_nvenc",
            "-f", "null",
            "-"
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    @property
    def nvenc_available(self) -> bool:
        return self._nvenc_available

    def build_filtergraph(
        self,
        effects: List[EffectEvent],
        source_fps: float = 60.0,
        focal_x: float = 0.50,
        focal_y: float = 0.50,
    ) -> Optional[str]:
        """
        Builds a combined, deterministic FFmpeg filtergraph for zoom, shake, and flash accents.
        Returns None if no effects are requested.
        """
        if not effects:
            return None

        zooms = [e for e in effects if e.type in [EFFECT_SUBTLE_ZOOM, EFFECT_PUNCH_ZOOM, EFFECT_IMPACT_ZOOM]]
        shakes = [e for e in effects if e.type in [EFFECT_MICRO_SHAKE, EFFECT_IMPACT_SHAKE]]
        flashes = [e for e in effects if e.type == EFFECT_EMPHASIS_FLASH]

        filters: List[str] = []

        # 1. Zoom Filter (via zoompan)
        if zooms:
            zoom_terms: List[str] = []
            for z in zooms:
                dur = z.duration()
                s0 = round(z.start, 3)
                s1 = round(z.end, 3)
                if z.type == EFFECT_IMPACT_ZOOM:
                    scale_delta = round(IMPACT_ZOOM_SCALE - 1.0, 3)
                elif z.type == EFFECT_PUNCH_ZOOM:
                    scale_delta = round(PUNCH_ZOOM_SCALE - 1.0, 3)
                else:
                    scale_delta = round(SUBTLE_ZOOM_SCALE - 1.0, 3)

                # Smooth half-sine bell curve
                term = f"{scale_delta}*sin(PI*(it-{s0})/{dur:.3f})*between(it,{s0},{s1})"
                zoom_terms.append(term)

            z_expr = "1.0+" + "+".join(zoom_terms)
            x_expr = f"max(0,min(iw-iw/zoom,(iw-iw/zoom)*{focal_x:.2f}))"
            y_expr = f"max(0,min(ih-ih/zoom,(ih-ih/zoom)*{focal_y:.2f}))"

            filters.append(
                f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s=1080x1920:fps={source_fps:.1f}"
            )

        # 2. Camera Shake Filter (via slight overscale + dynamic crop)
        if shakes:
            shake_x_terms: List[str] = []
            shake_y_terms: List[str] = []

            for s in shakes:
                s0 = round(s.start, 3)
                s1 = round(s.end, 3)
                if s.type == EFFECT_IMPACT_SHAKE:
                    amp = IMPACT_SHAKE_AMPLITUDE
                    freq = IMPACT_SHAKE_FREQ
                else:
                    amp = MICRO_SHAKE_AMPLITUDE
                    freq = MICRO_SHAKE_FREQ

                x_t = f"{amp}*sin(2*PI*{freq:.1f}*t)*between(t,{s0},{s1})"
                y_t = f"{amp}*cos(2*PI*{freq:.1f}*t)*between(t,{s0},{s1})"
                shake_x_terms.append(x_t)
                shake_y_terms.append(y_t)

            max_amp = max(
                IMPACT_SHAKE_AMPLITUDE if any(s.type == EFFECT_IMPACT_SHAKE for s in shakes) else MICRO_SHAKE_AMPLITUDE,
                4
            )
            pad = max_amp + 4  # Safe margin so no black borders appear
            scaled_w = 1080 + pad * 2
            scaled_h = 1920 + pad * 2

            crop_x = f"{pad}+" + "+".join(shake_x_terms)
            crop_y = f"{pad}+" + "+".join(shake_y_terms)

            filters.append(f"scale={scaled_w}:{scaled_h}")
            filters.append(f"crop=1080:1920:x='{crop_x}':y='{crop_y}'")

        # 3. Emphasis Flash Accent (via eq brightness)
        if flashes:
            flash_terms: List[str] = []
            for f in flashes:
                s0 = round(f.start, 3)
                s1 = round(f.end, 3)
                dur = f.duration()
                term = f"{FLASH_BRIGHTNESS:.2f}*sin(PI*(t-{s0})/{dur:.3f})*between(t,{s0},{s1})"
                flash_terms.append(term)

            b_expr = "+".join(flash_terms)
            filters.append(f"eq=brightness='{b_expr}'")

        filters.append("setsar=1")
        return ",".join(filters)

    def render_effects(
        self,
        input_video_path: Path,
        timeline: EffectTimeline,
        output_video_path: Path,
        source_fps: float = 60.0,
        facecam_info: Optional[Dict[str, Any]] = None,
        force_cpu: bool = False,
    ) -> Dict[str, Any]:
        """
        Renders context-aware visual effects onto the input video.
        Uses NVENC hardware acceleration with automated CPU fallback.
        """
        if not input_video_path.exists():
            raise EffectRenderError(f"Input video not found: {input_video_path}")

        output_video_path.parent.mkdir(parents=True, exist_ok=True)
        start_time = time.perf_counter()

        has_facecam = facecam_info and facecam_info.get("facecam_detected", False)
        # In facecam mode, top 35% is facecam, bottom 65% is gameplay, focal center is ~0.65
        focal_x = 0.50
        focal_y = 0.65 if has_facecam else 0.50

        filtergraph = self.build_filtergraph(
            effects=timeline.effects,
            source_fps=source_fps,
            focal_x=focal_x,
            focal_y=focal_y,
        )

        use_nvenc = self._nvenc_available and not force_cpu
        encoder = "h264_nvenc" if use_nvenc else "libx264"

        input_abs = str(input_video_path.resolve())
        output_abs = str(output_video_path.resolve())

        def _build_cmd(codec: str, audio_mode: str = "copy") -> list:
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-nostats",
                "-loglevel", "error",
                "-threads", str(CPU_THREADS),
                "-i", input_abs,
            ]
            if filtergraph:
                cmd.extend(["-vf", filtergraph])

            if codec == "h264_nvenc":
                cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-preset", NVENC_PRESET,
                    "-b:v", VIDEO_BITRATE,
                    "-pix_fmt", "yuv420p",
                ])
            else:
                cmd.extend([
                    "-c:v", "libx264",
                    "-crf", str(CPU_CRF),
                    "-preset", CPU_PRESET,
                    "-pix_fmt", "yuv420p",
                    "-threads", str(CPU_THREADS),
                ])

            if audio_mode == "copy":
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", AUDIO_CODEC, "-b:a", AUDIO_BITRATE])

            cmd.append(output_abs)
            return cmd

        cmd = _build_cmd(encoder, "copy")

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
            if res.returncode != 0:
                # If audio copy failed, try aac re-encode
                cmd = _build_cmd(encoder, "aac")
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)

            if res.returncode != 0 and use_nvenc:
                # Fallback to CPU libx264
                encoder = "libx264"
                cmd = _build_cmd(encoder, "copy")
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
                if res.returncode != 0:
                    cmd = _build_cmd(encoder, "aac")
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)

            if res.returncode != 0:
                raise EffectRenderError(f"FFmpeg effect render failed ({encoder}): {res.stderr}")

        except subprocess.TimeoutExpired as e:
            raise EffectRenderError(f"FFmpeg effect render timed out after 300s: {e}") from e
        except Exception as e:
            if not isinstance(e, EffectRenderError):
                raise EffectRenderError(f"Exception during effect rendering: {e}")
            raise

        render_time = round(time.perf_counter() - start_time, 2)
        file_size = output_video_path.stat().st_size if output_video_path.exists() else 0

        return {
            "output_video_path": str(output_video_path),
            "render_time_sec": render_time,
            "encoder": encoder,
            "file_size_bytes": file_size,
            "filtergraph": filtergraph,
            "status": "success",
        }
