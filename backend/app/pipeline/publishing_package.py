"""Publishing Package Engine: orchestrates thumbnails, metadata, and publish-ready manifests for YouTube Shorts."""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
import cv2

from backend.app.config import DEFAULT_RIGHTS_NOTE
from backend.app.pipeline.clip_summary_engine import ClipSummary, ClipSummaryEngine
from backend.app.pipeline.thumbnail_engine import ThumbnailEngine
from backend.app.pipeline.title_engine import TitleEngine
from backend.app.pipeline.description_engine import DescriptionEngine
from backend.app.pipeline.hashtag_engine import HashtagEngine


class PublishingPackageManager:
    """Creates complete, verified publishing bundles for each selected Short."""

    def __init__(
        self,
        summary_engine: Optional[ClipSummaryEngine] = None,
        thumbnail_engine: Optional[ThumbnailEngine] = None,
        title_engine: Optional[TitleEngine] = None,
        description_engine: Optional[DescriptionEngine] = None,
        hashtag_engine: Optional[HashtagEngine] = None,
    ):
        self.summary_engine = summary_engine or ClipSummaryEngine()
        self.thumbnail_engine = thumbnail_engine or ThumbnailEngine()
        self.title_engine = title_engine or TitleEngine()
        self.description_engine = description_engine or DescriptionEngine()
        self.hashtag_engine = hashtag_engine or HashtagEngine()

    def validate_package(
        self,
        package_dir: Path,
        manifest_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Validates that all publishing bundle assets, metadata, and video files are complete and valid."""
        errors: List[str] = []
        checks = {
            "final_video_exists": False,
            "thumbnail_exists": False,
            "thumbnail_resolution": False,
            "thumbnail_not_empty": False,
            "title_valid": False,
            "description_valid": False,
            "hashtags_valid": False,
            "keywords_valid": False,
            "metadata_valid": False,
            "manifest_valid": False,
        }

        # 1. Video file check
        video_file = package_dir / "final.mp4"
        if video_file.exists() and video_file.stat().st_size > 1000:
            checks["final_video_exists"] = True
        else:
            errors.append(f"Missing or empty final.mp4 in {package_dir}")

        # 2. Thumbnail check
        thumb_file = package_dir / "thumbnail.jpg"
        if thumb_file.exists() and thumb_file.stat().st_size > 5000:
            checks["thumbnail_exists"] = True
            checks["thumbnail_not_empty"] = True
            try:
                img = cv2.imread(str(thumb_file))
                if img is not None and img.shape[1] == 1280 and img.shape[0] == 720:
                    checks["thumbnail_resolution"] = True
                else:
                    errors.append(f"Invalid thumbnail resolution: {img.shape if img is not None else 'None'}")
            except Exception as e:
                errors.append(f"Failed to inspect thumbnail image: {e}")
        else:
            errors.append(f"Missing or empty thumbnail.jpg in {package_dir}")

        # 3. Text files check
        title_file = package_dir / "title.txt"
        if title_file.exists():
            t = title_file.read_text(encoding="utf-8").strip()
            if 3 <= len(t) <= 100:
                checks["title_valid"] = True
            else:
                errors.append(f"Invalid title length: {len(t)}")
        else:
            errors.append("Missing title.txt")

        desc_file = package_dir / "description.txt"
        if desc_file.exists():
            d = desc_file.read_text(encoding="utf-8").strip()
            if len(d) >= 30:
                checks["description_valid"] = True
            else:
                errors.append(f"Description too short: {len(d)}")
        else:
            errors.append("Missing description.txt")

        hash_file = package_dir / "hashtags.txt"
        if hash_file.exists():
            h_text = hash_file.read_text(encoding="utf-8").strip()
            tags = h_text.split()
            if 3 <= len(tags) <= 15:
                checks["hashtags_valid"] = True
            else:
                errors.append(f"Invalid hashtag count: {len(tags)}")
        else:
            errors.append("Missing hashtags.txt")

        kw_file = package_dir / "keywords.txt"
        if kw_file.exists():
            kw_text = kw_file.read_text(encoding="utf-8").strip()
            kws = [k.strip() for k in kw_text.split(",") if k.strip()]
            if len(kws) >= 3:
                checks["keywords_valid"] = True
            else:
                errors.append(f"Invalid keyword count: {len(kws)}")
        else:
            errors.append("Missing keywords.txt")

        # 4. Candidate metadata.json
        meta_file = package_dir / "metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    m_data = json.load(f)
                if m_data.get("phase") in ["6B", "6B.1"] and "video" in m_data and "title" in m_data:
                    checks["metadata_valid"] = True
                else:
                    errors.append("metadata.json missing required top-level keys")
            except Exception as e:
                errors.append(f"Corrupted metadata.json: {e}")
        else:
            errors.append("Missing metadata.json")

        # 5. Manifest check (if provided)
        if manifest_path:
            if Path(manifest_path).exists():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        man_data = json.load(f)
                    if "packages" in man_data and "source_video_id" in man_data:
                        checks["manifest_valid"] = True
                    else:
                        errors.append("publishing_manifest.json missing required keys")
                except Exception as e:
                    errors.append(f"Corrupted publishing_manifest.json: {e}")
            else:
                errors.append("Missing publishing_manifest.json")
        else:
            checks["manifest_valid"] = True

        is_valid = (len(errors) == 0 and all(checks.values()))
        return {
            "status": "PASS" if is_valid else "FAIL",
            "valid": is_valid,
            "package_path": str(package_dir),
            "checks": checks,
            "errors": errors,
        }

    def build_candidate_package(
        self,
        candidate_idx: int,
        candidate: Dict[str, Any],
        publishing_dir: Path,
        source_video_path: Optional[Path] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
        transcript_data: Optional[Dict[str, Any]] = None,
        phase5_timeline: Optional[Dict[str, Any]] = None,
        phase6a_timeline: Optional[Dict[str, Any]] = None,
        existing_titles: Optional[List[str]] = None,
        existing_descriptions: Optional[List[str]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Creates the full publishing bundle for a single candidate Short."""
        def log_step(msg: str):
            print(f"[Phase 6B] {msg}", flush=True)
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass

        log_step(f"Candidate {candidate_idx} packaging START")

        cand_dir = publishing_dir / f"candidate_{candidate_idx:02d}"
        cand_dir.mkdir(parents=True, exist_ok=True)

        # 1. Video Asset Copy / Reference
        # Prefer Phase 6A polished audio short, fallback to Phase 5 or Phase 4
        source_final_mp4 = Path(
            candidate.get("audio_polished_clip",
            candidate.get("final_clip",
            candidate.get("captioned_clip",
            candidate.get("short_clip", ""))))
        )

        target_mp4 = cand_dir / "final.mp4"
        if source_final_mp4.exists():
            # Copy final video into package directory without re-encoding
            if not target_mp4.exists() or target_mp4.stat().st_size != source_final_mp4.stat().st_size:
                shutil.copyfile(source_final_mp4, target_mp4)
        else:
            raise FileNotFoundError(f"Source video for candidate {candidate_idx} not found: {source_final_mp4}")

        # 2. Structured Clip Summary
        summary = self.summary_engine.summarize_candidate(
            candidate=candidate,
            video_metadata=source_metadata,
            transcript_data=transcript_data,
            phase5_timeline=phase5_timeline,
            phase6a_timeline=phase6a_timeline,
        )

        # 3. High-Quality Thumbnail Generation
        log_step(f"Candidate {candidate_idx} thumbnail START")
        thumb_file = cand_dir / "thumbnail.jpg"
        thumb_res = self.thumbnail_engine.extract_thumbnail(
            video_path=target_mp4,
            summary=summary,
            candidate=candidate,
            output_image_path=thumb_file,
            source_video_path=source_video_path,
        )
        log_step(f"Candidate {candidate_idx} thumbnail COMPLETE")

        # 4. Title Generation & Ranking (with cross-candidate deduplication)
        log_step(f"Candidate {candidate_idx} title START")
        title_res = self.title_engine.generate_and_rank_titles(summary, existing_titles=existing_titles)
        selected_title = title_res["selected_title"]
        log_step(f"Candidate {candidate_idx} title COMPLETE")

        # Pre-compute hashtags & keywords for description generator
        hashtags = self.hashtag_engine.generate_hashtags(summary)
        keywords = self.hashtag_engine.generate_keywords(summary)

        # 5. Description Generation (with cross-candidate deduplication)
        log_step(f"Candidate {candidate_idx} description START")
        description = self.description_engine.generate_description(
            summary=summary,
            selected_title=selected_title,
            hashtags=hashtags,
            source_metadata=source_metadata,
            existing_descriptions=existing_descriptions,
        )
        log_step(f"Candidate {candidate_idx} description COMPLETE")

        # 6. Hashtags & Keywords confirmation
        log_step(f"Candidate {candidate_idx} hashtags START")
        hashtags = self.hashtag_engine.generate_hashtags(summary)
        keywords = self.hashtag_engine.generate_keywords(summary)
        log_step(f"Candidate {candidate_idx} hashtags COMPLETE")

        # 7. Metadata Quality Evaluation
        quality_score = self.title_engine.compute_metadata_quality(
            title=selected_title,
            summary=summary,
            description=description,
            hashtags=hashtags,
            existing_titles=existing_titles,
            existing_descriptions=existing_descriptions,
        )

        # 8. Write Plaintext Metadata Files
        log_step(f"Candidate {candidate_idx} metadata WRITE START")
        (cand_dir / "title.txt").write_text(selected_title, encoding="utf-8")
        (cand_dir / "description.txt").write_text(description, encoding="utf-8")
        (cand_dir / "hashtags.txt").write_text(" ".join(hashtags), encoding="utf-8")
        (cand_dir / "keywords.txt").write_text(", ".join(keywords), encoding="utf-8")

        # 9. Build Candidate metadata.json
        candidate_meta = {
            "phase": "6B",
            "refinement_phase": "6B.1.1",
            "candidate_id": candidate_idx,
            "video": {
                "path": str(target_mp4.name),
                "duration": round(summary.duration, 2),
                "format": "mp4",
                "aspect_ratio": "9:16",
                "resolution": "1080x1920",
            },
            "thumbnail": {
                "path": str(thumb_file.name),
                "timestamp": thumb_res["frame_timestamp"],
                "resolution": thumb_res["resolution"],
                "score": thumb_res["score"],
                "text_used": thumb_res["text_used"],
                "text": thumb_res["text"],
            },
            "title": {
                "selected": selected_title,
                "score": title_res["selected_score"],
                "alternatives": title_res["alternatives"],
                "generation_mode": title_res["generation_mode"],
                "model": title_res["model"],
            },
            "description": description,
            "hashtags": hashtags,
            "keywords": keywords,
            "metadata_quality": quality_score,
            "summary": summary.to_dict(),
            "publishing_settings": {
                "category": "20",
                "category_name": "Gaming",
                "privacy_status": "private",
                "made_for_kids": False,
                "language": "en",
            },
            "rights_note": DEFAULT_RIGHTS_NOTE,
            "source_attribution": {
                "uploader": source_metadata.get("uploader", "") if source_metadata else "",
                "title": source_metadata.get("title", "") if source_metadata else "",
                "video_id": (source_metadata.get("id") or source_metadata.get("video_id", "")) if source_metadata else "",
            },
        }

        meta_path = cand_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(candidate_meta, f, indent=2, ensure_ascii=False)

        # 10. Validate bundle
        val_res = self.validate_package(cand_dir)

        # 11. Phase 7E Creator Quality Evaluation
        from backend.app.pipeline.creator_quality import CreatorQualityEvaluator
        creator_evaluator = CreatorQualityEvaluator()
        prelim_pkg = {
            "thumbnail_score": thumb_res["score"],
            "thumbnail_path": str(thumb_file),
            "title": selected_title,
            "description": description,
            "hashtags": hashtags,
            "validation": val_res,
            "metadata": candidate_meta,
        }
        transcript_words = transcript_data.get("words", []) if transcript_data else None
        publishability = creator_evaluator.evaluate(
            candidate=candidate,
            package_info=prelim_pkg,
            transcript_words=transcript_words,
            effects_info=phase5_timeline,
            audio_info=phase6a_timeline,
        )
        candidate_meta["publishability"] = publishability
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(candidate_meta, f, indent=2, ensure_ascii=False)
        log_step(f"Candidate {candidate_idx} metadata WRITE COMPLETE")

        # 12. Phase 8 Timeline / EDL Synthesis
        from backend.app.pipeline.timeline import TimelineEdlGenerator, TimelineStore
        edl_gen = TimelineEdlGenerator()
        tl_store = TimelineStore()
        timeline_edl = edl_gen.generate_edl(
            project_id=source_metadata.get("id", source_metadata.get("video_id", "project")) if source_metadata else "project",
            candidate_id=candidate_idx,
            candidate=candidate,
            transcript_data=transcript_data,
            phase5_timeline=phase5_timeline,
            phase6a_timeline=phase6a_timeline,
            source_video_path=str(source_video_path) if source_video_path else "source.mp4",
        )
        tl_store.save_timeline(publishing_dir.parent, timeline_edl, increment_version=False)

        log_step(f"Candidate {candidate_idx} packaging COMPLETE")

        return {
            "candidate_id": candidate_idx,
            "package_dir": str(cand_dir),
            "video_path": str(target_mp4),
            "thumbnail_path": str(thumb_file),
            "title": selected_title,
            "description": description,
            "hashtags": hashtags,
            "keywords": keywords,
            "thumbnail_score": thumb_res["score"],
            "thumbnail_timestamp": thumb_res["frame_timestamp"],
            "title_score": title_res["selected_score"],
            "metadata_quality": quality_score,
            "publishability": publishability,
            "validation": val_res,
            "metadata": candidate_meta,
        }

    def generate_publishing_manifest(
        self,
        publishing_dir: Path,
        packages: List[Dict[str, Any]],
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Writes the top-level publishing manifest for the entire video run."""
        manifest_path = publishing_dir / "publishing_manifest.json"

        manifest_data = {
            "phase": "6B",
            "refinement_phase": "6B.1.1",
            "source_video_id": (source_metadata.get("id") or source_metadata.get("video_id", "")) if source_metadata else "",
            "source_title": source_metadata.get("title", "") if source_metadata else "",
            "uploader": source_metadata.get("uploader", "") if source_metadata else "",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rights_note": DEFAULT_RIGHTS_NOTE,
            "total_packages": len(packages),
            "packages_passed": sum(1 for p in packages if p["validation"]["status"] == "PASS"),
            "packages": [
                {
                    "candidate_id": p["candidate_id"],
                    "package_dir": p["package_dir"],
                    "title": p["title"],
                    "thumbnail": p["thumbnail_path"],
                    "thumbnail_score": p["thumbnail_score"],
                    "thumbnail_timestamp": p["thumbnail_timestamp"],
                    "quality_score": p.get("metadata_quality", {}).get("overall", 0.9),
                    "status": p["validation"]["status"],
                    "publishability": p.get("publishability"),
                }
                for p in packages
            ],
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)

        return manifest_path
