"""Chunk Processor: executes memory-safe, time-bounded analysis on a single stream chunk."""

import gc
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from backend.app.config import (
    MIN_FREE_DISK_GB,
    MAX_DISK_USAGE_PCT,
    CLEANUP_CHUNK_AUDIO_IMMEDIATELY,
)
from backend.app.pipeline.transcriber import AudioTranscriber
from backend.app.pipeline.audio_analyzer import AudioAnalyzer
from backend.app.pipeline.transcript_analyzer import TranscriptAnalyzer
from backend.app.pipeline.candidate_generator import CandidateGenerator
from backend.app.pipeline.candidate_ranker import CandidateRanker
from .chunk_planner import ChunkPlan


class DiskSpaceError(Exception):
    """Raised when host disk space falls below safety thresholds."""
    pass


def check_disk_space(target_dir: Path, min_free_gb: float = MIN_FREE_DISK_GB, max_usage_pct: float = MAX_DISK_USAGE_PCT) -> None:
    """Verifies that sufficient disk space exists on the volume."""
    try:
        total, used, free = shutil.disk_usage(str(target_dir))
        free_gb = free / (1024 ** 3)
        usage_pct = (used / total) * 100.0 if total > 0 else 0.0

        if free_gb < min_free_gb:
            raise DiskSpaceError(
                f"Insufficient disk space for long-stream processing: {free_gb:.1f} GB available, "
                f"at least {min_free_gb:.1f} GB required."
            )
        if usage_pct > max_usage_pct:
            raise DiskSpaceError(
                f"Storage volume is {usage_pct:.1f}% full (limit: {max_usage_pct:.1f}%). "
                f"Processing paused to protect system drive."
            )
    except OSError:
        pass


def extract_chunk_audio(
    source_media: Path,
    chunk_start: float,
    chunk_duration: float,
    output_wav: Path,
) -> Path:
    """Uses FFmpeg to extract a precise temporal range into a mono 16kHz WAV."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{chunk_start:.2f}",
        "-t", f"{chunk_duration:.2f}",
        "-i", str(source_media),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_wav),
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"FFmpeg audio extraction timed out for chunk [{chunk_start}s + {chunk_duration}s]: {e}") from e
    if res.returncode != 0 or not output_wav.exists() or output_wav.stat().st_size == 0:
        err = res.stderr[-400:] if res.stderr else "Unknown FFmpeg error"
        raise RuntimeError(f"FFmpeg audio extraction failed for chunk [{chunk_start}s + {chunk_duration}s]: {err}")

    return output_wav


def convert_transcript_to_global_time(transcript_data: Dict[str, Any], offset_sec: float) -> Dict[str, Any]:
    """Converts relative chunk transcript timestamps into absolute global source timestamps."""
    global_segments = []
    global_words = []

    for seg in transcript_data.get("segments", []):
        seg_start = round(offset_sec + seg["start"], 2)
        seg_end = round(offset_sec + seg["end"], 2)

        seg_words = []
        for w in seg.get("words", []):
            w_start = round(offset_sec + w["start"], 2)
            w_end = round(offset_sec + w["end"], 2)
            clean_word = {
                "start": w_start,
                "end": w_end,
                "word": w["word"],
            }
            seg_words.append(clean_word)
            global_words.append(clean_word)

        global_segments.append({
            "start": seg_start,
            "end": seg_end,
            "text": seg["text"],
            "words": seg_words,
        })

    return {
        "language": transcript_data.get("language", "en"),
        "language_probability": transcript_data.get("language_probability", 1.0),
        "duration": transcript_data.get("duration", 0.0),
        "offset_sec": offset_sec,
        "segments": global_segments,
        "words": global_words,
    }


def convert_audio_analysis_to_global_time(audio_analysis: Dict[str, Any], offset_sec: float) -> Dict[str, Any]:
    """Shifts audio peaks, timeline timestamps, and silence intervals to global source time."""
    global_peaks = []
    for p in audio_analysis.get("peaks", []):
        gp = dict(p)
        gp["timestamp"] = round(offset_sec + p["timestamp"], 2)
        global_peaks.append(gp)

    global_timeline = []
    for pt in audio_analysis.get("timeline", []):
        gpt = dict(pt)
        gpt["t"] = round(offset_sec + pt["t"], 2)
        global_timeline.append(gpt)

    global_silences = []
    for sil in audio_analysis.get("silence_intervals", []):
        global_silences.append((
            round(offset_sec + sil[0], 2),
            round(offset_sec + sil[1], 2),
        ))

    return {
        "duration": audio_analysis.get("duration", 0.0),
        "global_mean_rms": audio_analysis.get("global_mean_rms", 0.0),
        "global_std_rms": audio_analysis.get("global_std_rms", 0.0),
        "timeline": global_timeline,
        "peaks": global_peaks,
        "silence_intervals": global_silences,
    }


class ChunkProcessor:
    """Executes sequential, memory-safe analysis for a single stream chunk."""

    def __init__(
        self,
        transcriber: Optional[AudioTranscriber] = None,
        audio_analyzer: Optional[AudioAnalyzer] = None,
        candidate_generator: Optional[CandidateGenerator] = None,
        candidate_ranker: Optional[CandidateRanker] = None,
    ):
        self.transcriber = transcriber or AudioTranscriber()
        self.audio_analyzer = audio_analyzer or AudioAnalyzer()
        self.candidate_generator = candidate_generator or CandidateGenerator()
        self.candidate_ranker = candidate_ranker or CandidateRanker()

    def process_chunk(
        self,
        source_media: Path,
        plan: ChunkPlan,
        temp_dir: Path,
        video_id: str,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Processes a single chunk, extracting audio, transcribing, detecting candidates, and cleaning up."""
        check_disk_space(temp_dir)

        chunk_audio_path = temp_dir / f"{plan.chunk_id}_audio.wav"

        try:
            if progress_cb:
                progress_cb(f"Extracting chunk audio for {plan.chunk_id} [{plan.source_start}s–{plan.source_end}s]...")

            extract_chunk_audio(
                source_media=source_media,
                chunk_start=plan.source_start,
                chunk_duration=plan.duration,
                output_wav=chunk_audio_path,
            )

            if progress_cb:
                progress_cb(f"Transcribing {plan.chunk_id} with faster-whisper...")

            raw_transcript = self.transcriber.transcribe(chunk_audio_path)
            global_transcript = convert_transcript_to_global_time(raw_transcript, plan.source_start)

            if progress_cb:
                progress_cb(f"Analyzing audio signal for {plan.chunk_id}...")

            raw_audio_analysis = self.audio_analyzer.analyze(chunk_audio_path)
            global_audio_analysis = convert_audio_analysis_to_global_time(raw_audio_analysis, plan.source_start)

            # Generate candidate moments within chunk
            transcript_analyzer = TranscriptAnalyzer(global_transcript)

            # Generate candidates anchored around signals
            raw_intervals = self.candidate_generator.generate_candidates(
                video_duration=plan.source_end,
                audio_analysis=global_audio_analysis,
                transcript_analyzer=transcript_analyzer,
            )

            # Filter candidates so they stay bounded within this chunk's window
            valid_intervals = [
                (max(plan.source_start, start), min(plan.source_end, end))
                for start, end in raw_intervals
                if end > start and (end - start) >= 15.0
            ]

            ranked = self.candidate_ranker.rank_candidates(
                candidates=valid_intervals,
                audio_analysis=global_audio_analysis,
                transcript_analyzer=transcript_analyzer,
                video_id=video_id,
                video_duration=plan.source_end,
                top_k=20,
            )

            candidates = ranked.get("candidates", [])
            for c in candidates:
                c["chunk_id"] = plan.chunk_id

            return {
                "chunk_id": plan.chunk_id,
                "index": plan.index,
                "source_start": plan.source_start,
                "source_end": plan.source_end,
                "duration": plan.duration,
                "status": "completed",
                "transcript": global_transcript,
                "audio_metrics": {
                    "mean_rms": round(float(raw_audio_analysis.get("global_mean_rms", 0.0)), 5),
                    "peaks_count": len(global_audio_analysis.get("peaks", [])),
                },
                "candidates": candidates,
            }

        finally:
            # Immediate cleanup of temporary WAV file to keep disk footprint minimal
            if CLEANUP_CHUNK_AUDIO_IMMEDIATELY and chunk_audio_path.exists():
                try:
                    chunk_audio_path.unlink()
                except Exception:
                    pass
            gc.collect()
