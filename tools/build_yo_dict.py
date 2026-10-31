"""Build the Russian ё-restoration dictionary from OpenCorpora (via pymorphy3).

Output: lyridan/data/ru_yo.txt.gz - one word per line, written with ё.
Only forms whose е-spelling is NOT itself a valid word form are included,
so restoring them is always safe (e.g. ещё, её? -> no: "ее" is ambiguous only
in theory; ёлка, идёт, моё, твоё, своё, зелёный ...).
A short list of frequent ambiguous pairs is handled by context rules in code.
"""
import gzip
import os
import sys

import pymorphy3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "lyridan", "data", "ru_yo.txt.gz")


def main():
    morph = pymorphy3.MorphAnalyzer()
    yo, plain = set(), set()
    for word, *_ in morph.dictionary.iter_known_words():
        w = word.lower()
        if not w.isalpha():
            continue
        if "ё" in w:
            yo.add(w)
        else:
            plain.add(w)
    safe = sorted(w for w in yo if w.replace("ё", "е") not in plain)
    ambiguous = sorted(w for w in yo if w.replace("ё", "е") in plain)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        fh.write("\n".join(safe))
    print(f"ё forms: {len(yo)}, safe: {len(safe)}, ambiguous: {len(ambiguous)}")
    print("ambiguous sample:", ambiguous[:80])


if __name__ == "__main__":
    sys.exit(main())
