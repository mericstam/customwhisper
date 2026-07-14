#!/usr/bin/env bash
# Stop CustomWhisper (the app and the wake-word listener).
# Safe to run even if nothing is running.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PID_FILE="$HERE/.cw_pids"
if [[ ! -f "$PID_FILE" ]]; then
    echo "Nothing to stop (no .cw_pids found)."
    exit 0
fi

while read -r pid; do
    [[ -n "$pid" ]] || continue
    # run.py launches src/main.py as a child; kill the children first, then the parent.
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
    echo "Stopped pid $pid (and its children)."
done <"$PID_FILE"

rm -f "$PID_FILE" "$HERE/.cw_wake_port"
echo "Done."
