"""Additional exports: syllabized text, romanized (enhanced) LRC."""
from __future__ import annotations

from typing import List

from .model import Line


def _ts(t: float, angle: bool = False) -> str:
    t = max(0.0, t)
    m = int(t // 60)
    s = t - m * 60
    body = f"{m:02d}:{s:05.2f}"
    return f"<{body}>" if angle else f"[{body}]"


def syllabized_text(lines: List[Line], syl_sep: str = "-", word_sep: str = " ",
                    timestamps: bool = False) -> str:
    out = []
    for ln in lines:
        text = word_sep.join(w.prefix + syl_sep.join(s.text for s in w.syllables) + w.suffix
                             for w in ln.words)
        out.append((_ts(ln.start) if timestamps else "") + text)
    return "\n".join(out) + "\n"


def lrc(lines: List[Line], enhanced: bool = False, offset: float = 0.0) -> str:
    out = []
    for ln in lines:
        if not enhanced:
            out.append(_ts(ln.start + offset) + " ".join(w.prefix + w.text + w.suffix for w in ln.words))
            continue
        parts = []
        for w in ln.words:
            parts.append(_ts(w.start + offset, True) + w.prefix + w.text + w.suffix)
        out.append(_ts(ln.start + offset) + " ".join(parts) + " " + _ts(ln.end + offset, True))
    return "\n".join(out) + "\n"
