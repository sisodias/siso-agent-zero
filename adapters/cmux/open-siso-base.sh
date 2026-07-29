#!/bin/zsh
set -euo pipefail

FACE_URL="${SISO_FACE_URL:-}"
CMUX="${CMUX_BIN:-cmux}"
AGENT_ZERO="${SISO_AGENT_ZERO_BIN:-siso-agent-zero}"

if ! command -v "$CMUX" >/dev/null 2>&1 || ! "$CMUX" ping >/dev/null 2>&1; then
  echo "cmux is not reachable; run $AGENT_ZERO in a terminal."
  [[ -n "$FACE_URL" ]] && echo "Open the configured Agent Brain face manually: $FACE_URL"
  exit 0
fi

workspace_json=$("$CMUX" --json new-workspace --command "$AGENT_ZERO" 2>/dev/null || true)
workspace=$(print -r -- "$workspace_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("workspace", ""))' 2>/dev/null || true)
"$CMUX" rename-workspace --workspace "${workspace:-workspace:1}" "SISO Base" 2>/dev/null || true

if [[ -n "$FACE_URL" ]]; then
  "$CMUX" new-split right --type browser --url "$FACE_URL" 2>/dev/null \
    || "$CMUX" new-pane --type browser --url "$FACE_URL" 2>/dev/null \
    || echo "Open $FACE_URL in a browser surface manually."
fi

"$CMUX" notify --title "SISO Base" --body "Agent Zero ready" 2>/dev/null || true
echo "SISO Base open."
