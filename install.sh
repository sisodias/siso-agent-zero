#!/bin/zsh
set -euo pipefail

SOURCE_ROOT="${0:A:h}"
INSTALL_ROOT="${SISO_AGENT_ZERO_HOME:-$HOME/.local/share/siso-agent-zero}"
BIN_DIR="${SISO_BIN_DIR:-$HOME/.local/bin}"

if [[ -e "$INSTALL_ROOT" ]]; then
  echo "Install target already exists: $INSTALL_ROOT" >&2
  echo "Run uninstall.sh first or choose a different SISO_AGENT_ZERO_HOME." >&2
  exit 1
fi

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"
for item in bin src config adapters docs README.md LICENSE PROVENANCE.md MIGRATION-MAP.json; do
  cp -R "$SOURCE_ROOT/$item" "$INSTALL_ROOT/$item"
done

cat > "$INSTALL_ROOT/.siso-agent-zero-install.json" <<'JSON'
{"package":"siso-agent-zero","contract_version":"1"}
JSON

link="$BIN_DIR/siso-agent-zero"
if [[ -e "$link" || -L "$link" ]]; then
  echo "Executable target already exists: $link" >&2
  echo "The package was copied but no executable link was changed." >&2
  exit 1
fi
ln -s "$INSTALL_ROOT/bin/siso-agent-zero" "$link"
echo "Installed SISO Agent Zero: $link"
