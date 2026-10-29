"""English syllabification.

Resolution order for every word:
  1. user dictionary (editable in the app, stored in the user's settings folder)
  2. built-in lyric overrides (slang / interjections / sung contractions)
  3. curated syllable dictionary (~47.7k polysyllabic words, karaoke style:
     onset-maximising, e.g. "li-ving", "ma-gic", "eve-ry", "dif-fe-rent")
  4. CMU Pronouncing Dictionary syllable count + trained boundary model
     (same style as the dictionary, ~95% exact on unseen dictionary words)
  5. boundary model alone (words unknown to every dictionary)
"""
from __future__ import annotations

import gzip
import os
import re
import threading
from typing import Dict, List, Optional, Set

from .hyphen_model import VOWELS, BoundaryModel

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Words the dictionary lacks or splits differently from how they are sung.
BUILTIN_OVERRIDES: Dict[str, str] = {
    "c'mon": "c'-mon",
    "cmon": "c-mon",
    "y'all": "y'all",
    "ma'am": "ma'am",
    "o'clock": "o'-clock",
    "rock'n'roll": "rock'n'-roll",
    "ooh": "ooh", "oh": "oh", "ah": "ah", "uh": "uh", "mm": "mm", "hmm": "hmm",
    "yeah": "yeah", "yea": "yea", "whoa": "whoa", "woah": "woah", "hey": "hey",
    "la": "la", "na": "na", "da": "da", "doo": "doo", "ba": "ba",
    "uh-huh": "uh-huh", "oh-oh": "oh-oh",
    "gonna": "gon-na", "wanna": "wan-na", "gotta": "got-ta", "outta": "out-ta",
    "kinda": "kin-da", "sorta": "sor-ta", "lotta": "lot-ta", "dunno": "dun-no",
    "lemme": "lem-me", "gimme": "gim-me", "betcha": "bet-cha", "gotcha": "got-cha",
    "whatcha": "what-cha", "wontcha": "wont-cha", "dontcha": "dont-cha",
    "tryna": "try-na", "imma": "im-ma", "ain't": "ain't", "'cause": "'cause",
    "cuz": "cuz", "'til": "'til", "til": "til", "'em": "'em", "ya": "ya",
    "baby": "ba-by", "babe": "babe",
    "everybody": "eve-ry-bo-dy", "everyone": "eve-ry-one", "everything": "eve-ry-thing",
    "everywhere": "eve-ry-where", "every": "eve-ry",
    "hour": "hour", "hours": "hours", "our": "our",
}


def _boundaries_from_hyphenated(h: str) -> List[int]:
    cuts, pos = [], 0
    for ch in h:
        if ch in "-•":
            cuts.append(pos)
        else:
            pos += 1
    return cuts


class EnglishSyllabifier:
    _lock = threading.Lock()

    def __init__(self, user_dict: Optional[Dict[str, str]] = None):
        self.user: Dict[str, List[int]] = {}
        self.dict: Dict[str, List[int]] = {}
        self._cmu: Optional[Dict[str, Set[int]]] = None
        self.model: Optional[BoundaryModel] = None
        self._load()
        if user_dict:
            self.set_user_dict(user_dict)

    def _load(self):
        path = os.path.join(DATA_DIR, "english_syllables.txt")
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                s = line.strip().lower()
                if s and "." not in s:
                    plain = s.replace("•", "")
                    self.dict[plain] = _boundaries_from_hyphenated(s)
        for w, h in BUILTIN_OVERRIDES.items():
            self.dict[w] = _boundaries_from_hyphenated(h)
        self.model = BoundaryModel.load(os.path.join(DATA_DIR, "english_model.json.gz"))

    def set_user_dict(self, entries: Dict[str, str]):
        self.user = {}
        for k, v in entries.items():
            key = k.strip().lower()
            val = v.strip().lower()
            if key and val.replace("-", "").replace("•", "") == key:
                self.user[key] = _boundaries_from_hyphenated(val)

    @property
    def cmu(self) -> Dict[str, Set[int]]:
        if self._cmu is None:
            with self._lock:
                if self._cmu is None:
                    d: Dict[str, Set[int]] = {}
                    try:
                        with gzip.open(os.path.join(DATA_DIR, "cmu_syllables.txt.gz"), "rt",
                                       encoding="utf-8") as fh:
                            for line in fh:
                                w, _, counts = line.rstrip("\n").partition("\t")
                                d[w] = {int(c) for c in counts.split(",") if c}
                    except OSError:
                        pass
                    self._cmu = d
        return self._cmu

    # ------------------------------------------------------------------
    def is_known(self, word: str) -> bool:
        """Is this an English word (curated dictionary or CMU Pronouncing Dictionary)?"""
        w = re.sub(r"[^a-z']", "", word.lower())
        return bool(w) and (w in self.user or w in self.dict or w in self.cmu)

    def boundaries(self, core: str) -> List[int]:
        """Boundary indices for a word core (letters/apostrophes only)."""
        low = core.lower()
        if len(low) <= 2:
            return []
        if low in self.user:
            return list(self.user[low])
        if low in self.dict:
            return list(self.dict[low])
        # Elongated words ("ooooh", "loooove"): collapse runs of 3+ letters
        collapsed, mapping = self._collapse(low)
        if collapsed != low:
            cuts = self.boundaries(collapsed)
            return [mapping[c] for c in cuts]
        if not any(c in VOWELS for c in low):
            return []
        # Contractions (there'll, you're, we've, I'd ...) never add a syllable
        m = re.match(r"^(.+?)('ll|'re|'ve|'d|'s|'m)$", low)
        if m and "'" not in m.group(1):
            return self.boundaries(m.group(1))
        # Possessive / plural of a known word: keep the base split
        for suf in ("'s", "s'", "s", "es", "'d", "'ll", "'re", "'ve"):
            base = low[: -len(suf)]
            if low.endswith(suf) and base in self.dict and len(base) > 2:
                if suf == "es" and not re.search(r"(s|x|z|ch|sh)$", base):
                    continue
                return list(self.dict[base])
        counts = self.cmu.get(low)
        if counts is None and low.endswith("in'"):
            counts = self.cmu.get(low[:-1] + "g")
        if counts is None and "'" in low:
            counts = self.cmu.get(low.replace("'", ""))
        if counts == {1}:
            return []
        return self.model.decode(low, counts)

    @staticmethod
    def _collapse(word: str):
        out, mapping = [], {}
        i = 0
        while i < len(word):
            j = i
            while j < len(word) and word[j] == word[i]:
                j += 1
            run = j - i
            keep = 2 if run >= 3 and word[i] in VOWELS else (1 if run >= 3 else run)
            for k in range(keep):
                out.append(word[i])
            # boundary before collapsed index len(out) maps to original j
            mapping[len(out)] = j
            # boundaries inside a kept run map 1:1
            for k in range(1, keep):
                mapping[len(out) - keep + k] = i + k
            i = j
        return "".join(out), mapping

    def syllabize(self, word: str) -> List[str]:
        """Split a word (may include surrounding punctuation) into syllables.

        Punctuation stays attached to the first/last syllable.
        """
        m = re.match(r"^([^\w']*)([\w']*?)([^\w']*)$", word, re.UNICODE)
        if not m or not m.group(2):
            return [word]
        pre, core, post = m.groups()
        if any(ch.isdigit() for ch in core):
            return [word]
        inner = core.strip("'")
        lead = len(core) - len(core.lstrip("'"))
        cuts = [c + lead for c in self.boundaries(inner)] if inner else []
        parts, last = [], 0
        for c in cuts:
            if 0 < c < len(core):
                parts.append(core[last:c])
                last = c
        parts.append(core[last:])
        parts = [p for p in parts if p]
        parts[0] = pre + parts[0]
        parts[-1] = parts[-1] + post
        return parts


_instance: Optional[EnglishSyllabifier] = None


def get_english() -> EnglishSyllabifier:
    global _instance
    if _instance is None:
        _instance = EnglishSyllabifier()
    return _instance
