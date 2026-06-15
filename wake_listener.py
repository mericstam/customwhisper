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
    parser.add_argument("--wakeword", default="hey_jarvis",
                        help="Pre-trained wake word model name (e.g. hey_jarvis, alexa, hey_mycroft).")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Detection confidence threshold (0-1). Higher = fewer false triggers.")
    parser.add_argument("--cooldown", type=float, default=3.0,
                        help="Seconds to ignore further triggers after one fires.")
    parser.add_argument("--framework", default="onnx", choices=["onnx", "tflite"],
                        help="Inference backend.")
    args = parser.parse_args()

    print("Ensuring wake-word models are downloaded...", flush=True)
    try:
        openwakeword.utils.download_models()
    except Exception as e:
        print(f"  (download_models note: {e})", flush=True)

    print(f"Loading wake word '{args.wakeword}' ({args.framework})...", flush=True)
    model = Model(wakeword_models=[args.wakeword], inference_framework=args.framework)

    kb = Controller()

    def trigger():
        kb.press(Key.ctrl_r)
        kb.press(Key.space)
        kb.release(Key.space)
        kb.release(Key.ctrl_r)

    # MME (default) accepts 16 kHz and coexists at idle; the recovery loop below
    # handles the brief contention while WhisperWriter records a dictation.
    device, extra_settings = None, None
    backend = "default (MME)"
    print(f"\nWake listener READY ({backend}). Say \"{args.wakeword.replace('_', ' ')}\" to start dictation.\n"
          f"(threshold={args.threshold}, cooldown={args.cooldown}s)\n", flush=True)

    last_trigger = 0.0
    # Outer loop: (re)open the stream and recover from transient device errors
    # (e.g. WhisperWriter briefly taking the mic during a dictation).
    while True:
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=FRAME, device=device,
                                extra_settings=extra_settings) as stream:
                while True:
                    try:
                        data, _ = stream.read(FRAME)
                    except sd.PortAudioError:
                        # Mic momentarily unavailable (likely active dictation). Recover.
                        break
                    audio = np.frombuffer(bytes(data), dtype=np.int16).flatten()
                    scores = model.predict(audio)
                    score = float(scores.get(args.wakeword, 0.0))
                    now = time.time()
                    if score >= args.threshold and (now - last_trigger) > args.cooldown:
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
