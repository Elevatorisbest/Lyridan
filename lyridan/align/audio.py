"""Audio loading and resampling to 16 kHz mono float32."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import numpy as np

SUPPORTED = (".wav", ".ogg", ".oga", ".flac", ".mp3", ".aif", ".aiff", ".opus")


def load_audio(path: str, sr: int = 16000) -> np.ndarray:
    """Read an audio file as mono float32 at ``sr`` Hz.

    WAV/OGG/FLAC/MP3/AIFF are read with libsndfile; anything else (m4a, wem…)
    needs ffmpeg on the PATH.
    """
    data, rate = None, None
    try:
        import soundfile as sf
        data, rate = sf.read(path, dtype="float32", always_2d=True)
    except Exception as e:  # noqa: BLE001
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError(f"Could not read {os.path.basename(path)} ({e}). "
                               f"Convert it to WAV, OGG, FLAC or MP3 first.") from e
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "a.wav")
            subprocess.run([ffmpeg, "-v", "error", "-y", "-i", path, "-ac", "1", "-ar", str(sr), out], check=True)
            import soundfile as sf
            data, rate = sf.read(out, dtype="float32", always_2d=True)
    mono = data.mean(axis=1).astype(np.float32)
    if rate != sr:
        import soxr
        mono = soxr.resample(mono, rate, sr, quality="HQ").astype(np.float32)
    return mono
