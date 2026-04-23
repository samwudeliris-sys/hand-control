#!/bin/bash
#
# Build a double-clickable Mac app bundle for Hand Control.
#
# The app is a thin wrapper: its executable opens Terminal.app via
# osascript and runs ``./run.sh`` from this repo. That keeps the
# banner/QR code visible (helpful on first launch) and means "close
# Terminal" = "stop the server" — the metaphor Mac users expect.
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
APP_NAME="Hand Control"
INSTALL_PARENT="${1:-$HOME/Applications}"
APP_DIR="$INSTALL_PARENT/$APP_NAME.app"

mkdir -p "$INSTALL_PARENT"

echo "Building $APP_DIR"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# --- Info.plist ---------------------------------------------------------

cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>               <string>Hand Control</string>
  <key>CFBundleDisplayName</key>        <string>Hand Control</string>
  <key>CFBundleIdentifier</key>         <string>com.handcontrol.launcher</string>
  <key>CFBundleVersion</key>            <string>1.0</string>
  <key>CFBundleShortVersionString</key> <string>1.0</string>
  <key>CFBundlePackageType</key>        <string>APPL</string>
  <key>CFBundleExecutable</key>         <string>launcher</string>
  <key>CFBundleIconFile</key>           <string>AppIcon</string>
  <key>LSApplicationCategoryType</key>  <string>public.app-category.utilities</string>
  <key>NSHighResolutionCapable</key>    <true/>
  <key>LSMinimumSystemVersion</key>     <string>11.0</string>
</dict>
</plist>
PLIST

# --- Launcher script (Contents/MacOS/launcher) --------------------------
#
# Two behaviors:
#   • Port 8000 free:  open a new Terminal tab running ``./run.sh``
#   • Port in use:     assume Hand Control is already running and just
#                      bring Terminal to the foreground, so the user
#                      sees the logs / QR instead of a crash-on-reboot.
#
# We bake REPO_DIR in at build time. If the user moves the repo,
# they should rerun this script to rebuild the app.
#
# Outer heredoc is UNquoted so $REPO_DIR is substituted once at
# build time. Shell-variable references that should survive until
# run time (like $PATH) are backslash-escaped.

cat > "$APP_DIR/Contents/MacOS/launcher" <<LAUNCHER
#!/bin/bash
REPO_DIR='$REPO_DIR'
export PATH="/usr/local/bin:/opt/homebrew/bin:\$PATH"

if lsof -ti :8000 >/dev/null 2>&1; then
  # Already running — just surface Terminal.
  osascript -e 'tell application "Terminal" to activate' || true
  exit 0
fi

# Fresh launch: open a new Terminal window running run.sh inside the
# repo. Single-quoted path inside the AppleScript do-script handles
# the space in "Hand control".
osascript <<OSA
tell application "Terminal"
  activate
  do script "cd '\$REPO_DIR' && ./run.sh"
end tell
OSA
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/launcher"
echo "  ✓ launcher installed"

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
  • Open Launchpad and click "Hand Control", or
  • Cmd+Space and type "Hand Control", or
  • Drag the app into your Dock for one-click access.

NEXT
