"""Find LilyPond pairs whose PDF does not show the music of their ground truth.

The LilyPond pairs are made by musicxml2ly and LilyPond from the reference
MusicXML (corpus-sampling.md). Where musicxml2ly loses track of time in a bar
it warns "Negative skip", and the notes it writes after that may be moved or
lost. This script converts each reference again and runs the export's music
check (src/omr/corpus/lilypond_check.py): LilyPond's MIDI of the same music,
compared with the reference bar by bar. The warning count is listed beside it;
it points at the faulty pairs but is not proof.

With a results.json of `omr evaluate` it adds the reader's note accuracy on the
LilyPond pair and its best accuracy on another engraving of the same score.

With --reject, each pair that fails the check is made a failure, as the export
would have made it: failure.txt is written in its folder, its metadata.txt is
removed, and its line in the set's index.txt and in the index.txt of each
raster version of the set (generated/raster/SET-*) becomes a failure line.

usage: python scripts/check_lilypond_pairs.py OUT.txt [IDS...] [--results RESULTS.json]
                                              [--set development] [--workers N] [--reject]
"""

import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from omr import paths
from omr.corpus import engravers


def check_pair(score_id, reference):
    """(score id, Negative skip warnings, share of notes found, failure reason or None)."""
    lily, converter = engravers.lilypond_paths()
    with tempfile.TemporaryDirectory() as tmp:
        ly = Path(tmp) / "score.ly"
        try:
            made = subprocess.run([*converter, "-o", str(ly), str(reference)],
                                  capture_output=True, text=True, errors="replace", timeout=300)
        except subprocess.TimeoutExpired:
            return score_id, None, None, "musicxml2ly timed out after 300 seconds"
        warnings = made.stderr.count("Negative skip")
        try:
            share = engravers.lilypond_music_share(reference, ly, lily)
        except engravers.ExportError as error:
            return score_id, warnings, None, str(error)
    return score_id, warnings, share, engravers.lilypond_music_failure(share)


def accuracies(results_path):
    """{score id: {job: note accuracy}} from a results.json."""
    data = json.loads(Path(results_path).read_text(encoding="utf-8"))
    out = {}
    for r in (data if isinstance(data, list) else data["results"]):
        if "notes" not in r:
            continue
        n = r["notes"]
        whole = n["truth"] + n["extra"] + n["clef errors"]
        out.setdefault(r["id"], {})[r["job"]] = n["exact"] / whole if whole else 1.0
    return out


def reject(root, set_name, failed):
    """Make each failed pair a failure in its folder and in every index of the set."""
    for sid, reason in failed.items():
        job = root / "generated" / set_name / sid / "lilypond"
        (job / "failure.txt").write_text(reason + "\n", encoding="utf-8")
        (job / "metadata.txt").unlink(missing_ok=True)
    indexes = [root / "generated" / set_name / "index.txt"]
    indexes += sorted((root / "generated" / "raster").glob(f"{set_name}-*/index.txt"))
    for index in indexes:
        lines = index.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            fields = line.split(" | ")
            if fields[0] == "pair" and fields[2] == "lilypond" and fields[1] in failed:
                lines[i] = " | ".join(["failure", fields[1], "lilypond", "", "", failed[fields[1]]])
        index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return indexes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out")
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--results")
    parser.add_argument("--set", default="development")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--reject", action="store_true")
    args = parser.parse_args()
    root = paths.require_corpus_dir()
    index = root / "generated" / args.set / "index.txt"
    pairs = []
    for line in index.read_text(encoding="utf-8").splitlines():
        fields = line.split(" | ")
        if fields[0] == "pair" and fields[2] == "lilypond" and (not args.ids or fields[1] in args.ids):
            pairs.append((fields[1], fields[5]))
    found = {}
    with ProcessPoolExecutor(args.workers) as pool:
        for future in as_completed([pool.submit(check_pair, *p) for p in pairs]):
            sid, warnings, share, reason = future.result()
            found[sid] = (warnings, share, reason)
    acc = accuracies(args.results) if args.results else {}
    rows = []
    for sid, (warnings, share, reason) in found.items():
        jobs = acc.get(sid, {})
        others = [v for j, v in jobs.items() if j != "lilypond"]
        rows.append((sid, warnings, share, reason, jobs.get("lilypond"), max(others) if others else None))
    rows.sort(key=lambda r: (r[3] is None, r[2] if r[2] is not None else -1, r[0]))
    fmt = lambda v: "none" if v is None else f"{100 * v:.1f}"
    lines = ["# score id | kept or rejected | notes found within their bar | Negative skip warnings | "
             "reader's LilyPond accuracy | best other engraving | reason"]
    lines += [f"{sid} | {'rejected' if reason else 'kept'} | {fmt(share)} | "
              f"{'none' if w is None else w} | {fmt(lily)} | {fmt(best)} | {reason or ''}"
              for sid, w, share, reason, lily, best in rows]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    failed = {r[0]: r[3] for r in rows if r[3]}
    print(f"{len(rows)} LilyPond pairs, {len(failed)} fail the music check. Written to {args.out}.")
    if args.reject and failed:
        for index in reject(root, args.set, failed):
            print(f"Made failures in {index}.")


if __name__ == "__main__":
    sys.exit(main())
