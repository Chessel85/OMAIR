"""Detector labels for the raster engines (Phase 2, Stage 2.1): the class of
each SMuFL name, the joins that make one box of a mark drawn in pieces, the
rendering of a page at a chosen staff space with its variations, the YOLO
tiles, and the label checks.

The rules are in docs/notes/raster-labels-spec.md.
"""

import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from omr.pdf import layout as lay
from omr.pdf import markings, notation, text

# ------------------------------------------------------------------ classes

NOTEHEADS = ["noteheadBlack", "noteheadHalf", "noteheadWhole", "noteheadDoubleWhole", "noteheadX",
             "noteheadSlash", "noteheadSlashWhite", "noteheadOther"]
RESTS = ["restDoubleWhole", "restWhole", "restHalf", "restQuarter", "rest8th", "rest16th", "rest32nd", "rest64th"]
FLAGS = ["flag8th", "flag16th", "flag32nd", "flag64th"]
ACCIDENTALS = ["accidentalSharp", "accidentalFlat", "accidentalNatural", "accidentalDoubleSharp",
               "accidentalDoubleFlat", "parenLeft", "parenRight"]
CLEFS = ["gClef", "gClef8vb", "gClef8va", "fClef", "fClef8vb", "cClef", "percussionClef"]
TIME = [f"timeSig{i}" for i in range(10)] + ["timeSigCommon", "timeSigCutCommon"]
TUPLETS = [f"tuplet{i}" for i in range(10)]
DYNAMICS = ["dynamicP", "dynamicPP", "dynamicPPP", "dynamicPPPP", "dynamicMP", "dynamicMF", "dynamicF",
            "dynamicFF", "dynamicFFF", "dynamicFFFF", "dynamicSF", "dynamicSFZ", "dynamicSFP", "dynamicSFFZ",
            "dynamicFZ", "dynamicFP", "dynamicRF", "dynamicRFZ", "dynamicOther"]
MARKS = ["augmentationDot", "staccato", "staccatissimo", "accent", "marcato", "tenuto", "fermata",
         "breathMark", "caesura", "ornamentTrill", "ornamentMordent", "ornamentShortTrill", "ornamentTurn",
         "ornamentTurnInverted", "ornamentOther", "arpeggio", "trillLine", "wavyGlissando", "upBow", "downBow",
         "pedalPed", "pedalUp", "segno", "coda", "octave8", "octave15", "brace", "bracketEnd", "text"]
CLASSES = NOTEHEADS + RESTS + FLAGS + ACCIDENTALS + CLEFS + TIME + TUPLETS + DYNAMICS + MARKS
CLASS_INDEX = {c: i for i, c in enumerate(CLASSES)}

_EXACT = {
    "noteheadBlack": "noteheadBlack", "noteheadHalf": "noteheadHalf", "noteheadWhole": "noteheadWhole",
    "noteheadDoubleWhole": "noteheadDoubleWhole", "noteheadDoubleWholeSquare": "noteheadDoubleWhole",
    "noteheadXBlack": "noteheadX", "noteheadXHalf": "noteheadX", "noteheadXWhole": "noteheadX",
    "noteheadCircleX": "noteheadX", "noteheadSlashHorizontalEnds": "noteheadSlash",
    "noteheadSlashWhiteHalf": "noteheadSlashWhite", "noteheadSlashWhiteWhole": "noteheadSlashWhite",
    "restDoubleWhole": "restDoubleWhole", "restDoubleWholeLegerLine": "restDoubleWhole",
    "restWhole": "restWhole", "restWholeLegerLine": "restWhole", "restHalf": "restHalf",
    "restHalfLegerLine": "restHalf", "restQuarter": "restQuarter", "rest8th": "rest8th", "rest16th": "rest16th",
    "rest32nd": "rest32nd", "rest64th": "rest64th", "rest128th": "rest64th", "rest256th": "rest64th",
    "rest512th": "rest64th", "rest1024th": "rest64th",
    "augmentationDot": "augmentationDot", "repeatDot": "augmentationDot", "metAugmentationDot": "augmentationDot",
    "articStaccatoAbove": "staccato", "articStaccatoBelow": "staccato",
    "accidentalSharp": "accidentalSharp", "accidentalFlat": "accidentalFlat",
    "accidentalNatural": "accidentalNatural", "accidentalDoubleSharp": "accidentalDoubleSharp",
    "accidentalDoubleFlat": "accidentalDoubleFlat",
    "gClef": "gClef", "gClef8vb": "gClef8vb", "gClef8va": "gClef8va", "fClef": "fClef", "fClef8vb": "fClef8vb",
    "cClef": "cClef", "unpitchedPercussionClef1": "percussionClef",
    "timeSigCommon": "timeSigCommon", "timeSigCutCommon": "timeSigCutCommon",
    "articAccentAbove": "accent", "articAccentBelow": "accent", "articMarcatoAbove": "marcato",
    "articMarcatoBelow": "marcato", "articTenutoAbove": "tenuto", "articTenutoBelow": "tenuto",
    "breathMarkComma": "breathMark",
    "ornamentTrill": "ornamentTrill", "ornamentMordent": "ornamentMordent",
    "ornamentShortTrill": "ornamentShortTrill", "ornamentTurn": "ornamentTurn",
    "ornamentTurnInverted": "ornamentTurnInverted",
    "stringsUpBow": "upBow", "stringsDownBow": "downBow", "keyboardPedalUp": "pedalUp",
    "segno": "segno", "coda": "coda", "codaSquare": "coda", "brace": "brace",
    "bracketTop": "bracketEnd", "bracketBottom": "bracketEnd",
}
_EXACT.update({f"timeSig{i}": f"timeSig{i}" for i in range(10)})
_EXACT.update({f"tuplet{i}": f"tuplet{i}" for i in range(10)})

# Glyphs joined into one box with their neighbours, by the kind of join.
ARPEGGIO = "arpeggio"
ROW_JOINS = {"wiggleTrill": "trillLine", "wiggleGlissando": "wavyGlissando"}
PEDAL_PIECES = ("keyboardPedalP", "keyboardPedalE", "keyboardPedalD", "keyboardPedalDot", "keyboardPedalPed")
OCTAVE_PREFIXES = ("ottava", "quindicesima", "octaveSuperscript", "octaveBaseline")
MET_NOTES = {"metNoteQuarterUp": "noteheadBlack", "metNote8thUp": "noteheadBlack", "metNote16thUp": "noteheadBlack",
             "metNoteHalfUp": "noteheadHalf", "metNoteWhole": "noteheadWhole"}


def class_of(name):
    """The detector class of a single SMuFL name, or None. Names that are
    joined with their neighbours (dynamics, arpeggios, pedal and octave
    marks) are classed by their joins, not here."""
    if name in _EXACT:
        return _EXACT[name]
    if name.startswith(("noteheadParenthesis", "accidentalParens", "accidentalBracket", "keyboardPedalParens")):
        return "parenLeft" if name.endswith("Left") else "parenRight" if name.endswith("Right") else None
    if name.startswith(("notehead", "noteShape")):
        return "noteheadOther"
    for flag in FLAGS[:3]:
        if name.startswith(flag):
            return flag
    if re.match(r"flag(64th|128th|256th|512th|1024th)", name):
        return "flag64th"
    if name.startswith("articStaccatissimo"):
        return "staccatissimo"
    if name.startswith("fermata"):
        return "fermata"
    if name.startswith("caesura"):
        return "caesura"
    if name.startswith("ornament"):
        return "ornamentOther"
    return None


def dynamic_class(value):
    """The class of a dynamic by the letters it shows ("mf" is dynamicMF)."""
    if re.fullmatch(r"p{4,}", value):
        return "dynamicPPPP"
    if re.fullmatch(r"f{4,}", value):
        return "dynamicFFFF"
    name = "dynamic" + value.upper()
    return name if name in CLASS_INDEX else "dynamicOther"


# --------------------------------------------------------------- page labels

@dataclass
class Label:
    cls: str
    box: tuple          # (x0, y0, x1, y1) in points, then in pixels
    names: list = field(default_factory=list)   # the SMuFL names or text it came from
    tighten: bool = False   # shrink to the ink found inside it once rendered
    ink: tuple = None       # in pixels: the ink box before the minimum size and padding, for the checks


def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _rows(symbols, space, along):
    """Group symbols that follow each other: side by side on one line
    (along="x") or stacked in one column (along="y")."""
    if along == "x":
        ordered = sorted(symbols, key=lambda s: s.box[0])
    else:
        ordered = sorted(symbols, key=lambda s: s.box[1])
    groups = []
    for s in ordered:
        for g in groups:
            last = g[-1]
            if along == "x":
                # on one baseline; letters overlap where the font kerns them (m and f)
                near = abs(last.y - s.y) <= 0.3 * space \
                    and -1.0 * space <= s.box[0] - last.box[2] <= 0.6 * space
            else:
                near = abs(last.box[0] - s.box[0]) <= 0.4 * space and -1.5 * space <= s.box[1] - last.box[3] <= 0.6 * space
            if near:
                g.append(s)
                break
        else:
            groups.append([s])
    return groups


def _at_clef(clef_box, box):
    """A small digit centred on a clef and touching its top or bottom (as
    omr.pdf.structure._at_clef)."""
    width = clef_box[2] - clef_box[0]
    gap = 0.15 * (clef_box[3] - clef_box[1])
    centre = (clef_box[0] + clef_box[2]) / 2
    if abs((box[0] + box[2]) / 2 - centre) > 0.3 * width:
        return False
    return clef_box[3] - gap <= box[1] <= clef_box[3] + gap or clef_box[1] - gap <= box[3] <= clef_box[1] + gap


def page_labels(page_symbols, text_chars=()):
    """([Label] in points for one page, a Counter of the names left without a
    class, and the boxes of ink left out on purpose). `text_chars` is
    [(char, box)] for the text layer, for the digits of tuplet numbers written
    as text. The ink left out (glyphs with no class, the stem of a
    metronome-mark note) is not counted as missing by the label checks."""
    space = page_symbols.staff_space or 4.0
    symbols = list(page_symbols.symbols)
    labels, unlabelled, ignored = [], Counter(), []
    used = set()

    # text drawn as outlines (Verovio's "MEI engraved with Verovio" footer):
    # rows of shapes clear of the staves that hold an unnamed shape. Letters
    # the vector reader matched to a symbol on such a row are text too.
    staves = [(x0, top - space, x1, bottom + space) for x0, x1, top, bottom in page_symbols.evidence.staves.boxes]
    clear = lambda b: not any(_overlap(b, s) for s in staves)
    loose = [(b, None) for b in page_symbols.unnamed if clear(b)]
    loose += [(s.box, s) for s in symbols if s.source == "outline" and clear(s.box)]
    for row in _box_rows(loose, space):
        if all(s is not None for _, s in row):
            continue   # matched symbols only: music off the staves, not text
        labels.append(Label("text", _union([b for b, _ in row]), ["outlined text"], tighten=True))
        used.update(id(s) for _, s in row if s is not None)
    in_rows = {b for row in _box_rows(loose, space) for b, s in row if s is None}
    ignored += [b for b in page_symbols.unnamed if b not in in_rows]

    # LilyPond's octave clefs: a clef with a small 8 below or above it
    clefs = [s for s in symbols if s.name in ("gClef", "fClef")]
    digit_runs = [r for r in page_symbols.text if r.text.strip() in ("8", "15")]
    for clef in clefs:
        digits = [s for s in symbols if s.name in ("timeSig8", "timeSig1", "timeSig5")
                  and s.size < 0.8 * clef.size and _at_clef(clef.box, s.box)]
        runs = [r for r in digit_runs if _at_clef(clef.box, r.box)]
        if not digits and not runs:
            continue
        shown = "".join(lay_digit(s.name) for s in sorted(digits, key=lambda s: s.box[0])) or runs[0].text.strip()
        boxes = [d.box for d in digits] + [r.box for r in runs]
        below = np.mean([(b[1] + b[3]) / 2 for b in boxes]) > (clef.box[1] + clef.box[3]) / 2
        cls = {("gClef", "8", True): "gClef8vb", ("gClef", "8", False): "gClef8va",
               ("fClef", "8", True): "fClef8vb"}.get((clef.name, shown, below))
        used.update(id(s) for s in [clef, *digits])
        used.update(id(r) for r in runs)
        if cls:
            labels.append(Label(cls, _union([clef.box, *boxes]), [clef.name, shown], tighten=True))
        else:
            unlabelled[f"{clef.name} with {shown}"] += 1
            ignored.append(_union([clef.box, *boxes]))

    # dynamics, joined as the reader joins them
    dynamics = [s for s in symbols if s.name in markings.DYNAMIC_GLYPHS and id(s) not in used]
    for g in _rows(dynamics, space, "x"):
        value = "".join(markings.DYNAMIC_GLYPHS[s.name] for s in g)
        labels.append(Label(dynamic_class(value), _union([s.box for s in g]), [s.name for s in g]))
        used.update(id(s) for s in g)

    # arpeggios (drawn turned, so the font's box is not the ink: tightened later)
    wiggles = [s for s in symbols if s.name.startswith(("wiggleArpeggiato", "arpeggiato"))]
    for g in _rows(wiggles, space, "y"):
        x0 = min(s.box[0] for s in g)
        y0, y1 = min(s.box[1] for s in g) - space, max(s.box[3] for s in g) + space
        labels.append(Label(ARPEGGIO, (x0 - 0.2 * space, y0, x0 + 1.2 * space, y1), [s.name for s in g], tighten=True))
        used.update(id(s) for s in g)
    for name, cls in ROW_JOINS.items():
        for g in _rows([s for s in symbols if s.name.startswith(name)], space, "x"):
            labels.append(Label(cls, _union([s.box for s in g]), [s.name for s in g]))
            used.update(id(s) for s in g)

    # pedal marks: Ped. as one glyph, or as letters and a dot
    for g in _rows([s for s in symbols if s.name in PEDAL_PIECES], space, "x"):
        labels.append(Label("pedalPed", _union([s.box for s in g]), [s.name for s in g]))
        used.update(id(s) for s in g)

    # octave marks: the number with its suffix
    for g in _rows([s for s in symbols if s.name.startswith(OCTAVE_PREFIXES)], space, "x"):
        cls = "octave15" if any(s.name.startswith("quindicesima") for s in g) else "octave8"
        labels.append(Label(cls, _union([s.box for s in g]), [s.name for s in g]))
        used.update(id(s) for s in g)

    for s in symbols:
        if id(s) in used:
            continue
        if s.name in MET_NOTES:
            # the notehead at the foot of a metronome-mark note
            x0, _, x1, y1 = s.box
            labels.append(Label(MET_NOTES[s.name], (x0, y1 - 1.0 * space, min(x1, x0 + 1.2 * space), y1), [s.name]))
            ignored.append(s.box)
            continue
        if s.name.startswith("csym"):
            continue   # joined to the chord symbol's text below
        cls = class_of(s.name)
        if cls is None:
            unlabelled[s.name] += 1
            ignored.append(s.box)
            continue
        box = s.box
        if s.name in ("restWholeLegerLine", "restHalfLegerLine"):
            centre = (box[0] + box[2]) / 2
            box = (centre - 0.65 * space, box[1], centre + 0.65 * space, box[3])
        labels.append(Label(cls, box, [s.name]))

    # text: tuplet numbers by digit, octave marks, and the rest as text runs
    chord_glyphs = [s for s in symbols if s.name.startswith("csym")]
    text_boxes = []
    for run in page_symbols.text:
        if id(run) in used or not run.text.strip():
            continue
        if text.is_italic(run.font) and notation.TUPLET_TEXT.match(run.text):
            digits = [(c, b) for c, b in text_chars if c.isdigit() and _inside_centre(b, run.box)]
            for c, b in digits:
                labels.append(Label(f"tuplet{c}", b, [run.text], tighten=True))
            if digits:
                continue
        match = notation.OCTAVE_TEXT.match(run.text)
        if match and match.group(2):
            labels.append(Label("octave15" if match.group(1) == "15" else "octave8", run.box, [run.text], tighten=True))
            continue
        text_boxes.append([run.box, [run.text]])
    for g in chord_glyphs:
        grown = (g.box[0] - 0.3 * space, g.box[1] - 0.3 * space, g.box[2] + 0.3 * space, g.box[3] + 0.3 * space)
        touching = [t for t in text_boxes if _overlap(grown, t[0])]
        if touching:
            touching[0][0] = _union([touching[0][0], g.box])
            touching[0][1].append(g.name)
        else:
            text_boxes.append([g.box, [g.name]])
    labels += [Label("text", box, names, tighten=True) for box, names in text_boxes]
    return labels, unlabelled, ignored


def _box_rows(boxes, space):
    """(box, symbol) items side by side on one line (overlapping heights,
    gaps under one staff space), as rows."""
    rows = []
    for item in sorted(boxes, key=lambda item: item[0][0]):
        b = item[0]
        for row in rows:
            last = row[-1][0]
            if b[0] - last[2] <= space and min(b[3], last[3]) - max(b[1], last[1]) > 0:
                row.append(item)
                break
        else:
            rows.append([item])
    return rows


def lay_digit(name):
    return name.replace("timeSig", "")


def _inside_centre(box, outer):
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return outer[0] <= x <= outer[2] and outer[1] <= y <= outer[3]


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def text_characters(page):
    """[(char, box)] for every character of the text layer, as the page is shown."""
    import pymupdf

    turn = page.rotation_matrix if page.rotation % 360 else None
    out = []
    for span in page.get_texttrace():
        for code, _, _, bbox in span["chars"]:
            if turn is not None:
                bbox = tuple(pymupdf.Rect(bbox) * turn)
            out.append((chr(code), tuple(bbox)))
    return out


# ------------------------------------------------------------------ rendering

INK = 128          # grey level below which a pixel is ink (the black-and-white variation)
FAINT_INK = 200    # for the checks and for fitting boxes: thin strokes render pale grey at small scales


def render(page, zoom):
    """The page as shown, greyscale, at `zoom` pixels per point."""
    import pymupdf

    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()


def staff_boxes_px(staves, zoom):
    """Five-line staves as (x0, x1, top, bottom) in pixels."""
    return [tuple(v * zoom for v in box) for box in staves.boxes]


def remove_staff_lines(ink, staff_boxes):
    """A copy of the ink mask with staff-line pixels removed: in each staff,
    rows that are mostly ink across the staff are staff lines, and their
    pixels are cleared where no ink lies just above and below the line."""
    out = ink.copy()
    h, w = ink.shape
    for x0, x1, top, bottom in staff_boxes:
        a, b = max(0, int(x0)), min(w, int(x1) + 1)
        y_lo, y_hi = max(1, int(top) - 3), min(h - 1, int(bottom) + 4)
        if b - a < 10:
            continue
        rows = [y for y in range(y_lo, y_hi) if ink[y, a:b].mean() > 0.6]
        bands, start = [], None
        for y in rows + [None]:
            if start is not None and (y is None or y != prev + 1):
                bands.append((start, prev))
                start = None
            if y is not None and start is None:
                start = y
            prev = y
        for y0, y1 in bands:
            above, below = max(0, y0 - 1), min(h - 1, y1 + 1)
            clear = ~ink[above, a:b] & ~ink[below, a:b]
            out[y0:y1 + 1, a:b] &= ~clear
    return out


def to_pixels(labels, zoom, space_px, shape):
    """Scale labels to pixels, apply the minimum size and padding, and clip to the image."""
    h, w = shape
    least = 0.5 * space_px
    out = []
    for lab in labels:
        x0, y0, x1, y1 = (v * zoom for v in lab.box)
        ink = (max(0.0, x0), max(0.0, y0), min(float(w), x1), min(float(h), y1))
        if x1 - x0 < least:
            c = (x0 + x1) / 2
            x0, x1 = c - least / 2, c + least / 2
        if y1 - y0 < least:
            c = (y0 + y1) / 2
            y0, y1 = c - least / 2, c + least / 2
        x0, y0, x1, y1 = max(0, x0 - 1), max(0, y0 - 1), min(w, x1 + 1), min(h, y1 + 1)
        out.append(Label(lab.cls, (x0, y0, x1, y1), lab.names, lab.tighten, ink))
    return out


def tighten(labels, ink, space_px):
    """Shrink the labels marked for it to the ink inside them (text, tuplet
    digits, octave text, arpeggios), keeping the minimum size."""
    for lab in labels:
        if not lab.tighten:
            continue
        x0, y0, x1, y1 = (int(round(v)) for v in lab.box)
        part = ink[y0:y1, x0:x1]
        if not part.any():
            continue
        ys, xs = np.nonzero(part)
        box = (x0 + xs.min(), y0 + ys.min(), x0 + xs.max() + 1, y0 + ys.max() + 1)
        lab.ink = tuple(float(v) for v in box)
        least = 0.5 * space_px
        bx0, by0, bx1, by1 = box
        if bx1 - bx0 < least:
            c = (bx0 + bx1) / 2
            bx0, bx1 = c - least / 2, c + least / 2
        if by1 - by0 < least:
            c = (by0 + by1) / 2
            by0, by1 = c - least / 2, c + least / 2
        lab.box = tuple(float(v) for v in (max(0, bx0 - 1), max(0, by0 - 1), min(ink.shape[1], bx1 + 1), min(ink.shape[0], by1 + 1)))
    return labels


def extend_outlined_text(labels, ink, space_px):
    """Widen each row of outlined text along its line while ink goes on
    within a staff space (Verovio's logo is one shape the reader skips)."""
    h, w = ink.shape
    gap = int(round(space_px))
    for lab in labels:
        if lab.names != ["outlined text"]:
            continue
        x0, y0, x1, y1 = (int(round(v)) for v in lab.box)
        rows = ink[max(0, y0):min(h, y1)]
        columns = rows.any(axis=0)
        while x1 < w and columns[x1:min(w, x1 + gap)].any():
            x1 = x1 + int(np.argmax(columns[x1:min(w, x1 + gap)])) + 1
            while x1 < w and columns[x1]:
                x1 += 1
        while x0 > 0 and columns[max(0, x0 - gap):x0].any():
            x0 = max(0, x0 - gap) + int(np.nonzero(columns[max(0, x0 - gap):x0])[0][0])
            while x0 > 0 and columns[x0 - 1]:
                x0 -= 1
        lab.box = (float(x0), lab.box[1], float(x1), lab.box[3])
        lab.ink = lab.box
    return labels


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def drop_duplicates(labels, limit=0.8):
    """One box for two of one class over the same ink (a unison notehead drawn twice)."""
    kept = []
    for lab in labels:
        if not any(k.cls == lab.cls and iou(k.box, lab.box) > limit for k in kept):
            kept.append(lab)
    return kept


# ------------------------------------------------------------------ variations

def choose_variations(rng):
    """The clean variations for one page (spec, "Detector data")."""
    v = {}
    if rng.random() < 0.3:
        v["blur"] = round(float(rng.uniform(0.3, 0.8)), 2)
    if rng.random() < 0.3:
        v["noise"] = round(float(rng.uniform(2, 6)), 1)
    if rng.random() < 0.2:
        v["black and white"] = True
    if rng.random() < 0.4:
        v["jpeg"] = int(rng.integers(50, 96))
    return v


def apply_variations(grey, v, rng):
    import cv2

    img = grey
    if "blur" in v:
        img = cv2.GaussianBlur(img, (0, 0), v["blur"])
    if "noise" in v:
        img = np.clip(img.astype(np.float32) + rng.normal(0, v["noise"], img.shape), 0, 255).astype(np.uint8)
    if "black and white" in v:
        img = np.where(img < INK, 0, 255).astype(np.uint8)
    if "jpeg" in v:
        ok, data = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, v["jpeg"]])
        img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    return img


def page_seed(*parts):
    """A seed for one page that does not depend on the order the pages are made in."""
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


# ------------------------------------------------------------------ tiles

TILE = 640
OVERLAP = 160
MIN_VISIBLE = 0.5
EMPTY_KEEP = 0.1


def tiles(image, labels, seed, size=TILE, overlap=OVERLAP):
    """Yield (x, y, tile image, [(class index, box in the tile)]) for the
    overlapping tiles of a page. A box is kept if at least half of it is
    inside, clipped to the tile. Tiles with no box are kept one in ten."""
    h, w = image.shape
    step = size - overlap
    xs = list(range(0, max(1, w - overlap), step))
    ys = list(range(0, max(1, h - overlap), step))
    rng = np.random.default_rng(seed)
    for y in ys:
        for x in xs:
            tile = np.full((size, size), 255, dtype=np.uint8)
            part = image[y:y + size, x:x + size]
            tile[:part.shape[0], :part.shape[1]] = part
            kept = []
            for lab in labels:
                x0, y0, x1, y1 = lab.box
                cx0, cy0, cx1, cy1 = max(x0, x), max(y0, y), min(x1, x + size), min(y1, y + size)
                if cx1 <= cx0 or cy1 <= cy0:
                    continue
                if (cx1 - cx0) * (cy1 - cy0) < MIN_VISIBLE * (x1 - x0) * (y1 - y0):
                    continue
                kept.append((CLASS_INDEX[lab.cls], (cx0 - x, cy0 - y, cx1 - x, cy1 - y)))
            if not kept and rng.random() >= EMPTY_KEEP:
                continue
            yield x, y, tile, kept


def yolo_lines(kept, size=TILE):
    return "".join(f"{c} {(b[0] + b[2]) / 2 / size:.6f} {(b[1] + b[3]) / 2 / size:.6f} "
                   f"{(b[2] - b[0]) / size:.6f} {(b[3] - b[1]) / size:.6f}\n" for c, b in kept)


def png_bytes(image):
    import cv2

    ok, data = cv2.imencode(".png", image)
    return data.tobytes()


# ------------------------------------------------------------------ checks

# How far a box's ink edge may be from the ink found: two pixels for
# anti-aliasing, and a tenth of a staff space because symbols.py measures a
# glyph's ink from a drawing at 12 pixels a staff space.
FIT_PIXELS = 2
FIT_SPACES = 0.1


def glyph_ink(doc, page_number, zoom):
    """The ink of the page's text layer alone (music-font and text glyphs),
    with every drawing removed: on a Type A page this is all the symbol ink,
    and none of the lines."""
    import pymupdf

    tmp = pymupdf.open()
    try:
        tmp.insert_pdf(doc, from_page=page_number - 1, to_page=page_number - 1)
        page = tmp[0]
        page.add_redact_annot(page.rect)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                              text=pymupdf.PDF_REDACT_TEXT_NONE)
        return render(page, zoom) < FAINT_INK
    finally:
        tmp.close()


def check_page(labels, ink, space_px, glyphs=None, ignored=()):
    """Counts for the label checks of one page (spec, "Checking the labels").
    `ink` is the clean ink mask with staff lines removed; `glyphs` is the ink
    of the text layer alone (glyph_ink), or None on a page drawn in outlines,
    whose unnamed shapes the vector reader counts instead. Glyph ink inside
    the `ignored` boxes (pixels), the ink the rule leaves out on purpose, is
    not counted.

    Returns (counts, fit counts by (class, kind), unlabelled pieces as
    (x, y, width, height) in pixels)."""
    import cv2

    h, w = ink.shape
    c = Counter()
    fit = Counter()
    for lab in labels:
        x0, y0, x1, y1 = lab.box
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            c["outside the image"] += 1
            continue
        e0, f0, e1, f1 = lab.ink or lab.box
        a0, b0 = max(0, int(e0) - 1), max(0, int(f0) - 1)
        a1, b1 = min(w, int(np.ceil(e1)) + 1), min(h, int(np.ceil(f1)) + 1)
        part = ink[b0:b1, a0:a1]
        fit[(lab.cls, "boxes")] += 1
        if not part.any():
            fit[(lab.cls, "empty")] += 1
            continue
        ys, xs = np.nonzero(part)
        gaps = (xs.min() + a0 - e0, ys.min() + b0 - f0, e1 - (xs.max() + a0 + 1), f1 - (ys.max() + b0 + 1))
        worst = max(gaps)
        if worst <= FIT_PIXELS + FIT_SPACES * space_px:
            fit[(lab.cls, "fit")] += 1
        elif worst <= FIT_PIXELS + 0.3 * space_px:
            fit[(lab.cls, "within 0.3 spaces")] += 1
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            if a.cls == b.cls and iou(a.box, b.box) > 0.5:
                c["double labels"] += 1
    pieces = []
    if glyphs is not None:
        covered = np.zeros_like(glyphs)
        for x0, y0, x1, y1 in [lab.box for lab in labels] + list(ignored):
            covered[max(0, int(y0) - 1):int(np.ceil(y1)) + 1, max(0, int(x0) - 1):int(np.ceil(x1)) + 1] = True
        c["glyph ink"] += int(glyphs.sum())
        rest = (glyphs & ~covered).astype(np.uint8)
        count, _, stats, _ = cv2.connectedComponentsWithStats(rest, connectivity=8)
        for k in range(1, count):
            x, y, bw, bh, area = (int(v) for v in stats[k])
            if area < 4 or min(bw, bh) <= 2:
                continue   # anti-aliasing at a box's edge
            c["unlabelled glyph ink"] += area
            c["unlabelled pieces"] += 1
            pieces.append((x, y, bw, bh))
    return c, fit, pieces
