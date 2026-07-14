"""Shut down every CustomWhisper-related Python process.

The app can be started several ways (the hotkey app, the hands-free wake-word
listener, the `.pyw` launchers, or `python src/main.py` directly), and each is a
separate `python`/`pythonw` process. Quitting the Qt app only ends its own
process, so wake-word listeners and stray duplicate instances used to linger and
keep holding the microphone. This finds all of them by repo path and kills them.

Works on Windows (PowerShell CIM query + taskkill) and POSIX platforms — macOS
and Linux — (pgrep/ps + kill). On any other platform the kill step is skipped
and the app just exits normally.
"""
import csv
import io
import os
import signal
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


def _list_python_processes_posix():
    """Return [(pid, ppid, command_line)] for all python processes on macOS/Linux.

    Uses `ps` (available on both). Returns [] if enumeration fails.
    """
    try:
        out = subprocess.run(
            ["ps", "-axww", "-o", "pid=,ppid=,command="],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception:
        return []

    procs = []
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        cmdline = parts[2]
        if "python" not in cmdline.lower():
            continue
        procs.append((pid, ppid, cmdline))
    return procs


# Our launchable entry-point scripts. On macOS a venv's python re-execs the
# framework Python binary, so `ps` shows the framework path with only the
# *relative* script name as an argument (e.g. "... /Python run.py") — the repo
# path never appears in the command line. We therefore identify our processes on
# POSIX by (a) running one of these scripts and (b) having their working
# directory inside this repo.
SCRIPT_MARKERS = ("run.py", "main.py", "wake_listener.py")


def _ancestors(pid, parent_of):
    """Walk up the parent chain from pid, returning the set of ancestor PIDs."""
    seen = set()
    cur = parent_of.get(pid)
    while cur and cur not in seen:
        seen.add(cur)
        cur = parent_of.get(cur)
    return seen


def _select_targets(procs):
    """Windows: given [(pid, ppid, cmdline)], return PIDs of our related processes.

    On Windows the venv interpreter (venv\\Scripts\\pythonw.exe) lives inside the
    repo, so the repo path is present in every child's command line.

    Spares this process and its ancestor launchers (run.py wrappers) so this
    process can still shut Qt down cleanly; those wrappers exit on their own.
    """
    parent_of = {pid: ppid for pid, ppid, _ in procs}
    me = os.getpid()
    spare = {me} | _ancestors(me, parent_of)

    repo_root = REPO_ROOT.lower()
    return [
        pid for pid, _, cmdline in procs
        if pid not in spare and repo_root in cmdline.lower()
    ]


def _proc_cwd(pid):
    """Return a process's current working directory, or None if unavailable."""
    if os.path.isdir("/proc"):  # Linux
        try:
            return os.readlink("/proc/%d/cwd" % pid)
        except OSError:
            return None
    # macOS (and other BSDs): lsof reports the cwd file descriptor.
    try:
        out = subprocess.run(
            ["lsof", "-a", "-d", "cwd", "-p", str(pid), "-Fn"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def _select_targets_posix(procs):
    """macOS/Linux: return PIDs of our related python processes.

    A process qualifies if it runs one of our entry-point scripts AND its working
    directory is this repo. Spares this process and its ancestor launchers.
    """
    parent_of = {pid: ppid for pid, ppid, _ in procs}
    me = os.getpid()
    spare = {me} | _ancestors(me, parent_of)

    repo_root = os.path.realpath(REPO_ROOT)
    targets = []
    for pid, _, cmdline in procs:
        if pid in spare:
            continue
        if not any(marker in cmdline for marker in SCRIPT_MARKERS):
            continue
        cwd = _proc_cwd(pid)
        if cwd and os.path.realpath(cwd) == repo_root:
            targets.append(pid)
    return targets


def kill_related_processes():
    """Kill every CustomWhisper python process except this one and its ancestors.

    Our own ancestor launchers (run.py wrappers) are spared so this process can
    still shut Qt down cleanly; those wrappers exit on their own once we do.
    Returns the list of PIDs it asked the OS to terminate.
    """
    if sys.platform.startswith("win"):
        procs = _list_python_processes()
        if not procs:
            return []
        targets = _select_targets(procs)
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

    # macOS / Linux
    if sys.platform == "darwin" or sys.platform.startswith("linux"):
        procs = _list_python_processes_posix()
        if not procs:
            return []
        targets = _select_targets_posix(procs)
        for pid in targets:
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            except Exception:
                pass
        return targets

    return []
