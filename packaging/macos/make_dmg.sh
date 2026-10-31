#!/usr/bin/env bash
# Package dist/Lyridan.app into a drag-to-Applications DMG.
# Usage: packaging/macos/make_dmg.sh <version> <arch-label>   (e.g. 2.0.0 AppleSilicon)
set -euo pipefail
VERSION="${1:-2.0.0}"
ARCH="${2:-$(uname -m)}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT/dist/Lyridan.app"
OUT="$ROOT/dist/Lyridan-${VERSION}-macOS-${ARCH}.dmg"
STAGE="$(mktemp -d)"

[ -d "$APP" ] || { echo "missing $APP - run pyinstaller first"; exit 1; }

# Ad-hoc signature so the app runs on Apple Silicon (no paid Developer ID needed).
codesign --force --deep --sign - "$APP"

cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/If the app does not open.txt" <<TXT
Lyridan is not notarized by Apple. If macOS says it is damaged or from an
unidentified developer, open Terminal and run:

    xattr -cr /Applications/Lyridan.app

then open Lyridan again (or right-click the app > Open).
TXT
rm -f "$OUT"
hdiutil create -volname "Lyridan ${VERSION}" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
rm -rf "$STAGE"
echo "created $OUT"
