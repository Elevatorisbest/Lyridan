# Lyridan
![lyridanlogo](https://github.com/user-attachments/assets/335da193-0a28-4bf8-8848-3dcc610e3332)
<img width="1000" height="700" alt="Example of lrc romanization and syllabization" src="https://github.com/user-attachments/assets/3d72db12-5c38-403e-8180-08ceb62d1e27" />




## What is it?
Lyridan is an experimental program that syllabizes and romanizes/transliterates .lrc lyric files. 

It also lets you generate roughly aligned and syllabized Rocksmith Vocal .XML arrangement files ready to be imported into a chart and game from a .ttml file (acquired from ex. Apple Music).

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

#### 1. Ensure that you have Python installed on your PC (Python 3.8 at minimum).
#### 2. Download the newest release of Lyridan from the Releases page of this repository.
#### 3. Place Lyridan.exe where you wish to use it (eg. Downloads folder, Desktop, etc.)
#### 4. Launch the executable.

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
pip install requirements.txt
```
or

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

## Disclaimer

I wrote this program using Google's newly released Antigravity IDE, where I generated basically all of the code using AI, because I unfortunately have next to no coding skills. I at no point claim that I am good at coding, and while I did my best to find and fix any bugs or oddities, they can still occur. Any help or contributions to improve the program via pull requests are very welcome and I will be very thankful for them if you choose to contribute to it.

This also means that this program is to be used merely as an assistance tool or an experiment when creating a Rocksmith chart, and is not meant to fully automate or replace the process of adding high quality lyrics to the chart.

## Credits

This program uses english language syllabization table (```English.txt```) taken from Ultra Star Creator github repository (https://github.com/UltraStar-Deluxe/UltraStar-Creator) for the purposes of syllabizing English .lrc lyric files. This repository therefore also uses a GPL-2.0 license.
