"""Tests for the raster engines' training labels (docs/notes/raster-labels-spec.md)."""

import xml.etree.ElementTree as ET
from collections import Counter
from types import SimpleNamespace

import numpy as np

from omr.corpus import raster_labels as rl
from omr.corpus import sequence_units as su
from omr.pdf.symbols import Symbol, TextRun


def sym(name, box, y=None, source="smufl", size=20.0):
    return Symbol(name, box[0], box[3] if y is None else y, size, box, "F", source)


def page(symbols, text=(), unnamed=(), staves=((0, 400, 100, 120),)):
    ev = SimpleNamespace(staves=SimpleNamespace(boxes=list(staves), staff_space_pt=5.0))
    return SimpleNamespace(symbols=list(symbols), text=list(text), unnamed=list(unnamed),
                           staff_space=5.0, evidence=ev, unmapped=Counter())


def test_every_class_is_unique_and_indexed():
    assert len(rl.CLASSES) == len(set(rl.CLASSES)) == 104
    assert all(rl.CLASS_INDEX[c] == i for i, c in enumerate(rl.CLASSES))


def test_names_share_a_class_when_they_look_alike():
    assert rl.class_of("flag8thUp") == rl.class_of("flag8thDown") == "flag8th"
    assert rl.class_of("flag128thUp") == "flag64th"
    assert rl.class_of("articAccentBelow") == "accent"
    assert rl.class_of("repeatDot") == "augmentationDot"
    assert rl.class_of("noteheadParenthesisLeft") == "parenLeft"
    assert rl.class_of("noteheadDiamondBlack") == "noteheadOther"
    assert rl.class_of("restWholeLegerLine") == "restWhole"
    assert rl.class_of("graceNoteSlashStemUp") is None


def test_dynamic_letters_join_into_one_dynamic():
    m = sym("dynamicMezzo", (10, 130, 15, 135), y=135)
    f = sym("dynamicForte", (14.5, 128, 18, 136), y=135)
    labels, missing, _ = rl.page_labels(page([m, f]))
    assert [(l.cls, l.box) for l in labels] == [("dynamicMF", (10, 128, 18, 136))]
    assert rl.dynamic_class("pppp") == "dynamicPPPP" and rl.dynamic_class("sfzp") == "dynamicOther"


def test_lilypond_octave_clef_is_one_box():
    clef = sym("gClef", (10, 95, 22, 130), size=20.0)
    eight = sym("timeSig8", (14, 130.5, 18, 134), size=12.0)
    labels, _, _ = rl.page_labels(page([clef, eight]))
    assert [l.cls for l in labels] == ["gClef8vb"]
    assert labels[0].box == (10, 95, 22, 134)


def test_italic_digits_are_tuplet_numbers_by_digit():
    run = TextRun("3", 50, 90, (50, 85, 54, 90), "Times-Italic", 8)
    words = TextRun("Allegro", 10, 80, (10, 74, 40, 80), "Times-Bold", 10)
    labels, _, _ = rl.page_labels(page([], text=[run, words]), text_chars=[("3", (50.5, 85.5, 53.5, 89.5))])
    assert sorted(l.cls for l in labels) == ["text", "tuplet3"]


def test_italic_digits_over_the_start_of_a_staff_are_a_bar_number():
    bar = TextRun("13", 1, 96, (1, 91, 9, 96), "Times-Italic", 8)        # staff from x 0, top 100
    tuplet = TextRun("3", 50, 96, (50, 91, 54, 96), "Times-Italic", 8)
    chars = [("1", (1, 91, 5, 96)), ("3", (5, 91, 9, 96)), ("3", (50, 91, 54, 96))]
    labels, _, _ = rl.page_labels(page([], text=[bar, tuplet]), text_chars=chars)
    assert sorted((l.cls, l.box[0]) for l in labels) == [("text", 1), ("tuplet3", 50)]


def test_outlined_text_row_takes_in_letters_matched_as_symbols():
    letters = [(100, 200, 103, 204), (104, 200, 107, 204)]
    wrong = sym("dynamicSforzando", (108, 200, 111, 204), source="outline")
    note = sym("noteheadBlack", (50, 108, 56, 112), source="outline")
    labels, _, _ = rl.page_labels(page([wrong, note], unnamed=letters))
    assert sorted(l.cls for l in labels) == ["noteheadBlack", "text"]
    text = next(l for l in labels if l.cls == "text")
    assert text.box == (100, 200, 111, 204)


def test_boxes_grow_to_half_a_staff_space_and_keep_their_ink_box():
    labels = rl.to_pixels([rl.Label("augmentationDot", (10, 10, 11, 11))], zoom=2.0, space_px=20.0, shape=(100, 100))
    box, ink = labels[0].box, labels[0].ink
    assert box[2] - box[0] == 10 + 2 and ink == (20.0, 20.0, 22.0, 22.0)


def test_duplicates_are_dropped():
    a = rl.Label("noteheadBlack", (0, 0, 10, 10))
    b = rl.Label("noteheadBlack", (0.2, 0, 10, 10))
    c = rl.Label("accidentalSharp", (0, 0, 10, 10))
    assert rl.drop_duplicates([a, b, c]) == [a, c]


def test_staff_lines_are_removed_but_not_the_symbols_on_them():
    ink = np.zeros((60, 200), dtype=bool)
    for y in (10, 20, 30, 40, 50):
        ink[y, :] = True
    ink[16:25, 50:60] = True      # a notehead across the line at 20
    out = rl.remove_staff_lines(ink, [(0, 199, 10, 50)])
    assert not out[30, 100] and out[20, 55]


def test_check_page_counts_fit_and_unlabelled_glyph_ink():
    ink = np.zeros((100, 100), dtype=bool)
    ink[10:20, 10:20] = True
    ink[50:56, 50:56] = True       # a glyph with no box
    lab = rl.Label("noteheadBlack", (9, 9, 21, 21), ink=(10, 10, 20, 20))
    loose = rl.Label("accidentalSharp", (60, 60, 90, 90), ink=(60, 60, 90, 90))
    counts, fit, pieces = rl.check_page([lab, loose], ink, space_px=10, glyphs=ink.copy())
    assert fit[("noteheadBlack", "fit")] == 1 and fit[("accidentalSharp", "empty")] == 1
    assert counts["unlabelled pieces"] == 1 and pieces == [(50, 50, 6, 6)]
    counts, _, _ = rl.check_page([lab], ink, space_px=10, glyphs=ink.copy(), ignored=[(49, 49, 57, 57)])
    assert counts["unlabelled pieces"] == 0


def test_tiles_keep_boxes_half_inside_and_few_empty_tiles():
    image = np.full((1200, 1200), 255, dtype=np.uint8)
    labels = [rl.Label("noteheadBlack", (470, 100, 490, 120))]
    found = list(rl.tiles(image, labels, seed=1))
    with_box = [t for t in found if t[3]]
    assert {(x, y) for x, y, _, _ in with_box} == {(0, 0), (480, 0)}
    assert all(t[2].shape == (640, 640) for t in found)
    line = rl.yolo_lines(with_box[0][3])
    assert line.startswith(f"{rl.CLASS_INDEX['noteheadBlack']} ")


def test_scores_are_split_the_same_way_every_time():
    assert rl.page_seed("a", 1) == rl.page_seed("a", 1) != rl.page_seed("a", 2)


def test_as_printed_moves_notes_under_octave_clefs_and_lines():
    xml = """<score-partwise><part id="P1"><measure number="1">
      <attributes><clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch></note>
      <direction><direction-type><octave-shift type="down" size="8"/></direction-type></direction>
      <note><pitch><step>D</step><octave>5</octave></pitch></note>
      <direction><direction-type><octave-shift type="stop" size="8"/></direction-type></direction>
      <note><pitch><step>E</step><octave>4</octave></pitch></note>
    </measure></part></score-partwise>"""
    root = su.as_printed(ET.fromstring(xml))
    assert [o.text for o in root.iter("octave")] == ["5", "5", "5"]
    assert root.find(".//clef-octave-change") is None and root.find(".//octave-shift") is None


def test_printed_notes_leave_out_rests_and_hidden_notes():
    measure = ET.fromstring("""<measure><note><pitch/></note><note><rest/></note>
        <note print-object="no"><pitch/></note><note><chord/><pitch/></note></measure>""")
    assert su.printed_notes(measure) == 2


def test_system_starts_from_print_elements():
    measures = [ET.fromstring(x) for x in ("<measure/>", "<measure/>", '<measure><print new-system="yes"/></measure>',
                                           '<measure><print new-page="yes"/></measure>')]
    assert su.system_starts(measures) == [0, 2, 3]


def test_a_slanted_wavy_line_is_one_box():
    pieces = [sym("wiggleTrill", (10 + 4 * k, 100 + 3 * k, 15 + 4 * k, 103 + 3 * k)) for k in range(4)]
    labels, _, _ = rl.page_labels(page(pieces, staves=()))
    assert [(l.cls, l.box, l.tighten) for l in labels] == [("trillLine", (10, 100, 27, 112), True)]


def test_a_brace_box_is_grown_upright_to_be_tightened():
    labels, _, _ = rl.page_labels(page([sym("brace", (5, 100, 9, 140))]))
    assert [(l.cls, l.box, l.tighten) for l in labels] == [("brace", (5, 87.5, 9, 152.5), True)]


def test_an_outlined_dot_over_a_notehead_is_a_staccato():
    head = sym("noteheadBlack", (20, 107.5, 26, 112.5), y=110, source="outline")
    over = sym("augmentationDot", (22, 102, 24, 104), source="outline")         # 1.4 spaces above
    after = sym("augmentationDot", (28, 106, 30, 108), source="outline")        # beside it: a rhythm dot
    labels, _, _ = rl.page_labels(page([head, over, after]))
    assert sorted((l.cls, l.box[0]) for l in labels if l.cls != "noteheadBlack") == [
        ("augmentationDot", 28), ("staccato", 22)]


def test_turned_glyph_boxes_turn_with_the_glyph():
    from omr.pdf import symbols

    ink = SimpleNamespace(left=0.0, top=-1.0, width=4.0, height=1.0)   # a level wiggle above its baseline
    assert symbols._placed_box(ink, (10, 50), 1.0, (1.0, 0.0)) == (10, 49, 14, 50)
    assert symbols._placed_box(ink, (10, 50), 1.0, (0.0, -1.0)) == (9, 46, 10, 50)   # drawn upward


def test_a_column_of_unnamed_upright_shapes_is_an_arpeggio():
    column = [(100, 100 + 4.5 * k, 2, 104.5 + 4.5 * k) for k in range(4)]
    column = [(b[0], b[1], b[0] + b[2], b[3]) for b in column]
    labels, _, ignored = rl.page_labels(page([], unnamed=column))
    assert [(l.cls, l.box) for l in labels] == [("arpeggio", (100, 100, 102, 118.0))] and ignored == []
    assert rl.unboxed(column + [(300, 300, 302, 305)], labels) == [(300, 300, 302, 305)]
