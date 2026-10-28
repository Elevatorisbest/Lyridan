"""Small dialogs: user dictionaries, about box."""
from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from .. import APP_NAME, AUTHOR, BUILD_DATE, DISPLAY_VERSION


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
    return (f"<h2>{APP_NAME} {DISPLAY_VERSION}</h2>"
            + (f"<p style='color:gray'>Built {BUILD_DATE}</p>" if BUILD_DATE else "")
            + f"<p>Synced lyrics (.ttml / .lrc) to Rocksmith 2014 vocal arrangements, with "
            f"syllabization and romanization for English, Japanese and Russian.</p>"
            f"<p>Made by {AUTHOR}.</p>"
            "<p><b>Language data</b><br>"
            "Japanese: MeCab via fugashi (MIT), UniDic-lite (BSD).<br>"
            "English: curated karaoke syllable dictionary, CMU Pronouncing Dictionary (BSD), "
            "trained boundary model for unknown words.<br>"
            "Russian: ё dictionary derived from OpenCorpora (CC BY-SA) via pymorphy3.</p>"
            "<p>Licensed under GPL-2.0.</p>")
