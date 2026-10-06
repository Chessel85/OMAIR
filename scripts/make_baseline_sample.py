"""Make the Stage 9 baseline sample: a seeded, stratified subset of the
development set, written as a set folder with its own index.txt.

Scores are grouped by genre and texture, then taken in turn from each group
(round robin, in seeded random order), so rare groups are covered. Every
pair of a chosen score is kept. usage: python scripts/make_baseline_sample.py [--scores N] [--seed N]
"""

import argparse
import random
from collections import defaultdict

from omr import paths
from omr.evaluate import harness


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20261007)
    args = ap.parse_args()
    root = paths.require_corpus_dir() / "generated" / "development"
    pairs, _ = harness.read_pairs("development", root)
    by_score = defaultdict(list)
    for p in pairs:
        by_score[p.id].append(p)
    groups = defaultdict(list)
    for score_id, items in sorted(by_score.items()):
        meta = items[0].meta
        groups[(meta.get("genre", "?"), meta.get("texture", "?"))].append(score_id)
    rng = random.Random(args.seed)
    for ids in groups.values():
        rng.shuffle(ids)
    keys = sorted(groups)
    rng.shuffle(keys)
    chosen = []
    while len(chosen) < args.scores and any(groups.values()):
        for key in keys:
            if groups[key] and len(chosen) < args.scores:
                chosen.append(groups[key].pop())
    out = paths.require_corpus_dir() / "generated" / "baseline-sample"
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# status | id | job | font | pdf | ground-truth MusicXML or reason",
             f"# baseline sample: {len(chosen)} scores of the development set, seed {args.seed}"]
    count = 0
    for score_id in sorted(chosen):
        for p in by_score[score_id]:
            lines.append(f"pair | {p.id} | {p.job} | {p.meta.get('font', '?')} | {p.pdf} | {p.truth}")
            count += 1
    (out / "index.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(chosen)} scores, {count} pairs, in {len(groups)} genre and texture groups, written to {out / 'index.txt'}")


if __name__ == "__main__":
    main()
