"""Rocksmith-style lyric display for the timeline preview.

Built from the exact vocal entries that will be exported, so it shows how the
lines will be split and timed in the game: the current line with every syllable
lighting up when it is sung, and the next line underneath.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..parsers.rsxml import VocalEntry

SUNG = QColor("#5ad1ff")       # Rocksmith-like blue for sung syllables
NOW = QColor("#ffffff")
UPCOMING = QColor("#e8e8e8")
NEXT = QColor("#8c8c8c")


@dataclass
class _Syl:
    time: float
    length: float
    text: str
    space_after: bool
    index: int


class LyricPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lines: List[List[_Syl]] = []
        self.starts: List[float] = []
        self.t: Optional[float] = None
        self.font_pt = 22
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.native = False

    def set_font_size(self, pt: int):
        self.font_pt = max(10, int(pt))
        self.setMinimumHeight(int(self.font_pt * 4.4))
        self.update()

    def set_entries(self, entries: List[VocalEntry]):
        self.lines, cur = [], []
        for i, e in enumerate(entries):
            lyr = e.lyric
            if lyr.endswith("+"):
                cur.append(_Syl(e.time, e.length, lyr[:-1], False, i))
                self.lines.append(cur)
                cur = []
            elif lyr.endswith("-"):
                cur.append(_Syl(e.time, e.length, lyr[:-1], False, i))
            else:
                cur.append(_Syl(e.time, e.length, lyr, True, i))
        if cur:
            self.lines.append(cur)
        self.starts = [l[0].time for l in self.lines]
        self.update()

    def set_time(self, t: Optional[float]):
        self.t = t
        self.update()

    def current(self) -> Tuple[int, int]:
        """(line index shown as current, index of the syllable being sung or -1)."""
        if not self.lines or self.t is None:
            return -1, -1
        li = bisect.bisect_right(self.starts, self.t) - 1
        if li < 0:
            return 0, -1                       # before the first lyric: show it as upcoming
        cur = -1
        for s in self.lines[li]:
            if s.time <= self.t:
                cur = s.index
        return li, cur

    # ------------------------------------------------------------------ painting
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = self.rect()
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, QColor(10, 12, 16))
        g.setColorAt(1, QColor(22, 26, 34))
        p.fillRect(r, g)
        li, cur = self.current()
        if li < 0:
            p.setPen(NEXT)
            f = QFont(self.font())
            f.setPointSize(max(10, self.font_pt // 2))
            p.setFont(f)
            p.drawText(r, Qt.AlignCenter, "In-game lyrics preview - load lyrics, then press Play or click the timeline")
            p.end()
            return
        big = QFont(self.font())
        big.setPointSize(self.font_pt)
        big.setBold(True)
        small = QFont(big)
        small.setPointSize(max(9, int(self.font_pt * 0.72)))
        small.setBold(False)
        line = self.lines[li]
        y1 = r.height() * 0.44
        self._draw_line(p, line, big, y1, active=True, cur=cur)
        if li + 1 < len(self.lines):
            self._draw_line(p, self.lines[li + 1], small, r.height() * 0.84, active=False, cur=-1)
        p.end()

    def _draw_line(self, p: QPainter, line: List[_Syl], font: QFont, baseline: float, active: bool, cur: int):
        fm = QFontMetricsF(font)
        pieces = []
        for s in line:
            pieces.append((s, s.text + (" " if s.space_after else "")))
        total = sum(fm.horizontalAdvance(t) for _, t in pieces)
        x = max(8.0, (self.width() - total) / 2)
        p.setFont(font)
        t = self.t if self.t is not None else -1
        for s, txt in pieces:
            w = fm.horizontalAdvance(txt)
            if not active:
                p.setPen(NEXT)
                p.drawText(QRectF(x, baseline - fm.ascent(), w + 2, fm.height()), Qt.AlignLeft, txt)
                x += w
                continue
            sung = s.time <= t
            is_now = s.index == cur and t < s.time + max(s.length, 0.12)
            if is_now:
                # glow + progress underline while the syllable is held
                glow = QColor(SUNG)
                glow.setAlpha(70)
                p.fillRect(QRectF(x - 2, baseline - fm.ascent() - 2, fm.horizontalAdvance(s.text) + 4,
                                  fm.height() + 4), glow)
                prog = 1.0 if s.length <= 0 else min(1.0, max(0.0, (t - s.time) / s.length))
                p.setPen(QPen(SUNG, 3))
                p.drawLine(int(x), int(baseline + fm.descent() + 3),
                           int(x + fm.horizontalAdvance(s.text) * prog), int(baseline + fm.descent() + 3))
                p.setPen(NOW)
            else:
                p.setPen(SUNG if sung else UPCOMING)
            p.drawText(QRectF(x, baseline - fm.ascent(), w + 2, fm.height()), Qt.AlignLeft, txt)
            x += w
