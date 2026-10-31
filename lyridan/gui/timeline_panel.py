"""Timeline panel: transport controls, in-game lyric preview and the timeline canvas."""
from __future__ import annotations

import bisect
import os
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QSlider, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget)

from ..parsers.rsxml import Beatmap, VocalEntry
from .audio_player import AudioPlayer
from .lyric_preview import LyricPreview
from .timeline import SHORTCUTS_HTML, OverviewBar, TimelineView

AUDIO_EXT = (".wav", ".ogg", ".flac", ".mp3", ".opus", ".m4a", ".aif", ".aiff")
AUDIO_FILTER = "Audio (*.wav *.ogg *.flac *.mp3 *.opus *.m4a *.aif *.aiff);;All files (*)"


def _clock(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:06.3f}"


def _mmss(t: float) -> str:
    m, s = divmod(int(max(0.0, t)), 60)
    return f"{m}:{s:02d}"


class TimelinePanel(QWidget):
    entryActivated = Signal(int)        # vocal entry index clicked / reached
    audioChanged = Signal(str)
    leaveRequested = Signal()           # Esc in the timeline

    click_focus = True                  # preview / overview / transport / clock clicks give the timeline the keys

    BASE_HEIGHT = 396                   # panel height (preview + timeline) in the default 1380 x 860 window

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # the in-game preview keeps its share of the panel (box and text grow together)
        self.preview.set_scale(self.height() / self.BASE_HEIGHT)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = AudioPlayer()
        self.entries: List[VocalEntry] = []
        self.beatmap: Optional[Beatmap] = None
        self.song_shift = 0.0          # intro silence + empty bars (for original-song audio)
        self.follow = True
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)

        # transport row, in a toolbar strip (DAW themes style #TransportBar; others see no frame)
        self.transport_bar = QFrame()
        self.transport_bar.setObjectName("TransportBar")
        bar = QHBoxLayout(self.transport_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(4)                    # what the row had as a nested layout
        self.btn_audio = QToolButton()
        self.btn_audio.setText("🎵 Audio…")
        self.btn_audio.setToolTip("Pick the audio file your chart uses (the WAV/OGG from your EOF / DLC Builder "
                                  "project). Dropping an audio file on the window works too.")
        self.btn_audio.clicked.connect(self.choose_audio)
        self.audio_label = QLabel()
        self.audio_label.setMinimumWidth(120)
        self._no_audio_label()
        self.btn_start = QToolButton()
        self.btn_start.setText("⏮")
        self.btn_start.setToolTip("Back to the first lyric")
        self.btn_start.clicked.connect(self.go_first_lyric)
        self.btn_play = QToolButton()
        self.btn_play.setText("▶ Play")
        self.btn_play.setToolTip("Play / pause (Space)")
        self.btn_play.clicked.connect(self.toggle_play)
        self.time_label = QLabel("0:00.000")
        self.time_label.setObjectName("MainCounter")
        f = self.time_label.font()
        self.time_label.setFont(f)              # family / size come from style_counters
        self.time_label.setMinimumWidth(90)
        self._clock_pt = f.pointSizeF() if f.pointSizeF() > 0 else 10.0
        self.speed = QComboBox()
        for v in (0.5, 0.75, 1.0):
            self.speed.addItem(f"{v:g}×", v)
        self.speed.setCurrentIndex(2)
        self.speed.setToolTip("Playback speed (slower playback lowers the pitch)")
        self.speed.currentIndexChanged.connect(lambda: setattr(self.player, "speed", self.speed.currentData()))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(80)
        self.volume.setToolTip("Volume")
        self.volume.valueChanged.connect(lambda v: setattr(self.player, "volume", v / 100))
        self.btn_metro = QToolButton()
        self.btn_metro.setText("Metronome")
        self.btn_metro.setCheckable(True)
        self.btn_metro.setToolTip("Click on the chart's beats (accent on each bar) - checks the beatmap too")
        self.btn_metro.toggled.connect(lambda on: setattr(self.player, "metronome", on))
        self.btn_follow = QToolButton()
        self.btn_follow.setText("Follow")
        self.btn_follow.setCheckable(True)
        self.btn_follow.setChecked(True)
        self.btn_follow.setToolTip("Scroll the timeline with the playhead")
        self.btn_follow.toggled.connect(lambda on: setattr(self, "follow", on))
        self.audio_mode = QComboBox()
        self.audio_mode.addItem("Auto-detect", "auto")
        self.audio_mode.addItem("Chart audio", "chart")
        self.audio_mode.addItem("Original song", "song")
        self.audio_mode.setToolTip("Chart audio already has the intro silence and empty bars (as in EOF). "
                                   "The original song is shifted by them automatically.")
        self.audio_mode.currentIndexChanged.connect(self._update_shift)
        self.nudge = QSpinBox()
        self.nudge.setRange(-5000, 5000)
        self.nudge.setSingleStep(10)
        self.nudge.setSuffix(" ms")
        self.nudge.setToolTip("Shift only the preview audio (does not change the export)")
        self.nudge.valueChanged.connect(self._update_shift)
        for wdg in (self.btn_audio, self.audio_label, self.btn_start, self.btn_play, self.time_label):
            bar.addWidget(wdg)
        bar.addStretch(1)
        for wdg in (QLabel("Audio is"), self.audio_mode, self.nudge, self.speed, QLabel("🔊"), self.volume,
                    self.btn_metro, self.btn_follow):
            bar.addWidget(wdg)
        lay.addWidget(self.transport_bar)

        self.preview = LyricPreview()
        lay.addWidget(self.preview)
        self.view = TimelineView()

        # navigation row: jump to a section, whole-song overview, zoom, keyboard help
        self.nav_bar = QFrame()
        self.nav_bar.setObjectName("NavBar")
        nav = QHBoxLayout(self.nav_bar)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(4)
        self.section_box = QComboBox()
        self.section_box.setToolTip("Jump to a section of the song (PgUp / PgDn in the timeline)")
        self.section_box.setMinimumWidth(150)
        self.section_box.activated.connect(self._section_chosen)
        self.overview = OverviewBar(self.view)
        self.overview.jumpRequested.connect(self.view.center_on)
        self.overview.seekRequested.connect(lambda t: (self.seek_chart(t), self.view.center_on(t)))
        self.btn_fit = btn_fit = QToolButton()
        btn_fit.setText("Fit")
        btn_fit.setToolTip("Show the whole song (F)")
        btn_fit.clicked.connect(self.view.fit)
        self.btn_zoom_out = zoom_out = QToolButton()
        zoom_out.setText("−")
        zoom_out.setToolTip("Zoom out (↓ or Ctrl + wheel)")
        zoom_out.clicked.connect(lambda: self.zoom_by(1 / 1.4))
        self.btn_zoom_in = zoom_in = QToolButton()
        zoom_in.setText("+")
        zoom_in.setToolTip("Zoom in (↑ or Ctrl + wheel)")
        zoom_in.clicked.connect(lambda: self.zoom_by(1.4))
        self.btn_keys = QToolButton()
        self.btn_keys.setText("⌨")
        self.btn_keys.setToolTip(SHORTCUTS_HTML)
        self.btn_keys.clicked.connect(lambda: QMessageBox.information(self, "Timeline controls", SHORTCUTS_HTML))
        self.focus_label = QLabel()
        self.focus_label.setMinimumWidth(190)
        nav.addWidget(self.section_box)
        nav.addWidget(self.overview, 1)
        for wdg in (btn_fit, zoom_out, zoom_in, self.btn_keys, self.focus_label):
            nav.addWidget(wdg)
        lay.addWidget(self.nav_bar)
        lay.addWidget(self.view, 1)

        c = self.view.canvas
        c.seekRequested.connect(self.seek_chart)
        c.navRequested.connect(self.navigate)
        c.entryClicked.connect(self.entryActivated.emit)
        c.playLineRequested.connect(self.play_from)
        c.zoomKeyRequested.connect(self.zoom_by)
        c.fitRequested.connect(self.view.fit)
        c.leaveRequested.connect(self.leaveRequested.emit)
        c.focusChanged.connect(self._show_focus)
        self._show_focus(False)

        # edit-window readouts (read-only) and line rewind / fast-forward (same as Ctrl/Alt + ← →)
        self.btn_rew = QToolButton()
        self.btn_rew.setText("◀◀")
        self.btn_rew.setToolTip("Previous lyric line (Ctrl/Alt + ← in the timeline)")
        self.btn_rew.clicked.connect(lambda: self.navigate(c._line_target(self.chart_time(), -1)))
        self.btn_ff = QToolButton()
        self.btn_ff.setText("▶▶")
        self.btn_ff.setToolTip("Next lyric line (Ctrl/Alt + → in the timeline)")
        self.btn_ff.clicked.connect(lambda: self.navigate(c._line_target(self.chart_time(), 1)))
        self.btn_loop = QToolButton()
        self.btn_loop.setText("⟲ Loop")
        self.btn_loop.setCheckable(True)
        self.btn_loop.setToolTip("Repeat the range shown in Start / End while playing (L in the timeline).\n"
                                 "With no range selected it locks onto the line at the playhead.\n"
                                 "Shift + drag in the timeline selects a range.")
        self.btn_loop.toggled.connect(self._loop_toggled)
        for b in (self.btn_rew, self.btn_ff, self.btn_loop):
            b.setFocusPolicy(Qt.NoFocus)
        self.sub_counter = self._lcd("SubCounter", "Bar | beat | tick at the playhead (960 ticks per beat)")
        self.line_start = self._lcd("Lcd", "Start of the lyric line at the playhead")
        self.line_end = self._lcd("Lcd", "End of the lyric line at the playhead")
        self.line_len = self._lcd("Lcd", "Length of the lyric line at the playhead")
        self.tempo_lcd = self._lcd("Lcd", "Tempo of the chart's beatmap at the playhead")
        self.meter_lcd = self._lcd("Lcd", "Beats per bar at the playhead")
        self.line_start.setToolTip("Start of the range (or of the line at the playhead) - click to jump there")
        self.line_end.setToolTip("End of the range (or of the line at the playhead) - click to jump there")
        self.line_len.setToolTip("Length of the range (or of the line at the playhead) - click to play it")
        self.time_label.setToolTip("Chart time (as in the exported XML) - click to use the timeline keys")
        self.sub_counter.setToolTip("Bar | beat | tick at the playhead (960 ticks per beat) - click to use the "
                                    "timeline keys")
        for lab in (self.line_start, self.line_end, self.line_len, self.time_label, self.sub_counter):
            lab.setCursor(Qt.PointingHandCursor)
            lab.installEventFilter(self)
        self._auto_range = False                # the range was set by Loop (follows nothing), not by the user
        self._play_until: Optional[float] = None  # Length click: stop here
        self._prev_t = 0.0
        self.preview.installEventFilter(self)
        self.overview.installEventFilter(self)
        for b in (self.btn_start, self.btn_rew, self.btn_play, self.btn_ff, self.btn_loop, self.btn_metro,
                  self.btn_follow, self.btn_fit, self.btn_zoom_in, self.btn_zoom_out):
            b.clicked.connect(self._focus_from_control)
        c.rangeSelected.connect(self._range_selected)
        c.rangeCleared.connect(self.clear_range)
        c.loopKeyRequested.connect(self.btn_loop.toggle)
        self._beat_bar: List[int] = []          # bar number of every beat
        self._beat_pos: List[int] = []          # beat number inside its bar

        # safeguard: toolbar controls never keep the keyboard, so arrow keys meant for the
        # timeline cannot change the speed, audio mode, volume... by accident
        for wdg in self.findChildren(QToolButton) + [self.volume]:
            wdg.setFocusPolicy(Qt.NoFocus)
        for box in (self.speed, self.audio_mode, self.section_box):
            box.setFocusPolicy(Qt.ClickFocus)
            box.activated.connect(lambda *_: c.setFocus(Qt.OtherFocusReason))
        self.nudge.setFocusPolicy(Qt.ClickFocus)
        self.nudge.editingFinished.connect(lambda: c.setFocus(Qt.OtherFocusReason))

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._last_active = -1
        sc = QShortcut(QKeySequence(Qt.Key_Space), self)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(self.toggle_play)

    # ------------------------------------------------------------------ focus
    def focus_timeline(self):
        self.view.canvas.setFocus(Qt.MouseFocusReason)

    def _focus_from_control(self, *_):
        if self.click_focus:
            self.focus_timeline()

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if ev.type() == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
            if obj in (self.preview, self.overview, self.time_label, self.sub_counter):
                self._focus_from_control()
            elif obj in (self.line_start, self.line_end, self.line_len):
                self._clock_clicked(obj)
                return True
        return super().eventFilter(obj, ev)

    # ------------------------------------------------------------------ range / loop
    def current_range(self, t: Optional[float] = None):
        """(start, end) of the selected range, else of the lyric line at the playhead, else None."""
        c = self.view.canvas
        if c.selection is not None:
            return c.selection
        t = self.chart_time() if t is None else t
        ai = self._active_index(t)
        ln = c._line_of(ai) if ai >= 0 else None
        if ln is None or (t > ln.end + 0.5 and ai + 1 >= len(self.entries)):
            return None
        return (ln.start, ln.end)

    def set_range(self, a: float, b: float, auto: bool = False):
        c = self.view.canvas
        c.selection = (min(a, b), max(a, b))
        self._auto_range = auto
        c.update()
        self._show_readouts(self.chart_time())

    def clear_range(self):
        c = self.view.canvas
        c.selection = None
        self._auto_range = False
        if self.btn_loop.isChecked():
            self.btn_loop.setChecked(False)
        c.update()
        self._show_readouts(self.chart_time())

    def _range_selected(self, a: float, b: float):
        self.set_range(a, b)

    def _loop_toggled(self, on: bool):
        c = self.view.canvas
        if on and c.selection is None:
            rng = self.current_range()
            if rng is None:
                self.btn_loop.setChecked(False)
                self.window().statusBar().showMessage("Loop: select a range (Shift + drag in the timeline) or "
                                                      "move the playhead onto a lyric line first.", 5000)
                return
            self.set_range(*rng, auto=True)
        c.loop_on = on
        if not on and self._auto_range:
            c.selection = None
            self._auto_range = False
        c.update()
        self._show_readouts(self.chart_time())

    def _clock_clicked(self, lab):
        rng = self.current_range()
        self._focus_from_control()
        if rng is None:
            return
        a, b = rng
        if lab is self.line_start:
            self.navigate(a)
        elif lab is self.line_end:
            self.navigate(b)
        else:                                   # Length: play the range (once, unless Loop is on)
            self.seek_chart(a)
            self.view.ensure_visible_time(a, page=False)
            self._play_until = None if self.btn_loop.isChecked() else b
            if self.player.loaded and not self.player.playing:
                self.toggle_play()
            elif not self.player.loaded:
                self._try_play_without_audio()

    @staticmethod
    def _lcd(name: str, tip: str) -> QLabel:
        lab = QLabel("")
        lab.setObjectName(name)
        lab.setToolTip(tip)
        lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lab

    # ------------------------------------------------------------------ data
    def set_project(self, beatmap: Optional[Beatmap], entries: List[VocalEntry], reference: List[VocalEntry],
                    silence_end: float, bars_end: float, song_shift: float):
        self.beatmap = beatmap
        self.entries = entries or []
        self.song_shift = song_shift
        self.view.canvas.set_data(beatmap, self.entries, reference, silence_end, bars_end)
        self.preview.set_entries(self.entries)
        self._beat_bar, self._beat_pos = [], []
        if beatmap and beatmap.beats:
            bar, pos = 0, 0
            for k, is_m in enumerate(beatmap.measure_flags):
                if is_m or k == 0:
                    bar, pos = bar + 1, 0
                pos += 1
                self._beat_bar.append(bar)
                self._beat_pos.append(pos)
        self._fill_sections()
        self.overview.update()
        self._update_shift()
        if not self.player.playing:
            self._show_time(self.chart_time())

    def set_accent(self, color, colors: Optional[dict] = None):
        from PySide6.QtGui import QColor
        colors = colors or {}
        c = self.view.canvas
        c.accent = QColor(color)
        c.wave_color = QColor(colors["wave"]) if colors.get("wave") else None
        c.playhead_color = QColor(colors.get("playhead", "#ff4d4d"))
        c.daw = colors if colors.get("style") == "daw" else None
        c.ROW_RULER = 32 if c.daw else type(c).ROW_RULER      # room for two stacked rulers
        c._resize()
        c.update()
        self.transport_bar.layout().setContentsMargins(*((2, 2, 2, 2) if c.daw else (0, 0, 0, 0)))
        self.nav_bar.layout().setContentsMargins(*((2, 2, 2, 2) if c.daw else (0, 0, 0, 0)))
        self.view.overlay.update()
        self.overview.update()
        self.style_counters(colors)
        self._show_focus(self.view.canvas.hasFocus())

    def _style_range_clocks(self):
        """Start / End / Length get an accent frame while they show a selected range (not just the line)."""
        bg, fg, edge, acc = self._lcd_colors
        frame = acc if getattr(self, "_range_shown", False) else edge
        for lab in (self.line_start, self.line_end, self.line_len):
            lab.setStyleSheet(f"background: {bg}; color: {fg}; border: 1px solid {frame}; border-radius: 2px; "
                              f"padding: 1px 6px; {self._lcd_font_css.get(lab, '')}")

    counter_scale = 1.0          # > 1 in a window bigger than the default (set by the main window)

    def set_counter_scale(self, scale: float):
        scale = max(1.0, scale)
        if abs(scale - self.counter_scale) > 0.01:
            self.counter_scale = scale
            if getattr(self, "_counter_colors", None) is not None:
                self.style_counters(self._counter_colors)

    def style_counters(self, colors: dict):
        """Edit-window counters: green (or the theme's clock colour) digits on a black LCD, in every theme.
        The font goes into the style sheet (not setFont): Qt puts a widget's first-polish font back
        whenever style sheets are re-applied, which used to shrink the clocks to the normal text size."""
        from PySide6.QtGui import QFont, QFontMetrics
        self._counter_colors = colors
        self._lcd_font_css = {}
        bg = colors.get("clock_bg") or "#0b0c0d"
        fg = colors.get("clock_fg") or "#3fe06a"
        edge = colors.get("border") or "#000000"
        base = self._clock_pt * self.counter_scale
        from .fonts import counter_family
        family = counter_family()
        for lab, scale, pad, sample in ((self.time_label, 1.75, "2px 8px", "00:00.000"),
                                        (self.sub_counter, 1.25, "1px 10px", "000| 0| 000"),
                                        (self.line_start, 1.0, "1px 6px", "0:00.000"),
                                        (self.line_end, 1.0, "1px 6px", "0:00.000"),
                                        (self.line_len, 1.0, "1px 6px", "0:00.000"),
                                        (self.tempo_lcd, 1.0, "1px 6px", "♩ 000.0"),
                                        (self.meter_lcd, 1.0, "1px 6px", "00/00")):
            f = QFont(family)
            f.setPointSizeF(base * scale)
            lab.setFont(f)
            css = f'font-family: "{family}"; font-weight: normal; font-size: {base * scale:.1f}pt;'
            self._lcd_font_css[lab] = css
            lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lab.setMinimumWidth(QFontMetrics(f).horizontalAdvance(sample) + (26 if scale > 1 else 16))
            lab.setStyleSheet(f"background: {bg}; color: {fg}; border: 1px solid {edge}; border-radius: 2px; "
                              f"padding: {pad}; {css}")
        acc = colors.get("accent") or "#3b82d6"
        if acc.lower() == edge.lower():           # e.g. Lyridan Dark: yellow frames already
            acc = "#ffffff"
        self._lcd_colors = (bg, fg, edge, acc)
        self._style_range_clocks()

    def choose_audio(self):
        start = os.path.dirname(self.player.path) if self.player.path else ""
        if not start and self.beatmap and self.beatmap.path:
            start = os.path.dirname(self.beatmap.path)
        p, _ = QFileDialog.getOpenFileName(self, "Song audio", start, AUDIO_FILTER)
        if p:
            self.load_audio(p)

    def load_audio(self, path: str, quiet: bool = False) -> bool:
        try:
            self.player.load(path)
        except Exception as e:  # noqa: BLE001
            if not quiet:
                QMessageBox.warning(self, "Lyridan", f"Could not load the audio:\n{e}")
            return False
        self.audio_label.setText(os.path.basename(path))
        self.view.canvas.clip_name = os.path.splitext(os.path.basename(path))[0]
        self.audio_label.setToolTip(path)
        self.audio_label.setStyleSheet("")
        self.btn_audio.setText("🎵 Audio…")
        self._update_shift()
        self.audioChanged.emit(path)
        return True

    def _no_audio_label(self):
        self.audio_label.setText("← pick your chart's audio")
        self.audio_label.setToolTip("Lyridan does not guess the audio file - choose the one your chart uses")
        self.audio_label.setStyleSheet("color: #d6a10a; font-weight: bold;")

    def unload_audio(self):
        if self._timer.isActive():
            self._timer.stop()
        self.player.unload()
        self.view.canvas.clip_name = ""
        self.btn_play.setText("▶ Play")
        self._no_audio_label()
        self._update_shift()
        self._tick()

    def audio_kind(self) -> str:
        """'chart' = audio already has intro silence + empty bars; 'song' = original song."""
        mode = self.audio_mode.currentData()
        if mode != "auto":
            return mode
        bm = self.beatmap
        if not self.player.loaded or not bm or not bm.song_length:
            return "chart"
        dur = self.player.duration
        if abs(dur - bm.song_length) < 1.5:
            return "chart"
        if self.song_shift > 0 and abs(dur + self.song_shift - bm.song_length) < 2.5:
            return "song"
        return "chart"

    def shift(self) -> float:
        """chart time = audio time + shift"""
        base = self.song_shift if self.audio_kind() == "song" else 0.0
        return base + self.nudge.value() / 1000.0

    def _update_shift(self, *_):
        sh = self.shift()
        self.view.canvas.set_audio(self.player.peaks if self.player.loaded else None, 100.0, sh)
        if self.beatmap and self.beatmap.beats:
            self.player.set_beats([t - sh for t in self.beatmap.beats], self.beatmap.measure_flags)
        if self.player.loaded:
            kind = self.audio_kind()
            self.audio_mode.setItemText(0, f"Auto ({'chart audio' if kind == 'chart' else 'original song'})")

    # ------------------------------------------------------------------ transport
    def chart_time(self) -> float:
        return self.player.position() + self.shift() if self.player.loaded else (self._cursor or 0.0)

    _cursor = 0.0

    def toggle_play(self):
        if not self.player.loaded:
            if not self._try_play_without_audio():
                return
        if self.player.playing:
            self.player.pause()
            self._timer.stop()
            self.btn_play.setText("▶ Play")
            self._tick()
        else:
            self.player.play()
            if self.player.device_error:
                self.window().statusBar().showMessage(
                    f"No audio output ({self.player.device_error}) - previewing silently.", 6000)
            self.btn_play.setText("⏸ Pause")
            self._timer.start()

    def _try_play_without_audio(self) -> bool:
        QMessageBox.information(self, "Lyridan", "Pick your chart's audio first (🎵 Audio… or drop the file on "
                                                 "the window).")
        return False

    def seek_chart(self, t: float):
        if self.player.loaded:
            self.player.seek(t - self.shift())
        else:
            self._cursor = t
        self._tick()

    def navigate(self, t: float):
        """Keyboard navigation: move the playhead and keep it in view."""
        self.seek_chart(max(0.0, t))
        self.view.ensure_visible_time(self.chart_time(), page=False)

    def play_from(self, t: float):
        self.seek_chart(max(0.0, t - 0.3))
        self.view.ensure_visible_time(t, page=False)
        if self.player.loaded and not self.player.playing:
            self.toggle_play()

    def zoom_by(self, factor: float):
        """Zoom keeping the playhead (or the view centre) where it is on screen."""
        v = self.view
        c = v.canvas
        a, b = v.visible_range()
        t = self.chart_time()
        if not (a <= t <= b):
            t = (a + b) / 2
        screen_x = c.x(t) - v.horizontalScrollBar().value()
        v.zoom_at(t, screen_x, c.pps * factor)

    def _fill_sections(self):
        box = self.section_box
        box.blockSignals(True)
        box.clear()
        secs = self.view.canvas.sections
        box.addItem("Go to section…" if secs else "No sections in the chart", None)
        if self.view.canvas.lines:
            box.addItem(f"First lyric  ({_mmss(self.view.canvas.lines[0].start)})",
                        max(0.0, self.view.canvas.lines[0].start - 1.0))
        for sct in secs:
            box.addItem(f"{sct.label}  ({_mmss(sct.start)})", sct.start)
        box.setCurrentIndex(0)
        box.blockSignals(False)

    def _section_chosen(self, i: int):
        t = self.section_box.itemData(i)
        self.section_box.setCurrentIndex(0)
        if t is None:
            return
        self.seek_chart(t)
        self.view.scroll_to_time(t, 40)

    def _show_focus(self, on: bool):
        if on:
            acc = self.view.canvas.accent
            text = "#000000" if acc.lightness() > 140 else "#ffffff"
            self.focus_label.setText("⌨  Keys active  ·  Esc to leave")
            self.focus_label.setStyleSheet(f"background: {acc.name()}; color: {text}; font-weight: bold; "
                                           "border-radius: 4px; padding: 3px 8px;")
        else:
            self.focus_label.setText("Click the timeline, preview or overview to use keys" if self.click_focus
                                     else "Click the timeline to use keys")
            self.focus_label.setStyleSheet("padding: 3px 8px;")

    def set_navigation(self, arrow_step: str, accelerate: bool):
        self.view.canvas.arrow_step = arrow_step
        self.view.canvas.accelerate = accelerate

    def go_first_lyric(self):
        if self.entries:
            t = max(0.0, self.entries[0].time - 2.0)
            self.seek_chart(t)
            self.view.scroll_to_time(t)

    def _active_index(self, t: float) -> int:
        if not self.entries:
            return -1
        times = [e.time for e in self.entries]
        i = bisect.bisect_right(times, t) - 1
        return i

    def _tick(self):
        t = self.chart_time()
        if self.player.playing:
            rng = self.view.canvas.selection
            if self.btn_loop.isChecked() and rng and self._prev_t < rng[1] <= t and t - self._prev_t < 0.3:
                self.seek_chart(rng[0])            # crossed the end of the loop: back to its start
                return
            if self._play_until is not None and t >= self._play_until:
                self._play_until = None
                self.toggle_play()                 # Length click: stop at the end of the range
                return
        else:
            self._play_until = None
        self._prev_t = t
        if self.player.loaded and not self.player.playing and self._timer.isActive():
            self._timer.stop()
            self.btn_play.setText("▶ Play")
        ai = self._active_index(t)
        self.view.canvas.set_playhead(t, ai)
        self.preview.set_time(t)
        self._show_time(t)
        self.overview.update()
        if self.follow and self.player.playing:
            self.view.ensure_visible_time(t)
        if ai != self._last_active:
            self._last_active = ai
            if ai >= 0 and self.player.playing:
                self.entryActivated.emit(ai)

    def _show_time(self, t: float):
        m, s = divmod(max(0.0, t), 60)
        self.time_label.setText(f"{int(m)}:{s:06.3f}")
        self.time_label.setToolTip("Chart time (as in the exported XML)")
        self._show_readouts(t)

    def _show_readouts(self, t: float):
        """Bars|Beats sub counter, current line start/end/length, tempo and meter (display only)."""
        bm = self.beatmap
        beats = bm.beats if bm else []
        k = bisect.bisect_right(beats, t) - 1 if beats else -1
        if 0 <= k < len(self._beat_bar):
            nxt = beats[k + 1] if k + 1 < len(beats) else beats[k] + (beats[k] - beats[k - 1] if k else 0.5)
            span = max(1e-6, nxt - beats[k])
            tick = int(min(959, (t - beats[k]) / span * 960))
            self.sub_counter.setText(f"{self._beat_bar[k]:>3}| {self._beat_pos[k]}| {tick:03d}")
            self.tempo_lcd.setText(f"♩ {60.0 / span:.1f}")
            j = k + 1                                   # beats in this bar = last beat number before the next bar
            while j < len(self._beat_bar) and self._beat_bar[j] == self._beat_bar[k]:
                j += 1
            den = 4
            for ts_t, _num, ts_den in (bm.ts_events or []):
                if ts_t <= t + 1e-6 and ts_den:
                    den = ts_den
            self.meter_lcd.setText(f"{self._beat_pos[j - 1]}/{den}")
        else:
            self.sub_counter.setText("  0| 0| 000")
            self.tempo_lcd.setText("♩ —")
            self.meter_lcd.setText("—")
        rng = self.current_range(t)
        if rng is None:
            for lab in (self.line_start, self.line_end, self.line_len):
                lab.setText("—")
        else:
            self.line_start.setText(_clock(rng[0]))
            self.line_end.setText(_clock(rng[1]))
            self.line_len.setText(_clock(rng[1] - rng[0]))
        has_range = self.view.canvas.selection is not None
        if has_range != getattr(self, "_range_shown", None) and getattr(self, "_lcd_colors", None):
            self._range_shown = has_range
            self._style_range_clocks()

    def shutdown(self):
        self._timer.stop()
        self.player.close()
