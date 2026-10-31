@echo off
REM Build Lyridan for Windows: PyInstaller app folder + Inno Setup installer.
REM Needs Python 3.11+ and (for the installer) Inno Setup 6 (iscc on PATH).
setlocal
cd /d "%~dp0"
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt pyinstaller || goto :error
REM Pass --channel stable for a release build (default: dev, with detailed build info)
for /f "delims=" %%v in ('python tools\write_build_info.py %*') do set LYRIDAN_VERSION=%%v
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\lyridan.spec || goto :error
where iscc >nul 2>nul
if %errorlevel%==0 (
  iscc /DAppVersion=%LYRIDAN_VERSION% packaging\windows\lyridan.iss || goto :error
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DAppVersion=%LYRIDAN_VERSION% packaging\windows\lyridan.iss || goto :error
) else (
  echo Inno Setup not found - skipping installer. The app is in dist\Lyridan\
)
echo Done. Output in dist\
exit /b 0
:error
echo Build failed.
exit /b 1
