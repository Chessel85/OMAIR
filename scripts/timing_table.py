"""Seconds a page for a timing run, with each file's staves a page (Stage 2.10, OP-3).

For each pair of a timing run made by `omr evaluate --workers 1 --cpu-only`,
the seconds the recogniser took (from the run's log), the pages of its PDF and
the staves on each page, counted from the vector PDF the pair was rendered
from (the raster pair's metadata names it) so that the count does not depend
on the reading being timed. A file's seconds are spread over its pages in
proportion to their staves, as the reading of a page grows with its staves.

usage: python scripts/timing_table.py SET_ROOT LOG [LOG ...]

Each LOG is an `omr evaluate` log over SET_ROOT (or a raster version of it);
the table has one column of seconds a page for each.
"""

import re
import sys
from pathlib import Path

LINE = re.compile(r"\d+ of \d+: (\S+) (\S+): .*?, ([\d.]+) seconds\.$")


def seconds(log):
    out = {}
    for line in Path(log).read_text(encoding="utf-8").splitlines():
        found = LINE.search(line)
        if found:
            out[(found[1], found[2])] = float(found[3])
    return out


def vector_pdf(pdf):
    meta = Path(pdf).parent / "metadata.txt"
    if meta.is_file():
        for line in meta.read_text(encoding="utf-8").splitlines():
            if line.startswith("raster source: "):
                return line.split(": ", 1)[1]
    return pdf


def staves(pdf):
    from omr.pdf.read import read_pdf

    _, layouts = read_pdf(pdf)
    return [len(layout.staves) for layout in layouts]


def main():
    from omr.evaluate import harness

    root, logs = Path(sys.argv[1]), sys.argv[2:]
    timed = [seconds(log) for log in logs]
    print("file | engraver | pages | staves a page | " + " | ".join(f"seconds a page, {Path(l).stem}" for l in logs))
    totals = [[0.0, 0] for _ in logs]
    pages_by_staves = []
    for pair in harness.read_index(root):
        score_id, job, pdf = pair[0], pair[1], pair[2]
        counts = staves(vector_pdf(pdf))
        cells = []
        for k, t in enumerate(timed):
            if (score_id, job) in t:
                s = t[(score_id, job)]
                totals[k][0] += s
                totals[k][1] += len(counts)
                cells.append(f"{s / len(counts):.1f}")
                for n in counts:   # each page's share, by its staves
                    pages_by_staves.append((n, k, s * n / max(1, sum(counts))))
            else:
                cells.append("-")
        print(f"{score_id} | {job} | {len(counts)} | {', '.join(map(str, counts))} | " + " | ".join(cells))
    for k, log in enumerate(logs):
        s, n = totals[k]
        print(f"{Path(log).stem}: {n} pages, {s:.0f} seconds, {s / max(1, n):.1f} seconds a page on average.")
        rows = sorted((n, t) for n, j, t in pages_by_staves if j == k)
        if rows:
            slowest = max(rows, key=lambda r: r[1])
            print(f"  most staves on a page {rows[-1][0]}; slowest page about {slowest[1]:.0f} seconds "
                  f"({slowest[0]} staves); pages over 60 seconds: {sum(1 for _, t in rows if t > 60)}.")
            for low, high in ((1, 4), (5, 8), (9, 12), (13, 99)):
                band = [t for m, t in rows if low <= m <= high]
                if band:
                    print(f"  {low} to {high} staves: {len(band)} pages, about {sum(band) / len(band):.1f} seconds a page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
