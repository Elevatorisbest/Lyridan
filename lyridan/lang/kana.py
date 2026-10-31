"""Kana handling: mora segmentation and Hepburn romanization.

Everything works on *mora* lists so that romanization and syllable splitting
stay aligned with the original characters (needed for timing and for
native-script exports).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import List, Optional

HIRA_START, HIRA_END = 0x3041, 0x3096


def hira_to_kata(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if HIRA_START <= o <= HIRA_END or ch in "ゝゞ":
            out.append(chr(o + 0x60))
        else:
            out.append(ch)
    return "".join(out)


def kata_to_hira(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if 0x30A1 <= o <= 0x30F6 or ch in "ヽヾ":
            out.append(chr(o - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def is_kana(ch: str) -> bool:
    o = ord(ch)
    return (0x3041 <= o <= 0x309F) or (0x30A0 <= o <= 0x30FF) or (0x31F0 <= o <= 0x31FF) or ch in "ー･ｰ"


def is_kanji(ch: str) -> bool:
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF) or (0x3400 <= o <= 0x4DBF) or (0xF900 <= o <= 0xFAFF) \
        or (0x20000 <= o <= 0x2FA1F) or ch in "々〆ヶヵ〇"


def is_japanese_char(ch: str) -> bool:
    return is_kana(ch) or is_kanji(ch)


# --------------------------------------------------------------------------
# Hepburn tables (katakana keys)
BASE = {
    "ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o",
    "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
    "サ": "sa", "シ": "shi", "ス": "su", "セ": "se", "ソ": "so",
    "タ": "ta", "チ": "chi", "ツ": "tsu", "テ": "te", "ト": "to",
    "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
    "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
    "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
    "ヤ": "ya", "ユ": "yu", "ヨ": "yo",
    "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
    "ワ": "wa", "ヰ": "i", "ヱ": "e", "ヲ": "o", "ン": "n",
    "ガ": "ga", "ギ": "gi", "グ": "gu", "ゲ": "ge", "ゴ": "go",
    "ザ": "za", "ジ": "ji", "ズ": "zu", "ゼ": "ze", "ゾ": "zo",
    "ダ": "da", "ヂ": "ji", "ヅ": "zu", "デ": "de", "ド": "do",
    "バ": "ba", "ビ": "bi", "ブ": "bu", "ベ": "be", "ボ": "bo",
    "パ": "pa", "ピ": "pi", "プ": "pu", "ペ": "pe", "ポ": "po",
    "ヴ": "vu", "ヷ": "va", "ヸ": "vi", "ヹ": "ve", "ヺ": "vo",
    "ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o",
    "ャ": "ya", "ュ": "yu", "ョ": "yo", "ヮ": "wa", "ヵ": "ka", "ヶ": "ke",
    "ッ": "", "ー": "",
}

DIGRAPHS = {}
for _c, _r in (("キ", "k"), ("ギ", "g"), ("ニ", "n"), ("ヒ", "h"), ("ビ", "b"), ("ピ", "p"),
               ("ミ", "m"), ("リ", "r")):
    DIGRAPHS[_c + "ャ"] = _r + "ya"
    DIGRAPHS[_c + "ュ"] = _r + "yu"
    DIGRAPHS[_c + "ョ"] = _r + "yo"
    DIGRAPHS[_c + "ェ"] = _r + "ye"
for _c, _r in (("シ", "sh"), ("チ", "ch"), ("ジ", "j"), ("ヂ", "j")):
    DIGRAPHS[_c + "ャ"] = _r + "a"
    DIGRAPHS[_c + "ュ"] = _r + "u"
    DIGRAPHS[_c + "ョ"] = _r + "o"
    DIGRAPHS[_c + "ェ"] = _r + "e"
DIGRAPHS.update({
    "ティ": "ti", "ディ": "di", "トゥ": "tu", "ドゥ": "du", "テュ": "tyu", "デュ": "dyu",
    "ファ": "fa", "フィ": "fi", "フェ": "fe", "フォ": "fo", "フュ": "fyu", "フャ": "fya", "フョ": "fyo",
    "ウィ": "wi", "ウェ": "we", "ウォ": "wo", "ウゥ": "wu",
    "ヴァ": "va", "ヴィ": "vi", "ヴェ": "ve", "ヴォ": "vo", "ヴュ": "vyu", "ヴャ": "vya", "ヴョ": "vyo",
    "ツァ": "tsa", "ツィ": "tsi", "ツェ": "tse", "ツォ": "tso", "ツュ": "tsyu",
    "クァ": "kwa", "クィ": "kwi", "クェ": "kwe", "クォ": "kwo", "クヮ": "kwa",
    "グァ": "gwa", "グィ": "gwi", "グェ": "gwe", "グォ": "gwo", "グヮ": "gwa",
    "イェ": "ye", "スィ": "si", "ズィ": "zi", "ホゥ": "hu",
    "シィ": "shi", "チィ": "chi", "ジィ": "ji",
})

SMALL = set("ァィゥェォャュョヮ")
VOWEL_OF = {"a": "a", "i": "i", "u": "u", "e": "e", "o": "o"}
MACRON = {"a": "ā", "i": "ī", "u": "ū", "e": "ē", "o": "ō"}


@dataclass
class Mora:
    kana: str                 # katakana for this mora (1-2 chars)
    roma: str = ""            # romaji (filled by romanize_morae)
    kind: str = "mora"        # "mora", "sokuon", "n", "long"


def split_morae(kana: str) -> List[Mora]:
    """Split a katakana/hiragana string into morae."""
    k = hira_to_kata(unicodedata.normalize("NFKC", kana))
    out: List[Mora] = []
    i = 0
    while i < len(k):
        ch = k[i]
        nxt = k[i + 1] if i + 1 < len(k) else ""
        if nxt in SMALL and (ch + nxt) in DIGRAPHS:
            out.append(Mora(ch + nxt))
            i += 2
            continue
        if ch == "ッ":
            out.append(Mora(ch, kind="sokuon"))
        elif ch == "ン":
            out.append(Mora(ch, kind="n"))
        elif ch in "ー〜～":
            out.append(Mora("ー", kind="long"))
        elif ch in "ヽヾ" and out:  # iteration marks
            prev = out[-1].kana
            if ch == "ヾ":
                prev = unicodedata.normalize("NFC", prev[0] + "゙") + prev[1:]
            out.append(Mora(prev))
        else:
            out.append(Mora(ch))
        i += 1
    return out


def mora_base(m: Mora) -> str:
    if m.kana in DIGRAPHS:
        return DIGRAPHS[m.kana]
    if m.kana in BASE:
        return BASE[m.kana]
    return m.kana  # non-kana passthrough


def _vowel(r: str) -> Optional[str]:
    for ch in reversed(r):
        if ch in "aiueo":
            return ch
        if ch in MACRON.values():
            return {v: k for k, v in MACRON.items()}[ch]
    return None


def romanize_morae(morae: List[Mora], *, long_vowels: str = "kana", n_apostrophe: bool = True,
                   sokuon_end: str = "") -> List[Mora]:
    """Fill ``roma`` for each mora (modified Hepburn).

    long_vowels: "kana"   - spell as written (ou, ei, ー -> repeated vowel)
                 "macron" - ō, ū, ā, ē (ー and same-vowel pairs)
                 "plain"  - drop the lengthening (Tokyo, ramen)
    """
    n = len(morae)
    bases = [mora_base(m) for m in morae]
    for idx, m in enumerate(morae):
        b = bases[idx]
        if m.kind == "sokuon":
            nb = bases[idx + 1] if idx + 1 < n else ""
            if nb and nb[0] not in "aiueon" and morae[idx + 1].kind == "mora":
                m.roma = "t" if nb.startswith("ch") else nb[0]
            else:
                m.roma = sokuon_end
        elif m.kind == "n":
            nb = bases[idx + 1] if idx + 1 < n else ""
            m.roma = "n'" if (n_apostrophe and nb and (nb[0] in "aiueoy")) else "n"
        elif m.kind == "long":
            prev_v = _vowel(morae[idx - 1].roma) if idx > 0 else None
            m.roma = prev_v or ""
        else:
            m.roma = b
    if long_vowels in ("macron", "plain"):
        for idx in range(1, n):
            m, p = morae[idx], morae[idx - 1]
            pv = _vowel(p.roma)
            if not pv or not p.roma or p.kind != "mora":
                continue
            is_long = m.kind == "long" or (m.kind == "mora" and m.roma == pv and pv in "aueo") \
                or (m.kind == "mora" and pv == "o" and m.roma == "u" and m.kana in ("ウ",))
            if is_long and m.roma:
                if long_vowels == "macron":
                    p.roma = p.roma[:-1] + MACRON[pv]
                m.roma = ""
                m.kind = "long"
    return morae


def kana_to_romaji(kana: str, **kw) -> str:
    return "".join(m.roma for m in romanize_morae(split_morae(kana), **kw))


# --------------------------------------------------------------------------
# Romaji -> morae (for already-romanized Japanese text, e.g. Apple ja-Latn)
_ROMA_UNITS = sorted({v for v in list(BASE.values()) + list(DIGRAPHS.values()) if v} |
                     {"si", "ti", "tu", "hu", "zi", "di", "du", "wo", "wi", "we", "ye", "va", "vi", "ve",
                      "vo", "sya", "syu", "syo", "tya", "tyu", "tyo", "zya", "zyu", "zyo", "jya", "jyu",
                      "jyo", "cya", "cyu", "cyo", "dya", "dyo"}, key=len, reverse=True)


def split_romaji(word: str) -> List[str]:
    """Split a romaji word into morae-like units keeping n, geminates and vowels separate.

    'kitte' -> ['ki','t','te'], 'konnichiwa' -> ['ko','n','ni','chi','wa'],
    'shin'ai' -> ['shi',"n'",'a','i'], 'tōkyō' -> ['tō','kyō']
    """
    w = word
    low = w.lower()
    out = []
    i = 0
    trans = {v: k for k, v in MACRON.items()}
    plain_low = "".join(trans.get(c, c) for c in low)
    while i < len(w):
        ch = plain_low[i]
        if not ch.isalpha():
            if out and ch == "'":
                out[-1] += w[i]
            else:
                out.append(w[i])
            i += 1
            continue
        # n before consonant / end / apostrophe
        if ch == "n" and (i + 1 >= len(w) or plain_low[i + 1] not in "aiueoy" or
                          (i + 1 < len(w) and plain_low[i + 1] == "'")):
            j = i + 1
            if j < len(w) and plain_low[j] == "'":
                j += 1
            out.append(w[i:j])
            i = j
            continue
        if ch == "m" and i + 1 < len(w) and plain_low[i + 1] in "bmp":  # traditional Hepburn m
            out.append(w[i])
            i += 1
            continue
        # geminate consonant
        if i + 1 < len(w) and ch not in "aiueon" and (plain_low[i + 1] == ch or
                                                       (ch == "t" and plain_low[i + 1:i + 3] == "ch")):
            out.append(w[i])
            i += 1
            continue
        for unit in _ROMA_UNITS:
            if plain_low.startswith(unit, i):
                out.append(w[i:i + len(unit)])
                i += len(unit)
                break
        else:
            # unknown letter: attach to previous unit (keeps foreign spellings intact)
            if out and out[-1][-1:].isalpha():
                out[-1] += w[i]
            else:
                out.append(w[i])
            i += 1
    return out
