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


@pytest.mark.parametrize(
    "name,sound,is_guitar",
    [
        ("Classical Guitar", "pluck.guitar.nylon-string", True),
        ("Guitar", "", True),
        ("Guitarra", "", True),
        ("Electric Guitar", "pluck.guitar.electric", False),
        ("Bass Guitar", "pluck.bass", False),
        ("Bass", "pluck.bass", False),
        ("Violin", "strings.violin", False),
    ],
)
def test_guitar_feature(name, sound, is_guitar):
    facts = facts_for([("P1", name, sound, 1)])
    assert ("guitar" in facts.features) == is_guitar
    if is_guitar:
        assert labels.texture(facts) == "single line"


def test_guitar_is_a_priority_feature_with_a_minimum_in_both_sets():
    assert "guitar" in config.PRIORITY_FEATURES
    assert config.SETS["development"]["feature_min"]["guitar"] >= 10
    assert config.SETS["regression"]["feature_min"]["guitar"] >= 3


def test_priority_feature_is_chosen_before_genre_minimums(monkeypatch):
    log = ProgressLog("t", stream=io.StringIO())
    from omr.corpus.roundtrip import RoundTrip
    monkeypatch.setattr(select.roundtrip, "check", lambda c: RoundTrip(True, "ok", "/r", 1))
    candidates = [make_candidate(i, "single line", genre=g, pool="regression")
                  for i, g in enumerate(config.GENRES * 3)]
    candidates += [make_candidate(100 + i, "single line", "classical", features=["guitar"], pool="regression")
                   for i in range(3)]
    chosen, _ = select.select_set("regression", candidates, log, composers={"bach"})
    singles = [c for c, _ in chosen if c.texture == "single line"]
    assert sum("guitar" in c.features for c in singles) == 3


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


@pytest.mark.parametrize(
    "result,passes",
    [(0, True), (3, False), (None, False)],
)
def test_round_trip_passes_only_on_an_explicit_zero(result, passes):
    """musicdiff returns None when a file fails to parse; that is not a pass."""
    pytest.importorskip("musicdiff")
    from omr.corpus import roundtrip

    failure = roundtrip.compare_notes("a.musicxml", "b.musicxml", diff=lambda *a, **k: result)
    assert (failure is None) is passes


def test_round_trip_failure_when_musicdiff_raises():
    pytest.importorskip("musicdiff")
    from omr.corpus import roundtrip

    def boom(*a, **k):
        raise ValueError("bad file")

    assert "bad file" in roundtrip.compare_notes("a", "b", diff=boom)


def test_round_trip_cache_rechecks_passes_from_an_older_check(tmp_path, monkeypatch):
    import json

    from omr.corpus import roundtrip

    monkeypatch.setattr(roundtrip, "cache_dir", lambda: tmp_path)
    runs = []

    def fake_run(candidate, folder, timeout):
        runs.append(candidate.id)
        return roundtrip.RoundTrip(False, "musicdiff could not parse one of the files")

    monkeypatch.setattr(roundtrip, "_run", fake_run)
    old_pass = type("C", (), {"id": "old-pass"})()
    old_fail = type("C", (), {"id": "old-fail"})()
    (tmp_path / "old-pass.json").write_text(json.dumps({"ok": True, "reason": "ok"}))
    (tmp_path / "old-fail.json").write_text(json.dumps({"ok": False, "reason": "differences"}))
    assert not roundtrip.check(old_pass).ok  # re-run under the current check
    assert not roundtrip.check(old_fail).ok  # a failure stays a failure, not re-run
    assert runs == ["old-pass"]
    assert json.loads((tmp_path / "old-pass.json").read_text())["version"] == roundtrip.CHECK_VERSION
    roundtrip.check(old_pass)
    assert runs == ["old-pass"]  # now read from the cache


@pytest.mark.parametrize(
    "credit,surname",
    [
        ("J. S. Bach (1685-1750)", "bach"),
        ("Wolfgang Amadeus Mozart 1756-1791", "mozart"),
        ("Bach, Johann Sebastian", "bach"),
        ("Johann Pachelbel Arranged by Melanie Dean", "pachelbel"),
        ("Music by Richard Rodgers", "rodgers"),
        ("Comp. Nat King ColeArr. J.T. Wolken", "cole"),
        ("Robert Wells and Mel Tormearr. by David Buckley", "torme"),
        ("Misc Praise Songs", ""),
        ("Trad.", ""),
        ("Rearranged By:Daniel De Richie", ""),
        ("English Words by AP Graves", ""),
        ("", ""),
    ],
)
def test_clean_composer_finds_the_surname(credit, surname):
    assert labels.clean_composer(credit) == surname


def test_near_copies_of_a_selected_piece():
    index = labels.NearCopyIndex([
        ("Amazing Grace", "John Newton (1725-1807)"),
        ("Canon in D", "Johann Pachelbel Arranged by Melanie Dean"),
        ("Falling", "Shan Lee Rowe"),
        ("Mozart - Voi che sapete", "Wolfgang Amadeus Mozart 1756-1791"),
    ])
    # same title, any composer, when the title is distinctive
    assert index.match("Amazing Grace", "Misc Praise Songs")
    assert index.match("Voi che sapete", "Mozart")
    # the title as a phrase inside a longer one, when it has two distinctive words
    assert index.match("Amazing Grace Horn Trio", "Arr. Deirdre Johnson")
    # generic titles need the composer, or no composer
    assert index.match("Canon in D", "Pachelbel")
    assert index.match("Canon in D", "")
    assert index.match("Pachelbel's Canon in D (woodwind)", "Johann Pachelbel")
    assert not index.match("Canon in D", "Some Student")
    assert not index.match("Prelude in C minor", "J. S. Bach")
    # one-word titles do not catch longer, unrelated titles
    assert not index.match("Can't Help Falling In Love", "Elvis Presley")
    assert index.match("Falling (choir)", "Shan Lee Rowe")


def test_training_pool_drops_near_copies_and_selection_skips_them(monkeypatch):
    from omr.corpus import training
    from omr.corpus.roundtrip import RoundTrip

    pieces = [("development", "d1", "Amazing Grace", "John Newton")]
    copy = Candidate("t1", "PDMX", "p", "m", "Amazing Grace (3 trombones)", "Trad", None, "", "k1", "training")
    other = Candidate("t2", "PDMX", "p", "m", "Greensleeves", "Trad", None, "", "k2", "training")
    kept, copies = training.split_training([copy, other], pieces)
    assert [c.id for c in kept] == ["t2"] and [c.id for c in copies] == ["t1"]
    assert training.repeated_selections(pieces + [("regression", "r1", "Amazing Grace in G", "")])

    monkeypatch.setattr(select.roundtrip, "check", lambda c: RoundTrip(True, "ok", "/r", 1))
    a = Candidate("a", "PDMX", "p", "m", "Amazing Grace", "Newton", "sacred", "", "ka", "development",
                  texture="piano", genre="sacred")
    b = Candidate("b", "PDMX", "p", "m", "Amazing Grace in G", "", "sacred", "", "kb", "development",
                  texture="piano", genre="sacred")
    chosen, _ = select.select_set("development", [a, b], ProgressLog("t"), composers=set())
    assert len(chosen) == 1


def fake_export_job(spec, reference, out):
    """A stand-in engraver: LilyPond fails, the rest succeed, and MuseScore 4
    also writes its own MusicXML."""
    if spec["engraver"] == "LilyPond":
        raise engravers.ExportError("musicxml2ly timed out after 300 seconds")
    out.mkdir(parents=True, exist_ok=True)
    (out / "score.pdf").write_bytes(b"%PDF")
    musicxml = None
    if spec["engraver"] == "MuseScore 4":
        musicxml = out / "score.musicxml"
        musicxml.write_text("<score-partwise/>", encoding="utf-8")
    return engravers.ExportResult(out / "score.pdf", musicxml, spec["engraver"], "1.0", spec["font"])


def fake_export_run(tmp_path, monkeypatch, scores=3):
    from omr.corpus.roundtrip import RoundTrip

    monkeypatch.setattr(generate, "output_dir", lambda name: tmp_path / name)
    monkeypatch.setattr(generate.paths, "check_free_space", lambda folder, gb: 500.0)
    monkeypatch.setattr(generate, "_run_job", fake_export_job)
    monkeypatch.setattr(generate, "check_pdf", lambda pdf, spec: None)
    monkeypatch.setattr(generate, "compare_with_reference",
                        lambda answer, reference: ("0 in notes and rests, 2 in all objects", 0))
    reference = tmp_path / "ref.musicxml"
    reference.write_text("<score-partwise/>", encoding="utf-8")
    return [(make_candidate(i, "piano"), RoundTrip(True, "ok", str(reference), 1)) for i in range(scores)]


def test_export_run_records_pairs_and_failures_and_resumes(tmp_path, monkeypatch):
    """The export loop, with stand-in engravers: LilyPond fails, the rest succeed."""
    chosen = fake_export_run(tmp_path, monkeypatch)
    stream = io.StringIO()
    log = ProgressLog("t", stream=stream)

    assert generate.generate_set("development", chosen, log, workers=1) == (15, 3)
    root = tmp_path / "development"
    ms4 = (root / "c0" / "musescore4-base" / "metadata.txt").read_text(encoding="utf-8")
    assert "ground truth file: score.musicxml\nground truth: exact\n" in ms4
    assert "difference from shared reference: 0 in notes and rests, 2 in all objects\n" in ms4
    ms3 = (root / "c0" / "musescore3-base" / "metadata.txt").read_text(encoding="utf-8")
    assert "ground truth file: ../reference.musicxml\nground truth: engraver input\n" in ms3
    assert "difference from shared reference" not in ms3
    assert "timed out" in (root / "c1" / "lilypond" / "failure.txt").read_text(encoding="utf-8")
    index = (root / "index.txt").read_text(encoding="utf-8")
    assert index.count("\npair |") == 15 and index.count("\nfailure |") == 3
    assert str(root / "c0" / "musescore4-base" / "score.musicxml") in index
    assert str(root / "c0" / "reference.musicxml") in index
    assert "development 2 of 3: c1 lilypond failed: musicxml2ly timed out" in stream.getvalue()
    assert "Difference from the shared reference: 0 in notes and rests, 2 in all objects." in stream.getvalue()

    # A second run skips everything already made or failed.
    assert generate.generate_set("development", chosen, log, workers=1) == (0, 0)
    assert "0 exports made, 18 already present or failed earlier" in stream.getvalue()


def test_export_run_stops_cleanly_when_the_drive_is_nearly_full(tmp_path, monkeypatch):
    from omr import paths

    def full(folder, gb):
        raise paths.CorpusDirError("only 50 GB free")

    monkeypatch.setattr(generate, "output_dir", lambda name: tmp_path / name)
    monkeypatch.setattr(generate.paths, "check_free_space", full)
    stream = io.StringIO()
    made, failed = generate.generate_set("development", [(make_candidate(0, "piano"), None)],
                                         ProgressLog("t", stream=stream), workers=1)
    assert (made, failed) == (0, 1)
    assert "Stopping cleanly so the run can be resumed: only 50 GB free" in stream.getvalue()


def test_old_musescore4_jobs_are_made_again_and_old_metadata_is_upgraded(tmp_path, monkeypatch):
    """Jobs made before the per-pair ground truth: MuseScore 4 kept no MusicXML,
    and the others recorded "reference, engraver input"."""
    chosen = fake_export_run(tmp_path, monkeypatch, scores=1)
    log = ProgressLog("t", stream=io.StringIO())
    generate.generate_set("development", chosen, log, workers=1)
    root = tmp_path / "development" / "c0"
    (root / "musescore4-variant" / "score.musicxml").unlink()
    meta = root / "verovio" / "metadata.txt"
    text = meta.read_text(encoding="utf-8")
    meta.write_text(text.replace("ground truth file: ../reference.musicxml\nground truth: engraver input\n",
                                 "ground truth: reference, engraver input\n"), encoding="utf-8")

    assert generate.generate_set("development", chosen, log, workers=1) == (1, 0)
    assert (root / "musescore4-variant" / "score.musicxml").is_file()
    assert meta.read_text(encoding="utf-8") == text


def test_comparison_with_the_shared_reference():
    calls = []

    def diff(a, b, visualize_diffs, detail):
        calls.append(detail.name)
        return {"NotesAndRests": 0, "AllObjects": 3}[detail.name]

    assert generate.compare_with_reference("a", "b", diff=diff) == ("0 in notes and rests, 3 in all objects", 0)
    assert calls == ["NotesAndRests", "AllObjects"]
    text, notes = generate.compare_with_reference("a", "b", diff=lambda *a, **k: None)
    assert notes is None and "could not parse" in text

    def broken(*a, **k):
        raise ValueError("bad\nfile")

    text, notes = generate.compare_with_reference("a", "b", diff=broken)
    assert notes is None and text == "could not be compared, musicdiff failed: bad file"


def test_differences_in_notes_are_a_warning(tmp_path, monkeypatch):
    chosen = fake_export_run(tmp_path, monkeypatch, scores=1)
    monkeypatch.setattr(generate, "compare_with_reference",
                        lambda answer, reference: ("2 in notes and rests, 5 in all objects", 2))
    log = ProgressLog("t", stream=io.StringIO())
    generate.generate_set("development", chosen, log, workers=1)
    assert log.warnings == 2  # the two MuseScore 4 jobs


def test_a_job_with_another_font_than_the_plan_is_made_again(tmp_path, monkeypatch):
    """After a redraw the font rotation moves; a kept job with the old font is redone."""
    chosen = fake_export_run(tmp_path, monkeypatch, scores=1)
    log = ProgressLog("t", stream=io.StringIO())
    generate.generate_set("development", chosen, log, workers=1)
    meta = tmp_path / "development" / "c0" / "musescore3-variant" / "metadata.txt"
    planned = dict(generate.plan_jobs(chosen)["c0"])["musescore3-variant"]["font"]
    other = next(f for f in config.MS3_VARIANT_FONTS if f != planned)
    meta.write_text(meta.read_text(encoding="utf-8").replace(f"font: {planned}\n", f"font: {other}\n"),
                    encoding="utf-8")
    assert generate.generate_set("development", chosen, log, workers=1) == (1, 0)
    assert f"font: {planned}\n" in meta.read_text(encoding="utf-8")
