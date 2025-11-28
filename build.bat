@echo off
echo ================================
echo Lyridan Build Script
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

pyinstaller --noconfirm --onefile --windowed --clean --name "Lyridan" --icon="lyridanlogo.ico" --hidden-import=syllabize --hidden-import=config --add-data "English.txt;." --add-data "lyridanlogo.jpg;." --collect-all tkinterdnd2 --collect-all pykakasi --collect-all transliterate "gui.py"

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
