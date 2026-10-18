"""Make the raster engines' training data from a set of vector pairs (Stage 2.1).

Each pair's PDF is read by the vector reader. Every page is rendered at a staff
space drawn from 10 to 24 pixels, labelled, checked and varied; a truth file
is written for it, a share of pages is cut into YOLO tiles, and the staves are
cut into homr's training units. The rules are in docs/notes/raster-labels-spec.md.

Output (under --out, by default generated/<set> on the corpus drive):
  pages/<score>/<job>/page-N.json   the truth file of each page
  pages/<score>/<job>/done.json     the pair's counts, so a run can resume
  detector/                         YOLO images, labels and data.yaml
  sequence/                         homr images, token files and index files
  label-check.txt                   the label checks by job

usage: python scripts/make_training_data.py [--set training] [--limit N] [--workers N] [--out FOLDER]
"""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from omr import parallel, paths
from omr.corpus import raster_labels as rl
from omr.log import ProgressLog

SPACE_RANGE = (10.0, 24.0)    # staff space in pixels
DETECTOR_SHARE = 0.02         # share of pages cut into tiles
VALIDATION_SHARE = 0.1        # share of scores kept for validation


def is_validation(score_id):
    return rl.page_seed("split", score_id) % 1000 < VALIDATION_SHARE * 1000


def pair_job(score_id, job, pdf, truth, out, detector_share, sequence):
    """Make one pair's pages, tiles and staff units. Runs in a worker; returns its counts."""
    import pymupdf

    from omr.pdf import symbols

    folder = out / "pages" / score_id / job
    done = folder / "done.json"
    if done.is_file():
        return json.loads(done.read_text(encoding="utf-8"))
    folder.mkdir(parents=True, exist_ok=True)
    split = "val" if is_validation(score_id) else "train"
    counts, fit, unlabelled, pieces = Counter(), Counter(), Counter(), []
    rendered = {}
    doc = pymupdf.open(pdf)
    try:
        pages = symbols.read_document(doc)
        for ps in pages:
            if not ps.staff_space:
                counts["pages without staves"] += 1
                continue
            page = doc[ps.page - 1]
            rng = np.random.default_rng(rl.page_seed(score_id, job, ps.page))
            space_px = float(rng.uniform(*SPACE_RANGE))
            zoom = space_px / ps.staff_space
            grey = rl.render(page, zoom)
            labels, missing, ignored = rl.page_labels(ps, rl.text_characters(page))
            unlabelled.update(missing)
            loose_shapes = rl.unboxed(ps.unnamed, labels)
            ignored = [tuple(v * zoom for v in box) for box in ignored]
            labels = rl.to_pixels(labels, zoom, space_px, grey.shape)
            staff_boxes = rl.staff_boxes_px(ps.evidence.staves, zoom)
            ink = rl.remove_staff_lines(grey < rl.FAINT_INK, staff_boxes)
            labels = rl.drop_duplicates(rl.extend_outlined_text(rl.tighten(labels, ink, space_px), ink, space_px))
            outlined = any(s.source == "outline" for s in ps.symbols)
            # glyph ink only where it shows: some engravers draw white over text
            glyphs = None if outlined else rl.glyph_ink(doc, ps.page, zoom) & (grey < rl.FAINT_INK)
            c, f, p = rl.check_page(labels, ink, space_px, glyphs, ignored)
            if outlined:
                c["unnamed outlined shapes"] += len(loose_shapes)
            counts.update(c)
            fit.update(f)
            pieces += [(ps.page, *piece) for piece in p]
            variations = rl.choose_variations(rng)
            image = rl.apply_variations(grey, variations, rng)
            counts["pages"] += 1
            counts["labels"] += len(labels)
            truth_page = {
                "pdf": str(pdf), "page": ps.page, "staff space px": round(space_px, 3), "zoom": round(zoom, 5),
                "size": list(image.shape[::-1]), "variations": variations,
                "staves": [[round(v, 1) for v in b] for b in staff_boxes],
                "labels": [{"class": l.cls, "box": [round(v, 1) for v in l.box], "from": l.names} for l in labels],
            }
            (folder / f"page-{ps.page}.json").write_text(json.dumps(truth_page), encoding="utf-8")
            if rl.page_seed("detector", score_id, job, ps.page) % 10000 < detector_share * 10000:
                counts["detector pages"] += 1
                seed = rl.page_seed("tiles", score_id, job, ps.page)
                for x, y, tile, kept in rl.tiles(image, labels, seed):
                    stem = f"{score_id}-{job}-p{ps.page}-{x}-{y}"
                    (out / "detector" / "images" / split / f"{stem}.png").write_bytes(rl.png_bytes(tile))
                    (out / "detector" / "labels" / split / f"{stem}.txt").write_text(rl.yolo_lines(kept), encoding="utf-8")
                    counts["tiles"] += 1
            if sequence:
                rendered[ps.page] = (image, zoom, space_px)
        if sequence:
            from omr.corpus import sequence_units

            counts.update(sequence_units.make_units(doc, pages, rendered, truth, score_id, job,
                                                    out / "sequence", split))
    finally:
        doc.close()
    result = {"counts": dict(counts), "fit": [[k[0], k[1], v] for k, v in fit.items()],
              "unlabelled names": dict(unlabelled), "pieces": pieces[:200]}
    done.write_text(json.dumps(result), encoding="utf-8")
    return result


def read_index(index):
    jobs = []
    for line in index.read_text(encoding="utf-8").splitlines():
        fields = [f.strip() for f in line.split(" | ")]
        if fields[0] == "pair":
            _, score_id, job, font, pdf, truth = fields[:6]
            jobs.append((score_id, job, font, Path(pdf), Path(truth)))
    return jobs


def write_report(out, results):
    """label-check.txt: the checks by job (engraver and font)."""
    by_job = defaultdict(lambda: {"counts": Counter(), "fit": Counter(), "names": Counter(), "worst": []})
    for (score_id, job, font), r in results:
        key = f"{job.split('-')[0]}, {font}"
        g = by_job[key]
        g["counts"].update(r["counts"])
        g["fit"].update({(c, k): v for c, k, v in r["fit"]})
        g["names"].update(r["unlabelled names"])
        g["worst"].append((r["counts"].get("unlabelled pieces", 0), f"{score_id} {job}", r["pieces"][:3]))
    lines = ["Label checks for the raster training data (docs/notes/raster-labels-spec.md, \"Checking the labels\").", ""]
    for key in sorted(by_job):
        g = by_job[key]
        c = g["counts"]
        lines.append(f"## {key}")
        lines.append(f"- {c['pages']} pages, {c['labels']} boxes, {c['tiles']} tiles, "
                     f"{c.get('units', 0)} staff units kept of {c.get('units seen', 0)}.")
        lines.append(f"- Boxes outside the image: {c['outside the image']}. Double labels: {c['double labels']}.")
        if c["glyph ink"]:
            share = c["unlabelled glyph ink"] / c["glyph ink"]
            lines.append(f"- Glyph ink with no box: {share:.2%} of the glyph ink, in {c['unlabelled pieces']} pieces.")
        if c["unnamed outlined shapes"]:
            lines.append(f"- Outlined shapes the vector reader could not name, outside every box: {c['unnamed outlined shapes']}.")
        poor = []
        for cls in rl.CLASSES:
            boxes = g["fit"][(cls, "boxes")]
            if boxes:
                rate = g["fit"][(cls, "fit")] / boxes
                if rate < 0.98:
                    poor.append(f"{cls} {rate:.1%} of {boxes} ({g['fit'][(cls, 'within 0.3 spaces')]} more within "
                                f"0.3 staff spaces, {g['fit'][(cls, 'empty')]} empty)")
        lines.append("- Classes whose boxes fit their ink under 98 percent: " + ("; ".join(poor) or "none") + ".")
        names = ", ".join(f"{n} {v}" for n, v in g["names"].most_common(8))
        lines.append(f"- Names with no class: {names or 'none'}.")
        worst = sorted(g["worst"], reverse=True)[:3]
        lines.append("- Most unlabelled pieces: " + "; ".join(
            f"{w[1]} ({w[0]}; first at page, x, y, width, height in pixels: {w[2]})" for w in worst if w[0]) + ".")
        for k in sorted(k for k in c if k.startswith("units dropped")):
            lines.append(f"- {k[0].upper() + k[1:]}: {c[k]}.")
        lines.append("")
    (out / "label-check.txt").write_text("\n".join(lines), encoding="utf-8")


def write_sequence_index(folder):
    """homr's index files ("image,tokens" a line) for each split, short units
    and those over the token limit apart, from the lists the pairs wrote."""
    from omr.corpus import sequence_units

    for split in ("train", "val"):
        short, long = [], []
        for listing in sorted((folder / "lists" / split).glob("*.txt")):
            for line in listing.read_text(encoding="utf-8").splitlines():
                image, tokens, length = line.rsplit(",", 2)
                (short if int(length) <= sequence_units.SHORT_TOKENS else long).append(f"{image},{tokens}\n")
        (folder / f"index-{split}.txt").write_text("".join(short), encoding="utf-8")
        (folder / f"index-{split}-long.txt").write_text("".join(long), encoding="utf-8")


def write_yaml(out):
    names = "\n".join(f"  {i}: {c}" for i, c in enumerate(rl.CLASSES))
    (out / "detector" / "data.yaml").write_text(
        f"path: {(out / 'detector').as_posix()}\ntrain: images/train\nval: images/val\nnames:\n{names}\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", default="training")
    parser.add_argument("--out", type=Path, help="Output folder (default: the set's folder on the corpus drive).")
    parser.add_argument("--limit", type=int, help="Only the first N pairs.")
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--detector-share", type=float, default=DETECTOR_SHARE)
    parser.add_argument("--no-sequence", action="store_true", help="Make no staff units.")
    args = parser.parse_args(argv)
    log = ProgressLog("make-training-data", path=str(paths.REPO_ROOT / "logs" / "make-training-data.log"))
    root = paths.require_corpus_dir()
    source = root / "generated" / args.set
    out = args.out or source
    jobs = read_index(source / "index.txt")
    if args.limit:
        jobs = jobs[: args.limit]
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (out / "detector" / sub).mkdir(parents=True, exist_ok=True)
    write_yaml(out)
    started = time.time()
    results = []
    with parallel.pool(args.workers) as pool:
        running = {}
        for number, (score_id, job, font, pdf, truth) in enumerate(jobs, 1):
            while len(running) >= 2 * args.workers:
                for future, info in parallel.finished(running, block=True):
                    results.append(_collect(future, info, len(jobs), log))
            paths.check_free_space(out)
            running[pool.submit(pair_job, score_id, job, pdf, truth, out, args.detector_share,
                                not args.no_sequence)] = (number, score_id, job, font)
        while running:
            for future, info in parallel.finished(running, block=True):
                results.append(_collect(future, info, len(jobs), log))
    results = [r for r in results if r is not None]
    write_report(out, results)
    if not args.no_sequence:
        write_sequence_index(out / "sequence")
    total = Counter()
    for _, r in results:
        total.update(r["counts"])
    log.info(f"{len(results)} pairs, {total['pages']} pages, {total['tiles']} tiles, "
             f"{total.get('units', 0)} staff units in {(time.time() - started) / 60:.0f} minutes. "
             f"Checks in {out / 'label-check.txt'}.")
    return log.finish(f"{len(results)} of {len(jobs)} pairs made")


def _collect(future, info, count, log):
    number, score_id, job, font = info
    try:
        r = future.result()
    except Exception as error:
        log.error(f"{number} of {count}: {score_id} {job} failed: {error!r}")
        return None
    c = r["counts"]
    log.info(f"{number} of {count}: {score_id} {job}: {c.get('pages', 0)} pages, {c.get('tiles', 0)} tiles, "
             f"{c.get('units', 0)} staff units.")
    return (score_id, job, font), r


if __name__ == "__main__":
    sys.exit(main())
