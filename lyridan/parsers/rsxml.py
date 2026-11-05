"""Rocksmith 2014 arrangement XML reading (beatmap, sections, notes, vocals)."""
from __future__ import annotations

import bisect
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Beatmap:
    beats: List[float]                       # ebeat times (seconds)
    measure_flags: List[bool]                # True when beat starts a measure
    start_beat: float = 0.0
    offset: float = 0.0
    song_length: float = 0.0
    title: str = ""
    artist: str = ""
    arrangement: str = ""
    sections: List[Tuple[float, str]] = field(default_factory=list)
    notes: List[Tuple[float, float, int]] = field(default_factory=list)  # (time, sustain, string)
    ts_events: List[Tuple[float, int, int]] = field(default_factory=list)  # (time, num, den)
    path: str = ""

    # ---- beat/measure helpers -------------------------------------------------
    @property
    def measure_starts(self) -> List[float]:
        ms = [t for t, f in zip(self.beats, self.measure_flags) if f]
        return ms or self.beats[::4]

    def measure_duration(self, index: int = 0) -> float:
        ms = self.measure_starts
        if index + 1 < len(ms):
            return ms[index + 1] - ms[index]
        return 4 * self.beat_interval_at(ms[index] if ms else 0)

    def first_n_measures_end(self, n: int) -> float:
        """Time at which the first ``n`` measures (from the first beat) end."""
        ms = self.measure_starts
        if not ms:
            return self.beats[0] if self.beats else 0.0
        if n < len(ms):
            return ms[n]
        last = ms[-1]
        return last + (n - len(ms) + 1) * self.measure_duration(len(ms) - 1)

    def beat_interval_at(self, t: float) -> float:
        b = self.beats
        if len(b) < 2:
            return 0.5
        i = bisect.bisect_right(b, t) - 1
        i = max(0, min(i, len(b) - 2))
        return b[i + 1] - b[i]

    def denominator_at(self, t: float) -> int:
        den = 4
        for et, _num, d in self.ts_events:
            if et <= t + 1e-6:
                den = d
        return den

    def beat_position(self, t: float) -> float:
        """Fractional beat index of time t (extrapolated outside the map)."""
        b = self.beats
        if not b:
            return t / 0.5
        if len(b) == 1:
            return (t - b[0]) / 0.5
        if t <= b[0]:
            return (t - b[0]) / (b[1] - b[0])
        if t >= b[-1]:
            return len(b) - 1 + (t - b[-1]) / (b[-1] - b[-2])
        i = bisect.bisect_right(b, t) - 1
        return i + (t - b[i]) / (b[i + 1] - b[i])

    def time_at(self, pos: float) -> float:
        b = self.beats
        if not b:
            return pos * 0.5
        if len(b) == 1:
            return b[0] + pos * 0.5
        if pos <= 0:
            return b[0] + pos * (b[1] - b[0])
        if pos >= len(b) - 1:
            return b[-1] + (pos - (len(b) - 1)) * (b[-1] - b[-2])
        i = int(pos)
        return b[i] + (pos - i) * (b[i + 1] - b[i])


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_beatmap(path: str) -> Beatmap:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag == "vocals":
        raise ValueError("This is a vocals XML. Please select an instrument arrangement "
                         "(lead/rhythm/bass) XML that contains the beatmap (<ebeats>).")
    ebeats = root.find("ebeats")
    if ebeats is None or len(ebeats) == 0:
        raise ValueError("No <ebeats> beatmap found in this XML.")
    beats, flags = [], []
    for eb in ebeats.findall("ebeat"):
        beats.append(_f(eb.get("time")))
        m = eb.get("measure")
        flags.append(m is not None and m.strip() not in ("", "-1"))
    order = sorted(range(len(beats)), key=lambda i: beats[i])
    beats = [beats[i] for i in order]
    flags = [flags[i] for i in order]

    bm = Beatmap(beats=beats, measure_flags=flags, path=path)
    bm.start_beat = _f(root.findtext("startBeat"), beats[0] if beats else 0.0)
    bm.offset = _f(root.findtext("offset"), 0.0)
    bm.song_length = _f(root.findtext("songLength"), beats[-1] if beats else 0.0)
    bm.title = (root.findtext("title") or "").strip()
    bm.artist = (root.findtext("artistName") or "").strip()
    bm.arrangement = (root.findtext("arrangement") or "").strip()

    secs = root.find("sections")
    if secs is not None:
        for s in secs.findall("section"):
            bm.sections.append((_f(s.get("startTime")), s.get("name", "")))
    evs = root.find("events")
    if evs is not None:
        for e in evs.findall("event"):
            m = re.match(r"TS:(\d+)/(\d+)", e.get("code", ""))
            if m:
                bm.ts_events.append((_f(e.get("time")), int(m.group(1)), int(m.group(2))))
    bm.ts_events.sort()

    # Notes for preview: take every level, de-duplicate by (time,string)
    seen = set()
    levels = root.find("levels")
    if levels is not None:
        for lvl in levels.findall("level"):
            for n in lvl.iter("note"):
                key = (round(_f(n.get("time")), 3), n.get("string"))
                if key in seen:
                    continue
                seen.add(key)
                bm.notes.append((_f(n.get("time")), _f(n.get("sustain")), int(_f(n.get("string"), 0))))
            for c in lvl.iter("chord"):
                t = _f(c.get("time"))
                key = (round(t, 3), "c")
                if key in seen:
                    continue
                seen.add(key)
                cns = c.findall("chordNote")
                sus = max((_f(cn.get("sustain")) for cn in cns), default=0.0)
                bm.notes.append((t, sus, -1))
    bm.notes.sort()
    return bm


@dataclass
class VocalEntry:
    time: float
    length: float
    lyric: str
    note: int = 0


def parse_vocals(path: str) -> List[VocalEntry]:
    root = ET.parse(path).getroot()
    if root.tag != "vocals":
        raise ValueError("Not a Rocksmith vocals XML.")
    out = []
    for v in root.findall("vocal"):
        out.append(VocalEntry(_f(v.get("time")), _f(v.get("length")), v.get("lyric", ""),
                              int(_f(v.get("note"), 0))))
    return out


def _xml_attr(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&apos;"))


# ---------------------------------------------------------------------------
# Overlap safety. Editor on Fire can crash on lyrics that overlap, so every exported
# file obeys these rules in whole milliseconds (the precision the XML is written in):
#   * no vocal starts before 0:00 (tools that clamp negative times to 0 would pile them up)
#   * each vocal is at least MIN_LEN_MS long
#   * each vocal ends at least MIN_GAP_MS before the next one starts
# MIN_GAP_MS is 2, not 1, so a reader that truncates instead of rounding still can't
# make two vocals touch.
MIN_GAP_MS = 2
MIN_LEN_MS = 1


def _ms(seconds: float) -> int:
    return int(round(seconds * 1000.0))


def vocal_overlaps(entries: List[VocalEntry]) -> List[int]:
    """Indices i where entries[i] breaks the rules above (overlaps / touches entries[i + 1],
    starts before 0, has no length or is out of order). Empty = safe to export."""
    bad = []
    for i, e in enumerate(entries):
        t, ln = _ms(e.time), _ms(e.length)
        if t < 0 or ln < MIN_LEN_MS:
            bad.append(i)
        elif i + 1 < len(entries) and t + ln > _ms(entries[i + 1].time) - MIN_GAP_MS:
            bad.append(i)
    return bad


@dataclass
class OverlapFix:
    entries: List[VocalEntry]
    moved: int = 0          # starts pushed later (before 0:00, or too close to the previous vocal)
    shortened: int = 0      # ends pulled in so they don't reach the next vocal (more than a rounding nudge)
    lengthened: int = 0     # zero-length vocals given a minimal length
    negative: int = 0       # vocals that were before 0:00

    @property
    def changed(self) -> bool:
        return bool(self.moved or self.shortened or self.lengthened)


def fix_vocal_overlaps(entries: List[VocalEntry]) -> OverlapFix:
    """Return a copy of ``entries`` that passes :func:`vocal_overlaps`.

    Vocals are sorted by time; a start that is before 0:00 or too close to the previous one is
    pushed just after it, then every length is clipped to end MIN_GAP_MS before the next start
    (and is at least MIN_LEN_MS). Already-safe input comes back unchanged.
    """
    order = sorted(range(len(entries)), key=lambda i: (entries[i].time, i))
    src = [entries[i] for i in order]
    fix = OverlapFix([])
    starts: List[int] = []
    prev = None
    for e in src:
        t = _ms(e.time)
        if t < 0:
            fix.negative += 1
        lo = 0 if prev is None else prev + MIN_LEN_MS + MIN_GAP_MS
        if t < lo:
            t = lo
            fix.moved += 1
        starts.append(t)
        prev = t
    out = []
    for i, e in enumerate(src):
        t = starts[i]
        want = _ms(e.length)
        ln = want
        if i + 1 < len(src):
            room = starts[i + 1] - MIN_GAP_MS - t          # >= MIN_LEN_MS by construction
            if ln > room:
                if ln - room > MIN_GAP_MS:                  # a real overlap, not a rounding nudge
                    fix.shortened += 1
                ln = room
        if ln < MIN_LEN_MS:
            ln = MIN_LEN_MS
            fix.lengthened += 1
        out.append(VocalEntry(t / 1000.0, ln / 1000.0, e.lyric, e.note))
    fix.entries = out
    return fix


def write_vocals(entries: List[VocalEntry], path: str) -> None:
    """Write a Rocksmith vocals XML in the same layout EOF / DLC Builder read.

    Overlapping or touching vocals are fixed first (see :func:`fix_vocal_overlaps`), so a
    written file can never contain lyrics that overlap."""
    entries = fix_vocal_overlaps(entries).entries
    if vocal_overlaps(entries):                          # cannot happen; never write a broken file
        raise ValueError("Internal error: overlapping vocals left after the overlap fix.")
    lines = ["<?xml version='1.0' encoding='UTF-8'?>", f'<vocals count="{len(entries)}">']
    for e in entries:
        lines.append(f'  <vocal time="{e.time:.3f}" length="{e.length:.3f}" '
                     f'lyric="{_xml_attr(e.lyric)}" note="{e.note}"/>')
    lines.append("</vocals>")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
