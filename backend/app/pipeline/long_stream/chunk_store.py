"""Chunk Store: persistent on-disk storage and manifest coordination for chunk analysis and checkpointing."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .chunk_planner import ChunkPlan


class ChunkStore:
    """Manages disk persistence for chunk analysis results and resumability manifests."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.long_stream_dir = self.project_dir / "long_stream"
        self.chunks_dir = self.long_stream_dir / "chunks"
        self.manifest_path = self.long_stream_dir / "manifest.json"

        self.long_stream_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

    def init_manifest(
        self,
        plans: List[ChunkPlan],
        video_id: str,
        source_duration: float,
        chunk_duration: float,
        overlap: float,
    ) -> Dict[str, Any]:
        """Initializes or merges with an existing manifest."""
        existing = self.load_manifest()
        if existing and existing.get("total_chunks") == len(plans):
            return existing

        manifest = {
            "version": "phase_7c",
            "video_id": video_id,
            "source_duration": round(source_duration, 2),
            "chunk_duration": round(chunk_duration, 2),
            "overlap": round(overlap, 2),
            "total_chunks": len(plans),
            "chunks_processed": 0,
            "chunks_failed": 0,
            "chunks_reused": 0,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "chunks": [p.to_dict() for p in plans],
        }
        self.save_manifest(manifest)
        return manifest

    def load_manifest(self) -> Optional[Dict[str, Any]]:
        """Loads manifest from disk if it exists and is valid."""
        if not self.manifest_path.exists():
            return None
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Persists manifest to disk atomically."""
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        temp_file = self.manifest_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        temp_file.replace(self.manifest_path)

    def is_chunk_completed(self, chunk_id: str) -> bool:
        """Checks if a chunk file exists on disk and is completed."""
        chunk_file = self.chunks_dir / f"{chunk_id}.json"
        if not chunk_file.exists():
            return False
        try:
            with open(chunk_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("status") == "completed"
        except Exception:
            return False

    def save_chunk_result(self, chunk_id: str, result: Dict[str, Any]) -> None:
        """Saves a chunk's complete analysis results to disk and updates manifest."""
        chunk_file = self.chunks_dir / f"{chunk_id}.json"
        temp_file = chunk_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        temp_file.replace(chunk_file)

        # Update manifest
        manifest = self.load_manifest()
        if manifest:
            for c in manifest.get("chunks", []):
                if c.get("chunk_id") == chunk_id:
                    c["status"] = "completed"
                    c["candidates_count"] = len(result.get("candidates", []))
                    break
            completed_count = sum(1 for c in manifest.get("chunks", []) if c.get("status") == "completed")
            manifest["chunks_processed"] = completed_count
            manifest["status"] = "in_progress" if completed_count < manifest["total_chunks"] else "completed"
            self.save_manifest(manifest)

    def mark_chunk_failed(self, chunk_id: str, error_msg: str) -> None:
        """Records chunk failure in manifest and disk file."""
        chunk_file = self.chunks_dir / f"{chunk_id}.json"
        error_payload = {
            "chunk_id": chunk_id,
            "status": "failed",
            "error": error_msg,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(chunk_file, "w", encoding="utf-8") as f:
            json.dump(error_payload, f, indent=2)

        manifest = self.load_manifest()
        if manifest:
            for c in manifest.get("chunks", []):
                if c.get("chunk_id") == chunk_id:
                    c["status"] = "failed"
                    c["error"] = error_msg
                    break
            manifest["chunks_failed"] = sum(1 for c in manifest.get("chunks", []) if c.get("status") == "failed")
            self.save_manifest(manifest)

    def load_chunk_result(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Loads a single chunk's saved results from disk."""
        chunk_file = self.chunks_dir / f"{chunk_id}.json"
        if not chunk_file.exists():
            return None
        try:
            with open(chunk_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_completed_chunks(self) -> List[Dict[str, Any]]:
        """Retrieves results of all successfully completed chunks, sorted chronologically."""
        results: List[Dict[str, Any]] = []
        for file in sorted(self.chunks_dir.glob("chunk_*.json")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("status") == "completed":
                        results.append(data)
            except Exception:
                pass
        results.sort(key=lambda x: x.get("source_start", 0.0))
        return results

    def get_resumable_plan(self, planned_chunks: List[ChunkPlan]) -> Tuple[List[ChunkPlan], int]:
        """
        Reconciles planned chunks with on-disk state.
        Marks completed chunks as completed so they are not re-executed.
        Returns (reconciled_plans, num_reused).
        """
        reused = 0
        for plan in planned_chunks:
            if self.is_chunk_completed(plan.chunk_id):
                plan.status = "completed"
                reused += 1
            else:
                plan.status = "pending"
        return planned_chunks, reused

    def collect_all_candidates(self) -> List[Dict[str, Any]]:
        """Aggregates all raw candidate moments across completed chunks."""
        all_candidates: List[Dict[str, Any]] = []
        for chunk in self.get_completed_chunks():
            chunk_id = chunk.get("chunk_id", "unknown")
            candidates = chunk.get("candidates", [])
            for c in candidates:
                cand = dict(c)
                cand["chunk_id"] = chunk_id
                all_candidates.append(cand)
        return all_candidates
