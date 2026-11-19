"""Audio extraction and metadata downloading using yt-dlp."""

from pathlib import Path
import os
import shutil
from typing import Dict, Any, Optional
import yt_dlp


class DownloaderError(Exception):
    """Raised when metadata extraction or audio download fails."""
    pass


def classify_download_error(err: Exception) -> str:
    """Translates yt-dlp technical errors into clean, human-readable explanations."""
    err_str = str(err).lower()
    if "private video" in err_str or "this video is private" in err_str or "sign in if you've been granted access" in err_str:
        return "This video is private. Please provide a public or unlisted YouTube video URL."
    if "video unavailable" in err_str or "this video does not exist" in err_str or "deleted" in err_str or "removed" in err_str:
        return "The requested video is deleted or unavailable on YouTube."
    if "sign in to confirm your age" in err_str or "age-restricted" in err_str:
        return "This video is age-restricted and cannot be processed in automated mode."
    if "not made this video available in your country" in err_str or "geo-restricted" in err_str or "country" in err_str:
        return "This video is geo-restricted and not available in your region."
    if "live stream recording is not available" in err_str or "premieres in" in err_str or "ongoing live stream" in err_str or "is live" in err_str:
        return "This live stream or premiere has not finished broadcasting and recording is not yet ready."
    if "unable to download webpage" in err_str or "connection refused" in err_str or "timed out" in err_str:
        return "Network connection to YouTube failed or timed out. Please check your internet connection."
    return f"Failed to retrieve video from YouTube: {str(err).split('ERROR:')[-1].strip()}"


class VideoDownloader:
    """Handles YouTube metadata extraction and audio-only extraction via yt-dlp."""

    def __init__(self, temp_dir: Optional[Path] = None):
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.temp_dir = temp_dir or (self.project_root / "temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.ffmpeg_path = self._locate_ffmpeg()
        self.deno_path = self._locate_deno()

    def _locate_ffmpeg(self) -> str:
        """Find the ffmpeg executable on PATH or known Windows install locations."""
        ffmpeg_in_path = shutil.which("ffmpeg")
        if ffmpeg_in_path:
            return ffmpeg_in_path

        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            winget_base = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if winget_base.exists():
                for candidate in winget_base.glob("**/ffmpeg.exe"):
                    return str(candidate)

        raise DownloaderError(
            "FFmpeg executable not found. Please install FFmpeg or ensure it is in PATH."
        )

    def _locate_deno(self) -> Optional[str]:
        """Find the Deno executable on PATH or default user install location."""
        deno_in_path = shutil.which("deno")
        if deno_in_path:
            return deno_in_path

        user_profile = os.environ.get("USERPROFILE", "")
        if user_profile:
            default_deno = Path(user_profile) / ".deno" / "bin" / "deno.exe"
            if default_deno.exists():
                return str(default_deno)

        return None

    def _build_ydl_opts(self, extra_opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build standard yt-dlp options configured with Deno and EJS remote components."""
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": self.ffmpeg_path,
            "remote_components": ["ejs:github", "ejs:npm"],
        }

        if self.deno_path:
            opts["js_runtimes"] = {"deno": {"path": self.deno_path}}
        else:
            opts["js_runtimes"] = {"deno": {}}

        if extra_opts:
            opts.update(extra_opts)

        return opts

    def validate_url(self, url: str) -> str:
        """Validate that the provided YouTube URL is not empty and reasonably formatted."""
        if not url or not url.strip():
            raise DownloaderError("The provided YouTube URL is empty.")

        clean_url = url.strip()
        if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            raise DownloaderError(f"Invalid URL schema. Expected 'http://' or 'https://': {clean_url}")

        valid_domains = ["youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com"]
        if not any(domain in clean_url for domain in valid_domains):
            raise DownloaderError(f"URL does not appear to be a YouTube link: {clean_url}")

        return clean_url

    def validate_live_url(self, url: str) -> str:
        """
        Validate that the provided live stream URL is not empty and is a valid live stream endpoint.
        Supports YouTube (/live/, @channel/live), Twitch, Kick, and direct HLS (.m3u8).
        """
        if not url or not url.strip():
            raise DownloaderError("The provided stream URL is empty.")

        clean_url = url.strip()
        if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            raise DownloaderError(f"Invalid URL schema. Expected 'http://' or 'https://': {clean_url}")

        valid_domains = [
            "youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com",
            "twitch.tv", "www.twitch.tv",
            "kick.com", "www.kick.com",
        ]
        is_known_platform = any(domain in clean_url.lower() for domain in valid_domains)
        is_m3u8 = ".m3u8" in clean_url.lower()

        if not (is_known_platform or is_m3u8):
            raise DownloaderError(f"URL does not appear to be a supported live stream platform or .m3u8 stream: {clean_url}")

        return clean_url

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        """Extract metadata for a YouTube URL without downloading video content."""
        clean_url = self.validate_url(url)
        opts = self._build_ydl_opts({"skip_download": True})

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                if not info:
                    raise DownloaderError(f"Unable to extract video information from {clean_url}")

                return {
                    "video_id": info.get("id", "unknown_id"),
                    "title": info.get("title", "Unknown Title"),
                    "duration": int(info.get("duration") or 0),
                    "uploader": info.get("uploader") or info.get("channel") or "Unknown Uploader",
                    "url": info.get("webpage_url") or clean_url,
                }
        except yt_dlp.utils.DownloadError as e:
            raise DownloaderError(classify_download_error(e)) from e
        except Exception as e:
            if isinstance(e, DownloaderError):
                raise
            raise DownloaderError(classify_download_error(e)) from e

    def download_audio(self, url: str, output_dir: Optional[Path] = None) -> Path:
        """
        Download only the audio stream and convert to 16kHz mono WAV format.
        Returns the Path to the generated WAV file.
        """
        clean_url = self.validate_url(url)
        target_dir = output_dir or self.temp_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        audio_output_template = target_dir / "audio.%(ext)s"
        expected_wav_path = target_dir / "audio.wav"

        # Remove existing file if present to guarantee clean output
        if expected_wav_path.exists():
            try:
                expected_wav_path.unlink()
            except OSError as e:
                raise DownloaderError(f"Failed to clear existing audio file at {expected_wav_path}: {e}")

        opts = self._build_ydl_opts({
            "format": "bestaudio/best",
            "outtmpl": str(audio_output_template),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }],
            "postprocessor_args": [
                "-ar", "16000",
                "-ac", "1",
            ],
        })

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([clean_url])

            if not expected_wav_path.exists():
                wav_candidates = list(target_dir.glob("*.wav"))
                if wav_candidates:
                    expected_wav_path = wav_candidates[0]
                else:
                    raise DownloaderError(f"WAV audio file was not produced in {target_dir}")

            if expected_wav_path.stat().st_size == 0:
                raise DownloaderError(f"Extracted audio file is 0 bytes: {expected_wav_path}")

            return expected_wav_path

        except yt_dlp.utils.DownloadError as e:
            raise DownloaderError(classify_download_error(e)) from e
        except Exception as e:
            if isinstance(e, DownloaderError):
                raise
            raise DownloaderError(classify_download_error(e)) from e
