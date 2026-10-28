"""Character-window boundary model used to syllabize words that are not in a dictionary.

A linear (averaged perceptron) model scores every gap between two letters;
the decoder then picks the best set of boundaries, optionally constrained to
an exact syllable count (from the CMU Pronouncing Dictionary for English).
The model is trained by ``tools/train_english_model.py`` on the curated
English syllable dictionary, so unknown words are split in the same style.
"""
from __future__ import annotations

import gzip
import json
from typing import Dict, Iterable, List, Optional, Sequence

VOWELS = set("aeiouyàáâäèéêëìíîïòóôöùúûüæœ")


def cv(c: str) -> str:
    if c in VOWELS:
        return "V"
    if c == "'":
        return "'"
    if c in "^$":
        return c
    return "C"


def gap_features(word: str, i: int) -> List[str]:
    """Features for a boundary *before* word[i] (1 <= i < len(word))."""
    w = "^^^^" + word + "$$$$"
    j = i + 4  # index in padded string of the char right after the gap
    feats = ["b"]
    for start in range(-4, 4):
        for n in range(1, 6):
            if start + n > 4:
                continue
            feats.append(f"{start},{w[j + start: j + start + n]}")
    pat = "".join(cv(c) for c in w[j - 4: j + 4])
    feats.append("p" + pat)
    feats.append("p5" + pat[1:6])
    feats.append("p3" + pat[2:5])
    feats.append(f"l{min(i, 5)}")
    feats.append(f"r{min(len(word) - i, 5)}")
    feats.append(f"lr{min(i, 4)},{min(len(word) - i, 4)}")
    return feats


class BoundaryModel:
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.w: Dict[str, float] = weights or {}

    @classmethod
    def load(cls, path: str) -> "BoundaryModel":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return cls(json.load(fh))

    def save(self, path: str) -> None:
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(self.w, fh, separators=(",", ":"))

    def scores(self, word: str) -> List[float]:
        """Score for a boundary before each position 1..len-1 (index 0 unused)."""
        w = self.w
        out = [0.0]
        for i in range(1, len(word)):
            out.append(sum(w.get(f, 0.0) for f in gap_features(word, i)))
        return out

    # ---- decoding -------------------------------------------------------------
    @staticmethod
    def _has_vowel(seg: str) -> bool:
        return any(c in VOWELS for c in seg)

    def decode(self, word: str, counts: Optional[Iterable[int]] = None) -> List[int]:
        """Return boundary positions. ``counts`` = allowed syllable counts (or None)."""
        n = len(word)
        if n <= 1:
            return []
        sc = self.scores(word)
        lw = word.lower()
        nvow_groups = max(1, sum(1 for k in range(n) if lw[k] in VOWELS and (k == 0 or lw[k - 1] not in VOWELS)))
        if counts:
            cands = sorted({c for c in counts if 1 <= c <= n})
        else:
            cands = None
        if cands is None:
            # unconstrained: every positive gap, then repair vowel-less syllables
            cuts = [i for i in range(1, n) if sc[i] > 0]
            return self._repair(lw, cuts, sc)
        best, best_val = None, None
        for k in cands:
            res = self._best_k(lw, sc, k)
            if res is None:
                continue
            val, cuts = res
            # mild prior towards vowel-group count
            val -= 0.15 * abs(k - nvow_groups)
            if best_val is None or val > best_val:
                best, best_val = cuts, val
        if best is None:
            cuts = [i for i in range(1, n) if sc[i] > 0]
            return self._repair(lw, cuts, sc)
        return best

    def _best_k(self, lw: str, sc: List[float], k: int):
        """Best k-syllable segmentation where each syllable holds a vowel."""
        n = len(lw)
        NEG = float("-inf")
        # dp[j][m]: best score splitting lw[:j] into m syllables, last ends at j
        dp = [[NEG] * (k + 1) for _ in range(n + 1)]
        bp = [[-1] * (k + 1) for _ in range(n + 1)]
        dp[0][0] = 0.0
        has_v_prefix = [0] * (n + 1)
        for i, c in enumerate(lw):
            has_v_prefix[i + 1] = has_v_prefix[i] + (1 if c in VOWELS else 0)
        for j in range(1, n + 1):
            for m in range(1, k + 1):
                for i in range(m - 1, j):
                    if dp[i][m - 1] == NEG:
                        continue
                    if has_v_prefix[j] - has_v_prefix[i] == 0:
                        continue
                    val = dp[i][m - 1] + (sc[i] if i > 0 else 0.0)
                    if val > dp[j][m]:
                        dp[j][m] = val
                        bp[j][m] = i
        if dp[n][k] == NEG:
            return None
        cuts = []
        j, m = n, k
        while m > 0:
            i = bp[j][m]
            if i > 0:
                cuts.append(i)
            j, m = i, m - 1
        return dp[n][k], sorted(cuts)

    def _repair(self, lw: str, cuts: List[int], sc: List[float]) -> List[int]:
        cuts = sorted(cuts)
        changed = True
        while changed and cuts:
            changed = False
            bounds = [0] + cuts + [len(lw)]
            for idx in range(len(bounds) - 1):
                seg = lw[bounds[idx]:bounds[idx + 1]]
                if not self._has_vowel(seg):
                    # drop the weaker adjacent cut
                    left = bounds[idx] if idx > 0 else None
                    right = bounds[idx + 1] if idx + 1 < len(bounds) - 1 else None
                    if left is None and right is None:
                        return []
                    if left is None:
                        drop = right
                    elif right is None:
                        drop = left
                    else:
                        drop = left if sc[left] < sc[right] else right
                    cuts.remove(drop)
                    changed = True
                    break
        return cuts


def train(words: Sequence[str], epochs: int = 8, sep: str = "•", log=print) -> BoundaryModel:
    """Averaged perceptron over gap decisions."""
    import random
    data = []
    for entry in words:
        plain = entry.replace(sep, "")
        cuts = set()
        pos = 0
        for ch in entry:
            if ch == sep:
                cuts.add(pos)
            else:
                pos += 1
        for i in range(1, len(plain)):
            data.append((gap_features(plain, i), 1 if i in cuts else -1))
    w: Dict[str, float] = {}
    u: Dict[str, float] = {}
    c = 1
    rng = random.Random(1)
    for ep in range(epochs):
        rng.shuffle(data)
        errs = 0
        for feats, y in data:
            s = sum(w.get(f, 0.0) for f in feats)
            if y * s <= 0:
                errs += 1
                for f in feats:
                    w[f] = w.get(f, 0.0) + y
                    u[f] = u.get(f, 0.0) + y * c
            c += 1
        log(f"epoch {ep + 1}: gap errors {errs}/{len(data)}")
    avg = {f: w[f] - u[f] / c for f in w}
    avg = {f: round(v, 3) for f, v in avg.items() if abs(v) >= 0.01}
    return BoundaryModel(avg)
