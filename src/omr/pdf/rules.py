"""The musical rules layer and the confidence flags (Stage 1.5).

The PDF reader notes its own doubts while it reads (score.doubts: onsets
that needed a costly search, tuplets read from the bar's length, staves
whose notes do not line up in time, symbols left over). This module adds
the checks that need the whole score:

1. Bar fullness (ACC-5): each voice fills its bar (notation.unfilled_bars).
2. Key and accidentals: a note spelled in a way the key makes unlikely.
3. Instrument range: a note outside the written range of the part's
   instrument or voice, when the part name says what it is.
4. Ties and slurs: a tie that does not join two notes of the same pitch,
   and a slur that starts and never stops (or the other way round).

`check(score)` gives every flag; `bar_flags` joins them into one flag per
part, staff and bar. Only the rules in FLAG_RULES go into the flag file
(`flag_file`, in the format the evaluation harness reads, docs/notes/
evaluation-spec.md, "Error flagging"); the others (range, key spelling,
slurs) rarely point at a note error, so the confidence report
(omr.confidence_report) lists them as things also worth checking. The
rules, their measured precision and the confidence figures are in
docs/notes/confidence-spec.md.
"""

import collections
import re
from dataclasses import dataclass
from fractions import Fraction

from omr.evaluate import events


@dataclass(frozen=True)
class Flag:
    part: int            # from 0
    staff: int | None    # from 1, or None for the whole part
    bar: int             # from 0, in score order
    rule: str
    reason: str
    onset: Fraction | None = None   # quarter notes from the start of the bar, when known


# ------------------------------------------------------------------ rules


def check(score):
    """Every flag for a score read by omr.pdf.structure.read_pdf with notes:
    the reader's doubts and the rules below."""
    flags = list(score.doubts)
    flags += bar_fullness(score)
    flags += key_spelling(score)
    flags += instrument_range(score)
    flags += ties(score)
    flags += slurs(score)
    return flags


def _beats(length):
    return f"{float(length):g} quarter note{'' if length == 1 else 's'}"


def bar_fullness(score):
    from omr.pdf import notation

    out = []
    for f in notation.unfilled_bars(score):
        how = "runs past the end of the bar" if f.length > f.expected else "stops short of the end of the bar"
        out.append(Flag(f.part, f.staff, f.bar, "bar fullness",
                        f"voice {f.voice} {how}: it lasts {_beats(f.length)} where the bar holds "
                        f"{_beats(f.expected)}"))
    return out


SHARP_ORDER = "FCGDAEB"


def _key_in_force(score):
    """(part, bar) -> fifths, from the key signatures."""
    keys = collections.defaultdict(list)
    for e in score.structure:
        if e.kind == "key":
            keys[e.part].append((e.bar, int(e.value)))
    for part in keys:
        keys[part].sort()

    def fifths(part, bar):
        value = 0
        for start, f in keys.get(part, ()):
            if start <= bar:
                value = f
        return value
    return fifths


def key_spelling(score):
    """A note spelled far round the circle of fifths from its key: more
    than five fifths beyond the key's seven letters, which leaves room for
    the raised and lowered notes of major and minor keys (a sharp fourth or
    a flat seventh) but not, say, a D sharp in A flat major."""
    fifths_at = _key_in_force(score)
    out = {}
    for n in score.notes:
        fifths = fifths_at(n.part, n.bar)
        # F is -1 and B is 5 on the line of fifths; each sharp adds 7
        position = SHARP_ORDER.index(n.pitch.step) - 1 + 7 * n.pitch.alter
        if position > fifths + 5 + SPELLING_MARGIN or position < fifths - 1 - SPELLING_MARGIN:
            out.setdefault((n.part, n.staff, n.bar), Flag(n.part, n.staff, n.bar, "key and accidentals",
                                                          f"{n.pitch.words()} is unlikely in the key", n.onset))
    return list(out.values())


SPELLING_MARGIN = 5


# Written ranges, generous by a step or two, as (lowest, highest) MIDI
# numbers. Transposing instruments are given in written pitch, as MusicXML
# stores them. The name is matched as a word, case ignored, longest first.
RANGES = {
    "soprano": (57, 84), "mezzo": (55, 81), "alto": (52, 79), "contralto": (52, 79),
    "tenor": (45, 72), "baritone": (40, 69), "bass": (33, 67),
    "violin": (55, 105), "viola": (48, 93), "cello": (36, 84), "violoncello": (36, 84),
    "double bass": (28, 72), "contrabass": (28, 72),
    "flute": (59, 98), "piccolo": (62, 98), "oboe": (57, 93), "clarinet": (52, 96),
    "bassoon": (33, 77), "saxophone": (56, 93), "sax": (56, 93),
    "horn": (40, 82), "trumpet": (52, 86), "trombone": (33, 77), "tuba": (26, 67),
    "recorder": (58, 100), "guitar": (38, 88),
}
_RANGE_NAMES = sorted(RANGES, key=len, reverse=True)


def range_of(name):
    """The written range for a part name, or None when the name does not say."""
    words = name.lower()
    for key in _RANGE_NAMES:
        if re.search(rf"\b{key}", words):
            # a bass clarinet, alto saxophone and the like: the instrument decides
            rest = words.replace(key, " ")
            for other in _RANGE_NAMES:
                if other != key and other not in key and re.search(rf"\b{other}", rest) and other not in (
                        "soprano", "mezzo", "alto", "contralto", "tenor", "baritone", "bass"):
                    return RANGES[other]
            return RANGES[key]
    return None


def instrument_range(score):
    out = {}
    ranges = [range_of(p.name) for p in score.parts]
    for n in score.notes:
        if n.part >= len(ranges) or ranges[n.part] is None or n.grace:
            continue
        low, high = ranges[n.part]
        pitch = n.pitch.sounding()
        if pitch < low or pitch > high:
            where = "below" if pitch < low else "above"
            out.setdefault((n.part, n.staff, n.bar), Flag(
                n.part, n.staff, n.bar, "instrument range",
                f"{n.pitch.words()} is {where} the range of {score.parts[n.part].name}", n.onset))
    return list(out.values())


def ties(score):
    """A tie start with no note of the same pitch starting where it ends on
    the staff, and a tie stop with no such note ending where it starts."""
    by_staff = collections.defaultdict(list)
    for n in score.notes:
        if not n.grace:
            by_staff[(n.part, n.staff)].append(n)
    out = {}
    for (part, staff), notes in by_staff.items():
        starts = collections.defaultdict(set)   # (bar, onset) -> pitches
        ends = collections.defaultdict(set)
        for n in notes:
            starts[(n.bar, n.onset)].add(n.pitch.sounding())
        for n in notes:
            end_bar, end = n.bar, n.onset + n.duration
            ends[(end_bar, end)].add(n.pitch.sounding())
        bar_length = {}
        for n in notes:
            bar_length[n.bar] = max(bar_length.get(n.bar, 0), n.onset + n.duration)
        for n in notes:
            pitch = n.pitch.sounding()
            if n.tie_start:
                end = n.onset + n.duration
                ok = pitch in starts.get((n.bar, end), ()) or (
                    end >= bar_length.get(n.bar, end) and pitch in starts.get((n.bar + 1, Fraction(0)), ()))
                if not ok:
                    out.setdefault((part, staff, n.bar), Flag(part, staff, n.bar, "ties",
                                                              f"a tie from {n.pitch.words()} reaches no note "
                                                              f"of the same pitch", n.onset))
            if n.tie_stop:
                ok = pitch in ends.get((n.bar, n.onset), ()) or (
                    n.onset == 0 and any(pitch in pitches for (bar, t), pitches in ends.items()
                                         if bar == n.bar - 1 and t >= bar_length.get(bar, t)))
                if not ok:
                    out.setdefault((part, staff, n.bar), Flag(part, staff, n.bar, "ties",
                                                              f"a tie to {n.pitch.words()} comes from no note "
                                                              f"of the same pitch", n.onset))
    return list(out.values())


def slurs(score):
    """A slur that starts and never stops in its part, or stops with no start."""
    out = []
    by_part = collections.defaultdict(list)
    for n in score.notes:
        for kind, number in n.slurs:
            by_part[n.part].append((n.bar, n.onset, 0 if kind == "stop" else 1, number, kind, n))
    for part, marks in by_part.items():
        open_slurs = {}
        for bar, onset, _, number, kind, n in sorted(marks, key=lambda m: m[:4]):
            if kind == "start":
                if number in open_slurs:
                    old = open_slurs[number]
                    out.append(Flag(part, old.staff, old.bar, "slurs", "a slur starts and does not stop", old.onset))
                open_slurs[number] = n
            elif number in open_slurs:
                del open_slurs[number]
            else:
                out.append(Flag(part, n.staff, n.bar, "slurs", "a slur stops that did not start", n.onset))
        for n in open_slurs.values():
            out.append(Flag(part, n.staff, n.bar, "slurs", "a slur starts and does not stop", n.onset))
    return out


# ------------------------------------------------------------------ output


@dataclass
class BarFlag:
    part: int
    staff: int | None
    bar: int
    reasons: list        # (rule, reason), in order, no repeats
    confidence: float    # the chance the bar is right as read
    onsets: list         # the onsets the flags give, where they give one


def bar_flags(flags, rules=None):
    """One flag per part, staff and bar, with every reason given there.
    `rules` limits the flags to those rules. The confidence is the chance
    that no rule's flag points at an error (RULE_PRECISION)."""
    joined = {}
    for f in flags:
        if rules is not None and f.rule not in rules:
            continue
        key = (f.part, f.staff, f.bar)
        b = joined.setdefault(key, BarFlag(f.part, f.staff, f.bar, [], 1.0, []))
        if (f.rule, f.reason) not in b.reasons:
            b.reasons.append((f.rule, f.reason))
        if f.onset is not None:
            b.onsets.append(f.onset)
    for b in joined.values():
        right = 1.0
        for rule in {r for r, _ in b.reasons}:
            right *= 1.0 - RULE_PRECISION.get(rule, 0.5)
        b.confidence = round(right, 2)
    return [joined[k] for k in sorted(joined, key=lambda k: (k[2], k[0], k[1] or 0))]


# The rules whose flags go into the flag file (they point at note errors).
FLAG_RULES = {"rhythm", "bar fullness", "staves disagree", "unprinted tuplet", "ties", "stray symbol",
              "hidden staves", "octave sign"}

# The share of each rule's flagged bars that held a note error on the
# exact pairs of the development set (docs/notes/confidence-spec.md).
RULE_PRECISION = {
    "rhythm": 0.64, "bar fullness": 0.58, "staves disagree": 0.49, "unprinted tuplet": 0.26,
    "ties": 0.20, "octave sign": 0.17, "stray symbol": 0.13, "hidden staves": 0.03,
    "slurs": 0.08, "key and accidentals": 0.03, "instrument range": 0.0,
}


def flag_file(flags):
    """The flag file's contents (spec, "Error flagging"), as a dictionary for
    JSON: the flags of FLAG_RULES, one per part, staff and bar."""
    out = []
    for b in bar_flags(flags, FLAG_RULES):
        entry = {"part": b.part + 1, "bar": b.bar + 1}
        if b.staff is not None:
            entry["staff"] = b.staff
        entry["reason"] = "; ".join(reason for _, reason in b.reasons)
        entry["confidence"] = b.confidence
        out.append(entry)
    return {"version": 1, "flags": out}


def as_harness_flags(flags, rules=FLAG_RULES):
    """(part, bar, staff or None) for metrics.compare_scores, as read_flags
    gives them from the flag file."""
    return [(b.part, b.bar, b.staff) for b in bar_flags(flags, rules)]
