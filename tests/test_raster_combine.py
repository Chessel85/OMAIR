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


def test_a_part_with_no_time_signature_takes_the_other_parts():
    # the guitar staff's 3/4 was misread, so Engine 2's second voice placed
    # after the bass note, past the end of the bar, went unnoticed (pdmx-XKU7wW67bJ8y)
    signatures = events.SignaturesInForce(events.Score(structure=[events.Marking("time", "3/4", 0, None, 0, Fraction(0))]))
    assert combine.time_in_force(signatures, 2, 1, 5) == "3/4"
    assert combine.time_in_force(signatures, 1, 0, 5) == "3/4"
    assert combine.time_in_force(events.SignaturesInForce(events.Score()), 2, 1, 5) is None


def test_a_chord_with_a_note_more_or_less_is_not_a_chord_read_differently():
    octave = [note(0, 1, "E"), note(0, 1, "E")]
    octave[1] = events.Note(0, 1, "1", 0, Fraction(0), events.Pitch("E", Fraction(0), 5), Fraction(1), "")
    assert combine.chords_differ((octave, []), ([octave[0]], []))           # a note left out
    other = [events.Note(0, 1, "1", 0, Fraction(0), events.Pitch("B", Fraction(0), 6), Fraction(1), "")]
    assert not combine.chords_differ((octave, []), (other, []))             # different pitches (pdmx-QkFxjWipz93Z)


def test_engine_2s_notes_at_the_edge_of_its_crop_count_as_out_of_range():
    # high octaves on a bass staff, up to nine ledger lines: Engine 2 reads a
    # run of D5s at the edge of its crop (pdmx-QkFxjWipz93Z)
    def at(step, octave, onset):
        return events.Note(0, 1, "1", 0, Fraction(onset), events.Pitch(step, Fraction(0), octave), Fraction(1), "")

    one = [at("E", 5, k) for k in range(4)] + [at("E", 6, k) for k in range(4)]
    two = [at("D", 5, k) for k in range(4)]
    bass = events.Score(parts=[events.Part("", 1)], notes=one,
                        structure=[events.Marking("time", "4/4", 0, None, 0, Fraction(0)),
                                   events.Marking("clef", "F 4", 0, 1, 0, Fraction(0))])
    bottom = events.clef_bottom("F 4")
    assert combine.range_faults(two, bottom) == 0
    assert combine.range_faults(two, bottom, (True, True)) == 4
    assert combine.range_faults(two, bottom, (False, True)) == 0        # a lower staff: the crop goes on above
    assert combine.range_faults(one, bottom) == 4                        # the E6s, past six ledger lines
    combined = combine.combine(bass, two, [])
    assert combined.disagree[0].chosen == 1
    octaves = [at(step, 6, k) for k in range(4) for step in "EG"]         # more notes far out than Engine 2 has
    bass.notes = octaves
    assert combine.combine(bass, two, []).disagree[0].chosen == 1        # Engine 1's range is not judged


def test_a_clef_change_inside_a_bar_keeps_the_notes_before_it_in_range():
    # a bass staff turning treble halfway through the bar: its C3s are in range
    # under the bass clef, though nine steps below the treble staff
    # (pdmx-KbWx8rTYY93p)
    notes = [events.Note(0, 2, "1", 0, Fraction(k, 2), events.Pitch("C", Fraction(0), 3), Fraction(1, 2), "")
             for k in range(4)]
    score = events.Score(parts=[events.Part("", 2)], notes=notes,
                         structure=[events.Marking("clef", "F 4", 0, 2, 0, Fraction(0)),
                                    events.Marking("clef", "G 2", 0, 2, 0, Fraction(2))])
    bottoms = combine._clef_bottoms(score)(0, 2, 0)
    assert bottoms == (events.clef_bottom("F 4"), events.clef_bottom("G 2"))
    assert combine.range_faults(notes, bottoms, (False, True)) == 0
    assert combine.range_faults(notes, bottoms[1], (False, True)) == 4


def test_only_engine_1s_doubts_about_notes_count_against_it(monkeypatch):
    from omr.raster import sequence_reading

    def run(rule):
        s = score([note(0, 4, "C")])
        s.doubts = [events.Flag(0, 1, 0, rule, "")]
        monkeypatch.setattr(sequence_reading, "read_notes",
                            lambda *a: ([note(0, 4, "D")], [], {(0, 1, 0)}, {}))
        sequence_reading.combine_notes(s, None, None)
        return [n.pitch.step for n in s.notes]

    assert run("unsure marking") == ["C"]     # an unsure staccato says nothing of the notes
    assert run("unsure symbol") == ["D"]


def test_a_reading_of_rests_only_loses_to_notes_even_with_a_doubt():
    # Engine 2 saw an eighth rest and missed the notes after it (pdmx-AcZ5nsmxvJxs)
    one = [note(0, 1), note(1, 1), note(2, 2)]
    rest = events.Rest(0, 1, "1", 0, Fraction(0), events.WHOLE_BAR)
    doubt = events.Flag(0, 1, 0, "rhythm", "")
    assert combine.combine(score(one), [], [rest], doubts=[doubt]).notes == one
