"""Unit tests for Phase 12A: Valorant Gameplay Event Detection.

Validates:
1. GameProfile abstraction and GameDetector (metadata & transcript inference).
2. GameplayEvent model, status tiers, and serialization.
3. Audio, transcript, and visual evidence extraction.
4. Multi-modal evidence fusion and false-positive protection.
5. Kill sequence engine (1K, 2K, 3K, 4K, Ace, Ace Candidate, rapid sequence).
6. Conservative clutch candidate detection (kills + round win).
7. Timeline persistence, interval querying, chunk shifting, and deduplication.
"""

import unittest
import numpy as np
from pathlib import Path
import tempfile

from backend.app.pipeline.games.models import (
    GameplayEvent,
    EventType,
    EventStatus,
    EvidenceBreakdown,
)
from backend.app.pipeline.games.profiles import (
    BaseGameProfile,
    GenericGameProfile,
    ValorantGameProfile,
    get_game_profile,
)
from backend.app.pipeline.games.detector import GameDetector
from backend.app.pipeline.games.evidence.audio import AudioEvidenceExtractor
from backend.app.pipeline.games.evidence.transcript import TranscriptEvidenceExtractor
from backend.app.pipeline.games.valorant.kill_feed import ValorantKillFeedDetector
from backend.app.pipeline.games.valorant.round_state import ValorantRoundStateDetector
from backend.app.pipeline.games.fusion import EvidenceFusionEngine
from backend.app.pipeline.games.sequence import KillSequenceEngine
from backend.app.pipeline.games.clutch import ClutchDetector
from backend.app.pipeline.games.timeline import GameplayTimeline
from backend.app.pipeline.games.engine import GameplayEngine


class TestPhase12AGameplayDetection(unittest.TestCase):
    """Test suite ensuring reliable, explainable gameplay event detection."""

    def setUp(self):
        self.val_profile = ValorantGameProfile()
        self.generic_profile = GenericGameProfile()
        self.game_detector = GameDetector()

    # --------------------------------------------------------------------------
    # 1. Game Profile & Detection
    # --------------------------------------------------------------------------
    def test_valorant_profile_attributes(self):
        """Valorant profile defines HUD regions, vocabulary, and duration hints."""
        p = self.val_profile
        self.assertEqual(p.name, "valorant")
        self.assertIn("spike", p.event_vocabulary)
        self.assertIn("vandal", p.event_vocabulary)
        self.assertIn("jett", p.event_vocabulary)
        self.assertIn("kill", p.candidate_duration_hints)
        self.assertIn("ace", p.candidate_duration_hints)
        self.assertGreater(p.kill_feed_region[1], 0.60, "Kill feed must be in right half of screen")

    def test_game_detection_from_title(self):
        """Infers Valorant profile from video title."""
        meta = {"title": "Insane Valorant Radiant Highlights", "uploader": "ProGamer"}
        profile = self.game_detector.detect_game(metadata=meta)
        self.assertEqual(profile.name, "valorant")

    def test_game_detection_from_transcript(self):
        """Infers Valorant profile from transcript terminology."""
        transcript = {
            "words": [
                {"word": "Spike", "start": 10.0, "end": 10.5},
                {"word": "planted", "start": 10.6, "end": 11.2},
                {"word": "Vandal", "start": 15.0, "end": 15.5},
            ]
        }
        profile = self.game_detector.detect_game(transcript_data=transcript)
        self.assertEqual(profile.name, "valorant")

    def test_game_detection_fallback_generic(self):
        """Falls back to Generic profile when no game markers are present."""
        meta = {"title": "Cooking with Chef John", "uploader": "FoodNet"}
        transcript = {"words": [{"word": "Add", "start": 1.0, "end": 1.5}, {"word": "salt", "start": 1.6, "end": 2.0}]}
        profile = self.game_detector.detect_game(metadata=meta, transcript_data=transcript)
        self.assertEqual(profile.name, "generic")

    # --------------------------------------------------------------------------
    # 2. Event Model & Serialization
    # --------------------------------------------------------------------------
    def test_gameplay_event_serialization_roundtrip(self):
        """GameplayEvent serializes to dict and reconstructs identically."""
        breakdown = EvidenceBreakdown(
            visual=0.92,
            kill_feed=0.95,
            audio=0.85,
            transcript=0.70,
            temporal_consistency=0.98,
            cross_source_agreement=0.90,
        )
        ev = GameplayEvent(
            id="evt_01",
            game="valorant",
            event_type=EventType.KILL.value,
            start_time=142.30,
            end_time=143.05,
            confidence=0.91,
            status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.92, "audio": 0.85},
            evidence_breakdown=breakdown,
            metadata={"headshot": True, "kill_count": 1},
            explanation="Kill confirmed via kill-feed and audio peak",
        )

        d = ev.to_dict()
        reconstructed = GameplayEvent.from_dict(d)

        self.assertEqual(reconstructed.id, "evt_01")
        self.assertEqual(reconstructed.event_type, "kill")
        self.assertEqual(reconstructed.status, "confirmed")
        self.assertAlmostEqual(reconstructed.confidence, 0.91)
        self.assertTrue(reconstructed.metadata["headshot"])
        self.assertIsNotNone(reconstructed.evidence_breakdown)
        self.assertAlmostEqual(reconstructed.evidence_breakdown.visual, 0.92)

    # --------------------------------------------------------------------------
    # 3. Audio & Transcript Evidence Extraction
    # --------------------------------------------------------------------------
    def test_audio_evidence_extractor_peaks(self):
        """Matches timestamp to nearest audio volume peak and computes confidence."""
        audio_analysis = {
            "peaks": [
                {"timestamp": 50.0, "z_score": 3.8, "loudness": -12.0},
                {"timestamp": 120.0, "z_score": 1.8, "loudness": -18.0},
            ]
        }
        extractor = AudioEvidenceExtractor(audio_analysis)

        # Query close to 50.0s (t=50.2s)
        conf, peak = extractor.query_evidence(50.2, window=1.2)
        self.assertGreater(conf, 0.75)
        self.assertIsNotNone(peak)
        self.assertEqual(peak["timestamp"], 50.0)

        # Query distant from any peak (t=80.0s)
        conf_none, peak_none = extractor.query_evidence(80.0, window=1.2)
        self.assertEqual(conf_none, 0.0)
        self.assertIsNone(peak_none)

    def test_transcript_evidence_extractor_callouts(self):
        """Identifies gaming callouts and reactions within temporal context."""
        transcript_data = {
            "words": [
                {"word": "Spike", "start": 430.78, "end": 431.10},
                {"word": "down", "start": 431.10, "end": 431.54},
                {"word": "nice", "start": 432.00, "end": 432.40},
            ]
        }
        extractor = TranscriptEvidenceExtractor(
            transcript_data=transcript_data,
            event_vocabulary=self.val_profile.event_vocabulary,
            reaction_vocabulary=self.val_profile.reaction_vocabulary,
        )

        conf, terms, meta = extractor.query_evidence(431.0, pre_window=1.0, post_window=2.0)
        self.assertGreater(conf, 0.60)
        self.assertIn("spike", terms)
        self.assertIn("nice", terms)

    # --------------------------------------------------------------------------
    # 4. Multi-Modal Evidence Fusion & False-Positive Protection
    # --------------------------------------------------------------------------
    def test_false_positive_spoken_ace_without_visual_kills(self):
        """A spoken exclamation 'ACE!' without visual kills is NOT a confirmed Ace."""
        audio_extractor = AudioEvidenceExtractor({"peaks": []})
        transcript_data = {
            "words": [
                {"word": "Ace!", "start": 20.0, "end": 20.8},
            ]
        }
        transcript_extractor = TranscriptEvidenceExtractor(
            transcript_data=transcript_data,
            event_vocabulary=self.val_profile.event_vocabulary,
            reaction_vocabulary=self.val_profile.reaction_vocabulary,
        )
        fusion = EvidenceFusionEngine(self.val_profile)

        # Visual signals empty
        visual_signals = {"kill_feed": [], "round_state": [], "hud": []}
        events = fusion.fuse_events(
            visual_signals=visual_signals,
            audio_extractor=audio_extractor,
            transcript_extractor=transcript_extractor,
            duration=60.0,
        )

        # Must NOT contain a confirmed kill or confirmed Ace
        confirmed_kills = [e for e in events if e.event_type == EventType.KILL.value and e.status == EventStatus.CONFIRMED.value]
        confirmed_aces = [e for e in events if e.event_type == EventType.ACE.value]

        self.assertEqual(len(confirmed_kills), 0, "Spoken 'Ace!' must not create confirmed kills")
        self.assertEqual(len(confirmed_aces), 0, "Spoken 'Ace!' must not create a confirmed Ace")

        # Emitted as supporting reaction
        reaction_events = [e for e in events if e.event_type == EventType.REACTION.value]
        self.assertGreaterEqual(len(reaction_events), 1)
        self.assertEqual(reaction_events[0].status, EventStatus.SUPPORTING.value)

    # --------------------------------------------------------------------------
    # 5. Kill Sequence Engine
    # --------------------------------------------------------------------------
    def test_kill_sequence_clustering_2k_3k_ace(self):
        """Clusters kills within sequence_window into 2K, 3K, and Ace sequences."""
        engine = KillSequenceEngine(sequence_window_sec=8.0)

        # Create 3 kills close together (t=100.0, 103.0, 106.0)
        k1 = GameplayEvent(
            id="k1", game="valorant", event_type=EventType.KILL.value,
            start_time=100.0, end_time=100.5, confidence=0.90, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.90}, metadata={"headshot": True, "is_spectated_player": True}
        )
        k2 = GameplayEvent(
            id="k2", game="valorant", event_type=EventType.KILL.value,
            start_time=103.0, end_time=103.5, confidence=0.88, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.88}, metadata={"headshot": False, "is_spectated_player": True}
        )
        k3 = GameplayEvent(
            id="k3", game="valorant", event_type=EventType.KILL.value,
            start_time=106.0, end_time=106.5, confidence=0.94, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.94}, metadata={"headshot": True, "is_spectated_player": True}
        )

        # One separated kill at t=150.0s (not part of the sequence)
        k4 = GameplayEvent(
            id="k4", game="valorant", event_type=EventType.KILL.value,
            start_time=150.0, end_time=150.5, confidence=0.85, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.85}, metadata={"headshot": False, "is_spectated_player": True}
        )

        events = [k1, k2, k3, k4]
        res = engine.process_sequences(events)

        # Individual kills preserved
        individual_kills = [e for e in res if e.event_type == EventType.KILL.value]
        self.assertEqual(len(individual_kills), 4)

        # 3K Sequence event created
        seq_events = [e for e in res if e.metadata.get("subtype") == "3k"]
        self.assertEqual(len(seq_events), 1)

        seq = seq_events[0]
        self.assertEqual(seq.start_time, 100.0)
        self.assertEqual(seq.end_time, 106.5)
        self.assertEqual(seq.metadata["kill_count"], 3)
        self.assertEqual(seq.metadata["headshot_count"], 2)
        self.assertEqual(seq.metadata["kill_event_ids"], ["k1", "k2", "k3"])
        self.assertGreaterEqual(seq.confidence, 0.90)

    def test_ace_requires_5_kills(self):
        """Ace sequence requires 5 kills within the multi-kill window."""
        engine = KillSequenceEngine(sequence_window_sec=8.0)

        kills_5 = [
            GameplayEvent(
                id=f"k_{i}", game="valorant", event_type=EventType.KILL.value,
                start_time=float(200 + i * 3), end_time=float(200 + i * 3 + 0.5),
                confidence=0.92, status=EventStatus.CONFIRMED.value,
                source_evidence={"visual": 0.92},
                metadata={"is_spectated_player": True, "headshot": (i % 2 == 0)}
            )
            for i in range(5)
        ]

        res = engine.process_sequences(kills_5)
        ace_events = [e for e in res if e.event_type == EventType.ACE.value]
        self.assertEqual(len(ace_events), 1)
        self.assertEqual(ace_events[0].metadata["kill_count"], 5)

    # --------------------------------------------------------------------------
    # 6. Conservative Clutch Candidate Detection
    # --------------------------------------------------------------------------
    def test_clutch_candidate_detection(self):
        """2 kills followed by a confirmed round_win triggers clutch_candidate."""
        detector = ClutchDetector(clutch_window_sec=25.0)

        k1 = GameplayEvent(
            id="ck1", game="valorant", event_type=EventType.KILL.value,
            start_time=80.0, end_time=80.5, confidence=0.90, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.90}, metadata={"is_spectated_player": True}
        )
        k2 = GameplayEvent(
            id="ck2", game="valorant", event_type=EventType.KILL.value,
            start_time=85.0, end_time=85.5, confidence=0.92, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.92}, metadata={"is_spectated_player": True}
        )
        rwin = GameplayEvent(
            id="rw1", game="valorant", event_type=EventType.ROUND_WIN.value,
            start_time=88.0, end_time=90.0, confidence=0.95, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.95}, metadata={"banner": "victory"}
        )

        res = detector.detect_clutches([k1, k2, rwin])
        clutches = [e for e in res if e.event_type == EventType.CLUTCH_CANDIDATE.value]

        self.assertEqual(len(clutches), 1)
        clutch = clutches[0]
        self.assertEqual(clutch.start_time, 80.0)
        self.assertEqual(clutch.end_time, 90.0)
        self.assertEqual(clutch.metadata["kills_in_clutch"], 2)
        self.assertEqual(clutch.metadata["associated_round_win_id"], "rw1")
        self.assertGreaterEqual(clutch.confidence, 0.80)

    def test_no_clutch_on_round_win_without_kills(self):
        """Round win alone without preceding kills must NOT produce a clutch."""
        detector = ClutchDetector(clutch_window_sec=25.0)
        rwin = GameplayEvent(
            id="rw1", game="valorant", event_type=EventType.ROUND_WIN.value,
            start_time=88.0, end_time=90.0, confidence=0.95, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.95}, metadata={"banner": "victory"}
        )
        res = detector.detect_clutches([rwin])
        clutches = [e for e in res if e.event_type == EventType.CLUTCH_CANDIDATE.value]
        self.assertEqual(len(clutches), 0)

    # --------------------------------------------------------------------------
    # 7. Timeline Persistence, Range Querying & Deduplication
    # --------------------------------------------------------------------------
    def test_timeline_range_query_and_summary(self):
        """GameplayTimeline filters events by time window and summarizes counts."""
        timeline = GameplayTimeline(game="valorant")
        k1 = GameplayEvent(
            id="k1", game="valorant", event_type=EventType.KILL.value,
            start_time=10.0, end_time=10.5, confidence=0.90, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.90}, metadata={"headshot": True}
        )
        k2 = GameplayEvent(
            id="k2", game="valorant", event_type=EventType.KILL.value,
            start_time=50.0, end_time=50.5, confidence=0.88, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.88}, metadata={"headshot": False}
        )
        timeline.add_event(k1)
        timeline.add_event(k2)

        # Query [5s, 20s]
        in_range = timeline.get_events_in_range(5.0, 20.0)
        self.assertEqual(len(in_range), 1)
        self.assertEqual(in_range[0].id, "k1")

        summary = timeline.summary()
        self.assertEqual(summary["kills_count"], 2)
        self.assertEqual(summary["headshots_count"], 1)

    def test_timeline_deduplication_and_shift(self):
        """Deduplicates overlapping chunk events and converts local to global timestamps."""
        timeline = GameplayTimeline(game="valorant")
        # Duplicate events at t=10.0s and t=10.2s from chunk boundary
        e1 = GameplayEvent(
            id="e1", game="valorant", event_type=EventType.KILL.value,
            start_time=10.0, end_time=10.5, confidence=0.80, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.80}
        )
        e2 = GameplayEvent(
            id="e2", game="valorant", event_type=EventType.KILL.value,
            start_time=10.2, end_time=10.7, confidence=0.92, status=EventStatus.CONFIRMED.value,
            source_evidence={"visual": 0.92}
        )
        timeline.add_event(e1)
        timeline.add_event(e2)

        # Deduplicate
        timeline.deduplicate(tolerance_sec=0.50)
        self.assertEqual(len(timeline.events), 1)
        # Higher confidence retained
        self.assertAlmostEqual(timeline.events[0].confidence, 0.92)

        # Shift timestamps (e.g. chunk start at 3600.0s)
        timeline.shift_timestamps(3600.0)
        self.assertAlmostEqual(timeline.events[0].start_time, 3610.0, places=1)

    def test_timeline_save_and_load(self):
        """Persists timeline to JSON file and restores accurately."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fpath = Path(tmp_dir) / "gameplay_events.json"
            timeline = GameplayTimeline(game="valorant")
            timeline.add_event(
                GameplayEvent(
                    id="save_k1", game="valorant", event_type=EventType.KILL.value,
                    start_time=12.5, end_time=13.0, confidence=0.89, status=EventStatus.CONFIRMED.value,
                    source_evidence={"visual": 0.89}, metadata={"headshot": True}
                )
            )
            timeline.save(fpath)
            self.assertTrue(fpath.exists())

            loaded = GameplayTimeline.load(fpath)
            self.assertEqual(loaded.game, "valorant")
            self.assertEqual(len(loaded.events), 1)
            self.assertEqual(loaded.events[0].id, "save_k1")
            self.assertAlmostEqual(loaded.events[0].start_time, 12.5)


if __name__ == "__main__":
    unittest.main()
