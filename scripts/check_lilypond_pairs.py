"""Find LilyPond pairs whose PDF may not show the music of their ground truth.

The LilyPond pairs are made by musicxml2ly and LilyPond from the reference
MusicXML (corpus-sampling.md). Where musicxml2ly loses track of time in a bar
it warns "Negative skip", and the notes it writes after that are moved or
lost, so the PDF does not show the ground truth. This script converts each
reference again (musicxml2ly only, no PDF) and counts those warnings. With a
results.json of `omr evaluate` it adds the reader's note accuracy on the
LilyPond pair and its best accuracy on another engraving of the same score:
a pair with many warnings that reads far worse than the other engravings is
a faulty pair, not a reader fault.

(Comparing LilyPond's MIDI with the reference was tried and dropped: repeats
and the split of parts into tracks made perfect pairs score low.)

usage: python scripts/check_lilypond_pairs.py OUT.txt [IDS...] [--results RESULTS.json]
                                              [--set development] [--workers N]
"""

import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from omr import paths
from omr.corpus import engravers


def count_warnings(score_id, reference):
    _, converter = engravers.lilypond_paths()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            made = subprocess.run([*converter, "-o", str(Path(tmp) / "score.ly"), str(reference)],
                                  capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return score_id, None
    return score_id, made.stderr.count("Negative skip")


def accuracies(results_path):
    """{score id: {job: note accuracy}} from a results.json."""
    data = json.loads(Path(results_path).read_text(encoding="utf-8"))
    out = {}
    for r in (data if isinstance(data, list) else data["results"]):
        if "notes" not in r:
            continue
        n = r["notes"]
        whole = n["truth"] + n["extra"] + n["clef errors"]
        out.setdefault(r["id"], {})[r["job"]] = n["exact"] / whole if whole else 1.0
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out")
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--results")
    parser.add_argument("--set", default="development")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    index = paths.require_corpus_dir() / "generated" / args.set / "index.txt"
    pairs = []
    for line in index.read_text(encoding="utf-8").splitlines():
        fields = line.split(" | ")
        if fields[0] == "pair" and fields[2] == "lilypond" and (not args.ids or fields[1] in args.ids):
            pairs.append((fields[1], fields[5]))
    found = {}
    with ProcessPoolExecutor(args.workers) as pool:
        for future in as_completed([pool.submit(count_warnings, *p) for p in pairs]):
            sid, n = future.result()
            found[sid] = n
    acc = accuracies(args.results) if args.results else {}
    rows = []
    for sid, n in found.items():
        jobs = acc.get(sid, {})
        lily = jobs.get("lilypond")
        others = [v for j, v in jobs.items() if j != "lilypond"]
        rows.append((sid, n, lily, max(others) if others else None))
    rows.sort(key=lambda r: (-(r[1] or 0), r[0]))
    fmt = lambda v: "none" if v is None else f"{100 * v:.1f}"
    lines = ["# score id | Negative skip warnings | reader's LilyPond accuracy | best other engraving"]
    lines += [f"{sid} | {'timeout' if n is None else n} | {fmt(lily)} | {fmt(best)}" for sid, n, lily, best in rows]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    flagged = [r for r in rows if r[1]]
    print(f"{len(rows)} LilyPond pairs, {len(flagged)} with Negative skip warnings. Written to {args.out}.")


if __name__ == "__main__":
    sys.exit(main())
