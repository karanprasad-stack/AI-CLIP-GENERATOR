import os
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from backend.app.pipeline.long_stream.chunk_store import ChunkStore
from backend.app.pipeline.caption_engine import CaptionEngine
from backend.app.pipeline.subtitles.normalizer import HinglishNormalizer
from backend.app.pipeline.subtitle_validator import SubtitleValidator
from backend.app.pipeline.publishing_package import PublishingPackageManager
from backend.app.services.project_manager import ProjectManager


class TestSubtitlesAndDescriptionRegression(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_chunk_store_merged_transcript(self):
        store = ChunkStore(self.test_path)
        chunks_dir = store.chunks_dir

        # Chunk 1: words at 10.0 and 11.0
        chunk1 = {
            "chunk_id": 1,
            "status": "completed",
            "source_start": 0.0,
            "transcript": {
                "language": "en",
                "segments": [
                    {
                        "start": 10.0,
                        "end": 12.0,
                        "text": "Nice shot",
                        "words": [
                            {"word": "Nice", "start": 10.0, "end": 10.8, "probability": 0.95},
                            {"word": "shot", "start": 10.9, "end": 11.8, "probability": 0.92},
                        ],
                    }
                ],
                "words": [
                    {"word": "Nice", "start": 10.0, "end": 10.8, "probability": 0.95},
                    {"word": "shot", "start": 10.9, "end": 11.8, "probability": 0.92},
                ],
            },
        }
        with open(chunks_dir / "chunk_0001.json", "w", encoding="utf-8") as f:
            json.dump(chunk1, f)

        # Chunk 2: overlap duplicate "shot" at 10.9 + new word "clutch" at 15.0
        chunk2 = {
            "chunk_id": 2,
            "status": "completed",
            "source_start": 15.0,
            "transcript": {
                "language": "en",
                "segments": [
                    {
                        "start": 15.0,
                        "end": 16.5,
                        "text": "Clutch play",
                        "words": [
                            {"word": "Clutch", "start": 15.0, "end": 15.8, "probability": 0.98},
                            {"word": "play", "start": 15.9, "end": 16.5, "probability": 0.94},
                        ],
                    }
                ],
                "words": [
                    {"word": "shot", "start": 10.9, "end": 11.8, "probability": 0.92},  # overlap dupe
                    {"word": "Clutch", "start": 15.0, "end": 15.8, "probability": 0.98},
                    {"word": "play", "start": 15.9, "end": 16.5, "probability": 0.94},
                ],
            },
        }
        with open(chunks_dir / "chunk_0002.json", "w", encoding="utf-8") as f:
            json.dump(chunk2, f)

        merged = store.get_merged_transcript("en")
        self.assertEqual(len(merged["segments"]), 2)
        # Deduplication should yield exactly 4 words (Nice, shot, Clutch, play)
        words = merged["words"]
        self.assertEqual(len(words), 4)
        self.assertEqual(words[0]["word"], "Nice")
        self.assertEqual(words[1]["word"], "shot")
        self.assertEqual(words[2]["word"], "Clutch")
        self.assertEqual(words[3]["word"], "play")

    def test_caption_engine_extract_words_nested_and_top_level(self):
        engine = CaptionEngine()

        # 1. Nested words inside segments
        nested_data = {
            "segments": [
                {
                    "start": 5.0,
                    "end": 8.0,
                    "words": [
                        {"word": "Headshot", "start": 5.2, "end": 6.0},
                        {"word": "Ace", "start": 6.2, "end": 7.0},
                    ],
                }
            ]
        }
        extracted1 = engine.extract_words(nested_data, 5.0, 7.5)
        self.assertEqual(len(extracted1), 2)
        self.assertEqual(extracted1[0].text, "Headshot")

        # 2. Top-level words fallback when segments is empty
        top_level_data = {
            "segments": [],
            "words": [
                {"word": "Planting", "start": 10.0, "end": 11.0},
                {"word": "Spike", "start": 11.2, "end": 12.0},
            ],
        }
        extracted2 = engine.extract_words(top_level_data, 9.5, 12.5)
        self.assertEqual(len(extracted2), 2)
        self.assertEqual(extracted2[1].text, "Spike")

    def test_hinglish_normalizer_synthetic_segment_fallback(self):
        normalizer = HinglishNormalizer()

        # Transcript with empty segments but non-empty words
        raw_data = {
            "language": "hi",
            "segments": [],
            "words": [
                {"word": "bhai", "start": 1.0, "end": 1.5},
                {"word": "kya", "start": 1.6, "end": 2.0},
                {"word": "shot", "start": 2.1, "end": 2.8},
            ],
        }

        normalized = normalizer.normalize_transcript(raw_data)
        self.assertTrue(len(normalized.get("words", [])) >= 3)
        self.assertTrue(len(normalized.get("segments", [])) >= 1)

    def test_subtitle_validator_allow_empty_dialogue(self):
        validator = SubtitleValidator()

        # Minimal valid ASS with 0 dialogue lines
        empty_ass = (
            "[Script Info]\n"
            "Title: Test\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1080\n"
            "PlayResY: 1920\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,250,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        ass_path = self.test_path / "test.ass"
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(empty_ass)

        # Without allow_empty_dialogue -> fails
        val_fail = validator.validate_ass(ass_path, allow_empty_dialogue=False)
        self.assertFalse(val_fail["valid"])

        # With allow_empty_dialogue -> succeeds
        val_pass = validator.validate_ass(ass_path, allow_empty_dialogue=True)
        self.assertTrue(val_pass["valid"])

    def test_publishing_manifest_serialization_includes_description_and_tags(self):
        pkg_manager = PublishingPackageManager()

        packages = [
            {
                "candidate_id": 1,
                "package_dir": str(self.test_path / "candidate_01"),
                "title": "INSANE ACE!",
                "description": "Watch this 1v5 clutch in Valorant! Like and subscribe for more.",
                "hashtags": ["#Valorant", "#Ace", "#Gaming"],
                "keywords": ["valorant", "ace", "clutch"],
                "video_path": str(self.test_path / "short.mp4"),
                "thumbnail_path": str(self.test_path / "thumb.jpg"),
                "thumbnail_score": 92.5,
                "metadata": {"title": {"selected": "INSANE ACE!"}},
                "validation": {"status": "PASS"},
            }
        ]

        manifest_path = pkg_manager.generate_publishing_manifest(self.test_path, packages)
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual(manifest["total_packages"], 1)
        pkg_entry = manifest["packages"][0]
        self.assertEqual(pkg_entry["candidate_id"], 1)
        self.assertEqual(pkg_entry["description"], "Watch this 1v5 clutch in Valorant! Like and subscribe for more.")
        self.assertEqual(pkg_entry["hashtags"], ["#Valorant", "#Ace", "#Gaming"])
        self.assertEqual(pkg_entry["keywords"], ["valorant", "ace", "clutch"])

    def test_project_manager_decorate_backfills_description_and_tags(self):
        pm = ProjectManager(self.test_path)
        project_id = "test_proj"
        proj_dir = self.test_path / project_id
        pub_dir = proj_dir / "publishing"
        cand1_dir = pub_dir / "candidate_01"
        cand1_dir.mkdir(parents=True, exist_ok=True)

        # 1. Create candidate_01/metadata.json with rich description
        metadata = {
            "title": {"selected": "Clove Ranked MVP"},
            "description": "35+ ELIMS with Clove in Valorant competitive queue!",
            "hashtags": ["#Valorant", "#Clove", "#Ranked"],
            "keywords": ["valorant", "clove", "ranked"],
        }
        with open(cand1_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f)

        # 2. Create publishing_manifest.json that omitted description & hashtags
        manifest_data = {
            "project_id": project_id,
            "total_packages": 1,
            "packages": [
                {
                    "candidate_id": 1,
                    "title": "Clove Ranked MVP",
                    "thumbnail": "publishing/candidate_01/thumbnail.jpg",
                    "status": "ready",
                }
            ],
        }
        with open(pub_dir / "publishing_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest_data, f)

        # 3. Bare project dict
        proj = {
            "id": project_id,
            "title": "Test Project",
            "published_packages": [
                {
                    "candidate_id": 1,
                    "title": "Clove Ranked MVP",
                    "description": "",  # empty initially
                }
            ],
        }

        # 4. Decorate project
        pm._decorate_project(proj)
        self.assertEqual(len(proj["published_packages"]), 1)
        pkg = proj["published_packages"][0]
        self.assertEqual(pkg["description"], "35+ ELIMS with Clove in Valorant competitive queue!")
        self.assertEqual(pkg["hashtags"], ["#Valorant", "#Clove", "#Ranked"])


if __name__ == "__main__":
    unittest.main()
