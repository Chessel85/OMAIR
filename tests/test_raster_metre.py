"""Tests for time signatures on page images checked against the notes (Stage 2.9)."""

from fractions import Fraction

from omr.evaluate import events
from omr.pdf import notation
from omr.raster import metre


def fake_reader(reaches):
    """A stand-in for notation.read_notes: in every part, bar k holds one
    voice reaching reaches[k] quarter notes, whatever the time signature."""
    calls = []

    def read(score, ordered, pages, layouts=()):
        calls.append(sorted({(e.part, e.value) for e in score.structure if e.kind == "time"}))
        for p in range(len(score.parts)):
            for k, reach in enumerate(reaches):
                score.notes.append(events.Note(p, 1, "1", k, Fraction(0), events.Pitch("C", Fraction(0), 4),
                                               Fraction(reach), ""))
        return score

    return read, calls


def score(times, bars):
    """A score before its notes are read: `times` [(part, value)] at bar 0."""
    parts = sorted({p for p, _ in times})
    return events.Score(parts=[events.Part("", 1) for _ in parts],
                        bars=[events.Bar(str(k + 1), 1, 1) for k in range(bars)],
                        structure=[events.Marking("time", v, p, None, 0, Fraction(0)) for p, v in times])


def times(s):
    return sorted((e.part, e.value) for e in s.structure if e.kind == "time")


def test_a_misread_time_signature_gives_way_to_the_one_the_notes_fill(monkeypatch):
    # 2/1 with its 1 hidden in the clef: cut time stays in one part, the 1 is a 4 in the other (pdmx-C1P12SpiRUyB)
    read, _ = fake_reader([8] * 6)
    monkeypatch.setattr(notation, "read_notes", read)
    s = metre.read_notes(score([(0, "2/2"), (1, "2/4")], 6), [], [])
    assert times(s) == [(0, "2/1"), (1, "2/1")]
    assert not notation.unfilled_bars(s)


def test_a_time_signature_the_notes_fill_is_read_once(monkeypatch):
    read, calls = fake_reader([4] * 6)
    monkeypatch.setattr(notation, "read_notes", read)
    s = metre.read_notes(score([(0, "4/4")], 6), [], [])
    assert times(s) == [(0, "4/4")] and len(calls) == 1


def test_a_value_that_does_not_halve_the_unfilled_bars_is_not_kept(monkeypatch):
    # every other bar short of a note: no other time fits better
    read, calls = fake_reader([4, 3, 4, 3, 4, 3])
    monkeypatch.setattr(notation, "read_notes", read)
    s = metre.read_notes(score([(0, "4/4")], 6), [], [])
    assert times(s) == [(0, "4/4")] and len(calls) > 1


def test_a_digit_the_detector_confuses_is_tried_first(monkeypatch):
    # 9/8 read as 6/8 (os-lc6007571): after the value read, 9/8 is tried next
    read, calls = fake_reader([Fraction(9, 2)] * 6)
    monkeypatch.setattr(notation, "read_notes", read)
    s = metre.read_notes(score([(0, "6/8"), (1, "6/8")], 6), [], [])
    assert times(s) == [(0, "9/8"), (1, "9/8")]
    assert calls[2] == [(0, "9/8"), (1, "9/8")]


def test_a_few_unfilled_bars_do_not_change_the_time(monkeypatch):
    # 3 of 8 bars misread for other reasons (pdmx-a9ydR5bAeJrn: 4/4 became 4/2)
    read, calls = fake_reader([4, 4, 4, 5, 4, 4, 5, 5])
    monkeypatch.setattr(notation, "read_notes", read)
    s = metre.read_notes(score([(0, "4/4")], 8), [], [])
    assert times(s) == [(0, "4/4")] and len(calls) == 1


def test_between_values_that_fill_alike_the_shorter_bar_is_kept(monkeypatch):
    # a reader that spreads notes out fills any bar of 4 quarters or more
    calls = []

    def read(score, ordered, pages, layouts=()):
        value = next(e.value for e in score.structure if e.kind == "time")
        length = metre._length(value)
        calls.append(value)
        for k in range(6):
            score.notes.append(events.Note(0, 1, "1", k, Fraction(0), events.Pitch("C", Fraction(0), 4),
                                           length if length >= 4 else Fraction(4), ""))
        return score

    monkeypatch.setattr(notation, "read_notes", read)
    s = metre.read_notes(score([(0, "2/4")], 6), [], [])
    assert times(s) == [(0, "2/2")]
