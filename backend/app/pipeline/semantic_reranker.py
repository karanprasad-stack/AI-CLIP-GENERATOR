"""Local LLM Semantic Highlight Reranker using local Ollama (hardware-safe, optional)."""

import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
import numpy as np

from backend.app.config import (
    SEMANTIC_RERANKER_ENABLED,
    SEMANTIC_RERANKER_HOST,
    SEMANTIC_RERANKER_MODEL,
    SEMANTIC_RERANKER_TIMEOUT_SEC,
    SEMANTIC_RERANKER_MAX_CANDIDATES,
)

logger = logging.getLogger(__name__)


class SemanticReranker:
    """Evaluates entertainment value, hook strength, and filler probability of top candidate moments using local Ollama."""

    def __init__(
        self,
        enabled: bool = SEMANTIC_RERANKER_ENABLED,
        host: str = SEMANTIC_RERANKER_HOST,
        model: str = SEMANTIC_RERANKER_MODEL,
        timeout_sec: float = SEMANTIC_RERANKER_TIMEOUT_SEC,
        max_candidates: int = SEMANTIC_RERANKER_MAX_CANDIDATES,
    ):
        self.enabled = enabled
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec
        self.max_candidates = max_candidates

    def is_available(self) -> bool:
        """Fast health-check (1.5s timeout) to determine if local Ollama daemon is reachable."""
        if not self.enabled:
            return False
        try:
            req = urllib.request.Request(
                f"{self.host}/api/tags",
                headers={"User-Agent": "AIClipper/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def evaluate_candidate(
        self,
        candidate: Dict[str, Any],
        game_title: str = "Gaming",
        game_archetype: str = "generic",
    ) -> Optional[Dict[str, Any]]:
        """Queries local Ollama to semantically score hook strength and entertainment value."""
        events_str = ", ".join(
            e.get("event_type", str(e)) if isinstance(e, dict) else str(e)
            for e in candidate.get("gameplay_events", [])[:5]
        ) or candidate.get("gameplay_event") or "general gameplay"

        transcript = str(candidate.get("transcript_excerpt") or "")
        # Limit transcript to ~300 words
        words = transcript.split()
        if len(words) > 300:
            transcript = " ".join(words[:300]) + "..."

        prompt = (
            f"You are a professional YouTube Shorts editor. Evaluate whether this clip has a strong hook, "
            f"meaningful action/dialogue payoff, and high standalone entertainment value for mobile viewers.\n\n"
            f"CLIP CONTEXT:\n"
            f"- Game: {game_title} (Archetype: {game_archetype})\n"
            f"- Duration: {candidate.get('duration', 45.0):.1f}s (Tier: {candidate.get('duration_tier', 'standard')})\n"
            f"- Detected Events: {events_str}\n"
            f"- Spoken Dialogue: \"{transcript}\"\n\n"
            f"TASK:\n"
            f"Output a valid JSON object evaluating this candidate. Do NOT output markdown or explanations outside JSON.\n"
            f'{{\n'
            f'  "hook_score": 0-100,\n'
            f'  "standalone_score": 0-100,\n'
            f'  "entertainment_score": 0-100,\n'
            f'  "is_filler": false,\n'
            f'  "verdict": "One short sentence explaining why this clip is strong or weak."\n'
            f'}}\n'
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.2,
                "num_predict": 120,
            },
        }

        try:
            req = urllib.request.Request(
                f"{self.host}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "AIClipper/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                if resp.status != 200:
                    return None
                data = json.loads(resp.read().decode("utf-8"))

            raw_resp = data.get("response", "").strip()
            parsed = json.loads(raw_resp)

            hook = float(np.clip(float(parsed.get("hook_score", 50)), 0.0, 100.0))
            standalone = float(np.clip(float(parsed.get("standalone_score", 50)), 0.0, 100.0))
            entertainment = float(np.clip(float(parsed.get("entertainment_score", 50)), 0.0, 100.0))
            is_filler = bool(parsed.get("is_filler", False))
            verdict = str(parsed.get("verdict", "")).strip()

            semantic_score = round(0.35 * hook + 0.30 * standalone + 0.35 * entertainment, 1)
            if is_filler:
                semantic_score = min(35.0, semantic_score)

            return {
                "enabled": True,
                "score": semantic_score,
                "is_filler": is_filler,
                "verdict": verdict,
                "hook_score": hook,
                "standalone_score": standalone,
                "entertainment_score": entertainment,
            }
        except Exception as e:
            logger.debug(f"Semantic reranking query failed: {e}")
            return None

    def rerank(
        self,
        candidates: List[Dict[str, Any]],
        game_profile: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Reranks the top candidates using local Ollama if reachable.
        Blends semantic score (30%) with base composite score (70%).
        Leaves candidates untouched if Ollama is offline.
        """
        if not candidates:
            return []

        # Fast health check
        available = self.is_available()
        if not available:
            for c in candidates:
                if "semantic_audit" not in c:
                    c["semantic_audit"] = {"enabled": False}
            return candidates

        game_title = (
            getattr(game_profile, "detected_title", None)
            or getattr(game_profile, "display_name", None)
            or "Gaming"
        )
        game_archetype = getattr(game_profile, "archetype", "generic")

        # Evaluate top candidates
        target_count = min(len(candidates), self.max_candidates)
        for i in range(target_count):
            c = candidates[i]
            base_score = float(c.get("final_score", c.get("score", 50.0)))
            c["base_composite_score"] = base_score

            eval_res = self.evaluate_candidate(c, game_title=game_title, game_archetype=game_archetype)
            if eval_res and eval_res.get("enabled"):
                sem_score = eval_res["score"]
                reranked = round(0.70 * base_score + 0.30 * sem_score, 1)
                c["final_score"] = reranked
                c["score"] = reranked
                c["semantic_audit"] = eval_res
            else:
                c["semantic_audit"] = {"enabled": False}

        # For remaining candidates beyond max_candidates:
        for j in range(target_count, len(candidates)):
            candidates[j]["semantic_audit"] = {"enabled": False}
            if "base_composite_score" not in candidates[j]:
                candidates[j]["base_composite_score"] = float(candidates[j].get("final_score", 50.0))

        # Re-sort candidates by final_score descending
        candidates.sort(key=lambda x: x["final_score"], reverse=True)

        # Update ranks
        for idx, item in enumerate(candidates, start=1):
            item["rank"] = idx

        return candidates
