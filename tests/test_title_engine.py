import unittest
from backend.app.pipeline.clip_summary_engine import ClipSummary
from backend.app.pipeline.title_engine import TitleEngine


class TestTitleEngine(unittest.TestCase):
    def setUp(self):
        self.engine = TitleEngine(ollama_enabled=False)
        self.summary = ClipSummary(
            candidate_id=1,
            duration=43.2,
            game="CS:GO",
            primary_event="timing",
            secondary_events=["shot", "flash"],
            strongest_reaction="talk about timing",
            climax_timestamp=18.9,
            intensity=0.88,
            tone="funny/chaotic",
            has_facecam=True,
            visual_effect_count=7,
            sfx_count=4,
        )

    def test_generate_rule_based_titles_diversity(self):
        titles = self.engine.generate_rule_based_titles(self.summary)
        self.assertGreaterEqual(len(titles), 3)
        self.assertLessEqual(len(titles), 5)

        # Check uniqueness
        self.assertEqual(len(titles), len(set(titles)))

        # Verify styles are represented
        titles_combined = " ".join(titles)
        self.assertIn("CS:GO", titles_combined)
        self.assertTrue(any("timing" in t.lower() for t in titles))

    def test_title_validation(self):
        valid, _ = self.engine.validate_title("The Craziest CS:GO Clutch 🔥", self.summary)
        self.assertTrue(valid)

        # Too long
        long_title = "A" * 120
        valid_long, err_long = self.engine.validate_title(long_title, self.summary)
        self.assertFalse(valid_long)

        # Excessive punctuation
        valid_punct, _ = self.engine.validate_title("NO WAY?!?!?!?", self.summary)
        self.assertFalse(valid_punct)

        # Too many hashtags
        valid_hash, _ = self.engine.validate_title("CSGO #gaming #shorts #clutch #win", self.summary)
        self.assertFalse(valid_hash)

    def test_score_and_rank_titles(self):
        res = self.engine.generate_and_rank_titles(self.summary)
        self.assertIn("selected_title", res)
        self.assertIn("selected_score", res)
        self.assertIn("alternatives", res)
        self.assertEqual(res["generation_mode"], "rule_based")
        self.assertGreater(res["selected_score"], 0.4)

    def test_ollama_fallback_safety(self):
        # Enable Ollama with unreachable host - must gracefully fallback to rule_based
        engine_with_llm = TitleEngine(ollama_enabled=True, ollama_host="http://localhost:99999")
        res = engine_with_llm.generate_and_rank_titles(self.summary)
        self.assertIsNotNone(res["selected_title"])
        self.assertEqual(res["generation_mode"], "rule_based")


if __name__ == "__main__":
    unittest.main()
