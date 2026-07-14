# Progress: macOS support via mlx-whisper

Working notes for adding Mac (Apple Silicon) support to CustomWhisper. Written on the Windows
machine after an investigation session; work continues on the MacBook. Delete this file when the
port is done.

## Status

- [x] Investigation complete (2026-07-13, on Windows)
- [x] Milestone 1: mlx-whisper backend implemented + verified end-to-end on Apple Silicon
- [~] Milestone 2: custom commands, process cleanup, launchers, installer, README done; wake
  listener/Vosk ported but not yet verified live on-device; interactive hotkey→paste needs a human
  with TCC permissions granted

### Done on the Mac (2026-07-13)

- **Env**: Python 3.11 (Homebrew) venv; `requirements-mac.txt` frozen. PyQt5 5.15.11 + Qt5 5.15.19
  install cleanly on arm64 — **risk #6 resolved, no PyQt6 migration needed**.
- **Backend** (`src/transcription.py`): `resolve_backend()` picks mlx-whisper on darwin,
  faster-whisper elsewhere; new `model_options.local.backend` schema option (`auto`/`faster_whisper`/
  `mlx_whisper`). faster-whisper import is now lazy so Mac doesn't need it. mlx model names map to
  `mlx-community/whisper-<model>-mlx`. Warm-up transcribe at startup. **Verified**: `say`-generated
  speech transcribes correctly through the real `transcribe_local()` path (base model, ~2.4s).
- **Paste** (`src/input_simulation.py`): `PASTE_MODIFIER` = Cmd on darwin, Ctrl elsewhere.
- **Open commands** (`src/custom_commands.py`): `_open_target()` dispatches macOS `open` / Windows
  `start` / Linux `xdg-open`.
- **Process cleanup** (`src/process_cleanup.py`): POSIX branch added. **Gotcha found & fixed**: a
  venv python on macOS re-execs the Homebrew *framework* binary, so `ps` shows the framework path +
  a *relative* script name — the repo path never appears in the command line. So POSIX matches on
  script-name markers + the process **cwd** (via `/proc` on Linux, `lsof` on macOS). **Verified**:
  Stop.command killed a live app + orphaned children.
- **Launchers/installer**: `Start CustomWhisper.command`, `Stop CustomWhisper.command` (use full venv
  python path), `install-mac.sh`. README updated with macOS install, the three TCC permissions, and
  the `backend` option. (The macOS wake word later moved in-app, so no `Start Hands-Free.command`.)
- App boots on Mac (only a cosmetic "Segoe UI" font-fallback warning; harmless).

### Bugs found & fixed during on-device GUI testing (2026-07-13/14)

- **UI unreadable** (`src/ui/base_window.py`, `src/main.py`): frameless windows painted a
  semi-transparent white bg with dark text → under macOS dark mode this was white-on-white. Now paint
  an opaque dark bg + light text on darwin, and apply a Fusion **dark palette** (`apply_macos_theme`)
  so the whole schema-driven Settings UI is readable. Windows/Linux unchanged.
- **Misleading Settings fields** (`src/ui/settings_window.py` `_is_field_hidden_for_backend`):
  `device`/`compute_type`/`vad_filter` are faster-whisper-only, so they're hidden when the mlx backend
  is active (mlx always uses the Metal GPU). Schema descriptions annotated too.
- **First-run save crash** (`src/main.py` `cleanup`): saving Settings on first launch called
  `cleanup()` before `initialize_components()` ran → `AttributeError: key_listener`. Now guards with
  `getattr`. Pre-existing bug (all platforms).
- **Key-map crash** (`src/key_listener.py` `_create_key_map`): the map was one dict literal referencing
  `Key.insert`/`num_lock`/`scroll_lock`/`pause`/`print_screen`, which **don't exist in pynput's Key
  enum on macOS** → `AttributeError` aborted the listener. Rebuilt defensively (skip absent keys).
- **Hotkey listener SIGTRAP crash** (`src/macos_pynput_patch.py`, wired in `main.py`): pynput's key
  listener runs on a background thread and calls `keycode_context()`, which uses the HIToolbox Text
  Input Source APIs (`TISCopyCurrentKeyboardInputSource` / `TISGetInputSourceProperty`). On macOS 14+
  those must run on the **main thread** — off-thread they hard-crash the process
  (`dispatch_assert_queue` / EXC_BREAKPOINT). Fix: compute the `(keyboard_type, layout_data)` tuple
  once on the main thread at startup and monkeypatch `keycode_context` to yield the cached value; also
  pre-resolve `HIServices.AXIsProcessTrusted` (pyobjc lazy import isn't thread-safe → the listener
  thread hit `KeyError('AXIsProcessTrusted')`). Verified: listener now starts, no crash.

### Verified working end-to-end on the Mac (2026-07-14)

Full flow confirmed by the user: hotkey dictation types into the active app, one-shot recording,
and the "Hey Jarvis" wake word. Additional fixes made to get there:

- **The TCC breakthrough — ship a `.app` bundle** (`install-mac.sh` now builds `CustomWhisper.app`,
  bundle id `com.customwhisper.app`, `LSUIElement`). Running via `python run.py` in a terminal ties
  macOS permissions to the *terminal*, so grants kept landing on the wrong identity. As its own app,
  CustomWhisper appears in Privacy & Security and you grant *it* Microphone + Accessibility + Input
  Monitoring directly. **Launch with `open CustomWhisper.app`, not `python run.py`.**
- **Self-requesting permissions** (`request_macos_permissions` in main.py): pops the Accessibility
  (`AXIsProcessTrustedWithOptions`) and Input Monitoring (`IOHIDRequestAccess`) prompts on launch.
- **Insight**: Input Monitoring drives the hotkey; **Accessibility** drives typing the result into
  other apps — they're separate grants, and the missing Accessibility was why "nothing typed".
- **`quitOnLastWindowClosed(False)`**: after removing `Qt.Tool`, the status overlay closing ended the
  app after one dictation. Fixed.
- **Empty-result suppression** (`on_transcription_complete`): silent/noise captures no longer type a
  blank line + Enter. Output errors are caught so a denied keystroke can't wedge the app.
- **Listener starts on the Start button** (`on_start_listening`) — not at launch — and starts both the
  hotkey listener and the wake-word listener.
- **Wake word integrated**: main.py spawns `wake_listener.py` as a child (so it shares the app's TCC
  identity → inherits mic/accessibility); `wake_listener.py` now reads `activation_key` from config
  (was hardcoded Right-Ctrl+Space) and logs a mic/score heartbeat.
- **Hotkey stop in VAD mode** (`on_activation`): pressing the hotkey again finalizes an in-progress
  recording instead of doing nothing.
- **In-dictation Vosk voice commands were misfiring** ("HOLD" on normal speech) and pausing the
  recording — surfaced as a config toggle; disable `voice_commands.enabled` if it mis-triggers.
- Earlier UI fixes: dark theme (`apply_macos_theme`), tray "Open Settings" `NoRole`, floating status
  overlay, first-run save crash guard, defensive pynput key map.

Recommended config for one-shot dictation: `recording_mode: voice_activity_detection`.

### Still open / nice-to-have
- Wake word triggers the same one-shot dictation as the hotkey; if you want the wake word to start
  *continuous* mode while the hotkey stays one-shot, that needs per-source mode logic (not done).
- `.app` launcher hardcodes the repo path at build time — re-run `install-mac.sh` if you move the repo.

## Investigation findings

### Transcription backend (the easy part, ~half a day)

`src/transcription.py` is the **only** file that touches faster-whisper (`create_local_model()`,
`transcribe_local()`). [mlx-whisper](https://pypi.org/project/mlx-whisper/) maps almost 1:1:

- `mlx_whisper.transcribe(audio, path_or_hf_repo=..., ...)` accepts a **numpy float32 array**
  directly — the existing `audio_data.astype(np.float32) / 32768.0` conversion works unchanged.
- Supports `language`, `initial_prompt`, `temperature`, `condition_on_previous_text` — everything
  we pass today **except `vad_filter`** (faster-whisper-specific; acceptable, we already do our own
  webrtcvad silence detection in `result_thread.py`).
- Stateless API — no `WhisperModel` object, but it caches the loaded model internally between
  calls. The warm-model pattern in `main.py` (`self.local_model = create_local_model()`) becomes a
  thin wrapper or a dummy warm-up transcribe at startup.
- Model names map mechanically to Hugging Face repos: `large-v3` →
  `mlx-community/whisper-large-v3-mlx`. Quantized variants exist (`...-q4` etc.).
- `device` / `compute_type` config options are irrelevant on Mac (always Metal GPU).
- Performance: ~3x faster than whisper.cpp on Apple Silicon per the
  [mlx-examples whisper README](https://github.com/ml-explore/mlx-examples/tree/main/whisper).

**Planned design:** add `model_options.local.backend: auto | faster_whisper | mlx_whisper` to
`config_schema.yaml`; `auto` picks `mlx_whisper` on `sys.platform == 'darwin'`, `faster_whisper`
elsewhere. Dispatch inside `create_local_model()` / `transcribe_local()`. Keep the existing
`model` dropdown values and translate to HF repo names for mlx.

### Windows-specific plumbing to port (the bulk of the work)

1. **Paste simulation** — `src/input_simulation.py` `_paste_clipboard()` hardcodes **Ctrl+V**;
   macOS needs **Cmd+V** (`PynputKey.cmd`). One-line platform switch. `pynput` and `pyperclip`
   themselves work on macOS.
2. **Custom "open" commands** — `src/custom_commands.py` `execute_command()` uses Windows shell
   `start ""`; macOS equivalent is `open "<target>"`. Simple platform switch.
3. **Process cleanup** — `src/process_cleanup.py` already no-ops off Windows (won't crash), but
   Exit won't kill the wake listener on Mac. Needs a POSIX version (`pgrep -f <repo_root>` +
   `kill`, or `psutil`).
4. **Launchers/installer** — `.pyw` files, `pythonw`, and `install.ps1` are Windows-only. Mac
   needs `.command` scripts or a shell script (optionally a launchd agent for the wake listener),
   plus a `requirements-mac.txt`: drop `ctranslate2` / `faster-whisper` / `pyreadline3`, add
   `mlx-whisper`.
5. **macOS permissions (biggest UX hurdle)** — three TCC grants needed: **Microphone**,
   **Accessibility** (simulated keystrokes), **Input Monitoring** (global hotkey via pynput).
   Granted to whatever binary runs Python (e.g. Terminal/iTerm or the venv python). README /
   install script must walk through System Settings > Privacy & Security.
6. **PyQt5 on Apple Silicon (RISK — verify first)** — pinned `PyQt5-Qt5==5.15.2` has **no arm64
   macOS wheel**. Bump to a `PyQt5-Qt5` release with universal2 wheels (5.15.11+) or migrate to
   PyQt6. Check this before anything else on the Mac.
7. **Wake word + Vosk** — `vosk` ships macOS arm64 wheels. `openwakeword` needs
   `inference_framework='onnx'` on Apple Silicon (default tflite runtime unavailable). Both need
   on-device verification.

## Suggested order of work on the Mac

1. Create venv (Python 3.11), try installing PyQt5 (risk #6) — decide PyQt5-bump vs PyQt6 early.
2. Draft `requirements-mac.txt`; install `mlx-whisper`, `pynput`, `sounddevice`, `soundfile`,
   `webrtcvad-wheels`, `pyperclip`, `openai`, `python-dotenv`, `PyYAML`, `audioplayer`.
3. Implement the `backend` dispatch in `src/transcription.py` + schema entry (works standalone,
   testable with a WAV file before touching the app).
4. Platform-switch fixes: Cmd+V paste (#1), `open` command (#2).
5. Run `python run.py`, grant TCC permissions, test hotkey → record → transcribe → paste.
6. Then milestone 2: wake listener (openwakeword onnx), POSIX process cleanup, launch scripts,
   README updates.

## Notes

- The Windows machine (NVIDIA/CUDA) stays on the faster-whisper backend — don't regress it.
  `requirements-win.txt` stays as-is.
- App is a fork of WhisperWriter (GPL-3.0); upstream had no Mac support either.
