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
  **Syllable-synced `.ttml` is strongly recommended** - see [Why .lrc is not recommended](#why-lrc-is-not-recommended).
- **Uses Apple's own syllable splits.** If the TTML splits a word (`para` + `dise`), those splits are kept and timed exactly.
- **Beat sync:** load any arrangement XML from your chart (lead, rhythm or bass). Every syllable is snapped to its beat grid (1/4 to 1/64 notes, triplets included, time-signature aware).
- **Charting guidelines** are toggles. Lyridan applies the offset for your audio's intro silence (10 s by default) and two empty bars (measured from your beatmap), and warns if a lyric would land inside them.
- **Rocksmith formatting:** `-` / `+` markup, first word of each line capitalized, punctuation cleanup, ASCII-safe characters for the stock font.
- **Phrase-aware line breaks:** lines are kept to about **7-8 sung syllables** (the usual charting rule of thumb; Japanese gets a little more). Every way of breaking a phrase is compared at once:
  - commas and real pauses are preferred break points
  - words that belong together are never torn apart: articles and prepositions stay with their noun, Russian "не" with its verb, Japanese particles with their word
  - tiny fragments are avoided, e.g. "Ya / zhdu otveta" becomes "Ya zhdu otveta"
  - a line one or two syllables over the limit is kept whole when splitting it would read worse
- **Editing:** fix any line in the editor (`Eve-ry mo-ment / Takes me to pa-ra-dise`). Lyridan keeps the timing and `/` forces a line break.
- **Timeline with playback and an in-game lyrics preview:** below the lyrics you see:
  - the song's waveform
  - your chart's measures, sections and notes
  - the generated vocals, with a mark at every Rocksmith line break
  - an optional reference vocals XML to compare against

  Press **Play** (Space / Ctrl+P) and the preview shows each line the way Rocksmith will: syllables light up as they're sung, the next line waits below. It is built from the exact vocals that will be exported, so you check the final sync and line breaks before exporting.
  - **Navigation:** click anywhere to seek; click a lyric to jump to its line in the table. Double-clicking a line's time in the table moves the playhead there.
  - **Controls:** metronome on the chart's beats, 0.5× / 0.75× speed, follow-playhead, zoom with Ctrl + mouse wheel.
  - **Finding the audio:** Lyridan picks up the song audio by itself. It looks in a DLC Builder project (`.rs2dlc`) or for audio files next to your chart XML, and reuses the audio from the alignment tool. You can also drop an audio file on the window.
  - **Chart audio or original song:** both work. Lyridan detects which one you loaded and shifts the original song by the intro silence and empty bars.
- **Options** (Edit → Options): themes (System, Light, Dark and the original black-and-yellow **Lyridan Dark** from v1.x), text sizes, playback defaults, reopening the last session, default export folder, export-disclaimer and acknowledgement reset, alignment-model management and the build information.
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

## Why .lrc is not recommended

A normal `.lrc` file only says when each **line** starts. Lyridan then has to *guess* when every syllable inside the line is sung, so the timing of plain `.lrc` lyrics is **likely to be poor** - on the test song only 3% of syllables landed within a 1/16 note of the hand-made chart, compared to 93% from Apple's syllable-synced `.ttml`. Use a syllable-synced `.ttml` whenever you can; the app shows a warning whenever an `.lrc` is loaded.

### Experimental: align an .lrc to the song audio

If an `.lrc` is all you have, **Tools → Align lyrics to song audio (experimental)** (or the button in the warning) can turn it into a syllable-synced `.ttml`:

1. Choose the song audio - your chart's audio, the original song, or best of all an isolated **vocal stem** (UVR, Demucs…).
2. Lyridan finds where the lyrics start in that audio (it recognises a chart's intro silence + empty bars automatically), then uses Meta's multilingual **MMS forced-alignment** speech model (run locally through ONNX Runtime) to find where every syllable is actually sung, using the `.lrc` line timestamps as anchors. Parenthesised backing-vocal parts of `.lrc` lines become background lines.
3. The result is saved as a normal syllable-synced `.ttml` you can keep, fix and reuse.

Measured on *Baby Be Mine* (plain `.lrc` + chart audio, compared to the hand-made Rocksmith chart):

| input | same 1/16 grid point | within a 1/16 note | median difference |
|---|---|---|---|
| Apple syllable `.ttml` | 175 / 405 | 93% | 68 ms |
| plain `.lrc`, estimated | 3 / 405 | 3% | 818 ms |
| plain `.lrc` + audio alignment | 230 / 405 | 84% | 1 ms |

Results **vary from song to song**: dense backing vocals, heavy effects, very fast or very long notes and overlapping singers are harder, and mistakes cluster in such passages. Treat it as a strong starting point and check everything by ear. A full song takes about 30-60 s on a modern CPU and ~1.5 GB of RAM.

**Japanese kanji readings are checked against the audio too.** Some kanji have several readings and songs often use a less common one (e.g. 緋 is normally *hi*, but in *Ghost Sequence* it is sung *aka*). While aligning, Lyridan compares every alternative reading of such kanji with the singing: a reading that wins clearly replaces the dictionary one, and close calls are only listed in the result for you to check by ear (nothing is changed for them). Turn it off with the checkbox in the alignment dialog or `--no-verify-readings`. Without audio, readings stay dictionary-based: write `{緋|あか}` in the lyrics to force a reading.

The model (~340 MB) is **downloaded on first use** after you accept its licence (see [Credits and licenses](#credits-and-licenses)) and can be removed again from the Tools menu. Command line: `python -m lyridan align song.lrc song.ogg -b chart.xml --yes`.

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
python -m lyridan align song.lrc song.ogg -b chart.xml --yes   # experimental: .lrc -> syllable .ttml
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
- ONNX Runtime (MIT), NumPy (BSD), soundfile / libsndfile (BSD / LGPL), python-soxr (LGPL), certifi (MPL-2.0)
- OpenCorpora data via pymorphy3 (CC BY-SA, ё list)

The optional alignment model is **not** part of Lyridan's code or installers. It is downloaded separately on first use:

- **Model:** the MMS forced aligner by Meta AI (V. Pratap et al., [*Scaling Speech Technology to 1,000+ Languages*](https://arxiv.org/abs/2305.13516), 2023), distributed through [torchaudio](https://docs.pytorch.org/audio/main/generated/torchaudio.pipelines.MMS_FA.html).
- **Licence:** [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/), **non-commercial use only**. That fits Lyridan, a free charting tool; it must not be used commercially.
- **Changes:** the Lyridan project exported it to ONNX and quantized it to 8-bit (`tools/export_alignment_model.py`).
- **Hosting:** the converted files are published, with this attribution, as the `alignment-model-v1` release by `.github/workflows/alignment-model.yml`.
- **Your code's licence:** the model's licence covers the model files only. Lyridan's source code stays GPL-2.0.

Made by Elevatorisbest.
