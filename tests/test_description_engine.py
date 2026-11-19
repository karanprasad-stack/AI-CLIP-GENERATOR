import unittest
from backend.app.pipeline.clip_summary_engine import ClipSummary
from backend.app.pipeline.description_engine import DescriptionEngine


class TestDescriptionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DescriptionEngine()
        self.summary = ClipSummary(
            candidate_id=1,
            duration=43.2,
            game="CS:GO",
            primary_event="clutch",
            secondary_events=["shot", "flash"],
            strongest_reaction="talk about timing",
            climax_timestamp=18.9,
            intensity=0.88,
            tone="funny/chaotic",
            has_facecam=True,
            visual_effect_count=7,
            sfx_count=4,
        )

    def test_description_length_and_content(self):
        hashtags = ["#CSGO", "#Gaming", "#GamingShorts", "#Shorts"]
        source_meta = {"uploader": "CAFM", "title": "CSGO Funny Moments"}

        desc = self.engine.generate_description(
            summary=self.summary,
            selected_title="The Craziest CS:GO Clutch 🔥",
            hashtags=hashtags,
            source_metadata=source_meta,
        )

        self.assertGreaterEqual(len(desc), 40)
        self.assertLessEqual(len(desc), 500)
        self.assertIn("CS:GO", desc)
        self.assertIn("#CSGO", desc)
        self.assertIn("CAFM", desc)

    def test_description_without_source_metadata(self):
        desc = self.engine.generate_description(
            summary=self.summary,
            selected_title="Title",
            hashtags=["#Gaming", "#Shorts"],
            source_metadata=None,
        )
        self.assertGreaterEqual(len(desc), 40)
        self.assertIn("#Gaming", desc)


if __name__ == "__main__":
    unittest.main()
