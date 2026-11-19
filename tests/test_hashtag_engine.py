import unittest
from backend.app.pipeline.clip_summary_engine import ClipSummary
from backend.app.pipeline.hashtag_engine import HashtagEngine


class TestHashtagEngine(unittest.TestCase):
    def setUp(self):
        self.engine = HashtagEngine()
        self.summary = ClipSummary(
            candidate_id=1,
            duration=43.2,
            game="CS:GO",
            primary_event="clutch",
            secondary_events=["shot"],
            strongest_reaction="talk about timing",
            climax_timestamp=18.9,
            intensity=0.88,
            tone="funny/chaotic",
            has_facecam=True,
            visual_effect_count=7,
            sfx_count=4,
        )

    def test_hashtag_generation_bounds_and_deduplication(self):
        tags = self.engine.generate_hashtags(self.summary)
        self.assertGreaterEqual(len(tags), 4)
        self.assertLessEqual(len(tags), 8)

        # All tags start with #
        self.assertTrue(all(t.startswith("#") for t in tags))

        # No duplicate tags case-insensitively
        lower_tags = [t.lower() for t in tags]
        self.assertEqual(len(lower_tags), len(set(lower_tags)))

        # Contains relevant tags
        self.assertIn("#csgo", lower_tags)
        self.assertIn("#shorts", lower_tags)

    def test_keyword_generation(self):
        kws = self.engine.generate_keywords(self.summary)
        self.assertGreaterEqual(len(kws), 4)

        lower_kws = [k.lower() for k in kws]
        self.assertIn("cs:go", lower_kws)
        self.assertIn("gaming", lower_kws)


if __name__ == "__main__":
    unittest.main()
