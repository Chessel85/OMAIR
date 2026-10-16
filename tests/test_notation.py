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


# ------------------------------------------------ a tuplet over part of a beam

def _beamed(values, xs):
    return [notation.Event(staff=None, x=x, right=x + 4, base=Fraction(v)) for v, x in zip(values, xs)]


def test_a_triplet_number_over_part_of_a_beam_group():
    # an eighth beamed to three triplet sixteenths, the "3" over the sixteenths
    group = _beamed(["1/2", "1/4", "1/4", "1/4"], [0, 20, 30, 40])
    mark = notation.TupletMark(3, None, 32, -10, (30, -12, 34, -8))
    assert notation._tuplet_run(mark, group) == group[1:]


def test_a_triplet_number_over_a_whole_group_keeps_it():
    group = _beamed(["1/2", "1/2", "1/2"], [0, 20, 40])
    mark = notation.TupletMark(3, None, 22, -10, (20, -12, 24, -8))
    assert notation._tuplet_run(mark, group) == group
    # an eighth and a sixteenth under each of two numbers: the whole group
    # is two triplets, so each number keeps it
    group = _beamed(["1/2", "1/4", "1/2", "1/4"], [0, 15, 30, 45])
    first = notation.TupletMark(3, None, 9, -10, (7, -12, 11, -8))
    assert notation._tuplet_run(first, group) == group


# ------------------------------------------------- bars and repeats from the page

from types import SimpleNamespace  # noqa: E402

from omr.evaluate import events  # noqa: E402


def _system(bars_end, text=()):
    staff = SimpleNamespace(top=100.0, space=5.0)
    bars = [SimpleNamespace(end=end) for end in bars_end]
    return (SimpleNamespace(text=list(text)), SimpleNamespace(staves=[staff], bars=bars, x0=50.0), None)


def _note(bar, onset, lyrics=()):
    pitch = events.Pitch("C", Fraction(0), 4)
    return events.Note(0, 1, "1", bar, Fraction(onset), pitch, Fraction(1), "quarter", lyrics=tuple(lyrics))


def _three_four_score(lengths):
    score = events.Score(parts=[events.Part("Voice", 1)])
    score.bars = [events.Bar(str(k + 1), 1, 1, Fraction(n)) for k, n in enumerate(lengths)]
    score.structure = [events.Marking("time", "3/4", 0, None, 0, Fraction(0))]
    return score


def test_a_bar_broken_across_a_line_is_one_bar():
    # the first system ends with no barline and the next starts with "(2)":
    # bar 2 is one beat at the end of a line and two at the start of the next
    score = _three_four_score([3, 1, 2, 3])
    score.notes = [_note(1, 0), _note(2, 0), _note(2, 1), _note(3, 0)]
    score.structure.append(events.Marking("clef", "G 2", 0, 1, 2, Fraction(0)))   # restated at the line
    bracketed = SimpleNamespace(text="(2)", box=(30.0, 85.0, 48.0, 95.0))
    ordered = [_system([object(), None]), _system([object(), object()], [bracketed])]
    notation.join_split_bars(score, ordered)
    assert len(score.bars) == 3 and score.bars[1].length == 3
    assert [(n.bar, n.onset) for n in score.notes] == [(1, 0), (1, 1), (1, 2), (2, 0)]
    assert not any(e.kind == "clef" for e in score.structure)


def test_a_line_ending_without_a_barline_and_no_sign_stays_two_bars():
    # a full bar on the next line, no bracketed number: nothing to join
    score = _three_four_score([3, 1, 3])
    score.notes = [_note(1, 0), _note(2, 0)]
    notation.join_split_bars(score, [_system([object(), None]), _system([object()])])
    assert len(score.bars) == 3


def test_a_repeat_sung_to_three_verses_is_played_three_times():
    score = _three_four_score([3, 3, 3])
    score.notes = [_note(0, 0, [("1", "a"), ("2", "b"), ("3", "c")]), _note(2, 0, [("1", "d")])]
    score.structure.append(events.Marking("repeat", "backward", 0, None, 1, Fraction(0)))
    notation.repeat_counts_from_verses(score)
    assert [e.value for e in score.structure if e.kind == "repeat"] == ["backward 3 times"]
    # two verses: the repeat is played twice, as written
    score.notes = [_note(0, 0, [("1", "a"), ("2", "b")])]
    score.structure[-1] = events.Marking("repeat", "backward", 0, None, 1, Fraction(0))
    notation.repeat_counts_from_verses(score)
    assert [e.value for e in score.structure if e.kind == "repeat"] == ["backward"]
