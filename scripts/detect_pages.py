"""Save the symbol detector's detections for every page of a raster set (Stage 2.4).

Each image page of each pair is turned level, its staff space measured and
read by the detector at 20 pixels a staff space, as `omr convert` reads it
(omr.raster.reading), and the detections are saved in the folder, keyed by
the page image, the model file and the page scale. A later `omr convert` or
`omr evaluate` run with OMR_DETECTIONS_DIR set to the folder and
OMR_DETECTOR set to the same model file reads them back instead of running
the detector, so fixes in the joining code are scored in minutes. Pages
already saved are skipped, so a stopped pass can be started again.

The detector runs in this process (on the GPU with a .pt model); the
levelling and staff space are done in the shared worker pool.

Pausing: before each pair, the pass looks at continue.txt in the
repository's folder, as training does (omr.pause).

usage: python scripts/detect_pages.py SET VERSION [VERSION ...] [--model FILE] [--out FOLDER]
           [--sample N] [--workers N]

e.g.   python scripts/detect_pages.py regression g300 g200 g150
"""

import argparse
import sys
import time
from pathlib import Path

from omr import parallel, paths, pause
from omr.corpus import raster_labels as rl
from omr.evaluate import harness
from omr.log import ProgressLog

DEFAULT_MODEL = Path("runs") / "detector" / "full" / "weights" / "best.pt"
DEFAULT_OUT = Path("detections")


def prepare_job(pdf):
    """Runs in a worker: [(level grey image, scale)] for the image pages of
    a raster PDF, as omr.raster.reading.detect_image reads them."""
    import pymupdf

    from omr.pdf import symbols
    from omr.raster import reading

    doc = pymupdf.open(str(pdf))
    try:
        out = []
        for ps in symbols.read_document(doc):
            if not reading.is_image_page(ps):
                continue
            seen = []
            reading.detect_image(doc[ps.page - 1], lambda grey, factor: seen.append((grey, factor)) or [])
            out += seen
        return out
    finally:
        doc.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("set", help="regression or development")
    parser.add_argument("versions", nargs="+", help="g300, g200, g150 or bw300")
    parser.add_argument("--model", type=Path, help=f"the detector's model (default {DEFAULT_MODEL} in the corpus folder)")
    parser.add_argument("--out", type=Path, help=f"the detections folder (default {DEFAULT_OUT} in the corpus folder)")
    parser.add_argument("--sample", type=int, help="only N pairs, a fixed draw from the set")
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    args = parser.parse_args()
    if args.set == "check":
        print("The check set stays sealed until a milestone; it is not read here.")
        return 2
    from omr.raster import reading

    corpus = paths.require_corpus_dir()
    model = args.model or corpus / DEFAULT_MODEL
    out = args.out or corpus / DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("detect_pages", out / "progress.log")
    raster = corpus / "generated" / "raster"
    pairs, _ = harness.read_pairs(args.set, raster / f"{args.set}-{args.versions[0]}")
    if args.sample and args.sample < len(pairs):
        pairs = sorted(pairs, key=lambda p: rl.page_seed("detector check", p.name))[:args.sample]
    jobs = [(pair, version, raster / f"{args.set}-{version}" / pair.id / pair.job / "score.pdf")
            for pair in pairs for version in args.versions]
    run = reading.detector(model, saved_in=False)
    counts = {"detected": 0}

    def counted(grey, factor):   # runs only for pages not yet saved
        counts["detected"] += 1
        return run(grey, factor)

    save = reading.saving(counted, out, model)
    pause.make_control()
    log.info(f"{model}: {len(pairs)} pairs of {args.set}, versions {', '.join(args.versions)}, into {out}.")
    pages = failed = 0
    started = time.time()
    with parallel.pool(args.workers) as executor:
        running = {}

        def collect(done):
            nonlocal pages, failed
            for future, (pair, version, _) in done:
                pause.wait_while_paused(log)
                try:
                    images = future.result()
                    for grey, factor in images:
                        save(grey, factor)
                        pages += 1
                except Exception as error:
                    failed += 1
                    log.error(f"{pair.name} {version} failed: {type(error).__name__}: {error}")
                collected.append(pair)
                if len(collected) % 50 == 0 or len(collected) == len(jobs):
                    minutes = (time.time() - started) / 60
                    log.info(f"{len(collected)} of {len(jobs)} files: {pages} pages, {counts['detected']} detected, "
                             f"{minutes:.0f} minutes.")

        collected = []
        for job in jobs:
            running[executor.submit(prepare_job, job[2])] = job
            while len(running) >= args.workers * 2:
                collect(parallel.finished(running, block=True))
        while running:
            collect(parallel.finished(running, block=True))
    seconds, detected = time.time() - started, counts["detected"]
    each = f" ({seconds / detected:.1f} seconds each)" if detected else ""
    return log.finish(f"{pages} pages in {len(jobs)} files, {detected} newly detected{each}, "
                      f"{failed} files failed; saved in {out}")


if __name__ == "__main__":
    sys.exit(main())
