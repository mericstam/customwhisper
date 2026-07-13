# Progress: macOS and Linux (Ubuntu) support

Working notes for porting CustomWhisper beyond Windows. Written on the Windows machine after an
investigation session; macOS is verified on-device, Linux is code-complete pending on-device
verification. Delete this file when both ports are done.

## Status

- [x] Investigation complete (2026-07-13, on Windows) — macOS via mlx-whisper, Linux via existing
      faster-whisper/CUDA
- [x] macOS milestone 1: mlx-whisper backend implemented + verified end-to-end on Apple Silicon
- [~] macOS milestone 2: custom commands, process cleanup, launchers, installer, README done; wake
      listener/Vosk ported and verified live on-device (see below)
- [~] Ubuntu milestone 1: `python run.py` works on Ubuntu (Xorg session) — no backend change needed.
      Code + packaging done (see "Linux (Ubuntu)" below); pending on-device verification.
- [~] Ubuntu milestone 2: Wayland-proper setup (evdev + ydotool) + IPC wake trigger + install.sh.
      IPC wake trigger + install.sh + launchers done; pending on-device verification.

## macOS (Apple Silicon)

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

## Linux (Ubuntu)

Linux is the easiest port: upstream WhisperWriter's Linux support is still in the fork —
`key_listener.py` has an evdev backend, `input_simulation.py` supports ydotool/dotool, and both
are already in `config_schema.yaml`. **No new transcription backend needed**: faster-whisper +
CTranslate2 runs natively on Linux with CUDA.

### Implemented (2026-07-14, code changes; unit-tested on WSL where no display/audio is needed)

- `src/custom_commands.py` — the shared `_open_target()` already dispatches `xdg-open` on Linux
  (landed with the macOS port).
- `src/process_cleanup.py` — the shared POSIX branch already covers Linux (reads `/proc/<pid>/cwd`,
  matches on script-name markers + cwd). No Linux-specific change needed.
- `src/wake_ipc.py` (new) — dependency-free loopback-TCP IPC: `WakeTriggerServer` (run by the app)
  + `send_trigger()` (called by the wake listener). Port advertised in `.cw_wake_port`. Verified the
  full round-trip (deliver → callback → port-file cleanup → graceful no-server fallback).
- `src/main.py` — starts `WakeTriggerServer` and routes it to `on_activation` via a `pyqtSignal`
  (thread-safe), stops it in `cleanup()`. This is the fix for the Wayland/evdev "fake keystroke is
  invisible" gotcha.
- `wake_listener.py` — new `--trigger {auto,ipc,keystroke}` (default `auto`): tries IPC, falls back
  to the pynput keystroke. Windows/macOS behaviour unchanged (IPC succeeds when the app is up).
- `requirements-linux.txt` (new) — Windows list minus `pyreadline3`, plus `evdev` for the Wayland
  input backend.
- `install.sh`, `start-customwhisper.sh`, `start-hands-free.sh`, `stop-customwhisper.sh` (new) —
  Linux equivalents of the `.pyw`/`install.ps1` flow. `.cw_wake_port` added to `.gitignore`.

Not yet done (need a real Ubuntu box): pip install of the Linux requirements, apt system packages,
CUDA cuDNN wiring, and the actual hotkey→record→transcribe→paste smoke test on X11 and Wayland.

### X11 vs Wayland (the main decision)

Recent Ubuntu (22.04+; 24.04 even with NVIDIA) defaults to GNOME on **Wayland**.

- **Easy path — "Ubuntu on Xorg" session** (pick at login screen): pynput works for both the
  global hotkey and typing; clipboard paste needs `xclip`; the hardcoded Ctrl+V is already
  correct on Linux. Use this to get milestone 1 running with zero permission plumbing.
- **Wayland-proper path**: pynput cannot listen globally. Use the existing **evdev** input
  backend (`input_backend: evdev`, requires user in the `input` group:
  `sudo usermod -aG input $USER` + re-login) and **ydotool** for typing (`ydotoold` daemon +
  `/dev/uinput` udev permissions) or **dotool**. Clipboard needs `wl-clipboard`.

### Wake-listener gotcha (fixed via IPC)

`wake_listener.py` used to trigger dictation by simulating the activation hotkey with pynput's
Controller. The evdev backend only sees real `/dev/input` events, so a pynput-synthesized keypress
is invisible to it (and pynput's Controller may not work on Wayland at all). Fixed with a direct IPC
trigger (`src/wake_ipc.py`, loopback TCP) that `main.py` listens on; the keystroke path stays as a
fallback (`--trigger auto`).

### Work items for Ubuntu

1. [x] `requirements-linux.txt` — Windows list minus `pyreadline3`, plus `evdev`. Keeps
   `openwakeword` + `vosk`. (The stale upstream UTF-16 `requirements.txt` is untouched for now —
   still worth deleting/replacing later.)
2. [ ] apt packages to document/install: `libportaudio2` (sounddevice), `libsndfile1` (soundfile),
   `ffmpeg`, `xclip` (X11) or `wl-clipboard` + `ydotool` (Wayland), Qt xcb libs
   (`libxcb-xinerama0` etc.), GStreamer plugins for `audioplayer` (or make the beep optional).
   Documented in `install.sh`; not yet installed/verified on a real box.
3. [ ] CUDA: needs cuBLAS + cuDNN 8 for ctranslate2 4.2.1 — `pip install nvidia-cublas-cu12
   nvidia-cudnn-cu12==8.*` and put their lib dirs on `LD_LIBRARY_PATH` (or system CUDA install).
   Documented in `install.sh`; not yet verified.
4. [x] `src/custom_commands.py` 'open' → `xdg-open "<target>"` (shared `_open_target()` with macOS).
5. [x] POSIX `process_cleanup.py` (script markers + cwd, spare self/ancestors) — shared with macOS.
6. [x] `install.sh` + shell launchers (`start-customwhisper.sh`, `start-hands-free.sh`,
   `stop-customwhisper.sh`). Optional `.desktop` autostart / systemd user unit for the wake
   listener still TODO.
7. [x] Wake trigger IPC change — `src/wake_ipc.py` + `main.py` server + `wake_listener.py
   --trigger auto`. Nicer on all platforms; keystroke kept as fallback.

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

### Windows-specific plumbing ported for both OSes

1. **Paste simulation** — `src/input_simulation.py` `_paste_clipboard()` hardcoded **Ctrl+V**;
   macOS needs **Cmd+V**. Done via `PASTE_MODIFIER` (Cmd on darwin, Ctrl on win/linux).
2. **Custom "open" commands** — `_open_target()` dispatches `start` (win) / `open` (mac) /
   `xdg-open` (linux).
3. **Process cleanup** — POSIX version added (script markers + cwd; see the macOS gotcha above).
4. **Launchers/installer** — macOS `.command` + `install-mac.sh`; Linux shell scripts + `install.sh`.
5. **macOS permissions** — three TCC grants (Microphone / Accessibility / Input Monitoring); solved
   by shipping a `.app` bundle so grants attach to CustomWhisper itself.
6. **PyQt5 on Apple Silicon** — resolved: PyQt5 5.15.11 + Qt5 5.15.19 install on arm64, no PyQt6.
7. **Wake word + Vosk** — `vosk` ships macOS arm64 wheels; `openwakeword` uses
   `inference_framework='onnx'`.

## Notes

- The Windows machine (NVIDIA/CUDA) stays on the faster-whisper backend — don't regress it.
  `requirements-win.txt` stays as-is.
- Platform switches now cover three OSes: paste chord (Ctrl+V win/linux, Cmd+V mac), open
  command (`start` win, `open` mac, `xdg-open` linux), process cleanup (PowerShell CIM win,
  ps/kill posix).
- App is a fork of WhisperWriter (GPL-3.0); upstream had Linux support but no Mac support.
</content>
</invoke>
