"""Core Hinglish Normalization Engine: preserves original transcript and word timestamps."""

import re
from typing import Dict, Any, List, Tuple, Optional

from .language_detector import detect_language
from .gaming_terms import is_gaming_term, get_canonical_gaming_term, is_acronym_or_proper_name
from .roman_hindi import (
    is_roman_hindi_word,
    normalize_roman_hindi_token,
    MULTI_TOKEN_CONTRACTIONS,
)
from .confidence import ConfidenceEvaluator

# Fillers that can be safely pruned at sentence boundaries if they add no reaction
HESITATION_FILLERS = {"uh", "umm", "uhh", "erm"}


class HinglishNormalizer:
    """Normalizes mixed Roman Hindi and English gaming subtitles faithfully."""

    def __init__(self, mode: str = "hinglish", confidence_threshold: float = 0.60):
        self.mode = mode.lower()  # 'auto', 'original', 'english', 'hindi', 'hinglish'
        self.confidence_evaluator = ConfidenceEvaluator(threshold=confidence_threshold)

    def normalize_word(self, word: str, is_sentence_start: bool = False) -> Tuple[str, bool, Optional[str]]:
        """
        Normalizes a single word token.
        Priority:
        1. Protected Gaming terms / acronyms (AWP, CS:GO, HP, clutch, one tap).
        2. Roman Hindi spelling normalization (kr -> kar, rha -> raha, bta -> bata).
        3. Standard sentence-start capitalization.
        Returns:
            (normalized_word, was_changed, reason)
        """
        clean_w = word.strip()
        if not clean_w:
            return word, False, None

        # 1. Protected gaming term check
        canonical_game = get_canonical_gaming_term(clean_w)
        if canonical_game is not None:
            if canonical_game != clean_w:
                return canonical_game, True, "gaming_canonical_casing"
            return clean_w, False, None

        # 2. Roman Hindi token spelling normalization
        rh_norm, rh_changed = normalize_roman_hindi_token(clean_w)
        if rh_changed:
            if is_sentence_start and rh_norm:
                rh_norm = rh_norm[0].upper() + rh_norm[1:]
            return rh_norm, True, "roman_hindi_spelling"

        # 3. Sentence-initial capitalization
        if is_sentence_start and clean_w and clean_w[0].islower():
            cap_w = clean_w[0].upper() + clean_w[1:]
            return cap_w, True, "sentence_capitalization"

        return clean_w, False, None

    def normalize_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes a single transcript segment while strictly preserving word timestamps.
        Returns a data contract containing original_text, normalized_text, words, and metadata.
        """
        original_text = str(segment.get("text", "")).strip()
        raw_words = segment.get("words", [])

        # If original text is empty, return empty structure
        if not original_text and not raw_words:
            return {
                "start": segment.get("start", 0.0),
                "end": segment.get("end", 0.0),
                "text": "",
                "original_text": "",
                "normalized_text": "",
                "language": "en",
                "subtitle_mode": self.mode,
                "confidence": 1.0,
                "words": [],
            }

        # 1. Language Detection
        lang_info = detect_language(original_text)
        detected_lang = lang_info["language"]

        # In 'original' mode or if Hindi Unicode is present, preserve unchanged
        if self.mode == "original" or detected_lang == "hindi":
            return {
                "start": segment.get("start", 0.0),
                "end": segment.get("end", 0.0),
                "text": original_text,
                "original_text": original_text,
                "normalized_text": original_text,
                "language": "hi" if detected_lang == "hindi" else "en",
                "subtitle_mode": self.mode,
                "confidence": lang_info["confidence"],
                "words": [
                    {
                        "word": w.get("word", ""),
                        "original": w.get("word", ""),
                        "normalized": w.get("word", ""),
                        "start": w.get("start", 0.0),
                        "end": w.get("end", 0.0),
                    }
                    for w in raw_words
                ],
                "normalization": {"changed": False, "reasons": []},
            }

        # In 'auto' mode: if purely English, do minimal cleanup, do NOT force Hindi rules
        if self.mode == "auto" and detected_lang == "english":
            target_lang_tag = "en"
            is_hinglish_target = False
        else:
            target_lang_tag = "hi-Latn"
            is_hinglish_target = True

        # 2. Token-level and compound phrase normalization
        normalized_words: List[Dict[str, Any]] = []
        reasons: List[str] = []
        substitutions = 0

        # Handle words list
        i = 0
        total_w = len(raw_words)

        while i < total_w:
            curr_w = raw_words[i]
            orig_word = str(curr_w.get("word", "")).strip()
            w_start = float(curr_w.get("start", 0.0))
            w_end = float(curr_w.get("end", 0.0))

            # Prune solitary hesitation filler at sentence beginning
            if i == 0 and orig_word.lower() in HESITATION_FILLERS and total_w > 1:
                substitutions += 1
                reasons.append("pruned_hesitation_filler")
                i += 1
                continue

            # Check 2-token compound contraction if in Hinglish target
            matched_compound = False
            if is_hinglish_target and (i + 1) < total_w:
                next_w = raw_words[i + 1]
                pair_key = (orig_word.lower().strip(".,!?"), str(next_w.get("word", "")).lower().strip(".,!?"))
                if pair_key in MULTI_TOKEN_CONTRACTIONS:
                    replacements = MULTI_TOKEN_CONTRACTIONS[pair_key]
                    is_start = (len(normalized_words) == 0)

                    # Word 1
                    w1_text = replacements[0]
                    if is_start:
                        w1_text = w1_text.capitalize()
                    normalized_words.append({
                        "word": w1_text,
                        "original": orig_word,
                        "normalized": w1_text,
                        "start": w_start,
                        "end": w_end,
                    })

                    # Word 2
                    w2_text = replacements[1]
                    normalized_words.append({
                        "word": w2_text,
                        "original": str(next_w.get("word", "")),
                        "normalized": w2_text,
                        "start": float(next_w.get("start", 0.0)),
                        "end": float(next_w.get("end", 0.0)),
                    })

                    substitutions += 1
                    reasons.append("compound_contraction_normalization")
                    matched_compound = True
                    i += 2
                    continue

            # Single token normalization
            is_sentence_start = (len(normalized_words) == 0)
            norm_word, changed, reason = self.normalize_word(orig_word, is_sentence_start=is_sentence_start)
            if changed and reason:
                substitutions += 1
                if reason not in reasons:
                    reasons.append(reason)

            normalized_words.append({
                "word": norm_word,
                "original": orig_word,
                "normalized": norm_word,
                "start": w_start,
                "end": w_end,
            })
            i += 1

        # Reconstruct normalized string
        normalized_text = " ".join(w["word"] for w in normalized_words)
        if not normalized_text:
            normalized_text = original_text

        # 3. Confidence & Fallback Evaluation
        confidence = self.confidence_evaluator.evaluate_segment_confidence(
            original_words=raw_words,
            normalized_words=normalized_words,
            language_info=lang_info,
            substitutions_made=substitutions,
        )

        # Fallback to original text if confidence drops below safety limit
        if self.confidence_evaluator.should_fallback(confidence):
            return {
                "start": segment.get("start", 0.0),
                "end": segment.get("end", 0.0),
                "text": original_text,
                "original_text": original_text,
                "normalized_text": original_text,
                "language": target_lang_tag,
                "subtitle_mode": self.mode,
                "confidence": confidence,
                "words": [
                    {
                        "word": w.get("word", ""),
                        "original": w.get("word", ""),
                        "normalized": w.get("word", ""),
                        "start": w.get("start", 0.0),
                        "end": w.get("end", 0.0),
                    }
                    for w in raw_words
                ],
                "normalization": {
                    "changed": False,
                    "fallback_applied": True,
                    "reasons": ["confidence_below_threshold_fallback"],
                },
            }

        return {
            "start": segment.get("start", 0.0),
            "end": segment.get("end", 0.0),
            "text": normalized_text,
            "original_text": original_text,
            "normalized_text": normalized_text,
            "language": target_lang_tag,
            "subtitle_mode": self.mode,
            "confidence": confidence,
            "words": normalized_words,
            "normalization": {
                "changed": substitutions > 0,
                "reasons": reasons,
            },
        }

    def normalize_transcript(self, transcript_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes entire transcript, adding normalized Hinglish segments while
        preserving all Whisper source timings and language metadata.
        """
        segments = list(transcript_data.get("segments", []))
        if not segments and transcript_data.get("words"):
            top_words = transcript_data.get("words", [])
            w_text = " ".join(str(w.get("word", "")) for w in top_words)
            w_start = float(top_words[0].get("start", 0.0)) if top_words else 0.0
            w_end = float(top_words[-1].get("end", 0.0)) if top_words else 0.0
            segments = [{
                "start": w_start,
                "end": w_end,
                "text": w_text,
                "words": top_words,
            }]

        normalized_segments: List[Dict[str, Any]] = []

        total_substitutions = 0
        total_segments = len(segments)
        changed_segments = 0

        for seg in segments:
            norm_seg = self.normalize_segment(seg)
            if norm_seg.get("normalization", {}).get("changed", False):
                changed_segments += 1
            normalized_segments.append(norm_seg)

        # Reconstruct flat word list for downstream consumers
        all_words = []
        for s in normalized_segments:
            all_words.extend(s.get("words", []))

        result = dict(transcript_data)
        result["segments"] = normalized_segments
        result["words"] = all_words
        result["subtitle_mode"] = self.mode
        result["hinglish_intelligence"] = {
            "total_segments": total_segments,
            "changed_segments": changed_segments,
            "normalized_ratio": round(changed_segments / max(1, total_segments), 2),
            "version": "phase7d-v1",
        }
        return result
