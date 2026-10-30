"""Try combining Engine 1 and Engine 2 from two saved evaluation folders
(Phase 2, Stage 2.7).

Takes the two folders compare_engines.py takes (Engine 1, and Engine 2
with OMR_ENGINE=sequence, on the same set). For each pair it combines the
two MusicXML outputs with omr.raster.combine, and scores Engine 1, Engine 2
and the combined reading against the truth by the harness's own matching.

`run` writes, into OUT: rows.jsonl, one row for each staff bar where the
engines differ (the faults each rule finds in each reading, and which
reading the truth says is right), and pairs.jsonl, the notes exact by each
reading for each pair. `rules` reads rows.jsonl again and reports what each
rule, and each set of weights, would choose, with no matching, so rules can
be weighed quickly; the staff bars right are counted as in compare_engines.
`write` writes each pair's combined reading as MusicXML with its flag file
(Engine 1's flags and the engine-disagreement flags), or with --engine1
Engine 1's reading through the same writer as the control, so that
`omr evaluate --predictions OUT` gives the harness's own figures, ACC-4
included.

usage: python scripts/try_combining.py run E1_FOLDER E2_FOLDER OUT [--every N] [--workers N]
       python scripts/try_combining.py write E1_FOLDER E2_FOLDER OUT [--engine1] [--every N] [--workers N]
       python scripts/try_combining.py rules OUT
"""

import argparse
import collections
import itertools
import json
import sys
from pathlib import Path

from omr import parallel, paths
from omr.log import ProgressLog

# orders of preference on a tie (see omr.raster.combine.combine); the first is the default
CONFIGS = {"mixed, 1, 2; chords 2, 1": (("mixed", 1, 2), (2, 1)), "mixed, 1, 2": (("mixed", 1, 2), None),
           "1, 2": ((1, 2), None)}


def _wrong_staff_bars(result):
    """{(part, staff, bar)} in output bars holding a note the truth does not
    agree with, or lined up with truth bars holding a note the output missed."""
    wrong = {(e.output.part, e.output.staff, e.output.bar) for e in result.errors}
    wrong |= {(n.part, n.staff, n.bar) for n in result.extra}
    back = {t: o for o, t in result.staff_map.items()}
    for n in result.missing:
        staff = back.get((n.part, n.staff))
        segment = result.truth_segment.get(n.bar)
        if staff is None or segment is None:
            continue
        for bar in result.segments[segment].output:
            wrong.add((*staff, bar))
    return wrong


def _flag_entries(path):
    """The entries of a flag file (part and bar counted from 1), or []."""
    return json.loads(path.read_text(encoding="utf-8")).get("flags", []) if path.is_file() else []


def _flags(path):
    """A flag file's flags as events.Flag, part and bar counted from 0."""
    from omr.evaluate import events

    return [events.Flag(f["part"] - 1, f.get("staff"), f["bar"] - 1, "", f.get("reason", ""))
            for f in _flag_entries(path)]


def write_pair(entry, first, second, out, alone):
    """Write the combined reading of one pair (or with `alone` Engine 1's,
    through the same writer, as the control) as OUT/<id>/<job>/score.musicxml,
    with Engine 1's flags and the engine-disagreement flags in flags.json,
    for `omr evaluate --predictions OUT`."""
    from omr import musicxml
    from omr.evaluate import events
    from omr.pdf import rules
    from omr.raster import combine

    folder = Path(entry["id"]) / entry["job"]
    outputs = [Path(first) / folder / "score.musicxml", Path(second) / folder / "score.musicxml"]
    if not all(p.is_file() for p in outputs):
        return "an engine wrote no MusicXML"
    one, two = (events.read(p) for p in outputs)
    entries = _flag_entries(Path(first) / folder / "flags.json")
    if not alone:
        combined = combine.combine(one, two.notes, two.rests, _flags(Path(first) / folder / "flags.json"))
        one.notes, one.rests = combined.notes, combined.rests
        joined = {(e["part"], e.get("staff"), e["bar"]): e for e in entries}
        for b in rules.bar_flags(combine.disagreement_flags(combined)):
            key = (b.part + 1, b.staff, b.bar + 1)
            reason = "; ".join(r for _, r in b.reasons)
            if key in joined:
                joined[key]["reason"] += "; " + reason
                joined[key]["confidence"] = round(joined[key]["confidence"] * b.confidence, 2)
            else:
                joined[key] = {"part": key[0], "bar": key[2], "staff": b.staff, "reason": reason,
                               "confidence": b.confidence}
        entries = list(joined.values())
    target = Path(out) / folder
    target.mkdir(parents=True, exist_ok=True)
    musicxml.write(one, target / "score.musicxml", title=entry["id"])
    (target / "flags.json").write_text(json.dumps({"version": 1, "flags": entries}, indent=1), encoding="utf-8")
    return None


def write(args):
    args.out.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("try_combining", args.out.with_suffix(".log"))
    entries = json.loads((args.second / "results.json").read_text(encoding="utf-8"))["results"][::args.every]
    with parallel.pool(args.workers) as executor:
        running = {executor.submit(write_pair, e, str(args.first), str(args.second), str(args.out), args.engine1): e
                   for e in entries}
        while running:
            for future, entry in parallel.finished(running, block=True):
                try:
                    why = future.result()
                    if why:
                        log.warning(f"{entry['id']} {entry['job']}: left out, {why}")
                except Exception as error:   # report and go on with the rest
                    log.error(f"{entry['id']} {entry['job']}: {type(error).__name__}: {error}")
    return log.finish("Combined readings written")


def try_pair(entry, first, second):
    from omr.evaluate import events, match as matching
    from omr.raster import combine

    folder = Path(entry["id"]) / entry["job"]
    outputs = [Path(first) / folder / "score.musicxml", Path(second) / folder / "score.musicxml"]
    if not all(p.is_file() for p in outputs):
        return {"left out": "an engine wrote no MusicXML"}
    try:
        truth = events.without_hidden_first_bar(events.read(paths.require_corpus_dir() / entry["truth"]))
        one, two = (events.without_hidden_first_bar(events.read(p)) for p in outputs)
    except events.MusicXMLError as error:
        return {"left out": str(error)[:80]}
    flags = _flags(Path(first) / folder / "flags.json")
    results = [matching.match(truth, s) for s in (one, two)]
    wrong = [_wrong_staff_bars(r) for r in results]
    with_music = {(n.part, n.staff, n.bar) for n in one.notes}
    configs = {}
    for name, prefer in CONFIGS.items():   # (order of preference, order where chords differ)
        combined = combine.combine(one, two.notes, two.rests, flags, prefer=prefer[0], chords=prefer[1])
        both = events.Score(one.parts, one.bars, combined.notes, combined.rests, one.markings, one.structure,
                            one.bar_counts, hidden_first_bar=one.hidden_first_bar)
        result = matching.match(truth, both)
        configs[name] = [len(result.exact), len(with_music - _wrong_staff_bars(result))]
        if name == next(iter(CONFIGS)):
            together = combined
    rows = []
    for sb in together.disagree:
        rows.append({"where": list(sb.where), "faults": sb.faults, "chosen": sb.chosen,
                     "right": [sb.where not in wrong[0], sb.where not in wrong[1]],
                     "notes": [len(sb.first[0]), len(sb.second[0])]})
    agree_right = len(with_music - wrong[0] - {tuple(r["where"]) for r in rows})
    agree_wrong = len((with_music & wrong[0]) - {tuple(r["where"]) for r in rows})
    return {"id": entry["id"], "job": entry["job"], "truth notes": len(truth.notes),
            "exact": [len(r.exact) for r in results],
            "staff bars": [len(with_music), len(with_music - wrong[0]), len(with_music - wrong[1])],
            "configs": configs, "agree right": agree_right, "agree wrong": agree_wrong,
            "rows": rows}


def run(args):
    args.out.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("try_combining", args.out / "run.log")
    entries = json.loads((args.second / "results.json").read_text(encoding="utf-8"))["results"]
    entries = entries[::args.every]
    found = []
    with parallel.pool(args.workers) as executor:
        running = {executor.submit(try_pair, e, str(args.first), str(args.second)): e for e in entries}
        while running:
            for future, entry in parallel.finished(running, block=True):
                try:
                    found.append(future.result())
                except Exception as error:   # report and go on with the rest
                    log.error(f"{entry['id']} {entry['job']}: {type(error).__name__}: {error}")
    with open(args.out / "rows.jsonl", "w", encoding="utf-8") as rows, \
            open(args.out / "pairs.jsonl", "w", encoding="utf-8") as pairs:
        for pair in found:
            if "left out" in pair:
                continue
            for row in pair.pop("rows"):
                rows.write(json.dumps({"id": pair["id"], "job": pair["job"], **row}) + "\n")
            pairs.write(json.dumps(pair) + "\n")
    report(args.out)
    return log.finish("Combining trial")


def _percent(n, total):
    return f"{100 * n / total:.2f} percent" if total else "none"


def report(out):
    pairs = [json.loads(line) for line in open(out / "pairs.jsonl", encoding="utf-8")]
    lines = [f"{len(pairs)} pairs", ""]
    names = ["Engine 1", "Engine 2"] + [f"combined ({c})" for c in CONFIGS]
    notes, bars = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for p in pairs:
        for job in (p["job"], "all pairs"):
            notes[job]["total"] += p["truth notes"]
            bars[job]["total"] += p["staff bars"][0]
            for name, n, b in zip(names, p["exact"] + [c[0] for c in p["configs"].values()],
                                  p["staff bars"][1:] + [c[1] for c in p["configs"].values()]):
                notes[job][name] += n
                bars[job][name] += b
    for what, table in (("Notes exact", notes), ("Staff bars right (output bars with notes)", bars)):
        lines.append(f"{what}:")
        for job in sorted(table, key=lambda j: (j == "all pairs", j)):
            t = table[job]
            lines.append(f"- {job}: " + "; ".join(f"{name} {_percent(t[name], t['total'])}" for name in names))
        lines.append("")
    lines += rules_report(out, pairs)
    (out / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def _choose(faults, weights):
    from omr.raster import combine

    return 2 if combine.penalty(faults[1], weights) < combine.penalty(faults[0], weights) else 1


def rules_report(out, pairs=None):
    """Staff bars right with each rule alone, the default weights, and a small grid."""
    from omr.raster import combine

    pairs = pairs or [json.loads(line) for line in open(out / "pairs.jsonl", encoding="utf-8")]
    rows = [json.loads(line) for line in open(out / "rows.jsonl", encoding="utf-8")]
    agree_right = sum(p["agree right"] for p in pairs)
    total = agree_right + sum(p["agree wrong"] for p in pairs) + len(rows)
    one = agree_right + sum(r["right"][0] for r in rows)
    two = agree_right + sum(r["right"][1] for r in rows)
    either = agree_right + sum(any(r["right"]) for r in rows)
    lines = [f"Staff bars with Engine 1 notes: {total:,}; the engines differ in {len(rows):,}",
             f"- Engine 1 always: {_percent(one, total)}; Engine 2 always: {_percent(two, total)}; "
             f"the right one, where one is: {_percent(either, total)}"]

    def score(weights):
        return agree_right + sum(r["right"][_choose(r["faults"], weights) - 1] for r in rows)

    for rule in combine.WEIGHTS:
        lines.append(f"- {rule} alone: {_percent(score({rule: 1}), total)}")
    lines.append(f"- default weights {combine.WEIGHTS}: {_percent(score(combine.WEIGHTS), total)}")
    grid = itertools.product((0, 0.5, 1, 2), (0, 0.1, 0.25, 0.5), (0, 0.5, 1, 2), (0, 0.5, 1, 2))
    best = max(grid, key=lambda w: score(dict(zip(combine.WEIGHTS, w))))
    weights = dict(zip(combine.WEIGHTS, best))
    lines.append(f"- best of the grid {weights}: {_percent(score(weights), total)}")
    lines.append("")
    lines.append("Where they differ, faults found in the right and the wrong reading (one right only):")
    for rule in combine.WEIGHTS:
        c = collections.Counter()
        for r in rows:
            if r["right"][0] != r["right"][1]:
                good, bad = (0, 1) if r["right"][0] else (1, 0)
                c["right has fewer" if r["faults"][good][rule] < r["faults"][bad][rule] else
                  "right has more" if r["faults"][good][rule] > r["faults"][bad][rule] else "same"] += 1
        lines.append(f"- {rule}: " + ", ".join(f"{k} {v:,}" for k, v in sorted(c.items())))
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("first", type=Path)
    r.add_argument("second", type=Path)
    r.add_argument("out", type=Path)
    r.add_argument("--every", type=int, default=1, help="Take every Nth pair")
    r.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    w = sub.add_parser("write")
    w.add_argument("first", type=Path)
    w.add_argument("second", type=Path)
    w.add_argument("out", type=Path)
    w.add_argument("--engine1", action="store_true", help="Write Engine 1's reading alone, as the control")
    w.add_argument("--every", type=int, default=1, help="Take every Nth pair")
    w.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    s = sub.add_parser("rules")
    s.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        return run(args)
    if args.command == "write":
        return write(args)
    print("\n".join(rules_report(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
