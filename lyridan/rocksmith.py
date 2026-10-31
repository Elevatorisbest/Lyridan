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
_RS_SAFE_MAP = {"’": "'", "‘": "'", "‚": "'", "´": "'", "“": "\"", "”": "\"", "„": "\"",
                "…": "...", "–": "-", "—": "-", " ": " "}


def rs_clean(text: str, ascii_only: bool, backticks_to_apostrophes: bool = True) -> str:
    t = "".join(_RS_SAFE_MAP.get(c, c) for c in text)
    if backticks_to_apostrophes:
        t = t.replace("`", "'")      # Editor on Fire crashes on ` in an imported vocals XML
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
        # 1) split at real pauses - but never into a fragment that a charter would
        #    rejoin by hand ("Ya" / "zhdu otveta" after a held note), and never
        #    right after a word that belongs to the next phrase ("ne" / "mogu")
        chunks: List[Tuple[List[Word], List[List[str]]]] = []
        cw, ct = [words[0]], [texts[0]]
        for i in range(1, len(words)):
            w, t = words[i], texts[i]
            gap = w.start - cw[-1].end
            if gap >= settings.gap_split_seconds and _gap_split_ok(cw, ct, words[i:], texts[i:], gap,
                                                                   native_cjk):
                chunks.append((cw, ct))
                cw, ct = [], []
            cw.append(w)
            ct.append(t)
        chunks.append((cw, ct))
        # 2) split chunks that are too long
        max_syl = settings.max_line_syllables
        if max_syl > 0 and ln.lang == "ja":
            max_syl += 4    # Japanese morae are short; 8 would chop every phrase
        for cw, ct in chunks:
            for part in _split_long(cw, ct, settings.max_line_chars, native_cjk, max_syl):
                out.append(RSLine(*part))
    return out


def _len(texts: List[List[str]], cjk: bool) -> int:
    if cjk:
        return sum(len("".join(t)) * 2 for t in texts)
    return sum(len("".join(t)) for t in texts) + max(0, len(texts) - 1)


# ---- phrase rules per language ------------------------------------------------
# Words that belong to the *next* word: a line should not end with them.
_BIND_RIGHT = {
    "en": set("""a an the my your his her its our their this that's to of in on at for from with by
and or but nor so if as than because i i'm i'll i've i'd we we're we'll they they're he she it's
you're you'll won't don't can't is are was were be will would could should can just very no""".split()),
    # Russian (Cyrillic source, ё written as е): prepositions, conjunctions, negation, subject pronouns
    "ru": set("""в во на за с со к ко по о об обо из от до у про при без для над под через перед между
сквозь из-за из-под около вокруг после среди и а но или да что чтобы как где куда когда если хотя
ни не я ты он она оно мы вы они мой моя мое мои твой твоя твое твои наш наша наше наши этот эта это
эти тот та те весь вся все самый очень так""".split()),
    "ja": set(),
}
# Words that belong to the *previous* word: a line should not start with them.
_BIND_LEFT = {
    "en": set("""'s n't 're 've 'll 'd""".split()),
    "ru": set("ли же ж бы б".split()),
    # Japanese particles / copula written as separate romaji words
    "ja": set("""は が の を に で と も へ か よ ね な や から まで より って わ ぞ ぜ さ だ です でしょう
じゃ wa ga no o wo ni de to mo e ka yo ne na ya kara made yori tte da desu""".split()),
}
# Words that naturally start a phrase: slight bonus for starting a line with them.
_PHRASE_START = {
    "en": set("""and but so or that to as when while if in on for with because cause till until
where who what how why then""".split()),
    "ru": set("""и а но или что чтобы как где куда когда если хотя пока потому зато ведь""".split()),
    "ja": set(),
}


def _key(w: Word) -> Tuple[str, str]:
    """(language, normalised word) - Russian/Japanese use the native spelling."""
    lang = w.lang if w.lang in _BIND_RIGHT else "en"
    base = w.source if (lang in ("ru", "ja") and w.source) else w.text
    base = re.sub(r"[^\w'\-]", "", base.lower()).replace("ё", "е").strip("-")
    return lang, base


def _binds_right(w: Word) -> bool:
    lang, k = _key(w)
    return k in _BIND_RIGHT[lang] and not re.search(r"[,.;:!?、。！？]", w.suffix or "")


def _binds_left(w: Word) -> bool:
    lang, k = _key(w)
    return k in _BIND_LEFT[lang] or _key_text(w) in _BIND_LEFT[lang]


def _key_text(w: Word) -> str:
    return re.sub(r"[^\w']", "", w.text).lower()


def _starts_phrase(w: Word) -> bool:
    lang, k = _key(w)
    return k in _PHRASE_START[lang]


def _gap_split_ok(lw, lt, rw, rt, gap: float, cjk: bool) -> bool:
    """Is a pause a good place for a new Rocksmith line?

    A short breath should not leave a tiny line ("Ya" / "No vprochem"): both halves
    need about 5 sung syllables, a longer pause (>= 1.5 s) accepts 3, and a pause of
    3 s or more always starts a new line.
    """
    if gap >= 3.0:                      # clearly separate phrases
        return True
    need = 3 if gap >= 1.5 else 5
    if cjk:
        need += 2
    if _syl(lt) < need or _syl(rt) < need:
        return False
    return not _binds_right(lw[-1]) and not _binds_left(rw[0])


def _syl(texts: List[List[str]]) -> int:
    """Sung syllables (Rocksmith notes) in a group of words."""
    return sum(1 for t in texts for x in t if x.strip())


def _too_long(texts, max_chars: int, max_syl: int, cjk: bool) -> bool:
    return (max_syl > 0 and _syl(texts) > max_syl) or (max_chars > 0 and _len(texts, cjk) > max_chars)


def _split_long(words: List[Word], texts: List[List[str]], max_chars: int, cjk: bool, max_syl: int = 0):
    """Split a phrase that is too long for one Rocksmith line.

    Charters keep a line to about 7-8 sung syllables. All ways of breaking the
    phrase are compared at once (dynamic programming) and the cheapest wins:
      * each line costs 1 (fewer lines are better when they fit),
      * a line 1-2 syllables over the limit costs a little, more costs a lot,
      * a line under 5 syllables costs more the shorter it is ("Ya" / "No vprochem"),
      * breaking after punctuation or at a pause is rewarded, breaking between words
        that belong together (preposition + noun, "ne" + verb, particles) is penalised.
    """
    n = len(words)
    if n < 2 or not _too_long(texts, max_chars, max_syl, cjk):
        return [(words, texts)]
    syl = [_syl([t]) for t in texts]
    limit = max_syl if max_syl > 0 else 10 ** 6
    ideal = min(7, limit) if max_syl > 0 else None
    short = 5 if not cjk else 6

    def line_cost(i: int, j: int) -> float:
        sy = sum(syl[i:j])
        c = 1.0
        over = sy - limit
        if over > 0:
            c += 0.8 * over if over <= 2 else 1.6 + 3.0 * (over - 2)
        if sy < short and not (i == 0 and j == n):
            c += 1.0 * (short - sy)
        if ideal is not None:
            c += 0.1 * abs(sy - ideal)
        if max_chars > 0:
            ln = _len(texts[i:j], cjk)
            if ln > max_chars:
                c += ((ln - max_chars) / 5.0) ** 2
        return c

    def break_cost(i: int) -> float:  # break between words[i-1] and words[i]
        c = 0.0
        if words[i - 1].suffix and re.search(r"[,.;:!?、。！？]", words[i - 1].suffix):
            c -= 1.2
        c -= min(max(0.0, words[i].start - words[i - 1].end), 1.0) * 3.0
        if _binds_right(words[i - 1]):
            c += 1.5          # "...in the" / "heat of..." - worse than a short line
        if _binds_left(words[i]):
            c += 1.5
        if _starts_phrase(words[i]):
            c -= 0.2
        return c

    INF = float("inf")
    best = [INF] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0
    for j in range(1, n + 1):
        for i in range(j):
            if best[i] == INF:
                continue
            c = best[i] + line_cost(i, j) + (break_cost(i) if i > 0 else 0.0)
            # tie-break: prefer the longer first line (ends phrases on stronger words)
            if c < best[j] - 1e-9 or (abs(c - best[j]) <= 1e-9 and i > back[j]):
                best[j], back[j] = c, i
    cuts = []
    j = n
    while j > 0:
        cuts.append(back[j])
        j = back[j]
    cuts = sorted(c for c in cuts if c > 0)
    out, last = [], 0
    for c in cuts + [n]:
        out.append((words[last:c], texts[last:c]))
        last = c
    return out


# ---------------------------------------------------------------------------
@dataclass
class ExportResult:
    entries: List[VocalEntry]
    offset: OffsetInfo
    warnings: List[str]
    lines: List[RSLine]
    entry_line: List[int] = field(default_factory=list)   # source line index of every entry


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
    word_line = {id(w): ln.index for ln in main for w in ln.words}
    events = []  # [start, end, text, joiner]
    entry_line: List[int] = []
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
                entry_line.append(word_line.get(id(w), -1))
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
        text = rs_clean(ev[2], settings.ascii_only and not native, settings.backtick_to_apostrophe) + ev[3]
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
    if settings.max_line_syllables > 0:
        lim = settings.max_line_syllables
        long_lines = [l for l in rs_lines if _syl(l.texts) > lim + (4 if l.words and l.words[0].lang == "ja" else 0) + 2]
        if long_lines:
            warnings.append(f"{len(long_lines)} line(s) still have more than {lim + 2} syllables - "
                            f"consider splitting them by hand.")
    return ExportResult(entries, off, warnings, rs_lines, entry_line)


def _cap_first(t: str) -> str:
    for i, c in enumerate(t):
        if c.isalpha():
            return t[:i] + c.upper() + t[i + 1:]
    return t
