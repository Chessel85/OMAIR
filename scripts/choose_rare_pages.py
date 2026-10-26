"""Choose the training pages to cut again for the detector's rare classes
(Stage 2.3).

Only 2 percent of training pages were cut into tiles, so classes that appear
on few pages have few boxes. A class is rare if the training tiles hold fewer
than --target of its boxes (tuplet3, the commonest tuplet number, three times
that). For each rare class, rarest first, pages are taken, those with the most
of it first, until the class reaches its target in the tiles kept, or the
pages run out. Only the tiles holding a rare box are counted, as
make_training_data.py --extra-tiles cuts them. A page already cut into tiles
is not taken, and at most --per-score pages of one score, so that a few long
scores do not fill a class. Validation scores are chosen the same way with
--val-target.

The labels are read from the truth files, with relabel_training.py's two
rules applied, since only the tiled pages' truth files were corrected.

Writes LIST (by default rare-pages.txt in the set's folder) and prints, by
class, the boxes in the tiles now and after.

usage: python scripts/choose_rare_pages.py [--set training] [--target 250] [--val-target 30]
                                           [--per-score 4] [--out LIST]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from omr import paths
from omr.corpus import raster_labels as rl

sys.path.insert(0, str(Path(__file__).parent))
import make_training_data as mt  # noqa: E402
import relabel_training as rt  # noqa: E402

MORE = {"tuplet3": 3}
NOT_COUNTED = {"noteheadOther"}   # a catch-all, not a symbol to learn


def tile_counts(root, split):
    have, tiled = Counter(), set()
    for f in (root / "detector" / "labels" / split).glob("*.txt"):
        m = rt.STEM.match(f.stem)
        tiled.add((m["score"], m["job"], int(m["page"])))
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                have[rl.CLASSES[int(line.split()[0])]] += 1
    return have, tiled


def corrected_labels(truth):
    labels = truth["labels"]
    rt.staccatos(labels, truth["staff space px"])
    labels, _, _ = rt.bar_numbers(labels, truth["staves"], truth["staff space px"])
    return labels


def rare_tile_boxes(truth, labels, rare):
    """The boxes, by class, in the tiles of a page that hold a rare box, and
    the number of such tiles (raster_labels.tiles' grid and half-inside rule)."""
    w, h = truth["size"]
    step = rl.TILE - rl.OVERLAP
    count, boxes = 0, Counter()
    for y in range(0, max(1, h - rl.OVERLAP), step):
        for x in range(0, max(1, w - rl.OVERLAP), step):
            kept = []
            for lab in labels:
                x0, y0, x1, y1 = lab["box"]
                cx0, cy0, cx1, cy1 = max(x0, x), max(y0, y), min(x1, x + rl.TILE), min(y1, y + rl.TILE)
                if cx1 > cx0 and cy1 > cy0 and (cx1 - cx0) * (cy1 - cy0) >= rl.MIN_VISIBLE * (x1 - x0) * (y1 - y0):
                    kept.append(lab["class"])
            if any(c in rare for c in kept):
                count += 1
                boxes.update(kept)
    return count, boxes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", default="training")
    parser.add_argument("--target", type=int, default=250)
    parser.add_argument("--val-target", type=int, default=30)
    parser.add_argument("--per-score", type=int, default=4)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    root = paths.require_corpus_dir() / "generated" / args.set
    out = args.out or root / "rare-pages.txt"

    pages = {}
    for f in (root / "pages").glob("*/*/page-*.json"):
        truth = json.loads(f.read_text(encoding="utf-8"))
        pages[(f.parent.parent.name, f.parent.name, truth["page"])] = Counter(
            lab["class"] for lab in corrected_labels(truth))

    have = {split: tile_counts(root, split) for split in ("train", "val")}
    tiled = have["train"][1] | have["val"][1]
    rare = {c for c in rl.CLASSES if c not in NOT_COUNTED and have["train"][0][c] < args.target * MORE.get(c, 1)}
    chosen, report = [], []
    for split, target in (("train", args.target), ("val", args.val_target)):
        got = Counter(have[split][0])
        per_score, tiles, taken = Counter(), 0, 0
        candidates = {k: c for k, c in pages.items() if mt.is_validation(k[0]) == (split == "val") and k not in tiled}
        for cls in sorted(rare, key=lambda c: (sum(v[c] for v in candidates.values()), c)):
            for key in sorted((k for k in candidates if candidates[k][cls]), key=lambda k: -candidates[k][cls]):
                if got[cls] >= target * MORE.get(cls, 1):
                    break
                if key in chosen or per_score[key[0]] >= args.per_score:
                    continue
                score, job, page = key
                truth = json.loads((root / "pages" / score / job / f"page-{page}.json").read_text(encoding="utf-8"))
                n, boxes = rare_tile_boxes(truth, corrected_labels(truth), rare)
                chosen.append(key)
                per_score[score] += 1
                taken += 1
                tiles += n
                got.update(boxes)
        report.append(f"{split}: {taken} pages, {tiles} tiles")
        report += [f"  {c:22} {have[split][0][c]:6} -> {got[c]:6}" for c in rl.CLASSES if c in rare]
    lines = ["classes | " + " ".join(c for c in rl.CLASSES if c in rare)]
    lines += [f"{s} | {j} | {p}" for s, j, p in sorted(chosen)]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(report))
    print(f"{len(chosen)} pages written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
