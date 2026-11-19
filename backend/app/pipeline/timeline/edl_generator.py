"""EDL Generator: synthesizes multi-track TimelineEDL from AI analysis and pipeline artifacts."""

from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from backend.app.pipeline.caption_engine import CaptionEngine
from backend.app.pipeline.emoji_engine import EmojiEngine
from backend.app.pipeline.ducking_engine import DuckingEngine
from .models import (
    TimelineEDL,
    TimelineBoundaries,
    TimelineVideoTrack,
    SubtitleItem,
    SubtitleWordItem,
    EmojiItem,
    EffectItem,
    SfxItem,
    DuckingItem,
    TimelineMetadata,
)


class TimelineEdlGenerator:
    """Extracts decisions from Phase 3-6A artifacts and synthesizes a clean, editable TimelineEDL."""

    def __init__(
        self,
        caption_engine: Optional[CaptionEngine] = None,
        emoji_engine: Optional[EmojiEngine] = None,
        ducking_engine: Optional[DuckingEngine] = None,
    ):
        self.caption_engine = caption_engine or CaptionEngine()
        self.emoji_engine = emoji_engine or EmojiEngine()
        self.ducking_engine = ducking_engine or DuckingEngine()

    def generate_edl(
        self,
        project_id: str,
        candidate_id: int,
        candidate: Dict[str, Any],
        transcript_data: Optional[Dict[str, Any]] = None,
        phase5_timeline: Optional[Dict[str, Any]] = None,
        phase6a_timeline: Optional[Dict[str, Any]] = None,
        source_video_path: Optional[str] = "source.mp4",
        layout: str = "smart_crop",
        aspect_ratio: str = "9:16",
    ) -> TimelineEDL:
        """Constructs an initial TimelineEDL document from existing AI artifacts."""
        start = float(candidate.get("start", candidate.get("candidate_start", 0.0)))
        end = float(candidate.get("end", candidate.get("candidate_end", 60.0)))
        duration = float(candidate.get("duration", candidate.get("candidate_duration", end - start)))

        cand_aspect = candidate.get("aspect_ratio", aspect_ratio) or "9:16"
        res = "1080x1080" if cand_aspect == "1:1" else "1080x1920"

        # 1. Boundaries Track
        boundaries = TimelineBoundaries(
            source_in=round(start, 3),
            source_out=round(end, 3),
            duration=round(duration, 3),
        )

        # 2. Video Track
        video_track = TimelineVideoTrack(
            source_file=Path(source_video_path).name if source_video_path else "source.mp4",
            layout=candidate.get("layout", layout) or "smart_crop",
            resolution=res,
            aspect_ratio=cand_aspect,
            fps=60,
            enabled=True,
        )

        # 3. Subtitles Track & Emoji Track
        subtitles_track: List[SubtitleItem] = []
        emoji_track: List[EmojiItem] = []

        if transcript_data:
            words = self.caption_engine.extract_words(
                transcript_data=transcript_data,
                clip_start=start,
                clip_end=end,
                clip_duration=duration,
            )
            groups = self.caption_engine.group_words(words)
            lang = transcript_data.get("language", "en")

            for idx, g in enumerate(groups, start=1):
                word_items = [
                    SubtitleWordItem(
                        word=w.text,
                        start=round(w.start, 3),
                        end=round(w.end, 3),
                    )
                    for w in g.words
                ]
                subtitles_track.append(
                    SubtitleItem(
                        id=f"sub_{idx:02d}",
                        start=round(g.start, 3),
                        end=round(g.end, 3),
                        text=g.text,
                        words=word_items,
                        language=lang,
                        confidence=0.95,
                        enabled=True,
                        source="ai",
                        edited=False,
                        original_text=g.text,
                    )
                )

            # Emojis
            emoji_events = self.emoji_engine.detect_emojis(
                transcript_data=transcript_data,
                clip_start=start,
                clip_end=end,
                clip_duration=duration,
            )
            for idx, ev in enumerate(emoji_events, start=1):
                e_start = float(ev.get("start", 0.0))
                e_end = float(ev.get("end", e_start + 1.2))
                emoji_track.append(
                    EmojiItem(
                        id=f"emo_{idx:02d}",
                        timestamp=round(e_start, 3),
                        duration=round(max(0.3, e_end - e_start), 2),
                        emoji=ev.get("emoji", "🔥"),
                        animation="pop",
                        position="top",
                        enabled=True,
                        source="ai",
                        edited=False,
                    )
                )

        # 4. Effects Track
        effects_track: List[EffectItem] = []
        p5_effects = []
        if phase5_timeline and "effects" in phase5_timeline:
            p5_effects = phase5_timeline["effects"]
        elif "effect_timeline" in candidate and isinstance(candidate["effect_timeline"], dict):
            p5_effects = candidate["effect_timeline"].get("effects", [])

        for idx, eff in enumerate(p5_effects, start=1):
            effects_track.append(
                EffectItem(
                    id=f"eff_{idx:02d}",
                    type=eff.get("type", "subtle_zoom"),
                    start=round(float(eff.get("start", 0.0)), 3),
                    end=round(float(eff.get("end", 0.0)), 3),
                    intensity=round(float(eff.get("intensity", 0.5)), 2),
                    focal_point=eff.get("focal_point", [0.5, 0.65]),
                    reason=eff.get("reason"),
                    enabled=True,
                    source="ai",
                    edited=False,
                )
            )

        # 5. SFX Track
        sfx_track: List[SfxItem] = []
        p6a_sfx = []
        if phase6a_timeline and "audio_events" in phase6a_timeline:
            p6a_sfx = phase6a_timeline["audio_events"]
        elif "audio_timeline" in candidate and isinstance(candidate["audio_timeline"], dict):
            p6a_sfx = candidate["audio_timeline"].get("audio_events", [])

        for idx, sfx in enumerate(p6a_sfx, start=1):
            sfx_track.append(
                SfxItem(
                    id=f"sfx_{idx:02d}",
                    timestamp=round(float(sfx.get("timestamp", 0.0)), 3),
                    event_type=sfx.get("event_type", "whoosh"),
                    asset_name=sfx.get("asset_name", "whoosh_soft.wav"),
                    gain_db=round(float(sfx.get("gain_db", -14.0)), 1),
                    reason=sfx.get("reason"),
                    enabled=True,
                    source="ai",
                    edited=False,
                )
            )

        # 6. Ducking Track
        ducking_track: List[DuckingItem] = []
        p6a_duck = []
        if phase6a_timeline and "ducking_schedule" in phase6a_timeline:
            p6a_duck = phase6a_timeline["ducking_schedule"]
        elif transcript_data:
            duck_plan = self.ducking_engine.compute_ducking_plan(
                transcript_data=transcript_data,
                candidate=candidate,
            )
            p6a_duck = duck_plan.get("intervals", [])

        for idx, duck in enumerate(p6a_duck, start=1):
            ducking_track.append(
                DuckingItem(
                    id=f"duck_{idx:02d}",
                    start=round(float(duck.get("start", 0.0)), 3),
                    end=round(float(duck.get("end", 0.0)), 3),
                    attenuation_db=round(float(duck.get("attenuation_db", -3.5)), 1),
                    attack_ms=int(duck.get("attack_ms", 150)),
                    release_ms=int(duck.get("release_ms", 300)),
                    enabled=True,
                    source="ai",
                    edited=False,
                )
            )

        return TimelineEDL(
            project_id=project_id,
            candidate_id=candidate_id,
            version=1,
            duration=round(duration, 3),
            boundaries=boundaries,
            video_track=video_track,
            subtitles_track=subtitles_track,
            emoji_track=emoji_track,
            effects_track=effects_track,
            sfx_track=sfx_track,
            ducking_track=ducking_track,
            metadata=TimelineMetadata(
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                source="ai_generated",
                edit_summary="Initial AI EDL generation",
                dirty_tracks=[],
            ),
        )
