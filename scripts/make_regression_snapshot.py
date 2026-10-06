"""Copy the regression set from the corpus folder into the repository (Stage 7).

CI cannot reach the corpus drive, so the fixed regression set (PDFs, ground
truth and metadata, about 34 MB) is kept in `regression/` in the repository.
The index there uses paths relative to itself.

Usage: python scripts/make_regression_snapshot.py [--replace]
Without --replace the script stops if `regression/` already exists, because a
changed set makes every recorded baseline out of date.
"""

import argparse
import shutil
import sys
from pathlib import Path

from omr import paths
from omr.log import ProgressLog

DEST = paths.REPO_ROOT / "regression"
COPIED = {"score.pdf", "score.musicxml", "reference.musicxml", "metadata.txt", "failure.txt"}


def relative(path, source):
    return Path(path).relative_to(source).as_posix()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--replace", action="store_true", help="Replace an existing regression/ folder.")
    args = parser.parse_args(argv)
    log = ProgressLog("regression-snapshot")
    source = paths.require_corpus_dir() / "generated" / "regression"
    if not (source / "index.txt").is_file():
        log.error(f"There is no regression set at {source}.")
        return log.finish("nothing copied")
    if DEST.exists():
        if not args.replace:
            log.error(f"{DEST} already exists. Use --replace to replace it, then update the baseline.")
            return log.finish("nothing copied")
        shutil.rmtree(DEST)
    lines, copied = [], 0
    for line in (source / "index.txt").read_text(encoding="utf-8").splitlines():
        fields = [f.strip() for f in line.split(" | ")]
        if fields[0] == "pair":
            fields[4], fields[5] = relative(fields[4], source), relative(fields[5], source)
            line = " | ".join(fields)
        lines.append(line)
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.name in COPIED:
            target = DEST / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            copied += 1
    (DEST / "index.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    size = sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file()) / 1024**2
    log.info(f"Copied {copied} files, {size:.1f} MB, to {DEST}.")
    return log.finish("regression set copied")


if __name__ == "__main__":
    sys.exit(main())
