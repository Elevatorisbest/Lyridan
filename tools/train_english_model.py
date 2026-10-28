"""Train the English syllable-boundary model from lyridan/data/english_syllables.txt.

Usage:  python tools/train_english_model.py [--eval]
--eval holds out 5% of the dictionary and reports word-level accuracy
(with and without CMU syllable counts) before training the final model.
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lyridan.lang.hyphen_model import train  # noqa: E402

DATA = os.path.join(ROOT, "lyridan", "data", "english_syllables.txt")
OUT = os.path.join(ROOT, "lyridan", "data", "english_model.json.gz")


def load_entries():
    out = []
    for line in open(DATA, encoding="utf-8"):
        s = line.strip().lower()
        if s and "•" in s and "." not in s:
            out.append(s)
    return out


def cmu_counts():
    from lyridan.lang.english import EnglishSyllabifier
    return EnglishSyllabifier().cmu


def evaluate(entries, epochs):
    rng = random.Random(7)
    items = entries[:]
    rng.shuffle(items)
    k = len(items) // 20
    test, tr = items[:k], items[k:]
    model = train(tr, epochs=epochs)
    cmu = cmu_counts()
    ok_free = ok_cmu = n_cmu = 0
    for e in test:
        plain = e.replace("•", "")
        gold = []
        pos = 0
        for ch in e:
            if ch == "•":
                gold.append(pos)
            else:
                pos += 1
        if model.decode(plain) == gold:
            ok_free += 1
        if plain in cmu:
            n_cmu += 1
            if model.decode(plain, cmu[plain]) == gold:
                ok_cmu += 1
    print(f"held-out words: {len(test)}")
    print(f"  unconstrained accuracy: {ok_free / len(test):.4f}")
    print(f"  with CMU counts ({n_cmu} words): {ok_cmu / max(1, n_cmu):.4f}")


if __name__ == "__main__":
    entries = load_entries()
    epochs = 10
    if "--eval" in sys.argv:
        evaluate(entries, epochs)
    model = train(entries, epochs=epochs)
    model.save(OUT)
    print("saved", OUT, len(model.w), "features")
