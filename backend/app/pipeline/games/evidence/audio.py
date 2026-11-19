"""Extracts normalized audio intensity and peak evidence for gameplay events."""

from typing import Dict, Any, List, Optional, Tuple


class AudioEvidenceExtractor:
    """Extracts timestamped audio peaks and volume bursts to corroborate gameplay events."""

    def __init__(self, audio_analysis: Optional[Dict[str, Any]] = None):
        self.peaks: List[Dict[str, Any]] = []
        if audio_analysis and "peaks" in audio_analysis:
            self.peaks = sorted(audio_analysis["peaks"], key=lambda p: float(p.get("timestamp", 0.0)))

    def query_evidence(self, timestamp: float, window: float = 1.20) -> Tuple[float, Optional[Dict[str, Any]]]:
        """
        Queries audio peak evidence within [timestamp - window, timestamp + window].
        Returns:
            (confidence: float in [0.0, 1.0], matching_peak: Optional[dict])
        """
        if not self.peaks:
            return 0.0, None

        best_peak = None
        min_dist = float("inf")

        for p in self.peaks:
            t = float(p.get("timestamp", 0.0))
            dist = abs(t - timestamp)
            if dist <= window and dist < min_dist:
                min_dist = dist
                best_peak = p

        if not best_peak:
            return 0.0, None

        # Normalize z-score into confidence (e.g. z=1.5 -> 0.60, z=3.0 -> 0.85, z>=4.5 -> 0.98)
        z_score = float(best_peak.get("z_score", 1.0))
        proximity_factor = max(0.5, 1.0 - (min_dist / window) * 0.5)

        base_conf = min(0.98, max(0.30, (z_score / 4.0) * 0.90))
        final_conf = round(base_conf * proximity_factor, 3)

        return final_conf, best_peak
