"""`omr convert`: read PDFs and page images and write MusicXML, braille, the confidence
report and the flag file (Stage 1.6). See docs/notes/musicxml-spec.md.

For each FILE the outputs go to FOLDER (default: the PDF's own folder),
named after the PDF: name.musicxml, name.brf, name-report.txt and
name-flags.json. With one FILE, --musicxml, --braille, --report and --flags
give a path for that output instead.
"""

import json
import sys
from pathlib import Path

from omr import braille as brl, confidence_report, musicxml
from omr.confidence_report import read_file
from omr.documents import IMAGE_SUFFIXES, InspectError, open_document
from omr.pdf import rules

OUTPUTS = ("musicxml", "braille", "report", "flags")


def say(line):
    """Print a line the console can show (a flat sign in a file name must not stop the run)."""
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    print(line.encode(encoding, "replace").decode(encoding), flush=True)


def default_paths(pdf, out_dir=None, braille_format=None):
    folder = Path(out_dir) if out_dir else Path(pdf).parent
    stem = Path(pdf).stem
    braille_name = f"{stem}-braille.txt" if braille_format == "unicode" else f"{stem}.brf"
    return {"musicxml": folder / f"{stem}.musicxml", "braille": folder / braille_name,
            "report": folder / f"{stem}-report.txt", "flags": folder / f"{stem}-flags.json"}


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def read_score(path):
    """(Score, pages in the file). Raises InspectError with the reason."""
    name = Path(path).name
    suffix = Path(path).suffix.lower()
    if suffix != ".pdf" and suffix not in IMAGE_SUFFIXES:
        raise InspectError(f"{name} is not a PDF or an image (PNG, JPEG or TIFF), so it cannot be converted.")
    doc = open_document(path)
    pages = doc.page_count
    doc.close()
    score = read_file(path)
    if not score.bars:
        raise InspectError(f"no staves were found in {name}. Run omr inspect on the file to see its page types.")
    return score, pages


def convert_file(path, paths, braille=True, braille_format=None, out=say):
    """Convert one PDF. Returns (failed, warnings)."""
    score, page_count = read_score(path)
    flags = rules.check(score)
    lines = confidence_report.report_lines(path, score, flags)
    music_pages = sorted({b.page for b in score.bars})
    empty = [p for p in range(1, page_count + 1) if p not in music_pages]
    notes = len([n for n in score.notes if not n.grace])
    read = (f"Read: {_plural(page_count, 'page')}, {_plural(len(score.parts), 'part')}, "
            f"{_plural(len(score.bars), 'bar')}, {_plural(notes, 'note')}.")
    if empty:
        read += f" No music was read on page{'s' if len(empty) > 1 else ''} {', '.join(map(str, empty))}."
    out(read)
    out(lines[1].replace("Summary: ", "Confidence: "))
    for key in OUTPUTS:
        if paths.get(key) is not None:
            Path(paths[key]).parent.mkdir(parents=True, exist_ok=True)
    left_out = musicxml.write(score, paths["musicxml"], title=Path(path).stem)
    written = [("MusicXML", paths["musicxml"], "")]
    failed = warnings = 0
    if left_out:
        warnings += 1
        notes_out = [e for e in left_out if hasattr(e, "pitch")]
        bars = sorted({(e.part, e.bar, e.staff) for e in left_out})
        out(f"Warning: {_plural(len(notes_out), 'note')} and {_plural(len(left_out) - len(notes_out), 'rest')} "
            "were not written to the MusicXML, as they would make more than four voices on a staff. "
            "The report says where.")
        lines.append("Not written to the MusicXML (more than four voices on a staff, which MuseScore cannot open):")
        for part, bar, staff in bars:
            here = [e for e in left_out if (e.part, e.bar, e.staff) == (part, bar, staff)]
            words = ", ".join(e.pitch.words() if hasattr(e, "pitch") else "a rest" for e in here)
            place = confidence_report.place_words(score, rules.BarFlag(part, staff, bar, [], 0.0, [min(e.onset for e in here)]))
            lines.append(f"- {place}: {words}.")
    if braille:
        try:
            count, left_out = brl.write(paths["musicxml"], paths["braille"], braille_format)
            written.append(("braille", paths["braille"], f", {_plural(count, 'line')}"))
            if left_out:
                warnings += 1
                out(f"Warning: the braille leaves out {_plural(len(left_out), 'item')} the translator "
                    f"cannot write: {'; '.join(sorted(set(left_out))[:5])}. The report lists them.")
                lines += ["Not in the braille (the translator cannot write them):"]
                lines += [f"- {item}" for item in left_out]
        except brl.BrailleError as error:
            failed = 1
            out(f"Failed: no braille was written: {error}. The MusicXML is still written; "
                "try it in another braille translator.")
            lines += [f"No braille was written: {error}."]
    paths["report"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    written.append(("report", paths["report"], ""))
    paths["flags"].write_text(json.dumps(rules.flag_file(flags), indent=1), encoding="utf-8")
    written.append(("flag file", paths["flags"], ""))
    folders = {Path(p).parent.resolve() for _, p, _ in written}
    if len(folders) == 1:
        out(f"Written to {folders.pop()}: " + "; ".join(f"{Path(p).name} ({what}{extra})" for what, p, extra in written) + ".")
    else:
        out("Written: " + "; ".join(f"{what} {p}{extra}" for what, p, extra in written) + ".")
    return failed, warnings


def run(files, out_dir=None, chosen=None, braille=True, braille_format=None, out=say):
    """Convert each file. `chosen` holds paths given for single outputs
    ({"musicxml": path, ...}), allowed with one file only."""
    chosen = {k: v for k, v in (chosen or {}).items() if v}
    if chosen and len(files) != 1:
        out(f"--{'/--'.join(sorted(chosen))} name one output file, so give one PDF, not {len(files)}.")
        out("Summary: nothing converted; the command was used wrongly.")
        return 2
    converted = failed = warnings = 0
    for path in files:
        out(f"File: {Path(path).name}")
        paths = default_paths(path, out_dir, braille_format)
        paths.update({k: Path(v) for k, v in chosen.items()})
        try:
            file_failed, file_warnings = convert_file(path, paths, braille, braille_format, out)
            converted += not file_failed
            failed += file_failed
            warnings += file_warnings
        except InspectError as error:
            failed += 1
            out(f"Failed: {error}")
        except OSError as error:
            failed += 1
            out(f"Failed: an output could not be written ({error}). Check that the folder exists "
                "and the file is not open in another program.")
        out("")
    out(f"Summary: {_plural(converted, 'file')} converted, {failed} failed, {_plural(warnings, 'warning')}.")
    return 1 if failed else 0
