# <img src="./assets/ww-logo.png" alt="logo" width="25" height="25"> CustomWhisper

A hands-free, voice-controlled speech-to-text tool for Windows and macOS (Apple Silicon). Built on a
customized fork of [WhisperWriter](https://github.com/savbell/whisper-writer), it transcribes your
microphone straight into the active window using a local Whisper model
([faster-whisper](https://github.com/SYSTRAN/faster-whisper) on Windows/NVIDIA,
[mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) on Apple Silicon) or the
OpenAI API.

> **Based on [WhisperWriter](https://github.com/savbell/whisper-writer) by savbell, licensed under
> GPL-3.0. This is a modified version.** Because the upstream project is GPL-3.0 (copyleft), this
> project is also licensed under [GPL-3.0](./LICENSE). See [Changes from upstream](#changes-from-upstream).

What makes this build *custom*:

- **Wake word** — start a dictation completely hands-free, no key press needed. Pick the wake phrase
  in **Settings > Wake word** (`hey_jarvis` by default; also `alexa`, `hey_mycroft`, `hey_rhasspy`, or
  a custom model such as `computer_v2` → *"Computer"*).
- **Spoken commands mid-dictation** — say *"Jarvis hold / continue / end session / cancel"* to pause,
  resume, finish, or discard a recording without touching the keyboard.
- **Custom app-launch commands** — map a spoken phrase (e.g. *"open word"*) to launching an app, file,
  or URL, or running a shell command, instead of typing the text out.
- **Clipboard paste output** — text is pasted instantly (Ctrl+V) instead of typed key-by-key, which is
  faster and immune to dropped characters.
- **Auto-submit** — optionally press Enter after the text is inserted.

## How it works

The app has two cooperating processes (both launched by `Start Hands-Free.pyw`):

1. **`run.py` → `src/main.py`** — the CustomWhisper app. Sits in the system tray, listens for the
   activation hotkey (`Right-Ctrl + Space` by default), records, transcribes, and writes the result
   into the focused window.
2. **`wake_listener.py`** — an always-on, fully local wake-word listener (openWakeWord). When it hears
   the configured wake phrase, it simulates the activation hotkey to kick off a dictation. It coexists
   with the app and auto-recovers if the mic is briefly grabbed during a dictation.

While recording, an optional **voice-command recognizer** (`src/command_recognizer.py`, using Vosk
with a constrained grammar) listens for command phrases and acts on them, trimming the spoken command
out of the audio so it isn't transcribed.

### Wake word

Choose the wake phrase in **Settings > Wake word** (`wake_word.model` in the config):

| Model | Say… | Notes |
|-------|------|-------|
| `hey_jarvis` *(default)* | "Hey Jarvis" | Official openWakeWord model — most reliable |
| `alexa` | "Alexa" | Official |
| `hey_mycroft` | "Hey Mycroft" | Official |
| `hey_rhasspy` | "Hey Rhasspy" | Official |
| `computer_v2` | "Computer" | Community model (bundled in `wakewords/`); less accurate — more misses and false triggers |

- **`wake_word.threshold`** (0–1, default `0.5`) — detection confidence. Raise it (e.g. `0.75`) if a
  short wake word like "Computer" fires too easily on background noise.
- **Custom models** — drop any openWakeWord `.onnx`/`.tflite` model into the `wakewords/` folder and
  set `wake_word.model` to its file name without the extension. Built-in names are used as-is.
- Changing the wake word in Settings restarts the app so the listener picks up the new phrase.

### Voice commands

| Say… | Action |
|------|--------|
| `Jarvis hold` / `Jarvis pause` | Pause recording (keeps listening for resume) |
| `Jarvis continue` / `Jarvis resume` / `Jarvis go on` | Resume recording |
| `Jarvis end session` / `Jarvis stop session` | Finish and transcribe |
| `Jarvis cancel session` / `Jarvis cancel` | Discard the recording |

Phrases are matched exactly. You can add variants in the `DEFAULT_COMMANDS` map in
`src/command_recognizer.py`.

### Custom app-launch commands

After a dictation is transcribed, the text is matched (case- and punctuation-insensitive) against a
list of phrase → action mappings you configure in **Settings > Commands** (`src/custom_commands.py`).
On a match, the action runs *instead* of the text being typed. Two action types:

- **`open`** — open an app, file, or URL via the host platform's opener (macOS `open`, Windows shell
  `start`, Linux `xdg-open`), which resolves app names, paths, and URLs.
- **`run`** — run a raw shell command line.

Mappings are stored in `config.yaml` under the top-level `custom_commands` key. For example, saying
*"open word"* can launch Word, or *"lock screen"* can run a command.

### Recording modes

Set via `recording_mode` in the config:

- `continuous` — stops after a pause, transcribes, then auto-restarts; press the hotkey to stop.
- `voice_activity_detection` — stops after a pause; press the hotkey again to record again.
- `press_to_toggle` — press once to start, press again to stop.
- `hold_to_record` — records only while the hotkey is held.

## Project layout

```
install.ps1                  # Windows installer: venv + deps + desktop shortcut
install-mac.sh               # macOS installer: venv + deps + builds CustomWhisper.app
run.py                       # entry point -> launches src/main.py
wake_listener.py             # "Hey Jarvis" wake-word listener (openWakeWord)
_launcher.py                 # shared windowless launch/stop helper (pythonw, Windows)
Start Hands-Free.pyw         # Windows: double-click app + wake listener, no console windows
Start CustomWhisper.pyw      # Windows: double-click app only (hotkey, no wake word)
Stop CustomWhisper.pyw       # Windows: double-click to stop the app and the listener
CustomWhisper.app            # macOS: the app bundle (built by install-mac.sh); the wake
                             #   word runs in-app, started with the Start button
Start CustomWhisper.command  # macOS: launch the app from a terminal (see live logs)
Stop CustomWhisper.command   # macOS: stop the app and the listener
src/
  main.py                    # app, system tray, orchestration
  key_listener.py            # global hotkey detection (pynput / evdev backends)
  result_thread.py           # records audio, runs VAD + voice commands, transcribes
  command_recognizer.py      # in-dictation Vosk command recognizer ("Jarvis ...")
  custom_commands.py         # post-dictation phrase -> launch app / run command
  process_cleanup.py         # kill related CustomWhisper processes on exit (Windows + POSIX)
  transcription.py           # local transcription (faster-whisper / mlx-whisper) or OpenAI API
  input_simulation.py        # types/pastes the result (pynput / clipboard / dotool)
  utils.py                   # ConfigManager (YAML config + schema)
  config_schema.yaml         # defaults + descriptions for every setting
  config.yaml                # your saved settings (git-ignored)
  ui/                        # PyQt5 windows: main, settings, status
wakewords/                   # custom openWakeWord models (e.g. computer_v2.onnx/.tflite)
assets/                      # icons, beep sound, demo gifs
```

## Getting started

### Prerequisites
- Python `3.11`
- **Windows:** for GPU transcription, an NVIDIA GPU with CUDA 12 (cuBLAS + cuDNN 8). Falls back to CPU
  automatically.
- **macOS:** Apple Silicon (M1 or newer). Transcription runs on the Metal GPU via mlx-whisper — no
  extra setup. Install Python 3.11 with `brew install python@3.11` if you don't have it.

### Install (Windows)

Run the installer from the repo root — it creates the venv, installs all dependencies, and adds a
**CustomWhisper** desktop shortcut. It's idempotent, so it's safe to re-run.

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Options: `-SkipDeps` (only set up venv + shortcut), `-NoShortcut` (skip the desktop shortcut).

<details>
<summary>Manual install</summary>

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements-win.txt
```

`requirements-win.txt` is the pinned, Windows-tested set and includes the custom-feature deps
(`openwakeword`, `vosk`, `audioplayer`, `pyperclip`).
</details>

### Install (macOS, Apple Silicon)

Run the installer from the repo root — it creates the venv and installs the Mac dependency set
(mlx-whisper backend + PyQt5 UI). It's idempotent, so it's safe to re-run.

```bash
./install-mac.sh
```

<details>
<summary>Manual install</summary>

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements-mac.txt
```

`requirements-mac.txt` is the pinned, Apple-Silicon set: it swaps faster-whisper/ctranslate2 for
`mlx-whisper` and keeps the custom-feature deps (`openwakeword`, `vosk`, `audioplayer`, `pyperclip`).
</details>

**macOS permissions.** The first time you run CustomWhisper, macOS prompts for three privacy grants.
Open **System Settings > Privacy & Security** and grant your terminal app (Terminal or iTerm) — or the
venv `python` — access under:

1. **Microphone** — to record your voice.
2. **Accessibility** — to paste/type the transcription into the active app.
3. **Input Monitoring** — to detect the global activation hotkey.

Until all three are granted, recording, pasting, or the hotkey (respectively) will silently do nothing.

> **Important:** macOS only applies a newly-granted Accessibility / Input Monitoring
> permission to *newly-started* processes. After granting them to your terminal app, **fully quit and
> reopen the terminal** (and relaunch CustomWhisper) — otherwise the hotkey still won't be detected
> even though the permission shows as granted. If you launch via the `.command` files from Finder, the
> responsible app is your terminal, so grant the permissions to Terminal/iTerm.

### Run

The app lives in the system tray. Press **Start** in its window to begin listening for the activation
hotkey; that also starts the "Hey Jarvis" wake word (unless `wake_word.enabled` is off). Say **"Hey
Jarvis"** or tap the hotkey to dictate.

- **macOS:** launch **`CustomWhisper.app`** (double-click in Finder, or `open CustomWhisper.app`). This
  gives the app its own identity for the privacy permissions — see [Install (macOS)](#install-macos-apple-silicon).
  `Start CustomWhisper.command` runs it from a terminal instead (handy for live logs); the wake word
  runs inside the app either way. After you press **Start** the window hides — **right-click the app's
  Dock icon** to reach **Open Main Window**, **Settings…**, or **Quit CustomWhisper**.
- **Windows:** double-click `Start Hands-Free.pyw` (app + wake listener) or `Start CustomWhisper.pyw`
  (hotkey only); these run windowless via `pythonw`.
- **Stop everything:** `Stop CustomWhisper.pyw` (Windows) / `Stop CustomWhisper.command` (macOS).

Output is written to `app_out.txt` / `wake_out.txt` for troubleshooting. On first run, a Settings
window opens — configure and save, then press **Start** to activate the listener.

## Configuration

Settings live in `src/config.yaml` (created on first save; git-ignored). Every option, its type, and a
description are defined in `src/config_schema.yaml`. Edit through the Settings window or the file
directly. Highlights:

- **`model_options.local`** — `backend` (`auto`/`faster_whisper`/`mlx_whisper`; `auto` picks
  mlx-whisper on Apple Silicon and faster-whisper elsewhere), `model` (e.g. `large-v3`), `device`
  (`cuda`/`cpu`/`auto`, faster-whisper only), `compute_type` (e.g. `float16`, faster-whisper only),
  `vad_filter`. On macOS the model name maps to the matching `mlx-community/whisper-<model>-mlx` repo,
  downloaded on first use; `device`/`compute_type` are ignored (always the Metal GPU).
- **`model_options.common.initial_prompt`** — a vocabulary hint to bias transcription toward your
  domain terms.
- **`recording_options`** — `activation_key`, `recording_mode`, `silence_duration`, `sample_rate`.
- **`post_processing`** — `input_method` (`pynput` to type, `clipboard` to paste), `press_enter_after`,
  `remove_filler_words` (strip spoken `um`/`uh`/`erm`/`hmm`; **off by default**), trailing space /
  period handling.
- **`voice_commands`** — `enabled` and `trim_ms` (safety margin trimmed around a spoken command so the
  command word isn't transcribed).
- **`wake_word`** — `enabled`, `model` (built-in name or a custom model in `wakewords/`; see
  [Wake word](#wake-word)), and `threshold` (detection confidence; raise it to reduce false triggers).

To use the OpenAI API instead of a local model, set `model_options.use_api: true` and put your key in
a `.env` file (`OPENAI_API_KEY=...`) or via the Settings window.

## Changes from upstream

This project modifies [WhisperWriter](https://github.com/savbell/whisper-writer) by adding:

- An always-on **wake-word listener** (`wake_listener.py`) for fully hands-free activation, with a
  **selectable wake phrase** (**Settings > Wake word**: `hey_jarvis`, `alexa`, `hey_mycroft`,
  `hey_rhasspy`, or custom `wakewords/` models like `computer_v2`) and a tunable detection threshold,
  plus windowless `.pyw` launchers (`Start Hands-Free.pyw`, `Stop CustomWhisper.pyw`) and an
  `install.ps1` setup script.
- **In-dictation voice commands** via Vosk (`src/command_recognizer.py`) — *"Jarvis hold / continue /
  end session / cancel"* — wired into the recording loop in `src/result_thread.py`, with audio
  trimming so command words aren't transcribed.
- A **`voice_commands`** config section (`src/config_schema.yaml`).
- **Custom app-launch commands** (`src/custom_commands.py`) — post-dictation phrase → action mappings
  that open an app/file/URL or run a shell command, configured in **Settings > Commands**.
- **Clipboard-paste output** (`input_method: clipboard`) and **auto-submit** (`press_enter_after`) in
  `src/input_simulation.py`.
- Optional **filler-word removal** (`remove_filler_words`, off by default) that strips spoken
  `um`/`uh`/`erm`/`hmm` in `src/transcription.py`.
- A **microphone test panel** in Settings (device picker, live level bar, receive-state status) plus a
  silent-mic timeout so a muted or busy device no longer hangs the recording loop
  (`src/result_thread.py`).
- **Full process cleanup on exit** (`src/process_cleanup.py`) — quitting the app also stops the
  hands-free wake-word listener and any stray CustomWhisper processes holding the microphone (Windows
  via PowerShell/taskkill, macOS/Linux via `ps`/cwd matching).
- **macOS (Apple Silicon) support** — an [mlx-whisper](https://github.com/ml-explore/mlx-examples)
  transcription backend selected automatically on Apple Silicon (`src/transcription.py`), Cmd+V
  clipboard paste, `open`-based app-launch commands, a **Dock-icon menu** (Open Main Window / Settings…
  / Quit), `.command` launchers, and `install-mac.sh`. Upstream WhisperWriter is Windows/Linux-only.

## Credits & licenses

Based on [WhisperWriter](https://github.com/savbell/whisper-writer) by savbell — **GPL-3.0**. This
project is distributed under the same license; see [LICENSE](./LICENSE).

Built with these open-source projects (installed as dependencies, not bundled):

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — transcription, Windows/NVIDIA (MIT)
- [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) — transcription, Apple Silicon (MIT)
- [openWakeWord](https://github.com/dscripka/openWakeWord) — wake word (Apache-2.0)
- [Vosk](https://github.com/alphacep/vosk-api) — voice commands (Apache-2.0)
- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) — UI (GPL-3.0 / commercial)
