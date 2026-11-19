"""Valorant Kill Feed visual detector using ROI frame differencing, color profiles, and headshot detection."""

import cv2
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

# Avoid OpenCL context on GPU to preserve NVENC and VRAM
cv2.ocl.setUseOpenCL(False)


@dataclass
class KillFeedSignal:
    timestamp: float
    confidence: float
    is_headshot: bool
    is_spectated_player: bool
    row_index: int
    raw_evidence: Dict[str, Any]


class ValorantKillFeedDetector:
    """Detects concrete kill events in the Valorant kill feed ROI with headshot and local-player attribution."""

    def __init__(
        self,
        kill_feed_region: Tuple[float, float, float, float] = (0.04, 0.74, 0.32, 0.985),
        cooldown_sec: float = 0.80,
        persistence_sec: float = 3.80,
    ):
        self.roi_coords = kill_feed_region
        self.cooldown_sec = cooldown_sec
        self.persistence_sec = persistence_sec
        self.prev_roi_gray: Optional[np.ndarray] = None
        self.last_detection_time: float = -100.0
        self.active_banner_rows: Dict[int, float] = {}

    def crop_kill_feed(self, frame: np.ndarray) -> np.ndarray:
        """Extracts normalized kill-feed sub-image from 16:9 full frame."""
        h, w = frame.shape[:2]
        ymin, xmin, ymax, xmax = self.roi_coords
        y1, y2 = int(h * ymin), int(h * ymax)
        x1, x2 = int(w * xmin), int(w * xmax)
        return frame[y1:y2, x1:x2]

    def process_frame(self, frame: np.ndarray, timestamp: float) -> Optional[KillFeedSignal]:
        """
        Processes a sampled video frame.
        Detects onset of new kill banners, headshot markers, and spectated player highlight.
        """
        roi = self.crop_kill_feed(frame)
        if roi.size == 0:
            return None

        # Clean expired active banners
        self.active_banner_rows = {
            r: t for r, t in self.active_banner_rows.items()
            if (timestamp - t) < self.persistence_sec
        }

        # Calculate temporal visual delta (onset change)
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        frame_delta = 0.0
        if self.prev_roi_gray is not None and self.prev_roi_gray.shape == roi_gray.shape:
            frame_delta = float(np.mean(cv2.absdiff(roi_gray, self.prev_roi_gray)))
        self.prev_roi_gray = roi_gray

        # Convert ROI to HSV for color profile matching
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask_red = cv2.bitwise_or(
            cv2.inRange(hsv, np.array([0, 110, 120]), np.array([10, 255, 255])),
            cv2.inRange(hsv, np.array([170, 110, 120]), np.array([180, 255, 255]))
        )
        mask_gold = cv2.inRange(hsv, np.array([18, 120, 140]), np.array([32, 255, 255]))
        mask_teal = cv2.inRange(hsv, np.array([75, 100, 120]), np.array([95, 255, 255]))

        # Global ROI color statistics
        tot_pixels = float(roi.shape[0] * roi.shape[1])
        red_pct = (float(np.count_nonzero(mask_red)) / tot_pixels) * 100.0
        gold_pct = (float(np.count_nonzero(mask_gold)) / tot_pixels) * 100.0
        teal_pct = (float(np.count_nonzero(mask_teal)) / tot_pixels) * 100.0

        # A valid kill onset requires:
        # 1. Significant appearance transition (frame_delta >= 18.0)
        # 2. Presence of high-contrast combat banner colors (red, gold, or teal)
        # 3. Cooldown of at least 1.20s since previous kill onset
        is_combat_color = (red_pct >= 5.0) or (gold_pct >= 10.0) or (teal_pct >= 4.0)
        is_onset_transition = frame_delta >= 18.0

        if is_onset_transition and is_combat_color and (timestamp - self.last_detection_time) >= 1.20:
            is_headshot = (red_pct >= 7.0 and gold_pct >= 15.0) or (red_pct >= 8.5)
            is_spectated = gold_pct >= 15.0

            conf = 0.75 + min(0.20, (frame_delta / 100.0) * 0.15 + (gold_pct / 100.0) * 0.10)
            if is_spectated:
                conf = min(0.98, conf + 0.05)
            if is_headshot:
                conf = min(0.98, conf + 0.04)

            self.last_detection_time = timestamp

            return KillFeedSignal(
                timestamp=round(timestamp, 3),
                confidence=round(conf, 3),
                is_headshot=is_headshot,
                is_spectated_player=is_spectated,
                row_index=0,
                raw_evidence={
                    "frame_delta": round(frame_delta, 2),
                    "red_pct": round(red_pct, 2),
                    "gold_pct": round(gold_pct, 2),
                    "teal_pct": round(teal_pct, 2),
                }
            )

        return None
