"""Timeline panel: transport controls, in-game lyric preview and the timeline canvas."""
from __future__ import annotations

import bisect
import os
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QSlider, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget)

from ..parsers.rsxml import Beatmap, VocalEntry
from .audio_player import AudioPlayer
from .lyric_preview import LyricPreview
from .timeline import SHORTCUTS_HTML, OverviewBar, TimelineView

AUDIO_EXT = (".wav", ".ogg", ".flac", ".mp3", ".opus", ".m4a", ".aif", ".aiff")
AUDIO_FILTER = "Audio (*.wav *.ogg *.flac *.mp3 *.opus *.m4a *.aif *.aiff);;All files (*)"


def _mmss(t: float) -> str:
    m, s = divmod(int(max(0.0, t)), 60)
    return f"{m}:{s:02d}"


class TimelinePanel(QWidget):
    entryActivated = Signal(int)        # vocal entry index clicked / reached
    audioChanged = Signal(str)
    leaveRequested = Signal()           # Esc in the timeline

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

        bar = QHBoxLayout()
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
        f = self.time_label.font()
        f.setFamily("Consolas" if os.name == "nt" else "Menlo")
        f.setBold(True)
        self.time_label.setFont(f)
        self.time_label.setMinimumWidth(90)
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
        lay.addLayout(bar)

        self.preview = LyricPreview()
        lay.addWidget(self.preview)
        self.view = TimelineView()

        # navigation row: jump to a section, whole-song overview, zoom, keyboard help
        nav = QHBoxLayout()
        nav.setSpacing(4)
        self.section_box = QComboBox()
        self.section_box.setToolTip("Jump to a section of the song (PgUp / PgDn in the timeline)")
        self.section_box.setMinimumWidth(150)
        self.section_box.activated.connect(self._section_chosen)
        self.overview = OverviewBar(self.view)
        self.overview.jumpRequested.connect(self.view.center_on)
        self.overview.seekRequested.connect(lambda t: (self.seek_chart(t), self.view.center_on(t)))
        btn_fit = QToolButton()
        btn_fit.setText("Fit")
        btn_fit.setToolTip("Show the whole song (F)")
        btn_fit.clicked.connect(self.view.fit)
        zoom_out = QToolButton()
        zoom_out.setText("−")
        zoom_out.setToolTip("Zoom out (↓ or Ctrl + wheel)")
        zoom_out.clicked.connect(lambda: self.zoom_by(1 / 1.4))
        zoom_in = QToolButton()
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
        lay.addLayout(nav)
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

    # ------------------------------------------------------------------ data
    def set_project(self, beatmap: Optional[Beatmap], entries: List[VocalEntry], reference: List[VocalEntry],
                    silence_end: float, bars_end: float, song_shift: float):
        self.beatmap = beatmap
        self.entries = entries or []
        self.song_shift = song_shift
        self.view.canvas.set_data(beatmap, self.entries, reference, silence_end, bars_end)
        self.preview.set_entries(self.entries)
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
        c.update()
        if colors.get("clock_bg"):
            self.time_label.setStyleSheet(f"background: {colors['clock_bg']}; color: {colors['clock_fg']}; "
                                          "border-radius: 4px; padding: 2px 8px;")
        else:
            self.time_label.setStyleSheet("padding: 2px 8px;")
        self._show_focus(self.view.canvas.hasFocus())

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
            self.focus_label.setText("Click the timeline to use keys")
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

    def shutdown(self):
        self._timer.stop()
        self.player.close()
