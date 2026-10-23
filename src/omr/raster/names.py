"""Detections to the vector reader's symbols (Phase 2, Stage 2.4).

Each detector class (omr.corpus.raster_labels.CLASSES) is given one SMuFL
name the reader knows, an origin where SMuFL anchors that glyph (placed in
the detection's box where the vector reader finds it in fonts of that
height, anchors.json, measured by scripts/measure_anchors.py), and a size
from its height, so the reader can tell grace notes and clef changes.
Two classes over one symbol are settled by confidence, and an unsure
detection carries a doubt that the reader turns into a flag.

The rules are in docs/notes/raster-reading-spec.md.
"""

import functools
import json
import re
import statistics
from pathlib import Path

from omr.corpus import raster_labels as rl
from omr.pdf import shapes
from omr.pdf.symbols import Symbol

SAME_SYMBOL = 0.5     # IoU at which boxes of two classes are one symbol
UNSURE = 0.5          # a detection less confident than this is a doubt
CLOSE = 0.15          # a rival class this near in confidence is a doubt
FULL_SIZE = 0.9       # a height this share of the reference's or more is full size
TYPICAL_COUNT = 5     # detections of one name on a page that give its usual height there
SOURCE = "detector"
ANCHORS = Path(__file__).with_name("anchors.json")

NAMES = {
    "noteheadX": "noteheadXBlack", "noteheadSlash": "noteheadSlashHorizontalEnds",
    "noteheadSlashWhite": "noteheadSlashWhiteHalf", "noteheadOther": "noteheadBlack",
    "parenLeft": "accidentalParensLeft", "parenRight": "accidentalParensRight",
    "percussionClef": "unpitchedPercussionClef1",
    "dynamicP": "dynamicPiano", "dynamicF": "dynamicForte", "dynamicSF": "dynamicSforzando1",
    "dynamicSFZ": "dynamicSforzato", "dynamicSFP": "dynamicSforzandoPiano", "dynamicSFFZ": "dynamicSforzatoFF",
    "dynamicFZ": "dynamicForzando", "dynamicFP": "dynamicFortePiano", "dynamicRF": "dynamicRinforzando1",
    "dynamicRFZ": "dynamicRinforzando2",
    "breathMark": "breathMarkComma", "arpeggio": "wiggleArpeggiatoUp", "trillLine": "wiggleTrill",
    "wavyGlissando": "wiggleGlissando", "upBow": "stringsUpBow", "downBow": "stringsDownBow",
    "pedalPed": "keyboardPedalPed", "pedalUp": "keyboardPedalUp", "octave8": "ottava", "octave15": "quindicesima",
}
# marks whose SMuFL name says which side of the note they are on
SIDED = {"staccato": "articStaccato", "staccatissimo": "articStaccatissimo", "accent": "articAccent",
         "marcato": "articMarcato", "tenuto": "articTenuto", "fermata": "fermata"}
UNNAMED = {"text", "dynamicOther", "ornamentOther"}
# drawn at any length: anchored at the box's bottom left, at full size
STRETCHED = {"arpeggio", "trillLine", "wavyGlissando", "brace", "bracketEnd"}
# the classes that change notes: their doubts go into the flag file
NOTE_CLASSES = set(rl.NOTEHEADS + rl.RESTS + rl.FLAGS + rl.ACCIDENTALS[:5] + rl.CLEFS + rl.TIME + rl.TUPLETS
                   + ["augmentationDot"])

WORDS = {
    "noteheadBlack": "black notehead", "noteheadHalf": "half notehead", "noteheadWhole": "whole notehead",
    "noteheadDoubleWhole": "double whole notehead", "noteheadX": "cross notehead", "noteheadSlash": "slash",
    "restDoubleWhole": "double whole rest", "restWhole": "whole rest", "restHalf": "half rest",
    "restQuarter": "quarter rest", "rest8th": "eighth rest", "rest16th": "sixteenth rest",
    "rest32nd": "32nd rest", "rest64th": "64th rest", "flag8th": "eighth flag", "flag16th": "sixteenth flag",
    "flag32nd": "32nd flag", "flag64th": "64th flag", "accidentalSharp": "sharp", "accidentalFlat": "flat",
    "accidentalNatural": "natural", "accidentalDoubleSharp": "double sharp", "accidentalDoubleFlat": "double flat",
    "gClef": "treble clef", "fClef": "bass clef", "cClef": "C clef", "augmentationDot": "dot",
}


def name_for(smufl_name):
    """The name a detection of this glyph's class is given, keeping the
    glyph's side or direction (for measuring anchors on vector pages), or
    None for glyphs whose detections are not anchored by a table: those with
    no class, dynamics (joined from letters in the labels) and marks drawn
    at any length."""
    cls = rl.class_of(smufl_name)
    if cls is None or cls in UNNAMED or cls in STRETCHED or cls.startswith("dynamic"):
        return None
    if cls in rl.FLAGS:
        return cls + ("Down" if smufl_name.endswith("Down") else "Up")
    if cls in SIDED:
        return SIDED[cls] + ("Below" if smufl_name.endswith("Below") else "Above")
    return NAMES.get(cls, cls)


def words(cls):
    """A detector class in plain words, for a doubt's reason."""
    if cls in WORDS:
        return WORDS[cls]
    if cls.startswith("timeSig"):
        return f"time signature {cls[7:].lower()}"
    if cls.startswith("tuplet"):
        return f"tuplet {cls[6:]}"
    if cls.startswith("dynamic"):
        return f"dynamic {cls[7:].lower()}"
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z0-9])", " ", cls).lower()


def _a(text):
    return ("an " if text[0] in "aeiou8" else "a ") + text


def settle(detections, limit=SAME_SYMBOL):
    """[(class, box, confidence, doubt)] from [(class index, box, confidence)]:
    of the boxes of different classes over one symbol, the most confident is
    kept. `doubt` is the reason in words, or None."""
    order = sorted(detections, key=lambda d: -d[2])
    kept = []   # [class, box, confidence, best rival confidence, rival class]
    for c, box, conf in order:
        cls = rl.CLASSES[c]
        rival = next((k for k in kept if k[0] != cls and rl.iou(k[1], box) >= limit), None)
        if rival is not None:
            if rival[3] is None:
                rival[3], rival[4] = conf, cls
            continue
        kept.append([cls, tuple(box), conf, None, None])
    out = []
    for cls, box, conf, other, other_cls in kept:
        doubt = None
        if other is not None and conf - other <= CLOSE:
            doubt = f"{_a(words(cls))} or {_a(words(other_cls))}"
        elif conf < UNSURE:
            doubt = f"perhaps {_a(words(cls))} ({round(100 * conf)} percent sure)"
        out.append((cls, box, conf, doubt))
    return out


@functools.cache
def anchors():
    """The measured anchors by name (scripts/measure_anchors.py)."""
    return json.loads(ANCHORS.read_text(encoding="utf-8"))


def anchor(name, box, space):
    """(x, y) of a glyph's origin in its ink box: where the vector reader
    finds it in fonts of that height (anchors.json), else where it lies in
    the Bravura reference glyph's box, else the bottom left."""
    x0, y0, x1, y1 = box
    measured = anchors().get(name)
    if measured is not None:
        height = (y1 - y0) / space if space > 0 else measured["middle"]
        share = measured["at"] + measured["slope"] * (height - measured["middle"])
        share = min(max(share, measured["low"]), measured["high"])
        return x0 + measured["x"] * (x1 - x0), y0 + share * (y1 - y0)
    ref = shapes.reference(name)
    if ref is None or ref.width <= 0 or ref.height <= 0:
        return x0, y1
    return x0 + (-ref.left / ref.width) * (x1 - x0), y0 + (-ref.top / ref.height) * (y1 - y0)


def full_height(name):
    """The ink height of a glyph at full size in staff spaces, in the font
    that draws it smallest (anchors.json), or the Bravura reference's."""
    measured = anchors().get(name)
    if measured is not None:
        return measured["full"]
    ref = shapes.reference(name)
    return ref.height if ref is not None else None


def size_of(name, box, space, typical=None):
    """The em in points: four staff spaces, less for a glyph clearly smaller
    than full size (a grace note, a clef change). Full size is the name's
    usual box height on the page (`typical`, in points), where there are
    enough of them and it is not itself small, since the detector's boxes
    are padded and fonts differ; else the font table's height."""
    full = full_height(name)
    if not full or space <= 0:
        return 4 * space
    full *= space
    if typical and typical >= FULL_SIZE * full:
        full = typical
    share = (box[3] - box[1]) / full
    return 4 * space if share >= FULL_SIZE else 4 * space * share


def typical_heights(found):
    """{name: median box height} for names with at least TYPICAL_COUNT
    detections on the page."""
    heights = {}
    for name, box in found:
        heights.setdefault(name, []).append(box[3] - box[1])
    return {name: statistics.median(h) for name, h in heights.items() if len(h) >= TYPICAL_COUNT}


def make(cls, name, box, conf, doubt, space, typical=None):
    """A Symbol for one detection, in page points."""
    x, y = (box[0], box[3]) if cls in STRETCHED else anchor(name, box, space)
    size = 4 * space if cls in STRETCHED else size_of(name, box, space, (typical or {}).get(name))
    rule = None
    if doubt:
        rule = ("unsure symbol" if cls in NOTE_CLASSES else "unsure marking", doubt)
    return Symbol(name, x, y, size, tuple(box), SOURCE, SOURCE, conf, rule)


def _centre(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _side(box, heads, space):
    """"Above" if the mark is above the nearest notehead in its column (or
    there is none), else "Below"."""
    cx, cy = _centre(box)
    near = [h for h in heads if abs(_centre(h)[0] - cx) <= 1.5 * space]
    if not near:
        return "Above"
    head = min(near, key=lambda h: abs(_centre(h)[1] - cy))
    return "Above" if cy < _centre(head)[1] else "Below"


def to_symbols(detections, space):
    """(symbols, text regions, masked boxes) for a page from its detections
    [(class index, box, confidence)], boxes in page points; `space` is the
    page's staff space in points. Flags are made up; `set_flag_directions`
    turns them once the stems are known."""
    found = settle(detections)
    heads = [box for cls, box, _, _ in found if cls in rl.NOTEHEADS]
    symbols, text, masked = [], [], []
    brackets = []
    typical = typical_heights((NAMES.get(cls, cls), box) for cls, box, _, _ in found)
    for cls, box, conf, doubt in found:
        if cls == "text":
            text.append(box)
            continue
        if cls in UNNAMED:
            masked.append(box)
            continue
        if cls in SIDED:
            name = SIDED[cls] + _side(box, heads, space)
        elif cls in rl.FLAGS:
            name = cls + "Up"
        elif cls == "bracketEnd":
            brackets.append((box, conf, doubt))
            continue
        else:
            name = NAMES.get(cls, cls)
        symbols.append(make(cls, name, box, conf, doubt, space, typical))
    symbols += _bracket_ends(brackets, space)
    return symbols, text, masked


def _bracket_ends(brackets, space):
    """Bracket ends: of those in one column the upper is the top, the lower
    the bottom; one alone is a top."""
    out, used = [], set()
    for i, (box, conf, doubt) in enumerate(brackets):
        if i in used:
            continue
        column = [j for j, (b, _, _) in enumerate(brackets)
                  if j not in used and abs(b[0] - box[0]) <= space]
        column.sort(key=lambda j: brackets[j][0][1])
        used.update(column)
        for k, j in enumerate(column):
            b, c, d = brackets[j]
            name = "bracketBottom" if k == len(column) - 1 and len(column) > 1 else "bracketTop"
            out.append(make("bracketEnd", name, b, c, d, space))
    return out


CLEF_NAMES = {NAMES.get(c, c) for c in rl.CLEFS}


def snap_clefs(symbols, level, space):
    """Put each clef's origin on the staff line nearest it, within half a
    staff space: a clef always sits on a line, and fonts differ by up to a
    quarter of a staff space in where the line lies in the clef's box, which
    is half a step. `level` holds the level lines (y, x0, x1, thickness);
    only those at least four staff spaces long, staff lines, count."""
    lines = [l for l in level if l[2] - l[1] >= 4 * space]
    for s in symbols:
        if s.source != SOURCE or s.name not in CLEF_NAMES:
            continue
        near = [l[0] for l in lines if l[1] - space <= s.x <= l[2] and abs(l[0] - s.y) <= 0.5 * space]
        if near:
            s.y = min(near, key=lambda y: abs(y - s.y))


MET_NOTES = {"noteheadBlack": "metNoteQuarterUp", "noteheadHalf": "metNoteHalfUp", "noteheadWhole": "metNoteWhole"}


def metronome_notes(symbols, text, level, space):
    """Name the notes of metronome marks, which the detector finds as
    noteheads: a notehead at least two staff spaces from every staff line
    (a level line at least four staff spaces long) with a text region
    starting within 2.5 staff spaces of its right edge, at its height. The
    reader then leaves them out of the music, and its text stage reads the
    mark (omr.pdf.text, which takes the same distance)."""
    lines = [l for l in level if l[2] - l[1] >= 4 * space]
    for s in symbols:
        if s.source != SOURCE or s.name not in MET_NOTES:
            continue
        cx, cy = _centre(s.box)
        if any(l[1] <= cx <= l[2] and abs(l[0] - cy) < 2 * space for l in lines):
            continue
        if any(abs(t[0] - s.box[2]) < 2.5 * space and s.box[1] - space <= (t[1] + t[3]) / 2 <= s.box[3] + space
               for t in text):
            s.name = MET_NOTES[s.name]


def set_flag_directions(symbols, verticals, space):
    """Turn each flag down where it hangs below the notes of its stem. The
    stem is a vertical line (x, top, bottom, width) within 0.6 staff spaces
    of the flag's left edge that reaches into the flag's height; its notes
    are the noteheads beside it (within 1.5 staff spaces across) along its
    length. A flag whose middle is below theirs is down, and its origin
    moves to the stem's lower end. With no stem or notes it stays up."""
    heads = [_centre(s.box) for s in symbols if s.source == SOURCE and s.name.startswith("notehead")]
    for k, s in enumerate(symbols):
        cls = s.name[:-2]
        if s.source != SOURCE or not s.name.endswith("Up") or cls not in rl.FLAGS:
            continue
        x0, y0, _, y1 = s.box
        stems = [v for v in verticals if abs(v[0] - x0) <= 0.6 * space and v[1] < y1 and v[2] > y0]
        ys = [hy for v in stems for hx, hy in heads
              if abs(hx - v[0]) <= 1.5 * space and v[1] - space <= hy <= v[2] + space]
        if ys and (y0 + y1) / 2 > sum(ys) / len(ys):
            symbols[k] = make(cls, cls + "Down", s.box, s.confidence, s.doubt[1] if s.doubt else None, space)
