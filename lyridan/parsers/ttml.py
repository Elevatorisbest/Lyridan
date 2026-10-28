"""TTML parser (Apple Music syllable/word/line-synced lyrics and generic TTML).

Accepts:
  * raw TTML documents (``<tt ...>``)
  * Apple Music API JSON responses wrapping the TTML string
    (``data[0].attributes.ttml`` or ``ttmlLocalizations``)
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from ..model import SourceLine, SourceLyrics, SourcePiece

TT = "http://www.w3.org/ns/ttml"
TTM = "http://www.w3.org/ns/ttml#metadata"
ITUNES = "http://music.apple.com/lyric-ttml-internal"
XML = "http://www.w3.org/XML/1998/namespace"


def parse_time(value: Optional[str]) -> Optional[float]:
    """Parse TTML clock/offset times: '20.349', '1:02.5', '00:01:02.5', '12.3s', '500ms'."""
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    m = re.fullmatch(r"([\d.]+)(h|m|s|ms)", v)
    if m:
        n = float(m.group(1))
        return round({"h": n * 3600, "m": n * 60, "s": n, "ms": n / 1000}[m.group(2)], 4)
    parts = v.split(":")
    try:
        total = 0.0
        for p in parts:
            total = total * 60 + float(p)
        return round(total, 4)
    except ValueError:
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def extract_ttml_string(content: str) -> str:
    """Return the TTML XML string from raw TTML or Apple JSON wrapper."""
    s = content.lstrip("﻿").strip()
    if s.startswith("{") or s.startswith("["):
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            data = None
        found = _find_ttml_in_json(data) if data is not None else None
        if found:
            return found
        m = re.search(r"<tt[\s>].*</tt>", s, re.DOTALL)
        if m:
            return m.group(0).replace('\\"', '"').replace("\\/", "/")
        raise ValueError("Could not find TTML content inside the JSON file.")
    return s


def _find_ttml_in_json(obj) -> Optional[str]:
    if isinstance(obj, str):
        return obj if "<tt" in obj else None
    if isinstance(obj, dict):
        for key in ("ttmlLocalizations", "ttml"):
            if isinstance(obj.get(key), str) and "<tt" in obj[key]:
                return obj[key]
        for v in obj.values():
            r = _find_ttml_in_json(v)
            if r:
                return r
    if isinstance(obj, list):
        for v in obj:
            r = _find_ttml_in_json(v)
            if r:
                return r
    return None


class _PieceCollector:
    """Walks a <p> (or transliteration <text>) collecting timed pieces.

    Background-vocal spans (ttm:role="x-bg") are collected into a separate list.
    """

    def __init__(self):
        self.main: List[SourcePiece] = []
        self.bg: List[SourcePiece] = []

    @staticmethod
    def _add_text(target: List[SourcePiece], text: Optional[str]):
        """Inter-span text: whitespace marks a word boundary, other text is untimed."""
        if not text:
            return
        if text.strip() == "":
            if target:
                target[-1].joined = False
            return
        # untimed literal text between spans: attach as untimed piece
        lead_space = text[:1].isspace()
        if target and lead_space:
            target[-1].joined = False
        for i, chunk in enumerate(text.split()):
            target.append(SourcePiece(chunk, None, None, joined=False))
        if not text[-1:].isspace() and target:
            target[-1].joined = True

    def walk(self, elem, target: List[SourcePiece], inherited_bg=False):
        is_bg = inherited_bg
        if _local(elem.tag) == "span" and elem.get(f"{{{TTM}}}role", "") in ("x-bg", "x-background"):
            is_bg = True
        tgt = self.bg if is_bg else target
        begin = parse_time(elem.get("begin"))
        end = parse_time(elem.get("end"))
        has_span_children = any(_local(c.tag) == "span" for c in elem)
        if _local(elem.tag) == "span" and not has_span_children:
            text = "".join(elem.itertext())
            if text.strip():
                lead = text[:1].isspace()
                if lead and tgt:
                    tgt[-1].joined = False
                chunks = text.split()
                if len(chunks) == 1:
                    tgt.append(SourcePiece(chunks[0], begin, end, joined=not text[-1:].isspace()))
                else:
                    # several words inside one timed span: split time evenly by length
                    total = sum(len(c) for c in chunks) or 1
                    t = begin
                    for i, c in enumerate(chunks):
                        if begin is not None and end is not None:
                            d = (end - begin) * len(c) / total
                            tgt.append(SourcePiece(c, t, t + d, joined=False))
                            t += d
                        else:
                            tgt.append(SourcePiece(c, None, None, joined=False))
                    tgt[-1].joined = not text[-1:].isspace()
            return
        # container (p / bg span / text): text, children, tails
        self._add_text(tgt, elem.text)
        for child in elem:
            if _local(child.tag) in ("span", "p"):
                self.walk(child, tgt if not is_bg else self.bg, is_bg)
            elif _local(child.tag) == "br":
                if tgt:
                    tgt[-1].joined = False
            self._add_text(tgt, child.tail)


def _fill_line_timing(pieces: List[SourcePiece], begin, end):
    """If pieces carry no timing (line-synced TTML), give the first piece the line timing."""
    if pieces and all(p.start is None for p in pieces) and begin is not None:
        # leave word timing to the distributor; mark the line span on first/last piece
        pieces[0].start = begin
        pieces[-1].end = end


def _clean_bg(pieces: List[SourcePiece]) -> List[SourcePiece]:
    return [p for p in pieces if p.text.strip()]


def parse_ttml(content: str, path: str = "") -> SourceLyrics:
    xml = extract_ttml_string(content)
    xml = re.sub(r"^<\?xml[^>]*\?>", "", xml).strip()
    root = ET.fromstring(xml)
    lang = root.get(f"{{{XML}}}lang", "") or ""
    timing_attr = (root.get(f"{{{ITUNES}}}timing") or "").lower()

    lyric_offset = 0.0
    leading_silence = 0.0
    romaji: Dict[str, List[SourcePiece]] = {}
    romaji_bg: Dict[str, List[SourcePiece]] = {}
    translations: Dict[str, str] = {}
    title = artist = ""

    for el in root.iter():
        name = _local(el.tag)
        if name == "iTunesMetadata":
            try:
                leading_silence = float(el.get("leadingSilence") or 0)
            except ValueError:
                pass
        elif name == "audio" and el.get("lyricOffset") is not None:
            try:
                lyric_offset = float(el.get("lyricOffset"))
            except ValueError:
                pass
        elif name == "transliteration":
            if True:  # any transliteration block (ja-Latn, ru-Latn, ...) is Latin script
                for text_el in el:
                    if _local(text_el.tag) != "text":
                        continue
                    key = text_el.get("for", "")
                    col = _PieceCollector()
                    col.walk(text_el, col.main)
                    if key and key not in romaji:
                        romaji[key] = [p for p in col.main if p.text.strip()]
                        romaji_bg[key] = _clean_bg(col.bg)
        elif name == "translation":
            for text_el in el:
                if _local(text_el.tag) == "text" and text_el.get("for"):
                    translations.setdefault(text_el.get("for"), " ".join("".join(text_el.itertext()).split()))
        elif name == "title" and el.text and not title:
            title = el.text.strip()

    lines: List[SourceLine] = []
    body = None
    for el in root:
        if _local(el.tag) == "body":
            body = el
    if body is None:
        raise ValueError("TTML has no <body>.")

    def handle_p(p, section: str):
        begin = parse_time(p.get("begin"))
        end = parse_time(p.get("end"))
        key = p.get(f"{{{ITUNES}}}key", "") or p.get(f"{{{XML}}}id", "")
        agent = p.get(f"{{{TTM}}}agent", "")
        col = _PieceCollector()
        col.walk(p, col.main)
        main = [x for x in col.main if x.text.strip()]
        bg = _clean_bg(col.bg)
        if main:
            _fill_line_timing(main, begin, end)
            ln = SourceLine(main, begin, end, False, agent, key, section,
                            romaji.get(key), translations.get(key, ""))
            lines.append(ln)
        if bg:
            bstart = next((x.start for x in bg if x.start is not None), begin)
            bend = next((x.end for x in reversed(bg) if x.end is not None), end)
            _fill_line_timing(bg, bstart, bend)
            lines.append(SourceLine(bg, bstart, bend, True, agent, key, section,
                                    romaji_bg.get(key) or None, ""))

    for div in body.iter():
        if _local(div.tag) != "div":
            continue
        section = div.get(f"{{{ITUNES}}}songPart", "") or div.get(f"{{{ITUNES}}}song-part", "")
        for p in div:
            if _local(p.tag) == "p":
                handle_p(p, section)
    if not lines:  # <p> directly in body
        for p in body:
            if _local(p.tag) == "p":
                handle_p(p, "")

    # Determine timing granularity
    timing = "line"
    if timing_attr == "word" or any(len(l.pieces) > 1 and all(x.start is not None for x in l.pieces) for l in lines):
        timing = "word"
        if any(any(x.joined for x in l.pieces) for l in lines):
            timing = "syllable"
    lines.sort(key=lambda l: (l.start if l.start is not None else 0.0))
    return SourceLyrics(lines=lines, language=lang, lyric_offset=lyric_offset,
                        leading_silence=leading_silence, timing=timing,
                        has_romaji=bool(romaji), path=path, title=title, artist=artist)
