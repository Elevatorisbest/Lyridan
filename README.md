# Lyridan
![lyridanlogo](https://github.com/user-attachments/assets/335da193-0a28-4bf8-8848-3dcc610e3332)


## What is it?
Lyridan is an experimental program that I created, originally to have a way of syllabizing and romanizing Japanese lyrics for my Rocksmith charts.

It ended up evolving into a humble program that also lets you create roughly aligned and syllabized Rocksmith Vocal .XML arrangements ready to be imported into the chart and game from a .ttml file (acquired from eg. Apple Music).

## Features

### Romanization/Transliteration of .lrc lyric files

#### Currently supported languages are:

- **Japanese** (🇯🇵)
- **Russian** (🇷🇺)

### Syllabization of .lrc lyric files

#### Currently supported languages are:

- **English** (🇬🇧)
- **Japanese** (🇯🇵)
- **Russian** (🇷🇺)

### Export to a text file ready for import into external programs like Ultra Star Creator

- Syllabe separator can be replaced with any character or set of characters you wish to use up to 20 characters long.

### Conversion of synced-by-beat .ttml lyric files into a Rocksmith Vocal .xml Arrangement file

- ⚠️ Experimental feature that depends on the accuracy of the provided .ttml file.
- Automatic romanization of Japanese (🇯🇵) .ttml files is included in the conversion process.

#### Languages that have been tested to work are:

- **English** (🇬🇧)
- **Japanese** (🇯🇵)



## Install

1. 

## Build Instructions

This folder contains all files needed to build Lyridan into a single executable.

### Required Files

- `gui.py` - Main GUI application
- `syllabize.py` - Core syllabization and Rocksmith export logic
- `config.py` - Configuration management (persistent settings)
- `English.txt` - English syllabification dictionary (47,737 words)
- `lyridanlogo.jpg` - Application icon/logo (window icon)
- `lyridanlogo.ico` - Application icon/logo (executable icon)
- `build.bat` - Automated build script (Windows)
- `create_icon.py` - Icon conversion utility (optional, used to generate .ico from .jpg)

### Prerequisites

Install the required Python packages:

```bash
pip install tkinterdnd2 pykakasi transliterate pyphen pyinstaller
```

### Building the Executable

#### Option 1: Use the build script (recommended)
Simply double-click `build.bat` or run:
```bash
build.bat
```

#### Option 2: Manual build
Run the PyInstaller command:
```bash
pyinstaller --noconfirm --onefile --windowed --clean --name "Lyridan" --icon="lyridanlogo.ico" --hidden-import=syllabize --hidden-import=config --add-data "English.txt;." --add-data "lyridanlogo.jpg;." --collect-all tkinterdnd2 --collect-all pykakasi --collect-all transliterate "gui.py"
```

### Output

The compiled executable will be located in:
- `dist/Lyridan.exe`

### Configuration File

Lyridan stores user preferences in:
- `%APPDATA%\Lyridan\options.lrdn`

This includes:
- Theme preference (Dark / Light / Lyridan Dark)
- Warning dialog acknowledgments



