"""Tests for Stage 1.3: notes and rests from vector PDFs (omr.pdf.notation)
and the note check."""

import sys
from fractions import Fraction
from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from omr.evaluate import events  # noqa: E402
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
    assert events.key_alter(2, "F") == 1 and events.key_alter(2, "C") == 1 and events.key_alter(2, "G") == 0
    assert events.key_alter(-3, "A") == -1 and events.key_alter(-3, "D") == 0
    assert events.key_alter(0, "B") == 0


def test_accidental_names():
    assert notation.accidental_alter("accidentalSharp") == 1
    assert notation.accidental_alter("accidentalDoubleFlat") == -2
    assert notation.accidental_alter("accidentalNatural") == 0
    assert notation.accidental_alter("accidentalQuarterToneSharpStein") is None
    assert notation.accidental_alter("noteheadBlack") is None


def test_tuplet_normal_numbers():
    assert notation._normal(3) == 2
    assert notation._normal(5) == 4
    assert notation._normal(2) == 3      # a duplet in compound time
    assert notation._normal(4) == 3     # a quadruplet: 4 in the time of 3
    assert notation._normal(7) == 4


# ------------------------------------------------------- columns and onsets

class _Symbol:
    def __init__(self, x, y, name="noteheadBlack"):
        self.name, self.x, self.y = name, x, y
        self.box = (x, y - 2.5, x + 6.5, y + 2.5)
        self.size = 20.0
        self.source = "smufl"


def _chord(x, base, direction=1, step=4, dots=0, top=100.0):
    staff = layout.Staff(1, top, SPACE, 50.0, 550.0)
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


def test_a_whole_bar_rest_beside_other_voices_starts_the_bar():
    # 6/8: a whole rest in the middle of the bar, and six eighths of the other voice
    rest = _chord(160, 3, 0, 4)
    rest.heads, rest.rest, rest.whole_bar = [], _Symbol(160, 110, "restWhole"), True
    notes = [_chord(100 + 25 * k, Fraction(1, 2), -1, 2) for k in range(6)]
    assert notation.assign_onsets(notes + [rest], SPACE, Fraction(3)) == 0
    assert rest.onset == 0
    assert [e.onset for e in notes] == [Fraction(k, 2) for k in range(6)]


def test_a_collision_is_between_voices_of_one_staff():
    # two staves read together: a chord stem down below, a note stem up of the
    # staff above at the same place, and a unison stem up set aside right of the chord
    above = _chord(100, Fraction(1, 2), 1, 2, top=40.0)
    chord = _chord(100, Fraction(1, 2), -1, 0)
    aside = _chord(107, Fraction(1, 4), 1, 0)
    assert len(notation._columns([above, chord, aside], SPACE)) == 1


def test_a_note_in_line_with_a_unison_set_aside_starts_with_it():
    # a chord stem down, a unison stem up set aside to its right, and a note
    # of the staff above in line with the unison, not with the chord
    chord = _chord(100, Fraction(1, 2), -1, 0)
    aside = _chord(107, Fraction(1, 4), 1, 0)
    above = _chord(107, Fraction(1, 2), 1, 2, top=40.0)
    assert len(notation._columns([chord, above, aside], SPACE)) == 1


def _heads_at(x, steps, name="noteheadBlack"):
    staff = _STAFF
    return [notation.Head(_Symbol(x, staff.bottom - s * SPACE / 2, name), staff, s, False) for s in steps]


_STAFF = layout.Staff(1, 100.0, SPACE, 50.0, 550.0)


def test_a_unison_drawn_twice_goes_to_both_stems_and_the_chord_keeps_its_middle():
    # a chord stem down (C E G C, its stem from the top C) and a sixteenth stem
    # up on the lower C, drawn twice; both stems run past every notehead
    heads = _heads_at(100, [0, 0, 2, 4, 7])
    up = notation.Stem(106.5, 80.0, heads[0].y, list(heads), up=True)
    down = notation.Stem(100.0, heads[4].y, 140.0, list(heads), up=False)
    notation._share_heads([up, down], SPACE)
    assert sorted(h.step for h in up.heads) == [0]
    assert sorted(h.step for h in down.heads) == [0, 2, 4, 7]


def test_an_open_and_a_black_unison_go_to_the_half_and_the_beamed_note():
    # a half note stem up from E with G above, and a sixteenth stem down from
    # the G: the G is drawn open and black on one spot
    e = _heads_at(100, [2], "noteheadHalf")
    g_open = _heads_at(100, [4], "noteheadHalf")
    g_black = _heads_at(100.2, [4])
    heads = e + g_open + g_black
    up = notation.Stem(106.5, 80.0, e[0].y, list(heads), up=True)
    down = notation.Stem(100.0, g_open[0].y, 140.0, g_open + g_black, up=False, flags=2)
    notation._share_heads([up, down], SPACE)
    for stem in (up, down):
        for h in stem.heads:
            h.stem = stem
    half, sixteenth = notation.make_chords(heads, [up, down], SPACE)
    assert half.base == 2 and sorted(h.step for h in half.heads) == [2, 4]
    assert sixteenth.base == Fraction(1, 4) and [h.symbol.name for h in sixteenth.heads] == ["noteheadBlack"]


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
    # no bracketed number: nothing to join, even where the pieces add up to a bar
    score = _three_four_score([3, 1, 2])
    score.notes = [_note(1, 0), _note(2, 0)]
    notation.join_split_bars(score, [_system([object(), None]), _system([object()])])
    assert len(score.bars) == 3


def test_a_line_starting_with_no_bar_number_where_the_others_have_one_continues_a_bar():
    # LilyPond without bracketed numbers: the systems after the first carry
    # their bar numbers, except one that starts in the middle of a bar
    score = _three_four_score([3, 1, 2, 3, 3])
    score.notes = [_note(1, 0), _note(2, 0), _note(2, 1), _note(3, 0)]
    def number(text):
        return [SimpleNamespace(text=text, box=(30.0, 85.0, 48.0, 95.0))]
    ordered = [_system([object(), None]), _system([object(), object()]),
               _system([object()], number("4")), _system([object()], number("5"))]
    notation.join_split_bars(score, ordered)
    assert len(score.bars) == 4 and score.bars[1].length == 3


def _head_event(x, step, direction, dots=0, rest=None):
    head = SimpleNamespace(step=step, box=(x, 0.0, x + 6.5, 6.0))
    return notation.Event(staff=None, x=x, right=x + 6.5, heads=[] if rest else [head], rest=rest,
                          direction=direction, dots=dots)


def test_a_unison_beside_a_dotted_note_starts_with_it():
    # a dotted quarter, stem down, and a sixteenth on the same note, stem up,
    # set to the right of the dot: one column (space 5)
    dotted = _head_event(340.0, -5, -1, dots=1)
    assert notation._same_column([dotted], _head_event(352.0, -5, 1), 5.0)
    # the same note again in the same voice, after the dot, is a new column
    assert not notation._same_column([dotted], _head_event(352.0, -5, -1), 5.0)
    # and so is the other voice's note when that voice has a rest in the column
    rest = _head_event(340.0, 0, 0, rest=SimpleNamespace(name="rest16th"))
    assert not notation._same_column([rest, dotted], _head_event(352.0, -5, 1), 5.0)


def test_a_staccato_under_the_next_note_is_not_a_dot_of_this_one():
    # D then E, both eighths, staccato dots under each; the dot under E is
    # level with D (one step lower), right of it
    d_head = SimpleNamespace(step=-1, y=105.0, box=(100.0, 102.5, 106.5, 107.5))
    e_head = SimpleNamespace(step=0, y=102.5, box=(115.0, 100.0, 121.5, 105.0))
    d_note = notation.Event(staff=None, x=100.0, right=106.5, heads=[d_head], direction=1)
    e_note = notation.Event(staff=None, x=115.0, right=121.5, heads=[e_head], direction=1)
    staccato = SimpleNamespace(box=(117.0, 104.0, 119.0, 106.0))   # under E, level with D
    notation.attach_dots([d_note, e_note], [staccato], 5.0, [])
    assert d_note.dots == 0
    # a real dot, right of D and level with it, still counts
    dot = SimpleNamespace(box=(108.0, 104.0, 110.0, 106.0))
    notation.attach_dots([d_note, e_note], [dot], 5.0, [])
    assert d_note.dots == 1
    # over a note of the other voice (stem the other way) a dot is still a dot
    e_note.direction = -1
    notation.attach_dots([d_note, e_note], [staccato], 5.0, [])
    assert d_note.dots == 1


def test_a_staccato_beside_a_rest_is_not_its_dot():
    # a sixteenth rest inside a beam, then a chord stem up with a staccato
    # under it, level with the rest (Verovio)
    rest = notation.Event(staff=None, x=100.0, right=104.0, rest=SimpleNamespace(box=(100.0, 95.0, 104.0, 110.0)))
    head = SimpleNamespace(step=0, y=102.5, box=(110.0, 100.0, 116.5, 105.0))
    chord = notation.Event(staff=None, x=110.0, right=116.5, heads=[head], direction=1)
    staccato = SimpleNamespace(box=(112.0, 107.0, 114.0, 109.0))
    notation.attach_dots([rest, chord], [staccato], 5.0, [])
    assert rest.dots == 0


# --------------------------------------------- tuplet brackets and tremolos

def test_a_bracket_hook_tells_which_side_its_notes_are():
    mark = notation.TupletMark(3, None, 50, 100, (48, 97, 52, 103))
    lines = [(20.0, 100.0, 46.0, 100.0), (54.0, 100.0, 80.0, 100.0)]
    down = [(20.0, 100.0, 104.0, 0.4), (80.0, 100.0, 104.0, 0.4)]
    up = [(20.0, 96.0, 100.0, 0.4), (80.0, 96.0, 100.0, 0.4)]
    assert notation._bracket_span(mark, lines, down, 5.0) == (20.0, 80.0, 1)
    assert notation._bracket_span(mark, lines, up, 5.0) == (20.0, 80.0, -1)
    assert notation._bracket_span(mark, lines, [], 5.0) == (20.0, 80.0, 0)
    # a bracket over a whole bar: halves longer than 30 spaces
    long = [(20.0, 100.0, 46.0, 100.0), (54.0, 100.0, 300.0, 100.0)]
    assert notation._bracket_span(mark, long, [], 5.0) == (20.0, 300.0, 0)


def test_strokes_between_two_stems_are_a_two_note_tremolo():
    staff = layout.Staff(1, 100.0, SPACE, 50.0, 550.0)

    def quarter(x):
        stem = notation.Stem(x + 6.5, 80.0, 105.0, up=True)
        return notation.Event(staff, x, x + 6.5, stem=stem, base=Fraction(1), direction=1)

    first, second = quarter(100.0), quarter(140.0)
    # two strokes floating between the stems, short of both
    strokes = [notation.Beam(112.0, 140.0, 88.0, 88.0, 1.0), notation.Beam(112.0, 140.0, 91.0, 91.0, 1.0)]
    notation.two_note_tremolos([first, second], strokes, SPACE)
    assert first.duration == second.duration == Fraction(1, 2)
    # strokes across one stem are a tremolo on that note alone
    alone = quarter(200.0)
    notation.two_note_tremolos([alone], [notation.Beam(203.0, 212.0, 88.0, 88.0, 1.0)], SPACE)
    assert alone.duration == 1


def test_the_notehead_of_a_metronome_mark_is_not_a_note():
    # LilyPond's "♩ = 100" sits low enough to touch the staff (pdmx-dmijoepBt994)
    head = SimpleNamespace(box=(103.0, 82.6, 107.6, 86.9))
    mark = SimpleNamespace(text="= 100", box=(109.7, 78.9, 134.0, 88.7))
    assert notation._tempo_head(head, [mark], SPACE)
    assert not notation._tempo_head(head, [SimpleNamespace(text="Allegro", box=mark.box)], SPACE)
