"""Run a recogniser over a corpus set and compare each output with its ground
truth (spec, "Recogniser interface" and "Inputs").

Each pair is one job for the shared worker pool. The worker runs the
recogniser, compares the result and returns the figures; only the main
process writes the log and the reports.
"""

import contextlib
import datetime
import io
import json
import os
import shlex
import subprocess
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

from omr import parallel, paths
from omr.evaluate import events, metrics, report

DEFAULT_TIMEOUT_S = 600
BUILT_IN = {
    "perfect": [sys.executable, "-m", "omr.evaluate.recognisers", "perfect", "{pdf}", "{out}", "--truth", "{truth}"],
    "damaged": [sys.executable, "-m", "omr.evaluate.recognisers", "damaged", "{pdf}", "{out}", "--truth", "{truth}"],
    "audiveris": [sys.executable, "-m", "omr.baselines", "audiveris", "{pdf}", "{out}"],
    "homr": [sys.executable, "-m", "omr.baselines", "homr", "{pdf}", "{out}"],
    "legato": [sys.executable, "-m", "omr.baselines", "legato", "{pdf}", "{out}"],
}


@dataclass
class Pair:
    id: str
    job: str
    pdf: Path
    truth: Path
    meta: dict

    @property
    def name(self):
        return f"{self.id} {self.job}"


def read_pairs(set_name, root=None):
    """The pairs of a set, from its index.txt and each pair's metadata.
    Returns (pairs, number of failed exports skipped)."""
    root = Path(root) if root else paths.require_corpus_dir() / "generated" / set_name
    index = root / "index.txt"
    if not index.is_file():
        raise FileNotFoundError(f"there is no index for the {set_name} set at {index}; run the corpus export first")
    pairs, failures = [], 0
    for line in index.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        fields = [f.strip() for f in line.split(" | ")]
        if fields[0] == "failure":
            failures += 1
            continue
        _, score_id, job, _font, pdf, truth = fields[:6]
        # Paths in a set kept in the repository are relative to its index.
        pdf, truth = (p if Path(p).is_absolute() else str(root / p) for p in (pdf, truth))
        meta_path = Path(pdf).parent / "metadata.txt"
        meta = {}
        if meta_path.is_file():
            meta = dict(l.split(": ", 1) for l in meta_path.read_text(encoding="utf-8").splitlines() if ": " in l)
        pairs.append(Pair(score_id, job, Path(pdf), Path(truth), meta))
    return pairs, failures


def select_pairs(pairs, engraver=None, font=None, genre=None, texture=None, limit=None):
    def keep(pair):
        for field, wanted in (("engraver", engraver), ("font", font), ("genre", genre), ("texture", texture)):
            if wanted and pair.meta.get(field, "").lower() != wanted.lower():
                return False
        return True
    chosen = [p for p in pairs if keep(p)]
    return chosen[:limit] if limit else chosen


def command_for(recogniser, pair, out):
    """The command for one pair. A built-in name, or a template with {pdf} and
    {out} (and {truth}, for test recognisers only). On Windows a template is
    passed as one command line, with each path quoted, as Windows expects."""
    values = {"pdf": str(pair.pdf), "out": str(out), "truth": str(pair.truth)}
    if recogniser in BUILT_IN:
        return [part.format(**values) for part in BUILT_IN[recogniser]]
    if os.name == "nt":
        return recogniser.format(**{k: subprocess.list2cmdline([v]) for k, v in values.items()})
    return [part.format(**values) for part in shlex.split(recogniser)]


def evaluate_pair(pair, recogniser, out, timeout, cpu_only, predictions, with_musicdiff):
    """Runs in a worker. Returns a result dictionary for the reports."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    result = {"id": pair.id, "job": pair.job, "meta": pair.meta, "pdf": str(pair.pdf), "truth": str(pair.truth)}
    seconds = None
    failure = None
    if predictions:
        output = Path(predictions) / pair.id / pair.job / "score.musicxml"
        flags = output.parent / "flags.json"
    else:
        output, flags = out / "score.musicxml", out / "flags.json"
        for stale in (output, flags):
            stale.unlink(missing_ok=True)
        env = dict(os.environ)
        if cpu_only:
            env["CUDA_VISIBLE_DEVICES"] = ""
        started = time.time()
        try:
            done = subprocess.run(command_for(recogniser, pair, out), capture_output=True, text=True,
                                  errors="replace", timeout=timeout, env=env)
            if done.returncode != 0:
                tail = " ".join((done.stderr or done.stdout).split())[-300:]
                failure = f"the recogniser exited with status {done.returncode}: {tail}"
        except subprocess.TimeoutExpired:
            failure = f"the recogniser took longer than {timeout} seconds"
        except OSError as error:
            failure = f"the recogniser could not start: {error}"
        seconds = time.time() - started
    result["seconds"] = seconds
    if failure is None and not output.is_file():
        failure = "the recogniser wrote no MusicXML"
    # A flag file that cannot be read means no flags; the notes are still scored.
    flag_list = None
    if failure is None and flags.is_file():
        try:
            flag_list = metrics.read_flags(flags)
        except ValueError as error:
            result["flag file problem"] = f"the flag file could not be read, so no flags were counted: {error}"
            flag_list = []
    try:
        if failure is None:
            try:
                figures = metrics.compare(pair.truth, output, flags=flag_list)
            except events.MusicXMLError as error:
                if not _readable(pair.truth):
                    raise
                failure = f"the output could not be read: {error}"
        if failure is not None:
            figures = metrics.failed_file(pair.truth, failure)
        elif with_musicdiff:
            figures["musicdiff"] = musicdiff_figures(pair.truth, output)
    except events.MusicXMLError as error:
        result["harness error"] = f"the ground truth could not be read: {error}"
        return result
    except Exception as error:   # a harness bug on one pair must not stop the run
        result["harness error"] = f"the harness failed on this pair ({type(error).__name__}: {error})"
        return result
    result.update(figures)
    (out / "figures.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    return result


def _readable(path):
    try:
        events.read(path)
        return True
    except events.MusicXMLError:
        return False


def musicdiff_figures(truth, output):
    """musicdiff's OMR-NED and edit counts (spec, "Comparison with published work")."""
    try:
        from musicdiff import _diff_omr_ned_metrics
        from musicdiff.detaillevel import DetailLevel

        figures = {}
        for name, level in (("notes and rests", DetailLevel.NotesAndRests), ("all objects", DetailLevel.AllObjects)):
            with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()),                     contextlib.redirect_stderr(io.StringIO()):
                warnings.simplefilter("ignore")   # music21's import warnings would clutter the screen
                m = _diff_omr_ned_metrics(str(output), str(truth), level)
            if m is None:
                return {"failed": "musicdiff could not read one of the files"}
            figures[name] = {"omr_ned": m.omr_ned, "edit distance": m.omr_edit_distance,
                             "truth symbols": m.gt_numsyms, "output symbols": m.pred_numsyms}
        return figures
    except Exception as error:   # musicdiff failures must not stop the run
        return {"failed": f"musicdiff failed: {' '.join(str(error).split())[:200]}"}


def run(set_name, recogniser, log, out_dir=None, predictions=None, workers=parallel.DEFAULT_WORKERS,
        timeout=DEFAULT_TIMEOUT_S, cpu_only=False, with_musicdiff=True, set_root=None, **filters):
    """Evaluate a set. Returns (results, path of the text report)."""
    pairs, export_failures = read_pairs(set_name, set_root)
    pairs = select_pairs(pairs, **filters)
    label = "predictions" if predictions else recogniser
    if out_dir is None:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)[:40]
        out_dir = paths.require_corpus_dir() / "evaluations" / f"{stamp}-{safe}-{set_name}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Evaluating {len(pairs)} pairs of the {set_name} set with {label}, up to {workers} at once. "
             f"Results go to {out_dir}. {export_failures} failed exports in the index are skipped.")
    results = []
    with parallel.pool(workers) as pool:
        running = {}

        def collect(block):
            for future, pair in parallel.finished(running, block):
                result = future.result()
                results.append(result)
                number = len(results)
                if "harness error" in result:
                    log.error(f"{number} of {len(pairs)}: {pair.name}: {result['harness error']}")
                elif "failed" in result:
                    log.warning(f"{number} of {len(pairs)}: {pair.name} failed: {result['failed']}")
                else:
                    log.info(f"{number} of {len(pairs)}: {pair.name}: {report.one_line(result)}")

        for pair in pairs:
            while len(running) >= 2 * workers:
                collect(block=True)
            future = pool.submit(evaluate_pair, pair, recogniser, out_dir / pair.id / pair.job,
                                 timeout, cpu_only, predictions, with_musicdiff)
            running[future] = pair
        while running:
            collect(block=True)
    results.sort(key=lambda r: (r["id"], r["job"]))
    text = report.overall(results, set_name, label, export_failures)
    (out_dir / "report.txt").write_text(text, encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(
        {"set": set_name, "recogniser": label, "export failures skipped": export_failures, "results": results},
        indent=1, default=str), encoding="utf-8")
    for result in results:
        if "harness error" not in result:
            path = out_dir / result["id"] / result["job"] / "report.txt"
            path.write_text(report.per_file(result), encoding="utf-8")
    return results, out_dir / "report.txt"
