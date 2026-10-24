"""Text in page images (Phase 2, Stage 2.5): docs/notes/raster-text-spec.md."""

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from omr.pdf.text import is_bold, is_italic
from omr.raster import page as rp
from omr.raster import text as rt


def written(word, italic=False, thickness=2, scale=1.5):
    """A white image with `word` in black, and its ink."""
    grey = np.full((80, 40 + 30 * len(word)), 255, dtype=np.uint8)
    cv2.putText(grey, word, (10, 55), cv2.FONT_HERSHEY_COMPLEX, scale, 0, thickness, cv2.LINE_AA)
    if italic:   # leaning right by 0.2 across per unit up, about as real italics do
        shear = np.float32([[1, -0.2, 0.2 * 55], [0, 1, 0]])
        grey = cv2.warpAffine(grey, shear, (grey.shape[1], grey.shape[0]), borderValue=255)
    return grey


def test_letters_set_how_far_text_reaches_above_and_below_the_baseline():
    assert rt.share("ao") == (rt.X_HEIGHT, 0.0)
    assert rt.share("Ty") == (rt.ASCENDER, rt.DESCENDER)
    assert rt.share("été")[0] == rt.ASCENDER
    assert rt.share("12")[0] == rt.ASCENDER
    assert rt.share("tant")[0] == rt.T_HEIGHT


def test_text_on_one_line_shares_its_median_size():
    # a lyric row on one baseline, a word on its own line, a title on the first
    sizes = [9.1, 9.9, 9.3, 9.6, 8.4, 20.0, 12.0]
    baselines = [100, 101, 100, 99, 60, 10, 100]
    assert rt.common_sizes(sizes, baselines, 20) == [9.45, 9.45, 9.45, 9.45, 8.4, 20.0, 12.0]
    assert rt.common_sizes([], [], 20) == []


def test_italic_letters_lean_and_upright_ones_do_not():
    upright = written("moderato") < rt.INK
    leaning = written("moderato", italic=True) < rt.INK
    assert rt.slant(upright)[0] < rt.ITALIC_SLANT
    lean, gain = rt.slant(leaning)
    assert lean >= rt.ITALIC_SLANT and gain >= rt.ITALIC_GAIN


def test_the_style_gives_a_font_name_the_text_rules_read():
    font, _, _ = rt.style(written("dolce", italic=True, thickness=1) < rt.INK, "dolce", 1.0)
    assert is_italic(font) and not is_bold(font)
    font, _, _ = rt.style(written("Allegro", thickness=5) < rt.INK, "Allegro", 1.0)
    assert is_bold(font) and not is_italic(font)
    font, _, _ = rt.style(written("Allegro", thickness=1) < rt.INK, "Allegro", 1.0)
    assert font == "image"


def test_digits_and_short_text_are_plain():
    """A lone digit's strokes lean like italics; tuplet numbers come from
    the detector, so fingering must not become one. A lone round capital
    has thick sides; as bold it would be a tempo mark, not a chord."""
    leaning = written("7", italic=True, thickness=1) < rt.INK
    assert rt.style(leaning, "7", 1.0)[0] == "image"
    assert rt.style(written("ff", italic=True, thickness=1) < rt.INK, "ff", 1.0)[0] == "image"
    assert rt.style(written("G", thickness=5) < rt.INK, "G", 1.0)[0] == "image"


def test_a_hyphen_read_after_a_syllable_is_left_to_the_hyphen_lines():
    assert rt.clean(" La- ") == "La"
    assert rt.clean("-") == "-"
    assert rt.clean("1-") == "1-"


def test_text_regions_become_text_runs_with_the_box_of_a_pdf_run():
    import pymupdf

    grey = written("ao")
    rows = np.nonzero((grey < rt.INK).any(axis=1))[0]
    cols = np.nonzero((grey < rt.INK).any(axis=0))[0]
    place = rp.Placement(grey.shape, pymupdf.Rect(0, 0, grey.shape[1] / 2, grey.shape[0] / 2))   # 2 pixels a point
    region = (cols[0] / 2, rows[0] / 2, (cols[-1] + 1) / 2, (rows[-1] + 1) / 2)
    runs = rt.read_regions(grey, place, [region], 10.0, read=lambda crops: [("ao", 0.9)] * len(crops))
    assert len(runs) == 1
    run = runs[0]
    assert run.text == "ao" and run.x == region[0]
    assert run.y == pytest.approx(region[3], abs=0.6)                 # no descender: the baseline is the ink's bottom
    assert run.size == pytest.approx((region[3] - region[1]) / rt.X_HEIGHT, rel=0.01)
    assert run.box[3] - run.box[1] == pytest.approx(run.size)
    assert rt.read_regions(grey, place, [region], 10.0, read=lambda crops: [("ao", 0.3)] * len(crops)) == []
    assert rt.read_regions(grey, place, [region], 10.0, read=lambda crops: [("", 0.9)] * len(crops)) == []


def test_readings_are_saved_and_read_back_for_the_same_crops_and_model(tmp_path):
    model = tmp_path / "ocr.onnx"
    model.write_bytes(b"model")
    calls = []

    def run(crops):
        calls.append(len(crops))
        return [("Ré", 0.875)] * len(crops)

    crop = written("Re")
    changed = crop.copy()
    changed[0, 0] = 0
    first = rt.saving(run, tmp_path / "ocr", model)([crop, crop])
    again = rt.saving(run, tmp_path / "ocr", model)([crop, crop])
    assert first == again == [("Ré", 0.875)] * 2 and calls == [2]
    rt.saving(run, tmp_path / "ocr", model)([crop, changed])
    assert calls == [2, 2] and len(list(tmp_path.rglob("*.json"))) == 2
    assert rt.saving(run, tmp_path / "ocr", model)([]) == [] and not list(tmp_path.rglob("*.part"))
