"""Tests for the corpus generator's pure logic: labels, pools, selection, job
planning and the MusicXML tweaks. The engraver programs themselves are not run
here (the inspector tests cover their output)."""

import io
import zipfile

import pytest

from omr.corpus import config, engravers, generate, labels, select
from omr.corpus.sources import Candidate
from omr.log import ProgressLog


def musicxml(parts, extra_notes=""):
    """A small MusicXML document. parts: list of (id, name, sound, staves)."""
    plist = "".join(
        f'<score-part id="{i}"><part-name>{n}</part-name>'
        f'<score-instrument id="{i}-I1"><instrument-sound>{s}</instrument-sound></score-instrument></score-part>'
        for i, n, s, _ in parts
    )
    body = ""
    for i, _n, _s, staves in parts:
        measures = ""
        for m in range(1, 9):
            attrs = f"<attributes><divisions>1</divisions><staves>{staves}</staves></attributes>" if m == 1 else ""
            measures += (f'<measure number="{m}">{attrs}<note><pitch><step>C</step><octave>4</octave></pitch>'
                         f"<duration>4</duration><voice>1</voice>{extra_notes if m == 1 else ''}</note></measure>")
        body += f'<part id="{i}">{measures}</part>'
    return f"<score-partwise><part-list>{plist}</part-list>{body}</score-partwise>"


def facts_for(parts, extra=""):
    import xml.etree.ElementTree as ET

    return labels.analyse(ET.fromstring(musicxml(parts, extra)))


@pytest.mark.parametrize(
    "parts,expected",
    [
        ([("P1", "Soprano", "voice.soprano", 1), ("P2", "Alto", "voice.alto", 1)], "choir"),
        ([("P1", "Voice", "voice.vocals", 1), ("P2", "Piano", "keyboard.piano", 2)], "voice with piano"),
        ([("P1", "Piano", "keyboard.piano", 2)], "piano"),
        ([("P1", "Flute", "wind.flutes.flute", 1)], "single line"),
        ([("P1", "Violin", "strings.violin", 1), ("P2", "Cello", "strings.cello", 1)], "chamber"),
        ([("P%d" % i, "Violin", "strings.violin", 1) for i in range(1, 8)], "small ensemble"),
        # A bass guitar is not a bass voice: the instrument sound decides.
        ([("P1", "Bass", "pluck.bass", 1)], "single line"),
        ([("P1", "Bass", "voice.bass", 1), ("P2", "Tenor", "voice.tenor", 1)], "choir"),
    ],
)
def test_texture_rules(parts, expected):
    assert labels.texture(facts_for(parts)) == expected


def test_hymn_layout_is_choir():
    import xml.etree.ElementTree as ET

    xml = musicxml([("P1", "Hymn", "keyboard.piano", 2)]).replace(
        "</note>", "<staff>1</staff><lyric><text>la</text></lyric></note><note><pitch><step>D</step><octave>3</octave></pitch>"
        "<duration>4</duration><staff>2</staff><lyric><text>la</text></lyric></note>", 1)
    facts = labels.analyse(ET.fromstring(xml))
    assert labels.texture(facts) == "choir"


def test_features_and_exclusions():
    parts = [("P1", "Piano", "keyboard.piano", 1)]
    assert "tuplets" in facts_for(parts, "<time-modification><actual-notes>3</actual-notes></time-modification>").features
    assert "grace notes" in facts_for(parts, "<grace/>").features
    assert "lyrics" in facts_for(parts, "<lyric><text>x</text></lyric>").features
    assert facts_for(parts, "<unpitched/>").excluded == "unpitched percussion"


def test_mxl_is_read(tmp_path):
    path = tmp_path / "x.mxl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("score.xml", musicxml([("P1", "Piano", "keyboard.piano", 1)]))
    root = labels.read_musicxml(path)
    assert labels.analyse(root).bars == 8


def test_genre_mapping_and_rules():
    assert labels.pdmx_genre("NA") is None
    assert labels.pdmx_genre("classical-soundtrack") == "classical"
    assert labels.pdmx_genre("pop-religiousmusic") == "sacred"
    assert labels.pdmx_genre("newage") == "other"
    assert labels.final_genre("classical", "choir", "Mass", "") == "choral"
    assert labels.final_genre("sacred", "choir", "Mass", "") == "sacred"
    assert labels.final_genre("folk", "piano", "Scales for beginners", "") == "educational"
    assert labels.final_genre(None, "piano", "Prelude", "") == "unlabelled"


def test_work_key_ignores_arrangement_words_and_catalogue_numbers():
    a = labels.work_key("Johann Sebastian Bach", "Jesu, Joy of Man's Desiring (easy piano arr.) BWV 147")
    b = labels.work_key("J. S. Bach", "Jesu Joy of Man's Desiring")
    assert a == b
    assert labels.work_key("Mozart", "Sonata") != labels.work_key("Haydn", "Sonata")


def test_pool_split_is_stable_and_roughly_right():
    keys = [f"composer{i}|title {i}" for i in range(20000)]
    pools = [labels.pool_of(k) for k in keys]
    assert pools == [labels.pool_of(k) for k in keys]
    assert 0.02 < pools.count("regression") / len(keys) < 0.04
    assert 0.10 < pools.count("development") / len(keys) < 0.14
    # The seed changes the split.
    assert [labels.pool_of(k, seed=1) for k in keys[:200]] != pools[:200]


def make_candidate(i, texture, genre="classical", features=(), pool="development", source="PDMX", composer="Bach"):
    return Candidate(
        id=f"c{i}", source=source, source_path=f"p/{i}", mxl=f"/none/{i}", title=f"T{i}", composer=composer,
        source_genre=genre, tags="", work_key=f"k{i}", pool=pool, bars=20, parts=2, texture=texture,
        genre=genre, features=list(features),
    )


def test_selection_fills_quotas_honours_minimums_and_skips_failed_round_trips(monkeypatch):
    log = ProgressLog("t", stream=io.StringIO())
    candidates = []
    n = 0
    for texture in config.TEXTURES:
        for genre in config.GENRES:
            for _ in range(8):
                candidates.append(make_candidate(n, texture, genre, features=["lyrics"] if n % 3 == 0 else [],
                                                 pool="regression"))
                n += 1

    def fake_check(c):
        from omr.corpus.roundtrip import RoundTrip

        return RoundTrip(c.id != "c0", "bad" if c.id == "c0" else "ok", "/ref.musicxml", 2)

    monkeypatch.setattr(select.roundtrip, "check", fake_check)
    chosen, shortfalls = select.select_set("regression", candidates, log, composers={"bach"})
    ids = [c.id for c, _ in chosen]
    assert len(ids) == len(set(ids)) == 50
    assert "c0" not in ids
    counts = {t: sum(1 for c, _ in chosen if c.texture == t) for t in config.TEXTURES}
    assert counts == config.SETS["regression"]["textures"]
    for genre in config.GENRES:
        assert sum(1 for c, _ in chosen if c.genre == genre) >= 3
    assert shortfalls == [] or all("feature" in s for s in shortfalls)
    # Same inputs, same selection.
    again, _ = select.select_set("regression", candidates, log, composers={"bach"})
    assert [c.id for c, _ in again] == ids


def test_regression_set_requires_public_domain_composer_and_short_scores():
    names = {"bach"}
    ok = make_candidate(1, "piano", pool="regression", composer="J. S. Bach")
    modern = make_candidate(2, "piano", pool="regression", composer="Somebody Modern")
    long = make_candidate(3, "piano", pool="regression", composer="Bach")
    long.bars = 65
    arr = make_candidate(4, "piano", pool="regression", composer="Bach arr. Somebody")
    own = make_candidate(5, "piano", pool="regression", composer="")
    own.original_cc0 = True
    openscore = make_candidate(6, "piano", pool="regression", source="OpenScore", composer="Anyone")
    allowed = [select.regression_allowed(c, names) for c in (ok, modern, long, arr, own, openscore)]
    assert allowed == [True, False, False, False, True, True]


def test_openscore_share_limit(monkeypatch):
    log = ProgressLog("t", stream=io.StringIO())
    candidates = [make_candidate(i, "voice with piano", source="OpenScore") for i in range(40)]
    candidates += [make_candidate(100 + i, "voice with piano") for i in range(20)]
    from omr.corpus.roundtrip import RoundTrip
    monkeypatch.setattr(select.roundtrip, "check", lambda c: RoundTrip(True, "ok", "/r", 1))
    chosen, _ = select.select_set("development", candidates, log, composers=set())
    voice = [c for c, _ in chosen if c.texture == "voice with piano"]
    assert sum(c.source == "OpenScore" for c in voice) <= int(0.4 * 50)


def test_every_score_gets_six_jobs_and_fonts_are_spread_over_textures():
    chosen = []
    for i in range(70):
        chosen.append((make_candidate(i, config.TEXTURES[i % 6]), None))
    jobs = generate.plan_jobs(chosen)
    assert all(len(v) == 6 for v in jobs.values())
    names = [name for name, _ in jobs["c0"]]
    assert names == ["musescore4-base", "musescore3-base", "lilypond", "verovio",
                     "musescore4-variant", "musescore3-variant"]
    seen = {}
    for c, _ in chosen:
        font = dict(jobs[c.id])["musescore4-variant"]["font"]
        seen.setdefault(c.texture, set()).add(font)
    assert all(len(fonts) >= 5 for fonts in seen.values())
    assert {dict(v)["musescore4-variant"]["staff_mm"] for v in jobs.values()} == set(config.MS4_STAFF_SIZES_MM)
    assert all(dict(v)["musescore3-variant"]["font"] in config.MS3_VARIANT_FONTS for v in jobs.values())


def test_staff_size_is_set_in_the_scaling_element():
    xml = b"<score-partwise><defaults><scaling><millimeters>7</millimeters><tenths>40</tenths></scaling></defaults><part-list/></score-partwise>"
    assert b"<millimeters>8</millimeters>" in engravers.set_staff_size(xml, 2.0)
    bare = b"<score-partwise><part-list/></score-partwise>"
    out = engravers.set_staff_size(bare, 1.5)
    assert b"<millimeters>6</millimeters><tenths>40</tenths>" in out
    assert out.index(b"<defaults>") < out.index(b"<part-list")


def test_verovio_svg_fix_adds_stroke_and_unwraps_inner_svg():
    svg = ('<svg viewBox="0 0 2100 2970"><svg class="definition-scale" viewBox="0 0 21000 29700">'
           '<path stroke-width="27" d="M0 0"/></svg></svg>')
    fixed = engravers.fix_verovio_svg(svg)
    assert 'stroke="black"' in fixed
    assert "definition-scale" not in fixed
    assert '<g transform="scale(0.1)">' in fixed
    assert fixed.count("<svg") == 1 and fixed.count("</svg>") == 1


def test_all_expected_font_names_have_a_pdf_name():
    for font in list(engravers.MUSESCORE4_FONTS) + list(engravers.MUSESCORE3_FONTS):
        assert font in engravers.PDF_FONT_NAMES
