"""Measure the detector's doubt thresholds against the note errors (Stage 2.4).

A detection on a page image becomes a doubt, rule "unsure symbol", when its
confidence is under omr.raster.names.UNSURE or a rival class over the same
symbol is within omr.raster.names.CLOSE of it. To set the two by the flags'
precision and the errors they catch (ACC-4), each pair of a raster set is
read once with every detection made a doubt that carries its numbers, and
the flag file is then scored for each pair of thresholds without reading
again, as scripts/check_flags.py scores it.

The report gives, for exact pairs (MuseScore 4) and all pairs: the flag file
without the rule, with today's thresholds, and over a grid of thresholds
(recall, bars flagged, flagged bars with an error); then, for the symbols of
the classes that change notes, the share whose bar holds a note error by
confidence and by class, which is the rule's precision at each setting.

Usage:
  python scripts/sweep_doubts.py --set-root FOLDER [--job NAME] [--limit N] [--workers N]
                                 [--json FILE] [--out FILE]
  python scripts/sweep_doubts.py --from-json FILE [--out FILE]

The detector and saved detections come from OMR_DETECTOR and
OMR_DETECTIONS_DIR, as for omr evaluate (default: the full run's best.pt
and E:/OMAIRCorpus/detections).
"""

import argparse
import collections
import json
import os
import sys
from pathlib import Path

from omr import parallel, paths
from omr.log import ProgressLog

sys.path.insert(0, str(Path(__file__).parent))
import check_flags  # noqa: E402
import check_notes  # noqa: E402

RULE = "unsure symbol"
UNSURE_GRID = (0.0, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8)
CLOSE_GRID = (None, 0.05, 0.1, 0.15, 0.2, 0.3)
BINS = (0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01)


def measured(cls, conf, other, other_cls):
    """Every detection a doubt, with its numbers in place of the words."""
    return json.dumps([cls, conf, other, other_cls])


def check_pair(pdf, truth_path):
    """The error places and every flag of one pair, with the numbers of
    each detection doubt."""
    from omr.evaluate import events, match, metrics
    from omr.pdf import rules
    from omr.pdf.read import read_pdf
    from omr.raster import names

    names.doubt_of = measured
    truth = events.read(truth_path)
    found, _ = read_pdf(pdf, notes=True)
    result = match.match(truth, found)
    return {"places": metrics.error_places(result),
            "flags": [(f.rule, f.part, f.staff, f.bar, f.reason) for f in rules.check(found)
                      if f.rule != "unsure marking"],
            "bars": sum(found.bar_counts) if found.bar_counts else 0}


def doubted(reason, unsure, close):
    cls, conf, other, _ = json.loads(reason)
    return conf < unsure or (close is not None and other is not None and conf - other <= close)


def with_thresholds(results, unsure, close):
    """The results with the doubt flags those thresholds keep, in the
    form check_flags.figures scores."""
    out = []
    for r in results:
        flags = [f[:4] for f in r["flags"] if f[0] != RULE or doubted(f[4], unsure, close)]
        out.append({"places": r["places"], "flags": flags, "bars": r["bars"]})
    return out


def symbol_precision(results, key):
    """{group: [symbols, symbols whose bar and staff hold a note error]}
    over the detections of the classes that change notes."""
    out = collections.defaultdict(lambda: [0, 0])
    for r in results:
        wrong = {(p, b, s) for where in r["places"] for p, b, s in where}
        wrong_part = {(p, b) for where in r["places"] for p, b, s in where}
        for rule, part, staff, bar, reason in r["flags"]:
            if rule != RULE:
                continue
            group = key(json.loads(reason))
            out[group][0] += 1
            hit = (part, bar) in wrong_part if staff is None else (part, bar, staff) in wrong or (part, bar, None) in wrong
            out[group][1] += hit
    return out


def conf_bin(numbers):
    conf = numbers[1]
    low = max(b for b in BINS if b <= conf) if conf >= BINS[0] else 0.0
    high = min(b for b in BINS if b > conf)
    return f"{low:.2f} to {min(high, 1.0):.2f}"


def report(results):
    lines = ["# Detector doubt thresholds against the note errors (Stage 2.4, ACC-4)", ""]
    groups = (("Exact pairs", check_flags.is_exact), ("All pairs", lambda j: True))
    for title, keep_job in groups:
        chosen = [r for (s, j), r in results.items() if keep_job(j)]
        if not chosen:
            continue
        lines += [f"## {title} ({len(chosen)} pairs)", ""]
        without = check_flags.figures(with_thresholds(chosen, 0.0, None))
        lines += [f"- Without the rule: {check_flags.words(without)}.",
                  f"- Today (under 0.5, rival within 0.15): "
                  f"{check_flags.words(check_flags.figures(with_thresholds(chosen, 0.5, 0.15)))}.", "",
                  "Grid (under, rival within): recall; bars flagged; flagged bars with an error; "
                  "the rule alone's flagged bars with an error:", ""]
        for unsure in UNSURE_GRID:
            for close in CLOSE_GRID:
                if unsure == 0.0 and close is None:
                    continue
                kept = with_thresholds(chosen, unsure, close)
                errors, covered, bars, flagged, with_error = check_flags.figures(kept)
                alone = check_flags.figures(kept, lambda rule: rule == RULE)
                lines.append(f"- {unsure:.2f}, {'none' if close is None else f'{close:.2f}'}: "
                             f"{check_flags.pct(covered, errors)}; {check_flags.pct(flagged, bars)}; "
                             f"{check_flags.pct(with_error, flagged)}; "
                             f"{check_flags.pct(alone[4], alone[3])} of {alone[3]:,}")
        lines += ["", "Symbols whose bar holds a note error, by confidence:", ""]
        for group, (n, hit) in sorted(symbol_precision(chosen, conf_bin).items()):
            lines.append(f"- {group}: {check_flags.pct(hit, n)} of {n:,}")
        lines += ["", "Symbols under 0.5 or with a rival within 0.15, by class (most first):", ""]
        unsure = [r | {"flags": [f for f in r["flags"] if f[0] != RULE or doubted(f[4], 0.5, 0.15)]}
                  for r in chosen]
        by_class = symbol_precision(unsure, lambda numbers: numbers[0])
        for cls, (n, hit) in sorted(by_class.items(), key=lambda kv: -kv[1][0]):
            lines.append(f"- {cls}: {check_flags.pct(hit, n)} of {n:,}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set-root")
    parser.add_argument("--from-json", help="Score the results saved by an earlier run's --json.")
    parser.add_argument("--job", help="Only this engraver job, for example musescore4-base.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--json", help="Also write every pair's error places and flags to this file.")
    parser.add_argument("--out", help="Also write the report to this file.")
    args = parser.parse_args(argv)
    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = ProgressLog("sweep-doubts", path=str(logs / "sweep-doubts.log"))
    if args.from_json:
        saved = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        results = {tuple(k.split("|")): r for k, r in saved.items()}
        failed = 0
    else:
        if not args.set_root:
            parser.error("give --set-root or --from-json")
        corpus = paths.corpus_dir()
        os.environ.setdefault("OMR_DETECTOR", str(corpus / "runs/detector/full/weights/best.pt"))
        os.environ.setdefault("OMR_DETECTIONS_DIR", str(corpus / "detections"))
        todo = check_notes.pairs(args.set_root, args.job, args.limit)
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
        if args.json:
            Path(args.json).write_text(json.dumps({f"{s}|{j}": r for (s, j), r in results.items()}),
                                       encoding="utf-8")
    text = report(results)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        log.info(f"Report written to {args.out}.")
    return log.finish(f"{len(results)} files scored, {failed} failed")


if __name__ == "__main__":
    sys.exit(main())
