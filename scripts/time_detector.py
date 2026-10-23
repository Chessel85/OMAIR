"""CPU time a page of the symbol detector (Stage 2.3).

  python scripts/time_detector.py WEIGHTS [--set development] [--version g300] [--pages 25]
                                  [--space 20] [--device cpu] [--name NAME]

Reads one page from each of a fixed draw of pairs, one page at a time in one
process, and times the detector on it as the converter will run it: the page
scaled to the chosen staff space, cut into tiles, read by the model, and the
boxes put back on the page (omr.raster.detect.detect_page). The page's staff
space comes from its vector PDF and is not timed; in the converter the line
finder measures it. The model is loaded and run once on a blank tile before
the timing. Writes a line a page and the totals to
<corpus>/evaluations/<name>/timing.txt.
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from omr import paths
from omr.corpus import raster_labels as rl
from omr.evaluate import harness


def raster_pdf(set_name, version, pair):
    return paths.corpus_dir() / "generated" / "raster" / f"{set_name}-{version}" / pair.id / pair.job / "score.pdf"


def staff_space_px(vector_pdf, page_index, width_px):
    """The staff space in the raster page's pixels, from the vector reader."""
    import pymupdf

    from omr.pdf import symbols

    doc = pymupdf.open(str(vector_pdf))
    try:
        ps = symbols.read_document(doc)[page_index]
        return ps.staff_space * width_px / doc[page_index].rect.width if ps.staff_space else None
    finally:
        doc.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("weights", type=Path, help="the detector's weights (.onnx or .pt)")
    parser.add_argument("--set", default="development")
    parser.add_argument("--version", default="g300")
    parser.add_argument("--pages", type=int, default=25, help="pages to time, one from each pair drawn")
    parser.add_argument("--space", type=float, default=20, help="staff space in pixels each page is scaled to")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--name", default="s23-onnx-timing")
    args = parser.parse_args()
    if args.set == "check":
        print("The check set stays sealed until a milestone; it is not timed here.")
        return 2
    import pymupdf
    from ultralytics import YOLO

    from omr.raster import detect
    from omr.raster import page as rp

    out_dir = paths.require_corpus_dir() / "evaluations" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs, _ = harness.read_pairs(args.set, paths.corpus_dir() / "generated" / "raster" / f"{args.set}-{args.version}")
    pairs = sorted(pairs, key=lambda p: rl.page_seed("detector timing", p.name))[:args.pages]

    model = YOLO(str(args.weights), task="detect")
    blank = np.full((rl.TILE, rl.TILE), 255, dtype=np.uint8)
    detect.detect_page(model, blank, device=args.device)

    lines, seconds, tiles = [], [], []
    for pair in pairs:
        doc = pymupdf.open(str(raster_pdf(args.set, args.version, pair)))
        try:
            k = rl.page_seed("detector timing page", pair.name) % doc.page_count
            grey, _ = rp.page_image(doc[k])
        finally:
            doc.close()
        space_px = grey is not None and staff_space_px(pair.meta["raster source"], k, grey.shape[1])
        if not space_px:
            lines.append(f"- {pair.name} page {k + 1}: no staff space, skipped.")
            continue
        factor = args.space / space_px
        h, w = round(grey.shape[0] * factor), round(grey.shape[1] * factor)
        n = len(detect.tile_origins(h)) * len(detect.tile_origins(w))
        began = time.perf_counter()
        found = detect.detect_page(model, grey, factor, device=args.device)
        took = time.perf_counter() - began
        seconds.append(took)
        tiles.append(n)
        lines.append(f"- {pair.name} ({pair.meta.get('engraver', 'unknown')}) page {k + 1}: {took:.2f} seconds, "
                     f"{n} tiles, {w} by {h} pixels, {len(found)} symbols.")
        print(lines[-1], flush=True)

    total = [f"Detector CPU timing: {args.weights}, {args.set} {args.version}, staff space {args.space} pixels, "
             f"device {args.device}, one page at a time.",
             f"{len(seconds)} pages: median {statistics.median(seconds):.2f} seconds a page, "
             f"mean {statistics.mean(seconds):.2f}, longest {max(seconds):.2f}, shortest {min(seconds):.2f}.",
             f"Tiles a page: median {statistics.median(tiles):.0f}, {min(tiles)} to {max(tiles)}; "
             f"{sum(seconds) / sum(tiles) * 1000:.0f} ms a tile on average.", ""]
    (out_dir / "timing.txt").write_text("\n".join(total + lines) + "\n", encoding="utf-8")
    print("\n".join(total[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
