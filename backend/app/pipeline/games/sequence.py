"""Kill Sequence Engine: clusters individual kills into 2K, 3K, 4K, Ace, and rapid kill sequences."""

import uuid
from typing import List, Dict, Any, Optional

from .models import GameplayEvent, EventType, EventStatus, EvidenceBreakdown


class KillSequenceEngine:
    """Clustering engine that groups temporal kill chains into structured multi-kill sequences."""

    def __init__(self, sequence_window_sec: float = 9.0):
        self.sequence_window_sec = sequence_window_sec

    def process_sequences(self, events: List[GameplayEvent]) -> List[GameplayEvent]:
        """
        Scans all events, detects kill clusters within sequence_window_sec,
        and generates sequence events while preserving all underlying individual events.
        """
        kill_events = [e for e in events if e.event_type == EventType.KILL.value]
        if not kill_events:
            return events

        # Sort kills chronologically
        sorted_kills = sorted(kill_events, key=lambda k: k.start_time)

        sequences: List[List[GameplayEvent]] = []
        current_seq: List[GameplayEvent] = [sorted_kills[0]]

        for next_kill in sorted_kills[1:]:
            last_kill = current_seq[-1]
            # Time delta between successive kills
            gap = next_kill.start_time - last_kill.end_time

            if gap <= self.sequence_window_sec:
                current_seq.append(next_kill)
            else:
                if len(current_seq) >= 2:
                    sequences.append(current_seq)
                current_seq = [next_kill]

        if len(current_seq) >= 2:
            sequences.append(current_seq)

        generated_sequence_events: List[GameplayEvent] = []

        for seq in sequences:
            count = len(seq)
            start_t = seq[0].start_time
            end_t = seq[-1].end_time
            dur = round(end_t - start_t, 3)

            # Average confidence of constituent kills + temporal density bonus
            avg_conf = sum(k.confidence for k in seq) / float(count)
            density_bonus = min(0.08, 0.02 * count)
            seq_conf = min(0.99, round(avg_conf + density_bonus, 3))

            headshot_count = sum(1 for k in seq if k.metadata.get("headshot", False))
            all_spectated = all(k.metadata.get("is_spectated_player", False) for k in seq)
            any_spectated = any(k.metadata.get("is_spectated_player", False) for k in seq)

            kill_ids = [k.id for k in seq]

            meta = {
                "kill_count": count,
                "duration": dur,
                "kill_event_ids": kill_ids,
                "headshot_count": headshot_count,
                "all_spectated_player": all_spectated,
                "any_spectated_player": any_spectated,
            }

            # Map sequence count to appropriate Tier 1 event type
            if count == 2:
                ev_type = EventType.MULTI_KILL.value
                subtype = "2k"
                title = "2K Multi-Kill"
            elif count == 3:
                ev_type = EventType.MULTI_KILL.value
                subtype = "3k"
                title = "3K Multi-Kill"
            elif count == 4:
                ev_type = EventType.MULTI_KILL.value
                subtype = "4k"
                title = "4K Multi-Kill"
            else:  # 5 or more kills
                # Strict Ace protection: 5 confirmed kills by same spectated player -> ACE, else ACE_CANDIDATE
                if all_spectated and count >= 5:
                    ev_type = EventType.ACE.value
                    subtype = "ace"
                    title = "ACE"
                else:
                    ev_type = EventType.ACE_CANDIDATE.value
                    subtype = "ace_candidate"
                    title = f"Ace Candidate ({count} Kills)"

            meta["subtype"] = subtype

            # Build evidence breakdown aggregating constituent kills
            vis_avg = sum(k.source_evidence.get("visual", 0.0) for k in seq) / float(count)
            aud_avg = sum(k.source_evidence.get("audio", 0.0) for k in seq) / float(count)
            tr_avg = sum(k.source_evidence.get("transcript", 0.0) for k in seq) / float(count)

            breakdown = EvidenceBreakdown(
                visual=round(vis_avg, 3),
                kill_feed=round(vis_avg, 3),
                audio=round(aud_avg, 3),
                transcript=round(tr_avg, 3),
                temporal_consistency=0.98,
                cross_source_agreement=0.95,
                raw_signals={"constituent_kills": count, "headshots": headshot_count}
            )

            status = EventStatus.CONFIRMED.value if seq_conf >= 0.75 else EventStatus.CANDIDATE.value

            seq_event = GameplayEvent(
                id=f"seq_{subtype}_{uuid.uuid4().hex[:8]}",
                game=seq[0].game,
                event_type=ev_type,
                start_time=start_t,
                end_time=end_t,
                confidence=seq_conf,
                status=status,
                source_evidence={"visual": vis_avg, "audio": aud_avg, "transcript": tr_avg},
                evidence_breakdown=breakdown,
                metadata=meta,
                explanation=f"{title}: {count} rapid kills in {dur:.1f}s ({headshot_count} headshot(s))",
            )
            generated_sequence_events.append(seq_event)

            # Rapid kill sequence detection: if average time between kills is < 2.5s
            if count >= 2 and (dur / count) <= 2.5:
                generated_sequence_events.append(
                    GameplayEvent(
                        id=f"seq_rapid_{uuid.uuid4().hex[:8]}",
                        game=seq[0].game,
                        event_type=EventType.RAPID_KILL_SEQUENCE.value,
                        start_time=start_t,
                        end_time=end_t,
                        confidence=min(0.98, seq_conf + 0.01),
                        status=status,
                        source_evidence=seq_event.source_evidence,
                        metadata={"associated_sequence_id": seq_event.id, "pace_sec_per_kill": round(dur / count, 2)},
                        explanation=f"Rapid kill sequence ({count} kills with {dur/count:.1f}s pace)",
                    )
                )

        # Merge original events with new sequence events and sort chronologically
        combined = list(events) + generated_sequence_events
        combined.sort(key=lambda e: (e.start_time, e.end_time))
        return combined
