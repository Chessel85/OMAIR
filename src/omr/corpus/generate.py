"""Export the selected scores through every engraver (spec, 'Exports').

The run is resumable: a job whose metadata file exists is skipped. Every PDF is
checked with the inspector before it is accepted, because MuseScore falls back
to Bravura without an error when a requested font is missing.
"""

import datetime
import shutil
import time
from pathlib import Path

from omr import inspect as inspector
from omr import paths
from omr.corpus import config, engravers, roundtrip


def output_dir(set_name):
    return paths.require_corpus_dir() / "generated" / set_name


def plan_jobs(chosen):
    """The six exports for each score: four base and two font variants.

    `chosen` is the list of (candidate, round trip) in selection order. Font
    and staff-size variants rotate across the set, sorted by texture and then
    by the shuffled (selection) order, so every font meets every texture.
    """
    order = sorted(range(len(chosen)), key=lambda i: (config.TEXTURES.index(chosen[i][0].texture), i))
    jobs = {}
    for rank, i in enumerate(order):
        ms4_font = config.MS4_VARIANT_FONTS[rank % len(config.MS4_VARIANT_FONTS)]
        size = config.MS4_STAFF_SIZES_MM[rank % len(config.MS4_STAFF_SIZES_MM)]
        ms3_font = config.MS3_VARIANT_FONTS[rank % len(config.MS3_VARIANT_FONTS)]
        jobs[chosen[i][0].id] = [
            ("musescore4-base", dict(engraver="MuseScore 4", font="Leland", staff_mm=None)),
            ("musescore3-base", dict(engraver="MuseScore 3", font="Emmentaler")),
            ("lilypond", dict(engraver="LilyPond", font="Emmentaler")),
            ("verovio", dict(engraver="Verovio", font="Verovio")),
            ("musescore4-variant", dict(engraver="MuseScore 4", font=ms4_font, staff_mm=size)),
            ("musescore3-variant", dict(engraver="MuseScore 3", font=ms3_font)),
        ]
    return jobs


def _run_job(spec, reference, out):
    kind = spec["engraver"]
    if kind == "MuseScore 4":
        return engravers.export_musescore4(reference, out, font=spec["font"], staff_space_mm=spec.get("staff_mm"))
    if kind == "MuseScore 3":
        return engravers.export_musescore3(reference, out, font=spec["font"])
    if kind == "LilyPond":
        return engravers.export_lilypond(reference, out, timeout=config.LILYPOND_TIMEOUT_S)
    return engravers.export_verovio(reference, out)


def check_pdf(pdf, spec):
    """Raise ExportError unless the PDF has the requested font and page type."""
    result = inspector.inspect_file(pdf)
    kinds = {decision.type for _, decision in result["results"]}
    expected = "B" if spec["engraver"] == "Verovio" else "A"
    # Text-only pages (a title page, a page of notes) are normal in an export and
    # are classed N. At least one page must have music, and none may be another type.
    if expected not in kinds or not kinds <= {expected, "N"}:
        raise engravers.ExportError(f"the inspector found page types {sorted(kinds)}, expected {expected} (and N for text-only pages)")
    if spec["engraver"] == "Verovio":
        return
    wanted = engravers.PDF_FONT_NAMES.get(spec["font"], spec["font"])
    names = {f.name for ev, _ in result["results"] for f in ev.music_fonts}
    if spec["engraver"] == "LilyPond":
        ok = any(n.startswith("Emmentaler") for n in names)
    else:
        ok = wanted in names
    if not ok:
        raise engravers.ExportError(f"the PDF uses music font(s) {sorted(names)}, not {wanted}")


def metadata_text(candidate, set_name, spec, result, ground_truth):
    fields = [
        ("source", candidate.source), ("source path", candidate.source_path),
        ("work key", candidate.work_key), ("title", candidate.title),
        ("composer", candidate.composer), ("set", set_name),
        ("texture", candidate.texture), ("genre", candidate.genre),
        ("features", ", ".join(candidate.features) or "none"),
        ("engraver", result.engraver), ("engraver version", result.version),
        ("font", spec["font"]),
        ("staff size", f"{spec['staff_mm']} mm" if spec.get("staff_mm") else "default"),
        ("ground truth", ground_truth), ("seed", config.SEED),
        ("date of export", datetime.date.today().isoformat()),
    ]
    return "".join(f"{k}: {v}\n" for k, v in fields)


def generate_set(set_name, chosen, log, min_free_gb=config.MIN_FREE_GB, retry_failures=False):
    """Export a whole set. Returns (pairs made, failures). A job that failed in
    an earlier run is not retried unless retry_failures is true: timeouts and
    wrong-font results would only fail again."""
    root = output_dir(set_name)
    root.mkdir(parents=True, exist_ok=True)
    jobs = plan_jobs(chosen)
    made = failed = skipped = 0
    for number, (candidate, trip) in enumerate(chosen, 1):
        try:
            free = paths.check_free_space(root, min_free_gb)
        except paths.CorpusDirError as error:
            log.error(f"Stopping cleanly so the run can be resumed: {error}")
            return made, failed + 1
        score_dir = root / candidate.id
        score_dir.mkdir(exist_ok=True)
        reference = score_dir / "reference.musicxml"
        if not reference.is_file():
            shutil.copyfile(trip.reference, reference)
        for job_name, spec in jobs[candidate.id]:
            out = score_dir / job_name
            if (out / "metadata.txt").is_file() or ((out / "failure.txt").is_file() and not retry_failures):
                skipped += 1
                continue
            started = time.time()
            try:
                if out.exists():
                    shutil.rmtree(out)
                result = _run_job(spec, reference, out)
                check_pdf(result.pdf, spec)
                truth = "reference, exact" if result.engraver == "MuseScore 4" else "reference, engraver input"
                if result.musicxml:
                    result.musicxml.unlink(missing_ok=True)  # the shared reference is the ground truth
                (out / "metadata.txt").write_text(
                    metadata_text(candidate, set_name, spec, result, truth), encoding="utf-8")
                made += 1
                log.info(f"{set_name} {number} of {len(chosen)}: {candidate.id} {job_name} ({spec['font']}) done in {time.time() - started:.0f} seconds.")
            except engravers.ExportError as error:
                failed += 1
                log.error(f"{set_name} {number} of {len(chosen)}: {candidate.id} {job_name} failed: {error}")
                (out / "failure.txt").parent.mkdir(parents=True, exist_ok=True)
                (out / "failure.txt").write_text(f"{error}\n", encoding="utf-8")
            except Exception as error:
                failed += 1
                log.error(f"{set_name} {number} of {len(chosen)}: {candidate.id} {job_name} failed unexpectedly: {error!r}")
    write_index(set_name, chosen)
    log.info(f"{set_name}: {made} exports made, {skipped} already present or failed earlier, {failed} failed in this run. Corpus folder size {folder_size_gb(root):.2f} GB.")
    return made, failed


def folder_size_gb(folder):
    return sum(f.stat().st_size for f in Path(folder).rglob("*") if f.is_file()) / 1024**3


def write_index(set_name, chosen):
    """A text index of every pair and every failure, one line each."""
    root = output_dir(set_name)
    lines = ["# status | id | job | font | pdf | reference MusicXML or reason"]
    for candidate, _ in chosen:
        score_dir = root / candidate.id
        if not score_dir.is_dir():
            continue
        for job in sorted(p for p in score_dir.iterdir() if p.is_dir()):
            meta = job / "metadata.txt"
            if meta.is_file():
                font = next((l.split(": ", 1)[1] for l in meta.read_text(encoding="utf-8").splitlines()
                             if l.startswith("font: ")), "")
                lines.append(" | ".join(["pair", candidate.id, job.name, font.strip(),
                                         str(job / "score.pdf"), str(score_dir / "reference.musicxml")]))
            elif (job / "failure.txt").is_file():
                reason = (job / "failure.txt").read_text(encoding="utf-8").strip()
                lines.append(" | ".join(["failure", candidate.id, job.name, "", "", reason]))
    (root / "index.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
