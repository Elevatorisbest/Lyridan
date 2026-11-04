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
from collections import deque
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
    """Plays the song through PortAudio. ``position()`` is the sample coming out of the speakers.

    Every audio block that is written is remembered with its DAC time and rate, so the position
    stays exact through seeks and speed changes (shuttle fast-forward / rewind): it is computed
    from the newest block that is already audible. Until the first block after a seek is audible,
    the playhead waits at the seek target instead of jumping back by the output latency.
    A negative ``speed`` plays backwards (rewind shuttle).
    """
    HISTORY = 128                           # remembered blocks (a few hundred ms at any latency)

    def __init__(self):
        self.data: Optional[np.ndarray] = None
        self.sr = 44100
        self.path = ""
        self.peaks = np.zeros((0, 2), dtype=np.float32)
        self.volume = 0.8
        self._speed = 1.0
        self.metronome = False
        self.clicks: List[tuple] = []      # (frame, accent)
        self._lock = threading.Lock()
        self._pos = 0.0                     # frame position of the next block to write
        self._blocks = deque(maxlen=self.HISTORY)  # (frame, dac time, rate) of written blocks
        self._anchor = 0.0                  # frame shown until a block is audible (play / seek)
        self._playing = False
        self._stream = None
        self._sd = None
        self._clock_start = None            # silent fallback clock: (perf_counter, frame)
        self._xfade_from: Optional[float] = None  # old position to cross-fade from at a seek (no click)
        self._last_pos = 0.0                # position() never runs against the playing direction
        self.device_error = ""
        self._click_hi = _click(self.sr, 1600)
        self._click_lo = _click(self.sr, 1000)

    @property
    def speed(self) -> float:
        return self._speed

    @speed.setter
    def speed(self, value: float):
        value = float(value)
        if self._clock_start is not None:   # silent clock: rebase so the change applies from now on
            self._clock_start = (time.perf_counter(), self.position() * self.sr)
        self._speed = value

    # ------------------------------------------------------------------ loading
    def load(self, path: str):
        data, sr = decode_audio(path)
        self.stop()
        with self._lock:
            self.data, self.sr, self.path = data, sr, path
            self._pos = 0.0
            self._blocks.clear()
            self._anchor = 0.0
        self.peaks = waveform_peaks(data, sr)
        self._click_hi = _click(sr, 1600)
        self._click_lo = _click(sr, 1000)
        self._close_stream()

    def unload(self):
        self.stop()
        self._close_stream()
        with self._lock:
            self.data, self.path = None, ""
            self._pos = 0.0
            self._blocks.clear()
            self._anchor = 0.0
        self.peaks = np.zeros((0, 2), dtype=np.float32)

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
        self._last_pos = self._pos / self.sr
        if self._ensure_stream():
            with self._lock:
                self._blocks.clear()
                self._anchor = self._pos
                self._xfade_from = None
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
            self._blocks.clear()
            self._anchor = self._pos
            self._xfade_from = None

    def stop(self):
        self.pause()
        self._pos = 0.0

    def toggle(self):
        self.pause() if self._playing else self.play()

    @property
    def playing(self) -> bool:
        if self._playing and self.data is not None and self._speed > 0 and self.position() >= self.duration:
            self.pause()
            self._pos = len(self.data)
        return self._playing

    def seek(self, seconds: float):
        if self.data is None:
            return
        frame = float(min(max(0.0, seconds), self.duration) * self.sr)
        live = self._playing and self._stream is not None and self._clock_start is None
        with self._lock:
            if live and self._xfade_from is None:
                self._xfade_from = self._pos         # what the next block would have played
            self._pos = frame
            self._blocks.clear()                     # nothing written so far is the new position
            self._anchor = frame
        self._last_pos = frame / self.sr
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
            return max(0.0, min(self.duration, (f0 + (time.perf_counter() - t0) * self.sr * self._speed) / self.sr))
        if self._stream is None:
            return self._pos / self.sr
        try:
            now = self._stream.time
        except Exception:  # noqa: BLE001
            return self._pos / self.sr
        with self._lock:
            blocks = list(self._blocks)
            anchor = self._anchor
        heard = None
        for b in reversed(blocks):                   # newest block that is already audible
            if b[1] <= now:
                heard = b
                break
        if heard is None:
            return anchor / self.sr                  # the latest play / seek is not audible yet
        frame, dac, rate = heard
        pos = max(0.0, min(self.duration, (frame + (now - dac) * self.sr * rate) / self.sr))
        last = self._last_pos                        # DAC-timestamp jitter: never step back
        if rate > 0 and last - 0.25 < pos < last:
            pos = last
        elif rate < 0 and last < pos < last + 0.25:
            pos = last
        self._last_pos = pos
        return pos

    # ------------------------------------------------------------------ audio thread
    XFADE_MS = 6.0                          # cross-fade at a seek while playing (avoids a click)

    def _dac_time(self, time_info) -> float:
        """DAC time of this block. Some host APIs report 0 or nonsense; estimate it then."""
        dac = getattr(time_info, "outputBufferDacTime", 0.0) or 0.0
        cur = getattr(time_info, "currentTime", 0.0) or 0.0
        if cur <= 0.0:
            try:
                cur = self._stream.time
            except Exception:  # noqa: BLE001
                cur = 0.0
        if dac <= 0.0 or abs(dac - cur) > 1.0:
            try:
                lat = float(self._stream.latency)
            except Exception:  # noqa: BLE001
                lat = 0.0
            dac = cur + lat
        return dac

    @staticmethod
    def _render(data: np.ndarray, pos: float, frames: int, step: float):
        idx = pos + np.arange(frames) * step
        valid = (idx >= 0) & (idx < len(data) - 1)
        out = np.zeros((frames, data.shape[1]), dtype=np.float32)
        if valid.any():
            i = idx[valid]
            i0 = i.astype(np.int64)
            frac = (i - i0)[:, None].astype(np.float32)
            out[valid] = data[i0] * (1 - frac) + data[i0 + 1] * frac
        return out, valid

    def _callback(self, outdata, frames, time_info, status):  # noqa: ARG002
        data = self.data
        dac = self._dac_time(time_info)
        with self._lock:
            pos = self._pos
            step = self._speed
            if step < 0 and pos <= 0.0:
                step = 0.0                           # rewound to the start: wait there (silence)
            self._blocks.append((pos, dac, step))
            old = self._xfade_from
            self._xfade_from = None
            self._pos = max(0.0, pos + frames * step)
        out, valid = self._render(data, pos, frames, step) if step else \
            (np.zeros((frames, data.shape[1]), dtype=np.float32), None)
        if old is not None and step:                 # fade the pre-seek audio out, the new audio in
            nx = min(frames, max(1, int(self.sr * self.XFADE_MS / 1000)))
            prev, _ = self._render(data, old, nx, step)
            ramp = np.linspace(0.0, 1.0, nx, dtype=np.float32)[:, None]
            out[:nx] = prev * (1 - ramp) + out[:nx] * ramp
        if self.metronome and self.clicks and step > 0:
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
        if step > 0 and not valid.any():
            raise self._sd.CallbackStop()            # played past the end

    def close(self):
        self.pause()
        self._close_stream()
