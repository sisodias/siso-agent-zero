#!/bin/zsh
# open-siso-base.sh — one gesture to open your JARVIS base in cmux.
# Drives the REAL cmux CLI (verified verbs) to lay out:
#   • a browser surface showing the Face (live brain dashboard, served by braind)
#   • a terminal surface running agent-zero (the one you talk to)
#
# cmux: socket /tmp/cmux.sock (CMUX_SOCKET_PATH), config ~/.config/cmux/cmux.json,
# automation.socketControlMode must allow socket control (Shaan's = allowAll).
#
# Usage:  open-siso-base.sh
set -e
FACE_URL="${SISO_FACE_URL:-https://shaans-mac-mini.tail100d11.ts.net:8831/}"
CMUX="${CMUX_BIN:-cmux}"

if ! command -v "$CMUX" >/dev/null 2>&1 || ! "$CMUX" ping >/dev/null 2>&1; then
  echo "cmux not reachable. Open the Face manually: $FACE_URL"
  echo "Then run 'agent-zero' in a terminal to talk to the brain."
  exit 0
fi

# New workspace whose first surface is a terminal running agent-zero.
WS=$("$CMUX" --json new-workspace --command "agent-zero" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('workspace','') if sys.stdin.isatty()==False else '')" 2>/dev/null || true)

# Rename it so it reads "SISO Base".
"$CMUX" rename-workspace --workspace "${WS:-workspace:1}" "SISO Base" 2>/dev/null || true

# Split a browser surface beside it, pointed at the live Face.
"$CMUX" new-split right --type browser --url "$FACE_URL" 2>/dev/null \
  || "$CMUX" new-pane --type browser --url "$FACE_URL" 2>/dev/null \
  || echo "  (open $FACE_URL in a cmux browser surface manually)"

# Friendly desktop notification.
"$CMUX" notify --title "SISO Base" --body "Face + agent-zero ready" 2>/dev/null || true

echo "SISO Base open: Face = $FACE_URL · agent-zero in the terminal surface."
