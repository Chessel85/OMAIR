"""`omr layout`: report the structure read from vector PDFs (Stage 1.2):
parts, systems, bars, and the clef, key and time changes, repeats, endings
and navigation marks, in words. See docs/notes/layout-spec.md.
"""

import json
from collections import Counter
from pathlib import Path

from omr.inspect import InspectError, open_document

KEY_NAMES = {0: "no sharps or flats"}


def _key_words(fifths):
    n = int(fifths)
    if n == 0:
        return "no sharps or flats"
    word = "sharp" if n > 0 else "flat"
    return f"{abs(n)} {word}{'s' if abs(n) != 1 else ''}"


def _clef_words(value):
    names = {"G 2": "treble", "F 4": "bass", "C 3": "alto", "C 4": "tenor", "C 1": "soprano",
             "F 3": "baritone", "G 1": "French violin", "percussion": "percussion", "TAB 5": "tablature"}
    base, _, octave = value.partition(" octave ")
    words = names.get(base, f"{base} line")
    if octave:
        words += f", {'an octave' if abs(int(octave)) == 1 else 'two octaves'} {'lower' if int(octave) < 0 else 'higher'}"
    return words


def read_file(path):
    """(Score, layouts). Raises InspectError."""
    from omr.pdf import layout, structure, symbols

    doc = open_document(path)
    try:
        pages = symbols.read_document(doc)
        layouts = layout.read_document(doc, pages)
        return structure.read_structure(layouts), layouts
    except InspectError:
        raise
    except Exception as error:   # report the file as failed, with the reason
        raise InspectError(f"{Path(path).name} could not be read ({error}).")
    finally:
        doc.close()


def report_lines(path, score, layouts):
    from omr.evaluate import events

    systems = [sy for pl in layouts for sy in pl.systems]
    out = [f"File: {Path(path).name}"]
    attached = sum(len(pl.attached) for pl in layouts)
    total = sum(len(pl.symbols) for pl in layouts)
    out.append(f"Summary: {len(layouts)} page{'s' if len(layouts) != 1 else ''}, {len(systems)} systems, "
               f"{len(score.parts)} part{'s' if len(score.parts) != 1 else ''}, {len(score.bars)} bars. "
               f"{attached} of {total} symbols placed on a staff.")
    out.append("Parts:")
    for n, part in enumerate(score.parts, 1):
        name = f" ({part.name})" if part.name else ""
        out.append(f"- Part {n}{name}: {part.staves} {'staff' if part.staves == 1 else 'staves'}.")
    per_page = Counter(pl.page for pl in layouts for _ in pl.systems)
    out.append("Systems by page: " + ", ".join(f"page {p} has {n}" for p, n in sorted(per_page.items())) + ".")
    changes = sorted(events.signature_changes(score), key=lambda e: (e.bar, e.part, e.kind))
    if changes:
        out.append("Changes, by bar (restated clefs, keys and times left out):")
    for e in changes:
        where = f"Bar {e.bar + 1}, part {e.part + 1}"
        if e.kind == "clef":
            staff = f" staff {e.staff}" if score.parts[e.part].staves > 1 else ""
            place = "" if e.onset == 0 else ", within the bar"
            out.append(f"- {where}{staff}: {_clef_words(e.value)} clef{place}.")
        elif e.kind == "key":
            out.append(f"- {where}: key signature of {_key_words(e.value)}.")
        elif e.kind == "time":
            out.append(f"- {where}: time signature {e.value.replace('/', ' over ')}.")
        elif e.kind == "repeat" and e.part == 0:
            out.append(f"- Bar {e.bar + 1}: {'start' if e.value == 'forward' else 'end'} of a repeat.")
        elif e.kind == "ending" and e.part == 0:
            kind, _, numbers = e.value.partition(" ")
            out.append(f"- Bar {e.bar + 1}: ending {numbers} {'starts' if kind == 'start' else 'ends'}.")
        elif e.kind == "navigation":
            out.append(f"- Bar {e.bar + 1}: {e.value}.")
    return out


def run(files, json_path=None, out=print):
    done, failed, records = 0, 0, []
    for path in files:
        try:
            score, layouts = read_file(path)
        except InspectError as error:
            failed += 1
            out(f"File: {Path(path).name}")
            out(f"Failed: {error}")
            out("")
            records.append({"file": str(path), "error": str(error)})
            continue
        done += 1
        for line in report_lines(path, score, layouts):
            out(line)
        out("")
        records.append({
            "file": str(path), "error": None,
            "parts": [{"name": p.name, "staves": p.staves} for p in score.parts],
            "bars": len(score.bars),
            "structure": [{"kind": e.kind, "value": e.value, "part": e.part, "staff": e.staff,
                           "bar": e.bar, "at_start": e.onset == 0} for e in score.structure],
        })
    if json_path:
        Path(json_path).write_text(json.dumps(records, indent=2), encoding="utf-8")
        out(f"JSON written to {json_path}.")
    out(f"Summary: {done} file{'s' if done != 1 else ''} read, {failed} failed.")
    return 1 if failed else 0
