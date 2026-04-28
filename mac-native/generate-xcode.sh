#!/usr/bin/env bash
# Generate BlindMonkeyMac.xcodeproj with XcodeGen (brew install xcodegen).
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v xcodegen >/dev/null 2>&1; then
  echo "Install XcodeGen: brew install xcodegen" >&2
  exit 1
fi
xcodegen generate --spec project.yml
echo "Open BlindMonkeyMac.xcodeproj in Xcode"
