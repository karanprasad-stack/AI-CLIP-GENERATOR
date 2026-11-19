"""Comprehensive subtitle and captioned video validator."""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional

from backend.app.config import (
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
    DEFAULT_ASPECT_RATIO,
    ASPECT_RATIO_1_1,
    get_output_dimensions,
)
from backend.app.pipeline.video_validator import VideoValidator


def parse_ass_timestamp(ts_str: str) -> float:
    """Parses ASS timestamp H:MM:SS.cs into seconds."""
    parts = ts_str.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid ASS timestamp format: '{ts_str}'")
    hrs = int(parts[0])
    mins = int(parts[1])
    secs = float(parts[2])
    return hrs * 3600.0 + mins * 60.0 + secs


class SubtitleValidator:
    """Validates ASS subtitle files and technical integrity of captioned Shorts."""

    def __init__(self, video_validator: Optional[VideoValidator] = None):
        self.video_validator = video_validator or VideoValidator()

    def validate_ass(
        self,
        ass_path: Path,
        clip_duration: Optional[float] = None,
        duration_tolerance_sec: float = 1.5,
        expected_width: int = OUTPUT_WIDTH,
        expected_height: int = OUTPUT_HEIGHT,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        allow_empty_dialogue: bool = False,
    ) -> Dict[str, Any]:
        """
        Validates the structure, syntax, and timing integrity of an ASS file.
        """
        errors: List[str] = []
        checks = {
            "file_exists": False,
            "size_nonzero": False,
            "has_script_info": False,
            "has_styles": False,
            "has_events": False,
            "target_resolution_1080x1920": False,
            "has_dialogue_lines": False,
            "timestamps_valid": False,
            "no_negative_timestamps": False,
            "within_clip_duration": False,
        }

        if aspect_ratio == ASPECT_RATIO_1_1 and expected_width == OUTPUT_WIDTH and expected_height == OUTPUT_HEIGHT:
            expected_width, expected_height = get_output_dimensions(aspect_ratio)

        if not ass_path.exists():
            errors.append(f"ASS file does not exist: {ass_path}")
            return {"valid": False, "ass_file": str(ass_path), "checks": checks, "errors": errors}

        checks["file_exists"] = True
        file_size = ass_path.stat().st_size
        if file_size <= 0:
            errors.append(f"ASS file is 0 bytes: {ass_path}")
            return {"valid": False, "ass_file": str(ass_path), "checks": checks, "errors": errors}

        checks["size_nonzero"] = True

        try:
            content = ass_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = ass_path.read_text(encoding="utf-8-sig")
            except Exception as e:
                errors.append(f"Could not read ASS file: {e}")
                return {"valid": False, "ass_file": str(ass_path), "checks": checks, "errors": errors}

        lines = content.splitlines()

        # Section presence
        checks["has_script_info"] = "[Script Info]" in content
        checks["has_styles"] = "[V4+ Styles]" in content
        checks["has_events"] = "[Events]" in content

        if not checks["has_script_info"]:
            errors.append("Missing [Script Info] section")
        if not checks["has_styles"]:
            errors.append("Missing [V4+ Styles] section")
        if not checks["has_events"]:
            errors.append("Missing [Events] section")

        # Resolution check
        has_resx = f"PlayResX: {expected_width}" in content
        has_resy = f"PlayResY: {expected_height}" in content
        checks["target_resolution_1080x1920"] = has_resx and has_resy
        checks["target_resolution_valid"] = has_resx and has_resy
        if not (has_resx and has_resy):
            errors.append(f"Target resolution mismatch (PlayResX:{expected_width}={has_resx}, PlayResY:{expected_height}={has_resy})")

        # Parse Dialogue lines
        dialogue_count = 0
        emoji_count = 0
        timestamps_valid = True
        no_negative = True
        within_duration = True
        max_seen_timestamp = 0.0

        for line in lines:
            line = line.strip()
            if not line.startswith("Dialogue:"):
                continue

            dialogue_count += 1
            # Dialogue: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            parts = line.split(",", 9)
            if len(parts) < 10:
                timestamps_valid = False
                errors.append(f"Malformed Dialogue line: {line}")
                continue

            style = parts[3].strip()
            if style == "Emoji":
                emoji_count += 1

            start_str = parts[1].strip()
            end_str = parts[2].strip()

            try:
                t_start = parse_ass_timestamp(start_str)
                t_end = parse_ass_timestamp(end_str)
            except Exception as e:
                timestamps_valid = False
                errors.append(f"Invalid timestamp in line: {line} ({e})")
                continue

            if t_start < 0.0 or t_end < 0.0:
                no_negative = False
                errors.append(f"Negative timestamp found: {start_str} -> {end_str}")

            if t_end <= t_start:
                timestamps_valid = False
                errors.append(f"Non-positive duration: start={t_start} end={t_end}")

            if t_end > max_seen_timestamp:
                max_seen_timestamp = t_end

            if clip_duration is not None and clip_duration > 0:
                if t_end > (clip_duration + duration_tolerance_sec):
                    within_duration = False
                    errors.append(
                        f"Timestamp {end_str} ({t_end:.2f}s) exceeds clip duration ({clip_duration:.2f}s + {duration_tolerance_sec}s)"
                    )

        checks["has_dialogue_lines"] = dialogue_count > 0 or allow_empty_dialogue
        if not checks["has_dialogue_lines"]:
            errors.append("No Dialogue lines found in ASS file")

        checks["timestamps_valid"] = timestamps_valid if dialogue_count > 0 else allow_empty_dialogue
        checks["no_negative_timestamps"] = no_negative
        checks["within_clip_duration"] = within_duration

        is_valid = all(checks.values()) and (len(errors) == 0)

        return {
            "valid": is_valid,
            "ass_file": str(ass_path),
            "dialogue_count": dialogue_count,
            "emoji_count": emoji_count,
            "max_timestamp": round(max_seen_timestamp, 3),
            "checks": checks,
            "errors": errors,
        }

    def validate_captioned_short(
        self,
        video_path: Path,
        ass_path: Path,
        expected_duration: Optional[float] = None,
        expected_width: int = OUTPUT_WIDTH,
        expected_height: int = OUTPUT_HEIGHT,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        allow_empty_dialogue: bool = False,
    ) -> Dict[str, Any]:
        """
        Validates both the ASS file and the burned-in captioned video MP4.
        """
        ass_res = self.validate_ass(
            ass_path,
            clip_duration=expected_duration,
            expected_width=expected_width,
            expected_height=expected_height,
            aspect_ratio=aspect_ratio,
            allow_empty_dialogue=allow_empty_dialogue,
        )
        video_res = self.video_validator.validate_short(
            video_path,
            expected_duration=expected_duration,
            expected_width=expected_width,
            expected_height=expected_height,
            aspect_ratio=aspect_ratio,
        )

        all_errors = list(ass_res.get("errors", [])) + list(video_res.get("errors", []))
        video_passed = (video_res.get("status") == "PASS") or bool(video_res.get("valid", False))
        ass_passed = bool(ass_res.get("valid", False))
        overall_valid = ass_passed and video_passed

        return {
            "valid": overall_valid,
            "status": "PASS" if overall_valid else "FAIL",
            "video_path": str(video_path),
            "ass_path": str(ass_path),
            "ass_validation": ass_res,
            "video_validation": video_res,
            "errors": all_errors,
        }
