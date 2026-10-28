"""Input file parsers."""
from __future__ import annotations

import os

from ..model import SourceLyrics
from .lrc import parse_lrc
from .ttml import parse_ttml

LYRIC_EXTENSIONS = (".ttml", ".xml", ".json", ".lrc", ".elrc", ".txt")


def read_text(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "cp1251", "shift_jis", "latin-1"):
        try:
            text = raw.decode(enc)
            if enc == "utf-16" and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return text
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_lyrics(path: str) -> SourceLyrics:
    """Load a lyrics file, detecting TTML vs LRC by content (not just extension)."""
    text = read_text(path)
    head = text.lstrip("﻿ \t\r\n")[:2000]
    if head.startswith("{") or "<tt" in head or "<tt " in text[:5000] or head.startswith("<?xml") and "<tt" in text:
        return parse_ttml(text, path)
    if os.path.splitext(path)[1].lower() == ".ttml":
        return parse_ttml(text, path)
    lyr = parse_lrc(text, path)
    if not lyr.lines:
        # plain text without timestamps: one untimed line per text line
        from ..model import SourceLine, SourcePiece
        lines = []
        for l in text.splitlines():
            if l.strip():
                lines.append(SourceLine([SourcePiece(w, None, None) for w in l.split()], None, None))
        lyr.lines = lines
        lyr.timing = "none"
    return lyr
