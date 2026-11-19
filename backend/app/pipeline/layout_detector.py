"""Lightweight facecam and layout detection using OpenCV."""

from pathlib import Path
from typing import Dict, Any, List, Optional
import cv2
import numpy as np

# Ensure OpenCV does not initialize an OpenCL context on GPU, leaving NVENC 100% free
cv2.ocl.setUseOpenCL(False)

from backend.app.config import (
    LAYOUT_AUTO,
    LAYOUT_SMART_CROP,
    LAYOUT_BLURRED_BG,
    LAYOUT_FACECAM,
    FACECAM_SAMPLE_INTERVAL_SEC,
    FACECAM_MIN_SAMPLES,
    FACECAM_MAX_SAMPLES,
    FACECAM_PERSISTENCE_THRESHOLD,
    FACECAM_REGION_TOLERANCE,
)


class LayoutDetector:
    """Estimates facecam presence and selects the appropriate 9:16 layout."""

    def __init__(self):
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def detect_facecam(
        self,
        video_path: Path,
        sample_interval: float = FACECAM_SAMPLE_INTERVAL_SEC,
        min_samples: int = FACECAM_MIN_SAMPLES,
        max_samples: int = FACECAM_MAX_SAMPLES,
        persistence_threshold: float = FACECAM_PERSISTENCE_THRESHOLD,
    ) -> Dict[str, Any]:
        """
        Analyze sampled frames to estimate whether the video contains a persistent facecam.
        Returns a dictionary with facecam_detected, confidence, and normalized region.
        """
        vpath = Path(video_path)
        if not vpath.exists():
            return {
                "facecam_detected": False,
                "confidence": 0.0,
                "region": None,
                "samples_checked": 0,
                "samples_with_face": 0,
                "recommended_layout": LAYOUT_SMART_CROP,
                "reason": "Video file not found",
            }

        cap = cv2.VideoCapture(str(vpath))
        if not cap.isOpened():
            return {
                "facecam_detected": False,
                "confidence": 0.0,
                "region": None,
                "samples_checked": 0,
                "samples_with_face": 0,
                "recommended_layout": LAYOUT_SMART_CROP,
                "reason": "Unable to open video with OpenCV",
            }

        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            duration = total_frames / fps if fps > 0 else 0.0

            if duration <= 1.0:
                sample_timestamps = [duration / 2.0]
            else:
                # Generate sample timestamps across the duration
                step = max(sample_interval, duration / max_samples)
                curr = 0.5
                sample_timestamps = []
                while curr < duration and len(sample_timestamps) < max_samples:
                    sample_timestamps.append(curr)
                    curr += step

            if len(sample_timestamps) < min_samples and duration > 2.0:
                sample_timestamps = list(np.linspace(0.5, duration - 0.5, min_samples))

            detected_boxes: List[Dict[str, float]] = []
            valid_samples_count = 0

            for t in sample_timestamps:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue

                valid_samples_count += 1
                fh, fw = frame.shape[:2]

                # Resize for lightweight CPU detection (width ~ 640px)
                scale = min(1.0, 640.0 / fw)
                proc_w = int(fw * scale)
                proc_h = int(fh * scale)
                small_frame = cv2.resize(frame, (proc_w, proc_h), interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)

                faces = self.face_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.15,
                    minNeighbors=4,
                    minSize=(24, 24),
                )

                if len(faces) > 0:
                    # Pick largest face in this frame
                    faces_sorted = sorted(faces, key=lambda b: b[2] * b[3], reverse=True)
                    x, y, w, h = faces_sorted[0]
                    detected_boxes.append({
                        "x": (x / scale) / fw,
                        "y": (y / scale) / fh,
                        "w": (w / scale) / fw,
                        "h": (h / scale) / fh,
                        "t": t,
                    })

        finally:
            cap.release()

        if valid_samples_count == 0 or len(detected_boxes) == 0:
            return {
                "facecam_detected": False,
                "confidence": 0.0,
                "region": None,
                "samples_checked": valid_samples_count,
                "samples_with_face": 0,
                "recommended_layout": LAYOUT_SMART_CROP,
                "reason": "No faces detected in sampled frames",
            }

        # Spatial clustering: cluster face detections that share spatial position
        clusters: List[List[Dict[str, float]]] = []
        for box in detected_boxes:
            cx = box["x"] + box["w"] / 2.0
            cy = box["y"] + box["h"] / 2.0
            matched = False
            for cluster in clusters:
                avg_cx = sum(b["x"] + b["w"] / 2.0 for b in cluster) / len(cluster)
                avg_cy = sum(b["y"] + b["h"] / 2.0 for b in cluster) / len(cluster)
                dist = np.hypot(cx - avg_cx, cy - avg_cy)
                if dist <= FACECAM_REGION_TOLERANCE:
                    cluster.append(box)
                    matched = True
                    break
            if not matched:
                clusters.append([box])

        # Find largest persistent cluster
        clusters.sort(key=len, reverse=True)
        dominant_cluster = clusters[0]
        cluster_len = len(dominant_cluster)
        persistence_ratio = cluster_len / float(valid_samples_count)

        facecam_detected = (
            persistence_ratio >= persistence_threshold
            and cluster_len >= 2
        )

        confidence = round(min(1.0, persistence_ratio / max(persistence_threshold, 0.01)), 2)
        confidence = min(confidence, 1.0)

        region: Optional[Dict[str, float]] = None
        if facecam_detected:
            # Average face bounding box
            avg_x = sum(b["x"] for b in dominant_cluster) / cluster_len
            avg_y = sum(b["y"] for b in dominant_cluster) / cluster_len
            avg_w = sum(b["w"] for b in dominant_cluster) / cluster_len
            avg_h = sum(b["h"] for b in dominant_cluster) / cluster_len

            # Pad bounding box by 50% to include webcam surround and shoulders
            pad_w = avg_w * 0.5
            pad_h = avg_h * 0.6
            reg_x = max(0.0, avg_x - pad_w)
            reg_y = max(0.0, avg_y - pad_h)
            reg_w = min(1.0 - reg_x, avg_w + 2.0 * pad_w)
            reg_h = min(1.0 - reg_y, avg_h + 2.0 * pad_h)

            region = {
                "x": round(float(reg_x), 3),
                "y": round(float(reg_y), 3),
                "width": round(float(reg_w), 3),
                "height": round(float(reg_h), 3),
            }

        recommended = LAYOUT_FACECAM if facecam_detected else LAYOUT_SMART_CROP

        return {
            "facecam_detected": facecam_detected,
            "confidence": confidence,
            "region": region,
            "samples_checked": valid_samples_count,
            "samples_with_face": len(detected_boxes),
            "dominant_cluster_samples": cluster_len,
            "persistence_ratio": round(persistence_ratio, 3),
            "recommended_layout": recommended,
            "reason": (
                f"Facecam verified with {cluster_len}/{valid_samples_count} persistent frames"
                if facecam_detected
                else f"No persistent facecam detected ({cluster_len}/{valid_samples_count} frames, threshold {persistence_threshold})"
            ),
        }

    def resolve_layout(
        self,
        requested_layout: str,
        facecam_info: Dict[str, Any],
    ) -> str:
        """
        Determine the layout to use based on user preference and detection result.
        """
        clean_req = (requested_layout or LAYOUT_AUTO).strip().lower()
        if clean_req in [LAYOUT_SMART_CROP, LAYOUT_BLURRED_BG, LAYOUT_FACECAM]:
            return clean_req

        # Automatic layout selection
        if facecam_info.get("facecam_detected", False):
            return LAYOUT_FACECAM
        return LAYOUT_SMART_CROP
