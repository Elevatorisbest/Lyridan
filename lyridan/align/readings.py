"""Audio-verified Japanese readings.

Song lyrics often use a reading other than the dictionary's (緋 sung "aka", not
"hi"; 宇宙 "sora"; 永遠 "towa"). When the song audio is available, every word
with alternative readings (from MeCab's n-best analyses and Lyridan's list of
known lyric readings) is tried: the whole line is romanized with each reading
and scored against the sung audio with the alignment model. A reading only
replaces the dictionary one when the audio supports it clearly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

from ..lang.japanese import JapaneseOptions, get_japanese, normalize_with_map
from ..lang.kana import is_kanji, kata_to_hira
from ..model import SourceLine, SourceLyrics, SourcePiece
from .aligner import PRE_ROLL_S, POST_ROLL_S, ctc_score, to_model_text

AUTO_MARGIN = 4.0     # log-likelihood a reading must win by to replace the dictionary reading
SUGGEST_MARGIN = 2.5  # ...to be reported as "the audio suggests X - check by ear"
MAX_CANDIDATES = 6    # readings tried per word


@dataclass
class ReadingChange:
    line_index: int
    line_text: str
    surface: str
    old: str          # hiragana
    new: str          # hiragana
    margin: float
    applied: bool = True


_UNVOICE = str.maketrans("ガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポヴ",
                         "カキクケコサシスセソタチツテトハヒフヘホハヒフヘホウ")


def _core(kana: str) -> str:
    """Reading without voicing, っ, ー and doubled vowels - the details the speech
    model cannot reliably hear in singing."""
    k = kana.translate(_UNVOICE).replace("ッ", "").replace("ー", "")
    out = []
    for ch in k:
        if out and ch in "アイウエオ" and out[-1] == ch:
            continue
        out.append(ch)
    return "".join(out)


def _minor_variant(alt: str, default: str) -> bool:
    """Skip variants that differ only in voicing / gemination / vowel length
    (境界 kyoukai-kyougai, 決して kesshite-keshite, 黒 kuro-kok) or that end in っ,
    which only appears inside compounds."""
    return alt.endswith("ッ") or _core(alt) == _core(default) or len(_core(alt)) < 1


def _romaji(text: str, opts: JapaneseOptions) -> str:
    from ..lang.english import get_english
    words, _ = get_japanese().process_line(text, opts, get_english())
    return " ".join("".join(s.text for s in w.syllables) for w in words)


def verify_readings(source: SourceLyrics, em: np.ndarray, spf: float, offset: float, opts: JapaneseOptions,
                    label_index: dict, blank: int,
                    progress: Optional[Callable[[str, float], bool]] = None
                    ) -> Tuple[SourceLyrics, List[ReadingChange]]:
    jp = get_japanese()
    changes: List[ReadingChange] = []
    lines = source.lines
    main_idx = [i for i, l in enumerate(lines) if not l.background and l.start is not None]

    def tokens_of(text: str) -> List[int]:
        return [label_index[c] for c in to_model_text(text) if c in label_index]

    for n, i in enumerate(main_idx):
        ln = lines[i]
        text = ln.text
        if not any(is_kanji(c) for c in text):
            continue
        norm, _ = normalize_with_map(text)
        if "{" in norm or "《" in norm:
            continue  # the user already gave readings
        t0 = ln.start + offset
        nxt = next((lines[j].start for j in main_idx if j > i and lines[j].start > ln.start), None)
        t1 = (nxt + offset) if nxt is not None else t0 + 8.0
        f0 = max(0, int((t0 - PRE_ROLL_S) / spf))
        f1 = min(len(em), int((t1 + POST_ROLL_S) / spf))
        window = em[f0:f1]
        if len(window) < 10:
            continue
        base_text = _romaji(norm, opts)
        base = ctc_score(window, tokens_of(base_text), blank)
        toks = jp.tokenize(norm, [], opts)
        accepted = []   # (start, end, surface, reading_kata, gain)
        for tk in toks:
            if tk.kind != "ja" or tk.forced or not any(is_kanji(c) for c in tk.surface):
                continue
            alts = [r for r in jp.alternative_readings(tk.surface, tk.kana)
                    if not _minor_variant(r, tk.kana)][:MAX_CANDIDATES]
            best_gain, best_r = 0.0, None
            for r in alts:
                cand = norm[:tk.start] + "{" + tk.surface + "|" + kata_to_hira(r) + "}" + norm[tk.end:]
                gain = ctc_score(window, tokens_of(_romaji(cand, opts)), blank) - base
                if gain > best_gain:
                    best_gain, best_r = gain, r
            if best_r is not None and best_gain >= AUTO_MARGIN:
                accepted.append((tk.start, tk.end, tk.surface, tk.kana, best_r, best_gain))
            elif best_r is not None and best_gain >= SUGGEST_MARGIN:
                changes.append(ReadingChange(i, text, tk.surface, kata_to_hira(tk.kana), kata_to_hira(best_r),
                                             round(best_gain, 1), applied=False))
        if accepted:
            # apply from the end so earlier offsets stay valid
            out = norm
            for a, b, surf, old, new, gain in sorted(accepted, reverse=True):
                out = out[:a] + "{" + surf + "|" + kata_to_hira(new) + "}" + out[b:]
            combined = ctc_score(window, tokens_of(_romaji(out, opts)), blank) - base
            if combined < AUTO_MARGIN:     # the changes do not help together: keep only the best one
                a, b, surf, old, new, gain = max(accepted, key=lambda x: x[5])
                out = norm[:a] + "{" + surf + "|" + kata_to_hira(new) + "}" + norm[b:]
                accepted = [(a, b, surf, old, new, gain)]
            for a, b, surf, old, new, gain in accepted:
                changes.append(ReadingChange(i, text, surf, kata_to_hira(old), kata_to_hira(new), round(gain, 1)))
            words = out.split()
            pieces = [SourcePiece(w, None, None) for w in words]
            pieces[0].start = ln.start
            lines[i] = SourceLine(pieces, ln.start, ln.end, ln.background, ln.agent, ln.key, ln.section,
                                  ln.romaji, ln.translation)
        if progress and progress("Checking Japanese readings against the audio…", (n + 1) / len(main_idx)) is False:
            raise InterruptedError("Cancelled")
    return source, changes
