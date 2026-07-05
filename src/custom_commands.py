"""
User-defined voice commands ("Hey Jarvis: open Word").

After a dictation is transcribed, the resulting text is compared against a list
of phrase -> action mappings the user configures in Settings > Commands. If the
spoken text matches a phrase, the associated action runs *instead* of the text
being typed out.

Commands are stored in config.yaml under the top-level 'custom_commands' key as
a list of dicts: {"phrase": str, "type": "open"|"run", "target": str}.

Action types:
  open  -- open an app, file, or URL. Uses the Windows shell 'start', which
           resolves registered app names (winword, excel, msedge, notepad),
           file paths, and URLs alike.
  run   -- run a raw shell command line.
"""
import os
import subprocess

from utils import ConfigManager


def _normalize(text):
    """Lowercase, drop surrounding punctuation/whitespace so 'Open Word.' == 'open word'."""
    if not text:
        return ""
    cleaned = "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace())
    return " ".join(cleaned.split())


def get_commands():
    """Return the configured command list (possibly empty)."""
    commands = ConfigManager.get_config_value('custom_commands', 'commands')
    return commands if isinstance(commands, list) else []


def is_enabled():
    enabled = ConfigManager.get_config_value('custom_commands', 'enabled')
    # Default to enabled when the key is absent (older configs) but commands exist.
    return True if enabled is None else bool(enabled)


def match_command(text, commands=None):
    """Return the command whose phrase matches the transcribed text, or None."""
    if commands is None:
        commands = get_commands()
    spoken = _normalize(text)
    if not spoken:
        return None
    for cmd in commands:
        phrase = _normalize(cmd.get('phrase', ''))
        if phrase and spoken == phrase:
            return cmd
    return None


def execute_command(cmd):
    """Run a single command's action. Returns True on a launch attempt."""
    target = (cmd.get('target') or '').strip()
    if not target:
        ConfigManager.console_print(f"Custom command '{cmd.get('phrase')}' has no target — skipping.")
        return False

    action = cmd.get('type', 'open')
    try:
        if action == 'run':
            subprocess.Popen(target, shell=True)
        else:  # 'open' (default): let the Windows shell resolve app names, files, URLs
            subprocess.Popen(f'start "" "{target}"', shell=True)
        ConfigManager.console_print(f"Custom command: '{cmd.get('phrase')}' -> {action} '{target}'.")
        return True
    except Exception as e:
        ConfigManager.console_print(f"Custom command '{cmd.get('phrase')}' failed: {e}")
        return False


def handle_transcription(text):
    """
    If the transcribed text matches a configured command, run it and return True
    (so the caller skips typing the text). Otherwise return False.
    """
    if not is_enabled():
        return False
    cmd = match_command(text)
    if cmd is None:
        return False
    execute_command(cmd)
    return True
