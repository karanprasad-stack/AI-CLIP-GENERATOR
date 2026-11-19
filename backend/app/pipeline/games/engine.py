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
from .archetypes.story_detector import StoryDetector
from .archetypes.horror_detector import HorrorDetector
from .archetypes.fps_detector import FPSDetector


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
        self.story_detector = StoryDetector(self.profile)
        self.horror_detector = HorrorDetector(self.profile)
        self.fps_detector = FPSDetector(self.profile)

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
        Dispatches to archetype-specific detector or Valorant specialized pipeline.
        """
        t0 = time.perf_counter()
        visual_sampled = 0

        # Archetype Dispatch
        if self.profile.name == "valorant":
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
                visual_sampled = visual_signals.get("sampled_frames_count", 0)

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

        elif self.profile.archetype == "story_open_world":
            final_events = self.story_detector.detect_events(
                video_path=video_path,
                audio_analysis=audio_analysis,
                transcript_data=transcript_data,
                duration=duration,
                start_sec=start_sec,
            )

        elif self.profile.archetype == "horror_survival":
            final_events = self.horror_detector.detect_events(
                video_path=video_path,
                audio_analysis=audio_analysis,
                transcript_data=transcript_data,
                duration=duration,
                start_sec=start_sec,
            )

        elif self.profile.archetype == "competitive_fps":
            final_events = self.fps_detector.detect_events(
                video_path=video_path,
                audio_analysis=audio_analysis,
                transcript_data=transcript_data,
                duration=duration,
                start_sec=start_sec,
            )

        else:
            # Fallback Generic
            audio_extractor = AudioEvidenceExtractor(audio_analysis)
            transcript_extractor = TranscriptEvidenceExtractor(
                transcript_data=transcript_data,
                event_vocabulary=self.profile.event_vocabulary,
                reaction_vocabulary=self.profile.reaction_vocabulary,
            )
            final_events = self.fusion_engine.fuse_events(
                visual_signals={"kill_feed": [], "round_state": [], "hud": []},
                audio_extractor=audio_extractor,
                transcript_extractor=transcript_extractor,
                duration=duration,
            )

        elapsed = round(time.perf_counter() - t0, 3)

        metadata = {
            "source_duration": duration,
            "processing_time_sec": elapsed,
            "game_profile": self.profile.name,
            "game_archetype": self.profile.archetype,
            "detected_title": getattr(self.profile, "detected_title", None) or self.profile.display_name,
            "scoring_weights": self.profile.scoring_weights,
            "effect_style": self.profile.effect_style,
            "max_effects_per_minute": self.profile.max_effects_per_minute,
            "visual_frames_sampled": visual_sampled,
        }

        timeline = GameplayTimeline(
            game=self.profile.name,
            events=final_events,
            metadata=metadata,
        )

        return timeline
