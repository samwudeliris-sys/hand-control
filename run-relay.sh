#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

ENV_FILE="$HOME/.hand-control.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

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

exec python -m relay.main
