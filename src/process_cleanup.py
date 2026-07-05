"""Shut down every CustomWhisper-related Python process.

The app can be started several ways (the hotkey app, the hands-free wake-word
listener, the `.pyw` launchers, or `python src/main.py` directly), and each is a
separate `python`/`pythonw` process. Quitting the Qt app only ends its own
process, so wake-word listeners and stray duplicate instances used to linger and
keep holding the microphone. This finds all of them by repo path and kills them.

Windows-only in practice (the app targets Windows); on other platforms the
kill step is skipped and the app just exits normally.
"""
import csv
import io
import os
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000  # don't flash a console window from pythonw

# Repo root = parent of this file's directory (this file lives in src/).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _list_python_processes():
    """Return [(pid, ppid, command_line)] for all python/pythonw processes.

    Uses a single PowerShell CIM query (WMIC is deprecated on Windows 11).
    Returns [] if enumeration fails for any reason.
    """
    ps = (
        "Get-CimInstance Win32_Process -Filter "
        "\"Name='python.exe' OR Name='pythonw.exe'\" | "
        "Select-Object ProcessId,ParentProcessId,CommandLine | "
        "ConvertTo-Csv -NoTypeInformation"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW,
            timeout=15,
        ).stdout
    except Exception:
        return []

    procs = []
    for row in csv.DictReader(io.StringIO(out)):
        try:
            pid = int(row.get("ProcessId") or 0)
            ppid = int(row.get("ParentProcessId") or 0)
        except (TypeError, ValueError):
            continue
        procs.append((pid, ppid, row.get("CommandLine") or ""))
    return procs


def _ancestors(pid, parent_of):
    """Walk up the parent chain from pid, returning the set of ancestor PIDs."""
    seen = set()
    cur = parent_of.get(pid)
    while cur and cur not in seen:
        seen.add(cur)
        cur = parent_of.get(cur)
    return seen


def kill_related_processes():
    """Kill every CustomWhisper python process except this one and its ancestors.

    Our own ancestor launchers (run.py wrappers) are spared so this process can
    still shut Qt down cleanly; those wrappers exit on their own once we do.
    Returns the list of PIDs it asked the OS to terminate.
    """
    if not sys.platform.startswith("win"):
        return []

    procs = _list_python_processes()
    if not procs:
        return []

    parent_of = {pid: ppid for pid, ppid, _ in procs}
    me = os.getpid()
    spare = {me} | _ancestors(me, parent_of)

    repo_root = REPO_ROOT.lower()
    targets = [
        pid for pid, _, cmdline in procs
        if pid not in spare and repo_root in cmdline.lower()
    ]

    for pid in targets:
        # /T also terminates child processes (e.g. a run.py wrapper's main.py).
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except Exception:
            pass
    return targets
