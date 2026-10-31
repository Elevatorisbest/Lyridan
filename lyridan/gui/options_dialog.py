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
        tabs.addTab(self._updates(), "Updates")
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
        note = QLabel("Every theme shows check boxes as a tick on the accent colour when on and an empty box when off.")
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
        self.click_focus = QCheckBox("Clicking the lyric preview, the overview strip, the transport buttons or the "
                                     "clocks also gives the keyboard to the timeline")
        self.click_focus.setChecked(self.s.timeline_click_focus)
        self.click_focus.setToolTip("Off: only a click on the timeline itself makes the arrow keys move the playhead.")
        f.addRow(self.click_focus)
        tip = QLabel("Timeline keys work only while the timeline has the keyboard (a coloured frame shows it); Esc "
                     "gives it back, and Tab never moves it into the settings. ← → step · Shift = faster · Ctrl/Alt + ← → = lines · PgUp/PgDn = "
                     "sections · ↑ ↓ = zoom · Space = play/pause · Enter = play the line · L = loop · "
                     "Shift + drag = select a range · Ctrl+P = play/pause anywhere.")
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

    def _updates(self):
        from .. import updater
        from ..update_channels import DEV_BRANCH, STABLE_BRANCH
        w, f = self._form()
        info = buildinfo.info()
        here = updater.track_of(info) or "unknown"
        self.upd_check = QCheckBox("Check for updates when Lyridan starts")
        self.upd_check.setChecked(self.s.update_check)
        f.addRow(self.upd_check)
        self.upd_auto = QCheckBox("Download updates in the background and install them the next time Lyridan "
                                  "starts")
        self.upd_auto.setToolTip("Off: Lyridan shows a bar with an Update now button and installs nothing on "
                                 "its own.")
        self.upd_auto.setChecked(self.s.update_auto_install)
        self.upd_check.toggled.connect(self.upd_auto.setEnabled)
        self.upd_auto.setEnabled(self.s.update_check)
        f.addRow(self.upd_auto)
        row = QHBoxLayout()
        self.upd_branch = QComboBox()
        self.upd_branch.setMinimumContentsLength(28)
        self._branch_items = {"": f"Automatic - same as this build ({here})",
                              STABLE_BRANCH: f"{STABLE_BRANCH} - stable releases"}
        for b in (DEV_BRANCH, self.s.update_branch, here):
            if b and b not in self._branch_items and not updater.is_excluded_branch(b):
                self._branch_items[b] = b
        self._fill_branches()
        self.upd_refresh = QPushButton("Refresh list")
        self.upd_refresh.setToolTip("Load every branch from GitHub (the old v1.1.1 branch and the test branches "
                                    "are not offered)")
        self.upd_refresh.clicked.connect(self._load_branches)
        row.addWidget(self.upd_branch, 1)
        row.addWidget(self.upd_refresh)
        f.addRow("Update from branch", row)
        self.upd_status = QLabel("")
        self.upd_status.setStyleSheet("color: gray;")
        self.upd_status.setWordWrap(True)
        f.addRow(self.upd_status)
        target = updater.install_target()
        lines = [f"This build: Lyridan {info.get('label', '')} from '{here}'"
                 + (f" @ {info.get('commit_short')}" if info.get("commit_short") else "") + "."]
        if not target.kind:
            lines.append(target.reason)
        lines.append("Branches other than main are development builds: they are built from every push and can "
                     "be unstable. Choosing a different branch installs its newest build, even if it is older "
                     "than this one. Your settings are kept.")
        note = QLabel("\n\n".join(lines))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        f.addRow(note)
        now = QPushButton("Check for updates now")
        now.clicked.connect(self._check_now)
        f.addRow(now)
        self._load_branches()
        return w

    def _fill_branches(self, built=None):
        current = self.upd_branch.currentData() if self.upd_branch.count() else self.s.update_branch
        self.upd_branch.blockSignals(True)
        self.upd_branch.clear()
        for key, label in self._branch_items.items():
            if built is not None and key and key in built and not built[key]:
                label += "  (no build yet)"
            self.upd_branch.addItem(label, key)
        self.upd_branch.setCurrentIndex(max(0, self.upd_branch.findData(current or "")))
        self.upd_branch.blockSignals(False)

    def _load_branches(self):
        from PySide6.QtCore import QThreadPool
        from .update_ui import BranchListJob
        self.upd_refresh.setEnabled(False)
        self.upd_status.setText("Loading branches from GitHub…")
        job = BranchListJob()
        job.signals.branches.connect(self._branches_loaded)
        QThreadPool.globalInstance().start(job)

    def _branches_loaded(self, branches, err):
        try:
            self.upd_refresh.setEnabled(True)
        except RuntimeError:            # dialog already closed
            return
        if err:
            self.upd_status.setText(f"Couldn't load the branch list ({err}).")
            return
        for name, _ in branches:
            self._branch_items.setdefault(name, name)
        self._fill_branches({name: has for name, has in branches})
        self.upd_status.setText(f"{len(branches)} branches on GitHub.")

    def _check_now(self):
        self._apply()
        if self.parent() is not None and hasattr(self.parent(), "updates"):
            self.parent().updates.check(manual=True)

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
        s.timeline_click_focus = self.click_focus.isChecked()
        s.restore_session = self.restore.isChecked()
        s.export_folder = self.export_dir.text().strip()
        s.disclaimer_acknowledged = not self.disclaimer.isChecked()
        old_branch = s.update_branch
        s.update_check = self.upd_check.isChecked()
        s.update_auto_install = self.upd_auto.isChecked()
        s.update_branch = self.upd_branch.currentData() or ""
        s.save()
        if s.update_branch != old_branch and self.parent() is not None and hasattr(self.parent(), "updates"):
            from .. import updater
            if updater.target_track(s.update_branch) != updater.target_track(old_branch):
                self.parent().updates.on_branch_changed()
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
