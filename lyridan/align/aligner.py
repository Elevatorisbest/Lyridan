"""Audio forced alignment of lyric lines (experimental)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from ..model import Line, SourceLine, SourceLyrics, SourcePiece
from ..settings import Settings

ProgressFn = Callable[[str, float], bool]  # (message, 0..1) -> False to cancel

CHUNK_S = 20.0       # inference chunk length
OVERLAP_S = 1.0      # context on each side of a chunk
PRE_ROLL_S = 0.6     # search this much before the LRC timestamp
ANCHOR_WEIGHT = 0.5  # log-prob penalty per second the line starts away from its timestamp
SKIP_FLOOR = float(np.log(0.2))  # cost per skipped frame before a line: like silence, but capped
POST_ROLL_S = 0.25   # ...and after the next line's timestamp
MAX_SHIFT_S = 4.0    # a line found further than this from its timestamp keeps the estimate


@dataclass
class LineResult:
    index: int
    text: str
    aligned: bool
    confidence: float
    shift: float = 0.0      # aligned first syllable - LRC timestamp (s)
    reason: str = ""


@dataclass
class AlignmentReport:
    lines: List[LineResult] = field(default_factory=list)
    offset: float = 0.0            # audio time - lyrics time
    offset_detected: bool = False
    offset_note: str = ""
    timeline_shift: float = 0.0    # subtracted from audio times when saving
    readings: list = field(default_factory=list)   # ReadingChange: readings changed by listening
    audio_kind: str = ""           # "chart" | "song" | "other"

    @property
    def aligned(self) -> int:
        return sum(1 for l in self.lines if l.aligned)

    @property
    def total(self) -> int:
        return len(self.lines)

    def summary(self) -> str:
        bad = [l for l in self.lines if not l.aligned]
        kind = {"chart": "your chart's audio (intro silence + empty bars)", "song": "the original song",
                "other": "an audio file with an unknown offset"}.get(self.audio_kind, "the audio")
        s = (f"Aligned {self.aligned} of {self.total} lines to the audio. The lyrics were found "
             f"{self.offset:+.2f} s into the audio{' (detected automatically)' if self.offset_detected else ''}, "
             f"which looks like {kind}.")
        if bad:
            s += f" {len(bad)} line(s) kept estimated timing - check them by ear."
        changed = [r for r in self.readings if r.applied]
        suggested = [r for r in self.readings if not r.applied]
        if changed:
            s += " Japanese readings changed after listening: " + ", ".join(
                f"{r.surface} {r.old} → {r.new}" for r in changed) + "."
        if suggested:
            s += " The audio also suggests (not changed - check by ear): " + ", ".join(
                f"{r.surface} {r.old} → {r.new}?" for r in suggested) + "."
        return s


# ---------------------------------------------------------------------------
class OnnxAligner:
    def __init__(self, model_path: str, meta: dict):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])
        self.labels: List[str] = list(meta["labels"])
        self.blank = int(meta.get("blank", 0))
        self.sr = int(meta.get("sample_rate", 16000))
        self.index = {c: i for i, c in enumerate(self.labels)}

    def _run(self, audio: np.ndarray) -> np.ndarray:
        x = audio.astype(np.float32)
        x = (x - x.mean()) / np.sqrt(x.var() + 1e-5)
        return self.session.run(None, {"audio": x[None, :]})[0][0]

    def emissions(self, audio: np.ndarray, progress: Optional[ProgressFn] = None) -> Tuple[np.ndarray, float]:
        """Log-probabilities for the whole song, computed in overlapping chunks.

        Returns (frames x labels, seconds per frame).
        """
        sr = self.sr
        n = len(audio)
        chunk, ov = int(CHUNK_S * sr), int(OVERLAP_S * sr)
        fps = 50.0  # wav2vec2: 20 ms frames
        total_frames = int(np.ceil(n / sr * fps))
        out = np.full((total_frames, len(self.labels)), -1e4, dtype=np.float32)
        out[:, self.blank] = 0.0
        starts = list(range(0, n, chunk))
        for k, s in enumerate(starts):
            a, b = max(0, s - ov), min(n, s + chunk + ov)
            seg = audio[a:b]
            if len(seg) < sr // 2:
                continue
            lp = self._run(seg)
            spf = (len(seg) / sr) / lp.shape[0]
            for f in range(lp.shape[0]):
                t = a / sr + (f + 0.5) * spf
                if s / sr <= t < min(n, s + chunk) / sr:
                    gi = int(t * fps)
                    if 0 <= gi < total_frames:
                        out[gi] = lp[f]
            if progress and progress("Listening to the song…", (k + 1) / len(starts)) is False:
                raise InterruptedError("Cancelled")
        return out, 1.0 / fps


def detect_offset(em: np.ndarray, spf: float, line_starts: Sequence[float], blank: int = 0,
                  search: Tuple[float, float] = (-10.0, 60.0), prior: Optional[float] = None
                  ) -> Tuple[float, float, str]:
    """Find the shift between lyric timestamps and the audio.

    Vocal activity (1 - P(blank)) should rise right after every line timestamp, so
    the shift whose onsets line up best with the timestamps wins. Returns
    (offset, contrast, note). ``prior`` (e.g. intro silence + empty bars from the
    chart settings) is used when the audio evidence is ambiguous.
    """
    v = 1.0 - np.exp(em[:, blank].astype(np.float64))
    fps = 1.0 / spf
    cs = np.concatenate([[0.0], np.cumsum(v)])
    starts = np.asarray([t for t in line_starts if t is not None], dtype=np.float64)
    if len(starts) < 3:
        return (prior or 0.0), 0.0, "too few lines to detect the offset"

    def mean(a, b):
        ia = np.clip((a * fps).astype(int), 0, len(v) - 1)
        ib = np.clip((b * fps).astype(int), 1, len(v))
        return (cs[ib] - cs[ia]) / np.maximum(ib - ia, 1)

    cands = np.arange(search[0], search[1], 0.02)
    scores = np.array([np.mean(mean(starts + d, starts + d + 1.5) - mean(starts + d - 0.6, starts + d))
                       for d in cands])
    i = int(scores.argmax())
    best, top = float(cands[i]), float(scores[i])
    far = np.abs(cands - best) > 1.0
    runner = float(scores[far].max()) if far.any() else 0.0
    if prior is not None:
        j = int(np.abs(cands - prior).argmin())
        lo, hi = max(0, j - 50), min(len(cands), j + 51)       # +-1 s around the prior
        k = lo + int(scores[lo:hi].argmax())
        if top - scores[k] < 0.15 * max(top, 1e-6):         # prior region is nearly as good
            best, top = float(cands[k]), float(scores[k])
    note = "" if top > 1.2 * max(runner, 1e-6) else "offset detection was not clear-cut - check the first lines"
    return best, top, note


def to_model_text(s: str) -> str:
    """Lower-case ASCII letters + apostrophe, as the MMS aligner expects (uroman-style)."""
    t = unicodedata.normalize("NFKD", s.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("ß", "ss").replace("æ", "ae").replace("œ", "oe").replace("’", "'")
    return re.sub(r"[^a-z']", "", t)


def ctc_align(logp: np.ndarray, tokens: Sequence[int], blank: int = 0,
              start_cost: Optional[np.ndarray] = None):
    """CTC Viterbi forced alignment with free (unaligned) audio before and after.

    ``start_cost[t]`` (<= 0) is added when the sung text starts at frame t; it keeps
    the line near its LRC timestamp unless the audio clearly says otherwise.
    Returns (list of (first_frame, last_frame) per token, mean token probability)
    or None if the text cannot fit.
    """
    T = logp.shape[0]
    L = len(tokens)
    if L == 0 or T < L:
        return None
    # skipped audio before the line costs like silence (capped, so other singing can be skipped too);
    # without this the path would start every line one frame late for free
    skip = np.maximum(logp[:, blank].astype(np.float64), SKIP_FLOOR)
    prefix = np.concatenate(([0.0], np.cumsum(skip)))[:T]
    S = 2 * L + 1
    lab = np.full(S, blank, dtype=np.int64)
    lab[1::2] = tokens
    # skip transition (s-2 -> s) allowed for tokens that differ from the token two states back
    can_skip = np.zeros(S, dtype=bool)
    for s in range(3, S, 2):
        can_skip[s] = lab[s] != lab[s - 2]
    NEG = -1e30
    dp = np.full(S, NEG, dtype=np.float64)
    bp = np.zeros((T, S), dtype=np.int8)       # 0 stay, 1 from s-1, 2 from s-2, 3 start here
    best_end, best_t, best_s = NEG, -1, -1
    for t in range(T):
        e = logp[t, lab].astype(np.float64)
        stay = dp
        prev1 = np.concatenate(([NEG], dp[:-1]))
        prev2 = np.concatenate(([NEG, NEG], dp[:-2]))
        prev2 = np.where(can_skip, prev2, NEG)
        cand = np.stack([stay, prev1, prev2])
        arg = cand.argmax(axis=0)
        val = cand.max(axis=0)
        # free start: the path may begin at frame t in state 0 or 1
        start = np.full(S, NEG)
        sc = prefix[t] + (0.0 if start_cost is None else float(start_cost[t]))
        start[0] = sc
        start[1] = sc
        use_start = start > val
        val = np.where(use_start, start, val)
        arg = np.where(use_start, 3, arg)
        dp = val + e
        bp[t] = arg
        for s_end in (S - 1, S - 2):
            if dp[s_end] > best_end:
                best_end, best_t, best_s = dp[s_end], t, s_end
    if best_t < 0:
        return None
    spans: List[List[int]] = [[-1, -1] for _ in range(L)]
    probs: List[float] = [0.0] * L
    s, t = best_s, best_t
    while t >= 0:
        if s % 2 == 1:
            k = (s - 1) // 2
            spans[k][0] = t
            if spans[k][1] < 0:
                spans[k][1] = t
            probs[k] = max(probs[k], float(np.exp(logp[t, lab[s]])))
        move = bp[t, s]
        if move == 3:
            break
        s -= int(move)
        t -= 1
    if any(a < 0 for a, _ in spans):
        return None
    return [(a, b) for a, b in spans], float(np.mean(probs))


def ctc_score(logp: np.ndarray, tokens: Sequence[int], blank: int = 0) -> float:
    """Log-likelihood of the text over the *whole* window (skipped audio before and
    after is charged like silence), so different texts for the same audio can be
    compared fairly. Higher is better."""
    T = logp.shape[0]
    L = len(tokens)
    if L == 0 or T < L:
        return float("-inf")
    skip = np.maximum(logp[:, blank].astype(np.float64), SKIP_FLOOR)
    prefix = np.concatenate(([0.0], np.cumsum(skip)))
    S = 2 * L + 1
    lab = np.full(S, blank, dtype=np.int64)
    lab[1::2] = tokens
    can_skip = np.zeros(S, dtype=bool)
    for k in range(3, S, 2):
        can_skip[k] = lab[k] != lab[k - 2]
    NEG = -1e30
    dp = np.full(S, NEG)
    best = NEG
    for t in range(T):
        e = logp[t, lab].astype(np.float64)
        prev1 = np.concatenate(([NEG], dp[:-1]))
        prev2 = np.where(can_skip, np.concatenate(([NEG, NEG], dp[:-2])), NEG)
        val = np.maximum(np.maximum(dp, prev1), prev2)
        val[0] = max(val[0], prefix[t])
        val[1] = max(val[1], prefix[t])
        dp = val + e
        tail = prefix[T] - prefix[t + 1]           # audio after the text, charged like silence
        best = max(best, dp[S - 1] + tail, dp[S - 2] + tail)
    return float(best)


# ---------------------------------------------------------------------------
def align_lyrics(source: SourceLyrics, audio_path: str, settings: Settings, model_path: str, meta: dict,
                 progress: Optional[ProgressFn] = None, audio: Optional[np.ndarray] = None,
                 offset: Optional[float] = None, offset_prior: Optional[float] = None
                 ) -> Tuple[SourceLyrics, AlignmentReport]:
    """Align line-synced lyrics to the song audio; returns syllable-synced lyrics + report.

    ``offset`` = audio time minus lyric time if known; otherwise it is detected from
    the audio (``offset_prior`` helps when detection is ambiguous). The returned
    lyrics stay on the *lyrics'* timeline, so the normal sync settings still apply.
    """
    from ..pipeline import process
    from .audio import load_audio

    if progress:
        progress("Reading audio…", 0.0)
    if audio is None:
        audio = load_audio(audio_path)
    aligner = OnnxAligner(model_path, meta)
    em, spf = aligner.emissions(audio, progress)
    song_len = len(audio) / aligner.sr

    s = Settings.from_json(settings.to_json())
    s.background = "exclude"
    report = AlignmentReport()
    main_starts = [l.start for l in source.lines if not l.background and l.start is not None]
    if offset is None:
        if progress:
            progress("Finding where the lyrics start in the audio…", 1.0)
        offset, _, note = detect_offset(em, spf, main_starts, aligner.blank, prior=offset_prior)
        report.offset_detected = True
        report.offset_note = note
    report.offset = offset
    # Save times so that Lyridan's sync settings reproduce exactly what was heard:
    #   chart audio (offset ~ intro silence + empty bars): times = audio time - that shift
    #   original song (offset ~ 0): times = audio time
    #   anything else: keep the lyrics' own timeline
    if offset_prior is not None and abs(offset - offset_prior) <= 2.0:
        report.audio_kind, report.timeline_shift = "chart", offset_prior
    elif abs(offset) <= 2.0:
        report.audio_kind, report.timeline_shift = "song", 0.0
    else:
        report.audio_kind, report.timeline_shift = "other", offset
        report.offset_note = (report.offset_note + "; " if report.offset_note else "") + \
            "the audio does not match the chart's sync settings - check the offset after loading"
    # Japanese: let the audio decide between dictionary and lyric readings (緋 hi / aka)
    from ..pipeline import detect_language
    if settings.verify_readings and any(detect_language(l.text) == "ja" for l in source.lines
                                        if not l.background):
        from .readings import verify_readings
        source = SourceLyrics(lines=list(source.lines), language=source.language, title=source.title,
                              artist=source.artist, lyric_offset=source.lyric_offset,
                              leading_silence=source.leading_silence, timing=source.timing,
                              has_romaji=source.has_romaji, path=source.path)
        source, report.readings = verify_readings(source, em, spf, offset, s.ja, aligner.index, aligner.blank,
                                                  progress)
    processed = process(source, s)
    src_lines = source.lines
    out_lines: List[SourceLine] = []
    lines = [l for l in processed.lines if not l.background]

    for n, ln in enumerate(lines):
        sl = src_lines[ln.index]
        t0 = (sl.start if sl.start is not None else ln.start) + offset
        nxt = None
        for m in lines[n + 1:]:
            st = src_lines[m.index].start
            if st is not None and st + offset > t0:
                nxt = st + offset
                break
        t1 = nxt if nxt is not None else min(song_len, t0 + 4.0 + 0.7 * sum(1 for _ in ln.syllables()))
        ws = max(0.0, t0 - PRE_ROLL_S)
        we = min(song_len, t1 + POST_ROLL_S)
        f0, f1 = int(ws / spf), max(int(ws / spf) + 1, int(we / spf))
        window = em[f0:f1]

        sylls = list(ln.syllables())
        tokens: List[int] = []
        owner: List[int] = []
        for si, sy in enumerate(sylls):
            for ch in to_model_text(sy.text):
                if ch in aligner.index:
                    tokens.append(aligner.index[ch])
                    owner.append(si)
        frame_t = (f0 + np.arange(len(window))) * spf
        cost = -ANCHOR_WEIGHT * np.abs(frame_t - t0)
        res = ctc_align(window, tokens, aligner.blank, cost) if tokens else None
        ok = False
        conf = 0.0
        reason = ""
        if res is None:
            reason = "text does not fit the audio window"
        else:
            spans, conf = res
            first = (f0 + spans[0][0]) * spf
            last = (f0 + spans[-1][1] + 1) * spf
            if abs(first - t0) > MAX_SHIFT_S:
                reason = f"found {first - t0:+.1f} s away from its timestamp"
            elif last - first < 0.06 * len(sylls):
                reason = "alignment collapsed"
            else:
                ok = True
                starts: List[Optional[float]] = [None] * len(sylls)
                ends: List[Optional[float]] = [None] * len(sylls)
                for (a, b), si in zip(spans, owner):
                    ta, tb = (f0 + a) * spf, (f0 + b + 1) * spf
                    starts[si] = ta if starts[si] is None else min(starts[si], ta)
                    ends[si] = tb if ends[si] is None else max(ends[si], tb)
                _fill_missing(starts, ends)
                durs = [max(0.05, (starts[i + 1] - starts[i])) for i in range(len(sylls) - 1)]
                typical = float(np.median(durs)) if durs else 0.3
                limit = (nxt - 0.05) if nxt is not None else song_len
                for i, sy in enumerate(sylls):
                    sy.start = starts[i]
                    if i + 1 < len(sylls):
                        gap = starts[i + 1] - starts[i]
                        sy.end = starts[i + 1] if gap <= max(0.9, 2.5 * typical) else \
                            starts[i] + max(ends[i] - starts[i], min(gap, 2.0 * typical))
                    else:
                        sy.end = min(limit, starts[i] + max(ends[i] - starts[i], 0.35, 2.5 * typical))
                    sy.end = max(sy.end, sy.start + 0.03)
                for sy in sylls:
                    sy.start -= report.timeline_shift
                    sy.end -= report.timeline_shift
        if not ok:  # estimated timing: move it onto the same timeline
            for sy in sylls:
                sy.start += offset - report.timeline_shift
                sy.end += offset - report.timeline_shift
        report.lines.append(LineResult(ln.index, ln.source_text, ok, conf,
                                       (sylls[0].start + report.timeline_shift - t0) if ok else 0.0, reason))
        out_lines.append(_to_source_line(ln, sl))
        if progress and progress("Aligning lines…", (n + 1) / max(1, len(lines))) is False:
            raise InterruptedError("Cancelled")

    # background lines (parenthesised parts) keep their line timing
    d = offset - report.timeline_shift
    for sl in src_lines:
        if sl.background:
            out_lines.append(SourceLine([SourcePiece(p.text, None if p.start is None else p.start + d,
                                                     None if p.end is None else p.end + d, p.joined)
                                         for p in sl.pieces],
                                        None if sl.start is None else sl.start + d,
                                        None if sl.end is None else sl.end + d, True, sl.agent, sl.key,
                                        sl.section))
    out_lines.sort(key=lambda l: (l.start if l.start is not None else 0.0))
    aligned = SourceLyrics(lines=out_lines, language=source.language or processed.language,
                           title=source.title, artist=source.artist, timing="syllable",
                           has_romaji=any(l.romaji for l in out_lines), path=source.path)
    return aligned, report


def _fill_missing(starts: List[Optional[float]], ends: List[Optional[float]]):
    """Syllables without letters (rare) get times between their neighbours."""
    n = len(starts)
    for i in range(n):
        if starts[i] is None:
            prev = next((j for j in range(i - 1, -1, -1) if starts[j] is not None), None)
            nxt = next((j for j in range(i + 1, n) if starts[j] is not None), None)
            if prev is not None and nxt is not None:
                starts[i] = starts[prev] + (starts[nxt] - starts[prev]) * (i - prev) / (nxt - prev)
            elif prev is not None:
                starts[i] = (ends[prev] or starts[prev]) + 0.05
            elif nxt is not None:
                starts[i] = max(0.0, starts[nxt] - 0.1)
            else:
                starts[i] = 0.0
            ends[i] = starts[i] + 0.1


def _to_source_line(ln: Line, sl: SourceLine) -> SourceLine:
    """Build Apple-style syllable pieces (native script + romaji transliteration)."""
    native_pieces: List[SourcePiece] = []
    roman_pieces: List[SourcePiece] = []
    needs_romaji = ln.lang in ("ja", "ru")
    for w in ln.words:
        n = len(w.syllables)
        for i, sy in enumerate(w.syllables):
            last = i == n - 1
            nat = sy.native if needs_romaji else sy.text
            pre = w.prefix if i == 0 else ""
            suf = w.suffix if last else ""
            if nat:
                native_pieces.append(SourcePiece(pre + nat + suf, round(sy.start, 3), round(sy.end, 3),
                                                 joined=not last))
            elif native_pieces:  # kanji already shown by the previous syllable: extend it
                native_pieces[-1].end = round(sy.end, 3)
                if last:
                    native_pieces[-1].joined = False
                    native_pieces[-1].text += suf
            if needs_romaji:
                roman_pieces.append(SourcePiece(pre + sy.text + suf, round(sy.start, 3), round(sy.end, 3),
                                                joined=not last))
    if ln.lang == "ja":  # Japanese is written without spaces between words
        for p in native_pieces:
            p.joined = True
    if native_pieces:
        native_pieces[-1].joined = False
    return SourceLine(native_pieces, native_pieces[0].start if native_pieces else sl.start,
                      native_pieces[-1].end if native_pieces else sl.end, sl.background, sl.agent, sl.key,
                      sl.section, roman_pieces or None, sl.translation)
