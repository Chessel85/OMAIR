"""Check the MusicXML writer (Stage 1.6) on a set of pairs.

For each pair (default: the regression set in the repository) the score is
read from the PDF, written as MusicXML, and checked four ways:

- Round trip: the harness's reader (`omr.evaluate.events`) reads the written
  file back into the same notes, rests, markings, structure, bars and parts
  (`omr.musicxml.round_trip_differences`).
- Figures: the harness scores the written file and its flag file
  (`metrics.compare`, as `omr evaluate` does) exactly as it scores the
  score in memory (`metrics.compare_scores`, as scripts/check_notes.py
  does): notes, structure, markings and flags (ACC-4).
- Schema: the file is valid MusicXML 4.0, when the schema is found
  (--schema, default the corpus folder's tools/musicxml-4.0-schema).
- Braille, with --braille: whether music21 translates the file, and what
  it leaves out. A file music21 cannot translate is listed, but is not a
  problem of the writer's and does not fail the check.

Usage:
  python scripts/check_convert.py [--set-root FOLDER] [--job NAME] [--score ID] [--limit N]
                                  [--workers N] [--schema FILE] [--braille] [--keep FOLDER] [--out FILE]

The command fails (exit status 1) if any pair could not be read or written,
loses or adds anything in the round trip, scores differently, or is not
valid. CI runs it on the regression set.
"""

import argparse
import collections
import dataclasses
import json
import sys
import tempfile
import time
from pathlib import Path

from omr import parallel, paths
from omr.log import ProgressLog

sys.path.insert(0, str(Path(__file__).parent))
from check_notes import pairs  # noqa: E402

SCHEMA = Path("tools") / "musicxml-4.0-schema" / "musicxml.xsd"
_schema = {}


def _validator(schema_path):
    if schema_path not in _schema:
        from lxml import etree

        _schema[schema_path] = etree.XMLSchema(etree.parse(str(schema_path)))
    return _schema[schema_path]


def _figures(f):
    """The figures a written file must share with the score in memory. The
    split of wrong notes by kind is left out: when two notes could match
    either of two, which pairing the harness keeps depends on the order the
    notes are listed in, which a file changes."""
    notes = {k: v for k, v in f["notes"].items() if k != "wrong by kind"}
    return {"notes": notes, "structure correct": f["structure"].get("correct"), "flags": f.get("flags"),
            "markings": {k: (v["truth"], v["found"], v["output"]) for k, v in f["markings"].items()},
            "note marks": f["note marks"]}


def check_pair(pdf, truth_path, out_path, schema_path, with_braille):
    from omr import braille, musicxml
    from omr.evaluate import events, metrics
    from omr.pdf import rules, structure

    result = {"problems": []}
    started = time.time()
    score, _ = structure.read_pdf(pdf, notes=True)
    result["read seconds"] = time.time() - started
    started = time.time()
    left_out = musicxml.write(score, out_path, title=Path(pdf).stem)
    result["left out"] = len(left_out)
    result["write seconds"] = time.time() - started
    back = events.read(out_path)
    for what, (lost, added) in musicxml.round_trip_differences(score, back).items():
        result["problems"].append(f"round trip: {len(lost)} {what} lost, {len(added)} added, "
                                  f"for example {(lost or added)[0]}")
    # rehearsal and metronome marks, which the harness's reader does not read
    from check_markings import truth_extras

    _, rehearsals, metronomes, _, _ = truth_extras(events.read_root(out_path))
    first_part = [m for m in score.markings if m.part == 0]
    for kind, read_back in (("rehearsal", rehearsals), ("metronome", metronomes)):
        kept = collections.Counter((m.bar, m.value) for m in first_part if m.kind == kind)
        if kept != collections.Counter(read_back):
            result["problems"].append(f"round trip: {kind} marks differ: {sorted(kept.items())} "
                                      f"read back as {sorted(read_back)}")
    truth = events.read(truth_path)
    # notes left out to keep four voices a staff (omr.musicxml._merge_voices) are not in the file
    gone = {id(e) for e in left_out}
    kept = dataclasses.replace(score, notes=[n for n in score.notes if id(n) not in gone],
                               rests=[r for r in score.rests if id(r) not in gone])
    flags = rules.check(score)
    flag_path = out_path.with_name("flags.json")
    flag_path.write_text(json.dumps(rules.flag_file(flags)), encoding="utf-8")
    in_memory = _figures(metrics.compare_scores(truth, kept, rules.as_harness_flags(flags)))
    written = _figures(metrics.compare(truth_path, out_path, flags=metrics.read_flags(flag_path)))
    # the words written for jumps found with no words are output words the score in memory lacks
    added = len(musicxml.added_words(score))
    if added and "words" in in_memory["markings"]:
        t, f, o = in_memory["markings"]["words"]
        in_memory["markings"]["words"] = (t, f, o + added)
    for key in in_memory:
        if in_memory[key] != written[key]:
            result["problems"].append(f"figures: {key} differ: in memory {in_memory[key]}, written {written[key]}")
    result["notes"] = written["notes"]
    if schema_path is not None:
        from lxml import etree

        validator = _validator(schema_path)
        if not validator.validate(etree.parse(str(out_path))):
            first = validator.error_log[0]
            result["problems"].append(f"schema: {len(validator.error_log)} errors, the first at line {first.line}: "
                                      f"{first.message}")
    if with_braille:
        started = time.time()
        try:
            text, left_out = braille.translate(out_path)
            result["braille lines"] = text.count("\n")
            result["braille left out"] = left_out
        except braille.BrailleError as error:
            result["braille failed"] = str(error)   # music21's limits, reported apart from the writer's problems
        result["braille seconds"] = time.time() - started
    return result


def report(results, schema_path, with_braille):
    lines = ["# MusicXML writer check (Stage 1.6)", ""]
    ok = sum(1 for r in results.values() if not r["problems"])
    lines.append(f"- Pairs checked: {len(results)}; with no problem: {ok}.")
    lines.append(f"- Schema: {'MusicXML 4.0, ' + str(schema_path) if schema_path else 'not checked (no schema found)'}.")
    if results:
        lines.append(f"- Writing took {sum(r['write seconds'] for r in results.values()):.1f} seconds in all, "
                     f"reading the PDFs {sum(r['read seconds'] for r in results.values()):.1f}.")
    left = [r["left out"] for r in results.values() if r.get("left out")]
    lines.append(f"- Notes and rests left out to keep four voices a staff: {sum(left)}, in {len(left)} files.")
    if with_braille:
        done = [r for r in results.values() if "braille lines" in r]
        left = collections.Counter(item.split(":")[0] for r in done for item in r["braille left out"])
        lines.append(f"- Braille: {len(done)} of {len(results)} files translated, "
                     f"{sum(r['braille seconds'] for r in results.values()):.1f} seconds in all.")
        if left:
            lines.append("- Left out of the braille or changed, by kind, with the number of times: "
                         + "; ".join(f"{k} {v}" for k, v in left.most_common()) + ".")
    failures = [(key, r["braille failed"]) for key, r in sorted(results.items()) if "braille failed" in r]
    if failures:
        lines += ["", "## No braille (music21 could not translate the file)", ""]
        lines += [f"- {score}, {job}: {reason}" for (score, job), reason in failures]
    problems = [(key, p) for key, r in sorted(results.items()) for p in r["problems"]]
    if problems:
        lines += ["", "## Problems", ""]
        lines += [f"- {score}, {job}: {p}" for (score, job), p in problems]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set-root", default=str(paths.REPO_ROOT / "regression"))
    parser.add_argument("--job", help="Only this engraver job, for example musescore4-base.")
    parser.add_argument("--score", help="Only this score id.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--schema", help="The MusicXML 4.0 schema (musicxml.xsd).")
    parser.add_argument("--braille", action="store_true", help="Also translate each file into braille.")
    parser.add_argument("--keep", metavar="FOLDER", help="Keep the written files in FOLDER/<score id>/<job>.")
    parser.add_argument("--out", help="Also write the report to this file.")
    args = parser.parse_args(argv)
    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = ProgressLog("check-convert", path=str(logs / "check-convert.log"))
    schema_path = Path(args.schema) if args.schema else None
    if schema_path is None:
        try:
            candidate = paths.require_corpus_dir() / SCHEMA
            schema_path = candidate if candidate.is_file() else None
        except paths.CorpusDirError:
            schema_path = None
    if schema_path is None:
        log.warning("No MusicXML 4.0 schema found, so validity is not checked. Give one with --schema.")
    elif not schema_path.is_file():
        log.error(f"The schema {schema_path} does not exist.")
        return log.finish("0 files checked")
    todo = pairs(args.set_root, args.job, args.limit, args.score)
    if not todo:
        log.error(f"No pairs found in {args.set_root}. Check the folder has an index.txt.")
        return log.finish("0 files checked")
    results = {}
    failed = 0
    with tempfile.TemporaryDirectory() as scratch:
        base = Path(args.keep) if args.keep else Path(scratch)
        with parallel.pool(args.workers) as executor:
            running = {}
            for score, job, pdf, truth in todo:
                out_path = base / score / job / "score.musicxml"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                future = executor.submit(check_pair, pdf, truth, out_path, schema_path, args.braille)
                running[future] = (score, job)
            while running:
                for future, (score, job) in parallel.finished(running, block=True):
                    if (len(results) + failed + 1) % 50 == 0:
                        log.info(f"{len(results) + failed + 1} of {len(todo)} pairs checked.")
                    try:
                        results[(score, job)] = r = future.result()
                        if r["problems"]:
                            log.error(f"{score} {job}: {'; '.join(r['problems'])}")
                    except Exception as error:   # report and go on with the rest
                        failed += 1
                        log.error(f"{score} {job}: {type(error).__name__}: {error}")
    # in the set's order, not the order the workers finished in
    results = {(s, j): results[(s, j)] for s, j, *_ in todo if (s, j) in results}
    text = report(results, schema_path, args.braille)
    encoding = sys.stdout.encoding or "ascii"
    print(text.encode(encoding, "replace").decode(encoding))
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        log.info(f"Report written to {args.out}.")
    with_problems = sum(1 for r in results.values() if r["problems"])
    return log.finish(f"{len(results)} files checked, {failed} failed, {with_problems} with problems")


if __name__ == "__main__":
    sys.exit(main())
