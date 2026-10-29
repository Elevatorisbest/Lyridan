"""Options dialog (application-wide preferences)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .. import buildinfo
from ..settings import Settings, config_dir
from .themes import THEME_CHOICES


class OptionsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.setMinimumSize(620, 520)
        self.s = settings
        self.reset_ack = False
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        tabs.addTab(self._appearance(), "Appearance")
        tabs.addTab(self._playback(), "Timeline && playback")
        tabs.addTab(self._general(), "General")
        tabs.addTab(self._model(), "Audio alignment")
        tabs.addTab(self._build(), "About this build")
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        lay.addWidget(bb)

    # ------------------------------------------------------------------ tabs
    def _form(self):
        w = QWidget()
        f = QFormLayout(w)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        return w, f

    def _appearance(self):
        w, f = self._form()
        self.theme = QComboBox()
        for k, v in THEME_CHOICES:
            self.theme.addItem(v, k)
        self.theme.setCurrentIndex(max(0, self.theme.findData(self.s.theme)))
        f.addRow("Theme", self.theme)
        self.font_pt = QSpinBox()
        self.font_pt.setRange(0, 20)
        self.font_pt.setSpecialValueText("System default")
        self.font_pt.setSuffix(" pt")
        self.font_pt.setValue(self.s.ui_font_pt)
        f.addRow("Interface text size", self.font_pt)
        self.preview_pt = QSpinBox()
        self.preview_pt.setRange(12, 48)
        self.preview_pt.setSuffix(" pt")
        self.preview_pt.setValue(self.s.preview_font_pt)
        f.addRow("In-game preview text size", self.preview_pt)
        note = QLabel("Lyridan Dark is the black-and-yellow theme from Lyridan 1.x. Every theme shows check boxes "
                      "as a tick on the accent colour when on and an empty box when off.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        f.addRow(note)
        return w

    def _playback(self):
        w, f = self._form()
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(self.s.playback_volume)
        f.addRow("Default volume", self.vol)
        self.metro = QCheckBox("Metronome on by default")
        self.metro.setChecked(self.s.metronome)
        f.addRow(self.metro)
        self.follow = QCheckBox("Timeline follows the playhead")
        self.follow.setChecked(self.s.follow_playhead)
        f.addRow(self.follow)
        from .timeline import ARROW_STEPS
        self.arrow_step = QComboBox()
        for k, label in ARROW_STEPS.items():
            self.arrow_step.addItem(label, k)
        self.arrow_step.setCurrentIndex(max(0, self.arrow_step.findData(self.s.timeline_arrow_step)))
        self.arrow_step.setToolTip("How far one press of ← / → moves the playhead in the timeline "
                                   "(Shift = 4× as far)")
        f.addRow("Arrow keys move by", self.arrow_step)
        self.accel = QCheckBox("Speed up while an arrow key is held")
        self.accel.setChecked(self.s.timeline_accelerate)
        f.addRow(self.accel)
        tip = QLabel("Timeline keys work only after you click the timeline (a coloured frame shows it); Esc gives "
                     "the keyboard back. ← → step · Shift = faster · Ctrl/Alt + ← → = lines · PgUp/PgDn = "
                     "sections · ↑ ↓ = zoom · Space = play/pause · Enter = play the line · Ctrl+P = play/pause "
                     "anywhere.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: gray;")
        f.addRow(tip)
        return w

    def _general(self):
        w, f = self._form()
        self.restore = QCheckBox("Reopen the last lyrics, beatmap and audio on start")
        self.restore.setChecked(self.s.restore_session)
        f.addRow(self.restore)
        row = QHBoxLayout()
        self.export_dir = QLineEdit(self.s.export_folder)
        self.export_dir.setPlaceholderText("Next to the beatmap XML (default)")
        b = QPushButton("Browse…")
        b.clicked.connect(self._pick_dir)
        row.addWidget(self.export_dir, 1)
        row.addWidget(b)
        f.addRow("Default export folder", row)
        self.disclaimer = QCheckBox("Show the export disclaimer")
        self.disclaimer.setChecked(not self.s.disclaimer_acknowledged)
        f.addRow(self.disclaimer)
        ack = QPushButton("Reset acknowledgements")
        ack.setToolTip("Show every notice you dismissed with 'don't show again' again")
        ack.clicked.connect(self._reset_ack)
        f.addRow(ack)
        folder = QPushButton("Open settings folder")
        folder.clicked.connect(lambda: _open(config_dir()))
        f.addRow(folder)
        return w

    def _model(self):
        from ..align import MODEL_INFO, ModelStore
        w, f = self._form()
        st = ModelStore()
        size = ""
        if st.is_installed():
            try:
                size = f" ({os.path.getsize(st.model_path) / 1048576:.0f} MB)"
            except OSError:
                pass
        self.model_status = QLabel(("Downloaded" + size) if st.is_installed() else "Not downloaded")
        f.addRow("Alignment model", self.model_status)
        lic = QLabel(f"{MODEL_INFO['name']} - {MODEL_INFO['license']}. Used only by Tools → Align lyrics to "
                     "song audio. Downloaded on first use.")
        lic.setWordWrap(True)
        lic.setStyleSheet("color: gray;")
        f.addRow(lic)
        rm = QPushButton("Remove downloaded model")
        rm.setEnabled(st.is_installed())
        rm.clicked.connect(lambda: (st.remove(), self.model_status.setText("Not downloaded"), rm.setEnabled(False)))
        f.addRow(rm)
        op = QPushButton("Open model folder")
        op.clicked.connect(lambda: _open(st.folder))
        f.addRow(op)
        return w

    def _build(self):
        w = QWidget()
        f = QFormLayout(w)
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
            lbl = QLabel(f'<a href="{url}">{url}</a>')
            lbl.setOpenExternalLinks(True)
            f.addRow(k, lbl)
        if buildinfo.is_dev():
            from PySide6.QtWidgets import QApplication
            copy = QPushButton("Copy build info (for bug reports)")
            copy.clicked.connect(lambda: QApplication.clipboard().setText(buildinfo.as_text()))
            f.addRow(copy)
        return w

    # ------------------------------------------------------------------ actions
    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Default export folder", self.export_dir.text() or "")
        if d:
            self.export_dir.setText(d)

    def _reset_ack(self):
        self.disclaimer.setChecked(True)
        self.reset_ack = True
        QMessageBox.information(self, "Options", "Dismissed notices will be shown again.")

    def _apply(self):
        s = self.s
        s.theme = self.theme.currentData()
        s.ui_font_pt = self.font_pt.value()
        s.preview_font_pt = self.preview_pt.value()
        s.playback_volume = self.vol.value()
        s.metronome = self.metro.isChecked()
        s.follow_playhead = self.follow.isChecked()
        s.timeline_arrow_step = self.arrow_step.currentData()
        s.timeline_accelerate = self.accel.isChecked()
        s.restore_session = self.restore.isChecked()
        s.export_folder = self.export_dir.text().strip()
        s.disclaimer_acknowledged = not self.disclaimer.isChecked()
        s.save()
        if self.parent() is not None and hasattr(self.parent(), "apply_options"):
            self.parent().apply_options(reset_ack=self.reset_ack)

    def _ok(self):
        self._apply()
        self.accept()


def _open(path: str):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    os.makedirs(path, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
