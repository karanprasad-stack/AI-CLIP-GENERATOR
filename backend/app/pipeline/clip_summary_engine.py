"""Clip Summary Engine: extracts structured, non-hallucinatory narrative intelligence from candidate signals."""

import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from backend.app.config import get_duration_tier


@dataclass
class ClipSummary:
    """Structured, verifiable summary of a candidate clip."""
    candidate_id: int
    duration: float
    game: str
    primary_event: str
    secondary_events: List[str]
    strongest_reaction: str
    climax_timestamp: float
    intensity: float
    tone: str
    has_facecam: bool
    visual_effect_count: int
    sfx_count: int
    source_signals: List[str] = field(default_factory=list)
    gameplay_stats: Dict[str, Any] = field(default_factory=dict)
    duration_tier: str = "standard"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "duration": round(self.duration, 2),
            "game": self.game,
            "primary_event": self.primary_event,
            "secondary_events": self.secondary_events,
            "strongest_reaction": self.strongest_reaction,
            "climax_timestamp": round(self.climax_timestamp, 2),
            "intensity": round(self.intensity, 3),
            "tone": self.tone,
            "has_facecam": self.has_facecam,
            "visual_effect_count": self.visual_effect_count,
            "sfx_count": self.sfx_count,
            "source_signals": self.source_signals,
            "gameplay_stats": self.gameplay_stats,
            "duration_tier": self.duration_tier,
        }


class ClipSummaryEngine:
    """Extracts verifiable clip intelligence across gameplay, transcript, visual, and audio layers."""

    GAME_PATTERNS = [
        (r"\b(cs:?go|cs2|counter-?strike)\b", "CS:GO", "Tactical FPS"),
        (r"\b(valorant|val)\b", "Valorant", "Tactical FPS"),
        (r"\b(apex(\s+legends)?)\b", "Apex Legends", "Battle Royale"),
        (r"\b(fortnite)\b", "Fortnite", "Battle Royale"),
        (r"\b(warzone|call\s+of\s+duty|cod)\b", "Call of Duty", "FPS"),
        (r"\b(gta\s*[v5]?|grand\s+theft\s+auto)\b", "GTA V", "Action"),
        (r"\b(minecraft)\b", "Minecraft", "Sandbox"),
        (r"\b(league\s+of\s+legends|lol)\b", "League of Legends", "MOBA"),
        (r"\b(overwatch|ow2?)\b", "Overwatch", "Hero Shooter"),
        (r"\b(rocket\s+league)\b", "Rocket League", "Sports/Action"),
    ]

    def detect_game(self, metadata: Optional[Dict[str, Any]]) -> str:
        """Identifies game title from video metadata without hallucinating."""
        if not metadata:
            return "Gaming"

        text_to_search = f"{metadata.get('title', '')} {metadata.get('description', '')}".lower()
        for pattern, name, _ in self.GAME_PATTERNS:
            if re.search(pattern, text_to_search, re.IGNORECASE):
                return name
        return "Gaming"

    def summarize_candidate(
        self,
        candidate: Dict[str, Any],
        video_metadata: Optional[Dict[str, Any]] = None,
        transcript_data: Optional[Dict[str, Any]] = None,
        phase5_timeline: Optional[Dict[str, Any]] = None,
        phase6a_timeline: Optional[Dict[str, Any]] = None,
    ) -> ClipSummary:
        """Builds a rich, truthful summary from existing pipeline evidence."""
        cand_id = int(candidate.get("rank", candidate.get("candidate_id", 1)))
        cand_start = float(candidate.get("candidate_start", 0.0))
        cand_end = float(candidate.get("candidate_end", 60.0))
        cand_dur = float(candidate.get("candidate_duration", cand_end - cand_start))

        # 1. Game Identification
        game = self.detect_game(video_metadata)

        # 2. Extract signals from gameplay event breakdown
        gameplay_bd = candidate.get("gameplay_event_breakdown", {})
        gaming_signals = gameplay_bd.get("gaming_lexical", {}).get("signals", [])
        reaction_signals = gameplay_bd.get("reaction_lexical", {}).get("signals", [])
        alignment_signals = gameplay_bd.get("audio_event_alignment", {}).get("signals", [])
        all_raw_signals = list(candidate.get("detected_signals", []))

        # Parse gaming event terms
        detected_events: List[str] = []
        for s in gaming_signals:
            name = s.split("@")[0].strip().lower()
            if name and name not in detected_events:
                detected_events.append(name)

        if not detected_events:
            # Fallback to general terms if any in all_raw_signals
            for s in all_raw_signals:
                if "@" in s and not s.startswith("audio_peak") and not s.startswith("phrase:") and not s.startswith("word:"):
                    name = s.split("@")[0].strip().lower()
                    if name not in detected_events:
                        detected_events.append(name)

        # Determine primary and secondary events
        priority_events = ["clutch", "headshot", "kill", "timing", "fail", "flash", "shot", "win", "revive"]
        sorted_events = sorted(
            detected_events,
            key=lambda e: priority_events.index(e) if e in priority_events else 99,
        )

        if sorted_events:
            primary_event = sorted_events[0]
            secondary_events = sorted_events[1:4] if len(sorted_events) > 1 else []
        elif reaction_signals:
            # If no combat word was found, anchor to vocal reaction
            rx_name = reaction_signals[0].split("@")[0].replace("phrase:", "").replace("word:", "").strip().lower()
            if rx_name in ["whoa", "wow", "what", "no way", "holy"]:
                primary_event = "shock"
            else:
                primary_event = "reaction"
            secondary_events = [rx_name] if rx_name else []
        elif alignment_signals:
            # Strong audio surge / scream / explosion
            primary_event = "chaos"
            secondary_events = ["audio surge"]
        else:
            primary_event = "gameplay highlight"
            secondary_events = []

        # Parse concrete verified gameplay events (Phase 12A/12B/12C)
        kills = 0
        headshots = 0
        aces = 0
        clutches = 0
        multi_kills = 0
        round_wins = 0
        spike_events = 0
        total_events = 0

        gameplay_events = candidate.get("gameplay_events", [])
        for ev in gameplay_events:
            ev_dict = ev if isinstance(ev, dict) else (ev.to_dict() if hasattr(ev, "to_dict") else vars(ev))
            if ev_dict.get("status") == "supporting":
                continue
            ev_type = str(ev_dict.get("event_type", "")).lower()
            meta = ev_dict.get("event_metadata", {}) or {}
            total_events += 1

            if ev_type in ("kill", "elimination"):
                kills += 1
                if meta.get("headshot") is True:
                    headshots += 1
            elif ev_type == "headshot":
                headshots += 1
                kills += 1
            elif ev_type in ("ace", "ace_candidate"):
                aces += 1
            elif ev_type in ("clutch", "clutch_candidate"):
                clutches += 1
            elif ev_type == "multi_kill":
                multi_kills += 1
            elif ev_type == "round_win":
                round_wins += 1
            elif ev_type in ("spike_planted", "spike_defused", "spike_denied"):
                spike_events += 1

        gameplay_stats = {
            "kills": kills,
            "headshots": headshots,
            "aces": aces,
            "clutches": clutches,
            "multi_kills": multi_kills,
            "round_wins": round_wins,
            "spike_events": spike_events,
            "total_events": total_events,
        }

        # Upgrade primary_event if high-value gameplay events exist
        if aces > 0:
            primary_event = "ace"
            if "ace" not in secondary_events:
                secondary_events.insert(0, "ace")
        elif clutches > 0:
            primary_event = "clutch"
            if "clutch" not in secondary_events:
                secondary_events.insert(0, "clutch")
        elif multi_kills > 0 or kills >= 3:
            primary_event = "multi-kill"
            if "multi-kill" not in secondary_events:
                secondary_events.insert(0, "multi-kill")
        elif headshots > 0 and primary_event in ("gameplay highlight", "reaction", "chaos"):
            primary_event = "headshot"
        elif kills > 0 and primary_event in ("gameplay highlight", "reaction", "chaos"):
            primary_event = "kill"

        duration_tier = candidate.get("duration_tier") or get_duration_tier(cand_dur)

        # 3. Extract Strongest Reaction
        strongest_reaction = "unknown"
        # Check phrase reactions first, then words
        phrase_rx = [s for s in reaction_signals if s.startswith("phrase:")]
        word_rx = [s for s in reaction_signals if s.startswith("word:")]

        if phrase_rx:
            strongest_reaction = phrase_rx[0].split("@")[0].replace("phrase:", "").strip()
        elif word_rx:
            strongest_reaction = word_rx[0].split("@")[0].replace("word:", "").strip()

        # 4. Climax Timestamp Determination
        # Climax is anchored around high-energy punch visual effects or strongest audio surge
        climax_t = cand_dur / 2.0  # sensible default

        # Try to find audio surge or reaction time
        candidate_timestamps: List[float] = []
        for s in all_raw_signals:
            if "@" in s:
                try:
                    time_part = s.split("@")[1].replace("s", "").strip()
                    abs_t = float(time_part)
                    if cand_start <= abs_t <= cand_end:
                        candidate_timestamps.append(abs_t - cand_start)
                except Exception:
                    pass

        # Try Phase 5 effects for climax
        p5_effects = []
        if phase5_timeline:
            p5_effects = phase5_timeline.get("effects", [])
        elif "timeline_data" in candidate:
            p5_effects = candidate["timeline_data"].get("effects", [])

        punch_times = [float(e.get("start", e.get("start_time", 0.0))) for e in p5_effects if "punch" in e.get("type", "")]

        if punch_times:
            climax_t = punch_times[0]
        elif candidate_timestamps:
            # Median of strong event timestamps
            climax_t = candidate_timestamps[len(candidate_timestamps) // 2]

        climax_t = max(0.0, min(cand_dur, climax_t))

        # 5. Tone & Intensity
        final_score = float(candidate.get("final_score", 70.0))
        intensity = min(1.0, max(0.0, final_score / 100.0))

        tone = "high-energy"
        lower_reaction = strongest_reaction.lower()
        if any(w in lower_reaction for w in ["whoa", "wow", "what", "holy", "insane", "no way"]):
            tone = "shock/disbelief"
        elif any(w in lower_reaction for w in ["timing", "fail", "lol", "why", "talk about timing"]):
            tone = "funny/chaotic"
        elif any(e in primary_event for e in ["clutch", "1v1", "1v3", "win"]):
            tone = "intense/clutch"

        # 6. Facecam & Counts
        has_facecam = (candidate.get("layout") == "facecam_gameplay")

        visual_count = len(p5_effects)
        if visual_count == 0:
            visual_count = int(candidate.get("effects_count", 0))

        sfx_count = int(candidate.get("sfx_count", 0))
        if sfx_count == 0 and phase6a_timeline:
            sfx_count = len(phase6a_timeline.get("audio_events", []))

        return ClipSummary(
            candidate_id=cand_id,
            duration=cand_dur,
            game=game,
            primary_event=primary_event,
            secondary_events=secondary_events,
            strongest_reaction=strongest_reaction,
            climax_timestamp=climax_t,
            intensity=intensity,
            tone=tone,
            has_facecam=has_facecam,
            visual_effect_count=visual_count,
            sfx_count=sfx_count,
            source_signals=all_raw_signals,
            gameplay_stats=gameplay_stats,
            duration_tier=duration_tier,
        )
