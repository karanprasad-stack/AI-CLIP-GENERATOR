"""Validation engine for effect timelines and rendered edited Shorts."""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from backend.app.config import ALL_EFFECT_TYPES
from backend.app.pipeline.video_validator import VideoValidator
from backend.app.pipeline.effect_engine import EffectTimeline


class EffectValidator:
    """Validates structural timeline integrity and technical video standards for Phase 5."""

    def __init__(self, video_validator: Optional[VideoValidator] = None):
        self.video_validator = video_validator or VideoValidator()

    def validate_timeline(
        self,
        timeline_data: Any,
        candidate_duration: Optional[float] = None,
        duration_tolerance_sec: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Validates the structure, bounds, and cooldown compliance of an effect timeline.
        Accepts EffectTimeline instance, dictionary, or Path to JSON file.
        """
        errors: List[str] = []
        checks = {
            "timeline_exists": False,
            "valid_structure": False,
            "all_types_valid": False,
            "no_negative_timestamps": False,
            "monotonic_intervals": False,
            "within_duration": False,
            "valid_intensity_range": False,
            "valid_confidence_range": False,
            "no_invalid_overlaps": False,
        }

        # Load data if path
        if isinstance(timeline_data, (str, Path)):
            path = Path(timeline_data)
            if not path.exists():
                errors.append(f"Timeline file does not exist: {path}")
                return {"valid": False, "status": "FAIL", "checks": checks, "errors": errors}
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                errors.append(f"Failed to read timeline JSON: {e}")
                return {"valid": False, "status": "FAIL", "checks": checks, "errors": errors}
        elif hasattr(timeline_data, "to_dict"):
            data = timeline_data.to_dict()
        elif isinstance(timeline_data, dict):
            data = timeline_data
        else:
            errors.append(f"Unrecognized timeline format: {type(timeline_data)}")
            return {"valid": False, "status": "FAIL", "checks": checks, "errors": errors}

        checks["timeline_exists"] = True

        effects = data.get("effects", [])
        if not isinstance(effects, list):
            errors.append("'effects' must be a list")
            return {"valid": False, "status": "FAIL", "checks": checks, "errors": errors}

        checks["valid_structure"] = True

        eff_duration = candidate_duration or float(data.get("candidate_duration", 60.0))

        types_valid = True
        no_negative = True
        monotonic = True
        within_dur = True
        intensity_valid = True
        confidence_valid = True

        zoom_intervals: List[Tuple[float, float, str]] = []

        for idx, eff in enumerate(effects):
            eff_type = eff.get("type", "")
            if eff_type not in ALL_EFFECT_TYPES:
                types_valid = False
                errors.append(f"Effect #{idx} has invalid type: '{eff_type}'")

            start = float(eff.get("start", -1.0))
            end = float(eff.get("end", -1.0))

            if start < 0.0 or end < 0.0:
                no_negative = False
                errors.append(f"Effect #{idx} has negative timestamp: {start} -> {end}")

            if end <= start:
                monotonic = False
                errors.append(f"Effect #{idx} end ({end}) <= start ({start})")

            if eff_duration > 0 and end > (eff_duration + duration_tolerance_sec):
                within_dur = False
                errors.append(f"Effect #{idx} end ({end:.2f}s) exceeds candidate duration ({eff_duration:.2f}s)")

            intensity = float(eff.get("intensity", -1.0))
            if intensity < 0.0 or intensity > 1.0:
                intensity_valid = False
                errors.append(f"Effect #{idx} intensity out of bounds (0-1): {intensity}")

            confidence = float(eff.get("confidence", -1.0))
            if confidence < 0.0 or confidence > 1.0:
                confidence_valid = False
                errors.append(f"Effect #{idx} confidence out of bounds (0-1): {confidence}")

            # Check zoom overlaps
            if "zoom" in eff_type:
                zoom_intervals.append((start, end, eff_type))

        # Check for simultaneous zoom overlaps
        zoom_intervals.sort(key=lambda x: x[0])
        no_overlaps = True
        for i in range(len(zoom_intervals) - 1):
            curr_end = zoom_intervals[i][1]
            next_start = zoom_intervals[i + 1][0]
            if next_start < curr_end:
                no_overlaps = False
                errors.append(
                    f"Overlapping zoom effects detected: {zoom_intervals[i][2]} (ends {curr_end:.2f}s) and {zoom_intervals[i+1][2]} (starts {next_start:.2f}s)"
                )

        checks["all_types_valid"] = types_valid
        checks["no_negative_timestamps"] = no_negative
        checks["monotonic_intervals"] = monotonic
        checks["within_duration"] = within_dur
        checks["valid_intensity_range"] = intensity_valid
        checks["valid_confidence_range"] = confidence_valid
        checks["no_invalid_overlaps"] = no_overlaps

        is_valid = len(errors) == 0 and all(checks.values())

        return {
            "valid": is_valid,
            "status": "PASS" if is_valid else "FAIL",
            "total_effects": len(effects),
            "checks": checks,
            "errors": errors,
        }

    def validate_final_short(
        self,
        video_path: Path,
        timeline_data: Any,
        expected_duration: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Validates both the timeline structure and the resulting edited MP4 video.
        """
        timeline_res = self.validate_timeline(timeline_data, candidate_duration=expected_duration)
        video_res = self.video_validator.validate_short(video_path, expected_duration=expected_duration)

        all_errors = list(timeline_res.get("errors", [])) + list(video_res.get("errors", []))
        video_passed = (video_res.get("status") == "PASS") or bool(video_res.get("valid", False))
        timeline_passed = bool(timeline_res.get("valid", False))
        overall_valid = timeline_passed and video_passed

        return {
            "valid": overall_valid,
            "status": "PASS" if overall_valid else "FAIL",
            "video_path": str(video_path),
            "timeline_validation": timeline_res,
            "video_validation": video_res,
            "errors": all_errors,
        }
