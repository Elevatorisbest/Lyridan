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
    # DAW edit window, dark: neutral graphite panels, stacked rulers, track name plates, clips with
    # name bars, blue toggles and a large light-on-black counter ("style": "daw" adds the extra look)
    "digital_studio": {
        "name": "Digital Studio", "style": "daw", "bg": "#2c2d30", "fg": "#d4d6da", "text_bg": "#1d1e21",
        "text_fg": "#e3e5e8", "entry_bg": "#18191b", "entry_fg": "#eceef1", "btn_bg": "#45474c",
        "btn_fg": "#eef0f3", "btn_active_bg": "#54575d", "frame_bg": "#252629", "highlight": "#3b82d6",
        "select_bg": "#2d5b8f", "select_fg": "#ffffff", "border": "#0f1012", "muted": "#8f9298",
        "accent": "#4b97e6", "group_title": "#b9bcc2", "vocals": "#e2736c", "wave": "#e2736c",
        "clock_bg": "#0b0c0d", "clock_fg": "#d6e6f7", "playhead": "#8fd3ff", "check_border": "#7d8087",
        "ruler_bg": "#323438", "ruler_fg": "#aeb2b8", "header_bg": "#38393d", "header_hi": "#45474c",
        "lane_line": "#0c0d0e", "grid_bar": "#49505a", "grid_beat": "#2b2e33", "marker": "#e9c349",
        "toolbar_top": "#3b3d41", "toolbar_bot": "#2e3033", "clip_text": "#101114", "notes_clip": "#5a8fd0",
    },
    # DAW edit window, classic light: cool grey panels, light-blue clips with navy waveforms, lime counter
    "digital_studio_light": {
        "name": "Digital Studio Light", "style": "daw", "bg": "#c4c8cd", "fg": "#141619", "text_bg": "#e8ebee",
        "text_fg": "#121417", "entry_bg": "#f7f8f9", "entry_fg": "#121417", "btn_bg": "#e2e5e8",
        "btn_fg": "#141619", "btn_active_bg": "#f2f4f6", "frame_bg": "#d5d9dd", "highlight": "#2f6fd0",
        "select_bg": "#a8c9ee", "select_fg": "#000000", "border": "#8e959d", "muted": "#545a62",
        "accent": "#2f6fd0", "group_title": "#244b80", "vocals": "#7fa8dc", "wave": "#2c4d78",
        "clock_bg": "#121a10", "clock_fg": "#b6ff5c", "playhead": "#0b1f4d",
        "ruler_bg": "#d3d7db", "ruler_fg": "#2a2f35", "header_bg": "#b5bac0", "header_hi": "#c9cdd2",
        "lane_line": "#8e959d", "grid_bar": "#8a96a6", "grid_beat": "#cfd5dc", "marker": "#c99a12",
        "toolbar_top": "#d6dade", "toolbar_bot": "#b9bec4", "clip_text": "#0d1520", "notes_clip": "#7fa8dc",
    },
    # classic British large-format console strip: charcoal panel, cream legends, light-grey caps,
    # red / green / blue knobs, orange meters and green LEDs
    "studio_console": {
        "name": "Studio Console", "bg": "#232427", "fg": "#efeadf", "text_bg": "#1b1c1e", "text_fg": "#f2eee6",
        "entry_bg": "#34363a", "entry_fg": "#f4f0e8", "btn_bg": "#d8d8d4", "btn_fg": "#121212",
        "btn_active_bg": "#f0f0ec", "frame_bg": "#2b2c30", "highlight": "#2f74c0", "select_bg": "#3b5f86",
        "select_fg": "#ffffff", "border": "#46484d", "muted": "#a29e95", "accent": "#3fcf5c",
        "group_title": "#f4efe2", "vocals": "#ff7a1a", "wave": "#cfcabe", "clock_bg": "#0b0b0c",
        "clock_fg": "#ffffff", "playhead": "#e2473a", "check_border": "#8f8b83", "toggle_on": "#c8322a",
    },
    # its light counterpart, after a silver-blue console strip: pale panels, teal and blue knobs,
    # a red makeup knob and blue LED meters on navy
    "studio_console_light": {
        "name": "Studio Console Light", "bg": "#bfc6ca", "fg": "#25292c", "text_bg": "#eef1f2",
        "text_fg": "#1c1f22", "entry_bg": "#ffffff", "entry_fg": "#1c1f22", "btn_bg": "#1f7f86",
        "btn_fg": "#ffffff", "btn_active_bg": "#17666c", "frame_bg": "#dfe4e6", "highlight": "#1f8a8f",
        "select_bg": "#a9d0db", "select_fg": "#000000", "border": "#97a2a7", "muted": "#59636a",
        "accent": "#1f8a8f", "group_title": "#1c6a70", "vocals": "#2d62b4", "wave": "#2d5fb0",
        "clock_bg": "#0b1430", "clock_fg": "#5bb8ff", "playhead": "#d8392f",
    },
}
THEME_CHOICES = [("system", "System (follow the operating system)"), ("light", "Light"), ("dark", "Dark"),
                 ("lyridan_dark", "Lyridan Dark (black & yellow, from v1.1.1)"),
                 ("running_red", "Running Red (light: white & red)"),
                 ("akai_dark", "Akai Dark (dark: bright red)"),
                 ("mech_red_orange", "Mechanical Red & Orange (dark: black, orange & red)"),
                 ("digital_studio", "Digital Studio (dark: DAW edit window look)"),
                 ("digital_studio_light", "Digital Studio Light (light: classic DAW edit window)"),
                 ("studio_console", "Studio Console (dark: charcoal console strip)"),
                 ("studio_console_light", "Studio Console Light (light: silver-blue console strip)")]

_BASE_KEYS = ("name", "bg", "fg", "text_bg", "text_fg", "entry_bg", "entry_fg", "btn_bg", "btn_fg", "btn_active_bg",
              "frame_bg", "highlight", "select_bg", "select_fg", "border", "muted", "accent")
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
    for k in list(base):
        if k not in _BASE_KEYS:
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
    sheet = _stylesheet(c, theme)
    if c.get("style") == "daw":
        sheet += _daw_stylesheet(c)
    app.setStyleSheet(sheet)


def _stylesheet(c: dict, theme: str) -> str:
    on, off, ondis = _indicator_images(c)
    gt = c.get("group_title", c["fg"])
    on_bg = c.get("toggle_on", c["highlight"])    # toggle buttons (Follow, Metronome) when switched on
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
QToolButton:checked {{ background: {on_bg}; color: {_contrast(on_bg)}; border-color: {on_bg}; font-weight: bold; }}
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


def _daw_stylesheet(c: dict) -> str:
    """Extra rules for DAW-style themes: compact square controls, edit-window toolbar strips,
    window-style tabs, slim scroll bars and recessed fields. Purely visual."""
    top, bot = c["toolbar_top"], c["toolbar_bot"]
    hi = c["header_hi"]
    return f"""
QMainWindow {{ background: {c['bg']}; }}
QMenuBar {{ background: {bot}; border-bottom: 1px solid {c['border']}; }}
QMenuBar::item {{ padding: 3px 9px; }}
QMenu::item {{ padding: 4px 22px 4px 18px; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 3px 6px; }}
QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {hi}, stop:1 {c['btn_bg']});
    color: {c['btn_fg']}; border: 1px solid {c['border']}; border-radius: 3px; padding: 4px 11px; }}
QPushButton:hover {{ background: {c['btn_active_bg']}; border-color: {c['border']}; }}
QPushButton:pressed {{ background: {c['select_bg']}; color: {c['select_fg']}; }}
QPushButton:default {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c['accent']},
    stop:1 {c['highlight']}); color: #ffffff; border-color: {c['border']}; }}
QPushButton:default:hover {{ background: {c['accent']}; }}
QToolButton {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {hi}, stop:1 {c['btn_bg']});
    color: {c['btn_fg']}; border: 1px solid {c['border']}; border-radius: 3px; padding: 2px 6px; }}
QToolButton:hover {{ background: {c['btn_active_bg']}; }}
QToolButton:pressed {{ background: {c['select_bg']}; }}
QToolButton:checked {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c['accent']},
    stop:1 {c['highlight']}); color: #ffffff; border-color: {c['border']}; }}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{ background: {c['entry_bg']};
    color: {c['entry_fg']}; border: 1px solid {c['border']}; border-radius: 2px; }}
QComboBox {{ padding: 2px 6px; }}
QGroupBox {{ border: 1px solid {c['border']}; border-radius: 3px; margin-top: 20px; padding-top: 4px;
    background: {c['frame_bg']}; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 0px; top: 0px;
    padding: 2px 8px; color: {c['group_title']}; font-weight: bold;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {top}, stop:1 {bot});
    border: 1px solid {c['border']}; border-bottom: none; border-top-left-radius: 3px;
    border-top-right-radius: 3px; }}
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 0px; top: -1px; background: {c['frame_bg']}; }}
QTabBar::tab {{ background: {bot}; color: {c['muted']}; border: 1px solid {c['border']}; border-bottom: none;
    padding: 4px 14px; margin-right: 1px; border-top-left-radius: 3px; border-top-right-radius: 3px; }}
QTabBar::tab:selected {{ background: {c['frame_bg']}; color: {c['fg']}; font-weight: bold;
    border-top: 2px solid {c['accent']}; }}
QTabBar::tab:hover:!selected {{ color: {c['fg']}; }}
QHeaderView::section {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {top}, stop:1 {bot});
    color: {c['ruler_fg']}; border: none; border-right: 1px solid {c['border']};
    border-bottom: 1px solid {c['border']}; padding: 3px 5px; }}
QTableWidget, QListWidget, QTreeView {{ alternate-background-color: {c['frame_bg']}; border-radius: 0px; }}
QFrame#FileCard {{ border: 1px solid {c['border']}; border-radius: 3px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {top}, stop:1 {bot}); }}
QFrame#TransportBar, QFrame#NavBar {{ border: 1px solid {c['border']}; border-radius: 0px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {top}, stop:1 {bot}); }}
QFrame#TransportBar QLabel, QFrame#NavBar QLabel {{ background: transparent; }}
QFrame#TransportBar QLabel#MainCounter {{ background: {c['clock_bg']}; color: {c['clock_fg']}; border: 1px solid {c['border']};
    border-radius: 2px; padding: 1px 6px; }}
QStatusBar {{ background: {bot}; border-top: 1px solid {c['border']}; }}
QSplitter::handle {{ background: {c['border']}; }}
QSplitter::handle:vertical {{ height: 3px; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QScrollBar:horizontal {{ background: {c['frame_bg']}; height: 12px; border: none; border-top: 1px solid {c['border']}; }}
QScrollBar:vertical {{ background: {c['frame_bg']}; width: 12px; border: none; border-left: 1px solid {c['border']}; }}
QScrollBar::handle:horizontal {{ background: {hi}; min-width: 24px; margin: 2px; border-radius: 3px; }}
QScrollBar::handle:vertical {{ background: {hi}; min-height: 24px; margin: 2px; border-radius: 3px; }}
QScrollBar::handle:hover {{ background: {c['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QSlider::groove:horizontal {{ height: 4px; background: {c['entry_bg']}; border: 1px solid {c['border']};
    border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f2f3f5, stop:1 #a9adb3);
    border: 1px solid {c['border']}; width: 9px; margin: -6px 0; border-radius: 2px; }}
QProgressBar {{ border-radius: 2px; }}
QProgressBar::chunk {{ border-radius: 1px; }}
"""
