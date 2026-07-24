#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  TinyML — Raspberry Pi Uninstaller
#  Removes desktop shortcuts and launcher. Does NOT delete models or binaries.
#  Run:  bash uninstall.sh
# ══════════════════════════════════════════════════════════════════════════════
set -e

G="\033[0;32m"; Y="\033[0;33m"; R="\033[0;31m"; C="\033[0;36m"; N="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${C}  ⚡ TinyML — Uninstaller${N}"
echo ""

remove() {
  local f="$1"
  if [ -f "$f" ] || [ -L "$f" ]; then
    rm -f "$f"
    echo -e "${G}  ✔ Removed: $f${N}"
  fi
}

remove "$HOME/.local/share/applications/tinyml.desktop"
remove "$HOME/Desktop/TinyML.desktop"
remove "$SCRIPT_DIR/launch.sh"

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo ""
echo -e "${Y}  Models and RAG binary are kept intact.${N}"
echo -e "${Y}  To fully remove everything, delete the project folder:${N}"
echo -e "    rm -rf $(dirname "$SCRIPT_DIR")"
echo ""
echo -e "${G}  Done.${N}"
echo ""
