"""`omr symbols`: name the music symbols in vector PDFs and report what could
not be named (Stage 1.1). Plain text for people, JSON for scripts. See
docs/notes/symbol-spec.md.
"""

import json
from collections import Counter
from pathlib import Path

from omr.inspect import InspectError, open_document, parse_pages

TABLE_WORDS = {
    "smufl": "SMuFL code points",
    "emmentaler": "the Emmentaler table",
    "sonata": "the Sonata table (Opus, Helsinki, Maestro)",
    "sonata-special": "the Sonata companion table (OpusSpecial, HelsinkiSpecial)",
}
HOW_WORDS = {
    "codes": "a SMuFL font",
    "name": "known by its name",
    "glyph names": "known by its glyph names",
    "shapes": "identified by its glyph shapes",
}


def read_file(path, pages=None):
    """{file, pages, results: [PageSymbols]}. Raises InspectError."""
    from omr.pdf import symbols

    doc = open_document(path)
    try:
        numbers = parse_pages(pages, len(doc))
        try:
            results = symbols.read_document(doc, numbers)
        except Exception as error:   # report the file as failed, with the reason
            raise InspectError(f"{Path(path).name} could not be read ({error}).")
        return {"file": str(path), "pages": len(doc), "results": results}
    finally:
        doc.close()


def _fonts(result):
    """{font name: FontMapping} for the music fonts of the file, first page seen."""
    fonts = {}
    for page in result["results"]:
        for name, mapping in page.fonts.items():
            if mapping.table is not None:
                fonts.setdefault(name, mapping)
    return fonts


def file_counts(result):
    symbols = Counter()
    unmapped = Counter()
    outlined_pages = 0
    for page in result["results"]:
        symbols.update(s.name for s in page.symbols)
        unmapped.update(page.unmapped)
        if any(s.source == "outline" for s in page.symbols):
            outlined_pages += 1
    return symbols, unmapped, outlined_pages


def report_lines(result):
    symbols, unmapped, outlined = file_counts(result)
    total, missing = sum(symbols.values()), sum(unmapped.values())
    name = Path(result["file"]).name
    pages = len(result["results"])
    out = [f"File: {name}"]
    share = f", {100 * missing / (total + missing):.1f} percent" if total + missing else ""
    out.append(f"Summary: {pages} page{'s' if pages != 1 else ''}, {total} symbols named, "
               f"{missing} glyphs or shapes unmapped{share}.")
    fonts = _fonts(result)
    if fonts:
        out.append("Music fonts:")
        for font, m in fonts.items():
            line = f"- {font}: {HOW_WORDS[m.how]}, named with {TABLE_WORDS[m.table]}"
            if m.how == "shapes" and m.score is not None:
                line += f"; {100 * m.score:.0f} percent of its glyphs fit the table"
            if m.program:
                line += f"; probably from {m.program}"
            out.append(line + ".")
    unknown = {m.font for page in result["results"] for m in page.fonts.values()
               if m.how == "shapes" and m.table is None} - set(fonts)
    for font in sorted(unknown):
        out.append(f"- {font}: on staves but not identified; its glyphs are not named.")
    if outlined:
        out.append(f"Outlined symbols: named by shape on {outlined} page{'s' if outlined != 1 else ''}.")
    if symbols:
        out.append("Most common symbols: " + ", ".join(f"{n} {name}" for name, n in symbols.most_common(10)) + ".")
    if unmapped:
        out.append("Unmapped:")
        for (font, what), n in unmapped.most_common():
            out.append(f"- {font}: {what}, {n} time{'s' if n != 1 else ''}.")
    return out


def file_json(result):
    symbols, unmapped, outlined = file_counts(result)
    return {
        "file": result["file"],
        "pages": result["pages"],
        "error": None,
        "symbols": dict(symbols),
        "unmapped": [{"font": f, "glyph": w, "count": n} for (f, w), n in unmapped.most_common()],
        "fonts": [{"font": name, "table": m.table, "how": m.how, "score": m.score, "program": m.program}
                  for name, m in _fonts(result).items()],
        "outlined_pages": outlined,
    }


def run(files, json_path=None, pages=None, out=print):
    """Report each file. Return the exit status (0, or 1 if a file failed)."""
    json_list, done, failed, unmapped_files = [], 0, 0, 0
    for path in files:
        try:
            result = read_file(path, pages)
        except InspectError as error:
            failed += 1
            out(f"File: {Path(path).name}")
            out(f"Failed: {error}")
            out("")
            json_list.append({"file": str(path), "error": str(error)})
            continue
        done += 1
        for line in report_lines(result):
            out(line)
        out("")
        entry = file_json(result)
        if entry["unmapped"]:
            unmapped_files += 1
        json_list.append(entry)
    if json_path:
        Path(json_path).write_text(json.dumps(json_list, indent=2), encoding="utf-8")
        out(f"JSON written to {json_path}.")
    out(f"Summary: {done} file{'s' if done != 1 else ''} read, {failed} failed, "
        f"{unmapped_files} with unmapped glyphs.")
    return 1 if failed else 0
