"""Application themes.

System, Light, Dark, the original Lyridan Dark (black & yellow) and four themed
palettes. Every theme gets clearly drawn check boxes (a tick on the accent colour
when on, an empty outlined box when off), generated as small PNGs at runtime.
Optional keys per theme: ``wave`` (timeline waveform), ``clock_bg`` / ``clock_fg``
(the transport time display), ``group_title`` (settings group headings).
"""
from __future__ import annotations

import os

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QApplication

# Colours carried over from Lyridan v1.1.1 (gui.py THEMES)
THEMES = {
    "light": {
        "name": "Light", "bg": "#f0f0f0", "fg": "#000000", "text_bg": "#ffffff", "text_fg": "#333333",
        "entry_bg": "#ffffff", "entry_fg": "#333333", "btn_bg": "#007acc", "btn_fg": "#ffffff",
        "btn_active_bg": "#005f9e", "frame_bg": "#ffffff", "highlight": "#007acc", "select_bg": "#add6ff",
        "select_fg": "#000000", "border": "#cccccc", "muted": "#6b6b6b", "accent": "#007acc",
    },
    "dark": {
        "name": "Dark", "bg": "#1e1e1e", "fg": "#ffffff", "text_bg": "#252526", "text_fg": "#d4d4d4",
        "entry_bg": "#3c3c3c", "entry_fg": "#cccccc", "btn_bg": "#0e639c", "btn_fg": "#ffffff",
        "btn_active_bg": "#1177bb", "frame_bg": "#252526", "highlight": "#007fd4", "select_bg": "#264f78",
        "select_fg": "#ffffff", "border": "#3c3c3c", "muted": "#9d9d9d", "accent": "#3794ff",
    },
    "lyridan_dark": {
        "name": "Lyridan Dark", "bg": "#000000", "fg": "#fbeb4e", "text_bg": "#0a0a0a", "text_fg": "#ffffff",
        "entry_bg": "#1a1a1a", "entry_fg": "#fbeb4e", "btn_bg": "#fbeb4e", "btn_fg": "#000000",
        "btn_active_bg": "#fff176", "frame_bg": "#0a0a0a", "highlight": "#fbeb4e", "select_bg": "#333333",
        "select_fg": "#fbeb4e", "border": "#fbeb4e", "muted": "#b8ac3c", "accent": "#fbeb4e",
    },
    # light: white surfaces with one bold red accent (free-running rooftop look)
    "running_red": {
        "name": "Running Red", "bg": "#f3f3f3", "fg": "#141414", "text_bg": "#ffffff", "text_fg": "#1a1a1a",
        "entry_bg": "#ffffff", "entry_fg": "#1a1a1a", "btn_bg": "#d7001b", "btn_fg": "#ffffff",
        "btn_active_bg": "#b00016", "frame_bg": "#ffffff", "highlight": "#d7001b", "select_bg": "#ffd5da",
        "select_fg": "#000000", "border": "#d0d0d0", "muted": "#666666", "accent": "#d7001b",
        "group_title": "#d7001b", "wave": "#9a9a9a", "clock_bg": "#ffffff", "clock_fg": "#d7001b",
        "playhead": "#111111",
    },
    # dark with bright red accents; body text stays near-white for readability
    "akai_dark": {
        "name": "Akai Dark", "bg": "#121214", "fg": "#f2f2f4", "text_bg": "#18181c", "text_fg": "#e8e8ec",
        "entry_bg": "#24242a", "entry_fg": "#f0f0f2", "btn_bg": "#e3202d", "btn_fg": "#ffffff",
        "btn_active_bg": "#ff3945", "frame_bg": "#1b1b1f", "highlight": "#ff3b47", "select_bg": "#5c1a20",
        "select_fg": "#ffffff", "border": "#3b3b42", "muted": "#a3a3ad", "accent": "#ff3b47",
        "group_title": "#ff5a64", "wave": "#b8b8c2", "clock_bg": "#0a0a0b", "clock_fg": "#ff4d58",
        "playhead": "#ffffff",
    },
    # black, signal orange and red, like a red-and-orange giant robot's armour plating
    "mech_red_orange": {
        "name": "Mechanical Red & Orange", "bg": "#0d0907", "fg": "#ffd2a8", "text_bg": "#140d0a",
        "text_fg": "#f7ece4", "entry_bg": "#24170f", "entry_fg": "#ffe3c9", "btn_bg": "#c8102e",
        "btn_fg": "#ffffff", "btn_active_bg": "#e52a40", "frame_bg": "#1a110c", "highlight": "#ff6a13",
        "select_bg": "#7a2a0e", "select_fg": "#ffffff", "border": "#6a3518", "muted": "#bf9070",
        "accent": "#ff6a13", "group_title": "#ff7a1f", "wave": "#ff9b54", "clock_bg": "#000000",
        "clock_fg": "#ff7a1f", "playhead": "#ffe14d",
    },
    # graphite studio console: grey panels, light-blue selection, green-on-black counter
    "studio_console": {
        "name": "Studio Console", "bg": "#2b2d31", "fg": "#d9dce1", "text_bg": "#1f2124", "text_fg": "#e2e4e8",
        "entry_bg": "#3a3d43", "entry_fg": "#eceef1", "btn_bg": "#4a4f57", "btn_fg": "#ffffff",
        "btn_active_bg": "#5b616b", "frame_bg": "#33363b", "highlight": "#4aa3e8", "select_bg": "#2e5f8a",
        "select_fg": "#ffffff", "border": "#4b4f56", "muted": "#9aa0a8", "accent": "#5cb8ff",
        "group_title": "#9fd3ff", "wave": "#8fc1ea", "clock_bg": "#050807", "clock_fg": "#5dff8f",
    },
}
THEME_CHOICES = [("system", "System (follow the operating system)"), ("light", "Light"), ("dark", "Dark"),
                 ("lyridan_dark", "Lyridan Dark (black & yellow, from v1.1.1)"),
                 ("running_red", "Running Red (light: white & red)"),
                 ("akai_dark", "Akai Dark (dark: bright red)"),
                 ("mech_red_orange", "Mechanical Red & Orange (dark: black, orange & red)"),
                 ("studio_console", "Studio Console (dark: DAW grey, green counter)")]

_default_palette = None
_default_font = None


def current_colors(theme: str) -> dict:
    if theme in THEMES:
        return THEMES[theme]
    app = QApplication.instance()
    pal = app.palette()
    dark = pal.window().color().lightness() < 128
    base = dict(THEMES["dark" if dark else "light"])
    base["accent"] = pal.highlight().color().name()
    for k in ("wave", "clock_bg", "clock_fg", "group_title", "playhead"):
        base.pop(k, None)
    return base


def _contrast(color: str) -> str:
    c = QColor(color)
    lum = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
    return "#000000" if lum > 0.55 else "#ffffff"


def _indicator_images(c: dict) -> tuple:
    """PNG check-box images (on / off / on-disabled) in the theme's colours; returns their paths."""
    from ..settings import config_dir
    folder = os.path.join(config_dir(), "theme_cache")
    os.makedirs(folder, exist_ok=True)
    acc, tick = c["accent"], _contrast(c["accent"])
    off_border = c.get("check_border") or c["muted"]
    out = []
    for kind, fill, line, mark in (("on", acc, acc, tick), ("off", c["entry_bg"], off_border, None),
                                   ("ondis", c["muted"], c["muted"], c["entry_bg"])):
        path = os.path.join(folder, f"cb_{kind}_{fill[1:]}_{line[1:]}_{(mark or 'x').lstrip('#')}.png")
        if not os.path.exists(path):
            size = 64                                   # drawn large, Qt scales it down crisply
            img = QImage(size, size, QImage.Format_ARGB32)
            img.fill(Qt.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(QPen(QColor(line), 6))
            p.setBrush(QColor(fill))
            p.drawRoundedRect(4, 4, size - 8, size - 8, 10, 10)
            if mark:
                path_ = QPainterPath(QPointF(16, 33))
                path_.lineTo(QPointF(27, 45))
                path_.lineTo(QPointF(49, 20))
                p.setPen(QPen(QColor(mark), 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path_)
            p.end()
            img.save(path, "PNG")
        out.append(path.replace("\\", "/"))
    return tuple(out)


def apply_theme(app: QApplication, theme: str, font_pt: int = 0) -> None:
    global _default_palette, _default_font
    if _default_palette is None:
        _default_palette = QPalette(app.palette())
        _default_font = QFont(app.font())
    app.setStyle("Fusion")
    f = QFont(_default_font)
    if font_pt:
        f.setPointSize(int(font_pt))
    app.setFont(f)
    if theme not in THEMES:
        app.setPalette(_default_palette)
        app.setStyleSheet("")
        return
    c = THEMES[theme]
    p = QPalette()
    roles = {
        QPalette.Window: c["bg"], QPalette.WindowText: c["fg"], QPalette.Base: c["text_bg"],
        QPalette.AlternateBase: c["frame_bg"], QPalette.Text: c["text_fg"], QPalette.Button: c["frame_bg"],
        QPalette.ButtonText: c["fg"],
        QPalette.Highlight: c["select_bg"] if theme in ("lyridan_dark", "mech_red_orange") else c["highlight"],
        QPalette.HighlightedText: c["select_fg"], QPalette.ToolTipBase: c["frame_bg"],
        QPalette.ToolTipText: c["text_fg"], QPalette.PlaceholderText: c["muted"], QPalette.Link: c["accent"],
        QPalette.BrightText: "#ff5555",
    }
    for role, col in roles.items():
        p.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c["muted"]))
    app.setPalette(p)
    app.setStyleSheet(_stylesheet(c, theme))


def _stylesheet(c: dict, theme: str) -> str:
    on, off, ondis = _indicator_images(c)
    gt = c.get("group_title", c["fg"])
    return f"""
QWidget {{ color: {c['fg']}; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QGroupBox {{ border: 1px solid {c['border']}; border-radius: 6px; margin-top: 12px; padding-top: 6px;
            background: {c['frame_bg']}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {gt}; font-weight: bold; }}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {c['entry_bg']}; color: {c['entry_fg']}; border: 1px solid {c['border']};
    border-radius: 4px; padding: 3px 5px; selection-background-color: {c['select_bg']};
    selection-color: {c['select_fg']}; }}
QComboBox QAbstractItemView {{ background: {c['entry_bg']}; color: {c['entry_fg']};
    selection-background-color: {c['select_bg']}; selection-color: {c['select_fg']}; }}
QPushButton {{ background: {c['btn_bg']}; color: {c['btn_fg']}; border: 1px solid {c['btn_bg']};
    border-radius: 4px; padding: 5px 12px; }}
QPushButton:hover {{ background: {c['btn_active_bg']}; border-color: {c['btn_active_bg']}; }}
QPushButton:disabled {{ background: {c['frame_bg']}; color: {c['muted']}; border-color: {c['border']}; }}
QPushButton:default {{ font-weight: bold; }}
QToolButton {{ background: {c['frame_bg']}; color: {c['fg']}; border: 1px solid {c['border']};
    border-radius: 4px; padding: 3px 7px; }}
QToolButton:hover {{ background: {c['select_bg']}; }}
QToolButton:checked {{ background: {c['btn_bg']}; color: {c['btn_fg']}; }}
QTableWidget, QListWidget, QTreeView {{ background: {c['text_bg']}; color: {c['text_fg']};
    gridline-color: {c['border'] if theme != 'lyridan_dark' else '#333333'}; border: 1px solid {c['border']};
    selection-background-color: {c['select_bg']}; selection-color: {c['select_fg']}; }}
QHeaderView::section {{ background: {c['frame_bg']}; color: {c['fg']}; border: none;
    border-bottom: 1px solid {c['border']}; padding: 4px; font-weight: bold; }}
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 4px; top: -1px; }}
QTabBar::tab {{ background: {c['frame_bg']}; color: {c['muted']}; border: 1px solid {c['border']};
    border-bottom: none; padding: 5px 12px; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
QTabBar::tab:selected {{ background: {c['bg']}; color: {c['fg']}; font-weight: bold; }}
QMenuBar {{ background: {c['bg']}; color: {c['fg']}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {c['select_bg']}; color: {c['select_fg']}; }}
QMenu {{ background: {c['frame_bg']}; color: {c['fg']}; border: 1px solid {c['border']}; }}
QStatusBar {{ background: {c['bg']}; color: {c['muted']}; }}
QScrollArea {{ border: none; }}
QFrame#FileCard {{ border: 1px solid {c['border']}; border-radius: 6px; background: {c['frame_bg']}; }}
QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {c['accent']}; width: 12px; margin: -5px 0; border-radius: 6px; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QCheckBox::indicator:unchecked {{ image: url("{off}"); }}
QCheckBox::indicator:checked {{ image: url("{on}"); }}
QCheckBox::indicator:checked:disabled {{ image: url("{ondis}"); }}
QCheckBox:disabled {{ color: {c['muted']}; }}
QProgressBar {{ border: 1px solid {c['border']}; border-radius: 4px; text-align: center; background: {c['entry_bg']}; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
QToolTip {{ background: {c['frame_bg']}; color: {c['text_fg']}; border: 1px solid {c['border']}; }}
QSplitter::handle {{ background: {c['border'] if theme != 'lyridan_dark' else '#333333'}; }}
"""
