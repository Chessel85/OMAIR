"""Tests for placing Engine 2's reading in Engine 1's parts and bars (Stage 2.6), without homr."""

from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import numpy as np

from omr.evaluate import events
from omr.raster import sequence_reading as sr


def note(part, staff, bar, octave=4, onset=Fraction(0)):
    return events.Note(part, staff, "1", bar, onset, events.Pitch("C", Fraction(0), octave), Fraction(1), "quarter")


def rest(part, staff, bar):
    return events.Rest(part, staff, "1", bar, Fraction(0), Fraction(1))


def test_place_moves_a_reading_into_the_parts_staves_and_bars():
    read = events.Score(bars=[None, None], notes=[note(0, 1, 0), note(0, 2, 1)], rests=[rest(0, 1, 1)])
    unit = sr.Unit(part=2, numbers=[1, 2], first_bar=10, bars=2, image=None)
    notes, rests, same = sr.place(read, unit)
    assert same
    assert [(n.part, n.staff, n.bar) for n in notes] == [(2, 1, 10), (2, 2, 11)]
    assert [(r.part, r.staff, r.bar) for r in rests] == [(2, 1, 11)]


def test_place_leaves_out_bars_beyond_the_system_and_maps_a_lone_lower_staff():
    read = events.Score(bars=[None, None, None], notes=[note(0, 1, 0), note(0, 1, 2)])
    unit = sr.Unit(part=0, numbers=[2], first_bar=4, bars=2, image=None)
    notes, _, same = sr.place(read, unit)
    assert not same
    assert [(n.staff, n.bar) for n in notes] == [(2, 4)]


def test_octave_clef_moves_notes_from_where_it_stands():
    score = events.Score(structure=[
        events.Marking("clef", "G 2 octave -1", 0, 1, 0, Fraction(0)),
        events.Marking("clef", "G 2", 0, 1, 3, Fraction(0)),
    ])
    shift = sr.octave_shifts(score)
    assert shift(note(0, 1, 1)) == -1
    assert shift(note(0, 1, 3)) == 0
    assert shift(note(0, 2, 1)) == 0


def test_units_cut_each_part_of_an_image_page_with_homrs_margins():
    def staff(top):
        return SimpleNamespace(top=top, bottom=top + 4, space=1.0, x0=10.0, x1=90.0)

    system = SimpleNamespace(staves=[staff(10), staff(30), staff(50)], bars=[None] * 3)
    mapping = SimpleNamespace(staves=[(0, 1), (1, 1), (1, 2)])
    place = SimpleNamespace(to_pixels=lambda box: tuple(2 * v for v in box))   # 2 pixels a point
    image_page = SimpleNamespace(grey=np.full((200, 200), 255, np.uint8), place=place)
    pl = SimpleNamespace(page=1)
    vector_pl = SimpleNamespace(page=2)
    found = sr.units(([(pl, system, mapping), (vector_pl, system, mapping)], []), [image_page, object()])
    assert [(u.part, u.numbers, u.first_bar, u.bars) for u in found] == [(0, [1], 0, 3), (1, [1, 2], 0, 3)]
    # 2 spaces each side of the staff, 4 above and below: (8, 6) to (92, 18) points
    assert found[0].image.shape == (24, 168)


def test_a_long_system_is_cut_into_the_fewest_even_pieces():
    assert sr.pieces([10, 10]) == [0]
    assert sr.pieces([26, 36, 16, 26, 20]) == [0, 2]
    assert sr.pieces([30] * 6) == [0, 2, 4]
    assert sr.pieces([30] * 6, last_start=2) == [0, 2]   # no piece after a key change
    assert sr.pieces([200]) == [0]


def test_a_piece_after_a_clef_change_is_moved_to_the_clef_in_force():
    clefs = {(0, 1): [((0, Fraction(0)), "G 2"), ((3, Fraction(0)), "F 4"), ((5, Fraction(1)), "G 2")]}
    assert sr.clef_shifts(clefs, 0, [1], 0, 2) == {}
    # read under the treble clef in front, a bass clef note is 12 steps lower
    assert sr.clef_shifts(clefs, 0, [1], 0, 4) == {1: (-12, (5, Fraction(1)))}


def test_moving_by_steps_keeps_printed_accidentals_and_follows_the_key():
    def at(step, alter, octave):
        return replace(note(0, 1, 0), pitch=events.Pitch(step, Fraction(alter), octave))

    # 12 steps down, from a treble to a bass clef reading: B flat from the key of F becomes D
    assert sr.moved_by_steps(at("B", -1, 4), -12, -1).pitch == events.Pitch("D", Fraction(0), 3)
    # a sharp the key does not give was printed, and stays
    assert sr.moved_by_steps(at("C", 1, 5), -12, -1).pitch == events.Pitch("E", Fraction(1), 3)
