"""Tests for Stage 1.1: naming music symbols (omr.pdf.symbols, smufl,
fonttables, shapes). The test PDFs are the Bach chorale in tests/data/inspect."""

import io
from collections import Counter
from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from omr.pdf import fonttables, shapes, smufl, symbols  # noqa: E402

DATA = Path(__file__).parent / "data" / "inspect"


def read(name):
    doc = pymupdf.open(DATA / name)
    return symbols.read_document(doc)


def counts(pages):
    return Counter(s.name for p in pages for s in p.symbols)


# ------------------------------------------------------------ names and tables

def test_smufl_names_from_verovio_and_the_supplement():
    assert smufl.name_of(0xE0A4) == "noteheadBlack"
    assert smufl.name_of(0xE050) == "gClef"
    assert smufl.name_of(0xE0A8) == "noteheadXHalf"        # from the supplement
    assert smufl.code_of("accidentalSharp") == 0xE262


def test_optional_glyphs_are_named_only_for_their_own_font():
    # U+F400 and up are each font's own glyphs
    assert smufl.name_of(0xF400, "Bravura") == "braceSmall"
    assert smufl.name_of(0xF400, "SomeOtherFont") is None


def test_a_restyled_optional_glyph_is_named_as_its_standard_glyph():
    assert smufl.name_of(0xF4BE, "Bravura") == "noteheadBlack"    # noteheadBlackOversized


@pytest.mark.parametrize("code, byte", [(0xF0CF, 0xCF), (0x0153, 0xCF), (0x2211, 0xB7), (ord("#"), 0x23), (0x4E00, None)])
def test_sonata_bytes_from_symbol_font_and_mac_roman_codes(code, byte):
    assert fonttables.sonata_byte(code) == byte


def test_sonata_table_names_the_common_symbols():
    assert fonttables.SONATA[0xCF] == "noteheadBlack"
    assert fonttables.SONATA[0x26] == "gClef"
    assert fonttables.SONATA[0xB7] == "restWhole"
    assert fonttables.SONATA_SPECIAL[0x7B] == "brace"


def test_every_table_name_is_a_smufl_name():
    names = set(fonttables.SONATA.values()) | set(fonttables.SONATA_SPECIAL.values())
    names |= {fonttables.emmentaler_symbol(n, 0xFFFD) for n in ("noteheads.s2", "clefs.G", "rests.0", "flags.u3")}
    unknown = {n for n in names if smufl.code_of(n) is None} - fonttables.NOT_SMUFL - {"brace"}
    assert not unknown


@pytest.mark.parametrize("name, table", [
    ("Opus", "sonata"), ("HelsinkiStd", "sonata"), ("Maestro", "sonata"), ("OpusSpecialStd", "sonata-special"),
    ("OpusText", None), ("Emmentaler-20", "emmentaler"), ("PFAEmmentaler-16", "emmentaler"), ("Times-Roman", None),
])
def test_legacy_table_by_font_name(name, table):
    found = fonttables.legacy_table(name)
    assert (found[0] if found else None) == table


@pytest.mark.parametrize("glyph, name", [
    ("noteheads.s2", "noteheadBlack"), ("accidentals.2", "accidentalSharp"), ("accidentals.M2", "accidentalFlat"),
    ("clefs.F_change", "fClef"), ("brace184", "brace"), ("three", "timeSig3"), ("noteheads.s2mi", "noteheadBlack"),
])
def test_emmentaler_names_including_old_and_size_variants(glyph, name):
    assert fonttables.emmentaler_symbol(glyph, 0xFFFD) == name


def test_emmentaler_digits_and_dynamics_by_code():
    assert fonttables.emmentaler_symbol(None, ord("4")) == "timeSig4"
    assert fonttables.emmentaler_symbol(None, ord("p")) == "dynamicPiano"


# ------------------------------------------------------------ the test PDFs

@pytest.mark.parametrize("name", ["ms4_leland.pdf", "ms3_default.pdf", "lilypond.pdf", "ms4_bravura.pdf"])
def test_font_pdfs_name_every_glyph_alike(name):
    pages = read(name)
    found = counts(pages)
    assert found["noteheadBlack"] == 157
    assert found["accidentalSharp"] == 46
    assert found["gClef"] == 6 and found["fClef"] == 6
    assert sum(sum(p.unmapped.values()) for p in pages) == 0


def test_lilypond_glyphs_are_named_by_the_emmentaler_table():
    pages = read("lilypond.pdf")
    assert pages[0].fonts["Emmentaler-20"].table == "emmentaler"


def test_outlined_verovio_page_is_named_by_shape():
    pages = read("verovio.pdf")
    found = counts(pages)
    assert found["noteheadBlack"] == 157
    assert found["noteheadHalf"] == 8
    assert found["fermataAbove"] == 6
    assert all(s.source == "outline" for p in pages for s in p.symbols)


def test_a_page_turned_into_outlines_gives_the_same_noteheads():
    doc = pymupdf.open(DATA / "ms4_leland.pdf")
    svg = doc[0].get_svg_image(text_as_path=True)
    outlined = pymupdf.open("pdf", pymupdf.open(stream=svg.encode(), filetype="svg").convert_to_pdf())
    found = Counter(s.name for s in symbols.read_page(outlined[0], 1).symbols)
    assert found["noteheadBlack"] == 157
    assert found["accidentalSharp"] == 46


def test_text_of_a_page_is_kept_as_runs():
    pages = read("ms4_leland.pdf")
    assert any(run.text.strip() for run in pages[0].text)


# ------------------------------------------------------------ renamed fonts

def _stand_in_font(mapping):
    """DejaVu Sans with some characters drawn as other glyphs: the musical
    sharp, flat, natural and quarter note on "#", "b", "n" and "q", as an
    8-bit legacy music font draws them. Returns (font file, {char: glyph id})."""
    ttlib = pytest.importorskip("fontTools.ttLib")
    matplotlib = pytest.importorskip("matplotlib")
    font = ttlib.TTFont(str(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"))
    order = font.getGlyphOrder()
    gids = {}
    for table in font["cmap"].tables:
        if table.isUnicode():
            for char, glyph in mapping.items():
                if ord(char) in table.cmap:
                    table.cmap[ord(char)] = glyph
    cmap = font.getBestCmap()
    for char in mapping:
        gids[char] = order.index(cmap[ord(char)])
    out = io.BytesIO()
    font.save(out)
    return out.getvalue(), gids


def test_a_renamed_font_is_identified_as_sonata_by_its_shapes():
    music = {"#": "uni266F", "b": "uni266D", "n": "uni266E", "q": "uni2669"}
    buffer, gids = _stand_in_font(music)
    uses = {(ord(c), gids[c]): 5 for c in music}
    table, score = symbols.identify_by_shapes(buffer, uses)
    assert table == "sonata"
    assert score >= symbols.IDENTIFIED


def test_a_letter_font_is_not_identified():
    buffer, gids = _stand_in_font({"#": "numbersign", "b": "b", "n": "n", "q": "q"})
    uses = {(ord(c), gids[c]): 5 for c in "#bnq"}
    table, _ = symbols.identify_by_shapes(buffer, uses)
    assert table is None


# ------------------------------------------------------------ shapes

def test_reference_shapes_have_their_smufl_size():
    head = shapes.reference("noteheadBlack")
    assert head.height == pytest.approx(1.0, abs=0.1)
    clef = shapes.reference("gClef")
    assert clef.height > 6


def test_a_reference_matches_itself_and_not_another_symbol():
    sharp = shapes.reference("accidentalSharp")
    assert shapes.similarity(sharp, sharp) == pytest.approx(1.0)
    assert shapes.similarity(sharp, shapes.reference("noteheadBlack")) < 0.6
    assert shapes.similarity(shapes.reference("gClef"), shapes.reference("fClef")) < 0.6


def test_whole_and_half_rests_are_told_apart_by_the_staff_line():
    from omr.pdf.evidence import Staves

    staves = Staves(five_line=1, staff_space_pt=5.0, boxes=[(0, 500, 100, 120)])
    # a whole rest hangs from the fourth line (y 105), a half rest sits on the middle line (y 110)
    assert symbols._whole_or_half(staves, 105.0, 107.5, 5.0) == "restWhole"
    assert symbols._whole_or_half(staves, 107.5, 110.0, 5.0) == "restHalf"
