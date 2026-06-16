"""Shared windowless launcher for CustomWhisper.

Starts project scripts with the venv's `pythonw.exe` so no console windows
appear. Each script's output is redirected to a log file, and the launched
PIDs are written to `.cw_pids` so the Stop launcher can shut everything down.

Used by the `.pyw` entry points (double-click), which are themselves
windowless. Don't run this module directly.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(HERE, ".cw_pids")
CREATE_NO_WINDOW = 0x08000000  # Windows: don't allocate a console for the child


def _interpreter(windowless=True):
    """Prefer the venv interpreter; fall back to whatever is running us."""
    name = "pythonw.exe" if windowless else "python.exe"
    venv = os.path.join(HERE, "venv", "Scripts", name)
    return venv if os.path.exists(venv) else sys.executable


def _error(msg):
    """Show a native message box (pythonw has no console to print to)."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "CustomWhisper", 0x10)
    except Exception:
        pass


def launch(jobs):
    """Spawn each (script, logfile) windowless. Returns 0 on success."""
    interp = _interpreter()
    if not os.path.exists(interp):
        _error(f"Python interpreter not found:\n{interp}\n\n"
               "Create the venv and install requirements first.")
        return 1

    pids = []
    for script, logname in jobs:
        script_path = os.path.join(HERE, script)
        if not os.path.exists(script_path):
            _error(f"Missing script:\n{script_path}")
            return 1
        log = open(os.path.join(HERE, logname), "w",
                   buffering=1, encoding="utf-8", errors="replace")
        proc = subprocess.Popen(
            [interp, script_path],
            cwd=HERE,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        pids.append(proc.pid)

    with open(PID_FILE, "w") as f:
        f.write("\n".join(str(p) for p in pids))
    return 0


def stop():
    """Terminate everything started by launch() (and any child processes)."""
    if not os.path.exists(PID_FILE):
        _error("Nothing to stop (no running CustomWhisper found).")
        return 0
    with open(PID_FILE) as f:
        pids = [line.strip() for line in f if line.strip()]
    for pid in pids:
        # /T kills the child tree too (run.py launches main.py as a child).
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"],
                       creationflags=CREATE_NO_WINDOW,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    return 0
