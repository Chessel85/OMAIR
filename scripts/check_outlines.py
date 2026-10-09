"""Check the outlined-symbol matcher (Stage 1.1, Type B) against Verovio's own glyph list.

The corpus's Verovio PDFs are outlined: Verovio writes SVG, and the SVG is
converted to PDF, so every symbol is a filled path. Rendering the same
reference MusicXML again with the same Verovio options gives the SVG, which
names every glyph and gives its origin. So each outlined shape the matcher
names can be checked exactly.

A true glyph is found if the matcher put a symbol of the same name within
half a staff space of its origin. Names that differ only in use, not in shape,
count as the same: every dot (rhythm, staccato, repeat) is a dot, and a clef
drawn for a change is that clef. A symbol near a true glyph of another name
is a confusion. The report gives recall and precision for each symbol name.

With --type-a, Type A PDFs (for example Sibelius and Finale files in legacy
fonts) are turned into outlined pages instead: PyMuPDF writes each page as
SVG with its text as paths, and the SVG is read back as a PDF. The truth is
the list of symbols the font tables give for the original page.

Usage:
  python scripts/check_outlines.py [--set-root FOLDER] [--limit N] [--workers N] [--fonts LIST]
  python scripts/check_outlines.py --type-a PDF... [--pages N]
  (default set: the regression set in the repository)
"""

import argparse
import collections
import re
import sys
from pathlib import Path

from omr import parallel, paths
from omr.log import ProgressLog

SCALE = 0.04          # PDF points per Verovio SVG unit (scale 40, page 21000 units = 840 points)
MARGIN = 500          # Verovio's page margin, in SVG units
NEAR = 0.5            # staff spaces


DOTS = {"augmentationDot", "repeatDot", "articStaccatoAbove", "articStaccatoBelow"}
SAME = {"articAccentBelow": "articAccentAbove", "articTenutoBelow": "articTenutoAbove",
        "articStaccatissimoWedgeAbove": "articStaccatissimoAbove",
        "articStaccatissimoWedgeBelow": "articStaccatissimoBelow"}


def same_shape(name):
    """The name a glyph is checked under: one name for every dot, one for an
    accent or tenuto above or below (the same shape), a wedge as a
    staccatissimo, and a change clef as its clef."""
    if name in DOTS:
        return "augmentationDot"
    return SAME.get(name, name).removesuffix("Change")


def truth_glyphs(reference):
    """[(page from 1, SMuFL name, x, y)] for every glyph Verovio draws."""
    import verovio

    from omr.pdf import smufl

    tk = verovio.toolkit()
    tk.setOptions({"svgViewBox": True, "svgRemoveXlink": True, "scale": 40})
    if not tk.loadFile(str(reference)):
        raise ValueError(f"Verovio could not load {reference}")
    out = []
    pattern = re.compile(r'<use href="#([0-9A-F]{4})-[^"]*" transform="translate\(([-\d.]+), ([-\d.]+)\)')
    # Verovio draws rhythm dots as ellipses, not glyphs.
    ellipse = re.compile(r'<ellipse cx="([-\d.]+)" cy="([-\d.]+)" rx="([-\d.]+)"')
    for page in range(1, tk.getPageCount() + 1):
        svg = tk.renderToSVG(page)
        for code, x, y in pattern.findall(svg):
            name = same_shape(smufl.name_of(int(code, 16), "Bravura") or f"U+{code}")
            out.append((page, name, (float(x) + MARGIN) * SCALE, (float(y) + MARGIN) * SCALE))
        for cx, cy, rx in ellipse.findall(svg):
            out.append((page, "augmentationDot", (float(cx) - float(rx) + MARGIN) * SCALE, (float(cy) + MARGIN) * SCALE))
    return out


def compare(truth, results, ignore=None, by_centre=False):
    """Counts {name: [true, found, matched]}, confusions and unmatched shapes.
    `truth` is [(page, name, x, y)]; `ignore` is {page: [boxes]} where named
    shapes are not counted (text turned into outlines). With `by_centre`,
    truth positions are ink centres and are compared with the centres of the
    outlined shapes, which are exact on both sides; otherwise with origins."""
    counts = collections.defaultdict(lambda: [0, 0, 0])
    confusions = collections.Counter()
    unmapped = 0
    for result in results:
        unmapped += sum(n for (font, _), n in result.unmapped.items() if font == "outlines")
        space = result.staff_space or 7.2
        boxes = (ignore or {}).get(result.page, [])
        found = [s for s in result.symbols if s.source == "outline"
                 and not any(b[0] <= (s.box[0] + s.box[2]) / 2 <= b[2] and b[1] <= (s.box[1] + s.box[3]) / 2 <= b[3]
                             for b in boxes)]
        for s in found:
            counts[s.name][1] += 1
        if by_centre:
            found = [symbols_at_centre(s) for s in found]
        used = set()
        for page, name, x, y in truth:
            if page != result.page:
                continue
            counts[name][0] += 1
            near = [(abs(s.x - x) + abs(s.y - y), i) for i, s in enumerate(found)
                    if i not in used and abs(s.x - x) <= NEAR * space and abs(s.y - y) <= NEAR * space]
            same = [(d, i) for d, i in near if found[i].name == name]
            if same:
                used.add(min(same)[1])
                counts[name][2] += 1
            elif near:
                i = min(near)[1]
                used.add(i)
                confusions[(name, found[i].name)] += 1
    return {k: list(v) for k, v in counts.items()}, dict(confusions), unmapped


def symbols_at_centre(symbol):
    import dataclasses
    return dataclasses.replace(symbol, x=(symbol.box[0] + symbol.box[2]) / 2, y=(symbol.box[1] + symbol.box[3]) / 2)


def _use_fonts(fonts):
    from omr.pdf import shapes

    if fonts:
        shapes.REFERENCE_FONTS[:] = fonts


def check_pair(pdf, reference, fonts=None):
    """Check one Verovio PDF against Verovio's glyph list."""
    import pymupdf

    from omr.pdf import symbols

    _use_fonts(fonts)
    truth = truth_glyphs(reference)
    return compare(truth, symbols.read_document(pymupdf.open(pdf)))


def check_type_a(pdf, pages, fonts=None):
    """Turn the music-font pages of a Type A PDF into outlines and check the
    outlines against the symbols the font tables give. Only symbols that the
    matcher looks for are counted as true; text turned into outlines is
    ignored."""
    import pymupdf

    from omr.pdf import symbols

    _use_fonts(fonts)
    doc = pymupdf.open(pdf)
    programs, identifier = symbols.FontPrograms(doc), None
    truth, results, ignore = [], [], {}
    wanted = {same_shape(n) for n in symbols.OUTLINE_CANDIDATES}
    done = 0
    for page in doc:
        if done >= pages:
            break
        identifier = identifier or symbols.FontIdentifier(programs)
        original = symbols.read_page(page, page.number + 1, programs, identifier)
        named = [s for s in original.symbols if s.source != "outline"]
        if len(named) < 20:
            continue
        done += 1
        svg = page.get_svg_image(text_as_path=True)
        outlined = pymupdf.open("pdf", pymupdf.open(stream=svg.encode(), filetype="svg").convert_to_pdf())
        result = symbols.read_page(outlined[0], page.number + 1)
        results.append(result)
        truth += [(page.number + 1, same_shape(s.name), (s.box[0] + s.box[2]) / 2, (s.box[1] + s.box[3]) / 2)
                  for s in named if same_shape(s.name) in wanted]
        ignore[page.number + 1] = [run.box for run in original.text]
    return compare(truth, results, ignore, by_centre=True)


def pairs(set_root, limit):
    index = Path(set_root) / "index.txt"
    out = []
    for line in index.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        fields = [f.strip() for f in line.split("|")]
        if fields[0] == "pair" and fields[2] == "verovio":
            out.append((fields[1], Path(set_root) / fields[4], Path(set_root) / fields[5]))
    return out[:limit] if limit else out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set-root", default=str(paths.REPO_ROOT / "regression"))
    parser.add_argument("--type-a", nargs="+", metavar="PDF",
                        help="Instead of Verovio pairs, outline these Type A PDFs and check against their font glyphs.")
    parser.add_argument("--pages", type=int, default=5, help="Pages to outline from each --type-a file (default 5).")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--fonts", help="Reference fonts to match against, comma separated "
                        "(default all: Bravura, Leland, Petaluma, Gootville, Leipzig). Verovio draws in "
                        "Leipzig, so leaving it out tests shapes from a font the matcher has not seen.")
    args = parser.parse_args(argv)
    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = ProgressLog("check-outlines", path=str(logs / "check-outlines.log"))
    if args.type_a:
        todo = [(Path(p).name, Path(p), None) for p in args.type_a][:args.limit]
    else:
        todo = pairs(args.set_root, args.limit)
    if not todo:
        log.error(f"No Verovio pairs in {args.set_root}. Check the folder has an index.txt.")
        return log.finish("0 files checked")
    totals = collections.defaultdict(lambda: [0, 0, 0])
    confusions = collections.Counter()
    unmapped = 0
    with parallel.pool(args.workers) as executor:
        fonts = args.fonts.split(",") if args.fonts else None
        if args.type_a:
            running = {executor.submit(check_type_a, pdf, args.pages, fonts): score for score, pdf, _ in todo}
        else:
            running = {executor.submit(check_pair, pdf, ref, fonts): score for score, pdf, ref in todo}
        while running:
            for future, score in parallel.finished(running, block=True):
                try:
                    counts, confused, missing = future.result()
                except Exception as error:   # report and go on with the rest
                    log.error(f"{score}: {error}")
                    continue
                for name, (t, f, m) in counts.items():
                    totals[name][0] += t
                    totals[name][1] += f
                    totals[name][2] += m
                confusions.update({tuple(k): v for k, v in confused.items()})
                unmapped += missing
                true = sum(c[0] for c in counts.values())
                matched = sum(c[2] for c in counts.values())
                log.info(f"{score}: {matched} of {true} glyphs found by shape")
    true = sum(c[0] for c in totals.values())
    found = sum(c[1] for c in totals.values())
    matched = sum(c[2] for c in totals.values())
    print()
    print("Outlined symbols by name (true glyphs, found, right):")
    for name, (t, f, m) in sorted(totals.items(), key=lambda kv: -kv[1][0]):
        recall = f"{100 * m / t:.1f} percent found" if t else "none true"
        precision = f"{100 * m / f:.1f} percent right" if f else "none named"
        print(f"- {name}: {t} true, {f} named; {recall}, {precision}")
    if confusions:
        print()
        print("Most common confusions (true name, named as):")
        for (a, b), n in confusions.most_common(15):
            print(f"- {a} named as {b}: {n}")
    print()
    print(f"Outlined shapes not matched to any symbol: {unmapped}")
    return log.finish(f"{len(todo)} files checked, {matched} of {true} glyphs found ({100 * matched / max(true, 1):.1f} percent), "
                      f"{matched} of {found} named symbols right ({100 * matched / max(found, 1):.1f} percent)")


if __name__ == "__main__":
    sys.exit(main())
