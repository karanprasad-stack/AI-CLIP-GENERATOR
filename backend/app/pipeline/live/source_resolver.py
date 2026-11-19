"""Resolves continuous candidate source media from discrete rolling segments for Phase 8 Timeline & Rendering."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from backend.app.pipeline.downloader import VideoDownloader
from backend.app.pipeline.live.models import LiveSegment, LiveCandidate


class SourceResolverError(Exception):
    """Raised when source media cannot be resolved from live segments."""
    pass


class LiveSourceResolver:
    """Resolves single or multi-segment source clips for live candidates and Phase 8 Timeline/EDL."""

    def __init__(self, ffmpeg_path: Optional[str] = None):
        downloader = VideoDownloader()
        self.ffmpeg_path = ffmpeg_path or downloader.ffmpeg_path

    def find_segments_for_range(
        self,
        global_start: float,
        global_end: float,
        segments: List[LiveSegment],
    ) -> List[LiveSegment]:
        """Finds all active/retained segments that cover the specified global timestamp interval."""
        matching: List[LiveSegment] = []
        for seg in sorted(segments, key=lambda s: s.segment_id):
            if seg.status == "deleted":
                continue
            # Check for overlap between [global_start, global_end] and [seg.global_start, seg.global_end]
            if max(global_start, seg.global_start) < min(global_end, seg.global_end):
                matching.append(seg)
        return matching

    def resolve_source_clip(
        self,
        global_start: float,
        global_end: float,
        segments: List[LiveSegment],
        output_clip_path: Path,
    ) -> Path:
        """
        Extracts a seamless continuous source clip from rolling segments covering [global_start, global_end].
        Handles single-segment coverage and cross-segment splicing with exact sample alignment.
        """
        output_clip_path.parent.mkdir(parents=True, exist_ok=True)
        clip_duration = max(0.1, global_end - global_start)

        # 1. Locate relevant segments
        relevant = self.find_segments_for_range(global_start, global_end, segments)
        if not relevant:
            raise SourceResolverError(
                f"No retained media segments found for global range {global_start:.2f}s → {global_end:.2f}s"
            )

        # Case A: Entirely contained within a single segment
        for seg in relevant:
            if seg.global_start <= global_start and seg.global_end >= global_end:
                seg_path = Path(seg.video_file)
                if not seg_path.exists():
                    continue
                local_offset = max(0.0, global_start - seg.global_start)
                cmd = [
                    self.ffmpeg_path,
                    "-y",
                    "-nostats",
                    "-loglevel", "error",
                    "-ss", f"{local_offset:.3f}",
                    "-i", str(seg_path),
                    "-t", f"{clip_duration:.3f}",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "18",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    str(output_clip_path),
                ]
                try:
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
                except subprocess.TimeoutExpired:
                    res = subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="Timeout")
                if res.returncode == 0 and output_clip_path.exists() and output_clip_path.stat().st_size > 0:
                    return output_clip_path

        # Case B: Crosses multiple rolling segments (splicing with overlap de-duplication)
        # Slices non-overlapping sub-intervals from each sequential segment and stitches them
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            part_files: List[Path] = []
            cur_time = global_start

            for seg in relevant:
                if cur_time >= global_end:
                    break
                seg_file = Path(seg.video_file)
                if not seg_file.exists():
                    continue

                part_start_global = max(cur_time, seg.global_start)
                # Splicing point: either candidate end or segment end
                part_end_global = min(global_end, seg.global_end)

                # If next segment overlaps and starts before part_end_global, transition at next segment's start
                next_segs = [s for s in relevant if s.segment_id > seg.segment_id]
                if next_segs and next_segs[0].global_start < part_end_global:
                    part_end_global = next_segs[0].global_start

                part_dur = max(0.0, part_end_global - part_start_global)
                if part_dur <= 0.05:
                    continue

                local_ss = max(0.0, part_start_global - seg.global_start)
                part_mp4 = temp_path / f"part_{seg.segment_id:04d}.mp4"

                cmd = [
                    self.ffmpeg_path,
                    "-y",
                    "-nostats",
                    "-loglevel", "error",
                    "-ss", f"{local_ss:.3f}",
                    "-i", str(seg_file),
                    "-t", f"{part_dur:.3f}",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "18",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    str(part_mp4),
                ]
                try:
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
                except subprocess.TimeoutExpired:
                    res = subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="Timeout")
                if res.returncode == 0 and part_mp4.exists():
                    part_files.append(part_mp4)
                    cur_time = part_end_global

            if not part_files:
                raise SourceResolverError(
                    f"Failed to extract component media parts for range {global_start:.2f}s → {global_end:.2f}s"
                )

            if len(part_files) == 1:
                shutil.copy2(part_files[0], output_clip_path)
                return output_clip_path

            # Concat multiple parts into single file
            concat_list = temp_path / "concat.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for p in part_files:
                    f.write(f"file '{p.resolve().as_posix()}'\n")

            cmd = [
                self.ffmpeg_path,
                "-y",
                "-nostats",
                "-loglevel", "error",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                str(output_clip_path),
            ]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                res = subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="Timeout")
            if res.returncode != 0 or not output_clip_path.exists() or output_clip_path.stat().st_size == 0:
                # Re-encode concat fallback if copy fails
                cmd_reencode = [
                    self.ffmpeg_path,
                    "-y",
                    "-nostats",
                    "-loglevel", "error",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_list),
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "18",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    str(output_clip_path),
                ]
                subprocess.run(cmd_reencode, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=180)

        return output_clip_path
