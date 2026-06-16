"""Double-click to stop CustomWhisper (the app and the wake-word listener),
windowless. Safe to run even if nothing is running."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _launcher import stop

raise SystemExit(stop())
