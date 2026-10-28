"""Application entry point for the GUI."""
from __future__ import annotations

import sys


def run() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from .. import APP_NAME, VERSION
    from .main_window import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("Elevatorisbest")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            win.load_any(arg)
    return app.exec()
