#!/usr/bin/env bash
#
# Template pipeline for notarizing a signed Mac build (Developer ID).
# Fill in your Apple Developer credentials and app paths before use.
#
# Prerequisite: "Developer ID Application" cert in your keychain,
# and an app already built (e.g. from Xcode or scripts/build-app.sh
# with signing enabled — today the launcher script is unsigned).
#
set -euo pipefail

: "${CODESIGN_IDENTITY:=Developer ID Application: YOUR NAME (TEAMID)}"
APP_PATH="${1:?Usage: $0 /path/To/Blind Monkey.app}"
ZIP_PATH="${2:-/tmp/BlindMonkey-for-notarization.zip}"

xcrun notarytool store-credentials "blindmonkey-notary" \
  --apple-id "${APPLE_ID:?}" \
  --team-id "${APPLE_TEAM_ID:?}" \
  --password "${NOTARY_APP_PASSWORD:?}" 2>/dev/null || true

ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

xcrun notarytool submit "$ZIP_PATH" \
  --keychain-profile "blindmonkey-notary" \
  --wait

xcrun stapler staple "$APP_PATH"

echo "Stapled and ready: $APP_PATH"
