#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  Edge SLM — Raspberry Pi Installer
#  Run once on your Pi:  bash install.sh
# ══════════════════════════════════════════════════════════════════════════════
set -e

# ── Colours ───────────────────────────────────────────────────────────────────
R="\033[0;31m"; G="\033[0;32m"; Y="\033[0;33m"; B="\033[0;34m"
C="\033[0;36m"; W="\033[1;37m"; N="\033[0m"

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RAG_DIR="$PROJECT_DIR/rag"
SPLITTER_DIR="$PROJECT_DIR/scripts/rag-document-splitter"
MODELS_DIR="$PROJECT_DIR/models"
PI_SCRIPT="$SCRIPT_DIR/edge-slm-pi.py"
DESKTOP_FILE="$SCRIPT_DIR/edge-slm.desktop"
ICON_FILE="$SCRIPT_DIR/icon.png"
APP_DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"
WRAPPER="$SCRIPT_DIR/launch.sh"

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${C}  ╔══════════════════════════════════════════╗${N}"
echo -e "${C}  ║      ⚡  Edge SLM  ·  Pi Installer       ║${N}"
echo -e "${C}  ╚══════════════════════════════════════════╝${N}"
echo ""

# ── 1. Detect Raspberry Pi ────────────────────────────────────────────────────
echo -e "${B}[1/8]${N} Checking hardware…"
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" && "$ARCH" != "armv7l" && "$ARCH" != "armv6l" ]]; then
  echo -e "${Y}  ⚠  This script targets ARM (Raspberry Pi). Detected: $ARCH${N}"
  read -rp "  Continue anyway? [y/N] " cont
  [[ "$cont" =~ ^[Yy]$ ]] || exit 1
fi

# RAM check
TOTAL_RAM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
TOTAL_RAM_MB=$((TOTAL_RAM_KB / 1024))
echo -e "  RAM: ${W}${TOTAL_RAM_MB} MB${N}"
if (( TOTAL_RAM_MB < 1800 )); then
  echo -e "${Y}  ⚠  Low RAM detected (${TOTAL_RAM_MB} MB). TinyLlama needs ~1 GB free.${N}"
  echo -e "${Y}     We'll configure a swap file automatically.${N}"
  NEED_SWAP=true
else
  NEED_SWAP=false
fi
echo -e "${G}  ✔ Hardware check OK${N}"

# ── 2. System packages ────────────────────────────────────────────────────────
echo ""
echo -e "${B}[2/8]${N} Installing system packages…"
echo -e "  ${Y}(sudo required for apt)${N}"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  python3 python3-pip python3-tk python3-venv \
  cmake git build-essential \
  libopenblas-dev liblapack-dev \
  curl wget ca-certificates 2>&1 | grep -E "^(Setting|Unpacking|Get:|Err)" || true
echo -e "${G}  ✔ System packages ready${N}"

# ── 3. Conan ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${B}[3/8]${N} Checking Conan package manager…"
if ! command -v conan &>/dev/null; then
  echo "  Installing Conan via pip…"
  pip3 install --user conan 2>&1 | tail -3
  # Add ~/.local/bin to PATH for this session
  export PATH="$HOME/.local/bin:$PATH"
fi
CONAN_VER=$(conan --version 2>/dev/null | head -1 || echo "unknown")
echo -e "${G}  ✔ $CONAN_VER${N}"

# Initialise conan default profile if needed
if [ ! -f "$HOME/.conan2/profiles/default" ]; then
  echo "  Detecting default Conan profile…"
  conan profile detect --force 2>&1 | tail -3
fi

# ── 4. Swap (if low RAM) ──────────────────────────────────────────────────────
if [ "$NEED_SWAP" = true ]; then
  echo ""
  echo -e "${B}[4/8]${N} Configuring swap file (2 GB)…"
  if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
    echo -e "${G}  ✔ 2 GB swap created and enabled${N}"
  else
    echo -e "${G}  ✔ Swap already exists${N}"
  fi
else
  echo ""
  echo -e "${B}[4/8]${N} Swap — ${G}not needed (sufficient RAM)${N}"
fi

# ── 5. Build RAG binary ───────────────────────────────────────────────────────
echo ""
echo -e "${B}[5/8]${N} Building RAG binary for ARM…"
RAG_BIN="$RAG_DIR/build/Release/apps/rag_demo/rag_demo"
if [ -f "$RAG_BIN" ]; then
  echo -e "${G}  ✔ Binary already built: $RAG_BIN${N}"
else
  echo -e "  ${Y}This may take 10–20 minutes. Go grab a coffee ☕${N}"
  cd "$RAG_DIR"
  # Install any conan recipes in the conan/ folder
  CONAN_RECIPES_DIR="$RAG_DIR/../rag/conan"
  if [ -d "$CONAN_RECIPES_DIR" ]; then
    for recipe in "$CONAN_RECIPES_DIR"/*/; do
      if [ -f "$recipe/conanfile.py" ]; then
        echo "  → Installing local recipe: $(basename "$recipe")"
        conan create "$recipe" --profile=default 2>&1 | tail -2 || true
      fi
    done
  fi
  conan build . --profile=default --build=missing 2>&1 | \
    grep -E "(Installing|Building|CMake|Error|error|Done|Finished)" || true
  cd "$SCRIPT_DIR"
  if [ -f "$RAG_BIN" ]; then
    echo -e "${G}  ✔ RAG binary built successfully${N}"
  else
    echo -e "${R}  ✗ Build failed — see output above.${N}"
    echo -e "  You can retry manually:"
    echo -e "    cd $RAG_DIR && conan build . --build=missing"
    echo ""
    echo -e "  ${Y}Continuing installer — UI will open but embedding/chat won't work until binary is built.${N}"
  fi
fi

# ── 6. Python venv for document splitter ─────────────────────────────────────
echo ""
echo -e "${B}[6/8]${N} Setting up Python venv for document splitter…"
VENV_DIR="$SPLITTER_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --quiet -r "$SPLITTER_DIR/requirements.txt"
  echo -e "${G}  ✔ Venv created${N}"
else
  echo -e "${G}  ✔ Venv already exists${N}"
fi

# ── 7. Check model files ──────────────────────────────────────────────────────
echo ""
echo -e "${B}[7/8]${N} Checking model files…"
TINY_LLAMA="$MODELS_DIR/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
NOMIC_EMBED="$MODELS_DIR/nomic-embed-text-v1.f32.gguf"
MISSING_MODELS=false

if [ -f "$TINY_LLAMA" ]; then
  SIZE=$(du -sh "$TINY_LLAMA" | cut -f1)
  echo -e "${G}  ✔ TinyLlama 1.1B Q4_K_M  ($SIZE)${N}"
else
  echo -e "${R}  ✗ TinyLlama not found: $TINY_LLAMA${N}"
  MISSING_MODELS=true
fi

if [ -f "$NOMIC_EMBED" ]; then
  SIZE=$(du -sh "$NOMIC_EMBED" | cut -f1)
  echo -e "${G}  ✔ nomic-embed-text-v1 F32 ($SIZE)${N}"
else
  echo -e "${R}  ✗ Embedding model not found: $NOMIC_EMBED${N}"
  MISSING_MODELS=true
fi

if [ "$MISSING_MODELS" = true ]; then
  echo ""
  echo -e "${Y}  ⚠  Some model files are missing.${N}"
  echo -e "  Copy the models/ folder from your Mac to the Pi:"
  echo -e "    ${W}scp -r models/ pi@<pi-hostname>:~/edge-slm-main/${N}"
fi

# ── 8. Desktop integration ────────────────────────────────────────────────────
echo ""
echo -e "${B}[8/8]${N} Creating desktop launcher…"

# Generate launch wrapper
cat > "$WRAPPER" << LAUNCHER
#!/usr/bin/env bash
# Edge SLM launcher — generated by install.sh
export PATH="\$HOME/.local/bin:\$PATH"
cd "$PROJECT_DIR"
python3 "$PI_SCRIPT"
LAUNCHER
chmod +x "$WRAPPER"

# Update .desktop file with real paths
mkdir -p "$APP_DESKTOP_DIR"
sed "s|EXEC_PATH|$WRAPPER|g; s|ICON_PATH|$ICON_FILE|g; s|PROJECT_PATH|$PROJECT_DIR|g" \
  "$DESKTOP_FILE" > "$APP_DESKTOP_DIR/edge-slm.desktop"
chmod +x "$APP_DESKTOP_DIR/edge-slm.desktop"

# Copy to Desktop if it exists
if [ -d "$DESKTOP_DIR" ]; then
  cp "$APP_DESKTOP_DIR/edge-slm.desktop" "$DESKTOP_DIR/Edge SLM.desktop"
  chmod +x "$DESKTOP_DIR/Edge SLM.desktop"
  echo -e "${G}  ✔ Desktop shortcut created${N}"
fi

# Refresh app menu
update-desktop-database "$APP_DESKTOP_DIR" 2>/dev/null || true
echo -e "${G}  ✔ App menu entry created${N}"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${C}  ╔══════════════════════════════════════════╗${N}"
echo -e "${C}  ║         ✅  Installation complete!        ║${N}"
echo -e "${C}  ╚══════════════════════════════════════════╝${N}"
echo ""
echo -e "  Launch the app:"
echo -e "    ${W}• Double-click 'Edge SLM' on your Desktop${N}"
echo -e "    ${W}• Or: bash $WRAPPER${N}"
echo -e "    ${W}• Or: python3 $PI_SCRIPT${N}"
echo ""
echo -e "  ${Y}First run: Use 'Run Full Pipeline' to chunk, embed, then chat.${N}"
echo ""
