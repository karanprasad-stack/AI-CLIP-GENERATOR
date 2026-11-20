"""Unit tests for Two-Stage Partial YouTube VOD Downloader (Phase 13)."""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import shutil

from backend.app.config import (
    PARTIAL_DOWNLOAD_ENABLED,
    PARTIAL_DOWNLOAD_THRESHOLD_SEC,
    PARTIAL_SEGMENT_KEYFRAME_PAD_SEC,
    PARTIAL_SEGMENT_MERGE_GAP_SEC,
    ANALYSIS_PROXY_MAX_HEIGHT,
    PRE_ROLL_SECONDS,
    POST_ROLL_SECONDS,
)
from backend.app.pipeline.downloader import is_remote_url
from backend.app.pipeline.video_downloader import VideoSourceDownloader
from backend.app.pipeline.clip_extractor import ClipExtractor


class TestPartialYouTubeDownload(unittest.TestCase):
    """Tests for interval merging, FFmpeg range seeking, fallback, caching, and threshold gating."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.downloader = VideoSourceDownloader(temp_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 1. Interval Merging Tests
    # --------------------------------------------------------------------------
    def test_merge_clip_intervals_empty(self):
        res = VideoSourceDownloader.merge_clip_intervals([])
        self.assertEqual(res, [])

    def test_merge_clip_intervals_separate_clips_remain_separate(self):
        """Clips far apart (> 30s gap after 5s keyframe padding) do not merge."""
        # Clip 0: 100 to 130 (padded: 95 to 135)
        # Clip 1: 500 to 530 (padded: 495 to 535)
        intervals = [(100.0, 130.0), (500.0, 530.0)]
        merged = VideoSourceDownloader.merge_clip_intervals(
            intervals=intervals,
            pad_sec=5.0,
            merge_gap_sec=30.0,
            video_duration=1000.0,
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["seg_start"], 95.0)
        self.assertEqual(merged[0]["seg_end"], 135.0)
        self.assertEqual(merged[0]["member_indices"], [0])

        self.assertEqual(merged[1]["seg_start"], 495.0)
        self.assertEqual(merged[1]["seg_end"], 535.0)
        self.assertEqual(merged[1]["member_indices"], [1])

    def test_merge_clip_intervals_overlapping_and_nearby_merge(self):
        """Clips within <= 30s of each other merge into a shared segment."""
        # Clip 0: 100 to 140 (padded: 95 to 145)
        # Clip 1: 160 to 190 (padded: 155 to 195) -> gap between 145 and 155 is 10s <= 30s
        # Clip 2: 700 to 730 (padded: 695 to 735) -> far away
        intervals = [(100.0, 140.0), (160.0, 190.0), (700.0, 730.0)]
        merged = VideoSourceDownloader.merge_clip_intervals(
            intervals=intervals,
            pad_sec=5.0,
            merge_gap_sec=30.0,
            video_duration=1000.0,
        )
        self.assertEqual(len(merged), 2)
        # First merged segment combines clips 0 and 1
        self.assertEqual(merged[0]["seg_start"], 95.0)
        self.assertEqual(merged[0]["seg_end"], 195.0)
        self.assertEqual(merged[0]["member_indices"], [0, 1])

        # Second segment has clip 2 alone
        self.assertEqual(merged[1]["seg_start"], 695.0)
        self.assertEqual(merged[1]["seg_end"], 735.0)
        self.assertEqual(merged[1]["member_indices"], [2])

    def test_merge_clip_intervals_boundary_clamping(self):
        """Interval start does not go below 0.0 and end does not exceed video_duration."""
        intervals = [(2.0, 20.0), (95.0, 105.0)]
        merged = VideoSourceDownloader.merge_clip_intervals(
            intervals=intervals,
            pad_sec=5.0,
            merge_gap_sec=10.0,
            video_duration=100.0,
        )
        self.assertEqual(merged[0]["seg_start"], 0.0)
        self.assertEqual(merged[1]["seg_end"], 100.0)

    # --------------------------------------------------------------------------
    # 2. FFmpeg Range-Seek Command Structure Verification
    # --------------------------------------------------------------------------
    @patch("subprocess.run")
    def test_download_segment_ffmpeg_range_command_structure(self, mock_run):
        """Confirms -ss is placed strictly BEFORE -i for both video and audio streams with copy flags."""
        fake_output = self.temp_dir / "test_seg.mp4"

        # Mock probe_video so probe passes after download
        self.downloader.probe_video = MagicMock(return_value={
            "width": 1920,
            "height": 1080,
            "duration": 50.0,
            "fps": 30.0,
        })

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        # Create dummy file so output_path.exists() and size checks pass
        fake_output.write_bytes(b"0" * 20000)

        stream_info = {
            "video_url": "https://googlevideo.com/videoplayback?id=123",
            "audio_url": "https://googlevideo.com/videoplayback?id=456",
            "http_headers": {"User-Agent": "Mozilla/5.0 Test"},
            "fps": 60.0,
            "width": 1920,
            "height": 1080,
            "duration": 1800.0,
        }

        # Clear file before calling to test download path (not cache)
        fake_output.unlink()

        def side_effect(cmd, *args, **kwargs):
            # Simulate FFmpeg creating the file
            fake_output.write_bytes(b"0" * 20000)
            return mock_proc

        mock_run.side_effect = side_effect

        res = self.downloader.download_segment(
            url="https://youtube.com/watch?v=dQw4w9WgXcQ",
            stream_info=stream_info,
            seg_start=120.0,
            seg_end=170.0,
            output_path=fake_output,
        )

        self.assertEqual(res["method"], "ffmpeg_range")
        self.assertEqual(res["seg_start"], 120.0)
        self.assertEqual(res["seg_end"], 170.0)

        # Inspect exact FFmpeg command invoked
        cmd = mock_run.call_args[0][0]
        # Verify -ss strictly precedes -i
        video_url_idx = cmd.index(stream_info["video_url"])
        ss_video_idx = cmd.index("-ss")
        self.assertLess(ss_video_idx, video_url_idx, "-ss must precede video -i")

        # Verify second -ss precedes audio -i
        audio_url_idx = cmd.index(stream_info["audio_url"])
        indices_of_ss = [i for i, x in enumerate(cmd) if x == "-ss"]
        self.assertEqual(len(indices_of_ss), 2)
        self.assertLess(indices_of_ss[1], audio_url_idx, "second -ss must precede audio -i")

        # Verify required flags
        self.assertIn("-c", cmd)
        self.assertEqual(cmd[cmd.index("-c") + 1], "copy")
        self.assertIn("-avoid_negative_ts", cmd)
        self.assertEqual(cmd[cmd.index("-avoid_negative_ts") + 1], "make_zero")
        self.assertIn("-reconnect", cmd)
        self.assertIn("-user_agent", cmd)

    # --------------------------------------------------------------------------
    # 3. Fallback to yt-dlp download_ranges
    # --------------------------------------------------------------------------
    @patch("subprocess.run")
    @patch("yt_dlp.YoutubeDL")
    def test_download_segment_fallback_to_ytdlp(self, mock_ytdlp_cls, mock_run):
        """When FFmpeg range seek fails, it falls back cleanly to yt-dlp download_ranges."""
        fake_output = self.temp_dir / "test_fallback_seg.mp4"

        # Make FFmpeg fail
        mock_proc_fail = MagicMock()
        mock_proc_fail.returncode = 1
        mock_run.return_value = mock_proc_fail

        # Mock yt-dlp to write output
        mock_ydl_instance = MagicMock()
        mock_ytdlp_cls.return_value.__enter__.return_value = mock_ydl_instance

        def ytdlp_download(urls):
            # Simulate yt-dlp writing a file in temp
            temp_seg_dirs = list(self.temp_dir.glob("seg_fallback_*"))
            if temp_seg_dirs:
                (temp_seg_dirs[0] / "seg.mp4").write_bytes(b"0" * 25000)

        mock_ydl_instance.download.side_effect = ytdlp_download

        self.downloader.probe_video = MagicMock(return_value={
            "width": 1920,
            "height": 1080,
            "duration": 40.0,
            "fps": 30.0,
        })

        stream_info = {
            "video_url": "https://googlevideo.com/videoplayback?id=123",
            "audio_url": None,
            "http_headers": {},
        }

        res = self.downloader.download_segment(
            url="https://youtube.com/watch?v=dQw4w9WgXcQ",
            stream_info=stream_info,
            seg_start=50.0,
            seg_end=90.0,
            output_path=fake_output,
        )

        self.assertEqual(res["method"], "ytdlp_sections")
        self.assertTrue(fake_output.exists())

    # --------------------------------------------------------------------------
    # 4. Cache Hit Skips Network Download
    # --------------------------------------------------------------------------
    @patch("subprocess.run")
    def test_download_segment_cache_hit(self, mock_run):
        """Existing valid segment file returns immediately from cache without calling FFmpeg or yt-dlp."""
        fake_output = self.temp_dir / "cached_seg.mp4"
        fake_output.write_bytes(b"0" * 30000)

        self.downloader.probe_video = MagicMock(return_value={
            "width": 1920,
            "height": 1080,
            "duration": 60.0,
            "fps": 30.0,
        })

        res = self.downloader.download_segment(
            url="https://youtube.com/watch?v=dQw4w9WgXcQ",
            stream_info={"video_url": "dummy"},
            seg_start=10.0,
            seg_end=70.0,
            output_path=fake_output,
        )

        self.assertEqual(res["method"], "cache")
        # Subprocess run should NOT have been called for download
        mock_run.assert_not_called()

    # --------------------------------------------------------------------------
    # 5. Threshold Gating & Analysis Proxy
    # --------------------------------------------------------------------------
    def test_threshold_gating_logic(self):
        """VODs <= 15 min (900s) use full download; VODs > 900s use partial download."""
        remote_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        local_path = "D:/Videos/gameplay.mp4"

        self.assertTrue(is_remote_url(remote_url))
        self.assertFalse(is_remote_url(local_path))

        short_duration = 600.0  # 10 min
        long_duration = 7200.0  # 2 hours

        # Short video: not partial
        use_partial_short = (
            PARTIAL_DOWNLOAD_ENABLED
            and is_remote_url(remote_url)
            and short_duration > PARTIAL_DOWNLOAD_THRESHOLD_SEC
        )
        self.assertFalse(use_partial_short)

        # Long video: partial
        use_partial_long = (
            PARTIAL_DOWNLOAD_ENABLED
            and is_remote_url(remote_url)
            and long_duration > PARTIAL_DOWNLOAD_THRESHOLD_SEC
        )
        self.assertTrue(use_partial_long)

        # Local file: not partial even if long
        use_partial_local = (
            PARTIAL_DOWNLOAD_ENABLED
            and is_remote_url(local_path)
            and long_duration > PARTIAL_DOWNLOAD_THRESHOLD_SEC
        )
        self.assertFalse(use_partial_local)

    # --------------------------------------------------------------------------
    # 6. Segment-Relative Extraction Math & Global Offset Preservation
    # --------------------------------------------------------------------------
    @patch("subprocess.run")
    def test_clip_extractor_global_offset_preservation(self, mock_run):
        """Extracting from a segment with global_offset preserves exact global extraction timestamps."""
        fake_seg = self.temp_dir / "seg_90_190.mp4"
        fake_seg.write_bytes(b"0" * 20000)
        output_clip = self.temp_dir / "candidate_01_source.mp4"

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        extractor = ClipExtractor()
        # Mock NVENC check to avoid lavfi check in tests
        extractor._nvenc_available = False

        cand_start_global = 100.0
        cand_end_global = 160.0
        seg_start = 90.0
        seg_end = 190.0

        def side_effect(cmd, *args, **kwargs):
            output_clip.write_bytes(b"0" * 15000)
            return mock_proc

        mock_run.side_effect = side_effect

        # Relative candidate bounds: (100 - 90 = 10.0, 160 - 90 = 70.0)
        ext_info = extractor.extract_candidate(
            source_path=fake_seg,
            output_clip_path=output_clip,
            candidate_start=cand_start_global - seg_start,
            candidate_end=cand_end_global - seg_start,
            pre_roll=PRE_ROLL_SECONDS,
            post_roll=POST_ROLL_SECONDS,
            source_duration=seg_end - seg_start,
            global_offset=seg_start,
        )

        # Expected global extraction start: cand_start - PRE_ROLL_SECONDS (100.0 - 0.5 = 99.5)
        # Expected global extraction end: cand_end + POST_ROLL_SECONDS (160.0 + 0.5 = 160.5)
        self.assertEqual(ext_info["extraction_start"], 99.5)
        self.assertEqual(ext_info["extraction_end"], 160.5)
        self.assertEqual(ext_info["candidate_start"], 100.0)
        self.assertEqual(ext_info["candidate_end"], 160.0)
        self.assertEqual(ext_info["extraction_duration"], 61.0)

        # Inspect FFmpeg seek inside the segment:
        cmd = mock_run.call_args[0][0]
        ss_idx = cmd.index("-ss")
        # In-segment seek time: (10.0 - 0.5) = 9.5s
        self.assertEqual(cmd[ss_idx + 1], "9.500")


if __name__ == "__main__":
    unittest.main()
