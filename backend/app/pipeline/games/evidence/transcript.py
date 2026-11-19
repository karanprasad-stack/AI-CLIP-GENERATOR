"""Extracts localized transcript callouts, gaming terms, and reaction evidence."""

from typing import Dict, Any, List, Optional, Tuple, Set


class TranscriptEvidenceExtractor:
    """Extracts localized speech callouts, tactical terms, and vocal reactions to corroborate gameplay."""

    def __init__(
        self,
        transcript_data: Optional[Dict[str, Any]] = None,
        event_vocabulary: Optional[List[str]] = None,
        reaction_vocabulary: Optional[List[str]] = None,
    ):
        self.words: List[Dict[str, Any]] = []
        if transcript_data:
            if "words" in transcript_data and transcript_data["words"]:
                self.words = sorted(transcript_data["words"], key=lambda w: float(w.get("start", 0.0)))
            elif "segments" in transcript_data:
                all_w = []
                for s in transcript_data["segments"]:
                    all_w.extend(s.get("words", []))
                self.words = sorted(all_w, key=lambda w: float(w.get("start", 0.0)))

        self.event_vocab: Set[str] = set(v.lower() for v in (event_vocabulary or []))
        self.reaction_vocab: Set[str] = set(r.lower() for r in (reaction_vocabulary or []))

    def query_evidence(
        self,
        timestamp: float,
        pre_window: float = 1.0,
        post_window: float = 3.5,
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        Queries speech terms occurring within [timestamp - pre_window, timestamp + post_window].
        Returns:
            (confidence: float, matched_terms: List[str], metadata: dict)
        """
        if not self.words:
            return 0.0, [], {}

        t_min = timestamp - pre_window
        t_max = timestamp + post_window

        relevant_words = [
            w for w in self.words
            if t_min <= float(w.get("start", 0.0)) <= t_max
        ]

        if not relevant_words:
            return 0.0, [], {}

        matched_events = []
        matched_reactions = []

        for w in relevant_words:
            raw_text = str(w.get("word", "")).lower().strip(".,!?:;\"'()")
            if not raw_text:
                continue

            if raw_text in self.event_vocab or raw_text in ["kill", "headshot", "clutch", "ace", "one tap", "1 tap", "spike", "defuse"]:
                matched_events.append(raw_text)
            elif raw_text in self.reaction_vocab or raw_text in ["nice", "let's go", "holy", "insane", "bhai", "omg", "sheesh"]:
                matched_reactions.append(raw_text)

        all_matched = list(dict.fromkeys(matched_events + matched_reactions))
        if not all_matched:
            return 0.0, [], {}

        # Scoring: High-signal game terms provide higher confidence than pure generic reaction
        conf = 0.35
        if matched_events:
            conf += 0.35
            if any(t in ["headshot", "one tap", "clutch", "ace", "spike"] for t in matched_events):
                conf += 0.15
        if matched_reactions:
            conf += 0.15

        conf = min(0.95, round(conf, 3))
        meta = {
            "events": matched_events,
            "reactions": matched_reactions,
            "terms_count": len(all_matched),
        }

        return conf, all_matched, meta
