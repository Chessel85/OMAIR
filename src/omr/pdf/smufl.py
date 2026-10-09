"""SMuFL glyph names and reference shapes.

Names and outlines come from the SMuFL fonts that Verovio installs with its
Python package (Bravura, Leland, Petaluma, Gootville, Leipzig): each font has
an XML file of bounding boxes with glyph names, and one SVG path per glyph.
Verovio's files cover the glyphs it draws, about 900; the few others found in
the corpus are listed in SUPPLEMENT. Code points from U+F400 up are each
font's own optional glyphs, so their names are looked up per font.
"""

import functools
import re
from dataclasses import dataclass
from pathlib import Path

STANDARD_END = 0xF3FF   # the last code point of SMuFL's recommended ranges

# Glyphs Verovio does not draw, by SMuFL name, with their code points
# (SMuFL 1.4 glyph names). The corpus and the legacy font tables use them.
SUPPLEMENT = {
    "reversedBrace": 0xE001, "systemDivider": 0xE007, "staff5Lines": 0xE014,
    "legerLine": 0xE022, "barlineSingle": 0xE030, "barlineDouble": 0xE031,
    "noteShapeDiamondBlack": 0xE1B9, "tremolo1": 0xE220, "tremolo2": 0xE221,
    "tremolo3": 0xE222, "accidentalParensLeft": 0xE26A, "accidentalParensRight": 0xE26B,
    "breathMarkComma": 0xE4CE, "breathMarkUpbow": 0xE4D0, "caesura": 0xE4D1,
    "caesuraCurved": 0xE4D4, "restDoubleWholeLegerLine": 0xE4F3,
    "restWholeLegerLine": 0xE4F4, "restHalfLegerLine": 0xE4F5,
    "lyricsElision": 0xE551, "graceNoteAcciaccaturaStemUp": 0xE560,
    "graceNoteSlashStemUp": 0xE564, "graceNoteSlashStemDown": 0xE565,
    "brassMuteClosed": 0xE5E5, "brassMuteHalfClosed": 0xE5E6, "brassMuteOpen": 0xE5E7,
    "stringsDownBow": 0xE610, "stringsUpBow": 0xE612, "stringsHarmonic": 0xE614,
    "stringsThumbPosition": 0xE624, "pluckedSnapPizzicatoAbove": 0xE631,
    "keyboardPedalE": 0xE652, "keyboardPedalD": 0xE653, "keyboardPedalDot": 0xE654,
    "keyboardPedalParensLeft": 0xE676, "keyboardPedalParensRight": 0xE677,
    "wiggleTrillFastest": 0xEAA0, "wiggleTrill": 0xEAA4, "wiggleArpeggiatoUp": 0xEAA9,
    "arrowheadBlackUp": 0xEB78, "fingering0": 0xED10, "fingering1": 0xED11,
    "fingering2": 0xED12, "fingering3": 0xED13, "fingering4": 0xED14,
    "csymAccidentalFlat": 0xED60, "csymAccidentalNatural": 0xED61, "csymAccidentalSharp": 0xED62,
    "fingering5": 0xED15,
    # chord symbol glyphs (MuseScore 4 sets them in Leland Text), Stage 1.4
    "csymDiminished": 0xE870, "csymHalfDiminished": 0xE871, "csymAugmented": 0xE872,
    "csymMajorSeventh": 0xE873, "csymMinor": 0xE874,
    # found in the corpus survey of 9 October 2026
    "reversedBracketTop": 0xE005, "reversedBracketBottom": 0xE006, "noteheadXWhole": 0xE0A7,
    "noteheadXHalf": 0xE0A8, "noteheadXOrnate": 0xE0AA, "noteheadTriangleDownBlack": 0xE0C7,
    "noteheadDiamondWhole": 0xE0D8, "noteheadDiamondWholeOld": 0xE0E0, "noteheadDiamondHalfOld": 0xE0E1,
    "noteheadRoundWhiteWithDot": 0xE115, "noteABlack": 0xE197, "noteASharpHalf": 0xE181,
    "noteCHalf": 0xE186, "noteCSharpHalf": 0xE187, "noteDFlatHalf": 0xE188, "noteDSharpHalf": 0xE18A,
    "noteFHalf": 0xE18F, "noteHSharpHalf": 0xE195, "noteShapeRoundWhite": 0xE1B0,
    "noteShapeRoundBlack": 0xE1B1, "noteShapeSquareWhite": 0xE1B2, "noteShapeSquareBlack": 0xE1B3,
    "noteShapeTriangleRightBlack": 0xE1B5, "noteShapeTriangleLeftWhite": 0xE1B6,
    "noteShapeTriangleLeftBlack": 0xE1B7, "noteShapeDiamondWhite": 0xE1B8,
    "noteShapeTriangleUpWhite": 0xE1BA, "noteShapeTriangleUpBlack": 0xE1BB,
    "accidentalSharpReversed": 0xE481, "dynamicDiminuendoHairpin": 0xE53F, "keyboardPlayWithRH": 0xE66E,
    "keyboardPlayWithRHEnd": 0xE66F, "guitarFadeIn": 0xE843,
    "guitarFadeOut": 0xE844, "guitarVolumeSwell": 0xE845, "conductorBeat4Simple": 0xE896,
    # used by the legacy font tables
    "noteheadSquareBlack": 0xE0B9, "noteheadTriangleUpBlack": 0xE0BE, "noteHalfUp": 0xE1D3,
    "noteHalfDown": 0xE1D4, "noteQuarterUp": 0xE1D5, "noteQuarterDown": 0xE1D6, "note8thUp": 0xE1D7,
    "note8thDown": 0xE1D8, "note16thUp": 0xE1D9, "note16thDown": 0xE1DA,
}

# Optional glyphs that only restyle a standard glyph are named as it
# (MuseScore 4 draws noteheads in Bravura with noteheadBlackOversized).
# "Small" is kept: it marks a cue-sized glyph.
STYLE_SUFFIXES = ("Oversized", "Larger", "Large", "Narrow", "Straight", "Short", "Light")

VEROVIO_FONTS = ("Bravura", "Leland", "Petaluma", "Gootville", "Leipzig")
UNITS_PER_SPACE = 250   # a staff space is a quarter of the 1000-unit em


@dataclass(frozen=True)
class Glyph:
    """One glyph of a reference font, in font units (y up), origin at 0, 0."""

    name: str
    code: int
    x: float
    y: float
    width: float
    height: float


def _data_folder():
    import verovio
    return Path(verovio.__file__).parent / "data"


@functools.cache
def font_glyphs(font):
    """{code point: Glyph} for one of Verovio's fonts."""
    path = _data_folder() / f"{font}.xml"
    glyphs = {}
    if not path.exists():
        return glyphs
    pattern = re.compile(r'<g c="([0-9A-F]+)" x="([-\d.]+)" y="([-\d.]+)" w="([-\d.]+)" h="([-\d.]+)"[^>]*n="([^"]+)"')
    for c, x, y, w, h, n in pattern.findall(path.read_text(encoding="utf-8")):
        code = int(c, 16)
        glyphs[code] = Glyph(n, code, float(x), float(y), float(w), float(h))
    return glyphs


@functools.cache
def standard_names():
    """{code point: name} for SMuFL's recommended ranges."""
    names = {}
    for font in VEROVIO_FONTS:
        for code, glyph in font_glyphs(font).items():
            if code <= STANDARD_END:
                names.setdefault(code, glyph.name)
    for name, code in SUPPLEMENT.items():
        names.setdefault(code, name)
    return names


@functools.cache
def codes_by_name():
    return {name: code for code, name in standard_names().items()}


def family_of(font_name):
    """The Verovio font a PDF font name belongs to, or None."""
    squashed = re.sub(r"[^a-z]", "", font_name.lower())
    for font in VEROVIO_FONTS:
        if squashed.startswith(font.lower()) or f"fonts{font.lower()}" in squashed:
            return font
    return None


def name_of(code, font_name=""):
    """The SMuFL name of a code point in a SMuFL font, or None. A code from
    U+F400 up is the font's own optional glyph, named only for a known font."""
    if code <= STANDARD_END:
        return standard_names().get(code)
    family = family_of(font_name)
    glyph = font_glyphs(family).get(code) if family else None
    if glyph is None:
        return None
    for suffix in STYLE_SUFFIXES:
        if glyph.name.endswith(suffix) and glyph.name[:-len(suffix)] in codes_by_name():
            return glyph.name[:-len(suffix)]
    return glyph.name


def code_of(name):
    return codes_by_name().get(name)


@functools.cache
def reference_glyph(name):
    """The Bravura glyph for a SMuFL name, or None if Bravura has no outline for it."""
    code = code_of(name)
    if code is None:
        return None
    return font_glyphs("Bravura").get(code)


@functools.cache
def outline_path(name, font="Bravura"):
    """The SVG path data of a glyph (font units, y up), or None."""
    code = code_of(name)
    if code is None:
        return None
    path = _data_folder() / font / f"{code:04X}.xml"
    if not path.exists():
        return None
    match = re.search(r' d="([^"]+)"', path.read_text(encoding="utf-8"))
    return match.group(1) if match else None
