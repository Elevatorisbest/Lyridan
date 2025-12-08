@echo off
echo ================================
echo Starting Lyridan Windows Build
echo ================================
echo.

echo Checking for PyInstaller...
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
) else (
    echo PyInstaller is installed.
)
echo.

echo Building Lyridan.exe...
echo.

pyinstaller --noconfirm --onefile --windowed --clean --name "Lyridan" --icon="lyridanlogo.ico" --hidden-import=syllabize --hidden-import=config --hidden-import=nlp_manager --add-data "English.txt;." --add-data "lyridanlogo.ico;." --collect-all tkinterdnd2 --collect-all pykakasi --collect-all transliterate --collect-all cutlet --collect-all sudachipy --collect-all sudachidict_full --collect-all g2p_en --collect-all torch --collect-all transformers --collect-all unidic_lite --collect-all fugashi "gui.py"

echo.
if %errorlevel% equ 0 (
    echo ================================
    echo Build successful!
    echo Executable location: dist\Lyridan.exe
    echo ================================
) else (
    echo ================================
    echo Build failed! Check the errors above.
    echo ================================
)

pause

