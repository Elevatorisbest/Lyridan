"""Regression tests. Run with:  python -m pytest -q"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
F = os.path.join(ROOT, "tests", "fixtures")

from lyridan.lang.english import get_english  # noqa: E402
from lyridan.lang.japanese import JapaneseOptions, get_japanese, resolve_native  # noqa: E402
from lyridan.lang import russian  # noqa: E402
from lyridan.lang.kana import kana_to_romaji, split_romaji  # noqa: E402
from lyridan.parsers import load_lyrics  # noqa: E402
from lyridan.parsers.rsxml import parse_beatmap, parse_vocals  # noqa: E402
from lyridan.pipeline import process  # noqa: E402
from lyridan.rocksmith import build_vocals  # noqa: E402
from lyridan.settings import Settings  # noqa: E402


# ----------------------------------------------------------------- English
@pytest.mark.parametrize("word,expected", [
    ("every", "eve-ry"), ("everything", "eve-ry-thing"), ("paradise", "pa-ra-dise"),
    ("ecstasy", "ec-sta-sy"), ("different", "dif-fe-rent"), ("living", "li-ving"),
    ("C'mon", "C'-mon"), ("There'll", "There'll"), ("heaven's", "hea-ven's"), ("Darling,", "Dar-ling,"),
    ("desire", "de-sire"), ("gonna", "gon-na"), ("love", "love"), ("sun?", "sun?"),
])
def test_english(word, expected):
    assert "-".join(get_english().syllabize(word)) == expected


# ----------------------------------------------------------------- Japanese
def ja(text, **kw):
    words, _ = get_japanese().process_line(text, JapaneseOptions(**kw), get_english())
    resolve_native(words, text)
    return " ".join(w.prefix + "-".join(s.text for s in w.syllables) + w.suffix for w in words)


@pytest.mark.parametrize("text,expected", [
    ("君の名は。", "ki-mi no na wa."),
    ("私は東京へ行こう", "wa-ta-shi wa to-u-kyo-u e i-ko-u"),
    ("抱きしめたい気持ちを", "da-ki-shi-me-ta-i ki-mo-chi o"),
    ("歌ってくれ", "u-tat-te ku-re"),
    ("ちょっと待って", "chot-to mat-te"),
    ("何をしても", "na-ni o shi-te mo"),
    ("何時までも", "i-tsu ma-de mo"),
    ("こんにちは", "kon-ni-chi-wa"),
    ("恋愛", "ren'-a-i"),
    ("心(こころ)の宇宙(そら)へ", "ko-ko-ro no so-ra e"),
    ("夢を抱いて", "yu-me o i-da-i-te"),
    ("シェイクスピア", "she-i-ku-su-pi-a"),
])
def test_japanese(text, expected):
    assert ja(text) == expected


def test_japanese_options():
    assert ja("東京", long_vowels="macron") == "tō-kyō"
    assert ja("思う", long_vowels="macron") == "o-mo-u"
    assert ja("君を", particle_wo="wo") == "ki-mi wo"
    assert ja("こんにちは", syllables="mora") == "ko-n-ni-chi-wa"
    assert ja("東京", syllables="syllable") == "tou-kyou"


def test_kana_and_romaji():
    assert kana_to_romaji("ティーンエイジャー") == "tiin'eijaa"
    assert split_romaji("kitte") == ["ki", "t", "te"]
    assert split_romaji("konnichiwa") == ["ko", "n", "ni", "chi", "wa"]


def test_japanese_native_mapping():
    words, _ = get_japanese().process_line("抱きしめて", JapaneseOptions(), get_english())
    resolve_native(words, "抱きしめて")
    assert [s.native for s in words[0].syllables] == ["抱", "き", "し", "め", "て"]


# ----------------------------------------------------------------- Russian
@pytest.mark.parametrize("word,syl,lat", [
    ("кошка", "ко-шка", "ko-shka"), ("солнце", "сол-нце", "sol-ntse"), ("еще", "е-щё", "ye-shcho"),
    ("ёлка", "ёл-ка", "yol-ka"), ("семья", "се-мья", "se-mya"), ("Достоевский", "До-сто-е-вский", "Do-sto-ye-vsky"),
])
def test_russian(word, syl, lat):
    w = russian.restore_yo(word)
    parts = russian.syllabize(w)
    chars = russian.translit_chars(w, "practical")
    out, pos = [], 0
    for p in parts:
        out.append("".join(chars[pos:pos + len(p)]))
        pos += len(p)
    assert "-".join(parts) == syl
    assert "-".join(out) == lat


def test_russian_schemes():
    assert russian.transliterate("Щука", "iso9") == "Ŝuka"
    assert russian.transliterate("Юля", "icao") == "Iulia"
    assert russian.transliterate("объятие", "gost_b") == "ob``yatie"


# ----------------------------------------------------------------- end to end
def test_reference_chart():
    """Generated vocals must closely match the hand-made reference chart."""
    import difflib
    s = Settings()
    src = load_lyrics(os.path.join(F, "baby_be_mine.ttml"))
    bm = parse_beatmap(os.path.join(F, "baby_be_mine_bass.xml"))
    res = build_vocals(process(src, s).lines, s, bm, src.lyric_offset, src.leading_silence)
    ref = parse_vocals(os.path.join(F, "baby_be_mine_vocals_reference.xml"))
    assert abs(res.offset.total - 14.024) < 1e-6
    a = [e.lyric.lower().rstrip("+-") for e in ref]
    b = [e.lyric.lower().rstrip("+-") for e in res.entries]
    same = sum(n for _, _, n in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_matching_blocks())
    assert same >= 400
    assert res.entries[0].time == pytest.approx(34.436, abs=0.002)   # "I"
    times = [e.time for e in res.entries]
    assert times == sorted(times) and len(set(times)) == len(times)
    assert res.entries[0].time >= bm.first_n_measures_end(2)


def test_enhanced_lrc_and_overrides():
    s = Settings()
    src = load_lyrics(os.path.join(F, "english_enhanced.lrc"))
    pr = process(src, s, overrides={0: "Ev-ery mo-ment / takes me to pa-ra-dise"})
    assert pr.lines[0].manual
    res = build_vocals(pr.lines, s, None)
    lyr = [e.lyric for e in res.entries]
    assert lyr[:5] == ["Ev-", "ery", "mo-", "ment+", "Takes"]


def test_japanese_ttml_romaji_and_native():
    s = Settings()
    src = load_lyrics(os.path.join(F, "japanese_sample.ttml"))
    assert src.has_romaji
    res = build_vocals(process(src, s).lines, s, None)
    assert [e.lyric for e in res.entries[:5]] == ["Ki-", "mi", "no", "na", "wa+"]
    resn = build_vocals(process(src, s, native_script=True).lines, s, None, native=True)
    assert [e.lyric for e in resn.entries[:4]] == ["君-", "の-", "名-", "は+"]


def test_build_info_channels(tmp_path, monkeypatch):
    import importlib
    import subprocess
    from lyridan import buildinfo
    env = dict(os.environ, GITHUB_ACTIONS="true", GITHUB_REF_TYPE="branch", GITHUB_REF_NAME="main",
               GITHUB_RUN_NUMBER="7")
    out = subprocess.check_output([sys.executable, os.path.join(ROOT, "tools", "write_build_info.py")],
                                  env=env, text=True).strip()
    assert out == buildinfo.VERSION
    env["GITHUB_REF_NAME"] = "dev"
    out = subprocess.check_output([sys.executable, os.path.join(ROOT, "tools", "write_build_info.py")],
                                  env=env, text=True).strip()
    assert out.endswith("-dev.7")
    import lyridan._build
    importlib.reload(lyridan._build)
    importlib.reload(buildinfo)
    assert buildinfo.is_dev() and any(k == "Branch" for k, _ in buildinfo.details())
    # restore the empty source-tree default
    with open(os.path.join(ROOT, "lyridan", "_build.py"), "w", encoding="utf-8") as fh:
        fh.write("# Generated by tools/write_build_info.py (git-ignored). Empty = running from source.\nBUILD_INFO = {}\n")
    importlib.reload(lyridan._build)
    importlib.reload(buildinfo)
    assert buildinfo.info()["build_number"] == "local"


# ----------------------------------------------------------------- audio alignment (experimental)
def test_lrc_background_split():
    from lyridan.parsers.lrc import parse_lrc
    src = parse_lrc("[00:10.00](Every night, it's alright) C'mon, girl\n[00:14.00]Next\n")
    assert [(l.text, l.background) for l in src.lines[:2]] == [("C'mon, girl", False),
                                                               ("(Every night, it's alright)", True)]


def test_ctc_align_and_offset_detection():
    import numpy as np
    from lyridan.align.aligner import ctc_align, detect_offset
    # synthetic emissions: blank everywhere, tokens 3,5,7 peak at frames 20, 30, 45
    T, C = 80, 28
    lp = np.full((T, C), -8.0, dtype=np.float32)
    lp[:, 0] = -0.01
    for f, tok in ((20, 3), (21, 3), (30, 5), (45, 7)):
        lp[f, tok], lp[f, 0] = -0.01, -6.0
    spans, conf = ctc_align(lp, [3, 5, 7])
    assert [a for a, _ in spans] == [20, 30, 45] and conf > 0.9
    # vocal activity right after every line timestamp, shifted by +12.34 s
    fps, n = 50, 50 * 120
    em = np.zeros((n, C), dtype=np.float32)
    starts = [5.0, 17.0, 31.5, 44.0, 60.2, 77.7]
    for s in starts:
        a = int((s + 12.34) * fps)
        em[a:a + 75, 0] = np.log(0.05)
    off, _, _ = detect_offset(em, 1 / fps, starts, search=(-5, 30))
    assert abs(off - 12.34) < 0.05


def test_ttml_writer_roundtrip(tmp_path):
    from lyridan.exports import ttml
    src = load_lyrics(os.path.join(F, "baby_be_mine.ttml"))
    p = tmp_path / "x.ttml"
    p.write_text(ttml(src), encoding="utf-8")
    back = load_lyrics(str(p))
    assert back.timing == "syllable"
    assert [l.text for l in back.lines][:3] == [l.text for l in src.lines][:3]
    assert sum(l.background for l in back.lines) == sum(l.background for l in src.lines)


@pytest.mark.skipif(not os.environ.get("LYRIDAN_ALIGN_MODEL") or not os.environ.get("LYRIDAN_TEST_AUDIO"),
                    reason="needs the alignment model and the song audio")
def test_alignment_real_song():
    import difflib
    import json
    import statistics
    from lyridan.align import align_lyrics
    model = os.environ["LYRIDAN_ALIGN_MODEL"]
    meta = json.load(open(os.path.splitext(model)[0] + ".json"))
    s = Settings()
    truth = process(load_lyrics(os.path.join(F, "baby_be_mine.ttml")), s)
    src = load_lyrics(os.path.join(F, "baby_be_mine.lrc"))
    al, rep = align_lyrics(src, os.environ["LYRIDAN_TEST_AUDIO"], s, model, meta)
    assert abs(rep.offset - 14.024) < 0.1           # chart audio = song + 10 s + 2 bars
    flat = lambda pr: [(x.text.lower(), x.start) for l in pr.lines if not l.background for x in l.syllables()]
    T, X = flat(truth), flat(process(al, s))
    sm = difflib.SequenceMatcher(a=[t[0] for t in T], b=[x[0] for x in X], autojunk=False)
    errs = [abs(X[j + k][1] - T[i + k][1]) for i, j, n in sm.get_matching_blocks() for k in range(n)]
    assert statistics.median(errs) < 0.12
    assert sum(e < 0.2 for e in errs) / len(errs) > 0.75


def _rs_lines(lines, s):
    return [" ".join("".join(t) for t in rl.texts) for rl in build_vocals(lines, s, None).lines]


def test_no_fragment_after_held_note():
    """A held first word must not become its own line ("Ya" / "zhdu otveta")."""
    from lyridan.model import SourceLine, SourceLyrics, SourcePiece
    pieces = [SourcePiece("Я", 56.20, 56.30), SourcePiece("жду", 58.70, 59.20),
              SourcePiece("ответа", 59.20, 60.50)]
    src = SourceLyrics([SourceLine(pieces, 56.2, 60.5)], timing="word")
    s = Settings()
    assert _rs_lines(process(src, s).lines, s) == ["Ya zhdu otveta"]


def test_russian_phrase_aware_split():
    """Long Russian lines are not split right after negation / prepositions."""
    from lyridan.model import SourceLine, SourceLyrics, SourcePiece
    words = "Про то, что больше не могу смотреть на дерьмо".split()
    pieces = [SourcePiece(w, 31.24 + 0.3 * i, 31.24 + 0.3 * (i + 1)) for i, w in enumerate(words)]
    src = SourceLyrics([SourceLine(pieces, 31.24, 31.24 + 0.3 * len(words))], timing="word")
    s = Settings()
    out = _rs_lines(process(src, s).lines, s)
    assert len(out) == 2
    assert not out[0].lower().endswith((" ne", " na", " v", " i"))
    assert [o.lower() for o in out] == ["pro to chto bolshe ne mogu", "smotret na dermo"]  # "ne mogu" together


def _rs_lines_lrc(lrc_text, **kw):
    from lyridan.parsers.lrc import parse_lrc
    s = Settings()
    for k, v in kw.items():
        setattr(s, k, v)
    res = build_vocals(process(parse_lrc(lrc_text), s).lines, s, None)
    lines, cur = [], ""
    for e in res.entries:
        l = e.lyric
        cur += l[:-1] if l[-1] in "-+" else l + " "
        if l.endswith("+"):
            lines.append(cur.strip())
            cur = ""
    return lines


def test_line_phrasing_syllable_limit():
    ru = _rs_lines_lrc("[00:10.00]Но, впрочем, в той тени, где я, пока и сухо, и тепло\n"
                   "[00:16.00]И, в общем, весело живём, хотя и дождь за окном\n"
                   "[00:22.00]Про то, что больше не могу смотреть на дерьмо\n[00:28.00]\n")
    assert ru == ["No vprochem v toy teni gde ya", "Poka i sukho i teplo",
                  "I v obshchem veselo zhivyom", "Khotya i dozhd za oknom",
                  "Pro to chto bolshe ne mogu", "Smotret na dermo"]
    en = _rs_lines_lrc("[00:10.00]Share my feelings in the heat of love's embrace\n[00:15.00]\n")
    assert en == ["Share my feelings", "In the heat of love's embrace"]
    # limit off -> one line
    assert len(_rs_lines_lrc("[00:10.00]Share my feelings in the heat of love's embrace\n[00:15.00]\n",
                         max_line_syllables=0, max_line_chars=0)) == 1


# ----------------------------------------------------------------- timeline helpers
def test_find_chart_audio_and_dlcbuilder_project(tmp_path):
    pytest.importorskip("PySide6")
    import json
    from lyridan.gui.timeline_panel import find_chart_audio
    (tmp_path / "song_preview.ogg").write_bytes(b"x")
    (tmp_path / "other.mp3").write_bytes(b"x" * 10)
    (tmp_path / "Baby Be Mine.wav").write_bytes(b"x" * 5)
    assert find_chart_audio([str(tmp_path)], "Baby Be Mine").endswith("Baby Be Mine.wav")
    sub = tmp_path / "audio"
    sub.mkdir()
    (sub / "main.wav").write_bytes(b"x")
    (tmp_path / "proj.rs2dlc").write_text(json.dumps({"AudioFile": {"Path": "audio/main.wav", "Volume": -8}}))
    assert find_chart_audio([str(tmp_path)]).endswith(os.path.join("audio", "main.wav"))


def test_audio_player_silent_clock(tmp_path):
    import time
    import numpy as np
    import soundfile as sf
    from lyridan.gui.audio_player import AudioPlayer
    p = tmp_path / "a.wav"
    sf.write(str(p), np.zeros((44100 * 3, 2), dtype=np.float32), 44100)
    pl = AudioPlayer()
    pl.load(str(p))
    assert abs(pl.duration - 3.0) < 1e-3 and len(pl.peaks) == 300
    pl._ensure_stream = lambda: False          # force the silent fallback clock
    pl.seek(1.0)
    pl.play()
    time.sleep(0.3)
    pos = pl.position()
    pl.pause()
    assert 1.2 < pos < 1.6 and not pl.playing


def test_export_entry_line_mapping():
    s = Settings()
    src = load_lyrics(os.path.join(F, "baby_be_mine.ttml"))
    pr = process(src, s)
    res = build_vocals(pr.lines, s, None)
    assert len(res.entry_line) == len(res.entries)
    first_line = [l for l in pr.lines if not l.background][0].index
    assert res.entry_line[0] == first_line and res.entry_line == sorted(res.entry_line)


# ----------------------------------------------------------------- mixed Japanese / English lyrics
def test_romaji_vs_english_detection():
    from lyridan.lang.japanese import looks_like_romaji
    for w in ("senakaawase", "sayonara", "kitte", "matcha", "sempai", "shin'ai", "arigatou"):
        assert looks_like_romaji(w), w
    for w in ("stars", "broken", "the", "just", "sky", "fleeting", "night", "Don't"):
        assert not looks_like_romaji(w), w


def test_long_vowels_only_join_inside_a_word():
    assert ja("背中合わせ", syllables="syllable") == "se-na-ka-a-wa-se"   # senaka + awase
    assert ja("東京", syllables="syllable") == "tou-kyou"
    assert ja("ラーメン", syllables="syllable") == "raa-men"
    assert ja("お母さん", syllables="syllable") == "o-kaa-san"
    assert ja("お母さん") == "o-ka-a-san"


@pytest.mark.parametrize("language", ["auto", "ja", "ja_romaji"])
@pytest.mark.parametrize("mode", ["mora_n", "syllable"])
def test_english_inside_japanese_lyrics(language, mode):
    from lyridan.parsers.lrc import parse_lrc
    s = Settings()
    s.language, s.ja.syllables = language, mode
    lrc = ("[00:10.00]Under the broken sky, we rewrite the stars.\n"
           "[00:15.00]背中合わせで刻むシーケンス\n[00:20.00]\n")
    res = build_vocals(process(parse_lrc(lrc), s).lines, s, None)
    lyr = [e.lyric for e in res.entries]
    assert "stars+" in lyr and "s-" not in lyr
    assert lyr[lyr.index("Se-"):lyr.index("Se-") + 6] == ["Se-", "na-", "ka-", "a-", "wa-", "se"]


def test_alternative_kanji_readings():
    ja = get_japanese()
    alts = ja.alternative_readings("緋", "ヒ")
    assert "アカ" in alts and "ヒ" not in alts


def test_reading_verification_helpers():
    pytest.importorskip("numpy")
    import numpy as np
    from lyridan.align.aligner import AlignmentReport, ctc_score
    from lyridan.align.readings import ReadingChange, _minor_variant
    # voicing / gemination / vowel length variants are not real alternative readings
    assert _minor_variant("コッ", "クロ")
    assert _minor_variant("ケシテ", "ケッシテ")
    assert _minor_variant("キョウガイ", "キョウカイ")
    assert not _minor_variant("アカ", "ヒ")
    # the scorer prefers the text that matches the frames
    logp = np.log(np.full((6, 3), 0.01))
    for f, k in enumerate([1, 1, 0, 2, 2, 0]):
        logp[f, k] = np.log(0.98)
    assert ctc_score(logp, [1, 2]) > ctc_score(logp, [2, 1])
    rep = AlignmentReport()
    rep.readings = [ReadingChange(0, "緋と黒", "緋", "ひ", "あか", 5.3),
                    ReadingChange(1, "瞬き", "瞬き", "まばたき", "またたき", 3.6, applied=False)]
    s = rep.summary()
    assert "緋 ひ → あか" in s and "check by ear" in s and "またたき?" in s
