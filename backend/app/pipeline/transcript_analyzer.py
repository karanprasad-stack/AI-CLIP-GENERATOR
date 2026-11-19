"""Transcript analysis for lexical excitement, reaction language, speech density, and gaming signals."""

import re
from typing import Dict, Any, List, Tuple, Optional

from backend.app.config import (
    REACTION_PHRASES,
    REACTION_WORDS,
    GAMEPLAY_WORDS,
    LAUGHTER_WORDS,
)


class TranscriptAnalyzer:
    """Analyzes Whisper transcript data for speech density, sentence boundaries, and emotional signals."""

    def __init__(self, transcript_data: Dict[str, Any]):
        self.raw_data = transcript_data
        self.language = transcript_data.get("language", "en")
        self.segments = transcript_data.get("segments", [])
        self.words = self._extract_all_words()
        self.sentences = self._extract_sentences()

    def _extract_all_words(self) -> List[Dict[str, Any]]:
        """Flatten word timestamps across all segments with normalized representations."""
        all_words: List[Dict[str, Any]] = []
        for s in self.segments:
            for w in s.get("words", []):
                raw_word = w.get("word", "").strip()
                clean_word = re.sub(r"[^\w]", "", raw_word).lower()
                all_words.append({
                    "word": raw_word,
                    "clean": clean_word,
                    "start": round(float(w.get("start", 0.0)), 2),
                    "end": round(float(w.get("end", 0.0)), 2),
                })
        return all_words

    def _extract_sentences(self) -> List[Dict[str, Any]]:
        """Group words into sentence units based on punctuation and silence gaps."""
        sentences: List[Dict[str, Any]] = []
        if not self.words:
            for s in self.segments:
                sentences.append({
                    "start": s.get("start", 0.0),
                    "end": s.get("end", 0.0),
                    "text": s.get("text", "").strip(),
                })
            return sentences

        current_words: List[str] = []
        sentence_start = self.words[0]["start"]

        for idx, w in enumerate(self.words):
            word_str = w["word"]
            current_words.append(word_str)

            has_terminator = bool(re.search(r"[.!?]$", word_str))
            has_gap = False
            if idx + 1 < len(self.words):
                gap = self.words[idx + 1]["start"] - w["end"]
                if gap >= 0.55:
                    has_gap = True

            if has_terminator or has_gap or (idx == len(self.words) - 1):
                sentence_end = w["end"]
                sentence_text = " ".join(current_words).strip()
                if sentence_text:
                    sentences.append({
                        "start": sentence_start,
                        "end": sentence_end,
                        "text": sentence_text,
                    })
                current_words = []
                if idx + 1 < len(self.words):
                    sentence_start = self.words[idx + 1]["start"]

        return sentences

    def find_nearest_sentence_start(self, target_time: float, search_window: float = 12.0) -> float:
        """Find the start timestamp of a sentence closest to target_time."""
        if not self.sentences:
            return max(0.0, target_time)

        candidates = [
            s["start"]
            for s in self.sentences
            if abs(s["start"] - target_time) <= search_window
        ]
        if candidates:
            return min(candidates, key=lambda t: abs(t - target_time))

        word_candidates = [
            w["start"]
            for w in self.words
            if abs(w["start"] - target_time) <= search_window
        ]
        if word_candidates:
            return min(word_candidates, key=lambda t: abs(t - target_time))

        return max(0.0, target_time)

    def find_nearest_sentence_end(self, target_time: float, search_window: float = 12.0) -> float:
        """Find the end timestamp of a sentence closest to target_time."""
        if not self.sentences:
            return target_time

        candidates = [
            s["end"]
            for s in self.sentences
            if abs(s["end"] - target_time) <= search_window
        ]
        if candidates:
            return min(candidates, key=lambda t: abs(t - target_time))

        word_candidates = [
            w["end"]
            for w in self.words
            if abs(w["end"] - target_time) <= search_window
        ]
        if word_candidates:
            return min(word_candidates, key=lambda t: abs(t - target_time))

        return target_time

    def get_timestamped_signals(self, start_sec: float, end_sec: float) -> List[Dict[str, Any]]:
        """
        Extracts all timestamped lexical signals (gaming words, reaction words, reaction phrases)
        within the interval [start_sec, end_sec]. Used for temporal clustering analysis.
        """
        words_in_range = [w for w in self.words if start_sec <= w["start"] <= end_sec]
        signals: List[Dict[str, Any]] = []

        # 1. Word-level signals
        for w in words_in_range:
            clean = w["clean"]
            if not clean:
                continue

            if clean in GAMEPLAY_WORDS:
                signals.append({
                    "type": "gaming",
                    "term": clean,
                    "t": w["start"],
                    "weight": 1.5,
                })
            elif clean in REACTION_WORDS:
                signals.append({
                    "type": "reaction_word",
                    "term": clean,
                    "t": w["start"],
                    "weight": 1.0,
                })
            elif clean in LAUGHTER_WORDS or "haha" in clean:
                signals.append({
                    "type": "laughter",
                    "term": clean,
                    "t": w["start"],
                    "weight": 1.2,
                })

        # 2. Multi-word reaction phrases
        full_text = " ".join(w["word"] for w in words_in_range).lower()
        for phrase in REACTION_PHRASES:
            # Find approximate timestamp of phrase
            if phrase in full_text:
                first_word = phrase.split()[0]
                for w in words_in_range:
                    if w["clean"] == first_word:
                        signals.append({
                            "type": "reaction_phrase",
                            "term": phrase,
                            "t": w["start"],
                            "weight": 2.5,
                        })
                        break

        # Sort signals by timestamp
        signals.sort(key=lambda x: x["t"])
        return signals

    def score_interval(
        self,
        start_sec: float,
        end_sec: float
    ) -> Tuple[float, Dict[str, Any], List[str]]:
        """
        Calculates normalized TranscriptExcitementScore (0-100) for a candidate interval [start_sec, end_sec].
        Returns: (score, metrics, reasons)
        """
        duration = max(1.0, end_sec - start_sec)
        words_in_range = [w for w in self.words if start_sec <= w["start"] <= end_sec]

        if not words_in_range:
            segs_in_range = [
                s for s in self.segments
                if not (s["end"] < start_sec or s["start"] > end_sec)
            ]
            full_text = " ".join(s.get("text", "") for s in segs_in_range).strip()
            total_words = len(full_text.split())
        else:
            full_text = " ".join(w["word"] for w in words_in_range).strip()
            total_words = len(words_in_range)

        if total_words == 0:
            return 20.0, {
                "word_count": 0,
                "wps": 0.0,
                "reaction_phrases": 0,
                "gaming_terms": 0,
                "speech_density": 0.0,
            }, ["no speech detected in interval"]

        text_lower = full_text.lower()
        clean_words = [re.sub(r"[^\w]", "", w).lower() for w in text_lower.split() if w]

        # 1. Multi-word reaction phrases (highest signal weight, up to 30 pts)
        matched_phrases: List[str] = []
        phrase_pts = 0.0
        for phrase in REACTION_PHRASES:
            if phrase in text_lower:
                matched_phrases.append(phrase)
                phrase_pts += 10.0
        phrase_pts = min(30.0, phrase_pts)

        # 2. Single reaction/surprise words (up to 20 pts)
        matched_reactions: List[str] = []
        reaction_pts = 0.0
        for word in clean_words:
            if word in REACTION_WORDS:
                matched_reactions.append(word)
                reaction_pts += 3.0
        reaction_pts = min(20.0, reaction_pts)

        # 3. Gaming and action vocabulary (up to 20 pts)
        matched_gaming: List[str] = []
        gaming_pts = 0.0
        for word in clean_words:
            if word in GAMEPLAY_WORDS:
                matched_gaming.append(word)
                gaming_pts += 4.0
        gaming_pts = min(20.0, gaming_pts)

        # 4. Laughter / humor signals (up to 15 pts)
        matched_laughter: List[str] = []
        laughter_pts = 0.0
        for word in clean_words:
            if word in LAUGHTER_WORDS or "haha" in word:
                matched_laughter.append(word)
                laughter_pts += 5.0
        laughter_pts = min(15.0, laughter_pts)

        # 5. Punctuation dynamics: Exclamations and Questions (up to 15 pts)
        exclamation_count = full_text.count("!")
        question_count = full_text.count("?")
        punct_pts = min(15.0, (exclamation_count * 4.0) + (question_count * 2.5))

        # 6. Word repetition (e.g. "wait wait wait", "really really", "no no") (up to 10 pts)
        repeat_count = 0
        for i in range(len(clean_words) - 1):
            if clean_words[i] and clean_words[i] == clean_words[i + 1]:
                repeat_count += 1
        repeat_pts = min(10.0, repeat_count * 4.0)

        # 7. Speech density (Words Per Second and active speech fraction)
        wps = total_words / duration
        # Active speech duration fraction
        active_speech_time = sum(w["end"] - w["start"] for w in words_in_range)
        speech_density = min(1.0, active_speech_time / duration)

        if 2.0 <= wps <= 4.2:
            density_pts = 10.0
        elif 1.0 <= wps < 2.0 or 4.2 < wps <= 5.5:
            density_pts = 6.0
        else:
            density_pts = 3.0

        raw_score = (
            phrase_pts
            + reaction_pts
            + gaming_pts
            + laughter_pts
            + punct_pts
            + repeat_pts
            + density_pts
        )

        base_floor = 35.0
        final_transcript_score = float(min(100.0, max(20.0, base_floor + (raw_score * 0.70))))

        reasons = []
        if matched_phrases:
            reasons.append(f"strong reaction phrases: {', '.join(set(matched_phrases[:2]))}")
        if exclamation_count >= 1:
            reasons.append("expressive speech with exclamation emphasis")
        if matched_reactions:
            reasons.append(f"surprise/reaction language: {', '.join(set(matched_reactions[:3]))}")
        if matched_gaming:
            reasons.append(f"gaming action terminology: {', '.join(set(matched_gaming[:2]))}")
        if matched_laughter:
            reasons.append("humor or laughter signals detected")
        if repeat_count >= 1:
            reasons.append("rapid repeated words indicating urgency or excitement")
        if 2.2 <= wps <= 3.8:
            reasons.append("ideal conversational speech pacing for shorts")

        metrics = {
            "word_count": total_words,
            "wps": round(wps, 2),
            "speech_density": round(speech_density, 2),
            "reaction_phrases": len(matched_phrases),
            "reaction_words": len(matched_reactions),
            "gaming_terms": len(matched_gaming),
            "exclamation_count": exclamation_count,
            "question_count": question_count,
            "phrase_matches": matched_phrases,
            "gaming_matches": matched_gaming,
        }

        return round(final_transcript_score, 1), metrics, reasons
