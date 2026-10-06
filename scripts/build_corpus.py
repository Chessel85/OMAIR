"""Build the development and regression corpora (Stage 5).

Steps, each resumable:
  candidates   read PDMX and OpenScore, apply the metadata filters, label each score
  composers    list the composers of regression candidates, for the owner's review
  select SET   draw the set (development or regression) and write its selection file
  export SET   export every selected score through every engraver
  training     list the training pool without near copies of the selected pieces
  report       count the pairs and failures in the corpus folder

Rules: docs/notes/corpus-sampling.md. Output folder: OMR_CORPUS_DIR.
"""

import argparse
import collections
import sys
from pathlib import Path

from omr import paths
from omr.corpus import config, generate, select, sources
from omr.log import ProgressLog


def make_log(name):
    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    return ProgressLog(name, path=str(logs / f"{name}.log"))


def check_corpus(log):
    try:
        folder = paths.require_corpus_dir()
        free = paths.check_free_space(folder, config.MIN_FREE_GB)
    except paths.CorpusDirError as error:
        log.error(str(error))
        return False
    log.info(f"Corpus folder {folder}, {free:.0f} GB free.")
    return True


def cmd_candidates(args, log):
    candidates = sources.load_or_build(log, refresh=args.refresh)
    by = collections.Counter((c.pool, c.texture) for c in candidates)
    for (pool, tex), n in sorted(by.items()):
        log.info(f"{pool}, {tex}: {n} candidates.")
    genres = collections.Counter((c.pool, c.genre) for c in candidates)
    for (pool, genre), n in sorted(genres.items()):
        log.info(f"{pool}, genre {genre}: {n} candidates.")
    return f"{len(candidates)} labelled candidates"


def cmd_composers(args, log):
    candidates = [c for c in sources.load_or_build(log) if c.pool == "regression" and c.bars <= config.REGRESSION_MAX_BARS]
    known = select.load_composers()
    counts = collections.Counter(c.composer for c in candidates if c.source == "PDMX")
    for composer, n in counts.most_common(args.top):
        mark = "listed" if select.composer_is_public_domain(composer, known) else "not listed"
        print(f"{composer or '(no composer)'}: {n} candidates, {mark}.")
    return f"{len(counts)} distinct composers among regression candidates"


def cmd_select(args, log):
    candidates = sources.load_or_build(log)
    chosen, shortfalls = select.select_set(args.set, candidates, log)
    path = select.write_selection(args.set, chosen, shortfalls)
    log.info(f"Selection written to {path}.")
    return f"{len(chosen)} scores selected for {args.set}, {len(shortfalls)} shortfalls"


def cmd_export(args, log):
    from omr.corpus import roundtrip

    if not check_corpus(log):
        return "stopped before starting"
    candidates = sources.load_or_build(log)
    chosen = [(c, roundtrip.check(c)) for c in select.read_selection(args.set, candidates)]
    if args.limit:
        chosen = chosen[: args.limit]
    made, failed = generate.generate_set(args.set, chosen, log, retry_failures=args.retry_failures)
    return f"{made} exports made, {failed} failed for {args.set}"


def cmd_training(args, log):
    from omr.corpus import training

    kept, copies = training.build(log)
    return f"{len(kept)} training candidates kept, {len(copies)} near copies removed"


def cmd_report(args, log):
    for name in config.SETS:
        index = generate.output_dir(name) / "index.txt"
        if not index.is_file():
            log.info(f"{name}: no index yet.")
            continue
        kinds = collections.Counter(line.split(" | ")[0] for line in index.read_text(encoding="utf-8").splitlines() if not line.startswith("#"))
        log.info(f"{name}: {kinds['pair']} pairs, {kinds['failure']} failures, {generate.folder_size_gb(generate.output_dir(name)):.2f} GB.")
    return "report done"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("candidates")
    p.add_argument("--refresh", action="store_true", help="Rebuild the candidate cache.")
    p = sub.add_parser("composers")
    p.add_argument("--top", type=int, default=200)
    for name in ("select", "export"):
        p = sub.add_parser(name)
        p.add_argument("set", choices=sorted(config.SETS))
        if name == "export":
            p.add_argument("--limit", type=int, help="Only the first N scores.")
            p.add_argument("--retry-failures", action="store_true")
    sub.add_parser("training")
    sub.add_parser("report")
    args = parser.parse_args(argv)
    log = make_log(f"build-corpus-{args.command}")
    try:
        summary = {"candidates": cmd_candidates, "composers": cmd_composers, "select": cmd_select,
                   "export": cmd_export, "training": cmd_training, "report": cmd_report}[args.command](args, log)
    except paths.CorpusDirError as error:
        log.error(str(error))
        summary = "stopped"
    return log.finish(summary)


if __name__ == "__main__":
    sys.exit(main())
