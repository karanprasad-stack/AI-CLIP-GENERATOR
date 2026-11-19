import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np

from backend.app.pipeline.clip_summary_engine import ClipSummary, ClipSummaryEngine
from backend.app.pipeline.title_engine import TitleEngine, compute_title_similarity
from backend.app.pipeline.description_engine import DescriptionEngine, compute_description_similarity
from backend.app.pipeline.hashtag_engine import HashtagEngine
from backend.app.pipeline.publishing_package import PublishingPackageManager


class TestPhase6B1MetadataRefinement(unittest.TestCase):
    def setUp(self):
        self.summary_engine = ClipSummaryEngine()
        self.title_engine = TitleEngine(ollama_enabled=False)
        self.desc_engine = DescriptionEngine()
        self.hashtag_engine = HashtagEngine()

        self.summary_timing = ClipSummary(
            candidate_id=1,
            duration=43.2,
            game="CS:GO",
            primary_event="timing",
            secondary_events=["fail", "shot"],
            strongest_reaction="talk about timing",
            climax_timestamp=18.9,
            intensity=0.88,
            tone="funny/chaotic",
            has_facecam=True,
            visual_effect_count=7,
            sfx_count=4,
            source_signals=["timing@178.6s", "fail@162.1s"],
        )

        self.summary_flash = ClipSummary(
            candidate_id=2,
            duration=37.5,
            game="CS:GO",
            primary_event="flash",
            secondary_events=["shot"],
            strongest_reaction="what",
            climax_timestamp=4.15,
            intensity=0.75,
            tone="shock/disbelief",
            has_facecam=True,
            visual_effect_count=3,
            sfx_count=1,
            source_signals=["flash@189.0s"],
        )

        self.summary_clutch = ClipSummary(
            candidate_id=3,
            duration=50.0,
            game="CS:GO",
            primary_event="clutch",
            secondary_events=["shot", "kill"],
            strongest_reaction="no way",
            climax_timestamp=35.0,
            intensity=0.95,
            tone="intense/clutch",
            has_facecam=False,
            visual_effect_count=5,
            sfx_count=3,
            source_signals=["clutch@120.0s", "kill@130.0s"],
        )

    # --------------------------------------------------------------------------
    # Title Tests
    # --------------------------------------------------------------------------

    def test_title_similarity_computation(self):
        t1 = "That Timing Was WAY Too Perfect 💀"
        t2 = "That Timing Was WAY Too Perfect 💀"
        self.assertEqual(compute_title_similarity(t1, t2), 1.0)

        # Minor variation
        t3 = "The Timing Was So Perfect 💀"
        sim_high = compute_title_similarity(t1, t3)
        self.assertGreaterEqual(sim_high, 0.40)

        # Distinct concept
        t4 = "He Did NOT See That Flash Coming 😭"
        sim_low = compute_title_similarity(t1, t4)
        self.assertLess(sim_low, 0.3)

    def test_cross_candidate_title_deduplication(self):
        # Candidate 1 picks a title
        res1 = self.title_engine.generate_and_rank_titles(self.summary_timing)
        title1 = res1["selected_title"]

        # Candidate 2 with similar signals must not receive title1 or near-identical title
        summary_timing_2 = ClipSummary(
            candidate_id=4,
            duration=40.0,
            game="CS:GO",
            primary_event="timing",
            secondary_events=["fail"],
            strongest_reaction="talk about timing",
            climax_timestamp=20.0,
            intensity=0.85,
            tone="funny/chaotic",
            has_facecam=True,
            visual_effect_count=4,
            sfx_count=2,
        )
        res2 = self.title_engine.generate_and_rank_titles(summary_timing_2, existing_titles=[title1])
        title2 = res2["selected_title"]

        self.assertNotEqual(title1, title2)
        sim = compute_title_similarity(title1, title2)
        self.assertLess(sim, 0.70, f"Title 2 '{title2}' is too similar to Title 1 '{title1}' (sim: {sim})")

    def test_generic_title_penalization(self):
        generic = "Insane CS:GO Gameplay Highlight Moment 🎯"
        score_gen, bd_gen = self.title_engine.score_title(generic, self.summary_timing)

        specific = "That Timing Was WAY Too Perfect 💀"
        score_spec, bd_spec = self.title_engine.score_title(specific, self.summary_timing)

        self.assertGreater(score_spec, score_gen)
        self.assertLess(bd_gen["specificity"], 0.3)

    def test_unsupported_claim_rejection(self):
        # Title claiming 1v5 clutch when clutch is not in summary signals
        valid, msg = self.title_engine.validate_title("The Greatest 1v5 Clutch Ever 🔥", self.summary_timing)
        self.assertFalse(valid)
        self.assertIn("1v5", msg)

    def test_punctuation_and_caps_validation(self):
        valid_p, _ = self.title_engine.validate_title("NO WAY?!?!?!?", self.summary_timing)
        self.assertFalse(valid_p)

        valid_c, _ = self.title_engine.validate_title("THIS IS ENTIRELY UPPERCASE TITLE FOR SHORTS", self.summary_timing)
        self.assertFalse(valid_c)

    def test_title_semantic_styles(self):
        # Timing style
        res_t = self.title_engine.generate_rule_based_titles(self.summary_timing)
        self.assertTrue(any("timing" in t.lower() for t in res_t))

        # Flash style
        res_f = self.title_engine.generate_rule_based_titles(self.summary_flash)
        self.assertTrue(any("flash" in t.lower() for t in res_f))

        # Clutch style
        res_c = self.title_engine.generate_rule_based_titles(self.summary_clutch)
        self.assertTrue(any("clutch" in t.lower() for t in res_c))

    # --------------------------------------------------------------------------
    # Description Tests
    # --------------------------------------------------------------------------

    def test_description_candidate_specific_and_length(self):
        desc1 = self.desc_engine.generate_description(
            summary=self.summary_timing,
            selected_title="That Timing Was WAY Too Perfect 💀",
            hashtags=["#Shorts", "#CSGO"],
            source_metadata={"uploader": "Nick", "title": "CSGO Moments"},
        )
        self.assertGreaterEqual(len(desc1), 40)
        self.assertLessEqual(len(desc1), 500)
        self.assertIn("timing", desc1.lower())
        self.assertIn("Nick", desc1)

        desc2 = self.desc_engine.generate_description(
            summary=self.summary_flash,
            selected_title="He Did NOT See That Flash Coming 😭",
            hashtags=["#Shorts", "#CSGO"],
            source_metadata={"uploader": "Nick", "title": "CSGO Moments"},
        )
        self.assertIn("flash", desc2.lower())
        self.assertNotEqual(desc1, desc2)

    # --------------------------------------------------------------------------
    # Hashtags & Keyword Tests
    # --------------------------------------------------------------------------

    def test_hashtags_range_and_deduplication(self):
        tags = self.hashtag_engine.generate_hashtags(self.summary_flash)
        self.assertGreaterEqual(len(tags), 4)
        self.assertLessEqual(len(tags), 8)
        self.assertIn("#Shorts", tags)
        self.assertIn("#CSGO", tags)

        # Unique lower
        low_tags = [t.lower() for t in tags]
        self.assertEqual(len(low_tags), len(set(low_tags)))

    def test_keywords_candidate_specific(self):
        kws = self.hashtag_engine.generate_keywords(self.summary_clutch)
        self.assertGreaterEqual(len(kws), 5)
        low_kws = [k.lower() for k in kws]
        self.assertIn("cs:go", low_kws)
        self.assertTrue(any("clutch" in k for k in low_kws))

    # --------------------------------------------------------------------------
    # Metadata Quality Score Test
    # --------------------------------------------------------------------------

    def test_metadata_quality_scoring(self):
        quality = self.title_engine.compute_metadata_quality(
            title="That Timing Was WAY Too Perfect 💀",
            summary=self.summary_timing,
            description="When the timing lines up like this in CS:GO, you just have to laugh.\n\n#Shorts #CSGO",
            hashtags=["#Shorts", "#CSGO", "#Timing"],
            existing_titles=[],
        )
        self.assertIn("overall", quality)
        self.assertIn("relevance", quality)
        self.assertIn("specificity", quality)
        self.assertIn("naturalness", quality)
        self.assertIn("uniqueness", quality)
        self.assertIn("grounding", quality)

        self.assertGreaterEqual(quality["overall"], 0.80)
        self.assertLessEqual(quality["overall"], 1.0)
        self.assertEqual(quality["grounding"], 1.0)

    # --------------------------------------------------------------------------
    # Fallback Tests
    # --------------------------------------------------------------------------

    def test_ollama_failure_fallback(self):
        # Broken port ensures timeout / connection refusal
        engine_broken_llm = TitleEngine(
            ollama_enabled=True,
            ollama_host="http://localhost:59999",
        )
        res = engine_broken_llm.generate_and_rank_titles(self.summary_timing)
        self.assertIsNotNone(res["selected_title"])
        self.assertEqual(res["generation_mode"], "rule_based")
        self.assertGreater(len(res["selected_title"]), 5)

    # --------------------------------------------------------------------------
    # Packaging Integration Test
    # --------------------------------------------------------------------------

    def test_publishing_package_includes_quality_metadata(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            pub_dir = base_dir / "publishing"
            pub_dir.mkdir(parents=True, exist_ok=True)

            mock_mp4 = base_dir / "mock.mp4"
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(str(mock_mp4), fourcc, 30.0, (1280, 720))
            for _ in range(30):
                out.write(np.ones((720, 1280, 3), dtype=np.uint8) * 100)
            out.release()

            manager = PublishingPackageManager()
            candidate = {
                "candidate_id": 1,
                "candidate_start": 0.0,
                "candidate_end": 1.0,
                "candidate_duration": 1.0,
                "audio_polished_clip": str(mock_mp4),
                "final_score": 88.0,
                "detected_signals": ["timing@0.5s", "phrase:talk about timing@0.6s"],
            }
            meta = {"id": "vid1", "title": "CSGO Fun", "uploader": "Nick"}

            pkg = manager.build_candidate_package(
                candidate_idx=1,
                candidate=candidate,
                publishing_dir=pub_dir,
                source_video_path=mock_mp4,
                source_metadata=meta,
            )

            self.assertEqual(pkg["validation"]["status"], "PASS")
            self.assertIn("metadata_quality", pkg)
            self.assertGreater(pkg["metadata_quality"]["overall"], 0.75)

            # Check that candidate's metadata.json on disk includes metadata_quality
            disk_meta_path = Path(pkg["package_dir"]) / "metadata.json"
            import json
            with open(disk_meta_path, "r", encoding="utf-8") as f:
                disk_meta = json.load(f)
            self.assertIn("metadata_quality", disk_meta)

    # --------------------------------------------------------------------------
    # Phase 6B.1.1 Follow-up Tests: Description Dedup & Short Title Refinement
    # --------------------------------------------------------------------------

    def test_duplicate_descriptions_prevented(self):
        desc1 = self.desc_engine.generate_description(
            summary=self.summary_timing,
            selected_title="The Most Painful CS:GO Fail Ever 💀",
            hashtags=["#Shorts", "#CSGO"],
            source_metadata={"uploader": "Nick", "title": "CSGO Moments"},
        )
        # Second call with existing_descriptions must yield a different narrative hook
        desc2 = self.desc_engine.generate_description(
            summary=self.summary_timing,
            selected_title="The Worst Possible Timing In CS:GO 😂",
            hashtags=["#Shorts", "#CSGO"],
            source_metadata={"uploader": "Nick", "title": "CSGO Moments"},
            existing_descriptions=[desc1],
        )
        self.assertNotEqual(desc1, desc2)
        sim = compute_description_similarity(desc1, desc2)
        self.assertLess(sim, 0.50, f"Description similarity {sim} exceeds threshold 0.50")

    def test_near_duplicate_descriptions_prevented(self):
        summary_timing_2 = ClipSummary(
            candidate_id=4,
            duration=40.0,
            game="CS:GO",
            primary_event="timing",
            secondary_events=["fail"],
            strongest_reaction="talk about timing",
            climax_timestamp=20.0,
            intensity=0.85,
            tone="funny/chaotic",
            has_facecam=True,
            visual_effect_count=4,
            sfx_count=2,
        )
        desc1 = self.desc_engine.generate_description(
            summary=self.summary_timing,
            selected_title="The Most Painful CS:GO Fail Ever 💀",
            hashtags=["#Shorts", "#CSGO"],
        )
        desc2 = self.desc_engine.generate_description(
            summary=summary_timing_2,
            selected_title="The Worst Possible Timing In CS:GO 😂",
            hashtags=["#Shorts", "#CSGO"],
            existing_descriptions=[desc1],
        )
        self.assertNotEqual(desc1, desc2)
        sim = compute_description_similarity(desc1, desc2)
        self.assertLess(sim, 0.50, f"Near duplicate description detected (sim: {sim})")

    def test_description_uses_candidate_specific_hook(self):
        desc_timing = self.desc_engine.generate_description(
            summary=self.summary_timing,
            selected_title="Timing Clip",
            hashtags=["#Shorts"],
        )
        self.assertTrue("timing" in desc_timing.lower() or "fail" in desc_timing.lower())

        desc_flash = self.desc_engine.generate_description(
            summary=self.summary_flash,
            selected_title="Flash Clip",
            hashtags=["#Shorts"],
        )
        self.assertTrue("flash" in desc_flash.lower() or "speechless" in desc_flash.lower() or "lobby" in desc_flash.lower())

    def test_description_attribution_preserved(self):
        desc = self.desc_engine.generate_description(
            summary=self.summary_timing,
            selected_title="Title",
            hashtags=["#Shorts"],
            source_metadata={"uploader": "Nick Bunyun", "title": "CAFM #256"},
            existing_descriptions=["Previous description 1", "Previous description 2"],
        )
        self.assertIn("Original footage: Nick Bunyun ('CAFM #256')", desc)

    def test_description_length_after_dedup(self):
        descs = []
        for _ in range(3):
            d = self.desc_engine.generate_description(
                summary=self.summary_timing,
                selected_title="Title",
                hashtags=["#Shorts", "#CSGO", "#Gaming"],
                source_metadata={"uploader": "Nick", "title": "Moments"},
                existing_descriptions=descs,
            )
            self.assertGreaterEqual(len(d), 40)
            self.assertLessEqual(len(d), 500)
            descs.append(d)

    def test_reaction_only_title_is_refined(self):
        short_title = '"Whoa" 💀'
        self.assertLess(len(short_title), 20)
        refined = self.title_engine.refine_short_title(short_title, self.summary_flash)
        self.assertGreaterEqual(len(refined), 20)
        self.assertTrue("Whoa" in refined or "Reaction" in refined)

    def test_short_title_remains_grounded(self):
        short_title = '"Whoa" 💀'
        refined = self.title_engine.refine_short_title(short_title, self.summary_flash)
        # Must not hallucinate unverified events
        self.assertNotIn("1v5", refined)
        self.assertNotIn("clutch", refined.lower())
        self.assertNotIn("ace", refined.lower())

    def test_short_title_not_expanded_without_context(self):
        empty_summary = ClipSummary(
            candidate_id=99,
            duration=20.0,
            game="Unknown",
            primary_event="gameplay highlight",
            secondary_events=[],
            strongest_reaction="unknown",
            climax_timestamp=0.0,
            intensity=0.5,
            tone="neutral",
            has_facecam=False,
            visual_effect_count=0,
            sfx_count=0,
        )
        raw_short = "Whoa"
        result = self.title_engine.refine_short_title(raw_short, empty_summary)
        # With zero contextual anchors, must return unchanged rather than inventing claims
        self.assertEqual(result, raw_short)


if __name__ == "__main__":
    unittest.main()
