"""Find candidate scores in PDMX and OpenScore and compute their labels.

Only scores that the pool split makes eligible for the development or
regression set are extracted and parsed, which keeps the run short. The split
depends only on the seed and the work key (see labels.pool_of).
"""

import csv
import json
import tarfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from omr import paths
from omr.corpus import config, labels

csv.field_size_limit(10**9)


@dataclass
class Candidate:
    id: str
    source: str            # "PDMX" or "OpenScore"
    source_path: str       # path inside the source, for the selection files
    mxl: str               # local path of the MusicXML file
    title: str
    composer: str
    source_genre: str | None
    tags: str
    work_key: str
    pool: str
    bars: int = 0
    parts: int = 0
    texture: str | None = None
    genre: str = "unlabelled"
    features: list = field(default_factory=list)
    excluded: str | None = None
    original_cc0: bool = False  # uploader's own work, marked CC0


def sources_dir():
    return paths.require_corpus_dir() / "sources"


def work_dir():
    folder = paths.require_corpus_dir() / "work"
    folder.mkdir(exist_ok=True)
    return folder


def _clean(value):
    return "" if value in (None, "NA") else value.strip()


def pdmx_candidates(log):
    """Rows of PDMX.csv that pass the metadata filters and are in a set pool."""
    csv_path = sources_dir() / "pdmx" / "PDMX.csv"
    found = []
    seen = total = 0
    with open(csv_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            if not (row["subset:no_license_conflict"] == "True"
                    and row["subset:deduplicated"] == "True"
                    and row["subset:all_valid"] == "True"):
                continue
            try:
                bars = int(float(row["song_length.bars"]))
                tracks = int(row["n_tracks"])
            except ValueError:
                continue
            if not (config.MIN_BARS <= bars <= config.MAX_BARS and 1 <= tracks <= config.MAX_PARTS):
                continue
            title = _clean(row["title"]) or _clean(row["song_name"])
            composer = _clean(row["composer_name"]) or _clean(row["artist_name"])
            key = labels.work_key(composer, title)
            pool = labels.pool_of(key)
            seen += 1
            if pool == "training":
                continue
            mxl_rel = row["mxl"].lstrip("./").replace("\\", "/")
            found.append(Candidate(
                id="pdmx-" + Path(mxl_rel).stem[-12:], source="PDMX", source_path=mxl_rel,
                mxl=str(sources_dir() / "pdmx" / "eligible" / mxl_rel),
                title=title, composer=composer,
                source_genre=labels.pdmx_genre(row["genres"]), tags=_clean(row["tags"]),
                work_key=key, pool=pool, bars=bars, parts=tracks,
                original_cc0=(row["is_original"] == "True" and row["license"] == "cc-zero"),
            ))
    log.info(f"PDMX: {total} rows read, {seen} passed the metadata filters, {len(found)} are in the development or regression pools.")
    return found


def extract_pdmx(candidates, log):
    """One pass over mxl.tar.gz, extracting only the wanted files. Returns the
    candidates whose file exists and is under the size limit."""
    root = sources_dir() / "pdmx" / "eligible"
    missing = [c for c in candidates if not Path(c.mxl).is_file()]
    if missing:
        wanted = {c.source_path: c for c in missing}
        archive = sources_dir() / "pdmx" / "mxl.tar.gz"
        log.info(f"Extracting {len(wanted)} MusicXML files from {archive.name}. This reads the whole archive and takes a few minutes.")
        done = 0
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                if member.name in wanted and member.isfile():
                    target = root / member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read())
                    done += 1
                    if done == len(wanted):
                        break
        log.info(f"Extracted {done} files.")
    if candidates and not any(Path(c.mxl).is_file() for c in candidates):
        raise RuntimeError("No MusicXML file was extracted from mxl.tar.gz. Is the archive complete?")
    kept = []
    for c in candidates:
        p = Path(c.mxl)
        if p.is_file() and p.stat().st_size <= config.MAX_MXL_BYTES:
            kept.append(c)
    log.info(f"{len(kept)} of {len(candidates)} files exist and are under {config.MAX_MXL_BYTES // 1000} KB.")
    return kept


def openscore_candidates(log):
    found = []
    base = sources_dir() / "openscore"
    for collection in ("Lieder", "StringQuartets"):
        scores = base / collection / "scores"
        if not scores.is_dir():
            log.warning(f"OpenScore {collection} is not downloaded ({scores}).")
            continue
        count = 0
        for mxl in sorted(scores.rglob("*.mxl")):
            rel = mxl.relative_to(scores)
            parts = rel.parts
            composer = parts[0].replace("_", " ")
            if "," in composer:
                last, first = composer.split(",", 1)
                composer = f"{first.strip()} {last.strip()}"
            title = mxl.parent.name.replace("_", " ")
            if mxl.stat().st_size > config.MAX_MXL_BYTES:
                continue
            key = labels.work_key(composer, title)
            pool = labels.pool_of(key)
            if pool == "training":
                continue
            found.append(Candidate(
                id="os-" + mxl.stem, source="OpenScore", source_path=f"{collection}/{rel.as_posix()}",
                mxl=str(mxl), title=title, composer=composer, source_genre="classical",
                tags="", work_key=key, pool=pool,
            ))
            count += 1
        log.info(f"OpenScore {collection}: {count} scores in the development or regression pools.")
    return found


def label_candidates(candidates, log):
    """Parse each MusicXML file and fill in texture, genre, features and size.
    Candidates that fail the size, specialised-notation or parse checks are
    dropped, with a count of each reason."""
    kept, dropped = [], {}
    for i, c in enumerate(candidates, 1):
        try:
            facts = labels.analyse(labels.read_musicxml(c.mxl))
        except Exception as error:
            dropped["unreadable MusicXML"] = dropped.get("unreadable MusicXML", 0) + 1
            continue
        reason = None
        if facts.excluded:
            reason = facts.excluded
        elif not (config.MIN_BARS <= facts.bars <= config.MAX_BARS):
            reason = "bar count outside the limits"
        elif facts.parts > config.MAX_PARTS:
            reason = "too many parts"
        tex = labels.texture(facts)
        if reason is None and tex is None:
            reason = "no texture matched"
        if reason:
            dropped[reason] = dropped.get(reason, 0) + 1
            continue
        c.bars, c.parts, c.texture = facts.bars, facts.parts, tex
        c.features = sorted(facts.features)
        c.genre = labels.final_genre(c.source_genre, tex, c.title, c.tags)
        kept.append(c)
        if i % 2000 == 0:
            log.info(f"Labelled {i} of {len(candidates)} candidates.")
    for reason, n in sorted(dropped.items()):
        log.info(f"Dropped {n} candidates: {reason}.")
    log.info(f"{len(kept)} candidates labelled and kept.")
    return kept


def load_or_build(log, refresh=False):
    """The labelled candidate list, cached in the corpus work folder."""
    cache = work_dir() / "candidates.json"
    if cache.is_file() and not refresh:
        data = json.loads(cache.read_text(encoding="utf-8"))
        log.info(f"Read {len(data)} labelled candidates from {cache}.")
        return [Candidate(**d) for d in data]
    pdmx = extract_pdmx(pdmx_candidates(log), log)
    everything = label_candidates(pdmx + openscore_candidates(log), log)
    cache.write_text(json.dumps([asdict(c) for c in everything], indent=1), encoding="utf-8")
    return everything
