"""Small dialogs: user dictionaries, about box."""
from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from .. import APP_NAME, AUTHOR
from .. import buildinfo


class DictDialog(QDialog):
    """Two-column editor for a user dictionary."""

    def __init__(self, title: str, help_text: str, col_a: str, col_b: str, data: Dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 480)
        lay = QVBoxLayout(self)
        lbl = QLabel(help_text)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([col_a, col_b])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.table)
        for k, v in sorted(data.items()):
            self._add(k, v)
        row = QHBoxLayout()
        add = QPushButton("Add entry")
        rem = QPushButton("Remove selected")
        add.clicked.connect(lambda: (self._add("", ""), self.table.editItem(self.table.item(self.table.rowCount() - 1, 0))))
        rem.clicked.connect(self._remove)
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _add(self, k, v):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(k))
        self.table.setItem(r, 1, QTableWidgetItem(v))

    def _remove(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def data(self) -> Dict[str, str]:
        out = {}
        for r in range(self.table.rowCount()):
            a = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            b = (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()
            if a and b:
                out[a] = b
        return out


def about_text() -> str:
    i = buildinfo.info()
    build = ""
    if buildinfo.is_dev():
        build = (f"<p style='color:gray'>Development build #{i.get('build_number', '?')} · "
                 f"{i.get('branch', '')} @ {i.get('commit_short', '')}"
                 + (f" · {i['build_date']}" if i.get("build_date") else "")
                 + "<br>Full details: Settings panel → Build information.</p>")
    return (f"<h2>{APP_NAME} {buildinfo.display_version()}</h2>" + build
            + f"<p>Synced lyrics (.ttml / .lrc) to Rocksmith 2014 vocal arrangements, with "
            f"syllabization and romanization for English, Japanese and Russian.</p>"
            f"<p>Made by {AUTHOR}.</p>"
            "<p><b>Language data</b><br>"
            "Japanese: MeCab via fugashi (MIT), UniDic-lite (BSD).<br>"
            "English: curated karaoke syllable dictionary, CMU Pronouncing Dictionary (BSD), "
            "trained boundary model for unknown words.<br>"
            "Russian: ё dictionary derived from OpenCorpora (CC BY-SA) via pymorphy3.<br>"
            "Experimental audio alignment (optional download): MMS forced aligner by Meta AI "
            "(Pratap et al., 2023), converted to ONNX/int8 by the Lyridan project - "
            "CC BY-NC 4.0, non-commercial use only.</p>"
            "<p>Licensed under GPL-2.0.</p>")


DISCLAIMER_SECONDS = 15

DISCLAIMER_HTML = """
<h3 style="margin-bottom:4px">Lyridan is an experimental assistance tool</h3>
<p>The vocals XML you are about to export is generated automatically. It is <b>not</b> a replacement for an
accurate, hand-made Rocksmith vocal track and is meant <b>strictly as a starting point</b> to speed up
your own charting.</p>
<ul>
<li><b>Always verify the result yourself</b> - open it in Editor on Fire or Charter and check it against the
song (or have other charters check it) <b>before</b> building it into a CDLC. Don't drop the exported file straight
into DLC Builder.</li>
<li>Syllable splits, romanization / latinization, line breaks and timing can contain mistakes.</li>
<li>The quality of the lyrics and of the sync <b>depends on the source file</b> (for example a .ttml from
Apple Music) and <b>varies from song to song</b>. With line-synced .lrc files the syllable timing comes from
the audio alignment (or is estimated without it), so check it a little more closely; a syllable-synced .ttml is
the most accurate source when one is available.</li>
<li>The sync assumes your chart's audio matches the source (intro silence, empty bars, offsets) - check the
first and last lines in particular.</li>
</ul>
"""


class DisclaimerDialog(QDialog):
    """Export disclaimer that can only be acknowledged after a countdown."""

    def __init__(self, parent=None, seconds: int = DISCLAIMER_SECONDS):
        super().__init__(parent)
        self.setWindowTitle("Before you export")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.remaining = seconds
        lay = QVBoxLayout(self)
        text = QLabel(DISCLAIMER_HTML)
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        lay.addWidget(text)
        self.dont_show = QCheckBox("I understand - don't show this again")
        lay.addWidget(self.dont_show)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel = QPushButton("Cancel export")
        self.cancel.clicked.connect(self.reject)
        self.ok = QPushButton()
        self.ok.setEnabled(False)
        self.ok.setDefault(False)
        self.ok.setAutoDefault(False)
        self.ok.setMinimumWidth(220)
        self.ok.clicked.connect(self.accept)
        row.addWidget(self.cancel)
        row.addWidget(self.ok)
        lay.addLayout(row)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._update_button()
        self._timer.start()

    def _tick(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self._timer.stop()
        self._update_button()

    def _update_button(self):
        if self.remaining > 0:
            self.ok.setText(f"Please read… ({self.remaining} s)")
            self.ok.setEnabled(False)
        else:
            self.ok.setText("I understand - export")
            self.ok.setEnabled(True)
            self.ok.setDefault(True)

    def accept(self):
        if self.remaining > 0:  # Enter key etc. cannot skip the countdown
            return
        super().accept()
