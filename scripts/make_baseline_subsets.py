"""Stage 9 follow-up sets, cut from the baseline sample (generated/baseline-sample).

  timing    a small set for clean one-worker timings (OP-2): from each engraver,
            short and long files, chosen by seed. Written to generated/baseline-timing.
  retry RESULTS NAME
            the pairs that failed in RESULTS (a results.json), written to
            generated/NAME, to run again after a wrapper fix.
  merge OLD NEW TARGET
            copy the outputs in OLD, then those in NEW over them, into TARGET,
            so that `omr evaluate --predictions TARGET` scores the whole sample.

usage: python scripts/make_baseline_subsets.py timing [--per-engraver N] [--seed N]
       python scripts/make_baseline_subsets.py retry RESULTS NAME
       python scripts/make_baseline_subsets.py merge OLD NEW TARGET
"""

import argparse
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path

import pymupdf

from omr import paths
from omr.evaluate import harness

HEADER = "# status | id | job | font | pdf | ground-truth MusicXML or reason"


def sample_pairs():
    root = paths.require_corpus_dir() / "generated" / "baseline-sample"
    pairs, _ = harness.read_pairs("development", root)
    return pairs


def write_index(name, comment, pairs):
    out = paths.require_corpus_dir() / "generated" / name
    out.mkdir(parents=True, exist_ok=True)
    lines = [HEADER, f"# {comment}"]
    lines += [f"pair | {p.id} | {p.job} | {p.meta.get('font', '?')} | {p.pdf} | {p.truth}" for p in pairs]
    (out / "index.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(pairs)} pairs written to {out / 'index.txt'}")


def timing(per_engraver, seed):
    """Half short (1 or 2 pages) and half longer (3 to 6 pages), from each engraver."""
    rng = random.Random(seed)
    by_engraver = defaultdict(lambda: ([], []))
    for p in sorted(sample_pairs(), key=lambda p: (p.id, p.job)):
        with pymupdf.open(p.pdf) as doc:
            pages = len(doc)
        if pages <= 6:
            by_engraver[p.meta.get("engraver", "?")][pages >= 3].append(p)
    chosen = []
    for engraver in sorted(by_engraver):
        for group in by_engraver[engraver]:
            rng.shuffle(group)
            taken = []
            for p in group:  # one pair per score, so the scores differ
                if len(taken) < per_engraver // 2 and p.id not in {q.id for q in chosen + taken}:
                    taken.append(p)
            chosen += taken
    write_index("baseline-timing", f"timing set: {len(chosen)} pairs of the baseline sample, seed {seed}", chosen)


def retry(results, name):
    data = json.loads(Path(results).read_text(encoding="utf-8"))["results"]
    failed = {(r["id"], r["job"]) for r in data if "failed" in r}
    pairs = [p for p in sample_pairs() if (p.id, p.job) in failed]
    write_index(name, f"pairs that failed in {results}", pairs)


def merge(old, new, target):
    target = Path(target)
    count = 0
    for folder in (Path(old), Path(new)):
        for xml in folder.glob("*/*/score.musicxml"):
            dest = target / xml.parent.relative_to(folder)
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(xml, dest / "score.musicxml")
            count += 1
    print(f"{count} outputs copied into {target}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("timing")
    t.add_argument("--per-engraver", type=int, default=4)
    t.add_argument("--seed", type=int, default=20261007)
    r = sub.add_parser("retry")
    r.add_argument("results")
    r.add_argument("name")
    m = sub.add_parser("merge")
    m.add_argument("old")
    m.add_argument("new")
    m.add_argument("target")
    args = ap.parse_args()
    if args.cmd == "timing":
        timing(args.per_engraver, args.seed)
    elif args.cmd == "retry":
        retry(args.results, args.name)
    else:
        merge(args.old, args.new, args.target)


if __name__ == "__main__":
    main()
