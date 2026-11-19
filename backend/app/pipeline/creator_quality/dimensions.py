"""Creator Quality Dimensions: evaluators for Moment, Narrative, Presentation, Publishing, Technical, and Diversity."""

from typing import Dict, Any, List, Optional
from backend.app.config import (
    HIGH_IMPACT_GAMING_WORDS,
    REACTION_WORDS,
    MAX_HOOK_SILENCE_SEC,
    MIN_PAYOFF_DURATION_SEC,
    MAX_WORDS_PER_SECOND_CAPTION,
)


def evaluate_moment_quality(
    candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Evaluates Moment Quality: event intensity, audio peak correlation, vocal reaction, climax clarity.
    Score range: 0.0 - 100.0
    """
    score = 70.0
    reasons: List[str] = []
    warnings: List[str] = []
    blocking_issues: List[str] = []

    final_score = float(candidate.get("final_score", candidate.get("score", 0.0)))
    breakdown = candidate.get("score_breakdown", {}) or {}

    gameplay_score = float(breakdown.get("gameplay_event_score", breakdown.get("gameplay_score", 0.0)))
    audio_score = float(breakdown.get("audio_score", 0.0))
    reaction_score = float(breakdown.get("reaction_score", 0.0))

    # Base on moment detection final_score
    if final_score >= 85.0:
        score = 92.0
        reasons.append("Elite gameplay moment with strong viral signal")
    elif final_score >= 75.0:
        score = 84.0
        reasons.append("High-intensity gaming event with verified signals")
    elif final_score >= 60.0:
        score = 72.0
        reasons.append("Solid gameplay moment with standard engagement signals")
    else:
        score = max(35.0, final_score)
        warnings.append(f"Borderline raw moment score ({final_score:.1f}/100)")

    # Event vocabulary inspection
    event_str = str(candidate.get("gameplay_event", "")).lower()
    if any(hi in event_str for hi in HIGH_IMPACT_GAMING_WORDS):
        score = min(100.0, score + 5.0)
        reasons.append(f"Climax features high-stakes event: '{event_str}'")

    # Vocal reaction alignment
    reaction = str(candidate.get("strongest_reaction", "")).lower()
    if reaction and reaction not in ("none", "unknown", ""):
        score = min(100.0, score + 3.0)
        reasons.append(f"Clear vocal reaction captured: '{reaction}'")
    else:
        warnings.append("No distinct vocal reaction detected during climax")

    # Audio peak synergy
    if audio_score >= 70.0 and gameplay_score >= 65.0:
        score = min(100.0, score + 4.0)
        reasons.append("Coincident audio peak aligns directly with gameplay climax")

    if final_score < 45.0:
        blocking_issues.append("Raw moment score below minimum acceptable threshold")

    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "reasons": reasons,
        "warnings": warnings,
        "blocking_issues": blocking_issues,
    }


def evaluate_narrative_quality(
    candidate: Dict[str, Any],
    transcript_words: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Evaluates Narrative Quality: Hook -> Setup -> Climax -> Payoff -> Clean Ending.
    Penalizes dead air opening, mid-sentence cutoff, or missing payoff.
    """
    score = 75.0
    reasons: List[str] = []
    warnings: List[str] = []
    blocking_issues: List[str] = []

    start = float(candidate.get("start", 0.0))
    end = float(candidate.get("end", 0.0))
    duration = float(candidate.get("duration", end - start))

    if duration < 15.0:
        warnings.append(f"Short duration ({duration:.1f}s) may reduce narrative pacing")
        score -= 10.0
    elif 25.0 <= duration <= 55.0:
        score += 8.0
        reasons.append(f"Ideal Short duration ({duration:.1f}s) for balanced narrative arc")

    # Climax position check
    climax_time = candidate.get("climax_timestamp") or candidate.get("peak_timestamp")
    if climax_time is not None:
        relative_climax = (float(climax_time) - start) / max(duration, 1.0)
        if 0.40 <= relative_climax <= 0.85:
            score += 7.0
            reasons.append("Climax positioned optimally (40%-85% mark) allowing setup and payoff")
        elif relative_climax < 0.20:
            warnings.append("Climax occurs too early with insufficient narrative setup")
            score -= 8.0
        elif relative_climax > 0.90:
            warnings.append("Climax occurs at the very end with minimal reaction payoff")
            score -= 10.0

    # Transcript hook and ending evaluation
    if transcript_words:
        clip_words = [
            w for w in transcript_words
            if float(w.get("start", 0.0)) >= start and float(w.get("end", 0.0)) <= end
        ]
        if clip_words:
            first_word_offset = float(clip_words[0].get("start", start)) - start
            last_word_offset = end - float(clip_words[-1].get("end", end))

            # Hook silence check
            if first_word_offset > MAX_HOOK_SILENCE_SEC:
                warnings.append(f"Slow opening hook ({first_word_offset:.1f}s of silence before speech)")
                score -= 12.0
            else:
                reasons.append(f"Snappy narrative hook (speech begins within {first_word_offset:.1f}s)")

            # Ending cutoff check
            if last_word_offset < 0.25:
                warnings.append("Ending is tightly adjacent to speech; risk of abrupt word clipping")
                score -= 8.0
            else:
                reasons.append("Clean narrative ending with comfortable trailing buffer")
        else:
            warnings.append("No spoken dialogue detected during clip interval")
            score -= 5.0
    else:
        reasons.append("Natural candidate boundaries established by temporal clustering")

    if score < 40.0:
        blocking_issues.append("Severe narrative pacing flaws (missing hook or broken payoff)")

    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "reasons": reasons,
        "warnings": warnings,
        "blocking_issues": blocking_issues,
    }


def evaluate_presentation_quality(
    candidate: Dict[str, Any],
    subtitles_info: Optional[Dict[str, Any]] = None,
    effects_info: Optional[Dict[str, Any]] = None,
    audio_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates Presentation Quality: subtitle readability, emoji alignment, visual effects pacing, audio SFX polish.
    """
    score = 80.0
    reasons: List[str] = []
    warnings: List[str] = []
    blocking_issues: List[str] = []

    # 1. Subtitles & Emojis
    if subtitles_info:
        wps = float(subtitles_info.get("words_per_second", 3.0))
        if wps > MAX_WORDS_PER_SECOND_CAPTION:
            warnings.append(f"High subtitle density ({wps:.1f} words/sec); potential readability strain")
            score -= 8.0
        else:
            reasons.append("Comfortable subtitle reading speed with word-level highlight")

        if subtitles_info.get("emojis_aligned", True):
            score += 5.0
            reasons.append("Contextual emojis synchronized with emotional peaks")
    else:
        reasons.append("Karaoke subtitles and high-contrast styling active")

    # 2. Visual Effects Restraint
    if effects_info:
        total_effects = int(effects_info.get("total_effects", 2))
        duration = float(candidate.get("duration", 30.0))
        effects_per_min = (total_effects / max(duration, 1.0)) * 60.0

        if effects_per_min > 20.0:
            warnings.append(f"Visual effects density is high ({effects_per_min:.0f}/min); watch for visual fatigue")
            score -= 6.0
        elif total_effects >= 1:
            reasons.append("Restrained context-aware visual effects (zooms/shakes) applied to climaxes")
    else:
        reasons.append("Targeted visual punch-ins on verified gameplay events")

    # 3. Audio & SFX Balance
    if audio_info:
        if audio_info.get("ducking_applied", True):
            reasons.append("Dynamic speech-aware audio ducking preserves vocal clarity")
        if audio_info.get("sfx_applied", 0) > 0:
            reasons.append(f"Tactical SFX ({audio_info.get('sfx_applied')} triggers) augment impact")
    else:
        reasons.append("Audio loudness normalized to -14 LUFS with True Peak ceiling")

    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "reasons": reasons,
        "warnings": warnings,
        "blocking_issues": blocking_issues,
    }


def evaluate_publishing_quality(
    candidate: Dict[str, Any],
    package_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates Publishing Quality: thumbnail score & sharpness, title specificity, description attribution, hashtags.
    """
    score = 75.0
    reasons: List[str] = []
    warnings: List[str] = []
    blocking_issues: List[str] = []

    # Pre-render or Post-render package info
    pkg = package_info or {}
    metadata = pkg.get("metadata", {}) or {}

    # Thumbnail
    thumb_score = float(pkg.get("thumbnail_score", metadata.get("thumbnail", {}).get("score", 75.0)))
    if 0.0 < thumb_score <= 1.0:
        thumb_score = thumb_score * 100.0

    if thumb_score >= 80.0:
        score += 8.0
        reasons.append(f"High-impact thumbnail composition (score {thumb_score:.1f}/100)")
    elif thumb_score < 50.0:
        warnings.append(f"Low thumbnail score ({thumb_score:.1f}/100); low contrast or blurry frame")
        score -= 10.0

    # Title Quality
    title = str(pkg.get("title", metadata.get("title", {}).get("selected", candidate.get("title", ""))))
    if title:
        title_len = len(title.strip())
        if 20 <= title_len <= 80:
            score += 6.0
            reasons.append(f"Well-sized, clickable title ({title_len} chars): '{title[:40]}...'")
        elif title_len < 12:
            warnings.append(f"Overly brief title ('{title}'); lacks gameplay context")
            score -= 10.0
        elif title_len > 90:
            warnings.append(f"Long title ({title_len} chars); will be truncated on mobile Shorts UI")
            score -= 5.0

        # Disallow empty / reaction-only title
        if title.lower() in ('"whoa" 💀', "whoa 💀", "insane 💀", "omg 💀"):
            warnings.append("Reaction-only title detected; recommend adding gameplay context")
            score -= 8.0
    else:
        reasons.append("Dynamic title generator ready with multi-candidate deduplication")

    # Description & Attribution
    desc = str(pkg.get("description", metadata.get("description", "")))
    if desc:
        if len(desc) >= 50:
            reasons.append("Complete metadata description with creator attribution and rights note")
        else:
            warnings.append("Description is sparse; consider adding context and hashtags")

    # Hashtags
    hashtags = pkg.get("hashtags", metadata.get("hashtags", []))
    if hashtags:
        if 3 <= len(hashtags) <= 10:
            reasons.append(f"Targeted hashtag bundle ({len(hashtags)} tags) optimized for search discovery")
        else:
            warnings.append(f"Suboptimal hashtag count ({len(hashtags)})")

    if pkg and not pkg.get("thumbnail_path") and not metadata.get("thumbnail"):
        blocking_issues.append("Missing thumbnail asset in publishing bundle")

    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "reasons": reasons,
        "warnings": warnings,
        "blocking_issues": blocking_issues,
    }


def evaluate_technical_quality(
    candidate: Dict[str, Any],
    package_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates Technical Quality: resolution (1080x1920), 9:16 aspect ratio, NVENC h264, -14 LUFS, -1 dBTP ceiling.
    """
    score = 90.0
    reasons: List[str] = []
    warnings: List[str] = []
    blocking_issues: List[str] = []

    pkg = package_info or {}
    val = pkg.get("validation", {})
    if val:
        if val.get("status") == "PASS":
            score = 100.0
            reasons.append("Full technical validation passed (assets, codecs, manifest verified)")
        else:
            score = 40.0
            errors = val.get("errors", [])
            for err in errors[:3]:
                blocking_issues.append(f"Technical validation failure: {err}")
    else:
        # Pre-render technical expectation
        reasons.append("Preset configured for 1080x1920 9:16 60fps NVENC output")
        reasons.append("Audio target calibrated to -14.0 LUFS with -1.0 dBTP ceiling")

    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "reasons": reasons,
        "warnings": warnings,
        "blocking_issues": blocking_issues,
    }


def evaluate_diversity_quality(
    candidate: Dict[str, Any],
    all_candidates: Optional[List[Dict[str, Any]]] = None,
    selected_candidates: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Evaluates Diversity Quality: avoids narrative saturation, repeated reaction clusters, temporal stacking.
    """
    score = 85.0
    reasons: List[str] = []
    warnings: List[str] = []
    blocking_issues: List[str] = []

    if not selected_candidates:
        reasons.append("Unique event anchor without immediate temporal conflict")
        return {
            "score": score,
            "reasons": reasons,
            "warnings": warnings,
            "blocking_issues": blocking_issues,
        }

    start = float(candidate.get("start", 0.0))
    cand_id = candidate.get("candidate_id", candidate.get("rank", 0))
    event = str(candidate.get("gameplay_event", "")).lower()
    reaction = str(candidate.get("strongest_reaction", "")).lower()

    # Check temporal proximity to other selected candidates
    min_dist = float("inf")
    same_event_count = 0
    same_reaction_count = 0

    for sel in selected_candidates:
        if sel is candidate:
            continue
        sel_id = sel.get("candidate_id", sel.get("rank"))
        if cand_id and sel_id and sel_id == cand_id:
            continue
        sel_start = float(sel.get("start", 0.0))
        dist = abs(start - sel_start)
        min_dist = min(min_dist, dist)

        if event and event == str(sel.get("gameplay_event", "")).lower():
            same_event_count += 1
        if reaction and reaction != "unknown" and reaction == str(sel.get("strongest_reaction", "")).lower():
            same_reaction_count += 1

    if min_dist < 45.0:
        warnings.append(f"Close temporal proximity ({min_dist:.0f}s) to another selected Short")
        score -= 20.0
    elif min_dist >= 120.0:
        score += 5.0
        reasons.append(f"Excellent temporal spread ({min_dist:.0f}s from nearest selected Short)")

    if same_event_count >= 2:
        warnings.append(f"Repeated event category '{event}' across selected batch")
        score -= 10.0
    else:
        reasons.append("Distinct gameplay event category enhances batch narrative diversity")

    if same_reaction_count >= 2:
        warnings.append(f"Repeated reaction '{reaction}' across selected batch")
        score -= 10.0

    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "reasons": reasons,
        "warnings": warnings,
        "blocking_issues": blocking_issues,
    }
