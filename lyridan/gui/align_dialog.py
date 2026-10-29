"""GUI flow for the experimental 'align .lrc to song audio' feature."""
from __future__ import annotations

import os
import traceback

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

AUDIO_FILTER = "Audio (*.wav *.ogg *.flac *.mp3 *.aif *.aiff *.opus *.m4a);;All files (*)"

LRC_WARNING = ("<b>Line-synced .lrc lyrics are not recommended.</b> They only say when each line starts, so "
               "Lyridan has to <i>guess</i> the timing of every syllable - expect poorly timed vocals. "
               "Use a syllable-synced <b>.ttml</b> (e.g. from Apple Music) whenever you can, or try the "
               "experimental audio alignment.")

MODEL_CONSENT = """
<h3>Download the alignment model?</h3>
<p>Audio alignment uses <b>Meta's MMS multilingual forced-alignment model</b>
(Pratap et al., <i>Scaling Speech Technology to 1,000+ Languages</i>, 2023), converted to ONNX and
compressed to 8-bit by the Lyridan project. It is about <b>{mb} MB</b> and is downloaded once from
Lyridan's GitHub releases into your Lyridan settings folder.</p>
<p>The model is licensed <b>CC-BY-NC 4.0 - non-commercial use only</b>. By downloading it you agree
to use it only for non-commercial purposes.
<a href="https://creativecommons.org/licenses/by-nc/4.0/">Licence</a> ·
<a href="{lic}">MMS licence notice</a> ·
<a href="https://arxiv.org/abs/2305.13516">Paper</a></p>
"""


class _Worker(QObject):
    progress = Signal(str, float)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.cancelled = False

    def run(self):
        try:
            res = self.fn(self._progress)
            self.finished.emit(res)
        except InterruptedError:
            self.failed.emit("cancelled")
        except Exception:  # noqa: BLE001
            self.failed.emit(traceback.format_exc())

    def _progress(self, msg, frac):
        self.progress.emit(msg, float(frac))
        return not self.cancelled


class _ProgressDialog(QDialog):
    """Progress window. Its slots live in the UI thread, so worker signals are delivered safely."""

    def __init__(self, parent, title):
        super().__init__(parent)
        from PySide6.QtWidgets import QProgressBar
        self.setWindowTitle("Lyridan")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.result_value = None
        self.error = None
        self.finished_ok = False
        lay = QVBoxLayout(self)
        self.label = QLabel(title)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.cancel = QPushButton("Cancel")
        lay.addWidget(self.label)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.cancel)
        lay.addLayout(row)

    def on_progress(self, msg, frac):
        self.label.setText(msg)
        self.bar.setValue(int(max(0.0, min(1.0, frac)) * 1000))

    def on_done(self, res):
        self.result_value = res
        self.finished_ok = True
        self.accept()

    def on_fail(self, err):
        self.error = err
        self.reject()


def _run_with_progress(parent, title: str, fn):
    """Run fn(progress) in a worker thread with a cancellable progress window. Returns result or None."""
    dlg = _ProgressDialog(parent, title)
    thread = QThread()
    worker = _Worker(fn)
    worker.moveToThread(thread)
    worker.progress.connect(dlg.on_progress)
    worker.finished.connect(dlg.on_done)
    worker.failed.connect(dlg.on_fail)

    def cancel():
        worker.cancelled = True
        dlg.label.setText("Cancelling…")
        dlg.cancel.setEnabled(False)

    dlg.cancel.clicked.connect(cancel)
    thread.started.connect(worker.run)
    thread.start()
    dlg.exec()
    worker.cancelled = worker.cancelled or not (dlg.finished_ok or dlg.error)
    thread.quit()
    thread.wait()
    if dlg.error and dlg.error != "cancelled":
        QMessageBox.critical(parent, "Lyridan", dlg.error)
    return dlg.result_value if dlg.finished_ok else None


class AlignSetupDialog(QDialog):
    """Pick the audio file and (optionally) a known offset."""

    def __init__(self, parent, default_dir: str, prior: float):
        super().__init__(parent)
        self.setWindowTitle("Align lyrics to song audio (experimental)")
        self.setMinimumWidth(600)
        lay = QVBoxLayout(self)
        info = QLabel(
            "<p>Lyridan listens to the song and moves every syllable to where it is actually sung, "
            "using the .lrc line timestamps as anchors. The result is a <b>syllable-synced .ttml</b> "
            "you can keep, fix and reuse.</p>"
            "<p><b>Tips:</b> an isolated vocal stem (e.g. from UVR / Demucs) gives the best results; the "
            "chart's audio or the original song both work. Accuracy varies - songs with heavy backing "
            "vocals, effects or very fast lines are harder. Always check the result by ear.</p>")
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setPlaceholderText("Song audio or vocal stem (.wav .ogg .flac .mp3)")
        b = QPushButton("Browse…")
        b.clicked.connect(lambda: self._browse(default_dir))
        row.addWidget(self.path, 1)
        row.addWidget(b)
        form.addRow("Audio", row)
        self.auto = QCheckBox("Detect where the lyrics start automatically (recommended)")
        self.auto.setChecked(True)
        form.addRow(self.auto)
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-120, 600)
        self.offset.setDecimals(3)
        self.offset.setSuffix(" s")
        self.offset.setValue(prior)
        self.offset.setEnabled(False)
        self.offset.setToolTip("Audio time minus lyric time. For your chart's audio this is usually the intro "
                               "silence plus the empty bars; for the original song it is 0.")
        self.auto.toggled.connect(lambda on: self.offset.setEnabled(not on))
        form.addRow("Known offset", self.offset)
        self.readings = QCheckBox("Japanese: let the audio pick kanji readings (緋 → aka or hi)")
        self.readings.setToolTip("For kanji with more than one reading, compares how well each reading matches "
                                 "the singing. Clear wins are applied, weaker ones are only listed for you to check.")
        form.addRow(self.readings)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Align")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _browse(self, d):
        p, _ = QFileDialog.getOpenFileName(self, "Song audio", d, AUDIO_FILTER)
        if p:
            self.path.setText(p)

    def _ok(self):
        if not os.path.isfile(self.path.text()):
            QMessageBox.warning(self, "Lyridan", "Please choose an audio file.")
            return
        self.accept()


def ensure_model(parent) -> bool:
    from ..align import MODEL_INFO, ModelStore
    store = ModelStore()
    if store.is_installed():
        return True
    box = QMessageBox(parent)
    box.setWindowTitle("Alignment model")
    box.setTextFormat(Qt.RichText)
    box.setText(MODEL_CONSENT.format(mb=MODEL_INFO["approx_mb"], lic=MODEL_INFO["license_url"]))
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
    box.button(QMessageBox.Yes).setText("Agree and download")
    if box.exec() != QMessageBox.Yes:
        return False

    def job(progress):
        def cb(done, total):
            mb = done / 1048576
            return progress(f"Downloading alignment model… {mb:.0f} / {total / 1048576:.0f} MB",
                            done / total if total else 0)
        store.download(cb)
        return True

    ok = _run_with_progress(parent, "Downloading alignment model…", job)
    if not ok and not store.is_installed():
        QMessageBox.warning(parent, "Lyridan", "The model was not downloaded. Check your internet connection "
                                               "and try again.")
        return False
    return True


def run_alignment(window) -> None:
    """Entry point used by the main window."""
    from ..align import ModelStore, align_lyrics
    from ..exports import ttml
    from ..parsers import load_lyrics

    src = window.source
    if src is None:
        return
    prior = 0.0
    if window.settings.intro_silence:
        prior += window.settings.intro_silence_seconds
    if window.settings.two_empty_bars and window.beatmap and window.beatmap.beats:
        ms = window.beatmap.measure_starts
        prior += window.beatmap.first_n_measures_end(window.settings.empty_bars) - (ms[0] if ms else 0)
    folder = os.path.dirname(window.source_path or os.path.expanduser("~"))
    setup = AlignSetupDialog(window, folder, prior)
    if window.timeline.player.loaded:
        setup.path.setText(window.timeline.player.path)      # the timeline's audio is a good default
    setup.readings.setChecked(window.settings.verify_readings)
    if not setup.exec():
        return
    window.settings.verify_readings = setup.readings.isChecked()
    if not ensure_model(window):
        return
    store = ModelStore()
    audio_path = setup.path.text()
    offset = None if setup.auto.isChecked() else setup.offset.value()

    def job(progress):
        return align_lyrics(src, audio_path, window.settings, store.model_path, store.meta(), progress,
                            offset=offset, offset_prior=prior or None)

    res = _run_with_progress(window, "Aligning lyrics to the audio…", job)
    if not res:
        return
    aligned, report = res
    if not window.timeline.player.loaded or window.timeline.player.path != audio_path:
        window.timeline.load_audio(audio_path, quiet=True)   # reuse the song audio for the preview
    bad = [l for l in report.lines if not l.aligned]
    detail = "\n".join(f"• {l.text[:60]} - {l.reason}" for l in bad[:12])
    msg = report.summary()
    if report.offset_note:
        msg += "\n\n⚠ " + report.offset_note.capitalize() + "."
    if detail:
        msg += "\n\nLines that kept estimated timing:\n" + detail
    msg += ("\n\nThis is experimental: listen through the result and fix what is off. "
            "Save it as a .ttml to reuse it?")
    QMessageBox.information(window, "Alignment finished", msg)
    base = os.path.splitext(window.source_path or "lyrics")[0]
    path, _ = QFileDialog.getSaveFileName(window, "Save aligned lyrics", base + "_aligned.ttml",
                                          "TTML lyrics (*.ttml)")
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(ttml(aligned))
        window.load_lyrics_file(path)
    else:
        aligned.path = window.source_path or ""
        window.use_aligned_source(aligned)
