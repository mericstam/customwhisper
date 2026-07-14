#!/usr/bin/env bash
# Start CustomWhisper (app only, hotkey activation, no wake word).
# Press the activation hotkey to dictate. Use ./stop-customwhisper.sh to stop.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PY="$HERE/venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3)"

"$PY" run.py >"$HERE/app_out.txt" 2>&1 &
echo $! >"$HERE/.cw_pids"
echo "CustomWhisper started (pid $!). Logs: app_out.txt"
