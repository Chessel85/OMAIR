"""Back up the corpus folder as zip files of about 1 GB each, for Dropbox.

The corpus folder holds hundreds of thousands of small files, which a sync
service is slow to watch and upload, so it is copied as a few dozen zip
files instead. Each zip holds one folder (or part of one): a folder bigger
than the chunk size is split into its subfolders, and a folder's own files
that are still too big are split into numbered parts. The names inside
every zip are relative to the corpus folder, so unzipping them all into
one empty folder gives the corpus folder back (RESTORE.txt in the backup
folder says so).

A zip is written only when its files have changed since the last backup
(their names, sizes and times are kept in manifest.json in the backup
folder), so a second backup uploads only what changed. Each zip is written
in a staging folder outside the backup folder and then moved in, so the
sync service never sees half a zip. A stopped backup can be started again.
Zips for folders that no longer exist are deleted; with --skip-tools the
zips of `tools` already in the backup folder are left as they are.

Run it when no long run is writing to the corpus folder, so the backup
holds one consistent state.

usage: python scripts/backup_corpus.py [--corpus FOLDER] [--out FOLDER] [--skip-tools]
           [--chunk-gb N] [--dry-run]

e.g.   python scripts/backup_corpus.py --skip-tools
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from omr import paths
from omr.log import ProgressLog

CORPUS = Path("E:/OMAIRCorpus")
OUT = Path.home() / "Dropbox" / "OMAIRDataBackup"
MANIFEST = "manifest.json"
# already compressed: stored as they are, to save time
STORED = {".png", ".jpg", ".jpeg", ".pdf", ".zip", ".mxl", ".gz", ".7z", ".whl", ".pt", ".onnx",
          ".mp3", ".tif", ".tiff"}

RESTORE = """To restore the corpus folder: unzip every .zip file here into one empty
folder (for example E:\\OMAIRCorpus). The names inside the zips are relative
to the corpus folder, so the folders come back as they were. manifest.json
records which files each zip holds and when the backup was made; it is not
needed for restoring. Made by scripts/backup_corpus.py in the OMR repository.
"""


def scan(folder):
    """A folder as {"path", "files": [(path, size, mtime_ns)], "subs": [scans], "total": bytes}."""
    files, subs = [], []
    with os.scandir(folder) as entries:
        for e in sorted(entries, key=lambda e: e.name):
            if e.is_dir(follow_symlinks=False):
                subs.append(scan(e.path))
            elif e.is_file(follow_symlinks=False):
                st = e.stat()
                files.append((Path(e.path), st.st_size, st.st_mtime_ns))
    total = sum(f[1] for f in files) + sum(s["total"] for s in subs)
    return {"path": Path(folder), "files": files, "subs": subs, "total": total}


def every_file(node):
    out = list(node["files"])
    for s in node["subs"]:
        out += every_file(s)
    return out


def chunk_name(corpus, folder, part=None, own=False):
    rel = Path(folder).relative_to(corpus).as_posix()
    rel = "top" if rel == "." else rel.replace("/", "__")
    return rel + (f"__part{part:02d}" if part else "") + ("__files" if own else "") + ".zip"


def chunks(corpus, node, limit):
    """{zip name: [(path, size, mtime_ns)]} for a scanned folder: the whole
    folder in one zip if it fits, else its own files in one zip (in parts if
    need be) and each subfolder chunked in turn."""
    if node["total"] <= limit:
        files = every_file(node)
        return {chunk_name(corpus, node["path"]): files} if files else {}
    out = {}
    if node["files"]:
        parts, size = [[]], 0
        for f in node["files"]:
            if parts[-1] and size + f[1] > limit:
                parts.append([])
                size = 0
            parts[-1].append(f)
            size += f[1]
        for i, p in enumerate(parts, 1):
            name = chunk_name(corpus, node["path"], i if len(parts) > 1 else None, own=bool(node["subs"]))
            out[name] = p
    for s in node["subs"]:
        out.update(chunks(corpus, s, limit))
    return out


def plan_zips(corpus, limit, skip_tools):
    """({zip name: files}, the name stems of zips left as they are)."""
    corpus = Path(corpus)
    root = scan(corpus)
    plan, kept = {}, []
    if root["files"]:
        plan[chunk_name(corpus, corpus, own=True)] = root["files"]
    for s in root["subs"]:
        if skip_tools and s["path"].name == "tools":
            kept.append(chunk_name(corpus, s["path"])[:-4])
            continue
        plan.update(chunks(corpus, s, limit))
    return plan, kept


def signature(corpus, files):
    h = hashlib.sha256()
    for path, size, mtime in files:
        h.update(f"{path.relative_to(corpus).as_posix()}|{size}|{mtime}\n".encode("utf-8"))
    return h.hexdigest()


def write_zip(corpus, files, target):
    with zipfile.ZipFile(target, "w", allowZip64=True) as z:
        for path, _, _ in files:
            kind = zipfile.ZIP_STORED if path.suffix.lower() in STORED else zipfile.ZIP_DEFLATED
            z.write(path, path.relative_to(corpus).as_posix(), compress_type=kind)


def gb(n):
    return f"{n / 1e9:.1f} GB"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", default=str(CORPUS), help="The folder to back up.")
    parser.add_argument("--out", default=str(OUT), help="The backup folder.")
    parser.add_argument("--skip-tools", action="store_true",
                        help="Leave out the tools folder (its zips already in the backup folder are kept).")
    parser.add_argument("--chunk-gb", type=float, default=1.0, help="The most a zip holds, before compression.")
    parser.add_argument("--dry-run", action="store_true", help="Say what would be written, and write nothing.")
    args = parser.parse_args(argv)
    corpus, out = Path(args.corpus), Path(args.out)
    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = ProgressLog("backup-corpus", path=str(logs / "backup-corpus.log"))
    if not corpus.is_dir():
        log.error(f"The corpus folder {corpus} was not found.")
        return log.finish("nothing backed up")
    if not out.is_dir():
        log.error(f"The backup folder {out} was not found. Make it first.")
        return log.finish("nothing backed up")

    log.info(f"Listing {corpus}{', without tools' if args.skip_tools else ''}.")
    plan, kept_prefixes = plan_zips(corpus, int(args.chunk_gb * 1e9), args.skip_tools)
    total = sum(f[1] for c in plan.values() for f in c)
    log.info(f"{len(plan)} zips planned, {sum(len(c) for c in plan.values()):,} files, {gb(total)}.")

    manifest_path = out / MANIFEST
    zips = json.loads(manifest_path.read_text(encoding="utf-8"))["zips"] if manifest_path.exists() else {}

    def kept(name):
        return any(name == p + ".zip" or name.startswith(p + "__") for p in kept_prefixes)

    stale = sorted({n for n in zips if n not in plan and not kept(n)}
                   | {p.name for p in out.glob("*.zip") if p.name not in plan and not kept(p.name)})
    todo = {n: c for n, c in plan.items()
            if zips.get(n, {}).get("signature") != signature(corpus, c) or not (out / n).exists()}
    log.info(f"{len(todo)} zips to write ({gb(sum(f[1] for c in todo.values() for f in c))} before "
             f"compression), {len(plan) - len(todo)} unchanged, {len(stale)} to delete.")
    if args.dry_run:
        for n, c in sorted(todo.items()):
            log.info(f"Would write {n}: {len(c):,} files, {gb(sum(f[1] for f in c))}.")
        for n in stale:
            log.info(f"Would delete {n}.")
        return log.finish("dry run, nothing written")

    def save():
        text = json.dumps({"made": time.strftime("%Y-%m-%d %H:%M"), "corpus": str(corpus), "zips": zips}, indent=1)
        tmp = manifest_path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(manifest_path)

    (out / "RESTORE.txt").write_text(RESTORE, encoding="utf-8")
    failed = written = 0
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="omr-backup-") as staging:
        for i, (name, c) in enumerate(sorted(todo.items()), 1):
            size = sum(f[1] for f in c)
            free = shutil.disk_usage(out).free
            if free < size + 2e9:
                log.error(f"Only {gb(free)} free beside the backup folder; {name} needs up to {gb(size)}. Stopped.")
                failed += 1
                break
            staged = Path(staging) / name
            try:
                write_zip(corpus, c, staged)
                shutil.move(str(staged), str(out / name))
            except Exception as error:   # report and go on with the rest
                failed += 1
                staged.unlink(missing_ok=True)
                log.error(f"{name}: {type(error).__name__}: {error}")
                continue
            written += 1
            zips[name] = {"signature": signature(corpus, c), "files": len(c), "bytes": size,
                          "zip bytes": (out / name).stat().st_size}
            save()
            log.info(f"{i} of {len(todo)}: {name}, {len(c):,} files, {gb(size)} into "
                     f"{gb(zips[name]['zip bytes'])}, {(time.time() - started) / 60:.0f} minutes.")
    deleted = 0
    if not failed:   # a failed run leaves the old zips, so nothing is lost
        for n in stale:
            (out / n).unlink(missing_ok=True)
            zips.pop(n, None)
            deleted += 1
    save()
    return log.finish(f"{written} zips written, {len(plan) - len(todo)} unchanged, {failed} failed, "
                      f"{deleted} deleted; in {out}")


if __name__ == "__main__":
    sys.exit(main())
