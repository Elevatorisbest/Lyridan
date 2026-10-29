"""Audio playback for the timeline preview.

Uses PortAudio (sounddevice) with the DAC timestamps of every audio block, so the
playhead matches what you hear (important for judging lyric sync). Without an
audio device it falls back to a silent clock so the preview still runs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
from typing import List, Optional, Sequence

import numpy as np


def decode_audio(path: str):
    """Return (float32 array frames x channels, sample_rate)."""
    import soundfile as sf
    try:
        data, sr = sf.read(path, dtype="float32", always_2d=True)
    except Exception as e:  # noqa: BLE001
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError(f"Could not read {os.path.basename(path)} ({e}). "
                               "Use WAV, OGG, FLAC or MP3.") from e
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "a.wav")
            subprocess.run([ffmpeg, "-v", "error", "-y", "-i", path, out], check=True)
            data, sr = sf.read(out, dtype="float32", always_2d=True)
    if data.shape[1] > 2:
        data = data[:, :2]
    return np.ascontiguousarray(data), int(sr)


def waveform_peaks(data: np.ndarray, sr: int, bins_per_second: int = 100) -> np.ndarray:
    """(n, 2) array of min/max per bin of the mono mix, for drawing."""
    mono = data.mean(axis=1)
    hop = max(1, sr // bins_per_second)
    n = len(mono) // hop
    if n == 0:
        return np.zeros((0, 2), dtype=np.float32)
    m = mono[: n * hop].reshape(n, hop)
    return np.stack([m.min(axis=1), m.max(axis=1)], axis=1).astype(np.float32)


def _click(sr: int, freq: float, ms: float = 28.0) -> np.ndarray:
    t = np.arange(int(sr * ms / 1000)) / sr
    env = np.exp(-t * 90.0)
    return (np.sin(2 * np.pi * freq * t) * env * 0.6).astype(np.float32)


class AudioPlayer:
    def __init__(self):
        self.data: Optional[np.ndarray] = None
        self.sr = 44100
        self.path = ""
        self.peaks = np.zeros((0, 2), dtype=np.float32)
        self.volume = 0.8
        self.speed = 1.0
        self.metronome = False
        self.clicks: List[tuple] = []      # (frame, accent)
        self._lock = threading.Lock()
        self._pos = 0.0                     # frame position of the next block to write
        self._ref = (0.0, 0.0)              # (frame at dac time, dac time) for interpolation
        self._playing = False
        self._stream = None
        self._sd = None
        self._clock_start = None            # silent fallback clock
        self.device_error = ""
        self._click_hi = _click(self.sr, 1600)
        self._click_lo = _click(self.sr, 1000)

    # ------------------------------------------------------------------ loading
    def load(self, path: str):
        data, sr = decode_audio(path)
        self.stop()
        with self._lock:
            self.data, self.sr, self.path = data, sr, path
            self._pos = 0.0
            self._ref = (0.0, 0.0)
        self.peaks = waveform_peaks(data, sr)
        self._click_hi = _click(sr, 1600)
        self._click_lo = _click(sr, 1000)
        self._close_stream()

    @property
    def loaded(self) -> bool:
        return self.data is not None

    @property
    def duration(self) -> float:
        return 0.0 if self.data is None else len(self.data) / self.sr

    def set_beats(self, beats: Sequence[float], measure_flags: Sequence[bool]):
        """Beat times in *audio* seconds for the metronome."""
        self.clicks = [(int(t * self.sr), bool(m)) for t, m in zip(beats, measure_flags) if t >= 0]

    # ------------------------------------------------------------------ transport
    def _ensure_stream(self) -> bool:
        if self._stream is not None:
            return True
        try:
            import sounddevice as sd
            self._sd = sd
            ch = self.data.shape[1] if self.data is not None else 2
            self._stream = sd.OutputStream(samplerate=self.sr, channels=ch, dtype="float32",
                                           callback=self._callback, latency="low")
            self.device_error = ""
            return True
        except Exception as e:  # noqa: BLE001  (no PortAudio / no output device)
            self._stream = None
            self.device_error = str(e) or "no audio output device"
            return False

    def _close_stream(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
        self._stream = None

    def play(self):
        if self.data is None or self._playing:
            return
        if self._pos >= len(self.data) - 1:
            self._pos = 0.0
        self._playing = True
        if self._ensure_stream():
            with self._lock:
                self._ref = (self._pos, None)
            try:
                self._stream.start()
                return
            except Exception as e:  # noqa: BLE001
                self.device_error = str(e)
                self._close_stream()
        self._clock_start = (time.perf_counter(), self._pos)

    def pause(self):
        if not self._playing:
            return
        self._pos = self.position() * self.sr
        self._playing = False
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:  # noqa: BLE001
                pass
        self._clock_start = None
        with self._lock:
            self._ref = (self._pos, None)

    def stop(self):
        self.pause()
        self._pos = 0.0

    def toggle(self):
        self.pause() if self._playing else self.play()

    @property
    def playing(self) -> bool:
        if self._playing and self.data is not None and self.position() >= self.duration:
            self.pause()
            self._pos = len(self.data)
        return self._playing

    def seek(self, seconds: float):
        if self.data is None:
            return
        frame = float(min(max(0.0, seconds), self.duration) * self.sr)
        with self._lock:
            self._pos = frame
            self._ref = (frame, None)
        if self._clock_start is not None:
            self._clock_start = (time.perf_counter(), frame)

    def position(self) -> float:
        """Seconds of the sample currently coming out of the speakers."""
        if self.data is None:
            return 0.0
        if not self._playing:
            return self._pos / self.sr
        if self._clock_start is not None:  # silent fallback
            t0, f0 = self._clock_start
            return min(self.duration, (f0 + (time.perf_counter() - t0) * self.sr * self.speed) / self.sr)
        with self._lock:
            frame, dac = self._ref
        if dac is None or self._stream is None:
            return frame / self.sr
        try:
            now = self._stream.time
        except Exception:  # noqa: BLE001
            return frame / self.sr
        return max(0.0, min(self.duration, (frame + (now - dac) * self.sr * self.speed) / self.sr))

    # ------------------------------------------------------------------ audio thread
    def _callback(self, outdata, frames, time_info, status):  # noqa: ARG002
        data = self.data
        with self._lock:
            pos = self._pos
            self._ref = (pos, time_info.outputBufferDacTime)
            step = self.speed
            idx = pos + np.arange(frames) * step
            self._pos = pos + frames * step
        n = len(data)
        valid = idx < n - 1
        out = np.zeros((frames, data.shape[1]), dtype=np.float32)
        if valid.any():
            i = idx[valid]
            i0 = i.astype(np.int64)
            frac = (i - i0)[:, None].astype(np.float32)
            out[valid] = data[i0] * (1 - frac) + data[i0 + 1] * frac
        if self.metronome and self.clicks:
            a, b = int(pos), int(pos + frames * step)
            for f, accent in self.clicks:
                if a - 2000 <= f < b:
                    snd = self._click_hi if accent else self._click_lo
                    off = int((f - pos) / step)
                    s0 = max(0, off)
                    k0 = s0 - off
                    k1 = min(len(snd), k0 + frames - s0)
                    if k1 > k0:
                        out[s0:s0 + (k1 - k0)] += snd[k0:k1, None]
        np.clip(out * self.volume, -1.0, 1.0, out=out)
        outdata[:] = out
        if not valid.any():
            raise self._sd.CallbackStop()

    def close(self):
        self.pause()
        self._close_stream()
