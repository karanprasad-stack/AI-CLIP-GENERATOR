"""Phase 9 Validation Script: Dual Source + Live Stream Rolling Capture & Timeline Integration.
Executes end-to-end controlled live stream simulation using real recorded YouTube media (EdtUDpqjltA).
"""

import os
import sys
import time
import json
import shutil
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import SOURCE_TYPE_LIVE
from backend.app.services.project_manager import ProjectManager
from backend.app.pipeline.live.models import LiveSessionStatus, LiveCandidateStatus
from backend.app.pipeline.live.live_store import LiveStore
from backend.app.pipeline.live.capture_engine import LiveCaptureEngine
from backend.app.pipeline.live.candidate_engine import LiveCandidateEngine
from backend.app.pipeline.live.source_resolver import LiveSourceResolver


def print_step(step_num: int, title: str):
    print(f"\n{'-'*60}")
    print(f"STEP {step_num}: {title.upper()}")
    print(f"{'-'*60}")


def main():
    print("=" * 80)
    print("PHASE 9: DUAL SOURCE + LIVE STREAM CLIPPING VALIDATION")
    print("MODE: CONTROLLED LIVE STREAM SIMULATION (Recorded YouTube Stream Media)")
    print("=" * 80)

    # Validate source media availability
    source_media = PROJECT_ROOT / "output" / "EdtUDpqjltA" / "source.mp4"
    if not source_media.exists() or source_media.stat().st_size == 0:
        print(f"ERROR: Source media not found at {source_media}")
        sys.exit(1)

    print(f"Verified base stream media: {source_media} ({source_media.stat().st_size / (1024*1024):.1f} MB)")

    output_base = PROJECT_ROOT / "output"
    pm = ProjectManager(base_output_dir=output_base)
    # Ensure fresh test directory for live simulation
    for existing_pid in ["live_sim_te", "live_sim_test"]:
        pm.delete_project(existing_pid)
        p_dir = output_base / existing_pid
        if p_dir.exists():
            shutil.rmtree(p_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # STEP 1: DUAL SOURCE PROJECT CREATION
    # -------------------------------------------------------------------------
    print_step(1, "Dual Source Project Creation (Live Stream Mode)")
    proj = pm.create_project(
        url="https://www.youtube.com/watch?v=live_sim_test",
        title="CS:GO Major Tournament Live Stream (Simulated)",
        source_type=SOURCE_TYPE_LIVE,
    )
    live_project_id = proj["id"]
    proj_dir = output_base / live_project_id
    live_store = LiveStore(proj_dir)

    assert proj["source_type"] == SOURCE_TYPE_LIVE, "Project must have source_type = live_stream"
    assert proj["status"] == "idle", "Live project must initialize in idle status"
    assert proj.get("live_session_info") is not None, "Live session info must be present"
    print(f"  ✓ Project created: id={live_project_id}, source_type={proj['source_type']}, status={proj['status']}")

    # -------------------------------------------------------------------------
    # STEP 2: ROLLING LIVE CAPTURE & SEGMENTATION
    # -------------------------------------------------------------------------
    print_step(2, "Rolling Live Capture & Segmentation (45s window, 15s overlap)")
    # Using 45s segment with 15s overlap (step size 30s)
    capture_engine = LiveCaptureEngine(
        live_dir=live_store.live_dir,
        segment_duration=45.0,
        segment_overlap=15.0,
    )

    t0 = time.perf_counter()
    # Capture Segment #1: 0s -> 45s
    seg1 = capture_engine.capture_segment_simulated(
        source_video=source_media,
        segment_id=1,
    )
    assert seg1 is not None, "Segment 1 must be captured"
    assert seg1.global_start == 0.0 and seg1.global_end == 45.0
    assert Path(seg1.video_file).exists() and Path(seg1.audio_file).exists()
    print(f"  ✓ Segment #1 captured: [{seg1.global_start:.1f}s → {seg1.global_end:.1f}s] ({seg1.duration:.1f}s, {seg1.file_size_bytes / (1024*1024):.2f} MB)")

    # Capture Segment #2: 30s -> 75s (overlapping 30s..45s)
    seg2 = capture_engine.capture_segment_simulated(
        source_video=source_media,
        segment_id=2,
    )
    assert seg2 is not None, "Segment 2 must be captured"
    assert seg2.global_start == 30.0 and seg2.global_end == 75.0
    assert Path(seg2.video_file).exists() and Path(seg2.audio_file).exists()
    print(f"  ✓ Segment #2 captured: [{seg2.global_start:.1f}s → {seg2.global_end:.1f}s] ({seg2.duration:.1f}s, {seg2.file_size_bytes / (1024*1024):.2f} MB)")
    print(f"  ✓ Rolling capture elapsed: {(time.perf_counter() - t0):.2f}s")

    live_store.save_manifest([seg1, seg2])

    # -------------------------------------------------------------------------
    # STEP 3: SEGMENT PROCESSING & GLOBAL CANDIDATE DETECTION
    # -------------------------------------------------------------------------
    print_step(3, "Segment Processing & Global Candidate Detection")
    candidate_engine = LiveCandidateEngine()

    cands_seg1, t_data1 = candidate_engine.analyze_segment(seg1)
    seg1.transcript_file = str(live_store.save_segment_transcript(seg1.segment_id, t_data1))
    print(f"  ✓ Segment #1 analyzed: {len(cands_seg1)} moments discovered")
    for c in cands_seg1[:2]:
        print(f"      • Moment [{c['start']:.1f}s → {c['end']:.1f}s] ({c['duration']:.1f}s) Score: {c['final_score']:.1f} Event: {c.get('gameplay_event')}")

    pool, logs1 = candidate_engine.merge_and_update_candidates(
        existing_pool=[],
        new_candidates=cands_seg1,
        segment=seg1,
    )
    live_store.save_candidates(pool)

    # -------------------------------------------------------------------------
    # STEP 4: CROSS-SEGMENT MERGING & DEDUPLICATION
    # -------------------------------------------------------------------------
    print_step(4, "Cross-Segment Boundary Merging & Deduplication")
    cands_seg2, t_data2 = candidate_engine.analyze_segment(seg2)
    seg2.transcript_file = str(live_store.save_segment_transcript(seg2.segment_id, t_data2))
    live_store.save_manifest([seg1, seg2])
    print(f"  ✓ Segment #2 analyzed: {len(cands_seg2)} moments discovered")

    pool_size_before = len(pool)
    pool, logs2 = candidate_engine.merge_and_update_candidates(
        existing_pool=pool,
        new_candidates=cands_seg2,
        segment=seg2,
    )
    live_store.save_candidates(pool)

    print(f"  ✓ Candidate pool size: {pool_size_before} → {len(pool)} candidates")
    for log_msg in logs2:
        print(f"      • {log_msg}")

    # Verify at least one candidate exists
    assert len(pool) > 0, "Candidate pool must contain detected moments"
    candidate_target = pool[0]
    print(f"\n  • Selected Lead Candidate: #{candidate_target.candidate_id}")
    print(f"      Global Window: [{candidate_target.global_start:.1f}s → {candidate_target.global_end:.1f}s] ({candidate_target.duration:.1f}s)")
    print(f"      Source Segments: {candidate_target.source_segments}")
    print(f"      Score: {candidate_target.score:.1f}")
    print(f"      Status: {candidate_target.status}")

    # -------------------------------------------------------------------------
    # STEP 5: CREATOR QUALITY GATING
    # -------------------------------------------------------------------------
    print_step(5, "Creator Quality Gating & Publishability Audit")
    pub = candidate_target.publishability
    assert pub is not None, "Candidate must undergo Creator Quality evaluation"
    print(f"  ✓ Quality Score:    {pub.get('score', candidate_target.score):.1f}/100 [{pub.get('level', 'strong').upper()}]")
    print(f"  ✓ Recommendation:   {pub.get('recommendation', 'review').upper()}")
    for reason in pub.get("reasons", [])[:3]:
        print(f"      • {reason}")

    # -------------------------------------------------------------------------
    # STEP 6: SOURCE MEDIA RESOLUTION (No full stream flattening)
    # -------------------------------------------------------------------------
    print_step(6, "Source Media Resolution (Extract continuous candidate clip)")
    resolver = LiveSourceResolver()
    cand_clip_dir = proj_dir / "publishing" / f"candidate_{candidate_target.candidate_id:02d}"
    cand_clip_dir.mkdir(parents=True, exist_ok=True)
    cand_clip_path = cand_clip_dir / "source.mp4"

    resolved_path = resolver.resolve_source_clip(
        global_start=candidate_target.global_start,
        global_end=candidate_target.global_end,
        segments=[seg1, seg2],
        output_clip_path=cand_clip_path,
    )
    assert resolved_path.exists() and resolved_path.stat().st_size > 0
    print(f"  ✓ Source media resolved cleanly without full stream merge:")
    print(f"      Path: {resolved_path} ({resolved_path.stat().st_size / (1024*1024):.2f} MB)")

    # Sync project candidate in ProjectManager
    pm._projects[live_project_id]["candidates"] = [c.to_candidate_dict() for c in pool]
    pm._projects[live_project_id]["selected_candidate_ids"] = [candidate_target.candidate_id]
    pm._save_projects()

    # -------------------------------------------------------------------------
    # STEP 7: PHASE 8 TIMELINE / EDL GENERATION & HUMAN EDITING
    # -------------------------------------------------------------------------
    print_step(7, "Phase 8 Timeline / EDL Generation & Human Editing")
    timeline_dict = pm.get_timeline(live_project_id, candidate_target.candidate_id)
    assert timeline_dict is not None
    assert timeline_dict["candidate_id"] == candidate_target.candidate_id
    assert timeline_dict["version"] >= 1

    sub_count = len(timeline_dict.get("subtitles_track", []))
    eff_count = len(timeline_dict.get("effects_track", []))
    sfx_count = len(timeline_dict.get("sfx_track", []))
    duck_count = len(timeline_dict.get("ducking_track", []))

    print(f"  ✓ Timeline EDL loaded for live candidate #{candidate_target.candidate_id} (Version: v{timeline_dict['version']})")
    print(f"      Initial Tracks: {sub_count} subtitles, {eff_count} effects, {sfx_count} sfx, {duck_count} ducking intervals")

    # Assert all applicable AI tracks are populated
    assert sub_count >= 1, "Live candidate must contain AI-generated subtitle items"
    assert eff_count >= 1, "Live candidate must contain AI-generated effect items"
    assert sfx_count >= 1, "Live candidate must contain AI-generated SFX items"
    assert duck_count >= 1, "Live candidate must contain AI-generated ducking intervals"

    # Human Modification 1: Subtitle text modification
    old_sub_text = timeline_dict["subtitles_track"][0]["text"]
    new_sub_text = "THAT TIMING WAS INSANE! 🔥"
    timeline_dict["subtitles_track"][0]["text"] = new_sub_text
    print(f"  ✓ Human edit applied to subtitle #1: '{old_sub_text}' → '{new_sub_text}'")

    # Human Modification 2: Disable one AI effect
    timeline_dict["effects_track"][0]["enabled"] = False
    print(f"  ✓ Human disabled AI effect: {timeline_dict['effects_track'][0]['id']} ({timeline_dict['effects_track'][0]['type']})")

    # Human Modification 3: Shift one SFX timing
    old_sfx_t = timeline_dict["sfx_track"][0]["timestamp"]
    timeline_dict["sfx_track"][0]["timestamp"] = round(old_sfx_t + 0.35, 2)
    print(f"  ✓ Human adjusted SFX #1 timestamp: {old_sfx_t:.2f}s → {timeline_dict['sfx_track'][0]['timestamp']:.2f}s")

    saved_tl = pm.save_timeline(live_project_id, candidate_target.candidate_id, timeline_dict)
    assert saved_tl["version"] > timeline_dict["version"]
    assert "subtitles" in saved_tl["metadata"]["dirty_tracks"]
    assert "effects" in saved_tl["metadata"]["dirty_tracks"]
    assert "sfx" in saved_tl["metadata"]["dirty_tracks"]

    # Verify track preservation across all tracks
    assert len(saved_tl["subtitles_track"]) == sub_count, "Subtitle count must be preserved"
    assert len(saved_tl["effects_track"]) == eff_count, "Effect count must be preserved"
    assert len(saved_tl["sfx_track"]) == sfx_count, "SFX count must be preserved"
    assert len(saved_tl["ducking_track"]) == duck_count, "Ducking count must be preserved"

    print(f"  ✓ Saved edited timeline: v{saved_tl['version']}. Dirty tracks detected: {saved_tl['metadata']['dirty_tracks']}")
    print(f"  ✓ Track preservation verified: all {sub_count} subtitles, {eff_count} effects, {sfx_count} sfx, and {duck_count} ducking items intact.")

    # -------------------------------------------------------------------------
    # STEP 8: RE-RENDER & CREATOR QUALITY RE-EVALUATION
    # -------------------------------------------------------------------------
    print_step(8, "Selective Re-Render & Creator Quality Re-Evaluation")
    t_render = time.perf_counter()
    render_result = pm.render_timeline(live_project_id, candidate_target.candidate_id)
    render_dur = time.perf_counter() - t_render

    final_mp4 = cand_clip_dir / "final.mp4"
    assert final_mp4.exists() and final_mp4.stat().st_size > 0
    print(f"  ✓ Render completed in {render_dur:.2f}s!")
    print(f"  ✓ Final Vertical 9:16 Video: {final_mp4} ({final_mp4.stat().st_size / (1024*1024):.2f} MB)")

    pub_final = render_result["publishability"]
    dims = pub_final.get("dimensions", {})

    print("\n  Creator Quality Dimension Audit:")
    print("  " + "-" * 38)
    print(f"  Moment:        {dims.get('moment', 0.0):.1f} / 100")
    print(f"  Narrative:     {dims.get('narrative', 0.0):.1f} / 100")
    print(f"  Presentation:  {dims.get('presentation', 0.0):.1f} / 100")
    print(f"  Publishing:    {dims.get('publishing', 0.0):.1f} / 100")
    print(f"  Technical:     {dims.get('technical', 0.0):.1f} / 100")
    print(f"  Diversity:     {dims.get('diversity', 0.0):.1f} / 100")
    print("  " + "-" * 38)
    print(f"  Composite:     {pub_final['score']:.1f} / 100 [{pub_final['level'].upper()}]")
    print(f"  Gate Decision: {pub_final['recommendation'].upper()}")
    if pub_final.get("blocking_issues"):
        print(f"  Blocking:      {pub_final['blocking_issues']}")
    else:
        print(f"  Blocking:      None (Zero technical or narrative blocking issues)")

    assert pub_final["recommendation"] == "publish", "Final Short must pass quality gate and be recommended for publishing"

    print("\n" + "=" * 80)
    print("ALL 8 PHASE 9.1 VALIDATION STEPS COMPLETED CLEANLY (LIVE PIPELINE HARDENED)")
    print("  • AI timeline tracks populated:          YES (Subtitles, Effects, SFX, Ducking)")
    print("  • Human multi-track edits detected:      YES (['subtitles', 'effects', 'sfx'])")
    print("  • Unrelated tracks preserved:            YES (100% preservation)")
    print("  • Quality recalculated after render:     YES (Zero technical failures)")
    print("  • Final output passed technical gate:    YES (PASS)")
    print("=" * 80)


if __name__ == "__main__":
    main()
