"""Application themes: System, Light, Dark and the original Lyridan Dark (black & yellow)."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
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
}
THEME_CHOICES = [("system", "System (follow the operating system)"), ("light", "Light"), ("dark", "Dark"),
                 ("lyridan_dark", "Lyridan Dark (black & yellow, from v1.1.1)")]

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
    return base


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
        QPalette.ButtonText: c["fg"], QPalette.Highlight: c["select_bg"] if theme == "lyridan_dark" else c["highlight"],
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
    return f"""
QWidget {{ color: {c['fg']}; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QGroupBox {{ border: 1px solid {c['border']}; border-radius: 6px; margin-top: 12px; padding-top: 6px;
            background: {c['frame_bg']}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {c['fg']}; font-weight: bold; }}
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
QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; }}
QCheckBox::indicator:unchecked {{ border: 1px solid {c['border']}; background: {c['entry_bg']}; border-radius: 3px; }}
QCheckBox::indicator:checked {{ border: 1px solid {c['border']}; background: {c['accent']}; border-radius: 3px; }}
QProgressBar {{ border: 1px solid {c['border']}; border-radius: 4px; text-align: center; background: {c['entry_bg']}; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
QToolTip {{ background: {c['frame_bg']}; color: {c['text_fg']}; border: 1px solid {c['border']}; }}
QSplitter::handle {{ background: {c['border'] if theme != 'lyridan_dark' else '#333333'}; }}
"""
