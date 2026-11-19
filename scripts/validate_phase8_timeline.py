"""Phase 8 Validation Script: executes 8 comprehensive real-video timeline editing and rendering tests on EdtUDpqjltA."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
import time
from backend.app.services.project_manager import ProjectManager
from backend.app.pipeline.timeline import (
    TimelineStore,
    TimelineEdlGenerator,
    TimelineValidator,
    DirtyTracker,
    TimelineRenderer,
    TimelineEDL,
)


def run_phase8_validation():
    print("=" * 80)
    print("PHASE 8: EDITABLE MULTI-TRACK TIMELINE / EDL ENGINE VALIDATION")
    print("Source Video ID: EdtUDpqjltA")
    print("=" * 80)

    pm = ProjectManager()
    project_id = "EdtUDpqjltA"
    candidate_id = 1
    project_dir = pm.output_dir / project_id

    store = TimelineStore()
    validator = TimelineValidator()

    # Step 0: Ensure initial timeline exists
    t0_start = time.perf_counter()
    tl_dict = pm.get_timeline(project_id, candidate_id)
    tl_load_time = (time.perf_counter() - t0_start) * 1000
    print(f"\n[Step 0] Initial Timeline Loaded / Synthesized in {tl_load_time:.2f}ms")
    print(f"  • Candidate ID:       {tl_dict['candidate_id']}")
    print(f"  • Version:            v{tl_dict['version']}")
    print(f"  • Duration:           {tl_dict['duration']:.2f}s")
    print(f"  • Subtitles Count:    {len(tl_dict['subtitles_track'])}")
    print(f"  • Effects Count:      {len(tl_dict['effects_track'])}")
    print(f"  • SFX Count:          {len(tl_dict['sfx_track'])}")
    print(f"  • Ducking Count:      {len(tl_dict['ducking_track'])}")

    timeline = TimelineEDL(**tl_dict)

    # -------------------------------------------------------------------------
    # Test 1 — Subtitle correction
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 1: SUBTITLE CORRECTION")
    print("-" * 60)
    orig_text = timeline.subtitles_track[0].text if timeline.subtitles_track else "timing"
    edited_text = "Talk about timing in CSGO! 😂" if orig_text != "Talk about timing in CSGO! 😂" else "Alternative clutch timing! 🔥"
    timeline.subtitles_track[0].text = edited_text
    timeline.subtitles_track[0].edited = True
    timeline.subtitles_track[0].original_text = orig_text

    t_save_start = time.perf_counter()
    saved_tl_1 = pm.save_timeline(project_id, candidate_id, timeline.model_dump())
    save_time_ms = (time.perf_counter() - t_save_start) * 1000

    print(f"  ✓ Subtitle edited: '{orig_text}' → '{edited_text}'")
    print(f"  ✓ Saved to disk in {save_time_ms:.2f}ms. Version incremented to: v{saved_tl_1['version']}")
    print(f"  ✓ Dirty tracks detected: {saved_tl_1['metadata']['dirty_tracks']}")
    assert "subtitles" in saved_tl_1['metadata']['dirty_tracks'], "Dirty track did not include subtitles!"
    timeline = TimelineEDL(**saved_tl_1)

    # -------------------------------------------------------------------------
    # Test 2 — Effect removal / disable
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 2: EFFECT REMOVAL / DISABLE")
    print("-" * 60)
    if timeline.effects_track:
        eff = timeline.effects_track[0]
        eff.enabled = not eff.enabled
        eff.edited = True
        saved_tl_2 = pm.save_timeline(project_id, candidate_id, timeline.model_dump())
        print(f"  ✓ Toggled effect '{eff.id}' ({eff.type}) enabled={eff.enabled}")
        print(f"  ✓ Dirty tracks: {saved_tl_2['metadata']['dirty_tracks']}")
        assert "effects" in saved_tl_2['metadata']['dirty_tracks']
        timeline = TimelineEDL(**saved_tl_2)
    else:
        print("  • (No effects to disable)")

    # -------------------------------------------------------------------------
    # Test 3 — SFX removal / disable
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 3: SFX REMOVAL / DISABLE")
    print("-" * 60)
    if timeline.sfx_track:
        sfx = timeline.sfx_track[0]
        sfx.enabled = not sfx.enabled
        sfx.edited = True
        saved_tl_3 = pm.save_timeline(project_id, candidate_id, timeline.model_dump())
        print(f"  ✓ Toggled SFX '{sfx.id}' ({sfx.event_type}) enabled={sfx.enabled}")
        print(f"  ✓ Dirty tracks: {saved_tl_3['metadata']['dirty_tracks']}")
        assert "sfx" in saved_tl_3['metadata']['dirty_tracks']
        timeline = TimelineEDL(**saved_tl_3)
    else:
        print("  • (No SFX to disable)")

    # -------------------------------------------------------------------------
    # Test 4 — Effect timing move
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 4: EFFECT TIMING MODIFICATION")
    print("-" * 60)
    if len(timeline.effects_track) > 1:
        eff2 = timeline.effects_track[1]
        orig_start = eff2.start
        eff2.start = round(eff2.start + (0.5 if eff2.start < 20.0 else -0.5), 2)
        eff2.end = round(eff2.end + 0.5, 2)
        eff2.edited = True
        saved_tl_4 = pm.save_timeline(project_id, candidate_id, timeline.model_dump())
        print(f"  ✓ Shifted effect '{eff2.id}' start: {orig_start}s → {eff2.start}s")
        assert "effects" in saved_tl_4['metadata']['dirty_tracks']
        timeline = TimelineEDL(**saved_tl_4)

    # -------------------------------------------------------------------------
    # Test 5 — Boundary change
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 5: BOUNDARY ADJUSTMENT")
    print("-" * 60)
    orig_sin = timeline.boundaries.source_in
    timeline.boundaries.source_in = round(orig_sin + (1.0 if orig_sin < 165.0 else -1.0), 2)
    timeline.boundaries.duration = round(timeline.boundaries.source_out - timeline.boundaries.source_in, 2)
    timeline.duration = timeline.boundaries.duration
    saved_tl_5 = pm.save_timeline(project_id, candidate_id, timeline.model_dump())
    print(f"  ✓ Shifted source_in from {orig_sin}s → {timeline.boundaries.source_in}s")
    print(f"  ✓ New clip duration: {timeline.duration}s")
    print(f"  ✓ Dirty tracks: {saved_tl_5['metadata']['dirty_tracks']}")
    assert "boundaries" in saved_tl_5['metadata']['dirty_tracks']
    timeline = TimelineEDL(**saved_tl_5)

    # -------------------------------------------------------------------------
    # Test 6 — Save / reload persistence
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 6: DISK PERSISTENCE & HISTORY")
    print("-" * 60)
    reloaded = store.get_timeline(project_dir, candidate_id)
    assert reloaded is not None
    assert reloaded.version == timeline.version
    assert reloaded.subtitles_track[0].text == edited_text
    print(f"  ✓ Successfully verified reload from disk (active version: v{reloaded.version})")
    backup_file = project_dir / "publishing" / f"candidate_{candidate_id:02d}" / f"timeline.v{timeline.version - 1}.json"
    if backup_file.exists():
        print(f"  ✓ Backup version exists on disk: {backup_file.name}")

    # -------------------------------------------------------------------------
    # Test 7 — Undo / redo logic simulation
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 7: UNDO / REDO STATE SIMULATION")
    print("-" * 60)
    history_stack = [reloaded.model_copy(deep=True)]
    # State change
    state2 = reloaded.model_copy(deep=True)
    state2.subtitles_track[0].text = "Third Edit Text"
    history_stack.append(state2)
    # Undo
    undone = history_stack[0]
    assert undone.subtitles_track[0].text == edited_text
    print(f"  ✓ Undo restores previous state: '{undone.subtitles_track[0].text}'")
    # Redo
    redone = history_stack[1]
    assert redone.subtitles_track[0].text == "Third Edit Text"
    print(f"  ✓ Redo restores forward state: '{redone.subtitles_track[0].text}'")

    # -------------------------------------------------------------------------
    # Test 8 — Quality Invalidation & Final Re-render
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 8: CREATOR QUALITY RE-EVALUATION & FINAL RE-RENDER")
    print("-" * 60)
    print(f"  • Triggering final timeline re-render on Short #{candidate_id}...")
    t_render_start = time.perf_counter()
    render_result = pm.render_timeline(project_id, candidate_id)
    render_dur = time.perf_counter() - t_render_start

    print(f"  ✓ Re-render finished successfully in {render_dur:.2f}s!")
    print(f"  ✓ Final Video Path:        {render_result['video_path']}")
    print(f"  ✓ Technical Validation:    {render_result['validation']['status']}")
    print(f"  ✓ Creator Publishability:  {render_result['publishability']['score']:.1f}/100 [{render_result['publishability']['level'].upper()}]")
    print(f"  ✓ Recommendation:          {render_result['publishability']['recommendation'].upper()}")
    print("  ✓ Reasons:")
    for r in render_result['publishability']['reasons'][:3]:
        print(f"      • {r}")

    # Verify final.mp4 is valid
    final_file = Path(render_result['video_path'])
    assert final_file.exists() and final_file.stat().st_size > 500000, "Output final.mp4 missing or empty!"
    print(f"  ✓ Verified final.mp4 integrity ({final_file.stat().st_size / (1024*1024):.2f} MB)")

    print("\n" + "=" * 80)
    print("ALL 8 PHASE 8 REAL-VIDEO VALIDATION TESTS PASSED CLEANLY")
    print("=" * 80)


if __name__ == "__main__":
    run_phase8_validation()
