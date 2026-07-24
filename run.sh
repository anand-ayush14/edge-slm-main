#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  TinyML · One-command launcher
#  Usage:  ./run.sh
# ─────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

echo ""
echo "  ⚡ TinyML RAG Pipeline"
echo "  ─────────────────────────────────────"

# ── 1. Check Python ──────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "  ✗ python3 not found. Please install Python 3.9+."
  exit 1
fi

PYTHON=python3

# ── 2. Ensure Streamlit UI dependency ────────────────────────
echo "  ► Checking UI dependencies…"
$PYTHON -c "import streamlit" 2>/dev/null || {
  echo "  ► Installing Streamlit…"
  $PYTHON -m pip install --quiet -r requirements.txt
}

# ── 3. Ensure splitter venv exists ───────────────────────────
SPLITTER_DIR="scripts/rag-document-splitter"
VENV_DIR="$SPLITTER_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "  ► Creating Python venv for document splitter…"
  $PYTHON -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --quiet -r "$SPLITTER_DIR/requirements.txt"
  echo "  ✔ Venv ready."
fi

# ── 4. Check RAG binary ───────────────────────────────────────
RAG_BIN="rag/build/Release/apps/rag_demo/rag_demo"
if [ ! -f "$RAG_BIN" ]; then
  echo ""
  echo "  ⚠  RAG binary not found at: $RAG_BIN"
  echo "     Build the project first:"
  echo "       cd rag"
  echo "       conan build . --build=missing"
  echo ""
  echo "  The UI will still open but embedding/chat steps will fail."
fi

# ── 5. Launch Streamlit UI ─────────────────────────────────────
echo "  ► Launching TinyML UI at http://localhost:8501 …"
echo ""
$PYTHON -m streamlit run app.py
