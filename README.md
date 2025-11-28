# Lyridan

A multilingual syllabization tool for LRC lyrics files and Rocksmith vocal XML creator.

## Features

- **LRC Syllabizer**: Romanize and syllabize Japanese, Russian, and English lyrics
- **Rocksmith Creator**: Generate Rocksmith-compatible vocal XML files from TTML lyrics
- **Theme Support**: Dark and Light themes
- **Persistent Settings**: Config file stored in AppData

## Building from Source

### Prerequisites

1. Python 3.8 or newer
2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Build Instructions

#### Windows (PowerShell)
```powershell
.\build.ps1
```

#### Manual Build
```bash
pyinstaller --noconfirm --onefile --windowed --clean --name "Lyridan" --hidden-import=syllabize --hidden-import=config --add-data "English.txt;." --collect-all tkinterdnd2 --collect-all pykakasi --collect-all transliterate gui.py
```

The compiled executable will be in the `dist` folder.

## Project Structure

```
Lyridan_Build/
├── gui.py           # Main GUI application
├── syllabize.py     # Syllabization logic (Japanese, Russian, English)
├── config.py        # Configuration management
├── English.txt      # English syllabification dictionary (47,737 words)
├── requirements.txt # Python dependencies
├── build.ps1        # Build script
└── README.md        # This file
```

## Files Description

- **gui.py**: Main application entry point with tkinter GUI
- **syllabize.py**: Core syllabization algorithms for multiple languages
- **config.py**: Manages persistent settings in `options.lrdn` file
- **English.txt**: Dictionary for English word syllabification

## Dependencies

- `tkinterdnd2`: Drag-and-drop support
- `pykakasi`: Japanese romanization
- `transliterate`: Russian transliteration
- `pyphen`: English syllabification (backup)
- `pyinstaller`: Executable compilation

## Config File Location

Settings are stored in:
- Windows: `%APPDATA%\Lyridan\options.lrdn`
- Linux/Mac: `~/.lyridan/options.lrdn`

## License

Created by Elevatorisbest, 2025
