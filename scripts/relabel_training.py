"""Bring the detector's training labels up to the label rule without rendering
again (Stage 2.3). Two rules were added after the training data was made
(docs/notes/raster-labels-spec.md):

- a dot named augmentationDot over or under a notehead is a staccato (Verovio
  names every dot augmentationDot);
- italic digits over the start of a staff are a bar number, labelled as text,
  not as tuplet digits (MuseScore writes bar numbers in italic).

Each page's truth file (pages/<score>/<job>/page-N.json) is corrected, and the
label file of every tile cut from it is made again from the corrected labels
by the same clipping rule as raster_labels.tiles. The tile images are not
touched. Without --write it only counts the changes.

usage: python scripts/relabel_training.py [--set training] [--write]
"""

import argparse
import copy
import json
import re
import sys
from collections import Counter, defaultdict
from types import SimpleNamespace

from omr import paths
from omr.corpus import raster_labels as rl

STEM = re.compile(r"^(?P<score>.+)-(?P<job>lilypond|verovio|musescore[34]-(?:base|variant))-p(?P<page>\d+)-(?P<x>\d+)-(?P<y>\d+)$")


def staccatos(labels, space):
    centres = [SimpleNamespace(box=h["box"], y=(h["box"][1] + h["box"][3]) / 2)
               for h in labels if h["class"] in rl.NOTEHEADS]
    changed = 0
    for lab in labels:
        if lab["class"] != "augmentationDot" or lab["from"] != ["augmentationDot"]:
            continue
        dot = SimpleNamespace(box=lab["box"])
        if rl._staccato_dot(dot, centres, space):
            lab["class"] = "staccato"
            changed += 1
    return changed


def bar_numbers(labels, staves, space):
    """Tuplet digits that are a bar number become one text label."""
    digits = sorted((lab for lab in labels if lab["class"] in rl.TUPLETS), key=lambda lab: lab["box"][0])
    runs = []
    for lab in digits:
        for run in runs:
            last = run[-1]["box"]
            if run[0]["from"] == lab["from"] and 0 <= lab["box"][0] - last[2] <= space \
                    and min(lab["box"][3], last[3]) > max(lab["box"][1], last[1]):
                run.append(lab)
                break
        else:
            runs.append([lab])
    drop, add = [], []
    for run in runs:
        box = rl._union([lab["box"] for lab in run])
        if rl._bar_number(SimpleNamespace(text="".join(run[0]["from"]), box=box), staves, space):
            drop += run
            add.append({"class": "text", "box": [round(v, 1) for v in box], "from": run[0]["from"]})
    ids = {id(lab) for lab in drop}
    return [lab for lab in labels if id(lab) not in ids] + add, len(add), len(drop)


def tile_lines(labels, x, y, size=rl.TILE):
    kept = []
    for lab in labels:
        x0, y0, x1, y1 = lab["box"]
        cx0, cy0, cx1, cy1 = max(x0, x), max(y0, y), min(x1, x + size), min(y1, y + size)
        if cx1 <= cx0 or cy1 <= cy0:
            continue
        if (cx1 - cx0) * (cy1 - cy0) < rl.MIN_VISIBLE * (x1 - x0) * (y1 - y0):
            continue
        kept.append((rl.CLASS_INDEX[lab["class"]], (cx0 - x, cy0 - y, cx1 - x, cy1 - y)))
    return rl.yolo_lines(kept)


def same(a, b, tolerance=0.002):
    """Two YOLO label files hold the same boxes, but for the truth files'
    rounding to a tenth of a pixel."""
    rows = lambda text: [tuple(float(v) for v in line.split()) for line in text.splitlines()]
    ra, rb = rows(a), rows(b)
    if len(ra) != len(rb):
        return False
    for p in ra:
        match = next((q for q in rb if q[0] == p[0] and max(abs(u - v) for u, v in zip(p[1:], q[1:])) <= tolerance),
                     None)
        if match is None:
            return False
        rb.remove(match)
    return True

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", default="training")
    parser.add_argument("--write", action="store_true", help="write the corrected files")
    args = parser.parse_args()
    root = paths.require_corpus_dir() / "generated" / args.set
    tiles = defaultdict(list)
    for split in ("train", "val"):
        for f in (root / "detector" / "labels" / split).glob("*.txt"):
            m = STEM.match(f.stem)
            tiles[(m["score"], m["job"], int(m["page"]))].append((f, int(m["x"]), int(m["y"])))
    counts = Counter()
    for (score, job, page), files in sorted(tiles.items()):
        truth_file = root / "pages" / score / job / f"page-{page}.json"
        truth = json.loads(truth_file.read_text(encoding="utf-8"))
        space = truth["staff space px"]
        before = copy.deepcopy(truth["labels"])
        labels = truth["labels"]
        counts["staccatos"] += staccatos(labels, space)
        labels, numbers, dropped = bar_numbers(labels, truth["staves"], space)
        counts["bar numbers"] += numbers
        counts["tuplet digits dropped"] += dropped
        truth["labels"] = labels
        counts["pages"] += 1
        for f, x, y in files:
            old = tile_lines(before, x, y)
            if not same(old, f.read_text(encoding="utf-8")):
                counts["tiles not reproduced"] += 1   # then left as it is
                continue
            new = tile_lines(labels, x, y)
            if new != old:
                counts["tiles changed"] += 1
                if args.write:
                    f.write_text(new, encoding="utf-8")
        if args.write:
            truth_file.write_text(json.dumps(truth), encoding="utf-8")
    print(", ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
