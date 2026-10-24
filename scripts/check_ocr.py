"""Score the text read from page images against the vector text (Stage 2.5).

For each pair of a raster set, each image page is read as `omr convert`
reads it (omr.raster.reading, with the detections saved in
OMR_DETECTIONS_DIR where set), and its text runs (omr.raster.text) are
compared with the text runs the vector reader takes from the pair's PDF:
each image run against the vector runs whose middles lie in its box, as
exact runs and the character error rate (spaces left out), italic and bold
right and wrong, and the size error; and the vector runs in no image run.
By engraver and in all. Runs in the shared worker pool; writes summary.txt
and the mismatches to mismatches.txt in OUT.

usage: python scripts/check_ocr.py SET_ROOT OUT [--every N] [--workers N]

e.g.   python scripts/check_ocr.py E:/OMAIRCorpus/generated/raster/regression-g300 E:/OMAIRCorpus/evaluations/s25-ocr-g300
"""

import argparse
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from omr import parallel


def distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def pair_job(raster_pdf, vector_pdf):
    """Runs in a worker: (counts, size errors, mismatch lines) for one pair."""
    import pymupdf

    from omr.pdf import symbols
    from omr.pdf.text import is_bold, is_italic
    from omr.raster import reading

    counts, sizes, lines = Counter(), [], []
    rdoc, vdoc = pymupdf.open(str(raster_pdf)), pymupdf.open(str(vector_pdf))
    vector_pages = symbols.read_document(vdoc)
    raster_pages = symbols.read_document(rdoc)
    _, raster_pages = reading.read_document(rdoc, raster_pages)
    for n, (rp, vp) in enumerate(zip(raster_pages, vector_pages), 1):
        truth = [r for r in vp.text if r.text.strip()]
        used = set()
        for run in rp.text:
            pad = 0.3 * run.size
            mine = sorted((k for k, r in enumerate(truth)
                           if run.box[0] - pad <= (r.box[0] + r.box[2]) / 2 <= run.box[2] + pad
                           and run.box[1] - pad <= (r.box[1] + r.box[3]) / 2 <= run.box[3] + pad),
                          key=lambda k: (round(truth[k].box[1]), truth[k].box[0]))
            used.update(mine)
            want = "".join(truth[k].text for k in mine).replace(" ", "")
            got = run.text.replace(" ", "")
            e = distance(got, want)
            counts["runs"] += 1
            counts["chars"] += len(want)
            counts["errors"] += e
            counts["exact"] += e == 0 and bool(want)
            counts["no vector run"] += not mine
            if e:
                lines.append(f"page {n}: {want!r} read {got!r}")
            if len(mine) == 1 and sum(c.isalpha() for c in want) >= 3:
                r = truth[mine[0]]
                for name, test in (("italic", is_italic), ("bold", is_bold)):
                    t, g = test(r.font), test(run.font)
                    counts[f"{name} {'right' if t == g else 'missed' if t else 'extra'}"] += 1
                sizes.append(run.size / r.size)
        counts["vector runs"] += len(truth)
        for k, r in enumerate(truth):
            if k not in used:
                counts["vector runs missed"] += 1
                lines.append(f"page {n}: vector run {r.text.strip()!r} in no image run")
    return counts, sizes, lines


def pairs(root, every):
    out = []
    for line in (root / "index.txt").read_text(encoding="utf-8").splitlines():
        if not line.startswith("pair |"):
            continue
        _, pid, job, _, pdf, _ = line.split(" | ")
        meta = (Path(pdf).parent / "metadata.txt").read_text(encoding="utf-8")
        fields = dict(l.split(": ", 1) for l in meta.splitlines() if ": " in l)
        out.append((pid, job, fields.get("engraver", job), Path(pdf), Path(fields["raster source"])))
    return out[::every]


def report(totals, sizes):
    t = totals
    out = [f"image runs {t['runs']:,}: exact {100 * t['exact'] / max(1, t['runs']):.1f} percent; "
           f"characters wrong {100 * t['errors'] / max(1, t['chars']):.2f} percent ({t['errors']:,} of {t['chars']:,}); "
           f"with no vector run {t['no vector run']:,}",
           f"vector runs {t['vector runs']:,}, in no image run {t['vector runs missed']:,}"]
    for name in ("italic", "bold"):
        out.append(f"{name}: right {t[f'{name} right']:,}, missed {t[f'{name} missed']:,}, "
                   f"called {name} wrongly {t[f'{name} extra']:,}")
    if sizes:
        q = statistics.quantiles(sizes, n=10)
        out.append(f"size, image over vector: median {statistics.median(sizes):.3f}, "
                   f"10th to 90th percentile {q[0]:.3f} to {q[-1]:.3f}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("set_root", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    args = ap.parse_args()
    todo = pairs(args.set_root, args.every)
    totals, by_engraver = Counter(), defaultdict(Counter)
    sizes, by_engraver_sizes, mismatches = [], defaultdict(list), []
    with parallel.pool(args.workers) as pool:
        running = {pool.submit(pair_job, pdf, src): (pid, job, eng) for pid, job, eng, pdf, src in todo}
        while running:
            for future, (pid, job, eng) in parallel.finished(running, block=True):
                try:
                    counts, sz, lines = future.result()
                except Exception as error:   # reported, and the rest carry on
                    mismatches.append(f"{pid} {job}: failed: {error}")
                    continue
                totals.update(counts)
                by_engraver[eng].update(counts)
                sizes += sz
                by_engraver_sizes[eng] += sz
                mismatches += [f"{pid} {job} {l}" for l in lines]
    out = [f"{len(todo)} pairs from {args.set_root}", ""] + report(totals, sizes)
    for eng in sorted(by_engraver):
        out += ["", eng] + report(by_engraver[eng], by_engraver_sizes[eng])
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    (args.out / "mismatches.txt").write_text("\n".join(sorted(mismatches)) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
