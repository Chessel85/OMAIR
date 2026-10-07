"""Stage 9: run LEGATO over a stratified sample of the baseline sample, a night at a time.

LEGATO takes about 20 minutes a page on the CPU, so it cannot run over the
whole baseline sample. This builds a queue (one MuseScore 4 pair per score, in
seeded round robin over the genre and texture groups, so every night's work
covers a spread) and works down it until a time limit. A pair that already has
a result is skipped, so running the same command again the next night carries
on. A file that would not finish before the limit is left for another night.

usage:
  python scripts/run_legato_sample.py queue [--max-pages N] [--seed N]
  python scripts/run_legato_sample.py run [--hours H] [--minutes-per-page M] [--dry-run]
  python scripts/run_legato_sample.py status

Results, under the corpus folder:
  generated/legato-sample/queue.txt   the queue, in order
  generated/legato-sample/index.txt   the pairs done so far, in set format
  evaluations/legato-sample-preds/<id>/<job>/score.musicxml   LEGATO's output
  evaluations/legato-sample.log       the progress log (one line per event)
"""

import argparse
import random
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from omr import paths
from omr.evaluate import harness
from omr.log import ProgressLog

JOB = "musescore4-base"
SEED = 20261007


def folders():
    root = paths.require_corpus_dir()
    return root / "generated" / "baseline-sample", root / "generated" / "legato-sample", root / "evaluations"


def page_count(pdf):
    import pymupdf
    with pymupdf.open(pdf) as doc:
        return len(doc)


def read_queue(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        order, score_id, job, pages, genre, texture = [f.strip() for f in line.split(" | ")]
        rows.append((int(order), score_id, job, int(pages), genre, texture))
    return rows


def make_queue(args):
    source, target, _ = folders()
    pairs, _ = harness.read_pairs("development", source)
    groups = defaultdict(list)
    skipped = 0
    for p in sorted(pairs, key=lambda p: p.id):
        if p.job != JOB:
            continue
        pages = page_count(p.pdf)
        if pages > args.max_pages:
            skipped += 1
            continue
        groups[(p.meta.get("genre", "?"), p.meta.get("texture", "?"))].append((p, pages))
    rng = random.Random(args.seed)
    for items in groups.values():
        rng.shuffle(items)
    keys = sorted(groups)
    rng.shuffle(keys)
    ordered = []
    while any(groups.values()):
        for key in keys:
            if groups[key]:
                ordered.append((key, *groups[key].pop()))
    target.mkdir(parents=True, exist_ok=True)
    lines = ["# order | id | job | pages | genre | texture",
             f"# LEGATO sample queue: one {JOB} pair per score of the baseline sample, "
             f"scores over {args.max_pages} pages left out, seed {args.seed}"]
    for number, (key, p, pages) in enumerate(ordered, 1):
        lines.append(f"{number} | {p.id} | {p.job} | {pages} | {key[0]} | {key[1]}")
    (target / "queue.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum(item[2] for item in ordered)
    print(f"{len(ordered)} pairs, {total} pages, in {len(groups)} genre and texture groups; "
          f"{skipped} scores left out for length. Written to {target / 'queue.txt'}")
    return 0


def result_folder(preds, score_id):
    return preds / score_id / JOB


def is_done(preds, score_id):
    return (result_folder(preds, score_id) / "score.musicxml").is_file()


def is_failed(preds, score_id):
    return (result_folder(preds, score_id) / "failure.txt").is_file()


def write_index(source, target, preds):
    """An index in set format that lists only the pairs LEGATO has finished."""
    pairs, _ = harness.read_pairs("development", source)
    lines = ["# status | id | job | font | pdf | ground-truth MusicXML or reason",
             "# LEGATO sample: the pairs done so far"]
    for p in sorted(pairs, key=lambda p: p.id):
        if p.job == JOB and is_done(preds, p.id):
            lines.append(f"pair | {p.id} | {p.job} | {p.meta.get('font', '?')} | {p.pdf} | {p.truth}")
    (target / "index.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines) - 2


def run(args):
    source, target, evaluations = folders()
    queue_file = target / "queue.txt"
    if not queue_file.is_file():
        print("There is no queue yet. Run: python scripts/run_legato_sample.py queue", file=sys.stderr)
        return 2
    paths.check_free_space(paths.require_corpus_dir())
    preds = evaluations / "legato-sample-preds"
    preds.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("legato-sample", evaluations / "legato-sample.log")
    pairs = {p.id: p for p in harness.read_pairs("development", source)[0] if p.job == JOB}
    queue = read_queue(queue_file)
    deadline = time.time() + args.hours * 3600
    done_now = pages_now = 0
    todo = [row for row in queue if not is_done(preds, row[1]) and not is_failed(preds, row[1])]
    log.info(f"Starting. {len(queue) - len(todo)} of {len(queue)} queued pairs already have a result. "
             f"Time limit {args.hours} hours, {args.minutes_per_page} minutes a page assumed.")
    while todo:
        remaining = deadline - time.time()
        fit = [row for row in todo if row[3] * args.minutes_per_page * 60 <= remaining]
        if not fit:
            log.info(f"Stopping: none of the {len(todo)} pairs left would finish in the "
                     f"{remaining / 60:.0f} minutes remaining.")
            break
        order, score_id, job, pages, genre, texture = fit[0]
        todo.remove(fit[0])
        out = result_folder(preds, score_id)
        log.info(f"Pair {order}, {score_id}, {pages} page(s), {genre}, {texture}: starting.")
        if args.dry_run:
            continue
        out.mkdir(parents=True, exist_ok=True)
        started = time.time()
        try:
            done = subprocess.run([sys.executable, "-m", "omr.baselines", "legato", str(pairs[score_id].pdf), str(out)],
                                  capture_output=True, text=True, errors="replace",
                                  timeout=pages * args.minutes_per_page * 60 * 2)
            problem = None if done.returncode == 0 else (done.stdout + done.stderr)[-400:]
        except subprocess.TimeoutExpired:
            problem = "took more than twice the expected time and was stopped"
        seconds = time.time() - started
        if problem or not (out / "score.musicxml").is_file():
            (out / "failure.txt").write_text(problem or "no output", encoding="utf-8")
            log.warning(f"Pair {order}, {score_id}: failed after {seconds / 60:.0f} minutes. {problem}")
        else:
            (out / "seconds.txt").write_text(f"{seconds:.0f}\n", encoding="utf-8")
            done_now += 1
            pages_now += pages
            log.info(f"Pair {order}, {score_id}: done in {seconds / 60:.0f} minutes "
                     f"({seconds / 60 / pages:.1f} a page).")
            write_index(source, target, preds)
    total = write_index(source, target, preds)
    left = len([r for r in queue if not is_done(preds, r[1]) and not is_failed(preds, r[1])])
    return log.finish(f"{done_now} pairs ({pages_now} pages) done this run, {total} done in all, {left} still queued")


def status(args):
    source, target, evaluations = folders()
    queue = read_queue(target / "queue.txt")
    preds = evaluations / "legato-sample-preds"
    done = [r for r in queue if is_done(preds, r[1])]
    failed = [r for r in queue if is_failed(preds, r[1])]
    print(f"{len(done)} done ({sum(r[3] for r in done)} pages), {len(failed)} failed, "
          f"{len(queue) - len(done) - len(failed)} still queued ({sum(r[3] for r in queue) - sum(r[3] for r in done + failed)} pages).")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    q = sub.add_parser("queue")
    q.add_argument("--max-pages", type=int, default=4)
    q.add_argument("--seed", type=int, default=SEED)
    r = sub.add_parser("run")
    r.add_argument("--hours", type=float, default=8.5)
    r.add_argument("--minutes-per-page", type=float, default=21)
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args()
    return {"queue": make_queue, "run": run, "status": status}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
