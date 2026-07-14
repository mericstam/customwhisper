#!/bin/bash
# Double-click to start CustomWhisper (app only, hotkey activation, no wake word).
# Press the activation hotkey (default Ctrl+Shift+Space) to dictate.
# Use "Stop CustomWhisper.command" to shut it down.
#
# First launch prompts for Microphone, Accessibility and Input Monitoring
# permissions (System Settings > Privacy & Security). Grant all three.
cd "$(dirname "$0")" || exit 1

VENV_PY="$PWD/venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "venv not found at $VENV_PY"
    echo "Run ./install-mac.sh first."
    read -r -p "Press Return to close..."
    exit 1
fi

exec "$VENV_PY" run.py
