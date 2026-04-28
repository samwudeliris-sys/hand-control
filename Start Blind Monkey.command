#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

ENV_FILE="$HOME/.hand-control.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

PORT="${PORT:-8000}"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
if [ ! -f ".venv/.installed" ] || [ requirements.txt -nt .venv/.installed ]; then
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -r requirements.txt
  touch .venv/.installed
fi

if lsof -ti "tcp:$PORT" >/dev/null 2>&1; then
  python scripts/print-qr.py --running
  printf '\nPress Return to close this window... '
  read -r _
  exit 0
fi

exec ./run.sh
