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
    """M / (T + E + C), as counts, C being the clef errors (spec, "Note accuracy")."""
    return notes["exact"], notes["truth"] + notes["extra"] + notes.get("clef errors", 0)


def note_errors(notes):
    return notes["truth"] - notes["exact"] + notes["extra"] + notes.get("clef errors", 0)


def error_words(result):
    """"12 note errors in 6 bars", counting each ground-truth bar once."""
    count = note_errors(result["notes"])
    if not count:
        return "0 note errors"
    bars = len({e["bar"] for e in result.get("errors", [])})
    return f"{count} note error{'s' if count != 1 else ''} in {bars} bar{'s' if bars != 1 else ''}"


def one_line(result):
    notes = result["notes"]
    m, d = note_accuracy(notes)
    structure = "structurally correct" if result["structure"]["correct"] else (
        f"{len(result['structure']['mismatches'])} structural mismatches")
    timing = f", {result['seconds']:.1f} seconds" if result.get("seconds") is not None else ""
    return f"note accuracy {percent(m, d)}, {error_words(result)}, {structure}{timing}."


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
    if notes.get("clef errors"):
        strict = result["diagnostics"]["strict note accuracy"]
        lines.append(f"- {notes['clef errors']} clef error{'s' if notes['clef errors'] > 1 else ''}, each counted as one error. "
                     f"Without the clef rule the note accuracy would be {percent(strict['matched'], strict['of'])}.")
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
    if "flag file problem" in result:
        lines.append(f"- {result['flag file problem'][0].upper()}{result['flag file problem'][1:]}.")
    errors = result.get("errors", [])
    if errors:
        lines += ["", f"Note errors, in bar order ({len(errors)})"]
        for e in errors[:MAX_ERRORS_LISTED]:
            lines.append(f"- {e['where']}: expected {e['expected']}, found {e['found']} ({e['kind']})."
                         + (f" {e['words']}" if "words" in e else ""))
        if len(errors) > MAX_ERRORS_LISTED:
            lines.append(f"- {len(errors) - MAX_ERRORS_LISTED} more errors are listed in figures.json.")
    return "\n".join(lines) + "\n"


def _fraction(value):
    """A share as (part, whole) for `percent`, keeping exactly 1 as 100 percent."""
    return (1, 1) if value == 1 else (value, 1)


def _add(total, result):
    notes = result["notes"]
    total["files"] += 1
    total["exact"] += notes["exact"]
    total["truth"] += notes["truth"]
    total["extra"] += notes["extra"]
    total["clef errors"] += notes.get("clef errors", 0)
    total["correct structure"] += result["structure"]["correct"]
    total["failed"] += "failed" in result


def _group_line(name, total):
    return (f"- {name}: {total['files']} files, note accuracy {percent(*note_accuracy(total))}, "
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
    lines.append(f"Summary: {files} files, note accuracy {percent(*note_accuracy(total))}, "
                 f"{percent(total['correct structure'], files)} structurally correct, {total['failed']} failed.")
    accuracies = sorted(note_accuracy(r["notes"])[0] / note_accuracy(r["notes"])[1]
                        for r in results if note_accuracy(r["notes"])[1])
    if accuracies:
        lines.append(f"Per-file note accuracy: median {percent(*_fraction(statistics.median(accuracies)))}, "
                     f"lowest {percent(*_fraction(accuracies[0]))}, highest {percent(*_fraction(accuracies[-1]))}.")
    lines.append("")
    lines += ["Targets"]
    lines.append(f"- ACC-1 note accuracy on vector PDFs (target {TARGETS['note accuracy']:g} percent): "
                 f"{percent(*note_accuracy(total))}, "
                 f"or {percent(*note_accuracy(completed))} over the {completed['files']} completed files.")
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
    bad_flags = sum(1 for r in results if "flag file problem" in r)
    if bad_flags:
        lines.append(f"- {bad_flags} flag files could not be read and count as no flags; each file's report says why.")
    lines.append("")

    lines.append("Note errors")
    kinds = collections.Counter()
    for r in results:
        n = r["notes"]
        kinds["wrong"] += n["wrong"]
        kinds["missing"] += n["missing"]
        kinds["extra"] += n["extra"]
        kinds["clef errors"] += n.get("clef errors", 0)
        for k, v in n["wrong by kind"].items():
            kinds[f"wrong: {k}"] += v
    lines.append(f"- {total['truth']:,} ground-truth notes, {total['exact']:,} exactly right, {kinds['wrong']:,} wrong, "
                 f"{kinds['missing']:,} missing, {kinds['extra']:,} extra, {kinds['clef errors']:,} clef errors "
                 "(each counted as one error).")
    for k in sorted(k for k in kinds if k.startswith("wrong: ")):
        lines.append(f"- {k[7:]}: {kinds[k]:,}.")
    lines.append("")

    lines.append("Diagnostic figures")
    for name in ("strict note accuracy", "pitch and duration", "sounding pitch", "staff", "voice", "ties", "rests"):
        if name == "strict note accuracy":
            # Results from before the clef rule have no strict figure: their note accuracy is the strict one.
            pairs = [r["diagnostics"].get(name) or {"matched": r["notes"]["exact"],
                     "of": r["notes"]["truth"] + r["notes"]["extra"]} for r in results]
        else:
            pairs = [r["diagnostics"][name] for r in results]
        a = sum(next(iter(d.values())) for d in pairs)
        b = sum(d["of"] for d in pairs)
        lines.append(f"- {name}: {percent(a, b)}.")
    lines.append("")

    # Engraver-input ground truth may hold markings the engraver did not draw, so
    # marking figures are given separately for exact and engraver-input pairs.
    lines.append("Markings found, by ground-truth kind")
    marks = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for r in results:
        side = "exact" if r.get("meta", {}).get("ground truth") == "exact" else "engraver input"
        for k, f in list(r["markings"].items()) + list(r.get("note marks", {}).items()):
            marks[k][side][0] += f["found"]
            marks[k][side][1] += f["truth"]
    for k in sorted(marks):
        sides = [f"{side} pairs {percent(a, b)} of {b:,}" for side, (a, b) in sorted(marks[k].items(),
                 key=lambda item: item[0] != "exact") if b]
        if sides:
            lines.append(f"- {k}: " + "; ".join(sides) + ".")
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
        lines += ["", f"Pairs the harness could not evaluate ({len(unreadable)}), not counted:"]
        lines += [f"- {r['id']} {r['job']}: {r['harness error']}" for r in unreadable]
    if export_failures:
        lines += ["", f"Also, {export_failures} exports failed when the corpus was made, so those pairs do not exist and are not counted."]
    return "\n".join(lines) + "\n"
