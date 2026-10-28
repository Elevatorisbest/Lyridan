"""Experimental: turn line-synced lyrics (.lrc) into syllable-synced lyrics using the song audio.

How it works
  1. The lyrics are processed as usual (syllables, romanization) so every syllable
     has Latin text.
  2. For every lyric line a window of audio is cut around the line's LRC timestamp
     (the LRC timing is used as an anchor, so errors cannot spread across lines).
  3. Meta's multilingual MMS forced-alignment model (wav2vec2, 1100+ languages,
     run through ONNX Runtime) gives per-frame character probabilities (20 ms frames).
  4. CTC Viterbi forced alignment finds the most likely time of every character;
     syllable times are taken from their characters.
  5. Lines the model is unsure about keep the estimated timing and are reported.

The result is written as a syllable-synced TTML file (Apple-style, with a
ja-Latn / ru-Latn transliteration block when the lyrics are not English).
"""
from .aligner import AlignmentReport, align_lyrics  # noqa: F401
from .model_store import MODEL_INFO, ModelStore  # noqa: F401
