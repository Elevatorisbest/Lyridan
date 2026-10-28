"""Rocksmith vocals export: offsets, beat-grid snapping, line breaking, lyric markup.

Rocksmith vocal markup:
  "syl-"  syllable continues the same word (no space after it)
  "syl+"  last syllable of a displayed lyric line (line break after it)
  "syl"   end of a word (space after it)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .model import Line, Word
from .parsers.rsxml import Beatmap, VocalEntry
from .settings import Settings

GRID_VALUES = {"1/4": 4, "1/8": 8, "1/12": 12, "1/16": 16, "1/24": 24, "1/32": 32, "1/64": 64}


@dataclass
class OffsetInfo:
    total: float
    parts: List[Tuple[str, float]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def compute_offset(settings: Settings, beatmap: Optional[Beatmap], lyric_offset: float = 0.0,
                   leading_silence: float = 0.0) -> OffsetInfo:
    info = OffsetInfo(0.0)
    if settings.intro_silence:
        info.parts.append((f"{settings.intro_silence_seconds:g} s intro silence", settings.intro_silence_seconds))
    if settings.two_empty_bars:
        if beatmap and beatmap.beats:
            ms = beatmap.measure_starts
            n = max(0, int(settings.empty_bars))
            dur = beatmap.first_n_measures_end(n) - (ms[0] if ms else beatmap.beats[0])
            info.parts.append((f"{n} empty bars (from beatmap)", dur))
        else:
            info.warnings.append("Empty-bars shift needs a beatmap XML - not applied.")
    if settings.apply_lyric_offset and lyric_offset:
        info.parts.append(("TTML lyricOffset", lyric_offset))
    if settings.apply_leading_silence and leading_silence:
        info.parts.append(("TTML leadingSilence", -leading_silence))
    if settings.manual_offset_ms:
        info.parts.append(("manual offset", settings.manual_offset_ms / 1000.0))
    info.total = sum(v for _, v in info.parts)
    return info


class Grid:
    """Snaps times to a subdivision of the beatmap (or passes them through)."""

    def __init__(self, beatmap: Optional[Beatmap], snap: str, min_gap: str):
        self.bm = beatmap if beatmap and len(beatmap.beats) >= 2 else None
        self.snap_den = GRID_VALUES.get(snap)
        self.gap_den = GRID_VALUES.get(min_gap)

    def _subdiv(self, t: float, den: Optional[int]) -> Optional[float]:
        if not den or not self.bm:
            return None
        ts_den = self.bm.denominator_at(t)
        return den / ts_den  # grid points per beat

    def snap(self, t: float) -> float:
        sub = self._subdiv(t, self.snap_den)
        if not sub:
            return round(t, 3)
        pos = self.bm.beat_position(t)
        return round(self.bm.time_at(round(pos * sub) / sub), 3)

    def step_after(self, t: float) -> float:
        """Next grid point strictly after t."""
        sub = self._subdiv(t, self.snap_den)
        if not sub:
            return round(t + 0.05, 3)
        pos = self.bm.beat_position(t)
        n = int(pos * sub + 0.5)
        while True:
            cand = round(self.bm.time_at(n / sub), 3)
            if cand > t + 1e-4:
                return cand
            n += 1

    def gap_at(self, t: float) -> float:
        sub = self._subdiv(t, self.gap_den)
        if not sub:
            return 0.0 if not self.gap_den else 0.06
        return self.bm.beat_interval_at(t) / sub


# ---------------------------------------------------------------------------
_RS_SAFE_MAP = {"’": "'", "‘": "'", "‚": "'", "´": "'", "`": "'", "“": "\"", "”": "\"", "„": "\"",
                "…": "...", "–": "-", "—": "-", " ": " "}


def rs_clean(text: str, ascii_only: bool) -> str:
    t = "".join(_RS_SAFE_MAP.get(c, c) for c in text)
    if ascii_only:
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if not unicodedata.combining(c))
        t = t.replace("ß", "ss").replace("æ", "ae").replace("œ", "oe").replace("ʹ", "'").replace("ʺ", "\"")
        t = "".join(c for c in t if ord(c) < 128)
    return t


def word_display(word: Word, settings: Settings) -> List[str]:
    """Clean syllable texts for display: punctuation filtered, quotes dropped."""
    keep = set(settings.keep_punctuation or "")
    out = []
    n = len(word.syllables)
    for i, s in enumerate(word.syllables):
        t = s.text
        t = t.replace("\"", "")
        # strip hyphens a source piece may carry ("ooh-")
        t = t.strip("-‐‑–—")
        if i == n - 1:
            suf = "".join(c for c in word.suffix if c in keep)
            t = t + suf
        out.append(t)
    # remove stray punctuation inside syllables except apostrophes and kept marks
    cleaned = []
    for t in out:
        t = re.sub(r"[\"“”«»()\[\]{}<>,.;:]", "", t) if t not in ("...",) else t
        cleaned.append(t)
    return cleaned


@dataclass
class RSLine:
    words: List[Word]
    texts: List[List[str]]

    def display_len(self) -> int:
        return sum(len("".join(t)) for t in self.texts) + max(0, len(self.texts) - 1)


def split_lines(lines: List[Line], settings: Settings, native_cjk: bool = False) -> List[RSLine]:
    out: List[RSLine] = []
    for ln in lines:
        words = [w for w in ln.words if w.syllables]
        texts = [word_display(w, settings) for w in words]
        pairs = [(w, t) for w, t in zip(words, texts) if "".join(t).strip()]
        if not pairs:
            continue
        words = [p[0] for p in pairs]
        texts = [p[1] for p in pairs]
        if ln.manual:
            # user-edited line: only the breaks the user asked for
            cw, ct = [], []
            for w, t in zip(words, texts):
                cw.append(w)
                ct.append(t)
                if w.break_after:
                    out.append(RSLine(cw, ct))
                    cw, ct = [], []
            if cw:
                out.append(RSLine(cw, ct))
            continue
        # 1) split at big timing gaps
        chunks: List[Tuple[List[Word], List[List[str]]]] = []
        cw, ct = [words[0]], [texts[0]]
        for w, t in zip(words[1:], texts[1:]):
            if w.start - cw[-1].end >= settings.gap_split_seconds:
                chunks.append((cw, ct))
                cw, ct = [], []
            cw.append(w)
            ct.append(t)
        chunks.append((cw, ct))
        # 2) split chunks that are too long
        for cw, ct in chunks:
            for part in _split_long(cw, ct, settings.max_line_chars, native_cjk):
                out.append(RSLine(*part))
    return out


def _len(texts: List[List[str]], cjk: bool) -> int:
    if cjk:
        return sum(len("".join(t)) * 2 for t in texts)
    return sum(len("".join(t)) for t in texts) + max(0, len(texts) - 1)


# Words that bind to the following word: avoid ending a line with them.
_BIND_RIGHT = set("""a an the my your his her its our their this that's to of in on at for from with by
and or but nor so if as than because i i'm i'll i've i'd we we're we'll they they're he she it's
you're you'll won't don't can't is are was were be will would could should can just very no""".split())
# Words that naturally start a phrase: slight bonus for starting a line with them.
_PHRASE_START = set("""and but so or that to as when while if in on for with because cause till until
where who what how why then""".split())


def _plain(w: Word) -> str:
    return re.sub(r"[^\w']", "", w.text).lower()


def _split_long(words: List[Word], texts: List[List[str]], max_chars: int, cjk: bool):
    if max_chars <= 0 or _len(texts, cjk) <= max_chars or len(words) < 2:
        return [(words, texts)]
    total = _len(texts, cjk)
    best_i, best_score = None, None
    for i in range(1, len(words)):
        left, right = _len(texts[:i], cjk), _len(texts[i:], cjk)
        score = -abs(left - right) / max(1, total) * 2.0
        gap = words[i].start - words[i - 1].end
        score += min(gap, 1.0) * 3.0
        if left >= right:
            score += 0.02
        if words[i - 1].suffix and re.search(r"[,.;:!?、。！？]", words[i - 1].suffix):
            score += 1.2
        if i < 2 or len(words) - i < 2:
            score -= 0.6
        if not cjk:
            if _plain(words[i - 1]) in _BIND_RIGHT:
                score -= 0.5
            if _plain(words[i]) in _PHRASE_START:
                score += 0.2
        if left > max_chars or right > max_chars:
            score -= 0.3
        if best_score is None or score > best_score:
            best_i, best_score = i, score
    i = best_i
    return (_split_long(words[:i], texts[:i], max_chars, cjk) +
            _split_long(words[i:], texts[i:], max_chars, cjk))


# ---------------------------------------------------------------------------
@dataclass
class ExportResult:
    entries: List[VocalEntry]
    offset: OffsetInfo
    warnings: List[str]
    lines: List[RSLine]


def build_vocals(lines: List[Line], settings: Settings, beatmap: Optional[Beatmap],
                 lyric_offset: float = 0.0, leading_silence: float = 0.0,
                 native: bool = False) -> ExportResult:
    off = compute_offset(settings, beatmap, lyric_offset, leading_silence)
    warnings = list(off.warnings)
    grid = Grid(beatmap, settings.snap, settings.min_gap)

    main = [l for l in lines if not l.background]
    bg = [l for l in lines if l.background]
    if settings.background == "nonoverlap" and bg:
        occupied = [(l.start, l.end) for l in main]
        for b in bg:
            if all(b.end <= s - 0.05 or b.start >= e + 0.05 for s, e in occupied):
                main.append(b)
                occupied.append((b.start, b.end))
        main.sort(key=lambda l: l.start)

    cjk = native and any(l.lang == "ja" for l in main)
    rs_lines = split_lines(main, settings, native_cjk=cjk)

    # flatten into events
    events = []  # [start, end, text, joiner]
    for li, rl in enumerate(rs_lines):
        nwords = len(rl.words)
        for wi, (w, texts) in enumerate(zip(rl.words, rl.texts)):
            for si, (s, t) in enumerate(zip(w.syllables, texts)):
                if not t:
                    continue
                last_syl = si == len(w.syllables) - 1 or not any(texts[si + 1:])
                last_word = wi == nwords - 1
                if last_syl and last_word:
                    joiner = "+"
                elif last_syl:
                    nxt = rl.words[wi + 1]
                    joiner = "-" if (native and w.lang == "ja" and nxt.lang == "ja") else ""
                else:
                    joiner = "-"
                events.append([s.start + off.total, s.end + off.total, t, joiner])
    if not events:
        return ExportResult([], off, warnings + ["No lyrics to export."], rs_lines)

    # capitalise first letter of each displayed line
    if settings.capitalize_lines:
        start_of_line = True
        for ev in events:
            if start_of_line:
                ev[2] = _cap_first(ev[2])
            start_of_line = ev[3] == "+"

    # snap starts, keep strictly increasing
    starts = []
    prev = None
    for ev in events:
        t = grid.snap(ev[0])
        if prev is not None and t <= prev + 1e-4:
            t = grid.step_after(prev)
        starts.append(t)
        prev = t
    entries: List[VocalEntry] = []
    for i, ev in enumerate(events):
        st = starts[i]
        en = grid.snap(ev[1]) if grid.snap_den else round(ev[1], 3)
        if i + 1 < len(events):
            limit = starts[i + 1] - grid.gap_at(starts[i + 1])
            en = min(en, limit)
        min_len = grid.gap_at(st) or 0.05
        if en - st < min_len:
            room = (starts[i + 1] - grid.gap_at(starts[i + 1]) - st) if i + 1 < len(events) else min_len
            en = st + max(0.0, min(min_len, room))
        text = rs_clean(ev[2], settings.ascii_only and not native) + ev[3]
        entries.append(VocalEntry(round(st, 3), round(max(0.0, en - st), 3), text, settings.note_value))

    # charting guideline checks
    first = entries[0].time
    if settings.intro_silence and first < settings.intro_silence_seconds:
        warnings.append(f"First lyric at {first:.3f}s is inside the {settings.intro_silence_seconds:g} s intro silence.")
    if beatmap and beatmap.beats and settings.two_empty_bars:
        bars_end = beatmap.first_n_measures_end(settings.empty_bars)
        if first < bars_end - 1e-3:
            warnings.append(f"First lyric at {first:.3f}s is inside the first {settings.empty_bars} bars "
                            f"(they end at {bars_end:.3f}s).")
    if beatmap and beatmap.song_length and entries[-1].time > beatmap.song_length:
        warnings.append("Some lyrics are after the end of the song (songLength) - check the offset.")
    long_lines = [l for l in rs_lines if l.display_len() > settings.max_line_chars + 8]
    if long_lines and settings.max_line_chars > 0:
        warnings.append(f"{len(long_lines)} line(s) are still longer than {settings.max_line_chars} characters.")
    return ExportResult(entries, off, warnings, rs_lines)


def _cap_first(t: str) -> str:
    for i, c in enumerate(t):
        if c.isalpha():
            return t[:i] + c.upper() + t[i + 1:]
    return t
