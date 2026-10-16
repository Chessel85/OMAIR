"""Stage 1.8 triage: sort each note error into a pattern that points at a cause.

Reads one results.json of `omr evaluate` and classes every note error of the
worst files (by note errors) into patterns:

- wrong staff: a missing note and an extra note with the same bar, beat, pitch
  and value, but on different staves (notes read right, placed on the wrong
  staff or part);
- bar displaced: the same, on the same staff but in a bar up to 8 away;
- bar shifted: onset errors where at least 3 notes of one bar and staff are
  moved by the same amount (the bar's contents start in the wrong place);
- onset other, duration (dot, tuplet, other), pitch (octave, accidental,
  steps), grace note missing or extra, and plain missing and extra notes.

It prints the totals by pattern, by job and for each file, so the files can be
looked at in order of what a fix would recover.

usage: python scripts/triage_errors.py RESULTS.json [--worst N] [--file ID] [--out FILE]
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

STEPS = "CDEFGAB"
BEAT = r"(\d[0-9/.]*(?: and \d+/\d+)?)"
PLACE = re.compile(r"^Bar (\d+) \(page (\d+), system (\d+)\), (.*), beat " + BEAT + "$")
NOTE = re.compile(r"^([A-G])((?: double)?(?: sharp| flat| natural)?) (-?\d+), (.*?)(?:, at beat " + BEAT + ")?$")


def beat(text):
    """'1 and 1/3' or '2.5' as a Fraction."""
    text = text.strip()
    if " and " in text:
        whole, part = text.split(" and ")
        return Fraction(whole) + Fraction(part)
    return Fraction(text)


def place(where):
    m = PLACE.match(where)
    if not m:
        return None
    return dict(bar=int(m.group(1)), page=int(m.group(2)), system=int(m.group(3)),
                staff=m.group(4), beat=beat(m.group(5)))


def note(text):
    m = NOTE.match(text)
    if not m:
        return None
    return dict(step=m.group(1), alter=m.group(2).strip(), octave=int(m.group(3)),
                value=m.group(4), at=beat(m.group(5)) if m.group(5) else None)


def steps_between(a, b):
    return (b["octave"] * 7 + STEPS.index(b["step"])) - (a["octave"] * 7 + STEPS.index(a["step"]))


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    results = data if isinstance(data, list) else data["results"]
    return [r for r in results if "harness error" not in r and "failed" not in r]


def error_count(r):
    n = r["notes"]
    return n["truth"] + n["extra"] + n["clef errors"] - n["exact"]


def classify(errors):
    """Pattern -> count for one file's error list."""
    found = Counter()
    missing, extra = [], []
    onset = defaultdict(list)
    for e in errors:
        kind = e["kind"]
        if kind == "clef error":
            found["clef error"] += 1
            continue
        if kind == "missing note":
            missing.append(e)
            continue
        if kind == "extra note":
            extra.append(e)
            continue
        p, t, o = place(e["where"]), note(e["expected"]), note(e["found"])
        if not (p and t and o):
            found["unparsed " + kind] += 1
            continue
        if "onset" in kind and t["at"] is not None and o["at"] is not None:
            onset[(p["bar"], p["staff"])].append((o["at"] - t["at"], kind))
            continue
        if "pitch" in kind:
            d = steps_between(t, o)
            if d and d % 7 == 0:
                found["pitch: octave"] += 1
            elif d == 0:
                found["pitch: accidental"] += 1
            elif abs(d) <= 2:
                found[f"pitch: {abs(d)} step{'s' if abs(d) > 1 else ''}"] += 1
            else:
                found["pitch: 3 or more steps"] += 1
            if "duration" not in kind:
                continue
        if "duration" in kind:
            tv, ov = t["value"], o["value"]
            if ("dotted" in tv) != ("dotted" in ov):
                found["duration: dot"] += 1
            elif any(w in tv for w in ("triplet", "tuplet")) != any(w in ov for w in ("triplet", "tuplet")):
                found["duration: tuplet"] += 1
            elif "grace" in tv or "grace" in ov:
                found["duration: grace"] += 1
            else:
                found["duration: other"] += 1
    for items in onset.values():
        shifts = Counter(s for s, _ in items)
        shift, n = shifts.most_common(1)[0]
        for s, _ in items:
            found["bar shifted" if (n >= 3 and s == shift) else "onset other"] += 1

    def key(e, with_staff, with_bar):
        p = place(e["where"])
        note_text = e["expected"] if e["kind"] == "missing note" else e["found"]
        if not p:
            return None
        return (p["bar"] if with_bar else None, p["staff"] if with_staff else None, p["beat"], note_text)

    def pair_off(left, right, with_staff, with_bar, match_bar=None):
        """Remove pairs from left and right that agree on the key; return the count."""
        pool = defaultdict(list)
        for e in right:
            k = key(e, with_staff, with_bar)
            if k is not None:
                pool[k].append(e)
        kept, paired = [], 0
        used = set()
        for e in left:
            k = key(e, with_staff, with_bar)
            candidates = [c for c in pool.get(k, []) if id(c) not in used
                          and (match_bar is None or match_bar(e, c))]
            if candidates:
                used.add(id(candidates[0]))
                paired += 1
            else:
                kept.append(e)
        return kept, [e for e in right if id(e) not in used], paired

    def other_staff(a, b):
        return place(a["where"])["staff"] != place(b["where"])["staff"]

    def near_bar(a, b):
        return 0 < abs(place(a["where"])["bar"] - place(b["where"])["bar"]) <= 8

    missing, extra, n = pair_off(missing, extra, with_staff=False, with_bar=True, match_bar=other_staff)
    if n:
        found["wrong staff"] += 2 * n
    missing, extra, n = pair_off(missing, extra, with_staff=True, with_bar=False, match_bar=near_bar)
    if n:
        found["bar displaced"] += 2 * n
    for e in missing:
        found["missing grace note" if "grace" in e["expected"] else "missing note"] += 1
    for e in extra:
        if not place(e["where"]):
            found["extra note in an unpaired bar"] += 1
        else:
            found["extra grace note" if "grace" in e["found"] else "extra note"] += 1
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results")
    parser.add_argument("--worst", type=int, default=100)
    parser.add_argument("--file", help="Only this score id (all its jobs).")
    parser.add_argument("--out")
    args = parser.parse_args()
    results = load(args.results)
    lines = []
    out = lines.append
    if args.file:
        chosen = [r for r in results if r["id"] == args.file]
    else:
        chosen = sorted(results, key=error_count, reverse=True)[: args.worst]
    total = Counter()
    by_job = defaultdict(Counter)
    rows = []
    for r in chosen:
        c = classify(r.get("errors", []))
        total += c
        by_job[r["job"]] += c
        rows.append((r, c))
    all_errors = sum(error_count(r) for r in results)
    chosen_errors = sum(error_count(r) for r in chosen)
    out(f"{len(chosen)} files, {chosen_errors} note errors ({100 * chosen_errors / all_errors:.1f} percent of {all_errors}).")
    out("\nBy pattern")
    for k, n in total.most_common():
        out(f"- {k}: {n}")
    out("\nBy job")
    for job, c in sorted(by_job.items()):
        top = ", ".join(f"{k} {n}" for k, n in c.most_common(4))
        out(f"- {job}: {sum(c.values())}; {top}")
    out("\nBy file")
    for r, c in rows:
        top = ", ".join(f"{k} {n}" for k, n in c.most_common(4))
        out(f"- {r['id']} {r['job']} ({r['meta'].get('texture', '')}): {error_count(r)} errors, "
            f"structure {'right' if r['structure']['correct'] else len(r['structure']['mismatches'])}; {top}")
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
