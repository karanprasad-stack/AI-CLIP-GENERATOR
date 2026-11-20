"""Timeline Renderer: executes deterministic re-rendering of Shorts directly from TimelineEDL."""

import json
import shutil
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from backend.app.config import (
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
    DEFAULT_ASPECT_RATIO,
    ASPECT_RATIO_1_1,
    get_output_dimensions,
    LAYOUT_AUTO,
)
from backend.app.pipeline.clip_extractor import ClipExtractor
from backend.app.pipeline.vertical_renderer import VerticalRenderer
from backend.app.pipeline.caption_engine import CaptionEngine, CaptionGroup, CaptionWord
from backend.app.pipeline.ass_generator import AssGenerator
from backend.app.pipeline.caption_renderer import CaptionRenderer
from backend.app.pipeline.effect_engine import EffectEvent, EffectTimeline
from backend.app.pipeline.effect_renderer import EffectRenderer
from backend.app.pipeline.audio_event_engine import AudioEvent, AudioTimeline
from backend.app.pipeline.ducking_engine import DuckingEngine
from backend.app.pipeline.audio_renderer import AudioRenderer
from backend.app.pipeline.video_validator import VideoValidator
from backend.app.pipeline.creator_quality import CreatorQualityEvaluator
from backend.app.pipeline.publishing_package import PublishingPackageManager
from .models import TimelineEDL


class TimelineRenderError(Exception):
    """Raised when timeline re-rendering fails."""
    pass


class TimelineRenderer:
    """Consumes TimelineEDL and executes targeted re-rendering using existing pipeline engines."""

    def __init__(
        self,
        clip_extractor: Optional[ClipExtractor] = None,
        vertical_renderer: Optional[VerticalRenderer] = None,
        ass_generator: Optional[AssGenerator] = None,
        caption_renderer: Optional[CaptionRenderer] = None,
        effect_renderer: Optional[EffectRenderer] = None,
        audio_renderer: Optional[AudioRenderer] = None,
        ducking_engine: Optional[DuckingEngine] = None,
        quality_evaluator: Optional[CreatorQualityEvaluator] = None,
    ):
        self.clip_extractor = clip_extractor or ClipExtractor()
        self.vertical_renderer = vertical_renderer or VerticalRenderer()
        self.ass_generator = ass_generator or AssGenerator()
        self.caption_renderer = caption_renderer or CaptionRenderer()
        self.effect_renderer = effect_renderer or EffectRenderer()
        self.audio_renderer = audio_renderer or AudioRenderer()
        self.ducking_engine = ducking_engine or DuckingEngine()
        self.quality_evaluator = quality_evaluator or CreatorQualityEvaluator()
        self.package_manager = PublishingPackageManager()
        self.video_validator = VideoValidator()

    def render_from_timeline(
        self,
        project_dir: Path,
        timeline: TimelineEDL,
        dirty_tracks: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Renders the complete Short from TimelineEDL and refreshes the publishing package.
        """
        start_time = time.perf_counter()
        cid = timeline.candidate_id
        dirty = dirty_tracks if dirty_tracks is not None else timeline.metadata.dirty_tracks

        # Target working directories
        clips_dir = project_dir / "clips"
        captions_dir = project_dir / "captions"
        effects_dir = project_dir / "effects"
        audio_dir = project_dir / "audio"
        pub_cand_dir = project_dir / "publishing" / f"candidate_{cid:02d}"

        clips_dir.mkdir(parents=True, exist_ok=True)
        captions_dir.mkdir(parents=True, exist_ok=True)
        effects_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
        pub_cand_dir.mkdir(parents=True, exist_ok=True)

        cand_source = pub_cand_dir / (timeline.video_track.source_file or "source.mp4")
        clips_cand_source = clips_dir / f"candidate_{cid:02d}_source.mp4"
        source_video = project_dir / "source.mp4"

        if not source_video.exists():
            # Check candidate-specific source file (e.g. from partial segment downloads or live stream segments)
            if cand_source.exists():
                source_video = cand_source
            elif clips_cand_source.exists():
                source_video = clips_cand_source
            elif timeline.video_track.source_file and Path(timeline.video_track.source_file).exists():
                source_video = Path(timeline.video_track.source_file)
            else:
                live_dir = project_dir / "live"
                if live_dir.exists():
                    from backend.app.pipeline.live import LiveSourceResolver, LiveStore
                    l_store = LiveStore(project_dir)
                    manifest = l_store.load_manifest()
                    cand_source.parent.mkdir(parents=True, exist_ok=True)
                    resolver = LiveSourceResolver()
                    resolver.resolve_source_clip(
                        global_start=timeline.boundaries.source_in,
                        global_end=timeline.boundaries.source_out,
                        segments=manifest,
                        output_clip_path=cand_source,
                    )
                    source_video = cand_source
                else:
                    raise TimelineRenderError(f"Source video not found: {source_video}")

        prefix = f"candidate_{cid:02d}"
        extracted_clip_path = clips_dir / f"{prefix}_extracted.mp4"
        vertical_clip_path = clips_dir / f"{prefix}_short.mp4"
        captioned_clip_path = captions_dir / f"{prefix}_captioned.mp4"
        ass_path = captions_dir / f"{prefix}.ass"
        effects_clip_path = effects_dir / f"{prefix}_final.mp4"
        audio_polished_clip = audio_dir / f"{prefix}_final.mp4"
        target_final_mp4 = pub_cand_dir / "final.mp4"

        boundaries_changed = "boundaries" in dirty or not vertical_clip_path.exists()
        subtitles_changed = boundaries_changed or "subtitles" in dirty or "emojis" in dirty or not captioned_clip_path.exists()
        effects_changed = subtitles_changed or "effects" in dirty or not effects_clip_path.exists()
        audio_changed = effects_changed or "sfx" in dirty or "ducking" in dirty or not audio_polished_clip.exists()

        cand_aspect = getattr(timeline.video_track, "aspect_ratio", "9:16") or "9:16"
        out_w, out_h = get_output_dimensions(cand_aspect)

        # Step 1: Boundaries & Vertical 9:16 Cropping
        if boundaries_changed:
            is_cand_clip = (
                source_video == cand_source
                or source_video == clips_cand_source
                or (timeline.video_track.source_file and source_video == Path(timeline.video_track.source_file))
            )
            ext_start = 0.0 if is_cand_clip else timeline.boundaries.source_in
            ext_end = timeline.boundaries.duration if is_cand_clip else timeline.boundaries.source_out

            self.clip_extractor.extract_candidate(
                source_path=source_video,
                output_clip_path=extracted_clip_path,
                candidate_start=ext_start,
                candidate_end=ext_end,
                pre_roll=0.0,
                post_roll=0.0,
            )

            # Apply vertical rendering
            self.vertical_renderer.render_short(
                input_clip_path=extracted_clip_path,
                output_short_path=vertical_clip_path,
                layout=timeline.video_track.layout or "smart_crop",
                aspect_ratio=cand_aspect,
                kill_feed_overlay=bool(timeline.video_track.kill_feed_overlay),
                kill_feed_roi=tuple(timeline.video_track.kill_feed_roi) if timeline.video_track.kill_feed_roi else None,
            )

        # Step 2: Subtitles & Emojis ASS Burning
        if subtitles_changed:
            caption_groups: List[CaptionGroup] = []
            for sub in timeline.subtitles_track:
                if not sub.enabled:
                    continue
                words = [
                    CaptionWord(
                        text=w.word,
                        start=w.start,
                        end=w.end,
                        index=w_idx,
                        global_start=timeline.boundaries.source_in + w.start,
                        global_end=timeline.boundaries.source_in + w.end,
                    )
                    for w_idx, w in enumerate(sub.words)
                ]
                caption_groups.append(
                    CaptionGroup(
                        words=words,
                        start=sub.start,
                        end=sub.end,
                        text=sub.text,
                    )
                )

            emoji_events = [
                {
                    "start": emo.timestamp,
                    "end": emo.timestamp + emo.duration,
                    "emoji": emo.emoji,
                }
                for emo in timeline.emoji_track
                if emo.enabled
            ]

            ass_gen = AssGenerator(
                output_width=out_w,
                output_height=out_h,
                aspect_ratio=cand_aspect,
            )
            ass_gen.write_ass_file(
                output_path=ass_path,
                caption_groups=caption_groups,
                emoji_events=emoji_events,
            )

            self.caption_renderer.render_captioned_short(
                short_video_path=vertical_clip_path,
                ass_path=ass_path,
                output_captioned_path=captioned_clip_path,
            )

        # Step 3: Visual Effects
        if effects_changed:
            effect_events = [
                EffectEvent(
                    type=eff.type,
                    start=eff.start,
                    end=eff.end,
                    intensity=eff.intensity,
                    confidence=1.0,
                    reason=eff.reason or "timeline_edl",
                    source_events=["timeline_edl"],
                    focal_point=tuple(eff.focal_point) if eff.focal_point else (0.5, 0.65),
                )
                for eff in timeline.effects_track
                if eff.enabled
            ]
            effect_timeline = EffectTimeline(
                candidate_id=cid,
                candidate_duration=timeline.duration,
                effects=effect_events,
            )
            self.effect_renderer.render_effects(
                input_video_path=captioned_clip_path,
                timeline=effect_timeline,
                output_video_path=effects_clip_path,
                facecam_info={"facecam_detected": False},
                output_width=out_w,
                output_height=out_h,
                aspect_ratio=cand_aspect,
            )

        # Step 4: SFX Mixing & Speech-Aware Ducking
        if audio_changed:
            audio_events = [
                AudioEvent(
                    timestamp=sfx.timestamp,
                    event_type=sfx.event_type,
                    asset_name=sfx.asset_name,
                    gain_db=sfx.gain_db,
                    intensity=0.8,
                    confidence=1.0,
                    source=sfx.source,
                    reason=sfx.reason or "timeline_edl",
                )
                for sfx in timeline.sfx_track
                if sfx.enabled
            ]
            audio_timeline = AudioTimeline(
                candidate_id=cid,
                candidate_duration=timeline.duration,
                audio_events=audio_events,
            )

            ducking_intervals = [
                {
                    "start": duck.start,
                    "end": duck.end,
                    "ducking_db": duck.attenuation_db,
                    "gain_ratio": round(10.0 ** (duck.attenuation_db / 20.0), 3),
                }
                for duck in timeline.ducking_track
                if duck.enabled
            ]
            ducking_summary = {
                "enabled": len(ducking_intervals) > 0,
                "intervals": ducking_intervals,
            }

            self.audio_renderer.render_audio(
                input_video_path=effects_clip_path,
                timeline=audio_timeline,
                ducking_summary=ducking_summary,
                output_video_path=audio_polished_clip,
            )

        # Validate rendered video before promoting to published target
        if not audio_polished_clip.exists() or audio_polished_clip.stat().st_size < 1000:
            raise TimelineRenderError(f"Rendered video is missing or empty: {audio_polished_clip}")

        val_vid = self.video_validator.validate_short(
            audio_polished_clip,
            expected_width=out_w,
            expected_height=out_h,
            aspect_ratio=cand_aspect,
        )
        if not val_vid.get("valid", False) and val_vid.get("status") != "PASS":
            raise TimelineRenderError(f"Rendered video failed technical validation: {val_vid.get('errors')}")

        # Atomic promotion: Stage to temporary file then replace target
        staging_final_mp4 = pub_cand_dir / "final.tmp.mp4"
        shutil.copyfile(audio_polished_clip, staging_final_mp4)
        staging_final_mp4.replace(target_final_mp4)

        # Step 5: Refresh Metadata & Creator Quality Audit
        meta_file = pub_cand_dir / "metadata.json"
        cand_meta: Dict[str, Any] = {}
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    cand_meta = json.load(f)
            except Exception:
                cand_meta = {}

        # Ensure essential publishing bundle assets exist
        thumb_file = pub_cand_dir / "thumbnail.jpg"
        if not thumb_file.exists() or thumb_file.stat().st_size < 5000:
            try:
                import cv2
                source_for_thumb = cand_source if (cand_source and cand_source.exists()) else target_final_mp4
                cap = cv2.VideoCapture(str(source_for_thumb.resolve()))
                if cap.isOpened():
                    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                    total_f = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 100
                    target_frame_num = int(min(total_f - 1, max(0, fps * (timeline.duration * 0.3))))
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_num)
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        thumb_img = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)
                        cv2.imwrite(str(thumb_file), thumb_img, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    cap.release()
            except Exception:
                pass

        title_file = pub_cand_dir / "title.txt"
        if not title_file.exists():
            sub_text = " ".join([s.text for s in timeline.subtitles_track if s.enabled][:3])
            t_str = cand_meta.get("title", {}).get("selected") or (f"{sub_text} 🔥" if sub_text else f"Epic Gaming Moment #{cid} 🔥")
            if len(t_str) < 15:
                t_str = f"Epic Gaming Moment: {t_str}"
            title_file.write_text(t_str[:80], encoding="utf-8")

        desc_file = pub_cand_dir / "description.txt"
        if not desc_file.exists():
            desc_str = f"Watch this epic gaming Short! Captured at {int(timeline.boundaries.source_in // 60):02d}:{int(timeline.boundaries.source_in % 60):02d}. #gaming #shorts"
            desc_file.write_text(desc_str, encoding="utf-8")

        hash_file = pub_cand_dir / "hashtags.txt"
        if not hash_file.exists():
            hash_file.write_text("#shorts #gaming #clutch #highlight #gameplay", encoding="utf-8")

        kw_file = pub_cand_dir / "keywords.txt"
        if not kw_file.exists():
            kw_file.write_text("gaming, shorts, clutch, highlight, gameplay", encoding="utf-8")

        # Update video specs and metadata
        if "phase" not in cand_meta:
            cand_meta["phase"] = "6B"
        cand_meta["candidate_id"] = cid
        cand_meta["video"] = {
            "path": target_final_mp4.name,
            "duration": round(timeline.duration, 2),
            "format": "mp4",
            "aspect_ratio": "9:16",
            "resolution": "1080x1920",
        }
        cand_meta["thumbnail"] = {"path": "thumbnail.jpg", "score": 85.0}
        cand_meta["title"] = {"selected": title_file.read_text(encoding="utf-8").strip()}
        cand_meta["description"] = desc_file.read_text(encoding="utf-8").strip()
        cand_meta["hashtags"] = hash_file.read_text(encoding="utf-8").strip().split()
        cand_meta["keywords"] = [k.strip() for k in kw_file.read_text(encoding="utf-8").strip().split(",") if k.strip()]

        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(cand_meta, f, indent=2, ensure_ascii=False)

        # Validate bundle
        val_res = self.package_manager.validate_package(pub_cand_dir)

        # Load original candidate to preserve all signals, event tags, tone, and reactions
        orig_candidate: Dict[str, Any] = {}
        for cand_json_file in [project_dir / "candidates.json", project_dir / "live" / "candidates.json"]:
            if cand_json_file.exists():
                try:
                    with open(cand_json_file, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                    c_list = c_data if isinstance(c_data, list) else c_data.get("candidates", [])
                    matched = next((c for c in c_list if c.get("candidate_id") == cid or c.get("rank") == cid), None)
                    if matched:
                        orig_candidate = dict(matched)
                        break
                except Exception:
                    pass

        # Re-evaluate Creator Quality with updated metrics & preserved signals
        candidate_repr = dict(orig_candidate)
        candidate_repr.update({
            "candidate_id": cid,
            "start": timeline.boundaries.source_in,
            "end": timeline.boundaries.source_out,
            "duration": timeline.duration,
            "final_score": orig_candidate.get("final_score", orig_candidate.get("score", cand_meta.get("summary", {}).get("final_score", 80.0))),
            "gameplay_event": orig_candidate.get("gameplay_event", cand_meta.get("summary", {}).get("primary_event", "highlight")),
            "secondary_events": orig_candidate.get("secondary_events", []),
            "strongest_reaction": orig_candidate.get("strongest_reaction", cand_meta.get("summary", {}).get("strongest_reaction", "none")),
            "tone": orig_candidate.get("tone", "neutral"),
            "signals": orig_candidate.get("signals", {}),
            "detected_signals": orig_candidate.get("detected_signals", []),
        })

        pkg_repr = {
            "thumbnail_score": cand_meta.get("thumbnail", {}).get("score", 85.0),
            "thumbnail_path": str(thumb_file) if thumb_file.exists() else None,
            "title": cand_meta.get("title", {}).get("selected", ""),
            "description": cand_meta.get("description", ""),
            "hashtags": cand_meta.get("hashtags", []),
            "validation": val_res,
            "metadata": cand_meta,
        }

        publishability = self.quality_evaluator.evaluate(
            candidate=candidate_repr,
            package_info=pkg_repr,
        )

        cand_meta["publishability"] = publishability
        cand_meta["timeline_version"] = timeline.version
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(cand_meta, f, indent=2, ensure_ascii=False)

        # Update master manifest
        manifest_file = project_dir / "publishing" / "publishing_manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as mf:
                    man_data = json.load(mf)
                for p in man_data.get("packages", []):
                    if p.get("candidate_id") == cid:
                        p["publishability"] = publishability
                        p["status"] = val_res["status"]
                with open(manifest_file, "w", encoding="utf-8") as mf:
                    json.dump(man_data, mf, indent=2, ensure_ascii=False)
            except Exception:
                pass

        render_time = round(time.perf_counter() - start_time, 2)

        return {
            "status": "success",
            "candidate_id": cid,
            "render_time_sec": render_time,
            "video_path": str(target_final_mp4),
            "validation": val_res,
            "publishability": publishability,
            "dirty_tracks": dirty,
        }
