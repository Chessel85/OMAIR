"""Measure where each symbol's origin lies in its ink box (Stage 2.4).

  python scripts/measure_anchors.py [--scores 40] [--workers 3]

Reads the vector PDFs of a fixed draw of training-pool scores in every job
(generated/training/index.txt) with the vector reader, and for each name a
detection is given (omr.raster.names.name_for) takes the origin's place in
the ink box, as a share of its width and height from the top left, and the
ink height in staff spaces.

Fonts place some origins differently (a flat in MuseJazz, a handwritten
style, is taller and its origin higher in its box), so the share down the
box is fitted against the box's height: a straight line through the median
(height, share) of each font with at least MIN_FONT glyphs, kept within the
range of those medians. With fewer than three fonts, or heights within 0.3
staff spaces of each other, the line is level at the median share.

Writes the table to src/omr/raster/anchors.json, which omr.raster.names
reads, and prints the figures by font. Training-pool scores only: the
evaluation sets are not looked at.
"""

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

from omr import parallel, paths

OUT = Path(__file__).resolve().parents[1] / "src" / "omr" / "raster" / "anchors.json"
MIN_COUNT = 20      # fewer measurements than this: the name is left to the Bravura reference
MIN_FONT = 10       # glyphs of a font for its median to count in the fit


def read_pdf(job_pdf):
    """[(name, x share, y share, height in staff spaces)] for one PDF."""
    import pymupdf

    from omr.pdf import symbols
    from omr.raster import names

    job, pdf = job_pdf
    out = []
    doc = pymupdf.open(pdf)
    try:
        for ps in symbols.read_document(doc):
            space = ps.staff_space
            if not space:
                continue
            for s in ps.symbols:
                name = names.name_for(s.name)
                x0, y0, x1, y1 = s.box
                if name is None or x1 - x0 <= 0 or y1 - y0 <= 0 or s.size < 3.4 * space:
                    continue   # small glyphs (grace notes, cues) would pull the full height down
                out.append((name, (s.x - x0) / (x1 - x0), (s.y - y0) / (y1 - y0), (y1 - y0) / space))
    finally:
        doc.close()
    return job, out


def fit(points, median):
    """{"slope", "at", "low", "high"}: the share down the box is
    at + slope * (height - median height of the points), within low to high."""
    heights = [h for h, _ in points]
    shares = [y for _, y in points]
    if len(points) < 3 or max(heights) - min(heights) < 0.3:
        return {"slope": 0.0, "at": median, "low": median, "high": median, "middle": 0.0}
    middle = statistics.mean(heights)
    slope = sum((h - middle) * (y - statistics.mean(shares)) for h, y in points) / sum((h - middle) ** 2 for h in heights)
    return {"slope": round(slope, 4), "at": round(statistics.mean(shares), 4),
            "low": round(min(shares), 3), "high": round(max(shares), 3), "middle": round(middle, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scores", type=int, default=40, help="scores drawn from the training pool")
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    args = parser.parse_args()
    index = paths.corpus_dir() / "generated" / "training" / "index.txt"
    rows = [line.split(" | ") for line in index.read_text(encoding="utf-8").splitlines()
            if line.startswith("pair |")]
    ids = sorted({r[1] for r in rows})
    chosen = set(random.Random(24).sample(ids, min(args.scores, len(ids))))
    jobs = [(r[3].strip() or r[2], r[4].strip()) for r in rows if r[1] in chosen]
    by_name = defaultdict(list)
    by_job = defaultdict(lambda: defaultdict(list))
    with parallel.pool(args.workers) as executor:
        for job, found in executor.map(read_pdf, jobs):
            for name, *values in found:
                by_name[name].append(values)
                by_job[name][job].append(values)
    table = {}
    for name in sorted(by_name):
        values = by_name[name]
        if len(values) < MIN_COUNT:
            continue
        table[name] = {key: round(statistics.median(v[k] for v in values), 3)
                       for k, key in enumerate(("x", "y", "height"))}
        points = [(statistics.median(v[2] for v in vs), statistics.median(v[1] for v in vs))
                  for vs in by_job[name].values() if len(vs) >= MIN_FONT]
        table[name].update(fit(points, table[name]["y"]))
        # the full height of the font that draws it smallest, so no font's full-size glyph is taken as small
        table[name]["full"] = round(min((h for h, _ in points), default=table[name]["height"]), 3)
        table[name]["count"] = len(values)
        spread = "; ".join(f"{job} y {statistics.median(v[1] for v in vs):.3f} height "
                           f"{statistics.median(v[2] for v in vs):.2f} ({len(vs)})"
                           for job, vs in sorted(by_job[name].items()))
        print(f"{name}: x {table[name]['x']}, y {table[name]['y']}, height {table[name]['height']}, "
              f"{len(values)} glyphs. By font: {spread}")
    OUT.write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
    print(f"{len(table)} names written to {OUT} from {len(jobs)} PDFs.")


if __name__ == "__main__":
    main()
