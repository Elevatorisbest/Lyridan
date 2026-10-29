"""User settings (persisted as JSON in the user's config folder)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from typing import Dict

from .lang.japanese import JapaneseOptions


def config_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "Lyridan")
    elif sys.platform == "darwin":
        path = os.path.expanduser("~/Library/Application Support/Lyridan")
    else:
        path = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "lyridan")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass
class Settings:
    # ---- language -----------------------------------------------------------
    language: str = "auto"                 # auto | en | ja | ru | ja_romaji
    ja: JapaneseOptions = field(default_factory=JapaneseOptions)
    use_source_romaji: bool = True         # use Apple's ja-Latn transliteration when present
    verify_readings: bool = True           # audio alignment: let the audio pick Japanese readings
    ru_scheme: str = "practical"
    ru_syllables: str = "phonetic"         # phonetic | closed
    ru_restore_yo: bool = True
    ru_soft_sign: bool = False             # keep ь as ' in practical scheme
    romanize: bool = True                  # False = keep native script in the main export
    split_hyphenated: bool = True          # "ooh-ooh" -> two words
    en_user_dict: Dict[str, str] = field(default_factory=dict)

    # ---- timing / sync ----------------------------------------------------------
    intro_silence: bool = True             # chart audio has 10 s of leading silence
    intro_silence_seconds: float = 10.0
    two_empty_bars: bool = True            # chart audio has two empty bars before the song
    empty_bars: int = 2
    apply_lyric_offset: bool = True        # Apple <audio lyricOffset>
    apply_leading_silence: bool = True     # Apple leadingSilence compensation
    manual_offset_ms: float = 0.0
    snap: str = "1/16"                     # off | 1/4 | 1/8 | 1/12 | 1/16 | 1/24 | 1/32 | 1/64
    min_gap: str = "1/32"                  # minimum gap between vocals (grid note or "0")
    syllable_weighting: str = "equal"      # equal | letters
    max_syllable_seconds: float = 0.6      # for line-only timing (plain LRC)
    background: str = "exclude"            # exclude | nonoverlap

    # ---- Rocksmith formatting -------------------------------------------------
    max_line_syllables: int = 8            # charter rule of thumb: 7-8 sung syllables per line
    max_line_chars: int = 40
    gap_split_seconds: float = 0.75
    capitalize_lines: bool = True
    keep_punctuation: str = "?!"
    ascii_only: bool = True                # Rocksmith default font is ASCII-only
    note_value: int = 0

    # ---- notices ------------------------------------------------------------
    disclaimer_acknowledged: bool = False  # "don't show again" on the export disclaimer

    # ---- application options (Options dialog) ------------------------------------
    theme: str = "dark"                    # system | light | dark | lyridan_dark
    ui_font_pt: int = 0                    # 0 = system default
    preview_font_pt: int = 22              # in-game lyric preview
    restore_session: bool = True           # reopen the last lyrics / beatmap / audio
    playback_volume: int = 80
    metronome: bool = False
    follow_playhead: bool = True
    timeline_arrow_step: str = "beat"      # 0.1s | quarter | half | beat | bar | 1s
    timeline_accelerate: bool = True       # arrow keys speed up while held
    export_folder: str = ""                # "" = next to the beatmap / lyrics
    last_session: Dict[str, str] = field(default_factory=dict)

    # ---- other exports ------------------------------------------------------
    text_syllable_sep: str = "-"
    text_word_sep: str = " "

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "Settings":
        s = cls()
        names = {f.name for f in fields(cls)}
        for k, v in (data or {}).items():
            if k == "ja" and isinstance(v, dict):
                jn = {f.name for f in fields(JapaneseOptions)}
                s.ja = JapaneseOptions(**{a: b for a, b in v.items() if a in jn})
            elif k in names:
                setattr(s, k, v)
        return s

    @classmethod
    def load(cls) -> "Settings":
        path = os.path.join(config_dir(), "settings.json")
        try:
            with open(path, encoding="utf-8") as fh:
                return cls.from_json(json.load(fh))
        except (OSError, ValueError):
            return cls()

    def save(self) -> None:
        path = os.path.join(config_dir(), "settings.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_json(), fh, ensure_ascii=False, indent=2)
