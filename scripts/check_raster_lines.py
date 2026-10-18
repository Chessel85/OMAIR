"""Check the lines found in page images against the vector reading (Stage 2.2).

For each pair of a raster set version (made by make_raster_set.py), read the
pair's vector PDF twice, with its own drawings and with the lines found in
the image, and compare the staves, barlines and stems, and the notes each
reading gets right (omr.raster.check). Writes one JSON line per pair to
results.jsonl and the totals to summary.txt in
<corpus>/evaluations/<name>, with a progress log beside them.

usage: python scripts/check_raster_lines.py SET VERSION [VERSION ...] [--name NAME]
           [--workers N] [--limit N] [--engraver NAME]

e.g.   python scripts/check_raster_lines.py regression g300 g200 g150
"""

import argparse
import json
import sys
from pathlib import Path

from omr import parallel, paths
from omr.evaluate import harness
from omr.log import ProgressLog

KINDS = ("staves", "barlines", "stems", "beams", "curves")


def pair_job(pair):
    from omr.raster import check

    vector = Path(pair.meta["raster source"])
    return check.check_pair(vector, pair.pdf, pair.truth)


def percent(part, whole):
    return f"{100 * part / whole:.2f}" if whole else "none"


def summary_lines(results, version):
    """Plain-text totals: over all pairs, then by engraver."""
    def block(rows, title):
        out = [title]
        for kind in KINDS:
            truth = sum(r[kind]["truth"] for r in rows)
            found = sum(r[kind]["found"] for r in rows)
            matched = sum(r[kind]["matched"] for r in rows)
            worst = max((r[kind]["error"] for r in rows), default=0.0)
            out.append(f"- {kind}: {matched} of {truth} found ({percent(matched, truth)} percent); "
                       f"{found - matched} extra; largest position error {worst:.2f} staff spaces.")
        vt = sum(r["notes vector"]["truth"] for r in rows)
        ve = sum(r["notes vector"]["exact"] for r in rows)
        re_ = sum(r["notes raster"]["exact"] for r in rows)
        out.append(f"- notes: vector lines {percent(ve, vt)} percent, image lines {percent(re_, vt)} percent "
                   f"({ve - re_} notes lost of {vt}).")
        return out

    ok = [r for r in results if "error" not in r]
    lines = [f"Stage 2.2 line check, {version}: {len(ok)} pairs read, {len(results) - len(ok)} failed.", ""]
    lines += block(ok, "All pairs:")
    for engraver in sorted({r["engraver"] for r in ok}):
        lines += [""] + block([r for r in ok if r["engraver"] == engraver], f"{engraver}:")
    complete = [r for r in ok if r["staves"]["matched"] == r["staves"]["truth"]]
    lines += ["", f"Pairs with every staff found: {len(complete)} of {len(ok)}."]
    failed = [r for r in results if "error" in r]
    if failed:
        lines += ["", "Failed pairs:"] + [f"- {r['pair']}: {r['error']}" for r in failed]
    return lines


def run_version(set_name, version, out_dir, log, workers, limit, engraver):
    root = paths.require_corpus_dir() / "generated" / "raster" / f"{set_name}-{version}"
    pairs, _ = harness.read_pairs(set_name, root)
    pairs = harness.select_pairs(pairs, engraver=engraver, limit=limit)
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"{set_name}-{version}: {len(pairs)} pairs, {workers} workers.")
    results = []
    with parallel.pool(workers) as executor, open(out_dir / "results.jsonl", "w", encoding="utf-8") as out:
        running = {}

        def collect(done):
            for future, pair in done:
                try:
                    row = future.result()
                except Exception as error:
                    row = {"error": f"{type(error).__name__}: {error}"}
                    log.error(f"{pair.name} failed: {row['error']}")
                row.update({"pair": pair.name, "engraver": pair.meta.get("engraver", "unknown")})
                results.append(row)
                out.write(json.dumps(row) + "\n")
                if len(results) % 25 == 0 or len(results) == len(pairs):
                    log.info(f"{len(results)} of {len(pairs)} pairs checked.")

        for pair in pairs:
            running[executor.submit(pair_job, pair)] = pair
            while len(running) >= workers * 2:
                collect(parallel.finished(running, block=True))
        while running:
            collect(parallel.finished(running, block=True))
    text = summary_lines(results, f"{set_name}-{version}")
    (out_dir / "summary.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    for line in text[2:]:
        if line:
            log.info(line)
    return sum("error" in r for r in results)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("set", help="regression, development or check")
    parser.add_argument("versions", nargs="+", help="g300, g200, g150 or bw300")
    parser.add_argument("--name", default="s22-lines", help="evaluation folder name; the version is added")
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--limit", type=int, help="only the first N pairs, for a trial")
    parser.add_argument("--engraver", help="only pairs from this engraver")
    args = parser.parse_args()
    if args.set == "check":
        print("The check set stays sealed until a milestone; it is not checked here.")
        return 2
    root = paths.require_corpus_dir() / "evaluations"
    root.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("check_raster_lines", root / f"{args.name}.log")
    failed = 0
    for version in args.versions:
        failed += run_version(args.set, version, root / f"{args.name}-{args.set}-{version}", log,
                              args.workers, args.limit, args.engraver)
    return log.finish(f"{len(args.versions)} version(s) checked, {failed} pair(s) failed")


if __name__ == "__main__":
    sys.exit(main())
