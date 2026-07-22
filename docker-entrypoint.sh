#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
#  Edge SLM — Docker Entrypoint
#  Handles display setup automatically:
#    • If DISPLAY is already set (physical screen / X11 forwarding) → use it
#    • Otherwise → start Xvfb on :99 (headless / SSH usage)
# ══════════════════════════════════════════════════════════════════════
set -e

# If no display is configured, start a virtual framebuffer
if [ -z "$DISPLAY" ]; then
    echo "[entrypoint] No DISPLAY set — starting Xvfb on :99"
    Xvfb :99 -screen 0 1024x700x24 &
    sleep 2
    export DISPLAY=:99
else
    echo "[entrypoint] Using display: $DISPLAY"
fi

# Run the command passed to docker run (default: the Pi app)
exec "$@"
