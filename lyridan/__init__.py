"""Lyridan - synced lyric to Rocksmith vocals converter.

Turns .ttml / .lrc lyrics (English, Japanese, Russian) into syllabized,
romanized and beat-synced Rocksmith vocal arrangement XML files.
"""

VERSION = "2.0.0"
APP_NAME = "Lyridan"
AUTHOR = "Elevatorisbest"

try:  # set by tools/write_build_info.py for packaged builds
    from ._build import BUILD, BUILD_DATE
except ImportError:  # pragma: no cover
    BUILD, BUILD_DATE = "", ""

DISPLAY_VERSION = BUILD or VERSION
