"""`omr confidence`: read vector PDFs and report the bars that may be wrong
(Stage 1.5): the first confidence report (OUT-3, OUT-4), and with --out the
flag file the evaluation harness reads (ACC-4). See
docs/notes/confidence-spec.md.
"""

import json
from fractions import Fraction
from pathlib import Path

from omr.inspect import InspectError, open_document


def read_file(path):
    """The Score read with notes. Raises InspectError."""
    from omr.pdf import structure

    open_document(path).close()   # the usual message for a missing or unreadable file
    try:
        score, _ = structure.read_pdf(path, notes=True)
        return score
    except InspectError:
        raise
    except Exception as error:   # report the file as failed, with the reason
        raise InspectError(f"{Path(path).name} could not be read ({error}).")


def _staff_words(score, part, staff):
    name = score.parts[part].name if part < len(score.parts) else ""
    words = name or f"part {part + 1}"
    staves = score.parts[part].staves if part < len(score.parts) else 1
    if staff is not None and staves > 1:
        if staves == 2:
            words += ", upper staff" if staff == 1 else ", lower staff"
        else:
            words += f", staff {staff}"
    return words


def _beat_words(score, part, bar, onset):
    """Beat 1, beat 2.5 and so on, counted in the time signature's beat."""
    beat_type = 4
    for e in score.structure:
        if e.kind == "time" and e.part == part and e.bar <= bar:
            beat_type = int(e.value.split("/")[1])
    beat = onset * Fraction(beat_type, 4) + 1
    return f"beat {float(beat):g}"


def place_words(score, flag):
    """Where a flag is, in words: page, system, bar, part and staff, and the
    beat when it is known."""
    bar = score.bars[flag.bar] if flag.bar < len(score.bars) else None
    words = []
    if bar is not None:
        words.append(f"Page {bar.page}, system {bar.system}, bar {bar.number}")
    else:
        words.append(f"Bar {flag.bar + 1}")
    words.append(_staff_words(score, flag.part, flag.staff))
    onsets = [o for o in flag.onsets if o is not None]
    if onsets:
        words.append(_beat_words(score, flag.part, flag.bar, min(onsets)))
    return ", ".join(words)


def report_lines(path, score, flags):
    """The confidence report (OUT-3, OUT-4): a summary, the flagged bars in
    score order, then the things also worth checking that seldom mean a
    wrong note (docs/notes/confidence-spec.md)."""
    from omr.pdf import rules

    joined = rules.bar_flags(flags, rules.FLAG_RULES)
    others = rules.bar_flags(flags, set(rules.RULE_PRECISION) - rules.FLAG_RULES)
    bars = len(score.bars)
    flagged_bars = len({b.bar for b in joined})
    out = [f"File: {Path(path).name}",
           f"Summary: {bars} bar{'s' if bars != 1 else ''}, {bars - flagged_bars} high confidence, "
           f"{len(joined)} flagged."]
    if joined:
        out.append("Flagged, in score order:")
    for b in joined:
        out.append(f"- {place_words(score, b)}: {'; '.join(reason for _, reason in b.reasons)}.")
    if others:
        out.append("Also worth checking:")
    for b in others:
        out.append(f"- {place_words(score, b)}: {'; '.join(reason for _, reason in b.reasons)}.")
    return out


def run(files, out_dir=None, out=print):
    from omr.pdf import rules

    done = failed = 0
    for path in files:
        try:
            score = read_file(path)
        except InspectError as error:
            failed += 1
            out(f"File: {Path(path).name}")
            out(f"Failed: {error}")
            out("")
            continue
        done += 1
        flags = rules.check(score)
        lines = report_lines(path, score, flags)
        for line in lines:
            out(line)
        out("")
        if out_dir:
            folder = Path(out_dir) / Path(path).stem
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "flags.json").write_text(json.dumps(rules.flag_file(flags), indent=1), encoding="utf-8")
            (folder / "confidence.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
            out(f"Flag file and report written to {folder}.")
            out("")
    out(f"Summary: {done} file{'s' if done != 1 else ''} read, {failed} failed.")
    return 1 if failed else 0
