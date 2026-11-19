"""Timeline Store: persistence, file-based storage, and lightweight versioning for TimelineEDL."""

import json
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from .models import TimelineEDL


class TimelineStore:
    """Manages reading and writing versioned timeline.json files on disk."""

    @staticmethod
    def get_timeline_path(project_dir: Path, candidate_id: int) -> Path:
        """Returns standard path to the candidate's timeline.json."""
        target_dir = project_dir / "publishing" / f"candidate_{candidate_id:02d}"
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "timeline.json"

    def get_timeline(self, project_dir: Path, candidate_id: int) -> Optional[TimelineEDL]:
        """Loads timeline.json for a candidate if it exists."""
        tl_path = self.get_timeline_path(project_dir, candidate_id)
        if not tl_path.exists():
            # Check secondary fallback
            alt_path = project_dir / "candidates" / f"candidate_{candidate_id:02d}" / "timeline.json"
            if alt_path.exists():
                tl_path = alt_path
            else:
                return None

        try:
            with open(tl_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return TimelineEDL(**data)
        except Exception:
            return None

    def save_timeline(
        self,
        project_dir: Path,
        timeline: TimelineEDL,
        increment_version: bool = True,
    ) -> TimelineEDL:
        """
        Saves TimelineEDL to disk with version increment and backup of previous version.
        """
        tl_path = self.get_timeline_path(project_dir, timeline.candidate_id)

        # Backup previous version if it exists
        if tl_path.exists() and increment_version:
            try:
                backup_name = f"timeline.v{timeline.version}.json"
                backup_path = tl_path.parent / backup_name
                tl_path.replace(backup_path)
            except Exception:
                pass

        if increment_version:
            timeline.version += 1

        timeline.metadata.updated_at = datetime.now(timezone.utc).isoformat()
        timeline.metadata.source = "user_edited"

        data = (
            timeline.model_dump()
            if hasattr(timeline, "model_dump")
            else timeline.dict()
        )

        temp_file = tl_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(tl_path)

        return timeline
