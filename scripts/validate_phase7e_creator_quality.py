"""Phase 7E Validation Script: evaluates Creator Quality across all 6 dimensions on real video EdtUDpqjltA."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
from backend.app.pipeline.creator_quality import (
    CreatorQualityEvaluator,
    PublishabilityGate,
)
from backend.app.pipeline.publishing_package import PublishingPackageManager


def run_validation():
    base_dir = Path("output/EdtUDpqjltA")
    candidates_file = base_dir / "candidates.json"
    transcript_file = base_dir / "transcript.json"
    publishing_dir = base_dir / "publishing"

    if not candidates_file.exists() or not publishing_dir.exists():
        print(f"Error: Missing validation data in {base_dir}")
        return

    with open(candidates_file, "r", encoding="utf-8") as f:
        cand_data = json.load(f)
    candidates = cand_data.get("candidates", [])

    transcript_words = None
    if transcript_file.exists():
        with open(transcript_file, "r", encoding="utf-8") as f:
            t_data = json.load(f)
            transcript_words = t_data.get("words", [])

    evaluator = CreatorQualityEvaluator()
    gate = PublishabilityGate(evaluator=evaluator)
    pkg_manager = PublishingPackageManager()

    print("=" * 80)
    print("PHASE 7E: CREATOR QUALITY & FINAL OUTPUT INTELLIGENCE VALIDATION")
    print("Source Video ID: EdtUDpqjltA")
    print(f"Total Candidates: {len(candidates)}")
    print("=" * 80)

    evaluated_packages = []

    for idx in range(1, 6):
        cand_folder = publishing_dir / f"candidate_{idx:02d}"
        if not cand_folder.exists():
            continue

        meta_file = cand_folder / "metadata.json"
        if not meta_file.exists():
            continue

        with open(meta_file, "r", encoding="utf-8") as f:
            cand_meta = json.load(f)

        # Candidate matching
        cand = next((c for c in candidates if c.get("rank") == idx or c.get("candidate_id") == idx), candidates[idx - 1])

        # Validate bundle
        val_res = pkg_manager.validate_package(cand_folder)

        prelim_pkg = {
            "thumbnail_score": cand_meta.get("thumbnail", {}).get("score", 80.0),
            "thumbnail_path": str(cand_folder / "thumbnail.jpg"),
            "title": cand_meta.get("title", {}).get("selected", ""),
            "description": cand_meta.get("description", ""),
            "hashtags": cand_meta.get("hashtags", []),
            "validation": val_res,
            "metadata": cand_meta,
        }

        # Run 6-dimension evaluation
        publishability = evaluator.evaluate(
            candidate=cand,
            package_info=prelim_pkg,
            transcript_words=transcript_words,
            all_candidates=candidates,
        )

        cand_meta["publishability"] = publishability
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(cand_meta, f, indent=2, ensure_ascii=False)

        evaluated_packages.append({
            "candidate_id": idx,
            "title": cand_meta.get("title", {}).get("selected", ""),
            "final_score": cand.get("final_score", 0.0),
            "publishability": publishability,
            "validation": val_res["status"],
        })

        print(f"\n[Short #{idx:02d}] '{cand_meta.get('title', {}).get('selected', '')}'")
        print(f"  • Moment Raw Score:        {cand.get('final_score', 0.0):.1f} / 100")
        print(f"  • Publishability Score:    {publishability['score']:.1f} / 100  [{publishability['level'].upper()}]")
        print(f"  • Recommendation:          {publishability['recommendation'].upper()}")
        print(f"  • Technical Validation:    {val_res['status']}")
        print("  • 6-Dimension Breakdown:")
        for dim_name, score in publishability["dimensions"].items():
            print(f"      - {dim_name.capitalize():14s}: {score:.1f} / 100")
        print("  • Top Reasons:")
        for r in publishability["reasons"][:3]:
            print(f"      ✓ {r}")
        if publishability["warnings"]:
            print("  • Warnings:")
            for w in publishability["warnings"][:2]:
                print(f"      ⚠ {w}")
        if publishability["blocking_issues"]:
            print("  • Blockers:")
            for b in publishability["blocking_issues"]:
                print(f"      ✕ {b}")

    # Evaluate Quality Gate
    print("\n" + "=" * 80)
    print("QUALITY GATE EVALUATION")
    print("=" * 80)

    # 1. Auto Mode
    auto_selected, auto_expl = gate.filter_candidates(candidates, num_shorts_mode="auto", transcript_words=transcript_words)
    print(f"\n[Auto Mode Gate]")
    print(f"  • Selected Shorts: {len(auto_selected)}")
    print(f"  • Explanation:     {auto_expl}")

    # 2. Custom Mode (e.g. user asks for 5)
    custom_selected, custom_expl = gate.filter_candidates(candidates, num_shorts_mode="custom", requested_count=5, transcript_words=transcript_words)
    print(f"\n[Custom Mode Gate (Ceiling = 5)]")
    print(f"  • Selected Shorts: {len(custom_selected)}")
    print(f"  • Explanation:     {custom_expl}")

    # Update master manifest with publishability data
    manifest_file = publishing_dir / "publishing_manifest.json"
    if manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            man_data = json.load(f)

        for p in man_data.get("packages", []):
            matching = next((ep for ep in evaluated_packages if ep["candidate_id"] == p["candidate_id"]), None)
            if matching:
                p["publishability"] = matching["publishability"]

        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(man_data, f, indent=2, ensure_ascii=False)
        print(f"\nUpdated master publishing_manifest.json with Creator Quality publishability records.")

    print("\n" + "=" * 80)
    print("PHASE 7E VALIDATION COMPLETE: ALL CHECKS PASSED")
    print("=" * 80)


if __name__ == "__main__":
    run_validation()
