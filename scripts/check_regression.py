"""Run the evaluation harness on the regression set and compare with the baseline (Stage 7).

The set is `regression/` in the repository. By default two stand-in
recognisers are run, `perfect` and `damaged` (fixed seed), until a real
recogniser exists. Each has recorded figures in `regression/baseline.txt`,
a plain-text file, so changes in accuracy show up in ordinary diffs.

The check fails (exit status 1) if any figure is worse than its baseline by
more than the margin, or if more files fail. A figure that is better is
reported and does not fail; update the baseline to keep the gain.

Usage:
  python scripts/check_regression.py                  check against the baseline
  python scripts/check_regression.py --update         record the current figures as the baseline
  python scripts/check_regression.py --recogniser NAME_OR_COMMAND   check another recogniser
  options: --margin POINTS (default 0.1), --musicdiff, --workers N, --out FOLDER
"""

import argparse
import collections
import sys
import tempfile
from pathlib import Path

from omr import parallel, paths
from omr.evaluate import harness
from omr.log import ProgressLog

SET_ROOT = paths.REPO_ROOT / "regression"
BASELINE = SET_ROOT / "baseline.txt"
DEFAULT_RECOGNISERS = ("perfect", "damaged")
DEFAULT_MARGIN = 0.1   # percentage points
HEADER = """# Regression baseline (Stage 7). Written by scripts/check_regression.py --update.
# One line per figure: recogniser | figure | value. Percentages are of the counts shown.
# Update it only on purpose; see docs/notes/regression.md."""

# Figures where a rise is bad, rather than a fall, and figures that must not change.
LOWER_IS_BETTER = {"files failed", "harness errors"}
EXACT = {"files evaluated"}


def pct(part, whole):
    return round(100.0 * part / whole, 2) if whole else None


def figures(results):
    """The figures the check compares, as {name: value}, percentages rounded to 0.01."""
    done = [r for r in results if "harness error" not in r]
    out = collections.OrderedDict()
    out["files evaluated"] = len(done)
    out["harness errors"] = len(results) - len(done)
    out["files failed"] = sum(1 for r in done if "failed" in r)
    exact = sum(r["notes"]["exact"] for r in done)
    whole = sum(r["notes"]["truth"] + r["notes"]["extra"] for r in done)
    out["note accuracy"] = pct(exact, whole)
    out["files structurally correct"] = pct(sum(1 for r in done if r["structure"]["correct"]), len(done))
    exact_pairs = [r for r in done if r.get("meta", {}).get("ground truth") == "exact"]
    found = sum(r["markings"][k]["found"] for r in exact_pairs for k in ("dynamic", "hairpin"))
    truth = sum(r["markings"][k]["truth"] for r in exact_pairs for k in ("dynamic", "hairpin"))
    out["dynamics and hairpins recall"] = pct(found, truth)
    flagged = [r for r in done if "flags" in r]
    if flagged:
        errors = sum(r["notes"]["truth"] - r["notes"]["exact"] + r["notes"]["extra"] for r in done)
        out["note errors in flagged bars"] = pct(sum(r["flags"]["covered"] for r in flagged), errors)
    by_engraver = collections.defaultdict(lambda: [0, 0])
    for r in done:
        key = r.get("meta", {}).get("engraver", r["job"])
        by_engraver[key][0] += r["notes"]["exact"]
        by_engraver[key][1] += r["notes"]["truth"] + r["notes"]["extra"]
    for key in sorted(by_engraver):
        out[f"note accuracy, {key}"] = pct(*by_engraver[key])
    return out


def write_baseline(path, by_recogniser):
    lines = [HEADER]
    for name, figs in by_recogniser.items():
        for key, value in figs.items():
            lines.append(f"{name} | {key} | {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_baseline(path):
    by_recogniser = collections.OrderedDict()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name, key, value = [f.strip() for f in line.split(" | ")]
        by_recogniser.setdefault(name, collections.OrderedDict())[key] = None if value == "None" else float(value)
    return by_recogniser


def compare(name, baseline, current, margin):
    """Returns (worse, better), each a list of plain-text lines."""
    worse, better = [], []
    for key, old in baseline.items():
        new = current.get(key)
        if new is None and old is None:
            continue
        if new is None or old is None:
            worse.append(f"{name}: {key} was {old} and is now {new}.")
        elif key in EXACT:
            if new != old:
                worse.append(f"{name}: {key} was {old:g} and is now {new:g}. The set has changed.")
        elif key in LOWER_IS_BETTER:
            if new > old:
                worse.append(f"{name}: {key} rose from {old:g} to {new:g}.")
            elif new < old:
                better.append(f"{name}: {key} fell from {old:g} to {new:g}.")
        elif new < old - margin:
            worse.append(f"{name}: {key} fell from {old:g} to {new:g} percent (margin {margin:g}).")
        elif new > old + margin:
            better.append(f"{name}: {key} rose from {old:g} to {new:g} percent.")
    for key in current:
        if key not in baseline:
            worse.append(f"{name}: {key} has no baseline. Update the baseline.")
    return worse, better


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recogniser", action="append",
                        help="Recogniser to run; repeat for several (default: perfect and damaged).")
    parser.add_argument("--update", action="store_true", help="Record the current figures as the baseline.")
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN,
                        help=f"Points a percentage may fall (default {DEFAULT_MARGIN}).")
    parser.add_argument("--musicdiff", action="store_true", help="Also run musicdiff (slower; its figures are not compared).")
    parser.add_argument("--workers", type=int, default=min(parallel.DEFAULT_WORKERS, parallel.max_workers()))
    parser.add_argument("--out", help="Where the harness reports go (default: a temporary folder).")
    args = parser.parse_args(argv)
    log = ProgressLog("check-regression")
    if not (SET_ROOT / "index.txt").is_file():
        log.error(f"There is no regression set at {SET_ROOT}. Run scripts/make_regression_snapshot.py.")
        return log.finish("regression check not run")
    recognisers = args.recogniser or list(DEFAULT_RECOGNISERS)
    current = collections.OrderedDict()
    scratch = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="omr-regression-"))
    for name in recognisers:
        label = "".join(c if c.isalnum() else "-" for c in name)[:40]
        results, _ = harness.run("regression", name, log, out_dir=scratch / label, workers=args.workers,
                                 with_musicdiff=args.musicdiff, set_root=SET_ROOT)
        current[name] = figures(results)
        log.info(f"{name}: " + "; ".join(f"{k} {v}" for k, v in current[name].items()
                                         if not k.startswith("note accuracy,")))
    if args.update:
        merged = read_baseline(BASELINE) if BASELINE.is_file() else collections.OrderedDict()
        merged.update(current)
        write_baseline(BASELINE, merged)
        log.info(f"Baseline written to {BASELINE}.")
        return log.finish("baseline updated")
    if not BASELINE.is_file():
        log.error(f"There is no baseline at {BASELINE}. Run with --update to record one.")
        return log.finish("regression check not run")
    recorded = read_baseline(BASELINE)
    failed = False
    for name in current:
        if name not in recorded:
            log.error(f"{name} has no recorded baseline. Run with --update --recogniser {name}.")
            failed = True
            continue
        worse, better = compare(name, recorded[name], current[name], args.margin)
        for line in better:
            log.info("Better: " + line)
        for line in worse:
            log.error("Worse: " + line)
        failed = failed or bool(worse)
    if failed:
        log.error("The regression check failed. If the change is intended, update the baseline "
                  "(docs/notes/regression.md).")
        return log.finish("regression check failed")
    return log.finish("regression check passed")


if __name__ == "__main__":
    sys.exit(main())
