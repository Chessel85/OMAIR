"""Check that a LilyPond pair's PDF shows the music of its ground truth.

The LilyPond pairs are made by musicxml2ly and LilyPond from the reference
MusicXML (corpus-sampling.md). musicxml2ly sometimes loses or moves music
("Negative skip" warnings), and then the PDF does not show the ground truth.
This script converts the reference again, with a MIDI block, and compares
LilyPond's MIDI with the reference: the share of the reference's notes (pitch
and onset, grace notes and tied continuations left out) that the MIDI has at the same time. LilyPond
writes each staff as a MIDI track starting at its own offset, so each track is
compared with the reference part it fits best, at the offset that fits best.
A low share means the pair is faulty, not the reader.

It writes one line per pair: score id, share, reference notes, MIDI notes, and
musicxml2ly's warning count.

usage: python scripts/check_lilypond_pairs.py OUT.txt [IDS...] [--set development] [--workers N]
"""

import argparse
import collections
import subprocess
import sys
import tempfile
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path

from omr import paths
from omr.corpus import engravers


def part_onsets(score):
    """For each part, a Counter of (MIDI pitch, onset in quarters) for every
    sounding note."""
    out = []
    for part in score.parts:
        found = collections.Counter()
        for n in part.flatten().notes:
            if n.duration.isGrace:
                continue
            for one in (n.notes if n.isChord else [n]):
                tie = one.tie if one.tie is not None else n.tie
                if tie is not None and tie.type in ("stop", "continue"):
                    continue   # MIDI sounds a tied note once
                found[(one.pitch.midi, Fraction(n.offset).limit_denominator(96))] += 1
        out.append(found)
    return out


def track_onsets(path):
    """For each MIDI track with notes, a Counter of (pitch, onset in quarters)."""
    from music21 import midi

    mf = midi.MidiFile()
    mf.open(str(path))
    mf.read()
    mf.close()
    out = []
    for track in mf.tracks:
        tick, found = 0, collections.Counter()
        for ev in track.events:
            if ev.isDeltaTime():
                tick += ev.time
            elif ev.isNoteOn() and ev.velocity > 0:
                found[(ev.pitch, Fraction(tick, mf.ticksPerQuarterNote).limit_denominator(96))] += 1
        if found:
            out.append(found)
    return out


def best_overlap(track, part):
    """Notes of `part` found in `track` at the single shift that finds most."""
    shifts = collections.Counter()
    by_pitch = collections.defaultdict(list)
    for (pitch, onset) in part:
        by_pitch[pitch].append(onset)
    for (pitch, onset) in track:
        for o in by_pitch.get(pitch, ())[:200]:
            shifts[onset - o] += 1
    best = 0
    for shift, _ in shifts.most_common(5):
        moved = collections.Counter({(p, o + shift): n for (p, o), n in part.items()})
        best = max(best, sum((moved & track).values()))
    return best


def check(score_id, reference):
    try:
        return _check(score_id, reference)
    except Exception as error:   # one file's failure is reported, not fatal
        return score_id, None, 0, 0, f"failed: {type(error).__name__}: {error}"[:200]


def _check(score_id, reference):
    import music21

    warnings.simplefilter("ignore")
    lily, converter = engravers.lilypond_paths()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ly = tmp / "score.ly"
        made = subprocess.run([*converter, "-m", "-o", str(ly), str(reference)],
                              capture_output=True, text=True, timeout=300)
        skips = made.stderr.count("Negative skip") + made.stderr.count("warning")
        subprocess.run([lily, "-o", str(tmp / "score"), str(ly)], capture_output=True, timeout=300)
        midi = tmp / "score.mid"
        if not midi.is_file():
            midi = tmp / "score.midi"
        if not midi.is_file():
            return score_id, None, 0, 0, skips
        parts = part_onsets(music21.converter.parse(str(reference)).toSoundingPitch())
        tracks = track_onsets(midi)
    total = sum(sum(p.values()) for p in parts)
    # each track counts against the part it fits best (a part of two staves
    # is two tracks)
    found = sum(max((best_overlap(t, part) for part in parts), default=0) for t in tracks)
    share = min(found, total) / total if total else None
    return score_id, share, total, sum(sum(t.values()) for t in tracks), skips


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out")
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--set", default="development")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    index = paths.require_corpus_dir() / "generated" / args.set / "index.txt"
    pairs = []
    for line in index.read_text(encoding="utf-8").splitlines():
        fields = line.split(" | ")
        if fields[0] == "pair" and fields[2] == "lilypond" and (not args.ids or fields[1] in args.ids):
            pairs.append((fields[1], fields[5]))
    lines = ["# score id | share of reference notes in LilyPond's MIDI | reference notes | MIDI notes | musicxml2ly warnings"]
    with ProcessPoolExecutor(args.workers) as pool:
        futures = [pool.submit(check, *p) for p in pairs]
        for k, future in enumerate(as_completed(futures), 1):
            sid, share, total, got, skips = future.result()
            text = "none" if share is None else f"{share:.3f}"
            lines.append(f"{sid} | {text} | {total} | {got} | {skips}")
            print(f"{k} of {len(pairs)}: {lines[-1]}", flush=True)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
