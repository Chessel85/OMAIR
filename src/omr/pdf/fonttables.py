"""Mapping tables for music fonts that are not SMuFL. Each maps a glyph to a
SMuFL name. See docs/notes/symbol-spec.md, "Font tables".

- Emmentaler (LilyPond) has no character codes: every glyph is U+FFFD. Its
  glyphs are named in the embedded font ("noteheads.s2"), so the table is by
  glyph name. One table covers every optical size (Emmentaler-11 to -26,
  PFAEmmentaler-NN, feta-alphabetNN) and Emmentaler-Brace.
- Opus and Helsinki (Sibelius) and Maestro (Finale) are 8-bit fonts on the
  Sonata layout: the same character means the same symbol in all three (a
  filled notehead is the Mac Roman byte 0xCF, "Œ"). Each has a companion
  "Special" font (OpusSpecial, HelsinkiSpecial) for brackets, braces,
  tremolo strokes and the like. The tables are by byte.

The Sonata table was built from the installed Maestro font and from the Opus,
Helsinki and Maestro glyphs embedded in the commercial engraver sample, each
drawn and looked at in context. Bytes not in the table are unmapped and are
counted, not guessed.
"""

import re

# ------------------------------------------------------------ Emmentaler

_EMMENTALER = {
    # noteheads
    "noteheads.s0": "noteheadWhole", "noteheads.s1": "noteheadHalf", "noteheads.s2": "noteheadBlack",
    "noteheads.sM1": "noteheadDoubleWhole", "noteheads.sM1double": "noteheadDoubleWholeSquare",
    "noteheads.uM2": "noteheadDoubleWholeSquare", "noteheads.dM2": "noteheadDoubleWholeSquare",
    "noteheads.s0diamond": "noteheadDiamondWhole", "noteheads.s1diamond": "noteheadDiamondHalf",
    "noteheads.s2diamond": "noteheadDiamondBlack", "noteheads.s0triangle": "noteheadTriangleUpWhole",
    "noteheads.s1triangle": "noteheadTriangleUpHalf", "noteheads.s2triangle": "noteheadTriangleUpBlack",
    "noteheads.s0cross": "noteheadXWhole", "noteheads.s1cross": "noteheadXHalf",
    "noteheads.s2cross": "noteheadXBlack", "noteheads.s2xcircle": "noteheadCircleX",
    "noteheads.s0slash": "noteheadSlashWhiteWhole", "noteheads.s1slash": "noteheadSlashWhiteHalf",
    "noteheads.s2slash": "noteheadSlashHorizontalEnds",
    # rests ("o" is the form drawn outside the staff, with a ledger line)
    "rests.M3": "restMaxima", "rests.M2": "restLonga", "rests.M1": "restDoubleWhole",
    "rests.M1o": "restDoubleWholeLegerLine", "rests.0": "restWhole", "rests.0o": "restWholeLegerLine",
    "rests.1": "restHalf", "rests.1o": "restHalfLegerLine", "rests.2": "restQuarter",
    "rests.2classical": "restQuarterOld", "rests.2z": "restQuarterZ", "rests.3": "rest8th",
    "rests.4": "rest16th", "rests.5": "rest32nd", "rests.6": "rest64th", "rests.7": "rest128th",
    "rests.8": "rest256th", "rests.9": "rest512th", "rests.10": "rest1024th",
    # accidentals, with the names of LilyPond before 2.12 (accidentals.2 is a sharp)
    "accidentals.sharp": "accidentalSharp", "accidentals.2": "accidentalSharp",
    "accidentals.natural": "accidentalNatural", "accidentals.0": "accidentalNatural",
    "accidentals.flat": "accidentalFlat", "accidentals.M2": "accidentalFlat",
    "accidentals.doublesharp": "accidentalDoubleSharp", "accidentals.4": "accidentalDoubleSharp",
    "accidentals.flatflat": "accidentalDoubleFlat", "accidentals.M4": "accidentalDoubleFlat",
    "accidentals.leftparen": "accidentalParensLeft", "accidentals.rightparen": "accidentalParensRight",
    "dots.dot": "augmentationDot",
    # clefs ("_change" is the smaller clef drawn for a change)
    "clefs.G": "gClef", "clefs.F": "fClef", "clefs.C": "cClef",
    "clefs.percussion": "unpitchedPercussionClef1", "clefs.varpercussion": "unpitchedPercussionClef2",
    "clefs.tab": "6stringTabClef",
    "timesig.C44": "timeSigCommon", "timesig.C22": "timeSigCutCommon",
    # flags
    "flags.u3": "flag8thUp", "flags.u4": "flag16thUp", "flags.u5": "flag32ndUp", "flags.u6": "flag64thUp",
    "flags.u7": "flag128thUp", "flags.d3": "flag8thDown", "flags.d4": "flag16thDown",
    "flags.d5": "flag32ndDown", "flags.d6": "flag64thDown", "flags.d7": "flag128thDown",
    "flags.ugrace": "graceNoteSlashStemUp", "flags.dgrace": "graceNoteSlashStemDown",
    # articulations and ornaments ("u" above the note, "d" below)
    "scripts.ufermata": "fermataAbove", "scripts.dfermata": "fermataBelow",
    "scripts.ushortfermata": "fermataShortAbove", "scripts.dshortfermata": "fermataShortBelow",
    "scripts.ulongfermata": "fermataLongAbove", "scripts.dlongfermata": "fermataLongBelow",
    "scripts.uverylongfermata": "fermataVeryLongAbove", "scripts.dverylongfermata": "fermataVeryLongBelow",
    "scripts.uveryshortfermata": "fermataVeryShortAbove", "scripts.dveryshortfermata": "fermataVeryShortBelow",
    "scripts.sforzato": "articAccentAbove", "scripts.staccato": "articStaccatoAbove",
    "scripts.ustaccatissimo": "articStaccatissimoAbove", "scripts.dstaccatissimo": "articStaccatissimoBelow",
    "scripts.tenuto": "articTenutoAbove", "scripts.uportato": "articTenutoStaccatoAbove",
    "scripts.dportato": "articTenutoStaccatoBelow", "scripts.umarcato": "articMarcatoAbove",
    "scripts.dmarcato": "articMarcatoBelow", "scripts.open": "brassMuteOpen",
    "scripts.halfopen": "brassMuteHalfClosed", "scripts.stopped": "brassMuteClosed",
    "scripts.upbow": "stringsUpBow", "scripts.uupbow": "stringsUpBow", "scripts.dupbow": "stringsUpBow",
    "scripts.downbow": "stringsDownBow", "scripts.udownbow": "stringsDownBow", "scripts.ddownbow": "stringsDownBow",
    "scripts.flageolet": "stringsHarmonic", "scripts.thumb": "stringsThumbPosition",
    "scripts.snappizzicato": "pluckedSnapPizzicatoAbove",
    "scripts.turn": "ornamentTurn", "scripts.reverseturn": "ornamentTurnInverted",
    "scripts.slashturn": "ornamentTurnSlash", "scripts.haydnturn": "ornamentHaydn",
    "scripts.trill": "ornamentTrill", "scripts.prall": "ornamentShortTrill",
    "scripts.mordent": "ornamentMordent", "scripts.prallprall": "ornamentTremblement",
    "scripts.prallmordent": "ornamentPrecompTrillWithMordent",
    "scripts.upprall": "ornamentPrecompSlide", "scripts.downprall": "ornamentPrecompMordentUpperPrefix",
    "scripts.pralldown": "ornamentPrecompTrillLowerSuffix", "scripts.lineprall": "ornamentPrecompAppoggTrill",
    "scripts.segno": "segno", "scripts.varsegno": "segnoSerpent1",
    "scripts.coda": "coda", "scripts.varcoda": "codaSquare",
    "scripts.rcomma": "breathMarkComma", "scripts.lcomma": "breathMarkComma",
    "scripts.caesura.straight": "caesura", "scripts.caesura.curved": "caesuraCurved",
    "scripts.arpeggio": "wiggleArpeggiatoUp", "scripts.arpeggio.arrow.1": "arrowheadBlackUp",
    "scripts.trill_element": "wiggleTrill",
    # pedal marks, built from letters
    "pedal.Ped": "keyboardPedalPed", "pedal.*": "keyboardPedalUp", "pedal.P": "keyboardPedalP",
    "pedal.d": "keyboardPedalD", "pedal.e": "keyboardPedalE", "pedal..": "keyboardPedalDot",
    "brackettips.up": "bracketTop", "brackettips.down": "bracketBottom",
    # shape-note heads: a black, half or whole notehead of another shape
    **{f"noteheads.s{v}{shape}{style}": ("noteheadBlack", "noteheadHalf", "noteheadWhole")[2 - v]
       for v in (0, 1, 2) for shape in ("do", "re", "mi", "fa", "sol", "la", "ti", "miMirror")
       for style in ("", "Thin", "Funk", "Walker")},
    **{f"noteheads.{d}{v}{shape}{style}": ("noteheadBlack", "noteheadHalf", "noteheadWhole")[2 - v]
       for d in ("u", "d") for v in (0, 1, 2) for shape in ("do", "re", "mi", "fa", "ti")
       for style in ("", "Thin", "Funk", "Walker")},
    "ties.lyric.short": "lyricsElision", "ties.lyric.default": "lyricsElision",
}
# Digits are time signatures, and the letters dynamics. The fattened digits
# are the same digits drawn heavier (LilyPond's figured bass and some styles).
_DIGITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
for _i, _digit in enumerate(_DIGITS):
    _EMMENTALER[_digit] = f"timeSig{_i}"
    _EMMENTALER[f"fattened.{_digit}"] = f"timeSig{_i}"
_EMMENTALER["fattened.four.alt"] = "timeSig4"
_EMMENTALER["four.alt"] = "timeSig4"
_DYNAMIC_LETTERS = {"f": "dynamicForte", "m": "dynamicMezzo", "n": "dynamicNiente", "p": "dynamicPiano",
                    "r": "dynamicRinforzando", "s": "dynamicSforzando", "z": "dynamicZ"}
_EMMENTALER.update(_DYNAMIC_LETTERS)
# The character codes the alphabet glyphs keep (digits and dynamic letters).
_EMMENTALER_CODES = {ord(str(i)): f"timeSig{i}" for i in range(10)}
_EMMENTALER_CODES.update({ord(letter): name for letter, name in _DYNAMIC_LETTERS.items()})


# Punctuation in the Emmentaler fonts belongs to text drawn in them (the dot
# of "8va", figured bass); it is passed on as text, not counted as unmapped.
EMMENTALER_TEXT = {"period": ".", "comma": ",", "hyphen": "-", "plus": "+", "slash": "/",
                   "parenleft": "(", "parenright": ")", "space": " "}


def emmentaler_symbol(glyph_name, code):
    """The SMuFL name for an Emmentaler glyph, by its glyph name if the font
    has one, else by its character code. Every brace size is a brace."""
    if glyph_name:
        if re.fullmatch(r"brace\d+", glyph_name):
            return "brace"
        if glyph_name in _EMMENTALER:
            return _EMMENTALER[glyph_name]
        if glyph_name.endswith("_change") and glyph_name[:-7] in _EMMENTALER:
            return _EMMENTALER[glyph_name[:-7]]
        if glyph_name.endswith(".figbass") and glyph_name[:-8] in _EMMENTALER:
            return _EMMENTALER[glyph_name[:-8]]
    return _EMMENTALER_CODES.get(code)


# ------------------------------------------------------------- Sonata layout
#
# Bytes are Mac Roman: 0xCF is "Œ" (U+0153). A Windows symbol font moves
# each byte up by U+F000. Where the three fonts differ, the difference is in
# how a symbol is used, not in what it is (Finale also uses the rhythm dot for
# staccato), and the later stages tell such cases apart by position.

SONATA = {
    0x21: "tremolo1", 0x23: "accidentalSharp", 0x25: "segno", 0x26: "gClef",
    0x27: "articStaccatissimoBelow", 0x28: "accidentalParensLeft", 0x29: "accidentalParensRight",
    0x2A: "keyboardPedalUp", 0x2B: "brassMuteClosed", 0x2C: "breathMarkComma",
    0x2D: "articTenutoAbove", 0x2E: "augmentationDot",
    0x30: "timeSig0", 0x31: "timeSig1", 0x32: "timeSig2", 0x33: "timeSig3", 0x34: "timeSig4",
    0x35: "timeSig5", 0x36: "timeSig6", 0x37: "timeSig7", 0x38: "timeSig8", 0x39: "timeSig9",
    0x3D: "staff5Lines", 0x3E: "articAccentAbove", 0x3F: "fClef", 0x40: "tremolo2", 0x41: "accidentalFlat",
    0x42: "cClef", 0x43: "timeSigCutCommon", 0x45: "note8thDown", 0x46: "dynamicMF",
    0x48: "noteHalfDown", 0x49: "accidentalSharp", 0x4A: "flag8thDown", 0x4B: "flag8thUp",
    0x4D: "ornamentMordent", 0x4E: "accidentalNatural", 0x50: "dynamicMP", 0x51: "noteQuarterDown",
    0x52: "flag16thDown", 0x53: "dynamicSforzando1", 0x54: "ornamentTurn", 0x55: "fermataAbove",
    0x56: "gClef8vb", 0x57: "noteheadDoubleWhole", 0x58: "note16thDown", 0x5A: "dynamicForzando",
    0x5B: "accidentalSharp", 0x5D: "accidentalDoubleSharp", 0x5E: "articMarcatoAbove",
    0x61: "accidentalSharp", 0x62: "accidentalFlat", 0x63: "timeSigCommon", 0x65: "note8thUp",
    0x66: "dynamicForte", 0x68: "noteHalfUp", 0x69: "accidentalFlat", 0x6A: "flag8thUp",
    0x6B: "articStaccatoAbove", 0x6D: "ornamentShortTrill", 0x6E: "accidentalNatural",
    0x6F: "stringsHarmonic", 0x70: "dynamicPiano", 0x71: "noteQuarterUp", 0x72: "flag16thUp",
    0x73: "dynamicSforzando", 0x74: "fClef8vb", 0x75: "fermataBelow", 0x76: "stringsUpBow",
    0x77: "noteheadWhole", 0x78: "note16thUp", 0x7A: "dynamicZ", 0x7B: "accidentalFlat",
    0x7E: "wiggleTrill",
    0x81: "accidentalDoubleSharp", 0x82: "dynamicSforzandoPiano", 0x8C: "accidentalDoubleFlat",
    0x8D: "dynamicSforzatoFF", 0xA0: "gClef8va", 0xA1: "keyboardPedalPed", 0xA7: "dynamicSforzato",
    0xA8: "rest32nd", 0xAB: "articStaccatissimoAbove", 0xAC: "articMarcatoAbove",
    0xAE: "articStaccatissimoAbove", 0xAF: "dynamicPPPP", 0xB2: "stringsUpBow",
    0xB3: "stringsDownBow", 0xB6: "dynamicSforzandoPianissimo", 0xB7: "restWhole",
    0xB8: "dynamicPPP", 0xB9: "dynamicPP", 0xBA: "accidentalDoubleFlat", 0xBE: "tremolo3",
    0xC3: "ottavaAlta", 0xC4: "dynamicFF", 0xC5: "rest16th", 0xC7: "repeat2Bars",
    0xCE: "restQuarter", 0xCF: "noteheadBlack", 0xD0: "noteheadSquareBlack",
    0xD1: "noteheadTriangleUpBlack", 0xD2: "accidentalNatural", 0xD3: "accidentalDoubleFlat",
    0xD4: "repeat1Bar", 0xD7: "ottavaBassaVb", 0xD8: "articStaccatissimoBelow", 0xD9: "ornamentTrill",
    0xDB: "quindicesimaAlta", 0xDC: "accidentalDoubleSharp", 0xDE: "coda",
    0xDF: "articAccentStaccatoAbove", 0xE2: "noteheadDiamondBlack", 0xE4: "rest8th",
    0xE5: "rest128th", 0xE6: "fClef8va", 0xE9: "accidentalNatural", 0xEA: "dynamicFortePiano",
    0xEB: "dynamicFFFF", 0xEC: "dynamicFFF", 0xEE: "restHalf", 0xEF: "flag8thDown",
    0xF4: "rest64th", 0xF9: "articTenutoAccentAbove", 0xFA: "noteheadHalf",
}

# The companion fonts (OpusSpecial, HelsinkiSpecial). Byte 0xC0, the hook at
# the end of a dashed line, has no SMuFL glyph; it is drawn with the line and
# is listed so that it is not counted as unmapped; so are the "va" and "vb" of
# "8va" and "8vb". Byte 0xB7 is a ledger line, which Sibelius draws as a glyph.
SONATA_SPECIAL = {
    0x3C: "accidentalParensLeft", 0x3D: "systemDivider", 0x3E: "accidentalParensRight",
    0x7B: "brace", 0xA1: "bracketTop", 0xA2: "bracketBottom", 0xAA: "augmentationDot",
    0xB7: "legerLine", 0xB8: "wiggleArpeggiatoUp", 0xBE: "tremolo1", 0xC0: "lineHook",
    0xD0: "articLaissezVibrerAbove", 0xD1: "articLaissezVibrerBelow", 0xD2: "ottava",
    0xD3: "ottavaSuffixAlta", 0xD4: "ottavaSuffixBassa", 0xDE: "graceNoteSlashStemUp",
}

# Names that are not SMuFL glyphs but are known parts of a drawing: the hook
# at the end of a dashed line, and the "va" or "vb" drawn after the "8" of an
# ottava (the "8" is SMuFL's "ottava").
NOT_SMUFL = {"lineHook", "ottavaSuffixAlta", "ottavaSuffixBassa"}

LEGACY_FAMILIES = {
    "opus": ("Sibelius", SONATA), "helsinki": ("Sibelius", SONATA), "inkpen2": ("Sibelius", SONATA),
    "reprise": ("Sibelius", SONATA), "norfolk": ("Sibelius", SONATA),
    "maestro": ("Finale", SONATA), "petrucci": ("Finale", SONATA), "engraver": ("Finale", SONATA),
    "jazz": ("Finale", SONATA), "broadwaycopyist": ("Finale", SONATA), "sonata": ("Sonata", SONATA),
}


def legacy_table(font_name):
    """(table name, table) for a named legacy font, or None. A name with
    "Special" uses the companion table; a text companion (OpusText) is text."""
    squashed = re.sub(r"[^a-z0-9]", "", font_name.lower())
    if squashed.startswith(("emmentaler", "pfaemmentaler", "feta")):
        return "emmentaler", None
    if "text" in squashed or "times" in squashed:
        return None
    for family, (_, table) in LEGACY_FAMILIES.items():
        if squashed.startswith(family):
            if "special" in squashed:
                return "sonata-special", SONATA_SPECIAL
            return "sonata", table
    return None


def sonata_byte(code):
    """The 8-bit Sonata byte for a character code from the PDF's text layer:
    a symbol-font code (U+F0xx) or a Unicode character from the Mac Roman set.
    None if the code is neither."""
    if 0xF020 <= code <= 0xF0FF:
        return code - 0xF000
    if 32 <= code < 0x80:
        return code
    try:
        return chr(code).encode("mac_roman")[0]
    except (UnicodeEncodeError, ValueError):
        return None
