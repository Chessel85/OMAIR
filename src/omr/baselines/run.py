"""Audiveris, homr and LEGATO as recognisers. Each runs as a separate process, on the CPU.

Where the tools live is set by `OMR_AUDIVERIS_DIR`, `OMR_HOMR_EXE` and
`OMR_LEGATO_DIR`, and defaults to `tools/` under the corpus folder (`omr.paths`).
LEGATO has its own Python 3.12 environment, its repository and its model cache
in that folder; it is a development baseline only and is never shipped.
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
LEGATO_DPI = 150


def _tools_dir():
    return Path(paths.corpus_dir()) / "tools"


def audiveris_dir():
    return Path(os.environ.get("OMR_AUDIVERIS_DIR") or _tools_dir() / "audiveris" / "Audiveris")


def homr_exe():
    return Path(os.environ.get("OMR_HOMR_EXE") or _tools_dir() / "homr-venv" / "Scripts" / "homr.exe")


def legato_dir():
    return Path(os.environ.get("OMR_LEGATO_DIR") or _tools_dir() / "legato")


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


def _page_images(pdf, folder, dpi=HOMR_DPI):
    import pymupdf
    images = []
    with pymupdf.open(pdf) as doc:
        for number, page in enumerate(doc, 1):
            path = folder / f"page{number:03d}.png"
            page.get_pixmap(dpi=dpi).save(path)
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


def _musescore_tidy(source, target):
    """LEGATO's own pipeline passes the converted MusicXML through MuseScore to tidy it."""
    from omr.corpus import engravers
    exe = engravers.musescore4_path()
    done = subprocess.run([str(exe), "-o", str(target), str(source)], capture_output=True, errors="replace")
    return done.returncode == 0 and Path(target).exists()


def run_legato(pdf, out):
    root = legato_dir()
    python = root / "venv" / "Scripts" / "python.exe"
    if not python.exists():
        return _fail(f"LEGATO not found at {root}")
    env = dict(os.environ, HF_HOME=str(root / "hf"), CUDA_VISIBLE_DEVICES="", PYTHONUTF8="1")
    with tempfile.TemporaryDirectory(dir=out) as work:
        work = Path(work)
        images = _page_images(pdf, work, LEGATO_DPI)
        done = subprocess.run([str(python), str(Path(__file__).with_name("legato_infer.py")), str(root / "repo"),
                               str(work)] + [str(i) for i in images], capture_output=True, text=True,
                              errors="replace", env=env)
        sys.stderr.write(done.stderr[-2000:])
        outputs = []
        for image in images:
            xml = work / f"{image.stem}.xml"
            if not xml.exists() or xml.stat().st_size == 0:
                continue
            tidy = work / f"{image.stem}.tidy.musicxml"
            outputs.append(tidy if _musescore_tidy(xml, tidy) else xml)
        if not outputs:
            return _fail("LEGATO wrote no MusicXML. " + (done.stdout + done.stderr)[-400:])
        _merge_pages(outputs, out / "score.musicxml")
    return 0


def main(argv):
    if len(argv) != 3 or argv[0] not in ("audiveris", "homr", "legato"):
        return _fail("usage: python -m omr.baselines audiveris|homr|legato PDF OUT")
    out = Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    run = {"audiveris": run_audiveris, "homr": run_homr, "legato": run_legato}[argv[0]]
    return run(Path(argv[1]), out)
