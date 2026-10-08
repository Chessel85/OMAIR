"""Stage 9: break down baseline results in ways the harness report does not.

Reads one results.json per recogniser (from `omr evaluate`) and prints a plain-text
analysis: failures, the spread of per-file accuracy, the error mix, spurious and
missed tuplets, clef errors, base against variant exports, staff size, score
features, pages, structural mismatch kinds, a head-to-head between recognisers,
and seconds per page. Note accuracy is M / (T + E + C), as in the evaluation spec.

usage: python scripts/analyse_baselines.py NAME=RESULTS.json [NAME=RESULTS.json ...] [--out FILE]
"""

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

STRUCTURE_PATTERNS = [
    ("parts", re.compile(r"has \d+ parts?, the output has")),
    ("bar count", re.compile(r"has \d+ bars?, the output has")),
    ("clef", re.compile(r"clef")),
    ("key signature", re.compile(r"key signature")),
    ("time signature", re.compile(r"time signature")),
    ("repeat", re.compile(r"repeat")),
    ("ending", re.compile(r"ending")),
    ("navigation", re.compile(r"segno|coda|fine|da capo|dal segno", re.I)),
]
TUPLET = re.compile(r"triplet|tuplet|\d+:\d+")
_pages = {}


def pages_of(pdf):
    if pdf not in _pages:
        try:
            with pymupdf.open(pdf) as doc:
                _pages[pdf] = len(doc)
        except Exception:
            _pages[pdf] = None
    return _pages[pdf]


def pct(a, b):
    return f"{100 * a / b:.1f} percent" if b else "none"


class Tally:
    """Pooled note accuracy over a group of files."""

    def __init__(self):
        self.exact = self.denominator = self.files = self.failed = 0

    def add(self, r):
        n = r["notes"]
        self.exact += n["exact"]
        self.denominator += n["truth"] + n["extra"] + n.get("clef errors", 0)
        self.files += 1
        self.failed += "failed" in r

    def line(self, label):
        failed = f", {self.failed} failed" if self.failed else ""
        return f"- {label}: {self.files} files, note accuracy {pct(self.exact, self.denominator)}{failed}."


def file_accuracy(r):
    n = r["notes"]
    d = n["truth"] + n["extra"] + n.get("clef errors", 0)
    return n["exact"] / d if d else 1.0


def grouped(results, key):
    groups = defaultdict(Tally)
    for r in results:
        groups[key(r)].add(r)
    return groups


def failure_kind(text):
    if "longer than" in text:
        return "timed out"
    if "wrote no MusicXML" in text:
        return "wrote no MusicXML"
    if "exited with status" in text:
        return "exited with an error"
    return text[:60]


def analyse(name, results, out):
    say = out.append
    say(f"## {name}")
    say("")
    total = Tally()
    for r in results:
        total.add(r)
    say(total.line("All files"))
    done = [r for r in results if "failed" not in r]
    kinds = Counter(failure_kind(r["failed"]) for r in results if "failed" in r)
    if kinds:
        say("- Failures: " + "; ".join(f"{k}: {v}" for k, v in kinds.most_common()) + ".")
        failed_notes = sum(r["notes"]["truth"] for r in results if "failed" in r)
        say(f"- The failed files hold {failed_notes:,} of {sum(r['notes']['truth'] for r in results):,} ground-truth notes.")
    acc = sorted(file_accuracy(r) for r in done)
    if acc:
        say(f"- Completed files: {len(acc)}. Per-file accuracy: median {100 * statistics.median(acc):.1f}, "
            f"lower quartile {100 * acc[len(acc) // 4]:.1f}, upper quartile {100 * acc[3 * len(acc) // 4]:.1f}.")
        for bound in (0.99, 0.95, 0.90):
            say(f"- Files at {round(bound * 100)} percent or better: {sum(a >= bound for a in acc)} of {len(acc)}.")
        say(f"- Files below 50 percent: {sum(a < 0.5 for a in acc)} of {len(acc)}.")
    say("")

    say("### Error mix (completed files)")
    n = Counter()
    wrong = Counter()
    for r in done:
        for k in ("truth", "exact", "wrong", "missing", "extra"):
            n[k] += r["notes"][k]
        n["clef"] += r["notes"].get("clef errors", 0)
        wrong.update(r["notes"]["wrong by kind"])
    errors = n["wrong"] + n["missing"] + n["extra"] + n["clef"]
    say(f"- {errors:,} errors: wrong {pct(n['wrong'], errors)}, missing {pct(n['missing'], errors)}, "
        f"extra {pct(n['extra'], errors)}, clef {pct(n['clef'], errors)}.")
    say("- Wrong notes by what differs: " + "; ".join(f"{k} {v:,}" for k, v in wrong.most_common()) + ".")
    spurious = missed = 0
    for r in done:
        for e in r["errors"]:
            exp, found = e.get("expected", ""), e.get("found", "")
            if TUPLET.search(found) and not TUPLET.search(exp):
                spurious += 1
            elif TUPLET.search(exp) and not TUPLET.search(found):
                missed += 1
    say(f"- Tuplets: {spurious:,} wrong notes read as tuplets that are not, {missed:,} tuplet notes read as plain notes "
        f"(together {pct(spurious + missed, n['wrong'])} of the wrong notes).")
    clefs = Counter()
    for r in done:
        for e in r["errors"]:
            if e["kind"] == "clef error":
                clefs[f"{e['expected'][2:]} read as {e['found'][2:]}"] += 1
    if clefs:
        say("- Clef errors: " + "; ".join(f"{k}: {v}" for k, v in clefs.most_common(8)) + ".")
    say("")

    say("### By export")
    for label, t in sorted(grouped(results, lambda r: r["job"]).items()):
        say(t.line(label))
    say("")
    say("### By staff size")
    for label, t in sorted(grouped(results, lambda r: r["meta"].get("staff size", "?")).items()):
        say(t.line(label))
    say("")
    say("### By number of pages")
    def page_band(r):
        p = pages_of(r["pdf"])
        return "?" if p is None else "1 page" if p == 1 else "2 pages" if p == 2 else "3 to 4 pages" if p <= 4 else "5 or more pages"
    for label, t in sorted(grouped(results, page_band).items()):
        say(t.line(label))
    say("")
    say("### Score features (each file counts under every feature it has)")
    features = defaultdict(Tally)
    without = defaultdict(Tally)
    names = {f for r in results for f in r["meta"].get("features", "").split(", ") if f and f != "none"}
    for r in results:
        have = set(r["meta"].get("features", "").split(", "))
        for f in names:
            (features if f in have else without)[f].add(r)
    for f in sorted(names):
        say(f"- {f}: with {pct(features[f].exact, features[f].denominator)} ({features[f].files} files), "
            f"without {pct(without[f].exact, without[f].denominator)} ({without[f].files} files).")
    say("")
    say("### Structural mismatches (completed files with at least one)")
    kinds = Counter()
    for r in done:
        found = set()
        for m in r["structure"]["mismatches"]:
            for kind, pattern in STRUCTURE_PATTERNS:
                if pattern.search(m):
                    found.add(kind)
                    break
        kinds.update(found)
    for kind, _ in STRUCTURE_PATTERNS:
        say(f"- {kind}: {kinds[kind]} of {len(done)} files.")
    say("")
    timed = [(r["seconds"], pages_of(r["pdf"])) for r in done if r.get("seconds") and pages_of(r["pdf"])]
    if timed:
        per_page = sorted(s / p for s, p in timed)
        say("### Time")
        say(f"- {len(timed)} timed files, {sum(p for _, p in timed)} pages. Seconds per page: median "
            f"{statistics.median(per_page):.0f}, fastest {per_page[0]:.0f}, slowest {per_page[-1]:.0f}. "
            f"Seconds per file: median {statistics.median(s for s, _ in timed):.0f}.")
        say("")


def head_to_head(named, out):
    say = out.append
    names = list(named)
    say("## Head to head")
    say("")
    by_pair = [{(r["id"], r["job"]): r for r in named[n]} for n in names]
    common = set.intersection(*(set(b) for b in by_pair))
    say(f"- {len(common)} pairs scored by all of {', '.join(names)}.")
    for i, a in enumerate(names):
        for j in range(i + 1, len(names)):
            b = names[j]
            wins = Counter()
            for key in common:
                x, y = file_accuracy(by_pair[i][key]), file_accuracy(by_pair[j][key])
                wins[a if x > y + 0.05 else b if y > x + 0.05 else "within 5 points"] += 1
            say(f"- {a} against {b}: " + "; ".join(f"{k} {v}" for k, v in wins.most_common()) + ".")
    best = Tally()
    for key in common:
        best.add(max((b[key] for b in by_pair), key=file_accuracy))
    say(f"- Taking the better output for each file would give {pct(best.exact, best.denominator)}.")
    say("")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+", help="NAME=path/to/results.json")
    ap.add_argument("--out")
    args = ap.parse_args()
    named = {}
    for item in args.results:
        name, path = item.split("=", 1)
        named[name] = json.loads(Path(path).read_text(encoding="utf-8"))["results"]
    out = ["# Baseline analysis", ""]
    for name, results in named.items():
        analyse(name, results, out)
    if len(named) > 1:
        head_to_head(named, out)
    text = "\n".join(out) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
