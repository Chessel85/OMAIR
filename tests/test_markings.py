"""Tests for Stage 1.4: text and markings from vector PDFs (omr.pdf.text,
omr.pdf.markings) and the markings check."""

import sys
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

pymupdf = pytest.importorskip("pymupdf")

from omr.evaluate import events  # noqa: E402
from omr.pdf import layout, markings, notation, symbols, text  # noqa: E402

ROOT = Path(__file__).parent.parent
REGRESSION = ROOT / "regression"
sys.path.insert(0, str(ROOT / "scripts"))
import check_markings  # noqa: E402
import check_notes  # noqa: E402

SPACE = 5.0


def staff(top, x0=50.0, x1=550.0):
    return layout.Staff(1, top, SPACE, x0, x1)


def system(*tops):
    return layout.System(1, 0, [staff(t) for t in tops], 50.0, 550.0)


def symbol(name, x0, y0, x1, y1, y=None):
    return symbols.Symbol(name, x0, y1 if y is None else y, 20.0, (x0, y0, x1, y1), "Leland", "smufl")


# ------------------------------------------------------------ chord symbols

def test_chord_symbols_in_the_harness_words():
    assert text.chord_value("G") == "G major"
    assert text.chord_value("Am") == "A m"
    assert text.chord_value("D7") == "D 7"
    assert text.chord_value("Bb") == "Bb major"
    assert text.chord_value("B♭maj7") == "Bb maj7"
    assert text.chord_value("F#m7b5") == "F# m7b5"
    assert text.chord_value("C/E") == "C major / E"
    assert text.chord_value("Dsus4") == "D sus4"


def test_words_are_not_chord_symbols():
    for word in ("Allegro", "dolce", "a tempo", "Fine", "cresc.", "VII", "CII", "Ten. I Mel."):
        assert text.chord_value(word) is None, word


# ------------------------------------------------------------ placement

def test_text_between_staves_goes_to_the_nearer_staff():
    sy = system(100.0, 160.0)          # staves 100-120 and 160-180
    upper, lower = sy.staves
    assert text.staff_for(sy, (60, 124, 80, 130))[0] is upper
    assert text.staff_for(sy, (60, 150, 80, 156))[0] is lower
    # a dynamic between the staves of one part (a piano) belongs to the upper staff
    assert text.staff_for(sy, (60, 150, 80, 156), prefer="upper")[0] is upper
    # between two parts it goes to the nearer staff: a singer's dynamic above the staff
    assert text.staff_for(sy, (60, 150, 80, 156), prefer="upper", same_part=lambda a, b: False)[0] is lower
    assert text.staff_for(sy, (60, 80, 80, 90)) == (upper, "above")


def test_dynamic_letters_set_together_are_one_dynamic():
    sy = system(100.0)
    page = SimpleNamespace(symbols=[
        symbol("dynamicMezzo", 100.0, 130.0, 108.7, 135.4, y=135.4),
        symbol("dynamicForte", 106.5, 126.1, 116.7, 138.4, y=135.4),   # kerned under the m
        symbol("dynamicPiano", 300.0, 130.0, 309.0, 138.1, y=135.4),
    ], systems=[sy], staves=sy.staves)
    found = sorted(value for value, _ in markings.dynamic_groups(page, sy))
    assert found == ["mf", "p"]


# ------------------------------------------------------------ hairpins

def test_a_hairpin_is_two_lines_that_meet_at_one_end():
    sy = system(100.0)
    cresc = [(100.0, 135.0, 160.0, 132.0), (100.0, 135.0, 160.0, 138.0)]       # meet on the left
    dim = [(300.0, 132.0, 360.0, 135.0), (300.0, 138.0, 360.0, 135.0)]         # meet on the right
    level = [(400.0, 132.0, 460.0, 132.0), (400.0, 137.0, 460.0, 137.0)]       # parallel: not a hairpin
    found = markings.hairpins(cresc + dim + level, sy)
    assert [(kind, starts, ends) for kind, *_, starts, ends in found] == [
        ("crescendo", True, True), ("diminuendo", True, True)]


def test_a_hairpin_carried_over_a_system_break():
    sy = system(100.0)
    # a crescendo that runs on to the next system ends open at the right margin
    running_on = [(450.0, 135.0, 549.0, 133.0), (450.0, 135.0, 549.0, 137.0)]
    # its continuation starts open at the left of the next system
    continued = [(60.0, 133.5, 120.0, 132.0), (60.0, 136.5, 120.0, 138.0)]
    (kind, *_, starts, ends), = markings.hairpins(running_on, sy)
    assert (kind, starts, ends) == ("crescendo", True, False)
    (kind, *_, starts, ends), = markings.hairpins(continued, sy)
    assert (kind, starts, ends) == ("crescendo", False, True)


# ------------------------------------------------------------ marks

def test_mark_names():
    assert markings.NOTE_MARKS[markings.mark_base("articStaccatoBelow")] == ("articulation staccato",)
    assert markings.NOTE_MARKS[markings.mark_base("fermataAbove")] == ("fermata",)
    assert markings.NOTE_MARKS[markings.mark_base("articMarcatoAbove")] == ("articulation strong-accent",)


def test_the_harness_reads_lyric_syllables():
    root = events.ET.fromstring(
        "<score-partwise><part-list><score-part id='P1'/></part-list><part id='P1'><measure number='1'>"
        "<attributes><divisions>1</divisions></attributes>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type>"
        "<lyric number='1'><syllabic>begin</syllabic><text>Hal</text></lyric></note>"
        "<note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type>"
        "<lyric number='1'><syllabic>end</syllabic><text>lo</text><extend/></lyric></note>"
        "</measure></part></score-partwise>")
    score = events.from_root(root)
    assert [n.syllables for n in score.notes] == [(("1", "begin", False),), (("1", "end", True),)]


# ------------------------------------------------- regression pairs, end to end

def check(score_id, job="musescore4-base"):
    pairs = check_notes.pairs(REGRESSION, job, None, score_id)
    assert len(pairs) == 1
    _, _, pdf, truth = pairs[0]
    return check_markings.check_pair(pdf, truth)


def recall(figures, kind):
    f = figures["markings"][kind]
    return f["found"] / f["truth"]


def test_chord_symbols_and_credits_of_a_lead_sheet():
    figures = check("pdmx-9mh9Dt5NAnR9")
    assert recall(figures, "chord symbol") >= 0.95
    assert figures["credits"]["title"]["found"] == 1 and figures["credits"]["composer"]["found"] == 1


def test_lyrics_and_hyphens_of_a_choir_score():
    figures = check("pdmx-kyKcYH1Z2cK9")
    lyrics = figures["note marks"]["lyrics"]
    assert lyrics["found"] >= 0.95 * lyrics["truth"]
    assert figures["syllables"]["right"] >= 0.95 * figures["syllables"]["truth"]


def test_dynamics_and_hairpins_of_a_choir_score():
    figures = check("pdmx-yEAWP5Dcw7sf")
    assert recall(figures, "dynamic") >= 0.95
    assert recall(figures, "hairpin") >= 0.95


def test_guitar_fingering_and_plucking():
    figures = check("pdmx-4viYqFUrsJaX")
    fingering = figures["note marks"]["technical fingering"]
    assert fingering["found"] >= 0.9 * fingering["truth"]
    assert figures["note marks"]["technical pluck"]["found"] > 0


def test_articulations_slurs_and_arpeggios_of_a_piano_piece():
    figures = check("pdmx-NhuNzKj3Y1Ds")
    marks = figures["note marks"]
    assert marks["arpeggiate"]["found"] == marks["arpeggiate"]["truth"]
    assert marks["slur ends"]["found"] >= 0.85 * marks["slur ends"]["truth"]
    assert marks["articulation staccato"]["found"] >= 0.9 * marks["articulation staccato"]["truth"]


def test_text_on_a_page_is_sorted_into_kinds():
    score, _ = notation_score("pdmx-9mh9Dt5NAnR9")
    kinds = {(i.kind, i.text) for i in score.text}
    assert ("title", "the Nameless Lassie") in kinds
    assert ("composer", "William Marshall") in kinds
    words = [m for m in score.markings if m.kind == "words"]
    assert any(m.value == "Slow Air" for m in words)
    assert not any(m.value in ("8", "9", "16", "17", "23") for m in words)   # bar numbers are not words


def notation_score(score_id, job="musescore4-base"):
    from omr.pdf import structure
    _, _, pdf, _ = check_notes.pairs(REGRESSION, job, None, score_id)[0]
    return structure.read_pdf(pdf, notes=True)


def test_span_breaks_split_lyric_syllables():
    run = symbols.TextRun("cielpur,", 224.0, 495.0, (224.0, 486.0, 250.0, 495.0), "FreeSerif", 8.6,
                          breaks=[(4, 236.0, 1.0)])
    pieces = text._pieces(run, 1)
    assert [p.text for p in pieces] == ["ciel", "pur,"]
    assert pieces[0].box[2] == pytest.approx(235.0) and pieces[1].box[0] == pytest.approx(236.0)


def test_staccato_dots_over_a_notehead():
    st = staff(100.0)
    head = notation.Head(symbol("noteheadBlack", 200.0, 117.5, 206.5, 122.5, y=120.0), st, 2, False)
    event = notation.Event(st, 200.0, 206.5, heads=[head])
    over = symbol("augmentationDot", 202.5, 125.5, 204.5, 127.5)     # under the head, centred
    beside = symbol("augmentationDot", 209.0, 119.0, 211.0, 121.0)   # level with it: an augmentation dot
    assert notation.staccato_dots([over, beside], [event], SPACE) == [over]
    assert Fraction(1) == event.value


def test_printed_chord_suffixes_name_their_kind():
    assert text.chord_kind("A m7") == ("A", "minor-seventh", None)
    assert text.chord_kind("G major") == ("G", "major", None)
    assert text.chord_kind("Bb Δ7") == ("Bb", "major-seventh", None)
    assert text.chord_kind("C major / E") == ("C", "major", "E")
    assert text.chord_kind("F# m7b5") == ("F#", "half-diminished", None)
