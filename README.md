# Lyridan - Build Instructions

This folder contains all files needed to build Lyridan into a single executable.

## Required Files

- `gui.py` - Main GUI application
- `syllabize.py` - Core syllabization and Rocksmith export logic
- `config.py` - Configuration management (persistent settings)
- `English.txt` - English syllabification dictionary (47,737 words)
- `build.bat` - Automated build script (Windows)

## Prerequisites

Install the required Python packages:

```bash
pip install tkinterdnd2 pykakasi transliterate pyphen pyinstaller
```

## Building the Executable

### Option 1: Use the build script (recommended)
Simply double-click `build.bat` or run:
```bash
build.bat
```

### Option 2: Manual build
Run the PyInstaller command:
```bash
pyinstaller --noconfirm --onefile --windowed --clean --name "Lyridan" --hidden-import=syllabize --hidden-import=config --add-data "English.txt;." --collect-all tkinterdnd2 --collect-all pykakasi --collect-all transliterate "gui.py"
```

## Output

The compiled executable will be located in:
- `dist/Lyridan.exe`

## Configuration File

Lyridan stores user preferences in:
- `%APPDATA%\Lyridan\options.lrdn`

This includes:
- Theme preference (Dark/Light)
- Warning dialog acknowledgments
