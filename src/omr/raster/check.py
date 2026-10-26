"""Check the lines found in page images against the vector reading (Stage 2.2).

Each pair of a raster set is read twice with the symbols of its vector PDF:
once with the PDF's own drawings, once with the lines found in its image
(omr.raster.page.RasterPage). The staves, barlines and stems the reader
settles on are compared, and both readings are scored against the ground
truth, so the notes lost to the image's lines show alone.

The rules are in docs/notes/raster-lines-spec.md, "The check".
"""

import contextlib
import tempfile
from pathlib import Path

STAFF_TOLERANCE = 0.3     # staff spaces, for the top line and each end
BARLINE_TOLERANCE = 0.5   # staff spaces along the staff
STEM_TOLERANCE = 0.3      # staff spaces across the stem
STEM_END_TOLERANCE = 0.5  # staff spaces at each end


@contextlib.contextmanager
def recording_stems(found):
    """Record every stem notation.find_stems returns while the block runs."""
    from omr.pdf import notation

    original = notation.find_stems

    def wrapper(*args, **kwargs):
        stems = original(*args, **kwargs)
        found.extend(stems)
        return stems

    notation.find_stems = wrapper
    try:
        yield
    finally:
        notation.find_stems = original


def read(vector_pdf, raster_pdf=None):
    """(Score, layouts, stems, line counts, shapes) read from the vector PDF,
    with the lines of the raster PDF's images if one is given. `shapes` are
    (page, staff space, notation.Shapes) of each page with staves."""
    import pymupdf

    from omr.pdf import layout as lay
    from omr.pdf import notation, structure, symbols
    from omr.raster import page as rp

    doc = pymupdf.open(str(vector_pdf))
    rdoc = pymupdf.open(str(raster_pdf)) if raster_pdf else None
    try:
        pages = symbols.read_document(doc)
        use = doc
        counts = None
        if rdoc is not None:
            use, counts = [], {"level": 0, "vertical": 0, "beams": 0}
            for k, ps in enumerate(pages):
                found, place = rp.read_lines(rdoc[k], rp.symbol_boxes(ps))
                drawn = rp.drawings(found, place) if found is not None else []
                use.append(rp.RasterPage(doc[k], drawn))
                if found is not None:
                    for key in counts:
                        counts[key] += len(getattr(found, key))
        stems = []
        layouts = lay.read_document(use, pages)
        shapes = []
        for pl in layouts:
            if pl.staves:
                space = pl.staff_space()
                found = notation.page_shapes(use[pl.page - 1], space)
                # symbols drawn as outlines are curved shapes too; only ties and slurs count
                boxes = rp.symbol_boxes(pages[pl.page - 1])[0]
                found.curves = [c for c in found.curves if not _inside_any(c.box, boxes)]
                shapes.append((pl.page, space, found))
        assigned = structure.assign_parts(layouts)
        score = structure.read_structure(layouts, assigned)
        with recording_stems(stems):
            notation.read_notes(score, assigned[0], use, layouts)
        return score, layouts, stems, counts, shapes
    finally:
        doc.close()
        if rdoc is not None:
            rdoc.close()


def _inside_any(box, boxes):
    """The box lies mostly (80 percent of its area) inside one of the boxes."""
    x0, y0, x1, y1 = box
    area = max((x1 - x0) * (y1 - y0), 1e-6)
    for a0, b0, a1, b1 in boxes:
        w, h = min(x1, a1) - max(x0, a0), min(y1, b1) - max(y0, b0)
        if w > 0 and h > 0 and w * h >= 0.8 * area:
            return True
    return False


def match_staves(truth, found):
    """{index in truth: index in found} for staves on the same page whose top
    line and ends agree within STAFF_TOLERANCE staff spaces."""
    out, used = {}, set()
    for i, t in enumerate(truth):
        tol = STAFF_TOLERANCE * t.space
        for j, f in enumerate(found):
            if j in used or f.page != t.page:
                continue
            if abs(f.top - t.top) <= tol and abs(f.x0 - t.x0) <= 2 * tol and abs(f.x1 - t.x1) <= 2 * tol:
                out[i] = j
                used.add(j)
                break
    return out


def barlines_of(layouts):
    """(page, staff top, x) of every barline line, for each staff of each system."""
    out = []
    for pl in layouts:
        for system in pl.systems:
            for group in system.barlines:
                for x, _ in group.lines:
                    out.append((pl.page, system.staves[0].top, x, system.staves[0].space))
    return out


def match_points(truth, found, tolerance):
    """Matches between (page, key, x, space) items: same page and key within a
    staff space, x within tolerance staff spaces. Returns (matched, errors in
    staff spaces)."""
    matched, errors, used = 0, [], set()
    by_page = {}
    for j, f in enumerate(found):
        by_page.setdefault(f[0], []).append((j, f))
    for page, key, x, space in truth:
        best = None
        for j, (fp, fkey, fx, _) in by_page.get(page, []):
            if j in used or abs(fkey - key) > space:
                continue
            d = abs(fx - x)
            if d <= tolerance * space and (best is None or d < best[1]):
                best = (j, d)
        if best:
            used.add(best[0])
            matched += 1
            errors.append(best[1] / space)
    return matched, errors


def stems_of(stems):
    return [(s.heads[0].staff.page, s.top, s.bottom, s.x, s.heads[0].staff.space) for s in stems if s.heads]


def match_stems(truth, found):
    """(matched, errors across in staff spaces, end errors in staff spaces)."""
    matched, across, ends, used = 0, [], [], set()
    by_page = {}
    for j, f in enumerate(found):
        by_page.setdefault(f[0], []).append((j, f))
    for page, top, bottom, x, space in truth:
        best = None
        for j, (_, ftop, fbottom, fx, _) in by_page.get(page, []):
            if j in used or abs(fx - x) > STEM_TOLERANCE * space:
                continue
            if abs(ftop - top) > STEM_END_TOLERANCE * space or abs(fbottom - bottom) > STEM_END_TOLERANCE * space:
                continue
            d = abs(fx - x)
            if best is None or d < best[1]:
                best = (j, d, max(abs(ftop - top), abs(fbottom - bottom)))
        if best:
            used.add(best[0])
            matched += 1
            across.append(best[1] / space)
            ends.append(best[2] / space)
    return matched, across, ends


def match_shapes(truth, found, ends):
    """(matched, found) for beams or curves: `ends` gives (x0, y0, x1, y1) of
    one; they match on the same page with each end within half a staff space."""
    matched = total = 0
    found_by_page = {page: items for page, _, items in found}
    for page, space, items in truth:
        pool = [ends(f) for f in found_by_page.get(page, [])]
        used = set()
        for t in items:
            a = ends(t)
            for j, b in enumerate(pool):
                if j not in used and all(abs(u - v) <= 0.5 * space for u, v in zip(a, b)):
                    used.add(j)
                    matched += 1
                    break
    total = sum(len(items) for _, _, items in found)
    return matched, total


def shape_figures(truth, found, kind, ends):
    pick = lambda shapes: [(page, space, getattr(s, kind)) for page, space, s in shapes]
    matched, total = match_shapes(pick(truth), pick(found), ends)
    return {"truth": sum(len(getattr(s, kind)) for _, _, s in truth), "found": total,
            "matched": matched, "error": 0.0}


def beam_ends(b):
    return (b.x0, b.y0, b.x1, b.y1)


def curve_ends(c):
    return (*c.left, *c.right)


def note_figures(score, truth_path, title):
    from omr import musicxml
    from omr.evaluate import metrics

    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "score.musicxml"
        musicxml.write(score, out, title=title)
        figures = metrics.compare(truth_path, out)
    notes = figures["notes"]
    return {"truth": notes["truth"], "exact": notes["exact"]}


def check_pair(vector_pdf, raster_pdf, truth_path):
    """The figures for one pair (see the module docstring)."""
    v_score, v_layouts, v_stems, _, v_shapes = read(vector_pdf)
    r_score, r_layouts, r_stems, counts, r_shapes = read(vector_pdf, raster_pdf)
    v_staves = [s for pl in v_layouts for s in pl.staves]
    r_staves = [s for pl in r_layouts for s in pl.staves]
    staff_match = match_staves(v_staves, r_staves)
    staff_errors = [abs(r_staves[j].top - v_staves[i].top) / v_staves[i].space for i, j in staff_match.items()]
    v_bars, r_bars = barlines_of(v_layouts), barlines_of(r_layouts)
    bar_matched, bar_errors = match_points(v_bars, r_bars, BARLINE_TOLERANCE)
    v_st, r_st = stems_of(v_stems), stems_of(r_stems)
    stem_matched, stem_across, stem_ends = match_stems(v_st, r_st)
    title = Path(vector_pdf).stem
    return {
        "staves": {"truth": len(v_staves), "found": len(r_staves), "matched": len(staff_match),
                   "error": max(staff_errors, default=0.0)},
        "barlines": {"truth": len(v_bars), "found": len(r_bars), "matched": bar_matched,
                     "error": max(bar_errors, default=0.0)},
        "stems": {"truth": len(v_st), "found": len(r_st), "matched": stem_matched,
                  "error": max(stem_across, default=0.0), "end error": max(stem_ends, default=0.0)},
        "beams": shape_figures(v_shapes, r_shapes, "beams", beam_ends),
        "curves": shape_figures(v_shapes, r_shapes, "curves", curve_ends),
        "notes vector": note_figures(v_score, truth_path, title),
        "notes raster": note_figures(r_score, truth_path, title),
        "lines": counts,
    }
