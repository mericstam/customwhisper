# <img src="./assets/ww-logo.png" alt="logo" width="25" height="25"> CustomWhisper

A hands-free, voice-controlled speech-to-text tool for Windows. Built on a customized fork of
[WhisperWriter](https://github.com/savbell/whisper-writer), it transcribes your microphone straight
into the active window using a local [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
model (or the OpenAI API).

> **Based on [WhisperWriter](https://github.com/savbell/whisper-writer) by savbell, licensed under
> GPL-3.0. This is a modified version.** Because the upstream project is GPL-3.0 (copyleft), this
> project is also licensed under [GPL-3.0](./LICENSE). See [Changes from upstream](#changes-from-upstream).

What makes this build *custom*:

- **"Hey Jarvis" wake word** — start a dictation completely hands-free, no key press needed.
- **Spoken commands mid-dictation** — say *"Jarvis hold / continue / end session / cancel"* to pause,
  resume, finish, or discard a recording without touching the keyboard.
- **Clipboard paste output** — text is pasted instantly (Ctrl+V) instead of typed key-by-key, which is
  faster and immune to dropped characters.
- **Auto-submit** — optionally press Enter after the text is inserted.

## How it works

The app has two cooperating processes (both launched by `Start Hands-Free.bat`):

1. **`run.py` → `src/main.py`** — the WhisperWriter app. Sits in the system tray, listens for the
   activation hotkey (`Right-Ctrl + Space` by default), records, transcribes, and writes the result
   into the focused window.
2. **`wake_listener.py`** — an always-on, fully local wake-word listener (openWakeWord). When it hears
   "Hey Jarvis", it simulates the activation hotkey to kick off a dictation. It coexists with the app
   and auto-recovers if the mic is briefly grabbed during a dictation.

While recording, an optional **voice-command recognizer** (`src/command_recognizer.py`, using Vosk
with a constrained grammar) listens for command phrases and acts on them, trimming the spoken command
out of the audio so it isn't transcribed.

### Voice commands

| Say… | Action |
|------|--------|
| `Jarvis hold` / `Jarvis pause` | Pause recording (keeps listening for resume) |
| `Jarvis continue` / `Jarvis resume` / `Jarvis go on` | Resume recording |
| `Jarvis end session` / `Jarvis stop session` | Finish and transcribe |
| `Jarvis cancel session` / `Jarvis cancel` | Discard the recording |

Phrases are matched exactly. You can add variants in the `DEFAULT_COMMANDS` map in
`src/command_recognizer.py`.

### Recording modes

Set via `recording_mode` in the config:

- `continuous` — stops after a pause, transcribes, then auto-restarts; press the hotkey to stop.
- `voice_activity_detection` — stops after a pause; press the hotkey again to record again.
- `press_to_toggle` — press once to start, press again to stop.
- `hold_to_record` — records only while the hotkey is held.

## Project layout

```
run.py                       # entry point -> launches src/main.py
wake_listener.py             # "Hey Jarvis" wake-word listener (openWakeWord)
Start Hands-Free.bat         # runs the app + wake listener together
Start WhisperWriter.bat      # runs just the app (hotkey only, no wake word)
src/
  main.py                    # app, system tray, orchestration
  key_listener.py            # global hotkey detection (pynput / evdev backends)
  result_thread.py           # records audio, runs VAD + voice commands, transcribes
  command_recognizer.py      # in-dictation Vosk command recognizer ("Jarvis ...")
  transcription.py           # local faster-whisper or OpenAI API transcription
  input_simulation.py        # types/pastes the result (pynput / clipboard / dotool)
  utils.py                   # ConfigManager (YAML config + schema)
  config_schema.yaml         # defaults + descriptions for every setting
  config.yaml                # your saved settings (git-ignored)
  ui/                        # PyQt5 windows: main, settings, status
assets/                      # icons, beep sound, demo gifs
```

## Getting started

### Prerequisites
- Python `3.11`
- For GPU transcription: an NVIDIA GPU with CUDA 12 (cuBLAS + cuDNN 8). Falls back to CPU automatically.

### Install (Windows)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements-win.txt
```

> `requirements-win.txt` is the pinned, Windows-tested set. The extra custom features also need
> `openwakeword`, `vosk`, `audioplayer`, and `pyperclip` — make sure these are installed in the venv.

### Run

- **Hands-free (app + wake word):** double-click `Start Hands-Free.bat`, then say **"Hey Jarvis"** to
  dictate (or tap **Right-Ctrl + Space**).
- **App only (hotkey, no wake word):** `Start WhisperWriter.bat`, or `python run.py`.

On first run, a Settings window opens. Configure and save, then press **Start** to activate the
listener.

## Configuration

Settings live in `src/config.yaml` (created on first save; git-ignored). Every option, its type, and a
description are defined in `src/config_schema.yaml`. Edit through the Settings window or the file
directly. Highlights:

- **`model_options.local`** — `model` (e.g. `large-v3`), `device` (`cuda`/`cpu`/`auto`),
  `compute_type` (e.g. `float16`), `vad_filter`.
- **`model_options.common.initial_prompt`** — a vocabulary hint to bias transcription toward your
  domain terms.
- **`recording_options`** — `activation_key`, `recording_mode`, `silence_duration`, `sample_rate`.
- **`post_processing`** — `input_method` (`pynput` to type, `clipboard` to paste), `press_enter_after`,
  trailing space / period handling.
- **`voice_commands`** — `enabled` and `trim_ms` (safety margin trimmed around a spoken command so the
  command word isn't transcribed).

To use the OpenAI API instead of a local model, set `model_options.use_api: true` and put your key in
a `.env` file (`OPENAI_API_KEY=...`) or via the Settings window.

## Changes from upstream

This project modifies [WhisperWriter](https://github.com/savbell/whisper-writer) by adding:

- An always-on **"Hey Jarvis" wake-word listener** (`wake_listener.py`) for fully hands-free
  activation, plus `Start Hands-Free.bat` to run it alongside the app.
- **In-dictation voice commands** via Vosk (`src/command_recognizer.py`) — *"Jarvis hold / continue /
  end session / cancel"* — wired into the recording loop in `src/result_thread.py`, with audio
  trimming so command words aren't transcribed.
- A **`voice_commands`** config section (`src/config_schema.yaml`).
- **Clipboard-paste output** (`input_method: clipboard`) and **auto-submit** (`press_enter_after`) in
  `src/input_simulation.py`.

## Credits & licenses

Based on [WhisperWriter](https://github.com/savbell/whisper-writer) by savbell — **GPL-3.0**. This
project is distributed under the same license; see [LICENSE](./LICENSE).

Built with these open-source projects (installed as dependencies, not bundled):

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — transcription (MIT)
- [openWakeWord](https://github.com/dscripka/openWakeWord) — wake word (Apache-2.0)
- [Vosk](https://github.com/alphacep/vosk-api) — voice commands (Apache-2.0)
- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) — UI (GPL-3.0 / commercial)
