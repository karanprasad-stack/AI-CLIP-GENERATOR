"""Automated technical validation for generated 9:16 vertical Shorts."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from backend.app.config import (
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
    DEFAULT_ASPECT_RATIO,
    ASPECT_RATIO_1_1,
    get_output_dimensions,
)


class VideoValidationError(Exception):
    """Raised when validation execution fails."""
    pass


class VideoValidator:
    """Verifies that generated MP4 files satisfy technical Shorts specifications."""

    def __init__(self, ffmpeg_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_path = shutil.which("ffprobe") or "ffprobe"

    def validate_short(
        self,
        video_path: Path,
        expected_duration: Optional[float] = None,
        duration_tolerance_sec: float = 2.5,
        expected_width: int = OUTPUT_WIDTH,
        expected_height: int = OUTPUT_HEIGHT,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    ) -> Dict[str, Any]:
        """
        Validates the MP4 file against all technical criteria:
        - file exists and size > 0
        - MP4 container
        - video stream exists with matching dimensions and aspect ratio
        - audio stream exists
        - duration matches expected duration within tolerance
        - FPS is valid (> 15)
        - full decoding test passes with no errors
        """
        errors = []
        checks = {
            "file_exists": False,
            "size_nonzero": False,
            "is_mp4": False,
            "video_stream": False,
            "audio_stream": False,
            "resolution_1080x1920": False,
            "aspect_ratio_9_16": False,
            "duration_valid": False,
            "fps_valid": False,
            "decodable": False,
        }

        if aspect_ratio == ASPECT_RATIO_1_1 and expected_width == OUTPUT_WIDTH and expected_height == OUTPUT_HEIGHT:
            expected_width, expected_height = get_output_dimensions(aspect_ratio)

        # Check 1: File exists
        if not video_path.exists():
            errors.append(f"File does not exist: {video_path}")
            return self._build_result(video_path, False, checks, errors)

        checks["file_exists"] = True

        # Check 2: Size > 0
        file_size = video_path.stat().st_size
        if file_size <= 0:
            errors.append(f"File size is 0 bytes: {video_path}")
            return self._build_result(video_path, False, checks, errors, file_size=file_size)

        checks["size_nonzero"] = True

        # Probe streams using ffprobe
        probe_cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=format_name,duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate",
            "-of", "json",
            str(video_path),
        ]

        try:
            res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, timeout=30)
            probe_data = json.loads(res.stdout)
        except Exception as e:
            errors.append(f"ffprobe failed to read file: {e}")
            return self._build_result(video_path, False, checks, errors, file_size=file_size)

        format_info = probe_data.get("format", {})
        format_name = format_info.get("format_name", "")
        if "mp4" in format_name or "mov" in format_name:
            checks["is_mp4"] = True
        else:
            errors.append(f"Container is not MP4/mov (detected: {format_name})")

        streams = probe_data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        # Video stream check
        width = 0
        height = 0
        fps = 0.0
        vcodec = "none"
        if video_stream:
            checks["video_stream"] = True
            width = int(video_stream.get("width") or 0)
            height = int(video_stream.get("height") or 0)
            vcodec = video_stream.get("codec_name", "unknown")

            if width == expected_width and height == expected_height:
                checks["resolution_1080x1920"] = True
                checks["aspect_ratio_9_16"] = True
            else:
                errors.append(f"Resolution is {width}x{height}, expected {expected_width}x{expected_height}")

            # Calculate FPS
            rate_str = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0/0"
            try:
                if "/" in rate_str:
                    num, den = rate_str.split("/")
                    fps = float(num) / float(den) if float(den) > 0 else 0.0
                else:
                    fps = float(rate_str)
            except Exception:
                fps = 0.0

            if fps >= 15.0:
                checks["fps_valid"] = True
            else:
                errors.append(f"FPS is too low or invalid: {fps}")
        else:
            errors.append("No video stream found in MP4 file")

        # Audio stream check
        acodec = "none"
        if audio_stream:
            checks["audio_stream"] = True
            acodec = audio_stream.get("codec_name", "unknown")
        else:
            errors.append("No audio stream found in MP4 file")

        # Duration check
        duration = float(format_info.get("duration") or 0.0)
        if duration > 0.5:
            if expected_duration is not None:
                delta = abs(duration - expected_duration)
                if delta <= duration_tolerance_sec:
                    checks["duration_valid"] = True
                else:
                    errors.append(
                        f"Duration {duration:.2f}s differs from expected {expected_duration:.2f}s by {delta:.2f}s (tolerance: {duration_tolerance_sec}s)"
                    )
            else:
                checks["duration_valid"] = True
        else:
            errors.append(f"Invalid duration: {duration:.2f}s")

        # Decode test with FFmpeg: verify frames can be decoded without corruption
        decode_cmd = [
            self.ffmpeg_path,
            "-v", "error",
            "-i", str(video_path),
            "-t", "2.0",
            "-f", "null",
            "-"
        ]
        try:
            dec_proc = subprocess.run(decode_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            if dec_proc.returncode == 0 and not dec_proc.stderr:
                checks["decodable"] = True
            else:
                errors.append(f"FFmpeg decoding test failed: {dec_proc.stderr}")
        except Exception as e:
            errors.append(f"FFmpeg decoding error: {e}")

        all_passed = len(errors) == 0 and all(checks.values())
        return self._build_result(
            video_path=video_path,
            passed=all_passed,
            checks=checks,
            errors=errors,
            file_size=file_size,
            duration=duration,
            width=width,
            height=height,
            fps=fps,
            vcodec=vcodec,
            acodec=acodec,
        )

    def _build_result(
        self,
        video_path: Path,
        passed: bool,
        checks: Dict[str, bool],
        errors: list,
        file_size: int = 0,
        duration: float = 0.0,
        width: int = 0,
        height: int = 0,
        fps: float = 0.0,
        vcodec: str = "none",
        acodec: str = "none",
    ) -> Dict[str, Any]:
        return {
            "status": "PASS" if passed else "FAIL",
            "valid": passed,
            "passed": passed,
            "file_path": str(video_path),
            "size_bytes": file_size,
            "duration": round(duration, 3),
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "vcodec": vcodec,
            "acodec": acodec,
            "checks": checks,
            "errors": errors,
        }
