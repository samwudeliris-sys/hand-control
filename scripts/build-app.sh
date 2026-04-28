#!/bin/bash
#
# Build a double-clickable Mac app bundle for Blind Monkey.
#
# The app is a small native Cocoa host that runs ``./run.sh`` from
# this repo in the background, captures logs, and exposes basic
# start/stop/link actions without opening Terminal.app.
#
# The bundle is installed to ``~/Applications/`` (no sudo needed)
# and registered with Launch Services so Spotlight picks it up
# immediately. Rerun this script anytime to rebuild — it's
# idempotent.
#
# Usage:
#   ./scripts/build-app.sh                # install to ~/Applications
#   ./scripts/build-app.sh /Applications  # install to /Applications (needs write access)

set -euo pipefail

cd "$(dirname "$0")/.."
REPO_DIR="$(pwd)"
APP_NAME="Blind Monkey"
INSTALL_PARENT="${1:-$HOME/Applications}"
APP_DIR="$INSTALL_PARENT/$APP_NAME.app"

mkdir -p "$INSTALL_PARENT"

echo "Building $APP_DIR"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

if ! command -v swiftc >/dev/null 2>&1; then
  echo "swiftc not found. Install Xcode Command Line Tools first:" >&2
  echo "  xcode-select --install" >&2
  exit 1
fi

# --- Info.plist ---------------------------------------------------------

cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>               <string>Blind Monkey</string>
  <key>CFBundleDisplayName</key>        <string>Blind Monkey</string>
  <key>CFBundleIdentifier</key>         <string>com.blindmonkey.launcher</string>
  <key>CFBundleVersion</key>            <string>1.0</string>
  <key>CFBundleShortVersionString</key> <string>1.0</string>
  <key>CFBundlePackageType</key>        <string>APPL</string>
  <key>CFBundleExecutable</key>         <string>launcher</string>
  <key>CFBundleIconFile</key>           <string>AppIcon</string>
  <key>LSApplicationCategoryType</key>  <string>public.app-category.utilities</string>
  <key>NSHighResolutionCapable</key>    <true/>
  <key>LSMinimumSystemVersion</key>     <string>11.0</string>
  <key>BMRepoDir</key>                  <string>__BM_REPO_DIR__</string>
</dict>
</plist>
PLIST
python3 - "$APP_DIR/Contents/Info.plist" "$REPO_DIR" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
repo = sys.argv[2]
path.write_text(path.read_text().replace("__BM_REPO_DIR__", repo))
PY

# --- Native launcher executable ---------------------------------------

swiftc \
  "$REPO_DIR/mac-companion/BlindMonkeyCompanion.swift" \
  -framework Cocoa \
  -o "$APP_DIR/Contents/MacOS/launcher"
chmod +x "$APP_DIR/Contents/MacOS/launcher"
echo "  ✓ native launcher compiled"

# --- App icon -----------------------------------------------------------
#
# Build an .icns from the PWA icon so Launchpad / Dock / Spotlight
# all show the same mark as the phone app. ``sips`` and ``iconutil``
# are preinstalled on macOS — no Homebrew needed.

SRC_ICON="$REPO_DIR/phone/icon-512.png"
if [ -f "$SRC_ICON" ] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  ICONSET_PARENT="$(mktemp -d)"
  ICONSET="$ICONSET_PARENT/AppIcon.iconset"
  mkdir -p "$ICONSET"

  sips -z 16 16     "$SRC_ICON" --out "$ICONSET/icon_16x16.png"         >/dev/null
  sips -z 32 32     "$SRC_ICON" --out "$ICONSET/icon_16x16@2x.png"      >/dev/null
  sips -z 32 32     "$SRC_ICON" --out "$ICONSET/icon_32x32.png"         >/dev/null
  sips -z 64 64     "$SRC_ICON" --out "$ICONSET/icon_32x32@2x.png"      >/dev/null
  sips -z 128 128   "$SRC_ICON" --out "$ICONSET/icon_128x128.png"       >/dev/null
  sips -z 256 256   "$SRC_ICON" --out "$ICONSET/icon_128x128@2x.png"    >/dev/null
  sips -z 256 256   "$SRC_ICON" --out "$ICONSET/icon_256x256.png"       >/dev/null
  sips -z 512 512   "$SRC_ICON" --out "$ICONSET/icon_256x256@2x.png"    >/dev/null
  sips -z 512 512   "$SRC_ICON" --out "$ICONSET/icon_512x512.png"       >/dev/null
  # The 512@2x slot ideally wants 1024px. sips upscales cleanly
  # enough for a launcher icon — not pixel-perfect but looks fine.
  sips -z 1024 1024 "$SRC_ICON" --out "$ICONSET/icon_512x512@2x.png"    >/dev/null

  iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/AppIcon.icns"
  rm -rf "$ICONSET_PARENT"
  echo "  ✓ icon baked"
else
  echo "  · skipping icon (source or tools missing — app will use default Mac icon)"
fi

# --- Register with Launch Services --------------------------------------
#
# Makes Spotlight, Launchpad, and "Open With" see the app right away
# without requiring a logout. If lsregister isn't at its usual path
# for some reason, we just warn — the app still works, it just might
# take a minute to show up in Spotlight.

LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
if [ -x "$LSREGISTER" ]; then
  "$LSREGISTER" -f "$APP_DIR" >/dev/null 2>&1 || true
  echo "  ✓ registered with Launch Services"
fi

cat <<NEXT

Built: $APP_DIR

To launch:
  • Open Launchpad and click "Blind Monkey", or
  • Cmd+Space and type "Blind Monkey", or
  • Drag the app into your Dock for one-click access.

NEXT
