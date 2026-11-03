"""Time signatures on page images checked against the notes (Stage 2.9).

The detector can miss a time signature digit or read it as another: an old
piece's 2/1 whose 1 sits inside the treble clef reads as 2 alone, so the
incipit's cut time stays in force, or as 2/4 (pdmx-C1P12SpiRUyB, MuseScore 3
variant); a 5 can read as an 8. The notes are then fitted to the wrong bar
length, and nearly every bar is over- or underfull from there on.

So on page images the notes are read, and each time signature whose stretch
of bars (to the next one) has many bars that do not fill (notation.unfilled_bars)
is tried with other values, the notes read again each time: the values read
in any part at that bar, each numerator read there over the usual beat types,
and the beat types read there with the bar length the notes most often reach.
A value goes to every part at that bar, and is kept only if it at least
halves the unfilled bars there. Reading the notes again takes well under a
second a score; the tries are capped.
"""

import collections
import copy
from fractions import Fraction

from omr.evaluate import events
from omr.pdf import notation

BEAT_TYPES = (1, 2, 4, 8, 16)
SHARE = 0.25     # a stretch is tried when this share of its part bars or more do not fill
MIN_BARS = 2     # and at least this many; a value kept must save at least this many
MAX_TRIES = 12   # readings of the notes a score, at most, besides the first


def read_notes(score, ordered, pages, layouts=()):
    """notation.read_notes, with the time signatures checked against the
    notes (above). `score` is filled in place, as notation.read_notes does."""
    base = copy.deepcopy(score)
    notation.read_notes(score, ordered, pages, layouts)
    points = sorted({e.bar for e in base.structure if e.kind == "time"})
    if not points:
        return score
    current, tries = score, 0
    for i, k in enumerate(points):
        end = points[i + 1] if i + 1 < len(points) else None
        before = _unfilled(current, k, end)
        first, last = _span(current, k, end)
        size = len(current.parts) * (last - first)
        if len(before) < MIN_BARS or len(before) < SHARE * size:
            continue
        best = None
        for value in _candidates(base, current, k, end):
            if tries >= MAX_TRIES:
                break
            tries += 1
            trial = _with_time(base, k, value)
            read = copy.deepcopy(trial)
            notation.read_notes(read, ordered, pages, layouts)
            left = _unfilled(read, k, end)
            if best is None or len(left) < len(best[2]):
                best = (trial, read, left)
        if best is not None and 2 * len(best[2]) <= len(before) and len(before) - len(best[2]) >= MIN_BARS:
            base, current = best[0], best[1]
    if current is not score:
        vars(score).update(vars(current))
    return score


def _after_joins(score, bar):
    """The index after notation.join_split_bars of the page layout's bar `bar`."""
    return bar - sum(1 for j in score.joined if j < bar)


def _span(score, k, end):
    """(first, last + 1) of the score's bars from the page layout's bar k up
    to `end` (None: to the last)."""
    return _after_joins(score, k), _after_joins(score, end) if end is not None else len(score.bars)


def _unfilled(score, k, end):
    """{(part, bar)} not filled in the page layout's bars k up to `end`."""
    first, last = _span(score, k, end)
    return {(f.part, f.bar) for f in notation.unfilled_bars(score) if first <= f.bar < last}


def _candidates(base, read, k, end):
    """Time signature values to try at the page layout's bar k: those read
    there, most often first; each numerator over the usual beat types; each
    beat type read there with the bar length the notes most often reach."""
    values = collections.Counter(e.value for e in base.structure if e.kind == "time" and e.bar == k)
    out = [v for v, _ in values.most_common()]
    numbers = [v.split("/") for v in out]
    out += [f"{n}/{d}" for n, _ in numbers for d in BEAT_TYPES]
    length = _commonest_reach(read, k, end)
    if length:
        for _, d in numbers:
            beats = length * int(d) / 4
            if beats.denominator == 1:
                out.append(f"{beats.numerator}/{d}")
    seen = set()
    return [v for v in out if not (v in seen or seen.add(v))]


def _commonest_reach(score, k, end):
    """The length in quarter notes the notes and rests of a part's bar most
    often reach over the stretch, or None."""
    first, last = _span(score, k, end)
    reach = collections.defaultdict(Fraction)
    for n in score.notes:
        if not n.grace and first <= n.bar < last:
            key = (n.part, n.bar)
            reach[key] = max(reach[key], n.onset + n.duration)
    for r in score.rests:
        if first <= r.bar < last and r.duration != events.WHOLE_BAR:
            key = (r.part, r.bar)
            reach[key] = max(reach[key], r.onset + r.duration)
    counts = collections.Counter(v for v in reach.values() if v > 0)
    return counts.most_common(1)[0][0] if counts else None


def _with_time(score, k, value):
    """A copy of the score before its notes are read, with `value` the time
    signature of every part at the page layout's bar k."""
    out = copy.deepcopy(score)
    structure, placed = [], False
    for e in out.structure:
        if e.kind == "time" and e.bar == k:
            if not placed:
                structure += [events.Marking("time", value, p, None, k, Fraction(0)) for p in range(len(out.parts))]
                placed = True
            continue
        structure.append(e)
    out.structure = structure
    return out
