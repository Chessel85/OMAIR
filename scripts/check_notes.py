"""Check the notes read from PDFs (Stage 1.3) against the ground truth.

For each pair of a set (default: the regression set in the repository), the
score is read from the PDF alone (`omr.pdf.structure.read_pdf` with notes)
and compared with the ground-truth MusicXML by the evaluation harness's own
comparison (`omr.evaluate.metrics.compare_scores`), so the figures are those
`omr evaluate` would give. No MusicXML is written.

The report gives note accuracy (M / (T + E + C)) for each engraver job and
for exact pairs (MuseScore 4) and engraver-input pairs (MuseScore 3,
LilyPond, Verovio), the error mix, and tuplet and onset errors separately,
as the baseline analysis did for Audiveris.

Usage:
  python scripts/check_notes.py [--set-root FOLDER] [--job NAME] [--score ID] [--limit N]
                                [--workers N] [--out FILE] [--json FILE] [--min-accuracy PERCENT]

With --min-accuracy the command fails (exit status 1) if the note accuracy
over all pairs checked is below that percentage, or if any pair could not be
read. CI runs it on the regression set.
"""

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from omr import parallel, paths
from omr.log import ProgressLog

TUPLET = re.compile(r"triplet|tuplet|\d+:\d+")


def check_pair(pdf, truth_path):
    """The harness figures for one pair, without the error words for exact notes."""
    from omr.evaluate import events, metrics
    from omr.pdf import notation, structure

    truth = events.read(truth_path)
    found, _ = structure.read_pdf(pdf, notes=True)
    # bar arithmetic (ACC-5) as flags: each voice that does not fill its bar
    flags = sorted({(f.part, f.bar, f.staff) for f in notation.unfilled_bars(found)})
    figures = metrics.compare_scores(truth, found, flags)
    return {"notes": figures["notes"], "errors": figures["errors"],
            "structure correct": figures["structure"].get("correct"),
            "diagnostics": figures["diagnostics"], "flags": figures["flags"],
            "note marks": figures["note marks"]}


def pairs(set_root, job, limit, score=None):
    out = []
    for line in (Path(set_root) / "index.txt").read_text(encoding="utf-8").splitlines():
        fields = [f.strip() for f in line.split("|")]
        if line.startswith("#") or fields[0] != "pair" or (job and fields[2] != job):
            continue
        if score and fields[1] != score:
            continue
        out.append((fields[1], fields[2], Path(set_root) / fields[4], Path(set_root) / fields[5]))
    return out[:limit] if limit else out


def accuracy(n):
    whole = n["truth"] + n["extra"] + n.get("clef errors", 0)
    return n["exact"] / whole if whole else 1.0


def pct(a, b):
    return f"{100 * a / b:.1f} percent" if b else "none"


class Tally:
    def __init__(self):
        self.exact = self.whole = self.files = 0

    def add(self, n):
        self.exact += n["exact"]
        self.whole += n["truth"] + n["extra"] + n.get("clef errors", 0)
        self.files += 1

    def words(self):
        return f"{pct(self.exact, self.whole)} over {self.files} files"


def report(results):
    lines = ["# Notes from PDFs against the ground truth (Stage 1.3)", ""]
    by_job = collections.defaultdict(Tally)
    groups = {"Exact pairs": Tally(), "Engraver-input pairs": Tally(), "All pairs": Tally()}
    for (score, job), r in results.items():
        by_job[job].add(r["notes"])
        groups["All pairs"].add(r["notes"])
        groups["Exact pairs" if job.startswith("musescore4") else "Engraver-input pairs"].add(r["notes"])
    for title, t in groups.items():
        if t.files:
            lines.append(f"- {title}: note accuracy {t.words()}.")
    lines += ["", "## By job", ""]
    for job, t in sorted(by_job.items()):
        lines.append(f"- {job}: {t.words()}.")
    lines += ["", "## Errors", ""]
    for title, keep in (("Exact pairs", lambda j: j.startswith("musescore4")),
                        ("Engraver-input pairs", lambda j: not j.startswith("musescore4"))):
        chosen = [r for (s, j), r in results.items() if keep(j)]
        if not chosen:
            continue
        n = collections.Counter()
        kinds = collections.Counter()
        for r in chosen:
            for k in ("missing", "extra", "wrong", "clef errors"):
                n[k] += r["notes"].get(k, 0)
            kinds.update(r["notes"].get("wrong by kind", {}))
        total = n["missing"] + n["extra"] + n["wrong"] + n["clef errors"]
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"- {total:,} errors: wrong {n['wrong']:,}, missing {n['missing']:,}, extra {n['extra']:,}, "
                     f"clef {n['clef errors']:,}.")
        lines.append("- Wrong notes by what differs: " + "; ".join(f"{k} {v:,}" for k, v in kinds.most_common()) + ".")
        onset = sum(v for k, v in kinds.items() if "onset" in k and k != "spelling only")
        spurious = missed = 0
        for r in chosen:
            for e in r["errors"]:
                if e["kind"] in ("missing note", "extra note", "clef error"):
                    continue
                exp, found = e.get("expected", ""), e.get("found", "")
                if TUPLET.search(found) and not TUPLET.search(exp):
                    spurious += 1
                elif TUPLET.search(exp) and not TUPLET.search(found):
                    missed += 1
        lines.append(f"- Onset errors (wrong notes whose onset differs): {onset:,}.")
        lines.append(f"- Tuplets: {spurious:,} notes read as tuplets that are not, {missed:,} tuplet notes read "
                     f"as plain notes (together {pct(spurious + missed, n['wrong'])} of the wrong notes).")
        lines.append("")
    lines += ["## Bar arithmetic (ACC-5)", "",
              "Each voice that does not fill its bar is flagged, and the flags are scored as the harness "
              "scores a flag file (ACC-4).", ""]
    for title, keep in (("Exact pairs", lambda j: j.startswith("musescore4")),
                        ("Engraver-input pairs", lambda j: not j.startswith("musescore4"))):
        chosen = [r["flags"] for (s, j), r in results.items() if keep(j) and "flags" in r]
        if not chosen:
            continue
        f = {k: sum(c[k] for c in chosen) for k in ("errors", "covered", "bars flagged", "bars",
                                                     "flagged bars with an error")}
        lines.append(f"- {title}: {f['bars flagged']:,} of {f['bars']:,} bars flagged "
                     f"({pct(f['bars flagged'], f['bars'])}); they hold {pct(f['covered'], f['errors'])} of the "
                     f"note errors; {pct(f['flagged bars with an error'], f['bars flagged'])} of flagged bars "
                     f"have an error.")
    lines += ["", "## Lowest files", ""]
    worst = sorted(results.items(), key=lambda kv: accuracy(kv[1]["notes"]))[:25]
    for (score, job), r in worst:
        n = r["notes"]
        lines.append(f"- {score}, {job}: {pct(n['exact'], n['truth'] + n['extra'] + n.get('clef errors', 0))} "
                     f"({n['truth']} notes, {n['missing']} missing, {n['extra']} extra, {n['wrong']} wrong).")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set-root", default=str(paths.REPO_ROOT / "regression"))
    parser.add_argument("--job", help="Only this engraver job, for example musescore4-base.")
    parser.add_argument("--score", help="Only this score id.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--out", help="Also write the report to this file.")
    parser.add_argument("--json", help="Also write every pair's figures and errors to this file.")
    parser.add_argument("--min-accuracy", type=float, metavar="PERCENT",
                        help="Fail if the note accuracy over all pairs is below this.")
    args = parser.parse_args(argv)
    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = ProgressLog("check-notes", path=str(logs / "check-notes.log"))
    todo = pairs(args.set_root, args.job, args.limit, args.score)
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
        Path(args.json).write_text(json.dumps({f"{s}|{j}": r for (s, j), r in results.items()}, indent=1),
                                   encoding="utf-8")
    exact = sum(r["notes"]["exact"] for r in results.values())
    whole = sum(r["notes"]["truth"] + r["notes"]["extra"] + r["notes"].get("clef errors", 0) for r in results.values())
    if args.min_accuracy is not None and (failed or not whole or 100 * exact / whole < args.min_accuracy):
        log.error(f"Note accuracy {pct(exact, whole)} with {failed} unread pairs; "
                  f"the floor is {args.min_accuracy} percent with every pair read.")
    return log.finish(f"{len(results)} files checked, {failed} failed, note accuracy {pct(exact, whole)}")


if __name__ == "__main__":
    sys.exit(main())
