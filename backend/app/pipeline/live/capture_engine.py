"""Rolling live stream capture layer with configurable segmentation and exponential backoff."""

import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import yt_dlp

from backend.app.config import (
    LIVE_SEGMENT_DURATION_SEC,
    LIVE_SEGMENT_OVERLAP_SEC,
    LIVE_MIN_SEGMENT_DURATION_SEC,
    LIVE_RECONNECT_MAX_ATTEMPTS,
    LIVE_RECONNECT_INITIAL_DELAY_SEC,
    LIVE_RECONNECT_BACKOFF_FACTOR,
    LIVE_RECONNECT_MAX_DELAY_SEC,
)
from backend.app.pipeline.downloader import VideoDownloader
from backend.app.pipeline.live.models import LiveSegment


class CaptureError(Exception):
    """Raised when live capture or segmentation fails."""
    pass


class LiveCaptureEngine:
    """Handles rolling capture of media segments from live streams or simulated sources."""

    def __init__(
        self,
        live_dir: Path,
        segment_duration: float = LIVE_SEGMENT_DURATION_SEC,
        segment_overlap: float = LIVE_SEGMENT_OVERLAP_SEC,
    ):
        self.live_dir = live_dir
        self.segments_dir = live_dir / "segments"
        self.segments_dir.mkdir(parents=True, exist_ok=True)

        self.segment_duration = float(segment_duration)
        self.segment_overlap = float(segment_overlap)
        self.step_sec = max(1.0, self.segment_duration - self.segment_overlap)

        self.downloader = VideoDownloader()
        self.ffmpeg_path = self.downloader.ffmpeg_path

    def compute_segment_timestamps(self, segment_id: int) -> Tuple[float, float, float]:
        """
        Calculates (global_start, global_end, duration) for a rolling segment.
        Segment index 1 starts at 0.0s.
        """
        idx = max(0, segment_id - 1)
        global_start = round(idx * self.step_sec, 2)
        duration = self.segment_duration
        global_end = round(global_start + duration, 2)
        return global_start, global_end, duration

    def extract_audio_wav(self, video_file: Path, output_wav: Path) -> Path:
        """Extracts 16kHz mono WAV from video segment for Whisper & audio intelligence."""
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        if output_wav.exists():
            output_wav.unlink(missing_ok=True)

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-nostats",
            "-loglevel", "error",
            "-i", str(video_file),
            "-ac", "1",
            "-ar", "16000",
            "-vn",
            str(output_wav),
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        except subprocess.TimeoutExpired as e:
            raise CaptureError(f"Audio extraction timed out for {video_file}: {e}") from e
        if res.returncode != 0 or not output_wav.exists() or output_wav.stat().st_size == 0:
            raise CaptureError(f"Audio extraction failed for {video_file}: {res.stderr}")
        return output_wav

    def capture_segment_simulated(
        self,
        source_video: Path,
        segment_id: int,
        source_duration: Optional[float] = None,
    ) -> Optional[LiveSegment]:
        """
        Extracts a rolling segment from a local source video for controlled simulation and testing.
        Simulates live stream arrival while maintaining identical segment boundaries and global timestamps.
        """
        if not source_video.exists():
            raise CaptureError(f"Simulation source video does not exist: {source_video}")

        global_start, global_end, target_dur = self.compute_segment_timestamps(segment_id)

        if source_duration and global_start >= source_duration:
            # Reached end of simulated stream
            return None

        actual_dur = target_dur
        if source_duration and (global_start + actual_dur > source_duration):
            actual_dur = max(0.0, source_duration - global_start)
            if actual_dur < LIVE_MIN_SEGMENT_DURATION_SEC:
                # Discard insignificant trailing tail
                return None

        video_path = self.segments_dir / f"segment_{segment_id:04d}.mp4"
        audio_path = self.segments_dir / f"segment_{segment_id:04d}.wav"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-nostats",
            "-loglevel", "error",
            "-ss", f"{global_start:.2f}",
            "-i", str(source_video),
            "-t", f"{actual_dur:.2f}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            str(video_path),
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        except subprocess.TimeoutExpired as e:
            raise CaptureError(f"Audio extraction timed out for {video_file}: {e}") from e
        if res.returncode != 0 or not video_path.exists():
            raise CaptureError(f"Simulated capture failed for segment {segment_id}: {res.stderr}")

        # Extract 16kHz audio
        self.extract_audio_wav(video_path, audio_path)

        file_size = video_path.stat().st_size + audio_path.stat().st_size

        return LiveSegment(
            segment_id=segment_id,
            local_start=0.0,
            local_end=actual_dur,
            global_start=global_start,
            global_end=round(global_start + actual_dur, 2),
            duration=round(actual_dur, 2),
            video_file=str(video_path),
            audio_file=str(audio_path),
            status="captured",
            file_size_bytes=file_size,
        )

    def capture_segment_live(
        self,
        stream_url: str,
        segment_id: int,
    ) -> Optional[LiveSegment]:
        """
        Captures a live segment incrementally from a live stream URL via yt-dlp/ffmpeg.
        Does NOT download the entire stream; writes only the discrete rolling window to disk.
        """
        global_start, global_end, target_dur = self.compute_segment_timestamps(segment_id)

        video_path = self.segments_dir / f"segment_{segment_id:04d}.mp4"
        audio_path = self.segments_dir / f"segment_{segment_id:04d}.wav"

        # Resolve live stream streamable URL
        clean_url = self.downloader.validate_live_url(stream_url)
        is_direct_hls = ".m3u8" in clean_url.lower()

        direct_stream_url = None
        if is_direct_hls:
            direct_stream_url = clean_url
        else:
            ydl_opts = self.downloader._build_ydl_opts({
                "format": "best[protocol^=m3u8_native]/best[protocol^=m3u8]/bestvideo+bestaudio/best",
            })

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(clean_url, download=False)
                    if info:
                        if info.get("is_live") is False and info.get("live_status") == "was_live":
                            raise CaptureError(f"Stream is not currently live (status: was_live): {clean_url}")
                        direct_stream_url = info.get("url")
                        if not direct_stream_url and "requested_formats" in info:
                            direct_stream_url = "\n".join(f.get("url", "") for f in info["requested_formats"] if f.get("url"))
            except Exception as e:
                if isinstance(e, CaptureError):
                    raise
                raise CaptureError(f"Failed to resolve live stream endpoint: {e}") from e

        if not direct_stream_url:
            direct_stream_url = clean_url

        stream_urls = [u.strip() for u in direct_stream_url.splitlines() if u.strip()]

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-nostats",
            "-loglevel", "error",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
        ]

        if len(stream_urls) >= 2:
            cmd.extend([
                "-i", stream_urls[0],
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
                "-i", stream_urls[1],
                "-t", f"{target_dur:.2f}",
                "-map", "0:v:0",
                "-map", "1:a:0?",
            ])
        else:
            url_to_use = stream_urls[0] if stream_urls else direct_stream_url
            cmd.extend([
                "-i", url_to_use,
                "-t", f"{target_dur:.2f}",
            ])

        cmd.extend([
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            str(video_path),
        ])

        capture_timeout = int(target_dur + 60)
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=capture_timeout)
        except subprocess.TimeoutExpired as e:
            raise CaptureError(f"Live segment capture timed out for {video_path}: {e}") from e
        if res.returncode != 0 or not video_path.exists() or video_path.stat().st_size == 0:
            raise CaptureError(f"Live segment capture failed: {res.stderr}")

        self.extract_audio_wav(video_path, audio_path)
        file_size = video_path.stat().st_size + audio_path.stat().st_size

        return LiveSegment(
            segment_id=segment_id,
            local_start=0.0,
            local_end=target_dur,
            global_start=global_start,
            global_end=global_end,
            duration=target_dur,
            video_file=str(video_path),
            audio_file=str(audio_path),
            status="captured",
            file_size_bytes=file_size,
        )

    def calculate_backoff_delay(self, attempt: int) -> float:
        """Computes exponential backoff delay with jitter for live reconnections."""
        delay = LIVE_RECONNECT_INITIAL_DELAY_SEC * (LIVE_RECONNECT_BACKOFF_FACTOR ** max(0, attempt - 1))
        return min(LIVE_RECONNECT_MAX_DELAY_SEC, delay)
