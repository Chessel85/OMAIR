"""Check the confidence flags (Stage 1.5) against the real note errors (ACC-4).

For each pair of a set (default: the regression set in the repository), the
score is read from the PDF alone (`omr.pdf.structure.read_pdf` with notes),
flagged by the rules layer (`omr.pdf.rules.check`), and compared with the
ground truth by the harness's own comparison, flags included
(`omr.evaluate.metrics.compare_scores`), so the figures are those
`omr evaluate` gives for a flag file.

The report gives, for exact pairs (MuseScore 4) and engraver-input pairs
(MuseScore 3, LilyPond, Verovio) separately: flagging recall (the share of
note errors in flagged bars), the share of bars flagged, and the share of
flagged bars that hold an error; then the same for each rule alone, and the
recall without it, so each rule's worth can be seen.

Usage:
  python scripts/check_flags.py [--set-root FOLDER] [--job NAME] [--score ID] [--limit N]
                                [--workers N] [--out FILE] [--json FILE] [--min-recall PERCENT]

With --min-recall the command fails (exit status 1) if the flagging recall
on exact pairs is below that percentage, or if any pair could not be read.
CI runs it on the regression set.
"""

import argparse
import collections
import json
import sys
from pathlib import Path

from omr import parallel, paths
from omr.log import ProgressLog

sys.path.insert(0, str(Path(__file__).parent))
import check_notes  # noqa: E402


def check_pair(pdf, truth_path):
    """The error places and the flags of one pair, for scoring by rule."""
    from omr.evaluate import events, match, metrics
    from omr.pdf import rules, structure

    truth = events.read(truth_path)
    found, _ = structure.read_pdf(pdf, notes=True)
    result = match.match(truth, found)
    return {"places": metrics.error_places(result),
            "flags": [(f.rule, f.part, f.staff, f.bar) for f in rules.check(found)],
            "bars": sum(found.bar_counts) if found.bar_counts else 0}


def in_flag_file(rule):
    from omr.pdf import rules

    return rule in rules.FLAG_RULES


def figures(results, keep=in_flag_file):
    """(errors, covered, bars, bars flagged, flagged bars with an error),
    scored as metrics._flags scores a flag file."""
    errors = covered = bars = flagged_bars = with_error = 0
    for r in results:
        flagged = collections.defaultdict(set)
        for rule, part, staff, bar in r["flags"]:
            if keep(rule):
                flagged[(part, bar)].add(staff)

        def covers(part, bar, staff):
            staves = flagged.get((part, bar))
            return bool(staves) and (None in staves or staff in staves)

        errors += len(r["places"])
        covered += sum(any(covers(*place) for place in where) for where in r["places"])
        bars += r["bars"]
        flagged_bars += len(flagged)
        with_error += len({(p, b) for where in r["places"] for p, b, s in where if covers(p, b, s)})
    return errors, covered, bars, flagged_bars, with_error


def pct(a, b):
    return check_notes.pct(a, b)


def words(f):
    errors, covered, bars, flagged, with_error = f
    return (f"recall {pct(covered, errors)} ({covered:,} of {errors:,} note errors); "
            f"{pct(flagged, bars)} of bars flagged ({flagged:,} of {bars:,}); "
            f"{pct(with_error, flagged)} of flagged bars have an error")


def is_exact(job):
    return job.startswith("musescore4")


def report(results):
    lines = ["# Confidence flags against the note errors (Stage 1.5, ACC-4)", ""]
    groups = (("Exact pairs", lambda j: is_exact(j)), ("Engraver-input pairs", lambda j: not is_exact(j)),
              ("All pairs", lambda j: True))
    rule_names = sorted({f[0] for r in results.values() for f in r["flags"]})
    for title, keep_job in groups:
        chosen = [r for (s, j), r in results.items() if keep_job(j)]
        if not chosen:
            continue
        whole = figures(chosen)
        lines += [f"## {title}", "", f"- The flag file: {words(whole)}.", "", "By rule:", ""]
        for rule in rule_names:
            alone = figures(chosen, lambda r, rule=rule: r == rule)
            if in_flag_file(rule):
                without = figures(chosen, lambda r, rule=rule: r != rule and in_flag_file(r))
                change = f"Without it, recall is {pct(without[1], without[0])}."
            else:
                added = figures(chosen, lambda r, rule=rule: r == rule or in_flag_file(r))
                change = (f"Report only, not in the flag file; with it, recall would be "
                          f"{pct(added[1], added[0])} with {pct(added[3], added[2])} of bars flagged.")
            lines.append(f"- {rule}: {words(alone)}. {change}")
        lines.append("")
    lines += ["## By job", ""]
    jobs = collections.defaultdict(list)
    for (s, j), r in results.items():
        jobs[j].append(r)
    for job, chosen in sorted(jobs.items()):
        lines.append(f"- {job}: {words(figures(chosen))}.")
    lines += ["", "## Files with the most errors outside flagged bars", ""]
    missed = []
    for (s, j), r in results.items():
        errors, covered = figures([r])[:2]
        missed.append((errors - covered, s, j, errors))
    for n, s, j, errors in sorted(missed, reverse=True)[:20]:
        if n:
            lines.append(f"- {s}, {j}: {n:,} of {errors:,} note errors outside flagged bars.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set-root", default=str(paths.REPO_ROOT / "regression"))
    parser.add_argument("--job", help="Only this engraver job, for example musescore4-base.")
    parser.add_argument("--score", help="Only this score id.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--out", help="Also write the report to this file.")
    parser.add_argument("--json", help="Also write every pair's error places and flags to this file.")
    parser.add_argument("--min-recall", type=float, metavar="PERCENT",
                        help="Fail if the flagging recall on exact pairs is below this.")
    args = parser.parse_args(argv)
    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = ProgressLog("check-flags", path=str(logs / "check-flags.log"))
    todo = check_notes.pairs(args.set_root, args.job, args.limit, args.score)
    if not todo:
        log.error(f"No pairs found in {args.set_root}. Check the folder has an index.txt.")
        return log.finish("0 files checked")
    results = {}
    failed = 0
    with parallel.pool(args.workers) as executor:
        running = {executor.submit(check_pair, pdf, truth): (score, job) for score, job, pdf, truth in todo}
        while running:
            for future, (score, job) in parallel.finished(running, block=True):
                try:
                    results[(score, job)] = future.result()
                except Exception as error:   # report and go on with the rest
                    failed += 1
                    log.error(f"{score} {job}: {type(error).__name__}: {error}")
    text = report(results)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        log.info(f"Report written to {args.out}.")
    if args.json:
        Path(args.json).write_text(json.dumps({f"{s}|{j}": r for (s, j), r in results.items()}),
                                   encoding="utf-8")
    exact = figures([r for (s, j), r in results.items() if is_exact(j)])
    recall = 100 * exact[1] / exact[0] if exact[0] else 100.0
    if args.min_recall is not None and (failed or recall < args.min_recall):
        log.error(f"Flagging recall on exact pairs {pct(exact[1], exact[0])} with {failed} unread pairs; "
                  f"the floor is {args.min_recall} percent with every pair read.")
    return log.finish(f"{len(results)} files checked, {failed} failed, flagging recall on exact pairs "
                      f"{pct(exact[1], exact[0])} with {pct(exact[3], exact[2])} of bars flagged")


if __name__ == "__main__":
    sys.exit(main())
