"""Source video downloader using yt-dlp and FFmpeg."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import yt_dlp

from backend.app.config import (
    MAX_SOURCE_HEIGHT,
    PARTIAL_SEGMENT_KEYFRAME_PAD_SEC,
    PARTIAL_SEGMENT_MERGE_GAP_SEC,
    ANALYSIS_PROXY_MAX_HEIGHT,
)
from backend.app.pipeline.downloader import VideoDownloader, DownloaderError, classify_download_error, is_remote_url


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

    def resolve_stream_urls(self, url: str, max_height: int = MAX_SOURCE_HEIGHT) -> Dict[str, Any]:
        """
        Resolve direct signed stream URLs for video and audio once via yt-dlp.
        Selects best video up to max_height and best audio stream.
        """
        clean_url = self.downloader_base.validate_url(url)
        format_selector = (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}]/best"
        )
        ydl_opts = self.downloader_base._build_ydl_opts({
            "format": format_selector,
            "skip_download": True,
        })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
        except Exception as e:
            raise DownloaderError(classify_download_error(e)) from e

        if not info:
            raise DownloaderError(f"Failed to extract stream information for {url}")

        requested_formats = info.get("requested_formats")
        video_url = ""
        audio_url: Optional[str] = None
        http_headers: Dict[str, str] = info.get("http_headers") or {}
        fps = 30.0
        width = 1920
        height = 1080

        if requested_formats and len(requested_formats) >= 2:
            v_fmt = next((f for f in requested_formats if f.get("vcodec") != "none"), requested_formats[0])
            a_fmt = next((f for f in requested_formats if f.get("acodec") != "none" and f.get("vcodec") == "none"), requested_formats[1])
            video_url = v_fmt.get("url") or ""
            audio_url = a_fmt.get("url")
            http_headers = v_fmt.get("http_headers") or info.get("http_headers") or {}
            fps = float(v_fmt.get("fps") or info.get("fps") or 30.0)
            width = int(v_fmt.get("width") or info.get("width") or 1920)
            height = int(v_fmt.get("height") or info.get("height") or 1080)
        elif requested_formats and len(requested_formats) == 1:
            fmt = requested_formats[0]
            video_url = fmt.get("url") or ""
            audio_url = None
            http_headers = fmt.get("http_headers") or info.get("http_headers") or {}
            fps = float(fmt.get("fps") or info.get("fps") or 30.0)
            width = int(fmt.get("width") or info.get("width") or 1920)
            height = int(fmt.get("height") or info.get("height") or 1080)
        else:
            video_url = info.get("url") or ""
            audio_url = None
            fps = float(info.get("fps") or 30.0)
            width = int(info.get("width") or 1920)
            height = int(info.get("height") or 1080)

        if not video_url:
            raise DownloaderError(f"Could not resolve playable video stream URL for {url}")

        duration = float(info.get("duration") or 0.0)
        title = str(info.get("title") or "")

        return {
            "video_url": video_url,
            "audio_url": audio_url,
            "http_headers": http_headers,
            "fps": round(fps, 3),
            "width": width,
            "height": height,
            "duration": duration,
            "title": title,
        }

    @staticmethod
    def merge_clip_intervals(
        intervals: List[Tuple[float, float]],
        pad_sec: float = PARTIAL_SEGMENT_KEYFRAME_PAD_SEC,
        merge_gap_sec: float = PARTIAL_SEGMENT_MERGE_GAP_SEC,
        video_duration: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Each input interval (cand_start, cand_end) is expanded by pad_sec on both sides
        (clamped to [0.0, video_duration]).
        Sort and merge any intervals where next_start <= current_end + merge_gap_sec.
        Returns a list of merged segment specs:
        [{"seg_start": float, "seg_end": float, "member_indices": List[int]}]
        """
        if not intervals:
            return []

        expanded: List[Tuple[float, float, int]] = []
        for idx, (s, e) in enumerate(intervals):
            pad_s = max(0.0, float(s) - pad_sec)
            pad_e = float(e) + pad_sec
            if video_duration and video_duration > 0:
                pad_e = min(float(video_duration), pad_e)
                pad_s = min(pad_s, pad_e)
            expanded.append((pad_s, pad_e, idx))

        expanded.sort(key=lambda x: (x[0], x[1]))

        merged: List[Dict[str, Any]] = []
        for s, e, orig_idx in expanded:
            if not merged:
                merged.append({
                    "seg_start": round(s, 3),
                    "seg_end": round(e, 3),
                    "member_indices": [orig_idx],
                })
            else:
                curr = merged[-1]
                if s <= curr["seg_end"] + merge_gap_sec:
                    curr["seg_end"] = round(max(curr["seg_end"], e), 3)
                    if orig_idx not in curr["member_indices"]:
                        curr["member_indices"].append(orig_idx)
                else:
                    merged.append({
                        "seg_start": round(s, 3),
                        "seg_end": round(e, 3),
                        "member_indices": [orig_idx],
                    })

        for item in merged:
            item["member_indices"].sort()

        return merged

    def download_segment(
        self,
        url: str,
        stream_info: Dict[str, Any],
        seg_start: float,
        seg_end: float,
        output_path: Path,
    ) -> Dict[str, Any]:
        """
        Download a specific 1080p time segment using HTTP Range input-seeking.
        Falls back to yt-dlp download_ranges if FFmpeg range seek fails.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Cache check
        if output_path.exists() and output_path.stat().st_size > 10_000:
            try:
                probe = self.probe_video(output_path)
                if probe["width"] > 0 and probe["height"] > 0 and probe["duration"] > 0:
                    return {
                        "path": output_path,
                        "seg_start": seg_start,
                        "seg_end": seg_end,
                        "size_mb": round(output_path.stat().st_size / (1024 * 1024), 2),
                        "method": "cache",
                    }
            except Exception:
                pass  # Corrupt or invalid cached file; re-download

        seg_duration = max(0.5, seg_end - seg_start)
        video_url = stream_info.get("video_url")
        audio_url = stream_info.get("audio_url")
        headers = stream_info.get("http_headers", {})
        user_agent = headers.get("User-Agent") or headers.get("user-agent")

        # 2. Primary Path: Direct FFmpeg HTTP Range Input-Seeking
        if video_url:
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-nostats",
                "-loglevel", "error",
            ]
            cmd.extend(["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"])
            if user_agent:
                cmd.extend(["-user_agent", str(user_agent)])
            cmd.extend(["-ss", f"{seg_start:.3f}", "-i", video_url])

            if audio_url and audio_url != video_url:
                cmd.extend(["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"])
                if user_agent:
                    cmd.extend(["-user_agent", str(user_agent)])
                cmd.extend(["-ss", f"{seg_start:.3f}", "-i", audio_url])

            cmd.extend(["-t", f"{seg_duration:.3f}"])

            if audio_url and audio_url != video_url:
                cmd.extend(["-map", "0:v:0", "-map", "1:a:0?"])
            else:
                cmd.extend(["-map", "0:v:0", "-map", "0:a:0?"])

            cmd.extend([
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-movflags", "+faststart",
                str(output_path),
            ])

            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
                if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 10_000:
                    probe = self.probe_video(output_path)
                    if probe["width"] > 0 and probe["height"] > 0:
                        return {
                            "path": output_path,
                            "seg_start": seg_start,
                            "seg_end": seg_end,
                            "size_mb": round(output_path.stat().st_size / (1024 * 1024), 2),
                            "method": "ffmpeg_range",
                        }
            except Exception:
                pass  # Fall through to Fallback 1

        # 3. Fallback 1: yt-dlp download_ranges
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception:
                pass

        temp_seg_dir = self.temp_dir / f"seg_fallback_{os.getpid()}_{int(seg_start)}_{int(seg_end)}"
        temp_seg_dir.mkdir(parents=True, exist_ok=True)
        temp_out = temp_seg_dir / "seg.%(ext)s"

        format_selector = (
            f"bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<=1080]+bestaudio/"
            f"best[height<=1080]/best"
        )

        clean_url = self.downloader_base.validate_url(url)
        ydl_opts = self.downloader_base._build_ydl_opts({
            "format": format_selector,
            "outtmpl": str(temp_out),
            "download_ranges": yt_dlp.utils.download_range_func(None, [(seg_start, seg_end)]),
            "force_keyframes_at_cuts": True,
            "merge_output_format": "mp4",
        })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([clean_url])

            downloaded = list(temp_seg_dir.glob("seg.*"))
            if not downloaded:
                raise DownloaderError(f"yt-dlp range download produced no file in {temp_seg_dir}")

            produced = downloaded[0]
            if produced.suffix.lower() != ".mp4":
                conv_mp4 = temp_seg_dir / "seg_converted.mp4"
                c_cmd = [
                    self.ffmpeg_path,
                    "-y",
                    "-nostats",
                    "-loglevel", "error",
                    "-i", str(produced),
                    "-c", "copy",
                    str(conv_mp4),
                ]
                subprocess.run(c_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=120)
                produced = conv_mp4

            shutil.move(str(produced), str(output_path))
            shutil.rmtree(temp_seg_dir, ignore_errors=True)

            probe = self.probe_video(output_path)
            return {
                "path": output_path,
                "seg_start": seg_start,
                "seg_end": seg_end,
                "size_mb": round(output_path.stat().st_size / (1024 * 1024), 2),
                "method": "ytdlp_sections",
            }
        except Exception as e:
            shutil.rmtree(temp_seg_dir, ignore_errors=True)
            if isinstance(e, DownloaderError):
                raise
            raise DownloaderError(f"Failed to download 1080p segment [{seg_start:.1f} - {seg_end:.1f}]: {e}") from e

    def download_analysis_proxy(
        self,
        url: str,
        output_file: Path,
        max_height: int = ANALYSIS_PROXY_MAX_HEIGHT,
    ) -> Optional[Path]:
        """
        Download a lightweight video-only 360p analysis proxy for long-VOD visual CV.
        Returns None gracefully on error so audio/transcript analysis can proceed.
        """
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if output_file.exists() and output_file.stat().st_size > 10_000:
            try:
                probe = self.probe_video(output_file)
                if probe["width"] > 0 and probe["height"] > 0:
                    return output_file
            except Exception:
                pass

        temp_proxy_dir = self.temp_dir / f"proxy_{os.getpid()}"
        temp_proxy_dir.mkdir(parents=True, exist_ok=True)
        temp_template = temp_proxy_dir / "proxy.%(ext)s"

        format_selector = (
            f"bestvideo[height<={max_height}][ext=mp4]/"
            f"bestvideo[height<={max_height}]/"
            f"worst[ext=mp4]/"
            f"worst"
        )

        try:
            clean_url = self.downloader_base.validate_url(url)
            ydl_opts = self.downloader_base._build_ydl_opts({
                "format": format_selector,
                "outtmpl": str(temp_template),
                "merge_output_format": "mp4",
            })
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([clean_url])

            downloaded = list(temp_proxy_dir.glob("proxy.*"))
            if not downloaded:
                shutil.rmtree(temp_proxy_dir, ignore_errors=True)
                return None

            produced = downloaded[0]
            if produced.suffix.lower() != ".mp4":
                conv_mp4 = temp_proxy_dir / "proxy_converted.mp4"
                c_cmd = [
                    self.ffmpeg_path,
                    "-y",
                    "-nostats",
                    "-loglevel", "error",
                    "-i", str(produced),
                    "-c", "copy",
                    str(conv_mp4),
                ]
                subprocess.run(c_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=120)
                produced = conv_mp4

            if output_file.exists():
                output_file.unlink()

            shutil.move(str(produced), str(output_file))
            shutil.rmtree(temp_proxy_dir, ignore_errors=True)
            return output_file
        except Exception:
            shutil.rmtree(temp_proxy_dir, ignore_errors=True)
            return None
