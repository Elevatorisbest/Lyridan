"""Russian: ё restoration, syllabification and latinization.

Syllables are split on the Cyrillic spelling (Russian orthography is close to
phonemic, so every vowel letter is exactly one syllable), then each syllable is
transliterated with the context of the whole word, so standards with
context-dependent rules (е -> ye after vowels, -ий -> -y ...) stay correct.
"""
from __future__ import annotations

import gzip
import os
import re
from typing import Dict, List, Optional, Set, Tuple

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

VOWELS = set("аеёиоуыэюяАЕЁИОУЫЭЮЯ")
SONORANTS = set("рлмнРЛМН")
SIGNS = set("ьъЬЪ")
CYR = re.compile(r"[А-Яа-яЁё]")

# --------------------------------------------------------------------------
# ё restoration
_yo: Optional[Dict[str, str]] = None


def _yo_dict() -> Dict[str, str]:
    global _yo
    if _yo is None:
        d = {}
        try:
            with gzip.open(os.path.join(DATA_DIR, "ru_yo.txt.gz"), "rt", encoding="utf-8") as fh:
                for line in fh:
                    w = line.strip()
                    if w:
                        d[w.replace("ё", "е")] = w
        except OSError:
            pass
        _yo = d
    return _yo


def restore_yo(word: str) -> str:
    """Restore ё in a word when it is unambiguous (идет -> идёт, еще -> ещё)."""
    if "е" not in word.lower() or "ё" in word.lower():
        return word
    low = word.lower()
    target = _yo_dict().get(low)
    if not target:
        return word
    out = []
    for o, t in zip(word, target):
        out.append(("Ё" if o.isupper() else "ё") if t == "ё" else o)
    return "".join(out)


# --------------------------------------------------------------------------
# syllabification
def syllable_cuts(word: str, style: str = "phonetic") -> List[int]:
    """Boundary positions inside ``word`` (letters only).

    style "phonetic": open syllables (ко-шка, се-стра), a sonorant before another
        consonant closes the syllable (кар-та, сол-нце), й always closes (май-ка),
        doubled consonants split (ван-на), ь/ъ stay with their consonant.
    style "closed": every consonant but the last stays left (кош-ка, сест-ра).
    """
    low = word.lower()
    vpos = [i for i, c in enumerate(low) if c in VOWELS]
    cuts = []
    for a, b in zip(vpos, vpos[1:]):
        cl = low[a + 1:b]           # consonant cluster between vowels (may include ь ъ й)
        if not cl:
            cuts.append(a + 1)
            continue
        # units: consonant + following sign(s)
        units: List[Tuple[int, int]] = []
        i = a + 1
        while i < b:
            j = i + 1
            while j < b and low[j] in SIGNS:
                j += 1
            units.append((i, j))
            i = j
        if len(units) == 1:
            cuts.append(units[0][0])         # V-CV (also ма-йор, се-мья)
            continue
        if style == "closed":
            cuts.append(units[-1][0])
            continue
        first = low[units[0][0]]
        second = low[units[1][0]]
        if first == "й":
            cuts.append(units[0][1])
        elif first == second and units[0][1] - units[0][0] == 1:
            cuts.append(units[1][0])         # ван-на, кас-са
        elif first in SONORANTS and second not in ("й",):
            cuts.append(units[0][1])         # кар-та, пол-ный, сол-нце
        else:
            cuts.append(units[0][0])         # ко-шка, се-стра
    return cuts


def syllabize(word: str, style: str = "phonetic") -> List[str]:
    cuts = syllable_cuts(word, style)
    parts, last = [], 0
    for c in cuts:
        parts.append(word[last:c])
        last = c
    parts.append(word[last:])
    return [p for p in parts if p]


# --------------------------------------------------------------------------
# transliteration
SCHEMES = {
    "practical": "Practical (Wikipedia/English, no diacritics)",
    "bgn": "BGN/PCGN (ASCII form)",
    "gost_b": "GOST 7.79-2000 System B / ISO 9 ASCII",
    "iso9": "ISO 9:1995 / GOST 7.79 System A (diacritics)",
    "icao": "ICAO Doc 9303 (Russian passports)",
    "alalc": "ALA-LC / Library of Congress (no diacritics)",
    "scholarly": "Scholarly / scientific (diacritics)",
}

_COMMON = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "з": "z", "и": "i", "к": "k", "л": "l",
    "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
}

_TABLES = {
    "practical": {"е": "e", "ё": "yo", "ж": "zh", "й": "y", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
                  "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"},
    "bgn": {"е": "e", "ё": "ë", "ж": "zh", "й": "y", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
            "щ": "shch", "ъ": "\"", "ы": "y", "ь": "'", "э": "e", "ю": "yu", "я": "ya"},
    "gost_b": {"е": "e", "ё": "yo", "ж": "zh", "й": "j", "х": "x", "ц": "cz", "ч": "ch", "ш": "sh",
               "щ": "shh", "ъ": "``", "ы": "y`", "ь": "`", "э": "e`", "ю": "yu", "я": "ya"},
    "iso9": {"е": "e", "ё": "ë", "ж": "ž", "й": "j", "х": "h", "ц": "c", "ч": "č", "ш": "š",
             "щ": "ŝ", "ъ": "ʺ", "ы": "y", "ь": "ʹ", "э": "è", "ю": "û", "я": "â"},
    "icao": {"е": "e", "ё": "e", "ж": "zh", "й": "i", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
             "щ": "shch", "ъ": "ie", "ы": "y", "ь": "", "э": "e", "ю": "iu", "я": "ia"},
    "alalc": {"е": "e", "ё": "e", "ж": "zh", "й": "i", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
              "щ": "shch", "ъ": "\"", "ы": "y", "ь": "'", "э": "e", "ю": "iu", "я": "ia"},
    "scholarly": {"е": "e", "ё": "ë", "ж": "ž", "й": "j", "х": "x", "ц": "c", "ч": "č", "ш": "š",
                  "щ": "šč", "ъ": "ʺ", "ы": "y", "ь": "ʹ", "э": "è", "ю": "ju", "я": "ja"},
}


def _is_vowel_or_sign(c: str) -> bool:
    return c.lower() in VOWELS or c.lower() in SIGNS


def translit_chars(word: str, scheme: str = "practical", keep_soft_sign: bool = False) -> List[str]:
    """Transliterate a word, returning one output string per input character."""
    table = dict(_COMMON)
    table.update(_TABLES.get(scheme, _TABLES["practical"]))
    low = word.lower()
    out: List[str] = []
    n = len(word)
    for i, ch in enumerate(word):
        c = low[i]
        prev = low[i - 1] if i > 0 else ""
        nxt = low[i + 1] if i + 1 < n else ""
        if c not in table:
            out.append(ch)
            continue
        r = table[c]
        if scheme in ("practical", "bgn"):
            word_start = i == 0 or not CYR.match(prev)
            if c == "е" and (word_start or prev in VOWELS or prev in SIGNS):
                r = "ye"
            elif c == "ё":
                if scheme == "bgn":
                    r = "yë" if (word_start or prev in VOWELS or prev in SIGNS) else "ë"
                else:
                    r = "o" if (prev and prev in "жчшщ") else "yo"
            elif scheme == "practical" and c == "ь" and keep_soft_sign:
                r = "'"
            if scheme == "practical":
                at_end = i + 1 >= n or not CYR.match(nxt)
                # -ий / -ый endings -> -y (Dostoevsky, Tolstoy keeps -oy)
                if c == "й" and at_end and prev in ("и", "ы"):
                    r = ""
                if c in ("и", "ы") and nxt == "й" and (i + 2 >= n or not CYR.match(low[i + 2])):
                    r = "y"
                # ь before vowel: Ilya (Илья), семья -> semya
                if c == "ь" and nxt in VOWELS and not keep_soft_sign:
                    r = ""
            if scheme == "bgn" and c == "э" and prev and prev not in ("й",) and not word_start \
                    and prev in "бвгджзклмнпрстфхцчшщ":
                r = "e"
        if scheme == "gost_b" and c == "ц":
            r = "c" if nxt in ("и", "е", "ы", "й") else "cz"
        if scheme == "icao" and c == "ъ":
            r = "ie"
        # case
        if ch.isupper() and r:
            if len(r) > 1 and (i + 1 < n and word[i + 1].isupper()):
                r = r.upper()
            else:
                r = r[0].upper() + r[1:]
        out.append(r)
    return out


def transliterate(text: str, scheme: str = "practical", keep_soft_sign: bool = False) -> str:
    out = []
    for m in re.finditer(r"[А-Яа-яЁё]+|[^А-Яа-яЁё]+", text):
        seg = m.group(0)
        if CYR.match(seg):
            out.append("".join(translit_chars(seg, scheme, keep_soft_sign)))
        else:
            out.append(seg)
    return "".join(out)
