"""Advanced SubStation Alpha (.ass) generator with Shorts-style karaoke highlighting."""

from pathlib import Path
from typing import List, Dict, Any, Optional

from backend.app.config import (
    CAPTION_FONT_NAME,
    CAPTION_FONT_SIZE,
    CAPTION_BASE_COLOR,
    CAPTION_ACTIVE_COLOR,
    CAPTION_OUTLINE_COLOR,
    CAPTION_SHADOW_COLOR,
    CAPTION_OUTLINE_WIDTH,
    CAPTION_SHADOW_DEPTH,
    CAPTION_ALIGNMENT,
    CAPTION_MARGIN_V,
    EMOJI_FONT_NAME,
    EMOJI_FONT_SIZE,
    EMOJI_MARGIN_V,
)
from backend.app.pipeline.caption_engine import CaptionGroup


def format_ass_timestamp(seconds: float) -> str:
    """Converts a timestamp in seconds to ASS H:MM:SS.cs format."""
    total_sec = max(0.0, float(seconds))
    hrs = int(total_sec // 3600)
    mins = int((total_sec % 3600) // 60)
    secs = int(total_sec % 60)
    centis = int(round((total_sec - int(total_sec)) * 100))
    if centis >= 100:
        secs += 1
        centis = 0
    if secs >= 60:
        mins += 1
        secs = 0
    if mins >= 60:
        hrs += 1
        mins = 0
    return f"{hrs:d}:{mins:02d}:{secs:02d}.{centis:02d}"


def escape_ass_text(text: str) -> str:
    """Escapes curly braces and special characters for ASS safety."""
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


class AssGenerator:
    """Generates valid ASS files with karaoke active-word highlighting and emoji overlays."""

    def __init__(
        self,
        font_name: str = CAPTION_FONT_NAME,
        font_size: int = CAPTION_FONT_SIZE,
        base_color: str = CAPTION_BASE_COLOR,
        active_color: str = CAPTION_ACTIVE_COLOR,
        outline_color: str = CAPTION_OUTLINE_COLOR,
        shadow_color: str = CAPTION_SHADOW_COLOR,
        outline_width: int = CAPTION_OUTLINE_WIDTH,
        shadow_depth: int = CAPTION_SHADOW_DEPTH,
        margin_v: int = CAPTION_MARGIN_V,
        emoji_font_name: str = EMOJI_FONT_NAME,
        emoji_font_size: int = EMOJI_FONT_SIZE,
        emoji_margin_v: int = EMOJI_MARGIN_V,
    ):
        self.font_name = font_name
        self.font_size = font_size
        self.base_color = base_color
        self.active_color = active_color
        self.outline_color = outline_color
        self.shadow_color = shadow_color
        self.outline_width = outline_width
        self.shadow_depth = shadow_depth
        self.margin_v = margin_v

        self.emoji_font_name = emoji_font_name
        self.emoji_font_size = emoji_font_size
        self.emoji_margin_v = emoji_margin_v

    def build_header(self) -> str:
        """Constructs [Script Info] and [V4+ Styles] headers targeting 1080x1920."""
        return f"""[Script Info]
Title: AI Gaming Shorts Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{self.font_name},{self.font_size},{self.base_color},&H000000FF&,{self.outline_color},{self.shadow_color},-1,0,0,0,100,100,0,0,1,{self.outline_width},{self.shadow_depth},{CAPTION_ALIGNMENT},40,40,{self.margin_v},1
Style: Emoji,{self.emoji_font_name},{self.emoji_font_size},&H00FFFFFF&,&H000000FF&,&H00000000&,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,{CAPTION_ALIGNMENT},40,40,{self.emoji_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def generate_events(
        self,
        caption_groups: List[CaptionGroup],
        emoji_events: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        Builds karaoke dialogue events highlighting each word in turn,
        plus contextual animated emoji events.
        """
        dialogue_lines: List[str] = []

        # 1. Caption Karaoke Dialogue Events
        for group in caption_groups:
            words = group.words
            if not words:
                continue

            num_words = len(words)

            # Each word in the group highlights sequentially; subtitles start
            # at the exact millisecond the first spoken word begins.
            for i, active_word in enumerate(words):
                w_start = words[i].start
                # The word stays active until the next word begins or group ends
                if i < num_words - 1:
                    w_end = words[i + 1].start
                else:
                    w_end = group.end

                if w_end <= w_start:
                    w_end = w_start + 0.10

                t_start = format_ass_timestamp(w_start)
                t_end = format_ass_timestamp(w_end)

                # Assemble karaoke text with active word emphasized
                word_parts: List[str] = []
                for j, w in enumerate(words):
                    clean_w = escape_ass_text(w.text)
                    if j == i:
                        # Highlight active word with gold color & subtle 108% scale pop
                        word_parts.append(
                            f"{{\\c{self.active_color}\\fscx108\\fscy108}}{clean_w}{{\\c{self.base_color}\\fscx100\\fscy100}}"
                        )
                    else:
                        word_parts.append(clean_w)

                karaoke_line = " ".join(word_parts)
                dialogue_lines.append(
                    f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{karaoke_line}"
                )

        # 2. Contextual Emoji Dialogue Events
        if emoji_events:
            for ev in emoji_events:
                e_start = format_ass_timestamp(ev["start"])
                e_end = format_ass_timestamp(ev["end"])
                emoji_char = ev.get("emoji", "")
                if not emoji_char:
                    continue

                # Pop-in bounce animation with gentle fade
                anim_tag = r"{\fad(100,100)\t(0,120,\fscx120\fscy120)\t(120,240,\fscx100\fscy100)}"
                dialogue_lines.append(
                    f"Dialogue: 1,{e_start},{e_end},Emoji,,0,0,0,,{anim_tag}{emoji_char}"
                )

        return dialogue_lines

    def generate_ass(
        self,
        caption_groups: List[CaptionGroup],
        emoji_events: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Returns the full valid ASS subtitle script as a string."""
        header = self.build_header()
        events = self.generate_events(caption_groups, emoji_events)
        return header + "\n".join(events) + "\n"

    def write_ass_file(
        self,
        output_path: Path,
        caption_groups: List[CaptionGroup],
        emoji_events: Optional[List[Dict[str, Any]]] = None,
    ) -> Path:
        """Writes the generated ASS content to output_path using UTF-8 encoding."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = self.generate_ass(caption_groups, emoji_events)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return output_path
