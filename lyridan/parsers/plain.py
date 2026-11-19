"""Plain-text lyrics (a hand-written .txt): no timestamps at all.

Every non-empty line becomes one lyric line. Understood extras:
  [Chorus], [Verse 2: Name], "Chorus:"   section headers (not sung)
  ... (x2)  /  ... x3  /  ... [x2]       repeat the line N times
  (backing vocals)                       parenthesised parts become background lines, like in .lrc
  "You might also like", "123Embed"      junk often pasted along with lyrics from websites

The lines get a rough sequential estimate (so the timeline is usable before aligning);
``timing = "none"`` tells the audio aligner to ignore those times and find every line by listening.
"""
from __future__ import annotations

import re
from typing import List

from ..model import SourceLine, SourceLyrics, SourcePiece
from .lrc import AGENT_PREFIX, _split_background

SECTION_BRACKET = re.compile(r"^\s*[\[{<]\s*([^\]}>]*?)\s*[\]}>]\s*$")
SECTION_WORDS = ("intro", "verse", "pre-chorus", "prechorus", "pre chorus", "chorus", "post-chorus", "hook",
                 "bridge", "outro", "refrain", "interlude", "breakdown", "instrumental", "solo", "coda", "drop")
SECTION_COLON = re.compile(r"^\s*(" + "|".join(re.escape(w) for w in SECTION_WORDS) + r")\b[^:]{0,24}:\s*$",
                           re.IGNORECASE)
REPEAT = re.compile(r"(?:^|\s)[\(\[]?\s*(?:[x×]\s*(\d{1,2})|(\d{1,2})\s*[x×])\s*[\)\]]?\s*$", re.IGNORECASE)
META = re.compile(r"^\s*\[(ti|ar|al|au|by|re|ve|length|offset|#)\s*:.*\]\s*$", re.IGNORECASE)
JUNK = re.compile(r"^\s*(you might also like|\d*\s*embed|see .{1,60} live|get tickets as low as .*)\s*$",
                  re.IGNORECASE)
TRAILING_EMBED = re.compile(r"\d*Embed\s*$")

EST_SYLLABLE_S = 0.3      # rough estimate before aligning: seconds per vowel group
EST_GAP_S = 0.8           # ...and between lines


def _estimate(text: str) -> float:
    groups = len(re.findall(r"[aeiouyаеёиоуыэюяàâäéèêëîïôöùûü]+|[^\W\d_a-zA-ZЀ-ӿ]", text.lower()))
    return max(1.0, groups * EST_SYLLABLE_S)


def looks_untimed(text: str) -> bool:
    """True when nothing in the text looks like an LRC time tag."""
    return not re.search(r"[\[<]\d+:\d{1,2}", text)


def parse_plain(content: str, path: str = "", split_background: bool = True) -> SourceLyrics:
    content = content.lstrip("﻿")
    lines: List[SourceLine] = []
    section = ""
    t = 0.0
    last: List[SourceLine] = []          # the lines added for the previous lyric line (for a lone "x2")

    def add(main: str, bgs: List[str], agent: str) -> List[SourceLine]:
        nonlocal t
        added: List[SourceLine] = []
        start = t
        end = t + _estimate(main or " ".join(bgs))
        if main:
            pieces = [SourcePiece(w, None, None) for w in main.split()]
            pieces[0].start = start
            added.append(SourceLine(pieces, start, end, agent=agent, section=section))
        for bg in bgs:
            pieces = [SourcePiece(w, None, None) for w in f"({bg})".split()]
            pieces[0].start = start
            added.append(SourceLine(pieces, start, end, background=True, agent=agent, section=section))
        t = end + EST_GAP_S
        lines.extend(added)
        return added

    for raw in content.splitlines():
        if not raw.strip() or JUNK.match(raw) or META.match(raw):
            continue
        rm = REPEAT.search(raw)
        if rm and not raw[:rm.start()].strip(" \t([{"):
            # a repeat mark on its own line: sing the previous line again
            n = int(rm.group(1) or rm.group(2))
            for _ in range(max(0, min(16, n) - 1)):
                if last:
                    main = " ".join(p.text for p in last[0].pieces) if not last[0].background else ""
                    bgs = [" ".join(p.text for p in l.pieces).strip("()") for l in last if l.background]
                    add(main, bgs, last[0].agent)
            continue
        m = SECTION_BRACKET.match(raw)
        if m:
            section = m.group(1).split(":")[0].strip()
            continue
        if SECTION_COLON.match(raw):
            section = raw.strip().rstrip(":").strip()
            continue
        body = TRAILING_EMBED.sub("", raw).strip()
        times = 1
        rm = REPEAT.search(body)
        if rm and rm.start() > 0:
            times = max(1, min(16, int(rm.group(1) or rm.group(2))))
            body = body[:rm.start()].strip()
        agent = ""
        am = AGENT_PREFIX.match(body)
        if am and len(body) > am.end():
            agent = am.group(1)
            body = body[am.end():]
        main, bgs = _split_background(body) if split_background else (body, [])
        if not main and not bgs:
            continue
        for _ in range(times):
            last = add(main, bgs, agent)
    return SourceLyrics(lines=lines, timing="none", path=path)
