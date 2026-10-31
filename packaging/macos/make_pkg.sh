#!/usr/bin/env bash
# Package dist/Lyridan.app into a macOS installer (.pkg) that installs to /Applications.
# Usage: packaging/macos/make_pkg.sh <version-label> <arch-label>   (e.g. 2.0.0-dev.42 Intel)
set -euo pipefail
LABEL="${1:-2.0.1}"
ARCH="${2:-$(uname -m)}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT/dist/Lyridan.app"
OUT="$ROOT/dist/Lyridan-${LABEL}-macOS-${ARCH}-Installer.pkg"
NUMERIC="$(echo "$LABEL" | sed -E 's/^([0-9]+\.[0-9]+\.[0-9]+).*/\1/')"
WORK="$(mktemp -d)"

[ -d "$APP" ] || { echo "missing $APP - run pyinstaller first"; exit 1; }
codesign --force --deep --sign - "$APP"

mkdir -p "$WORK/root/Applications"
cp -R "$APP" "$WORK/root/Applications/"
# Always install into /Applications (do not "relocate" to an older copy elsewhere on disk)
pkgbuild --analyze --root "$WORK/root" "$WORK/component.plist"
plutil -replace 0.BundleIsRelocatable -bool NO "$WORK/component.plist"
pkgbuild --root "$WORK/root" --component-plist "$WORK/component.plist" \
         --identifier com.elevatorisbest.lyridan --version "$NUMERIC" \
         --install-location / "$WORK/Lyridan-component.pkg"
productbuild --package "$WORK/Lyridan-component.pkg" "$OUT"
rm -rf "$WORK"
echo "created $OUT"
