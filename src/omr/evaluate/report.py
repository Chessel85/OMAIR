"""Plain-text reports from the harness results (spec, "Reports").

Headings are plain lines and lists start with a dash, so the reports read well
with NVDA. Overall figures add the counts over all files before dividing.
"""

import collections
import statistics

MAX_ERRORS_LISTED = 50
LOWEST_FILES = 10
BREAKDOWNS = (("engraver", "engraver"), ("font", "font"), ("genre", "genre"), ("texture", "texture"),
              ("ground truth", "ground-truth kind"))
TARGETS = {"note accuracy": 99.0, "structure": 95.0, "flagging": 90.0, "markings": 90.0}


def percent(part, whole):
    if not whole:
        return "no data"
    if part == whole:
        return "100 percent"
    value = 100.0 * part / whole
    if part < whole:
        value = min(value, 99.9)   # never round a shortfall up to 100
    return f"{value:.1f} percent"


def note_accuracy(notes):
    """M / (T + E), as counts (spec, "Note accuracy")."""
    return notes["exact"], notes["truth"] + notes["extra"]


def note_errors(notes):
    return notes["truth"] - notes["exact"] + notes["extra"]


def one_line(result):
    notes = result["notes"]
    m, d = note_accuracy(notes)
    structure = "structurally correct" if result["structure"]["correct"] else (
        f"{len(result['structure']['mismatches'])} structural mismatches")
    timing = f", {result['seconds']:.1f} seconds" if result.get("seconds") is not None else ""
    return f"note accuracy {percent(m, d)}, {note_errors(notes)} note errors, {structure}{timing}."


def _title(result):
    meta = result.get("meta", {})
    bits = [result["id"], meta.get("engraver", result["job"]), meta.get("font", "")]
    title = ", ".join(b for b in bits if b)
    if meta.get("title"):
        title += f" ({meta['title']})"
    return title


def per_file(result):
    lines = [f"Evaluation of {_title(result)}", ""]
    if "failed" in result:
        lines += [f"Summary: the recogniser failed: {result['failed']}. Every note counts as missing.", ""]
    else:
        lines += [f"Summary: {one_line(result)}", ""]
    notes = result["notes"]
    lines += ["Notes",
              f"- {notes['truth']} notes in the ground truth, {notes['output']} in the output.",
              f"- {notes['exact']} exactly right, {notes['wrong']} wrong, {notes['missing']} missing, {notes['extra']} extra."]
    for kind, count in sorted(notes["wrong by kind"].items()):
        lines.append(f"- {count} with a {kind} difference." if kind != "spelling only" else
                     f"- {count} of the pitch errors are spelling only (the same sounding pitch).")
    lines += ["", "Structure"]
    structure = result["structure"]
    if structure["correct"]:
        lines.append("- Structurally correct.")
    lines += [f"- {m}" for m in structure["mismatches"]] + [f"- Note: {m}" for m in structure.get("notes", [])]
    lines += ["", "Markings"]
    for kind, f in result["markings"].items():
        if f["truth"] or f["output"]:
            lines.append(f"- {kind}: {f['found']} of {f['truth']} found ({percent(f['found'], f['truth'])}), "
                         f"{f['output']} in the output.")
    for missed in [m for f in result["markings"].values() for m in f["missed"]][:MAX_ERRORS_LISTED]:
        lines.append(f"- Missed: {missed}")
    if "flags" in result:
        f = result["flags"]
        lines += ["", "Error flags",
                  f"- {f['covered']} of {f['errors']} note errors are in flagged bars ({percent(f['covered'], f['errors'])}).",
                  f"- {f['bars flagged']} of {f['bars']} bars flagged; {f['flagged bars with an error']} of them have an error."]
    errors = result.get("errors", [])
    if errors:
        lines += ["", f"Note errors, in bar order ({len(errors)})"]
        for e in errors[:MAX_ERRORS_LISTED]:
            lines.append(f"- {e['where']}: expected {e['expected']}, found {e['found']} ({e['kind']}).")
        if len(errors) > MAX_ERRORS_LISTED:
            lines.append(f"- {len(errors) - MAX_ERRORS_LISTED} more errors are listed in figures.json.")
    return "\n".join(lines) + "\n"


def _add(total, result):
    notes = result["notes"]
    total["files"] += 1
    total["exact"] += notes["exact"]
    total["truth"] += notes["truth"]
    total["extra"] += notes["extra"]
    total["correct structure"] += result["structure"]["correct"]
    total["failed"] += "failed" in result


def _group_line(name, total):
    return (f"- {name}: {total['files']} files, note accuracy {percent(total['exact'], total['truth'] + total['extra'])}, "
            f"{percent(total['correct structure'], total['files'])} structurally correct"
            + (f", {total['failed']} failed" if total["failed"] else "") + ".")


def overall(results, set_name, label, export_failures=0):
    unreadable = [r for r in results if "harness error" in r]
    results = [r for r in results if "harness error" not in r]
    lines = [f"Evaluation of the {set_name} set with {label}", ""]
    total = collections.Counter()
    completed = collections.Counter()
    for r in results:
        _add(total, r)
        if "failed" not in r:
            _add(completed, r)
    files = total["files"]
    lines.append(f"Summary: {files} files, note accuracy {percent(total['exact'], total['truth'] + total['extra'])}, "
                 f"{percent(total['correct structure'], files)} structurally correct, {total['failed']} failed.")
    lines.append("")
    lines += ["Targets"]
    lines.append(f"- ACC-1 note accuracy on vector PDFs (target {TARGETS['note accuracy']:g} percent): "
                 f"{percent(total['exact'], total['truth'] + total['extra'])}, "
                 f"or {percent(completed['exact'], completed['truth'] + completed['extra'])} over the {completed['files']} completed files.")
    lines.append(f"- ACC-1 files structurally correct (target {TARGETS['structure']:g} percent): "
                 f"{percent(total['correct structure'], files)}.")
    exact_pairs = [r for r in results if r.get("meta", {}).get("ground truth") == "exact"]
    found = sum(r["markings"][k]["found"] for r in exact_pairs for k in ("dynamic", "hairpin"))
    truth = sum(r["markings"][k]["truth"] for r in exact_pairs for k in ("dynamic", "hairpin"))
    lines.append(f"- ACC-6 recall of dynamics and hairpins (target {TARGETS['markings']:g} percent, exact pairs only): "
                 f"{percent(found, truth)} ({found:,} of {truth:,}).")
    flagged = [r for r in results if "flags" in r]
    if flagged:
        covered = sum(r["flags"]["covered"] for r in flagged)
        errors = sum(note_errors(r["notes"]) for r in results)
        bars = sum(r["flags"]["bars"] for r in flagged)
        flagged_bars = sum(r["flags"]["bars flagged"] for r in flagged)
        lines.append(f"- ACC-4 note errors in flagged bars (target {TARGETS['flagging']:g} percent): "
                     f"{percent(covered, errors)} ({covered:,} of {errors:,}); {percent(flagged_bars, bars)} of bars flagged.")
    else:
        lines.append("- ACC-4 error flagging: the recogniser wrote no flag files.")
    lines.append("")

    lines.append("Note errors")
    kinds = collections.Counter()
    for r in results:
        n = r["notes"]
        kinds["wrong"] += n["wrong"]
        kinds["missing"] += n["missing"]
        kinds["extra"] += n["extra"]
        for k, v in n["wrong by kind"].items():
            kinds[f"wrong: {k}"] += v
    lines.append(f"- {total['truth']:,} ground-truth notes, {total['exact']:,} exactly right, {kinds['wrong']:,} wrong, "
                 f"{kinds['missing']:,} missing, {kinds['extra']:,} extra.")
    for k in sorted(k for k in kinds if k.startswith("wrong: ")):
        lines.append(f"- {k[7:]}: {kinds[k]:,}.")
    lines.append("")

    lines.append("Diagnostic figures")
    for name in ("pitch and duration", "sounding pitch", "staff", "voice", "ties", "rests"):
        a = sum(next(iter(r["diagnostics"][name].values())) for r in results)
        b = sum(r["diagnostics"][name]["of"] for r in results)
        lines.append(f"- {name}: {percent(a, b)}.")
    marks = collections.defaultdict(lambda: [0, 0])
    for r in results:
        for k, f in r.get("note marks", {}).items():
            marks[k][0] += f["found"]
            marks[k][1] += f["truth"]
        for k, f in r["markings"].items():
            if k not in ("dynamic", "hairpin"):
                marks[k][0] += f["found"]
                marks[k][1] += f["truth"]
    for k, (a, b) in sorted(marks.items()):
        if b:
            lines.append(f"- {k}: {percent(a, b)} of {b:,} found.")
    lines.append("")

    for field, heading in BREAKDOWNS:
        groups = collections.defaultdict(collections.Counter)
        for r in results:
            _add(groups[r.get("meta", {}).get(field, "unknown")], r)
        lines.append(f"By {heading}")
        lines += [_group_line(name, groups[name]) for name in sorted(groups)]
        lines.append("")

    nedded = [r["musicdiff"] for r in results if isinstance(r.get("musicdiff"), dict) and "failed" not in r["musicdiff"]]
    lines.append("Comparison with published work")
    if nedded:
        for level in ("notes and rests", "all objects"):
            values = [m[level]["omr_ned"] for m in nedded]
            lines.append(f"- Mean OMR-NED, {level}: {statistics.fmean(values):.4f} over {len(values)} files.")
        failures = sum(1 for r in results if isinstance(r.get("musicdiff"), dict) and "failed" in r["musicdiff"])
        if failures:
            lines.append(f"- musicdiff could not compare {failures} files.")
    else:
        lines.append("- musicdiff was not run.")
    lines.append("- TEDn is not computed yet (open item).")
    lines.append("")

    timed = [r["seconds"] for r in results if r.get("seconds") is not None]
    if timed:
        lines += ["Timing", f"- Median {statistics.median(timed):.1f} seconds per file, longest {max(timed):.1f} seconds.", ""]

    ranked = sorted((r for r in results if "failed" not in r and note_errors(r["notes"])),
                    key=lambda r: note_accuracy(r["notes"])[0] / max(1, note_accuracy(r["notes"])[1]))
    if ranked:
        lines.append(f"Lowest {min(LOWEST_FILES, len(ranked))} files by note accuracy")
        for r in ranked[:LOWEST_FILES]:
            lines.append(f"- {_title(r)}: {one_line(r)}")
    else:
        lines += ["Lowest files by note accuracy", "- Every completed file has no note errors."]
    lines.append("")
    failed = [r for r in results if "failed" in r]
    lines.append(f"Failed files ({len(failed)})")
    lines += [f"- {_title(r)}: {r['failed']}" for r in failed] or ["- None."]
    if unreadable:
        lines += ["", f"Ground truth that could not be read ({len(unreadable)}), not counted:"]
        lines += [f"- {r['id']} {r['job']}: {r['harness error']}" for r in unreadable]
    if export_failures:
        lines += ["", f"Also, {export_failures} exports failed when the corpus was made, so those pairs do not exist and are not counted."]
    return "\n".join(lines) + "\n"
