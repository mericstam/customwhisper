#!/usr/bin/env bash
# Start CustomWhisper hands-free: the app plus the "Hey Jarvis" wake listener.
# Say the wake word or tap the activation hotkey to dictate.
# Use ./stop-customwhisper.sh to stop everything.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PY="$HERE/venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3)"

"$PY" run.py >"$HERE/app_out.txt" 2>&1 &
app_pid=$!
# Give the app a moment to bind its wake-IPC port before the listener starts,
# so the first detection reaches it over IPC (else it falls back to a keystroke).
sleep 2
"$PY" wake_listener.py >"$HERE/wake_out.txt" 2>&1 &
wake_pid=$!

printf '%s\n%s\n' "$app_pid" "$wake_pid" >"$HERE/.cw_pids"
echo "CustomWhisper started (app pid $app_pid, wake pid $wake_pid)."
echo "Logs: app_out.txt, wake_out.txt"
