"""Check the confidence flags (Stage 1.5) against the real note errors (ACC-4).

For each pair of a set (default: the regression set in the repository), the
score is read from the PDF alone (`omr.pdf.read.read_pdf` with notes),
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
                                [--workers N] [--out FILE] [--json FILE] [--log FILE]
                                [--min-recall PERCENT]

A line is logged as each pair finishes: how many are done, how long the pair
took, and about when the run will end. With --json each pair's result is also
kept as it finishes, in a file beside it ending .pairs.jsonl; a run started
again with the same --json goes on from there, reading only the pairs not yet
done (delete that file to start afresh).

While continue.txt in the repository's folder does not say yes (omr.pause),
the run pauses: pairs not started wait, and a pair being read waits at its
next image page or Engine 2 system. The self-check by re-rendering
(omr.selfcheck) runs unless OMR_SELFCHECK is 0.

With --min-recall the command fails (exit status 1) if the flagging recall
on exact pairs is below that percentage, or if any pair could not be read.
CI runs it on the regression set.
"""

import argparse
import collections
import itertools
import json
import sys
import time
from pathlib import Path

from omr import parallel, pause, paths
from omr.log import ProgressLog

sys.path.insert(0, str(Path(__file__).parent))
import check_notes  # noqa: E402


def check_pair(pdf, truth_path):
    """The error places and the flags of one pair, for scoring by rule, and
    the seconds it took to read. Each pair waits first, and at each image
    page and Engine 2 system, while continue.txt does not say yes (omr.pause)."""
    import logging
    import time

    from omr import pause
    from omr.evaluate import events, match, metrics
    from omr.pdf import rules
    from omr.pdf.read import read_pdf

    log = logging.getLogger("check-flags")
    pause.within_pieces(log)
    pause.wait_while_paused(log)
    start = time.monotonic()
    truth = events.read(truth_path)
    found, _ = read_pdf(pdf, notes=True, selfcheck=True)
    result = match.match(truth, found)
    return {"places": metrics.error_places(result),
            "flags": [(f.rule, f.part, f.staff, f.bar) for f in rules.check(found)],
            "bars": sum(found.bar_counts) if found.bar_counts else 0,
            "seconds": round(time.monotonic() - start, 1)}


def kept_file(json_path):
    """The file each pair's result is kept in as it finishes, beside --json."""
    path = Path(json_path)
    return path.with_name(path.stem + ".pairs.jsonl")


def read_kept(path):
    """{(score, job): result} kept by an earlier start of the run. A last line
    cut short when the run was stopped is left out (that pair is read again)."""
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            out[(entry["score"], entry["job"])] = entry["result"]
        except (ValueError, KeyError, TypeError):
            continue
    return out


def duration(seconds):
    """Seconds in words: "3 hours 5 minutes", "12 minutes", "under a minute"."""
    minutes = round(seconds / 60)
    if minutes < 1:
        return "under a minute"
    hours, minutes = divmod(minutes, 60)
    words = []
    if hours:
        words.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        words.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return " ".join(words)


def progress_line(done, total, score, job, seconds, rate, now):
    """The line logged as a pair finishes. `rate` is the seconds of running
    (pauses left out) a pair has taken on average in this start of the run,
    or None before there is enough to go on; `now` is time.time()."""
    line = f"{done} of {total} done. {score} {job} took {duration(seconds)}."
    left = total - done
    if not left:
        return line
    if rate is None:
        return line + " Too early to say when the run will end."
    rest = rate * left
    then, today = time.localtime(now + rest), time.localtime(now)
    day = "" if (then.tm_year, then.tm_yday) == (today.tm_year, today.tm_yday) else " on a later day"
    left_words = "Under a minute" if rest < 30 else f"About {duration(rest)}"
    return line + f" {left_words} left, ending about {time.strftime('%H:%M', then)}{day}."


class _NoFile:
    """Stands in for the kept file when there is no --json."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, text):
        pass

    def flush(self):
        pass


class _Clock:
    """Running time with pauses left out, for the estimate of the end, and
    the log lines when a pause by continue.txt starts and ends."""

    def __init__(self, clock=time.time):
        self.time = clock
        self.start = clock()
        self.paused_since = None
        self.paused = 0.0
        self.finished = 0

    def now(self):
        return self.time()

    def look(self, log, running):
        now = self.time()
        if self.paused_since is None and not pause.may_continue():
            self.paused_since = now
            log.info(f"Pausing: {pause.CONTROL} does not say yes. Pairs not started wait; each pair being "
                     f"read ({running} in the pool) waits at its next image page or Engine 2 system. "
                     f"Write yes in it to carry on.")
        elif self.paused_since is not None and pause.may_continue():
            self.paused += now - self.paused_since
            log.info(f"Carrying on after {duration(now - self.paused_since)} paused.")
            self.paused_since = None

    def rate(self, workers):
        """Seconds of running a pair, as the pool goes, or None for now."""
        if self.finished < max(3, workers):
            return None
        now = self.time()
        paused = self.paused + (now - self.paused_since if self.paused_since is not None else 0)
        return (now - self.start - paused) / self.finished


def in_flag_file(rule):
    from omr.pdf import rules

    return rule in rules.FLAG_RULES


def figures(results, keep=in_flag_file):
    """(errors, covered, bars, bars flagged, flagged bars with an error),
    scored as the harness scores a flag file (metrics.flag_coverage)."""
    from omr.evaluate import metrics

    errors = covered = bars = flagged_bars = with_error = 0
    for r in results:
        kept = [(part, bar, staff) for rule, part, staff, bar in r["flags"] if keep(rule)]
        c, f, w = metrics.flag_coverage(r["places"], kept)
        errors += len(r["places"])
        covered += c
        bars += r["bars"]
        flagged_bars += f
        with_error += w
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
                change = (f"Without it, recall is {pct(without[1], without[0])} with "
                          f"{pct(without[3], without[2])} of bars flagged.")
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
    parser.add_argument("--json", help="Also write every pair's error places and flags to this file "
                        "(and keep each as it finishes, to go on from there if the run is stopped).")
    parser.add_argument("--log", help="The progress log (default logs/check-flags.log in the repository).")
    parser.add_argument("--min-recall", type=float, metavar="PERCENT",
                        help="Fail if the flagging recall on exact pairs is below this.")
    args = parser.parse_args(argv)
    log_path = Path(args.log) if args.log else paths.REPO_ROOT / "logs" / "check-flags.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("check-flags", path=str(log_path))
    todo = check_notes.pairs(args.set_root, args.job, args.limit, args.score)
    if not todo:
        log.error(f"No pairs found in {args.set_root}. Check the folder has an index.txt.")
        return log.finish("0 files checked")
    pause.make_control()
    kept = kept_file(args.json) if args.json else None
    wanted = {(s, j) for s, j, *_ in todo}
    results = {k: r for k, r in (read_kept(kept) if kept else {}).items() if k in wanted}
    left = [(s, j, pdf, truth) for s, j, pdf, truth in todo if (s, j) not in results]
    if results:
        log.info(f"Going on from {kept}: {len(results)} of {len(todo)} pairs already done, {len(left)} to read.")
    else:
        log.info(f"{len(todo)} pairs to read with {args.workers} workers.")
    failed = 0
    with parallel.pool(args.workers) as executor, (open(kept, "a", encoding="utf-8") if kept else _NoFile()) as keep:
        # pairs handed out a few at a time, not all at once: with one worker
        # each is read as it is handed out, and its line logged before the next
        waiting, running = iter(left), {}
        ahead = 1 if args.workers == 1 else 2 * args.workers
        clock = _Clock()
        while True:
            clock.look(log, len(running))
            for score, job, pdf, truth in itertools.islice(waiting, max(0, ahead - len(running))):
                running[executor.submit(check_pair, pdf, truth)] = (score, job)
            if not running:
                break
            for future, (score, job) in parallel.finished(running, block=True, timeout=60):
                try:
                    result = future.result()
                except Exception as error:   # report and go on with the rest
                    failed += 1
                    log.error(f"{score} {job}: {type(error).__name__}: {error}")
                    continue
                results[(score, job)] = result
                keep.write(json.dumps({"score": score, "job": job, "result": result}) + "\n")
                keep.flush()
                clock.finished += 1
                log.info(progress_line(len(results) + failed, len(todo), score, job, result.get("seconds", 0),
                                       clock.rate(args.workers), clock.now()))
    # in the set's order, not the order the workers finished in
    results = {(s, j): results[(s, j)] for s, j, *_ in todo if (s, j) in results}
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
