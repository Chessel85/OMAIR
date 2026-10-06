"""Draw the development and regression sets (spec, 'Drawing the sets')."""

import random
from pathlib import Path

from omr import paths
from omr.corpus import config, labels, roundtrip

COMPOSER_LIST = paths.REPO_ROOT / "scripts" / "public_domain_composers.txt"
SELECTION_DIR = paths.REPO_ROOT / "docs" / "corpus-selection"


BLOCKER_WORDS = {
    "arr", "arranged", "arrangement", "arranger", "transcription", "transcribed", "transcription",
    "realization", "realizations", "harmony", "adapted", "edited", "ed", "orchestrated",
    "lyrics", "words", "text", "after", "by", "feat", "featuring", "remix",
}


def load_composers(path=COMPOSER_LIST):
    """Phrases naming composers whose music is public domain (one per line,
    '#' comments). A composer string matches if a phrase occurs in it as a run
    of whole words."""
    if not Path(path).is_file():
        return set()
    names = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            names.add(" ".join(labels._plain(line).split()))
    return names


def composer_is_public_domain(composer, names):
    """True if the composer string names a listed composer and mentions no
    arranger, editor or lyricist (whose work may still be in copyright)."""
    words = labels._plain(composer).split()
    if not words or BLOCKER_WORDS & set(words):
        return False
    text = " " + " ".join(words) + " "
    return any(f" {phrase} " in text for phrase in names)


def regression_allowed(c, names):
    """Extra rules for the committed regression set."""
    if c.bars > config.REGRESSION_MAX_BARS:
        return False
    if c.source == "OpenScore":
        return True
    if composer_is_public_domain(c.composer, names):
        return True
    return bool(c.original_cc0) and not c.composer


def _gain(c, cfg, genre_counts, feature_counts):
    priority_gain = sum(1 for f in config.PRIORITY_FEATURES
                        if f in c.features and feature_counts.get(f, 0) < cfg["feature_min"].get(f, 0))
    genre_gain = 1 if genre_counts.get(c.genre, 0) < cfg["genre_min"].get(c.genre, 0) else 0
    feature_gain = sum(1 for f in c.features if feature_counts.get(f, 0) < cfg["feature_min"].get(f, 0))
    return priority_gain, genre_gain, feature_gain


def select_set(name, candidates, log, composers=None):
    """Return (chosen candidates with their round-trip records, shortfalls)."""
    cfg = config.SETS[name]
    composers = composers if composers is not None else load_composers()
    pool = sorted((c for c in candidates if c.pool == name), key=lambda c: c.id)
    random.Random(config.SEED).shuffle(pool)
    if name == "regression":
        pool = [c for c in pool if regression_allowed(c, composers)]
    log.info(f"{name}: {len(pool)} eligible candidates.")
    chosen, genre_counts, feature_counts, used_keys = [], {}, {}, set()
    near_copies = labels.NearCopyIndex([])
    shortfalls = []
    for texture in config.TEXTURES:
        quota = cfg["textures"][texture]
        openscore_cap = int(config.OPENSCORE_SHARE_LIMIT * quota) if texture in ("voice with piano", "chamber") else quota
        openscore_used = 0
        remaining = [c for c in pool if c.texture == texture]
        filled = rejected = 0
        while filled < quota and remaining:
            allowed = [c for c in remaining if c.work_key not in used_keys
                       and not (c.source == "OpenScore" and openscore_used >= openscore_cap)]
            if not allowed:
                break
            best = max(allowed, key=lambda c: _gain(c, cfg, genre_counts, feature_counts))
            remaining.remove(best)
            if near_copies.match(best.title, best.composer):
                log.info(f"{name}: skipped {best.id} ({best.title}): a near copy of a piece already chosen.")
                continue
            trip = roundtrip.check(best)
            if trip.ok and name == "regression" and trip.pages > config.REGRESSION_MAX_PAGES:
                trip = roundtrip.RoundTrip(False, f"{trip.pages} pages is over the limit of {config.REGRESSION_MAX_PAGES}")
            if not trip.ok:
                rejected += 1
                log.info(f"{name}: rejected {best.id} ({best.title}): {trip.reason}.")
                continue
            chosen.append((best, trip))
            used_keys.add(best.work_key)
            near_copies.add(best.title, best.composer)
            genre_counts[best.genre] = genre_counts.get(best.genre, 0) + 1
            for f in best.features:
                feature_counts[f] = feature_counts.get(f, 0) + 1
            openscore_used += best.source == "OpenScore"
            filled += 1
        log.info(f"{name}: texture {texture}: {filled} of {quota} chosen, {rejected} rejected by the round trip.")
        if filled < quota:
            shortfalls.append(f"texture {texture}: {filled} of {quota}")
    for genre, minimum in cfg["genre_min"].items():
        if genre_counts.get(genre, 0) < minimum:
            shortfalls.append(f"genre {genre}: {genre_counts.get(genre, 0)} of at least {minimum}")
    for feature, minimum in cfg["feature_min"].items():
        if feature_counts.get(feature, 0) < minimum:
            shortfalls.append(f"feature {feature}: {feature_counts.get(feature, 0)} of at least {minimum}")
    for line in shortfalls:
        log.warning(f"{name}: shortfall, {line}.")
    return chosen, shortfalls


def write_selection(name, chosen, shortfalls):
    """One line per selected score, in the repository (no music, so it can be committed)."""
    SELECTION_DIR.mkdir(parents=True, exist_ok=True)
    path = SELECTION_DIR / f"{name}.txt"
    lines = [f"# {name} set, seed {config.SEED}. Fields: id | source | source path | texture | genre | title | composer"]
    lines += [f"# shortfall: {s}" for s in shortfalls]
    for c, _trip in chosen:
        lines.append(" | ".join([c.id, c.source, c.source_path, c.texture, c.genre, c.title, c.composer]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def read_selection(name, candidates):
    """The chosen candidates for a set, in file order, from the selection file."""
    by_id = {c.id: c for c in candidates}
    chosen = []
    for line in (SELECTION_DIR / f"{name}.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        chosen.append(by_id[line.split(" | ")[0]])
    return chosen
