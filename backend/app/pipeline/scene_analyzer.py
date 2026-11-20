"""Lightweight scene-cut and static lobby/menu analyzer using CPU OpenCV."""

from pathlib import Path
from typing import Dict, Any, List, Optional
import cv2
import numpy as np

# Guarantee CPU-only execution without OpenCL GPU context
cv2.ocl.setUseOpenCL(False)

from backend.app.config import (
    SCENE_STATIC_SCREEN_THRESHOLD,
    SCENE_CUT_CORRELATION_THRESHOLD,
)


class SceneAnalyzer:
    """Analyzes candidate video windows for static screens (loading/menu/lobby) and snaps hard scene-cut boundaries."""

    def __init__(
        self,
        static_threshold: float = SCENE_STATIC_SCREEN_THRESHOLD,
        scene_cut_threshold: float = SCENE_CUT_CORRELATION_THRESHOLD,
        sample_fps: float = 1.0,
    ):
        self.static_threshold = static_threshold
        self.scene_cut_threshold = scene_cut_threshold
        self.sample_fps = sample_fps

    def analyze_candidate(
        self,
        video_path: Optional[Path],
        start_sec: float,
        end_sec: float,
        has_high_speech_peak: bool = False,
    ) -> Dict[str, Any]:
        """
        Analyzes a candidate temporal window for:
        1. Static screen proportion (frozen/lobby/loading screens).
        2. Hard scene-cut boundary snapping within first/last 20% of the clip.
        """
        if not video_path:
            return {
                "is_static_screen": False,
                "static_ratio": 0.0,
                "scene_cuts": [],
                "adjusted_start": start_sec,
                "adjusted_end": end_sec,
                "reasons": [],
            }

        vpath = Path(video_path)
        if not vpath.exists():
            return {
                "is_static_screen": False,
                "static_ratio": 0.0,
                "scene_cuts": [],
                "adjusted_start": start_sec,
                "adjusted_end": end_sec,
                "reasons": [],
            }

        cap = cv2.VideoCapture(str(vpath))
        if not cap.isOpened():
            return {
                "is_static_screen": False,
                "static_ratio": 0.0,
                "scene_cuts": [],
                "adjusted_start": start_sec,
                "adjusted_end": end_sec,
                "reasons": [],
            }

        duration = max(0.1, end_sec - start_sec)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        max_source_sec = total_frames / fps if fps > 0 else end_sec

        # Generate sample timestamps at 1.0 FPS
        sample_times = []
        curr = start_sec + 0.5
        while curr < end_sec and curr <= max_source_sec:
            sample_times.append(curr)
            curr += (1.0 / self.sample_fps)

        if len(sample_times) < 2:
            cap.release()
            return {
                "is_static_screen": False,
                "static_ratio": 0.0,
                "scene_cuts": [],
                "adjusted_start": start_sec,
                "adjusted_end": end_sec,
                "reasons": [],
            }

        sampled_grays: List[np.ndarray] = []
        sampled_hists: List[np.ndarray] = []
        valid_times: List[float] = []

        try:
            for t in sample_times:
                f_idx = int(round(t * fps))
                cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue

                # Downscale to 320px width for fast CPU computation
                h, w = frame.shape[:2]
                scale = min(1.0, 320.0 / w)
                small = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                # Compute 2D HSV histogram (H: 16 bins, S: 16 bins)
                hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
                cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

                sampled_grays.append(gray)
                sampled_hists.append(hist)
                valid_times.append(t)
        finally:
            cap.release()

        if len(sampled_grays) < 2:
            return {
                "is_static_screen": False,
                "static_ratio": 0.0,
                "scene_cuts": [],
                "adjusted_start": start_sec,
                "adjusted_end": end_sec,
                "reasons": [],
            }

        # 1. Static Screen Detection (mean pixel diff between adjacent 1s frames)
        static_intervals = 0
        total_intervals = len(sampled_grays) - 1
        scene_cuts: List[float] = []

        for i in range(total_intervals):
            # Pixel difference
            diff = float(np.mean(cv2.absdiff(sampled_grays[i], sampled_grays[i + 1])))
            if diff < 2.0:
                static_intervals += 1

            # Histogram correlation for scene cut detection
            corr = cv2.compareHist(sampled_hists[i], sampled_hists[i + 1], cv2.HISTCMP_CORREL)
            if corr < self.scene_cut_threshold:
                scene_cuts.append(round(valid_times[i + 1], 2))

        static_ratio = static_intervals / total_intervals if total_intervals > 0 else 0.0
        is_static_screen = (static_ratio >= self.static_threshold) and (not has_high_speech_peak)

        reasons = []
        if is_static_screen:
            reasons.append(f"static screen detected ({int(static_ratio * 100)}% motionless frames)")

        # 2. Hard Scene-Cut Boundary Snapping (first 20% or last 20% of clip)
        adjusted_start = start_sec
        adjusted_end = end_sec

        early_threshold = start_sec + 0.20 * duration
        late_threshold = end_sec - 0.20 * duration

        for cut in scene_cuts:
            # Check early cut (snap start if remaining duration >= 15s)
            if start_sec < cut <= early_threshold:
                if (adjusted_end - cut) >= 15.0:
                    adjusted_start = cut
                    reasons.append(f"snapped start boundary to clean scene cut at {cut:.1f}s")
                    break

        for cut in reversed(scene_cuts):
            # Check late cut (snap end if remaining duration >= 15s)
            if late_threshold <= cut < end_sec:
                if (cut - adjusted_start) >= 15.0:
                    adjusted_end = cut
                    reasons.append(f"snapped end boundary to clean scene cut at {cut:.1f}s")
                    break

        return {
            "is_static_screen": is_static_screen,
            "static_ratio": round(static_ratio, 2),
            "scene_cuts": scene_cuts,
            "adjusted_start": round(adjusted_start, 2),
            "adjusted_end": round(adjusted_end, 2),
            "reasons": reasons,
        }

