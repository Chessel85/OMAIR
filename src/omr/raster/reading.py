"""Page images read by the vector reader (Phase 2, Stage 2.4).

A page with no music symbols of its own whose image covers most of it is
read from the image: turned level, its staff space measured, its symbols
found by the detector at PAGE_SPACE pixels a staff space and named
(omr.raster.names), its lines found with the symbols masked
(omr.raster.lines), and handed to the reader as a PageSymbols and a
RasterPage whose drawings are those lines.

The rules are in docs/notes/raster-reading-spec.md.
"""

import functools
import os
from pathlib import Path

from omr.raster import names
from omr.raster import page as rp

PAGE_SPACE = 20.0     # pixels a staff space the page is scaled to for the detector
CONFIDENCE = 0.25     # the detector's lowest confidence kept
MODEL_ENV = "OMR_DETECTOR"
DEFAULT_MODEL = Path("runs") / "detector" / "full" / "weights" / "best.onnx"


def model_path():
    """The detector's model file: OMR_DETECTOR, or the full run's ONNX file
    in the corpus folder."""
    from omr import paths

    configured = os.environ.get(MODEL_ENV)
    return Path(configured) if configured else paths.corpus_dir() / DEFAULT_MODEL


@functools.cache
def _model(path):
    from ultralytics import YOLO

    if not Path(path).is_file():
        raise FileNotFoundError(f"the symbol detector's model {path} was not found. "
                                f"Set {MODEL_ENV} to the model file.")
    return YOLO(str(path), task="detect")


def detector(path=None):
    """A function (grey image, scale) -> [(class index, box in pixels,
    confidence)] that runs the detector model (loaded once a process)."""
    from omr.raster import detect

    path = str(path or model_path())

    def run(grey, factor):
        return detect.detect_page(_model(path), grey, factor, conf=CONFIDENCE)
    return run


def is_image_page(page_symbols):
    """The page has no music symbols of its own and an image covers at
    least half of it (the inspector's raster test)."""
    from omr.pdf import classify

    return not page_symbols.symbols and page_symbols.evidence.image_coverage >= classify.BIG_IMAGE


def read_page(page, number, detect=None):
    """(PageSymbols, RasterPage) for a PDF page holding a page image.
    `detect` is a function as `detector` gives (the default model if None)."""
    from omr.pdf import evidence
    from omr.pdf.symbols import PageSymbols
    from omr.raster import lines as rl

    grey, rect = rp.page_image(page)
    if grey is None:
        return _empty(page, number)
    grey, angle = rl.level(grey)
    place = rp.Placement(grey.shape, rect)
    space_px, _ = rl.staff_space(rl.ink_of(grey))
    if not space_px:
        return _empty(page, number)
    detect = detect or detector()
    found = [(c, _to_points(place, b), p) for c, b, p in detect(grey, PAGE_SPACE / space_px)]
    space_pt = space_px * place.sy
    symbols, text, masked = names.to_symbols(found, space_pt)
    named = PageSymbols(number, None, symbols, text_regions=text, masked=masked)
    boxes, flags = rp.symbol_boxes(named)
    lines = rl.find_lines(grey, [place.to_pixels(b) for b in boxes], [place.to_pixels(b) for b in flags])
    lines.tilt = angle
    verticals = [(place.x0 + x * place.sx, place.y0 + top * place.sy, place.y0 + bottom * place.sy, w * place.sx)
                 for x, top, bottom, w in lines.vertical]
    names.set_flag_directions(symbols, verticals, space_pt)
    level = [(place.y0 + y * place.sy, place.x0 + x0 * place.sx, place.x0 + x1 * place.sx, t * place.sy)
             for y, x0, x1, t in lines.level]
    names.snap_clefs(symbols, level, space_pt)
    raster_page = rp.RasterPage(page, rp.drawings(lines, place))
    named.evidence = evidence.gather(raster_page, number)
    return named, raster_page


def _to_points(place, box):
    p, q = place.point(box[0], box[1]), place.point(box[2], box[3])
    return (p.x, p.y, q.x, q.y)


def _empty(page, number):
    from omr.pdf import evidence
    from omr.pdf.symbols import PageSymbols

    raster_page = rp.RasterPage(page, [])
    return PageSymbols(number, evidence.gather(raster_page, number)), raster_page


def read_document(doc, pages, detect=None):
    """(pages to read, PageSymbols) for a document whose PageSymbols the
    vector reader gave: each image page is read from its image, and its
    RasterPage stands for it; vector pages are left as they are."""
    use, out = [], []
    for ps in pages:
        page = doc[ps.page - 1]
        if is_image_page(ps):
            if detect is None:
                detect = detector()
            ps, page = read_page(page, ps.page, detect)
        use.append(page)
        out.append(ps)
    return use, out
