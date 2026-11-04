"""Keyboard focus for the edit window: the timeline owns the keyboard by default.

Arrow keys, Space, Enter, PgUp/PgDn ... always drive the timeline (navigation and playback),
whatever was clicked last: buttons, check boxes, drop-downs, tabs, the lyrics table, the empty
parts of the window. Only a value field you click into (a number box, a text field, a table
cell being edited) takes the keyboard, and only until you submit it (Enter / Esc) or click
anywhere else - then the keyboard goes straight back to the timeline.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (QAbstractButton, QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox,
                               QLineEdit, QPlainTextEdit, QTabBar, QTextEdit, QWidget)


def is_value_field(w: Optional[QWidget]) -> bool:
    """A widget that should keep the keyboard while you type a value into it."""
    if w is None or not w.isEnabled():
        return False
    if isinstance(w, QAbstractSpinBox):
        return not w.isReadOnly()
    if isinstance(w, QLineEdit):
        par = w.parentWidget()
        if isinstance(par, QAbstractSpinBox):        # the line edit inside a number box
            return not par.isReadOnly()
        if isinstance(par, QComboBox):
            return par.isEditable()
        return not w.isReadOnly()
    if isinstance(w, (QPlainTextEdit, QTextEdit)):
        return not w.isReadOnly()
    if isinstance(w, QComboBox):
        return w.isEditable()
    return False


def _submits_on_enter(w: QWidget) -> bool:
    """Enter finishes the value (single-line fields), as opposed to a multi-line text box."""
    return isinstance(w, (QAbstractSpinBox, QLineEdit, QComboBox))


class TimelineKeyboard(QObject):
    """Keeps the keyboard on ``canvas`` except while a value field in ``window`` is being edited."""

    def __init__(self, window: QWidget, canvas: QWidget):
        super().__init__(window)
        self.window = window
        self.canvas = canvas
        self._pending = False
        self._leaving: Optional[QWidget] = None      # field that was submitted / clicked off
        app = QApplication.instance()
        app.focusChanged.connect(self._focus_changed)
        app.installEventFilter(self)

    # ------------------------------------------------------------------ helpers
    def _mine(self, w: Optional[QWidget]) -> bool:
        return isinstance(w, QWidget) and w.window() is self.window

    def harden(self):
        """Controls that are clicked, not typed into, never take the keyboard at all
        (so there is no flicker and Space / arrows can't toggle or change them)."""
        for w in self.window.findChildren(QWidget):
            if w is self.canvas:
                continue
            if isinstance(w, (QAbstractButton, QAbstractSlider, QTabBar)):
                w.setFocusPolicy(Qt.NoFocus)
            elif isinstance(w, QComboBox) and not w.isEditable():
                w.setFocusPolicy(Qt.NoFocus)          # the drop-down list still opens on click
            elif isinstance(w, QAbstractSpinBox) or (isinstance(w, QLineEdit) and is_value_field(w)):
                w.setFocusPolicy(Qt.ClickFocus)       # no Tab / wheel focus: only a deliberate click

    def give_back(self):
        """Hand the keyboard to the timeline now (if this window is the one in use)."""
        self._pending = False
        if not self.canvas.isVisible():
            return
        active = QApplication.activeWindow()
        if active is not None and active is not self.window:
            return                                    # a dialog / popup is open: leave it alone
        fw = QApplication.focusWidget()
        if fw is self.canvas:
            return
        self.canvas.setFocus(Qt.OtherFocusReason)

    def _give_back_later(self, leaving: Optional[QWidget] = None):
        """Once the current event is done (a click may still be moving the focus).
        ``leaving``: a field the keyboard must leave even if it still has the focus then."""
        if leaving is not None:
            self._leaving = leaving
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self._settle)

    def _settle(self):
        self._pending = False
        leaving, self._leaving = self._leaving, None
        fw = QApplication.focusWidget()
        if leaving is not None and fw is leaving and self._mine(fw):
            self.give_back()
            return
        if fw is None or not self._mine(fw):
            if fw is None and QApplication.activeWindow() is self.window:
                self.give_back()
            return
        if fw is self.canvas or is_value_field(fw):
            return
        self.give_back()

    @staticmethod
    def _same_field(obj, fw: QWidget) -> bool:
        """The click landed on the focused field itself (its text, arrows or drop-down button)."""
        if not isinstance(obj, QWidget):
            return False
        if obj is fw or fw.isAncestorOf(obj):
            return True
        par = fw.parentWidget()                       # the line edit inside a number box / combo
        return isinstance(par, (QAbstractSpinBox, QComboBox)) and (obj is par or par.isAncestorOf(obj))

    # ------------------------------------------------------------------ Qt hooks
    def _focus_changed(self, old, new):
        if new is None or not self._mine(new):
            return
        if new is self.canvas or is_value_field(new):
            return
        self._give_back_later()                       # a button, table, tab ... got it: take it back

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.MouseButtonPress and self._mine(obj):
            fw = QApplication.focusWidget()
            if is_value_field(fw) and self._mine(fw) and not self._same_field(obj, fw):
                self._give_back_later(fw)             # clicked off the field (onto another field: it keeps it)
        elif t == QEvent.KeyPress and self._mine(obj) and obj is QApplication.focusWidget() \
                and is_value_field(obj):
            key = ev.key()
            if key == Qt.Key_Escape:
                self._give_back_later(obj)
            elif key in (Qt.Key_Return, Qt.Key_Enter) and _submits_on_enter(obj):
                self._give_back_later(obj)            # the field handles Enter (commits) first
        elif t == QEvent.WindowActivate and obj is self.window:
            self._give_back_later()                   # back from a dialog / another app
        return False
