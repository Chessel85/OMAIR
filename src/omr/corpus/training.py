"""The training pool, without near copies of the selected pieces (spec,
"Keeping the training pool clean").

The pool split by work key stays as it is. The work key misses many
arrangements of one piece, because uploaders write the composer in many ways,
so every training-pool score that is a near copy of a selected piece is removed
here. (The draw itself skips near copies of pieces already chosen.)
"""

from omr.corpus import labels, select, sources


def selected_pieces(set_names=("development", "regression")):
    """(set, id, title, composer) for every score in the selection files."""
    pieces = []
    for name in set_names:
        path = select.SELECTION_DIR / f"{name}.txt"
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
