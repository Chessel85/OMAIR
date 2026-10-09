"""Evidence gathered from one PDF page, with PyMuPDF. No OCR, and no rendering
except in `raster_measures`. The rules that use this evidence are in
`omr.pdf.classify`. See docs/notes/inspector-spec.md.
"""

import hashlib
import re
import statistics
import string
from collections import Counter
from dataclasses import dataclass, field

PUA = (0xE000, 0xF8FF)
SMUFL = (0xE000, 0xF3FF)
# A Windows "symbol" font (Sibelius's Opus and Helsinki, Finale's Maestro when
# printed) has each byte code moved up by U+F000, so its glyphs fall in this
# block, inside the SMuFL range. Such a font is an 8-bit legacy font, not SMuFL.
SYMBOL_BLOCK = (0xF020, 0xF0FF)
SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")

# Legacy music fonts, matched as a prefix of the name with case, spaces and
# hyphens ignored. Stage 8 extends this list.
LEGACY_FONTS = (
    "Emmentaler", "PFAEmmentaler", "Feta", "Feta-alphabet", "Opus", "Helsinki", "Reprise", "Inkpen2", "Norfolk",
    "Maestro", "Petrucci", "Jazz", "Engraver", "Broadway Copyist", "Sonata",
    "Tamburo", "Seville", "Toccata", "Pori", "Ash",
)
SMUFL_FAMILIES = (
    "bravura", "leland", "musejazz", "petaluma", "gootville", "gonville",
    "mscore", "emmentaler", "finale", "sebastian", "ross", "profondo", "haydn",
)


def _squash(name):
    return re.sub(r"[\s\-_]", "", name).lower()


def strip_subset_prefix(name):
    return SUBSET_PREFIX.sub("", name)


# Companion text fonts of legacy music fonts (Opus Text, Engraver Text,
# Maestro Times) are text, not music.
LEGACY_TEXT_MARKERS = ("text", "times")


def is_legacy_name(name):
    """The name starts with a listed legacy font as a whole word: the next
    character is not a lower-case letter. So "EngraverFontSet" and "Opus Std"
    match, but "Engravers MT" and "AshleyScript" do not."""
    compact = re.sub(r"[\s\-_]", "", strip_subset_prefix(name))
    squashed = compact.lower()
    if any(marker in squashed for marker in LEGACY_TEXT_MARKERS):
        return False
    for legacy in LEGACY_FONTS:
        prefix = _squash(legacy)
        if squashed.startswith(prefix):
            rest = compact[len(prefix):]
            if not rest or not rest[0].islower():
                return True
    return False


def is_symbol_font(use):
    """Most of the font's glyphs are in the Windows symbol-font block."""
    return use.symbol_glyphs >= 0.5 * use.glyphs > 0


def plain_code(code):
    """A symbol-font code moved back to the byte it stands for."""
    return code - 0xF000 if SYMBOL_BLOCK[0] <= code <= SYMBOL_BLOCK[1] else code


def is_smufl_text_name(name):
    squashed = _squash(strip_subset_prefix(name))
    return squashed.endswith("text") and any(squashed.startswith(f) for f in SMUFL_FAMILIES)


@dataclass
class FontUse:
    name: str
    font_type: str = "unknown"
    glyphs: int = 0
    pua_glyphs: int = 0
    smufl_glyphs: int = 0
    symbol_glyphs: int = 0  # in the Windows symbol-font block
    unmapped_glyphs: int = 0
    glyph_ids: set = field(default_factory=set)
    centres: list = field(default_factory=list)  # glyph centres, for the staff test
    origins: list = field(default_factory=list)  # glyph origins (on the baseline), likewise
    on_staves: int = 0  # glyphs whose origin or centre is inside a staff
    codes: Counter = field(default_factory=Counter)  # (character code, glyph id) -> uses
    letter_share: float | None = None  # share of glyphs drawn as their letter; None if not tested
    cls: str = "text"

    def to_dict(self):
        return {
            "name": self.name,
            "font_type": self.font_type,
            "class": self.cls,
            "glyphs": self.glyphs,
            "pua_glyphs": self.pua_glyphs,
            "unmapped_glyphs": self.unmapped_glyphs,
            "distinct_glyph_ids": len(self.glyph_ids),
            "glyphs_on_staves": self.on_staves,
            "letter_share": None if self.letter_share is None else round(self.letter_share, 3),
        }


@dataclass
class Staves:
    five_line: int = 0
    one_line: int = 0
    six_line: int = 0
    staff_space_pt: float | None = None
    boxes: list = field(default_factory=list)  # (x0, x1, top, bottom) of five-line staves


@dataclass
class PageEvidence:
    page: int
    width_pt: float
    height_pt: float
    rotation: int
    fonts: list
    hidden_text_glyphs: int
    lines: dict
    filled: dict
    staves: Staves
    outlined: dict
    images: list
    image_coverage: float
    raster: dict | None = None

    @property
    def music_fonts(self):
        return [f for f in self.fonts if f.cls in ("smufl", "legacy", "unknown_music")]

    @property
    def music_glyphs(self):
        return sum(f.glyphs for f in self.music_fonts)

    @property
    def repeated_shapes(self):
        return self.outlined["repeated_instances"]

    def to_dict(self):
        out = {
            "page": self.page,
            "width_pt": round(self.width_pt, 1),
            "height_pt": round(self.height_pt, 1),
            "rotation": self.rotation,
            "fonts": [f.to_dict() for f in self.fonts],
            "hidden_text_glyphs": self.hidden_text_glyphs,
            "lines": self.lines,
            "filled": self.filled,
            "staves": {
                "five_line": self.staves.five_line,
                "one_line": self.staves.one_line,
                "six_line": self.staves.six_line,
                "staff_space_pt": self.staves.staff_space_pt,
            },
            "outlined_shapes": self.outlined,
            "images": self.images,
            "image_coverage": round(self.image_coverage, 4),
        }
        if self.raster is not None:
            out["raster_measures"] = self.raster
        return out


# ---------------------------------------------------------------- text glyphs

def _display_turn(page):
    """The matrix that turns the page's stored coordinates into the way it is
    shown, or None if it is not rotated. A landscape score is often stored as
    a portrait page with a rotation, so its staff lines are vertical as stored."""
    return page.rotation_matrix if page.rotation % 360 else None


def read_text_glyphs(page):
    """Return (fonts by name, hidden glyph count). Invisible text is counted apart.
    Positions are as the page is shown."""
    import pymupdf

    turn = _display_turn(page)
    font_types = {}
    for entry in page.get_fonts(full=True):
        font_types[strip_subset_prefix(entry[3])] = entry[2]
    fonts = {}
    hidden = 0
    for span in page.get_texttrace():
        count = len(span["chars"])
        if span.get("type") == 3 or span.get("opacity", 1.0) == 0:
            hidden += count
            continue
        name = strip_subset_prefix(span["font"])
        use = fonts.get(name)
        if use is None:
            use = fonts[name] = FontUse(name, font_types.get(name, "unknown"))
        for code, glyph_id, origin, bbox in span["chars"]:
            if turn is not None:
                origin = tuple(pymupdf.Point(origin) * turn)
                bbox = tuple(pymupdf.Rect(bbox) * turn)
            use.glyphs += 1
            use.glyph_ids.add(glyph_id)
            use.codes[(code, glyph_id)] += 1
            if PUA[0] <= code <= PUA[1]:
                use.pua_glyphs += 1
            if SMUFL[0] <= code <= SMUFL[1]:
                use.smufl_glyphs += 1
            if SYMBOL_BLOCK[0] <= code <= SYMBOL_BLOCK[1]:
                use.symbol_glyphs += 1
            if code == 0xFFFD or code < 32:
                use.unmapped_glyphs += 1
            use.centres.append(((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2))
            use.origins.append((origin[0], origin[1]))
    return fonts, hidden


# An unknown font is probably music when at least this share of its glyphs
# (and at least 10 glyphs) sit on staves. Measured on about 4,150 pages with
# real music fonts: at one half, 11 percent of pages fail; at one quarter, 1 of
# 445 files is missed. Text fonts stay far below it. Stage 8 re-measures this
# on the legacy fonts found in real files.
STAFF_SHARE = 0.25
MIN_ON_STAVES = 10


def classify_fonts(fonts, staves, page=None):
    """Put each font into one class (spec, 'Music font identification').
    With the page, a font not known by its codes or name that has many glyphs
    on staves is also tested for letter shapes, and a font drawn as letters is
    text wherever it sits."""
    boxes = _plausible_boxes(staves)
    for use in fonts.values():
        use.on_staves = _glyphs_on_staves(use, boxes)
        if is_smufl_text_name(use.name):
            use.cls = "smufl_text"
        elif use.glyphs >= 5 and use.pua_glyphs >= 0.8 * use.glyphs and (
            use.smufl_glyphs >= 0.1 * use.glyphs or use.smufl_glyphs >= 10
        ) and not is_symbol_font(use):
            use.cls = "smufl"
        elif is_legacy_name(use.name):
            use.cls = "legacy"
        else:
            if page is not None and use.on_staves >= MIN_ON_STAVES:
                use.letter_share = letter_share(page, use)
            on_staves = use.on_staves >= MIN_ON_STAVES and use.on_staves >= STAFF_SHARE * use.glyphs
            use.cls = "unknown_music" if on_staves and not looks_like_letters(use) else "text"


# ------------------------------------------------------------ letter shapes
#
# A text font that sits on staves (dynamics and tempo words, tuplet numbers on
# a dense page) passes the position test. Its glyphs are drawn as the letters
# their character codes name, which a music font's are not: a legacy 8-bit
# music font puts a quarter note on "q" and a clef on "&", and Emmentaler has
# no character codes at all. So each glyph coded as an ASCII letter or digit is
# drawn from the embedded font and compared with that character in the
# standard PDF fonts. Measured on 191 letters in 9 text fonts (Century
# Schoolbook, Edwin, FreeSerif, Liberation Serif) and 101 music glyphs: 98
# percent of letters reach 0.7, and a music glyph compared with its best of
# all 62 letters and digits reaches it about 1 time in 10 (mostly
# time-signature digits). A font is drawn as letters when at least half of its
# glyph uses, spaces aside, pass, so the noteheads of a legacy font outvote its
# few letter-like glyphs (dynamics, time-signature digits).

LETTERS = string.ascii_letters + string.digits
SHAPE_SIZE = 24
LETTER_LIKE = 0.7
LETTER_SHARE = 0.5
_REFERENCE_FONTS = ("helv", "heit", "hebo", "hebi", "tiro", "tiit", "tibo", "tibi", "cour", "coit")
_references = {}


def looks_like_letters(use):
    return use.letter_share is not None and use.letter_share >= LETTER_SHARE


def letter_share(page, use):
    """The share of the font's glyph uses (spaces aside) that are drawn as the
    ASCII letter or digit their code names. None if the font cannot be drawn
    (not embedded, or Type 3)."""
    counted = {key: n for key, n in use.codes.items() if key[0] != 32}
    total = sum(counted.values())
    if not total:
        return None
    buffer = _font_buffer(page, use.name)
    if not buffer:
        return None
    testable = [key for key in counted if plain_code(key[0]) < 128 and chr(plain_code(key[0])) in LETTERS]
    if not testable:
        return 0.0
    try:
        shapes = _draw_glyphs(buffer, [gid for _, gid in testable])
    except Exception:   # a font PyMuPDF cannot embed again
        return None
    passed = sum(counted[key] for key, shape in zip(testable, shapes)
                 if shape is not None and _letter_likeness(shape, chr(plain_code(key[0]))) >= LETTER_LIKE)
    return passed / total


def _font_buffer(page, name):
    """The embedded font file of the font the text layer calls `name`. That
    name comes from the font file, so it can differ from the PDF's name for
    the font ("Name" against "Name Book"): an exact match is used if there is
    one, otherwise the only PDF font whose name starts with it."""
    entries = [(xref, strip_subset_prefix(basefont)) for xref, _, font_type, basefont, *_
               in page.get_fonts(full=True) if xref and font_type != "Type3"]
    matches = [xref for xref, base in entries if base == name]
    if not matches:
        matches = [xref for xref, base in entries if _squash(base).startswith(_squash(name))]
    if len(matches) != 1:
        return None
    try:
        return page.parent.extract_font(matches[0])[3]
    except Exception:   # PyMuPDF raises plain exceptions
        return None


def _cells(build, count, cell=100, size=48):
    """Draw `count` glyphs, one to a cell, and return each one's normalised shape."""
    import numpy as np
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=cell * count, height=cell)
    build(doc, page, cell, size)
    pix = page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)
    grey = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return [_normalise(grey[:, i * cell:(i + 1) * cell]) for i in range(count)]


def _draw_glyphs(buffer, gids):
    """Draw glyphs by glyph id from an embedded font, which need not map
    characters to glyphs (most subset fonts do not)."""
    def build(doc, page, cell, size):
        page.insert_font(fontname="F0", fontbuffer=buffer)
        shows = " ".join(f"1 0 0 1 {i * cell + 20} {cell * 0.3} Tm <{gid:04x}> Tj" for i, gid in enumerate(gids))
        xref = doc.get_new_xref()
        doc.update_object(xref, "<<>>")
        doc.update_stream(xref, f"BT /F0 {size} Tf {shows} ET".encode())
        doc.xref_set_key(page.xref, "Contents", f"{xref} 0 R")
    return _cells(build, len(gids))


def _letter_likeness(shape, char):
    if char not in _references:
        def build(doc, page, cell, size):
            for i, font in enumerate(_REFERENCE_FONTS):
                page.insert_text((i * cell + 20, cell * 0.7), char, fontname=font, fontsize=size)
        _references[char] = [r for r in _cells(build, len(_REFERENCE_FONTS)) if r is not None]
    return max((_correlation(shape, r) for r in _references[char]), default=0.0)


def _normalise(cell):
    """The ink, cropped, centred in a square (so the proportions count) and
    scaled to SHAPE_SIZE pixels a side. None if there is no ink."""
    import cv2
    import numpy as np

    ink = 255 - cell.astype(np.float32)
    ys, xs = np.nonzero(ink > 64)
    if len(xs) == 0:
        return None
    crop = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    side = max(h, w)
    square = np.zeros((side, side), np.float32)
    square[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = crop
    return cv2.resize(square, (SHAPE_SIZE, SHAPE_SIZE), interpolation=cv2.INTER_AREA) / 255


def _correlation(a, b):
    import numpy as np

    a, b = a - a.mean(), b - b.mean()
    scale = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / scale) if scale else 0.0


def _plausible_boxes(staves):
    """Five-line staves are four staff spaces tall. A box far from that is
    probably five evenly spaced text rules (such as "cresc." lines), not a staff."""
    space = staves.staff_space_pt
    if not space:
        return list(staves.boxes)
    return [b for b in staves.boxes if abs((b[3] - b[2]) - 4 * space) <= 0.25 * 4 * space]


def _inside(boxes, x, y):
    return any(x0 <= x <= x1 and top <= y <= bottom for x0, x1, top, bottom in boxes)


def _glyphs_on_staves(use, boxes):
    """Count glyphs whose centre or origin is between the top and bottom lines
    of a staff (no margin, so fingerings and lyrics do not count). The centre
    alone is unreliable: the PDF library gives every glyph the font's full
    ascender-to-descender box, so the centre can sit most of a staff space from
    the ink. Legacy fonts put the baseline at the staff position, so the origin
    is checked too. The character is not tested: legacy 8-bit music fonts put
    symbols on letters and punctuation."""
    return sum(
        1
        for centre, origin in zip(use.centres, use.origins)
        if _inside(boxes, *centre) or _inside(boxes, *origin)
    )


# ---------------------------------------------------------- vector shapes

def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _item_points(item):
    kind = item[0]
    if kind == "re":
        r = item[1]
        return [(r.x0, r.y0), (r.x1, r.y1)]
    if kind == "qu":
        q = item[1]
        return [(p.x, p.y) for p in (q.ul, q.ur, q.lr, q.ll)]
    return [(p.x, p.y) for p in item[1:]]


def read_drawings(page):
    """Count lines and filled shapes, and collect horizontal-line candidates
    and curved filled shapes for the staff and outline tests. Positions are
    as the page is shown."""
    turn = _display_turn(page)
    lines = {"horizontal": 0, "vertical": 0, "other": 0}
    filled = {"rectangles": 0, "polygons": 0, "curved": 0}
    candidates = []  # (y, x0, x1, thickness)
    curved_shapes = []  # list of item lists
    for d in page.get_drawings():
        kind = d["type"]
        items = d["items"]
        if turn is not None:
            items = [(item[0], *(part * turn if hasattr(part, "transform") else part for part in item[1:]))
                     for item in items]
            d = dict(d, rect=d["rect"] * turn)
        width = d.get("width") or 0.0
        if "s" in kind:
            for item in items:
                if item[0] != "l":
                    continue
                p1, p2 = item[1], item[2]
                dy, dx = abs(p1.y - p2.y), abs(p1.x - p2.x)
                if dy < 0.2:
                    lines["horizontal"] += 1
                    candidates.append(((p1.y + p2.y) / 2, min(p1.x, p2.x), max(p1.x, p2.x), width))
                elif dx < 0.2:
                    lines["vertical"] += 1
                else:
                    lines["other"] += 1
        if "f" in kind:
            has_curve = any(item[0] == "c" for item in items)
            if has_curve:
                filled["curved"] += 1
                curved_shapes.append(items)
            elif all(item[0] == "re" for item in items):
                filled["rectangles"] += 1
            else:
                filled["polygons"] += 1
            if not has_curve:
                r = d["rect"]
                w, h = r.width, r.height
                if w > 0 and w >= 30 * max(h, 0.01):
                    candidates.append(((r.y0 + r.y1) / 2, r.x0, r.x1, h))
    return lines, filled, candidates, curved_shapes


MIN_STAFF_SPACES = 6   # shortest staff, in staff spaces


def find_staves(candidates, glyph_centres):
    """Find five-line staves from horizontal line candidates (spec, 'Staves')."""
    staves = Staves()
    # 2. merge pieces of one line: same y (within 0.3) and touching along x
    merged = []
    for y, x0, x1, t in sorted(candidates, key=lambda c: (c[0], c[1])):
        for m in reversed(merged[-50:]):
            if abs(m[0] - y) <= 0.3 and x0 <= m[2] + 0.5 and x1 >= m[1] - 0.5:
                # The longer piece gives the thickness, so a beam drawn exactly
                # on a staff line (Finale does this) does not make the line thick.
                if x1 - x0 > m[2] - m[1]:
                    m[3] = t
                m[1], m[2] = min(m[1], x0), max(m[2], x1)
                break
        else:
            merged.append([y, x0, x1, t])
    # 3. group lines whose x ranges overlap by 80 percent of the longer one
    groups = []
    for line in merged:
        for g in groups:
            ref = g[0]
            overlap = min(ref[2], line[2]) - max(ref[1], line[1])
            longer = max(ref[2] - ref[1], line[2] - line[1])
            if longer > 0 and overlap >= 0.8 * longer:
                g.append(line)
                break
        else:
            groups.append([line])
    gaps_seen = []
    in_run = set()
    for g in groups:
        g.sort(key=lambda c: c[0])
        i = 0
        while i + 5 <= len(g):
            run = _equal_gap_run(g, i)
            if run is None:
                i += 1
                continue
            lo, hi = i, i + run
            ys = [g[k][0] for k in range(lo, hi)]
            gap = statistics.median(b - a for a, b in zip(ys, ys[1:]))
            x0 = min(g[k][1] for k in range(lo, hi))
            x1 = max(g[k][2] for k in range(lo, hi))
            # A staff is many staff spaces long; a stack of ledger lines between
            # two staves is only two or three.
            if max(g[k][3] for k in range(lo, hi)) <= gap / 3 and gap > 0 and x1 - x0 >= MIN_STAFF_SPACES * gap:
                length = hi - lo
                if length == 6:
                    staves.six_line += 1
                elif length == 5 or length >= 10:
                    for part in range(length // 5 if length >= 10 else 1):
                        a = lo + part * 5
                        staves.five_line += 1
                        staves.boxes.append((x0, x1, g[a][0], g[a + 4][0]))
                        gaps_seen.append(gap)
                if length in (5, 6) or length >= 10:
                    in_run.update(id(g[k]) for k in range(lo, hi))
            i = hi
    # 4. one-line runs that carry glyphs (percussion)
    for g in groups:
        for line in g:
            if id(line) in in_run:
                continue
            near = sum(1 for x, y in glyph_centres
                       if line[1] <= x <= line[2] and abs(y - line[0]) < 8)
            if near >= 5:
                staves.one_line += 1
    if gaps_seen:
        staves.staff_space_pt = round(statistics.median(gaps_seen), 3)
    return staves


def _equal_gap_run(group, start):
    """Length of the run of equally spaced lines starting at `start`, or None
    if fewer than five. Gaps must be within 10 percent of the median."""
    best = None
    for length in range(5, min(len(group) - start, 12) + 1):
        ys = [group[start + k][0] for k in range(length)]
        gaps = [b - a for a, b in zip(ys, ys[1:])]
        median = statistics.median(gaps)
        if median > 0 and all(abs(g - median) <= 0.1 * median for g in gaps):
            best = length
        else:
            break
    return best


def fingerprint_outlines(curved_shapes, staff_space):
    """Count small curved filled shapes and fingerprint them (spec, 'Outlined
    shapes'). Position and scale-to-staff are removed, so identical symbols
    match wherever they are drawn."""
    prints = Counter()
    for items in curved_shapes:
        points = [p for item in items for p in _item_points(item)]
        x0, y0, x1, y1 = _bbox(points)
        w, h = x1 - x0, y1 - y0
        if w > 4 * staff_space or h > 4 * staff_space or w > 4 * h or w <= 0 or h <= 0:
            continue
        key = []
        for item in items:
            key.append(item[0])
            for px, py in _item_points(item):
                key.append(round((px - x0) / staff_space / 0.05))
                key.append(round((py - y0) / staff_space / 0.05))
        prints[hashlib.md5(repr(key).encode()).hexdigest()] += 1
    top = [n for _, n in prints.most_common(5)]
    return {
        "count": sum(prints.values()),
        "distinct": len(prints),
        "top_repeats": top,
        "repeated_instances": sum(n for n in prints.values() if n >= 5),
    }


# ------------------------------------------------------------------ images

def _union_area(rects, clip):
    """Area of the union of rectangles (x0, y0, x1, y1), clipped to `clip`."""
    cx0, cy0, cx1, cy1 = clip
    rects = [(max(a, cx0), max(b, cy0), min(c, cx1), min(d, cy1)) for a, b, c, d in rects]
    rects = [r for r in rects if r[2] > r[0] and r[3] > r[1]]
    if not rects:
        return 0.0
    xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
    area = 0.0
    for xa, xb in zip(xs, xs[1:]):
        spans = sorted((r[1], r[3]) for r in rects if r[0] <= xa and r[2] >= xb)
        covered, end = 0.0, None
        for lo, hi in spans:
            if end is None or lo > end:
                covered += hi - lo
                end = hi
            elif hi > end:
                covered += hi - end
                end = hi
        area += covered * (xb - xa)
    return area


def read_images(page):
    """Return (image list, coverage). Images under 10 percent of the page are
    listed but do not count towards coverage."""
    details = {entry[0]: entry for entry in page.get_images(full=True)}
    page_area = page.rect.width * page.rect.height
    images, big = [], []
    for info in page.get_image_info(xrefs=True):
        bbox = info["bbox"]
        w_pt, h_pt = bbox[2] - bbox[0], bbox[3] - bbox[1]
        entry = details.get(info.get("xref"))
        dpi = info["width"] / (w_pt / 72) if w_pt > 0 else None
        images.append({
            "width_px": info["width"],
            "height_px": info["height"],
            "drawn_width_pt": round(w_pt, 1),
            "drawn_height_pt": round(h_pt, 1),
            "dpi": round(dpi) if dpi else None,
            "bits": info.get("bpc"),
            "colour_space": info.get("cs-name"),
            "filter": entry[8] if entry else None,
        })
        if page_area > 0 and w_pt * h_pt >= 0.1 * page_area:
            big.append(tuple(bbox))
    clip = (page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1)
    coverage = _union_area(big, clip) / page_area if page_area else 0.0
    return images, min(1.0, coverage)


# ---------------------------------------------------------------- the page

def gather(page, number):
    """Gather all vector, text and image evidence for a page."""
    fonts, hidden = read_text_glyphs(page)
    lines, filled, candidates, curved = read_drawings(page)
    centres = [c for use in fonts.values() for c in use.centres]
    staves = find_staves(candidates, centres)
    classify_fonts(fonts, staves, page)
    outlined = fingerprint_outlines(curved, staves.staff_space_pt or 5.0)
    images, coverage = read_images(page)
    return PageEvidence(
        page=number,
        width_pt=page.rect.width,
        height_pt=page.rect.height,
        rotation=page.rotation,
        fonts=sorted(fonts.values(), key=lambda f: -f.glyphs),
        hidden_text_glyphs=hidden,
        lines=lines,
        filled=filled,
        staves=staves,
        outlined=outlined,
        images=images,
        image_coverage=coverage,
    )


# ----------------------------------------------------------- raster measures

def raster_measures(page, images):
    """Render the page at 100 dpi in greyscale and measure the signs of a
    physical page (spec, 'Telling C from D'). The only code here that renders."""
    import cv2
    import numpy as np
    import pymupdf

    pix = page.get_pixmap(dpi=100, colorspace=pymupdf.csGRAY)
    grey = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    h, w = grey.shape

    # 1. background: 90th percentile brightness in each cell of a 4 by 4 grid
    cells = [
        np.percentile(grey[r * h // 4:(r + 1) * h // 4, c * w // 4:(c + 1) * w // 4], 90)
        for r in range(4) for c in range(4)
    ]
    background_range = float(max(cells) - min(cells))

    # 2. dark border: outer 3 percent of each side
    bh, bw = max(1, int(h * 0.03)), max(1, int(w * 0.03))
    strips = [grey[:bh, :], grey[-bh:, :], grey[:, :bw], grey[:, -bw:]]
    dark_border = bool(any((s < 100).mean() > 0.30 for s in strips))

    # 3. tilt: horizontal projection over the middle columns, angles -3 to 3
    band = (grey[:, w // 4: 3 * w // 4] < 160).astype(np.float32)
    best_angle, best_score = 0.0, -1.0
    centre = (band.shape[1] / 2, band.shape[0] / 2)
    for step in range(-30, 31):
        angle = step / 10
        matrix = cv2.getRotationMatrix2D(centre, angle, 1.0)
        rotated = cv2.warpAffine(band, matrix, (band.shape[1], band.shape[0]))
        score = float(np.var(rotated.sum(axis=1)))
        if score > best_score + 1e-9:
            best_angle, best_score = angle, score

    # 4. bilevel scan: every large image is 1 bit or a bilevel compression
    large = [i for i in images if i["drawn_width_pt"] * i["drawn_height_pt"] >= 0.1 * page.rect.width * page.rect.height]
    bilevel = bool(large) and all(
        i["bits"] == 1 or (i["filter"] or "") in ("CCITTFaxDecode", "JBIG2Decode") for i in large
    )
    return {
        "background_range": round(background_range, 1),
        "dark_border": dark_border,
        "tilt_degrees": best_angle,
        "bilevel": bilevel,
    }
