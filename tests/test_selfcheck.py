"""Tests for the self-check by re-rendering (Stage 2.8, omr.selfcheck)."""

from dataclasses import replace
from pathlib import Path

import pytest

from omr import selfcheck as sc
from omr.selfcheck import Item

ROOT = Path(__file__).resolve().parent.parent
REGRESSION = ROOT / "regression"


def head(x, step, kind="black", **kw):
    return Item("head", x, step, kind, **kw)


def test_step_words():
    assert sc.step_words(0) == "line 1"
    assert sc.step_words(3) == "space 2"
    assert sc.step_words(8) == "line 5"
    assert sc.step_words(10) == "1 lines above the staff"
    assert sc.step_words(-3) == "1.5 lines below the staff"


def test_columns_join_staves_at_one_onset_and_a_second_on_one_staff():
    items = {0: [head(1.0, 4), head(4.0, 5), head(5.2, 6)],     # a second drawn side by side at 4.0
             1: [head(1.2, 2), Item("rest", 4.1, 4, "restQuarter")]}
    cols = sc.columns(items)
    assert [round(c.x, 1) for c in cols] == [1.0, 4.0]
    assert sorted(cols[1].by_staff) == [0, 1]
    assert len(cols[1].by_staff[0]) == 2


def test_whole_rests_stand_outside_the_columns():
    cols = sc.columns({0: [Item("rest", 6.0, 6, "restWhole"), head(6.2, 4)]})
    assert len(cols) == 1 and cols[0].by_staff[0][0].kind == "head"


def compare(page, drawn):
    page_music = {0: [i for i in page if i.kind in ("head", "rest")]}
    drawn_music = {0: [i for i in drawn if i.kind in ("head", "rest")]}
    return sc.compare_staff((0, page), (0, drawn), sc.columns(page_music), sc.columns(drawn_music))


def test_a_staff_bar_drawn_alike_matches_whatever_the_spacing():
    page = [head(10, 4), Item("dot", 11.5, 5), head(20, 6, "half")]
    drawn = [head(1, 4, alter=0), Item("dot", 2.6, 5), head(4, 6, "half", alter=0)]
    assert compare(page, drawn) is None


def test_differences_are_found_and_said_in_words():
    page = [head(10, 4), head(20, 6)]
    assert "2 notes or rests" in compare(page, [head(1, 4, alter=0)])
    reason = compare(page, [head(1, 4, alter=0), head(3, 7, alter=0)])
    assert "second note or rest" in reason and "space 4" in reason and "line 4" in reason
    reason = compare(page, [head(1, 4, alter=0), head(3, 6, "half", alter=0)])
    assert "black heads, the drawing half" in reason
    reason = compare([head(10, 4), Item("dot", 11.5, 5)], [head(1, 4, alter=0)])
    assert "the page has a dot" in reason


def test_flags_count_only_from_the_page():
    # the converter writes no beams, so a drawn flag on a note the page beams is no difference
    assert compare([head(10, 4)], [head(1, 4, alter=0), Item("flag", 1.2, 0, "flag8th")]) is None
    assert compare([head(10, 4), Item("flag", 11.2, 0, "flag8th")], [head(1, 4, alter=0)]) is not None


def test_accidentals_compare_what_they_give():
    sharp = Item("accidental", 9.0, 4, "accidentalSharp", 1)
    # a courtesy sharp on a note the key already sharpens
    assert compare([sharp, head(10, 4)], [head(1, 4, alter=1, printed=False)]) is None
    # the page prints a sharp, the music read has none
    assert "where the page prints a sharp" in compare([sharp, head(10, 4)], [head(1, 4, alter=0)])
    # the drawing needs an accidental the page does not print
    assert "that the page does not print" in compare([head(10, 4)], [head(1, 4, alter=-1, printed=True)])


def test_repeat_dots_are_not_augmentation_dots():
    items = [head(10, 2), Item("dot", 14.0, 3), Item("dot", 14.0, 5)]
    assert [i.kind for i in sc.without_repeat_dots(items)] == ["head"]


def test_a_head_between_two_staves_goes_where_the_drawing_has_it():
    page = {0: [head(5, -5, other=(1, 13))], 1: [Item("rest", 1, 4, "restQuarter")]}
    drawn = {0: [], 1: [Item("rest", 1, 4, "restQuarter"), head(5, 13)]}
    placed = sc._placed(page, drawn)
    assert placed[0] == [] and [i.step for i in placed[1] if i.kind == "head"] == [13]


def test_mei_alterations():
    mei = ('<mei xmlns="http://www.music-encoding.org/ns/mei"><note xml:id="a" accid.ges="f"/>'
           '<note xml:id="b"><accid accid="s"/></note><note xml:id="c" staff="2"/></mei>')
    assert sc.mei_notes(mei)[:2] == ({"a": (-1, False), "b": (1, True), "c": (0, False)}, {"c": 1})


def test_beams_and_flags_from_mei_values():
    mei = ('<mei xmlns="http://www.music-encoding.org/ns/mei"><note xml:id="a" dur="4"/>'
           '<chord dur="16"><note xml:id="b"/></chord><note xml:id="c" dur="1"/><note xml:id="d" dur="8"/></mei>')
    assert sc.mei_notes(mei)[2] == {"a": 0, "b": 2, "c": None, "d": 1}


def test_beams_are_compared_where_both_sides_have_stems():
    assert compare([head(10, 4, strokes=1)], [head(1, 4, alter=0, strokes=1)]) is None
    reason = compare([head(10, 4, strokes=2)], [head(1, 4, alter=0, strokes=1)])
    assert "2 beams or flags, the drawing 1 beam or flag" in reason
    assert compare([head(10, 4)], [head(1, 4, alter=0, strokes=1)]) is None    # no stem found on the page


def read(score_id, job="musescore4-base"):
    from omr.pdf import structure
    from omr.pdf.read import read_pdf

    pdf = REGRESSION / score_id / job / "score.pdf"
    score, layouts = read_pdf(pdf, notes=True)
    return score, structure.assign_parts(layouts)[0]


def test_a_score_read_rightly_draws_again_alike():
    pytest.importorskip("verovio")
    score, ordered = read("os-lc6159296")
    assert sc.check(score, ordered) == []


def test_a_note_moved_a_step_is_flagged_in_its_bar():
    pytest.importorskip("verovio")
    from omr.evaluate import events

    score, ordered = read("os-lc6159296")
    k, note = next((k, n) for k, n in enumerate(score.notes) if n.bar == 3 and not n.grace)
    up = {"C": "D", "D": "E", "E": "F", "F": "G", "G": "A", "A": "B", "B": "C"}[note.pitch.step]
    octave = note.pitch.octave + (1 if note.pitch.step == "B" else 0)
    score.notes[k] = replace(note, pitch=events.Pitch(up, note.pitch.alter, octave))
    flags = sc.check(score, ordered)
    assert [(f.part, f.staff, f.bar) for f in flags] == [(note.part, note.staff, 3)]
    assert flags[0].rule == "self-check"
