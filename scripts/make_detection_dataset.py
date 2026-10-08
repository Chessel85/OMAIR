"""Make the small symbol-detection dataset for the Stage 10 training benchmark.

Scores come from the development set (their reference MusicXML). Verovio draws
each score with bounding boxes for every symbol; the pages are rendered with
PyMuPDF, cut into overlapping square tiles, and written in YOLO format under
<corpus>/benchmark/detection. The development scores are split into training
and validation by score, so no score is in both.

usage: python scripts/make_detection_dataset.py [--scores N] [--tile PIXELS] [--seed N]
"""

import argparse
import random
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pymupdf
import verovio

from omr import paths
from omr.log import ProgressLog

CLASSES = ["notehead", "stem", "beam", "flag", "rest", "clef", "accidental",
           "dots", "meter", "barline", "dynamic"]
CLASS_OF = {"note": 0, "stem": 1, "beam": 2, "flag": 3, "rest": 4, "clef": 5,
            "accid": 6, "keyAccid": 6, "dots": 7, "meterSig": 8, "barLine": 9, "dynam": 10}
ZOOM = 2.6            # pixels per point; a 640 x 880 point page becomes 1664 x 2288
UNITS = 0.04          # points per Verovio unit (640 / 16000)
MIN_VISIBLE = 0.5     # share of a symbol that must lie inside a tile to keep it
SCALES = (35, 40, 50)

_TRANSLATE = re.compile(r"translate\(\s*([-\d.]+)[ ,]+([-\d.]+)\s*\)")


def render_pages(path, scale):
    """Yield (png as numpy array, labels as [class, x0, y0, x1, y1] in pixels) for each page."""
    tk = verovio.toolkit()
    tk.setOptions({"pageWidth": 1600, "pageHeight": 2200, "scale": scale,
                   "adjustPageHeight": False, "svgViewBox": True, "svgBoundingBoxes": True})
    if not tk.loadFile(str(path)):
        raise RuntimeError("Verovio could not read the file")
    for page in range(1, tk.getPageCount() + 1):
        svg = tk.renderToSVG(page)
        labels = boxes(svg)
        yield picture(svg), labels


def boxes(svg):
    root = ET.fromstring(svg)
    out = []

    def walk(node, dx, dy):
        tag = node.tag.split("}")[-1]
        if tag == "g":
            m = _TRANSLATE.search(node.get("transform", ""))
            if m:
                dx, dy = dx + float(m.group(1)), dy + float(m.group(2))
            names = node.get("class", "").split()
            if "bounding-box" in names and names[0] in CLASS_OF:
                for rect in node:
                    if rect.tag.endswith("rect"):
                        x, y = float(rect.get("x")) + dx, float(rect.get("y")) + dy
                        w, h = float(rect.get("width")), float(rect.get("height"))
                        k = UNITS * ZOOM
                        out.append([CLASS_OF[names[0]], x * k, y * k, (x + w) * k, (y + h) * k])
        for child in node:
            walk(child, dx, dy)

    walk(root, 0, 0)  # the page margin translate is read from the file itself
    return out


def picture(svg):
    """Flatten the SVG so PyMuPDF draws it: it ignores the nested svg, CSS strokes and 'transparent'."""
    svg = re.sub(r'<svg class="definition-scale"[^>]*>',
                 f'<g stroke="black" class="definition-scale" transform="scale({UNITS})">', svg, count=1)
    cut = svg.rindex("</svg>", 0, svg.rindex("</svg>"))
    svg = svg[:cut] + "</g>" + svg[cut + 6:]
    svg = re.sub(r'<rect [^>]*fill="transparent"[^>]*/>', "", svg)
    doc = pymupdf.open(stream=svg.encode("utf8"), filetype="svg")
    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def tiles(image, labels, size, step, rng, keep_empty=0.05):
    """Yield (tile array, YOLO label lines) for the tiles of one page."""
    height, width = image.shape
    for top in range(0, max(height - size, 0) + step, step):
        for left in range(0, max(width - size, 0) + step, step):
            top0, left0 = min(top, max(height - size, 0)), min(left, max(width - size, 0))
            crop = image[top0:top0 + size, left0:left0 + size]
            if crop.shape != (size, size):
                canvas = np.full((size, size), 255, np.uint8)
                canvas[:crop.shape[0], :crop.shape[1]] = crop
                crop = canvas
            lines = []
            for cls, x0, y0, x1, y1 in labels:
                cx0, cy0 = max(x0 - left0, 0), max(y0 - top0, 0)
                cx1, cy1 = min(x1 - left0, size), min(y1 - top0, size)
                area = (x1 - x0) * (y1 - y0)
                if cx1 <= cx0 or cy1 <= cy0 or area <= 4:
                    continue
                if (cx1 - cx0) * (cy1 - cy0) < MIN_VISIBLE * area:
                    continue
                lines.append(f"{cls} {(cx0 + cx1) / 2 / size:.5f} {(cy0 + cy1) / 2 / size:.5f} "
                             f"{(cx1 - cx0) / size:.5f} {(cy1 - cy0) / size:.5f}")
            if lines or rng.random() < keep_empty:
                yield crop, lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", type=int, default=40)
    ap.add_argument("--tile", type=int, default=1024)
    ap.add_argument("--seed", type=int, default=20261008)
    ap.add_argument("--max-pages", type=int, default=3, help="pages used from each score")
    args = ap.parse_args()
    corpus = paths.require_corpus_dir()
    paths.check_free_space(corpus)
    out = corpus / "benchmark" / "detection"
    out.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("detection-dataset", out.parent / "detection-dataset.log")
    rng = random.Random(args.seed)
    folders = sorted(p for p in (corpus / "generated" / "development").iterdir()
                     if (p / "reference.musicxml").is_file())
    rng.shuffle(folders)
    chosen = folders[:args.scores]
    cut = max(1, int(len(chosen) * 0.8))
    counts = {"train": 0, "val": 0}
    objects = [0] * len(CLASSES)
    import cv2
    for index, folder in enumerate(chosen):
        split = "train" if index < cut else "val"
        for sub in ("images", "labels"):
            (out / sub / split).mkdir(parents=True, exist_ok=True)
        try:
            scale = rng.choice(SCALES)
            for page, (image, labels) in enumerate(render_pages(folder / "reference.musicxml", scale)):
                if page >= args.max_pages:
                    break
                for n, (crop, lines) in enumerate(tiles(image, labels, args.tile, args.tile * 7 // 8, rng)):
                    name = f"{folder.name}-p{page + 1}-t{n}"
                    cv2.imwrite(str(out / "images" / split / f"{name}.png"), crop)
                    (out / "labels" / split / f"{name}.txt").write_text("\n".join(lines) + "\n" if lines else "")
                    counts[split] += 1
                    for line in lines:
                        objects[int(line.split()[0])] += 1
            log.info(f"Score {index + 1} of {len(chosen)}: {folder.name} ({split}, scale {scale}). "
                     f"Tiles so far: {counts['train']} training, {counts['val']} validation.")
        except Exception as e:  # one bad score must not stop the run
            log.warning(f"Score {folder.name} skipped: {e}")
    names = "\n".join(f"  {i}: {c}" for i, c in enumerate(CLASSES))
    (out / "data.yaml").write_text(
        f"path: {out.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n{names}\n")
    log.info("Objects per class: " + ", ".join(f"{c} {n}" for c, n in zip(CLASSES, objects)))
    return log.finish(f"{counts['train']} training tiles, {counts['val']} validation tiles, tile {args.tile} pixels")


if __name__ == "__main__":
    sys.exit(main())
