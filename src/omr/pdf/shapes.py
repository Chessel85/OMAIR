"""Glyph shapes: drawing them and comparing them with SMuFL reference glyphs.

Used to tell which legacy font a renamed font is, and to name the outlined
symbols of Type B pages. Every shape is drawn in grey, cropped to its ink and
reduced to a SHAPE_SIZE square (evidence._normalise), and two shapes are
compared by correlation. Sizes are kept apart, in staff spaces where known,
because a shape alone cannot tell a whole rest from a half rest or a beam
piece. See docs/notes/symbol-spec.md, "Shapes".
"""

import functools
from dataclasses import dataclass

from omr.pdf import evidence, smufl

DRAW_SIZE = 40      # points per em when a font glyph is drawn
CELL = 160          # points per cell; the origin sits at ORIGIN in each cell
ORIGIN = (50, 100)
PIXELS_PER_SPACE = 12   # outlined shapes and references are drawn at this scale


@dataclass
class Shape:
    """A drawn glyph: its normalised image, its ink size, and where its
    origin lies relative to its ink box, all in staff spaces (em / 4 for a
    font glyph drawn without a staff). `image` is None if there is no ink."""

    image: object
    width: float = 0.0
    height: float = 0.0
    left: float = 0.0     # ink left edge minus origin x
    top: float = 0.0      # ink top minus origin y (y down, so above the origin is negative)


def _measure(grey, scale, origin):
    """A Shape from a grey cell drawn at `scale` pixels a staff space."""
    import numpy as np

    ink = 255 - grey.astype(np.float32)
    ys, xs = np.nonzero(ink > 64)
    if len(xs) == 0:
        return Shape(None)
    return Shape(
        evidence._normalise(grey),
        (xs.max() - xs.min() + 1) / scale,
        (ys.max() - ys.min() + 1) / scale,
        (xs.min() - origin[0]) / scale,
        (ys.min() - origin[1]) / scale,
    )


def _grey(pix):
    import numpy as np
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def draw_font_glyphs(buffer, gids):
    """Draw glyphs by glyph id from an embedded font program. Sizes are in
    quarters of an em, which is a staff space for a SMuFL font."""
    import pymupdf

    if not gids:
        return []
    doc = pymupdf.open()
    page = doc.new_page(width=CELL * len(gids), height=CELL)
    page.insert_font(fontname="F0", fontbuffer=buffer)
    shows = " ".join(f"1 0 0 1 {i * CELL + ORIGIN[0]} {CELL - ORIGIN[1]} Tm <{gid:04x}> Tj"
                     for i, gid in enumerate(gids))
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, f"BT /F0 {DRAW_SIZE} Tf {shows} ET".encode())
    doc.xref_set_key(page.xref, "Contents", f"{xref} 0 R")
    grey = _grey(page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY))
    scale = DRAW_SIZE / 4
    return [_measure(grey[:, i * CELL:(i + 1) * CELL], scale, ORIGIN) for i in range(len(gids))]


@functools.cache
def reference(name, font="Bravura"):
    """The Shape of a SMuFL glyph in a reference font, or None if it has no outline."""
    import pymupdf

    path = smufl.outline_path(name, font)
    if path is None:
        return None
    units = smufl.UNITS_PER_SPACE / PIXELS_PER_SPACE
    size = CELL * units
    ox, oy = ORIGIN[0] * units, ORIGIN[1] * units
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{CELL}" height="{CELL}" '
           f'viewBox="{-ox} {-oy} {size} {size}"><rect x="{-ox}" y="{-oy}" width="{size}" height="{size}" fill="white"/>'
           f'<path transform="scale(1,-1)" d="{path}" fill="black"/></svg>')
    doc = pymupdf.open(stream=svg.encode(), filetype="svg")
    grey = _grey(doc[0].get_pixmap(colorspace=pymupdf.csGRAY))
    return _measure(grey, PIXELS_PER_SPACE, ORIGIN)


def draw_paths(drawings, staff_space):
    """Draw filled vector paths (items from PyMuPDF's get_drawings, already in
    page coordinates as shown) as one shape, at PIXELS_PER_SPACE. The origin
    is put at the ink's top left; the caller knows the page position."""
    import pymupdf

    points = [p for d in drawings for item in d["items"] for p in evidence._item_points(item)]
    x0, y0, x1, y1 = evidence._bbox(points)
    scale = PIXELS_PER_SPACE / staff_space
    width = int((x1 - x0) * scale) + 8
    height = int((y1 - y0) * scale) + 8
    doc = pymupdf.open()
    page = doc.new_page(width=max(width, 8), height=max(height, 8))

    def at(p):
        return pymupdf.Point((p.x - x0) * scale + 4, (p.y - y0) * scale + 4)

    for d in drawings:
        shape = page.new_shape()
        for item in d["items"]:
            kind = item[0]
            if kind == "l":
                shape.draw_line(at(item[1]), at(item[2]))
            elif kind == "c":
                shape.draw_bezier(at(item[1]), at(item[2]), at(item[3]), at(item[4]))
            elif kind == "re":
                r = item[1]
                shape.draw_rect(pymupdf.Rect(at(r.tl), at(r.br)))
            elif kind == "qu":
                q = item[1]
                shape.draw_quad(pymupdf.Quad(at(q.ul), at(q.ur), at(q.ll), at(q.lr)))
        shape.finish(fill=(0, 0, 0), color=None, even_odd=bool(d.get("even_odd")), closePath=True)
        shape.commit()
    grey = _grey(page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY))
    return _measure(grey, PIXELS_PER_SPACE, (4, 4))


def _blurred(shape):
    """The image slightly blurred, so that thin strokes a pixel apart (an
    accent, a flag) still overlap."""
    import cv2

    if getattr(shape, "_blur", None) is None:
        shape._blur = cv2.GaussianBlur(shape.image, (5, 5), 1.0)
    return shape._blur


# The fonts whose outlines are references. Symbols drawn as outlines come from
# any music font, so each is compared with all of them and the best fit kept.
REFERENCE_FONTS = list(smufl.VEROVIO_FONTS)


def references(name):
    """The Shapes of a SMuFL glyph in every reference font that has it."""
    return [r for font in REFERENCE_FONTS if (r := reference(name, font)) is not None]


def best_fit(shape, name):
    """(similarity, reference Shape) of the reference of `name` that fits the
    shape best and whose size fits, or (0.0, None)."""
    best = (0.0, None)
    for ref in references(name):
        if size_fits(shape, ref):
            sim = similarity(shape, ref)
            if sim > best[0]:
                best = (sim, ref)
    return best


def similarity(a, b):
    """Correlation of two normalised shapes, 0 if either is empty."""
    if a is None or b is None or a.image is None or b.image is None:
        return 0.0
    return evidence._correlation(_blurred(a), _blurred(b))


def turned(shape):
    """The shape turned a quarter turn (a vertical wiggle compared with a level one)."""
    import numpy as np

    if shape.image is None:
        return shape
    return Shape(np.ascontiguousarray(np.rot90(shape.image)), shape.height, shape.width)


def size_fits(shape, ref, tolerance=0.45):
    """The shape's width and height are each within `tolerance` (as a share)
    of the reference's, in staff spaces. Fonts differ in style, so the
    tolerance is wide; it still separates noteheads from clefs and beams."""
    for a, b in ((shape.width, ref.width), (shape.height, ref.height)):
        if b <= 0 or not (1 - tolerance) * b <= a <= (1 + tolerance) * b:
            return False
    return True
