"""Check the structure read from PDFs (Stage 1.2) against the ground truth.

For each pair of a set (default: the regression set in the repository), the
structure is read from the PDF alone (`omr.pdf.structure`) and compared with
the ground-truth MusicXML: the number of parts and of staves in each, the
number of bars, and the clef, key and time changes, repeats, endings and
navigation marks with their bars. Restated clefs, keys and times are left
out of both, as in the harness (spec decision 11).

Stage 1.2 has no rhythm yet, so a clef change in the middle of a bar is
compared by its bar and by whether it is at the start of the bar, not by its
exact onset (Stage 1.3 adds onsets). A ground-truth clef after the last note
of a bar counts as at the start of the next bar: the two print the same.
Everything else is compared exactly.

A file is structurally right when every item matches. The figures are given
for each engraver job and separately for exact pairs (MuseScore 4, whose
ground truth is the file written with the PDF) and engraver-input pairs
(MuseScore 3, LilyPond, Verovio), whose PDF can legitimately differ from
the reference they were made from.

Usage:
  python scripts/check_structure.py [--set-root FOLDER] [--job NAME] [--limit N]
                                    [--workers N] [--out FILE]
"""

import argparse
import collections
import sys
from pathlib import Path

from omr import parallel, paths
from omr.log import ProgressLog

KINDS = ("clef", "key", "time", "repeat", "ending", "navigation")
CORE = ("parts", "bars", "clef", "key", "time")   # what the Stage 1.2 done condition names


def comparable(score):
    """{kind: Counter of keys} for the structure events, restatements left out."""
    from omr.evaluate import events

    out = collections.defaultdict(collections.Counter)
    for e in events.signature_changes(score):
        if e.kind not in KINDS:
            continue
        if e.kind == "clef":
            bar, start = e.bar, e.onset == 0
            # A clef after the last note of a bar prints the same as one at the
            # start of the next, and files encode it both ways.
            length = score.bars[bar].length if bar < len(score.bars) else 0
            if not start and length and e.onset >= length and bar + 1 < len(score.bars):
                bar, start = bar + 1, True
            out["clef"][(e.part, e.staff or 1, bar, start, e.value)] += 1
        else:
            out[e.kind][(e.part, e.bar, e.value)] += 1
    return out


def describe(kind, key):
    if kind == "clef":
        part, staff, bar, start, value = key
        where = "at the start of" if start else "within"
        return f"a {value} clef {where} bar {bar + 1}, part {part + 1} staff {staff}"
    part, bar, value = key
    return f"{'an' if kind == 'ending' else 'a'} {kind} {value} in bar {bar + 1}, part {part + 1}"


def check_pair(pdf, truth_path):
    """(mismatch lines, counts) for one pair."""
    from omr.evaluate import events
    from omr.pdf import structure

    truth = events.read(truth_path)
    found, _ = structure.read_pdf(pdf)
    lines = []
    if len(truth.parts) != len(found.parts):
        lines.append(f"parts: the ground truth has {len(truth.parts)}, the PDF reading has {len(found.parts)}")
    else:
        for n, (a, b) in enumerate(zip(truth.parts, found.parts)):
            if a.staves != b.staves:
                lines.append(f"part {n + 1}: the ground truth has {a.staves} staves, the PDF reading has {b.staves}")
    if len(truth.bars) != len(found.bars):
        lines.append(f"bars: the ground truth has {len(truth.bars)}, the PDF reading has {len(found.bars)}")
    a, b = comparable(truth), comparable(found)
    kinds = collections.Counter()
    for kind in KINDS:
        missing = a[kind] - b[kind]
        extra = b[kind] - a[kind]
        for key, n in sorted(missing.items()):
            lines.append(f"{kind}: missing {describe(kind, key)}" + (f" ({n} times)" if n > 1 else ""))
        for key, n in sorted(extra.items()):
            lines.append(f"{kind}: extra {describe(kind, key)}" + (f" ({n} times)" if n > 1 else ""))
        if missing or extra:
            kinds[kind] += 1
    if lines and lines[0].startswith(("parts", "part ")):
        kinds["parts"] += 1
    if any(l.startswith("bars") for l in lines):
        kinds["bars"] += 1
    return lines, dict(kinds)


def pairs(set_root, job, limit):
    out = []
    for line in (Path(set_root) / "index.txt").read_text(encoding="utf-8").splitlines():
        fields = [f.strip() for f in line.split("|")]
        if line.startswith("#") or fields[0] != "pair" or (job and fields[2] != job):
            continue
        out.append((fields[1], fields[2], Path(set_root) / fields[4], Path(set_root) / fields[5]))
    return out[:limit] if limit else out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set-root", default=str(paths.REPO_ROOT / "regression"))
    parser.add_argument("--job", help="Only this engraver job, for example musescore4-base.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--out", help="Also write the report to this file.")
    args = parser.parse_args(argv)
    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = ProgressLog("check-structure", path=str(logs / "check-structure.log"))
    todo = pairs(args.set_root, args.job, args.limit)
    if not todo:
        log.error(f"No pairs found in {args.set_root}. Check the folder has an index.txt.")
        return log.finish("0 files checked")
    results = {}
    with parallel.pool(args.workers) as executor:
        running = {executor.submit(check_pair, pdf, truth): (score, job) for score, job, pdf, truth in todo}
        while running:
            for future, (score, job) in parallel.finished(running, block=True):
                try:
                    results[(score, job)] = future.result()
                except Exception as error:   # report and go on with the rest
                    log.error(f"{score} {job}: {error}")
    report = []
    by_job = collections.defaultdict(lambda: [0, 0])
    kinds_by_job = collections.defaultdict(collections.Counter)
    for (score, job), (lines, kinds) in sorted(results.items()):
        by_job[job][1] += 1
        if not lines:
            by_job[job][0] += 1
        kinds_by_job[job].update(kinds)
    report.append("# Structure from PDFs against the ground truth (Stage 1.2)")
    report.append("")
    exact = [j for j in by_job if j.startswith("musescore4")]
    other = [j for j in by_job if not j.startswith("musescore4")]
    core_right = collections.Counter()
    for (score, job), (lines, kinds) in results.items():
        if not set(kinds) & set(CORE):
            core_right[job] += 1
    for title, jobs in (("Exact pairs", exact), ("Engraver-input pairs", other)):
        right = sum(by_job[j][0] for j in jobs)
        core = sum(core_right[j] for j in jobs)
        total = sum(by_job[j][1] for j in jobs)
        if total:
            report.append(f"- {title}: {right} of {total} files structurally right ({100 * right / total:.1f} percent); "
                          f"{core} of {total} right in parts, bars, clefs, keys and times ({100 * core / total:.1f} percent).")
    report.append("")
    report.append("## By job")
    report.append("")
    for job in sorted(by_job):
        right, total = by_job[job]
        kinds = ", ".join(f"{k} {n}" for k, n in kinds_by_job[job].most_common())
        report.append(f"- {job}: {right} of {total} right." + (f" Files with mismatches by kind: {kinds}." if kinds else ""))
    report.append("")
    report.append("## Mismatches")
    for (score, job), (lines, _) in sorted(results.items()):
        if lines:
            report.append("")
            report.append(f"### {score}, {job}")
            report.append("")
            report += [f"- {line}" for line in lines[:12]]
            if len(lines) > 12:
                report.append(f"- and {len(lines) - 12} more")
    text = "\n".join(report)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        log.info(f"Report written to {args.out}.")
    right = sum(v[0] for v in by_job.values())
    return log.finish(f"{len(results)} files checked, {right} structurally right")


if __name__ == "__main__":
    sys.exit(main())
