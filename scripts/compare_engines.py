"""Compare Engine 1 (the symbol detector path) and Engine 2 (the sequence
reader) bar by bar on the same raster set (Phase 2, Stage 2.6).

Takes two evaluation folders made by `omr evaluate` on the same set, one
with Engine 1 and one with OMR_ENGINE=sequence, and compares each pair's
two MusicXML outputs with the ground truth by the harness's own matching.
A bar of a staff is right for an engine when every true note in it is read
exactly and no extra note is read there. The report counts the staff bars
right in both, in Engine 1 only, in Engine 2 only, and in neither: the bars
right in one engine only are what combining them could gain. Figures are
given for each engraver job and over all pairs.

usage: python scripts/compare_engines.py ENGINE1_FOLDER ENGINE2_FOLDER [--out FILE] [--workers N]
"""

import argparse
import collections
import json
import sys
from pathlib import Path

from omr import parallel, paths
from omr.log import ProgressLog

KINDS = ("both", "engine 1 only", "engine 2 only", "neither")


def right_bars(truth, output_path):
    """{(part, staff, bar): right} over the truth's staff bars that hold notes."""
    from omr.evaluate import events, match as matching

    output = events.read(output_path)
    result = matching.match(events.without_hidden_first_bar(truth), events.without_hidden_first_bar(output))
    right = {}
    for t, _ in result.exact:
        right.setdefault((t.part, t.staff, t.bar), True)
    for wrong in [e.truth for e in result.errors] + result.missing + result.extra:
        right[(wrong.part, wrong.staff, wrong.bar)] = False
    return right


def compare_pair(entry, first, second):
    """Counts of KINDS for one pair, or the reason it was left out."""
    from omr.evaluate import events

    folder = Path(entry["id"]) / entry["job"]
    outputs = [Path(first) / folder / "score.musicxml", Path(second) / folder / "score.musicxml"]
    if not all(p.is_file() for p in outputs):
        return {"left out": "an engine wrote no MusicXML"}
    try:
        truth = events.read(paths.require_corpus_dir() / entry["truth"])
        one, two = (right_bars(truth, p) for p in outputs)
    except events.MusicXMLError as error:
        return {"left out": str(error)[:80]}
    counts = collections.Counter()
    for key in set(one) | set(two):
        a, b = one.get(key, False), two.get(key, False)
        counts[KINDS[0] if a and b else KINDS[1] if a else KINDS[2] if b else KINDS[3]] += 1
    return dict(counts)


def _percent(n, total):
    return f"{100 * n / total:.1f} percent" if total else "none"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("first", type=Path, help="Engine 1's evaluation folder")
    parser.add_argument("second", type=Path, help="Engine 2's evaluation folder")
    parser.add_argument("--out", type=Path, help="Report file (default: engines.txt in Engine 2's folder)")
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    args = parser.parse_args()
    out = args.out or args.second / "engines.txt"
    log = ProgressLog("compare_engines", out.with_suffix(".log"))
    entries = json.loads((args.second / "results.json").read_text(encoding="utf-8"))["results"]
    by_job, left_out = collections.defaultdict(collections.Counter), collections.Counter()
    found = []
    with parallel.pool(args.workers) as executor:
        running = {executor.submit(compare_pair, e, str(args.first), str(args.second)): e for e in entries}
        while running:
            for future, entry in parallel.finished(running, block=True):
                try:
                    found.append((entry, future.result()))
                except Exception as error:   # report and go on with the rest
                    log.error(f"{entry['id']} {entry['job']}: {type(error).__name__}: {error}")
    for entry, counts in found:
        if "left out" in counts:
            left_out[counts["left out"]] += 1
            continue
        by_job[entry["job"]].update(counts)
        by_job["all pairs"].update(counts)
    lines = [f"Engine 1 ({args.first.name}) against Engine 2 ({args.second.name}), staff bars with notes", ""]
    for job in sorted(by_job, key=lambda j: (j == "all pairs", j)):
        c = by_job[job]
        total = sum(c.values())
        lines.append(f"## {job}: {total:,} staff bars")
        lines += [f"- right in {kind}: {c[kind]:,} ({_percent(c[kind], total)})" for kind in KINDS]
        lines.append(f"- Engine 1 right: {_percent(c[KINDS[0]] + c[KINDS[1]], total)}; Engine 2 right: "
                     f"{_percent(c[KINDS[0]] + c[KINDS[2]], total)}; either right: {_percent(total - c[KINDS[3]], total)}")
        lines.append("")
    if left_out:
        lines.append("Pairs left out: " + "; ".join(f"{n} ({why})" for why, n in left_out.most_common()) + ".")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info(f"report written to {out}")
    return log.finish("Engine comparison")


if __name__ == "__main__":
    sys.exit(main())
