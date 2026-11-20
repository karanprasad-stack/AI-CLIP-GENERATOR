"""Vertical 9:16 Shorts Renderer with NVENC acceleration and layout filters."""

import time
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from backend.app.config import (
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
    OUTPUT_FPS_FALLBACK,
    VIDEO_BITRATE,
    NVENC_PRESET,
    CPU_PRESET,
    CPU_CRF,
    CPU_THREADS,
    AUDIO_CODEC,
    AUDIO_BITRATE,
    LAYOUT_SMART_CROP,
    LAYOUT_BLURRED_BG,
    LAYOUT_FACECAM,
    VERTICAL_FOCAL_X,
    FACECAM_TOP_HEIGHT_RATIO,
    DEFAULT_ASPECT_RATIO,
    ASPECT_RATIO_1_1,
    DEFAULT_KILL_FEED_OVERLAY,
    KILL_FEED_PIP_WIDTH,
    KILL_FEED_PIP_MARGIN_X,
    KILL_FEED_PIP_MARGIN_Y,
    KILL_FEED_PIP_ALPHA,
    get_output_dimensions,
)


class RenderError(Exception):
    """Raised when 9:16 vertical rendering fails."""
    pass


class VerticalRenderer:
    """Renders 16:9 input clips into high quality 9:16 vertical Shorts."""

    def __init__(self, ffmpeg_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        self._nvenc_available = self._detect_nvenc()

    def _detect_nvenc(self) -> bool:
        """Check if h264_nvenc encoder is operational on this machine."""
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
        layout: str,
        facecam_region: Optional[Dict[str, float]] = None,
        focal_x: float = VERTICAL_FOCAL_X,
        output_width: int = OUTPUT_WIDTH,
        output_height: int = OUTPUT_HEIGHT,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        kill_feed_overlay: bool = False,
        kill_feed_roi: Optional[Tuple[float, float, float, float]] = None,
    ) -> str:
        """Construct the FFmpeg complex filtergraph for the selected layout and aspect ratio."""
        is_square = (aspect_ratio == ASPECT_RATIO_1_1) or (output_width == output_height)
        use_pip = bool(
            kill_feed_overlay
            and not is_square
            and (aspect_ratio == DEFAULT_ASPECT_RATIO or aspect_ratio == "9:16")
            and (layout == LAYOUT_SMART_CROP or layout == "smart_crop")
            and (kill_feed_roi is not None)
        )

        if layout == LAYOUT_SMART_CROP:
            if is_square:
                # 1:1 Square: center square crop from 16:9 gameplay
                return (
                    f"[0:v]crop=ih:ih:(iw-ih)*{focal_x}:0,"
                    f"scale={output_width}:{output_height},"
                    f"setsar=1[outv]"
                )
            if use_pip and kill_feed_roi:
                x1, y1, x2, y2 = kill_feed_roi
                rw = round(x2 - x1, 4)
                rh = round(y2 - y1, 4)
                rx = round(x1, 4)
                ry = round(y1, 4)
                return (
                    f"[0:v]split=2[main_src][kf_src];"
                    f"[main_src]crop=ih*9/16:ih:(iw-ih*9/16)*{focal_x}:0,"
                    f"scale={output_width}:{output_height},setsar=1[base];"
                    f"[kf_src]crop=iw*{rw}:ih*{rh}:iw*{rx}:ih*{ry},"
                    f"scale={KILL_FEED_PIP_WIDTH}:-2:flags=lanczos,"
                    f"format=rgba,colorchannelmixer=aa={KILL_FEED_PIP_ALPHA},"
                    f"pad=iw+6:ih+6:3:3:color=black@0.45[kf_pip];"
                    f"[base][kf_pip]overlay=W-w-{KILL_FEED_PIP_MARGIN_X}:{KILL_FEED_PIP_MARGIN_Y}:format=auto,"
                    f"format=yuv420p,setsar=1[outv]"
                )
            # 9:16 Vertical: Crop 9:16 window centered at focal_x and scale to 1080x1920
            return (
                f"[0:v]crop=ih*9/16:ih:(iw-ih*9/16)*{focal_x}:0,"
                f"scale={output_width}:{output_height},"
                f"setsar=1[outv]"
            )

        elif layout == LAYOUT_BLURRED_BG:
            # Foreground centered, background blurred & scaled to fill canvas
            return (
                f"[0:v]split=2[fg][bg];"
                f"[bg]scale=-1:{output_height},crop={output_width}:{output_height},"
                f"boxblur=20:5,eq=brightness=-0.08:contrast=0.95[bg_blurred];"
                f"[fg]scale={output_width}:-2[fg_scaled];"
                f"[bg_blurred][fg_scaled]overlay=0:({output_height}-overlay_h)/2,"
                f"setsar=1[outv]"
            )

        elif layout == LAYOUT_FACECAM:
            cam_h = int(output_height * FACECAM_TOP_HEIGHT_RATIO)
            game_h = output_height - cam_h

            if facecam_region:
                rx = facecam_region.get("x", 0.70)
                ry = facecam_region.get("y", 0.05)
                rw = facecam_region.get("width", 0.25)
                rh = facecam_region.get("height", 0.30)
                crop_cam = f"crop=iw*{rw}:ih*{rh}:iw*{rx}:ih*{ry}"
            else:
                # Default top-right quadrant if region unavailable
                crop_cam = "crop=iw*0.28:ih*0.35:iw*0.70:ih*0.05"

            if is_square:
                crop_game = f"crop=ih*{game_h}/{output_height}:ih:(iw-ih*{game_h}/{output_height})*{focal_x}:0"
            else:
                crop_game = f"crop=ih*9/16*{game_h}/{output_height}:ih:(iw-ih*9/16*{game_h}/{output_height})*{focal_x}:0"

            return (
                f"[0:v]{crop_cam},scale={output_width}:{cam_h}:force_original_aspect_ratio=increase,"
                f"crop={output_width}:{cam_h}[cam];"
                f"[0:v]{crop_game},"
                f"scale={output_width}:{game_h}[game];"
                f"[cam][game]vstack=inputs=2,setsar=1[outv]"
            )

        else:
            # Fallback to smart crop
            if is_square:
                return (
                    f"[0:v]crop=ih:ih:(iw-ih)*{focal_x}:0,"
                    f"scale={output_width}:{output_height},"
                    f"setsar=1[outv]"
                )
            if use_pip and kill_feed_roi:
                x1, y1, x2, y2 = kill_feed_roi
                rw = round(x2 - x1, 4)
                rh = round(y2 - y1, 4)
                rx = round(x1, 4)
                ry = round(y1, 4)
                return (
                    f"[0:v]split=2[main_src][kf_src];"
                    f"[main_src]crop=ih*9/16:ih:(iw-ih*9/16)*{focal_x}:0,"
                    f"scale={output_width}:{output_height},setsar=1[base];"
                    f"[kf_src]crop=iw*{rw}:ih*{rh}:iw*{rx}:ih*{ry},"
                    f"scale={KILL_FEED_PIP_WIDTH}:-2:flags=lanczos,"
                    f"format=rgba,colorchannelmixer=aa={KILL_FEED_PIP_ALPHA},"
                    f"pad=iw+6:ih+6:3:3:color=black@0.45[kf_pip];"
                    f"[base][kf_pip]overlay=W-w-{KILL_FEED_PIP_MARGIN_X}:{KILL_FEED_PIP_MARGIN_Y}:format=auto,"
                    f"format=yuv420p,setsar=1[outv]"
                )
            return (
                f"[0:v]crop=ih*9/16:ih:(iw-ih*9/16)*{focal_x}:0,"
                f"scale={output_width}:{output_height},"
                f"setsar=1[outv]"
            )

    def render_short(
        self,
        input_clip_path: Path,
        output_short_path: Path,
        layout: str = LAYOUT_SMART_CROP,
        facecam_region: Optional[Dict[str, float]] = None,
        source_fps: Optional[float] = None,
        force_cpu: bool = False,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        kill_feed_overlay: bool = False,
        kill_feed_roi: Optional[Tuple[float, float, float, float]] = None,
    ) -> Dict[str, Any]:
        """
        Render a Short from the input clip with selectable aspect ratio (9:16 or 1:1)
        and optional 9:16 kill-feed picture-in-picture (PIP) overlay.
        Preserves original audio and source FPS.
        """
        if not input_clip_path.exists():
            raise RenderError(f"Input clip does not exist: {input_clip_path}")

        output_short_path.parent.mkdir(parents=True, exist_ok=True)
        start_time = time.perf_counter()

        width, height = get_output_dimensions(aspect_ratio)

        filtergraph = self.build_filtergraph(
            layout=layout,
            facecam_region=facecam_region,
            output_width=width,
            output_height=height,
            aspect_ratio=aspect_ratio,
            kill_feed_overlay=kill_feed_overlay,
            kill_feed_roi=kill_feed_roi,
        )

        use_nvenc = self._nvenc_available and not force_cpu
        encoder = "h264_nvenc" if use_nvenc else "libx264"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-nostats",
            "-loglevel", "error",
            "-threads", str(CPU_THREADS),
            "-i", str(input_clip_path),
            "-filter_complex", filtergraph,
            "-map", "[outv]",
            "-map", "0:a?",
        ]

        if source_fps and source_fps > 0:
            cmd.extend(["-r", f"{source_fps:.3f}"])

        if use_nvenc:
            cmd.extend([
                "-c:v", "h264_nvenc",
                "-preset", NVENC_PRESET,
                "-b:v", VIDEO_BITRATE,
                "-pix_fmt", "yuv420p",
            ])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", CPU_PRESET,
                "-crf", str(CPU_CRF),
                "-threads", str(CPU_THREADS),
                "-pix_fmt", "yuv420p",
            ])

        cmd.extend([
            "-c:a", AUDIO_CODEC,
            "-b:a", AUDIO_BITRATE,
            "-movflags", "+faststart",
            str(output_short_path),
        ])

        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
            if proc.returncode != 0:
                # If NVENC failed unexpectedly, try CPU fallback once
                if use_nvenc:
                    print(f"NVENC failed ({proc.stderr[:100]}...). Falling back to libx264.")
                    return self.render_short(
                        input_clip_path=input_clip_path,
                        output_short_path=output_short_path,
                        layout=layout,
                        facecam_region=facecam_region,
                        source_fps=source_fps,
                        force_cpu=True,
                        aspect_ratio=aspect_ratio,
                        kill_feed_overlay=kill_feed_overlay,
                        kill_feed_roi=kill_feed_roi,
                    )
                raise RenderError(f"FFmpeg vertical render failed: {proc.stderr}")

            elapsed = round(time.perf_counter() - start_time, 2)

            if not output_short_path.exists() or output_short_path.stat().st_size == 0:
                raise RenderError(f"Rendered Short was not created or is 0 bytes: {output_short_path}")

            pip_applied = bool(
                kill_feed_overlay
                and kill_feed_roi is not None
                and aspect_ratio != ASPECT_RATIO_1_1
                and width != height
                and layout == LAYOUT_SMART_CROP
            )

            return {
                "short_clip_path": str(output_short_path),
                "layout": layout,
                "encoder": encoder,
                "rendering_time_sec": elapsed,
                "output_resolution": {
                    "width": width,
                    "height": height,
                },
                "fps": source_fps or OUTPUT_FPS_FALLBACK,
                "aspect_ratio": aspect_ratio,
                "kill_feed_overlay": pip_applied,
                "kill_feed_roi": list(kill_feed_roi) if kill_feed_roi else None,
            }

        except subprocess.TimeoutExpired as e:
            raise RenderError(f"FFmpeg vertical render timed out after 300s: {e}") from e
        except Exception as e:
            if isinstance(e, RenderError):
                raise
            raise RenderError(f"Unexpected error rendering vertical Short: {e}") from e
