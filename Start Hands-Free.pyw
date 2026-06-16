"""Double-click to start CustomWhisper hands-free (app + "Hey Jarvis" listener),
windowless. Say "Hey Jarvis" or tap Right-Ctrl+Space to dictate.
Use "Stop CustomWhisper.pyw" to shut everything down."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _launcher import launch

raise SystemExit(launch([
    ("run.py", "app_out.txt"),
    ("wake_listener.py", "wake_out.txt"),
]))
