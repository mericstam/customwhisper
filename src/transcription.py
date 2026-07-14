import io
import os
import re
import sys
import numpy as np
import soundfile as sf
from openai import OpenAI

from utils import ConfigManager

# faster-whisper (Windows/Linux + NVIDIA/CPU) and mlx-whisper (Apple Silicon) are
# imported lazily inside their respective backends so each platform only needs the
# one it actually uses installed.

# Only unambiguous spoken disfluencies. Real words like "er" (err), "ah", and
# "mm" are deliberately excluded to avoid eating legitimate transcription.
FILLER_WORDS_PATTERN = re.compile(
    r"(?:\s*[,;:]\s*)?\b(?:uh+|um+|erm+|hm+)\b(?:\s*[,;:])?",
    re.IGNORECASE,
)
SPACING_BEFORE_PUNCTUATION_PATTERN = re.compile(r"\s+([,.!?;:])")
MULTIPLE_SPACES_PATTERN = re.compile(r"[ \t]{2,}")


def remove_filler_words(transcription):
    """
    Remove common single-word disfluencies (um, uh, erm, hmm) while preserving
    punctuation and sentence spacing.
    """
    transcription = FILLER_WORDS_PATTERN.sub("", transcription)
    transcription = SPACING_BEFORE_PUNCTUATION_PATTERN.sub(r"\1", transcription)
    transcription = MULTIPLE_SPACES_PATTERN.sub(" ", transcription)
    transcription = SPACING_BEFORE_PUNCTUATION_PATTERN.sub(r"\1", transcription)
    return transcription.strip()

def resolve_backend(local_model_options):
    """
    Decide which local transcription backend to use.

    'auto' selects mlx-whisper on Apple Silicon (macOS) and faster-whisper
    everywhere else. Explicit 'faster_whisper' / 'mlx_whisper' override it.
    """
    backend = (local_model_options.get('backend') or 'auto').lower()
    if backend == 'auto':
        return 'mlx_whisper' if sys.platform == 'darwin' else 'faster_whisper'
    return backend


def _mlx_repo_for_model(model_name):
    """
    Map a Whisper model name (the same values the 'model' dropdown offers) to its
    mlx-community Hugging Face repo. The org names them uniformly as
    'mlx-community/whisper-<name>-mlx' (e.g. large-v3 -> whisper-large-v3-mlx).
    """
    return f'mlx-community/whisper-{model_name}-mlx'


class MlxLocalModel:
    """
    Thin handle around an mlx-whisper model.

    mlx-whisper has a stateless module-level API (mlx_whisper.transcribe) that
    caches the loaded model internally between calls, so there is no persistent
    model object like faster-whisper's WhisperModel. This wrapper just carries the
    resolved repo/path so transcribe_local() can tell the two backends apart and
    so main.py's warm-model pattern still holds an object.
    """
    backend = 'mlx_whisper'

    def __init__(self, path_or_hf_repo):
        self.path_or_hf_repo = path_or_hf_repo


def _create_mlx_model(local_model_options):
    """Create (and warm up) an mlx-whisper backed local model for Apple Silicon."""
    model_path = local_model_options.get('model_path')
    path_or_hf_repo = model_path or _mlx_repo_for_model(local_model_options['model'])
    ConfigManager.console_print(f'Using mlx-whisper backend: {path_or_hf_repo}')

    model = MlxLocalModel(path_or_hf_repo)

    # Warm up: mlx-whisper loads (and downloads, if needed) the weights lazily on
    # the first transcribe. Do a tiny silent pass now so the first real dictation
    # isn't stalled by a model download/load.
    try:
        import mlx_whisper
        mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32),
                               path_or_hf_repo=path_or_hf_repo,
                               language='en',
                               verbose=None)
        ConfigManager.console_print('mlx-whisper model warmed up.')
    except Exception as e:
        ConfigManager.console_print(f'mlx-whisper warm-up skipped: {e}')

    return model


def _create_faster_whisper_model(local_model_options):
    """Create a faster-whisper WhisperModel (Windows/Linux, NVIDIA/CPU)."""
    from faster_whisper import WhisperModel

    compute_type = local_model_options['compute_type']
    model_path = local_model_options.get('model_path')

    if compute_type == 'int8':
        device = 'cpu'
        ConfigManager.console_print('Using int8 quantization, forcing CPU usage.')
    else:
        device = local_model_options['device']

    try:
        if model_path:
            ConfigManager.console_print(f'Loading model from: {model_path}')
            model = WhisperModel(model_path,
                                 device=device,
                                 compute_type=compute_type,
                                 download_root=None)  # Prevent automatic download
        else:
            model = WhisperModel(local_model_options['model'],
                                 device=device,
                                 compute_type=compute_type)
    except Exception as e:
        ConfigManager.console_print(f'Error initializing WhisperModel: {e}')
        ConfigManager.console_print('Falling back to CPU.')
        model = WhisperModel(model_path or local_model_options['model'],
                             device='cpu',
                             compute_type=compute_type,
                             download_root=None)

    return model


def create_local_model():
    """
    Create a local transcription model, dispatching to the platform-appropriate
    backend (mlx-whisper on Apple Silicon, faster-whisper otherwise).
    """
    ConfigManager.console_print('Creating local model...')
    local_model_options = ConfigManager.get_config_section('model_options')['local']
    backend = resolve_backend(local_model_options)

    if backend == 'mlx_whisper':
        model = _create_mlx_model(local_model_options)
    else:
        model = _create_faster_whisper_model(local_model_options)

    ConfigManager.console_print('Local model created.')
    return model

def transcribe_local(audio_data, local_model=None):
    """
    Transcribe an audio file using a local model.
    """
    if not local_model:
        local_model = create_local_model()
    model_options = ConfigManager.get_config_section('model_options')
    common = model_options['common']
    local_opts = model_options['local']

    # Convert int16 to float32
    audio_data_float = audio_data.astype(np.float32) / 32768.0

    if isinstance(local_model, MlxLocalModel):
        import mlx_whisper
        # mlx-whisper mirrors faster-whisper's decode options except vad_filter
        # (we do our own webrtcvad silence detection in result_thread.py).
        result = mlx_whisper.transcribe(
            audio_data_float,
            path_or_hf_repo=local_model.path_or_hf_repo,
            language=common['language'],
            initial_prompt=common['initial_prompt'],
            condition_on_previous_text=local_opts['condition_on_previous_text'],
            temperature=common['temperature'],
            verbose=None,
        )
        return result['text']

    response = local_model.transcribe(audio=audio_data_float,
                                      language=common['language'],
                                      initial_prompt=common['initial_prompt'],
                                      condition_on_previous_text=local_opts['condition_on_previous_text'],
                                      temperature=common['temperature'],
                                      vad_filter=local_opts['vad_filter'],)
    return ''.join([segment.text for segment in list(response[0])])

def transcribe_api(audio_data):
    """
    Transcribe an audio file using the OpenAI API.
    """
    model_options = ConfigManager.get_config_section('model_options')
    client = OpenAI(
        api_key=os.getenv('OPENAI_API_KEY') or None,
        base_url=model_options['api']['base_url'] or 'https://api.openai.com/v1'
    )

    # Convert numpy array to WAV file
    byte_io = io.BytesIO()
    sample_rate = ConfigManager.get_config_section('recording_options').get('sample_rate') or 16000
    sf.write(byte_io, audio_data, sample_rate, format='wav')
    byte_io.seek(0)

    response = client.audio.transcriptions.create(
        model=model_options['api']['model'],
        file=('audio.wav', byte_io, 'audio/wav'),
        language=model_options['common']['language'],
        prompt=model_options['common']['initial_prompt'],
        temperature=model_options['common']['temperature'],
    )
    return response.text

def post_process_transcription(transcription):
    """
    Apply post-processing to the transcription.
    """
    transcription = transcription.strip()
    post_processing = ConfigManager.get_config_section('post_processing')
    if post_processing.get('remove_filler_words'):
        transcription = remove_filler_words(transcription)
    if post_processing['remove_trailing_period'] and transcription.endswith('.'):
        transcription = transcription[:-1]
    if post_processing['add_trailing_space']:
        transcription += ' '
    if post_processing['remove_capitalization']:
        transcription = transcription.lower()

    return transcription

def transcribe(audio_data, local_model=None):
    """
    Transcribe audio date using the OpenAI API or a local model, depending on config.
    """
    if audio_data is None:
        return ''

    if ConfigManager.get_config_value('model_options', 'use_api'):
        transcription = transcribe_api(audio_data)
    else:
        transcription = transcribe_local(audio_data, local_model)

    return post_process_transcription(transcription)

