"""Tests for reading page images with the vector reader (omr.raster.names
and omr.raster.reading)."""

from pathlib import Path

import pytest

from omr.corpus import raster_labels as rl
from omr.raster import names

DATA = Path(__file__).parent / "data" / "inspect"
SPACE = 5.0   # points a staff space
HEAD = rl.CLASS_INDEX["noteheadBlack"]
SHARP = rl.CLASS_INDEX["accidentalSharp"]
NATURAL = rl.CLASS_INDEX["accidentalNatural"]


def test_settle_keeps_the_more_confident_class_and_doubts_a_close_one():
    box = (10, 10, 15, 24)
    close = names.settle([(SHARP, box, 0.62), (NATURAL, box, 0.55)])
    assert close == [("accidentalSharp", box, 0.62, "a sharp or a natural")]
    clear = names.settle([(SHARP, box, 0.9), (NATURAL, box, 0.4)])
    assert clear == [("accidentalSharp", box, 0.9, None)]
    unsure = names.settle([(HEAD, box, 0.31)])
    assert unsure[0][3] == "perhaps a black notehead (31 percent sure)"


def test_symbols_are_anchored_and_sized_as_smufl_glyphs():
    head = (100.0, 50.0, 100.0 + 1.17 * SPACE, 50.0 + SPACE)
    grace = (200.0, 50.0, 200.0 + 0.7 * SPACE, 50.0 + 0.6 * SPACE)
    symbols, _, _ = names.to_symbols([(HEAD, head, 0.9), (HEAD, grace, 0.9)], SPACE)
    full, small = sorted(symbols, key=lambda s: s.x)
    assert full.name == "noteheadBlack" and full.source == "detector"
    assert full.x == pytest.approx(100.0) and full.y == pytest.approx(52.5, abs=0.1)   # left edge, centre line
    assert full.size == pytest.approx(4 * SPACE)
    assert small.size == pytest.approx(4 * SPACE * 0.6, rel=0.01)
    assert full.doubt is None and full.confidence == 0.9


def test_a_g_clef_is_anchored_on_its_g_line():
    box = (10.0, 0.0, 10.0 + 2.67 * SPACE, 7.08 * SPACE)   # Bravura's, with its G line 4.42 spaces down
    (clef,), _, _ = names.to_symbols([(rl.CLASS_INDEX["gClef"], box, 0.95)], SPACE)
    assert clef.y == pytest.approx(4.42 * SPACE, abs=0.25 * SPACE)


def test_a_clef_is_snapped_to_the_nearest_staff_line():
    box = (10.0, 0.0, 10.0 + 2.67 * SPACE, 7.4 * SPACE)
    (clef,), _, _ = names.to_symbols([(rl.CLASS_INDEX["gClef"], box, 0.95)], SPACE)
    staff = [(clef.y + 0.27 * SPACE + k * SPACE, 0.0, 400.0, 0.5) for k in range(-3, 2)]
    ledger = [(clef.y - 0.1 * SPACE, 8.0, 16.0, 0.5)]   # too short to be a staff line
    names.snap_clefs([clef], staff + ledger, SPACE)
    assert clef.y == pytest.approx(staff[3][0])


def test_a_flat_is_anchored_by_its_height():
    """A tall flat (MuseJazz, a handwritten style) has its origin higher in
    its box than an ordinary one."""
    flat = rl.CLASS_INDEX["accidentalFlat"]
    found = [(flat, (10.0, 0.0, 14.0, 2.5 * SPACE), 0.9), (flat, (30.0, 0.0, 35.0, 3.4 * SPACE), 0.9)]
    usual, tall = sorted(names.to_symbols(found, SPACE)[0], key=lambda s: s.x)
    assert usual.y / (2.5 * SPACE) == pytest.approx(0.72, abs=0.02)
    assert tall.y / (3.4 * SPACE) == pytest.approx(0.65, abs=0.02)


def test_marks_take_their_side_from_the_nearest_notehead():
    head = (100.0, 50.0, 106.0, 55.0)
    above = (101.0, 40.0, 103.0, 42.0)
    below = (101.0, 62.0, 103.0, 64.0)
    stacc = rl.CLASS_INDEX["staccato"]
    symbols, _, _ = names.to_symbols([(HEAD, head, 0.9), (stacc, above, 0.9), (stacc, below, 0.8)], SPACE)
    assert sorted(s.name for s in symbols) == ["articStaccatoAbove", "articStaccatoBelow", "noteheadBlack"]


def test_text_and_unknown_marks_are_kept_apart():
    found = [(rl.CLASS_INDEX["text"], (0, 0, 50, 10), 0.9), (rl.CLASS_INDEX["dynamicOther"], (0, 20, 10, 30), 0.9),
             (rl.CLASS_INDEX["dynamicMF"], (0, 40, 15, 50), 0.9)]
    symbols, text, masked = names.to_symbols(found, SPACE)
    assert [s.name for s in symbols] == ["dynamicMF"]
    assert text == [(0, 0, 50, 10)] and masked == [(0, 20, 10, 30)]


def test_doubts_name_their_rule():
    found = [(HEAD, (0, 0, 6, 5), 0.3), (rl.CLASS_INDEX["accent"], (0, 20, 6, 25), 0.3)]
    symbols, _, _ = names.to_symbols(found, SPACE)
    rules = {s.name: s.doubt[0] for s in symbols}
    assert rules == {"noteheadBlack": "unsure symbol", "articAccentBelow": "unsure marking"}


def test_a_flag_turns_down_when_it_hangs_below_its_notes():
    flag = rl.CLASS_INDEX["flag8th"]
    up_box = (100.0, 10.0, 105.0, 26.0)
    down_box = (200.0, 40.0, 206.0, 56.0)
    heads = [(94.0, 25.5, 100.0, 30.5), (200.0, 21.5, 206.0, 26.5)]   # at the other end of each stem
    found = [(flag, up_box, 0.9), (flag, down_box, 0.9)] + [(HEAD, h, 0.9) for h in heads]
    symbols, _, _ = names.to_symbols(found, SPACE)
    symbols = [s for s in symbols if s.name.startswith("flag")] + [s for s in symbols if s.name.startswith("note")]
    stems = [(100.2, 10.0, 28.0, 0.6), (200.2, 24.0, 56.0, 0.6)]
    names.set_flag_directions(symbols, stems, SPACE)
    up, down = sorted((s for s in symbols if s.name.startswith("flag")), key=lambda s: s.x)
    assert up.name == "flag8thUp" and up.y == pytest.approx(10.0, abs=0.5)
    assert down.name == "flag8thDown" and down.y == pytest.approx(56.0, abs=0.5)


def test_bracket_ends_in_one_column_are_top_and_bottom():
    end = rl.CLASS_INDEX["bracketEnd"]
    symbols, _, _ = names.to_symbols([(end, (10, 100, 20, 106), 0.9), (end, (10, 10, 20, 16), 0.9)], SPACE)
    assert sorted((s.box[1], s.name) for s in symbols) == [(10, "bracketTop"), (100, "bracketBottom")]


def test_an_image_page_reads_as_its_vector_page(tmp_path, monkeypatch):
    """A page rendered to an image and read with the detector replaced by
    the page's true labels gives the vector reading's notes."""
    pymupdf = pytest.importorskip("pymupdf")
    pytest.importorskip("cv2")
    from omr.pdf import structure, symbols
    from omr.raster import detect, page as rp, reading

    source = DATA / "ms4_leland.pdf"
    vector_doc = pymupdf.open(str(source))
    zoom = 300 / 72
    pix = vector_doc[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
    doc = pymupdf.open()
    page = doc.new_page(width=vector_doc[0].rect.width, height=vector_doc[0].rect.height)
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    image_pdf = tmp_path / "page.pdf"
    doc.save(str(image_pdf))
    vector_page = symbols.read_document(vector_doc, [1])[0]
    grey, _ = rp.page_image(page)
    truth = detect.truth_labels(vector_page, vector_doc[0], grey, zoom)

    def fake(_grey, _factor):
        return [(rl.CLASS_INDEX[lab.cls], lab.box, 0.9) for lab in truth]

    monkeypatch.setattr(reading, "detector", lambda path=None: fake)
    vector_score, _ = structure.read_pdf(source, notes=True)
    image_score, layouts = structure.read_pdf(image_pdf, notes=True)
    vector_notes = [n for n in vector_score.notes if n.bar < len(image_score.bars)]
    assert image_score.bars and len(layouts[0].staves) >= 1
    pitches = lambda notes: sorted((n.part, n.bar, str(n.pitch)) for n in notes)
    same = len(set(pitches(vector_notes)) & set(pitches(image_score.notes)))
    assert same >= 0.95 * len(set(pitches(vector_notes)))


def test_saved_detections_are_read_back_for_the_same_image_scale_and_model(tmp_path):
    np = pytest.importorskip("numpy")
    from omr.raster import reading

    model, other = tmp_path / "a.onnx", tmp_path / "b.onnx"
    model.write_bytes(b"model a")
    other.write_bytes(b"model b")
    calls = []

    def run(grey, factor):
        calls.append(factor)
        return [(HEAD, (1.5, 2.25, 7.125, 8.0), 0.875)]

    folder = tmp_path / "saved"
    grey = np.full((40, 30), 255, dtype=np.uint8)
    first = reading.saving(run, folder, model)(grey, 0.5)
    again = reading.saving(run, folder, model)(grey, 0.5)
    assert again == first == [(HEAD, (1.5, 2.25, 7.125, 8.0), 0.875)] and len(calls) == 1
    changed = grey.copy()
    changed[3, 4] = 0
    reading.saving(run, folder, model)(changed, 0.5)
    reading.saving(run, folder, model)(grey, 0.6)
    reading.saving(run, folder, other)(grey, 0.5)
    assert len(calls) == 4 and len(list(folder.rglob("*.json"))) == 4
    assert not list(folder.rglob("*.part"))


def test_the_detector_saves_only_when_a_folder_is_set(tmp_path, monkeypatch):
    from omr.raster import reading

    model = tmp_path / "a.onnx"
    model.write_bytes(b"model a")
    monkeypatch.delenv(reading.DETECTIONS_ENV, raising=False)
    assert reading.detector(model).__name__ == "run"
    monkeypatch.setenv(reading.DETECTIONS_ENV, str(tmp_path / "saved"))
    assert reading.detector(model).__name__ == "cached"


def test_a_grace_note_is_small_against_the_pages_usual_notehead():
    """The detector's boxes are padded, so a grace notehead is measured
    against the page's usual notehead height, not the font's."""
    full = [(HEAD, (10.0 * k, 50.0, 10.0 * k + 6.5, 50.0 + 1.3 * SPACE), 0.9) for k in range(1, 7)]
    grace = (HEAD, (100.0, 50.0, 104.5, 50.0 + 0.94 * SPACE), 0.9)
    symbols, _, _ = names.to_symbols(full + [grace], SPACE)
    small = max(symbols, key=lambda s: s.x)
    assert small.size == pytest.approx(4 * SPACE * 0.94 / 1.3, rel=0.01)
    assert all(s.size == pytest.approx(4 * SPACE) for s in symbols if s is not small)


def test_a_notehead_beside_tempo_text_away_from_the_staff_is_a_metronome_note():
    staff = [(100.0 + k * SPACE, 0.0, 400.0, 0.5) for k in range(5)]
    tempo = (50.0, 70.0, 55.0, 75.0)
    in_staff = (150.0, 110.0, 156.0, 115.0)
    text = [(57.0, 68.0, 80.0, 77.0), (158.0, 109.0, 170.0, 116.0)]
    symbols, _, _ = names.to_symbols([(HEAD, tempo, 0.9), (HEAD, in_staff, 0.9)], SPACE)
    names.metronome_notes(symbols, text, staff, SPACE)
    assert sorted(s.name for s in symbols) == ["metNoteQuarterUp", "noteheadBlack"]


def test_a_detected_tuplet_is_taken_off_a_bar_that_adds_up_without_it():
    from fractions import Fraction

    from omr.pdf import notation

    def bar(n, base, tuplet):
        return [notation.Event(None, 10.0 * k, 10.0 * k + 5, base=base, tuplet=tuplet, tuplet_detected=True)
                for k in range(n)]

    fingering = bar(4, Fraction(1, 4), (3, 2))   # four quarters in 4/4, with a 3 that is not a tuplet
    cost = notation.assign_onsets(fingering, SPACE, Fraction(1))
    assert notation.detected_tuplets(fingering, SPACE, Fraction(1), cost) == 0
    assert all(e.tuplet is None for e in fingering)
    triplets = bar(6, Fraction(1, 8), (3, 2)) + bar(1, Fraction(1, 2), None)   # 2 triplets of eighths and a half
    for e in triplets[-1:]:
        e.x, e.right, e.tuplet_detected = 60.0, 65.0, False
    cost = notation.assign_onsets(triplets, SPACE, Fraction(1))
    notation.detected_tuplets(triplets, SPACE, Fraction(1), cost)
    assert all(e.tuplet == (3, 2) for e in triplets[:6])
