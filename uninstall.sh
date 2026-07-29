#!/bin/zsh
set -euo pipefail

INSTALL_ROOT="${SISO_AGENT_ZERO_HOME:-$HOME/.local/share/siso-agent-zero}"
BIN_DIR="${SISO_BIN_DIR:-$HOME/.local/bin}"
MARKER="$INSTALL_ROOT/.siso-agent-zero-install.json"
link="$BIN_DIR/siso-agent-zero"

case "$INSTALL_ROOT" in
  ""|/|"$HOME"|"$HOME/")
    echo "Refusing unsafe install target: $INSTALL_ROOT" >&2
    exit 1
    ;;
esac

if [[ ! -f "$MARKER" ]] || ! grep -q '"package":"siso-agent-zero"' "$MARKER"; then
  echo "Refusing to remove unmarked target: $INSTALL_ROOT" >&2
  exit 1
fi

if [[ -L "$link" && "$(readlink "$link")" == "$INSTALL_ROOT/bin/siso-agent-zero" ]]; then
  rm "$link"
fi
rm -rf -- "$INSTALL_ROOT"
echo "Uninstalled SISO Agent Zero."
