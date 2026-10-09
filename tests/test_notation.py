"""Tests for Stage 1.3: notes and rests from vector PDFs (omr.pdf.notation)
and the note check."""

import sys
from fractions import Fraction
from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from omr.pdf import layout, notation  # noqa: E402

ROOT = Path(__file__).parent.parent
REGRESSION = ROOT / "regression"
sys.path.insert(0, str(ROOT / "scripts"))
import check_notes  # noqa: E402

SPACE = 5.0


# ------------------------------------------------------------------ pitch

def test_pitch_of_staff_steps_under_each_clef():
    assert notation.pitch_of("G 2", 0) == ("E", 4)          # bottom line of a treble staff
    assert notation.pitch_of("G 2", 8) == ("F", 5)          # top line
    assert notation.pitch_of("F 4", 0) == ("G", 2)
    assert notation.pitch_of("C 3", 4) == ("C", 4)          # middle line of an alto staff
    assert notation.pitch_of("G 2 octave -1", 0) == ("E", 3)  # guitar and tenor clef
    assert notation.pitch_of("G 2", -2) == ("C", 4)         # middle C on a ledger line


def test_key_alterations():
    assert notation.key_alter(2, "F") == 1 and notation.key_alter(2, "C") == 1 and notation.key_alter(2, "G") == 0
    assert notation.key_alter(-3, "A") == -1 and notation.key_alter(-3, "D") == 0
    assert notation.key_alter(0, "B") == 0


def test_accidental_names():
    assert notation.accidental_alter("accidentalSharp") == 1
    assert notation.accidental_alter("accidentalDoubleFlat") == -2
    assert notation.accidental_alter("accidentalNatural") == 0
    assert notation.accidental_alter("accidentalQuarterToneSharpStein") is None
    assert notation.accidental_alter("noteheadBlack") is None


def test_tuplet_normal_numbers():
    assert notation._normal(3, False) == 2
    assert notation._normal(5, False) == 4
    assert notation._normal(2, True) == 3      # a duplet in compound time
    assert notation._normal(4, False) == 3     # a quadruplet: 4 in the time of 3
    assert notation._normal(7, False) == 4


# ------------------------------------------------------- columns and onsets

class _Symbol:
    def __init__(self, x, y, name="noteheadBlack"):
        self.name, self.x, self.y = name, x, y
        self.box = (x, y - 2.5, x + 6.5, y + 2.5)
        self.size = 20.0
        self.source = "smufl"


def _chord(x, base, direction=1, step=4, dots=0):
    staff = layout.Staff(1, 100.0, SPACE, 50.0, 550.0)
    head = notation.Head(_Symbol(x, staff.bottom - step * SPACE / 2), staff, step, False)
    return notation.Event(staff, x, x + 6.5, heads=[head], base=Fraction(base), dots=dots, direction=direction)


def test_one_voice_runs_on():
    evs = [_chord(100, 1), _chord(130, Fraction(1, 2)), _chord(150, Fraction(1, 2)), _chord(170, 2)]
    assert notation.assign_onsets(evs, SPACE, Fraction(4)) == 0
    assert [e.onset for e in evs] == [0, 1, Fraction(3, 2), 2]


def test_two_voices_start_together_and_keep_their_own_time():
    # stems up: four quarters; stems down: two halves, at the same places as quarters 1 and 3
    up = [_chord(100 + 30 * k, 1, 1, 6) for k in range(4)]
    down = [_chord(100, 2, -1, 1), _chord(160, 2, -1, 1)]
    assert notation.assign_onsets(up + down, SPACE, Fraction(4)) == 0
    assert [e.onset for e in up] == [0, 1, 2, 3]
    assert [e.onset for e in down] == [0, 2]
    assert {e.voice for e in up} != {e.voice for e in down}


def test_a_voice_that_stops_early_does_not_pull_the_next_column_in():
    # stems down: one quarter, then nothing (rests hidden); stems up: a half and two quarters
    evs = [_chord(100, 2, 1, 6), _chord(100, 1, -1, 1), _chord(160, 1, 1, 6), _chord(190, 1, 1, 6)]
    notation.assign_onsets(evs, SPACE, Fraction(4))
    assert [e.onset for e in evs] == [0, 0, 2, 3]


def test_a_missed_note_costs_one_column_not_the_rest_of_the_bar():
    # the first eighth was not read: the half note alone cannot place the eighths after it
    evs = [_chord(100, 2, -1, 1), _chord(121, Fraction(1, 2), 1, 8), _chord(142, Fraction(1, 2), 1, 6),
           _chord(163, Fraction(1, 2), 1, 3), _chord(184, 1, 1, 4), _chord(184, 2, -1, -3)]
    notation.assign_onsets(evs, SPACE, Fraction(4))
    assert all(e.onset < 4 for e in evs)
    assert evs[4].onset == 2


def test_a_unison_set_aside_is_one_column():
    # an eighth with its stem up, and a half note in the other voice set aside to its right
    up = _chord(100, Fraction(1, 2), 1, 0)
    down = _chord(107, 2, -1, 0)
    assert len(notation._columns([up, down], SPACE)) == 1


def test_a_second_in_one_voice_is_two_columns():
    # a sixteenth stem down then a dotted eighth stem up a step lower: one voice, two times
    a = _chord(100, Fraction(1, 4), -1, 5)
    b = _chord(108.5, Fraction(3, 4), 1, 4)
    assert len(notation._columns([a, b], SPACE)) == 2


def test_other_staves_place_a_voice_that_starts_late():
    # a voice whose rests are hidden: its first note lines up with the third column of another staff
    late = [_chord(160, Fraction(1, 2), 1, 6), _chord(175, Fraction(1, 2), 1, 6)]
    reference = [(100, Fraction(0)), (130, Fraction(1)), (160, Fraction(2)), (175, Fraction(5, 2))]
    notation.assign_onsets(late, SPACE, Fraction(4), reference)
    assert [e.onset for e in late] == [2, Fraction(5, 2)]


def test_dotted_and_tuplet_durations():
    e = _chord(100, Fraction(1, 2), dots=1)
    assert e.duration == Fraction(3, 4)
    e.tuplet = (3, 2)
    assert e.duration == Fraction(1, 2)


# ---------------------------------------------------------------- beams

def test_a_sloped_beam_from_a_four_sided_shape():
    beam = notation._quad_beam([(100, 50), (140, 48), (140, 50.5), (100, 52.5)], SPACE)
    assert beam is not None
    assert beam.thickness == pytest.approx(2.5)
    assert beam.y_at(120) == pytest.approx(50.25)


def test_a_staff_line_is_not_a_beam():
    assert notation._quad_beam([(100, 50), (400, 50), (400, 50.5), (100, 50.5)], SPACE) is None


# ------------------------------------------------- regression pairs, end to end

PAIRS = [
    ("pdmx-WKLPkfGG8YTD", "musescore4-base", 1.0),    # four parts
    ("pdmx-kyKcYH1Z2cK9", "musescore4-base", 1.0),    # three voices on staves, grace notes
    ("pdmx-nB6NCro6E24g", "musescore4-base", 0.98),   # triplets, notes high above the staff
    ("pdmx-VyxQ6BWr8tmk", "musescore4-base", 0.97),   # piano, ties across barlines
    ("pdmx-NhuNzKj3Y1Ds", "musescore4-base", 0.97),   # guitar in two voices
    ("pdmx-Gpyq556zefWD", "lilypond", 1.0),
    ("pdmx-4viYqFUrsJaX", "musescore3-base", 0.98),   # hidden stems, unisons between voices
]


@pytest.mark.parametrize("score_id, job, floor", PAIRS)
def test_regression_pairs_read_their_notes(score_id, job, floor):
    pairs = check_notes.pairs(REGRESSION, job, None, score_id)
    assert len(pairs) == 1
    _, _, pdf, truth = pairs[0]
    figures = check_notes.check_pair(pdf, truth)
    assert check_notes.accuracy(figures["notes"]) >= floor
