"""Lyridan main window."""
from __future__ import annotations

import json
import os
import traceback
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                               QToolButton, QVBoxLayout, QWidget)

from .. import APP_NAME, VERSION, buildinfo
from ..parsers import load_lyrics
from ..parsers.rsxml import Beatmap, VocalEntry, parse_beatmap, parse_vocals, write_vocals
from ..settings import Settings, config_dir
from .dialogs import DictDialog, DisclaimerDialog, about_text
from .timeline_panel import AUDIO_EXT, TimelinePanel

LYRIC_FILTER = "Lyrics (*.ttml *.lrc *.elrc *.json *.xml *.txt);;All files (*)"
XML_FILTER = "Rocksmith XML (*.xml);;All files (*)"
PROJECT_FILTER = "Lyridan project (*.lyridan);;All files (*)"


def _resource(name: str) -> str:
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    for cand in (os.path.join(base, name), os.path.join(base, "assets", name)):
        if os.path.exists(cand):
            return cand
    return ""


class _WarmupSignals(QObject):
    done = Signal()


class _Warmup(QRunnable):
    """Loads the dictionaries in the background so the first conversion is instant."""

    def __init__(self):
        super().__init__()
        self.signals = _WarmupSignals()

    def run(self):
        try:
            from ..lang.english import get_english
            from ..lang.japanese import get_japanese
            get_english().cmu
            get_japanese().tagger
        except Exception:
            pass
        try:
            self.signals.done.emit()
        except RuntimeError:  # window already closed
            pass


class FileCard(QFrame):
    """Shows one input file with Browse / Clear buttons."""

    def __init__(self, title: str, hint: str, parent=None):
        super().__init__(parent)
        self.setObjectName("FileCard")
        self.setFrameShape(QFrame.StyledPanel)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 6)
        col = QVBoxLayout()
        self.title = QLabel(f"<b>{title}</b>")
        self.name = QLabel(hint)
        self.name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.name.setWordWrap(True)
        self.info = QLabel("")
        self.info.setStyleSheet("color: gray;")
        col.addWidget(self.title)
        col.addWidget(self.name)
        col.addWidget(self.info)
        lay.addLayout(col, 1)
        self.browse = QPushButton("Browse…")
        self.clear = QToolButton()
        self.clear.setText("✕")
        self.clear.setToolTip("Remove")
        lay.addWidget(self.browse)
        lay.addWidget(self.clear)
        self.hint = hint

    def set_file(self, path: Optional[str], info: str = ""):
        self.name.setText(os.path.basename(path) if path else self.hint)
        self.name.setToolTip(path or "")
        self.info.setText(info)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {buildinfo.display_version()}"
                            + ("  [DEV BUILD]" if buildinfo.is_dev() else ""))
        icon = _resource("lyridanlogo.ico") or _resource("lyridanlogo.png")
        if icon:
            self.setWindowIcon(QIcon(icon))
        self.setAcceptDrops(True)
        self.resize(1380, 860)

        self.settings = Settings.load()
        self.ja_user_dict: Dict[str, str] = dict(self.settings.ja.user_dict)
        self.source = None
        self.source_path: Optional[str] = None
        self.beatmap: Optional[Beatmap] = None
        self.beatmap_path: Optional[str] = None
        self.reference: List[VocalEntry] = []
        self.reference_path: Optional[str] = None
        self.overrides: Dict[int, str] = {}
        self.processed = None
        self.result = None
        self._loading_ui = False
        self._table_updating = False

        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.setInterval(250)
        self._recalc_timer.timeout.connect(self.recalculate)

        self._build_menu()
        self._build_ui()
        self._wheel_guard = WheelGuard(self)
        QApplication.instance().installEventFilter(self._wheel_guard)
        self._load_settings_into_ui()
        if buildinfo.is_dev():
            i = buildinfo.info()
            tag = QLabel(f" DEV #{i.get('build_number', '?')} · {i.get('branch', '')} @ {i.get('commit_short', '')} ")
            tag.setStyleSheet("background:#f5a524; color:black; font-weight:bold; border-radius:3px;")
            tag.setToolTip(buildinfo.as_text())
            self.statusBar().addPermanentWidget(tag)
        self.apply_options()
        QTimer.singleShot(0, self.restore_session)
        self.statusBar().showMessage("Loading language dictionaries…")
        w = _Warmup()
        w.signals.done.connect(lambda: self.statusBar().showMessage("Ready - drop a .ttml/.lrc file and a Rocksmith XML", 8000))
        QThreadPool.globalInstance().start(w)

    # ------------------------------------------------------------------ UI
    def _build_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("&File")
        for text, slot, sc in (("Open lyrics…", self.open_lyrics, QKeySequence.Open),
                               ("Open beatmap XML…", self.open_beatmap, "Ctrl+B"),
                               ("Compare with existing vocals XML…", self.open_reference, None),
                               ("Remove comparison vocals", lambda: self.clear_reference(), None),
                               (None, None, None),
                               ("Open project…", self.open_project, "Ctrl+Shift+O"),
                               ("Save project…", self.save_project, QKeySequence.Save),
                               (None, None, None),
                               ("Export Rocksmith vocals…", self.export_vocals, "Ctrl+E"),
                               ("Export native-script vocals…", self.export_native, None),
                               ("Export syllabized text / LRC…", self.export_text, None),
                               (None, None, None),
                               ("Quit", self.close, QKeySequence.Quit)):
            if text is None:
                fm.addSeparator()
                continue
            a = QAction(text, self)
            a.triggered.connect(slot)
            if sc:
                a.setShortcut(sc)
            fm.addAction(a)
        em = mb.addMenu("&Edit")
        a = QAction("Options…", self)
        a.setShortcut(QKeySequence.Preferences if not QKeySequence(QKeySequence.Preferences).isEmpty()
                      else QKeySequence("Ctrl+,"))
        a.setMenuRole(QAction.PreferencesRole)
        a.triggered.connect(self.open_options)
        em.addAction(a)
        pm = mb.addMenu("&Playback")
        for text, slot, sc in (("Play / pause", lambda: self.timeline.toggle_play(), "Ctrl+P"),
                               ("Go to first lyric", lambda: self.timeline.go_first_lyric(), "Ctrl+Home"),
                               ("Load song audio…", lambda: self.timeline.choose_audio(), "Ctrl+Shift+A")):
            a = QAction(text, self)
            a.triggered.connect(slot)
            a.setShortcut(sc)
            pm.addAction(a)
        tm = mb.addMenu("&Tools")
        self.act_align = QAction("Align lyrics to song audio…", self)
        self.act_align.triggered.connect(self.align_to_audio)
        tm.addAction(self.act_align)
        a = QAction("Remove downloaded alignment model", self)
        a.triggered.connect(self.remove_model)
        tm.addAction(a)
        dm = mb.addMenu("&Dictionaries")
        a = QAction("English syllables…", self)
        a.triggered.connect(self.edit_en_dict)
        dm.addAction(a)
        a = QAction("Japanese readings…", self)
        a.triggered.connect(self.edit_ja_dict)
        dm.addAction(a)
        hm = mb.addMenu("&Help")
        a = QAction("About Lyridan", self)
        a.triggered.connect(lambda: QMessageBox.about(self, "About Lyridan", about_text()))
        hm.addAction(a)
        a = QAction("Open settings folder", self)
        a.triggered.connect(lambda: _open_folder(config_dir()))
        hm.addAction(a)

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)

        cards = QHBoxLayout()
        self.lyrics_card = FileCard("1. Lyrics", "Drop a .ttml or .lrc file here")
        self.lyrics_card.browse.clicked.connect(self.open_lyrics)
        self.lyrics_card.clear.clicked.connect(self.clear_lyrics)
        self.beat_card = FileCard("2. Beatmap", "Drop the Rocksmith XML of your chart (lead/rhythm/bass)")
        self.beat_card.browse.clicked.connect(self.open_beatmap)
        self.beat_card.clear.clicked.connect(self.clear_beatmap)
        cards.addWidget(self.lyrics_card, 3)
        cards.addWidget(self.beat_card, 3)
        new_btn = QPushButton("New chart…")
        new_btn.setToolTip("Clear the lyrics, beatmap, audio and edits to start on another song "
                           "(asks first; your settings are kept)")
        new_btn.clicked.connect(self.new_chart)
        new_btn.setAutoDefault(False)
        new_btn.setFocusPolicy(Qt.NoFocus)
        opt_btn = QPushButton("⚙  Options")
        opt_btn.setToolTip("App options: theme, text size, playback, timeline keys, export folder… "
                           "(also Edit → Options)")
        opt_btn.clicked.connect(self.open_options)
        opt_btn.setAutoDefault(False)
        opt_btn.setFocusPolicy(Qt.NoFocus)
        side = QVBoxLayout()
        side.setSpacing(6)
        side.addWidget(opt_btn)
        side.addStretch(1)
        side.addWidget(new_btn)
        cards.addLayout(side)
        root.addLayout(cards)

        split = QSplitter(Qt.Horizontal)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_editor(), "Lyrics")
        self.rs_preview = QPlainTextEdit()
        self.rs_preview.setReadOnly(True)
        mono = QFont("Consolas" if os.name == "nt" else "Menlo")
        mono.setStyleHint(QFont.Monospace)
        self.rs_preview.setFont(mono)
        prev_wrap = QWidget()
        pl = QVBoxLayout(prev_wrap)
        prow = QHBoxLayout()
        self.preview_mode = QComboBox()
        self.preview_mode.addItems(["Rocksmith lines", "Vocals XML"])
        self.preview_mode.currentIndexChanged.connect(self._update_preview)
        prow.addWidget(QLabel("Show:"))
        prow.addWidget(self.preview_mode)
        prow.addStretch(1)
        pl.addLayout(prow)
        pl.addWidget(self.rs_preview)
        self.tabs.addTab(prev_wrap, "Output preview")
        self.notes = QListWidget()
        self.notes.setWordWrap(True)
        self.tabs.addTab(self.notes, "Notes")
        self.timeline = TimelinePanel()
        self.timeline.entryActivated.connect(self._on_entry_activated)
        self.timeline.audioChanged.connect(self._on_audio_changed)
        self.timeline.leaveRequested.connect(lambda: self.table.setFocus(Qt.OtherFocusReason))
        left = QSplitter(Qt.Vertical)
        left.addWidget(self.tabs)
        left.addWidget(self.timeline)
        left.setStretchFactor(0, 3)
        left.setStretchFactor(1, 2)
        left.setSizes([360, 440])
        left.setChildrenCollapsible(False)
        split.addWidget(left)

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setMinimumWidth(360)
        settings_scroll.setWidget(self._build_settings())
        split.addWidget(settings_scroll)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([980, 400])
        root.addWidget(split, 1)

        bottom = QHBoxLayout()
        self.offset_label = QLabel("")
        self.offset_label.setWordWrap(True)
        bottom.addWidget(self.offset_label, 1)
        self.btn_text = QPushButton("Export text / LRC…")
        self.btn_text.clicked.connect(self.export_text)
        self.btn_native = QPushButton("Export native script XML…")
        self.btn_native.clicked.connect(self.export_native)
        self.btn_export = QPushButton("Export Rocksmith vocals XML…")
        self.btn_export.setDefault(True)
        self.btn_export.setMinimumHeight(34)
        f = self.btn_export.font()
        f.setBold(True)
        self.btn_export.setFont(f)
        self.btn_export.clicked.connect(self.export_vocals)
        for b in (self.btn_text, self.btn_native, self.btn_export):
            bottom.addWidget(b)
        root.addLayout(bottom)
        self.setCentralWidget(central)
        self._update_buttons()

    def _build_editor(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        tip = QLabel("Edit the <b>Syllables</b> column to fix anything: words are separated by spaces, syllables "
                     "by <b>-</b>, and <b>/</b> forces a Rocksmith line break. Timing is kept automatically. "
                     "Right-click a line to reset it.")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        from .align_dialog import LRC_WARNING
        self.lrc_banner = QFrame()
        self.lrc_banner.setStyleSheet("QFrame{background:#e6f0fb; border:1px solid #8bb4e6; border-radius:6px;}"
                                      "QLabel{color:#14304f; border:none;}")
        bl = QHBoxLayout(self.lrc_banner)
        bl.setContentsMargins(10, 6, 10, 6)
        warn = QLabel("ℹ " + LRC_WARNING)
        warn.setWordWrap(True)
        bl.addWidget(warn, 1)
        self.btn_align = QPushButton("Align to song audio…")
        self.btn_align.clicked.connect(self.align_to_audio)
        bl.addWidget(self.btn_align)
        self.lrc_banner.setVisible(False)
        lay.addWidget(self.lrc_banner)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Time", "Source", "Syllables (editable)", "Notes"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.Interactive)
        hh.resizeSection(3, 160)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
                                   QAbstractItemView.AnyKeyPressed)
        self.table.setWordWrap(True)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.table.cellDoubleClicked.connect(self._on_cell_double)
        lay.addWidget(self.table, 1)
        self.empty_hint = QLabel("No lyrics loaded yet.\n\nDrop a .ttml (e.g. Apple Music syllable lyrics) or "
                                 ".lrc file onto this window,\nthen drop the Rocksmith XML of your chart for the beatmap.")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setStyleSheet("color: gray; font-size: 14px;")
        lay.addWidget(self.empty_hint)
        return w

    def _group(self, title: str):
        g = QGroupBox(title)
        f = QFormLayout(g)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        return g, f

    def _build_settings(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        S = self

        # language
        g, f = self._group("Language")
        S.cb_lang = QComboBox()
        for k, v in (("auto", "Auto-detect"), ("en", "English"), ("ja", "Japanese"), ("ru", "Russian"),
                     ("ja_romaji", "Japanese (already romanized)")):
            S.cb_lang.addItem(v, k)
        f.addRow("Lyrics language", S.cb_lang)
        S.cb_romanize = QComboBox()
        S.cb_romanize.addItem("Romanized / latinized (Rocksmith font)", True)
        S.cb_romanize.addItem("Keep native script", False)
        f.addRow("Main export", S.cb_romanize)
        S.lang_info = QLabel("")
        S.lang_info.setStyleSheet("color: gray;")
        f.addRow(S.lang_info)
        lay.addWidget(g)

        # japanese
        g, f = self._group("Japanese")
        S.grp_ja = g
        S.cb_ja_syl = QComboBox()
        for k, v in (("mora_n", "Mora, ん/っ joined (ko-n→kon)"), ("mora", "Every mora (ko-n-ni-chi-wa)"),
                     ("syllable", "Syllables (long vowels joined: tou-kyou)")):
            S.cb_ja_syl.addItem(v, k)
        f.addRow("Syllables", S.cb_ja_syl)
        S.cb_ja_long = QComboBox()
        for k, v in (("kana", "As written (tou, ee, raamen)"), ("macron", "Macrons (tō, ē, rāmen)"),
                     ("plain", "Simplified (to, e, ramen)")):
            S.cb_ja_long.addItem(v, k)
        f.addRow("Long vowels", S.cb_ja_long)
        S.cb_ja_wo = QComboBox()
        S.cb_ja_wo.addItem("o (Hepburn)", "o")
        S.cb_ja_wo.addItem("wo", "wo")
        f.addRow("Particle を", S.cb_ja_wo)
        S.cb_ja_ha = QComboBox()
        S.cb_ja_ha.addItem("wa / e (as pronounced)", "wa")
        S.cb_ja_ha.addItem("ha / he (as written)", "ha")
        f.addRow("Particles は / へ", S.cb_ja_ha)
        S.ck_ja_apos = QCheckBox("n' before vowels (shin'ai)")
        S.ck_ja_lyric = QCheckBox("Lyric readings (私→watashi, 明日→ashita…)")
        S.ck_ja_apple = QCheckBox("Use romaji included in the TTML (Apple)")
        S.ck_ja_foreign = QCheckBox("Katakana loanwords in English (ラブ→love)")
        for c in (S.ck_ja_apos, S.ck_ja_lyric, S.ck_ja_apple, S.ck_ja_foreign):
            f.addRow(c)
        b = QPushButton("Reading dictionary…")
        b.clicked.connect(self.edit_ja_dict)
        f.addRow(b)
        lay.addWidget(g)

        # russian
        g, f = self._group("Russian")
        S.grp_ru = g
        from ..lang.russian import SCHEMES
        S.cb_ru_scheme = QComboBox()
        for k, v in SCHEMES.items():
            S.cb_ru_scheme.addItem(v, k)
        f.addRow("Latinization", S.cb_ru_scheme)
        S.cb_ru_syl = QComboBox()
        S.cb_ru_syl.addItem("Phonetic, open syllables (ко-шка)", "phonetic")
        S.cb_ru_syl.addItem("Closed (кош-ка)", "closed")
        f.addRow("Syllables", S.cb_ru_syl)
        S.ck_ru_yo = QCheckBox("Restore ё (еще → ещё, идет → идёт)")
        S.ck_ru_soft = QCheckBox("Show ь as ' (practical scheme)")
        f.addRow(S.ck_ru_yo)
        f.addRow(S.ck_ru_soft)
        lay.addWidget(g)

        # english
        g, f = self._group("English")
        S.ck_hyphen = QCheckBox("Split hyphenated words (ooh-ooh → ooh ooh)")
        f.addRow(S.ck_hyphen)
        b = QPushButton("Syllable dictionary…")
        b.clicked.connect(self.edit_en_dict)
        f.addRow(b)
        lay.addWidget(g)

        # sync
        g, f = self._group("Sync to beatmap")
        S.ck_silence = QCheckBox("Audio has intro silence")
        S.sp_silence = QDoubleSpinBox()
        S.sp_silence.setRange(0, 60)
        S.sp_silence.setDecimals(3)
        S.sp_silence.setSuffix(" s")
        row = QHBoxLayout()
        row.addWidget(S.ck_silence)
        row.addWidget(S.sp_silence)
        f.addRow(row)
        S.ck_bars = QCheckBox("Audio has empty bars before the song")
        S.sp_bars = QSpinBox()
        S.sp_bars.setRange(0, 16)
        S.sp_bars.setSuffix(" bars")
        row = QHBoxLayout()
        row.addWidget(S.ck_bars)
        row.addWidget(S.sp_bars)
        f.addRow(row)
        S.ck_lyricoff = QCheckBox("Apply TTML lyricOffset")
        S.ck_leading = QCheckBox("Compensate TTML leadingSilence")
        f.addRow(S.ck_lyricoff)
        f.addRow(S.ck_leading)
        S.sp_manual = QDoubleSpinBox()
        S.sp_manual.setRange(-60000, 60000)
        S.sp_manual.setDecimals(0)
        S.sp_manual.setSingleStep(10)
        S.sp_manual.setSuffix(" ms")
        f.addRow("Manual offset", S.sp_manual)
        S.cb_snap = QComboBox()
        for k in ("off", "1/4", "1/8", "1/12", "1/16", "1/24", "1/32", "1/64"):
            S.cb_snap.addItem("No snapping" if k == "off" else f"{k} notes", k)
        f.addRow("Snap to grid", S.cb_snap)
        S.cb_gap = QComboBox()
        for k in ("0", "1/64", "1/32", "1/16"):
            S.cb_gap.addItem("None" if k == "0" else f"{k} note", k)
        f.addRow("Min. gap between notes", S.cb_gap)
        S.cb_weight = QComboBox()
        S.cb_weight.addItem("Equal", "equal")
        S.cb_weight.addItem("By letters", "letters")
        f.addRow("Syllables inside a word", S.cb_weight)
        S.cb_bg = QComboBox()
        S.cb_bg.addItem("Leave out", "exclude")
        S.cb_bg.addItem("Include when not overlapping", "nonoverlap")
        f.addRow("Background vocals", S.cb_bg)
        lay.addWidget(g)

        # formatting
        g, f = self._group("Rocksmith formatting")
        S.sp_maxsyl = QSpinBox()
        S.sp_maxsyl.setRange(0, 40)
        S.sp_maxsyl.setSpecialValueText("No limit")
        S.sp_maxsyl.setSuffix(" syllables")
        S.sp_maxsyl.setToolTip("Charters keep a Rocksmith lyric line to about 7-8 sung syllables. Lines 1-2 over "
                               "are kept whole when any split would leave an awkward fragment. Japanese gets +4.")
        f.addRow("Max syllables per line", S.sp_maxsyl)
        S.sp_maxchars = QSpinBox()
        S.sp_maxchars.setRange(0, 200)
        S.sp_maxchars.setSpecialValueText("No limit")
        S.sp_maxchars.setSuffix(" characters")
        f.addRow("Max line length", S.sp_maxchars)
        S.sp_gapsplit = QDoubleSpinBox()
        S.sp_gapsplit.setRange(0.1, 10)
        S.sp_gapsplit.setDecimals(2)
        S.sp_gapsplit.setSuffix(" s")
        f.addRow("New line after pauses ≥", S.sp_gapsplit)
        S.ck_caps = QCheckBox("Capitalize the first word of each line")
        S.ck_ascii = QCheckBox("Rocksmith-safe characters only (ASCII)")
        f.addRow(S.ck_caps)
        f.addRow(S.ck_ascii)
        S.le_punct = QLineEdit()
        S.le_punct.setMaxLength(12)
        f.addRow("Keep punctuation", S.le_punct)
        S.sp_note = QSpinBox()
        S.sp_note.setRange(0, 255)
        f.addRow("Vocal note value", S.sp_note)
        lay.addWidget(g)

        reset = QPushButton("Restore default settings")
        reset.clicked.connect(self.reset_settings)
        lay.addWidget(reset)
        opts = QPushButton("Options… (theme, playback, notices, build info)")
        opts.clicked.connect(self.open_options)
        lay.addWidget(opts)
        lay.addStretch(1)

        # change notifications
        for cb in (S.cb_lang, S.cb_romanize, S.cb_ja_syl, S.cb_ja_long, S.cb_ja_wo, S.cb_ja_ha, S.cb_ru_scheme,
                   S.cb_ru_syl, S.cb_snap, S.cb_gap, S.cb_weight, S.cb_bg):
            cb.currentIndexChanged.connect(self._settings_changed)
        for ck in (S.ck_ja_apos, S.ck_ja_lyric, S.ck_ja_apple, S.ck_ja_foreign, S.ck_ru_yo, S.ck_ru_soft,
                   S.ck_hyphen, S.ck_silence, S.ck_bars, S.ck_lyricoff, S.ck_leading, S.ck_caps, S.ck_ascii):
            ck.toggled.connect(self._settings_changed)
        for sp in (S.sp_silence, S.sp_bars, S.sp_manual, S.sp_maxsyl, S.sp_maxchars, S.sp_gapsplit, S.sp_note):
            sp.valueChanged.connect(self._settings_changed)
        S.le_punct.textChanged.connect(self._settings_changed)
        return w

    def _build_info_group(self) -> QGroupBox:
        """Stable builds: just the version. Dev builds: full build/commit/runtime details."""
        g = QGroupBox("Build information")
        f = QFormLayout(g)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        if buildinfo.is_dev():
            badge = QLabel("DEVELOPMENT BUILD - may be unstable")
            badge.setStyleSheet("background:#f5a524; color:black; font-weight:bold; padding:3px 6px; "
                                "border-radius:4px;")
            f.addRow(badge)
        for k, v in buildinfo.details():
            lbl = QLabel(v)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            f.addRow(k, lbl)
        for k, url in buildinfo.links():
            lbl = QLabel(f'<a href="{url}">{url.split("/")[-1][:12] if "commit" in url else "open"}</a>')
            lbl.setOpenExternalLinks(True)
            f.addRow(k, lbl)
        if buildinfo.is_dev():
            copy = QPushButton("Copy build info (for bug reports)")
            copy.clicked.connect(lambda: (QApplication.clipboard().setText(buildinfo.as_text()),
                                          self.statusBar().showMessage("Build info copied", 4000)))
            f.addRow(copy)
        return g

    # ------------------------------------------------------------ settings <-> UI
    @staticmethod
    def _set_combo(cb: QComboBox, value):
        i = cb.findData(value)
        cb.setCurrentIndex(i if i >= 0 else 0)

    def _load_settings_into_ui(self):
        s, S = self.settings, self
        self._loading_ui = True
        try:
            self._set_combo(S.cb_lang, s.language)
            self._set_combo(S.cb_romanize, s.romanize)
            self._set_combo(S.cb_ja_syl, s.ja.syllables)
            self._set_combo(S.cb_ja_long, s.ja.long_vowels)
            self._set_combo(S.cb_ja_wo, s.ja.particle_wo)
            self._set_combo(S.cb_ja_ha, s.ja.particle_ha)
            S.ck_ja_apos.setChecked(s.ja.n_apostrophe)
            S.ck_ja_lyric.setChecked(s.ja.lyric_readings)
            S.ck_ja_apple.setChecked(s.use_source_romaji)
            S.ck_ja_foreign.setChecked(s.ja.foreign_spelling)
            self._set_combo(S.cb_ru_scheme, s.ru_scheme)
            self._set_combo(S.cb_ru_syl, s.ru_syllables)
            S.ck_ru_yo.setChecked(s.ru_restore_yo)
            S.ck_ru_soft.setChecked(s.ru_soft_sign)
            S.ck_hyphen.setChecked(s.split_hyphenated)
            S.ck_silence.setChecked(s.intro_silence)
            S.sp_silence.setValue(s.intro_silence_seconds)
            S.ck_bars.setChecked(s.two_empty_bars)
            S.sp_bars.setValue(s.empty_bars)
            S.ck_lyricoff.setChecked(s.apply_lyric_offset)
            S.ck_leading.setChecked(s.apply_leading_silence)
            S.sp_manual.setValue(s.manual_offset_ms)
            self._set_combo(S.cb_snap, s.snap)
            self._set_combo(S.cb_gap, s.min_gap)
            self._set_combo(S.cb_weight, s.syllable_weighting)
            self._set_combo(S.cb_bg, s.background)
            S.sp_maxsyl.setValue(s.max_line_syllables)
            S.sp_maxchars.setValue(s.max_line_chars)
            S.sp_gapsplit.setValue(s.gap_split_seconds)
            S.ck_caps.setChecked(s.capitalize_lines)
            S.ck_ascii.setChecked(s.ascii_only)
            S.le_punct.setText(s.keep_punctuation)
            S.sp_note.setValue(s.note_value)
        finally:
            self._loading_ui = False

    def _read_settings_from_ui(self):
        s, S = self.settings, self
        s.language = S.cb_lang.currentData()
        s.romanize = S.cb_romanize.currentData()
        s.ja.syllables = S.cb_ja_syl.currentData()
        s.ja.long_vowels = S.cb_ja_long.currentData()
        s.ja.particle_wo = S.cb_ja_wo.currentData()
        s.ja.particle_ha = S.cb_ja_ha.currentData()
        s.ja.particle_he = "he" if s.ja.particle_ha == "ha" else "e"
        s.ja.n_apostrophe = S.ck_ja_apos.isChecked()
        s.ja.lyric_readings = S.ck_ja_lyric.isChecked()
        s.use_source_romaji = S.ck_ja_apple.isChecked()
        s.ja.foreign_spelling = S.ck_ja_foreign.isChecked()
        s.ja.user_dict = dict(self.ja_user_dict)
        s.ru_scheme = S.cb_ru_scheme.currentData()
        s.ru_syllables = S.cb_ru_syl.currentData()
        s.ru_restore_yo = S.ck_ru_yo.isChecked()
        s.ru_soft_sign = S.ck_ru_soft.isChecked()
        s.split_hyphenated = S.ck_hyphen.isChecked()
        s.intro_silence = S.ck_silence.isChecked()
        s.intro_silence_seconds = S.sp_silence.value()
        s.two_empty_bars = S.ck_bars.isChecked()
        s.empty_bars = S.sp_bars.value()
        s.apply_lyric_offset = S.ck_lyricoff.isChecked()
        s.apply_leading_silence = S.ck_leading.isChecked()
        s.manual_offset_ms = S.sp_manual.value()
        s.snap = S.cb_snap.currentData()
        s.min_gap = S.cb_gap.currentData()
        s.syllable_weighting = S.cb_weight.currentData()
        s.background = S.cb_bg.currentData()
        s.max_line_syllables = S.sp_maxsyl.value()
        s.max_line_chars = S.sp_maxchars.value()
        s.gap_split_seconds = S.sp_gapsplit.value()
        s.capitalize_lines = S.ck_caps.isChecked()
        s.ascii_only = S.ck_ascii.isChecked()
        s.keep_punctuation = S.le_punct.text()
        s.note_value = S.sp_note.value()

    def _settings_changed(self, *_):
        if self._loading_ui:
            return
        self._read_settings_from_ui()
        self._recalc_timer.start()

    def reset_acknowledgements(self):
        self.settings.disclaimer_acknowledged = False
        self._disclaimer_seen_this_session = False
        self.settings.save()
        self.statusBar().showMessage("Acknowledgements reset - the export disclaimer will be shown again.", 6000)

    def _confirm_disclaimer(self) -> bool:
        """Shown before the first vocals export of each session until 'don't show again' is ticked."""
        if self.settings.disclaimer_acknowledged or getattr(self, "_disclaimer_seen_this_session", False):
            return True
        dlg = DisclaimerDialog(self)
        if not dlg.exec():
            return False
        self._disclaimer_seen_this_session = True
        if dlg.dont_show.isChecked():
            self.settings.disclaimer_acknowledged = True
            self.settings.save()
        return True

    def reset_settings(self):
        en = dict(self.settings.en_user_dict)
        ack = self.settings.disclaimer_acknowledged
        self.settings = Settings()
        self.settings.disclaimer_acknowledged = ack
        self.settings.en_user_dict = en
        self.settings.ja.user_dict = dict(self.ja_user_dict)
        self._load_settings_into_ui()
        self._read_settings_from_ui()
        self.recalculate()

    # ------------------------------------------------------------------ files
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for url in ev.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self.load_any(path)

    def load_any(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".lyridan":
            return self.load_project(path)
        if ext in AUDIO_EXT:
            return self.timeline.load_audio(path)
        if ext == ".xml":
            head = open(path, "rb").read(4096).decode("utf-8", "ignore")
            if "<vocals" in head:
                return self.load_reference(path)
            if "<song" in head or "<ebeats" in head:
                return self.load_beatmap(path)
        return self.load_lyrics_file(path)

    def open_lyrics(self):
        p, _ = QFileDialog.getOpenFileName(self, "Open lyrics", self._last_dir(), LYRIC_FILTER)
        if p:
            self.load_lyrics_file(p)

    def open_beatmap(self):
        p, _ = QFileDialog.getOpenFileName(self, "Open Rocksmith arrangement XML", self._last_dir(), XML_FILTER)
        if p:
            self.load_beatmap(p)

    def open_reference(self):
        p, _ = QFileDialog.getOpenFileName(self, "Existing vocals XML to compare with", self._last_dir(), XML_FILTER)
        if p:
            self.load_reference(p)

    def _last_dir(self):
        for p in (self.source_path, self.beatmap_path):
            if p:
                return os.path.dirname(p)
        return os.path.expanduser("~")

    def load_lyrics_file(self, path: str, keep_overrides: bool = False):
        try:
            src = load_lyrics(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Could not read lyrics", f"{os.path.basename(path)}\n\n{e}")
            return
        if not src.lines:
            QMessageBox.warning(self, "No lyrics", "No lyric lines were found in this file.")
            return
        self.source = src
        self.source_path = path
        if not keep_overrides:
            self.overrides = {}
        timing = {"syllable": "syllable-synced", "word": "word-synced", "line": "line-synced",
                  "none": "not synced"}.get(src.timing, src.timing)
        extra = ", includes romaji" if src.has_romaji else ""
        if src.timing == "line":
            extra += " - align to audio for syllable timing"
        self.lyrics_card.set_file(path, f"{len(src.lines)} lines, {timing}{extra}")
        self.settings.last_session["lyrics"] = path
        self._update_lrc_banner()
        self.recalculate()

    def _update_lrc_banner(self):
        self.lrc_banner.setVisible(bool(self.source) and self.source.timing in ("line", "none"))

    def use_aligned_source(self, src):
        """Use audio-aligned lyrics without saving them to a file."""
        self.source = src
        self.overrides = {}
        self.lyrics_card.set_file(self.source_path, f"{len(src.lines)} lines, audio-aligned (not saved)")
        self._update_lrc_banner()
        self.recalculate()

    def align_to_audio(self):
        from .align_dialog import run_alignment
        if not self.source:
            QMessageBox.information(self, "Lyridan", "Load a .lrc lyrics file first.")
            return
        run_alignment(self)

    def remove_model(self):
        from ..align import ModelStore
        st = ModelStore()
        if not st.is_installed():
            QMessageBox.information(self, "Lyridan", "The alignment model is not downloaded.")
            return
        if QMessageBox.question(self, "Lyridan", "Delete the downloaded alignment model (~340 MB)?") == \
                QMessageBox.Yes:
            st.remove()
            self.statusBar().showMessage("Alignment model removed.", 5000)

    def load_beatmap(self, path: str):
        try:
            bm = parse_beatmap(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Could not read beatmap", f"{os.path.basename(path)}\n\n{e}")
            return
        if (self.beatmap_path and os.path.normcase(os.path.abspath(self.beatmap_path)) !=
                os.path.normcase(os.path.abspath(path)) and self.timeline.player.loaded):
            self.timeline.unload_audio()           # that audio belonged to the previous chart
            self.settings.last_session.pop("audio", None)
            self.statusBar().showMessage("New chart loaded - pick its audio with 🎵 Audio…", 10000)
        self.beatmap = bm
        self.beatmap_path = path
        bars = len(bm.measure_starts)
        name = " - ".join(x for x in (bm.artist, bm.title) if x)
        self.beat_card.set_file(path, f"{name}  ·  {bm.arrangement or 'arrangement'}, {bars} bars, "
                                      f"first beat {bm.beats[0]:.3f}s")
        self.settings.last_session["beatmap"] = path
        self.recalculate()

    def load_reference(self, path: str):
        try:
            self.reference = parse_vocals(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Could not read vocals", f"{os.path.basename(path)}\n\n{e}")
            return
        self.reference_path = path
        self.settings.last_session["reference"] = path
        self.statusBar().showMessage(f"Comparing with {os.path.basename(path)} ({len(self.reference)} vocals) - "
                                     "shown in the timeline's reference rows. File → Remove comparison vocals "
                                     "hides it.", 10000)
        self.recalculate()

    def new_chart(self):
        """Start over for another song. Asks first; Cancel is the default so Enter/Esc never clear."""
        if not (self.source or self.beatmap or self.timeline.player.loaded or self.reference):
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Start a new chart?")
        box.setText("<b>Clear everything for a new chart?</b>")
        box.setInformativeText("This removes the loaded lyrics, beatmap, audio, comparison vocals, your syllable "
                               "edits and the manual offset. Options and conversion settings are kept.\n\n"
                               "Unsaved edits are lost - use Save project first if you want to keep them.")
        save = box.addButton("Save project first…", QMessageBox.ActionRole)
        clear = box.addButton("Clear and start new", QMessageBox.DestructiveRole)
        cancel = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        clear.setEnabled(False)                    # guards against a reflex click / Enter
        timer = QTimer(box)                        # owned by the dialog: never fires after it closes
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: clear.setEnabled(True))
        timer.start(1200)
        box.exec()
        if box.clickedButton() is save:
            self.save_project()
            return
        if box.clickedButton() is not clear:
            return
        self.timeline.unload_audio()
        self.clear_reference()
        self.clear_beatmap()
        self.clear_lyrics()
        self.settings.manual_offset_ms = 0.0
        self.settings.language = "auto"
        self.settings.last_session = {}
        self._load_settings_into_ui()
        self.recalculate()
        self.timeline.seek_chart(0.0)
        self.timeline.view.horizontalScrollBar().setValue(0)
        self.statusBar().showMessage("Ready for a new chart: drop the lyrics, the chart XML and its audio.", 10000)

    def clear_lyrics(self):
        self.settings.last_session.pop("lyrics", None)
        self.source = None
        self.source_path = None
        self.overrides = {}
        self.lyrics_card.set_file(None)
        self._update_lrc_banner()
        self.recalculate()

    def clear_beatmap(self):
        self.settings.last_session.pop("beatmap", None)
        self.beatmap = None
        self.beatmap_path = None
        self.beat_card.set_file(None)
        self.recalculate()

    def clear_reference(self):
        self.settings.last_session.pop("reference", None)
        self.reference = []
        self.reference_path = None
        self.recalculate()

    # ------------------------------------------------------------------ processing
    def recalculate(self):
        from ..pipeline import LANG_NAMES, process
        from ..rocksmith import build_vocals
        self._recalc_timer.stop()
        if not self.source:
            self.processed = None
            self.result = None
            self.grp_ja.setVisible(True)
            self.grp_ru.setVisible(True)
            self._fill_table()
            self._refresh_outputs()
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.processed = process(self.source, self.settings, overrides=self.overrides)
            self.result = build_vocals(self.processed.lines, self.settings, self.beatmap,
                                       self.source.lyric_offset, self.source.leading_silence)
        except Exception:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Processing error", traceback.format_exc())
            return
        QApplication.restoreOverrideCursor()
        lang = LANG_NAMES.get(self.processed.language, self.processed.language)
        used = {l.lang for l in self.processed.lines} | {self.processed.language}
        self.grp_ja.setVisible("ja" in used or "ja_romaji" in used)
        self.grp_ru.setVisible("ru" in used)
        self.lang_info.setText(f"Detected: {lang}" if self.settings.language == "auto" else f"Using: {lang}")
        self._fill_table()
        self._refresh_outputs()

    def _fill_table(self):
        from ..pipeline import format_line
        self._table_updating = True
        self.table.setRowCount(0)
        lines = self.processed.lines if self.processed else []
        self.empty_hint.setVisible(not lines)
        self.table.setVisible(bool(lines))
        src_lines = self.source.lines if self.source else []
        for ln in lines:
            r = self.table.rowCount()
            self.table.insertRow(r)
            m, s = divmod(ln.start, 60)
            t = QTableWidgetItem(f"{int(m):02d}:{s:06.3f}")
            t.setFlags(t.flags() & ~Qt.ItemIsEditable)
            t.setData(Qt.UserRole, ln.index)
            src_text = src_lines[ln.index].text if 0 <= ln.index < len(src_lines) else ln.source_text
            if ln.background:
                src_text = "[bg] " + src_text
            a = QTableWidgetItem(src_text)
            a.setFlags(a.flags() & ~Qt.ItemIsEditable)
            b = QTableWidgetItem(format_line(ln))
            notes = list(ln.warnings)
            if ln.manual:
                f = b.font()
                f.setBold(True)
                b.setFont(f)
                b.setForeground(QColor("#3e9bf5"))
                notes.insert(0, "edited")
            if not ln.timed:
                notes.append("estimated timing")
            c = QTableWidgetItem("; ".join(notes))
            c.setToolTip("\n".join(notes))
            c.setFlags(c.flags() & ~Qt.ItemIsEditable)
            if any("unknown" in n for n in ln.warnings):
                c.setForeground(QColor("#e5484d"))
            elif ln.warnings:
                c.setForeground(QColor("#f5a524"))
            for col, it in enumerate((t, a, b, c)):
                self.table.setItem(r, col, it)
        self.table.resizeRowsToContents()
        self._table_updating = False

    def _on_cell_double(self, row, col):
        if col == 0 and self.result:
            idx = self.table.item(row, 0).data(Qt.UserRole)
            ln = next((l for l in self.processed.lines if l.index == idx), None)
            if ln:
                self._seek_line(idx)

    def _seek_line(self, line_index: int):
        """Move the playhead to the first syllable of a lyric line."""
        if not self.result:
            return
        for i, li in enumerate(self.result.entry_line):
            if li == line_index:
                t = self.result.entries[i].time
                self.timeline.seek_chart(max(0.0, t - 0.5))
                self.timeline.view.scroll_to_time(t, 120)
                return

    def _on_entry_activated(self, entry_index: int):
        """Timeline click / playback reached a syllable: select its lyric row."""
        if not self.result or not (0 <= entry_index < len(self.result.entry_line)):
            return
        line_index = self.result.entry_line[entry_index]
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.data(Qt.UserRole) == line_index:
                if self.table.currentRow() != r:
                    self.table.blockSignals(True)
                    self.table.selectRow(r)
                    self.table.blockSignals(False)
                    self.table.scrollToItem(it)
                break

    def _on_audio_changed(self, path: str):
        self.settings.last_session["audio"] = path
        self.statusBar().showMessage(f"Audio loaded: {os.path.basename(path)}", 5000)

    def _song_shift(self) -> float:
        """Intro silence + empty bars: how much later the chart audio is than the original song."""
        sh = self.settings.intro_silence_seconds if self.settings.intro_silence else 0.0
        if self.settings.two_empty_bars and self.beatmap and self.beatmap.beats:
            ms = self.beatmap.measure_starts
            sh += self.beatmap.first_n_measures_end(self.settings.empty_bars) - (ms[0] if ms else 0.0)
        return sh

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._table_updating or item.column() != 2:
            return
        idx = self.table.item(item.row(), 0).data(Qt.UserRole)
        text = item.text().strip()
        if text:
            self.overrides[idx] = text
        else:
            self.overrides.pop(idx, None)
        QTimer.singleShot(0, self.recalculate)

    def _table_menu(self, pos):
        row = self.table.rowAt(pos.y())
        menu = QMenu(self)
        if row >= 0:
            idx = self.table.item(row, 0).data(Qt.UserRole)
            a = menu.addAction("Reset this line")
            a.setEnabled(idx in self.overrides)
            a.triggered.connect(lambda: (self.overrides.pop(idx, None), self.recalculate()))
            a = menu.addAction("Show in timeline")
            a.triggered.connect(lambda: self._on_cell_double(row, 0))
        a = menu.addAction("Reset all edits")
        a.setEnabled(bool(self.overrides))
        a.triggered.connect(lambda: (self.overrides.clear(), self.recalculate()))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _refresh_outputs(self):
        res = self.result
        silence_end = self.settings.intro_silence_seconds if self.settings.intro_silence else 0.0
        bars_end = 0.0
        if self.beatmap and self.settings.two_empty_bars and self.beatmap.beats:
            bars_end = self.beatmap.first_n_measures_end(self.settings.empty_bars)
        self.timeline.set_project(self.beatmap, res.entries if res else [], self.reference,
                                  silence_end, bars_end, self._song_shift())
        # offset summary
        if res:
            parts = " + ".join(f"{name} ({v:+.3f})" for name, v in res.offset.parts) or "no shift"
            self.offset_label.setText(f"<b>Offset {res.offset.total:+.3f} s</b> = {parts}  ·  "
                                      f"{len(res.entries)} vocals")
        else:
            self.offset_label.setText("")
        # notes
        self.notes.clear()
        items = []
        if self.processed:
            items += [("info", w) for w in self.processed.warnings]
        if res:
            items += [("warn", w) for w in res.warnings]
        if not self.beatmap and self.source:
            items.insert(0, ("warn", "No beatmap loaded: lyrics are not snapped to the chart's beat grid."))
        if self.source and self.source.timing in ("line", "none"):
            items.insert(0, ("warn", "Line-synced .lrc: syllable timing is only estimated and likely inaccurate. "
                                     "Prefer a syllable-synced .ttml, or use Tools → Align lyrics to song audio."))
        for kind, text in items:
            it = QListWidgetItem(("⚠ " if kind == "warn" else "• ") + text)
            if kind == "warn":
                it.setForeground(QColor("#f5a524"))
            self.notes.addItem(it)
        self.tabs.setTabText(2, f"Notes ({len(items)})" if items else "Notes")
        self._update_preview()
        self._update_buttons()

    def _update_preview(self):
        res = self.result
        if not res:
            self.rs_preview.setPlainText("")
            return
        if self.preview_mode.currentIndex() == 1:
            lines = ["<?xml version='1.0' encoding='UTF-8'?>", f'<vocals count="{len(res.entries)}">']
            for e in res.entries:
                lines.append(f'  <vocal time="{e.time:.3f}" length="{e.length:.3f}" lyric="{e.lyric}" note="{e.note}"/>')
            lines.append("</vocals>")
            self.rs_preview.setPlainText("\n".join(lines))
            return
        out, cur, start = [], "", None
        for e in res.entries:
            if start is None:
                start = e.time
            lyr = e.lyric
            if lyr.endswith("+"):
                cur += lyr[:-1]
                m, s = divmod(start, 60)
                out.append(f"[{int(m):02d}:{s:06.3f}]  {cur}")
                cur, start = "", None
            elif lyr.endswith("-"):
                cur += lyr[:-1]
            else:
                cur += lyr + " "
        if cur:
            out.append(cur)
        self.rs_preview.setPlainText("\n".join(out))

    def _update_buttons(self):
        ok = bool(self.result and self.result.entries)
        for b in (self.btn_export, self.btn_native, self.btn_text):
            b.setEnabled(ok)
        if self.processed:
            self.btn_native.setEnabled(ok and self.processed.language in ("ja", "ru"))

    # ------------------------------------------------------------------ export
    def _default_out(self, suffix: str) -> str:
        if self.settings.export_folder and os.path.isdir(self.settings.export_folder):
            return os.path.join(self.settings.export_folder, f"{suffix}.xml")
        if self.beatmap_path:
            return os.path.join(os.path.dirname(self.beatmap_path), f"{suffix}.xml")
        base = self.source_path or os.path.join(os.path.expanduser("~"), "lyrics")
        return os.path.join(os.path.dirname(base), os.path.splitext(os.path.basename(base))[0] + f"_{suffix}.xml")

    def export_vocals(self):
        if not (self.result and self.result.entries):
            return
        if not self._confirm_disclaimer():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Rocksmith vocals", self._default_out("Vocals_RS2"),
                                              XML_FILTER)
        if not path:
            return
        write_vocals(self.result.entries, path)
        self._export_done(path, self.result.warnings)

    def export_native(self):
        from ..pipeline import process
        from ..rocksmith import build_vocals
        if not self.source:
            return
        if not self._confirm_disclaimer():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save native-script vocals",
                                              self._default_out("JVocals_RS2" if self.processed.language == "ja"
                                                                else "Vocals_native_RS2"), XML_FILTER)
        if not path:
            return
        pr = process(self.source, self.settings, native_script=True)
        res = build_vocals(pr.lines, self.settings, self.beatmap, self.source.lyric_offset,
                           self.source.leading_silence, native=True)
        write_vocals(res.entries, path)
        self._export_done(path, res.warnings + ["Native script needs a custom lyrics font in DLC Builder / "
                                                 "the Rocksmith Custom Song Toolkit."])

    def export_text(self):
        from ..exports import lrc, syllabized_text
        if not self.processed:
            return
        base = os.path.splitext(self.source_path or "lyrics")[0]
        path, flt = QFileDialog.getSaveFileName(
            self, "Export text", base + "_syllabized.txt",
            "Syllabized text (*.txt);;Romanized LRC (*.lrc);;Romanized enhanced LRC (*.lrc)")
        if not path:
            return
        if "enhanced" in flt:
            data = lrc(self.processed.lines, enhanced=True)
        elif "LRC" in flt:
            data = lrc(self.processed.lines)
        else:
            data = syllabized_text(self.processed.lines, self.settings.text_syllable_sep,
                                   self.settings.text_word_sep)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(data)
        self._export_done(path, [])

    def _export_done(self, path, warnings):
        msg = f"Saved {os.path.basename(path)} - open it in EOF or Charter and check it against the song before " \
              "building your CDLC."
        self.statusBar().showMessage(msg, 15000)
        if warnings:
            QMessageBox.information(self, "Exported", msg + "\n\n" + "\n".join("• " + w for w in warnings))

    # ------------------------------------------------------------------ dictionaries
    def edit_en_dict(self):
        d = DictDialog("English syllable dictionary",
                       "Your own syllable splits. They override the built-in dictionary. "
                       "Write the syllables with '-' (example: word <b>lyridan</b>, syllables <b>ly-ri-dan</b>).",
                       "Word", "Syllables", self.settings.en_user_dict, self)
        if d.exec():
            self.settings.en_user_dict = d.data()
            self.settings.save()
            self.recalculate()

    def edit_ja_dict(self):
        d = DictDialog("Japanese reading dictionary",
                       "Readings for words or phrases (kanji → hiragana). They are applied before analysis, "
                       "e.g. <b>宇宙</b> → <b>そら</b>, <b>運命</b> → <b>さだめ</b>. "
                       "You can also write furigana straight into a lyric file: 宇宙(そら) or {宇宙|そら}.",
                       "Text", "Reading (kana)", self.ja_user_dict, self)
        if d.exec():
            self.ja_user_dict = d.data()
            self.settings.ja.user_dict = dict(self.ja_user_dict)
            self.settings.save()
            self.recalculate()

    # ------------------------------------------------------------------ projects
    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save project", os.path.splitext(self.source_path or "song")[0]
                                              + ".lyridan", PROJECT_FILTER)
        if not path:
            return
        data = {"lyridan": VERSION, "lyrics": self.source_path, "beatmap": self.beatmap_path,
                "reference": self.reference_path, "settings": self.settings.to_json(),
                "audio": self.timeline.player.path if self.timeline.player.loaded else None,
                "overrides": {str(k): v for k, v in self.overrides.items()}}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        self.statusBar().showMessage(f"Project saved: {os.path.basename(path)}", 8000)

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open project", self._last_dir(), PROJECT_FILTER)
        if path:
            self.load_project(path)

    def load_project(self, path: str):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Could not open project", str(e))
            return
        ack = self.settings.disclaimer_acknowledged
        self.settings = Settings.from_json(data.get("settings", {}))
        self.settings.disclaimer_acknowledged = ack
        self.ja_user_dict = dict(self.settings.ja.user_dict)
        self._load_settings_into_ui()
        self.overrides = {int(k): v for k, v in (data.get("overrides") or {}).items()}
        missing = []
        for key, loader in (("beatmap", self.load_beatmap), ("reference", self.load_reference)):
            p = data.get(key)
            if p and os.path.exists(p):
                loader(p)
            elif p:
                missing.append(p)
        p = data.get("lyrics")
        if p and os.path.exists(p):
            self.load_lyrics_file(p, keep_overrides=True)
        elif p:
            missing.append(p)
        a = data.get("audio")
        if a and os.path.exists(a):
            self.timeline.load_audio(a, quiet=True)
        elif a:
            missing.append(a)
        if missing:
            QMessageBox.warning(self, "Missing files", "These files were not found:\n" + "\n".join(missing))

    def closeEvent(self, ev):
        try:
            self._read_settings_from_ui()
            self.settings.playback_volume = self.timeline.volume.value()
            self.settings.metronome = self.timeline.btn_metro.isChecked()
            self.settings.follow_playhead = self.timeline.btn_follow.isChecked()
            self.settings.save()
        except Exception:  # noqa: BLE001
            pass
        self.timeline.shutdown()
        super().closeEvent(ev)

    # ------------------------------------------------------------------ options / theme / session
    def open_options(self):
        from .options_dialog import OptionsDialog
        self._read_settings_from_ui()
        OptionsDialog(self.settings, self).exec()

    def apply_options(self, reset_ack: bool = False):
        from .themes import apply_theme, current_colors
        app = QApplication.instance()
        apply_theme(app, self.settings.theme, self.settings.ui_font_pt)
        colors = current_colors(self.settings.theme)
        vocals = colors.get("vocals") or (colors["accent"] if self.settings.theme != "light" else "#2e8b57")
        self.timeline.set_accent(vocals, colors)
        self.timeline.preview.set_font_size(self.settings.preview_font_pt)
        self.timeline.volume.setValue(self.settings.playback_volume)
        self.timeline.btn_metro.setChecked(self.settings.metronome)
        self.timeline.btn_follow.setChecked(self.settings.follow_playhead)
        self.timeline.set_navigation(self.settings.timeline_arrow_step, self.settings.timeline_accelerate)
        if reset_ack:
            self._disclaimer_seen_this_session = False
        self.update()

    def restore_session(self):
        if not self.settings.restore_session:
            return
        sess = dict(self.settings.last_session or {})
        for key, loader in (("beatmap", self.load_beatmap), ("lyrics", self.load_lyrics_file),
                            ("reference", self.load_reference)):
            p = sess.get(key)
            if p and os.path.isfile(p):
                loader(p)
        a = sess.get("audio")
        if a and os.path.isfile(a) and not self.timeline.player.loaded:
            self.timeline.load_audio(a, quiet=True)


class WheelGuard(QObject):
    """Safeguard: the mouse wheel over a settings field (number box, drop-down, slider) scrolls
    the panel instead of changing the value, unless you clicked into that field first."""

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox
        if ev.type() != QEvent.Wheel:
            return False
        w = obj
        if isinstance(w, QWidget) and not isinstance(w, (QAbstractSpinBox, QComboBox, QAbstractSlider)):
            par = w.parentWidget()
            if isinstance(par, QAbstractSpinBox):    # the line edit inside a spin box
                w = par
        if not isinstance(w, (QAbstractSpinBox, QComboBox, QAbstractSlider)) or w.hasFocus():
            return False
        from PySide6.QtWidgets import QScrollBar
        if isinstance(w, QScrollBar):
            return False                              # a real scroll bar
        p = w.parentWidget()
        while p is not None and not isinstance(p, QAbstractScrollArea):
            p = p.parentWidget()
        if p is not None:
            bar = p.verticalScrollBar()
            bar.setValue(bar.value() - ev.angleDelta().y())
        return True


def _open_folder(path: str):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
