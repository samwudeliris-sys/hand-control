#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# --- Platform check ---------------------------------------------------------
if [[ "$(uname)" != "Darwin" ]]; then
  echo "Hand Control only runs on macOS. Detected: $(uname)" >&2
  exit 1
fi

# --- Python check -----------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.10+ from python.org or:" >&2
  echo "    brew install python" >&2
  exit 1
fi

PY_OK=$(python3 - <<'PY'
import sys
print("ok" if sys.version_info >= (3, 10) else "old")
PY
)
if [[ "$PY_OK" != "ok" ]]; then
  PY_VER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
  echo "Python 3.10+ required, found $PY_VER." >&2
  echo "Install a newer Python (e.g. 'brew install python')." >&2
  exit 1
fi

# --- Virtualenv + deps ------------------------------------------------------
if [ ! -d ".venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f ".venv/.installed" ] || [ requirements.txt -nt .venv/.installed ]; then
  echo "Installing dependencies..."
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
  touch .venv/.installed
fi

# --- Run --------------------------------------------------------------------
exec python -m server.main
