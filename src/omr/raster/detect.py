"""The symbol detector on whole pages (Phase 2, Stage 2.3).

A page is cut into the same overlapping 640 pixel tiles as the training data,
each tile is read by the YOLO model, and the boxes are put back on the page:
a box cut by the edge of its tile is dropped where a neighbouring tile holds
the whole symbol; the pieces of a symbol too big for the overlap (a brace, a
large clef), which no tile holds whole and which reach across the overlap,
are joined into one box; and boxes of one class over the same symbol are
merged.
The page can first be scaled to a chosen staff space.

`truth_labels` makes the labels of a rendered page from its vector PDF by
the label rule (docs/notes/raster-labels-spec.md), and `match` scores the
detections against them.
"""

import numpy as np

from omr.corpus import raster_labels as rl

TILE = rl.TILE
OVERLAP = rl.OVERLAP
EDGE = 2            # pixels: a box this near an inner tile edge is cut by it
SAME_SYMBOL = 0.5   # IoU at which two boxes of one class are one symbol
INSIDE = 0.7        # share of a cut piece inside a whole box of its class: the same symbol
ACROSS = 0.5        # overlap across a tile edge, as a share of the narrower piece, to join two pieces
LONG = 1.0          # share of the overlap a cut piece must reach in from its cut edge: a symbol bigger than it
MATCH = 0.5         # IoU at which a detection matches a label


def truth_labels(page_symbols, vector_page, grey, zoom):
    """[Label] in pixels for a page image that shows `vector_page` at `zoom`
    pixels a point, made as the training data's labels are."""
    space_px = page_symbols.staff_space * zoom
    labels, _, _ = rl.page_labels(page_symbols, rl.text_characters(vector_page))
    labels = rl.to_pixels(labels, zoom, space_px, grey.shape)
    staff_boxes = rl.staff_boxes_px(page_symbols.evidence.staves, zoom)
    ink = rl.remove_staff_lines(grey < rl.FAINT_INK, staff_boxes)
    return rl.drop_duplicates(rl.extend_outlined_text(rl.tighten(labels, ink, space_px), ink, space_px))


def tile_origins(length, size=TILE, overlap=OVERLAP):
    return list(range(0, max(1, length - overlap), size - overlap))


def scaled(grey, factor):
    import cv2

    if abs(factor - 1) < 1e-3:
        return grey
    h, w = grey.shape
    method = cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC
    return cv2.resize(grey, (max(1, round(w * factor)), max(1, round(h * factor))), interpolation=method)


def detect_page(model, grey, factor=1.0, conf=0.25, device=None, batch=16):
    """[(class index, (x0, y0, x1, y1) in the page's pixels, confidence)] for
    a greyscale page, scaled by `factor` before tiling."""
    image = scaled(grey, factor)
    h, w = image.shape
    origins = [(x, y) for y in tile_origins(h) for x in tile_origins(w)]
    whole, pieces = [], []
    for start in range(0, len(origins), batch):
        chunk = origins[start:start + batch]
        tiles = []
        for x, y in chunk:
            tile = np.full((TILE, TILE), 255, dtype=np.uint8)
            part = image[y:y + TILE, x:x + TILE]
            tile[:part.shape[0], :part.shape[1]] = part
            tiles.append(np.repeat(tile[:, :, None], 3, axis=2))
        results = model.predict(tiles, imgsz=TILE, conf=conf, device=device, max_det=1000, verbose=False)
        for (x, y), result in zip(chunk, results):
            boxes = result.boxes
            for c, b, p in zip(boxes.cls.tolist(), boxes.xyxy.tolist(), boxes.conf.tolist()):
                d = (int(c), (b[0] + x, b[1] + y, b[2] + x, b[3] + y), p)
                across, down = _cut_sides(b, x, y, w, h)
                if not (across or down):
                    whole.append(d)
                elif (across and b[2] - b[0] >= LONG * OVERLAP) or (down and b[3] - b[1] >= LONG * OVERLAP):
                    pieces.append(d)
    found = merge(whole + join_pieces(pieces, whole))
    return [(c, tuple(v / factor for v in b), p) for c, b, p in found]


def _cut(box, x, y, w, h):
    """The box touches an edge of its tile that is not the page's edge, so
    the neighbouring tile holds more of it."""
    return any(_cut_sides(box, x, y, w, h))


def _cut_sides(box, x, y, w, h):
    """(cut by a left or right inner edge, cut by a top or bottom inner edge).
    A cut piece that does not reach right across the overlap, past the
    neighbouring tile's edge, in the direction it is cut belongs to a symbol
    that the neighbouring tile holds whole (or to nothing: the model also
    sees half-symbols at a tile's edge that are not there), and is dropped;
    a longer one may be part of a symbol too big for any tile to hold whole."""
    x0, y0, x1, y1 = box
    return ((x0 < EDGE and x > 0) or (x1 > TILE - EDGE and x + TILE < w),
            (y0 < EDGE and y > 0) or (y1 > TILE - EDGE and y + TILE < h))


def join_pieces(pieces, whole, overlap=OVERLAP):
    """The boxes of symbols cut by inner tile edges. A piece mostly inside a
    whole box of its class is that symbol, read whole by another tile, and is
    dropped. The rest are symbols bigger than the overlap: their pieces from
    neighbouring tiles each run right across the shared strip, so two pieces
    of one class that overlap along one direction by at least half the
    overlap, and across it by at least half the narrower piece, are joined
    into one box, with the higher confidence. A piece left alone (its
    partner was missed) is kept as it is."""
    left = [d for d in pieces
            if not any(c == d[0] and _inside(d[1], b) >= INSIDE for c, b, _ in whole)]
    groups = [[d] for d in left]
    joined = True
    while joined:
        joined = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if any(_same_symbol(a, b, overlap) for a in groups[i] for b in groups[j]):
                    groups[i] += groups.pop(j)
                    joined = True
                    break
            if joined:
                break
    out = []
    for g in groups:
        boxes = [b for _, b, _ in g]
        out.append((g[0][0], (min(b[0] for b in boxes), min(b[1] for b in boxes),
                              max(b[2] for b in boxes), max(b[3] for b in boxes)), max(p for _, _, p in g)))
    return out


def _inside(a, b):
    """The share of box a that lies inside box b."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = (a[2] - a[0]) * (a[3] - a[1])
    return ix * iy / area if area > 0 else 0.0


def _same_symbol(a, b, overlap):
    if a[0] != b[0]:
        return False
    (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = a[1], b[1]
    ox = min(ax1, bx1) - max(ax0, bx0)
    oy = min(ay1, by1) - max(ay0, by0)
    narrow_x = min(ax1 - ax0, bx1 - bx0)
    narrow_y = min(ay1 - ay0, by1 - by0)
    return ((oy >= overlap / 2 and narrow_x > 0 and ox >= ACROSS * narrow_x)
            or (ox >= overlap / 2 and narrow_y > 0 and oy >= ACROSS * narrow_y))


def merge(found, limit=SAME_SYMBOL):
    """Keep the most confident of the boxes of one class over the same symbol."""
    kept = []
    for cls in {c for c, _, _ in found}:
        ours = sorted((d for d in found if d[0] == cls), key=lambda d: -d[2])
        chosen = []
        for d in ours:
            if not any(rl.iou(d[1], k[1]) > limit for k in chosen):
                chosen.append(d)
        kept += chosen
    return kept


def match(labels, found, limit=MATCH):
    """Score detections against labels on one page. Returns a dict by class
    name of {"truth", "found", "matched", "other class"}: a label is matched
    by the most confident unused detection of its class over it; a label
    left unmatched that a detection of another class covers counts as
    "other class"."""
    out = {}

    def row(cls):
        return out.setdefault(cls, {"truth": 0, "found": 0, "matched": 0, "other class": 0})

    for c, _, _ in found:
        row(rl.CLASSES[c])["found"] += 1
    used = set()
    missed = []
    for lab in labels:
        row(lab.cls)["truth"] += 1
        best, best_iou = None, limit
        for k, (c, box, _) in enumerate(found):
            if k in used or rl.CLASSES[c] != lab.cls:
                continue
            v = rl.iou(lab.box, box)
            if v >= best_iou:
                best, best_iou = k, v
        if best is None:
            missed.append(lab)
        else:
            used.add(best)
            row(lab.cls)["matched"] += 1
    for lab in missed:
        if any(rl.CLASSES[c] != lab.cls and rl.iou(lab.box, box) >= limit for c, box, _ in found):
            row(lab.cls)["other class"] += 1
    return out
