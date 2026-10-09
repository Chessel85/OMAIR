"""Tests for Stage 1.2: staves, systems, bars and structure from vector PDFs
(omr.pdf.layout, omr.pdf.structure) and the structure check."""

import sys
from fractions import Fraction
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
