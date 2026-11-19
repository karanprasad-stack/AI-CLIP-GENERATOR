"""CLI entry point for AI Gaming Shorts Generator (Phases 1, 2, 3, 4, 5, and 6A)."""

import sys
import argparse
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.pipeline.pipeline import run_pipeline, PipelineError
from backend.app.config import TOP_N_CANDIDATES, LAYOUT_AUTO


def format_duration(seconds: float) -> str:
    """Format duration in seconds to a human-readable HH:MM:SS or MM:SS string."""
    s = int(round(seconds))
    mins, secs = divmod(s, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def make_progress_reporter(total_steps: int):
    """Factory creating a clean step-by-step progress reporter."""
    def reporter(step: int, message: str) -> None:
        print(f"[{step}/{total_steps}] {message}")
    return reporter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI Gaming Shorts Generator - CLI (Video, Subtitles, Effects & Audio Polish)"
    )
    parser.add_argument(
        "url",
        type=str,
        nargs="?",
        help="YouTube video or stream URL",
    )
    parser.add_argument(
        "--phase",
        type=str,
        default="6b",
        choices=["1", "2", "3", "4", "5", "6", "6a", "6A", "6b", "6B"],
        help="Execution phase (1=Audio/Transcript, 2=Candidates, 3=9:16 Shorts, 4=Captions, 5=Effects, 6a=Audio Polish, 6b=Publishing Package). Default: 6b",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=TOP_N_CANDIDATES,
        help=f"Number of top candidates to render into Shorts. Default: {TOP_N_CANDIDATES}",
    )
    parser.add_argument(
        "--layout",
        type=str,
        default=LAYOUT_AUTO,
        choices=["auto", "smart_crop", "blurred_background", "facecam_gameplay"],
        help="Shorts layout strategy (auto, smart_crop, blurred_background, facecam_gameplay). Default: auto",
    )
    parser.add_argument(
        "--captions",
        type=str,
        default="on",
        choices=["on", "off"],
        help="Enable/disable karaoke subtitle generation (on/off). Default: on",
    )
    parser.add_argument(
        "--emoji",
        type=str,
        default="on",
        choices=["on", "off"],
        help="Enable/disable contextual emoji overlays (on/off). Default: on",
    )
    parser.add_argument(
        "--effects",
        type=str,
        default="on",
        choices=["on", "off"],
        help="Enable/disable context-aware visual effects (on/off). Default: on",
    )
    parser.add_argument(
        "--audio",
        type=str,
        default="on",
        choices=["on", "off"],
        help="Enable/disable audio processing & normalization (on/off). Default: on",
    )
    parser.add_argument(
        "--sfx",
        type=str,
        default="on",
        choices=["on", "off"],
        help="Enable/disable sound effect mixing (on/off). Default: on",
    )
    parser.add_argument(
        "--ducking",
        type=str,
        default="on",
        choices=["on", "off"],
        help="Enable/disable speech-aware audio ducking (on/off). Default: on",
    )
    parser.add_argument(
        "--thumbnail",
        type=str,
        default="on",
        choices=["on", "off"],
        help="Enable/disable 1280x720 thumbnail generation (on/off). Default: on",
    )
    parser.add_argument(
        "--metadata",
        type=str,
        default="on",
        choices=["on", "off"],
        help="Enable/disable publishing metadata generation (on/off). Default: on",
    )
    parser.add_argument(
        "--llm",
        type=str,
        default="off",
        choices=["on", "off"],
        help="Enable/disable optional local Ollama LLM for titles (on/off). Default: off",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print full traceback on failure for debugging",
    )

    args = parser.parse_args()

    if not args.url:
        print("Error: No YouTube URL provided.", file=sys.stderr)
        print("Usage: python -m backend.app.main \"https://www.youtube.com/watch?v=...\" [--phase 6b] [--top 5]", file=sys.stderr)
        return 1

    phase_str = str(args.phase).strip().lower()
    if phase_str in ["6b", "6B"]:
        phase_num = 6
        total_steps = 23
    elif "6" in phase_str or "6a" in phase_str:
        phase_num = 6
        total_steps = 19
    elif phase_str == "5":
        phase_num = 5
        total_steps = 15
    elif phase_str == "4":
        phase_num = 4
        total_steps = 12
    elif phase_str == "3":
        phase_num = 3
        total_steps = 9
    else:
        phase_num = int(phase_str)
        total_steps = 5

    reporter = make_progress_reporter(total_steps)

    captions_bool = (args.captions.lower() == "on")
    emoji_bool = (args.emoji.lower() == "on")
    effects_bool = (args.effects.lower() == "on")
    audio_bool = (args.audio.lower() == "on")
    sfx_bool = (args.sfx.lower() == "on")
    ducking_bool = (args.ducking.lower() == "on")
    thumb_bool = (args.thumbnail.lower() == "on")
    meta_bool = (args.metadata.lower() == "on")
    llm_bool = (args.llm.lower() == "on")

    try:
        result = run_pipeline(
            url=args.url,
            progress_callback=reporter,
            phase=args.phase,
            top_n=args.top,
            layout=args.layout,
            captions=captions_bool,
            emoji=emoji_bool,
            effects=effects_bool,
            audio=audio_bool,
            sfx=sfx_bool,
            ducking=ducking_bool,
            thumbnail=thumb_bool,
            metadata_enabled=meta_bool,
            llm=llm_bool,
        )

        if phase_num <= 2:
            candidates_count = result["candidates_count"]
            best = result["best_candidate"]

            print("\n✓ Phase 2 complete")
            print(f"✓ Candidates found: {candidates_count}")

            if best:
                start_fmt = format_duration(best["start"])
                end_fmt = format_duration(best["end"])
                print(f"✓ Best candidate: {start_fmt} → {end_fmt} ({best['duration']:.1f}s)")
                print(f"✓ Score: {best['score']:.1f}")
            else:
                print("✓ No candidates could be generated for this video.")

        elif phase_num == 3:
            print("\n" + "=" * 65)
            print("✓ PHASE 3 COMPLETE: 9:16 YouTube Shorts Generated")
            print("=" * 65)
            print(f"✓ Source Video ID: {result['video_id']}")
            print(f"✓ Title: {result['title']}")
            print(f"✓ Layout Selected: {result['layout_used']}")
            print(f"✓ Total Phase 3 Runtime: {result['phase3_time_sec']:.2f}s")
            print(f"✓ Shorts Generated: {result['shorts_passed']}/{result['top_candidates_processed']} PASS\n")

            print("Generated Shorts:")
            for c in result.get("processed_candidates", []):
                rank = c["rank"]
                score = c["final_score"]
                status = c.get("status", "UNKNOWN")
                ext_dur = c.get("extraction_duration", 0.0)
                render_sec = c.get("rendering_time_sec", 0.0)
                short_path = c.get("short_clip", "")
                val_status = c.get("validation", {}).get("status", status)

                print(f"  [{rank}] Score: {score:.1f} | Duration: {ext_dur:.1f}s | Render Time: {render_sec:.2f}s | Status: {val_status}")
                print(f"      File: {short_path}")

            print(f"\nPhase 3 Metadata: {result['phase3_metadata_file']}")

        elif phase_num == 4:
            print("\n" + "=" * 70)
            print("✓ PHASE 4 COMPLETE: Word-Level Subtitles & Emojis Generated")
            print("=" * 70)
            print(f"✓ Source Video ID: {result['video_id']}")
            print(f"✓ Title: {result['title']}")
            print(f"✓ Captions Enabled: {result['captions_enabled']} | Emojis Enabled: {result['emojis_enabled']}")
            print(f"✓ Total Phase 4 Runtime: {result['phase4_time_sec']:.2f}s")
            print(f"✓ Captioned Shorts: {result['shorts_passed']}/{result['top_candidates_processed']} PASS\n")

            print("Generated Captioned Shorts:")
            for c in result.get("processed_candidates", []):
                rank = c["rank"]
                score = c["final_score"]
                status = c.get("phase4_status", "UNKNOWN")
                ext_dur = c.get("extraction_duration", 0.0)
                words = c.get("words_count", 0)
                groups = c.get("caption_groups_count", 0)
                emojis = c.get("emojis_count", 0)
                render_sec = c.get("caption_render_time_sec", 0.0)
                encoder = c.get("caption_encoder", "nvenc")
                cap_clip = c.get("captioned_clip", "")
                ass_file = c.get("ass_file", "")

                print(f"  [{rank}] Score: {score:.1f} | Duration: {ext_dur:.1f}s | Words: {words} ({groups} groups) | Emojis: {emojis} | Render: {render_sec:.2f}s ({encoder}) | Status: {status}")
                print(f"      ASS:   {ass_file}")
                print(f"      Video: {cap_clip}")

            print(f"\nPhase 4 Metadata: {result['phase4_metadata_file']}")

        elif phase_num == 5:
            print("\n" + "=" * 75)
            print("✓ PHASE 5 COMPLETE: Context-Aware Visual Effects & Final Shorts Generated")
            print("=" * 75)
            print(f"✓ Source Video ID: {result['video_id']}")
            print(f"✓ Title: {result['title']}")
            print(f"✓ Effects Enabled: {result['effects_enabled']} | Total Effects: {result['total_effects_applied']}")
            print(f"✓ Total Phase 5 Runtime: {result['phase5_time_sec']:.2f}s")
            print(f"✓ Final Shorts: {result['shorts_passed']}/{result['top_candidates_processed']} PASS\n")

            print("Final Edited Shorts:")
            for c in result.get("processed_candidates", []):
                rank = c["rank"]
                score = c["final_score"]
                status = c.get("phase5_status", "UNKNOWN")
                ext_dur = c.get("extraction_duration", 0.0)
                eff_count = c.get("effects_count", 0)
                eff_breakdown = c.get("effects_breakdown", {})
                render_sec = c.get("effect_render_time_sec", 0.0)
                encoder = c.get("effect_encoder", "h264_nvenc")
                final_clip = c.get("final_clip", "")
                timeline_file = c.get("effect_timeline_file", "")

                eff_str = ", ".join(f"{k}: {v}" for k, v in eff_breakdown.items()) if eff_breakdown else "none"
                print(f"  [{rank}] Score: {score:.1f} | Duration: {ext_dur:.1f}s | Effects: {eff_count} ({eff_str}) | Render: {render_sec:.2f}s ({encoder}) | Status: {status}")
                print(f"      Timeline: {timeline_file}")
                print(f"      Final:    {final_clip}")

            print(f"\nPhase 5 Metadata: {result['phase5_metadata_file']}")

        elif result.get("phase") in ["6B", "6B.1", "6B.1.1"]:
            # Phase 6B / 6B.1.1 Summary Output
            print("\n" + "=" * 75)
            print("✓ PHASE 6B.1.1 COMPLETE: Metadata Quality Refinement & Publishing Complete")
            print("=" * 75)
            print(f"✓ Source Video ID: {result['video_id']}")
            print(f"✓ Title: {result['title']}")
            print(f"✓ Total Runtime: {result['phase6b_time_sec']:.2f}s")
            print(f"✓ Publishing Packages: {result['packages_passed']}/{result['top_candidates_processed']} PASS\n")

            print("Final Publishing Bundles:")
            for p in result.get("published_packages", []):
                cand_id = p["candidate_id"]
                title = p["title"]
                thumb_ts = p["thumbnail_timestamp"]
                thumb_score = p["thumbnail_score"]
                status = p["validation"]["status"]
                pkg_dir = p["package_dir"]
                q_score = p.get("metadata_quality", {}).get("overall", 0.9)

                print(f"  [{cand_id}] Title: \"{title}\"")
                print(f"      Thumbnail: {thumb_ts:.2f}s (Score: {thumb_score:.3f}) | Quality: {q_score:.2f} | Status: {status}")
                print(f"      Package Directory: {pkg_dir}")

            print(f"\nPublishing Manifest: {result['manifest_file']}")

        else:
            # Phase 6A Summary Output
            print("\n" + "=" * 75)
            print("✓ PHASE 6A COMPLETE: Audio Polish, SFX & Loudness Normalization Complete")
            print("=" * 75)
            print(f"✓ Source Video ID: {result['video_id']}")
            print(f"✓ Title: {result['title']}")
            print(f"✓ Audio: {result['audio_enabled']} | SFX: {result['sfx_enabled']} (Total: {result['total_sfx_applied']}) | Ducking: {result['ducking_enabled']}")
            print(f"✓ Total Phase 6A Runtime: {result['phase6a_time_sec']:.2f}s")
            print(f"✓ Polished Shorts: {result['shorts_passed']}/{result['top_candidates_processed']} PASS\n")

            print("Final Polished Shorts:")
            for c in result.get("processed_candidates", []):
                rank = c["rank"]
                score = c["final_score"]
                status = c.get("phase6a_status", "UNKNOWN")
                ext_dur = c.get("extraction_duration", 0.0)
                sfx_count = c.get("sfx_count", 0)
                sfx_breakdown = c.get("sfx_breakdown", {})
                duck_intervals = c.get("ducking_intervals_count", 0)
                lufs = c.get("measured_lufs", -14.0)
                tp = c.get("measured_tp", -1.0)
                render_sec = c.get("audio_render_time_sec", 0.0)
                polished_clip = c.get("audio_polished_clip", "")
                timeline_file = c.get("audio_timeline_file", "")

                sfx_str = ", ".join(f"{k}: {v}" for k, v in sfx_breakdown.items()) if sfx_breakdown else "none"
                print(f"  [{rank}] Score: {score:.1f} | Duration: {ext_dur:.1f}s | SFX: {sfx_count} ({sfx_str}) | Ducking: {duck_intervals} zones | LUFS: {lufs:.1f} | Peak: {tp:.1f} dBTP | Render: {render_sec:.2f}s | Status: {status}")
                print(f"      Audio Timeline: {timeline_file}")
                print(f"      Polished Short: {polished_clip}")

            print(f"\nPhase 6A Metadata: {result['phase6a_metadata_file']}")

        return 0

    except PipelineError as e:
        print(f"\n[ERROR] Pipeline failed: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1
    except KeyboardInterrupt:
        print("\n[!] Process cancelled by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"\n[ERROR] Unexpected failure: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
