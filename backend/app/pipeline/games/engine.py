"""Central Gameplay Event Engine orchestrating multi-modal evidence, sequences, and timeline generation."""

import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from .models import GameplayEvent, EventType, EventStatus
from .profiles.base import BaseGameProfile
from .profiles import get_game_profile
from .evidence.audio import AudioEvidenceExtractor
from .evidence.transcript import TranscriptEvidenceExtractor
from .evidence.visual import VisualEvidenceExtractor
from .fusion import EvidenceFusionEngine
from .sequence import KillSequenceEngine
from .clutch import ClutchDetector
from .timeline import GameplayTimeline


class GameplayEngine:
    """Orchestrates multi-modal gameplay event detection, kill sequencing, and timeline persistence."""

    def __init__(self, profile: Optional[BaseGameProfile] = None):
        self.profile = profile or get_game_profile("generic")
        self.visual_extractor = VisualEvidenceExtractor(self.profile)
        self.fusion_engine = EvidenceFusionEngine(self.profile)
        self.sequence_engine = KillSequenceEngine(
            sequence_window_sec=float(self.profile.detection_config.get("multi_kill_window_sec", 9.0))
        )
        self.clutch_detector = ClutchDetector(
            clutch_window_sec=float(self.profile.detection_config.get("clutch_window_sec", 28.0))
        )

    def detect_events(
        self,
        video_path: Optional[Path] = None,
        audio_analysis: Optional[Dict[str, Any]] = None,
        transcript_data: Optional[Dict[str, Any]] = None,
        duration: float = 0.0,
        start_sec: float = 0.0,
        max_visual_frames: Optional[int] = None,
    ) -> GameplayTimeline:
        """
        Executes end-to-end gameplay event detection.
        1. Extract audio peaks & volume envelope.
        2. Extract transcript keywords & reactions.
        3. Extract visual kill feed & HUD signals (if video_path provided).
        4. Fuse multi-modal evidence into typed events.
        5. Form 2K, 3K, 4K, Ace sequences.
        6. Detect conservative clutch candidates.
        7. Returns populated GameplayTimeline.
        """
        t0 = time.perf_counter()

        # 1. Initialize evidence extractors
        audio_extractor = AudioEvidenceExtractor(audio_analysis)
        transcript_extractor = TranscriptEvidenceExtractor(
            transcript_data=transcript_data,
            event_vocabulary=self.profile.event_vocabulary,
            reaction_vocabulary=self.profile.reaction_vocabulary,
        )

        # 2. Extract visual signals if video is accessible
        visual_signals: Dict[str, List[Any]] = {"kill_feed": [], "round_state": [], "hud": []}
        if video_path and video_path.exists() and self.profile.detection_config.get("kill_feed_enabled", True):
            visual_signals = self.visual_extractor.extract_visual_signals(
                video_path=video_path,
                start_sec=start_sec,
                duration=duration,
                max_frames=max_visual_frames,
            )

        # 3. Fuse multi-modal signals into base events
        base_events = self.fusion_engine.fuse_events(
            visual_signals=visual_signals,
            audio_extractor=audio_extractor,
            transcript_extractor=transcript_extractor,
            duration=duration,
        )

        # 4. Form kill sequences (2K, 3K, 4K, Ace)
        sequenced_events = self.sequence_engine.process_sequences(base_events)

        # 5. Detect clutch candidates
        final_events = self.clutch_detector.detect_clutches(sequenced_events)

        elapsed = round(time.perf_counter() - t0, 3)

        metadata = {
            "source_duration": duration,
            "processing_time_sec": elapsed,
            "game_profile": self.profile.name,
            "visual_frames_sampled": visual_signals.get("sampled_frames_count", 0),
        }

        timeline = GameplayTimeline(
            game=self.profile.name,
            events=final_events,
            metadata=metadata,
        )

        return timeline
