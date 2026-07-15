"""
Always-on wake-word listener for WhisperWriter.

Listens to the microphone for a wake phrase (default: "Hey Jarvis") using
openWakeWord (fully local). On detection, it simulates the WhisperWriter
activation hotkey (Right-Ctrl + Space), which starts a dictation in
voice_activity_detection mode (records until you stop speaking).

Robust against the mic being briefly grabbed by WhisperWriter during a
dictation: it auto-recovers the audio stream instead of crashing, and
prefers the WASAPI backend (shared mode) so it can coexist with the app.

Run this ALONGSIDE WhisperWriter (run.py). See "Start Hands-Free.bat".
"""
import os
import sys
import time
import argparse
import numpy as np
import sounddevice as sd
from pynput.keyboard import Controller, Key

import openwakeword
from openwakeword.model import Model

SAMPLE_RATE = 16000
FRAME = 1280  # 80 ms at 16 kHz (openWakeWord's expected chunk size)


# openWakeWord's bundled pre-trained models (referenced by bare name).
BUILTIN_WAKEWORDS = {
    'alexa', 'hey_jarvis', 'hey_mycroft', 'hey_rhasspy', 'timer', 'weather',
}


def load_wakeword_config():
    """Read wake_word.{model,threshold} from config. Falls back to hey_jarvis/0.5."""
    model, threshold = 'hey_jarvis', 0.5
    try:
        import yaml
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, 'src', 'config.yaml')) as f:
            cfg = yaml.safe_load(f) or {}
        ww = cfg.get('wake_word', {}) or {}
        model = ww.get('model') or model
        if ww.get('threshold') is not None:
            threshold = float(ww['threshold'])
    except Exception as e:
        print(f"  (couldn't read wake_word config, using {model}: {e})", flush=True)
    return model, threshold


def resolve_wakeword(name, framework):
    """Map a wake-word name to (model_arg, score_key).

    A built-in name is passed through as-is. Any other name is treated as a
    custom model bundled in wakewords/<name>.<ext>; openWakeWord keys its score
    by the file's base name, so that becomes the score_key.
    """
    if name in BUILTIN_WAKEWORDS:
        return name, name
    here = os.path.dirname(os.path.abspath(__file__))
    ext = 'tflite' if framework == 'tflite' else 'onnx'
    path = os.path.join(here, 'wakewords', f'{name}.{ext}')
    if os.path.exists(path):
        return path, name
    # Unknown name and no bundled file — let openWakeWord try it as a built-in
    # (it will raise a clear error if it isn't one).
    return name, name


def _parent_gone(initial_ppid):
    """True once our parent process has died and the OS has reparented us.

    On POSIX an orphaned child is reparented (to launchd/init), so getppid()
    stops matching the pid that spawned us. This lets the listener self-terminate
    when the app that started it exits — even on a crash or force-quit, where the
    app never gets to kill us — so no orphan is left holding the mic / hotkey.
    """
    try:
        return os.getppid() != initial_ppid
    except Exception:
        return False

# Map activation-key tokens (as written in config's recording_options.activation_key)
# to pynput keys, so the wake word triggers the SAME hotkey the app listens for.
_MODMAP = {
    'ctrl': Key.ctrl, 'control': Key.ctrl,
    'shift': Key.shift,
    'alt': Key.alt, 'option': Key.alt,
    'cmd': Key.cmd, 'command': Key.cmd, 'super': Key.cmd, 'win': Key.cmd,
    'space': Key.space, 'enter': Key.enter, 'return': Key.enter,
    'tab': Key.tab, 'esc': Key.esc, 'escape': Key.esc,
}


def load_activation_keys():
    """Read recording_options.activation_key from config and parse it into a list
    of pynput keys. Falls back to Ctrl+Space if the config can't be read."""
    key_str = 'ctrl+space'
    try:
        import yaml
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, 'src', 'config.yaml')) as f:
            cfg = yaml.safe_load(f)
        key_str = (cfg.get('recording_options', {}).get('activation_key')
                   or key_str)
    except Exception as e:
        print(f"  (couldn't read activation_key from config, using ctrl+space: {e})", flush=True)

    keys = []
    for tok in str(key_str).lower().split('+'):
        tok = tok.strip()
        if not tok:
            continue
        if tok in _MODMAP:
            keys.append(_MODMAP[tok])
        elif len(tok) == 1:
            keys.append(tok)  # a literal character key
        else:
            keys.append(getattr(Key, tok, tok))
    return keys or [Key.ctrl, Key.space], key_str


def pick_wasapi_input():
    """Return (device_index, extra_settings) for WASAPI shared-mode input, or (None, None)."""
    try:
        for i, api in enumerate(sd.query_hostapis()):
            if "WASAPI" in api["name"]:
                dev = api.get("default_input_device", -1)
                if dev is not None and dev >= 0:
                    try:
                        extra = sd.WasapiSettings(exclusive=False)
                    except Exception:
                        extra = None
                    return dev, extra
    except Exception:
        pass
    return None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wakeword", default=None,
                        help="Wake word: a built-in openWakeWord name (hey_jarvis, "
                             "alexa, hey_mycroft, hey_rhasspy) or a custom model in "
                             "wakewords/ (e.g. computer_v2). Defaults to wake_word.model "
                             "in config.yaml.")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Detection confidence threshold (0-1). Higher = fewer false "
                             "triggers. Defaults to wake_word.threshold in config.yaml.")
    parser.add_argument("--cooldown", type=float, default=3.0,
                        help="Seconds to ignore further triggers after one fires.")
    parser.add_argument("--framework", default="onnx", choices=["onnx", "tflite"],
                        help="Inference backend.")
    parser.add_argument("--exit-with-parent", action="store_true",
                        help="Exit automatically when the process that spawned this "
                             "listener dies. The app passes this so an unclean app "
                             "exit (crash/force-quit) can't leave an orphan behind.")
    args = parser.parse_args()

    initial_ppid = os.getppid()

    # CLI flags win; otherwise take the wake word + threshold from config.yaml.
    cfg_model, cfg_threshold = load_wakeword_config()
    wakeword = args.wakeword or cfg_model
    threshold = args.threshold if args.threshold is not None else cfg_threshold
    model_arg, score_key = resolve_wakeword(wakeword, args.framework)

    print("Ensuring wake-word models are downloaded...", flush=True)
    try:
        openwakeword.utils.download_models()
    except Exception as e:
        print(f"  (download_models note: {e})", flush=True)

    print(f"Loading wake word '{wakeword}' ({args.framework}) from {model_arg}...", flush=True)
    model = Model(wakeword_models=[model_arg], inference_framework=args.framework)

    kb = Controller()
    activation_keys, activation_str = load_activation_keys()
    print(f"Wake word will trigger the activation hotkey: {activation_str}", flush=True)

    def trigger():
        # Press the configured combo (modifiers first), then release in reverse.
        for k in activation_keys:
            kb.press(k)
        for k in reversed(activation_keys):
            kb.release(k)

    # MME (default) accepts 16 kHz and coexists at idle; the recovery loop below
    # handles the brief contention while WhisperWriter records a dictation.
    device, extra_settings = None, None
    backend = "default (MME)"
    spoken = wakeword.replace('_v1', '').replace('_v2', '').replace('_', ' ')
    print(f"\nWake listener READY ({backend}). Say \"{spoken}\" to start dictation.\n"
          f"(threshold={threshold}, cooldown={args.cooldown}s)\n", flush=True)

    last_trigger = 0.0
    # Outer loop: (re)open the stream and recover from transient device errors
    # (e.g. WhisperWriter briefly taking the mic during a dictation).
    while True:
        if args.exit_with_parent and _parent_gone(initial_ppid):
            print("  parent process gone; exiting wake listener.", flush=True)
            return
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=FRAME, device=device,
                                extra_settings=extra_settings) as stream:
                while True:
                    if args.exit_with_parent and _parent_gone(initial_ppid):
                        print("  parent process gone; exiting wake listener.", flush=True)
                        return
                    try:
                        data, _ = stream.read(FRAME)
                    except sd.PortAudioError:
                        # Mic momentarily unavailable (likely active dictation). Recover.
                        break
                    audio = np.frombuffer(bytes(data), dtype=np.int16).flatten()
                    scores = model.predict(audio)
                    score = float(scores.get(score_key, 0.0))
                    now = time.time()
                    if score >= threshold and (now - last_trigger) > args.cooldown:
                        last_trigger = now
                        print(f"  [{time.strftime('%H:%M:%S')}] detected (score={score:.2f}) -> dictation", flush=True)
                        trigger()
        except sd.PortAudioError as e:
            print(f"  audio device busy/unavailable, retrying: {e}", flush=True)
        except Exception as e:
            print(f"  unexpected error, retrying: {e}", flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nWake listener stopped.")
        sys.exit(0)
