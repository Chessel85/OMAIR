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
import re
from pathlib import Path

import numpy as np

from omr import paths
from omr.pdf import classify, evidence
from omr.pdf.symbols import PageSymbols
from omr.raster import lines as rl, names, page as rp, text as rt

PAGE_SPACE = 20.0     # pixels a staff space the page is scaled to for the detector
CONFIDENCE = 0.25     # the detector's lowest confidence kept
MODEL_ENV = "OMR_DETECTOR"
DETECTIONS_ENV = "OMR_DETECTIONS_DIR"
DEFAULT_MODEL = Path("runs") / "detector" / "full" / "weights" / "best.onnx"
BRACKET_GAP = (0.8, 3.0)   # staff spaces: the gap a tuplet number leaves in its bracket
BRACKET_HALF = (1.0, 30.0)  # staff spaces: the length of one half of a tuplet bracket
BRACKET_DIGIT_SCORE = 0.9   # OCR's lowest score for a number read in a bracket's gap
LEDGER_MORE = 1.5          # staff spaces: how much wider than its notehead a ledger line can be
HOOK_LENGTH = (0.4, 1.8)    # staff spaces: the length of a tuplet bracket's hook


def model_path():
    """The detector's model file: OMR_DETECTOR, or the full run's ONNX file
    in the corpus folder."""
    configured = os.environ.get(MODEL_ENV)
    return Path(configured) if configured else paths.corpus_dir() / DEFAULT_MODEL


def _check_model(path):
    if not Path(path).is_file():
        raise FileNotFoundError(f"the symbol detector's model {path} was not found. "
                                f"Set {MODEL_ENV} to the model file.")


@functools.cache
def _model(path):
    _check_model(path)   # before the import: a missing model is the message to give, installed or not
    from ultralytics import YOLO

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
    key.update(model_digest(str(model)).encode())
    key.update(f"{factor:.6f} {CONFIDENCE} {grey.shape}".encode())
    key.update(grey.tobytes())
    name = key.hexdigest()
    return Path(folder) / name[:2] / f"{name}.json"


@functools.cache
def model_digest(path):
    """The SHA-256 of a model file, read once a process."""
    _check_model(path)
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_image_page(page_symbols):
    """The page has no music symbols of its own and an image covers at
    least half of it (the inspector's raster test)."""
    return not page_symbols.symbols and page_symbols.evidence.image_coverage >= classify.BIG_IMAGE


def read_page(page, number, detect=None, read_text=None):
    """(PageSymbols, RasterPage) for a PDF page holding a page image.
    `detect` is a function as `detector` gives (the default model if None),
    `read_text` one as `omr.raster.text.reader` gives."""
    seen = detect_image(page, detect)
    if seen is None:
        return _empty(page, number)
    grey, angle, place, space_px, found = seen
    space_pt = space_px * place.sy
    symbols, text, masked = names.to_symbols(found, space_pt)
    symbols = names.trim_to_ink(symbols, rl.ink_of(grey), place)
    named = PageSymbols(number, None, symbols, text_regions=text, masked=masked)
    boxes, flags = rp.symbol_boxes(named)
    rests = [s.box for s in symbols if s.name in names.BEAM_LIKE]
    heads = [s.box for s in symbols if s.name.startswith("notehead")]
    apart = set(rests) | set(heads)
    boxes = [b for b in boxes if b not in apart]
    lines = rl.find_lines(grey, *([place.to_pixels(b) for b in part] for part in (boxes, flags, rests, heads)))
    lines.tilt = angle
    digits = [place.to_pixels(s.box) for s in symbols if s.name in names.TIME_DIGITS]
    lines.vertical = [v for v in lines.vertical if not _in_digits(v, digits)]
    lines.vertical = rl.across_text(lines.vertical, [place.to_pixels(b) for b in text], lines.space, rl.ink_of(grey))
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
    read_text = read_text or rt.reader()
    named.text = rt.read_regions(grey, place, text, space_px, read_text)
    symbols = named.symbols = symbols + bracket_numbers(grey, lines, symbols, place, space_pt, read_text)
    bracket_hooks(lines, rl.ink_of(grey), [place.to_pixels(s.box) for s in symbols if s.name.startswith("tuplet")])
    raster_page = rp.RasterPage(page, rp.drawings(lines, place))
    raster_page.grey, raster_page.place = grey, place   # for Engine 2 (omr.raster.sequence_reading)
    named.evidence = evidence.gather(raster_page, number)
    return named, raster_page


def _bracket_halves(lines, space):
    """(x0, y0, x1, y1, curve) in pixels, left to right, of lines that may
    be half a tuplet bracket: level lines, nearly level thin lines (a
    sloping bracket), and the spans of curves (a half traced with its hook),
    `curve` being the curve's index in lines.curves, else None."""
    lo, hi = BRACKET_HALF[0] * space, BRACKET_HALF[1] * space
    out = [(x0, y, x1, y, None) for y, x0, x1, _ in lines.level if lo <= x1 - x0 <= hi]
    for x0, y0, x1, y1, _ in lines.thin:
        if x1 < x0:
            x0, y0, x1, y1 = x1, y1, x0, y0
        if lo <= x1 - x0 <= hi and abs(y1 - y0) <= 0.3 * (x1 - x0):
            out.append((x0, y0, x1, y1, None))
    for k, curve in enumerate(lines.curves):
        pts = np.asarray(curve, float)
        left, right = pts[pts[:, 0].argmin()], pts[pts[:, 0].argmax()]
        if lo <= right[0] - left[0] <= hi:
            out.append((left[0], left[1], right[0], right[1], k))
    return out


def _ledger(half, heads, space):
    """Whether a would-be bracket half is a ledger line: centred on a
    notehead (or one of a stack of ledger lines under it) and no more than
    LEDGER_MORE staff spaces wider. Ledger lines of neighbouring notes look
    like the halves of a bracket, and a stem with ledger stubs in the gap
    between them reads as a 4 (pdmx-QkFxjWipz93Z)."""
    x0, _, x1, _, _ = half
    return any(x0 <= (t[0] + t[2]) / 2 <= x1 and x1 - x0 <= t[2] - t[0] + LEDGER_MORE * space
               for t in heads)


def bracket_gaps(lines, ink, taken, space):
    """(ink box, (left half, right half)) in pixels for the gaps of tuplet
    brackets: a half ending and another starting 0.8 to 3 staff spaces on at
    the same height, with ink between them and no notehead or tuplet number
    already there (`taken`, pixel boxes). The halves are as _bracket_halves
    gives them, less ledger lines (_ledger)."""
    halves = [h for h in _bracket_halves(lines, space) if not _ledger(h, taken, space)]
    out = []
    for a in halves:
        right = [b for b in halves if abs(b[1] - a[3]) <= 0.5 * space
                 and BRACKET_GAP[0] * space <= b[0] - a[2] <= BRACKET_GAP[1] * space]
        if not right:
            continue
        b = min(right, key=lambda h: h[0])
        y = (a[3] + b[1]) / 2
        gx0, gx1 = int(a[2]) + 1, int(b[0])
        gy0, gy1 = max(int(y - 1.1 * space), 0), int(y + 1.1 * space) + 1
        if any(t[0] < gx1 and t[2] > gx0 and t[1] < gy1 and t[3] > gy0 for t in taken):
            continue
        sub = ink[gy0:gy1, gx0:gx1]
        if sub.sum() < 0.3 * space:
            continue
        rows, cols = np.nonzero(sub)
        box = (gx0 + cols.min(), gy0 + rows.min(), gx0 + cols.max() + 1, gy0 + rows.max() + 1)
        if all(box != g[0] for g in out):
            out.append((box, (a, b)))
    return out


def _straighten(lines, used):
    """Bracket halves traced as curves (with their hooks) become level thin
    lines at the height of their end by the number, which the vector reader
    finds as the bracket (notation._bracket_span); it does not look at
    curves. `used` are (half, is the left half) pairs."""
    gone = set()
    for (x0, y0, x1, y1, k), left in used:
        if k is None or k in gone:
            continue
        y = y1 if left else y0
        lines.thin.append((x0, y, x1, y, 1.0))
        gone.add(k)
    if gone:
        lines.curves = [c for k, c in enumerate(lines.curves) if k not in gone]


def _hook(ink, x, y, space):
    """(top, bottom) of the hook at a bracket's outer end (x, y), pixels:
    ink running straight up or down from the line for HOOK_LENGTH staff
    spaces, or None."""
    h, w = ink.shape
    x, y = int(round(x)), int(round(y))
    if not (0 <= x < w and 0 <= y < h):
        return None
    cols = ink[:, max(x - 1, 0):x + 2].any(axis=1)
    thick = max(2, round(0.15 * space))
    for way in (1, -1):
        r = y + way * thick
        n = 0
        while 0 <= r < h and cols[r]:
            r += way
            n += 1
        if HOOK_LENGTH[0] * space <= n <= HOOK_LENGTH[1] * space:
            return (y, r) if way > 0 else (r, y)
    return None


def bracket_hooks(lines, ink, numbers):
    """Vertical lines for the hooks of tuplet brackets, which tell the reader
    the side of the bracket's notes (notation._bracket_span): a hook is
    about a staff space long, under the vertical lines' least length, so a
    bracket between two staves went to the wrong one (pdmx-TQZXkjDhLjeG).
    For each tuplet number (`numbers`, pixel boxes) with a bracket half
    ending just before it and another starting just after it, the ink at
    the halves' outer ends is followed up or down."""
    space = lines.space
    halves = _bracket_halves(lines, space)
    for x0, y0, x1, y1 in numbers:
        cy = (y0 + y1) / 2
        left = [h for h in halves if 0 <= x0 - h[2] <= 1.5 * space and abs(h[3] - cy) <= 1.5 * space]
        right = [h for h in halves if 0 <= h[0] - x1 <= 1.5 * space and abs(h[1] - cy) <= 1.5 * space]
        if not left or not right:
            continue
        a, b = max(left, key=lambda h: h[2]), min(right, key=lambda h: h[0])
        for x, y in ((a[0], a[1]), (b[2], b[3])):
            hook = _hook(ink, x, y, space)
            if hook and not any(abs(v[0] - x) <= 1 and v[1] <= hook[1] and v[2] >= hook[0] for v in lines.vertical):
                lines.vertical.append((float(x), float(hook[0]), float(hook[1]), 1.0))


def bracket_numbers(grey, lines, symbols, place, space_pt, read):
    """Tuplet number symbols read by OCR in the gaps of tuplet brackets
    where the detector found none (MuseScore 4's italic 4 over a quadruplet,
    pdmx-jiVBTaknDNuh): a single digit 2 to 9, read with a score of at
    least BRACKET_DIGIT_SCORE (the bracket's ends either side of it rule out
    an octave line's 8 and a volta's number). Their bracket halves traced
    as curves are made straight lines in `lines` (_straighten)."""
    taken = [place.to_pixels(s.box) for s in symbols if s.name.startswith(("notehead", "tuplet"))]
    gaps = bracket_gaps(lines, rl.ink_of(grey), taken, lines.space)
    if not gaps:
        return []
    pad = 3
    crops = [grey[max(b[1] - pad, 0):b[3] + pad, max(b[0] - pad, 0):b[2] + pad] for b, _ in gaps]
    out, used = [], []
    for (b, (left, right)), (text, score) in zip(gaps, read(crops)):
        digit = re.fullmatch(r"[-_ ]*([2-9])[-_ ]*", text)
        if digit and score >= BRACKET_DIGIT_SCORE:
            box = (place.x0 + b[0] * place.sx, place.y0 + b[1] * place.sy,
                   place.x0 + b[2] * place.sx, place.y0 + b[3] * place.sy)
            name = f"tuplet{digit.group(1)}"
            out.append(names.make(name, name, box, score, None, space_pt))
            used += [(left, True), (right, False)]
    _straighten(lines, used)
    return out


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
                read_text = rt.reader()
            ps, page = read_page(page, ps.page, detect, read_text)
        use.append(page)
        out.append(ps)
    return use, out
