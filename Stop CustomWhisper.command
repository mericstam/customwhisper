#!/bin/bash
# Double-click to stop CustomWhisper (the app and the wake-word listener).
# Safe to run even if nothing is running.
cd "$(dirname "$0")" || exit 1

VENV_PY="$PWD/venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "venv not found — nothing to stop."
    exit 0
fi

# Delegate to the same process_cleanup logic the app's Exit menu uses, so there's
# one source of truth for how our processes are identified (script name + repo
# working directory).
"$VENV_PY" - <<'PY'
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from process_cleanup import kill_related_processes
killed = kill_related_processes()
print(f"Stopped CustomWhisper (terminated {killed})." if killed
      else "Nothing to stop (no running CustomWhisper found).")
PY
