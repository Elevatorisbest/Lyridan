"""LRC parser: standard line-synced LRC and enhanced (A2 / word-timed) LRC.

Supported syntax:
  [mm:ss.xx]text                 line timing (also [mm:ss], [mm:ss:xx], [h:mm:ss.xx])
  [00:01.00][00:30.00]text       repeated lines
  [00:12.00]<00:12.00>I <00:12.40>love <00:12.90>you <00:13.50>
  [00:12.00]I <00:12.40>love <00:12.90>you <00:13.50>
  <00:12.00>pa<00:12.20>ra<00:12.40>dise   (no space -> pieces of one word)
  [offset:+120]                  global offset in ms (positive = lyrics earlier)
  [ti:], [ar:], [al:] ...        metadata
  "v1:", "M:", "F:", "D:" duet prefixes are stripped (kept as agent)
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..model import SourceLine, SourceLyrics, SourcePiece

TIME_TAG = re.compile(r"\[(\d+):(\d{1,2})(?:[.:](\d{1,3}))?\]|\[(\d+):(\d{1,2}):(\d{1,2})[.:](\d{1,3})\]")
LINE_TAG = re.compile(r"^\s*((?:\[\d+:\d{1,2}(?::\d{1,2})?(?:[.:]\d{1,3})?\]\s*)+)(.*)$")
WORD_TAG = re.compile(r"<(\d+):(\d{1,2})(?:[.:](\d{1,3}))?>")
META_TAG = re.compile(r"^\s*\[([a-zA-Z#]+):(.*)\]\s*$")
AGENT_PREFIX = re.compile(r"^\s*(v\d+|[MFD]|[MFD]\d*)\s*:\s*", re.IGNORECASE)


def _frac(s: Optional[str]) -> float:
    if not s:
        return 0.0
    return int(s) / (10 ** len(s))


def _parse_tag_time(tag: str) -> Optional[float]:
    inner = tag.strip("[]<>")
    parts = re.split(r":", inner)
    try:
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        if len(parts) == 3:
            a, b, c = parts
            # mm:ss:xx (centiseconds) vs h:mm:ss.xx
            if "." in c:
                return int(a) * 3600 + int(b) * 60 + float(c)
            if len(c) <= 2 and int(b) < 60:
                return int(a) * 60 + int(b) + _frac(c)
            return int(a) * 3600 + int(b) * 60 + float(c)
    except ValueError:
        return None
    return None


def _split_enhanced(text: str, line_start: float) -> Tuple[List[SourcePiece], bool]:
    """Split a line body containing <mm:ss.xx> word tags into timed pieces."""
    tags = list(WORD_TAG.finditer(text))
    if not tags:
        return [], False
    pieces: List[SourcePiece] = []
    # Text before first tag is timed from line start
    segments = []  # (time, text)
    first = text[: tags[0].start()]
    if first.strip():
        segments.append((line_start, first))
    for i, m in enumerate(tags):
        t = _parse_tag_time(m.group(0))
        nxt = tags[i + 1].start() if i + 1 < len(tags) else len(text)
        segments.append((t, text[m.end():nxt]))
    # Each segment: text until next tag. Its end = next segment's time.
    for i, (t, seg) in enumerate(segments):
        end = segments[i + 1][0] if i + 1 < len(segments) else None
        if not seg.strip():
            if pieces:
                pieces[-1].joined = False
                if pieces[-1].end is None:
                    pieces[-1].end = t
            continue
        lead = seg[:1].isspace()
        if lead and pieces:
            pieces[-1].joined = False
        words = seg.split()
        if len(words) == 1:
            pieces.append(SourcePiece(words[0], t, end, joined=not seg[-1:].isspace()))
        else:
            total = sum(len(w) for w in words) or 1
            cur = t
            for w in words:
                d = ((end - t) * len(w) / total) if end is not None and t is not None else None
                pieces.append(SourcePiece(w, cur, (cur + d) if d is not None else None, joined=False))
                if d is not None:
                    cur += d
            pieces[-1].joined = not seg[-1:].isspace()
    if pieces:
        pieces[-1].joined = False
    return pieces, True


def parse_lrc(content: str, path: str = "") -> SourceLyrics:
    content = content.lstrip("﻿")
    offset_ms = 0.0
    title = artist = ""
    entries = []  # (time, body, order)
    order = 0
    for raw in content.splitlines():
        meta = META_TAG.match(raw)
        if meta and not re.match(r"^\d", meta.group(1)):
            key, val = meta.group(1).lower(), meta.group(2).strip()
            if key == "offset":
                try:
                    offset_ms = float(val)
                except ValueError:
                    pass
            elif key == "ti":
                title = val
            elif key == "ar":
                artist = val
            continue
        m = LINE_TAG.match(raw)
        if not m:
            continue
        times = [_parse_tag_time(t.group(0)) for t in re.finditer(r"\[[^\]]+\]", m.group(1))]
        body = m.group(2)
        for t in times:
            if t is not None:
                entries.append((t, body, order))
                order += 1
    entries.sort(key=lambda e: (e[0], e[2]))
    shift = -offset_ms / 1000.0

    lines: List[SourceLine] = []
    any_enhanced = False
    any_joined = False
    for idx, (raw_t, body, _) in enumerate(entries):
        t = raw_t + shift
        next_t = None
        for j in range(idx + 1, len(entries)):
            if entries[j][0] + shift > t:
                next_t = entries[j][0] + shift
                break
        agent = ""
        am = AGENT_PREFIX.match(body)
        if am and len(body) > am.end():
            agent = am.group(1)
            body = body[am.end():]
        if not WORD_TAG.sub("", body).strip():
            continue  # blank line: just an end marker
        pieces, enhanced = _split_enhanced(body, raw_t)
        if enhanced:
            any_enhanced = True
            # word tags are absolute times: apply offset too
            for p in pieces:
                if p.start is not None:
                    p.start = p.start + shift
                if p.end is not None:
                    p.end = p.end + shift
            if pieces and pieces[-1].end is None:
                pieces[-1].end = next_t
            any_joined = any_joined or any(p.joined for p in pieces)
            end = pieces[-1].end if pieces else next_t
            lines.append(SourceLine(pieces, t, end, agent=agent))
        else:
            words = body.split()
            pieces = [SourcePiece(w, None, None) for w in words]
            if pieces:
                pieces[0].start = t
            lines.append(SourceLine(pieces, t, next_t, agent=agent))
    timing = "syllable" if any_joined else ("word" if any_enhanced else "line")
    return SourceLyrics(lines=lines, timing=timing, path=path, title=title, artist=artist)
