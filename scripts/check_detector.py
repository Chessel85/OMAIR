"""Score the symbol detector against the vector labels of raster pages (Stage 2.3).

For each pair of a raster set, the pair's vector PDF is read and labelled by
the label rule (docs/notes/raster-labels-spec.md), at each version's
resolution, in the shared worker pool. The main process reads each page
image with the detector (omr.raster.detect) and matches its boxes to the
labels: recall and precision by class, the groups the vector reader most
depends on, and the same by engraver. Writes one JSON line per pair and
version to results.jsonl and the totals to summary.txt in
<corpus>/evaluations/<name>, with a progress log beside them.

usage: python scripts/check_detector.py WEIGHTS SET VERSION [VERSION ...] [--name NAME]
           [--sample N] [--space PIXELS] [--conf C] [--device cpu|0] [--workers N]

e.g.   python scripts/check_detector.py runs/scale-wide/weights/best.pt development g300 g200 g150 --sample 60
"""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from omr import parallel, paths
from omr.corpus import raster_labels as rl
from omr.evaluate import harness
from omr.log import ProgressLog

GROUPS = {
    "noteheads": rl.NOTEHEADS,
    "accidentals": ["accidentalSharp", "accidentalFlat", "accidentalNatural", "accidentalDoubleSharp",
                    "accidentalDoubleFlat"],
    "dots": ["augmentationDot"],
    "rests": rl.RESTS,
    "clefs": rl.CLEFS,
    "flags": rl.FLAGS,
    "tuplet numbers": rl.TUPLETS,
    "time signatures": rl.TIME,
    "dynamics": rl.DYNAMICS,
}


def raster_pdf(set_name, version, pair):
    return paths.corpus_dir() / "generated" / "raster" / f"{set_name}-{version}" / pair.id / pair.job / "score.pdf"


def label_job(vector_pdf, rasters):
    """Runs in a worker: {version: [(staff space px, [(class, box)]) for each page]}."""
    import pymupdf

    from omr.pdf import symbols
    from omr.raster import detect
    from omr.raster import page as rp

    doc = pymupdf.open(str(vector_pdf))
    try:
        pages = symbols.read_document(doc)
        out = {}
        for version, pdf in rasters.items():
            rdoc = pymupdf.open(str(pdf))
            try:
                rows = []
                for ps in pages:
                    grey, rect = rp.page_image(rdoc[ps.page - 1])
                    if grey is None or not ps.staff_space:
                        rows.append(None)
                        continue
                    zoom = grey.shape[1] / rect.width
                    labels = detect.truth_labels(ps, doc[ps.page - 1], grey, zoom)
                    rows.append((ps.staff_space * zoom, [(lab.cls, lab.box) for lab in labels]))
                out[version] = rows
            finally:
                rdoc.close()
        return out
    finally:
        doc.close()


def detect_pair(model, pdf, rows, space, conf, device):
    """The class counts of one pair's pages, and the pages read."""
    import pymupdf

    from omr.raster import detect
    from omr.raster import page as rp

    totals = defaultdict(Counter)
    doc = pymupdf.open(str(pdf))
    pages = 0
    try:
        for k, row in enumerate(rows):
            if row is None:
                continue
            space_px, truth = row
            grey, _ = rp.page_image(doc[k])
            factor = space / space_px if space else 1.0
            found = detect.detect_page(model, grey, factor, conf=conf, device=device)
            labels = [rl.Label(c, tuple(b)) for c, b in truth]
            for cls, counts in detect.match(labels, found).items():
                totals[cls].update(counts)
            pages += 1
    finally:
        doc.close()
    return {cls: dict(c) for cls, c in totals.items()}, pages


def percent(part, whole):
    return f"{100 * part / whole:.2f}" if whole else "none"


def summary_lines(rows, title):
    by_class = defaultdict(Counter)
    for r in rows:
        for cls, c in r["classes"].items():
            by_class[cls].update(c)

    def line(name, classes):
        t = sum(by_class[c]["truth"] for c in classes)
        f = sum(by_class[c]["found"] for c in classes)
        m = sum(by_class[c]["matched"] for c in classes)
        o = sum(by_class[c]["other class"] for c in classes)
        return (f"- {name}: recall {percent(m, t)} percent ({m} of {t}); precision {percent(m, f)} percent "
                f"({f - m} extra); {o} missed as another class.")

    out = [title, line("all classes", rl.CLASSES)]
    out += [line(g, classes) for g, classes in GROUPS.items()]
    return out, by_class


def write_summary(out_dir, results, versions, seconds):
    lines = [f"Stage 2.3 detector check: {len({r['pair'] for r in results})} pairs.", ""]
    for version in versions:
        rows = [r for r in results if r["version"] == version and "error" not in r]
        pages = sum(r["pages"] for r in rows)
        text, by_class = summary_lines(rows, f"{version}, all engravers ({pages} pages, "
                                             f"{seconds.get(version, 0) / max(pages, 1):.1f} seconds a page to detect):")
        lines += text + [""]
        for engraver in sorted({r["engraver"] for r in rows}):
            text, _ = summary_lines([r for r in rows if r["engraver"] == engraver], f"{version}, {engraver}:")
            lines += text + [""]
        lines.append(f"{version}, every class with labels (recall, precision, labels):")
        for cls in rl.CLASSES:
            c = by_class.get(cls)
            if c and c["truth"]:
                lines.append(f"- {cls}: {percent(c['matched'], c['truth'])}, {percent(c['matched'], c['found'])}, "
                             f"{c['truth']}.")
        lines.append("")
    failed = [r for r in results if "error" in r]
    if failed:
        lines += ["Failed pairs:"] + [f"- {r['pair']} {r['version']}: {r['error']}" for r in failed]
    (out_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("weights", type=Path, help="the detector's weights (.pt or .onnx)")
    parser.add_argument("set", help="regression or development")
    parser.add_argument("versions", nargs="+", help="g300, g200, g150 or bw300")
    parser.add_argument("--name", default="s23-detector", help="evaluation folder name")
    parser.add_argument("--sample", type=int, help="only N pairs, a fixed draw from the set")
    parser.add_argument("--space", type=float, help="scale each page to this staff space in pixels first")
    parser.add_argument("--conf", type=float, default=0.25, help="least confidence kept")
    parser.add_argument("--device", default=None, help="cpu or 0 (the GPU); the default is the GPU if there is one")
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    args = parser.parse_args()
    if args.set == "check":
        print("The check set stays sealed until a milestone; it is not checked here.")
        return 2
    from ultralytics import YOLO

    out_dir = paths.require_corpus_dir() / "evaluations" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("check_detector", out_dir / "progress.log")
    pairs, _ = harness.read_pairs(args.set, paths.corpus_dir() / "generated" / "raster" / f"{args.set}-{args.versions[0]}")
    if args.sample and args.sample < len(pairs):
        # a fixed draw, so every engraver and font is in it and runs compare
        pairs = sorted(pairs, key=lambda p: rl.page_seed("detector check", p.name))[:args.sample]
    model = YOLO(str(args.weights), task="detect")
    log.info(f"{args.weights}: {len(pairs)} pairs of {args.set}, versions {', '.join(args.versions)}, "
             f"staff space {args.space or 'as rendered'}, confidence {args.conf}.")
    results, seconds = [], Counter()
    with parallel.pool(args.workers) as executor, open(out_dir / "results.jsonl", "w", encoding="utf-8") as out:
        running = {}

        def collect(done):
            for future, pair in done:
                try:
                    labels = future.result()
                except Exception as error:
                    log.error(f"{pair.name} labels failed: {type(error).__name__}: {error}")
                    labels = {v: None for v in args.versions}
                for version in args.versions:
                    row = {"pair": pair.name, "version": version, "engraver": pair.meta.get("engraver", "unknown")}
                    if labels[version] is None:
                        row["error"] = "no labels"
                    else:
                        started = time.time()
                        try:
                            row["classes"], row["pages"] = detect_pair(
                                model, raster_pdf(args.set, version, pair), labels[version],
                                args.space, args.conf, args.device)
                        except Exception as error:
                            row["error"] = f"{type(error).__name__}: {error}"
                            log.error(f"{pair.name} {version} failed: {row['error']}")
                        seconds[version] += time.time() - started
                    results.append(row)
                    out.write(json.dumps(row) + "\n")
                done_pairs = len(results) // len(args.versions)
                if done_pairs % 10 == 0 or done_pairs == len(pairs):
                    log.info(f"{done_pairs} of {len(pairs)} pairs checked.")

        for pair in pairs:
            rasters = {v: raster_pdf(args.set, v, pair) for v in args.versions}
            running[executor.submit(label_job, pair.meta["raster source"], rasters)] = pair
            while len(running) >= args.workers * 2:
                collect(parallel.finished(running, block=True))
        while running:
            collect(parallel.finished(running, block=True))
    lines = write_summary(out_dir, results, args.versions, seconds)
    for line in lines:
        if "all engravers" in line or line.startswith("- all classes"):
            log.info(line)
    return log.finish(f"{len(pairs)} pairs checked in {len(args.versions)} version(s); summary in {out_dir / 'summary.txt'}")


if __name__ == "__main__":
    sys.exit(main())
