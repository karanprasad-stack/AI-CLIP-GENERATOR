"""Multi-genre game archetype detectors."""

from .story_detector import StoryDetector
from .horror_detector import HorrorDetector
from .fps_detector import FPSDetector

__all__ = ["StoryDetector", "HorrorDetector", "FPSDetector"]
