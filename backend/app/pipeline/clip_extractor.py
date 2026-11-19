"""Deterministic candidate clip extraction using FFmpeg."""

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from backend.app.config import (
    PRE_ROLL_SECONDS,
    POST_ROLL_SECONDS,
    AUDIO_CODEC,
    AUDIO_BITRATE,
    CPU_THREADS,
)


class ClipExtractionError(Exception):
    """Raised when candidate clip extraction fails."""
    pass


class ClipExtractor:
    """Extracts candidate sub-clips from the main source video with pre/post-roll padding."""

    def __init__(self, ffmpeg_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        self._nvenc_available = self._detect_nvenc()

    def _detect_nvenc(self) -> bool:
        """Check if h264_nvenc is available and functional on the current system."""
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

    def extract_candidate(
        self,
        source_path: Path,
        output_clip_path: Path,
        candidate_start: float,
        candidate_end: float,
        pre_roll: float = PRE_ROLL_SECONDS,
        post_roll: float = POST_ROLL_SECONDS,
        source_duration: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Extract candidate clip with padding clamped to source duration boundaries.
        Uses frame-accurate encoding (-ss before -i with NVENC or libx264) to ensure
        the output media starts precisely at extraction_start (0.0s relative).
        Stream copy (-c copy) is intentionally avoided because it snaps to preceding
        keyframes, causing timing desynchronization between speech audio and subtitles.
        """
        if not source_path.exists():
            raise ClipExtractionError(f"Source video not found: {source_path}")

        # Compute extraction bounds with clamping
        extraction_start = max(0.0, candidate_start - pre_roll)
        if source_duration and source_duration > 0:
            extraction_end = min(source_duration, candidate_end + post_roll)
        else:
            extraction_end = candidate_end + post_roll

        clip_duration = max(0.1, extraction_end - extraction_start)
        output_clip_path.parent.mkdir(parents=True, exist_ok=True)

        # Frame-accurate extraction with precise input seeking and re-encoding
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-nostats",
            "-loglevel", "error",
            "-ss", f"{extraction_start:.3f}",
            "-i", str(source_path),
            "-t", f"{clip_duration:.3f}",
        ]

        if self._nvenc_available:
            cmd.extend([
                "-c:v", "h264_nvenc",
                "-preset", "p5",
                "-b:v", "6M",
                "-pix_fmt", "yuv420p",
            ])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-threads", str(CPU_THREADS),
                "-pix_fmt", "yuv420p",
            ])

        cmd.extend([
            "-c:a", AUDIO_CODEC,
            "-b:a", AUDIO_BITRATE,
            "-movflags", "+faststart",
            str(output_clip_path),
        ])

        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
            if proc.returncode != 0:
                raise ClipExtractionError(
                    f"FFmpeg clip extraction failed for {output_clip_path.name}: {proc.stderr}"
                )

            if not output_clip_path.exists() or output_clip_path.stat().st_size == 0:
                raise ClipExtractionError(
                    f"Output clip was not created or is empty: {output_clip_path}"
                )

            return {
                "source_clip_path": str(output_clip_path),
                "candidate_start": round(candidate_start, 3),
                "candidate_end": round(candidate_end, 3),
                "candidate_duration": round(candidate_end - candidate_start, 3),
                "extraction_start": round(extraction_start, 3),
                "extraction_end": round(extraction_end, 3),
                "extraction_duration": round(clip_duration, 3),
                "encoder_used": "h264_nvenc" if self._nvenc_available else "libx264",
            }
        except subprocess.TimeoutExpired as e:
            raise ClipExtractionError(f"FFmpeg clip extraction timed out after 180s: {e}") from e
        except Exception as e:
            if isinstance(e, ClipExtractionError):
                raise
            raise ClipExtractionError(f"Unexpected error extracting clip: {e}") from e
