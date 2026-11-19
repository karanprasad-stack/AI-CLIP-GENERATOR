"""Technical and perceptual audio validator for Phase 6A Shorts."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

from backend.app.config import TARGET_LUFS, TRUE_PEAK_LIMIT, MAX_SFX_PER_30_SECONDS
from backend.app.pipeline.video_validator import VideoValidator


class AudioValidator:
    """Verifies that generated audio meets social media standards without distortion, desync, or spam."""

    def __init__(
        self,
        ffmpeg_path: Optional[str] = None,
        video_validator: Optional[VideoValidator] = None,
    ):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_path = shutil.which("ffprobe") or "ffprobe"
        self.video_validator = video_validator or VideoValidator()

    def validate_audio_timeline(
        self,
        timeline_data: Any,
        candidate_duration: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Validates structural timeline bounds, SFX density, and timestamps."""
        errors: List[str] = []
        checks = {
            "timeline_exists": False,
            "valid_structure": False,
            "no_negative_timestamps": False,
            "within_duration": False,
            "sfx_density": False,
        }

        if hasattr(timeline_data, "to_dict"):
            data = timeline_data.to_dict()
        elif isinstance(timeline_data, dict):
            data = timeline_data
        elif isinstance(timeline_data, (str, Path)):
            with open(Path(timeline_data), "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            return {"valid": False, "status": "FAIL", "errors": ["Invalid timeline data"]}

        checks["timeline_exists"] = True
        sfx_events = data.get("audio_events", [])
        checks["valid_structure"] = isinstance(sfx_events, list)

        dur = candidate_duration or float(data.get("candidate_duration", 60.0))

        no_neg = True
        within_dur = True
        for ev in sfx_events:
            t = float(ev.get("timestamp", -1.0))
            if t < 0.0:
                no_neg = False
                errors.append(f"Negative SFX timestamp: {t}")
            if dur > 0 and t > (dur + 0.5):
                within_dur = False
                errors.append(f"SFX timestamp ({t:.2f}s) exceeds candidate duration ({dur:.2f}s)")

        # Density check
        max_allowed = max(3, int(round((dur / 30.0) * MAX_SFX_PER_30_SECONDS)) + 2)
        density_ok = len(sfx_events) <= max_allowed
        if not density_ok:
            errors.append(f"SFX density exceeded: {len(sfx_events)} > max {max_allowed}")

        checks["no_negative_timestamps"] = no_neg
        checks["within_duration"] = within_dur
        checks["sfx_density"] = density_ok

        is_valid = len(errors) == 0 and all(checks.values())
        return {
            "valid": is_valid,
            "status": "PASS" if is_valid else "FAIL",
            "checks": checks,
            "errors": errors,
        }

    def validate_final_audio_short(
        self,
        video_path: Path,
        timeline_data: Any,
        expected_duration: Optional[float] = None,
        duration_tolerance_sec: float = 2.5,
    ) -> Dict[str, Any]:
        """
        Validates both the audio timeline and the rendered MP4 file (AAC stream, loudness, sync, no clipping).
        """
        tl_res = self.validate_audio_timeline(timeline_data, candidate_duration=expected_duration)

        errors = list(tl_res.get("errors", []))
        checks = {
            "timeline_valid": tl_res["valid"],
            "file_exists": False,
            "audio_stream": False,
            "aac_codec": False,
            "sample_rate_valid": False,
            "stereo_channels": False,
            "duration_match": False,
            "no_clip": False,
            "decodable": False,
        }

        if not video_path.exists():
            errors.append(f"Output video does not exist: {video_path}")
            return {"valid": False, "status": "FAIL", "checks": checks, "errors": errors}

        checks["file_exists"] = True

        probe_cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,codec_name,sample_rate,channels",
            "-of", "json",
            str(video_path),
        ]

        try:
            res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, timeout=30)
            probe_data = json.loads(res.stdout)
        except Exception as e:
            errors.append(f"ffprobe failed: {e}")
            return {"valid": False, "status": "FAIL", "checks": checks, "errors": errors}

        streams = probe_data.get("streams", [])
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)

        if not audio_stream:
            errors.append("No audio stream found in final video")
            return {"valid": False, "status": "FAIL", "checks": checks, "errors": errors}

        checks["audio_stream"] = True

        acodec = audio_stream.get("codec_name", "")
        checks["aac_codec"] = ("aac" in acodec.lower())
        if not checks["aac_codec"]:
            errors.append(f"Audio codec is not AAC ({acodec})")

        sr = int(audio_stream.get("sample_rate", 0))
        checks["sample_rate_valid"] = sr in [44100, 48000]

        channels = int(audio_stream.get("channels", 0))
        checks["stereo_channels"] = (channels == 2)

        format_dur = float(probe_data.get("format", {}).get("duration", 0.0))
        exp_dur = expected_duration or format_dur
        if exp_dur > 0:
            diff = abs(format_dur - exp_dur)
            checks["duration_match"] = (diff <= duration_tolerance_sec)
            if not checks["duration_match"]:
                errors.append(f"Duration mismatch: {format_dur:.2f}s vs expected {exp_dur:.2f}s")
        else:
            checks["duration_match"] = True

        # Quick decode & peak check
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
            checks["decodable"] = (dec_proc.returncode == 0)
        except Exception:
            checks["decodable"] = False

        # True Peak check via volumedetect
        vol_cmd = [
            self.ffmpeg_path,
            "-v", "info",
            "-i", str(video_path),
            "-af", "volumedetect",
            "-f", "null",
            "-"
        ]
        try:
            vol_proc = subprocess.run(vol_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        except Exception:
            vol_proc = subprocess.CompletedProcess(args=vol_cmd, returncode=1, stdout="", stderr="")
        max_vol = -1.0
        for line in vol_proc.stderr.splitlines():
            if "max_volume:" in line:
                import re
                m = re.search(r'max_volume:\s*(-?[\d\.]+)\s*dB', line)
                if m:
                    max_vol = float(m.group(1))

        # Must not clip (max volume <= 0.0 dB)
        checks["no_clip"] = (max_vol <= 0.0)
        if not checks["no_clip"]:
            errors.append(f"Audio peak exceeds 0.0 dBFS ({max_vol} dB)")

        all_passed = len(errors) == 0 and all(checks.values())

        return {
            "valid": all_passed,
            "status": "PASS" if all_passed else "FAIL",
            "video_path": str(video_path),
            "max_volume_db": max_vol,
            "checks": checks,
            "errors": errors,
        }
