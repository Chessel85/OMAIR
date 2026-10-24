"""Page images read by the vector reader (Phase 2, Stage 2.4).

A page with no music symbols of its own whose image covers most of it is
read from the image: turned level, its staff space measured, its symbols
found by the detector at PAGE_SPACE pixels a staff space and named
(omr.raster.names), its lines found with the symbols masked
(omr.raster.lines), and handed to the reader as a PageSymbols and a
RasterPage whose drawings are those lines.

With OMR_DETECTIONS_DIR set, each page's detections are saved in that
folder, keyed by the page image, the model file and the page scale, and read
back on later runs instead of running the detector again.

The rules are in docs/notes/raster-reading-spec.md.
"""

import functools
import hashlib
import json
import os
from pathlib import Path

from omr.raster import names
from omr.raster import page as rp

PAGE_SPACE = 20.0     # pixels a staff space the page is scaled to for the detector
CONFIDENCE = 0.25     # the detector's lowest confidence kept
MODEL_ENV = "OMR_DETECTOR"
DETECTIONS_ENV = "OMR_DETECTIONS_DIR"
DEFAULT_MODEL = Path("runs") / "detector" / "full" / "weights" / "best.onnx"


def model_path():
    """The detector's model file: OMR_DETECTOR, or the full run's ONNX file
    in the corpus folder."""
    from omr import paths

    configured = os.environ.get(MODEL_ENV)
    return Path(configured) if configured else paths.corpus_dir() / DEFAULT_MODEL


def _check_model(path):
    if not Path(path).is_file():
        raise FileNotFoundError(f"the symbol detector's model {path} was not found. "
                                f"Set {MODEL_ENV} to the model file.")


@functools.cache
def _model(path):
    from ultralytics import YOLO

    _check_model(path)
    return YOLO(str(path), task="detect")


def detector(path=None, saved_in=None):
    """A function (grey image, scale) -> [(class index, box in pixels,
    confidence)] that runs the detector model (loaded once a process).
    Detections are saved in the folder `saved_in`, or with it None in
    OMR_DETECTIONS_DIR if set; with it False, never."""
    from omr.raster import detect

    path = str(path or model_path())

    def run(grey, factor):
        return detect.detect_page(_model(path), grey, factor, conf=CONFIDENCE)

    folder = os.environ.get(DETECTIONS_ENV) if saved_in is None else saved_in
    return saving(run, Path(folder), path) if folder else run


def saving(run, folder, model):
    """`run`, with each page's detections saved in `folder` and read back
    when the same image is read at the same scale with the same model."""
    def cached(grey, factor):
        file = saved_file(folder, grey, factor, model)
        try:
            return [(c, tuple(b), p) for c, b, p in json.loads(file.read_text(encoding="utf-8"))]
        except (OSError, ValueError):
            pass
        found = run(grey, factor)
        file.parent.mkdir(parents=True, exist_ok=True)
        part = file.with_name(f"{file.stem}.{os.getpid()}.part")   # so a reader never sees half a file
        part.write_text(json.dumps([[c, list(b), p] for c, b, p in found]), encoding="utf-8")
        part.replace(file)
        return found
    return cached


def saved_file(folder, grey, factor, model):
    """The file a page's detections are saved in: named by the image's
    contents, the scale and the model file's contents."""
    key = hashlib.sha256()
    key.update(_model_digest(str(model)).encode())
    key.update(f"{factor:.6f} {CONFIDENCE} {grey.shape}".encode())
    key.update(grey.tobytes())
    name = key.hexdigest()
    return Path(folder) / name[:2] / f"{name}.json"


@functools.cache
def _model_digest(path):
    _check_model(path)
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_image_page(page_symbols):
    """The page has no music symbols of its own and an image covers at
    least half of it (the inspector's raster test)."""
    from omr.pdf import classify

    return not page_symbols.symbols and page_symbols.evidence.image_coverage >= classify.BIG_IMAGE


def read_page(page, number, detect=None, read_text=None):
    """(PageSymbols, RasterPage) for a PDF page holding a page image.
    `detect` is a function as `detector` gives (the default model if None),
    `read_text` one as `omr.raster.text.reader` gives."""
    from omr.pdf import evidence
    from omr.pdf.symbols import PageSymbols
    from omr.raster import lines as rl
    from omr.raster import text as rt

    seen = detect_image(page, detect)
    if seen is None:
        return _empty(page, number)
    grey, angle, place, space_px, found = seen
    space_pt = space_px * place.sy
    symbols, text, masked = names.to_symbols(found, space_pt)
    named = PageSymbols(number, None, symbols, text_regions=text, masked=masked)
    boxes, flags = rp.symbol_boxes(named)
    rests = [s.box for s in symbols if s.name in names.BEAM_LIKE]
    boxes = [b for b in boxes if b not in rests]
    lines = rl.find_lines(grey, *([place.to_pixels(b) for b in part] for part in (boxes, flags, rests)))
    lines.tilt = angle
    digits = [place.to_pixels(s.box) for s in symbols if s.name in names.TIME_DIGITS]
    lines.vertical = [v for v in lines.vertical if not _in_digits(v, digits)]
    beams = [(place.x0 + x0 * place.sx, place.x0 + x1 * place.sx,
              place.y0 + min(t0, t1) * place.sy, place.y0 + max(b0, b1) * place.sy)
             for x0, x1, t0, b0, t1, b1 in lines.beams]
    symbols = named.symbols = names.without_beams(symbols, beams)
    verticals = [(place.x0 + x * place.sx, place.y0 + top * place.sy, place.y0 + bottom * place.sy, w * place.sx)
                 for x, top, bottom, w in lines.vertical]
    names.set_flag_directions(symbols, verticals, space_pt)
    level = [(place.y0 + y * place.sy, place.x0 + x0 * place.sx, place.x0 + x1 * place.sx, t * place.sy)
             for y, x0, x1, t in lines.level]
    names.snap_clefs(symbols, level, space_pt)
    names.metronome_notes(symbols, text, level, space_pt)
    named.text = rt.read_regions(grey, place, text, space_px, read_text or rt.reader())
    raster_page = rp.RasterPage(page, rp.drawings(lines, place))
    named.evidence = evidence.gather(raster_page, number)
    return named, raster_page


DIGIT_SHARE = 0.4   # a vertical line this much inside time signature digits is part of them


def _in_digits(vertical, digits):
    """The vertical line (x, top, bottom, width) lies mostly in the boxes of
    time signature digits: the strokes of a 1 over a 1 the detector missed
    reach the height of the staff and would be a barline."""
    x, top, bottom, _ = vertical
    inside = sum(max(0.0, min(bottom, b[3]) - max(top, b[1])) for b in digits if b[0] <= x <= b[2])
    return bottom > top and inside >= DIGIT_SHARE * (bottom - top)


def detect_image(page, detect=None):
    """(level grey image, angle turned, Placement, staff space in pixels,
    detections in page points) for a page's image, or None if it has no
    image or no staff space."""
    from omr.raster import lines as rl

    grey, rect = rp.page_image(page)
    if grey is None:
        return None
    grey, angle = rl.level(grey)
    place = rp.Placement(grey.shape, rect)
    space_px, _ = rl.staff_space(rl.ink_of(grey))
    if not space_px:
        return None
    detect = detect or detector()
    found = [(c, _to_points(place, b), p) for c, b, p in detect(grey, PAGE_SPACE / space_px)]
    return grey, angle, place, space_px, found


def _to_points(place, box):
    p, q = place.point(box[0], box[1]), place.point(box[2], box[3])
    return (p.x, p.y, q.x, q.y)


def _empty(page, number):
    from omr.pdf import evidence
    from omr.pdf.symbols import PageSymbols

    raster_page = rp.RasterPage(page, [])
    return PageSymbols(number, evidence.gather(raster_page, number)), raster_page


def read_document(doc, pages, detect=None, read_text=None):
    """(pages to read, PageSymbols) for a document whose PageSymbols the
    vector reader gave: each image page is read from its image, and its
    RasterPage stands for it; vector pages are left as they are."""
    use, out = [], []
    for ps in pages:
        page = doc[ps.page - 1]
        if is_image_page(ps):
            if detect is None:
                detect = detector()
            if read_text is None:
                from omr.raster import text as rt
                read_text = rt.reader()
            ps, page = read_page(page, ps.page, detect, read_text)
        use.append(page)
        out.append(ps)
    return use, out
