"""Stage 8 survey: run `omr inspect` over real-world PDFs and tabulate the result.

Sub-commands:
  pdmx-sample N   extract a seeded sample of N PDFs from the PDMX archive
  inspect         inspect every PDF in the survey sources, resumable
  report          write the counts as plain text (survey-counts.txt in the corpus work folder)
  symbols         name the music symbols in every PDF (Stage 1.1), resumable
  symbols-report  write the symbol counts and unmapped glyphs (symbols-counts.txt)

Sources, all under `sources/` in the corpus folder:
  openscore  (the OpenScore string quartet and lieder PDFs, MuseScore output)
  mutopia    (collect_mutopia.py)
  pdmx-pdf   (pdmx-sample, real MuseScore.com exports)
  other      (any PDFs placed there by hand, for example IMSLP files)
Results: `survey/results.jsonl`, one JSON record per file. The symbol
survey also reads the regression set in the repository, and writes
`survey/symbols.jsonl`.
"""

import argparse
import csv
import hashlib
import json
import random
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

from omr import inspect as omr_inspect
from omr import paths
from omr.log import ProgressLog
from omr.parallel import DEFAULT_WORKERS, check_workers, pool

SEED = 20261007
SOURCES = ("openscore", "mutopia", "pdmx-pdf", "other")


def survey_dir():
    folder = paths.require_corpus_dir() / "survey"
    folder.mkdir(exist_ok=True)
    return folder


def pdmx_sample(count, log):
    src = paths.require_corpus_dir() / "sources"
    csv.field_size_limit(10**9)
    wanted = {}
    with open(src / "pdmx" / "PDMX.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["subset:no_license_conflict"] == "True" and row["pdf"] not in ("", "NA"):
                wanted[row["pdf"].lstrip("./")] = row["license"]
    names = sorted(wanted)
    chosen = set(random.Random(SEED).sample(names, min(count, len(names))))
    out = src / "pdmx-pdf"
    out.mkdir(exist_ok=True)
    index = out / "index.txt"
    got = 0
    log.info(f"{len(chosen)} PDFs chosen from {len(names)} eligible. Reading the archive (one pass).")
    with tarfile.open(src / "pdmx" / "pdf.tar.gz", "r|gz") as tar:
        for member in tar:
            name = member.name.lstrip("./")
            if name in chosen and member.isfile():
                target = out / (hashlib.sha1(name.encode()).hexdigest()[:12] + ".pdf")
                if not target.exists():
                    target.write_bytes(tar.extractfile(member).read())
                with open(index, "a", encoding="utf-8") as f:
                    f.write(f"{target.name}\t{wanted[name]}\t{name}\n")
                got += 1
    log.info(f"Extracted {got} PDFs.")
    return got


def _inspect_one(path):
    try:
        result = omr_inspect.inspect_file(path)
        return omr_inspect.file_json(result)
    except omr_inspect.InspectError as error:
        return omr_inspect.error_json(path, str(error))
    except Exception as error:  # a crash on one odd file must not stop the survey
        return omr_inspect.error_json(path, f"crash: {type(error).__name__}: {error}")


def run_inspect(workers, log):
    src = paths.require_corpus_dir() / "sources"
    results = survey_dir() / "results.jsonl"
    done = set()
    if results.exists():
        done = {json.loads(l)["source_key"] for l in results.read_text(encoding="utf-8").splitlines() if l}
    todo = []
    for source in SOURCES:
        folder = src / source
        if folder.is_dir():
            todo += [(source, p) for p in sorted(folder.rglob("*.pdf")) if f"{source}/{p.relative_to(folder).as_posix()}" not in done]
    log.info(f"{len(todo)} files to inspect, {len(done)} already done.")
    failed = 0
    with pool(workers) as ex, open(results, "a", encoding="utf-8") as out:
        futures = {ex.submit(_inspect_one, p): (s, p) for s, p in todo}
        import concurrent.futures as cf
        for n, fut in enumerate(cf.as_completed(futures), 1):
            source, path = futures[fut]
            rec = fut.result()
            rec["source"] = source
            rec["source_key"] = f"{source}/{path.relative_to(src / source).as_posix()}"
            rec["bytes"] = path.stat().st_size
            if rec["error"]:
                failed += 1
                log.warning(f"{rec['source_key']}: {rec['error']}")
            out.write(json.dumps(rec) + "\n")
            out.flush()
            if n % 200 == 0:
                log.info(f"{n} of {len(todo)} done.")
    return len(todo), failed


def _symbols_one(path):
    from omr import symbol_report

    try:
        return symbol_report.file_json(symbol_report.read_file(path))
    except omr_inspect.InspectError as error:
        return {"file": str(path), "error": str(error)}
    except Exception as error:  # a crash on one odd file must not stop the survey
        return {"file": str(path), "error": f"crash: {type(error).__name__}: {error}"}


def symbol_sources():
    src = paths.require_corpus_dir() / "sources"
    folders = {source: src / source for source in SOURCES}
    folders["regression"] = paths.REPO_ROOT / "regression"
    return folders


def run_symbols(workers, log):
    results = survey_dir() / "symbols.jsonl"
    done = set()
    if results.exists():
        done = {json.loads(l)["source_key"] for l in results.read_text(encoding="utf-8").splitlines() if l}
    todo = []
    for source, folder in symbol_sources().items():
        if folder.is_dir():
            todo += [(source, folder, p) for p in sorted(folder.rglob("*.pdf"))
                     if f"{source}/{p.relative_to(folder).as_posix()}" not in done]
    log.info(f"{len(todo)} files to read, {len(done)} already done.")
    failed = 0
    with pool(workers) as ex, open(results, "a", encoding="utf-8") as out:
        futures = {ex.submit(_symbols_one, p): (s, f, p) for s, f, p in todo}
        import concurrent.futures as cf
        for n, fut in enumerate(cf.as_completed(futures), 1):
            source, folder, path = futures[fut]
            rec = fut.result()
            rec["source"] = source
            rec["source_key"] = f"{source}/{path.relative_to(folder).as_posix()}"
            if rec.get("error"):
                failed += 1
                log.warning(f"{rec['source_key']}: {rec['error']}")
            out.write(json.dumps(rec) + "\n")
            out.flush()
            if n % 200 == 0:
                log.info(f"{n} of {len(todo)} done.")
    return len(todo), failed


def symbols_report(log):
    path = survey_dir() / "symbols.jsonl"
    recs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]
    lines = ["# Symbol survey (Stage 1.1)", "",
             "Every music glyph is named by SMuFL code point or a font table, and outlined",
             "symbols by shape. Unmapped glyphs are counted per file.", ""]
    by_source = defaultdict(list)
    for r in recs:
        by_source[r["source"]].append(r)
    for source, rs in [("all sources", recs)] + sorted(by_source.items()):
        ok = [r for r in rs if not r.get("error")]
        named = sum(sum(r["symbols"].values()) for r in ok)
        unmapped = Counter()
        for r in ok:
            for u in r["unmapped"]:
                unmapped[(u["font"], u["glyph"])] += u["count"]
        missing = sum(unmapped.values())
        with_unmapped = [r for r in ok if r["unmapped"]]
        font_glyphs = sum(n for (f, _), n in unmapped.items() if f != "outlines")
        lines += [f"## {source}", "",
                  f"- Files: {len(rs)}, failed: {len(rs) - len(ok)}.",
                  f"- Symbols named: {named}. Unmapped: {missing} ({pct(missing, named + missing)}), "
                  f"of which {font_glyphs} font glyphs and {missing - font_glyphs} outlined shapes.",
                  f"- Files with any unmapped glyph or shape: {len(with_unmapped)} ({pct(len(with_unmapped), len(ok))})."]
        worst = sorted(with_unmapped, key=lambda r: -sum(u["count"] for u in r["unmapped"]))[:5]
        if worst:
            lines.append("- Most unmapped: " + "; ".join(
                f"{Path(r['file']).name} {sum(u['count'] for u in r['unmapped'])}" for r in worst) + ".")
        shapes = Counter((f["font"], f["table"]) for r in ok for f in r["fonts"] if f["how"] == "shapes")
        if shapes:
            lines.append("- Fonts identified by shape: " + "; ".join(f"{f} as {t} ({n} files)" for (f, t), n in shapes.most_common(10)) + ".")
        if unmapped:
            lines += ["", "Unmapped, most common:", ""]
            for (font, glyph), n in unmapped.most_common(25):
                lines.append(f"- {font}: {glyph}, {n}.")
        lines.append("")
    out = survey_dir() / "symbols-counts.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Counts written to {out}.")


def load():
    path = survey_dir() / "results.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]


def pct(a, b):
    return f"{100 * a / b:.1f} percent" if b else "n/a"


def report(log):
    recs = load()
    lines = ["# Survey counts", ""]
    by_source = defaultdict(list)
    for r in recs:
        by_source[r["source"]].append(r)
    for source, rs in [("all sources", recs)] + sorted(by_source.items()):
        ok = [r for r in rs if not r["error"]]
        pages = [p for r in ok for p in r["page_results"]]
        lines += [f"## {source}", "",
                  f"- Files: {len(rs)}, failed to open: {len(rs) - len(ok)}, pages: {len(pages)}."]
        types = Counter(p["type"] for p in pages)
        lines.append("- Pages by type: " + ", ".join(f"{t} {n} ({pct(n, len(pages))})" for t, n in sorted(types.items())))
        ftypes = Counter(tuple(sorted(r["summary"]["types"])) for r in ok)
        lines.append("- Files by set of page types: " + ", ".join(f"{'+'.join(k) or 'none'} {n}" for k, n in ftypes.most_common()))
        conf = Counter((p["type"], p["confidence"]) for p in pages)
        lines.append("- Type and confidence: " + ", ".join(f"{t}/{c} {n}" for (t, c), n in sorted(conf.items())))
        outlined = sum(1 for r in ok if any(p["type"] == "B" for p in r["page_results"]))
        lines.append(f"- Files with at least one outlined-glyph page (B): {outlined} ({pct(outlined, len(ok))}).")
        prod = Counter((r["producer"] or r["creator"] or "none")[:40] for r in ok)
        lines.append("- Producers (top 10): " + "; ".join(f"{k} {n}" for k, n in prod.most_common(10)))
        fonts = defaultdict(lambda: [0, 0, set(), ""])
        for r in ok:
            for f in r["summary"]["music_fonts"]:
                e = fonts[f["name"]]
                e[0] += 1; e[1] += f["glyphs"]; e[3] = f["class"]
        lines += ["", "Music fonts, by number of files:", ""]
        for name, (n, g, _, cls) in sorted(fonts.items(), key=lambda kv: -kv[1][0])[:25]:
            lines.append(f"- {name}: {n} files ({pct(n, len(ok))}), {g} glyphs, class {cls}.")
        lines.append("")
    # fonts not classed as music but with glyphs on staves
    cand = defaultdict(lambda: [0, 0, 0])
    for r in recs:
        for p in r.get("page_results", []):
            for f in p["fonts"]:
                if f["class"] in ("text", "smufl_text") and f.get("glyphs_on_staves", 0) >= 10:
                    c = cand[f["name"]]
                    c[0] += 1; c[1] += f["glyphs_on_staves"]; c[2] += f["glyphs"]
    lines += ["## Fonts with glyphs on staves but not classed as music", ""]
    for name, (pg, inside, total) in sorted(cand.items(), key=lambda kv: -kv[1][1])[:30]:
        lines.append(f"- {name}: {pg} pages, {inside} of {total} glyphs on staves.")
    lines.append("")
    out = survey_dir() / "survey-counts.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Counts written to {out}.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pdmx-sample"); s.add_argument("count", type=int)
    i = sub.add_parser("inspect"); i.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    sub.add_parser("report")
    y = sub.add_parser("symbols"); y.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    sub.add_parser("symbols-report")
    args = ap.parse_args(argv)
    log = ProgressLog("survey", path=survey_dir() / "survey.log")
    if args.cmd == "pdmx-sample":
        n = pdmx_sample(args.count, log)
        return log.finish(f"{n} PDFs extracted")
    if args.cmd == "inspect":
        n, failed = run_inspect(check_workers(args.workers), log)
        return log.finish(f"{n} files inspected, {failed} failed to open")
    if args.cmd == "symbols":
        n, failed = run_symbols(check_workers(args.workers), log)
        return log.finish(f"{n} files read, {failed} failed")
    if args.cmd == "symbols-report":
        symbols_report(log)
        return log.finish("symbol report written")
    report(log)
    return log.finish("report written")


if __name__ == "__main__":
    sys.exit(main())
