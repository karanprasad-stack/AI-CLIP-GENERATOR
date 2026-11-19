"""Unit tests for Live Stream URL Clipping, format handling, and capture engine stability."""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import subprocess

from backend.app.pipeline.downloader import VideoDownloader, DownloaderError
from backend.app.pipeline.live.capture_engine import LiveCaptureEngine, CaptureError


class TestLiveStreamUrlFix(unittest.TestCase):
    """Test suite for live stream URL validation and capture engine stability."""

    def setUp(self):
        self.downloader = VideoDownloader()

    def test_validate_live_url_valid_platforms(self):
        """Verify that YouTube live, Twitch, Kick, and direct HLS .m3u8 URLs pass validation."""
        valid_urls = [
            "https://www.youtube.com/watch?v=liveStreamId",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
            "https://youtube.com/@esl_csgo/live",
            "https://twitch.tv/shroud",
            "https://www.twitch.tv/tarik",
            "https://kick.com/xqc",
            "https://stream.provider.com/live/master.m3u8",
            "https://cdn.example.org/hls/live_720p.m3u8?token=abc123xyz",
        ]
        for url in valid_urls:
            validated = self.downloader.validate_live_url(url)
            self.assertEqual(validated, url.strip())

    def test_validate_live_url_invalid(self):
        """Verify that empty, non-http, or unsupported domains raise DownloaderError."""
        invalid_urls = [
            "",
            "   ",
            "ftp://twitch.tv/stream",
            "random string",
            "https://unsupported-site.com/video",
        ]
        for url in invalid_urls:
            with self.assertRaises(DownloaderError):
                self.downloader.validate_live_url(url)

    @patch("backend.app.pipeline.live.capture_engine.subprocess.run")
    def test_capture_segment_direct_m3u8_bypasses_ytdlp(self, mock_subproc):
        """Verify that direct .m3u8 stream URLs bypass yt-dlp extraction and construct FFmpeg command directly."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_subproc.return_value = mock_proc

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            engine = LiveCaptureEngine(live_dir=Path(tmp_dir), segment_duration=15.0)

            # Create mock dummy output files so stat checks pass
            seg_video = engine.segments_dir / "segment_0001.mp4"
            seg_video.write_bytes(b"dummy_video_bytes")
            seg_audio = engine.segments_dir / "segment_0001.wav"
            seg_audio.write_bytes(b"dummy_audio_bytes")

            with patch.object(engine, "extract_audio_wav") as mock_extract:
                m3u8_url = "https://example.com/live/stream.m3u8"
                seg = engine.capture_segment_live(stream_url=m3u8_url, segment_id=1)

                self.assertIsNotNone(seg)
                self.assertEqual(seg.segment_id, 1)

                # Check FFmpeg command passed to subprocess.run
                cmd = mock_subproc.call_args[0][0]
                self.assertIn("-reconnect", cmd)
                self.assertIn("-reconnect_streamed", cmd)
                self.assertIn(m3u8_url, cmd)
                self.assertIn("-t", cmd)
                # Timeout must be target_dur + 60 = 75
                self.assertEqual(mock_subproc.call_args[1].get("timeout"), 75)

    @patch("backend.app.pipeline.live.capture_engine.yt_dlp.YoutubeDL")
    @patch("backend.app.pipeline.live.capture_engine.subprocess.run")
    def test_capture_segment_multiline_urls_handled(self, mock_subproc, mock_ydl_cls):
        """Verify that dual video/audio stream URLs returned by yt-dlp are mapped into dual inputs."""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "url": "https://stream.yt.com/video_hls.m3u8\nhttps://stream.yt.com/audio_hls.m3u8",
            "is_live": True,
        }

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_subproc.return_value = mock_proc

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            engine = LiveCaptureEngine(live_dir=Path(tmp_dir), segment_duration=30.0)

            seg_video = engine.segments_dir / "segment_0001.mp4"
            seg_video.write_bytes(b"dummy_video_bytes")
            seg_audio = engine.segments_dir / "segment_0001.wav"
            seg_audio.write_bytes(b"dummy_audio_bytes")

            with patch.object(engine, "extract_audio_wav"):
                seg = engine.capture_segment_live(stream_url="https://www.youtube.com/live/12345678901", segment_id=1)
                self.assertIsNotNone(seg)

                cmd = mock_subproc.call_args[0][0]
                # Must contain both -i inputs and mappings
                self.assertIn("https://stream.yt.com/video_hls.m3u8", cmd)
                self.assertIn("https://stream.yt.com/audio_hls.m3u8", cmd)
                self.assertIn("-map", cmd)
                self.assertIn("0:v:0", cmd)
                self.assertIn("1:a:0?", cmd)

    @patch("backend.app.pipeline.live.capture_engine.yt_dlp.YoutubeDL")
    def test_capture_segment_offline_stream_detected(self, mock_ydl_cls):
        """Verify that offline / ended streams are identified and raise CaptureError."""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "is_live": False,
            "live_status": "was_live",
        }

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            engine = LiveCaptureEngine(live_dir=Path(tmp_dir), segment_duration=30.0)
            with self.assertRaises(CaptureError) as ctx:
                engine.capture_segment_live(stream_url="https://www.youtube.com/live/endedStream", segment_id=1)
            self.assertIn("not currently live", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
