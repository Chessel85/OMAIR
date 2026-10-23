"""A page image as the vector reader sees a page (Stage 2.2).

The vector reader asks a page for its drawings (PyMuPDF's get_drawings).
RasterPage answers with the lines omr.raster.lines finds in the image, as
stroked lines and filled four-sided beams in page points, as the page is
shown. Everything else is passed to the PDF page underneath, so the reader's
layout and notation stages run on it unchanged.
"""

import numpy as np
import pymupdf

from omr.raster import lines as rl


def page_image(page):
    """(grey image as a numpy array, its rectangle on the page) of the
    largest image on a PDF page, or (None, None) if it has none."""
    best = None
    for info in page.get_images(full=True):
        xref = info[0]
        for rect in page.get_image_rects(xref):
            if best is None or rect.get_area() > best[1].get_area():
                best = (xref, rect)
    if best is None:
        return None, None
    pix = pymupdf.Pixmap(page.parent, best[0])
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if pix.n != 1:
        pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
    grey = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
    return grey, best[1]


class Placement:
    """Turns pixels into page points: the image fills `rect`."""

    def __init__(self, shape, rect):
        h, w = shape
        self.x0, self.y0 = rect.x0, rect.y0
        self.sx, self.sy = rect.width / w, rect.height / h

    def to_pixels(self, box):
        x0, y0, x1, y1 = box
        return ((x0 - self.x0) / self.sx, (y0 - self.y0) / self.sy,
                (x1 - self.x0) / self.sx, (y1 - self.y0) / self.sy)

    def point(self, x, y):
        return pymupdf.Point(self.x0 + x * self.sx, self.y0 + y * self.sy)


def drawings(found, place):
    """The Lines as PyMuPDF drawing dictionaries in page points."""
    out = []

    def stroke(p1, p2, width):
        out.append({"type": "s", "items": [("l", p1, p2)], "width": width,
                    "rect": pymupdf.Rect(p1, p2).normalize(), "dashes": "[] 0"})

    for y, x0, x1, thick in found.level:
        stroke(place.point(x0, y), place.point(x1, y), thick * place.sy)
    for x, top, bottom, width in found.vertical:
        stroke(place.point(x, top), place.point(x, bottom), width * place.sx)
    for x0, x1, t0, b0, t1, b1 in found.beams:
        corners = [place.point(x0, t0), place.point(x1, t1), place.point(x1, b1), place.point(x0, b0)]
        items = [("l", corners[k], corners[(k + 1) % 4]) for k in range(4)]
        rect = pymupdf.Rect(corners[0], corners[0])
        for p in corners[1:]:
            rect |= p
        out.append({"type": "f", "items": items, "width": None, "rect": rect, "dashes": None})
    for x0, y0, x1, y1, thick in found.thin:
        stroke(place.point(x0, y0), place.point(x1, y1), thick * place.sy)
    for y, x0, x1, thick in found.dashed:
        stroke(place.point(x0, y), place.point(x1, y), thick * place.sy)
        out[-1]["dashes"] = "[3 3] 0"
    for trace in found.curves:
        out.append(curve(trace, place))
    return out


def curve(trace, place, pieces=6):
    """A filled curved shape round a traced curve: its top edge left to right
    and its bottom edge back, each as Bezier pieces through points taken
    along it (the reader needs a curve's ends and its box)."""
    picks = sorted({round(k * (len(trace) - 1) / pieces) for k in range(pieces + 1)})
    tops = [place.point(trace[k][0], trace[k][1]) for k in picks]
    bottoms = [place.point(trace[k][0], trace[k][2]) for k in reversed(picks)]
    items = []
    for edge in (tops, bottoms):
        for p, q in zip(edge, edge[1:]):
            items.append(("c", p, p + (q - p) / 3, p + (q - p) * 2 / 3, q))
    if len(items) > 1:
        items.insert(len(items) // 2, ("l", tops[-1], bottoms[0]))
    rect = pymupdf.Rect(tops[0], tops[0])
    for p in tops + bottoms:
        rect |= p
    return {"type": "f", "items": items, "width": None, "rect": rect, "dashes": None}


class RasterPage:
    """A PDF page whose drawings are the lines found in an image. `page` is
    the page asked for everything else (its text, fonts and rectangle); for
    the Stage 2.2 check it is the vector page the image was rendered from."""

    rotation = 0
    rotation_matrix = pymupdf.Identity

    def __init__(self, page, drawn):
        self._page = page
        self._drawings = drawn

    def get_drawings(self):
        return self._drawings

    def __getattr__(self, name):
        return getattr(self._page, name)


def symbol_boxes(page_symbols):
    """(ink boxes of a page's symbols and text runs, boxes of its flags), in
    page points."""
    boxes = [s.box for s in page_symbols.symbols if not s.name.startswith("flag")]
    boxes += [run.box for run in page_symbols.text]
    boxes += list(page_symbols.unnamed) + list(page_symbols.text_regions) + list(page_symbols.masked)
    return boxes, [s.box for s in page_symbols.symbols if s.name.startswith("flag")]


def read_lines(image_page, boxes_pt=((), ())):
    """(Lines in pixels, Placement) for the image on a PDF page, with the
    symbol and flag boxes (symbol_boxes) given in page points. A tilted
    image is turned level first, and the lines are those of the level page:
    the symbols must come from the same level image (in Engine 1 the
    detector reads it after this turn)."""
    grey, rect = page_image(image_page)
    if grey is None:
        return None, None
    grey, angle = rl.level(grey)
    place = Placement(grey.shape, rect)
    boxes, flags = ([place.to_pixels(b) for b in part] for part in boxes_pt)
    found = rl.find_lines(grey, boxes, flags)
    found.tilt = angle
    return found, place
