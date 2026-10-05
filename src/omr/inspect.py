"""`omr inspect`: report the page types, fonts and shapes in PDF and image files.

Plain text for people, JSON for scripts. See docs/notes/inspector-spec.md.
"""

import json
from collections import Counter
from pathlib import Path

from omr.pdf import classify, evidence

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
CLASS_LABELS = {
    "smufl": "SMuFL music font",
    "smufl_text": "SMuFL text font",
    "legacy": "legacy music font, mapping table needed",
    "unknown_music": "unknown font, probably music",
    "text": "text font",
}


class InspectError(Exception):
    """A file could not be read. The message says why."""


def parse_pages(spec, count):
    """Turn '1-3,7' into a sorted list of page numbers (from 1) within count."""
    if not spec:
        return list(range(1, count + 1))
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        try:
            if "-" in part:
                lo, hi = part.split("-", 1)
                pages.update(range(int(lo), int(hi) + 1))
            else:
                pages.add(int(part))
        except ValueError:
            raise InspectError(f"'{spec}' is not a page list. Use a form like 1-3,7.")
    return sorted(p for p in pages if 1 <= p <= count)


def open_document(path):
    import pymupdf

    path = Path(path)
    if not path.is_file():
        raise InspectError(f"{path} does not exist or is not a file.")
    try:
        if path.suffix.lower() in IMAGE_SUFFIXES:
            image = pymupdf.open(str(path))
            doc = pymupdf.open("pdf", image.convert_to_pdf())
            image.close()
        else:
            doc = pymupdf.open(str(path))
    except Exception as error:
        raise InspectError(f"{path.name} could not be opened ({error}). It may be damaged or not a PDF.")
    if doc.needs_pass or doc.is_encrypted:
        doc.close()
        raise InspectError(f"{path.name} is encrypted. Remove the password first.")
    return doc


def inspect_file(path, pages=None):
    """Return a result dict for one file, with the decisions attached.
    Raises InspectError if the file cannot be read."""
    doc = open_document(path)
    try:
        meta = doc.metadata or {}
        numbers = parse_pages(pages, len(doc))
        results = []
        for number in numbers:
            page = doc[number - 1]
            try:
                ev = evidence.gather(page, number)
                decision = classify.classify(ev, lambda: evidence.raster_measures(page, ev.images))
            except Exception as error:
                raise InspectError(f"{Path(path).name} page {number} could not be read ({error}).")
            results.append((ev, decision))
        return {
            "file": str(path),
            "pages": len(doc),
            "producer": meta.get("producer") or "",
            "creator": meta.get("creator") or "",
            "error": None,
            "results": results,
        }
    finally:
        doc.close()


def file_json(result):
    """The JSON form of one file's result (fixed field names, see the spec)."""
    types = Counter()
    fonts = {}
    page_results = []
    for ev, decision in result["results"]:
        types[decision.type] += 1
        for font in ev.fonts:
            if font.cls != "text":
                entry = fonts.setdefault(font.name, {"name": font.name, "class": font.cls, "glyphs": 0})
                entry["glyphs"] += font.glyphs
        page = ev.to_dict()
        page.update(
            type=decision.type, confidence=decision.confidence,
            reason=decision.reason, notes=decision.notes,
        )
        page_results.append(page)
    return {
        "file": result["file"],
        "pages": result["pages"],
        "producer": result["producer"],
        "creator": result["creator"],
        "error": None,
        "summary": {"types": dict(types), "music_fonts": list(fonts.values())},
        "page_results": page_results,
    }


def error_json(path, message):
    return {"file": str(path), "pages": 0, "producer": "", "creator": "", "error": message,
            "summary": {"types": {}, "music_fonts": []}, "page_results": []}


# ------------------------------------------------------------------ text

def _made_by(result):
    parts = [p for p in (result["creator"], result["producer"]) if p]
    return " / ".join(dict.fromkeys(parts))


def _font_line(font):
    line = f"- {font.name}: {CLASS_LABELS[font.cls]}, {font.glyphs} glyphs"
    if font.unmapped_glyphs and font.cls != "text":
        line += f", {font.unmapped_glyphs} without Unicode values"
    return line + "."


def summary_lines(result):
    """The one-paragraph summary at the top of each file's report."""
    types = Counter(d.type for _, d in result["results"])
    counted = len(result["results"])
    pages = f"{counted} page" + ("" if counted == 1 else "s")
    if counted != result["pages"]:
        pages += f" inspected of {result['pages']}"
    kinds = ", ".join(
        f"Type {t} on {n} page" + ("" if n == 1 else "s") if t != "N" else f"no music on {n} page" + ("" if n == 1 else "s")
        for t, n in sorted(types.items())
    )
    music = {}
    for ev, _ in result["results"]:
        for font in ev.music_fonts:
            music.setdefault(font.name, font)
    font_text = ", ".join(
        f"{name} ({'SMuFL' if f.cls == 'smufl' else 'legacy' if f.cls == 'legacy' else 'unknown, probably music'})"
        for name, f in music.items()
    )
    line = f"Summary: {pages}. {kinds}."
    if font_text:
        line += f" Music font: {font_text}."
    made = _made_by(result)
    if made:
        line += f" Made by {made}."
    return [line]


def page_lines(ev, decision):
    out = [f"Page {ev.page}"]
    out.append(f"Type {decision.type}, {decision.confidence} confidence: {decision.reason}")
    for note in decision.notes:
        out.append(f"Note: {note}.")
    s = ev.staves
    if s.five_line:
        mm = s.staff_space_pt * 25.4 / 72
        out.append(
            f"Staves: {s.five_line} five-line staves. Staff space {s.staff_space_pt:.1f} points, {mm:.2f} millimetres."
        )
    else:
        out.append("Staves: none found.")
    if s.six_line:
        out.append(f"Also {s.six_line} six-line staves (tablature).")
    if s.one_line:
        out.append(f"Also {s.one_line} single lines carrying glyphs (percussion).")
    if ev.fonts:
        out.append("Fonts:")
        for font in ev.fonts:
            out.append(_font_line(font))
    else:
        out.append("Fonts: none.")
    if ev.hidden_text_glyphs:
        out.append(f"Hidden text: {ev.hidden_text_glyphs} glyphs, probably an OCR layer.")
    li, fi = ev.lines, ev.filled
    stroked = li["horizontal"] + li["vertical"] + li["other"]
    out.append(
        f"Vector lines: {stroked} stroked, of which {li['horizontal']} horizontal and {li['vertical']} vertical."
    )
    filled = fi["rectangles"] + fi["polygons"] + fi["curved"]
    out.append(
        f"Filled shapes: {filled}, of which {fi['rectangles']} rectangles, {fi['polygons']} polygons and {fi['curved']} curved."
    )
    o = ev.outlined
    if o["count"]:
        top = ", ".join(str(n) for n in o["top_repeats"])
        out.append(
            f"Outlined shapes: {o['count']} small curved {'shape' if o['count'] == 1 else 'shapes'}, {o['distinct']} distinct. Most common repeat counts: {top}."
        )
    else:
        out.append("Outlined shapes: none.")
    if ev.images:
        out.append(f"Images: {len(ev.images)}, covering {ev.image_coverage * 100:.0f} percent of the page.")
        for image in ev.images:
            out.append(
                f"- {image['width_px']} by {image['height_px']} pixels, about {image['dpi']} dpi, "
                f"{image['bits']} bits, {image['colour_space']}, filter {image['filter'] or 'none'}."
            )
    else:
        out.append("Images: none.")
    if ev.raster:
        r = ev.raster
        out.append(
            f"Raster measures: background varies by {r['background_range']:.0f} out of 255, "
            f"dark border {'yes' if r['dark_border'] else 'no'}, tilt {r['tilt_degrees']:+.1f} degrees, "
            f"bilevel {'yes' if r['bilevel'] else 'no'}."
        )
    return out


def _signature(ev, decision):
    return (decision.type, tuple((f.name, f.cls) for f in ev.fonts))


def report_lines(result, brief=False):
    out = [f"File: {Path(result['file']).name}"]
    out.extend(summary_lines(result))
    if brief:
        return out
    previous, first_page, run_start = None, None, None
    pending = []  # pages that match the first page of their run
    for ev, decision in result["results"]:
        sig = _signature(ev, decision)
        if sig == previous:
            pending.append(ev.page)
            continue
        if pending:
            out.append("")
            out.append(_same_as(pending, first_page))
        pending = []
        out.append("")
        out.extend(page_lines(ev, decision))
        previous, first_page = sig, ev.page
    if pending:
        out.append("")
        out.append(_same_as(pending, first_page))
    return out


def _same_as(pages, first):
    if len(pages) == 1:
        return f"Page {pages[0]}: same type and fonts as page {first}."
    return f"Pages {pages[0]} to {pages[-1]}: same type and fonts as page {first}."


def warnings_for(result):
    out = []
    for ev, decision in result["results"]:
        for w in decision.warnings:
            out.append(f"{Path(result['file']).name}, page {ev.page}: {w}.")
    return out


def run(files, json_path=None, pages=None, brief=False, out=print):
    """Inspect each file. Return the exit status (0 or 1)."""
    json_list, inspected, failed, warning_count = [], 0, 0, 0
    for path in files:
        try:
            result = inspect_file(path, pages)
        except InspectError as error:
            failed += 1
            out(f"File: {Path(path).name}")
            out(f"Failed: {error}")
            out("")
            json_list.append(error_json(path, str(error)))
            continue
        inspected += 1
        for line in report_lines(result, brief):
            out(line)
        found = warnings_for(result)
        warning_count += len(found)
        for line in found:
            out(f"Warning: {line}")
        out("")
        json_list.append(file_json(result))
    if json_path:
        Path(json_path).write_text(json.dumps(json_list, indent=2), encoding="utf-8")
        out(f"JSON written to {json_path}.")
    out(f"Summary: {inspected} file{'s' if inspected != 1 else ''} inspected, {failed} failed, {warning_count} warnings.")
    return 1 if failed else 0
