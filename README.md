# Lyridan

![lyridanlogo](https://github.com/user-attachments/assets/335da193-0a28-4bf8-8848-3dcc610e3332)

Lyridan turns synced lyrics (`.ttml` or `.lrc`) into a **Rocksmith 2014 vocals arrangement XML**. The output is already syllabized, romanized and snapped to your chart's beatmap, ready to import into **Editor on Fire**, **Charter** or **DLC Builder**.

Version 2.0 is a full rewrite of the app.

## Features

| | English | Japanese | Russian |
|---|---|---|---|
| Automatic syllables | ✅ dictionary + trained model | ✅ mora / syllable modes | ✅ phonetic or closed syllables |
| Romanization / latinization | — | ✅ Hepburn (configurable) | ✅ 7 standards |
| Native-script export | — | ✅ kana/kanji (JVocals) | ✅ Cyrillic |

- **Inputs:** Apple Music syllable-synced TTML (raw TTML or the JSON API response), word- or line-synced TTML, plain LRC, and enhanced LRC (`<mm:ss.xx>` word tags).
- **Uses Apple's own syllable splits.** If the TTML splits a word (`para` + `dise`), those splits are kept and timed exactly.
- **Beat sync:** load any arrangement XML from your chart (lead, rhythm or bass). Every syllable is snapped to its beat grid (1/4 to 1/64 notes, triplets included, time-signature aware).
- **Charting guidelines** are toggles. Lyridan applies the offset for your audio's intro silence (10 s by default) and two empty bars (measured from your beatmap), and warns if a lyric would land inside them.
- **Rocksmith formatting:** `-` / `+` markup, line splitting at pauses and by length, first word of each line capitalized, punctuation cleanup, ASCII-safe characters for the stock font.
- **Editing:** fix any line in the editor (`Eve-ry mo-ment / Takes me to pa-ra-dise`). Lyridan keeps the timing and `/` forces a line break.
- **Timeline:** shows your chart's measures, sections and notes next to the generated vocals, plus an optional reference vocals XML to compare against.
- **Projects** (`.lyridan`) save the files, settings and your edits. **User dictionaries** hold your own English syllable splits and Japanese readings.
- **Other exports:** syllabized text (for UltraStar Creator and similar) and romanized LRC or enhanced LRC.

## How sync works

```
chart time = lyric time
           + intro silence            (default 10 s)                 [toggle]
           + N empty bars             (read from your beatmap)       [toggle]
           + TTML lyricOffset         (Apple, e.g. -0.139 s)          [toggle]
           - TTML leadingSilence      (Apple, e.g. 0.200 s)           [toggle]
           + manual offset (ms)
```

The total is shown at the bottom of the window. With the defaults, the bundled test song (*Baby Be Mine*) gets an offset of +14.024 s. Compared with the hand-charted vocals:

- 405 of 416 syllables are identical.
- Median timing difference is 0.000 s.
- 86% of syllables land within 150 ms.
- The first lyric is on the exact same 1/16 grid point.

If your chart's audio was prepared differently, turn off the toggles that don't apply and use the manual offset. The timeline shows the result against your chart notes.

## Language details

### English
1. Your own dictionary.
2. Built-in lyric words (gonna, c'mon, everybody…).
3. A curated 47,700-word karaoke-style syllable dictionary (*li-ving, ma-gic, eve-ry, dif-fe-rent*).
4. For any other word, a boundary model trained on that dictionary, guided by syllable counts from the CMU Pronouncing Dictionary. It splits about 95% of unseen dictionary words exactly like the dictionary would.

Contractions, possessives, elongated words (*ooooh*) and hyphenated words are handled.

### Japanese
- **Readings** come from MeCab (fugashi) with UniDic, so they depend on context.
- **Lyric corrections:** 私→watashi, 明日→ashita, 貴女→anata, 抱く→daku (or *idaku* after 夢を), 何を→nani o, 何時まで→itsu made…
- **Reading review:** words that songs often read differently (宇宙 *sora*, 永遠 *towa*, 運命 *sadame*, 刃 *yaiba*…) are listed in the Notes column for you to check.
- **Furigana in the lyric file wins:** `宇宙(そら)`, `宇宙（そら）`, `{宇宙|そら}`, `|宇宙《そら》`. A reading dictionary in the app does the same for every song.
- **Romanization is modified Hepburn.** は/へ/を are spelled as pronounced, including inside words (こんにちは → *konnichiwa*). っ doubles the consonant, *tch* before *ch*.
- **Romanization options:**
  - long vowels: as written (*tou*), macrons (*tō*) or simplified (*to*)
  - を: *o* or *wo*
  - *n'* before vowels
  - katakana loanwords spelled in English (ラブ → *love*)
- **Grouping:** verbs keep their endings (*dakishimetai, utatte, aitakute*), particles stay separate (*kimi no*, *boku wa*), and English words inside Japanese lines stay English.
- **Syllable modes:** every mora, mora with ん/っ joined (default: *kon-ni-chi-wa*), or syllables with long vowels joined (*tou-kyou*).
- **Apple romaji:** if the TTML includes Apple's own romaji (`ja-Latn` transliteration), Lyridan can use it directly.
- **Native-script export:** every romaji syllable keeps a link to its kana/kanji, so a Japanese vocals XML (for a custom font in DLC Builder) can be exported with the same timing.

### Russian
- **ё restoration** (еще → ещё, идет → идёт). It uses a 120,000-word-form list built from OpenCorpora and only restores ё where the spelling is unambiguous.
- **Syllables:** phonetic and open (*ко-шка, се-стра, кар-та, сол-нце, ван-на*) or closed (*кош-ка*).
- **Latinization standards:** Practical (Wikipedia/English), BGN/PCGN, GOST 7.79-B, ISO 9, ICAO (passports), ALA-LC and Scholarly. Context rules (*ye* after vowels, *-sky* endings…) are applied per word, then split by syllable.

## Installation

### Windows
Download `Lyridan-<version>-Windows-x64-Setup.exe` from Releases and run it. A portable `.zip` is also provided.
*SmartScreen may warn because the app isn't code-signed. Choose "More info → Run anyway".*

### macOS (Apple Silicon and Intel)
Download the DMG for your Mac (`AppleSilicon` or `Intel`), open it and drag Lyridan to Applications.
The app isn't notarized. If macOS says it's damaged or from an unidentified developer, run:
```bash
xattr -cr /Applications/Lyridan.app
```

## Using it

1. Drop a `.ttml` / `.lrc` file onto the window.
2. Drop the arrangement XML of the chart you're working on (it has the synced beatmap).
3. Check the **Lyrics** tab (edit lines if needed), the **Timeline** and the **Notes** tab.
4. Click **Export Rocksmith vocals XML…** and import it in EOF / Charter / DLC Builder.

Command line (also works with the installed app):
```bash
python -m lyridan convert song.ttml -b "2_Bass_RS2.xml" -o "1_Vocals_RS2.xml" [--native-output JVocals.xml]
python -m lyridan text song.lrc          # print syllabized / romanized lyrics
python -m lyridan convert --help         # all options
```

## Building from source

Requires Python 3.11+.

```bash
pip install -r requirements-dev.txt
python -m pytest -q          # tests
python Lyridan.py            # run the app
```

- **Windows installer:** `build_windows.bat` (needs Inno Setup 6 for the installer step).
- **macOS app + DMG:** `bash build_macos.sh` (builds for the architecture of the Mac it runs on).
- **CI** (`.github/workflows/build.yml`): every push runs the tests, then builds:
  - Windows: installer + portable zip
  - macOS Apple Silicon (`macos-15`) and Intel (`macos-15-intel`): `.pkg` installer + `.dmg`

  Each frozen app is smoke-tested before packaging.

| Push to | Channel | Version shown | Published as |
|---|---|---|---|
| `dev` (or any other branch) | dev | `2.0.0-dev.<run> (<commit>)` with full build info in **Settings → Build information** (branch, commit, message, build number, build machine, workflow run link, runtime library versions, "Copy build info" button) and a DEV badge | rolling pre-release **dev-latest** + workflow artifacts |
| `main` | stable | `2.0.0` only | GitHub release **v2.0.0** (re-uploaded if `VERSION` wasn't bumped) |
| tag `v*` | stable | `2.0.0` only | release for that tag |

Bump `VERSION` in `lyridan/__init__.py` before merging to `main` to get a new release. Local builds are dev builds unless you pass `--channel stable` (`build_windows.bat --channel stable`, `bash build_macos.sh --channel stable`). `python -m lyridan --version` prints the same build info.

The bundled language data can be rebuilt with the scripts in `tools/`:

| Script | Rebuilds |
|---|---|
| `train_english_model.py --eval` | English boundary model |
| `build_cmu_counts.py` | CMU syllable counts |
| `build_yo_dict.py` | ё dictionary |
| `compare_reference.py -v` | Compares output with the reference chart |

### Project layout
```
lyridan/
  parsers/   ttml.py, lrc.py, rsxml.py     input files, beatmap, vocals XML
  lang/      english.py, japanese.py, kana.py, russian.py, hyphen_model.py
  pipeline.py    language processing + timing of every syllable
  rocksmith.py   offsets, grid snapping, line breaking, Rocksmith markup
  gui/           PySide6 interface
  data/          dictionaries and models
packaging/   PyInstaller spec, Inno Setup script, DMG script
tests/       regression tests + reference song files
```

## Credits and licenses
Lyridan is GPL-2.0. It uses:

- PySide6 / Qt (LGPL)
- fugashi (MIT) and MeCab (BSD)
- UniDic-lite (BSD)
- the CMU Pronouncing Dictionary (BSD)
- OpenCorpora data via pymorphy3 (CC BY-SA, ё list)

Made by Elevatorisbest.
