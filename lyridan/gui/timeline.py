"""Timeline preview: beat grid, sections, chart notes, generated and reference vocals."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QScrollArea, QToolTip, QWidget

from ..parsers.rsxml import Beatmap, VocalEntry

STRING_COLORS = ["#e5484d", "#f5d90a", "#3e9bf5", "#f76b15", "#46a758", "#8e4ec6", "#888888"]


class TimelineCanvas(QWidget):
    zoomChanged = Signal(float)

    ROW_RULER = 24
    ROW_SECTIONS = 22
    ROW_NOTES = 40
    ROW_VOCALS = 64
    ROW_REF = 64

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pps = 80.0  # pixels per second
        self.beatmap: Optional[Beatmap] = None
        self.vocals: List[VocalEntry] = []
        self.reference: List[VocalEntry] = []
        self.silence_end = 0.0
        self.bars_end = 0.0
        self.duration = 60.0
        self.view_h = 0
        self.setMouseTracking(True)
        self.setMinimumHeight(self._height())

    def _height(self):
        return max(self.view_h, self.ROW_RULER + self.ROW_SECTIONS + self.ROW_NOTES + self.ROW_VOCALS +
                   self.ROW_REF + 16)

    def set_data(self, beatmap, vocals, reference, silence_end, bars_end):
        self.beatmap = beatmap
        self.vocals = vocals or []
        self.reference = reference or []
        self.silence_end = silence_end
        self.bars_end = bars_end
        ends = [10.0]
        if beatmap and beatmap.beats:
            ends.append(beatmap.song_length or beatmap.beats[-1])
        if self.vocals:
            ends.append(self.vocals[-1].time + self.vocals[-1].length)
        if self.reference:
            ends.append(self.reference[-1].time + self.reference[-1].length)
        self.duration = max(ends) + 5
        self._resize()
        self.update()

    def set_zoom(self, pps: float):
        self.pps = max(10.0, min(800.0, pps))
        self._resize()
        self.update()
        self.zoomChanged.emit(self.pps)

    def _resize(self):
        self.setFixedSize(QSize(int(self.duration * self.pps) + 40, self._height()))

    def x(self, t: float) -> float:
        return 20 + t * self.pps

    def t_at(self, x: float) -> float:
        return (x - 20) / self.pps

    # ------------------------------------------------------------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        pal = self.palette()
        bg = pal.base().color()
        fg = pal.text().color()
        dark = bg.lightness() < 128
        p.fillRect(ev.rect(), bg)
        r = ev.rect()
        t0, t1 = self.t_at(r.left()) - 1, self.t_at(r.right()) + 1
        h = self.height()
        y_sec = self.ROW_RULER
        y_notes = y_sec + self.ROW_SECTIONS
        y_voc = y_notes + self.ROW_NOTES
        y_ref = y_voc + self.ROW_VOCALS

        # guideline zones
        if self.silence_end > 0:
            p.fillRect(QRectF(self.x(0), 0, self.silence_end * self.pps, h),
                       QColor(229, 72, 77, 40 if dark else 28))
        if self.bars_end > self.silence_end:
            p.fillRect(QRectF(self.x(self.silence_end), 0, (self.bars_end - self.silence_end) * self.pps, h),
                       QColor(245, 165, 36, 40 if dark else 30))

        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1.5))
        p.setFont(small)
        grid_c = QColor(fg)
        grid_c.setAlpha(35)
        bar_c = QColor(fg)
        bar_c.setAlpha(110)

        # beat grid
        bm = self.beatmap
        if bm and bm.beats:
            mnum = 0
            for t, is_m in zip(bm.beats, bm.measure_flags):
                if is_m:
                    mnum += 1
                if t < t0 or t > t1:
                    continue
                X = self.x(t)
                if is_m:
                    p.setPen(QPen(bar_c, 1))
                    p.drawLine(QPointF(X, 12), QPointF(X, h))
                    p.drawText(QPointF(X + 3, 11), str(mnum))
                else:
                    p.setPen(QPen(grid_c, 1))
                    p.drawLine(QPointF(X, y_sec), QPointF(X, h))
            # sections
            sec_font = QFont(small)
            sec_font.setBold(True)
            p.setFont(sec_font)
            for t, name in bm.sections:
                if t1 >= t >= t0 - 30:
                    p.setPen(QPen(QColor("#3e9bf5"), 1))
                    p.drawText(QPointF(self.x(t) + 3, y_sec + 14), name)
            p.setFont(small)
            # notes
            for t, sus, string in bm.notes:
                if t + sus < t0 or t > t1:
                    continue
                c = QColor(STRING_COLORS[string % 6] if string >= 0 else STRING_COLORS[6])
                yy = y_notes + 2 + (max(0, string) % 6) * 5
                p.fillRect(QRectF(self.x(t), yy, max(2.0, sus * self.pps), 3), c)
        else:
            # plain seconds ruler
            p.setPen(QPen(grid_c, 1))
            s = int(max(0, t0))
            while s <= t1:
                X = self.x(s)
                p.drawLine(QPointF(X, 12), QPointF(X, h))
                p.drawText(QPointF(X + 3, 11), f"{s}s")
                s += 1 if self.pps > 40 else 5

        # labels
        p.setPen(QPen(fg, 1))
        lab = QColor(fg)
        lab.setAlpha(140)
        p.setPen(lab)
        vis_x = r.left() + 4
        p.drawText(QPointF(vis_x, y_notes + 36), "chart notes")
        p.drawText(QPointF(vis_x, y_voc + 12), "Lyridan")
        if self.reference:
            p.drawText(QPointF(vis_x, y_ref + 12), "reference")

        self._draw_vocals(p, self.vocals, y_voc + 16, QColor("#46a758"), t0, t1, small)
        if self.reference:
            self._draw_vocals(p, self.reference, y_ref + 16, QColor("#8e4ec6"), t0, t1, small)
        p.end()

    def _draw_vocals(self, p: QPainter, entries, y, color, t0, t1, font):
        fm = QFontMetrics(font)
        row_end = [-1e9, -1e9]  # stagger labels on two text rows when they would overlap
        for e in entries:
            if e.time + e.length < t0 or e.time > t1:
                continue
            X = self.x(e.time)
            w = max(3.0, e.length * self.pps)
            c = QColor(color)
            c.setAlpha(170)
            p.fillRect(QRectF(X, y, w, 10), c)
            p.setPen(QPen(color.darker(130), 1))
            p.drawLine(QPointF(X, y - 3), QPointF(X, y + 24))
            txt = e.lyric
            tw = fm.horizontalAdvance(txt) + 4
            row = 0 if X >= row_end[0] else (1 if X >= row_end[1] else (0 if row_end[0] <= row_end[1] else 1))
            row_end[row] = X + tw
            p.setPen(self.palette().text().color())
            p.drawText(QPointF(X + 2, y + 23 + row * 14), txt)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            factor = 1.2 if ev.angleDelta().y() > 0 else 1 / 1.2
            self.set_zoom(self.pps * factor)
            ev.accept()
        else:
            ev.ignore()

    def mouseMoveEvent(self, ev):
        t = self.t_at(ev.position().x())
        hit = None
        for e in self.vocals + self.reference:
            if e.time - 0.03 <= t <= e.time + max(e.length, 0.08):
                hit = e
                break
        if hit:
            QToolTip.showText(ev.globalPosition().toPoint(), f"{hit.lyric}\n{hit.time:.3f}s  len {hit.length:.3f}s", self)
        else:
            QToolTip.hideText()


class TimelineView(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = TimelineCanvas()
        self.setWidget(self.canvas)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            self.canvas.wheelEvent(ev)
            return
        # plain wheel scrolls horizontally
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - ev.angleDelta().y())
        ev.accept()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.canvas.view_h = self.viewport().height()
        self.canvas._resize()

    def scroll_to_time(self, t: float):
        self.horizontalScrollBar().setValue(int(self.canvas.x(t) - 60))
