"""The training pool, without near copies of the selected pieces (spec,
"Keeping the training pool clean").

The pool split by work key stays as it is. The work key misses many
arrangements of one piece, because uploaders write the composer in many ways,
so every training-pool score that is a near copy of a selected piece is removed
here. (The draw itself skips near copies of pieces already chosen.)
"""

from omr import parallel
from omr.corpus import config, labels, roundtrip, select, sources


def selected_pieces(set_names=("development", "regression", "check")):
    """(set, id, title, composer) for every score in the selection files."""
    pieces = []
    for name in set_names:
        path = select.SELECTION_DIR / f"{name}.txt"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            fields = line.split(" | ")
            pieces.append((name, fields[0], fields[5], fields[6]))
    return pieces


def repeated_selections(pieces):
    """Selected scores that are near copies of a score listed before them,
    within a set or across the sets."""
    index = labels.NearCopyIndex([])
    found = []
    for piece in pieces:
        _, _, title, composer = piece
        if index.match(title, composer):
            found.append(piece)
        index.add(title, composer)
    return found


def split_training(candidates, pieces):
    """Return (kept, near copies) from the training-pool candidates."""
    index = labels.NearCopyIndex([(title, composer) for _, _, title, composer in pieces])
    kept, copies = [], []
    for c in candidates:
        (copies if index.match(c.title, c.composer) else kept).append(c)
    return kept, copies


def build(log):
    """Write the training pool and the removed near copies to the corpus work
    folder. Returns (kept, near copies)."""
    pieces = selected_pieces()
    for name, cid, title, composer in repeated_selections(pieces):
        log.warning(f"Selected score {name} {cid} ({title}) is a near copy of a score selected before it.")
    candidates = sources.pdmx_candidates(log, pools=("training",)) + sources.openscore_candidates(log, pools=("training",))
    kept, copies = split_training(candidates, pieces)
    folder = sources.work_dir()
    header = "# Fields: id | source | source path | title | composer\n"
    for filename, rows in (("training-pool.txt", kept), ("training-near-copies.txt", copies)):
        lines = [" | ".join([c.id, c.source, c.source_path, c.title, c.composer]) for c in rows]
        (folder / filename).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    log.info(f"Training pool: {len(candidates)} candidates by metadata, {len(copies)} removed as near copies "
             f"of a selected piece, {len(kept)} kept. Lists are in {folder}.")
    return kept, copies


# ------------------------------------------------- the training draw
#
# Scores for the raster engines' training data (raster-labels-spec.md,
# "Source scores"): the training pool shuffled with the seed, the first
# TRAINING_LABELLED labelled, then taken round robin over the texture and
# genre groups until TRAINING_SIZE pass the round trip.

def pool_candidates(log):
    """The training-pool candidates listed in training-pool.txt, by metadata."""
    listed = sources.work_dir() / "training-pool.txt"
    if not listed.is_file():
        raise FileNotFoundError(f"there is no training pool list at {listed}; run build_corpus.py training first")
    ids = {line.split(" | ")[0] for line in listed.read_text(encoding="utf-8").splitlines()
           if line.strip() and not line.startswith("#")}
    candidates = sources.pdmx_candidates(log, pools=("training",)) + sources.openscore_candidates(log, pools=("training",))
    return [c for c in candidates if c.id in ids]


def round_robin(candidates):
    """The candidates in turn from each (texture, genre) group, each group in
    the order given, so every group is drawn from before any is drawn twice."""
    groups = {}
    for c in candidates:
        groups.setdefault((c.texture, c.genre), []).append(c)
    order = []
    queues = [groups[k] for k in sorted(groups)]
    while any(queues):
        for q in queues:
            if q:
                order.append(q.pop(0))
    return order


def draw(log, size=config.TRAINING_SIZE, labelled=config.TRAINING_LABELLED, workers=parallel.DEFAULT_WORKERS):
    """Return [(candidate, round trip)] for the first `size` candidates, in
    round-robin order, that pass the round trip. Round trips run `workers` at
    a time; the result does not depend on the number of workers."""
    import random

    pool = sorted(pool_candidates(log), key=lambda c: c.id)
    random.Random(config.SEED).shuffle(pool)
    pool = sources.extract_pdmx(pool[:labelled], log)
    order = round_robin(sources.label_candidates(pool, log))
    log.info(f"Training draw: {len(order)} labelled candidates in {len(set((c.texture, c.genre) for c in order))} groups.")
    # Every candidate submitted is finished before the end, so the first `size`
    # passes in draw order are the ones a run with one worker would choose.
    results = {}
    with parallel.pool(workers) as executor:
        running, next_index = {}, 0
        while next_index < len(order) or running:
            passed = sum(t.ok for t in results.values())
            while len(running) < 2 * workers and next_index < len(order) and passed < size:
                running[executor.submit(roundtrip.check, order[next_index])] = next_index
                next_index += 1
            if not running:
                break
            for future, i in parallel.finished(running, block=True):
                trip = results[i] = future.result()
                c = order[i]
                if trip.ok:
                    log.info(f"Training draw: {c.id} ({c.texture}, {c.genre}) passed the round trip.")
                else:
                    log.info(f"Training draw: {c.id} rejected: {trip.reason}.")
    chosen = [(order[i], results[i]) for i in sorted(results) if results[i].ok][:size]
    rejected = sum(not t.ok for t in results.values())
    log.info(f"Training draw: {len(chosen)} chosen, {rejected} rejected by the round trip.")
    if len(chosen) < size:
        log.warning(f"Training draw: only {len(chosen)} of {size} found; label more of the pool.")
    return chosen


def write_draw(chosen):
    """The selection file (no music, committed) and the labelled candidates
    (corpus work folder), so the export reads the same scores back."""
    import json
    from dataclasses import asdict

    path = select.write_selection("training", chosen, [])
    (sources.work_dir() / "training-candidates.json").write_text(
        json.dumps([asdict(c) for c, _ in chosen], indent=1), encoding="utf-8")
    return path


def read_draw():
    """[(candidate, round trip)] of the training draw, in draw order."""
    import json

    data = json.loads((sources.work_dir() / "training-candidates.json").read_text(encoding="utf-8"))
    chosen = [sources.Candidate(**d) for d in data]
    return [(c, roundtrip.check(c)) for c in chosen]
