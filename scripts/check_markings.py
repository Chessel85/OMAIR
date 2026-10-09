"""Check the text and markings read from PDFs (Stage 1.4) against the ground truth.

For each pair of a set (default: the regression set in the repository), the
score is read from the PDF alone (`omr.pdf.structure.read_pdf` with notes),
and compared with the ground-truth MusicXML by the evaluation harness's own
rules, so the marking figures are those `omr evaluate` would give:

- dynamics, hairpins, hairpin ends, words and chord symbols, by text, bar
  and onset (recall and precision); ACC-6 is the recall of dynamics and
  hairpins together on exact pairs (MuseScore 4);
- articulations, fermatas, ornaments, fingering, slur ends and lyrics on
  exactly matched notes (recall), and the lyric syllables (hyphens and
  melismas) on matched lyrics.

It also scores the text kinds the harness does not compare: the title,
subtitle, composer, lyricist and rights against the ground truth's credits,
rehearsal marks, metronome marks, and part names.

Usage:
  python scripts/check_markings.py [--set-root FOLDER] [--job NAME] [--score ID] [--limit N]
                                   [--workers N] [--out FILE] [--json FILE] [--min-acc6 PERCENT]

With --min-acc6 the command fails (exit status 1) if ACC-6 over the exact
pairs checked is below that percentage, or if any pair could not be read.
"""

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from omr import parallel, paths
from omr.log import ProgressLog

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_notes import pairs, pct  # noqa: E402

MARKING_KINDS = ("dynamic", "hairpin", "hairpin end", "words", "chord symbol")
CREDIT_KINDS = ("title", "subtitle", "composer", "lyricist", "rights")


def norm(text):
    return " ".join((text or "").lower().replace("ﬁ", "fi").replace("ﬂ", "fl").replace("ﬀ", "ff").split())


def truth_extras(root):
    """Credits, rehearsal marks, metronome marks and part names of a ground truth."""
    credits = []
    for c in root.iter("credit"):
        kind = (c.findtext("credit-type") or "").strip()
        words = " ".join(" ".join((w.text or "").split()) for w in c.findall("credit-words")).strip()
        if kind in CREDIT_KINDS and words:
            credits.append((kind, words))
    rehearsals, metronomes = [], []
    first = root.find("part")
    if first is not None:
        for bar, measure in enumerate(first.findall("measure")):
            for d in measure.iter("direction"):
                for r in d.iter("rehearsal"):
                    if (r.text or "").strip():
                        rehearsals.append((bar, r.text.strip()))
                for m in d.iter("metronome"):
                    unit = (m.findtext("beat-unit") or "").strip() + ("." if m.find("beat-unit-dot") is not None else "")
                    per = (m.findtext("per-minute") or "").strip()
                    if per:
                        metronomes.append((bar, f"{unit} = {per}"))
    names = [(sp.findtext("part-name") or "").strip() for sp in root.iter("score-part")]
    chords = []
    for part in root.findall("part"):
        for bar, measure in enumerate(part.findall("measure")):
            for h in measure.iter("harmony"):
                step = (h.findtext("root/root-step") or "").strip()
                if not step:
                    continue
                alter = {"-1": "b", "1": "#"}.get((h.findtext("root/root-alter") or "").strip(), "")
                chords.append((bar, step + alter, (h.findtext("kind") or "").strip()))
    return credits, rehearsals, metronomes, names, chords


def check_pair(pdf, truth_path):
    from omr.evaluate import events, match, metrics
    from omr.evaluate.describe import Describer
    from omr.pdf import structure
    from omr.pdf import text as pdf_text

    root = events.read_root(truth_path)
    truth = events.from_root(root)
    found, _ = structure.read_pdf(pdf, notes=True)
    result = match.match(truth, found)
    say = Describer(truth)
    markings = metrics._markings(truth, result.output, result, say)
    note_marks = metrics._note_marks(result)
    # lyric syllables: on matched notes with the same lyric text
    syllables = {"truth": 0, "right": 0}
    for t, o in result.exact:
        out = {(text, ): None for _, text in o.lyrics}
        forms_o = {text: form for (_, text), form in zip(o.lyrics, o.syllables)}
        for (_, text), form in zip(t.lyrics, t.syllables):
            if text and (text, ) in out:
                syllables["truth"] += 1
                other = forms_o.get(text)
                syllables["right"] += other is not None and other[1:] == form[1:]
    credits, rehearsals, metronomes, names, chords = truth_extras(root)
    page_text = [(i.kind, norm(i.text)) for i in found.text]
    credit_figures = {k: {"truth": 0, "found": 0, "text found": 0} for k in CREDIT_KINDS}
    missed_credits = []
    for kind, words in credits:
        credit_figures[kind]["truth"] += 1
        target = norm(words)
        if (kind, target) in page_text:
            credit_figures[kind]["found"] += 1
            credit_figures[kind]["text found"] += 1
        elif any(t == target for _, t in page_text):
            credit_figures[kind]["text found"] += 1
            missed_credits.append(f"{kind} {words!r} found as {next(k for k, t in page_text if t == target)}")
        else:
            missed_credits.append(f"{kind} {words!r} not found")
    output_credits = collections.Counter(k for k, _ in page_text if k in CREDIT_KINDS)
    out_rehearsals = {(m.bar, norm(m.value)) for m in found.markings if m.kind == "rehearsal"}
    out_metronomes = {(m.bar, m.value) for m in found.markings if m.kind == "metronome"}
    bar_map = {}
    for segment in result.segments:
        for t_bar, o_bar in zip(segment.truth, segment.output):
            bar_map[t_bar] = o_bar
    # chord symbols by meaning: root and MusicXML kind in the same bar, whatever
    # the ground truth prints (MuseScore often writes a kind without its text)
    out_chords = collections.Counter()
    for m in found.markings:
        if m.kind == "chord symbol":
            chord_root, kind, _ = pdf_text.chord_kind(m.value)
            out_chords[(m.bar, chord_root, kind)] += 1
    truth_chords = collections.Counter((bar_map.get(b), r, k) for b, r, k in chords)
    names_found = 0
    if len(names) > 1 and len(found.parts) == len(names):
        names_found = sum(norm(a) == norm(b.name) for a, b in zip(names, found.parts) if a)
    return {
        "markings": {k: {"truth": v["truth"], "found": v["found"], "output": v["output"], "missed": v["missed"][:20]}
                     for k, v in markings.items()},
        "note marks": note_marks,
        "syllables": syllables,
        "credits": credit_figures, "output credits": dict(output_credits), "missed credits": missed_credits,
        "rehearsals": {"truth": len(rehearsals), "output": len(out_rehearsals),
                       "found": sum((bar_map.get(b), norm(t)) in out_rehearsals for b, t in rehearsals)},
        "metronomes": {"truth": len(metronomes), "output": len(out_metronomes),
                       "found": sum((bar_map.get(b), v) in out_metronomes for b, v in metronomes)},
        "part names": {"truth": sum(1 for n in names if n) if len(names) > 1 else 0, "found": names_found},
        "chords by meaning": {"truth": sum(truth_chords.values()), "found": sum((truth_chords & out_chords).values())},
        "notes": {"exact": len(result.exact), "truth": len(truth.notes)},
    }


def exact_job(job):
    return job.startswith("musescore4")


def report(results):
    lines = ["# Text and markings from PDFs against the ground truth (Stage 1.4)", ""]
    groups = (("Exact pairs", exact_job), ("Engraver-input pairs", lambda j: not exact_job(j)))
    exact = [r for (s, j), r in results.items() if exact_job(j)]
    if exact:
        f = sum(r["markings"][k]["found"] for r in exact for k in ("dynamic", "hairpin"))
        t = sum(r["markings"][k]["truth"] for r in exact for k in ("dynamic", "hairpin"))
        lines.append(f"- ACC-6, recall of dynamics and hairpins on exact pairs (target 90 percent): {pct(f, t)} "
                     f"({f:,} of {t:,}).")
        lines.append("")
    lines += ["## Markings by text, bar and onset", ""]
    for title, keep in groups:
        chosen = [r for (s, j), r in results.items() if keep(j)]
        if not chosen:
            continue
        lines.append(f"### {title} ({len(chosen)} files)")
        lines.append("")
        for k in MARKING_KINDS:
            t = sum(r["markings"][k]["truth"] for r in chosen)
            f = sum(r["markings"][k]["found"] for r in chosen)
            o = sum(r["markings"][k]["output"] for r in chosen)
            lines.append(f"- {k}: recall {pct(f, t)} ({f:,} of {t:,}), precision {pct(f, o)} ({o:,} written).")
        lines.append("")
    lines += ["## Marks on matched notes (recall)", ""]
    for title, keep in groups:
        chosen = [r for (s, j), r in results.items() if keep(j)]
        if not chosen:
            continue
        totals = collections.defaultdict(lambda: [0, 0])
        for r in chosen:
            for k, v in r["note marks"].items():
                totals[k][0] += v["found"]
                totals[k][1] += v["truth"]
        s_right = sum(r["syllables"]["right"] for r in chosen)
        s_truth = sum(r["syllables"]["truth"] for r in chosen)
        lines.append(f"### {title}")
        lines.append("")
        for k, (f, t) in sorted(totals.items(), key=lambda kv: -kv[1][1]):
            lines.append(f"- {k}: {pct(f, t)} ({f:,} of {t:,}).")
        lines.append(f"- Lyric syllables (hyphen and melisma right, of the lyrics found): {pct(s_right, s_truth)} "
                     f"({s_right:,} of {s_truth:,}).")
        lines.append("")
    lines += ["## Page text and other text", "",
              "Credits are compared by kind and text with the ground truth's credits. "
              "Exact pairs only: the engraver-input PDFs set their own headings.", ""]
    for k in CREDIT_KINDS:
        t = sum(r["credits"][k]["truth"] for r in exact)
        f = sum(r["credits"][k]["found"] for r in exact)
        tf = sum(r["credits"][k]["text found"] for r in exact)
        o = sum(r["output credits"].get(k, 0) for r in exact)
        lines.append(f"- {k}: {pct(f, t)} found with the right kind ({f} of {t}); text found under any kind "
                     f"{pct(tf, t)}; {o} written.")
    for name, key in (("Rehearsal marks", "rehearsals"), ("Metronome marks", "metronomes")):
        t = sum(r[key]["truth"] for r in exact)
        f = sum(r[key]["found"] for r in exact)
        o = sum(r[key]["output"] for r in exact)
        lines.append(f"- {name}: recall {pct(f, t)} ({f} of {t}), precision {pct(f, o)} ({o} written).")
    t = sum(r["chords by meaning"]["truth"] for r in exact)
    f = sum(r["chords by meaning"]["found"] for r in exact)
    lines.append(f"- Chord symbols by meaning (root and kind in the same bar, not the printed text the harness "
                 f"compares): {pct(f, t)} ({f:,} of {t:,}).")
    t = sum(r["part names"]["truth"] for r in exact)
    f = sum(r["part names"]["found"] for r in exact)
    lines.append(f"- Part names (scores of two or more parts): {pct(f, t)} ({f} of {t}).")
    lines += ["", "## By job", ""]
    by_job = collections.defaultdict(list)
    for (s, j), r in results.items():
        by_job[j].append(r)
    for job, chosen in sorted(by_job.items()):
        parts = []
        for k in ("dynamic", "hairpin", "words", "chord symbol"):
            t = sum(r["markings"][k]["truth"] for r in chosen)
            f = sum(r["markings"][k]["found"] for r in chosen)
            o = sum(r["markings"][k]["output"] for r in chosen)
            parts.append(f"{k} {pct(f, t)} recall, {pct(f, o)} precision")
        lt = sum(r["note marks"].get("lyrics", {}).get("truth", 0) for r in chosen)
        lf = sum(r["note marks"].get("lyrics", {}).get("found", 0) for r in chosen)
        parts.append(f"lyrics {pct(lf, lt)}")
        lines.append(f"- {job}: " + "; ".join(parts) + ".")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set-root", default=str(paths.REPO_ROOT / "regression"))
    parser.add_argument("--job", help="Only this engraver job, for example musescore4-base.")
    parser.add_argument("--score", help="Only this score id.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS)
    parser.add_argument("--out", help="Also write the report to this file.")
    parser.add_argument("--json", help="Also write every pair's figures to this file.")
    parser.add_argument("--min-acc6", type=float, metavar="PERCENT",
                        help="Fail if ACC-6 over the exact pairs is below this.")
    args = parser.parse_args(argv)
    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = ProgressLog("check-markings", path=str(logs / "check-markings.log"))
    todo = pairs(args.set_root, args.job, args.limit, args.score)
    if not todo:
        log.error(f"No pairs found in {args.set_root}. Check the folder has an index.txt.")
        return log.finish("0 files checked")
    results = {}
    failed = 0
    with parallel.pool(args.workers) as executor:
        running = {executor.submit(check_pair, pdf, truth): (score, job) for score, job, pdf, truth in todo}
        while running:
            for future, (score, job) in parallel.finished(running, block=True):
                try:
                    results[(score, job)] = future.result()
                except Exception as error:   # report and go on with the rest
                    failed += 1
                    log.error(f"{score} {job}: {type(error).__name__}: {error}")
                done = len(results) + failed
                if done % 100 == 0:
                    log.info(f"{done} of {len(todo)} pairs checked.")
    text = report(results)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        log.info(f"Report written to {args.out}.")
    if args.json:
        Path(args.json).write_text(json.dumps({f"{s}|{j}": r for (s, j), r in results.items()}, indent=1),
                                   encoding="utf-8")
    exact = [r for (s, j), r in results.items() if exact_job(j)]
    f = sum(r["markings"][k]["found"] for r in exact for k in ("dynamic", "hairpin"))
    t = sum(r["markings"][k]["truth"] for r in exact for k in ("dynamic", "hairpin"))
    if args.min_acc6 is not None and (failed or (t and 100 * f / t < args.min_acc6)):
        log.error(f"ACC-6 {pct(f, t)} with {failed} unread pairs; the floor is {args.min_acc6} percent "
                  f"with every pair read.")
    return log.finish(f"{len(results)} files checked, {failed} failed, ACC-6 {pct(f, t)}")


if __name__ == "__main__":
    sys.exit(main())
