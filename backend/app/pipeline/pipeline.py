"""Phase 1, Phase 2, Phase 3, Phase 4, Phase 5, and Phase 6A Pipeline Orchestrator."""

import gc
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, Union

from .downloader import VideoDownloader, DownloaderError, is_remote_url
from .transcriber import AudioTranscriber, TranscriberError
from .audio_analyzer import AudioAnalyzer, AudioAnalyzerError
from .transcript_analyzer import TranscriptAnalyzer
from .candidate_generator import CandidateGenerator
from .candidate_ranker import CandidateRanker
from .video_downloader import VideoSourceDownloader
from .clip_extractor import ClipExtractor, ClipExtractionError
from .layout_detector import LayoutDetector
from .vertical_renderer import VerticalRenderer, RenderError
from .video_validator import VideoValidator, VideoValidationError
from .caption_engine import CaptionEngine
from .ass_generator import AssGenerator
from .emoji_engine import EmojiEngine
from .caption_renderer import CaptionRenderer, CaptionRenderError
from .subtitle_validator import SubtitleValidator
from .effect_engine import EffectEngine, EffectTimeline, EffectEvent
from .effect_renderer import EffectRenderer, EffectRenderError
from .effect_validator import EffectValidator
from .sfx_library import SfxLibrary
from .audio_event_engine import AudioEventEngine, AudioTimeline, AudioEvent
from .ducking_engine import DuckingEngine
from .audio_renderer import AudioRenderer, AudioRenderError
from .audio_validator import AudioValidator
from .clip_summary_engine import ClipSummaryEngine, ClipSummary
from .thumbnail_engine import ThumbnailEngine
from .title_engine import TitleEngine
from .description_engine import DescriptionEngine
from .hashtag_engine import HashtagEngine
from .publishing_package import PublishingPackageManager
from .long_stream import LongStreamOrchestrator, is_long_stream
from .subtitles import HinglishNormalizer
from .creator_quality import CreatorQualityEvaluator, PublishabilityGate
from .games import GameDetector, GameplayEngine, GameplayTimeline
from backend.app.config import (
    MAX_SOURCE_HEIGHT,
    PARTIAL_DOWNLOAD_ENABLED,
    PARTIAL_DOWNLOAD_THRESHOLD_SEC,
    PARTIAL_SEGMENT_KEYFRAME_PAD_SEC,
    PARTIAL_SEGMENT_MERGE_GAP_SEC,
    ANALYSIS_PROXY_MAX_HEIGHT,
    TOP_N_CANDIDATES,
    PRE_ROLL_SECONDS,
    POST_ROLL_SECONDS,
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
    DEFAULT_ASPECT_RATIO,
    ASPECT_RATIO_1_1,
    get_output_dimensions,
    get_duration_tier,
    get_narrative_structure,
    LAYOUT_AUTO,
    LAYOUT_SMART_CROP,
    DEFAULT_KILL_FEED_OVERLAY,
    CAPTION_FONT_NAME,
    CAPTION_FONT_SIZE,
    CAPTION_BASE_COLOR,
    CAPTION_ACTIVE_COLOR,
    CAPTION_OUTLINE_WIDTH,
    CAPTION_MARGIN_V,
    EMOJI_FONT_NAME,
    EMOJI_FONT_SIZE,
    EMOJI_MARGIN_V,
    AUDIO_ENABLED,
    SFX_ENABLED,
    DUCKING_ENABLED,
    TARGET_LUFS,
    TRUE_PEAK_LIMIT,
    THUMBNAIL_ENABLED,
    METADATA_ENABLED,
    OLLAMA_ENABLED,
)


class PipelineError(Exception):
    """Raised when an error occurs during pipeline execution."""
    pass


def run_pipeline(
    url: str,
    output_base_dir: Optional[Path] = None,
    temp_base_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    phase: Union[int, str] = "6b",
    top_n: int = TOP_N_CANDIDATES,
    layout: str = LAYOUT_AUTO,
    captions: bool = True,
    emoji: bool = True,
    effects: bool = True,
    audio: bool = AUDIO_ENABLED,
    sfx: bool = SFX_ENABLED,
    ducking: bool = DUCKING_ENABLED,
    thumbnail: bool = THUMBNAIL_ENABLED,
    metadata_enabled: bool = METADATA_ENABLED,
    llm: bool = OLLAMA_ENABLED,
    settings: Optional[Dict[str, Any]] = None,
    long_stream_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Optional[Any] = None,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
) -> Dict[str, Any]:
    """
    Executes the pipeline up to the specified phase (1, 2, 3, 4, 5, 6A, or 6B).
    phase=1: Audio download + Whisper transcription
    phase=2: Candidate generation + gaming event ranking
    phase=3: Source video acquisition, lossless clipping & Short rendering (9:16 or 1:1)
    phase=4: Word-level subtitles, karaoke captions & contextual emojis burned on Short
    phase=5: Context-aware visual effects (zoom, shake, flash) rendered onto edited Shorts
    phase=6 / 6a: Audio Polish & SFX Engine (whoosh, impacts, speech-aware ducking & loudnorm)
    phase=6b: Metadata, Thumbnail & Publishing Package Engine
    """
    aspect_ratio = (settings.get("aspect_ratio") if settings else None) or aspect_ratio or DEFAULT_ASPECT_RATIO
    output_width, output_height = get_output_dimensions(aspect_ratio)
    kill_feed_setting = (settings.get("kill_feed_overlay") if settings else None) or DEFAULT_KILL_FEED_OVERLAY
    # Normalize phase input
    phase_str = str(phase).strip().lower()
    if phase_str in ["6b", "6B"]:
        phase_num = 6
    elif "6" in phase_str or "6a" in phase_str:
        phase_num = 6
    elif phase_str in ["1", "2", "3", "4", "5"]:
        phase_num = int(phase_str)
    else:
        phase_num = 6

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    output_root = output_base_dir or (project_root / "output")
    temp_root = temp_base_dir or (project_root / "temp")

    output_root.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)

    def report_progress(step: int, message: str) -> None:
        if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
            raise PipelineError("Pipeline execution was cancelled by user.")
        if progress_callback:
            progress_callback(step, message)

    try:
        downloader = VideoDownloader(temp_dir=temp_root)

        # Step 1: Metadata extraction (with local cache check)
        import re
        vid_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
        cached_vid = vid_match.group(1) if vid_match else None
        cached_meta_file = (output_root / cached_vid / "metadata.json") if cached_vid else None

        if cached_meta_file and cached_meta_file.exists():
            try:
                with open(cached_meta_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                video_id = metadata["video_id"]
                video_duration = float(metadata.get("duration", 0.0))
                report_progress(1, f"Metadata loaded from local cache ({video_id})...")
            except Exception:
                report_progress(1, "Extracting metadata...")
                metadata = downloader.extract_metadata(url)
                video_id = metadata["video_id"]
                video_duration = float(metadata["duration"])
        else:
            report_progress(1, "Extracting metadata...")
            metadata = downloader.extract_metadata(url)
            video_id = metadata["video_id"]
            video_duration = float(metadata["duration"])

        job_output_dir = output_root / video_id
        job_temp_dir = temp_root / video_id

        job_output_dir.mkdir(parents=True, exist_ok=True)
        job_temp_dir.mkdir(parents=True, exist_ok=True)

        metadata_file = job_output_dir / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        final_audio_path = job_output_dir / "audio.wav"
        transcript_file = job_output_dir / "transcript.json"
        candidates_file = job_output_dir / "candidates.json"
        source_video_path = job_output_dir / "source.mp4"

        # Check if Phase 1 and 2 artifacts already exist
        ranked_results: Optional[Dict[str, Any]] = None
        transcript_data: Optional[Dict[str, Any]] = None

        if candidates_file.exists() and transcript_file.exists() and final_audio_path.exists():
            try:
                with open(candidates_file, "r", encoding="utf-8") as f:
                    ranked_results = json.load(f)
                with open(transcript_file, "r", encoding="utf-8") as f:
                    transcript_data = json.load(f)

                # Auto-recover full words if transcript_file was saved with empty segments from legacy run
                if is_long_stream(video_duration) and not transcript_data.get("segments") and not transcript_data.get("words"):
                    chunks_dir = job_output_dir / "long_stream" / "chunks"
                    if chunks_dir.exists():
                        from backend.app.pipeline.long_stream.chunk_store import ChunkStore
                        c_store = ChunkStore(job_output_dir)
                        rec_t = c_store.get_merged_transcript(language=transcript_data.get("language", metadata.get("language", "en")))
                        if rec_t.get("segments") or rec_t.get("words"):
                            rec_t["duration"] = video_duration
                            transcript_data = rec_t
                            with open(transcript_file, "w", encoding="utf-8") as f:
                                json.dump(transcript_data, f, indent=2, ensure_ascii=False)

                report_progress(2, "Audio already available, skipping download...")
                report_progress(3, "Transcript already available, skipping Whisper...")
                report_progress(4, "Analysis cached, skipping re-analysis...")
                report_progress(5, "Candidates loaded from cache...")
            except Exception:
                ranked_results = None
                transcript_data = None

        is_long = is_long_stream(video_duration)

        if not ranked_results or not transcript_data:
            if is_long:
                report_progress(2, "Acquiring source audio for long-stream chunk analysis...")
                if not final_audio_path.exists():
                    temp_audio_path = downloader.download_audio(url, output_dir=job_temp_dir)
                    shutil.copy2(temp_audio_path, final_audio_path)

                report_progress(3, "Initializing long-stream chunk planner...")
                orchestrator = LongStreamOrchestrator()

                def orchestrator_event_cb(evt: Dict[str, Any]):
                    if long_stream_event_callback:
                        long_stream_event_callback(evt)
                    msg = evt.get("message", "")
                    report_progress(4, msg)

                orchestrator_res = orchestrator.process(
                    video_id=video_id,
                    source_media=final_audio_path,
                    source_duration=video_duration,
                    project_dir=job_output_dir,
                    temp_dir=job_temp_dir,
                    settings=settings,
                    event_callback=orchestrator_event_cb,
                )

                ranked_results = {
                    "video_id": video_id,
                    "duration": video_duration,
                    "scoring_version": "phase7c-long-stream",
                    "long_stream": True,
                    "long_stream_info": orchestrator_res["long_stream_info"],
                    "candidates": orchestrator_res["candidates"],
                    "selected_candidate_ids": orchestrator_res["selected_candidate_ids"],
                    "quality_gate_reason": orchestrator_res.get("quality_gate_reason"),
                }
                with open(candidates_file, "w", encoding="utf-8") as f:
                    json.dump(ranked_results, f, indent=2, ensure_ascii=False)

                transcript_data = orchestrator_res.get("transcript")
                if not transcript_data or (not transcript_data.get("segments") and not transcript_data.get("words")):
                    from backend.app.pipeline.long_stream.chunk_store import ChunkStore
                    c_store = ChunkStore(job_output_dir)
                    transcript_data = c_store.get_merged_transcript(language=metadata.get("language", "en"))
                transcript_data["duration"] = video_duration

                with open(transcript_file, "w", encoding="utf-8") as f:
                    json.dump(transcript_data, f, indent=2, ensure_ascii=False)

            else:
                transcriber = AudioTranscriber()
                audio_analyzer = AudioAnalyzer()
                candidate_generator = CandidateGenerator()
                candidate_ranker = CandidateRanker()

                # Step 2: Download audio
                report_progress(2, "Downloading audio...")
                temp_audio_path = downloader.download_audio(url, output_dir=job_temp_dir)
                shutil.copy2(temp_audio_path, final_audio_path)

                # Step 3: Transcription
                report_progress(3, "Transcribing audio...")
                transcript_data = transcriber.transcribe(final_audio_path)
                transcriber.unload_model()
                gc.collect()
                with open(transcript_file, "w", encoding="utf-8") as f:
                    json.dump(transcript_data, f, indent=2, ensure_ascii=False)

                # Step 4: Analyze audio + transcript
                report_progress(4, "Analyzing audio + transcript...")
                audio_analysis = audio_analyzer.analyze(final_audio_path)
                transcript_analyzer = TranscriptAnalyzer(transcript_data)
                effective_duration = video_duration if video_duration > 0 else audio_analysis.get("duration", 0.0)

                # Phase 12A/12B: Game Detection & Gameplay Event Timeline
                game_detector = GameDetector()
                game_profile = game_detector.detect_game(metadata=metadata, transcript_data=transcript_data, settings=settings)

                # Ensure Phase 12A visual detection gets appropriate video input
                is_long_vod = (
                    PARTIAL_DOWNLOAD_ENABLED
                    and is_remote_url(url)
                    and effective_duration > PARTIAL_DOWNLOAD_THRESHOLD_SEC
                    and not source_video_path.exists()
                )

                cv_video_path = None
                if phase_num >= 3 and game_profile.name != "generic":
                    if not source_video_path.exists():
                        if is_long_vod:
                            # Stage 1: Download lightweight 360p analysis proxy instead of full 1080p video
                            report_progress(4, "Acquiring lightweight 360p proxy for visual gameplay event detection...")
                            video_source_downloader = VideoSourceDownloader(temp_dir=job_temp_dir)
                            proxy_target = job_temp_dir / "analysis_proxy_360p.mp4"
                            proxy_result = video_source_downloader.download_analysis_proxy(
                                url=url, output_file=proxy_target, max_height=ANALYSIS_PROXY_MAX_HEIGHT
                            )
                            cv_video_path = proxy_result if (proxy_result and proxy_result.exists()) else None
                        else:
                            report_progress(4, "Acquiring source video for visual gameplay event detection...")
                            video_source_downloader = VideoSourceDownloader(temp_dir=job_temp_dir)
                            video_source_downloader.download_source_video(url=url, output_file=source_video_path)
                            cv_video_path = source_video_path
                    else:
                        cv_video_path = source_video_path

                gameplay_engine = GameplayEngine(profile=game_profile)
                gameplay_timeline = gameplay_engine.detect_events(
                    video_path=cv_video_path if (cv_video_path and cv_video_path.exists()) else None,
                    audio_analysis=audio_analysis,
                    transcript_data=transcript_data,
                    duration=effective_duration,
                )
                gameplay_events_file = job_output_dir / "gameplay_events.json"
                gameplay_timeline.save(gameplay_events_file)

                # Step 5: Generate & Rank Candidate Moments
                report_progress(5, f"Ranking candidate moments (Game Profile: {game_profile.display_name})...")
                candidates_raw = candidate_generator.generate_candidates(
                    video_duration=effective_duration,
                    audio_analysis=audio_analysis,
                    transcript_analyzer=transcript_analyzer,
                    gameplay_timeline=gameplay_timeline,
                )

                ranked_results = candidate_ranker.rank_candidates(
                    candidates=candidates_raw,
                    audio_analysis=audio_analysis,
                    transcript_analyzer=transcript_analyzer,
                    video_id=video_id,
                    video_duration=effective_duration,
                    top_k=10,
                    gameplay_timeline=gameplay_timeline,
                )
                ranked_results["game"] = game_profile.name
                ranked_results["game_archetype"] = game_profile.archetype
                ranked_results["detected_game_title"] = getattr(game_profile, "detected_title", None) or game_profile.display_name
                ranked_results["gameplay_events_file"] = str(gameplay_events_file)

                with open(candidates_file, "w", encoding="utf-8") as f:
                    json.dump(ranked_results, f, indent=2, ensure_ascii=False)

        # If only running up to Phase 2, return here
        if "game_profile" not in locals() or game_profile is None:
            game_detector = GameDetector()
            game_profile = game_detector.detect_game(metadata=metadata, transcript_data=transcript_data, settings=settings)

        effective_duration = video_duration if video_duration > 0 else float(ranked_results.get("duration", 0.0))
        all_candidates = ranked_results.get("candidates", [])

        # Phase 7E: Evaluate Creator Quality & Publishability for all candidates
        creator_evaluator = CreatorQualityEvaluator()
        transcript_words = transcript_data.get("words", []) if transcript_data else None
        for cand in all_candidates:
            if "publishability" not in cand:
                cand["publishability"] = creator_evaluator.evaluate(
                    candidate=cand,
                    transcript_words=transcript_words,
                    all_candidates=all_candidates,
                )

        if phase_num <= 2:
            if job_temp_dir.exists():
                shutil.rmtree(job_temp_dir, ignore_errors=True)

            return {
                "phase": phase_num,
                "video_id": video_id,
                "title": metadata["title"],
                "duration": effective_duration,
                "uploader": metadata["uploader"],
                "language": transcript_data.get("language", "en") if transcript_data else "en",
                "segments_count": len(transcript_data.get("segments", [])) if transcript_data else 0,
                "candidates_count": len(all_candidates),
                "candidates": all_candidates,
                "best_candidate": all_candidates[0] if all_candidates else None,
                "output_dir": job_output_dir,
                "metadata_file": metadata_file,
                "audio_file": final_audio_path,
                "transcript_file": transcript_file,
                "candidates_file": candidates_file,
                "long_stream": ranked_results.get("long_stream", is_long),
                "long_stream_info": ranked_results.get("long_stream_info"),
                "selected_candidate_ids": ranked_results.get("selected_candidate_ids"),
                "quality_gate_reason": ranked_results.get("quality_gate_reason"),
                "game": ranked_results.get("game", "generic"),
                "gameplay_events_file": ranked_results.get("gameplay_events_file"),
            }

        # ======================================================================
        # Phase 3: Video Acquisition, Layout Detection, Clipping & 9:16 Rendering
        # ======================================================================
        phase3_metadata_file = job_output_dir / "phase3_metadata.json"
        clips_dir = job_output_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        source_video_path = job_output_dir / "source.mp4"

        selected_candidates = all_candidates[:top_n]
        processed_candidates: List[Dict[str, Any]] = []
        resolved_layout = layout
        source_fps = 30.0
        source_duration = effective_duration
        facecam_info: Dict[str, Any] = {"facecam_detected": False}

        # Fast resumption if Phase 3 is already complete
        p3_cached = False
        user_wants_kf = str(kill_feed_setting).lower() in ("auto", "on", "true")
        has_roi = getattr(game_profile, "kill_feed_roi", None) is not None

        if phase3_metadata_file.exists():
            try:
                with open(phase3_metadata_file, "r", encoding="utf-8") as f:
                    p3_cached_data = json.load(f)
                cached_aspect = p3_cached_data.get("aspect_ratio", "9:16")
                cached_layout = p3_cached_data.get("layout_strategy", layout)
                cached_kf_overlay = p3_cached_data.get("kill_feed_overlay", False)
                expected_kf = bool(
                    user_wants_kf
                    and aspect_ratio == "9:16"
                    and cached_layout == LAYOUT_SMART_CROP
                    and has_roi
                )
                if cached_aspect != aspect_ratio or cached_kf_overlay != expected_kf:
                    p3_cached = False
                else:
                    cached_list = p3_cached_data.get("candidates", [])
                    if len(cached_list) >= min(top_n, len(selected_candidates)):
                        all_exist = all(Path(c.get("short_clip", "")).exists() for c in cached_list[:top_n])
                        if all_exist:
                            processed_candidates = cached_list[:top_n]
                            resolved_layout = p3_cached_data.get("layout_strategy", layout)
                            facecam_info = p3_cached_data.get("facecam_info", facecam_info)
                            source_fps = float(p3_cached_data.get("fps", 30.0))
                            source_duration = float(p3_cached_data.get("source_duration", effective_duration))
                            p3_cached = True
                            report_progress(6, "Source video already cached...")
                            report_progress(7, "Layout analysis cached...")
                            report_progress(8, f"Phase 3 vertical clips loaded from cache ({len(processed_candidates)} clips)...")
            except Exception:
                p3_cached = False

        if not p3_cached:
            phase3_start_time = time.perf_counter()

            # Determine whether to use two-stage partial segment downloads
            is_remote = is_remote_url(url)
            use_partial = (
                PARTIAL_DOWNLOAD_ENABLED
                and is_remote
                and effective_duration > PARTIAL_DOWNLOAD_THRESHOLD_SEC
                and not source_video_path.exists()
            )

            video_source_downloader = VideoSourceDownloader(temp_dir=temp_root)
            downloaded_segments: List[Dict[str, Any]] = []
            cand_to_segment: Dict[int, Dict[str, Any]] = {}
            total_seg_mb: float = 0.0
            source_fps: float = 30.0
            source_duration: float = effective_duration

            if use_partial:
                try:
                    report_progress(6, "Resolving 1080p stream URLs for partial segment download...")
                    stream_info = video_source_downloader.resolve_stream_urls(url, max_height=MAX_SOURCE_HEIGHT)
                    source_fps = stream_info.get("fps", 30.0)
                    source_duration = stream_info.get("duration", effective_duration)

                    # Build candidate intervals accounting for pre/post-roll padding
                    intervals = []
                    for cand in selected_candidates:
                        c_start = float(cand.get("start", cand.get("candidate_start", 0.0)))
                        c_end = float(cand.get("end", cand.get("candidate_end", 0.0)))
                        intervals.append((max(0.0, c_start - PRE_ROLL_SECONDS), c_end + POST_ROLL_SECONDS))

                    merged_segments = video_source_downloader.merge_clip_intervals(
                        intervals=intervals,
                        pad_sec=PARTIAL_SEGMENT_KEYFRAME_PAD_SEC,
                        merge_gap_sec=PARTIAL_SEGMENT_MERGE_GAP_SEC,
                        video_duration=source_duration,
                    )

                    segments_dir = job_output_dir / "segments"
                    segments_dir.mkdir(parents=True, exist_ok=True)

                    for seg_idx, seg in enumerate(merged_segments, start=1):
                        s_start = seg["seg_start"]
                        s_end = seg["seg_end"]
                        seg_path = segments_dir / f"seg_{int(s_start)}_{int(s_end)}.mp4"
                        report_progress(6, f"Downloading 1080p segment {seg_idx}/{len(merged_segments)} ({s_start:.1f}s - {s_end:.1f}s)...")
                        seg_res = video_source_downloader.download_segment(
                            url=url,
                            stream_info=stream_info,
                            seg_start=s_start,
                            seg_end=s_end,
                            output_path=seg_path,
                        )
                        downloaded_segments.append(seg_res)
                        total_seg_mb += seg_res.get("size_mb", 0.0)
                        for m_idx in seg.get("member_indices", []):
                            cand_to_segment[m_idx] = seg_res

                    report_progress(6, f"Downloaded {len(downloaded_segments)} segment(s) totaling {total_seg_mb:.1f} MB (saved full {source_duration/60:.0f}m VOD download)...")
                except Exception as e:
                    report_progress(6, f"Partial segment download failed ({e}); falling back to full source video download...")
                    use_partial = False
                    downloaded_segments = []
                    cand_to_segment = {}
                    total_seg_mb = 0.0

            if not use_partial:
                # Step 6: Acquire full source video
                report_progress(6, "Acquiring source video (single download)...")
                source_info = video_source_downloader.download_source_video(
                    url=url,
                    output_file=source_video_path,
                )
                source_fps = source_info.get("fps", 30.0)
                source_duration = source_info.get("duration", effective_duration)

            # Step 7: Layout and Facecam detection
            report_progress(7, "Analyzing video layout & facecam presence...")
            layout_detector = LayoutDetector()
            detection_video = downloaded_segments[0]["path"] if (use_partial and downloaded_segments) else source_video_path
            facecam_info = layout_detector.detect_facecam(detection_video)
            resolved_layout = layout_detector.resolve_layout(layout, facecam_info)
            use_kill_feed_pip = bool(
                user_wants_kf
                and aspect_ratio == "9:16"
                and resolved_layout == LAYOUT_SMART_CROP
                and has_roi
            )

            # Step 8: Sequential candidate clip extraction & vertical rendering
            report_progress(8, f"Processing top {top_n} candidates (Layout: {resolved_layout}, Kill-Feed PIP: {use_kill_feed_pip})...")
            clip_extractor = ClipExtractor()
            renderer = VerticalRenderer()
            validator = VideoValidator()

            processed_candidates = []

            for idx, cand in enumerate(selected_candidates, start=1):
                cand_idx_0 = idx - 1
                cand_start = float(cand["start"])
                cand_end = float(cand["end"])
                cand_score = float(cand.get("final_score", cand.get("score", 0.0)))

                report_progress(8, f"Processing candidate {idx}/{len(selected_candidates)} (Rank #{idx}, Score {cand_score:.1f})...")

                source_clip_file = clips_dir / f"candidate_{idx:02d}_source.mp4"
                short_clip_file = clips_dir / f"candidate_{idx:02d}_short.mp4"

                cand_record: Dict[str, Any] = {
                    "rank": idx,
                    "candidate_start": cand_start,
                    "candidate_end": cand_end,
                    "candidate_duration": round(cand_end - cand_start, 3),
                    "final_score": cand_score,
                    "component_scores": cand.get("component_scores", cand.get("scores", {})),
                    "gameplay_event_breakdown": cand.get("gameplay_event_breakdown", {}),
                    "detected_signals": cand.get("detected_signals", []),
                    "ranking_reasons": cand.get("ranking_reasons", []),
                    "source_clip": str(source_clip_file),
                    "short_clip": str(short_clip_file),
                    "layout": resolved_layout,
                    "aspect_ratio": aspect_ratio,
                    "kill_feed_overlay": use_kill_feed_pip,
                    "kill_feed_roi": list(game_profile.kill_feed_roi) if game_profile.kill_feed_roi else None,
                    "gameplay_events": cand.get("gameplay_events", []),
                    "gameplay_sequences": cand.get("gameplay_sequences", []),
                    "duration_tier": cand.get("duration_tier", get_duration_tier(cand_end - cand_start)),
                    "narrative_structure": cand.get("narrative_structure", get_narrative_structure(cand.get("duration_tier", "standard"))),
                    "game_archetype": cand.get("game_archetype", getattr(game_profile, "archetype", "generic")),
                    "effect_style": cand.get("effect_style", getattr(game_profile, "effect_style", "standard")),
                    "max_effects_per_minute": cand.get("max_effects_per_minute", getattr(game_profile, "max_effects_per_minute", 10)),
                    "detected_game_title": cand.get("detected_game_title", getattr(game_profile, "detected_title", None) or game_profile.display_name),
                }

                try:
                    # 8a: Extract source clip with padding
                    if use_partial and cand_idx_0 in cand_to_segment:
                        seg_info = cand_to_segment[cand_idx_0]
                        seg_path = seg_info["path"]
                        s_start = seg_info["seg_start"]
                        s_end = seg_info["seg_end"]
                        ext_info = clip_extractor.extract_candidate(
                            source_path=seg_path,
                            output_clip_path=source_clip_file,
                            candidate_start=cand_start - s_start,
                            candidate_end=cand_end - s_start,
                            pre_roll=PRE_ROLL_SECONDS,
                            post_roll=POST_ROLL_SECONDS,
                            source_duration=s_end - s_start,
                            global_offset=s_start,
                        )
                    else:
                        ext_info = clip_extractor.extract_candidate(
                            source_path=source_video_path,
                            output_clip_path=source_clip_file,
                            candidate_start=cand_start,
                            candidate_end=cand_end,
                            pre_roll=PRE_ROLL_SECONDS,
                            post_roll=POST_ROLL_SECONDS,
                            source_duration=source_duration,
                        )
                    cand_record["extraction_start"] = ext_info["extraction_start"]
                    cand_record["extraction_end"] = ext_info["extraction_end"]
                    cand_record["extraction_duration"] = ext_info["extraction_duration"]

                    # 8b: Render Short (9:16 or 1:1)
                    render_info = renderer.render_short(
                        input_clip_path=source_clip_file,
                        output_short_path=short_clip_file,
                        layout=resolved_layout,
                        facecam_region=facecam_info.get("region"),
                        source_fps=source_fps,
                        aspect_ratio=aspect_ratio,
                        kill_feed_overlay=use_kill_feed_pip,
                        kill_feed_roi=game_profile.kill_feed_roi,
                    )
                    cand_record["rendering_time_sec"] = render_info["rendering_time_sec"]
                    cand_record["encoder"] = render_info["encoder"]

                    # 8c: Validate rendered Short
                    val_result = validator.validate_short(
                        video_path=short_clip_file,
                        expected_duration=ext_info["extraction_duration"],
                        expected_width=output_width,
                        expected_height=output_height,
                        aspect_ratio=aspect_ratio,
                    )
                    cand_record["validation"] = val_result
                    cand_record["status"] = val_result["status"]

                except Exception as e:
                    cand_record["status"] = "FAIL"
                    cand_record["error"] = str(e)
                    cand_record["validation"] = {
                        "status": "FAIL",
                        "errors": [str(e)],
                        "checks": {},
                    }

                processed_candidates.append(cand_record)
                gc.collect()

            phase3_elapsed = round(time.perf_counter() - phase3_start_time, 2)

            # Step 9: Save phase3_metadata.json
            report_progress(9, "Generating Phase 3 metadata...")
            phase3_metadata: Dict[str, Any] = {
                "source_video_id": video_id,
                "source_title": metadata.get("title", "Unknown"),
                "source_duration": round(source_duration, 2),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "layout_strategy": resolved_layout,
                "aspect_ratio": aspect_ratio,
                "kill_feed_overlay": use_kill_feed_pip,
                "kill_feed_roi": list(game_profile.kill_feed_roi) if game_profile.kill_feed_roi else None,
                "facecam_detected": facecam_info.get("facecam_detected", False),
                "facecam_info": facecam_info,
                "output_resolution": {
                    "width": output_width,
                    "height": output_height,
                },
                "fps": source_fps,
                "encoder": "h264_nvenc" if renderer.nvenc_available else "libx264",
                "total_phase3_time_sec": phase3_elapsed,
                "download_mode": "partial_segments" if use_partial else "full_video",
                "segments_downloaded": len(downloaded_segments) if use_partial else 0,
                "total_downloaded_mb": round(total_seg_mb, 2) if use_partial else (round(source_video_path.stat().st_size / (1024 * 1024), 2) if source_video_path.exists() else 0.0),
                "shorts_requested": len(selected_candidates),
                "shorts_generated": sum(1 for c in processed_candidates if c.get("status") == "PASS"),
                "candidates": processed_candidates,
            }

            with open(phase3_metadata_file, "w", encoding="utf-8") as f:
                json.dump(phase3_metadata, f, indent=2, ensure_ascii=False)

        # If only running up to Phase 3, return here
        if phase_num <= 3:
            if job_temp_dir.exists():
                shutil.rmtree(job_temp_dir, ignore_errors=True)

            return {
                "phase": 3,
                "video_id": video_id,
                "title": metadata["title"],
                "duration": effective_duration,
                "uploader": metadata["uploader"],
                "language": transcript_data.get("language", "en"),
                "candidates_count": len(all_candidates),
                "top_candidates_processed": len(processed_candidates),
                "shorts_passed": sum(1 for c in processed_candidates if c.get("status") == "PASS"),
                "layout_used": resolved_layout,
                "output_dir": job_output_dir,
                "source_video_file": source_video_path,
                "metadata_file": metadata_file,
                "audio_file": final_audio_path,
                "transcript_file": transcript_file,
                "candidates_file": candidates_file,
                "phase3_metadata_file": phase3_metadata_file,
                "processed_candidates": processed_candidates,
            }

        # ======================================================================
        # Phase 4: Word-Level Subtitles, Karaoke Captions & Contextual Emojis
        # ======================================================================
        phase4_metadata_file = job_output_dir / "phase4_metadata.json"
        captions_dir = job_output_dir / "captions"
        captions_dir.mkdir(parents=True, exist_ok=True)

        phase4_candidates: List[Dict[str, Any]] = []
        p4_cached = False

        if phase_num >= 5 and phase4_metadata_file.exists():
            try:
                with open(phase4_metadata_file, "r", encoding="utf-8") as f:
                    p4_cached_data = json.load(f)
                cached_p4_list = p4_cached_data.get("candidates", [])
                if len(cached_p4_list) >= min(top_n, len(processed_candidates)):
                    if all(Path(c.get("captioned_clip", "")).exists() for c in cached_p4_list[:top_n]):
                        phase4_candidates = cached_p4_list[:top_n]
                        p4_cached = True
                        report_progress(10, "Phase 4 captions & emojis loaded from cache...")
                        report_progress(11, f"Phase 4 captioned videos loaded ({len(phase4_candidates)} clips)...")
            except Exception:
                p4_cached = False

        # Extract audio peaks for confidence alignment if audio is available
        audio_peaks: List[Dict[str, Any]] = []
        if final_audio_path.exists():
            try:
                audio_analyzer = AudioAnalyzer()
                audio_analysis = audio_analyzer.analyze(final_audio_path)
                audio_peaks = audio_analysis.get("peaks", [])
            except Exception:
                audio_peaks = []

        if not p4_cached:
            phase4_start_time = time.perf_counter()
            subtitle_mode = str(settings.get("subtitle_language", "auto")).lower() if settings else "auto"
            report_progress(10, f"Initializing Phase 4 subtitle & emoji engine (Mode: {subtitle_mode}, Captions: {captions}, Emojis: {emoji})...")

            # Phase 7D: Apply Hinglish Subtitle Normalization
            normalizer = HinglishNormalizer(mode=subtitle_mode)
            effective_transcript_data = normalizer.normalize_transcript(transcript_data)

            caption_engine = CaptionEngine()
            ass_generator = AssGenerator(
                output_width=output_width,
                output_height=output_height,
                aspect_ratio=aspect_ratio,
            )
            emoji_engine = EmojiEngine()
            caption_renderer = CaptionRenderer()
            subtitle_validator = SubtitleValidator(video_validator=VideoValidator())

            phase4_candidates = []

            for idx, cand in enumerate(processed_candidates, start=1):
                report_progress(11, f"Generating captions & burning subtitles for candidate {idx}/{len(processed_candidates)}...")

                short_clip_path = Path(cand["short_clip"])
                ext_start = float(cand.get("extraction_start", cand["candidate_start"]))
                ext_end = float(cand.get("extraction_end", cand["candidate_end"]))
                ext_duration = float(cand.get("extraction_duration", ext_end - ext_start))

                ass_file_path = captions_dir / f"candidate_{idx:02d}.ass"
                captioned_clip_path = captions_dir / f"candidate_{idx:02d}_captioned.mp4"
                cand_trans_path = captions_dir / f"candidate_{idx:02d}_transcript.json"

                # 1. Process candidate words into rhythmic 1-4 word groups
                caption_groups = []
                if captions:
                    caption_groups = caption_engine.process_candidate(
                        transcript_data=effective_transcript_data,
                        candidate_start=ext_start,
                        candidate_end=ext_end,
                        clip_duration=ext_duration,
                    )

                # 2. Contextual emoji detection
                emoji_events = []
                if emoji:
                    emoji_events = emoji_engine.detect_emojis(
                        transcript_data=effective_transcript_data,
                        clip_start=ext_start,
                        clip_end=ext_end,
                        audio_peaks=audio_peaks,
                        clip_duration=ext_duration,
                        gameplay_events=cand.get("gameplay_events", []),
                    )

                # 3. Generate and write ASS subtitle file
                ass_generator.write_ass_file(
                    output_path=ass_file_path,
                    caption_groups=caption_groups,
                    emoji_events=emoji_events,
                )

                # Save candidate-level normalized transcript contract (original vs normalized)
                cand_words = [
                    w for w in effective_transcript_data.get("words", [])
                    if ext_start <= float(w.get("start", 0.0)) < ext_end
                ]
                cand_contract = {
                    "candidate_id": idx,
                    "original_text": " ".join(str(w.get("original", w.get("word", ""))) for w in cand_words),
                    "normalized_text": " ".join(str(w.get("normalized", w.get("word", ""))) for w in cand_words),
                    "language": "hi-Latn" if subtitle_mode == "hinglish" else effective_transcript_data.get("language", "en"),
                    "subtitle_mode": subtitle_mode,
                    "confidence": 0.94 if cand_words else 1.0,
                    "words": cand_words,
                    "start": ext_start,
                    "end": ext_end,
                }
                with open(cand_trans_path, "w", encoding="utf-8") as f:
                    json.dump(cand_contract, f, indent=2, ensure_ascii=False)

                # 4. Burn subtitles onto 9:16 vertical Short
                cand_p4: Dict[str, Any] = dict(cand)
                cand_p4.update({
                    "ass_file": str(ass_file_path),
                    "captioned_clip": str(captioned_clip_path),
                    "caption_groups_count": len(caption_groups),
                    "words_count": sum(len(g.words) for g in caption_groups),
                    "emojis_count": len(emoji_events),
                    "emojis_detected": emoji_events,
                    "subtitle_mode": subtitle_mode,
                    "language": cand_contract["language"],
                    "normalized_transcript_file": str(cand_trans_path),
                    "aspect_ratio": aspect_ratio,
                })

                try:
                    render_res = caption_renderer.render_captioned_short(
                        short_video_path=short_clip_path,
                        ass_path=ass_file_path,
                        output_captioned_path=captioned_clip_path,
                    )
                    cand_p4["caption_render_time_sec"] = render_res["render_time_sec"]
                    cand_p4["caption_encoder"] = render_res["encoder"]

                    # 5. Technical and subtitle validation
                    val_res = subtitle_validator.validate_captioned_short(
                        video_path=captioned_clip_path,
                        ass_path=ass_file_path,
                        expected_duration=ext_duration,
                        expected_width=output_width,
                        expected_height=output_height,
                        aspect_ratio=aspect_ratio,
                        allow_empty_dialogue=(len(caption_groups) == 0),
                    )
                    cand_p4["subtitle_validation"] = val_res
                    cand_p4["phase4_status"] = "PASS" if val_res["valid"] else "FAIL"

                except Exception as e:
                    cand_p4["phase4_status"] = "FAIL"
                    cand_p4["phase4_error"] = str(e)
                    cand_p4["subtitle_validation"] = {
                        "valid": False,
                        "errors": [str(e)],
                    }

                phase4_candidates.append(cand_p4)
                gc.collect()

            phase4_elapsed = round(time.perf_counter() - phase4_start_time, 2)

            # Step 12: Write phase4_metadata.json
            report_progress(12, "Finalizing Phase 4 metadata and summary...")
            phase4_metadata: Dict[str, Any] = {
                "source_video_id": video_id,
                "source_title": metadata.get("title", "Unknown"),
                "source_duration": round(source_duration, 2),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "captions_enabled": captions,
                "emojis_enabled": emoji,
                "caption_style": {
                    "font": CAPTION_FONT_NAME,
                    "size": CAPTION_FONT_SIZE,
                    "active_color": CAPTION_ACTIVE_COLOR,
                    "base_color": CAPTION_BASE_COLOR,
                    "outline_width": CAPTION_OUTLINE_WIDTH,
                    "margin_v": CAPTION_MARGIN_V,
                },
                "emoji_style": {
                    "font": EMOJI_FONT_NAME,
                    "size": EMOJI_FONT_SIZE,
                    "margin_v": EMOJI_MARGIN_V,
                },
                "encoder": "h264_nvenc" if caption_renderer.nvenc_available else "libx264",
                "subtitle_mode": subtitle_mode,
                "language": effective_transcript_data.get("language", "en"),
                "hinglish_intelligence": effective_transcript_data.get("hinglish_intelligence"),
                "total_phase4_time_sec": phase4_elapsed,
                "shorts_captioned": sum(1 for c in phase4_candidates if c.get("phase4_status") == "PASS"),
                "candidates": phase4_candidates,
            }

            with open(phase4_metadata_file, "w", encoding="utf-8") as f:
                json.dump(phase4_metadata, f, indent=2, ensure_ascii=False)

        # If only running up to Phase 4, return here
        if phase_num <= 4:
            if job_temp_dir.exists():
                shutil.rmtree(job_temp_dir, ignore_errors=True)

            return {
                "phase": 4,
                "video_id": video_id,
                "title": metadata["title"],
                "duration": effective_duration,
                "uploader": metadata["uploader"],
                "language": transcript_data.get("language", "en"),
                "candidates_count": len(all_candidates),
                "top_candidates_processed": len(phase4_candidates),
                "shorts_passed": sum(1 for c in phase4_candidates if c.get("phase4_status") == "PASS"),
                "captions_enabled": captions,
                "emojis_enabled": emoji,
                "output_dir": job_output_dir,
                "captions_dir": captions_dir,
                "source_video_file": source_video_path,
                "metadata_file": metadata_file,
                "audio_file": final_audio_path,
                "transcript_file": transcript_file,
                "candidates_file": candidates_file,
                "phase3_metadata_file": phase3_metadata_file,
                "phase4_metadata_file": phase4_metadata_file,
                "processed_candidates": phase4_candidates,
            }

        # ======================================================================
        # Phase 5: Context-Aware Visual Effects Engine (Zoom, Shake, Flash)
        # ======================================================================
        phase5_metadata_file = job_output_dir / "phase5_metadata.json"
        effects_dir = job_output_dir / "effects"
        effects_dir.mkdir(parents=True, exist_ok=True)

        phase5_candidates: List[Dict[str, Any]] = []
        p5_cached = False

        if phase_num >= 6 and phase5_metadata_file.exists():
            try:
                with open(phase5_metadata_file, "r", encoding="utf-8") as f:
                    p5_cached_data = json.load(f)
                cached_p5_list = p5_cached_data.get("candidates", [])
                if len(cached_p5_list) >= min(top_n, len(phase4_candidates)):
                    if all(Path(c.get("final_clip", "")).exists() for c in cached_p5_list[:top_n]):
                        phase5_candidates = cached_p5_list[:top_n]
                        p5_cached = True
                        report_progress(13, "Visual effects & timelines loaded from cache...")
                        report_progress(14, f"Phase 5 final clips loaded ({len(phase5_candidates)} clips)...")
            except Exception:
                p5_cached = False

        if not p5_cached:
            phase5_start_time = time.perf_counter()
            report_progress(13, f"Initializing Phase 5 Visual Effects Engine (Effects: {effects})...")

            effect_engine = EffectEngine()
            effect_renderer = EffectRenderer()
            effect_validator = EffectValidator(video_validator=VideoValidator())

            phase5_candidates = []

            for idx, cand in enumerate(phase4_candidates, start=1):
                report_progress(14, f"Generating effect timeline & rendering visual effects for candidate {idx}/{len(phase4_candidates)}...")

                captioned_clip_path = Path(cand.get("captioned_clip", cand.get("short_clip")))
                ext_duration = float(cand.get("extraction_duration", 45.0))

                timeline_path = effects_dir / f"candidate_{idx:02d}_effect_timeline.json"
                final_video_path = effects_dir / f"candidate_{idx:02d}_final.mp4"

                # 1. Generate effect timeline
                if effects:
                    timeline = effect_engine.generate_timeline(
                        candidate_id=idx,
                        candidate=cand,
                        phase4_data=cand,
                        audio_peaks=audio_peaks,
                        facecam_info=facecam_info,
                    )
                else:
                    timeline = EffectTimeline(
                        candidate_id=idx,
                        candidate_duration=ext_duration,
                        effects=[],
                    )

                # 2. Write effect timeline JSON
                effect_engine.write_timeline_file(timeline_path, timeline)

                cand_p5: Dict[str, Any] = dict(cand)
                cand_p5.update({
                    "effect_timeline_file": str(timeline_path),
                    "final_clip": str(final_video_path),
                    "effects_count": len(timeline.effects),
                    "effects_breakdown": {
                        eff.type: sum(1 for e in timeline.effects if e.type == eff.type)
                        for eff in timeline.effects
                    },
                    "timeline_data": timeline.to_dict(),
                    "aspect_ratio": aspect_ratio,
                })

                # 3. Render final video with visual effects
                try:
                    render_res = effect_renderer.render_effects(
                        input_video_path=captioned_clip_path,
                        timeline=timeline,
                        output_video_path=final_video_path,
                        source_fps=source_fps,
                        facecam_info=facecam_info,
                        output_width=output_width,
                        output_height=output_height,
                        aspect_ratio=aspect_ratio,
                    )
                    cand_p5["effect_render_time_sec"] = render_res["render_time_sec"]
                    cand_p5["effect_encoder"] = render_res["encoder"]

                    # 4. Technical and timeline validation
                    val_res = effect_validator.validate_final_short(
                        video_path=final_video_path,
                        timeline_data=timeline,
                        expected_duration=ext_duration,
                        aspect_ratio=aspect_ratio,
                    )
                    cand_p5["effect_validation"] = val_res
                    cand_p5["phase5_status"] = "PASS" if val_res["valid"] else "FAIL"

                except Exception as e:
                    cand_p5["phase5_status"] = "FAIL"
                    cand_p5["phase5_error"] = str(e)
                    cand_p5["effect_validation"] = {
                        "valid": False,
                        "errors": [str(e)],
                    }

                phase5_candidates.append(cand_p5)
                gc.collect()

            phase5_elapsed = round(time.perf_counter() - phase5_start_time, 2)

            # Step 15: Save phase5_metadata.json
            report_progress(15, "Finalizing Phase 5 metadata and summary...")
            total_effects_applied = sum(len(c.get("timeline_data", {}).get("effects", [])) for c in phase5_candidates)
            all_effect_types_count: Dict[str, int] = {}
            for c in phase5_candidates:
                for eff in c.get("timeline_data", {}).get("effects", []):
                    t = eff.get("type", "unknown")
                    all_effect_types_count[t] = all_effect_types_count.get(t, 0) + 1

            phase5_metadata: Dict[str, Any] = {
                "source_video_id": video_id,
                "source_title": metadata.get("title", "Unknown"),
                "source_duration": round(source_duration, 2),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "effects_enabled": effects,
                "encoder": "h264_nvenc" if effect_renderer.nvenc_available else "libx264",
                "total_phase5_time_sec": phase5_elapsed,
                "shorts_completed": sum(1 for c in phase5_candidates if c.get("phase5_status") == "PASS"),
                "total_effects_applied": total_effects_applied,
                "effect_type_distribution": all_effect_types_count,
                "candidates": phase5_candidates,
            }

            with open(phase5_metadata_file, "w", encoding="utf-8") as f:
                json.dump(phase5_metadata, f, indent=2, ensure_ascii=False)

        # If only running up to Phase 5, return here
        if phase_num <= 5:
            if job_temp_dir.exists():
                shutil.rmtree(job_temp_dir, ignore_errors=True)

            return {
                "phase": 5,
                "video_id": video_id,
                "title": metadata["title"],
                "duration": effective_duration,
                "uploader": metadata["uploader"],
                "language": transcript_data.get("language", "en"),
                "candidates_count": len(all_candidates),
                "top_candidates_processed": len(phase5_candidates),
                "shorts_passed": sum(1 for c in phase5_candidates if c.get("phase5_status") == "PASS"),
                "captions_enabled": captions,
                "emojis_enabled": emoji,
                "effects_enabled": effects,
                "output_dir": job_output_dir,
                "captions_dir": captions_dir,
                "effects_dir": effects_dir,
                "source_video_file": source_video_path,
                "metadata_file": metadata_file,
                "audio_file": final_audio_path,
                "transcript_file": transcript_file,
                "candidates_file": candidates_file,
                "phase3_metadata_file": phase3_metadata_file,
                "phase4_metadata_file": phase4_metadata_file,
                "phase5_metadata_file": phase5_metadata_file,
                "processed_candidates": phase5_candidates,
            }

        # ======================================================================
        # Phase 6A: Audio Polish & SFX Engine (Whoosh, Impacts, Ducking & Normalization)
        # ======================================================================
        audio_dir = job_output_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        phase6a_metadata_file = job_output_dir / "phase6a_metadata.json"

        phase6a_candidates: List[Dict[str, Any]] = []
        phase6a_elapsed = 0.0
        all_sfx_types_count: Dict[str, int] = {}

        cached_p6a = False
        if phase_str in ["6b", "6B"] and phase6a_metadata_file.exists():
            try:
                with open(phase6a_metadata_file, "r", encoding="utf-8") as f:
                    cached_p6a_data = json.load(f)
                cached_cands = cached_p6a_data.get("candidates", [])
                if len(cached_cands) >= len(phase5_candidates) and all(Path(c.get("audio_polished_clip", "")).exists() for c in cached_cands[:len(phase5_candidates)]):
                    phase6a_candidates = cached_cands[:len(phase5_candidates)]
                    phase6a_elapsed = float(cached_p6a_data.get("total_phase6a_time_sec", 0.0))
                    all_sfx_types_count = cached_p6a_data.get("sfx_type_distribution", {})
                    cached_p6a = True
                    report_progress(16, f"Phase 6A polished audio shorts loaded from cache ({len(phase6a_candidates)} clips)...")
            except Exception:
                cached_p6a = False

        if not cached_p6a:
            phase6a_start_time = time.perf_counter()
            report_progress(16, f"Initializing Phase 6A Audio Polish & SFX Engine (SFX: {sfx}, Ducking: {ducking})...")

            sfx_library = SfxLibrary()
            audio_event_engine = AudioEventEngine(sfx_library=sfx_library)
            ducking_engine = DuckingEngine()
            audio_renderer = AudioRenderer(sfx_library=sfx_library, ducking_engine=ducking_engine)
            audio_validator = AudioValidator()

            for idx, cand in enumerate(phase5_candidates, start=1):
                report_progress(17, f"Generating audio timeline & speech ducking curves for candidate {idx}/{len(phase5_candidates)}...")

                p5_video_path = Path(cand.get("final_clip", cand.get("captioned_clip")))
                ext_duration = float(cand.get("extraction_duration", 45.0))

                audio_timeline_path = audio_dir / f"candidate_{idx:02d}_audio_timeline.json"
                final_audio_short_path = audio_dir / f"candidate_{idx:02d}_final.mp4"

                # 1. Compute speech-aware ducking plan
                ducking_summary = {}
                if ducking and transcript_data:
                    ducking_summary = ducking_engine.compute_ducking_plan(
                        transcript_data=transcript_data,
                        candidate=cand,
                        impact_events=cand.get("timeline_data", {}).get("effects", []),
                    )

                # 2. Generate synchronized audio event timeline
                if sfx and audio:
                    audio_timeline = audio_event_engine.generate_timeline(
                        candidate_id=idx,
                        candidate=cand,
                        phase5_timeline=cand.get("timeline_data"),
                        phase4_data=cand,
                        audio_peaks=audio_peaks,
                        ducking_summary=ducking_summary,
                    )
                else:
                    audio_timeline = AudioTimeline(
                        candidate_id=idx,
                        candidate_duration=ext_duration,
                        audio_events=[],
                        ducking_summary=ducking_summary,
                    )

                # 3. Write audio timeline JSON
                audio_event_engine.write_timeline_file(audio_timeline_path, audio_timeline)

                cand_p6: Dict[str, Any] = dict(cand)
                cand_p6.update({
                    "audio_timeline_file": str(audio_timeline_path),
                    "audio_polished_clip": str(final_audio_short_path),
                    "sfx_count": len(audio_timeline.audio_events),
                    "sfx_breakdown": {
                        ev.event_type: sum(1 for e in audio_timeline.audio_events if e.event_type == ev.event_type)
                        for ev in audio_timeline.audio_events
                    },
                    "ducking_intervals_count": ducking_summary.get("speech_intervals_count", 0),
                    "ducking_summary": ducking_summary,
                    "aspect_ratio": aspect_ratio,
                })

                # 4. Render final polished audio mix
                report_progress(18, f"Rendering polished audio mix (SFX + ducking + loudness normalization) for candidate {idx}/{len(phase5_candidates)}...")

                try:
                    render_res = audio_renderer.render_audio(
                        input_video_path=p5_video_path,
                        timeline=audio_timeline,
                        ducking_summary=ducking_summary,
                        output_video_path=final_audio_short_path,
                    )
                    cand_p6["audio_render_time_sec"] = render_res["render_time_sec"]
                    cand_p6["measured_lufs"] = render_res["measured_lufs"]
                    cand_p6["measured_tp"] = render_res["measured_tp"]

                    # 5. Technical and audio validation
                    expected_dur = float(cand.get("validation", {}).get("duration", ext_duration))
                    val_res = audio_validator.validate_final_audio_short(
                        video_path=final_audio_short_path,
                        timeline_data=audio_timeline,
                        expected_duration=expected_dur,
                        duration_tolerance_sec=2.5,
                    )
                    cand_p6["audio_validation"] = val_res
                    cand_p6["phase6a_status"] = "PASS" if val_res["valid"] else "FAIL"

                except Exception as e:
                    cand_p6["phase6a_status"] = "FAIL"
                    cand_p6["phase6a_error"] = str(e)
                    cand_p6["audio_validation"] = {
                        "valid": False,
                        "errors": [str(e)],
                    }

                phase6a_candidates.append(cand_p6)
                gc.collect()

            phase6a_elapsed = round(time.perf_counter() - phase6a_start_time, 2)

            # Step 19: Save phase6a_metadata.json
            report_progress(19, "Finalizing Phase 6A metadata and summary...")
            all_sfx_types_count = {}
            for c in phase6a_candidates:
                for sfx_type, count in c.get("sfx_breakdown", {}).items():
                    all_sfx_types_count[sfx_type] = all_sfx_types_count.get(sfx_type, 0) + count

            phase6a_metadata: Dict[str, Any] = {
                "phase": "6A",
                "source_video_id": video_id,
                "source_title": metadata.get("title", "Unknown"),
                "source_duration": round(source_duration, 2),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "audio_enabled": audio,
                "sfx_enabled": sfx,
                "ducking_enabled": ducking,
                "target_lufs": TARGET_LUFS,
                "true_peak_limit": TRUE_PEAK_LIMIT,
                "total_phase6a_time_sec": phase6a_elapsed,
                "shorts_completed": sum(1 for c in phase6a_candidates if c.get("phase6a_status") == "PASS"),
                "total_sfx_applied": sum(all_sfx_types_count.values()),
                "sfx_type_distribution": all_sfx_types_count,
                "candidates": phase6a_candidates,
            }

            with open(phase6a_metadata_file, "w", encoding="utf-8") as f:
                json.dump(phase6a_metadata, f, indent=2, ensure_ascii=False)

        if phase_str in ["6a", "6"]:
            # Clean temporary directory
            if job_temp_dir.exists():
                shutil.rmtree(job_temp_dir, ignore_errors=True)

            return {
                "phase": "6A",
                "video_id": video_id,
                "title": metadata["title"],
                "duration": effective_duration,
                "uploader": metadata["uploader"],
                "language": transcript_data.get("language", "en"),
                "candidates_count": len(all_candidates),
                "top_candidates_processed": len(phase6a_candidates),
                "shorts_passed": sum(1 for c in phase6a_candidates if c.get("phase6a_status") == "PASS"),
                "captions_enabled": captions,
                "emojis_enabled": emoji,
                "effects_enabled": effects,
                "audio_enabled": audio,
                "sfx_enabled": sfx,
                "ducking_enabled": ducking,
                "total_sfx_applied": sum(all_sfx_types_count.values()),
                "phase6a_time_sec": phase6a_elapsed,
                "output_dir": job_output_dir,
                "captions_dir": captions_dir,
                "effects_dir": effects_dir,
                "audio_dir": audio_dir,
                "source_video_file": source_video_path,
                "metadata_file": metadata_file,
                "audio_file": final_audio_path,
                "transcript_file": transcript_file,
                "candidates_file": candidates_file,
                "phase3_metadata_file": phase3_metadata_file,
                "phase4_metadata_file": phase4_metadata_file,
                "phase5_metadata_file": phase5_metadata_file,
                "phase6a_metadata_file": phase6a_metadata_file,
                "processed_candidates": phase6a_candidates,
            }

        # ======================================================================
        # Phase 6B: Metadata, Thumbnail & Publishing Package Engine
        # ======================================================================
        phase6b_start_time = time.perf_counter()
        report_progress(20, f"Initializing Phase 6B Publishing Package Engine (Thumbnail: {thumbnail}, Metadata: {metadata_enabled}, LLM: {llm})...")

        publishing_dir = job_output_dir / "publishing"
        publishing_dir.mkdir(parents=True, exist_ok=True)

        package_manager = PublishingPackageManager(
            summary_engine=ClipSummaryEngine(),
            thumbnail_engine=ThumbnailEngine(text_enabled=thumbnail),
            title_engine=TitleEngine(ollama_enabled=llm),
            description_engine=DescriptionEngine(),
            hashtag_engine=HashtagEngine(),
        )

        published_packages: List[Dict[str, Any]] = []
        existing_titles: List[str] = []
        existing_descriptions: List[str] = []

        for idx, cand in enumerate(phase6a_candidates, start=1):
            report_progress(21, f"Generating thumbnail, title & metadata package for candidate {idx}/{len(phase6a_candidates)}...")

            p5_tl_file = cand.get("effect_timeline_file")
            p5_tl = None
            if p5_tl_file and Path(p5_tl_file).exists():
                try:
                    with open(p5_tl_file, "r", encoding="utf-8") as f:
                        p5_tl = json.load(f)
                except Exception:
                    pass

            p6a_tl_file = cand.get("audio_timeline_file")
            p6a_tl = None
            if p6a_tl_file and Path(p6a_tl_file).exists():
                try:
                    with open(p6a_tl_file, "r", encoding="utf-8") as f:
                        p6a_tl = json.load(f)
                except Exception:
                    pass

            pkg_info = package_manager.build_candidate_package(
                candidate_idx=idx,
                candidate=cand,
                publishing_dir=publishing_dir,
                source_video_path=source_video_path if source_video_path.exists() else None,
                source_metadata=metadata,
                transcript_data=transcript_data,
                phase5_timeline=p5_tl,
                phase6a_timeline=p6a_tl,
                existing_titles=existing_titles,
                existing_descriptions=existing_descriptions,
                log_callback=lambda msg: report_progress(21, msg),
            )
            published_packages.append(pkg_info)
            existing_titles.append(pkg_info["title"])
            existing_descriptions.append(pkg_info.get("description", ""))
            gc.collect()

        # Step 22: Generate publishing manifest
        report_progress(22, "Generating master publishing_manifest.json...")
        manifest_file = package_manager.generate_publishing_manifest(
            publishing_dir=publishing_dir,
            packages=published_packages,
            source_metadata=metadata,
        )

        # Validate all packages with manifest reference
        for pkg in published_packages:
            val = package_manager.validate_package(Path(pkg["package_dir"]), manifest_path=manifest_file)
            pkg["validation"] = val

        phase6b_elapsed = round(time.perf_counter() - phase6b_start_time, 2)
        report_progress(23, "Finalizing Phase 6B publishing packages...")

        # Clean temporary directory
        if job_temp_dir.exists():
            shutil.rmtree(job_temp_dir, ignore_errors=True)

        return {
            "phase": "6B",
            "video_id": video_id,
            "title": metadata["title"],
            "duration": effective_duration,
            "uploader": metadata["uploader"],
            "language": transcript_data.get("language", "en"),
            "candidates_count": len(all_candidates),
            "top_candidates_processed": len(published_packages),
            "packages_passed": sum(1 for p in published_packages if p["validation"]["status"] == "PASS"),
            "captions_enabled": captions,
            "emojis_enabled": emoji,
            "effects_enabled": effects,
            "audio_enabled": audio,
            "sfx_enabled": sfx,
            "ducking_enabled": ducking,
            "thumbnail_enabled": thumbnail,
            "metadata_enabled": metadata_enabled,
            "llm_enabled": llm,
            "phase6b_time_sec": phase6b_elapsed,
            "output_dir": job_output_dir,
            "publishing_dir": publishing_dir,
            "manifest_file": manifest_file,
            "published_packages": published_packages,
        }

    except (DownloaderError, TranscriberError, AudioAnalyzerError, ClipExtractionError, RenderError, VideoValidationError, CaptionRenderError, EffectRenderError, AudioRenderError) as e:
        raise PipelineError(str(e)) from e
    except Exception as e:
        raise PipelineError(f"Unexpected pipeline error: {str(e)}") from e
