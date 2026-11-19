"""Chunk Planner: partitions long streams into overlapping, manageable temporal analysis windows."""

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from backend.app.config import (
    LONG_STREAM_THRESHOLD_SEC,
    CHUNK_DURATION_SEC,
    CHUNK_OVERLAP_SEC,
    MIN_CHUNK_DURATION_SEC,
)


@dataclass
class ChunkPlan:
    """Represents a planned temporal window for analysis."""
    chunk_id: str
    index: int
    source_start: float
    source_end: float
    duration: float
    overlap_start: float = 0.0
    overlap_end: float = 0.0
    status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChunkPlan":
        return cls(
            chunk_id=data["chunk_id"],
            index=data["index"],
            source_start=float(data["source_start"]),
            source_end=float(data["source_end"]),
            duration=float(data["duration"]),
            overlap_start=float(data.get("overlap_start", 0.0)),
            overlap_end=float(data.get("overlap_end", 0.0)),
            status=data.get("status", "pending"),
        )


def is_long_stream(duration: float, threshold: Optional[float] = None) -> bool:
    """Determines whether a video duration qualifies as a long stream."""
    limit = threshold if threshold is not None else LONG_STREAM_THRESHOLD_SEC
    return float(duration) >= float(limit)


def plan_chunks(
    source_duration: float,
    chunk_duration: float = CHUNK_DURATION_SEC,
    overlap: float = CHUNK_OVERLAP_SEC,
    min_chunk_duration: float = MIN_CHUNK_DURATION_SEC,
) -> List[ChunkPlan]:
    """
    Plans overlapping temporal chunks across a source video duration.

    Args:
        source_duration: Total video length in seconds.
        chunk_duration: Target duration of each chunk in seconds (e.g. 600s / 10m).
        overlap: Temporal overlap between adjacent chunks in seconds (e.g. 45s).
        min_chunk_duration: Minimum duration below which a final trailing slice is merged.

    Returns:
        List of ChunkPlan objects covering [0.0, source_duration].
    """
    if source_duration <= 0:
        return []

    # Single chunk if duration is within chunk_duration or small edge case
    if source_duration <= chunk_duration:
        return [
            ChunkPlan(
                chunk_id="chunk_0001",
                index=1,
                source_start=0.0,
                source_end=round(source_duration, 2),
                duration=round(source_duration, 2),
                overlap_start=0.0,
                overlap_end=0.0,
                status="pending",
            )
        ]

    step_size = max(1.0, chunk_duration - overlap)
    chunks: List[ChunkPlan] = []
    current_start = 0.0
    idx = 1

    while current_start < source_duration:
        target_end = current_start + chunk_duration

        if target_end >= source_duration:
            # Reached or surpassed the end of the video
            source_end = source_duration
            dur = source_end - current_start
            # If this final chunk would be shorter than min_chunk_duration and we already have a chunk,
            # extend the previous chunk to cover the end rather than creating a stub chunk.
            if dur < min_chunk_duration and len(chunks) > 0:
                prev = chunks[-1]
                prev.source_end = round(source_duration, 2)
                prev.duration = round(prev.source_end - prev.source_start, 2)
                prev.overlap_end = 0.0
                break

            overlap_start = overlap if idx > 1 else 0.0
            chunks.append(
                ChunkPlan(
                    chunk_id=f"chunk_{idx:04d}",
                    index=idx,
                    source_start=round(current_start, 2),
                    source_end=round(source_end, 2),
                    duration=round(dur, 2),
                    overlap_start=round(overlap_start, 2),
                    overlap_end=0.0,
                    status="pending",
                )
            )
            break

        # Check remaining time after this chunk
        remaining = source_duration - target_end
        if remaining < min_chunk_duration:
            # Merge remainder into this chunk so we don't produce an undersized final chunk
            source_end = source_duration
            dur = source_end - current_start
            overlap_start = overlap if idx > 1 else 0.0
            chunks.append(
                ChunkPlan(
                    chunk_id=f"chunk_{idx:04d}",
                    index=idx,
                    source_start=round(current_start, 2),
                    source_end=round(source_end, 2),
                    duration=round(dur, 2),
                    overlap_start=round(overlap_start, 2),
                    overlap_end=0.0,
                    status="pending",
                )
            )
            break

        overlap_start = overlap if idx > 1 else 0.0
        overlap_end = overlap
        dur = target_end - current_start

        chunks.append(
            ChunkPlan(
                chunk_id=f"chunk_{idx:04d}",
                index=idx,
                source_start=round(current_start, 2),
                source_end=round(target_end, 2),
                duration=round(dur, 2),
                overlap_start=round(overlap_start, 2),
                overlap_end=round(overlap_end, 2),
                status="pending",
            )
        )

        current_start += step_size
        idx += 1

    return chunks


class ChunkPlanner:
    """High-level planner with configurable parameters."""

    def __init__(
        self,
        threshold: float = LONG_STREAM_THRESHOLD_SEC,
        chunk_duration: float = CHUNK_DURATION_SEC,
        overlap: float = CHUNK_OVERLAP_SEC,
        min_chunk_duration: float = MIN_CHUNK_DURATION_SEC,
    ):
        self.threshold = threshold
        self.chunk_duration = chunk_duration
        self.overlap = overlap
        self.min_chunk_duration = min_chunk_duration

    def is_long_stream(self, duration: float) -> bool:
        return is_long_stream(duration, self.threshold)

    def plan(self, source_duration: float) -> List[ChunkPlan]:
        return plan_chunks(
            source_duration=source_duration,
            chunk_duration=self.chunk_duration,
            overlap=self.overlap,
            min_chunk_duration=self.min_chunk_duration,
        )
