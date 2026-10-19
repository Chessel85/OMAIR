"""The symbol detector on whole pages (Phase 2, Stage 2.3).

A page is cut into the same overlapping 640 pixel tiles as the training data,
each tile is read by the YOLO model, and the boxes are put back on the page:
a box cut by the edge of its tile is dropped where a neighbouring tile holds
the whole symbol, and boxes of one class over the same symbol are merged.
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
    found = []
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
                if _cut(b, x, y, w, h):
                    continue
                found.append((int(c), (b[0] + x, b[1] + y, b[2] + x, b[3] + y), p))
    found = merge(found)
    return [(c, tuple(v / factor for v in b), p) for c, b, p in found]


def _cut(box, x, y, w, h):
    """The box touches an edge of its tile that is not the page's edge, and
    lies in the overlap, so the neighbouring tile holds more of it."""
    x0, y0, x1, y1 = box
    return ((x0 < EDGE and x > 0) or (y0 < EDGE and y > 0)
            or (x1 > TILE - EDGE and x + TILE < w) or (y1 > TILE - EDGE and y + TILE < h))


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
