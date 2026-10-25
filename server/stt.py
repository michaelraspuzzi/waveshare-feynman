"""Speech-to-text with Whisper running locally on Apple Silicon (mlx-whisper)."""
import os

import numpy as np

MODEL = os.environ.get("FEYNMAN_WHISPER", "mlx-community/whisper-small.en-mlx")


def transcribe(pcm16: bytes) -> str:
    import mlx_whisper

    audio = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
    if len(audio) < 16000 * 0.3:
        return ""
    result = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL, language="en")
    return result.get("text", "").strip()


def warm_up():
    transcribe(np.zeros(16000, dtype="<i2").tobytes())
