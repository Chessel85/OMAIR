"""Audiveris and homr as recognisers. Both run as separate processes, on the CPU.

Where the tools live is set by `OMR_AUDIVERIS_DIR` and `OMR_HOMR_EXE`, and
defaults to `tools/` under the corpus folder (`omr.paths`).
"""

import copy
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from omr import paths

HOMR_DPI = 300


def _tools_dir():
    return Path(paths.corpus_dir()) / "tools"


def audiveris_dir():
    return Path(os.environ.get("OMR_AUDIVERIS_DIR") or _tools_dir() / "audiveris" / "Audiveris")


def homr_exe():
    return Path(os.environ.get("OMR_HOMR_EXE") or _tools_dir() / "homr-venv" / "Scripts" / "homr.exe")


def _fail(message):
    print(message, file=sys.stderr)
    return 1


def run_audiveris(pdf, out):
    root = audiveris_dir()
    java = root / "runtime" / "bin" / "java.exe"
    if not java.exists():
        return _fail(f"Audiveris not found at {root}")
    with tempfile.TemporaryDirectory(dir=out) as work:
        done = subprocess.run(
            [str(java), "-cp", str(root / "app" / "*"), "Audiveris", "-batch", "-transcribe", "-export",
             "-output", work, str(pdf)], capture_output=True, text=True, errors="replace")
        mxl = list(Path(work).glob("*.mxl"))
        if not mxl:
            return _fail("Audiveris wrote no MusicXML. " + (done.stdout + done.stderr)[-400:])
        # a multi-movement book gives book.mvt1.mxl and so on; the first is used
        mxl.sort()
        with zipfile.ZipFile(mxl[0]) as z:
            name = next(n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF"))
            (out / "score.musicxml").write_bytes(z.read(name))
    return 0


def _page_images(pdf, folder):
    import pymupdf
    images = []
    with pymupdf.open(pdf) as doc:
        for number, page in enumerate(doc, 1):
            path = folder / f"page{number:03d}.png"
            page.get_pixmap(dpi=HOMR_DPI).save(path)
            images.append(path)
    return images


def _merge_pages(files, target):
    """homr reads one page image per run. Join the pages: part N of each page
    continues part N of the first. A page with fewer parts leaves the rest short."""
    trees = [ET.parse(f) for f in files]
    first = trees[0].getroot()
    parts = first.findall("part")
    for tree in trees[1:]:
        for merged, extra in zip(parts, tree.getroot().findall("part")):
            offset = len(merged.findall("measure"))
            for measure in extra.findall("measure"):
                measure = copy.deepcopy(measure)
                measure.set("number", str(offset + int(re.sub(r"\D", "", measure.get("number", "0")) or 0)))
                merged.append(measure)
    first_tree = trees[0]
    first_tree.write(target, encoding="utf-8", xml_declaration=True)


def run_homr(pdf, out):
    exe = homr_exe()
    if not exe.exists():
        return _fail(f"homr not found at {exe}")
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="")
    with tempfile.TemporaryDirectory(dir=out) as work:
        work = Path(work)
        outputs, problems = [], []
        for image in _page_images(pdf, work):
            done = subprocess.run([str(exe), str(image)], capture_output=True, text=True, errors="replace",
                                  env=env, cwd=work)
            result = image.with_suffix(".musicxml")
            if done.returncode == 0 and result.exists():
                outputs.append(result)
            else:
                problems.append(f"{image.name}: {(done.stdout + done.stderr)[-200:].strip()}")
        if not outputs:
            return _fail("homr wrote no MusicXML. " + "; ".join(problems))
        for problem in problems:
            print("page skipped: " + problem, file=sys.stderr)
        _merge_pages(outputs, out / "score.musicxml")
    return 0


def main(argv):
    if len(argv) != 3 or argv[0] not in ("audiveris", "homr"):
        return _fail("usage: python -m omr.baselines audiveris|homr PDF OUT")
    out = Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    return (run_audiveris if argv[0] == "audiveris" else run_homr)(Path(argv[1]), out)
