"""Valorant HUD detector for bottom-center kill skull flashes and low-HP indicators."""

import cv2
import numpy as np
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class HudSignal:
    timestamp: float
    signal_type: str       # "local_kill_skull", "low_hp"
    confidence: float
    details: Dict[str, Any]


class ValorantHudDetector:
    """Inspects bottom-center combat skull flash and bottom-left health."""

    def __init__(
        self,
        skull_region: Tuple[float, float, float, float] = (0.76, 0.44, 0.88, 0.56),
        health_region: Tuple[float, float, float, float] = (0.90, 0.16, 0.99, 0.28),
    ):
        self.skull_region = skull_region
        self.health_region = health_region
        self.last_skull_time: float = -100.0

    def process_frame(self, frame: np.ndarray, timestamp: float) -> Optional[HudSignal]:
        """Inspects HUD regions for combat skull flash or critical low health."""
        h, w = frame.shape[:2]

        # 1. Bottom-Center Kill Skull Flash (animates on local player kill)
        if (timestamp - self.last_skull_time) >= 0.80:
            sy1, sx1, sy2, sx2 = self.skull_region
            skull_crop = frame[int(h * sy1):int(h * sy2), int(w * sx1):int(w * sx2)]
            if skull_crop.size > 0:
                hsv_skull = cv2.cvtColor(skull_crop, cv2.COLOR_BGR2HSV)
                # Skull flash is bright gold/yellow or saturated red
                lower_gold = np.array([18, 130, 160])
                upper_gold = np.array([32, 255, 255])
                mask_gold = cv2.inRange(hsv_skull, lower_gold, upper_gold)
                gold_density = float(np.count_nonzero(mask_gold)) / float(mask_gold.size)

                if gold_density >= 0.05:
                    self.last_skull_time = timestamp
                    conf = min(0.96, 0.82 + gold_density * 2.0)
                    return HudSignal(
                        timestamp=round(timestamp, 3),
                        signal_type="local_kill_skull",
                        confidence=round(conf, 3),
                        details={"gold_density": round(gold_density, 4)}
                    )

        return None
