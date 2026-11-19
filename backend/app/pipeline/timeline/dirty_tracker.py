"""Dirty Track Tracker: detects track-level modifications between timeline versions."""

from typing import List, Optional
from .models import TimelineEDL


class DirtyTracker:
    """Compares two timeline states to determine which tracks have been modified."""

    @staticmethod
    def detect_dirty_tracks(old_tl: Optional[TimelineEDL], new_tl: TimelineEDL) -> List[str]:
        """
        Returns list of dirty track identifiers:
        ['boundaries', 'video', 'subtitles', 'emojis', 'effects', 'sfx', 'ducking']
        """
        if old_tl is None:
            # All active tracks are considered dirty on initial creation
            dirty = ["boundaries", "video", "subtitles", "emojis", "effects", "sfx", "ducking"]
            new_tl.metadata.dirty_tracks = dirty
            return dirty

        dirty: List[str] = []

        # 1. Boundaries Track
        ob = old_tl.boundaries
        nb = new_tl.boundaries
        if (
            abs(ob.source_in - nb.source_in) > 0.05
            or abs(ob.source_out - nb.source_out) > 0.05
            or abs(ob.duration - nb.duration) > 0.05
        ):
            dirty.append("boundaries")

        # 2. Video Track
        ov = old_tl.video_track
        nv = new_tl.video_track
        if (
            ov.layout != nv.layout
            or ov.resolution != nv.resolution
            or ov.fps != nv.fps
            or ov.enabled != nv.enabled
        ):
            dirty.append("video")

        # 3. Subtitles Track
        if len(old_tl.subtitles_track) != len(new_tl.subtitles_track):
            dirty.append("subtitles")
        else:
            for os_item, ns_item in zip(old_tl.subtitles_track, new_tl.subtitles_track):
                if (
                    os_item.id != ns_item.id
                    or os_item.text != ns_item.text
                    or abs(os_item.start - ns_item.start) > 0.02
                    or abs(os_item.end - ns_item.end) > 0.02
                    or os_item.enabled != ns_item.enabled
                    or len(os_item.words) != len(ns_item.words)
                ):
                    dirty.append("subtitles")
                    break

        # 4. Emoji Track
        if len(old_tl.emoji_track) != len(new_tl.emoji_track):
            dirty.append("emojis")
        else:
            for oe, ne in zip(old_tl.emoji_track, new_tl.emoji_track):
                if (
                    oe.id != ne.id
                    or oe.emoji != ne.emoji
                    or abs(oe.timestamp - ne.timestamp) > 0.02
                    or oe.enabled != ne.enabled
                    or oe.position != ne.position
                ):
                    dirty.append("emojis")
                    break

        # 5. Effects Track
        if len(old_tl.effects_track) != len(new_tl.effects_track):
            dirty.append("effects")
        else:
            for o_eff, n_eff in zip(old_tl.effects_track, new_tl.effects_track):
                if (
                    o_eff.id != n_eff.id
                    or o_eff.type != n_eff.type
                    or abs(o_eff.start - n_eff.start) > 0.02
                    or abs(o_eff.end - n_eff.end) > 0.02
                    or abs(o_eff.intensity - n_eff.intensity) > 0.02
                    or o_eff.enabled != n_eff.enabled
                ):
                    dirty.append("effects")
                    break

        # 6. SFX Track
        if len(old_tl.sfx_track) != len(new_tl.sfx_track):
            dirty.append("sfx")
        else:
            for o_sfx, n_sfx in zip(old_tl.sfx_track, new_tl.sfx_track):
                if (
                    o_sfx.id != n_sfx.id
                    or o_sfx.event_type != n_sfx.event_type
                    or o_sfx.asset_name != n_sfx.asset_name
                    or abs(o_sfx.timestamp - n_sfx.timestamp) > 0.02
                    or abs(o_sfx.gain_db - n_sfx.gain_db) > 0.1
                    or o_sfx.enabled != n_sfx.enabled
                ):
                    dirty.append("sfx")
                    break

        # 7. Ducking Track
        if len(old_tl.ducking_track) != len(new_tl.ducking_track):
            dirty.append("ducking")
        else:
            for od, nd in zip(old_tl.ducking_track, new_tl.ducking_track):
                if (
                    od.id != nd.id
                    or abs(od.start - nd.start) > 0.02
                    or abs(od.end - nd.end) > 0.02
                    or abs(od.attenuation_db - nd.attenuation_db) > 0.1
                    or od.enabled != nd.enabled
                ):
                    dirty.append("ducking")
                    break

        new_tl.metadata.dirty_tracks = dirty
        return dirty
