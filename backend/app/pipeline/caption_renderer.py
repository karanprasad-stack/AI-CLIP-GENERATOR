"""Caption rendering engine burning karaoke ASS subtitles onto 9:16 vertical Shorts."""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional

from backend.app.config import (
    VIDEO_BITRATE,
    NVENC_PRESET,
    CPU_PRESET,
    CPU_CRF,
    CPU_THREADS,
    AUDIO_CODEC,
    AUDIO_BITRATE,
)


class CaptionRenderError(Exception):
    """Raised when caption burning or rendering fails."""
    pass


class CaptionRenderer:
    """Burns ASS subtitles onto vertical 9:16 Shorts with NVENC acceleration."""

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

    def render_captioned_short(
        self,
        short_video_path: Path,
        ass_path: Path,
        output_captioned_path: Path,
        force_cpu: bool = False,
    ) -> Dict[str, Any]:
        """
        Burns the ASS subtitle script onto the 9:16 short video.
        Uses NVENC hardware acceleration with automatic CPU fallback.
        """
        if not short_video_path.exists():
            raise CaptionRenderError(f"Input short video not found: {short_video_path}")
        if not ass_path.exists():
            raise CaptionRenderError(f"ASS subtitle file not found: {ass_path}")

        output_captioned_path.parent.mkdir(parents=True, exist_ok=True)
        start_time = time.perf_counter()

        use_nvenc = self._nvenc_available and not force_cpu
        encoder = "h264_nvenc" if use_nvenc else "libx264"

        # On Windows, path separators and drive colons in filter arguments trigger
        # FFmpeg option delimiter errors (e.g. 'D:/...' parses 'D' as an option).
        # We run FFmpeg with cwd set to the ASS file's directory and pass the simple filename.
        ass_dir = str(ass_path.parent.resolve())
        ass_filename = ass_path.name
        input_abs = str(short_video_path.resolve())
        output_abs = str(output_captioned_path.resolve())

        # Base filter syntax
        vf_filter = f"ass='{ass_filename}'"

        def _build_cmd(codec: str, audio_mode: str = "copy") -> list:
            c = [
                self.ffmpeg_path,
                "-y",
                "-nostats",
                "-loglevel", "error",
                "-threads", str(CPU_THREADS),
                "-i", input_abs,
                "-vf", vf_filter,
            ]
            if codec == "h264_nvenc":
                c.extend([
                    "-c:v", "h264_nvenc",
                    "-preset", NVENC_PRESET,
                    "-b:v", VIDEO_BITRATE,
                    "-pix_fmt", "yuv420p",
                ])
            else:
                c.extend([
                    "-c:v", "libx264",
                    "-crf", str(CPU_CRF),
                    "-preset", CPU_PRESET,
                    "-pix_fmt", "yuv420p",
                    "-threads", str(CPU_THREADS),
                ])

            if audio_mode == "copy":
                c.extend(["-c:a", "copy"])
            else:
                c.extend(["-c:a", AUDIO_CODEC, "-b:a", AUDIO_BITRATE])

            c.append(output_abs)
            return c

        cmd = _build_cmd(encoder, "copy")

        try:
            res = subprocess.run(cmd, cwd=ass_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
            if res.returncode != 0:
                # If audio copy failed, try re-encoding audio
                cmd = _build_cmd(encoder, "aac")
                res = subprocess.run(cmd, cwd=ass_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)

            if res.returncode != 0 and use_nvenc:
                # Fallback from NVENC to CPU
                encoder = "libx264"
                cmd = _build_cmd(encoder, "copy")
                res = subprocess.run(cmd, cwd=ass_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
                if res.returncode != 0:
                    cmd = _build_cmd(encoder, "aac")
                    res = subprocess.run(cmd, cwd=ass_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)

            if res.returncode != 0:
                raise CaptionRenderError(f"FFmpeg caption render failed ({encoder}): {res.stderr}")

        except subprocess.TimeoutExpired as e:
            raise CaptionRenderError(f"FFmpeg caption render timed out after 300s: {e}") from e
        except Exception as e:
            if not isinstance(e, CaptionRenderError):
                raise CaptionRenderError(f"Exception during caption rendering: {e}")
            raise

        render_time = round(time.perf_counter() - start_time, 2)
        file_size = output_captioned_path.stat().st_size if output_captioned_path.exists() else 0

        return {
            "captioned_video_path": str(output_captioned_path),
            "render_time_sec": render_time,
            "encoder": encoder,
            "file_size_bytes": file_size,
            "status": "success",
        }
