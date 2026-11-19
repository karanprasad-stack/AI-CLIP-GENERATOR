"""Source video downloader using yt-dlp and FFmpeg."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import yt_dlp

from backend.app.config import MAX_SOURCE_HEIGHT
from backend.app.pipeline.downloader import VideoDownloader, DownloaderError, classify_download_error


class VideoSourceDownloader:
    """Handles downloading and caching the full source video once per job."""

    def __init__(self, temp_dir: Optional[Path] = None):
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.temp_dir = temp_dir or (self.project_root / "temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.downloader_base = VideoDownloader(temp_dir=self.temp_dir)
        self.ffmpeg_path = self.downloader_base.ffmpeg_path
        self.deno_path = self.downloader_base.deno_path

    def probe_video(self, video_path: Path) -> Dict[str, Any]:
        """Inspect video file using ffprobe and return stream metadata."""
        if not video_path.exists() or video_path.stat().st_size == 0:
            raise DownloaderError(f"Video file does not exist or is 0 bytes: {video_path}")

        ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate",
            "-of", "json",
            str(video_path)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, timeout=30)
            probe_data = json.loads(res.stdout)
        except Exception as e:
            raise DownloaderError(f"Failed to probe video at {video_path}: {e}") from e

        streams = probe_data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            raise DownloaderError(f"No video stream found in {video_path}")

        # Compute FPS
        fps = 30.0
        avg_rate = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "30/1"
        try:
            if "/" in avg_rate:
                num, den = avg_rate.split("/")
                fps = float(num) / float(den) if float(den) > 0 else 30.0
            else:
                fps = float(avg_rate)
        except Exception:
            fps = 30.0

        format_info = probe_data.get("format", {})
        duration = float(format_info.get("duration") or 0.0)

        return {
            "path": str(video_path),
            "width": int(video_stream.get("width") or 0),
            "height": int(video_stream.get("height") or 0),
            "duration": duration,
            "fps": round(fps, 3),
            "vcodec": video_stream.get("codec_name", "unknown"),
            "acodec": audio_stream.get("codec_name", "none") if audio_stream else "none",
            "size_bytes": video_path.stat().st_size,
        }

    def download_source_video(
        self,
        url: str,
        output_file: Path,
        max_height: int = MAX_SOURCE_HEIGHT,
        force_redownload: bool = False,
    ) -> Dict[str, Any]:
        """
        Download source video once up to max_height.
        If output_file already exists and is a valid video, reuses it without re-downloading.
        """
        clean_url = self.downloader_base.validate_url(url)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if not force_redownload and output_file.exists() and output_file.stat().st_size > 1024 * 1024:
            try:
                info = self.probe_video(output_file)
                if info["width"] > 0 and info["height"] > 0 and info["duration"] > 0:
                    return info
            except Exception:
                # File may be corrupt; re-download
                pass

        temp_target = self.temp_dir / f"download_source_{os.getpid()}"
        temp_target.mkdir(parents=True, exist_ok=True)
        temp_template = temp_target / "source.%(ext)s"

        format_selector = (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}]/best"
        )

        ydl_opts = self.downloader_base._build_ydl_opts({
            "format": format_selector,
            "outtmpl": str(temp_template),
            "merge_output_format": "mp4",
        })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([clean_url])

            downloaded_files = list(temp_target.glob("source.*"))
            if not downloaded_files:
                raise DownloaderError(f"No source video produced by yt-dlp in {temp_target}")

            produced_video = downloaded_files[0]
            if produced_video.suffix.lower() != ".mp4":
                # Ensure it is containerized as MP4
                converted_mp4 = temp_target / "source_converted.mp4"
                ffmpeg_cmd = [
                    self.ffmpeg_path,
                    "-y",
                    "-nostats",
                    "-loglevel", "error",
                    "-i", str(produced_video),
                    "-c", "copy",
                    str(converted_mp4)
                ]
                subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=120)
                produced_video = converted_mp4

            if output_file.exists():
                output_file.unlink()

            shutil.move(str(produced_video), str(output_file))
            shutil.rmtree(temp_target, ignore_errors=True)

            return self.probe_video(output_file)

        except yt_dlp.utils.DownloadError as e:
            raise DownloaderError(classify_download_error(e)) from e
        except Exception as e:
            if isinstance(e, DownloaderError):
                raise
            raise DownloaderError(classify_download_error(e)) from e
