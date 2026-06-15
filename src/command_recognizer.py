"""
In-dictation voice command recognizer for WhisperWriter.

Uses Vosk (offline, streaming) with a grammar constrained to a small set of
command phrases, so it reliably detects commands like "jarvis session hold"
spoken during a dictation, while ignoring normal speech.

Returns one of: 'hold', 'resume', 'stop', 'cancel' (or None).
"""
import json

from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)  # silence Vosk's verbose logging

# Natural-language variants mapped to actions. The user need not say an exact
# rigid phrase -- any of these works. Keep them lowercase, single-spaced.
DEFAULT_COMMANDS = {
    "hold": [
        "jarvis hold", "jarvis pause",
    ],
    "resume": [
        "jarvis continue", "jarvis resume", "jarvis go on",
    ],
    "stop": [
        "jarvis end session", "jarvis stop session",
    ],
    "cancel": [
        "jarvis cancel session", "jarvis cancel",
    ],
}

_MODEL = None


def _get_model():
    """Load the small English Vosk model once and cache it (auto-downloaded)."""
    global _MODEL
    if _MODEL is None:
        _MODEL = Model(lang="en-us")
    return _MODEL


def _norm(text):
    return " ".join(text.lower().split())


class CommandRecognizer:
    def __init__(self, commands=None, sample_rate=16000):
        commands = commands or DEFAULT_COMMANDS
        # phrase -> action map (normalized)
        self.phrase_to_action = {}
        for action, phrases in commands.items():
            for p in phrases:
                self.phrase_to_action[_norm(p)] = action

        self.sample_rate = sample_rate
        self.model = _get_model()
        grammar = json.dumps(sorted(self.phrase_to_action.keys()) + ["[unk]"])
        self._grammar = grammar
        self.rec = KaldiRecognizer(self.model, sample_rate, grammar)
        self._frames_in_phrase = 0  # frames elapsed since the current command word onset

    def reset(self):
        """Start a fresh recognition (e.g. at the start of each dictation)."""
        self.rec = KaldiRecognizer(self.model, self.sample_rate, self._grammar)
        self._frames_in_phrase = 0

    def process(self, frame_bytes):
        """
        Feed one audio frame (int16 PCM bytes at sample_rate).
        Returns (action, frames_since_command_started) when a command phrase
        completes, else (None, 0). The frame count lets the caller trim exactly
        the command audio out of the recording.
        """
        try:
            if self.rec.AcceptWaveform(frame_bytes):
                text = json.loads(self.rec.Result()).get("text", "")
            else:
                text = json.loads(self.rec.PartialResult()).get("partial", "")
        except Exception:
            return None, 0

        text = _norm(text)
        if not text:
            # No command words being heard -> reset the onset counter.
            self._frames_in_phrase = 0
            return None, 0

        # A command word is being heard; count how long it's been going.
        self._frames_in_phrase += 1

        for phrase, action in self.phrase_to_action.items():
            if text == phrase or text.endswith(" " + phrase):
                frames = self._frames_in_phrase
                self.reset()
                return action, frames
        return None, 0
