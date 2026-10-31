"""Fonts bundled with Lyridan (assets/fonts)."""
from __future__ import annotations

import os
import sys

# Green LCD text in the toolbar (clocks, file names): a modified Inter Medium with tabular
# digits, so running clocks don't jitter. See assets/fonts/OFL.txt.
COUNTER_FAMILY = "Lyridan Counter"
COUNTER_FILE = "LyridanCounter-Medium.ttf"
_loaded = None


def _font_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(base, "assets", "fonts", name)


def load_bundled_fonts() -> bool:
    """Register the bundled fonts with Qt (needs a QApplication). Safe to call more than once."""
    global _loaded
    if _loaded is None:
        from PySide6.QtGui import QFontDatabase
        fid = QFontDatabase.addApplicationFont(_font_path(COUNTER_FILE))
        _loaded = fid >= 0 and COUNTER_FAMILY in QFontDatabase.applicationFontFamilies(fid)
    return _loaded


def counter_family() -> str:
    if load_bundled_fonts():
        return COUNTER_FAMILY
    return "Segoe UI" if os.name == "nt" else ("Helvetica Neue" if sys.platform == "darwin" else "Sans Serif")
