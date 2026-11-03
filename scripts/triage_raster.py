"""Stage 2.9 triage of the raster penalty: which part of the image reading
makes each note error that the PDF reading does not make.

Each pair of a raster set is read six ways, with everything else the vector
reader's own:

- vector: the pair's vector PDF (symbols, lines and text from the PDF);
- symbols: the symbols found in the image, with the PDF's lines and text;
- lines: the lines found in the image (and the staves they give), with the
  PDF's symbols and text;
- text: the text read from the image, with the PDF's symbols and lines;
- engine 1: the whole image reading with Engine 1 alone;
- both: the whole image reading with the engines combined (Stage 2.7), as
  `omr convert` reads an image.

Each reading is scored against the ground truth and its note errors are
counted by staff bar of the truth (part, staff, bar). A staff bar where
"both" has more errors than "vector" carries part of the raster penalty. Its
cause is the single swap that brings errors there (symbols, lines, text), two
of them, "together" when only the whole Engine 1 reading does, or "engine 2"
when Engine 1 alone has no more errors there than the PDF.

For a staff bar the symbols spoil, the detections on that staff and bar of
the page are matched against the labels the detector was trained on (made
from the PDF, as check_detector.py makes them): labels missed, labels found
as another class, and detections with no label, by class.

Writes one JSON line per pair to results.jsonl and the ranking to
summary.txt in <corpus>/evaluations/<name>, with a log beside them.
Saved detections and Engine 2 readings are used (OMR_DETECTIONS_DIR), so set
OMR_DETECTOR to the model they were saved with.

usage: python scripts/triage_raster.py SET VERSION [--name NAME] [--every N]
           [--limit N] [--workers N] [--summary-only]

e.g.   python scripts/triage_raster.py development g200 --every 6 --name s36-triage
"""

import argparse
import collections
import copy
import json
import sys
import tempfile
from pathlib import Path

from omr import parallel, paths, pause
from omr.evaluate import harness
from omr.log import ProgressLog

READINGS = ("vector", "symbols", "lines", "text", "engine 1", "both")
SWAPS = ("symbols", "lines", "text")
MOVED = 0.3   # staff spaces: a matched notehead or clef this far off in height counts as moved


# ------------------------------------------------------------ reading

def read_with(pages, use, engines=False):
    """(Score, ordered systems) read from PageSymbols and page objects, as
    omr.pdf.read.read_pdf does after its symbols."""
    from omr.evaluate import events
    from omr.pdf import layout as lay, notation, structure

    pages = copy.deepcopy(pages)
    layouts = lay.read_document(use, pages)
    assigned = structure.assign_parts(layouts)
    score = structure.read_structure(layouts, assigned)
    if any(s.source == "detector" for p in pages for s in p.symbols):
        from omr.raster import metre   # as read_pdf reads page images
        metre.read_notes(score, assigned[0], use, layouts)
    else:
        notation.read_notes(score, assigned[0], use, layouts)
    if engines:
        from omr.raster import sequence_reading
        sequence_reading.combine_notes(score, assigned, use)
    events.navigation_from_words(score)
    return score, assigned[0]


def mixed(vector, raster, symbols=False, text=False, lines=False):
    """A PageSymbols taking the image's symbols, text or lines (with the
    staves its evidence gives) and the rest from the PDF's."""
    from omr.pdf.symbols import PageSymbols

    return PageSymbols(vector.page, raster.evidence if lines else vector.evidence,
                       raster.symbols if symbols else vector.symbols,
                       raster.text if text else vector.text,
                       text_regions=raster.text_regions if symbols else [],
                       masked=raster.masked if symbols else [])


# ------------------------------------------------------------ scoring

def score_units(score, truth, title):
    """Note errors by truth staff bar: ({(part, staff, bar): errors},
    {(part, staff, bar): Counter of error kinds}, match result, whether the
    output's first bar was joined to its second)."""
    from omr import musicxml
    from omr.evaluate import events, match as matching

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "score.musicxml"
        musicxml.write(score, path, title=title)
        output = events.read(path)
    output = events.with_ending_ends_alike(output)
    joined = events.without_hidden_first_bar(output)
    shifted = joined is not output
    output = events.without_trailing_empty_bars(joined)
    result = matching.match(truth, output)
    counts, kinds = collections.Counter(), collections.defaultdict(collections.Counter)

    def add(unit, kind):
        counts[unit] += 1
        kinds[unit][kind] += 1

    for note in result.missing:
        add((note.part, note.staff, note.bar), "missing")
    for pair in result.errors:
        add((pair.truth.part, pair.truth.staff, pair.truth.bar), "+".join(pair.differs))
    for note in result.extra:
        segment = result.output_segment.get(note.bar)
        bars = result.segments[segment].truth if segment is not None else []
        part, staff = result.staff_map.get((note.part, note.staff), (None, None))
        add((part, staff, bars[0] if bars else None), "extra")
    for c in result.clef_corrections:
        add((*c.truth_staff, c.first_bar), "clef")
    return counts, kinds, result, shifted


def truth_of(path):
    from omr.evaluate import events

    truth = events.read(path)
    truth = events.with_ending_ends_alike(truth)
    truth = events.without_hidden_first_bar(truth)
    return events.without_trailing_empty_bars(truth)


# ------------------------------------------------------------ places on the page

def layout_bars(ordered):
    """[(page layout, system, SystemParts, bar index in the system)] in the
    page layout's bar order."""
    return [(pl, system, mapping, j) for pl, system, mapping in ordered for j in range(len(system.bars))]


def staff_regions(unit, result, shifted, score, ordered):
    """[(page, (x0, y0, x1, y1) in points, staff space)] of the truth staff
    bar in the vector reading's page layout, or [] if it cannot be placed."""
    from omr.pdf import layout as lay

    part, staff, bar = unit
    index = result.truth_segment.get(bar)
    if index is None or part is None:
        return []
    out_staff = next((o for o, t in result.staff_map.items() if t == (part, staff)), None)
    if out_staff is None:
        return []
    score_bars = set()
    for o in result.segments[index].output:
        score_bars.update({0, 1} if shifted and o == 0 else {o + 1} if shifted else {o})
    entries = layout_bars(ordered)
    joined = sorted(score.joined)
    regions = []
    for k, (pl, system, mapping, j) in enumerate(entries):
        if k - sum(1 for n in joined if n < k) not in score_bars:
            continue
        for s, (p, number) in zip(system.staves, mapping.staves):
            if (p, number) != (out_staff[0], out_staff[1]):
                continue
            i = system.staves.index(s)
            above = system.staves[i - 1].bottom if i > 0 else s.top - 4 * s.space
            below = system.staves[i + 1].top if i + 1 < len(system.staves) else s.bottom + 4 * s.space
            x0 = lay.bar_start(system, j)
            regions.append((pl.page, (x0, (above + s.top) / 2, system.bars[j].x1, (s.bottom + below) / 2), s.space))
    return regions


def centre(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def inside(box, region):
    x, y = centre(box)
    return region[0] <= x <= region[2] and region[1] <= y <= region[3]


# ------------------------------------------------------------ symbols against labels

def page_matches(vector_ps, vector_page, raster_page, detect):
    """For one page: [(class, label box in points, outcome, found class or
    None, height off in staff spaces)] for each training label, and [(class,
    box in points)] for each detection with no label. Outcome is "matched",
    "moved", "other class" or "missed"."""
    from omr.corpus import raster_labels as rl
    from omr.raster import detect as dt, names, reading

    seen = reading.detect_image(raster_page, detect)
    if seen is None or not vector_ps.staff_space:
        return [], []
    grey, _, place, _, found = seen
    zoom = 1 / place.sx
    labels = dt.truth_labels(vector_ps, vector_page, grey, zoom)
    settled = names.settle(found)
    found_px = [(cls, place.to_pixels(box)) for cls, box, _, _ in settled]
    space_px = vector_ps.staff_space * zoom

    def to_points(box):
        return (place.x0 + box[0] * place.sx, place.y0 + box[1] * place.sy,
                place.x0 + box[2] * place.sx, place.y0 + box[3] * place.sy)

    used, out = set(), []
    for lab in labels:
        best, best_iou = None, dt.MATCH
        for k, (cls, box) in enumerate(found_px):
            if k not in used and cls == lab.cls:
                v = rl.iou(lab.box, box)
                if v >= best_iou:
                    best, best_iou = k, v
        if best is not None:
            used.add(best)
            off = abs(centre(found_px[best][1])[1] - centre(lab.box)[1]) / space_px
            heights = lab.cls in rl.NOTEHEADS or lab.cls in rl.CLEFS or lab.cls in rl.ACCIDENTALS
            outcome = "moved" if heights and off > MOVED else "matched"
            out.append((lab.cls, to_points(lab.box), outcome, lab.cls, round(off, 2)))
            continue
        rival = max(((rl.iou(lab.box, box), k) for k, (cls, box) in enumerate(found_px) if k not in used),
                    default=(0, None))
        if rival[0] >= dt.MATCH:
            used.add(rival[1])
            out.append((lab.cls, to_points(lab.box), "other class", found_px[rival[1]][0], None))
        else:
            out.append((lab.cls, to_points(lab.box), "missed", None, None))
    extra = [(cls, to_points(box)) for k, (cls, box) in enumerate(found_px) if k not in used]
    return out, extra


def symbol_faults(regions, matches):
    """The symbol faults inside the regions: ["missed X", "X as Y", "X moved",
    "extra Y"]."""
    faults = []
    for page, region, _ in regions:
        labels, extra = matches.get(page, ([], []))
        for cls, box, outcome, got, _ in labels:
            if not inside(box, region) or outcome == "matched":
                continue
            faults.append(f"missed {cls}" if outcome == "missed" else f"{cls} moved" if outcome == "moved"
                          else f"{cls} as {got}")
        faults += [f"extra {cls}" for cls, box in extra if inside(box, region)]
    return faults


# ------------------------------------------------------------ one pair

def triage_pair(vector_pdf, raster_pdf, truth_path):
    """The figures for one pair (see the module docstring)."""
    import pymupdf

    from omr.pdf import symbols
    from omr.raster import reading, text as rt

    title = Path(vector_pdf).stem
    truth = truth_of(truth_path)
    vdoc, rdoc = pymupdf.open(str(vector_pdf)), pymupdf.open(str(raster_pdf))
    try:
        vuse = [vdoc[i] for i in range(len(vdoc))]
        vpages = symbols.read_document(vdoc, shown=vuse)
        detect, read_text = reading.detector(), rt.reader()
        rpages, ruse = [], []
        for k, vps in enumerate(vpages):
            ps, page = reading.read_page(rdoc[k], vps.page, detect, read_text)
            rpages.append(ps)
            ruse.append(page)
        # the image's lines were found with its own symbols masked, as the image reading finds them
        with_lines = ruse
        readings = {
            "vector": (vpages, vuse, False),
            "symbols": ([mixed(v, r, symbols=True) for v, r in zip(vpages, rpages)], vuse, False),
            "lines": ([mixed(v, r, lines=True) for v, r in zip(vpages, rpages)], with_lines, False),
            "text": ([mixed(v, r, text=True) for v, r in zip(vpages, rpages)], vuse, False),
            "engine 1": (rpages, ruse, False),
            "both": (rpages, ruse, True),
        }
        scored, failed = {}, {}
        for name, (pages, use, engines) in readings.items():
            try:
                score, ordered = read_with(pages, use, engines)
                scored[name] = (*score_units(score, truth, title), score, ordered)
            except Exception as error:   # one reading failing is itself a finding
                failed[name] = f"{type(error).__name__}: {error}"
        if "vector" not in scored or "both" not in scored:
            return {"failed readings": failed, "truth notes": len(truth.notes)}
        matches = {}
        for k, vps in enumerate(vpages):
            if rpages[k].symbols:
                matches[vps.page] = page_matches(vps, vdoc[k], rdoc[k], detect)
    finally:
        vdoc.close()
        rdoc.close()

    counts = {name: s[0] for name, s in scored.items()}
    totals = {name: sum(c.values()) for name, c in counts.items()}
    v_counts, v_kinds, v_result, v_shifted, v_score, v_ordered = scored["vector"]
    units = []
    every = set().union(*(c.keys() for c in counts.values()))
    for unit in sorted(every, key=lambda u: tuple(-1 if x is None else x for x in u)):
        base = v_counts.get(unit, 0)
        added = {name: counts[name].get(unit, 0) - base for name in counts if name != "vector"}
        if added.get("both", 0) <= 0 and added.get("engine 1", 0) <= 0:
            continue
        swaps = [s for s in SWAPS if added.get(s, 0) > 0]
        if added.get("engine 1", 0) <= 0:
            cause = "engine 2"
        elif swaps:
            cause = " and ".join(swaps)
        else:
            cause = "together"
        row = {"unit": list(unit), "added": added, "cause": cause,
               "kinds": dict(scored["both"][1].get(unit, {}))}
        if "symbols" in swaps or cause == "together":
            regions = staff_regions(unit, v_result, v_shifted, v_score, v_ordered)
            row["placed"] = bool(regions)
            row["faults"] = symbol_faults(regions, matches)
        units.append(row)
    label_totals = collections.Counter()
    for labels, extra in matches.values():
        for cls, _, outcome, got, _ in labels:
            label_totals[f"{outcome}|{cls}"] += 1
        for cls, _ in extra:
            label_totals[f"extra|{cls}"] += 1
    return {"truth notes": len(truth.notes), "errors": totals, "failed readings": failed,
            "units": units, "labels": dict(label_totals)}


def pair_job(pair):
    return triage_pair(Path(pair.meta["raster source"]), pair.pdf, pair.truth)


# ------------------------------------------------------------ summary

def summary_lines(results, title):
    ok = [r for r in results if "units" in r]
    lines = [f"Stage 2.9 raster triage, {title}: {len(ok)} pairs triaged, {len(results) - len(ok)} not "
             f"(a reading failed or the pair could not be read).", ""]
    truth = sum(r["truth notes"] for r in ok)
    lines.append(f"Note errors over {truth} notes, each reading:")
    for name in READINGS:
        errors = sum(r["errors"].get(name, 0) for r in ok)
        lines.append(f"- {name}: {errors} errors, {100 * (1 - errors / truth):.2f} percent of notes right"
                     if truth else f"- {name}: {errors}")
    failures = collections.Counter(name for r in results for name in r.get("failed readings", {}))
    if failures:
        lines.append("Readings that failed: " + ", ".join(f"{n} {c}" for n, c in failures.most_common()))

    # the penalty in the combined reading, by cause
    by_cause, bars_by_cause = collections.Counter(), collections.Counter()
    gained = 0
    for r in ok:
        for u in r["units"]:
            a = u["added"].get("both", 0)
            if a > 0:
                by_cause[u["cause"]] += a
                bars_by_cause[u["cause"]] += 1
        gained += sum(-u["added"]["both"] for u in r["units"] if u["added"].get("both", 0) < 0)
    total = sum(by_cause.values())
    lines += ["", f"Errors the image adds (staff bars where the combined reading has more errors than the PDF "
                  f"reading): {total} errors in {sum(bars_by_cause.values())} staff bars. By cause:"]
    for cause, n in by_cause.most_common():
        lines.append(f"- {cause}: {n} errors ({100 * n / total:.1f} percent) in {bars_by_cause[cause]} staff bars")
    lines.append(f"Errors Engine 2 saves where Engine 1 alone adds them: {gained}.")

    # error kinds by cause
    lines += ["", "Kinds of error added, by cause (combined reading):"]
    for cause, _ in by_cause.most_common():
        kinds = collections.Counter()
        for r in ok:
            for u in r["units"]:
                if u["cause"] == cause and u["added"].get("both", 0) > 0:
                    kinds.update(u["kinds"])
        lines.append(f"- {cause}: " + ", ".join(f"{k} {n}" for k, n in kinds.most_common(8)))

    # symbol faults, each staff bar's added errors shared among its faults
    faults, bars, unplaced, faultless = collections.Counter(), collections.Counter(), 0, 0
    for r in ok:
        for u in r["units"]:
            a = u["added"].get("both", 0)
            if a <= 0 or "faults" not in u:
                continue
            if not u.get("placed"):
                unplaced += a
                continue
            if not u["faults"]:
                faultless += a
                continue
            share = a / len(u["faults"])
            for f in u["faults"]:
                faults[f] += share
            for f in set(u["faults"]):
                bars[f] += 1
    lines += ["", "Symbol faults in the staff bars the symbols (or the whole reading) spoil: errors shared "
                  "among the faults found there, top 40:"]
    for f, n in faults.most_common(40):
        lines.append(f"- {f}: {n:.0f} errors, {bars[f]} staff bars")
    lines.append(f"Errors in such staff bars with no symbol fault there: {faultless}; not placed on the page: "
                 f"{unplaced}.")

    # the detector against its labels over the pages read
    lt = collections.Counter()
    for r in ok:
        lt.update(r["labels"])
    lines += ["", "Detector against the training labels on these pages (labels missed, found as another class, "
                  "moved; detections with no label), worst classes by faults:"]
    classes = {k.split("|", 1)[1] for k in lt}
    rows = []
    for cls in classes:
        n = sum(lt[f"{o}|{cls}"] for o in ("matched", "moved", "other class", "missed"))
        bad = lt[f"missed|{cls}"] + lt[f"other class|{cls}"] + lt[f"moved|{cls}"] + lt[f"extra|{cls}"]
        rows.append((bad, cls, n))
    for bad, cls, n in sorted(rows, reverse=True)[:25]:
        lines.append(f"- {cls}: {n} labels; missed {lt[f'missed|{cls}']}, other class {lt[f'other class|{cls}']}, "
                     f"moved {lt[f'moved|{cls}']}; extra {lt[f'extra|{cls}']}")

    # the worst pairs
    lines += ["", "Pairs with the most errors added (combined reading against the PDF reading):"]
    worst = sorted(ok, key=lambda r: r["errors"].get("vector", 0) - r["errors"].get("both", 0))[:20]
    for r in worst:
        e = r["errors"]
        lines.append(f"- {r['pair']}: vector {e.get('vector')}, symbols {e.get('symbols')}, lines {e.get('lines')}, "
                     f"text {e.get('text')}, engine 1 {e.get('engine 1')}, both {e.get('both')} "
                     f"of {r['truth notes']} notes")
    return lines


# ------------------------------------------------------------ main

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("set", help="regression or development")
    parser.add_argument("version", help="g300, g200 or g150")
    parser.add_argument("--name", default="s36-triage", help="evaluation folder name")
    parser.add_argument("--every", type=int, default=1, help="every Nth pair only")
    parser.add_argument("--limit", type=int, help="only the first N pairs chosen, for a trial")
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--summary-only", action="store_true", help="rewrite summary.txt from results.jsonl")
    args = parser.parse_args()
    if args.set == "check":
        print("The check set stays sealed until a milestone; it is not triaged.")
        return 2
    out_dir = paths.require_corpus_dir() / "evaluations" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    title = f"{args.set}-{args.version}, every {args.every}"
    if args.summary_only:
        results = [json.loads(line) for line in open(out_dir / "results.jsonl", encoding="utf-8")]
        (out_dir / "summary.txt").write_text("\n".join(summary_lines(results, title)) + "\n", encoding="utf-8")
        return 0
    log = ProgressLog("triage_raster", out_dir / "triage.log")
    root = paths.require_corpus_dir() / "generated" / "raster" / f"{args.set}-{args.version}"
    pairs, _ = harness.read_pairs(args.set, root)
    pairs = pairs[::args.every][:args.limit] if args.limit else pairs[::args.every]
    done = set()
    results_path = out_dir / "results.jsonl"
    results = []
    if results_path.is_file():   # carry on from an earlier run
        results = [json.loads(line) for line in open(results_path, encoding="utf-8")]
        done = {r["pair"] for r in results}
    todo = [p for p in pairs if p.name not in done]
    log.info(f"{title}: {len(pairs)} pairs, {len(todo)} to triage, {args.workers} workers.")
    with parallel.pool(args.workers) as executor, open(results_path, "a", encoding="utf-8") as out:
        running = {}

        def collect(finished):
            for future, pair in finished:
                try:
                    row = future.result()
                except Exception as error:
                    row = {"error": f"{type(error).__name__}: {error}"}
                    log.error(f"{pair.name} failed: {row['error']}")
                row.update({"pair": pair.name, "engraver": pair.meta.get("engraver", "unknown")})
                results.append(row)
                out.write(json.dumps(row) + "\n")
                out.flush()
                if len(results) % 10 == 0:
                    log.info(f"{len(results)} of {len(pairs)} pairs triaged.")

        for pair in todo:
            pause.wait_while_paused(log)
            running[executor.submit(pair_job, pair)] = pair
            while len(running) >= args.workers * 2:
                collect(parallel.finished(running, block=True))
        while running:
            collect(parallel.finished(running, block=True))
    (out_dir / "summary.txt").write_text("\n".join(summary_lines(results, title)) + "\n", encoding="utf-8")
    return log.finish(f"{len(results)} pairs triaged")


if __name__ == "__main__":
    sys.exit(main())
