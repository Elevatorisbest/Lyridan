"""Timeline panel: transport controls, in-game lyric preview and the timeline canvas."""
from __future__ import annotations

import bisect
import glob
import json
import os
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QSlider, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget)

from ..parsers.rsxml import Beatmap, VocalEntry
from .audio_player import AudioPlayer
from .lyric_preview import LyricPreview
from .timeline import TimelineView

AUDIO_EXT = (".wav", ".ogg", ".flac", ".mp3", ".opus", ".m4a", ".aif", ".aiff")
AUDIO_FILTER = "Audio (*.wav *.ogg *.flac *.mp3 *.opus *.m4a *.aif *.aiff);;All files (*)"


def find_chart_audio(folders: List[str], title: str = "") -> Optional[str]:
    """Best guess for the chart's audio: DLC Builder project audio, then audio files nearby."""
    seen = set()
    cands = []
    for folder in folders:
        if not folder or not os.path.isdir(folder) or folder in seen:
            continue
        seen.add(folder)
        # DLC Builder project (.rs2dlc is JSON): look for audio paths in it
        for proj in glob.glob(os.path.join(folder, "*.rs2dlc")):
            try:
                data = json.load(open(proj, encoding="utf-8-sig"))
            except Exception:  # noqa: BLE001
                continue
            for path in _json_paths(data):
                full = path if os.path.isabs(path) else os.path.join(os.path.dirname(proj), path)
                if full.lower().endswith(AUDIO_EXT) and os.path.isfile(full) and "preview" not in \
                        os.path.basename(full).lower():
                    return full
        for f in os.listdir(folder):
            full = os.path.join(folder, f)
            low = f.lower()
            if low.endswith(AUDIO_EXT) and os.path.isfile(full) and "preview" not in low:
                cands.append(full)
    if not cands:
        return None
    words = [w for w in title.lower().split() if len(w) > 2]

    def rank(path):
        low = os.path.basename(path).lower()
        ext_rank = {".wav": 3, ".ogg": 2, ".flac": 2}.get(os.path.splitext(low)[1], 1)
        title_hit = sum(1 for w in words if w in low)
        return (title_hit, ext_rank, os.path.getsize(path))

    return max(cands, key=rank)


def _json_paths(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _json_paths(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _json_paths(v)
    elif isinstance(obj, str) and obj.lower().endswith(AUDIO_EXT):
        yield obj


class TimelinePanel(QWidget):
    entryActivated = Signal(int)        # vocal entry index clicked / reached
    audioChanged = Signal(str)

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
        self.btn_audio.setToolTip("Load the chart's song audio (drop an audio file on the window works too)")
        self.btn_audio.clicked.connect(self.choose_audio)
        self.audio_label = QLabel("No audio")
        self.audio_label.setMinimumWidth(120)
        self.audio_label.setStyleSheet("color: gray;")
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
        zoom_out = QToolButton()
        zoom_out.setText("−")
        zoom_out.setToolTip("Zoom out (Ctrl + wheel)")
        zoom_in = QToolButton()
        zoom_in.setText("+")
        zoom_in.setToolTip("Zoom in (Ctrl + wheel)")
        for wdg in (self.btn_audio, self.audio_label, self.btn_start, self.btn_play, self.time_label):
            bar.addWidget(wdg)
        bar.addStretch(1)
        for wdg in (QLabel("Audio is"), self.audio_mode, self.nudge, self.speed, QLabel("🔊"), self.volume, self.btn_metro,
                    self.btn_follow, zoom_out, zoom_in):
            bar.addWidget(wdg)
        lay.addLayout(bar)

        self.preview = LyricPreview()
        lay.addWidget(self.preview)
        self.view = TimelineView()
        lay.addWidget(self.view, 1)
        zoom_out.clicked.connect(lambda: self.view.canvas.set_zoom(self.view.canvas.pps / 1.4))
        zoom_in.clicked.connect(lambda: self.view.canvas.set_zoom(self.view.canvas.pps * 1.4))
        self.view.canvas.seekRequested.connect(self.seek_chart)
        self.view.canvas.entryClicked.connect(self.entryActivated.emit)

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
        self._update_shift()
        if not self.player.playing:
            self._show_time(self.chart_time())

    def set_accent(self, color):
        from PySide6.QtGui import QColor
        self.view.canvas.accent = QColor(color)
        self.view.canvas.update()

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
        self._update_shift()
        self.audioChanged.emit(path)
        return True

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
        QMessageBox.information(self, "Lyridan", "Load the song audio first (🎵 Audio… or drop it on the window). "
                                                 "Lyridan also finds it next to your chart XML automatically.")
        return False

    def seek_chart(self, t: float):
        if self.player.loaded:
            self.player.seek(t - self.shift())
        else:
            self._cursor = t
        self._tick()

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
