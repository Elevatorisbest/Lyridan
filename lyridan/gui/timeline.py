"""Timeline: beat grid, sections, waveform, chart notes, generated/reference vocals and a playhead.

All times on the canvas are *chart* seconds (what ends up in the XML).
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QScrollArea, QToolTip, QWidget

from ..parsers.rsxml import Beatmap, VocalEntry

STRING_COLORS = ["#e5484d", "#f5d90a", "#3e9bf5", "#f76b15", "#46a758", "#8e4ec6", "#888888"]
LEFT = 20


class TimelineCanvas(QWidget):
    zoomChanged = Signal(float)
    seekRequested = Signal(float)          # chart seconds
    entryClicked = Signal(int)             # index into vocals

    ROW_RULER = 26
    ROW_SECTIONS = 20
    ROW_WAVE = 70
    ROW_NOTES = 34
    ROW_VOCALS = 66
    ROW_REF = 66

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pps = 90.0
        self.beatmap: Optional[Beatmap] = None
        self.vocals: List[VocalEntry] = []
        self.reference: List[VocalEntry] = []
        self.silence_end = 0.0
        self.bars_end = 0.0
        self.duration = 60.0
        self.view_h = 0
        self.playhead: Optional[float] = None
        self.peaks: Optional[np.ndarray] = None      # (n, 2) min/max per bin
        self.peaks_bps = 100.0
        self.audio_shift = 0.0                        # chart time = audio time + shift
        self.accent = QColor("#46a758")
        self.active_index = -1
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._resize()

    # ------------------------------------------------------------------ data
    def _height(self):
        h = self.ROW_RULER + self.ROW_SECTIONS + self.ROW_NOTES + self.ROW_VOCALS + 12
        if self.peaks is not None:
            h += self.ROW_WAVE
        if self.reference:
            h += self.ROW_REF
        return max(self.view_h, h)

    def set_data(self, beatmap, vocals, reference, silence_end, bars_end):
        self.beatmap = beatmap
        self.vocals = vocals or []
        self.reference = reference or []
        self.silence_end = silence_end
        self.bars_end = bars_end
        self._update_duration()
        self.update()

    def set_audio(self, peaks: Optional[np.ndarray], bins_per_second: float, shift: float):
        self.peaks = peaks if peaks is not None and len(peaks) else None
        self.peaks_bps = bins_per_second
        self.audio_shift = shift
        self._update_duration()
        self.update()

    def _update_duration(self):
        ends = [10.0]
        bm = self.beatmap
        if bm and bm.beats:
            ends.append(bm.song_length or bm.beats[-1])
        if self.vocals:
            ends.append(self.vocals[-1].time + self.vocals[-1].length)
        if self.reference:
            ends.append(self.reference[-1].time + self.reference[-1].length)
        if self.peaks is not None:
            ends.append(len(self.peaks) / self.peaks_bps + self.audio_shift)
        self.duration = max(ends) + 3
        self._resize()

    def set_zoom(self, pps: float, anchor_t: Optional[float] = None):
        self.pps = max(8.0, min(1000.0, pps))
        self._resize()
        self.update()
        self.zoomChanged.emit(self.pps)

    def _resize(self):
        self.setFixedSize(QSize(int(self.duration * self.pps) + 2 * LEFT, self._height()))

    def x(self, t: float) -> float:
        return LEFT + t * self.pps

    def t_at(self, x: float) -> float:
        return (x - LEFT) / self.pps

    def set_playhead(self, t: Optional[float], active_index: int = -1):
        old = self.playhead
        self.playhead = t
        self.active_index = active_index
        # repaint only the strips that changed (cheap during playback)
        for v in (old, t):
            if v is not None:
                X = int(self.x(v))
                self.update(X - 300, 0, 600, self.height())

    # ------------------------------------------------------------------ rows
    def _rows(self):
        y = self.ROW_RULER
        rows = {"sections": y}
        y += self.ROW_SECTIONS
        if self.peaks is not None:
            rows["wave"] = y
            y += self.ROW_WAVE
        rows["notes"] = y
        y += self.ROW_NOTES
        rows["vocals"] = y
        y += self.ROW_VOCALS
        if self.reference:
            rows["ref"] = y
        return rows

    # ------------------------------------------------------------------ painting
    def paintEvent(self, ev):
        p = QPainter(self)
        pal = self.palette()
        bg = pal.base().color()
        fg = pal.text().color()
        dark = bg.lightness() < 128
        r = ev.rect()
        p.fillRect(r, bg)
        t0, t1 = self.t_at(r.left()) - 1, self.t_at(r.right()) + 1
        h = self.height()
        rows = self._rows()

        # guideline zones
        if self.silence_end > 0:
            p.fillRect(QRectF(self.x(0), 0, self.silence_end * self.pps, h), QColor(229, 72, 77, 38 if dark else 26))
        if self.bars_end > self.silence_end:
            p.fillRect(QRectF(self.x(self.silence_end), 0, (self.bars_end - self.silence_end) * self.pps, h),
                       QColor(245, 165, 36, 38 if dark else 30))

        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1.5))
        p.setFont(small)
        grid_c = QColor(fg)
        grid_c.setAlpha(28)
        bar_c = QColor(fg)
        bar_c.setAlpha(100)

        # ruler background
        ruler_bg = QColor(fg)
        ruler_bg.setAlpha(14)
        p.fillRect(QRectF(r.left(), 0, r.width(), self.ROW_RULER), ruler_bg)

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
                    p.drawLine(QPointF(X, 2), QPointF(X, h))
                    p.drawText(QPointF(X + 3, 12), str(mnum))
                else:
                    p.setPen(QPen(grid_c, 1))
                    p.drawLine(QPointF(X, self.ROW_RULER - 6), QPointF(X, h))
            sec_font = QFont(small)
            sec_font.setBold(True)
            p.setFont(sec_font)
            p.setPen(QPen(QColor("#3e9bf5"), 1))
            for t, name in bm.sections:
                if t1 >= t >= t0 - 30:
                    p.drawText(QPointF(self.x(t) + 3, rows["sections"] + 14), name)
            p.setFont(small)
        # seconds along the ruler
        lab = QColor(fg)
        lab.setAlpha(130)
        p.setPen(lab)
        step = 1 if self.pps >= 60 else (5 if self.pps >= 15 else 10)
        s = int(max(0, t0) // step * step)
        while s <= t1:
            X = self.x(s)
            p.drawLine(QPointF(X, self.ROW_RULER - 4), QPointF(X, self.ROW_RULER))
            m, sec = divmod(s, 60)
            p.drawText(QPointF(X + 2, self.ROW_RULER - 4), f"{m}:{sec:02d}")
            s += step

        # waveform
        if "wave" in rows and self.peaks is not None:
            y0 = rows["wave"]
            mid = y0 + self.ROW_WAVE / 2
            amp = self.ROW_WAVE / 2 - 4
            wc = QColor(fg)
            wc.setAlpha(110)
            a_t0 = max(0.0, t0 - self.audio_shift)
            a_t1 = max(0.0, t1 - self.audio_shift)
            i0 = int(a_t0 * self.peaks_bps)
            i1 = min(len(self.peaks), int(a_t1 * self.peaks_bps) + 1)
            if i1 > i0:
                seg = self.peaks[i0:i1]
                # one vertical line per pixel column
                xs = self.x(np.arange(i0, i1) / self.peaks_bps + self.audio_shift)
                cols = np.floor(xs).astype(int)
                p.setPen(QPen(wc, 1))
                last_c, lo, hi = None, 0.0, 0.0
                for cx, (mn, mx) in zip(cols, seg):
                    if cx != last_c:
                        if last_c is not None:
                            p.drawLine(QPointF(last_c, mid - hi * amp), QPointF(last_c, mid - lo * amp))
                        last_c, lo, hi = cx, mn, mx
                    else:
                        lo, hi = min(lo, mn), max(hi, mx)
                if last_c is not None:
                    p.drawLine(QPointF(last_c, mid - hi * amp), QPointF(last_c, mid - lo * amp))
            p.setPen(lab)
            p.drawText(QPointF(r.left() + 4, y0 + 12), "audio")

        # chart notes
        y_notes = rows["notes"]
        if bm:
            for t, sus, string in bm.notes:
                if t + sus < t0 or t > t1:
                    continue
                c = QColor(STRING_COLORS[string % 6] if string >= 0 else STRING_COLORS[6])
                yy = y_notes + 3 + (max(0, string) % 6) * 5
                p.fillRect(QRectF(self.x(t), yy, max(2.0, sus * self.pps), 3), c)
        p.setPen(lab)
        p.drawText(QPointF(r.left() + 4, y_notes + 32), "chart notes")

        p.drawText(QPointF(r.left() + 4, rows["vocals"] + 12), "Lyridan vocals")
        self._draw_vocals(p, self.vocals, rows["vocals"] + 16, self.accent, t0, t1, small, True)
        if "ref" in rows:
            p.setPen(lab)
            p.drawText(QPointF(r.left() + 4, rows["ref"] + 12), "reference")
            self._draw_vocals(p, self.reference, rows["ref"] + 16, QColor("#8e4ec6"), t0, t1, small, False)

        # playhead
        if self.playhead is not None and t0 <= self.playhead <= t1:
            X = self.x(self.playhead)
            ph = QColor("#ff4d4d")
            p.setPen(QPen(ph, 2))
            p.drawLine(QPointF(X, 0), QPointF(X, h))
            p.setBrush(ph)
            p.drawPolygon(QPolygonF([QPointF(X - 6, 0), QPointF(X + 6, 0), QPointF(X, 8)]))
        p.end()

    def _draw_vocals(self, p: QPainter, entries, y, color, t0, t1, font, mark_active):
        fm = QFontMetrics(font)
        row_end = [-1e9, -1e9]
        text_c = self.palette().text().color()
        for i, e in enumerate(entries):
            if e.time + e.length < t0 or e.time > t1:
                continue
            X = self.x(e.time)
            w = max(3.0, e.length * self.pps)
            c = QColor(color)
            active = mark_active and i == self.active_index
            c.setAlpha(255 if active else 165)
            p.fillRect(QRectF(X, y, w, 10), c)
            p.setPen(QPen(color.darker(130) if not active else QColor("#ff4d4d"), 1))
            p.drawLine(QPointF(X, y - 3), QPointF(X, y + 24))
            if e.lyric.endswith("+"):   # Rocksmith line break after this syllable
                p.setPen(QPen(QColor(color), 2))
                p.drawLine(QPointF(X + w + 2, y - 4), QPointF(X + w + 2, y + 14))
            txt = e.lyric
            tw = fm.horizontalAdvance(txt) + 4
            row = 0 if X >= row_end[0] else (1 if X >= row_end[1] else (0 if row_end[0] <= row_end[1] else 1))
            row_end[row] = X + tw
            p.setPen(QColor("#ff4d4d") if active else text_c)
            p.drawText(QPointF(X + 2, y + 23 + row * 14), txt)

    # ------------------------------------------------------------------ interaction
    def _hit(self, pos) -> int:
        rows = self._rows()
        y = pos.y()
        if not (rows["vocals"] <= y < rows["vocals"] + self.ROW_VOCALS):
            return -1
        t = self.t_at(pos.x())
        for i, e in enumerate(self.vocals):
            if e.time - 0.03 <= t <= e.time + max(e.length, 0.1):
                return i
        return -1

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            factor = 1.2 if ev.angleDelta().y() > 0 else 1 / 1.2
            self.set_zoom(self.pps * factor)
            ev.accept()
        else:
            ev.ignore()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            i = self._hit(ev.position())
            if i >= 0:
                self.entryClicked.emit(i)
                self.seekRequested.emit(self.vocals[i].time)
            else:
                self.seekRequested.emit(max(0.0, self.t_at(ev.position().x())))
            self._dragging = True

    def mouseMoveEvent(self, ev):
        if getattr(self, "_dragging", False) and ev.buttons() & Qt.LeftButton and ev.position().y() < self.ROW_RULER:
            self.seekRequested.emit(max(0.0, self.t_at(ev.position().x())))
            return
        i = self._hit(ev.position())
        if i >= 0:
            e = self.vocals[i]
            QToolTip.showText(ev.globalPosition().toPoint(), f"{e.lyric}\n{e.time:.3f}s  length {e.length:.3f}s", self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, ev):
        self._dragging = False


class TimelineView(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = TimelineCanvas()
        self.setWidget(self.canvas)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            # zoom around the mouse position
            c = self.canvas
            mouse_x = ev.position().x()
            t = c.t_at(self.horizontalScrollBar().value() + mouse_x)
            c.wheelEvent(ev)
            self.horizontalScrollBar().setValue(int(c.x(t) - mouse_x))
            return
        bar = self.horizontalScrollBar()
        delta = ev.angleDelta().y() or ev.angleDelta().x()
        bar.setValue(bar.value() - delta)
        ev.accept()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.canvas.view_h = self.viewport().height()
        self.canvas._resize()

    def scroll_to_time(self, t: float, margin: float = 60):
        self.horizontalScrollBar().setValue(int(self.canvas.x(t) - margin))

    def ensure_visible_time(self, t: float):
        """Page-follow the playhead during playback."""
        bar = self.horizontalScrollBar()
        X = self.canvas.x(t)
        w = self.viewport().width()
        if X < bar.value() + 40 or X > bar.value() + w - 80:
            bar.setValue(int(X - w * 0.25))
