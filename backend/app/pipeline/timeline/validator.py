"""Timeline Validator: strict validation of multi-track EDL data contracts and integrity constraints."""

from typing import List, Tuple, Dict, Any
from backend.app.config import ALL_EFFECT_TYPES, ALL_SFX_TYPES
from backend.app.pipeline.sfx_library import SfxLibrary, SFX_ASSET_NAMES
from .models import TimelineEDL


class TimelineValidator:
    """Validates timeline schema constraints, timestamps, ranges, and asset references."""

    def __init__(self, sfx_library: SfxLibrary = None):
        self.sfx_library = sfx_library or SfxLibrary()
        self.valid_sfx_assets = set(SFX_ASSET_NAMES.values())

    def validate(self, timeline: TimelineEDL, project_dir: Any = None) -> Tuple[bool, List[str]]:
        """
        Validates all tracks and values.
        Returns: (is_valid, list_of_error_messages)
        """
        errors: List[str] = []

        # 1. Top-Level Constraints
        if timeline.version < 1:
            errors.append(f"Invalid timeline version: {timeline.version}. Must be >= 1.")

        if timeline.candidate_id < 1:
            errors.append(f"Invalid candidate_id: {timeline.candidate_id}. Must be >= 1.")

        if timeline.duration <= 0.0:
            errors.append(f"Invalid duration: {timeline.duration}. Must be > 0.")

        # 2. Boundaries Track
        b = timeline.boundaries
        if b.source_in < 0.0:
            errors.append(f"Boundary source_in ({b.source_in}s) cannot be negative.")

        if b.source_out <= b.source_in:
            errors.append(f"Boundary source_out ({b.source_out}) must be > source_in ({b.source_in}).")

        b_dur = b.source_out - b.source_in
        if b_dur < b.min_allowed or b_dur > b.max_allowed:
            errors.append(f"Clip duration ({b_dur:.2f}s) outside allowed bounds [{b.min_allowed}s, {b.max_allowed}s].")

        dur_diff = abs(timeline.duration - b_dur)
        if dur_diff > 0.5:
            errors.append(f"Timeline duration ({timeline.duration:.2f}s) does not match boundary range ({b_dur:.2f}s).")

        max_clip_time = timeline.duration + 0.5

        # Video Track validation
        if timeline.video_track:
            v_layout = timeline.video_track.layout
            allowed_layouts = {"smart_crop", "blurred_background", "facecam_gameplay", "auto"}
            if v_layout and v_layout not in allowed_layouts:
                errors.append(f"Video track has unsupported layout '{v_layout}'. Allowed: {allowed_layouts}")

        # 3. Subtitles Track
        sub_ids = set()
        for idx, sub in enumerate(timeline.subtitles_track):
            if not sub.id or not sub.id.strip():
                errors.append(f"Subtitle at index {idx} has missing or empty ID.")
            elif sub.id in sub_ids:
                errors.append(f"Duplicate subtitle ID detected: '{sub.id}'.")
            else:
                sub_ids.add(sub.id)

            if sub.start < 0.0:
                errors.append(f"Subtitle '{sub.id}' has negative start time: {sub.start}s.")
            if sub.end <= sub.start:
                errors.append(f"Subtitle '{sub.id}' has end ({sub.end}s) <= start ({sub.start}s).")
            if sub.enabled and sub.start > max_clip_time:
                errors.append(f"Subtitle '{sub.id}' starts beyond clip duration: {sub.start}s > {timeline.duration}s.")
            if not sub.text or not sub.text.strip():
                errors.append(f"Subtitle '{sub.id}' text cannot be empty.")

            # Validate word timings if present
            for w in sub.words:
                if w.start < 0.0 or w.end <= w.start:
                    errors.append(f"Subtitle '{sub.id}' word '{w.word}' has invalid range [{w.start}s, {w.end}s].")

        # 4. Emoji Track
        emo_ids = set()
        for idx, emo in enumerate(timeline.emoji_track):
            if not emo.id or not emo.id.strip():
                errors.append(f"Emoji at index {idx} has missing or empty ID.")
            elif emo.id in emo_ids:
                errors.append(f"Duplicate emoji ID detected: '{emo.id}'.")
            else:
                emo_ids.add(emo.id)

            if emo.timestamp < 0.0:
                errors.append(f"Emoji '{emo.id}' has negative timestamp: {emo.timestamp}s.")
            if emo.enabled and emo.timestamp > max_clip_time:
                errors.append(f"Emoji '{emo.id}' timestamp exceeds clip duration: {emo.timestamp}s > {timeline.duration}s.")
            if not emo.emoji or not emo.emoji.strip():
                errors.append(f"Emoji '{emo.id}' cannot be empty.")

        # 5. Effects Track
        eff_ids = set()
        for idx, eff in enumerate(timeline.effects_track):
            if not eff.id or not eff.id.strip():
                errors.append(f"Effect at index {idx} has missing or empty ID.")
            elif eff.id in eff_ids:
                errors.append(f"Duplicate effect ID detected: '{eff.id}'.")
            else:
                eff_ids.add(eff.id)

            if eff.type not in ALL_EFFECT_TYPES:
                errors.append(f"Effect '{eff.id}' has unsupported type '{eff.type}'. Allowed: {ALL_EFFECT_TYPES}")
            if eff.start < 0.0:
                errors.append(f"Effect '{eff.id}' has negative start: {eff.start}s.")
            if eff.end <= eff.start:
                errors.append(f"Effect '{eff.id}' has end ({eff.end}s) <= start ({eff.start}s).")
            if eff.enabled and eff.start > max_clip_time:
                errors.append(f"Effect '{eff.id}' starts beyond clip duration: {eff.start}s > {timeline.duration}s.")
            if not (0.0 <= eff.intensity <= 1.0):
                errors.append(f"Effect '{eff.id}' intensity ({eff.intensity}) must be in range [0.0, 1.0].")

        # 6. SFX Track
        sfx_ids = set()
        for idx, sfx in enumerate(timeline.sfx_track):
            if not sfx.id or not sfx.id.strip():
                errors.append(f"SFX at index {idx} has missing or empty ID.")
            elif sfx.id in sfx_ids:
                errors.append(f"Duplicate SFX ID detected: '{sfx.id}'.")
            else:
                sfx_ids.add(sfx.id)

            if sfx.event_type not in ALL_SFX_TYPES:
                errors.append(f"SFX '{sfx.id}' has unsupported event_type '{sfx.event_type}'. Allowed: {ALL_SFX_TYPES}")
            if sfx.timestamp < 0.0:
                errors.append(f"SFX '{sfx.id}' has negative timestamp: {sfx.timestamp}s.")
            if sfx.enabled and sfx.timestamp > max_clip_time:
                errors.append(f"SFX '{sfx.id}' timestamp exceeds clip duration: {sfx.timestamp}s > {timeline.duration}s.")
            if sfx.asset_name not in self.valid_sfx_assets:
                errors.append(f"SFX '{sfx.id}' asset '{sfx.asset_name}' not found in library.")

        # 7. Ducking Track
        duck_ids = set()
        for idx, duck in enumerate(timeline.ducking_track):
            if not duck.id or not duck.id.strip():
                errors.append(f"Ducking at index {idx} has missing or empty ID.")
            elif duck.id in duck_ids:
                errors.append(f"Duplicate ducking ID detected: '{duck.id}'.")
            else:
                duck_ids.add(duck.id)

            if duck.start < 0.0:
                errors.append(f"Ducking '{duck.id}' has negative start: {duck.start}s.")
            if duck.end <= duck.start:
                errors.append(f"Ducking '{duck.id}' has end ({duck.end}s) <= start ({duck.start}s).")
            if duck.attenuation_db > 0.0:
                errors.append(f"Ducking '{duck.id}' attenuation ({duck.attenuation_db}dB) must be <= 0.0dB.")

        is_valid = len(errors) == 0
        return is_valid, errors
