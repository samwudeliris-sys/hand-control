#!/usr/bin/env bash
# Verify the local Blind Monkey / Hand Control server is healthy.
# Exits 0 if /health is OK and Accessibility is granted to the *server* process.
# Usage:  ./scripts/verify-blind-monkey.sh
#         STRICT=1  also require at least one Cursor window (fails if Cursor is closed)

set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
URL="https://127.0.0.1:${PORT}/health"

if ! curl -fsSk --max-time 4 "$URL" | python3 -c "
import json, os, sys
d = json.load(sys.stdin)
if not d.get('ok'):
    print('verify: /health not ok', d, file=sys.stderr)
    sys.exit(1)
ax = d.get('accessibility') or {}
if ax.get('trusted') is not True:
    py = (d.get('process') or {}).get('python')
    print('verify: FAIL — server Python is not in Accessibility. Enable:', py, file=sys.stderr)
    sys.exit(1)
n = int(d.get('windows_count', 0))
if os.environ.get('STRICT', '').strip().lower() in ('1', 'true', 'yes') and n < 1:
    print('verify: STRICT: expected at least one Cursor window, got', n, file=sys.stderr)
    sys.exit(1)
lerr = d.get('list_windows_error')
if lerr and n < 1:
    print('verify: note (list_windows):', lerr, file=sys.stderr)
print('verify: ok — accessibility=trusted windows=%d python=%s' % (
    n, (d.get('process') or {}).get('python', '?')
))
"; then
  exit 1
fi
