"""Music symbols on a vector PDF page (Stage 1.1). Every glyph of a music
font is named with a SMuFL name: by its code point in a SMuFL font, and by a
mapping table for Emmentaler, Opus, Helsinki and Maestro. A font renamed by a
printer driver ("TTE26B52B8t00") is identified by its glyph shapes. On a Type B
page, symbols drawn as outlines are named by matching their shapes. Glyphs
that cannot be named are counted per font. Text fonts give text runs.

The rules are in docs/notes/symbol-spec.md.
"""

import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from omr.pdf import evidence, fonttables, geometry, shapes, smufl

RENAMED = re.compile(r"^TT[0-9A-F]+t00$|^T3Font|^F\d+$")


@dataclass
class Symbol:
    """One music symbol. (x, y) is its origin as the page is shown, which is
    where SMuFL anchors the symbol (a notehead's centre line, a clef's line).
    `size` is the em in points: four staff spaces for a music font at its
    design size. `box` is the ink (x0, y0, x1, y1). A symbol read from a
    page image (omr.raster.names) has the detector's `confidence`, and a
    `doubt` (rule, reason) when the detector was unsure of it."""

    name: str
    x: float
    y: float
    size: float
    box: tuple
    font: str
    source: str     # "smufl", "emmentaler", "sonata", "sonata-special", "outline" or "detector"
    confidence: float | None = None
    doubt: tuple | None = None


@dataclass
class TextRun:
    text: str
    x: float          # origin of the first character
    y: float
    box: tuple
    font: str
    size: float
    breaks: list = field(default_factory=list)   # (index in text, x, gap before it) where a new span of the PDF starts


@dataclass
class FontMapping:
    """How one font's glyphs are named."""

    font: str
    table: str | None           # "smufl", "emmentaler", "sonata", "sonata-special", or None (text)
    how: str                    # "codes", "name", "glyph names" or "shapes"
    score: float | None = None  # share of glyph uses whose shape fits the table (shapes only)
    program: str | None = None  # "Sibelius" or "Finale", for a legacy font


@dataclass
class PageSymbols:
    page: int
    evidence: object
    symbols: list = field(default_factory=list)
    text: list = field(default_factory=list)
    unmapped: Counter = field(default_factory=Counter)   # (font, description) -> uses
    unnamed: list = field(default_factory=list)          # ink boxes of outlined shapes not matched
    fonts: dict = field(default_factory=dict)            # font name -> FontMapping
    text_regions: list = field(default_factory=list)     # boxes of text found in a page image, not yet read
    masked: list = field(default_factory=list)           # boxes of other ink in a page image the reader is not given

    @property
    def staff_space(self):
        return self.evidence.staves.staff_space_pt


# ------------------------------------------------------------ font programs

class FontPrograms:
    """The embedded font programs of one document, by xref, with their glyph
    names, cached across pages."""

    def __init__(self, doc):
        self.doc = doc
        self._buffers = {}
        self._names = {}
        self.shapes = {}    # (xref, gid): the glyph drawn by _ink_boxes, or None

    def buffer(self, xref):
        if xref not in self._buffers:
            try:
                self._buffers[xref] = self.doc.extract_font(xref)[3] or None
            except Exception:   # PyMuPDF raises plain exceptions
                self._buffers[xref] = None
        return self._buffers[xref]

    def glyph_names(self, xref):
        """The glyph names by glyph id (CFF or TrueType), or None."""
        if xref not in self._names:
            self._names[xref] = _glyph_names(self.buffer(xref))
        return self._names[xref]


def _glyph_names(buffer):
    if not buffer:
        return None
    try:
        if buffer[:4] in (b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf"):
            from fontTools.ttLib import TTFont
            return TTFont(io.BytesIO(buffer)).getGlyphOrder()
        if buffer[:1] == b"\x01":    # bare CFF
            from fontTools.cffLib import CFFFontSet
            cff = CFFFontSet()
            cff.decompile(io.BytesIO(buffer), None)
            return list(cff[cff.fontNames[0]].charset)
    except Exception:   # a damaged or unusual font program
        return None
    return None


def font_xrefs(page):
    """{font name as the text layer gives it: [xrefs]} for the page."""
    out = defaultdict(list)
    for xref, _, font_type, basefont, *_ in evidence.page_fonts(page):
        if xref and font_type != "Type3":
            out[evidence.strip_subset_prefix(basefont)].append(xref)
    return out


def _xref_for(xrefs_by_name, name):
    """The font program of a text-layer font name: an exact match, else the
    only one whose name starts with it (as evidence._font_buffer does)."""
    if name in xrefs_by_name:
        return xrefs_by_name[name][0]
    squashed = evidence.squash(name)
    matches = [x for base, xs in xrefs_by_name.items() if evidence.squash(base).startswith(squashed) for x in xs]
    return matches[0] if len(matches) == 1 else None


# ------------------------------------------------------- identifying a font

FIT = 0.6           # similarity at which a glyph fits the table's symbol
IDENTIFIED = 0.5    # share of glyph uses that must fit for a table to be chosen
EMMENTALER_PREFIXES = ("noteheads.", "clefs.", "accidentals.", "rests.", "flags.", "scripts.", "brace")


def identify_by_shapes(buffer, uses):
    """Which Sonata table fits a renamed font best. `uses` is {(code, gid): n}.
    Each glyph used is drawn and compared with the Bravura symbol the table
    names for its byte; a glyph fits if it reaches FIT and its size fits.
    Returns (table name, score) for the best table, or (None, best score)."""
    keyed = [(fonttables.sonata_byte(code), gid, n) for (code, gid), n in uses.items()]
    keyed = [(b, gid, n) for b, gid, n in keyed if b is not None and b != 0x20]
    total = sum(n for _, _, n in keyed)
    if not total or not buffer:
        return None, 0.0
    try:
        drawn = dict(zip([gid for _, gid, _ in keyed], shapes.draw_font_glyphs(buffer, [gid for _, gid, _ in keyed])))
    except Exception:   # a font PyMuPDF cannot embed again
        return None, 0.0
    best = (None, 0.0)
    for table_name, table in (("sonata", fonttables.SONATA), ("sonata-special", fonttables.SONATA_SPECIAL)):
        fitting = 0
        for b, gid, n in keyed:
            shape = drawn.get(gid)
            if shape is not None and table.get(b) in smufl.codes_by_name() \
                    and shapes.best_fit(shape, table[b])[0] >= FIT:
                fitting += n
        score = fitting / total
        if score > best[1]:
            best = (table_name, score)
    return best if best[1] >= IDENTIFIED else (None, best[1])


class FontIdentifier:
    """Decides, once per document, how each music font's glyphs are named."""

    def __init__(self, programs):
        self.programs = programs
        self.known = {}

    def mapping(self, use, xref, page_fonts):
        if use.name in self.known:
            return self.known[use.name]
        mapping = self._decide(use, xref, page_fonts)
        if mapping.how != "shapes" or mapping.table is not None:
            self.known[use.name] = mapping
        return mapping

    def _decide(self, use, xref, page_fonts):
        if use.cls in ("smufl", "smufl_text"):
            return FontMapping(use.name, "smufl", "codes")
        if use.glyphs and use.smufl_glyphs == use.glyphs and not evidence.is_symbol_font(use):
            # a few glyphs, all SMuFL code points: too few for the inspector's
            # rule, but music (a page whose only Bravura glyphs are its braces)
            return FontMapping(use.name, "smufl", "codes")
        named = fonttables.legacy_table(use.name)
        if named is not None:
            table = named[0]
            program = None if table == "emmentaler" else _program(use.name)
            return FontMapping(use.name, table, "name", program=program)
        names = self.programs.glyph_names(xref) if xref else None
        if names and sum(1 for n in names if n.startswith(EMMENTALER_PREFIXES)) >= 3:
            return FontMapping(use.name, "emmentaler", "glyph names")
        if use.cls in ("legacy", "unknown_music") or RENAMED.match(use.name):
            table, score = identify_by_shapes(self.programs.buffer(xref) if xref else None, use.codes)
            return FontMapping(use.name, table, "shapes", score)
        return FontMapping(use.name, None, "codes")


def _program(name):
    """Sibelius or Finale from a legacy font's own name, or None for a renamed font."""
    squashed = evidence.squash(name)
    if squashed.startswith(("opus", "helsinki", "inkpen", "reprise", "norfolk")):
        return "Sibelius"
    if squashed.startswith(("maestro", "petrucci", "engraver", "jazz", "broadway")):
        return "Finale"
    return None


def guess_programs(mappings):
    """A renamed Sonata font is Sibelius's if a Sibelius font or a Special
    companion font is on the page, else Finale's. Only a guess: the two
    layouts agree, and the program matters only to how later stages read the
    rhythm dot."""
    sibelius = any(m.table == "sonata-special" or m.program == "Sibelius" for m in mappings)
    for m in mappings:
        if m.table in ("sonata", "sonata-special") and m.program is None:
            m.program = "Sibelius" if sibelius else "Finale"


# ---------------------------------------------------------------- the page

def name_glyph(mapping, code, glyph_name):
    """The SMuFL name of one glyph under a font mapping, or None."""
    if mapping.table == "smufl":
        return smufl.name_of(code, mapping.font)
    if mapping.table == "emmentaler":
        return fonttables.emmentaler_symbol(glyph_name, code)
    if mapping.table in ("sonata", "sonata-special"):
        table = fonttables.SONATA if mapping.table == "sonata" else fonttables.SONATA_SPECIAL
        return table.get(fonttables.sonata_byte(code))
    return None


def _is_text_glyph(mapping, code, glyph_name):
    """A glyph of a music font that is text: a letter, digit or punctuation
    mark in a SMuFL font (chord symbols and tempo marks in MuseJazz Text,
    Bravura Text), or punctuation in Emmentaler."""
    if mapping.table == "smufl":
        return 32 <= code < 0xE000
    if mapping.table == "emmentaler":
        return glyph_name in fonttables.EMMENTALER_TEXT
    return False


def _describe(code, glyph_name):
    if glyph_name and not re.fullmatch(r"glyph\d+|uni[0-9A-F]{4}|g\d+", glyph_name):
        return f"glyph {glyph_name}"
    if code == 0xFFFD or code < 32:
        return f"a glyph with no character code{f' ({glyph_name})' if glyph_name else ''}"
    return f"character U+{code:04X}"


def read_page(page, number, programs=None, identifier=None, ev=None):
    """All symbols and text on one page. Pass the same `programs` and
    `identifier` for every page of a document so fonts are identified once."""
    import pymupdf

    programs = programs or FontPrograms(page.parent)
    identifier = identifier or FontIdentifier(programs)
    ev = ev or evidence.gather(page, number)
    result = PageSymbols(number, ev)
    turn = geometry.display_turn(page)
    xrefs = font_xrefs(page)
    uses = {use.name: use for use in ev.fonts}
    mappings = {}
    for name, use in uses.items():
        xref = _xref_for(xrefs, name)
        mappings[name] = (identifier.mapping(use, xref, list(xrefs)), xref)
        result.fonts[name] = mappings[name][0]
    guess_programs(result.fonts.values())
    ink = _ink_boxes(programs, page, mappings)
    run = None
    for span in evidence.page_texttrace(page):
        if span.get("type") == 3 or span.get("opacity", 1.0) == 0:
            continue
        name = evidence.strip_subset_prefix(span["font"])
        mapping, xref = mappings.get(name, (None, None))
        size = span["size"]
        is_music = mapping is not None and mapping.table is not None
        names = programs.glyph_names(xref) if (is_music and xref) else None
        new_span = True
        for code, gid, origin, bbox in span["chars"]:
            if turn is not None:
                origin = tuple(pymupdf.Point(origin) * turn)
                bbox = tuple(pymupdf.Rect(bbox) * turn)
            if not is_music:
                run = _add_text(result.text, run, name, size, code, origin, bbox, new_span)
                new_span = False
                continue
            run = None
            if code == 32:
                continue
            glyph_name = names[gid] if names and gid < len(names) else None
            if _is_text_glyph(mapping, code, glyph_name):
                text_code = ord(fonttables.EMMENTALER_TEXT.get(glyph_name, chr(code))) if code == 0xFFFD else code
                run = _add_text(result.text, run, name, size, text_code, origin, bbox, new_span)
                new_span = False
                continue
            symbol = name_glyph(mapping, code, glyph_name)
            if symbol is None:
                result.unmapped[(name, _describe(code, glyph_name))] += 1
                continue
            y = origin[1]
            if symbol == "restWhole" and mapping.table == "sonata":
                y -= size / 4   # a Sonata whole rest's origin is the line below the one it hangs from
            box = ink.get((xref, gid))
            if box is not None:
                box = _placed_box(box, origin, size / 4, span["dir"] if turn is None else (1.0, 0.0))
            else:
                box = tuple(bbox)
            result.symbols.append(Symbol(symbol, origin[0], y, size, box, name, mapping.table))
    if outlined_page(ev):
        result.symbols.extend(outline_symbols(page, ev, result.unmapped, result.unnamed))
    else:
        result.symbols.extend(outline_braces(page, ev))
    braces = [s.box for s in result.symbols if s.name == "brace"]
    result.symbols.extend(b for b in brace_halves(page, ev)
                          if not any(_boxes_overlap(b.box, other) for other in braces))
    return result


def _curve_box(items):
    """The ink box of a path, from points along its curves (a curve's control
    points can lie far outside its ink)."""
    points = []
    for item in items:
        if item[0] == "c":
            p0, p1, p2, p3 = item[1:]
            for k in range(11):
                t = k / 10
                u = 1 - t
                points.append((u ** 3 * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t ** 3 * p3.x,
                               u ** 3 * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t ** 3 * p3.y))
        else:
            points.extend(geometry.item_points(item))
    return geometry.bbox(points)


def _boxes_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def brace_halves(page, ev):
    """Braces drawn as two halves (Verovio does this): two narrow curved
    shapes, one above the other, meeting at the brace's point, with the same
    left and right edges. Each half alone looks like a tie, so the shape
    tests above skip it."""
    space = ev.staves.staff_space_pt
    if not space:
        return []
    halves = []
    for d in evidence.shown_drawings(page):
        items = d["items"]
        if "f" not in d["type"] or not items or any(item[0] != "c" for item in items) or len(items) > 4:
            continue
        x0, y0, x1, y1 = _curve_box(items)
        if y1 - y0 > 1.5 * space and x1 - x0 < (y1 - y0) / 3:
            halves.append((x0, y0, x1, y1))
    halves.sort(key=lambda b: (b[1], b[0]))
    found, used = [], set()
    for i, upper in enumerate(halves):
        if i in used:
            continue
        for j in range(i + 1, len(halves)):
            lower = halves[j]
            if j in used or abs(lower[1] - upper[3]) > 0.1 * space:
                continue
            same_edges = abs(lower[0] - upper[0]) < 0.2 * space and abs(lower[2] - upper[2]) < 0.2 * space
            if same_edges and abs((lower[3] - lower[1]) - (upper[3] - upper[1])) < 0.2 * space:
                used.update((i, j))
                box = (upper[0], upper[1], upper[2], lower[3])
                found.append(Symbol("brace", box[0], box[3], 4 * space, box, "outlines", "outline"))
                break
    return found


def outline_braces(page, ev):
    """Braces drawn as outlines on a page whose other symbols are font
    glyphs (MuseScore 3 does this): tall, narrow curved filled shapes that
    match the brace."""
    space = ev.staves.staff_space_pt
    if not space:
        return []
    found = []
    for d in evidence.shown_drawings(page):
        if "f" not in d["type"] or not any(item[0] == "c" for item in d["items"]):
            continue
        r = d["rect"]
        w, h = r.width / space, r.height / space
        if not (h > 3 and w < h / 6):
            continue
        match = _match_outline(shapes.draw_paths([d], space), w, h)
        if match and match[0] == "brace":
            found.append(Symbol("brace", r.x0, r.y1, 4 * space, (r.x0, r.y0, r.x1, r.y1), "outlines", "outline"))
    return found


def outlined_page(ev):
    """The music is drawn as outlines: more repeated outlined shapes than
    music-font glyphs (the inspector's Type B rule), or staves with almost no
    music glyphs."""
    glyphs = ev.music_glyphs
    return ev.repeated_shapes > glyphs or (ev.staves.five_line >= 1 and glyphs < 3 and ev.outlined["count"] > 0)


def _add_text(runs, run, font, size, code, origin, bbox, new_span=False):
    """Add a character to the current run, or start a new one when the font,
    size or line changes or there is a gap of more than half an em. Where a
    new span of the PDF joins the run, the place is kept in `breaks` (lyric
    syllables are separate spans set close together)."""
    char = chr(code) if code not in (0xFFFD,) and code >= 32 else ""
    if run is not None and run.font == font and abs(run.size - size) < 0.01 and abs(run.y - origin[1]) < 0.3 * size \
            and origin[0] - run.box[2] < 0.5 * size and origin[0] >= run.box[0]:
        if new_span and char and not char.isspace():
            run.breaks.append((len(run.text), origin[0], origin[0] - run.box[2]))
        run.text += char
        run.box = (min(run.box[0], bbox[0]), min(run.box[1], bbox[1]), max(run.box[2], bbox[2]), max(run.box[3], bbox[3]))
        return run
    if char.isspace() or not char:
        return None
    run = TextRun(char, origin[0], origin[1], tuple(bbox), font, size)
    runs.append(run)
    return run


def _placed_box(shape, origin, scale, direction):
    """The page box of a glyph's ink box, for a glyph drawn at `origin` with
    its baseline along `direction` (MuseScore draws arpeggios upright and
    slanted trill and glissando lines turned)."""
    dx, dy = direction
    corners = [(shape.left + u * shape.width, shape.top + v * shape.height) for u in (0, 1) for v in (0, 1)]
    xs = [origin[0] + (a * dx - b * dy) * scale for a, b in corners]
    ys = [origin[1] + (a * dy + b * dx) * scale for a, b in corners]
    return (min(xs), min(ys), max(xs), max(ys))


def _ink_boxes(programs, page, mappings):
    """{(xref, gid): Shape} for every music glyph on the page, drawn once."""
    wanted = defaultdict(set)
    for span in evidence.page_texttrace(page):
        mapping, xref = mappings.get(evidence.strip_subset_prefix(span["font"]), (None, None))
        if mapping is not None and mapping.table is not None and xref:
            wanted[xref].update(gid for _, gid, _, _ in span["chars"])
    boxes = {}
    for xref, gids in wanted.items():
        cached = programs.shapes
        todo = sorted(g for g in gids if (xref, g) not in cached)
        buffer = programs.buffer(xref)
        if todo and buffer:
            try:
                for gid, shape in zip(todo, shapes.draw_font_glyphs(buffer, todo)):
                    cached[(xref, gid)] = shape if shape.image is not None else None
            except Exception:   # a font PyMuPDF cannot embed again
                cached.update({(xref, g): None for g in todo})
        boxes.update({(xref, g): cached.get((xref, g)) for g in gids if cached.get((xref, g)) is not None})
    return boxes


# -------------------------------------------------------- outlined symbols

# The symbols an outlined page is matched against: the ones that carry the
# music. Others are counted as unmapped shapes. Where two SMuFL glyphs have
# the same shape (an accent above or below the note) only one is listed, and
# the later stages place it by position. A staccatissimo wedge is named as
# the plain staccatissimo it means.
OUTLINE_CANDIDATES = (
    "noteheadBlack", "noteheadHalf", "noteheadWhole", "noteheadDoubleWhole",
    "noteheadSlashHorizontalEnds", "noteheadSlashWhiteHalf", "noteheadSlashWhiteWhole",   # rhythm slashes
    "noteheadXBlack", "noteheadCircleX", "noteheadDiamondBlack",                          # drums and harmonics
    "restWhole", "restHalf", "restQuarter", "rest8th", "rest16th", "rest32nd", "rest64th",
    "accidentalSharp", "accidentalFlat", "accidentalNatural", "accidentalDoubleSharp", "accidentalDoubleFlat",
    "gClef", "fClef", "cClef", "gClef8vb", "unpitchedPercussionClef1",
    "flag8thUp", "flag8thDown", "flag16thUp", "flag16thDown", "flag32ndUp", "flag32ndDown",
    "augmentationDot", "timeSigCommon", "timeSigCutCommon",
    *(f"timeSig{i}" for i in range(10)), *(f"tuplet{i}" for i in range(10)),
    "dynamicPiano", "dynamicForte", "dynamicMezzo", "dynamicSforzando", "dynamicZ", "dynamicRinforzando",
    "dynamicMP", "dynamicMF", "dynamicPP", "dynamicFF", "dynamicPPP", "dynamicFFF", "dynamicFortePiano",
    "dynamicSforzato", "dynamicForzando",
    "articAccentAbove", "articStaccatissimoAbove", "articStaccatissimoBelow",
    "articStaccatissimoWedgeAbove", "articStaccatissimoWedgeBelow", "articMarcatoAbove", "articMarcatoBelow",
    "fermataAbove", "fermataBelow", "ornamentTrill", "ornamentTurn", "ornamentMordent", "ornamentShortTrill",
    "breathMarkComma", "segno", "coda", "brace", "bracketTop", "bracketBottom", "keyboardPedalPed",
    "keyboardPedalUp", "stringsUpBow", "stringsDownBow", "wiggleTrill", "wiggleArpeggiatoUp", "tremolo1",
)
OUTLINE_MATCH = 0.75    # similarity needed to name an outlined shape
MAX_SYMBOL_SPACES = 8   # larger shapes (slurs, ties, beams) are not symbols


def outline_symbols(page, ev, unmapped, unnamed=None):
    """Name the filled vector shapes of the page that look like music symbols.
    Identical shapes (the same fingerprint) are matched once. Three kinds of
    shape get their own tests, because a plain shape match cannot name them:
    a small level rectangle on a staff line (a whole or half rest drawn
    without curves), a tall narrow shape (a brace, drawn at the height of
    the staves it joins), and a vertical wiggle (an arpeggio, which SMuFL
    draws level and engravers turn upright). The ink boxes of shapes that
    look like symbols but match none are added to `unnamed`."""
    space = ev.staves.staff_space_pt
    if not space:
        return []
    found, cache = [], {}
    for d in evidence.shown_drawings(page):
        if "f" not in d["type"] or not d["items"]:
            continue
        items = d["items"]
        kinds = [item[0] for item in items]
        points = [p for item in items for p in geometry.item_points(item)]
        x0, y0, x1, y1 = geometry.bbox(points)
        w, h = (x1 - x0) / space, (y1 - y0) / space
        if w <= 0 or h <= 0:
            continue
        if "c" not in kinds:
            if _level_rectangle(points) and 0.8 <= w <= 1.7 and 0.3 <= h <= 0.75:
                name = _whole_or_half(ev.staves, y0, y1, space)
                if name:   # a rest drawn as a plain rectangle
                    found.append(Symbol(name, x0, y0 if name == "restWhole" else y1, 4 * space,
                                        (x0, y0, x1, y1), "outlines", "outline"))
            if _rhythm_slash(points, w, h):   # a slash notehead drawn as a slanted four-sided piece
                found.append(Symbol("noteheadSlashHorizontalEnds", x0, (y0 + y1) / 2, 4 * space,
                                    (x0, y0, x1, y1), "outlines", "outline"))
                continue
            if len(items) <= 4:
                continue   # rectangles and four-sided pieces: stems, barlines, beams
        if set(kinds) == {"c"} and len(kinds) <= 3:
            continue   # a crescent of two or three curves: a tie or a short slur
        key = evidence.fingerprint(items, x0, y0, space)
        if key not in cache:
            shape = shapes.draw_paths([dict(d, items=items)], space)
            cache[key] = "slur" if _thin_band(shape, w, h) else _match_outline(shape, w, h)
        if cache[key] == "slur":
            continue   # a slur or tie: a long, thin curved band
        match = cache[key]
        if match is None:
            if "c" in kinds and w <= MAX_SYMBOL_SPACES and h <= MAX_SYMBOL_SPACES:
                unmapped[("outlines", "an outlined shape not matched")] += 1
                if unnamed is not None:
                    unnamed.append((x0, y0, x1, y1))
            continue
        name, ref = match
        if name in ("restWhole", "restHalf"):
            name = _whole_or_half(ev.staves, y0, y1, space) or name
            ref = shapes.reference(name)
        name = {"articStaccatissimoWedgeAbove": "articStaccatissimoAbove",
                "articStaccatissimoWedgeBelow": "articStaccatissimoBelow"}.get(name, name)
        if ref is None:   # anchored at the bottom left, as SMuFL anchors a brace
            x, y = x0, y1
        else:   # the origin sits in the ink box where it sits in the reference's
            x = x0 + (-ref.left / ref.width) * (x1 - x0)
            y = y0 + (-ref.top / ref.height) * (y1 - y0)
        found.append(Symbol(name, x, y, 4 * space, (x0, y0, x1, y1), "outlines", "outline"))
    return found


BRACE_MATCH = 0.6


def _match_outline(shape, w, h):
    """(name, reference Shape or None) for an outlined shape, or None."""
    if shape.image is None:
        return None
    if h > 3 and w < h / 6:   # tall and narrow: a brace (any height), else nothing
        sim = max((shapes.similarity(shape, r) for r in shapes.references("brace")), default=0.0)
        return ("brace", None) if sim >= BRACE_MATCH else None
    if w > MAX_SYMBOL_SPACES or h > MAX_SYMBOL_SPACES or w > 4 * h:
        return None
    best, best_sim = None, 0.0
    for name in OUTLINE_CANDIDATES:
        sim, ref = shapes.best_fit(shape, name)
        if sim > best_sim:
            best, best_sim = (name, ref), sim
    if h > 2 * w:   # upright: also try the level wiggles turned upright
        upright = shapes.turned(shape)
        for name in ("wiggleArpeggiatoUp", "wiggleTrill"):
            sim, ref = shapes.best_fit(upright, name)
            if sim > best_sim:
                best, best_sim = ("wiggleArpeggiatoUp", None), sim
    return best if best_sim >= OUTLINE_MATCH else None


def _thin_band(shape, w, h):
    """A long curved band with little ink for its size: a slur or a tie
    (drawn with more curves than the simple crescent test catches)."""
    if shape.image is None or w < 2.4 * h:   # a fermata is about twice as wide as tall
        return False
    return float(shape.image.mean()) < 0.25


def _rhythm_slash(points, w, h):
    """A rhythm slash: four corners, a short level edge at the top right and
    one at the bottom left, about two staff spaces wide and high (`w` and
    `h` are in staff spaces)."""
    corners = sorted(set((round(x, 1), round(y, 1)) for x, y in points))
    if len(corners) != 4 or not (1.2 <= w <= 2.6 and 1.4 <= h <= 2.6):
        return False
    top = sorted((p for p in corners if abs(p[1] - min(c[1] for c in corners)) < 0.2), key=lambda p: p[0])
    bottom = sorted((p for p in corners if abs(p[1] - max(c[1] for c in corners)) < 0.2), key=lambda p: p[0])
    if len(top) != 2 or len(bottom) != 2:
        return False
    top_edge, bottom_edge = top[1][0] - top[0][0], bottom[1][0] - bottom[0][0]
    width = max(c[0] for c in corners) - min(c[0] for c in corners)
    return top_edge < 0.5 * width and bottom_edge < 0.5 * width and top[0][0] > bottom[1][0] - 0.5 * top_edge


def _level_rectangle(points):
    """Four corners, two at each of two heights: a level rectangle."""
    ys = sorted({round(p[1], 1) for p in points})
    xs = sorted({round(p[0], 1) for p in points})
    return len(ys) == 2 and len(xs) == 2


def _whole_or_half(staves, top, bottom, space):
    """A whole rest hangs below a staff line, a half rest sits on one; the
    two are the same shape. The edge nearer a line decides. None if neither
    edge is on a line of a staff (or a ledger line next to it)."""
    for x0, x1, staff_top, staff_bottom in staves.boxes:
        if not staff_top - 2 * space <= top <= staff_bottom + 2 * space:
            continue
        lines = [staff_top + k * space for k in range(-2, 7)]
        hang = min(abs(top - line) for line in lines)
        sit = min(abs(bottom - line) for line in lines)
        if min(hang, sit) <= 0.15 * space:
            return "restWhole" if hang < sit else "restHalf"
    return None


# ------------------------------------------------------------ the document

def read_document(doc, pages=None, shown=None):
    """PageSymbols for each page (all pages, or the numbers from 1 given).
    `shown` is the document's pages already loaded, to read in place of
    loading them again."""
    programs = FontPrograms(doc)
    identifier = FontIdentifier(programs)
    numbers = pages or range(1, len(doc) + 1)
    return [read_page((shown or doc)[n - 1], n, programs, identifier) for n in numbers]
