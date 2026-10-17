"""Make the raster versions of a corpus set (Phase 2, Stage 2.0).

Every page of each pair's PDF is rendered to an image and written into a new
PDF that holds only that image, so the file is Type C. The ground truth and the
pair metadata are the vector pair's. Four versions are made, each a set folder
of its own under <corpus>/generated/raster:

    <set>-g300   greyscale, 300 dpi
    <set>-g200   greyscale, 200 dpi
    <set>-g150   greyscale, 150 dpi
    <set>-bw300  black and white (1 bit), 300 dpi, threshold at half grey

Each folder has an index.txt in the usual form, so a version is scored with

    omr evaluate --set development --set-root <corpus>/generated/raster/development-g300 ...

Every page written is checked with the inspector, which must call it Type C;
the types are recorded in the pair's metadata.txt and summed in the log.
A pair already written is skipped, so a stopped run can be started again.

The set "commercial" takes the PDFs in <corpus>/sources/other/imslp, which
have no ground truth; its folders hold files.txt instead of index.txt.

usage: python scripts/make_raster_set.py SET [SET ...] [--workers N] [--limit N]
"""

import argparse
import io
import os
import sys
from collections import Counter
from pathlib import Path

from omr import parallel, paths
from omr.log import ProgressLog

VERSIONS = {  # name: (dpi, black and white)
    "g300": (300, False),
    "g200": (200, False),
    "g150": (150, False),
    "bw300": (300, True),
}
THRESHOLD = 128
MIN_FREE_GB = 20
HEADER = "# status | id | job | font | pdf | ground-truth MusicXML or reason"


def image_bytes(pix, black_and_white):
    """PNG bytes of a greyscale pixmap, or of its 1-bit thresholded copy."""
    if not black_and_white:
        return pix.tobytes("png")
    from PIL import Image

    grey = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    bits = grey.point(lambda v: 255 if v >= THRESHOLD else 0).convert("1", dither=Image.Dither.NONE)
    buffer = io.BytesIO()
    bits.save(buffer, "PNG")
    return buffer.getvalue()


def render(source, targets):
    """Write each version of source. targets maps version name to output PDF.
    Returns {version: Counter of page types} from the inspector."""
    import pymupdf

    from omr.inspect import inspect_file

    src = pymupdf.open(str(source))
    docs = {name: pymupdf.open() for name in targets}
    try:
        for page in src:
            for dpi in sorted({VERSIONS[name][0] for name in targets}):
                pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
                for name, (version_dpi, bw) in VERSIONS.items():
                    if name in targets and version_dpi == dpi:
                        new = docs[name].new_page(width=page.rect.width, height=page.rect.height)
                        new.insert_image(new.rect, stream=image_bytes(pix, bw))
        types = {}
        for name, target in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_suffix(".part")
            docs[name].save(str(part), deflate=True, garbage=3)
            docs[name].close()
            os.replace(part, target)
            types[name] = Counter(d.type for _, d in inspect_file(target)["results"])
        return types
    finally:
        src.close()
        for doc in docs.values():
            if not doc.is_closed:
                doc.close()


def type_words(counter):
    return ", ".join(f"{t} on {n} page{'s' if n > 1 else ''}" for t, n in sorted(counter.items()))


def read_types(words):
    """The Counter written by type_words."""
    counter = Counter()
    for part in words.split(", "):
        kind, _, rest = part.partition(" on ")
        counter[kind] += int(rest.split()[0])
    return counter


def pair_job(source, meta_path, out_dirs, source_set):
    """Runs in a worker: render one pair into every version not yet made and
    write its metadata. Returns {version: Counter of page types}."""
    meta = meta_path.read_text(encoding="utf-8") if meta_path.is_file() else ""
    todo = {name: out / "score.pdf" for name, out in out_dirs.items() if not (out / "metadata.txt").is_file()}
    made = render(source, todo) if todo else {}
    types = {}
    for name, out in out_dirs.items():
        if name in made:
            dpi, bw = VERSIONS[name]
            lines = [meta.rstrip("\n")] if meta else []
            lines += [f"raster: {'black and white' if bw else 'greyscale'}, {dpi} dpi",
                      f"raster set: {source_set}",
                      f"raster source: {source}",
                      f"raster page types: {type_words(made[name])}"]
            (out / "metadata.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
            types[name] = made[name]
        else:
            line = [l for l in (out / "metadata.txt").read_text(encoding="utf-8").splitlines()
                    if l.startswith("raster page types: ")]
            types[name] = read_types(line[0].split(": ", 1)[1])
    return types


def corpus_jobs(set_name, base, root):
    """(jobs, index lines by version). A job is (key, source pdf, metadata, output folders)."""
    source_root = root / "generated" / set_name
    index = source_root / "index.txt"
    if not index.is_file():
        raise FileNotFoundError(f"there is no index for the {set_name} set at {index}")
    jobs, lines = [], {name: [HEADER] for name in VERSIONS}
    for line in index.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        fields = [f.strip() for f in line.split(" | ")]
        if fields[0] != "pair":
            for name in VERSIONS:
                lines[name].append(line)
            continue
        _, score_id, job, font, pdf, truth = fields[:6]
        pdf, truth = (Path(p) if Path(p).is_absolute() else source_root / p for p in (pdf, truth))
        out_dirs = {name: base / f"{set_name}-{name}" / score_id / job for name in VERSIONS}
        for name in VERSIONS:
            lines[name].append(f"pair | {score_id} | {job} | {font} | {out_dirs[name] / 'score.pdf'} | {truth}")
        jobs.append((f"{score_id} {job}", pdf, pdf.parent / "metadata.txt", out_dirs))
    return jobs, lines


def commercial_jobs(base, root):
    sources = sorted((root / "sources" / "other" / "imslp").glob("*.pdf"))
    jobs, lines = [], {name: ["# raster versions of the commercial PDFs; no ground truth"] for name in VERSIONS}
    for pdf in sources:
        out_dirs = {name: base / f"commercial-{name}" / pdf.stem for name in VERSIONS}
        for name in VERSIONS:
            lines[name].append(str(out_dirs[name] / "score.pdf"))
        jobs.append((pdf.stem, pdf, pdf.with_suffix(".none"), out_dirs))
    return jobs, lines


def make_set(set_name, root, log, workers, limit):
    base = root / "generated" / "raster"
    if set_name == "commercial":
        jobs, lines = commercial_jobs(base, root)
        list_name = "files.txt"
    else:
        jobs, lines = corpus_jobs(set_name, base, root)
        list_name = "index.txt"
    if limit:
        jobs = jobs[:limit]
    log.info(f"{set_name}: {len(jobs)} files to render in {len(VERSIONS)} versions, {workers} workers.")
    totals = {name: Counter() for name in VERSIONS}
    failed = 0
    with parallel.pool(workers) as executor:
        running = {}
        for number, (key, pdf, meta, out_dirs) in enumerate(jobs, 1):
            if number % 50 == 1:
                paths.check_free_space(base.parent, MIN_FREE_GB)
            running[executor.submit(pair_job, pdf, meta, out_dirs, set_name)] = (number, key)
            while len(running) >= workers * 2:
                failed += collect(parallel.finished(running, block=True), totals, len(jobs), log)
        while running:
            failed += collect(parallel.finished(running, block=True), totals, len(jobs), log)
    for name in VERSIONS:
        folder = base / f"{set_name}-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        if limit:  # a trial: the list would name pairs that were not rendered
            where = "No list written, as this was a trial."
        else:
            (folder / list_name).write_text("\n".join(lines[name]) + "\n", encoding="utf-8")
            where = f"List in {folder / list_name}."
        not_c = sum(n for t, n in totals[name].items() if t != "C")
        words = type_words(totals[name]) or "no pages"
        (log.warning if not_c else log.info)(f"{set_name}-{name}: {words}; {not_c} pages not Type C. {where}")
    return failed


def collect(done, totals, count, log):
    failed = 0
    for future, (number, key) in done:
        try:
            for name, counter in future.result().items():
                totals[name].update(counter)
            if number % 100 == 0 or number == count:
                log.info(f"{number} of {count} done ({key}).")
        except Exception as error:
            failed += 1
            log.error(f"{key} could not be rendered: {error}")
    return failed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sets", nargs="+", help="corpus sets (regression, development, check) or commercial")
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--limit", type=int, help="only the first N files of each set, for a trial")
    args = parser.parse_args()
    root = paths.require_corpus_dir()
    log_dir = root / "generated" / "raster"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("make_raster_set", log_dir / "make_raster_set.log")
    failed = 0
    for set_name in args.sets:
        failed += make_set(set_name, root, log, args.workers, args.limit)
    return log.finish(f"{len(args.sets)} set(s) rendered, {failed} file(s) failed")


if __name__ == "__main__":
    sys.exit(main())
