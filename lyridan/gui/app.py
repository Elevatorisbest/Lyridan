"""Application entry point for the GUI."""
from __future__ import annotations

import sys


def _startup_update():
    """Install an update downloaded during the last session before the window opens.
    Returns (exit_now, startup_info)."""
    try:
        from .. import updater
        from ..settings import Settings
        s = Settings.load()
        first = updater.claim_instance()
        has_files = any(not a.startswith("-") and a != "gui" for a in sys.argv[1:])
        st = updater.on_startup(s.update_check, s.update_auto_install, s.update_branch,
                                has_file_args=has_files, first_instance=first)
        if st.install:
            try:
                updater.launch_install(st.install)
                return True, st
            except Exception as e:  # noqa: BLE001
                state = updater.UpdateState.load()
                state.pending = None
                if st.install.get("commit") and st.install["commit"] not in state.failed:
                    state.failed.append(st.install["commit"])
                state.save()
                st.message, st.level = f"The update couldn't be started: {e}", "warning"
        return False, st
    except Exception:  # noqa: BLE001 - the updater must never stop Lyridan from starting
        return False, None


def run() -> int:
    exit_now, startup = _startup_update()
    if exit_now:
        return 0
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
    from .fonts import load_bundled_fonts
    load_bundled_fonts()
    win = MainWindow(update_startup=startup)
    win.show()
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            win.load_any(arg)
    return app.exec()
