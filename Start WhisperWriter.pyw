"""Double-click to start CustomWhisper (app only, hotkey activation, no wake
word), windowless. Press Right-Ctrl+Space to dictate.
Use "Stop CustomWhisper.pyw" to shut it down."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _launcher import launch

raise SystemExit(launch([
    ("run.py", "app_out.txt"),
]))
