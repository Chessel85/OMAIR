"""Decide a page's type from its evidence, by the rules in
docs/notes/inspector-spec.md ("Decision rules" and "Telling C from D").

Thresholds are starting values. If you change one, change the spec too.
"""

from dataclasses import dataclass, field

from omr.pdf import evidence

MIN_SYMBOLS = 10  # music glyphs or repeated shapes needed to call a page A or B
FEW_SYMBOLS = 3   # enough when staves are also found (the last page of a score is often sparse)
BIG_IMAGE = 0.50
SMALL_IMAGE = 0.10
UNEVEN_BACKGROUND = 40
TILT_LIMIT = 0.3

TYPE_NAMES = {
    "A": "vector music with font glyphs",
    "B": "vector music with outlined glyphs",
    "C": "clean raster music",
    "D": "photo or scan",
    "N": "no music",
}


@dataclass
class Decision:
    type: str
    confidence: str
    reason: str
    notes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def staves_text(n):
    return "1 staff" if n == 1 else f"{n} staves"


def music_font_names(ev):
    return " and ".join(f.name for f in ev.music_fonts) or "no font"


def split_raster(ev, measures, confidence="medium", base_reason=""):
    """Type C or D from the raster measures. Never high confidence in Phase 0."""
    signs = []
    if measures["background_range"] > UNEVEN_BACKGROUND:
        signs.append(
            f"uneven background (paper brightness varies by {measures['background_range']:.0f} out of 255)"
        )
    if measures["dark_border"]:
        signs.append("dark border")
    if abs(measures["tilt_degrees"]) > TILT_LIMIT:
        signs.append(f"tilted staff lines ({measures['tilt_degrees']:+.1f} degrees)")
    notes = []
    if signs:
        reason = "Image shows signs of a physical page: " + ", ".join(signs) + "."
        kind = "D"
    else:
        reason = "Image looks like a clean digital rendering: even white background, no border, level staff lines."
        kind = "C"
        if measures["bilevel"]:
            notes.append("clean bilevel scan of a printed page")
            confidence = "medium"
    if base_reason:
        reason = f"{base_reason} {reason}"
    return kind, confidence, reason, notes


def classify(ev, raster_fn):
    """Return a Decision. `raster_fn()` is called only if the page is raster."""
    glyphs, repeated = ev.music_glyphs, ev.repeated_shapes
    staves = ev.staves.five_line
    coverage = ev.image_coverage
    notes, warnings = [], []

    def finish(kind, confidence, reason):
        if kind in ("A", "B"):
            if glyphs >= MIN_SYMBOLS and repeated >= MIN_SYMBOLS:
                notes.append("mixed: both font glyphs and outlined shapes")
                warnings.append("mixed page: both font glyphs and outlined shapes")
            if coverage >= BIG_IMAGE:
                notes.append("large image also present, possibly a background")
        if kind == "B" and confidence == "low":
            warnings.append("Type B page with low confidence: look at it by hand")
        for font in ev.fonts:
            if font.cls == "unknown_music":
                warnings.append(f"unknown font, probably music: {font.name}")
                if font.font_type == "Type3":
                    notes.append(f"{font.name} is a Type 3 font: Phase 1 would need to fingerprint its glyph procedures")
            elif font.cls == "text" and font.on_staves >= 10 and not evidence.looks_like_letters(font):
                warnings.append(f"text font with {font.on_staves} glyphs on staves, check it is not music: {font.name}")
        if ev.hidden_text_glyphs:
            notes.append("hidden text layer, probably OCR")
            warnings.append("hidden text layer, probably OCR")
        return Decision(kind, confidence, reason, notes, warnings)

    # 1. raster
    if coverage >= BIG_IMAGE and glyphs < MIN_SYMBOLS and repeated < MIN_SYMBOLS:
        kind, conf, reason, extra = split_raster(ev, _measure(ev, raster_fn))
        notes.extend(extra)
        return finish(kind, conf, f"An image covers {coverage * 100:.0f} percent of the page and there are no music symbols in the vector content. {reason}")
    # 2. type A (a few glyphs are enough when staves are found, with medium confidence)
    few = staves >= 1 and glyphs >= FEW_SYMBOLS
    if (glyphs >= MIN_SYMBOLS or few) and glyphs >= repeated:
        conf = "high" if staves >= 1 and glyphs >= MIN_SYMBOLS else "medium"
        return finish("A", conf, f"{_plural(glyphs, 'music glyph')} in {music_font_names(ev)}, and {staves_text(staves)} found from vector lines.")
    # 3. type B
    few = staves >= 1 and repeated >= FEW_SYMBOLS
    if (repeated >= MIN_SYMBOLS or few) and repeated > glyphs:
        conf = "high" if staves >= 1 and repeated >= MIN_SYMBOLS else "medium"
        return finish("B", conf, f"{repeated} outlined shapes are repeated ({ev.outlined['distinct']} distinct shapes in all) and {staves_text(staves)} found from vector lines.")
    # 4. vector, symbols not found
    if staves >= 1:
        return finish("B", "low", "Staves found but no music symbols identified.")
    # 5. raster, partial
    if coverage >= SMALL_IMAGE:
        kind, conf, reason, extra = split_raster(ev, _measure(ev, raster_fn), "low")
        notes.extend(extra)
        return finish(kind, "low", f"Music may be in a smaller image ({coverage * 100:.0f} percent of the page). {reason}")
    # 6. no music
    return finish("N", "high", "No staves, music glyphs or large images found.")


def _measure(ev, raster_fn):
    ev.raster = raster_fn()
    return ev.raster
