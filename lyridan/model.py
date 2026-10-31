"""Core data model shared by parsers, language engines and exporters.

Source lyrics are parsed into ``SourceLine`` objects made of ``SourcePiece``
objects (the smallest timed text unit of the input file: a TTML <span>,
an enhanced-LRC word, or a whole LRC line).

Language processing turns each SourceLine into a ``Line`` made of ``Word``
objects, each holding one or more timed ``Syllable`` objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SourcePiece:
    """A timed fragment of text from the input file.

    ``joined`` is True when the next piece belongs to the same word
    (no whitespace between them in the source, e.g. Apple's "para" + "dise").
    ``start``/``end`` may be None for untimed pieces (plain LRC lines are
    timed per line only, so their single piece carries the line timing).
    """
    text: str
    start: Optional[float]
    end: Optional[float]
    joined: bool = False


@dataclass
class SourceLine:
    pieces: List[SourcePiece]
    start: Optional[float]
    end: Optional[float]
    background: bool = False        # Apple ttm:role="x-bg"
    agent: str = ""                 # singer id (v1, v2 ...)
    key: str = ""                   # Apple itunes:key (L1, L2 ...)
    section: str = ""               # Verse / Chorus ...
    romaji: Optional[List[SourcePiece]] = None  # Apple transliteration for this line
    translation: str = ""

    @property
    def text(self) -> str:
        out = []
        for i, p in enumerate(self.pieces):
            out.append(p.text)
            if not p.joined and i < len(self.pieces) - 1:
                out.append(" ")
        return "".join(out).strip()


@dataclass
class SourceLyrics:
    lines: List[SourceLine]
    language: str = ""              # declared language (xml:lang) if any
    title: str = ""
    artist: str = ""
    lyric_offset: float = 0.0       # Apple <audio lyricOffset>, seconds
    leading_silence: float = 0.0    # Apple leadingSilence, seconds
    timing: str = "line"            # "syllable", "word" or "line"
    has_romaji: bool = False
    path: str = ""


@dataclass
class Syllable:
    text: str                       # display text (romanized if applicable)
    start: float = 0.0              # seconds on the *source* timeline
    end: float = 0.0
    native: str = ""                # native-script text (kana/kanji/cyrillic)
    cs: int = -1                    # source character span in the line text
    ce: int = -1


@dataclass
class Word:
    syllables: List[Syllable]
    source: str = ""                # original surface text
    lang: str = "en"
    prefix: str = ""                # leading punctuation, e.g. "("
    suffix: str = ""                # trailing punctuation, e.g. ",", "?"
    break_after: bool = False       # user-forced Rocksmith line break after this word

    @property
    def start(self) -> float:
        return self.syllables[0].start

    @property
    def end(self) -> float:
        return self.syllables[-1].end

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.syllables)

    def hyphenated(self, sep: str = "-") -> str:
        return sep.join(s.text for s in self.syllables)


@dataclass
class Line:
    words: List[Word]
    background: bool = False
    agent: str = ""
    section: str = ""
    lang: str = "en"
    source_text: str = ""
    timed: bool = True              # False when timing was estimated (plain LRC)
    manual: bool = False            # edited by the user (no automatic line splitting)
    index: int = -1                 # index of the source line
    warnings: List[str] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.words[0].start if self.words else 0.0

    @property
    def end(self) -> float:
        return self.words[-1].end if self.words else 0.0

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    def syllabized(self, syl_sep: str = "-", word_sep: str = " ") -> str:
        return word_sep.join(w.hyphenated(syl_sep) for w in self.words)

    def syllables(self):
        for w in self.words:
            for s in w.syllables:
                yield s
