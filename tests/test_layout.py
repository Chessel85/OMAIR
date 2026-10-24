"""Tests for Stage 1.2: staves, systems, bars and structure from vector PDFs
(omr.pdf.layout, omr.pdf.structure) and the structure check."""

import sys
from fractions import Fraction
from types import SimpleNamespace
from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from omr.evaluate import events  # noqa: E402
from omr.pdf import layout, structure  # noqa: E402

ROOT = Path(__file__).parent.parent
REGRESSION = ROOT / "regression"
DATA = Path(__file__).parent / "data" / "inspect"
sys.path.insert(0, str(ROOT / "scripts"))
import check_structure  # noqa: E402


# ------------------------------------------------------------- staff lines

def test_stacked_hairlines_are_one_line():
    # five hairlines 0.12 points apart, as a printer driver draws one thick line
    pieces = [(50.0 + 0.12 * k, 70.0, 570.0, 0.12) for k in range(5)]
    lines = layout.horizontal_lines(pieces)
    assert len(lines) == 1
    assert lines[0].thickness == pytest.approx(0.6, abs=0.01)


def test_pieces_of_one_line_are_joined_across_small_gaps():
    lines = layout.horizontal_lines([(100.0, 50.0, 200.0, 0.5), (100.0, 201.0, 400.0, 0.5)])
    assert len(lines) == 1 and lines[0].x0 == 50.0 and lines[0].x1 == 400.0


def test_ledger_lines_of_neighbouring_notes_do_not_make_a_false_staff():
    # five ledger lines on each of three high notes, their ends 1.2 points apart
    pieces = [(60.0 - 5.0 * k, x0, x0 + 10.0, 0.8) for k in range(5) for x0 in (185.0, 196.2, 207.4)]
    lines = layout.horizontal_lines(pieces)
    assert len(lines) == 15
    assert layout.find_staves(lines, 1) == []


def _staff_lines(top, space=5.0, x0=50.0, x1=550.0):
    return [(top + k * space, x0, x1, 0.5) for k in range(5)]


def test_five_equal_lines_are_a_staff():
    staves = layout.find_staves(layout.horizontal_lines(_staff_lines(100.0)), 1)
    assert len(staves) == 1
    assert staves[0].top == 100.0 and staves[0].space == 5.0


def test_a_short_line_above_a_staff_does_not_make_a_false_staff():
    # a bracket line one space above the staff, with the staff's top four lines,
    # is five equal lines; it must not take the staff's place
    lines = layout.horizontal_lines(_staff_lines(100.0) + [(95.0, 210.0, 254.0, 0.5)])
    staves = layout.find_staves(lines, 1)
    assert [s.top for s in staves] == [100.0]


def test_staff_steps():
    staff = layout.Staff(1, 100.0, 5.0, 50.0, 550.0)
    assert staff.step(120.0) == 0      # bottom line
    assert staff.step(100.0) == 8      # top line
    assert staff.step(117.5) == 1      # first space


# ----------------------------------------------------------- the test PDFs

def _read(path):
    return structure.read_pdf(path)


def test_bach_chorale_has_four_named_parts_and_ten_bars():
    score, layouts = _read(DATA / "ms4_leland.pdf")
    assert [(p.name, p.staves) for p in score.parts] == [("Soprano", 1), ("Alto", 1), ("Tenor", 1), ("Bass", 1)]
    assert len(score.bars) == 10
    clefs = [e for e in events.signature_changes(score) if e.kind == "clef"]
    assert [e.value for e in clefs] == ["G 2", "G 2", "F 4", "F 4"]   # the tenor is in the bass clef here


@pytest.mark.parametrize("name", ["ms4_leland.pdf", "ms3_default.pdf", "lilypond.pdf", "verovio.pdf"])
def test_every_engraver_gives_the_same_bars_and_key(name):
    score, _ = _read(DATA / name)
    reference, _ = _read(DATA / "ms4_leland.pdf")
    assert len(score.bars) == len(reference.bars)
    keys = [e.value for e in events.signature_changes(score) if e.kind == "key"]
    assert keys == [e.value for e in events.signature_changes(reference) if e.kind == "key"]


# ------------------------------------------------- regression pairs, end to end

PAIRS = [
    ("pdmx-aig1TYdTKfSA", "musescore4-base"),    # start repeat after the clef, repeats
    ("pdmx-WKLPkfGG8YTD", "musescore4-base"),    # four parts, endings
    ("os-lc5043613", "musescore4-base"),         # voice and piano, key and time changes
    ("pdmx-43id8LnKKREH", "musescore3-base"),    # piano brace drawn as an outline
    ("pdmx-1ZqV4GDzxsoo", "lilypond"),           # six staves joined only by their barlines
    ("pdmx-t8yRZoyLKyGj", "musescore4-base"),    # time change before a start repeat
]


@pytest.mark.parametrize("score_id, job", PAIRS)
def test_regression_pairs_are_structurally_right(score_id, job):
    index = {(f[1], f[2]): f for f in (
        [x.strip() for x in line.split("|")] for line in (REGRESSION / "index.txt").read_text(encoding="utf-8").splitlines()
        if line.startswith("pair"))}
    fields = index[(score_id, job)]
    lines, _ = check_structure.check_pair(REGRESSION / fields[4], REGRESSION / fields[5])
    assert lines == []


# ------------------------------------------------------------ the check

def test_a_clef_after_the_last_note_counts_as_at_the_start_of_the_next_bar():
    score = events.Score()
    score.parts = [events.Part("", 1)]
    score.bars = [events.Bar("1", 1, 1, Fraction(4)), events.Bar("2", 1, 1, Fraction(4))]
    score.structure = [events.Marking("clef", "G 2", 0, 1, 0, Fraction(0)),
                       events.Marking("clef", "F 4", 0, 1, 0, Fraction(4))]
    found = check_structure.comparable(score)["clef"]
    assert (0, 1, 1, True, "F 4") in found


# ------------------------------------------------------------- key signatures

def test_key_letters_follow_the_clef():
    assert structure._letter("G 2", 8) == 3    # F on the top line of a treble staff
    assert structure._letter("F 4", 6) == 3    # F on the fourth line of a bass staff
    assert structure._letter("C 3", 4) == 0    # C on the middle line of an alto staff


def test_octave_clef_value():
    assert structure.clef_value("gClef8vb", 2) == "G 2 octave -1"
    assert structure.clef_value("cClef", 6) == "C 4"


# ------------------------------------------------- systems with hidden staves

def test_shortened_instrument_names():
    for short, full in [("Pno.", "Piano"), ("Bk. Voc.", "Backing Vocals"), ("B. Guit.", "Bass Guitar"),
                        ("B♭ Tpt.", "B♭ Trumpet"), ("Tr. Fa", "Trompes en Fa"), ("Vl. II", "Violins II"),
                        ("Vln. 1", "Violin 1"), ("Piano", "Piano")]:
        assert structure._same_name(short, full), (short, full)
    for short, full in [("Bk. Voc.", "Lead Vocals"), ("Vl. I", "Violins II"), ("Vln. 2", "Violin 1"),
                        ("A.", "Soprano")]:
        assert not structure._same_name(short, full), (short, full)


def _hidden_staff_system(monkeypatch, names, clefs, groups):
    """A system of len(clefs) staves whose names, clefs and brace groups are given."""
    staves = [object() for _ in clefs]
    clef_of = dict(zip(map(id, staves), clefs))
    system = type("System", (), {"staves": staves})()
    page = type("Page", (), {"symbols": [], "text": []})()
    monkeypatch.setattr(structure, "_names_at_left", lambda pl, sy: names)
    monkeypatch.setattr(structure, "_initial_clef", lambda pl, st: clef_of[id(st)])
    monkeypatch.setattr(structure, "staff_groups", lambda sy, symbols, text: groups)
    return page, system


# master: a two-staff part, a one-staff part, a two-staff part, none named in the system
MASTER_NAMES = ["Piano eléctrico", "Piano eléctrico", "Piano de cola", "Piano", "Piano"]
MASTER_CLEFS = ["gClef", "fClef", "fClef", "gClef", "fClef"]
MASTER_SLOTS = [(0, 1), (0, 2), (1, 1), (2, 1), (2, 2)]


def test_a_braced_pair_matches_a_whole_two_staff_part(monkeypatch):
    # treble and bass joined by a brace, then a lone bass staff: the clefs alone
    # fit three ways; the brace and the part edges leave one
    page, system = _hidden_staff_system(monkeypatch, {}, ["gClef", "fClef", "fClef"], [[0, 1], [2]])
    chosen, certain = structure._match_staves(page, system, MASTER_NAMES, MASTER_CLEFS, MASTER_SLOTS)
    assert chosen == [0, 1, 2] and certain


def test_shortened_names_choose_the_parts(monkeypatch):
    names = ["B♭ Trumpet", "Lead Vocals", "Backing Vocals", "Piano", "Piano", "Bass Guitar"]
    clefs = ["gClef", "gClef", "gClef", "gClef", "fClef", "fClef"]
    slots = [(0, 1), (1, 1), (2, 1), (3, 1), (3, 2), (4, 1)]
    page, system = _hidden_staff_system(
        monkeypatch, {0: "B♭ Tpt.", 1: "Bk. Voc.", 2: "Pno.", 4: "B. Guit."},
        ["gClef", "gClef", "gClef", "fClef", "fClef"], [[0], [1], [2, 3], [4]])
    chosen, _ = structure._match_staves(page, system, names, clefs, slots)
    assert chosen == [0, 2, 3, 4, 5]


def test_two_endings_drawn_with_one_joined_line():
    # two first-time brackets side by side: their lines touch and are joined
    # into one, but each has its hook and its number
    from types import SimpleNamespace

    staff = SimpleNamespace(top=100.0, space=5.0)
    bars = [SimpleNamespace(x0=x0, x1=x1, end=object()) for x0, x1 in ((50, 100), (100, 200), (200, 300), (300, 500))]
    system = SimpleNamespace(staves=[staff], bars=bars, x0=50.0, x1=500.0)
    run = lambda text, x: SimpleNamespace(text=text, box=(x, 85.0, x + 5, 92.0))
    page = SimpleNamespace(text=[run("1.", 103), run("1.", 205)],
                           verticals=[(100.0, 83.0, 93.0, 0.5), (198.0, 83.0, 93.0, 0.5),
                                      (202.0, 83.0, 93.0, 0.5), (300.0, 83.0, 93.0, 0.5)])
    line = layout._Line(83.0, 100.0, 300.0, 0.5)
    assert structure.system_endings(page, system, [line]) == [(1, 1, "1", True), (2, 2, "1", True)]


def test_a_one_line_percussion_staff():
    # a five-line staff, then a single line with a percussion clef on it
    from types import SimpleNamespace

    five = [layout._Line(100 + 5 * k, 50, 500, 0.5) for k in range(5)]
    single = layout._Line(160, 50, 500, 0.5)
    staves = layout.find_staves(five + [single], 1)
    assert len(staves) == 1
    clef = SimpleNamespace(name="unpitchedPercussionClef1", box=(55, 155, 60, 165))
    found = layout.one_line_staves(five + [single], staves, [clef], 1)
    assert len(found) == 1 and found[0].lines == 1 and found[0].middle == 160
    # a note on the line is on line 1, as MusicXML counts a one-line staff
    assert found[0].step(160) == 0 and found[0].step(157.5) == 1
    # a line with no percussion clef is not a staff (a long tie, a hairpin)
    assert layout.one_line_staves(five + [single], staves, [], 1) == []


def test_a_bar_number_at_a_staff_start_starts_a_system():
    from types import SimpleNamespace

    staff = layout.Staff(1, 300.0, 4.0, 35.0, 500.0)
    number = SimpleNamespace(text="72", box=(27.0, 291.0, 35.0, 298.0))
    lyric = SimpleNamespace(text="Man,", box=(49.0, 290.0, 72.0, 298.0))
    assert layout._starts_system(staff, [number])
    assert not layout._starts_system(staff, [lyric])


def test_a_brace_round_other_braces_joins_no_staves():
    staff = lambda top: SimpleNamespace(top=top, bottom=top + 20, middle=top + 10, x0=100.0, space=5.0)
    system = SimpleNamespace(staves=[staff(100), staff(150), staff(200), staff(250)], x0=100.0)
    brace = lambda top, bottom, x1: SimpleNamespace(name="brace", box=(x1 - 8, top, x1, bottom))
    inner = [brace(100, 170, 98), brace(200, 270, 98)]
    assert structure.staff_groups(system, inner, ()) == [[0, 1], [2, 3]]
    assert structure.staff_groups(system, [*inner, brace(100, 270, 92)], ()) == [[0, 1], [2, 3]]
    assert structure.staff_groups(system, [brace(100, 270, 92)], ()) == [[0, 1, 2, 3]]


def test_a_time_signature_with_a_zero_is_not_read(monkeypatch):
    staff = SimpleNamespace(top=100.0, bottom=120.0, space=5.0)
    system = SimpleNamespace(bars=[None])
    digit = lambda name, top: SimpleNamespace(name=name, x=50.0, box=(48.0, top, 52.0, top + 9))
    region = [digit("timeSig3", 100.0)]
    monkeypatch.setattr(structure, "_signature_region", lambda *args: region)
    region.append(digit("timeSig4", 111.0))
    assert structure.staff_times(None, system, staff) == [(0, "3/4")]
    region[:] = [digit("timeSig0", 100.0), digit("timeSig0", 111.0)]
    assert structure.staff_times(None, system, staff) == []
