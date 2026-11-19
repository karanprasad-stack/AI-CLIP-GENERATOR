"""Valorant Round State detector: round wins, losses, and spike state transitions."""

import cv2
import numpy as np
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class RoundStateSignal:
    timestamp: float
    event_type: str        # "round_win", "round_loss", "spike_planted", "spike_defused"
    confidence: float
    details: Dict[str, Any]


class ValorantRoundStateDetector:
    """Detects round end outcomes (VICTORY / DEFEAT) and spike state in Valorant."""

    def __init__(
        self,
        center_banner_region: Tuple[float, float, float, float] = (0.20, 0.28, 0.45, 0.72),
        round_state_region: Tuple[float, float, float, float] = (0.01, 0.44, 0.08, 0.56),
        cooldown_sec: float = 12.0,
    ):
        self.center_banner_region = center_banner_region
        self.round_state_region = round_state_region
        self.cooldown_sec = cooldown_sec
        self.last_round_end_time: float = -100.0
        self.last_spike_time: float = -100.0

    def process_frame(self, frame: np.ndarray, timestamp: float) -> Optional[RoundStateSignal]:
        """Inspects center banner and top timer/spike for round events."""
        h, w = frame.shape[:2]

        # -------------------------------------------------------------
        # 1. Center Screen Banner: VICTORY / DEFEAT
        # -------------------------------------------------------------
        if (timestamp - self.last_round_end_time) >= self.cooldown_sec:
            by1, bx1, by2, bx2 = self.center_banner_region
            banner_crop = frame[int(h * by1):int(h * by2), int(w * bx1):int(w * bx2)]
            if banner_crop.size > 0:
                hsv_banner = cv2.cvtColor(banner_crop, cv2.COLOR_BGR2HSV)

                # Victory Cyan/Teal mask
                lower_cyan = np.array([80, 100, 140])
                upper_cyan = np.array([105, 255, 255])
                mask_cyan = cv2.inRange(hsv_banner, lower_cyan, upper_cyan)
                cyan_density = float(np.count_nonzero(mask_cyan)) / float(mask_cyan.size)

                # Defeat Red mask
                lower_red1 = np.array([0, 120, 140])
                upper_red1 = np.array([10, 255, 255])
                lower_red2 = np.array([170, 120, 140])
                upper_red2 = np.array([180, 255, 255])
                mask_red = cv2.bitwise_or(
                    cv2.inRange(hsv_banner, lower_red1, upper_red1),
                    cv2.inRange(hsv_banner, lower_red2, upper_red2)
                )
                red_density = float(np.count_nonzero(mask_red)) / float(mask_red.size)

                if cyan_density >= 0.06:
                    conf = min(0.96, 0.80 + cyan_density * 1.5)
                    self.last_round_end_time = timestamp
                    return RoundStateSignal(
                        timestamp=round(timestamp, 3),
                        event_type="round_win",
                        confidence=round(conf, 3),
                        details={"banner_color": "cyan", "density": round(cyan_density, 4)}
                    )
                elif red_density >= 0.08:
                    conf = min(0.95, 0.78 + red_density * 1.5)
                    self.last_round_end_time = timestamp
                    return RoundStateSignal(
                        timestamp=round(timestamp, 3),
                        event_type="round_loss",
                        confidence=round(conf, 3),
                        details={"banner_color": "red", "density": round(red_density, 4)}
                    )

        # -------------------------------------------------------------
        # 2. Top-Center Spike Status
        # -------------------------------------------------------------
        if (timestamp - self.last_spike_time) >= 15.0:
            ry1, rx1, ry2, rx2 = self.round_state_region
            spike_crop = frame[int(h * ry1):int(h * ry2), int(w * rx1):int(w * rx2)]
            if spike_crop.size > 0:
                hsv_spike = cv2.cvtColor(spike_crop, cv2.COLOR_BGR2HSV)
                # Spike flashing red
                lower_spk = np.array([170, 140, 150])
                upper_spk = np.array([180, 255, 255])
                mask_spk = cv2.inRange(hsv_spike, lower_spk, upper_spk)
                spk_density = float(np.count_nonzero(mask_spk)) / float(mask_spk.size)

                if spk_density >= 0.08:
                    self.last_spike_time = timestamp
                    return RoundStateSignal(
                        timestamp=round(timestamp, 3),
                        event_type="spike_planted",
                        confidence=0.82,
                        details={"spike_density": round(spk_density, 4)}
                    )

        return None
