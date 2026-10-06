"""Tests for the PDF inspector against the expected results in
docs/notes/inspector-spec.md. The engraver PDFs in tests/data/inspect/ were made
by scripts/make_inspect_testdata.py from Bach's BWV 66.6 (public domain)."""

import json
from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from omr import inspect as inspector  # noqa: E402
from omr.cli import main  # noqa: E402

DATA = Path(__file__).parent / "data" / "inspect"


def page_result(path, page=1):
    result = inspector.inspect_file(path)
    return result["results"][page - 1]


def music_fonts(ev):
    return {f.name: f.cls for f in ev.music_fonts}


@pytest.mark.parametrize(
    "name,font",
    [
        ("ms4_leland", "Leland"),
        ("ms4_bravura", "Bravura"),
        ("ms4_petaluma", "Petaluma"),
        ("ms4_gonville", "Gootville"),
        ("ms4_musejazz", "MuseJazz"),
        ("ms4_finale_maestro", "FinaleMaestro"),
        ("ms4_finale_broadway", "FinaleBroadway"),
        ("ms3_default", "MScore"),
    ],
)
def test_musescore_exports_are_type_a_with_smufl_font(name, font):
    ev, decision = page_result(DATA / f"{name}.pdf")
    assert (decision.type, decision.confidence) == ("A", "high")
    assert music_fonts(ev).get(font) == "smufl"
    assert ev.staves.five_line == 12
    assert ev.staves.staff_space_pt == pytest.approx(5.0, abs=0.1)


def test_finale_broadway_also_uses_a_few_bravura_glyphs():
    ev, _ = page_result(DATA / "ms4_finale_broadway.pdf")
    assert music_fonts(ev)["Bravura"] == "smufl"


def test_lilypond_is_type_a_with_legacy_font_and_no_unicode():
    ev, decision = page_result(DATA / "lilypond.pdf")
    assert (decision.type, decision.confidence) == ("A", "high")
    font = next(f for f in ev.fonts if f.name.startswith("Emmentaler"))
    assert font.cls == "legacy"
    assert font.unmapped_glyphs == font.glyphs > 100


def test_verovio_is_type_b_with_repeated_shapes_and_times_text():
    ev, decision = page_result(DATA / "verovio.pdf")
    assert (decision.type, decision.confidence) == ("B", "high")
    assert ev.repeated_shapes > 100
    assert ev.outlined["top_repeats"][0] > 100
    assert not ev.music_fonts


def test_made_by_comes_from_metadata_only():
    result = inspector.inspect_file(DATA / "ms4_leland.pdf")
    assert "MuseScore" in result["creator"]


# -------------------------------------------------- built in the test


@pytest.fixture(scope="module")
def raster_png(tmp_path_factory):
    folder = tmp_path_factory.mktemp("raster")
    page = pymupdf.open(DATA / "ms4_leland.pdf")[0]
    png = folder / "page.png"
    page.get_pixmap(dpi=300).save(png)
    return png


def wrap_image(png, out, hidden_text=False):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, filename=str(png))
    if hidden_text:
        page.insert_text((100, 100), "Christus der ist mein Leben", render_mode=3)
    doc.save(out)
    return out


def test_clean_raster_is_type_c(raster_png, tmp_path):
    ev, decision = page_result(wrap_image(raster_png, tmp_path / "c.pdf"))
    assert decision.type == "C"
    assert decision.confidence != "high"
    assert ev.image_coverage > 0.9
    assert ev.images[0]["dpi"] >= 290


def test_rotated_raster_on_grey_background_is_type_d(raster_png, tmp_path):
    image = cv2.imread(str(raster_png))
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), 2.0, 1.0)
    rotated = cv2.warpAffine(image, matrix, (w, h), borderValue=(110, 110, 110))
    png = tmp_path / "rotated.png"
    cv2.imwrite(str(png), rotated)
    ev, decision = page_result(wrap_image(png, tmp_path / "d.pdf"))
    assert decision.type == "D"
    assert "tilt" in decision.reason or "background" in decision.reason


def test_tilt_alone_is_enough_for_type_d(raster_png, tmp_path):
    image = cv2.imread(str(raster_png))
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), 2.0, 1.0)
    rotated = cv2.warpAffine(image, matrix, (w, h), borderValue=(255, 255, 255))
    png = tmp_path / "tilted.png"
    cv2.imwrite(str(png), rotated)
    ev, decision = page_result(wrap_image(png, tmp_path / "tilt.pdf"))
    assert decision.type == "D"
    # The measured angle is the correction, so its sign is opposite to the rotation.
    assert abs(abs(ev.raster["tilt_degrees"]) - 2.0) <= 0.5


def test_png_file_is_inspected_directly(raster_png):
    ev, decision = page_result(raster_png)
    assert decision.type == "C"


def test_text_only_page_has_no_music(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    for i in range(10):
        page.insert_text((72, 100 + i * 20), "Some ordinary words on a page of text.")
    doc.save(tmp_path / "text.pdf")
    ev, decision = page_result(tmp_path / "text.pdf")
    assert decision.type == "N"


def test_hidden_text_layer_is_noted_and_does_not_count_as_a_font(raster_png, tmp_path):
    ev, decision = page_result(wrap_image(raster_png, tmp_path / "ocr.pdf", hidden_text=True))
    assert decision.type == "C"
    assert any("hidden text layer" in n for n in decision.notes)
    assert ev.hidden_text_glyphs > 0
    assert ev.fonts == []


def test_large_image_under_music_is_noted_as_background(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    pix = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 60, 80), 0)
    pix.clear_with(235)
    page.insert_image(page.rect, pixmap=pix)
    doc.insert_pdf(pymupdf.open(DATA / "ms4_leland.pdf"))
    # A vector page with its own large background image: merge by overlaying.
    base = doc[1]
    base.insert_image(base.rect, pixmap=pix, overlay=False)
    doc.save(tmp_path / "bg.pdf")
    ev, decision = page_result(tmp_path / "bg.pdf", page=2)
    assert decision.type == "A"
    assert any("background" in n for n in decision.notes)


# ------------------------------------------------------ files and command


def test_missing_and_damaged_files_fail_but_others_are_read(tmp_path, capsys):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    code = main(["inspect", str(bad), str(DATA / "ms4_leland.pdf"), str(tmp_path / "gone.pdf")])
    out = capsys.readouterr().out
    assert code == 1
    assert "Failed:" in out
    assert "Type A" in out
    assert out.strip().splitlines()[-1] == "Summary: 1 file inspected, 2 failed, 0 warnings."


def test_json_has_the_fixed_fields(tmp_path, capsys):
    path = tmp_path / "out.json"
    assert main(["inspect", str(DATA / "verovio.pdf"), "--json", str(path)]) == 0
    capsys.readouterr()
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = data[0]
    for key in ("file", "pages", "producer", "creator", "error", "summary", "page_results"):
        assert key in entry
    page = entry["page_results"][0]
    for key in ("page", "width_pt", "height_pt", "rotation", "type", "confidence", "reason",
                "notes", "fonts", "hidden_text_glyphs", "lines", "filled", "staves",
                "outlined_shapes", "images", "image_coverage"):
        assert key in page
    assert page["type"] == "B"
    assert entry["summary"]["types"] == {"B": 1}


def test_brief_gives_only_summaries(capsys):
    assert main(["inspect", "--brief", str(DATA / "lilypond.pdf")]) == 0
    out = capsys.readouterr().out
    assert "Page 1" not in out
    assert "Summary: 1 page. Type A on 1 page." in out


def test_pages_option_and_page_grouping(tmp_path, capsys):
    doc = pymupdf.open()
    for _ in range(3):
        doc.insert_pdf(pymupdf.open(DATA / "ms4_leland.pdf"))
    doc.save(tmp_path / "three.pdf")
    assert main(["inspect", str(tmp_path / "three.pdf")]) == 0
    out = capsys.readouterr().out
    assert "Pages 2 to 3: same type and fonts as page 1." in out
    assert main(["inspect", "--pages", "2", str(tmp_path / "three.pdf")]) == 0
    out = capsys.readouterr().out
    assert "Page 2" in out and "Page 1" not in out


def test_wrong_usage_exits_with_2(capsys):
    assert main(["inspect"]) == 2


def test_report_has_no_tables_or_art(capsys):
    main(["inspect", str(DATA / "ms4_leland.pdf")])
    out = capsys.readouterr().out
    assert "|" not in out and "+--" not in out


# ------------------------------------------------- sparse pages and export checks


def _evidence(glyphs=0, repeated=0, staves=0, coverage=0.0):
    from omr.pdf import evidence as E

    fonts = [E.FontUse("Leland", glyphs=glyphs, cls="smufl")] if glyphs else []
    return E.PageEvidence(
        page=1, width_pt=595, height_pt=842, rotation=0, fonts=fonts, hidden_text_glyphs=0,
        lines={"horizontal": 0, "vertical": 0, "other": 0},
        filled={"rectangles": 0, "polygons": 0, "curved": 0},
        staves=E.Staves(five_line=staves, staff_space_pt=5.0 if staves else None),
        outlined={"count": repeated, "distinct": 1, "top_repeats": [repeated], "repeated_instances": repeated},
        images=[], image_coverage=coverage,
    )


def test_sparse_last_page_with_staves_is_type_a_with_medium_confidence():
    from omr.pdf import classify

    decision = classify.classify(_evidence(glyphs=7, staves=3), lambda: None)
    assert (decision.type, decision.confidence) == ("A", "medium")
    decision = classify.classify(_evidence(repeated=6, staves=2), lambda: None)
    assert (decision.type, decision.confidence) == ("B", "medium")


def test_staves_with_almost_no_symbols_stay_low_confidence_b():
    from omr.pdf import classify

    decision = classify.classify(_evidence(glyphs=2, staves=3), lambda: None)
    assert (decision.type, decision.confidence) == ("B", "low")
    assert classify.classify(_evidence(glyphs=5), lambda: None).type == "N"


def test_export_check_allows_text_only_pages_but_needs_music(tmp_path):
    from omr.corpus import engravers, generate

    spec = {"engraver": "MuseScore 4", "font": "Leland"}
    doc = pymupdf.open()
    page = doc.new_page()
    for i in range(10):
        page.insert_text((72, 100 + i * 20), "A title page with only words on it.")
    doc.insert_pdf(pymupdf.open(DATA / "ms4_leland.pdf"))
    doc.save(tmp_path / "with_title.pdf")
    generate.check_pdf(tmp_path / "with_title.pdf", spec)  # does not raise
    only_text = pymupdf.open()
    only_text.new_page().insert_text((72, 100), "Words only.")
    only_text.save(tmp_path / "text.pdf")
    with pytest.raises(engravers.ExportError):
        generate.check_pdf(tmp_path / "text.pdf", spec)
    with pytest.raises(engravers.ExportError):
        generate.check_pdf(DATA / "lilypond.pdf", spec)  # wrong engraver and font
