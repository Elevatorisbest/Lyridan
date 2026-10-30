"""Timeline: beat grid, sections, waveform, chart notes, generated/reference vocals and a playhead.

All times on the canvas are *chart* seconds (what ends up in the XML).

Layout (top to bottom): ruler (bars + time), sections, audio waveform, chart notes,
then for the Lyridan vocals (and the optional reference) a *lines* row with the
whole Rocksmith line as text and a *syllables* row with one bar per syllable.
Row names live in a fixed gutter on the left so they never smear while scrolling.

Keyboard (only while the timeline has focus - click it; Esc leaves):
  ← →           move the playhead (step set in Options; speeds up while held)
  Shift + ← →   4× bigger steps          Ctrl/Alt + ← →  previous / next lyric line
  PgUp / PgDn   previous / next section  Home / End      start / end of the song
  ↑ ↓           zoom in / out            Space           play / pause
  Enter         play the current line    F               fit the whole song
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QScrollArea, QToolTip, QWidget

from ..parsers.rsxml import Beatmap, VocalEntry

STRING_COLORS = ["#e5484d", "#f5d90a", "#3e9bf5", "#f76b15", "#46a758", "#8e4ec6", "#888888"]
LEFT = 20              # canvas padding before t = 0
GUTTER = 96            # fixed row-name column (overlay)
REF_COLOR = QColor("#a172e0")

SECTION_NAMES = {
    "noguitar": "No guitar", "prechorus": "Pre-chorus", "postchorus": "Post-chorus", "modverse": "Verse (mod.)",
    "modchorus": "Chorus (mod.)", "postvs": "Post-verse", "postbrdg": "Post-bridge", "fadein": "Fade in",
    "fadeout": "Fade out", "buildup": "Build-up",
}
SECTION_COLORS = {
    "intro": "#5b8def", "verse": "#46a758", "prechorus": "#d6a10a", "chorus": "#e5484d", "postchorus": "#e5484d",
    "bridge": "#8e4ec6", "solo": "#f76b15", "outro": "#5b8def", "noguitar": "#888888", "breakdown": "#12a594",
    "riff": "#f76b15", "interlude": "#12a594", "hook": "#e5484d",
}

ARROW_STEPS = {            # Options -> Timeline: what one arrow-key press moves
    "0.1s": "0.1 s", "quarter": "1/4 beat", "half": "1/2 beat", "beat": "1 beat", "bar": "1 bar", "1s": "1 s",
}


@dataclass
class Section:
    start: float
    end: float
    key: str
    label: str            # "Verse 2"

    @property
    def color(self) -> QColor:
        return QColor(SECTION_COLORS.get(self.key.lower().rstrip("0123456789"), "#3e9bf5"))


@dataclass
class LyricLine:
    first: int            # index of the first entry
    last: int             # index of the last entry
    start: float
    end: float
    text: str


def sections_of(bm: Optional[Beatmap], song_end: float) -> List[Section]:
    if not bm or not bm.sections:
        return []
    out: List[Section] = []
    counts: dict = {}
    items = sorted(bm.sections)
    for i, (t, name) in enumerate(items):
        key = name.strip()
        base = SECTION_NAMES.get(key.lower(), key[:1].upper() + key[1:])
        counts[base] = counts.get(base, 0) + 1
        end = items[i + 1][0] if i + 1 < len(items) else max(song_end, t + 1.0)
        out.append(Section(t, end, key, base))
    # number repeated names (Verse 1, Verse 2...) only when they repeat
    seen: dict = {}
    for s in out:
        if counts[s.label] > 1:
            seen[s.label] = seen.get(s.label, 0) + 1
            s.label = f"{s.label} {seen[s.label]}"
    return out


def display_syllable(lyric: str) -> str:
    """Rocksmith markup removed: 'Eve-' -> 'Eve', 'ooh+' -> 'ooh'."""
    t = lyric
    if t.endswith("+"):
        t = t[:-1]
    if t.endswith("-"):
        t = t[:-1]
    return t


def lines_of(entries: List[VocalEntry]) -> List[LyricLine]:
    out: List[LyricLine] = []
    start = 0
    text = ""
    for i, e in enumerate(entries):
        lyr = e.lyric
        plus = lyr.endswith("+")
        core = lyr[:-1] if plus else lyr
        joined = core.endswith("-")
        text += display_syllable(lyr) + ("" if joined else " ")
        if plus or i == len(entries) - 1:
            out.append(LyricLine(start, i, entries[start].time,
                                 max(e.time + e.length for e in entries[start:i + 1]), text.strip()))
            start, text = i + 1, ""
    return out


class TimelineCanvas(QWidget):
    zoomChanged = Signal(float)
    seekRequested = Signal(float)          # chart seconds (mouse)
    navRequested = Signal(float)           # chart seconds (keyboard: seek + keep visible)
    entryClicked = Signal(int)             # index into vocals
    playLineRequested = Signal(float)      # play from here
    zoomKeyRequested = Signal(float)       # zoom factor around the playhead
    fitRequested = Signal()
    leaveRequested = Signal()              # Esc: give the keyboard back to the rest of the window
    focusChanged = Signal(bool)

    ROW_RULER = 26
    ROW_SECTIONS = 20
    ROW_WAVE = 46
    ROW_NOTES = 33
    ROW_LINES = 22
    ROW_SYLLS = 32

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pps = 90.0
        self.beatmap: Optional[Beatmap] = None
        self.vocals: List[VocalEntry] = []
        self.reference: List[VocalEntry] = []
        self.lines: List[LyricLine] = []
        self.ref_lines: List[LyricLine] = []
        self.sections: List[Section] = []
        self.silence_end = 0.0
        self.bars_end = 0.0
        self.duration = 60.0
        self.view_h = 0
        self.playhead: Optional[float] = None
        self.peaks: Optional[np.ndarray] = None      # (n, 2) min/max per bin
        self.peaks_bps = 100.0
        self.audio_shift = 0.0                        # chart time = audio time + shift
        self.accent = QColor("#46a758")
        self.wave_color: Optional[QColor] = None      # theme colour for the waveform (None = text colour)
        self.playhead_color = QColor("#ff4d4d")       # playhead + the syllable being sung (contrasts the accent)
        self.daw: Optional[dict] = None               # DAW-style theme colours (rulers, clips, lanes) or None
        self.clip_name = ""                           # audio file name shown on the waveform clip (DAW style)
        self.active_index = -1
        self.arrow_step = "beat"
        self.accelerate = True
        self._held = 0
        self._drag = None                             # ("scrub", ) | ("pan", x0, scroll0)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._resize()

    # ------------------------------------------------------------------ data
    def _height(self):
        h = self.ROW_RULER + self.ROW_SECTIONS + self.ROW_NOTES + self.ROW_LINES + self.ROW_SYLLS + 10
        if self.peaks is not None:
            h += self.ROW_WAVE
        if self.reference:
            h += self.ROW_LINES + self.ROW_SYLLS
        return max(self.view_h, h)

    def set_data(self, beatmap, vocals, reference, silence_end, bars_end):
        self.beatmap = beatmap
        self.vocals = vocals or []
        self.reference = reference or []
        self.lines = lines_of(self.vocals)
        self.ref_lines = lines_of(self.reference)
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
        self.sections = sections_of(bm, self.duration - 3)
        self._resize()

    def set_zoom(self, pps: float):
        self.pps = max(4.0, min(1200.0, pps))
        self._resize()
        self.update()
        self.zoomChanged.emit(self.pps)

    def _resize(self):
        self.setFixedSize(QSize(int(self.duration * self.pps) + 2 * LEFT + GUTTER, self._height()))

    def x(self, t: float) -> float:
        return GUTTER + LEFT + t * self.pps

    def t_at(self, x: float) -> float:
        return (x - GUTTER - LEFT) / self.pps

    def set_playhead(self, t: Optional[float], active_index: int = -1):
        old = self.playhead
        old_active = self.active_index
        self.playhead = t
        self.active_index = active_index
        for v in (old, t):           # repaint only the strips that changed (cheap during playback)
            if v is not None:
                X = int(self.x(v))
                self.update(X - 12, 0, 24, self.height())
        if old_active != active_index:   # the highlighted syllable / line changed
            for i in (old_active, active_index):
                if 0 <= i < len(self.vocals):
                    ln = self._line_of(i)
                    a = self.x(ln.start if ln else self.vocals[i].time) - 4
                    b = self.x(ln.end if ln else self.vocals[i].time + self.vocals[i].length) + 200
                    self.update(int(a), 0, int(b - a), self.height())

    def _line_of(self, entry: int) -> Optional[LyricLine]:
        firsts = [l.first for l in self.lines]
        k = bisect.bisect_right(firsts, entry) - 1
        return self.lines[k] if 0 <= k < len(self.lines) else None

    # ------------------------------------------------------------------ rows
    def rows(self) -> dict:
        """name -> (y, height); also used by the gutter overlay."""
        y = self.ROW_RULER
        rows = {"ruler": (0, self.ROW_RULER), "sections": (y, self.ROW_SECTIONS)}
        y += self.ROW_SECTIONS
        if self.peaks is not None:
            rows["wave"] = (y, self.ROW_WAVE)
            y += self.ROW_WAVE
        rows["notes"] = (y, self.ROW_NOTES)
        y += self.ROW_NOTES
        rows["lines"] = (y, self.ROW_LINES)
        y += self.ROW_LINES
        rows["sylls"] = (y, self.ROW_SYLLS)
        y += self.ROW_SYLLS
        if self.reference:
            rows["ref_lines"] = (y, self.ROW_LINES)
            y += self.ROW_LINES
            rows["ref_sylls"] = (y, self.ROW_SYLLS)
        return rows

    # ------------------------------------------------------------------ painting
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        pal = self.palette()
        bg = pal.base().color()
        fg = pal.text().color()
        dark = bg.lightness() < 128
        r = ev.rect()
        d = self.daw
        if d:
            bg = QColor(d["text_bg"])
        p.fillRect(r, bg)
        t0, t1 = self.t_at(r.left()) - 1, self.t_at(r.right()) + 1
        h = self.height()
        rows = self.rows()
        rulers_h = self.ROW_RULER + self.ROW_SECTIONS      # ruler + markers lanes

        if d:
            # DAW look: rulers on their own lighter strip, tracks separated by dark lane lines
            p.fillRect(QRectF(r.left(), 0, r.width(), rulers_h), QColor(d["ruler_bg"]))
            lane = QColor(d["lane_line"])
            for name, (y, rh) in rows.items():
                if name in ("lines", "ref_lines"):        # a track's lines + syllables form one lane
                    continue
                p.fillRect(QRectF(r.left(), y + rh - 1, r.width(), 1), lane)
        else:
            # alternate row shading so the rows are easy to tell apart
            shade = QColor(fg)
            shade.setAlpha(9)
            for name in ("sections", "notes", "sylls", "ref_sylls"):
                if name in rows:
                    y, rh = rows[name]
                    p.fillRect(QRectF(r.left(), y, r.width(), rh), shade)

        # intro silence / empty bars
        top = rulers_h if d else 0
        if self.silence_end > 0:
            p.fillRect(QRectF(self.x(0), top, self.silence_end * self.pps, h - top),
                       QColor(229, 72, 77, (22 if dark else 18) if d else (34 if dark else 22)))
        if self.bars_end > self.silence_end:
            p.fillRect(QRectF(self.x(self.silence_end), top, (self.bars_end - self.silence_end) * self.pps, h - top),
                       QColor(245, 165, 36, (22 if dark else 20) if d else (34 if dark else 26)))

        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1.5))
        p.setFont(small)
        fm = QFontMetrics(small)
        grid_c = QColor(fg)
        grid_c.setAlpha(22)
        bar_c = QColor(fg)
        bar_c.setAlpha(80)
        lab = QColor(fg)
        lab.setAlpha(140)

        if d:
            grid_c = QColor(d["grid_beat"])
            bar_c = QColor(d["grid_bar"])
            lab = QColor(d["ruler_fg"])
            half = self.ROW_RULER // 2                  # Bars|Beats on top, Min:Secs underneath
            p.fillRect(QRectF(r.left(), half, r.width(), 1), QColor(d["lane_line"]))
        else:
            ruler_bg = QColor(fg)
            ruler_bg.setAlpha(16)
            p.fillRect(QRectF(r.left(), 0, r.width(), self.ROW_RULER), ruler_bg)

        bm = self.beatmap
        if bm and bm.beats:
            # measure numbers every bar, or every 2/4/8 bars when zoomed out
            mlen = bm.measure_duration(0) if hasattr(bm, "measure_duration") else 2.0
            every = 1
            while mlen * every * self.pps < 28:
                every *= 2
            mnum = 0
            bold = QFont(small)
            bold.setBold(True)
            for t, is_m in zip(bm.beats, bm.measure_flags):
                if is_m:
                    mnum += 1
                if t < t0 or t > t1:
                    continue
                X = self.x(t)
                if d:
                    if is_m:
                        p.setPen(QPen(bar_c, 1))
                        p.drawLine(QPointF(X, rulers_h), QPointF(X, h))
                        p.setPen(QPen(lab, 1))
                        p.drawLine(QPointF(X, 1), QPointF(X, half - 1))
                        if (mnum - 1) % every == 0:
                            p.setFont(bold)
                            p.drawText(QPointF(X + 3, half - 3), str(mnum))
                            p.setFont(small)
                    elif self.pps * mlen / 4 > 6:
                        p.setPen(QPen(grid_c, 1))
                        p.drawLine(QPointF(X, rulers_h), QPointF(X, h))
                        p.setPen(QPen(bar_c, 1))
                        p.drawLine(QPointF(X, half - 4), QPointF(X, half - 1))
                elif is_m:
                    p.setPen(QPen(bar_c, 1))
                    p.drawLine(QPointF(X, 2), QPointF(X, h))
                    if (mnum - 1) % every == 0:
                        p.setFont(bold)
                        p.setPen(lab)
                        p.drawText(QPointF(X + 3, 12), str(mnum))
                        p.setFont(small)
                elif self.pps * mlen / 4 > 6:
                    p.setPen(QPen(grid_c, 1))
                    p.drawLine(QPointF(X, self.ROW_RULER - 6), QPointF(X, h))
        # time labels along the bottom of the ruler
        p.setPen(lab)
        step = next(s for s in (1, 2, 5, 10, 15, 30, 60, 120) if s * self.pps >= 56)
        s = int(max(0, t0) // step * step)
        while s <= t1:
            X = self.x(s)
            p.drawLine(QPointF(X, self.ROW_RULER - 5), QPointF(X, self.ROW_RULER))
            m, sec = divmod(s, 60)
            p.drawText(QPointF(X + 3, self.ROW_RULER - 4), f"{m}:{sec:02d}")
            s += step

        # sections: coloured blocks with their names (DAW look: a marker ruler)
        y, rh = rows["sections"]
        sec_font = QFont(small)
        sec_font.setBold(True)
        sfm = QFontMetrics(sec_font)
        p.setFont(sec_font)
        vis_left = self.visibleRegion().boundingRect().left() + GUTTER
        if d:
            self._draw_markers(p, y, rh, t0, t1, sfm, vis_left)
        for sct in ([] if d else self.sections):
            if sct.end < t0 or sct.start > t1:
                continue
            a, b = self.x(sct.start), self.x(sct.end)
            c = QColor(sct.color)
            c.setAlpha(70 if dark else 55)
            p.fillRect(QRectF(a, y + 2, b - a - 1, rh - 4), c)
            c.setAlpha(255)
            p.fillRect(QRectF(a, y + 2, 3, rh - 4), c)
            p.setPen(fg)
            ta = max(a, min(vis_left, b - sfm.horizontalAdvance(sct.label) - 12))   # label sticks to the left edge
            txt = sfm.elidedText(sct.label, Qt.ElideRight, int(b - ta - 10))
            p.drawText(QRectF(ta + 6, y, b - ta - 8, rh), Qt.AlignVCenter | Qt.AlignLeft, txt)
        p.setFont(small)

        # waveform
        if "wave" in rows and self.peaks is not None:
            y0, rh = rows["wave"]
            mid = y0 + rh / 2
            amp = rh / 2 - 4
            wc = QColor(self.wave_color) if self.wave_color is not None else QColor(fg)
            wc.setAlpha(170 if self.wave_color is not None else 110)
            if d:
                y0, mid, amp, wc = self._draw_audio_clip(p, y0, rh, bg, small)
            a_t0 = max(0.0, t0 - self.audio_shift)
            a_t1 = max(0.0, t1 - self.audio_shift)
            i0 = int(a_t0 * self.peaks_bps)
            i1 = min(len(self.peaks), int(a_t1 * self.peaks_bps) + 1)
            if i1 > i0:
                seg = self.peaks[i0:i1]
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

        # chart notes (one lane per string)
        y_notes, nh = rows["notes"]
        if d and bm and bm.notes:
            a = self.x(bm.notes[0][0])
            b = self.x(max(t + sus for t, sus, _ in bm.notes))
            body = QColor(d["notes_clip"])
            body.setAlpha(38)
            p.fillRect(QRectF(a - 2, y_notes + 1, b - a + 4, nh - 3), body)
        if bm:
            for t, sus, string in bm.notes:
                if t + sus < t0 or t > t1:
                    continue
                c = QColor(STRING_COLORS[string % 6] if string >= 0 else STRING_COLORS[6])
                yy = y_notes + 3 + (max(0, string) % 6) * 5
                p.fillRect(QRectF(self.x(t), yy, max(2.0, sus * self.pps), 3), c)

        p.setRenderHint(QPainter.Antialiasing, True)
        self._draw_vocals(p, self.vocals, self.lines, rows["lines"], rows["sylls"], self.accent, t0, t1, small, True)
        if "ref_lines" in rows:
            self._draw_vocals(p, self.reference, self.ref_lines, rows["ref_lines"], rows["ref_sylls"], REF_COLOR,
                              t0, t1, small, False)

        # playhead
        if self.playhead is not None and t0 <= self.playhead <= t1:
            X = self.x(self.playhead)
            ph = QColor(self.playhead_color)
            p.setPen(QPen(ph, 1.5 if d else 2))
            p.drawLine(QPointF(X, 0), QPointF(X, h))
            p.setBrush(ph)
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([QPointF(X - 6, 0), QPointF(X + 6, 0), QPointF(X, 8)]))
        p.end()

    def _draw_vocals(self, p: QPainter, entries: List[VocalEntry], lines: List[LyricLine], line_row, syl_row,
                     color: QColor, t0, t1, font, live: bool):
        fg = self.palette().text().color()
        d = self.daw
        fm = QFontMetrics(font)
        active_line = self._line_of(self.active_index) if live and self.active_index >= 0 else None
        # --- lines: one block per Rocksmith line, with the whole line as text
        ly, lh = line_row
        vis_left = self.visibleRegion().boundingRect().left() + GUTTER
        bold = QFont(font)
        bold.setBold(True)
        bfm = QFontMetrics(bold)
        p.setFont(bold)
        for n, ln in enumerate(lines):
            if ln.end < t0 or ln.start > t1:
                continue
            a, b = self.x(ln.start), self.x(ln.end)
            c = QColor(color)
            is_active = active_line is not None and ln.first == active_line.first
            path = QPainterPath()
            if d:                                      # a clip: solid body, darker outline, dark name text
                c = c.lighter(118) if is_active else (c if n % 2 == 0 else c.darker(112))
                path.addRoundedRect(QRectF(a + 0.5, ly + 1.5, max(4.0, b - a - 1), lh - 3), 2, 2)
                p.fillPath(path, c)
                p.setPen(QPen(QColor(d["lane_line"]) if not is_active else QColor(self.playhead_color), 1))
                p.drawPath(path)
            else:
                c.setAlpha(150 if is_active else (70 if n % 2 == 0 else 45))
                path.addRoundedRect(QRectF(a, ly + 3, max(4.0, b - a), lh - 6), 4, 4)
                p.fillPath(path, c)
            ta = max(a, min(vis_left, b - 60))          # keep the start of the text in view
            txt = bfm.elidedText(ln.text, Qt.ElideRight, int(b - ta - 8))
            if b - ta > 24:
                p.setPen(QColor(d["clip_text"]) if d else fg)
                p.drawText(QRectF(ta + 5, ly + 3, b - ta - 8, lh - 6), Qt.AlignVCenter | Qt.AlignLeft, txt)
        p.setFont(font)
        # --- syllables: a bar per syllable, text underneath (only when it fits, never overlapping)
        sy, sh = syl_row
        bar_y, bar_h = sy + 4, 9
        i0 = max(0, bisect.bisect_left([e.time for e in entries], t0 - 30) - 1)
        for i in range(i0, len(entries)):
            e = entries[i]
            if e.time > t1:
                break
            if e.time + e.length < t0 and (i + 1 >= len(entries) or entries[i + 1].time < t0):
                continue
            X = self.x(e.time)
            w = max(3.0, e.length * self.pps)
            nxt = entries[i + 1].time if i + 1 < len(entries) else e.time + e.length + 5
            room = (nxt - e.time) * self.pps - 4
            active = live and i == self.active_index
            c = QColor(self.playhead_color) if active else QColor(color)
            c.setAlpha(255 if active else 200)
            path = QPainterPath()
            if d:
                path.addRoundedRect(QRectF(X + 0.5, bar_y + 0.5, w - 1, bar_h), 1.5, 1.5)
                p.fillPath(path, c)
                p.setPen(QPen(QColor(d["lane_line"]), 1))
                p.drawPath(path)
            else:
                path.addRoundedRect(QRectF(X, bar_y, w, bar_h), 2.5, 2.5)
                p.fillPath(path, c)
            lyr = e.lyric
            core = lyr[:-1] if lyr.endswith("+") else lyr
            if core.endswith("-") and i + 1 < len(entries):     # same word continues: connect the bars
                c2 = QColor(color)
                c2.setAlpha(150)
                p.setPen(QPen(c2, 1.5))
                p.drawLine(QPointF(X + w, bar_y + bar_h / 2), QPointF(self.x(nxt), bar_y + bar_h / 2))
            if lyr.endswith("+"):                                 # end of a Rocksmith line
                p.setPen(QPen(QColor(color), 2))
                p.drawLine(QPointF(X + w + 2, bar_y - 3), QPointF(X + w + 2, bar_y + bar_h + 3))
            txt = display_syllable(lyr)
            if room > 10:
                txt = fm.elidedText(txt, Qt.ElideRight, int(room))
                if txt and txt != "…":
                    p.setPen(QColor(self.playhead_color) if active else fg)
                    p.drawText(QPointF(X + 1, bar_y + bar_h + 13), txt)

    # ------------------------------------------------------------------ DAW-style helpers
    def _draw_markers(self, p: QPainter, y: float, rh: float, t0: float, t1: float, sfm: QFontMetrics,
                      vis_left: float):
        """Sections as a marker ruler: a coloured flag at each start, the name beside it and a thin
        coloured strip along the bottom showing how far the section runs."""
        d = self.daw
        outline = QColor(d["lane_line"])
        text = QColor(d["ruler_fg"])
        for sct in self.sections:
            if sct.end < t0 or sct.start > t1:
                continue
            a, b = self.x(sct.start), self.x(sct.end)
            c = QColor(sct.color)
            strip = QColor(c)
            strip.setAlpha(110)
            p.fillRect(QRectF(a, y + rh - 5, b - a - 1, 3), strip)
            p.setPen(QPen(c.darker(150), 1))
            p.drawLine(QPointF(a, y + 2), QPointF(a, y + rh - 2))
            flag = QPolygonF([QPointF(a, y + 2), QPointF(a + 9, y + 2), QPointF(a + 9, y + 9),
                              QPointF(a + 4.5, y + 13), QPointF(a, y + 9)])
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setBrush(c)
            p.setPen(QPen(outline, 1))
            p.drawPolygon(flag)
            p.setRenderHint(QPainter.Antialiasing, False)
            p.setBrush(Qt.NoBrush)
            ta = max(a, min(vis_left, b - sfm.horizontalAdvance(sct.label) - 16))   # label sticks to the left
            txt = sfm.elidedText(sct.label, Qt.ElideRight, int(b - ta - 16))
            p.setPen(text)
            p.drawText(QRectF(ta + 12, y, b - ta - 14, rh - 4), Qt.AlignVCenter | Qt.AlignLeft, txt)

    def _draw_audio_clip(self, p: QPainter, y0: float, rh: float, bg: QColor, font: QFont):
        """Draws the audio as one clip (body, outline, name bar along the bottom) and returns the
        geometry for the waveform inside it: (top, middle, amplitude, waveform colour)."""
        d = self.daw
        col = QColor(self.wave_color) if self.wave_color is not None else QColor(self.accent)
        start = self.audio_shift
        end = self.audio_shift + len(self.peaks) / self.peaks_bps
        a, b = self.x(max(0.0, start)), self.x(end)
        name_h = 11
        body = QColor(
            int(bg.red() * 0.8 + col.red() * 0.2), int(bg.green() * 0.8 + col.green() * 0.2),
            int(bg.blue() * 0.8 + col.blue() * 0.2))
        rect = QRectF(a + 0.5, y0 + 1.5, b - a - 1, rh - 4)
        p.fillRect(rect, body)
        p.fillRect(QRectF(rect.left(), rect.bottom() - name_h, rect.width(), name_h), col)
        p.setPen(QPen(QColor(d["lane_line"]), 1))
        p.drawRect(rect)
        if self.clip_name:
            vis_left = self.visibleRegion().boundingRect().left() + GUTTER
            fm = QFontMetrics(font)
            ta = max(a, min(vis_left, b - fm.horizontalAdvance(self.clip_name) - 10))
            p.setPen(QColor("#000000") if col.lightness() > 140 else QColor("#ffffff"))
            p.drawText(QRectF(ta + 4, rect.bottom() - name_h, b - ta - 8, name_h), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(self.clip_name, Qt.ElideRight, int(max(0, b - ta - 8))))
        wave_top = y0 + 2
        wave_h = rh - 4 - name_h - 1
        wc = QColor(col) if bg.lightness() < 128 else col.darker(140)
        return wave_top, wave_top + wave_h / 2, wave_h / 2 - 2, wc

    # ------------------------------------------------------------------ hit tests
    def _row_at(self, y: float) -> str:
        for name, (ry, rh) in self.rows().items():
            if ry <= y < ry + rh:
                return name
        return ""

    def _hit(self, pos) -> int:
        """Vocal entry under the mouse (syllable row), else -1."""
        if self._row_at(pos.y()) != "sylls":
            return -1
        t = self.t_at(pos.x())
        times = [e.time for e in self.vocals]
        i = bisect.bisect_right(times, t + 0.03) - 1
        if 0 <= i < len(self.vocals):
            e = self.vocals[i]
            nxt = self.vocals[i + 1].time if i + 1 < len(self.vocals) else e.time + e.length
            if t <= max(e.time + max(e.length, 0.1), min(nxt, e.time + 0.4)):
                return i
        return -1

    def _line_hit(self, pos) -> Optional[LyricLine]:
        row = self._row_at(pos.y())
        if row not in ("lines", "ref_lines"):
            return None
        t = self.t_at(pos.x())
        for ln in (self.lines if row == "lines" else self.ref_lines):
            if ln.start - 0.05 <= t <= ln.end + 0.05:
                return ln
        return None

    def _section_hit(self, pos) -> Optional[Section]:
        if self._row_at(pos.y()) != "sections":
            return None
        t = self.t_at(pos.x())
        return next((s for s in self.sections if s.start <= t < s.end), None)

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, ev):
        self.setFocus(Qt.MouseFocusReason)
        pos = ev.position()
        if ev.button() in (Qt.MiddleButton, Qt.RightButton):
            sa = self._scroll_area()
            if sa:
                self._drag = ("pan", ev.globalPosition().x(), sa.horizontalScrollBar().value())
                self.setCursor(Qt.ClosedHandCursor)
            return
        if ev.button() != Qt.LeftButton:
            return
        sct = self._section_hit(pos)
        if sct is not None:
            self.seekRequested.emit(sct.start)
            return
        i = self._hit(pos)
        if i >= 0:
            self.entryClicked.emit(i)
            self.seekRequested.emit(self.vocals[i].time)
        else:
            ln = self._line_hit(pos)
            self.seekRequested.emit(ln.start if ln else max(0.0, self.t_at(pos.x())))
        self._drag = ("scrub",)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        ln = self._line_hit(ev.position())
        if ln is None:
            i = self._hit(ev.position())
            ln = self._line_of(i) if i >= 0 else None
        if ln is not None:
            self.playLineRequested.emit(ln.start)

    def mouseMoveEvent(self, ev):
        if self._drag and self._drag[0] == "pan":
            sa = self._scroll_area()
            if sa:
                sa.horizontalScrollBar().setValue(int(self._drag[2] - (ev.globalPosition().x() - self._drag[1])))
            return
        if self._drag and self._drag[0] == "scrub" and ev.buttons() & Qt.LeftButton:
            self.seekRequested.emit(max(0.0, self.t_at(ev.position().x())))
            return
        self._tooltip(ev)

    def _tooltip(self, ev):
        pos = ev.position()
        gp = ev.globalPosition().toPoint()
        i = self._hit(pos)
        if i >= 0:
            e = self.vocals[i]
            ln = self._line_of(i)
            QToolTip.showText(gp, f"<b>{display_syllable(e.lyric)}</b> &nbsp; {_fmt(e.time)} · {e.length:.3f} s"
                                  f"<br>Rocksmith text: <code>{e.lyric}</code>"
                                  + (f"<br><i>{ln.text}</i>" if ln else "")
                                  + "<br><small>Click: jump here · double-click: play this line</small>", self)
            return
        ln = self._line_hit(pos)
        if ln is not None:
            QToolTip.showText(gp, f"<b>{ln.text}</b><br>{_fmt(ln.start)} – {_fmt(ln.end)} · "
                                  f"{ln.last - ln.first + 1} syllables"
                                  "<br><small>Click: jump to the line · double-click: play it</small>", self)
            return
        sct = self._section_hit(pos)
        if sct is not None:
            QToolTip.showText(gp, f"<b>{sct.label}</b> ({sct.key})<br>{_fmt(sct.start)} – {_fmt(sct.end)}"
                                  "<br><small>Click: jump to the section</small>", self)
            return
        QToolTip.hideText()

    def mouseReleaseEvent(self, ev):
        if self._drag and self._drag[0] == "pan":
            self.unsetCursor()
        self._drag = None

    def _scroll_area(self) -> Optional["TimelineView"]:
        w = self.parentWidget()
        while w is not None and not isinstance(w, QScrollArea):
            w = w.parentWidget()
        return w

    # ------------------------------------------------------------------ keyboard
    def focusInEvent(self, ev):
        super().focusInEvent(ev)
        self.focusChanged.emit(True)

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        self._held = 0
        self.focusChanged.emit(False)

    def grid_times(self) -> List[float]:
        """Positions the arrow keys step through."""
        bm = self.beatmap
        step = self.arrow_step
        if step in ("0.1s", "1s") or not bm or len(bm.beats) < 2:
            d = 1.0 if step == "1s" else (0.1 if step == "0.1s" else 0.25)
            return list(np.arange(0.0, self.duration, d))
        if step == "bar":
            return list(bm.measure_starts)
        sub = {"quarter": 4, "half": 2}.get(step, 1)
        out = []
        for a, b in zip(bm.beats, bm.beats[1:]):
            out.extend(a + (b - a) * k / sub for k in range(sub))
        out.append(bm.beats[-1])
        return out

    def _step(self, t: float, n: int) -> float:
        """Move n grid points from t (snapping to the grid first)."""
        g = getattr(self, "_grid_cache", None)
        key = (self.arrow_step, id(self.beatmap), round(self.duration, 1))
        if g is None or g[0] != key:
            g = (key, self.grid_times())
            self._grid_cache = g
        pts = g[1]
        if not pts:
            return max(0.0, t + 0.25 * n)
        eps = 1e-3
        if n > 0:
            k = bisect.bisect_right(pts, t + eps) + n - 1
        else:
            k = bisect.bisect_left(pts, t - eps) + n
        k = max(0, min(len(pts) - 1, k))
        return max(0.0, pts[k])

    def keyPressEvent(self, ev):
        key, mods = ev.key(), ev.modifiers()
        t = self.playhead or 0.0
        if key in (Qt.Key_Left, Qt.Key_Right):
            sign = -1 if key == Qt.Key_Left else 1
            if mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
                self.navRequested.emit(self._line_target(t, sign))
            else:
                self._held = self._held + 1 if ev.isAutoRepeat() else 0
                mult = 1
                if self.accelerate:
                    mult = 1 if self._held < 8 else 2 if self._held < 20 else 4 if self._held < 40 else 8
                if mods & Qt.ShiftModifier:
                    mult *= 4
                self.navRequested.emit(self._step(t, sign * mult))
        elif key in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.navRequested.emit(self._section_target(t, -1 if key == Qt.Key_PageUp else 1))
        elif key == Qt.Key_Home:
            self.navRequested.emit(0.0)
        elif key == Qt.Key_End:
            self.navRequested.emit(max(0.0, self.duration - 3))
        elif key in (Qt.Key_Up, Qt.Key_Plus, Qt.Key_Equal):
            self.zoomKeyRequested.emit(1.25)
        elif key in (Qt.Key_Down, Qt.Key_Minus):
            self.zoomKeyRequested.emit(1 / 1.25)
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            ln = None
            if self.lines:
                k = bisect.bisect_right([l.start for l in self.lines], t + 1e-3) - 1
                ln = self.lines[max(0, k)]
            self.playLineRequested.emit(ln.start if ln else t)
        elif key == Qt.Key_F and not mods:
            self.fitRequested.emit()
        elif key == Qt.Key_Escape:
            self.leaveRequested.emit()
        else:
            super().keyPressEvent(ev)
            return
        ev.accept()     # navigation keys never reach other widgets

    def keyReleaseEvent(self, ev):
        if not ev.isAutoRepeat():
            self._held = 0
        ev.accept()

    def _line_target(self, t: float, sign: int) -> float:
        starts = [l.start for l in self.lines]
        if not starts:
            return t
        if sign > 0:
            k = bisect.bisect_right(starts, t + 1e-3)
            return starts[min(k, len(starts) - 1)]
        k = bisect.bisect_left(starts, t - 0.25) - 1      # a tap near a line start goes to the previous line
        return starts[max(0, k)]

    def _section_target(self, t: float, sign: int) -> float:
        starts = [s.start for s in self.sections]
        if not starts:
            return self._step(t, sign * 8)
        if sign > 0:
            k = bisect.bisect_right(starts, t + 1e-3)
            return starts[min(k, len(starts) - 1)]
        k = bisect.bisect_left(starts, t - 0.25) - 1
        return starts[max(0, k)]


def _fmt(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:06.3f}"


ROW_TITLES = {"ruler": "Bar · time", "sections": "Sections", "wave": "Audio", "notes": "Chart notes",
              "lines": "Lyric lines", "sylls": "Syllables", "ref_lines": "Reference lines",
              "ref_sylls": "Ref. syllables"}


class _Overlay(QWidget):
    """Fixed row names on the left + focus frame, drawn over the scrolling canvas."""

    def __init__(self, view: "TimelineView"):
        super().__init__(view.viewport())
        self.view = view
        self.focused = False
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, ev):
        p = QPainter(self)
        pal = self.palette()
        bg = pal.window().color()
        fg = pal.text().color()
        c = self.view.canvas
        dy = -self.view.verticalScrollBar().value()
        if c.daw:
            self._paint_daw(p, c, dy)
            p.end()
            return
        p.fillRect(QRectF(0, 0, GUTTER, self.height()), bg)
        sep = QColor(fg)
        sep.setAlpha(40)
        p.setPen(sep)
        p.drawLine(GUTTER - 1, 0, GUTTER - 1, self.height())
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
        p.setFont(f)
        for name, (y, h) in c.rows().items():
            title = ROW_TITLES.get(name, name)
            col = QColor(fg)
            col.setAlpha(170)
            if name in ("lines", "sylls"):
                col = QColor(c.accent)
            elif name in ("ref_lines", "ref_sylls"):
                col = QColor(REF_COLOR)
            p.setPen(col)
            p.drawText(QRectF(6, y + dy, GUTTER - 10, h), Qt.AlignVCenter | Qt.AlignLeft, title)
            p.setPen(sep)
            p.drawLine(0, int(y + dy + h), GUTTER - 1, int(y + dy + h))
        if self.focused:
            pen = QPen(QColor(c.accent), 2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(1, 1, self.width() - 2, self.height() - 2))
        p.end()

    def _paint_daw(self, p: QPainter, c: "TimelineCanvas", dy: float):
        """Ruler names right-aligned on the ruler strip; every other row gets a track header with a
        colour strip and a recessed name plate."""
        d = c.daw
        lane = QColor(d["lane_line"])
        p.fillRect(QRectF(0, 0, GUTTER, self.height()), QColor(d["header_bg"]))
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.5))
        p.setFont(f)
        rows = c.rows()
        colors = {"wave": c.wave_color or c.accent, "notes": QColor(d["notes_clip"]), "lines": c.accent,
                  "sylls": c.accent, "ref_lines": REF_COLOR, "ref_sylls": REF_COLOR}
        titles = dict(ROW_TITLES, wave="Audio", notes="Chart notes", lines="Vocals", ref_lines="Reference")
        for name, (y, h) in rows.items():
            y += dy
            if name in ("ruler", "sections"):
                p.fillRect(QRectF(0, y, GUTTER, h), QColor(d["ruler_bg"]))
                p.setPen(QColor(d["ruler_fg"]))
                if name == "ruler":
                    half = h // 2
                    p.drawText(QRectF(4, y, GUTTER - 10, half), Qt.AlignVCenter | Qt.AlignRight, "Bars|Beats")
                    p.drawText(QRectF(4, y + half, GUTTER - 10, h - half), Qt.AlignVCenter | Qt.AlignRight,
                               "Min:Secs")
                    p.fillRect(QRectF(0, y + half, GUTTER, 1), lane)
                else:
                    p.drawText(QRectF(4, y, GUTTER - 10, h), Qt.AlignVCenter | Qt.AlignRight, "Markers")
                p.fillRect(QRectF(0, y + h - 1, GUTTER, 1), lane)
                continue
            if name in ("sylls", "ref_sylls"):         # second half of a vocal track: no separate plate
                p.fillRect(QRectF(0, y, 5, h), colors[name])
                sub = QColor(d["muted"])
                p.setPen(sub)
                p.drawText(QRectF(10, y, GUTTER - 16, h), Qt.AlignVCenter | Qt.AlignLeft,
                           "syllables" if name == "sylls" else "ref. syllables")
                p.fillRect(QRectF(0, y + h - 1, GUTTER, 1), lane)
                continue
            p.fillRect(QRectF(0, y, 5, h), colors.get(name, c.accent))     # track colour strip
            plate = QRectF(9, y + 3, GUTTER - 15, min(16, h - 6))
            p.setPen(QPen(lane, 1))
            p.setBrush(QColor(d["entry_bg"]))
            p.drawRoundedRect(plate, 2, 2)
            p.setBrush(Qt.NoBrush)
            p.setPen(QColor(d["fg"]))
            p.drawText(plate.adjusted(5, 0, -3, 0), Qt.AlignVCenter | Qt.AlignLeft,
                       QFontMetrics(f).elidedText(titles.get(name, name), Qt.ElideRight, int(plate.width() - 8)))
            if name not in ("lines", "ref_lines"):
                p.fillRect(QRectF(0, y + h - 1, GUTTER, 1), lane)
        p.fillRect(QRectF(GUTTER - 1, 0, 1, self.height()), lane)
        if self.focused:
            p.setPen(QPen(QColor(d["accent"]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(1, 1, self.width() - 2, self.height() - 2))


class TimelineView(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = TimelineCanvas()
        self.setWidget(self.canvas)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setFocusPolicy(Qt.NoFocus)          # the canvas takes the keyboard, not the scroll area
        self.overlay = _Overlay(self)
        self.canvas.focusChanged.connect(self._focus)
        self.verticalScrollBar().valueChanged.connect(self.overlay.update)
        self.horizontalScrollBar().valueChanged.connect(self._repaint_sticky)
        self.canvas.zoomChanged.connect(lambda *_: self.overlay.update())

    def _repaint_sticky(self, *_):
        """Section and line names stick to the left edge, so their rows are redrawn on scroll."""
        c = self.canvas
        r = c.visibleRegion().boundingRect()
        rows = c.rows()
        for name in ("sections", "lines", "ref_lines", "wave"):
            if name in rows:
                y, h = rows[name]
                c.update(r.left(), y, r.width(), h)

    def _focus(self, on: bool):
        self.overlay.focused = on
        self.overlay.update()

    def wheelEvent(self, ev):
        c = self.canvas
        if ev.modifiers() & Qt.ControlModifier:
            factor = 1.2 if ev.angleDelta().y() > 0 else 1 / 1.2
            mouse_x = ev.position().x()
            self.zoom_at(c.t_at(self.horizontalScrollBar().value() + mouse_x), mouse_x, c.pps * factor)
            ev.accept()
            return
        bar = self.horizontalScrollBar()
        delta = ev.angleDelta().x() or ev.angleDelta().y()
        if ev.modifiers() & Qt.ShiftModifier:
            delta *= 4                     # Shift + wheel: scroll faster
        bar.setValue(bar.value() - delta)
        ev.accept()

    def zoom_at(self, t: float, screen_x: float, pps: float):
        """Zoom keeping time t at screen position screen_x."""
        self.canvas.set_zoom(pps)
        self.horizontalScrollBar().setValue(int(self.canvas.x(t) - screen_x))

    def fit(self):
        c = self.canvas
        w = max(100, self.viewport().width() - GUTTER - 2 * LEFT)
        c.set_zoom(w / max(1.0, c.duration))
        self.horizontalScrollBar().setValue(0)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.canvas.view_h = self.viewport().height()
        self.canvas._resize()
        self.overlay.setGeometry(self.viewport().rect())
        self.overlay.raise_()

    def visible_range(self) -> Tuple[float, float]:
        v = self.horizontalScrollBar().value()
        return self.canvas.t_at(v + GUTTER), self.canvas.t_at(v + self.viewport().width())

    def scroll_to_time(self, t: float, margin: float = 60):
        self.horizontalScrollBar().setValue(int(self.canvas.x(t) - GUTTER - margin))

    def center_on(self, t: float):
        w = self.viewport().width() - GUTTER
        self.horizontalScrollBar().setValue(int(self.canvas.x(t) - GUTTER - w / 2))

    def ensure_visible_time(self, t: float, page: bool = True):
        """Keep t on screen: page-follow during playback, small scrolls while stepping."""
        bar = self.horizontalScrollBar()
        X = self.canvas.x(t)
        left = bar.value() + GUTTER
        w = self.viewport().width() - GUTTER
        if X < left + 30 or X > left + w - 60:
            if page:
                bar.setValue(int(X - GUTTER - w * 0.25))
            elif X < left + 30:
                bar.setValue(int(X - GUTTER - 30))
            else:
                bar.setValue(int(X - GUTTER - w + 60))


class OverviewBar(QWidget):
    """The whole song at a glance: sections, lyric lines, playhead and the visible window.
    Click or drag to move the view there; double-click also moves the playhead."""
    jumpRequested = Signal(float)       # centre the view on this time
    seekRequested = Signal(float)

    def __init__(self, view: TimelineView, parent=None):
        super().__init__(parent)
        self.view = view
        self.setFixedHeight(26)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setToolTip("Whole song - click or drag to view that part, double-click to move the playhead there")
        view.horizontalScrollBar().valueChanged.connect(self.update)
        view.canvas.zoomChanged.connect(lambda *_: self.update())

    def _t(self, x: float) -> float:
        return max(0.0, x / max(1, self.width()) * self.view.canvas.duration)

    def _x(self, t: float) -> float:
        return t / max(1e-6, self.view.canvas.duration) * self.width()

    def paintEvent(self, ev):
        p = QPainter(self)
        c = self.view.canvas
        pal = self.palette()
        fg = pal.text().color()
        bg = pal.base().color()
        if c.daw:                                      # "universe" strip: recessed, framed
            bg = QColor(c.daw["entry_bg"])
        p.fillRect(self.rect(), bg)
        h = self.height()
        for s in c.sections:
            col = QColor(s.color)
            col.setAlpha(80)
            p.fillRect(QRectF(self._x(s.start), 0, self._x(s.end) - self._x(s.start), h), col)
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 2))
        p.setFont(f)
        fm = QFontMetrics(f)
        p.setPen(fg)
        for s in c.sections:
            a, b = self._x(s.start), self._x(s.end)
            if b - a > fm.horizontalAdvance(s.label) + 6:
                p.drawText(QRectF(a + 3, 0, b - a - 3, 12), Qt.AlignLeft | Qt.AlignVCenter, s.label)
        acc = QColor(c.accent)
        for ln in c.lines:
            p.fillRect(QRectF(self._x(ln.start), h - 9, max(1.5, self._x(ln.end) - self._x(ln.start)), 5), acc)
        a, b = self.view.visible_range()
        win = QColor(fg)
        if c.daw:
            win = QColor(c.daw["select_fg"])
        win.setAlpha(40)
        p.fillRect(QRectF(self._x(a), 0, max(3.0, self._x(b) - self._x(a)), h), win)
        win.setAlpha(150)
        p.setPen(QPen(win, 1))
        p.drawRect(QRectF(self._x(a), 0.5, max(3.0, self._x(b) - self._x(a)), h - 1))
        if c.playhead is not None:
            p.setPen(QPen(QColor(c.playhead_color), 2))
            X = self._x(c.playhead)
            p.drawLine(QPointF(X, 0), QPointF(X, h))
        if c.daw:
            p.setPen(QPen(QColor(c.daw["lane_line"]), 1))
            p.drawRect(QRectF(0, 0, self.width() - 1, h - 1))
        p.end()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.jumpRequested.emit(self._t(ev.position().x()))

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton:
            self.jumpRequested.emit(self._t(ev.position().x()))

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.seekRequested.emit(self._t(ev.position().x()))

    def wheelEvent(self, ev):
        self.view.wheelEvent(ev)


SHORTCUTS_HTML = """
<b>Timeline keyboard</b> (click the timeline first - a coloured frame shows it is listening;
<b>Esc</b> hands the keyboard back, so these keys never touch your settings):
<table cellspacing=4>
<tr><td><b>← →</b></td><td>move the playhead (step set in Options; speeds up while held)</td></tr>
<tr><td><b>Shift + ← →</b></td><td>4× bigger steps</td></tr>
<tr><td><b>Ctrl/Alt + ← →</b></td><td>previous / next lyric line</td></tr>
<tr><td><b>PgUp / PgDn</b></td><td>previous / next section</td></tr>
<tr><td><b>Home / End</b></td><td>start / end of the song</td></tr>
<tr><td><b>↑ ↓</b></td><td>zoom in / out</td></tr>
<tr><td><b>Space</b> · <b>Enter</b></td><td>play / pause · play the current line</td></tr>
<tr><td><b>F</b></td><td>fit the whole song</td></tr>
</table>
<b>Mouse</b>: click = move the playhead (drag to scrub) · click a section = jump to it ·
double-click a lyric line = play it · wheel = scroll (Shift = faster) · Ctrl + wheel = zoom ·
right/middle-drag = pan · the overview strip above shows the whole song: click or drag it to look somewhere else.
"""
