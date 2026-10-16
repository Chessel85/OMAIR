"""Write a set folder holding only some pairs of the development set, for a
fast check of a fix on the files it affects:

    omr evaluate --set development --set-root FOLDER --recogniser omr

Pairs are chosen by score id (all jobs, or `id:job` for one), by a file of such
lines, or as the worst N files of a results.json.

usage: python scripts/make_subset.py FOLDER [IDS...] [--from-file FILE]
                                     [--worst N --results RESULTS.json] [--job JOB]
"""

import argparse
import json
import sys
from pathlib import Path

from omr import paths


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder")
    parser.add_argument("ids", nargs="*", help="score ids, or id:job for one pair")
    parser.add_argument("--from-file", help="a file of ids or id:job, one a line")
    parser.add_argument("--worst", type=int, help="the worst N pairs by note errors of --results")
    parser.add_argument("--results")
    parser.add_argument("--job", help="only this job")
    parser.add_argument("--set", default="development")
    args = parser.parse_args()
    wanted = list(args.ids)
    if args.from_file:
        wanted += [line.split("#")[0].strip() for line in Path(args.from_file).read_text(encoding="utf-8").splitlines()]
    if args.worst:
        data = json.loads(Path(args.results).read_text(encoding="utf-8"))
        results = [r for r in (data if isinstance(data, list) else data["results"]) if "notes" in r]
        n = lambda r: r["notes"]["truth"] + r["notes"]["extra"] + r["notes"]["clef errors"] - r["notes"]["exact"]
        wanted += [f"{r['id']}:{r['job']}" for r in sorted(results, key=n, reverse=True)[: args.worst]]
    wanted = [w for w in wanted if w]
    ids = {w for w in wanted if ":" not in w}
    pairs = {tuple(w.split(":", 1)) for w in wanted if ":" in w}
    index = paths.require_corpus_dir() / "generated" / args.set / "index.txt"
    lines = index.read_text(encoding="utf-8").splitlines()
    kept = [lines[0]]
    for line in lines[1:]:
        fields = line.split(" | ")
        if line.startswith("#") or fields[0] != "pair":
            continue
        if args.job and fields[2] != args.job:
            continue
        if fields[1] in ids or (fields[1], fields[2]) in pairs:
            kept.append(line)
    folder = Path(args.folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.txt").write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"{len(kept) - 1} pairs written to {folder / 'index.txt'}.")
    return 0 if len(kept) > 1 else 1


if __name__ == "__main__":
    sys.exit(main())
