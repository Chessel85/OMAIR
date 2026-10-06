"""Check the evaluation harness against its two test recognisers (Stage 6).

  perfect   every pair must score 100 percent on every figure
  damaged   every pair must score exactly what its damage.json says

Usage: python scripts/check_harness.py [--set regression] [--limit N] [--workers N] [--no-musicdiff] [--only perfect|damaged]
Each mismatch is listed in plain text; the exit status is 1 if there is any.
musicdiff oddities (a nonzero OMR-NED for a file compared with itself, or a file
it cannot read) are warnings: they are musicdiff's faults, not the harness's.
"""

import argparse
import json
import sys
from pathlib import Path

from omr import parallel, paths
from omr.evaluate import harness, report
from omr.log import ProgressLog


def check_perfect(result):
    """Problems with the project figures. musicdiff's own oddities are returned
    separately, as warnings: they are not faults in the harness."""
    problems = []
    n = result["notes"]
    if "failed" in result:
        return [f"failed: {result['failed']}"]
    if n["exact"] != n["truth"] or n["output"] != n["truth"] or n["extra"] or n["missing"] or n["wrong"]:
        problems.append(f"notes {n}")
    if not result["structure"]["correct"]:
        problems.append(f"structure: {result['structure']['mismatches'][:3]}")
    for kind, f in result["markings"].items():
        if f["found"] != f["truth"] or f["output"] != f["truth"]:
            problems.append(f"{kind}: {f['found']} of {f['truth']} found, {f['output']} in output")
    for name, f in result["diagnostics"].items():
        if next(iter(f.values())) != f["of"]:
            problems.append(f"diagnostic {name}: {f}")
    for name, f in result.get("note marks", {}).items():
        if f["found"] != f["truth"]:
            problems.append(f"{name}: {f}")
    return problems


def musicdiff_oddities(result):
    ned = result.get("musicdiff", {})
    if "failed" in ned:
        return [ned["failed"]]
    return [f"OMR-NED {level} is {m['omr_ned']:.4f} for a file compared with itself"
            for level, m in ned.items() if m["omr_ned"] != 0]


def check_damaged(result, out_dir):
    if "failed" in result:
        return [f"failed: {result['failed']}"]
    damage = json.loads((out_dir / result["id"] / result["job"] / "damage.json").read_text(encoding="utf-8"))
    e = damage["expected"]
    n = result["notes"]
    got = {
        "missing": n["missing"], "extra": n["extra"], "wrong": n["wrong"],
        "pitch": n["wrong by kind"].get("pitch", 0), "duration": n["wrong by kind"].get("duration", 0),
        "spelling only": n["wrong by kind"].get("spelling only", 0),
        "exact": n["exact"], "structure mismatches": len(result["structure"]["mismatches"]),
        "dynamics found": result["markings"]["dynamic"]["found"],
        "covered": result["flags"]["covered"], "bars flagged": result["flags"]["bars flagged"],
        "voice errors": result["diagnostics"]["voice"]["of"] - result["diagnostics"]["voice"]["right"],
    }
    want = {
        "missing": e["missing"], "extra": e["extra"], "wrong": e["wrong"], "pitch": e["pitch"],
        "duration": e["duration"], "spelling only": e["spelling only"],
        "exact": n["truth"] - e["missing"] - e["wrong"], "structure mismatches": e["structure mismatches"],
        "dynamics found": result["markings"]["dynamic"]["truth"] - e["dynamics removed"],
        "covered": e["covered"], "bars flagged": e["bars_flagged"], "voice errors": 0,
    }
    problems = [f"{k}: expected {want[k]}, got {got[k]}" for k in want if want[k] != got[k]]
    if problems:
        problems.append(f"damage: {damage['changes']}; structure: {result['structure']['mismatches'][:3]}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", default="regression", choices=("development", "regression"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--no-musicdiff", action="store_true", help="Skip musicdiff (the slowest step).")
    parser.add_argument("--only", choices=("perfect", "damaged"), help="Run only one of the two test recognisers.")
    args = parser.parse_args(argv)
    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = ProgressLog("check-harness", path=str(logs / "check-harness.log"))
    base = paths.require_corpus_dir() / "evaluations" / "harness-check"
    checked = 0
    for kind, check in (("perfect", lambda r, d: check_perfect(r)), ("damaged", check_damaged)):
        if args.only and kind != args.only:
            continue
        out_dir = base / f"{kind}-{args.set}"
        results, _ = harness.run(args.set, kind, log, out_dir=out_dir, workers=args.workers,
                                 with_musicdiff=(kind == "perfect" and not args.no_musicdiff), limit=args.limit)
        bad = 0
        for result in results:
            checked += 1
            if "harness error" in result:
                log.error(f"{kind}: {result['id']} {result['job']}: {result['harness error']}")
                continue
            problems = check(result, out_dir)
            if kind == "perfect":
                for oddity in musicdiff_oddities(result):
                    log.warning(f"musicdiff: {result['id']} {result['job']}: {oddity}")
            if problems:
                bad += 1
                log.error(f"{kind}: {result['id']} {result['job']}: " + "; ".join(problems))
        log.info(f"{kind}: {len(results) - bad} of {len(results)} pairs scored as expected.")
    return log.finish(f"{checked} harness checks")


if __name__ == "__main__":
    sys.exit(main())
