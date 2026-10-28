#!/usr/bin/env bash
# Build Lyridan.app and a DMG for the architecture of this Mac (Intel or Apple Silicon).
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller
VERSION="$(python3 tools/write_build_info.py "$@")"
python3 -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/lyridan.spec
case "$(uname -m)" in
  arm64) ARCH=AppleSilicon ;;
  *) ARCH=Intel ;;
esac
bash packaging/macos/make_dmg.sh "$VERSION" "$ARCH"
