"""Japanese processing: readings, romanization, word grouping and syllabization.

Pipeline for one lyric line:
  1. width normalisation (half-width kana -> full width, full-width ASCII -> ASCII)
     keeping a map back to the original characters (needed for timing)
  2. furigana / ruby annotations in the text are honoured and removed:
        漢字(かんじ)  漢字（かんじ）  {漢字|かんじ}  |漢字《かんじ》  漢字《かんじ》
  3. user-dictionary phrases are forced (surface -> reading)
  4. morphological analysis with MeCab (fugashi) + UniDic for context-aware
     readings, with lyric-specific corrections (私→わたし, 明日→あした,
     抱く→だく, 何を→なにを ...); unknown words are read per character
  5. tokens are grouped into romaji words (verb + auxiliaries, noun + suffix,
     particles separate) and every mora keeps a link to its source characters
  6. romanization in modified Hepburn (configurable) and grouping of morae into
     sung syllables
"""
from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..model import Syllable, Word
from .kana import (Mora, hira_to_kata, is_kana, is_kanji, kata_to_hira, romanize_morae,
                   split_morae, split_romaji)


@dataclass
class JapaneseOptions:
    long_vowels: str = "kana"        # kana | macron | plain
    particle_wo: str = "o"           # o | wo   (を)
    particle_ha: str = "wa"          # wa | ha  (は as particle)
    particle_he: str = "e"           # e | he   (へ as particle)
    n_apostrophe: bool = True        # shin'ai
    syllables: str = "mora_n"        # mora | mora_n (ん/っ joined) | syllable (long vowels joined)
    lyric_readings: bool = True      # 私→わたし, 明日→あした, ...
    foreign_spelling: bool = False   # ラブ -> love (UniDic loanword origin)
    split_particles: bool = True     # particles as separate words
    user_dict: Dict[str, str] = field(default_factory=dict)  # surface -> kana reading


# Token-level reading corrections that are almost always right in song lyrics
LYRIC_READINGS = {
    "私": "ワタシ", "明日": "アシタ", "貴女": "アナタ", "貴男": "アナタ", "貴方": "アナタ",
    "彼方": "カナタ", "此処": "ココ", "其処": "ソコ", "何処": "ドコ", "何故": "ナゼ",
    "一人": "ヒトリ", "二人": "フタリ", "独り": "ヒトリ", "大人": "オトナ", "昨日": "キノウ",
    "今日": "キョウ", "眼差し": "マナザシ", "微笑": "ホホエミ", "頬": "ホオ", "日々": "ヒビ",
    "我": "ワレ", "我等": "ワレラ", "汝": "ナンジ", "己": "オノレ", "誰": "ダレ",
    "瞬間": "シュンカン", "刹那": "セツナ", "一緒": "イッショ", "時": "トキ",
}

# Words that songs frequently sing with a non-standard reading. They are kept
# with the dictionary reading but reported so the user can review them.
AMBIGUOUS_READINGS = {
    "宇宙": "うちゅう / そら", "永遠": "えいえん / とわ", "運命": "うんめい / さだめ",
    "故郷": "こきょう / ふるさと", "地球": "ちきゅう / ほし", "本気": "ほんき / まじ",
    "未来": "みらい / あす", "瞬間": "しゅんかん / とき", "理由": "りゆう / わけ",
    "生命": "せいめい / いのち", "現在": "げんざい / いま", "行く": "いく / ゆく",
    "行こう": "いこう / ゆこう", "時間": "じかん / とき", "強敵": "きょうてき / とも",
    "明日": "あした / あす", "一日": "いちにち / ついたち", "未知": "みち",
    "心": "こころ / ハート", "仲間": "なかま / とも", "刃": "は / やいば", "詩": "し / うた",
    "命": "いのち / めい", "雨": "あめ / あま",
}

_PUNCT_MAP = {
    "、": ",", "。": ".", "！": "!", "？": "?", "…": "...", "‥": "..", "・": "", "「": "\"",
    "」": "\"", "『": "\"", "』": "\"", "（": "(", "）": ")", "【": "[", "】": "]", "〜": "~",
    "～": "~", "♪": "", "♡": "", "☆": "", "★": "", "〈": "<", "〉": ">", "《": "<", "》": ">",
    "：": ":", "；": ";", "，": ",", "．": ".", "＂": "\"", "＇": "'", "　": " ",
}

_NUM_READ = {0: "ゼロ", 1: "イチ", 2: "ニ", 3: "サン", 4: "ヨン", 5: "ゴ", 6: "ロク", 7: "ナナ",
             8: "ハチ", 9: "キュウ"}


def number_reading(n: int) -> str:
    if n == 0:
        return "ゼロ"
    parts = []
    units = [(10 ** 8, "オク"), (10 ** 4, "マン")]
    for val, name in units:
        if n >= val:
            parts.append(number_reading(n // val) + name)
            n %= val
    special = {(3, 1000): "サンゼン", (8, 1000): "ハッセン", (3, 100): "サンビャク",
               (6, 100): "ロッピャク", (8, 100): "ハッピャク"}
    for val, name in ((1000, "セン"), (100, "ヒャク"), (10, "ジュウ")):
        d = n // val
        if d:
            if (d, val) in special:
                parts.append(special[(d, val)])
            elif d == 1:
                parts.append(name)
            else:
                parts.append(_NUM_READ[d] + name)
            n %= val
    if n:
        parts.append(_NUM_READ[n])
    return "".join(parts)


@dataclass
class JToken:
    surface: str
    start: int
    end: int
    kana: str = ""
    pron: str = ""
    pos1: str = ""
    pos2: str = ""
    pos3: str = ""
    lemma: str = ""
    goshu: str = ""
    kind: str = "ja"          # ja | latin | punct | space | number
    forced: bool = False
    flagged: str = ""          # note for ambiguous reading


# ---------------------------------------------------------------------------
def normalize_with_map(text: str) -> Tuple[str, List[Tuple[int, int]]]:
    """Width-normalise; return new text and [orig_start, orig_end) per new char."""
    out, spans = [], []
    i = 0
    while i < len(text):
        ch = text[i]
        # half-width katakana + (semi)voiced mark -> single full-width char
        if "ｦ" <= ch <= "ﾝ" and i + 1 < len(text) and text[i + 1] in "ﾞﾟ":
            comb = unicodedata.normalize("NFKC", text[i:i + 2])
            if len(comb) == 1:
                out.append(comb)
                spans.append((i, i + 2))
                i += 2
                continue
        n = unicodedata.normalize("NFKC", ch) if ch not in "　〜～・" else ch
        if len(n) == 1:
            out.append(n)
        else:
            out.append(ch)
        spans.append((i, i + 1))
        i += 1
    return "".join(out), spans


_RUBY_PATTERNS = [
    re.compile(r"\{([^{}|]+)\|([^{}|]+)\}"),
    re.compile(r"[|｜]([^|｜《》]+)《([^《》]+)》"),
    re.compile(r"([㐀-鿿豈-﫿々〆ヶ]+)《([^《》]+)》"),
    re.compile(r"([㐀-鿿豈-﫿々〆ヶ]+)[(（]([ぁ-ゟ゠-ヿー]+)[)）]"),
]


def strip_ruby(text: str, spans: List[Tuple[int, int]]):
    """Remove ruby annotations. Returns (text, spans, forced[(start,end,reading)])."""
    forced = []
    for pat in _RUBY_PATTERNS:
        while True:
            m = pat.search(text)
            if not m:
                break
            base, reading = m.group(1), m.group(2)
            b0 = m.start()
            new_text = text[:b0] + base + text[m.end():]
            base_start_in_match = m.start(1) - m.start()
            new_spans = spans[:b0] + spans[m.start(1):m.start(1) + len(base)] + spans[m.end():]
            # shift existing forced ranges after the match
            delta = len(base) - (m.end() - m.start())
            forced = [(s + (delta if s >= m.end() else 0), e + (delta if e >= m.end() else 0), r)
                      for s, e, r in forced]
            forced.append((b0, b0 + len(base), hira_to_kata(reading)))
            text, spans = new_text, new_spans
            _ = base_start_in_match
    return text, spans, forced


def align_reading(surface: str, reading: str) -> List[Tuple[str, str]]:
    """Align a token surface with its katakana reading (okurigana aware).

    '抱きしめ','ダキシメ' -> [('抱','ダ'),('きしめ','キシメ')]
    """
    if not surface:
        return []
    runs = []  # (text, is_kana)
    for ch in surface:
        k = is_kana(ch)
        if runs and runs[-1][1] == k:
            runs[-1] = (runs[-1][0] + ch, k)
        else:
            runs.append((ch, k))
    if len(runs) == 1:
        return [(surface, reading)]
    pattern = "^" + "".join(
        "(" + re.escape(hira_to_kata(t)) + ")" if k else "(.+?)" for t, k in runs) + "$"
    m = re.match(pattern, reading)
    if not m:
        return [(surface, reading)]
    return [(runs[i][0], m.group(i + 1)) for i in range(len(runs))]


class JapaneseEngine:
    _lock = threading.Lock()

    def __init__(self):
        self._tagger = None
        self.unknown = set()

    @property
    def tagger(self):
        if self._tagger is None:
            with self._lock:
                if self._tagger is None:
                    import fugashi
                    self._tagger = fugashi.Tagger()
        return self._tagger

    # ------------------------------------------------------------------
    def fallback_reading(self, text: str) -> str:
        """Reading for a token UniDic does not know: analyse it character by character."""
        out = []
        for ch in text:
            if is_kana(ch):
                out.append(hira_to_kata(ch))
                continue
            reading = ""
            for node in self.tagger(ch):
                k = getattr(node.feature, "kana", None)
                if k and k != "*":
                    reading += k
            if not reading:
                self.unknown.add(ch)
                return ""
            out.append(hira_to_kata(reading))
        return "".join(out)

    _LATIN_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’]*(?:[\-][A-Za-z0-9'’]+)*")

    def _tokenize_segment(self, seg: str, offset: int) -> List[JToken]:
        """Latin words are kept whole; everything else goes through MeCab."""
        toks: List[JToken] = []
        pos = 0
        for m in self._LATIN_RUN.finditer(seg):
            if not re.search(r"[A-Za-z]", m.group(0)):
                continue  # pure numbers stay with MeCab (counters)
            if m.start() > pos:
                toks += self._mecab_segment(seg[pos:m.start()], offset + pos)
            toks.append(JToken(m.group(0), offset + m.start(), offset + m.end(), kind="latin"))
            pos = m.end()
        if pos < len(seg):
            toks += self._mecab_segment(seg[pos:], offset + pos)
        return toks

    def _mecab_segment(self, seg: str, offset: int) -> List[JToken]:
        toks: List[JToken] = []
        if not seg:
            return toks
        pos = 0
        for node in self.tagger(seg):
            surf = node.surface
            idx = seg.find(surf, pos)
            if idx < 0:
                idx = pos
            pos = idx + len(surf)
            f = node.feature
            pos1 = getattr(f, "pos1", "") or ""
            tok = JToken(surf, offset + idx, offset + idx + len(surf), pos1=pos1,
                         pos2=getattr(f, "pos2", "") or "", pos3=getattr(f, "pos3", "") or "",
                         lemma=getattr(f, "lemma", "") or "", goshu=getattr(f, "goshu", "") or "")
            kana = getattr(f, "kana", None)
            pron = getattr(f, "pron", None)
            if pos1 == "記号" and kana and kana != "*" and any(is_kanji(c) or is_kana(c) for c in surf):
                pos1 = tok.pos1 = "名詞"
            if pos1 in ("補助記号", "記号") or (surf.strip() == "" and surf):
                tok.kind = "space" if surf.strip() == "" else "punct"
            elif pos1 == "空白":
                tok.kind = "space"
            elif re.fullmatch(r"[A-Za-z][A-Za-z'’\-]*", surf):
                tok.kind = "latin"
            elif re.fullmatch(r"[0-9]+", surf):
                tok.kind = "number"
                tok.kana = number_reading(int(surf)) if len(surf) < 10 else surf
                tok.pron = tok.kana
            else:
                if not kana or kana == "*":
                    if all(is_kana(c) for c in surf):
                        kana = hira_to_kata(surf)
                    else:
                        kana = self.fallback_reading(surf)
                        if not kana:
                            tok.flagged = "unknown"
                tok.kana = hira_to_kata(kana)
                tok.pron = hira_to_kata(pron) if pron and pron != "*" else tok.kana
                if not all(is_kana(c) or is_kanji(c) for c in surf):
                    # mixed latin/other inside a token: keep as other
                    if not any(is_kana(c) or is_kanji(c) for c in surf):
                        tok.kind = "latin" if re.search(r"[A-Za-z]", surf) else "punct"
            toks.append(tok)
        return toks

    def tokenize(self, text: str, forced: List[Tuple[int, int, str]], opts: JapaneseOptions) -> List[JToken]:
        # user dictionary phrases -> forced ranges (longest match first, no overlaps)
        forced = list(forced)
        if opts.user_dict:
            taken = [False] * len(text)
            for s, e, _ in forced:
                for i in range(s, e):
                    taken[i] = True
            for surf in sorted(opts.user_dict, key=len, reverse=True):
                if not surf:
                    continue
                start = 0
                while True:
                    i = text.find(surf, start)
                    if i < 0:
                        break
                    if not any(taken[i:i + len(surf)]):
                        forced.append((i, i + len(surf), hira_to_kata(opts.user_dict[surf])))
                        for k in range(i, i + len(surf)):
                            taken[k] = True
                    start = i + len(surf)
        forced.sort()
        toks: List[JToken] = []
        pos = 0
        for s, e, reading in forced:
            if s > pos:
                toks += self._tokenize_segment(text[pos:s], pos)
            toks.append(JToken(text[s:e], s, e, kana=reading, pron=reading, pos1="名詞",
                               pos2="普通名詞", kind="ja", forced=True))
            pos = e
        if pos < len(text):
            toks += self._tokenize_segment(text[pos:], pos)
        if opts.lyric_readings:
            self._apply_lyric_rules(toks)
        for t in toks:
            if t.kind == "ja" and not t.forced and t.surface in AMBIGUOUS_READINGS:
                t.flagged = AMBIGUOUS_READINGS[t.surface]
        return toks

    @staticmethod
    def _apply_lyric_rules(toks: List[JToken]):
        n = len(toks)
        for i, t in enumerate(toks):
            if t.kind != "ja" or t.forced:
                continue
            nxt = toks[i + 1] if i + 1 < n else None
            if t.surface in LYRIC_READINGS and t.surface != "時":
                t.kana = t.pron = LYRIC_READINGS[t.surface]
            # 何 + particle -> なに
            if t.surface == "何":
                if nxt is None or nxt.kind != "ja":
                    t.kana = t.pron = "ナニ"
                elif nxt.surface == "時" and i + 2 < n and toks[i + 2].surface in (
                        "まで", "も", "か", "だって", "でも", "の", "から"):
                    t.kana = t.pron = "イツ"
                    nxt.kana = nxt.pron = ""
                    nxt.surface_merge = True  # type: ignore[attr-defined]
                elif nxt.pos1 == "助詞" and nxt.surface in (
                        "を", "が", "も", "か", "に", "は", "と", "より", "から", "まで", "や", "さえ",
                        "ひとつ", "一つ", "して", "しに", "ゆえ", "故", "やら", "ぞ"):
                    t.kana = t.pron = "ナニ"
                elif nxt.surface in ("一つ", "ひとつ", "気", "より", "処", "事", "もの", "者"):
                    t.kana = t.pron = "ナニ"
            # 抱く: だく (but 夢/希望/想い を 抱く -> いだく)
            if t.lemma.startswith("抱く") and t.kana.startswith("イダ"):
                prev_obj = toks[i - 2].surface if i >= 2 and toks[i - 1].surface == "を" else ""
                if prev_obj not in ("夢", "希望", "想い", "思い", "野望", "不安", "疑問", "志", "願い",
                                    "理想", "憧れ", "誇り", "大志", "疑い", "期待", "幻想"):
                    t.kana = t.kana[1:]
                    t.pron = t.pron[1:] if t.pron.startswith("イダ") else t.pron
        # merge tokens marked by the rules (何+時 -> いつ)
        i = 0
        while i < len(toks):
            if getattr(toks[i], "surface_merge", False) and i > 0:
                prev = toks[i - 1]
                prev.surface += toks[i].surface
                prev.end = toks[i].end
                del toks[i]
                continue
            i += 1

    # ------------------------------------------------------------------
    @staticmethod
    def _attach_to_prev(tok: JToken, prev: Optional[JToken], opts: JapaneseOptions) -> bool:
        if prev is None or prev.kind not in ("ja", "number") or tok.kind not in ("ja", "number"):
            return False
        if prev.pos1 == "接頭辞":
            return True
        p1, p2 = tok.pos1, tok.pos2
        if p1 == "助動詞":
            if tok.surface in ("だ", "で", "です", "でし", "だっ", "でしょ", "だろ", "でしょう", "だろう", "じゃ",
                               "なら", "な", "に") and prev.pos1 != "動詞":
                return False
            return True
        if p1 == "接尾辞":
            return True
        if prev.pos2 == "数詞" and p1 == "名詞" and "助数詞" in tok.pos3:
            return True
        if p1 == "助詞" and p2 == "接続助詞" and tok.surface in ("て", "で", "ば", "ちゃ", "じゃ", "たり", "だり", "ちゃう"):
            return prev.pos1 in ("動詞", "形容詞", "助動詞")
        if p1 == "動詞" and p2 == "非自立可能" and tok.surface in ("る", "た", "てる", "とく", "ちゃう"):
            return True
        if not opts.split_particles and p1 == "助詞":
            return True
        return False

    def romanize_token(self, tok: JToken, opts: JapaneseOptions) -> List[Mora]:
        kana = tok.kana or hira_to_kata(tok.surface)
        morae = split_morae(kana)
        pron_m = split_morae(tok.pron) if tok.pron else []
        # particle and within-token は/へ/を that are pronounced わ/え/お
        is_particle = tok.pos1 == "助詞"
        if len(pron_m) == len(morae):
            for m, p in zip(morae, pron_m):
                if m.kana in ("ハ", "ヘ", "ヲ") and p.kana in ("ワ", "エ", "オ"):
                    m.kana = p.kana
                    m.pron_particle = True  # type: ignore[attr-defined]
        if is_particle and tok.surface in ("は", "ハ") and len(morae) == 1:
            morae[0].kana = "ワ"
            morae[0].pron_particle = True  # type: ignore[attr-defined]
        if is_particle and tok.surface in ("へ", "ヘ") and len(morae) == 1:
            morae[0].kana = "エ"
            morae[0].pron_particle = True  # type: ignore[attr-defined]
        if tok.surface in ("を", "ヲ"):
            morae[0].kana = "オ"
            morae[0].pron_particle = True  # type: ignore[attr-defined]
        romanize_morae(morae, long_vowels=opts.long_vowels, n_apostrophe=opts.n_apostrophe)
        # verbs ending in う keep the u even with macrons (思う omou, not omō)
        if opts.long_vowels != "kana" and tok.pos1 in ("動詞", "助動詞") and morae and \
                hira_to_kata(tok.surface)[-1:] == "ウ" and morae[-1].roma == "":
            morae[-1].roma = "u"
            morae[-1].kind = "mora"
            prev = morae[-2] if len(morae) > 1 else None
            if prev and prev.roma and prev.roma[-1] in "ōū":
                prev.roma = prev.roma[:-1] + {"ō": "o", "ū": "u"}[prev.roma[-1]]
        for m in morae:
            if getattr(m, "pron_particle", False):
                original = {"ワ": "ハ", "エ": "ヘ", "オ": "ヲ"}[m.kana]
                if original == "ハ" and opts.particle_ha == "ha":
                    m.roma = "ha"
                elif original == "ヘ" and opts.particle_he == "he":
                    m.roma = "he"
                elif original == "ヲ" and opts.particle_wo == "wo":
                    m.roma = "wo"
        return morae

    def mora_char_spans(self, tok: JToken, morae: List[Mora]) -> List[Tuple[int, int]]:
        """Source char span (in normalized text) for every mora of a token."""
        spans: List[Tuple[int, int]] = []
        chunks = align_reading(tok.surface, tok.kana or hira_to_kata(tok.surface))
        cpos = tok.start
        mi = 0
        for ctext, creading in chunks:
            n_m = len(split_morae(creading)) if creading else 0
            c0, c1 = cpos, cpos + len(ctext)
            if all(is_kana(c) for c in ctext) and n_m == len(split_morae(ctext)):
                # kana: one span per mora, by kana length of the mora
                kpos = c0
                for _ in range(n_m):
                    if mi >= len(morae):
                        break
                    width = len(morae[mi].kana) if len(morae[mi].kana) <= c1 - kpos else 1
                    spans.append((kpos, min(c1, kpos + max(1, width))))
                    kpos = min(c1, kpos + max(1, width))
                    mi += 1
            else:
                # kanji chunk: distribute morae across characters
                nchars = max(1, len(ctext))
                for k in range(n_m):
                    if mi >= len(morae):
                        break
                    ci = min(nchars - 1, (k * nchars) // max(1, n_m))
                    spans.append((c0 + ci, c0 + ci + 1))
                    mi += 1
            cpos = c1
        while len(spans) < len(morae):
            spans.append((tok.start, tok.end))
        return spans[:len(morae)]

    @staticmethod
    def group_morae(morae: List[Mora], mode: str) -> List[List[int]]:
        groups: List[List[int]] = []
        for i, m in enumerate(morae):
            if not m.roma and m.kind in ("long", "sokuon") and groups:
                groups[-1].append(i)
                continue
            join = False
            if groups:
                if m.kind == "sokuon":
                    join = True
                elif m.kind == "n" and mode in ("mora_n", "syllable"):
                    join = True
                elif mode == "syllable":
                    prev_r = morae[groups[-1][-1]].roma
                    pv = prev_r[-1:] if prev_r else ""
                    if m.kind == "long":
                        join = True
                    elif m.roma in ("u",) and pv in ("o", "u") and m.kana == "ウ":
                        join = True
                    elif m.roma == "i" and pv in ("e", "i") and m.kana == "イ":
                        join = True
                    elif m.roma in ("a", "e", "o") and m.roma == pv and len(m.kana) == 1:
                        join = True
            if join:
                groups[-1].append(i)
            else:
                groups.append([i])
        return groups

    # ------------------------------------------------------------------
    def process_line(self, text: str, opts: JapaneseOptions, english=None) -> Tuple[List[Word], List[str]]:
        """Return (words, warnings). Syllable cs/ce refer to indices in ``text``."""
        norm, spans = normalize_with_map(text)
        norm, spans, forced = strip_ruby(norm, spans)
        toks = self.tokenize(norm, forced, opts)
        warnings = []
        for t in toks:
            if t.flagged and not t.kana:
                warnings.append(f"{t.surface}: unknown reading - add it to the Japanese dictionary")
            elif t.flagged:
                warnings.append(f"{t.surface}: read as {kata_to_hira(t.kana)} (songs also use {t.flagged})")

        words: List[Word] = []
        pending_prefix = ""
        cur: Optional[dict] = None
        prev_tok: Optional[JToken] = None

        def orig_span(a: int, b: int) -> Tuple[int, int]:
            if a >= len(spans):
                return (len(text), len(text))
            b = max(a + 1, b)
            return spans[a][0], spans[min(b, len(spans)) - 1][1]

        def flush():
            nonlocal cur
            if cur and cur["morae"]:
                words.append(self._build_word(cur, opts))
            cur = None

        for tok in toks:
            if tok.kind == "space":
                flush()
                prev_tok = None
                continue
            if tok.kind == "punct":
                p = "".join(_PUNCT_MAP.get(c, c) for c in tok.surface)
                if p.strip() == "":
                    flush()
                    prev_tok = None
                    continue
                if p in ("(", "[", "\"", "<") and (cur is None or prev_tok is None):
                    pending_prefix += p
                    continue
                if p in ("(", "[", "<"):
                    flush()
                    pending_prefix += p
                    prev_tok = None
                    continue
                if cur is not None:
                    cur["suffix"] += p
                elif words:
                    words[-1].suffix += p
                else:
                    pending_prefix += p
                continue
            if tok.kind == "latin":
                flush()
                sylls = english.syllabize(tok.surface) if english else [tok.surface]
                pos = tok.start
                out = []
                for s in sylls:
                    a, b = orig_span(pos, pos + len(s))
                    out.append(Syllable(s, native=s, cs=a, ce=b))
                    pos += len(s)
                w = Word(out, source=tok.surface, lang="en", prefix=pending_prefix)
                pending_prefix = ""
                words.append(w)
                prev_tok = None
                continue
            # Japanese / number
            if opts.foreign_spelling and tok.goshu == "外" and "-" in tok.lemma and english:
                foreign = tok.lemma.split("-", 1)[1]
                if re.fullmatch(r"[A-Za-z][A-Za-z' ]*", foreign) and " " not in foreign:
                    flush()
                    a, b = orig_span(tok.start, tok.end)
                    sylls = english.syllabize(foreign)
                    w = Word([Syllable(s, cs=a, ce=b) for s in sylls], source=tok.surface,
                             lang="en", prefix=pending_prefix)
                    w.syllables[0].native = tok.surface
                    pending_prefix = ""
                    words.append(w)
                    prev_tok = tok
                    continue
            morae = self.romanize_token(tok, opts)
            mspans = [orig_span(a, b) for a, b in self.mora_char_spans(tok, morae)]
            if cur is not None and self._attach_to_prev(tok, prev_tok, opts):
                cur["morae"] += morae
                cur["spans"] += mspans
                cur["source"] += tok.surface
            else:
                flush()
                cur = {"morae": morae, "spans": mspans, "source": tok.surface,
                       "prefix": pending_prefix, "suffix": ""}
                pending_prefix = ""
            prev_tok = tok
        flush()
        if pending_prefix and words:
            words[-1].suffix += pending_prefix
        return words, warnings

    def _build_word(self, cur: dict, opts: JapaneseOptions) -> Word:
        morae: List[Mora] = cur["morae"]
        spans = cur["spans"]
        # re-resolve context-dependent morae across token boundaries
        for i, m in enumerate(morae):
            nxt = morae[i + 1].roma if i + 1 < len(morae) else ""
            if m.kind == "sokuon":
                if nxt and nxt[0] not in "aiueon" and morae[i + 1].kind == "mora":
                    m.roma = "t" if nxt.startswith("ch") else nxt[0]
                else:
                    m.roma = ""
            elif m.kind == "n":
                m.roma = "n'" if (opts.n_apostrophe and nxt and nxt[0] in "aiueoy") else "n"
        groups = self.group_morae(morae, opts.syllables)
        sylls: List[Syllable] = []
        owned_until = -1
        for g in groups:
            roma = "".join(morae[i].roma for i in g)
            a = min(spans[i][0] for i in g)
            b = max(spans[i][1] for i in g)
            # native text: characters not already shown by an earlier syllable
            na = max(a, owned_until)
            native = ""
            if b > na:
                native = (na, b)
                owned_until = b
            sylls.append(Syllable(roma, cs=a, ce=b, native=native))  # native resolved later
        sylls = [s for s in sylls if s.text or s.native]
        if not sylls:
            sylls = [Syllable("", cs=spans[0][0], ce=spans[-1][1])]
        # empty romaji syllable (lone sokuon/long mark) -> merge into previous
        merged: List[Syllable] = []
        for s in sylls:
            if not s.text and merged:
                merged[-1].ce = max(merged[-1].ce, s.ce)
                if s.native:
                    pa = merged[-1].native
                    merged[-1].native = (pa[0], s.native[1]) if pa else s.native
                continue
            merged.append(s)
        return Word(merged, source=cur["source"], lang="ja", prefix=cur["prefix"], suffix=cur["suffix"])

    # ------------------------------------------------------------------
    def syllabize_romaji_word(self, word: str, mode: str = "mora_n") -> List[str]:
        """Syllabize an already-romanized Japanese word (e.g. Apple's ja-Latn)."""
        m = re.match(r"^([^\w']*)([\w'āīūēōâîûêô\-]*?)([^\w']*)$", word)
        if not m or not m.group(2):
            return [word]
        pre, core, post = m.groups()
        units = split_romaji(core)
        groups: List[str] = []
        for u in units:
            low = u.lower()
            is_n = low in ("n", "n'", "m")
            is_gem = len(low) == 1 and low not in "aiueon" and low.isalpha()
            is_vowel = low in ("a", "i", "u", "e", "o")
            join = False
            if groups:
                prev = groups[-1].lower()
                if is_gem:
                    join = True
                elif is_n and mode in ("mora_n", "syllable"):
                    join = True
                elif not low.isalpha() and low != "'":
                    join = True
                elif mode == "syllable" and is_vowel:
                    pv = prev[-1:]
                    if (low == "u" and pv in "ou") or (low == "i" and pv in "ei") or (low == pv and low in "aeo"):
                        join = True
            if join:
                groups[-1] += u
            else:
                groups.append(u)
        if not groups:
            groups = [core]
        groups[0] = pre + groups[0]
        groups[-1] = groups[-1] + post
        return groups


def resolve_native(words: List[Word], text: str):
    """Turn native (start,end) tuples into strings from the original line text."""
    for w in words:
        for s in w.syllables:
            if isinstance(s.native, tuple):
                a, b = s.native
                s.native = text[a:b] if 0 <= a < b <= len(text) else ""
            elif s.native is None:
                s.native = ""


_engine: Optional[JapaneseEngine] = None


def get_japanese() -> JapaneseEngine:
    global _engine
    if _engine is None:
        _engine = JapaneseEngine()
    return _engine
