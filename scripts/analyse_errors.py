"""Phase 1: where omr's remaining errors are, from one results.json of `omr evaluate`.

Prints a plain-text analysis for choosing what to fix next: how concentrated the
note errors are (the worst files and the accuracy without them), errors above the
best engraving of the same score (the engraver gap), note accuracy and structural
correctness by job, structure failures by mismatch kind (all, one kind only, and
near misses with one or two mismatches), seconds a page, and the worst files with
their commonest error kinds.

usage: python scripts/analyse_errors.py RESULTS.json [--worst N] [--out FILE]
"""

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyse_baselines import STRUCTURE_PATTERNS, pages_of  # noqa: E402


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    results = data if isinstance(data, list) else data["results"]
    return [r for r in results if "harness error" not in r and "failed" not in r]


def whole(r):
    n = r["notes"]
    return n["truth"] + n["extra"] + n["clef errors"]


def errors(r):
    return whole(r) - r["notes"]["exact"]


def pct(a, b):
    return f"{100 * a / b:.2f}" if b else "no data"


def mismatch_kinds(r):
    return {next((name for name, p in STRUCTURE_PATTERNS if p.search(m)), "other")
            for m in r["structure"]["mismatches"]}


def analyse(results, worst, out):
    total_errors = sum(errors(r) for r in results)
    total = sum(whole(r) for r in results)
    out(f"{len(results)} files, note accuracy {pct(total - total_errors, total)} percent, "
        f"{sum(1 for r in results if errors(r))} files with any note error.")

    out("\nConcentration of note errors")
    ranked = sorted(results, key=errors, reverse=True)
    for k in (10, 25, 50, 100, 200):
        e = sum(errors(r) for r in ranked[:k])
        out(f"- worst {k} files: {pct(e, total_errors)} percent of errors; "
            f"accuracy without their errors {pct(total - total_errors + e, total)} percent.")

    out("\nErrors above the best engraving of the same score")
    by_score = defaultdict(list)
    for r in results:
        by_score[r["id"]].append(r)
    gap = Counter()
    for jobs in by_score.values():
        best = min(errors(r) / max(1, whole(r)) for r in jobs)
        for r in jobs:
            gap[r["job"]] += max(0, errors(r) - round(best * whole(r)))
    for job, n in sorted(gap.items()):
        out(f"- {job}: {n}")
    out(f"- all: {sum(gap.values())}, {pct(sum(gap.values()), total_errors)} percent of all errors.")

    out("\nBy job")
    by_job = defaultdict(list)
    for r in results:
        by_job[r["job"]].append(r)
    for job, rs in sorted(by_job.items()):
        e, w = sum(errors(r) for r in rs), sum(whole(r) for r in rs)
        right = sum(r["structure"]["correct"] for r in rs)
        out(f"- {job}: {len(rs)} files, notes {pct(w - e, w)} percent, "
            f"structure {pct(right, len(rs))} percent ({right}).")

    failing = [r for r in results if not r["structure"]["correct"]]
    out(f"\nStructure: {len(failing)} files not structurally correct")
    any_kind, one_kind = Counter(), Counter()
    for r in failing:
        kinds = mismatch_kinds(r)
        any_kind.update(kinds)
        if len(kinds) == 1:
            one_kind.update(kinds)
    out("- files with each kind: " + ", ".join(f"{k} {n}" for k, n in any_kind.most_common()) + ".")
    out(f"- files failing on one kind only ({sum(one_kind.values())}): "
        + ", ".join(f"{k} {n}" for k, n in one_kind.most_common()) + ".")
    out(f"- files with only 1 or 2 mismatches: {sum(1 for r in failing if len(r['structure']['mismatches']) <= 2)}.")

    timed = [(r["seconds"], pages_of(r["pdf"])) for r in results if r.get("seconds") and r.get("pdf")]
    timed = [(s, p) for s, p in timed if p]
    if timed:
        per_page = [s / p for s, p in timed]
        out(f"\nSpeed: {sum(s for s, _ in timed) / sum(p for _, p in timed):.2f} seconds a page overall, "
            f"median {statistics.median(per_page):.2f}, slowest {max(per_page):.2f}, over {len(timed)} files.")

    out(f"\nWorst {worst} files by note errors")
    for r in ranked[:worst]:
        kinds = Counter(e.get("kind", "?") for e in r.get("errors", []) if isinstance(e, dict))
        top = ", ".join(f"{k} {n}" for k, n in kinds.most_common(3))
        out(f"- {r['id']} {r['job']}: {errors(r)} errors, accuracy {pct(r['notes']['exact'], whole(r))} percent; {top}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results")
    parser.add_argument("--worst", type=int, default=50)
    parser.add_argument("--out")
    args = parser.parse_args()
    lines = []
    analyse(load(args.results), args.worst, lines.append)
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    sys.stdout.write(text.encode(sys.stdout.encoding or "utf-8", "replace").decode(sys.stdout.encoding or "utf-8"))


if __name__ == "__main__":
    main()
