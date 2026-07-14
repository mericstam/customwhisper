"""Local IPC channel to trigger a dictation without simulating a keystroke.

The hands-free wake listener normally starts a dictation by faking the
activation hotkey (Right-Ctrl+Space) with pynput. That breaks on the
Wayland/evdev input path: the evdev backend only sees *real* `/dev/input`
events, so a pynput-synthesized keypress is invisible to it (and pynput's
Controller may not work on Wayland at all).

This module lets the wake listener poke the running app directly over a
loopback TCP socket instead. The app runs a `WakeTriggerServer`; the wake
listener calls `send_trigger()`. It is deliberately dependency-free (no Qt, no
project imports) so `wake_listener.py` can use the client half without pulling
in the GUI stack. Works identically on Windows, macOS and Linux — the keystroke
path stays as a fallback.

Wire format: the server binds an ephemeral 127.0.0.1 port and writes it to
`.cw_wake_port` in the repo root. A client connects and sends the line
`activate\n`; the server fires its callback for any non-empty line.
"""
import os
import socket
import threading

# Repo root = parent of this file's directory (this file lives in src/).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT_FILE = os.path.join(REPO_ROOT, ".cw_wake_port")

_HOST = "127.0.0.1"


def _read_port():
    """Return the port the server last advertised, or None."""
    try:
        with open(PORT_FILE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def send_trigger(timeout=1.0):
    """Ask the running app to start a dictation. Returns True if delivered.

    Returns False (rather than raising) when no app is listening, so callers
    can fall back to the keystroke path.
    """
    port = _read_port()
    if not port:
        return False
    try:
        with socket.create_connection((_HOST, port), timeout=timeout) as sock:
            sock.sendall(b"activate\n")
        return True
    except OSError:
        return False


class WakeTriggerServer(threading.Thread):
    """Background listener that invokes `on_trigger` for each incoming poke.

    `on_trigger` runs on this server thread, so in a GUI app it should marshal
    onto the main thread (e.g. emit a Qt signal) rather than touch widgets
    directly.
    """

    def __init__(self, on_trigger):
        super().__init__(daemon=True)
        self._on_trigger = on_trigger
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((_HOST, 0))
        self._sock.listen(4)
        self._sock.settimeout(0.5)  # so the accept loop can notice _stop
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()

    def start(self):
        """Advertise the port and begin accepting connections."""
        try:
            with open(PORT_FILE, "w") as f:
                f.write(str(self.port))
        except OSError:
            pass
        super().start()

    def run(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    conn.settimeout(1.0)
                    data = conn.recv(64)
                except OSError:
                    data = b""
            if data.strip():
                try:
                    self._on_trigger()
                except Exception as e:
                    print(f"Wake trigger callback failed: {e}", flush=True)

    def stop(self):
        """Stop accepting connections and remove the advertised port file."""
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        # Only remove the port file if it still points at us.
        if _read_port() == self.port:
            try:
                os.remove(PORT_FILE)
            except OSError:
                pass
