# Progress: macOS support via mlx-whisper

Working notes for adding Mac (Apple Silicon) support to CustomWhisper. Written on the Windows
machine after an investigation session; work continues on the MacBook. Delete this file when the
port is done.

## Status

- [x] Investigation complete (2026-07-13, on Windows)
- [ ] Milestone 1: `python run.py` works on a Mac — mlx-whisper backend + hotkey + clipboard paste
- [ ] Milestone 2: wake listener, custom commands, process cleanup, launchers, installer, README

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
