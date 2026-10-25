"""Check that musicxml2ly gave LilyPond the music of the reference.

musicxml2ly sometimes loses track of time in a bar (it warns "Negative skip")
and moves or drops the notes after it, so the PDF shows other music than the
ground truth (docs/notes/error-triage.md, cause 14). LilyPond writes a MIDI
file from the same score block it prints, and its note starts (time and pitch)
are compared with the reference's, bar by bar: each bar of the reference takes
the time shift that matches most of its notes, so a short bar earlier on does
not count against the bars after it. A pair is kept when at least
MIN_NOTES_IN_BAR of the reference's notes are found.

musicxml2ly's own --midi block is not used: it plays the parts one after
another and unfolds repeats. Chord symbols are silenced (the reference holds
them as text), transpositions are removed (the reference holds written pitch),
and a unison of two voices counts once (MIDI writes it once). Tied
continuations, grace notes and cue notes of the reference are left out.
"""

import collections
import re
import struct
from fractions import Fraction
from pathlib import Path

from omr.evaluate import events

MIN_NOTES_IN_BAR = 0.99
GRID = 96   # times are rounded to 1/96 of a quarter note
MIDI_BLOCK = '\\midi { \\context { \\ChordNames \\remove "Note_performer" } }'


class CheckError(ValueError):
    """The LilyPond file cannot be turned into a MIDI version."""


def midi_version(ly_text):
    """musicxml2ly's output with its score block writing MIDI instead of a page."""
    if ly_text.count("\\layout {}") != 1:
        raise CheckError("the LilyPond file does not have exactly one score block")
    ly_text = re.sub(r"\\transposition\s+[a-g](?:is|es|s)*[',]*", "", ly_text)
    return ly_text.replace("\\layout {}", MIDI_BLOCK)


def _number(data, i):
    """A MIDI variable-length number at i: (value, next index)."""
    value = 0
    while True:
        b = data[i]
        i += 1
        value = (value << 7) | (b & 0x7F)
        if b < 0x80:
            return value, i


def read_midi(path):
    """The distinct (time, pitch) note starts of a MIDI file, all tracks together,
    with time in 1/GRID quarter notes. The percussion channel is left out."""
    data = Path(path).read_bytes()
    if data[:4] != b"MThd":
        raise CheckError("the MIDI file has no header")
    _, tracks, division = struct.unpack(">HHH", data[8:14])
    pos = 8 + struct.unpack(">I", data[4:8])[0]
    notes = set()
    for _ in range(tracks):
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        track = data[pos + 8:pos + 8 + length]
        pos += 8 + length
        i, tick, status = 0, 0, 0
        while i < len(track):
            delta, i = _number(track, i)
            tick += delta
            if track[i] >= 0x80:
                status = track[i]
                i += 1
            if status == 0xFF:
                size, i = _number(track, i + 1)
                i += size
            elif status in (0xF0, 0xF7):
                size, i = _number(track, i)
                i += size
            else:
                kind = status & 0xF0
                size = 1 if kind in (0xC0, 0xD0) else 2
                args = track[i:i + size]
                i += size
                if kind == 0x90 and args[1] > 0 and status & 0x0F != 9:
                    notes.add((round(Fraction(tick, division) * GRID), args[0]))
    return notes


def reference_notes(path):
    """{bar: set of (time, pitch)} for the reference, time as in read_midi."""
    score = events.read(path)
    starts, at = [], Fraction(0)
    for bar in score.bars:
        starts.append(at)
        at += bar.length
    bars = collections.defaultdict(set)
    for n in score.notes:
        if n.grace or n.tie_stop or n.cue or n.bar >= len(starts):
            continue
        bars[n.bar].add((round((starts[n.bar] + n.onset) * GRID), int(n.pitch.sounding())))
    return bars


def notes_in_bar(reference_bars, midi_notes):
    """(reference notes found in the MIDI within their bar, reference notes)."""
    by_pitch = collections.defaultdict(list)
    for t, p in midi_notes:
        by_pitch[p].append(t)
    found = total = 0
    for notes in reference_bars.values():
        total += len(notes)
        shifts = collections.Counter(mt - t for t, p in notes for mt in by_pitch[p])
        found += max((sum((t + shift, p) in midi_notes for t, p in notes)
                      for shift, _ in shifts.most_common(5)), default=0)
    return found, total


def share_found(reference, midi):
    """The share of the reference's notes found in the MIDI within their bar."""
    found, total = notes_in_bar(reference_notes(reference), read_midi(midi))
    return found / total if total else 1.0
