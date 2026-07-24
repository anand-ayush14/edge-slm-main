#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
#  TinyML — Docker Entrypoint
#  The UI is a headless Streamlit web app, so no display setup is needed.
# ══════════════════════════════════════════════════════════════════════
set -e

exec "$@"
