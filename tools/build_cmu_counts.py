"""Extract syllable counts from the CMU Pronouncing Dictionary (BSD licence).

Output: lyridan/data/cmu_syllables.txt.gz  -  "word<TAB>counts" (counts comma separated)
Run once at development time; the app then has no runtime dependency on cmudict.
"""
import gzip
import os

import cmudict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "lyridan", "data", "cmu_syllables.txt.gz")

with gzip.open(OUT, "wt", encoding="utf-8") as fh:
    for w, prons in sorted(cmudict.dict().items()):
        counts = sorted({sum(ch.isdigit() for ch in "".join(p)) for p in prons})
        fh.write(f"{w}\t{','.join(map(str, counts))}\n")
print("wrote", OUT)
