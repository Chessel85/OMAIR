"""Tests for combining Engine 1 and Engine 2 staff bar by staff bar (Stage 2.7)."""

from fractions import Fraction

from omr.evaluate import events
from omr.raster import combine


def note(onset, duration, step="C", bar=0, voice="1", staff=1):
    return events.Note(0, staff, voice, bar, Fraction(onset), events.Pitch(step, Fraction(0), 4),
                       Fraction(duration), "")


def score(notes, time="4/4"):
    return events.Score(parts=[events.Part("", 1)], notes=notes,
                        structure=[events.Marking("time", time, 0, None, 0, Fraction(0)),
                                   events.Marking("clef", "G 2", 0, 1, 0, Fraction(0))])


def test_fullness_counts_gaps_overruns_and_a_short_bar():
    full = [note(0, 1), note(1, 1), note(2, 2)]
    assert combine.fullness_faults(full, [], Fraction(4)) == 0
    assert combine.fullness_faults([note(0, 1), note(2, 2)], [], Fraction(4)) == 1       # gap
    assert combine.fullness_faults([note(0, 2), note(2, 3)], [], Fraction(4)) == 1       # runs past
    assert combine.fullness_faults([note(0, 1), note(1, 1)], [], Fraction(4)) == 1       # stops short
    assert combine.fullness_faults([], [], Fraction(4)) == 1                             # empty
    assert combine.fullness_faults([], [], None) == 1


def test_an_empty_reading_is_never_chosen():
    one = [note(0, 1), note(1, 2, "D")]                 # overlaps and stops short
    combined = combine.combine(score(one), [], [])
    assert combined.notes == one and not combined.disagree
    two = [note(0, 4)]
    combined = combine.combine(score([]), two, [])
    assert combined.notes == two and not combined.disagree


def test_engine_2s_notes_carry_engine_1s_markings():
    from dataclasses import replace
    one = [replace(note(0, 1), marks=frozenset({"staccato"}), lyrics=((1, "la"),)),
           replace(note(1, 1, "E"), slurs=(("start", 1),)), replace(note(1, 1, "G"), marks=frozenset({"arpeggiate"}))]
    two = [note(0, 2), note(2, 1, "G"), note(2, 1, "E")]     # second onset placed differently
    carried = combine.with_marks(one, two)
    assert carried[0].marks == {"staccato"} and carried[0].lyrics == ((1, "la"),)
    assert carried[1].marks == {"arpeggiate"} and carried[2].slurs == (("start", 1),)
    assert [n.duration for n in carried] == [n.duration for n in two]


def test_fullness_takes_voices_apart_and_tuplets_as_written():
    third = Fraction(2, 3)
    triplets = [note(Fraction(k) * third, third) for k in range(3)] + [note(2, 2)]
    lower = [note(0, 4, "E", voice="2")]
    assert combine.fullness_faults(triplets + lower, [], Fraction(4)) == 0


def test_agreeing_bars_keep_engine_1():
    one = [note(0, 4)]
    combined = combine.combine(score(one), [note(0, 4)], [])
    assert combined.notes == one and not combined.disagree


def test_fewer_faults_wins_and_mixed_takes_engine_2s_durations():
    one = [note(0, 1), note(1, 1), note(2, 1)]          # a half note read as a quarter: stops short
    two = [note(0, 1), note(1, 1), note(2, 2, "D")]     # right length, wrong pitch
    combined = combine.combine(score(one), two, [])
    assert combined.disagree[0].chosen == "mixed"
    assert sorted((n.onset, n.pitch.step, n.duration) for n in combined.notes) == [
        (0, "C", 1), (1, "C", 1), (2, "C", 2)]


def test_a_tie_goes_to_the_first_preferred():
    one, two = [note(0, 4, "C")], [note(0, 4, "D")]
    assert combine.combine(score(one), two, []).notes == one
    assert combine.combine(score(one), two, [], prefer=(2, 1)).notes == two


def test_engine_1_doubt_counts_against_it():
    one, two = [note(0, 4, "C")], [note(0, 4, "D")]
    doubt = events.Flag(0, 1, 0, "doubt", "perhaps a flat")
    assert combine.combine(score(one), two, [], doubts=[doubt], prefer=(1, 2)).notes == two


def test_percussion_keeps_engine_1():
    one, two = [note(0, 4, "C")], [note(0, 4, "D")]
    drums = events.Score(parts=[events.Part("", 1)], notes=one,
                         structure=[events.Marking("clef", "percussion", 0, 1, 0, Fraction(0))])
    assert combine.combine(drums, two, [], prefer=(2, 1)).notes == one


def test_disagreement_is_put_in_words():
    one = ([note(0, 2, "F"), note(2, 2)], [])
    two = ([note(0, 2, "G"), note(2, 2)], [])
    assert combine.describe(one, two) == "the engines disagree on the first note: Engine 1 reads F 4, Engine 2 G 4"
    longer = ([note(0, 2), note(2, 2)], [])
    shorter = ([note(0, 2), note(2, 1)], [])
    assert "length of the second note (C 4)" in combine.describe(longer, shorter)
    assert combine.describe(longer, ([note(0, 4)], [])) == (
        "the engines disagree on the number of notes: Engine 1 reads 2 notes, Engine 2 1 note")


def test_each_staff_bar_that_differs_is_a_doubt():
    one, two = [note(0, 4, "C", bar=0), note(0, 4, "E", bar=1)], [note(0, 4, "D", bar=0), note(0, 4, "E", bar=1)]
    flags = combine.disagreement_flags(combine.combine(score(one), two, []))
    assert [(f.bar, f.rule, f.onset) for f in flags] == [(0, combine.RULE, 0)]
    assert flags[0].reason.endswith("kept Engine 1's reading")


def test_engine_2_a_bar_out_of_step_keeps_engine_1():
    from types import SimpleNamespace
    steps = ["C", "D", "E", "F", "G", "A"]
    one = [note(0, 4, s, bar=b) for b, s in enumerate(steps)]
    doubts = [SimpleNamespace(part=0, staff=1, bar=b) for b in range(6)]   # Engine 1 doubted everywhere
    other = [note(0, 4, "B", bar=b) for b in range(6)]
    assert combine.combine(score(one), other, [], doubts).notes == other
    two = [note(0, 4, "B")] + [note(0, 4, s, bar=b + 1) for b, s in enumerate(steps[:-1])]   # a bar late
    combined = combine.combine(score(one), two, [], doubts)
    assert sorted(combined.notes, key=lambda n: n.bar) == one and not combined.disagree
