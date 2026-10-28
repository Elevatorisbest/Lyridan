"""Command line interface.

  lyridan                          start the GUI
  lyridan convert song.ttml -b bass.xml -o vocals.xml [options]
  lyridan text song.lrc             print syllabized / romanized lyrics
"""
from __future__ import annotations

import argparse
import os
import sys

from . import VERSION


def _settings_from_args(a):
    from .settings import Settings
    s = Settings.load() if a.use_saved else Settings()
    if a.lang:
        s.language = a.lang
    if a.no_intro_silence:
        s.intro_silence = False
    if a.no_empty_bars:
        s.two_empty_bars = False
    if a.no_apple_offsets:
        s.apply_lyric_offset = False
        s.apply_leading_silence = False
    if a.offset_ms is not None:
        s.manual_offset_ms = a.offset_ms
    if a.snap:
        s.snap = a.snap
    if a.max_chars is not None:
        s.max_line_chars = a.max_chars
    if a.background:
        s.background = a.background
    if a.ru_scheme:
        s.ru_scheme = a.ru_scheme
    if a.ja_syllables:
        s.ja.syllables = a.ja_syllables
    if a.no_source_romaji:
        s.use_source_romaji = False
    return s


def _ensure_console():
    """Windowed (frozen) builds have no stdout; attach to the calling console for CLI use."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    if sys.platform == "win32":
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                sys.stderr = sys.stdout
        except Exception:  # noqa: BLE001
            pass
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] == "gui" or (argv[0] not in ("convert", "text", "-h", "--help", "--version")
                                         and not argv[0].startswith("-")):
        from .gui.app import run
        return run()
    _ensure_console()
    if argv[0] == "--version":
        from . import buildinfo
        print(f"Lyridan {buildinfo.display_version()}")
        if "-v" in argv or "--verbose" in argv or buildinfo.is_dev():
            print(buildinfo.as_text())
        return 0
    p = argparse.ArgumentParser(prog="lyridan", description=f"Lyridan {VERSION}")
    sub = p.add_subparsers(dest="cmd")

    def common(sp):
        sp.add_argument("input")
        sp.add_argument("--lang", choices=["auto", "en", "ja", "ru", "ja_romaji"])
        sp.add_argument("--ru-scheme", choices=["practical", "bgn", "gost_b", "iso9", "icao", "alalc", "scholarly"])
        sp.add_argument("--ja-syllables", choices=["mora", "mora_n", "syllable"])
        sp.add_argument("--no-source-romaji", action="store_true")
        sp.add_argument("--use-saved", action="store_true", help="start from the GUI's saved settings")
        sp.add_argument("--no-intro-silence", action="store_true")
        sp.add_argument("--no-empty-bars", action="store_true")
        sp.add_argument("--no-apple-offsets", action="store_true")
        sp.add_argument("--offset-ms", type=float)
        sp.add_argument("--snap")
        sp.add_argument("--max-chars", type=int)
        sp.add_argument("--background", choices=["exclude", "nonoverlap"])

    c = sub.add_parser("convert", help="create a Rocksmith vocals XML")
    common(c)
    c.add_argument("-b", "--beatmap", help="Rocksmith arrangement XML with the synced beatmap")
    c.add_argument("-o", "--output")
    c.add_argument("--native-output", help="also write a native-script (kana/kanji, cyrillic) vocals XML")
    t = sub.add_parser("text", help="print syllabized / romanized lyrics")
    common(t)
    t.add_argument("--sep", default="-")
    a = p.parse_args(argv)
    if not a.cmd:
        p.print_help()
        return 1

    from .parsers import load_lyrics
    from .pipeline import process
    s = _settings_from_args(a)
    src = load_lyrics(a.input)
    pr = process(src, s)
    for w in pr.warnings:
        print("note:", w, file=sys.stderr)
    if a.cmd == "text":
        from .exports import syllabized_text
        sys.stdout.write(syllabized_text(pr.lines, a.sep))
        return 0

    from .parsers.rsxml import parse_beatmap, write_vocals
    from .rocksmith import build_vocals
    bm = parse_beatmap(a.beatmap) if a.beatmap else None
    res = build_vocals(pr.lines, s, bm, src.lyric_offset, src.leading_silence)
    out = a.output or os.path.splitext(a.input)[0] + "_Vocals_RS2.xml"
    write_vocals(res.entries, out)
    print(f"wrote {out}: {len(res.entries)} vocals, offset {res.offset.total:+.3f}s")
    for w in res.warnings:
        print("warning:", w, file=sys.stderr)
    if a.native_output:
        prn = process(src, s, native_script=True)
        resn = build_vocals(prn.lines, s, bm, src.lyric_offset, src.leading_silence, native=True)
        write_vocals(resn.entries, a.native_output)
        print(f"wrote {a.native_output}: {len(resn.entries)} vocals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
