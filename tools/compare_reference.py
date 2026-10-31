"""Compare Lyridan output with the hand-made reference chart (tests/fixtures)."""
import difflib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lyridan.parsers import load_lyrics  # noqa: E402
from lyridan.parsers.rsxml import parse_beatmap, parse_vocals  # noqa: E402
from lyridan.pipeline import process  # noqa: E402
from lyridan.rocksmith import build_vocals  # noqa: E402
from lyridan.settings import Settings  # noqa: E402

F = os.path.join(ROOT, "tests", "fixtures")


def run(settings=None, verbose=False):
    s = settings or Settings()
    src = load_lyrics(os.path.join(F, "test_song.ttml"))
    bm = parse_beatmap(os.path.join(F, "baby_be_mine_bass.xml"))
    pr = process(src, s)
    res = build_vocals(pr.lines, s, bm, src.lyric_offset, src.leading_silence)
    ref = parse_vocals(os.path.join(F, "test_song_vocals_reference.xml"))
    a = [e.lyric.lower() for e in ref]
    b = [e.lyric.lower() for e in res.entries]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    same_text = exact_t = near_t = 0
    diffs = []
    for i, j, n in sm.get_matching_blocks():
        for k in range(n):
            same_text += 1
            d = res.entries[j + k].time - ref[i + k].time
            diffs.append(d)
            if abs(d) < 0.003:
                exact_t += 1
            if abs(d) < 0.15:
                near_t += 1
    strip = lambda x: x.rstrip("+-")
    a2 = [strip(x) for x in a]
    b2 = [strip(x) for x in b]
    sm2 = difflib.SequenceMatcher(a=a2, b=b2, autojunk=False)
    same_syl = sum(n for _, _, n in sm2.get_matching_blocks())
    print(f"offset {res.offset.total:.3f}s {res.offset.parts}")
    print(f"reference vocals {len(ref)}, generated {len(res.entries)}")
    print(f"identical syllables (ignoring markers): {same_syl}/{len(ref)}")
    print(f"identical lyric incl. -/+ markers: {same_text}/{len(ref)}")
    print(f"  of those, same time (±3ms): {exact_t}, within 150ms: {near_t}")
    if diffs:
        import statistics
        print(f"  median time diff {statistics.median(diffs):+.3f}s")
    if verbose:
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                print(tag, [r.lyric for r in ref[i1:i2]], "->", [e.lyric for e in res.entries[j1:j2]])
    print("warnings:", res.warnings)
    return res


if __name__ == "__main__":
    run(verbose="-v" in sys.argv)
