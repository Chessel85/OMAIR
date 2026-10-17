"""Tests for Stage 1.6: the MusicXML writer (omr.musicxml), the braille
adapter (omr.braille) and omr convert."""

import json
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import pytest

from omr import braille, musicxml
from omr.cli import main
from omr.evaluate import events, metrics
from omr.pdf import text

ROOT = Path(__file__).parent.parent
REGRESSION = ROOT / "regression"
DATA = Path(__file__).parent / "data" / "inspect"
F = Fraction


def _note(step, octave, alter=0, bar=0, onset=0, duration=1, value="quarter", part=0, staff=1, voice="1", **extra):
    return events.Note(part, staff, voice, bar, F(onset), events.Pitch(step, F(alter), octave), F(duration),
                       value, **extra)


def _rest(bar=0, onset=0, duration=1, part=0, staff=1, voice="1"):
    return events.Rest(part, staff, voice, bar, F(onset), duration if duration == events.WHOLE_BAR else F(duration))


def _score():
    """A two-staff piano part and a voice part, with something of every kind the writer handles."""
    score = events.Score(parts=[events.Part("Soprano", 1), events.Part("Piano", 2)],
                         bars=[events.Bar("1", 1, 1), events.Bar("2", 1, 1), events.Bar("3", 1, 2),
                               events.Bar("4", 2, 1)],
                         bar_counts=[4, 4])
    M = events.Marking
    for p in (0, 1):
        score.structure += [M("key", "-1", p, None, 0, F(0)), M("time", "4/4", p, None, 0, F(0)),
                            M("time", "3/4", p, None, 3, F(0)), M("key", "2", p, None, 2, F(0)),
                            M("repeat", "forward", p, None, 1, F(0)), M("repeat", "backward", p, None, 2, F(0)),
                            M("ending", "start 1 2", p, None, 2, F(0)), M("ending", "stop 1 2", p, None, 2, F(0))]
    score.structure += [M("clef", "G 2", 0, 1, 0, F(0)), M("clef", "G 2", 1, 1, 0, F(0)),
                        M("clef", "F 4", 1, 2, 0, F(0)), M("clef", "G 2 octave -1", 1, 2, 1, F(2)),
                        M("navigation", "segno", 0, None, 1, F(0)), M("navigation", "fine", 0, None, 3, F(0))]
    score.markings += [M("dynamic", "mf", 0, 1, 0, F(0)), M("dynamic", "più p", 1, 1, 1, F(1)),
                       M("hairpin", "crescendo", 1, 2, 0, F(1)), M("hairpin end", "1", 1, 2, 0, F(3)),
                       M("words", "dolce", 0, 1, 0, F(1, 2)), M("words", "Fine", 0, 1, 3, F(2)),
                       M("chord symbol", "Bb major", 0, 1, 0, F(0)), M("chord symbol", "A m7 / E", 0, 1, 1, F(2)),
                       M("rehearsal", "A", 0, None, 1, F(0)), M("metronome", "quarter. = 60", 0, None, 0, F(0))]
    score.notes += [
        _note("C", 5, lyrics=(("1", "Hal"),), syllables=(("1", "begin", False),), slurs=(("start", "1"),)),
        _note("D", 5, onset=1, lyrics=(("1", "le"),), syllables=(("1", "end", True),), slurs=(("stop", "1"),)),
        _note("E", 5, -1, onset=2, duration=F(1, 3), value="eighth"),   # a triplet
        _note("F", 5, onset=F(7, 3), duration=F(1, 3), value="eighth"),
        _note("G", 5, onset=F(8, 3), duration=F(1, 3), value="eighth", marks=frozenset({"articulation staccato"})),
        _note("A", 4, onset=3, duration=F(0), value="eighth", grace=1),
        _note("B", 4, -1, onset=3, tie_start=True, marks=frozenset({"fermata"})),
        _note("B", 4, -1, bar=1, tie_stop=True, duration=F(3, 2), value="quarter."),
        _note("F", 4, 1, bar=1, onset=F(3, 2), duration=F(1, 2), value="eighth"),   # F sharp, then F natural
        _note("F", 4, bar=1, onset=2, duration=2, value="half"),
        _note("C", 5, bar=2, duration=2, value="half", cue=True, tie_start=True,
              lyrics=(("1", " Ah  "),), syllables=(("1", "single", False),)),
        _note("C", 5, bar=2, onset=2, duration=2, value="half", cue=True, tie_stop=True),
        _note("D", 5, bar=3, duration=3, value="half.", marks=frozenset({"ornament trill-mark"})),
        # piano: a chord, two voices on the upper staff, the lower staff
        _note("C", 4, part=1, duration=2, value="half", marks=frozenset({"arpeggiate", "technical fingering"}),
              fingering=(("fingering", "1"),)),
        _note("E", 4, part=1, duration=2, value="half", marks=frozenset({"arpeggiate"})),
        _note("G", 4, part=1, onset=2, duration=2, value="half"),
        _note("C", 4, part=1, voice="2", onset=2, duration=2, value="half"),
        _note("C", 3, part=1, staff=2, voice="5", duration=4, value="whole"),
        _note("D", 3, part=1, staff=2, voice="5", bar=1, duration=2, value="half"),
        _note("E", 3, part=1, staff=2, voice="5", bar=1, onset=2, duration=2, value="half"),
    ]
    score.rests += [_rest(part=1, voice="2", duration=2), _rest(bar=1, part=1, duration=events.WHOLE_BAR),
                    _rest(bar=2, part=1, duration=events.WHOLE_BAR), _rest(bar=2, part=1, staff=2, voice="5",
                                                                            duration=events.WHOLE_BAR),
                    _rest(bar=3, part=1, duration=F(2, 3)), _rest(bar=3, part=1, onset=F(2, 3), duration=F(4, 3)),
                    _rest(bar=3, part=1, onset=2, duration=1), _rest(bar=3, part=1, staff=2, voice="5", duration=3)]
    score.text += [text.TextItem("title", "A Test Song", (0, 0, 1, 1), 1),
                   text.TextItem("composer", "Anon.", (0, 0, 1, 1), 1)]
    return score


def _write(score, tmp_path, name="score.musicxml"):
    path = tmp_path / name
    musicxml.write(score, path)
    return path


# ------------------------------------------------------------ round trip

def test_every_kind_survives_the_round_trip(tmp_path):
    score = _score()
    back = events.read(_write(score, tmp_path))
    assert musicxml.round_trip_differences(score, back) == {}
    assert [(b.number, b.page, b.system) for b in back.bars] == [(b.number, b.page, b.system) for b in score.bars]
    assert [(p.name, p.staves) for p in back.parts] == [("Soprano", 1), ("Piano", 2)]


def test_rehearsal_metronome_and_credits_are_written(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_markings

    root = events.read_root(_write(_score(), tmp_path))
    credits, rehearsals, metronomes, names, _ = check_markings.truth_extras(root)
    assert ("title", "A Test Song") in credits and ("composer", "Anon.") in credits
    assert rehearsals == [(1, "A")] and metronomes == [(0, "quarter. = 60")]
    assert root.findtext("work/work-title") == "A Test Song"
    assert root.find("identification/creator").text == "Anon."
    sound = [s.get("tempo") for s in root.iter("sound") if s.get("tempo")]
    assert sound == ["90"]   # a dotted quarter at 60 is 90 quarter notes a minute


def test_jumps_go_with_their_words(tmp_path):
    root = events.read_root(_write(_score(), tmp_path))
    fine = [d for d in root.iter("direction") if d.findtext("direction-type/words") == "Fine"]
    assert len(fine) == 1 and fine[0].find("sound").get("fine") == "yes"
    score = _score()
    score.markings = [m for m in score.markings if m.value != "Fine"]   # no words read: the writer adds them
    assert musicxml.added_words(score) == [(3, "Fine")]
    back = events.read(_write(score, tmp_path, "no-words.musicxml"))
    assert any(m.kind == "words" and m.value == "Fine" for m in back.markings)
    assert musicxml.round_trip_differences(score, back) == {}


def test_chord_symbols_in_musicxml():
    harmony = {}
    for value in ("Bb major", "A m7 / E", "C 7#9"):
        root = ET.fromstring(musicxml.to_string(_chord_score(value)).split("\n", 2)[2])
        h = next(root.iter("harmony"))
        harmony[value] = (h.findtext("root/root-step"), h.findtext("root/root-alter"), h.findtext("kind"),
                          h.find("kind").get("text"), h.findtext("bass/bass-step"))
    assert harmony["Bb major"] == ("B", "-1", "major", None, None)
    assert harmony["A m7 / E"] == ("A", None, "minor-seventh", "m7", "E")
    assert harmony["C 7#9"][2:4] == ("other", "7#9")


def _chord_score(value):
    score = events.Score(parts=[events.Part("", 1)], bars=[events.Bar("1", 1, 1)], bar_counts=[1])
    score.notes = [_note("C", 4, duration=4, value="whole")]
    score.markings = [events.Marking("chord symbol", value, 0, 1, 0, F(0))]
    return score


def test_accidentals_follow_the_key_and_the_bar(tmp_path):
    root = events.read_root(_write(_score(), tmp_path))
    notes = root.find("part").findall("measure")
    shown = [(n.findtext("pitch/step"), n.findtext("accidental")) for m in notes[:2] for n in m.findall("note")
             if n.find("pitch") is not None]
    # key of F: E flat needs a flat, B flat none; the tied B flat none; F sharp then F natural
    assert ("E", "flat") in shown and ("B", None) in shown
    assert ("F", "sharp") in shown and ("F", "natural") in shown


def test_rest_values():
    assert musicxml.rest_value(F(3, 2)) == ("quarter", 1, None)
    assert musicxml.rest_value(F(1, 3)) == ("eighth", 0, (3, 2))
    assert musicxml.rest_value(F(1, 5)) == ("16th", 0, (5, 4))
    assert musicxml.rest_value(F(7, 4)) == ("quarter", 2, None)


def test_tuplet_brackets_only_for_complete_tuplets(tmp_path):
    score = events.Score(parts=[events.Part("", 1)], bars=[events.Bar("1", 1, 1)], bar_counts=[1])
    score.structure = [events.Marking("time", "2/4", 0, None, 0, F(0))]
    third = F(1, 3)
    score.notes = [_note("C", 4, onset=0, duration=third, value="eighth"),
                   _note("D", 4, onset=third, duration=third, value="eighth"),
                   _note("E", 4, onset=2 * third, duration=third, value="eighth"),
                   _note("F", 4, onset=1, duration=third, value="eighth"),     # two of three: incomplete
                   _note("G", 4, onset=1 + third, duration=third, value="eighth")]
    root = events.read_root(_write(score, tmp_path))
    marks = [[t.get("type") for t in n.iter("tuplet")] for n in root.iter("note")]
    assert marks == [["start"], [], ["stop"], [], []]
    assert all(n.find("time-modification") is not None for n in root.iter("note"))
    assert musicxml.round_trip_differences(score, events.read(tmp_path / "score.musicxml")) == {}


def test_a_staff_keeps_at_most_four_voices(tmp_path):
    score = events.Score(parts=[events.Part("", 1)], bars=[events.Bar("1", 1, 1)], bar_counts=[1])
    score.notes = [_note("C", 4, voice=str(v), duration=4, value="whole") for v in range(1, 5)]
    score.notes += [_note("D", 5, voice="5", duration=2, value="half"),         # fits nowhere
                    _note("E", 5, voice="6", duration=4, value="whole")]        # a chord with voice 1
    left = musicxml.write(score, tmp_path / "v.musicxml")
    back = events.read(tmp_path / "v.musicxml")
    assert {n.voice for n in back.notes} == {"1", "2", "3", "4"}
    assert [n.pitch.words() for n in left] == ["D 5"]
    assert len(back.notes) == 5


def test_schema_valid_when_the_schema_is_at_hand(tmp_path):
    etree = pytest.importorskip("lxml.etree")
    from omr import paths

    try:
        schema = paths.require_corpus_dir() / "tools" / "musicxml-4.0-schema" / "musicxml.xsd"
    except paths.CorpusDirError:
        pytest.skip("no corpus folder")
    if not schema.is_file():
        pytest.skip("no MusicXML 4.0 schema in the corpus folder")
    validator = etree.XMLSchema(etree.parse(str(schema)))
    assert validator.validate(etree.parse(str(_write(_score(), tmp_path)))), validator.error_log


def test_a_regression_pair_scores_the_same_written_as_in_memory(tmp_path):
    pytest.importorskip("pymupdf")
    from omr.pdf import rules, structure

    folder = REGRESSION / "pdmx-kyKcYH1Z2cK9" / "musescore4-base"
    score, _ = structure.read_pdf(folder / "score.pdf", notes=True)
    path = _write(score, tmp_path)
    assert musicxml.round_trip_differences(score, events.read(path)) == {}
    flags = rules.check(score)
    (tmp_path / "flags.json").write_text(json.dumps(rules.flag_file(flags)), encoding="utf-8")
    in_memory = metrics.compare_scores(events.read(folder / "score.musicxml"), score, rules.as_harness_flags(flags))
    written = metrics.compare(folder / "score.musicxml", path, flags=metrics.read_flags(tmp_path / "flags.json"))
    assert written["notes"] == in_memory["notes"]
    assert written["flags"] == in_memory["flags"]
    assert written["structure"]["correct"] == in_memory["structure"]["correct"]


# --------------------------------------------------------------- braille

def test_braille_ascii():
    assert braille.to_brf("⠀⠁⠃⠿\n") == " AB=\n"
    assert braille.format_for("x.brf") == "brf" and braille.format_for("x.txt") == "unicode"
    assert braille.format_for("x.brf", "unicode") == "unicode"
    with pytest.raises(ValueError):
        braille.format_for("x.brf", "pdf")


def test_music21_warnings_in_words():
    assert braille._words("<music21.expressions.RehearsalMark 'A'> cannot be transcribed to braille.") \
        == "rehearsal mark: A"
    assert braille._words("Barline <music21.bar.Repeat direction=start> cannot be transcribed to braille.") \
        == "repeat barline: start"


def test_braille_from_the_written_file(tmp_path):
    pytest.importorskip("music21")
    path = _write(_score(), tmp_path)
    lines, left_out = braille.write(path, tmp_path / "score.brf")
    brf = (tmp_path / "score.brf").read_bytes()
    assert lines > 3 and brf.isascii() and b"\r\n" in brf
    braille.write(path, tmp_path / "score.txt")
    unicode_text = (tmp_path / "score.txt").read_text(encoding="utf-8")
    assert all(0x2800 <= ord(c) <= 0x28FF or c in " \n" for c in unicode_text)
    assert all(":" in item for item in left_out)


# --------------------------------------------------------------- command

def test_convert_writes_every_output(tmp_path, capsys):
    pytest.importorskip("pymupdf")
    pytest.importorskip("music21")
    assert main(["convert", str(DATA / "ms4_leland.pdf"), "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    for name in ("ms4_leland.musicxml", "ms4_leland.brf", "ms4_leland-report.txt", "ms4_leland-flags.json"):
        assert (tmp_path / name).is_file(), name
    assert "Read: 1 page, 4 parts, 10 bars" in out
    assert out.strip().splitlines()[-1].startswith("Summary: 1 file converted, 0 failed")
    report = (tmp_path / "ms4_leland-report.txt").read_text(encoding="utf-8")
    assert report.splitlines()[1].startswith("Summary: 10 bars")
    assert json.loads((tmp_path / "ms4_leland-flags.json").read_text(encoding="utf-8"))["version"] == 1


def test_convert_paths_for_one_file(tmp_path, capsys):
    pytest.importorskip("pymupdf")
    xml_path = tmp_path / "out" / "piece.musicxml"
    assert main(["convert", str(DATA / "ms4_leland.pdf"), "--musicxml", str(xml_path),
                 "--report", str(tmp_path / "r.txt"), "--flags", str(tmp_path / "f.json"), "--no-braille",
                 "--out", str(tmp_path / "rest")]) == 0
    assert xml_path.is_file() and (tmp_path / "r.txt").is_file() and (tmp_path / "f.json").is_file()
    assert not list(tmp_path.glob("rest/*.brf"))
    assert main(["convert", "a.pdf", "b.pdf", "--musicxml", "x.musicxml"]) == 2


def test_convert_failures(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("not music", encoding="utf-8")
    assert main(["convert", str(tmp_path / "notes.txt"), str(tmp_path / "missing.pdf")]) == 1
    out = capsys.readouterr().out
    assert "is not a PDF or an image" in out
    assert "Summary: 0 files converted, 2 failed" in out


def test_convert_names_raster_input(tmp_path, capsys):
    pymupdf = pytest.importorskip("pymupdf")
    pytest.importorskip("cv2")
    src = pymupdf.open(str(DATA / "ms4_leland.pdf"))
    pix = src[0].get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
    png = tmp_path / "page.png"
    pix.save(str(png))
    doc = pymupdf.open()
    page = doc.new_page(width=src[0].rect.width, height=src[0].rect.height)
    page.insert_image(page.rect, filename=str(png))
    doc.save(str(tmp_path / "page.pdf"))
    assert main(["convert", str(png), str(tmp_path / "page.pdf"), "--out", str(tmp_path / "out")]) == 1
    out = capsys.readouterr().out
    assert "page.png is an image" in out
    assert "holds images of music, not vector music (every page, Type C or D)" in out
