"""Turns parsed source lyrics into syllabized, romanized, timed lines."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .lang import russian
from .lang.english import get_english
from .lang.japanese import get_japanese, looks_like_romaji, resolve_native
from .lang.kana import is_japanese_char
from .model import Line, SourceLine, SourceLyrics, SourcePiece, Syllable, Word
from .settings import Settings

LANG_NAMES = {"en": "English", "ja": "Japanese", "ru": "Russian", "ja_romaji": "Japanese (romaji)"}
HYPHENS = "-‐‑‒–—"
_PUNCT_STRIP = re.compile(r"^([^\w']*)(.*?)([^\w']*)$", re.UNICODE)


@dataclass
class Processed:
    lines: List[Line]
    language: str
    warnings: List[str] = field(default_factory=list)
    source: Optional[SourceLyrics] = None


def detect_language(text: str) -> str:
    ja = sum(1 for c in text if is_japanese_char(c))
    ru = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    if ja and ja >= ru:
        return "ja"
    if ru and ru >= lat * 0.3:
        return "ru"
    return "en"


def build_text(pieces: List[SourcePiece]) -> Tuple[str, List[int]]:
    text, owner = [], []
    for i, p in enumerate(pieces):
        text.append(p.text)
        owner.extend([i] * len(p.text))
        if not p.joined and i < len(pieces) - 1:
            text.append(" ")
            owner.append(-1)
    return "".join(text), owner


# ---------------------------------------------------------------------------
def _split_tokens(text: str, split_hyphen: bool) -> List[Tuple[int, int]]:
    """Whitespace tokens (and hyphen-separated parts) as (start, end) offsets."""
    out = []
    for m in re.finditer(r"\S+", text):
        s, e = m.start(), m.end()
        if not split_hyphen:
            out.append((s, e))
            continue
        tok = text[s:e]
        last = 0
        for hm in re.finditer(f"[{HYPHENS}]+", tok):
            # only split between letters (keeps "-" prefixes like "-ing" intact)
            left = tok[:hm.start()]
            right = tok[hm.end():]
            if re.search(r"\w$", left) and re.search(r"^\w", right):
                out.append((s + last, s + hm.start()))
                last = hm.end()
        out.append((s + last, e))
    return [(a, b) for a, b in out if b > a]


def _merge_piece_bounds(core_start: int, core: str, cuts: List[int], owner: List[int]) -> List[int]:
    """Make syllable cuts respect boundaries between source pieces (e.g. Apple 'para|dise')."""
    piece_cuts = []
    for i in range(1, len(core)):
        a, b = owner[core_start + i - 1], owner[core_start + i]
        if a != b and a >= 0 and b >= 0:
            piece_cuts.append(i)
    if not piece_cuts:
        return cuts
    final = set(piece_cuts)
    for c in cuts:
        if all(abs(c - p) > 1 for p in piece_cuts):
            final.add(c)
    return sorted(final)


def process_alpha_line(text: str, owner: List[int], settings: Settings, lang_hint: str,
                       native_script: bool) -> List[Word]:
    eng = get_english()
    jp = get_japanese()
    words: List[Word] = []
    for s, e in _split_tokens(text, settings.split_hyphenated):
        tok = text[s:e]
        m = _PUNCT_STRIP.match(tok)
        pre, core, post = m.groups() if m else ("", tok, "")
        if not core:
            if words:
                words[-1].suffix += tok
            continue
        cs = s + len(pre)
        is_cyr = bool(russian.CYR.search(core))
        if is_cyr:
            word_text = russian.restore_yo(core) if settings.ru_restore_yo else core
            cyr_parts = russian.syllabize(word_text, settings.ru_syllables)
            cuts, pos = [], 0
            for p in cyr_parts[:-1]:
                pos += len(p)
                cuts.append(pos)
            cuts = _merge_piece_bounds(cs, core, cuts, owner)
            chars = russian.translit_chars(word_text, settings.ru_scheme, settings.ru_soft_sign)
            sylls, last = [], 0
            for c in cuts + [len(core)]:
                native = word_text[last:c]
                latin = "".join(chars[last:c])
                shown = native if (native_script or not settings.romanize) else latin
                sylls.append(Syllable(shown, native=native, cs=cs + last, ce=cs + c))
                last = c
            words.append(Word(sylls, source=core, lang="ru", prefix=pre, suffix=post))
            continue
        if lang_hint == "ja_romaji" and (looks_like_romaji(core) or not eng.is_known(core)):
            # romaji, unless it is clearly an English word ("stars", "broken", "the")
            parts = jp.syllabize_romaji_word(core, settings.ja.syllables)
            lang = "ja"
        else:
            parts = eng.syllabize(core)
            lang = "en"
        cuts, pos = [], 0
        for p in parts[:-1]:
            pos += len(p)
            cuts.append(pos)
        cuts = _merge_piece_bounds(cs, core, cuts, owner)
        sylls, last = [], 0
        for c in cuts + [len(core)]:
            seg = core[last:c]
            sylls.append(Syllable(seg, native=seg, cs=cs + last, ce=cs + c))
            last = c
        words.append(Word(sylls, source=core, lang=lang, prefix=pre, suffix=post))
    return words


# ---------------------------------------------------------------------------
def assign_timing(words: List[Word], owner: List[int], pieces: List[SourcePiece],
                  line_start: Optional[float], line_end: Optional[float], settings: Settings) -> bool:
    """Give every syllable start/end seconds. Returns True if timing came from the source."""
    sylls = [s for w in words for s in w.syllables]
    if not sylls:
        return True
    fully_timed = all(p.start is not None and p.end is not None for p in pieces)

    def weight(s: Syllable) -> float:
        if settings.syllable_weighting == "letters":
            return max(1.0, float(len(re.sub(r"\W", "", s.text))))
        return 1.0

    if fully_timed:
        def piece_of(s: Syllable) -> int:
            for k in range(max(0, s.cs), min(len(owner), max(s.ce, s.cs + 1))):
                if owner[k] >= 0:
                    return owner[k]
            # nearest owned char
            for d in range(1, len(owner)):
                for k in (s.cs - d, s.cs + d):
                    if 0 <= k < len(owner) and owner[k] >= 0:
                        return owner[k]
            return 0

        def last_piece_of(s: Syllable) -> int:
            for k in range(min(len(owner), max(s.ce, s.cs + 1)) - 1, max(0, s.cs) - 1, -1):
                if owner[k] >= 0:
                    return owner[k]
            return piece_of(s)

        groups = {}
        order = []
        for s in sylls:
            pi = piece_of(s)
            if pi not in groups:
                groups[pi] = []
                order.append(pi)
            groups[pi].append(s)
        for pi in order:
            p = pieces[pi]
            grp = groups[pi]
            total = sum(weight(s) for s in grp)
            t = p.start
            dur = max(0.0, p.end - p.start)
            for s in grp:
                d = dur * weight(s) / total
                s.start, s.end = t, t + d
                t += d
        # syllables spanning several pieces end with their last piece
        for s in sylls:
            lp = last_piece_of(s)
            fp = piece_of(s)
            if lp != fp and len(groups.get(lp, [])) == 0:
                s.end = max(s.end, pieces[lp].end)
        # keep monotonic order
        for a, b in zip(sylls, sylls[1:]):
            if b.start < a.start:
                b.start = a.start
            if a.end > b.start and b.start > a.start:
                a.end = b.start
        return True

    # Line-level timing only: spread syllables over the sung part of the line
    start = line_start if line_start is not None else (pieces[0].start or 0.0)
    total_w = sum(weight(s) for s in sylls)
    natural = len(sylls) * settings.max_syllable_seconds
    if line_end is not None and line_end > start:
        span = min(line_end - start - 0.05, natural)
        span = max(span, min(line_end - start, 0.12 * len(sylls)))
    else:
        span = natural
    t = start
    for s in sylls:
        d = span * weight(s) / total_w
        s.start, s.end = t, t + d
        t += d
    return False


# ---------------------------------------------------------------------------
def process(source: SourceLyrics, settings: Settings, native_script: bool = False,
            overrides: Optional[dict] = None) -> Processed:
    """Process all lines. ``overrides`` maps source line index -> edited syllable text."""
    jp = get_japanese()
    eng = get_english()
    if settings.en_user_dict:
        eng.set_user_dict(settings.en_user_dict)
    ja_opts = settings.ja
    lines: List[Line] = []
    warnings: List[str] = []

    if settings.language != "auto":
        doc_lang = settings.language
    else:
        sample = " ".join(l.text for l in source.lines[:200])
        doc_lang = detect_language(sample)

    for li, sl in enumerate(source.lines):
        if sl.background and settings.background == "exclude":
            continue
        line_lang = doc_lang if settings.language != "auto" else detect_language(sl.text)
        if line_lang in ("ja_romaji", "en", "ru") and detect_language(sl.text) == "ja":
            line_lang = "ja"          # Japanese script is always read as Japanese
        pieces = sl.pieces
        use_romaji = (line_lang == "ja" and not native_script and settings.romanize and
                      settings.use_source_romaji and sl.romaji)
        if use_romaji:
            pieces = sl.romaji
        text, owner = build_text(pieces)
        warns: List[str] = []
        if line_lang == "ja" and not use_romaji:
            words, warns = jp.process_line(text, ja_opts, eng)
            resolve_native(words, text)
            if native_script or not settings.romanize:
                for w in words:
                    if w.lang == "ja":
                        for s in w.syllables:
                            s.text = s.native
                        w.syllables = _merge_empty(w.syllables)
        else:
            hint = "ja_romaji" if (use_romaji or line_lang == "ja_romaji") else line_lang
            words = process_alpha_line(text, owner, settings, hint, native_script)
            if native_script:
                for w in words:
                    for s in w.syllables:
                        s.text = s.native or s.text
        words = [w for w in words if w.syllables and any(s.text for s in w.syllables)]
        if not words:
            continue
        timed = assign_timing(words, owner, pieces, sl.start, sl.end, settings)
        ln = Line(words, background=sl.background, agent=sl.agent, section=sl.section,
                  lang="ja" if line_lang in ("ja", "ja_romaji") else line_lang,
                  source_text=sl.text, timed=timed, warnings=warns, index=li)
        lines.append(ln)
        warnings.extend(warns)
    if overrides:
        for i, ln in enumerate(lines):
            txt = overrides.get(ln.index)
            if txt is not None and txt.strip():
                lines[i] = apply_override(ln, txt)
    lines.sort(key=lambda l: l.start)
    if source.timing in ("line", "none"):
        warnings.insert(0, "This file only has line timing - syllable times inside each line are estimated.")
    return Processed(lines=lines, language=doc_lang, warnings=_dedupe(warnings), source=source)


def _merge_empty(sylls: List[Syllable]) -> List[Syllable]:
    out: List[Syllable] = []
    for s in sylls:
        if not s.text and out:
            out[-1].end = max(out[-1].end, s.end)
            out[-1].ce = max(out[-1].ce, s.ce)
            continue
        out.append(s)
    return [s for s in out if s.text] or sylls[:1]


def _dedupe(items: List[str]) -> List[str]:
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def format_line(line: Line, syl_sep: str = "-") -> str:
    """Editable text form of a line: words by spaces, syllables by '-', ' / ' = forced break."""
    parts = []
    for w in line.words:
        parts.append(w.prefix + syl_sep.join(s.text for s in w.syllables) + w.suffix)
        if w.break_after and w is not line.words[-1]:
            parts.append("/")
    return " ".join(parts)


def apply_override(line: Line, text: str) -> Line:
    """Rebuild a line from user-edited text, keeping the timing of the original.

    Letters of the new text are aligned with the old letters; each new syllable
    starts at the time of its first letter.
    """
    import difflib
    old_chars: List[str] = []
    old_times: List[float] = []
    for s in line.syllables():
        letters = [c for c in s.text if c.isalnum()] or ["_"]
        n = len(letters)
        for k, c in enumerate(letters):
            old_chars.append(c.lower())
            old_times.append(s.start + (s.end - s.start) * k / n)
    line_start, line_end = line.start, line.end

    # parse the edited text
    new_words: List[Tuple[str, List[str], str, bool]] = []  # prefix, syllables, suffix, break_after
    for si, seg in enumerate(text.split("/")):
        toks = seg.split()
        for ti, tok in enumerate(toks):
            m = _PUNCT_STRIP.match(tok)
            pre, core, post = m.groups() if m else ("", tok, "")
            if not core:
                if new_words:
                    p, sy, su, b = new_words[-1]
                    new_words[-1] = (p, sy, su + tok, b)
                continue
            sylls = [x for x in core.split("-") if x] or [core]
            new_words.append((pre, sylls, post, False))
        if new_words and si < len(text.split("/")) - 1:
            p, sy, su, _ = new_words[-1]
            new_words[-1] = (p, sy, su, True)
    if not new_words:
        return line

    new_chars: List[str] = []
    syl_first_char: List[int] = []
    for _, sylls, _, _ in new_words:
        for sy in sylls:
            syl_first_char.append(len(new_chars))
            letters = [c.lower() for c in sy if c.isalnum()] or ["_"]
            new_chars.extend(letters)
    mapping: List[Optional[float]] = [None] * len(new_chars)
    sm = difflib.SequenceMatcher(a=old_chars, b=new_chars, autojunk=False)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            mapping[b + k] = old_times[a + k]
    # interpolate unmatched letters by relative position
    total = max(1, len(new_chars))
    for i in range(len(mapping)):
        if mapping[i] is None:
            prev_i = next((j for j in range(i - 1, -1, -1) if mapping[j] is not None), None)
            next_i = next((j for j in range(i + 1, len(mapping)) if mapping[j] is not None), None)
            if prev_i is not None and next_i is not None:
                t0, t1 = mapping[prev_i], mapping[next_i]
                mapping[i] = t0 + (t1 - t0) * (i - prev_i) / (next_i - prev_i)
            elif prev_i is not None:
                mapping[i] = mapping[prev_i] + (line_end - mapping[prev_i]) * (i - prev_i) / (total - prev_i)
            elif next_i is not None:
                mapping[i] = line_start + (mapping[next_i] - line_start) * i / max(1, next_i)
            else:
                mapping[i] = line_start + (line_end - line_start) * i / total
    # monotonic
    for i in range(1, len(mapping)):
        if mapping[i] < mapping[i - 1]:
            mapping[i] = mapping[i - 1]

    old_sylls = list(line.syllables())
    words: List[Word] = []
    si = 0
    starts = [mapping[c] for c in syl_first_char]
    for pre, sylls, post, brk in new_words:
        out = []
        for sy in sylls:
            st = starts[si]
            if si + 1 < len(starts):
                en = starts[si + 1]
                # keep original pauses: end no later than old syllable end containing the letter
            else:
                en = line_end
            out.append(Syllable(sy, st, max(st, en), native=sy))
            si += 1
        words.append(Word(out, source="".join(sylls), lang=line.lang, prefix=pre, suffix=post, break_after=brk))
    # restore pauses: a syllable ends where the old syllable holding its last letter ended
    flat = [s for w in words for s in w.syllables]
    last_chars = [c - 1 for c in syl_first_char[1:]] + [len(new_chars) - 1]
    for i, s in enumerate(flat):
        t_last = mapping[last_chars[i]]
        holder = None
        for os_ in old_sylls:
            if os_.start - 1e-6 <= t_last:
                holder = os_
        if holder is not None:
            if i + 1 < len(flat):
                s.end = max(s.start, min(s.end, max(holder.end, t_last)))
            else:
                s.end = max(s.end, holder.end) if holder.end > s.start else s.end
    return Line(words, background=line.background, agent=line.agent, section=line.section,
                lang=line.lang, source_text=line.source_text, timed=line.timed,
                warnings=line.warnings, manual=True, index=line.index)
