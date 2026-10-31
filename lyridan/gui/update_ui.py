"""Update notification bar and the background check / download (see lyridan/updater.py)."""
from __future__ import annotations

import os
import sys
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from .. import buildinfo, updater
from ..update_channels import STABLE_BRANCH


class _Signals(QObject):
    checked = Signal(object, object, str, str, bool)      # offer, manifest, track, error, manual
    progress = Signal(int, int)
    downloaded = Signal(str, str)                          # path, error
    branches = Signal(object, str)                         # [(name, has_build)], error


class _CheckJob(QRunnable):
    def __init__(self, branch_setting: str, manual: bool):
        super().__init__()
        self.signals = _Signals()
        self.branch_setting = branch_setting
        self.manual = manual

    def run(self):
        offer = manifest = None
        track, err = "", ""
        try:
            offer, manifest, track = updater.check(self.branch_setting, manual=self.manual)
        except Exception as e:  # noqa: BLE001
            err = str(e) or e.__class__.__name__
            track = updater.target_track(self.branch_setting)
        try:
            self.signals.checked.emit(offer, manifest, track, err, self.manual)
        except RuntimeError:
            pass


class _DownloadJob(QRunnable):
    def __init__(self, offer):
        super().__init__()
        self.signals = _Signals()
        self.offer = offer
        self.cancel = False

    def run(self):
        path, err = "", ""
        try:
            path = updater.download(self.offer, progress=lambda d, t: self._progress(d, t),
                                    cancelled=lambda: self.cancel)
        except InterruptedError:
            err = "cancelled"
        except Exception as e:  # noqa: BLE001
            err = str(e) or e.__class__.__name__
        try:
            self.signals.downloaded.emit(path, err)
        except RuntimeError:
            pass

    def _progress(self, done, total):
        try:
            self.signals.progress.emit(done, total)
        except RuntimeError:
            self.cancel = True


class BranchListJob(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = _Signals()

    def run(self):
        out, err = [], ""
        try:
            out = updater.list_branches()
        except Exception as e:  # noqa: BLE001
            err = str(getattr(e, "reason", "") or e) or e.__class__.__name__
        try:
            self.signals.branches.emit(out, err)
        except RuntimeError:
            pass


class UpdateBar(QFrame):
    """Slim, dismissible bar above the edit window - never a modal pop-up."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UpdateBar")
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("#UpdateBar { background: palette(alternate-base); border-bottom: 1px solid "
                           "palette(mid); } #UpdateBar QLabel { background: transparent; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 6, 4)
        lay.setSpacing(8)
        self.icon = QLabel("⬆")
        self.text = QLabel()
        self.text.setTextFormat(Qt.PlainText)
        self.text.setWordWrap(False)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(180)
        self.progress.setMaximumHeight(14)
        self.progress.setTextVisible(False)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(6)
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setAutoRaise(True)
        self.close_btn.setToolTip("Hide")
        self.close_btn.clicked.connect(self.hide)
        lay.addWidget(self.icon)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.progress)
        lay.addLayout(self.buttons)
        lay.addWidget(self.close_btn)
        self.hide()

    def show_message(self, text: str, buttons=(), icon: str = "⬆", progress: bool = False, tooltip: str = ""):
        while self.buttons.count():
            w = self.buttons.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.icon.setText(icon)
        self.text.setText(text)
        self.text.setToolTip(tooltip)
        self.progress.setVisible(progress)
        for label, slot in buttons:
            b = QPushButton(label)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(slot)
            self.buttons.addWidget(b)
        self.show()

    def set_progress(self, done: int, total: int):
        if total > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(done * 1000 / total))
        else:
            self.progress.setRange(0, 0)


def _branch_note(offer) -> str:
    b = offer.track
    return "" if b == STABLE_BRANCH else f" (branch '{b}')"


class UpdateController(QObject):
    def __init__(self, window, startup: Optional[updater.Startup] = None):
        super().__init__(window)
        self.win = window
        self.bar = UpdateBar()
        old = window.takeCentralWidget()
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.bar)
        if old is not None:
            v.addWidget(old, 1)
        window.setCentralWidget(box)
        self._checking = False
        self._report_next = False
        self._job: Optional[_DownloadJob] = None
        self.offer: Optional[updater.Offer] = None
        self.manifest = None
        self.track = ""
        if startup and startup.message:
            if startup.level == "warning":
                self.bar.show_message(startup.message, [("Download page", self._open_page)], icon="⚠")
            else:
                window.statusBar().showMessage(startup.message, 10000)

    @property
    def settings(self):
        return self.win.settings

    # ------------------------------------------------------------------ checking
    def check_on_launch(self):
        if self.settings.update_check and getattr(sys, "frozen", False):
            self.check(manual=False)

    def check(self, manual: bool = False):
        if self._checking:
            self._report_next |= manual                   # answer the running check out loud
            return
        if self._job is not None:
            if manual:
                self.win.statusBar().showMessage("An update is being downloaded…", 4000)
            return
        self._checking = True
        if manual:
            self.win.statusBar().showMessage("Checking for updates…")
        job = _CheckJob(self.settings.update_branch, manual)
        job.signals.checked.connect(self._on_checked)
        QThreadPool.globalInstance().start(job)

    def _on_checked(self, offer, manifest, track, err, manual):
        self._checking = False
        manual, self._report_next = manual or self._report_next, False
        self.offer, self.manifest, self.track = offer, manifest, track
        if manual:
            self.win.statusBar().clearMessage()
        if err:
            if manual:
                QMessageBox.warning(self.win, "Check for updates", f"Couldn't check for updates.\n\n{err}")
            return
        if offer is None:
            if manual:
                self._report_none(manifest, track)
            return
        target = updater.install_target()
        if offer.auto and self.settings.update_auto_install and target.kind:
            st = updater.UpdateState.load()
            if st.pending and st.pending.get("commit") == offer.commit and \
                    os.path.exists(st.pending.get("path", "")):
                self._show_ready()
            else:
                self._download(then="pending", foreground=manual)
            return
        self._show_offer(offer, target)

    def _report_none(self, manifest, track):
        info = buildinfo.info()
        if manifest is None:
            text = (f"No build of the '{track}' branch is published right now." if track != STABLE_BRANCH else
                    "No stable Lyridan 2 release is published yet.")
        else:
            text = f"You have the newest build{'' if track == STABLE_BRANCH else f' of {track!r}'}: " \
                   f"Lyridan {info.get('label', '')}."
        QMessageBox.information(self.win, "Check for updates", text)

    def _show_offer(self, offer, target=None):
        target = target or updater.install_target()
        info = buildinfo.info()
        if offer.kind == "switch":
            text = (f"Updates follow '{offer.track}', but this build is from '{updater.track_of(info)}'. "
                    f"Lyridan {offer.label} from '{offer.track}' is available.")
        elif offer.kind == "rebuild":
            text = f"Published build Lyridan {offer.label}{_branch_note(offer)} differs from this local build."
        else:
            text = f"Lyridan {offer.label}{_branch_note(offer)} is available."
        tip = "\n".join(x for x in (offer.manifest.get("commit_subject", ""),
                                    offer.why_not_auto and f"Not installed automatically: {offer.why_not_auto}")
                        if x)
        btns = []
        if target.kind and offer.asset:
            btns.append(("Update now" if offer.kind != "switch" else f"Install the {offer.track} build",
                         lambda: self._download(then="install")))
        else:
            btns.append(("Download page", self._open_page))
        if offer.kind == "switch":
            btns.append((f"Follow '{updater.track_of(info)}' instead", self._follow_current))
        btns.append(("What's new", lambda: QDesktopServices.openUrl(QUrl(offer.changes_url(info)))))
        btns.append(("Skip this build" if offer.kind != "switch" else "Not now", self._skip))
        self.bar.show_message(text, btns, tooltip=tip)

    def _open_page(self):
        url = self.offer.page_url() if self.offer else "https://github.com/Elevatorisbest/Lyridan/releases"
        QDesktopServices.openUrl(QUrl(url))

    def _skip(self):
        if self.offer:
            st = updater.UpdateState.load()
            st.skipped = self.offer.commit
            st.save()
        self.bar.hide()

    def _follow_current(self):
        self.settings.update_branch = ""
        self.settings.save()
        self.bar.hide()
        self.win.statusBar().showMessage(f"Updates now follow '{updater.track_of(buildinfo.info())}'.", 6000)

    def on_branch_changed(self):
        """Options changed the branch: switching to it was asked for, so it may install automatically."""
        st = updater.UpdateState.load()
        st.switch_requested = updater.target_track(self.settings.update_branch)
        st.skipped = ""
        if st.pending and st.pending.get("track") != st.switch_requested:
            updater._remove(st.pending.get("path", ""))
            st.pending = None
        st.save()
        self.bar.hide()
        self.check(manual=False)

    # ------------------------------------------------------------------ download / install
    def _download(self, then: str, foreground: bool = False):
        if self._job is not None or self.offer is None:
            return
        offer = self.offer
        job = _DownloadJob(offer)
        self._job = job
        if foreground or then == "install":
            self.bar.show_message(f"Downloading Lyridan {offer.label}…", [("Cancel", self._cancel_download)],
                                  progress=True)
            self.bar.set_progress(0, 0)
            job.signals.progress.connect(self.bar.set_progress)
        job.signals.downloaded.connect(lambda path, err: self._on_downloaded(offer, path, err, then))
        QThreadPool.globalInstance().start(job)

    def _cancel_download(self):
        if self._job:
            self._job.cancel = True
        self.bar.hide()

    def _on_downloaded(self, offer, path, err, then):
        self._job = None
        if err:
            if err != "cancelled" and (then == "install" or self.bar.progress.isVisible()):
                self.bar.show_message(f"The update couldn't be downloaded: {err}",
                                      [("Try again", lambda: self._download(then="install")),
                                       ("Download page", self._open_page)], icon="⚠")
            return
        updater.make_pending(offer, path)
        if then == "install":
            self.install_now()
        else:
            self._show_ready()

    def _show_ready(self):
        o = self.offer
        label = o.label if o else ""
        self.bar.show_message(f"Lyridan {label}{_branch_note(o) if o else ''} is ready. It will be installed the "
                              "next time you start Lyridan.", [("Restart and update now", self.install_now)])

    def install_now(self):
        if getattr(self.win, "overrides", None):
            r = QMessageBox.question(self.win, "Update Lyridan",
                                     "Lyridan will close, install the update and start again.\n\n"
                                     "Your line edits are not saved in a project yet. Save the project first "
                                     "if you want to keep them.\n\nUpdate now?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        st = updater.UpdateState.load()
        pending = updater.mark_attempt(st)
        if not pending:
            return
        try:
            updater.launch_install(pending)
        except Exception as e:  # noqa: BLE001
            st.pending = None
            st.save()
            self.bar.show_message(f"The update couldn't be started: {e}", [("Download page", self._open_page)],
                                  icon="⚠")
            return
        self.win.close()
        QApplication.instance().quit()
