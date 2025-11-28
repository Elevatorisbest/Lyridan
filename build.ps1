# Lyridan Build Script
# This script compiles Lyridan into a single executable

Write-Host "Building Lyridan..." -ForegroundColor Cyan

# Clean previous build artifacts
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "*.spec") { Remove-Item -Force "*.spec" }

# Run PyInstaller
pyinstaller --noconfirm --onefile --windowed --clean --name "Lyridan" `
    --hidden-import=syllabize `
    --hidden-import=config `
    --add-data "English.txt;." `
    --collect-all tkinterdnd2 `
    --collect-all pykakasi `
    --collect-all transliterate `
    "gui.py"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild successful! Executable is located in the 'dist' folder." -ForegroundColor Green
    Write-Host "Location: $(Get-Location)\dist\Lyridan.exe" -ForegroundColor Yellow
} else {
    Write-Host "`nBuild failed!" -ForegroundColor Red
}
