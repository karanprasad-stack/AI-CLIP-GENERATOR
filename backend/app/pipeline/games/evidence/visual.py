"""Lightweight, efficient visual frame sampler and event signal extractor using OpenCV."""

import cv2
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from ..profiles.base import BaseGameProfile
from ..valorant.kill_feed import ValorantKillFeedDetector, KillFeedSignal
from ..valorant.round_state import ValorantRoundStateDetector, RoundStateSignal
from ..valorant.hud import ValorantHudDetector, HudSignal

# Guarantee no OpenCL initialization on GPU to keep NVENC and CUDA intact
cv2.ocl.setUseOpenCL(False)


class VisualEvidenceExtractor:
    """Samples video frames at low FPS (e.g. 2.0 fps) to extract HUD, kill feed, and round state signals."""

    def __init__(self, profile: BaseGameProfile):
        self.profile = profile
        cfg = profile.detection_config
        self.sample_fps = float(cfg.get("sample_fps", 2.0))

        # Initialize visual detectors
        self.kill_feed_detector = ValorantKillFeedDetector(
            kill_feed_region=profile.kill_feed_region,
            cooldown_sec=float(cfg.get("kill_banner_cooldown_sec", 0.80)),
            persistence_sec=float(cfg.get("kill_persistence_sec", 3.80)),
        )
        self.round_state_detector = ValorantRoundStateDetector(
            center_banner_region=profile.center_banner_region,
            round_state_region=profile.round_state_region,
        )
        self.hud_detector = ValorantHudDetector(
            skull_region=getattr(profile, "bottom_center_skull_region", (0.76, 0.44, 0.88, 0.56)),
            health_region=profile.health_region,
        )

    def extract_visual_signals(
        self,
        video_path: Path,
        start_sec: float = 0.0,
        duration: Optional[float] = None,
        max_frames: Optional[int] = None,
    ) -> Dict[str, List[Any]]:
        """
        Samples video frames efficiently, returning detected visual signals.
        Uses fast frame grabbing to decode only requested sample frames.
        """
        if not video_path.exists():
            return {"kill_feed": [], "round_state": [], "hud": []}

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {"kill_feed": [], "round_state": [], "hud": []}

        source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        source_dur = total_frames / source_fps if source_fps > 0 else 0.0

        end_sec = (start_sec + duration) if duration else source_dur
        end_sec = min(source_dur, end_sec) if source_dur > 0 else end_sec

        # Calculate frame step for desired sample_fps
        frame_step = max(1, int(round(source_fps / self.sample_fps)))

        # Seek to start_sec
        start_frame = int(start_sec * source_fps)
        end_frame = int(end_sec * source_fps)
        if start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        kill_feed_signals: List[KillFeedSignal] = []
        round_state_signals: List[RoundStateSignal] = []
        hud_signals: List[HudSignal] = []

        curr_frame_idx = start_frame
        processed_count = 0

        try:
            while cap.isOpened() and curr_frame_idx <= end_frame:
                if max_frames and processed_count >= max_frames:
                    break

                ret = cap.grab()
                if not ret:
                    break

                if (curr_frame_idx - start_frame) % frame_step == 0:
                    ret_frame, frame = cap.retrieve()
                    if not ret_frame or frame is None:
                        curr_frame_idx += 1
                        continue

                    timestamp = round(curr_frame_idx / source_fps, 3)

                    # 1. Kill Feed Detection
                    kf_sig = self.kill_feed_detector.process_frame(frame, timestamp)
                    if kf_sig:
                        kill_feed_signals.append(kf_sig)

                    # 2. Round State Detection
                    rs_sig = self.round_state_detector.process_frame(frame, timestamp)
                    if rs_sig:
                        round_state_signals.append(rs_sig)

                    # 3. HUD Combat Detection
                    hud_sig = self.hud_detector.process_frame(frame, timestamp)
                    if hud_sig:
                        hud_signals.append(hud_sig)

                    processed_count += 1

                curr_frame_idx += 1

        finally:
            cap.release()

        return {
            "kill_feed": kill_feed_signals,
            "round_state": round_state_signals,
            "hud": hud_signals,
            "sampled_frames_count": processed_count,
        }
