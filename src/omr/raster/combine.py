"""Engine 1 and Engine 2 combined, staff bar by staff bar (Phase 2, Stage 2.7).

Engine 1 (the symbol detector path) and Engine 2 (the sequence reader) read
the same bars: Engine 2's notes are placed in Engine 1's bars
(omr.raster.sequence_reading). Where the two read a staff bar's notes the
same way, Engine 1's reading stands (it carries the markings). Where they
differ, there are up to three readings: Engine 1's, Engine 2's, and, when
both have the same number of notes at every onset, Engine 1's notes with
Engine 2's durations (mixed()). Each is judged by musical rules and the one
with the fewest faults is kept; on a tie, the first in the order of
preference. Every staff bar where they differ is reported, so the flag
rules can mark it. A staff bar one engine wrote nothing in (no notes, no
rests) takes the other's reading unjudged, and where Engine 2 is a bar out
of step with Engine 1 (out_of_step()) Engine 1's stands; Engine 2's notes, when kept,
carry Engine 1's markings (with_marks()).

The rules (each counts faults; `weights` says how much each counts):
- fullness: voice by voice, with tuplet ratios already in the durations, a
  gap or overlap between one onset and the next, a voice running past the
  bar, and the bar's music stopping short of the time signature.
- key: notes whose alteration is not the key's for their letter (weight 0:
  on the development set the right reading had more such notes more often).
- range: notes more than RANGE staff steps outside the staff.
- doubt: Engine 1 noted a doubt or broke a rule in the bar (its flags).
"""

import collections
from dataclasses import dataclass, field, replace
from fractions import Fraction

from omr.evaluate import events

RANGE = 12          # staff steps beyond the outer line: six ledger lines
WEIGHTS = {"fullness": 1.0, "key": 0, "range": 1.0, "doubt": 1.0}   # key: see the progress log


@dataclass
class StaffBar:
    """Both readings of one staff bar and the faults found in each."""
    where: tuple                     # (part, staff, bar)
    first: tuple                     # (notes, rests) by Engine 1
    second: tuple                    # (notes, rests) by Engine 2
    faults: tuple = ()               # ({rule: count} for Engine 1, for Engine 2)
    chosen: object = 1               # 1, 2 or "mixed"


@dataclass
class Combined:
    notes: list
    rests: list
    disagree: list = field(default_factory=list)    # StaffBar, where the engines differ


def _by_staff_bar(items):
    out = collections.defaultdict(list)
    for item in items:
        out[(item.part, item.staff, item.bar)].append(item)
    return out


def _signature(notes, rests):
    """What must match for the engines to agree: the notes. Rests are left
    out: the engines write a whole-bar rest differently, and fullness judges
    them where the notes differ."""
    return collections.Counter(n.key for n in notes)


def bar_length(time):
    """Quarter notes in a bar of a time signature such as "6/8", or None."""
    try:
        top, bottom = time.split("/")
        return sum(Fraction(t) for t in top.split("+")) * 4 / Fraction(bottom)
    except (AttributeError, ValueError, ZeroDivisionError):
        return None


def fullness_faults(notes, rests, length):
    """Gaps, overlaps and overruns, voice by voice, and the bar stopping short.
    A bar with nothing in it stops short too: a staff bar the other engine has
    notes in is not right empty (the reference writes rests there)."""
    voices = collections.defaultdict(dict)    # voice -> {onset: longest duration there}
    for item in list(notes) + list(rests):
        if getattr(item, "grace", 0):
            continue
        d = length if item.duration == events.WHOLE_BAR else item.duration
        if d is None:
            continue
        starts = voices[item.voice]
        starts[item.onset] = max(starts.get(item.onset, Fraction(0)), d)
    faults = 0
    ends = []
    for starts in voices.values():
        at = None
        for onset in sorted(starts):
            if at is not None and onset != at:
                faults += 1
            at = onset + starts[onset]
        ends.append(at)
        if length is not None and at > length:
            faults += 1
    if not ends or length is not None and max(ends) < length:
        faults += 1
    return faults


def key_faults(notes, fifths):
    return sum(1 for n in notes if n.pitch.alter != events.key_alter(fifths, n.pitch.step))


def range_faults(notes, bottom):
    if bottom is None:
        return 0
    out = 0
    for n in notes:
        d = events.STEPS.index(n.pitch.step) + 7 * n.pitch.octave
        if d < bottom - RANGE or d > bottom + 8 + RANGE:
            out += 1
    return out


def _clef_bottoms(score):
    """A function (part, staff, bar) -> bottom line of the clef in force at the bar's start."""
    clefs = collections.defaultdict(list)
    for m in sorted((m for m in score.structure if m.kind == "clef"), key=lambda m: (m.bar, m.onset)):
        clefs[(m.part, m.staff)].append((m.bar, events.clef_bottom(m.value)))

    def bottom(part, staff, bar):
        found = None
        for b, value in clefs.get((part, staff), []):
            if b > bar:
                break
            found = value
        return found
    return bottom


def faults(notes, rests, where, signatures, bottom_of, doubted):
    part, staff, bar = where
    return {"fullness": fullness_faults(notes, rests, bar_length(signatures.time(part, bar))),
            "key": key_faults(notes, signatures.key(part, bar)),
            "range": range_faults(notes, bottom_of(part, staff, bar)),
            "doubt": int(where in doubted)}


def penalty(found, weights=WEIGHTS):
    return sum(weights.get(rule, 0) * n for rule, n in found.items())


def mixed(one, two):
    """Engine 1's notes with Engine 2's durations, and Engine 2's rests, when
    both have the same number of notes at every onset (paired at each onset
    from the lowest pitch up); else None. Engine 1 reads pitches and onsets
    better, Engine 2 durations (progress log, Stage 2.7)."""
    (n1, _), (n2, r2) = one, two
    at1, at2 = collections.defaultdict(list), collections.defaultdict(list)
    for n in n1:
        at1[(n.onset, n.grace)].append(n)
    for n in n2:
        at2[(n.onset, n.grace)].append(n)
    if {k: len(v) for k, v in at1.items()} != {k: len(v) for k, v in at2.items()}:
        return None
    notes = []
    for k, group in at1.items():
        order = lambda n: n.pitch.sounding()
        for a, b in zip(sorted(group, key=order), sorted(at2[k], key=order)):
            notes.append(replace(a, duration=b.duration, value=b.value))
    return notes, list(r2)


def _pairs(first, second):
    """Engine 1's notes paired with Engine 2's at one onset: the same pitch
    first, then the rest from the lowest up."""
    order = lambda n: n.pitch.sounding()
    left, pairs = sorted(first, key=order), []
    rest = []
    for b in sorted(second, key=order):
        same = next((a for a in left if a.pitch == b.pitch), None)
        if same is None:
            rest.append(b)
        else:
            left.remove(same)
            pairs.append((same, b))
    return pairs + list(zip(left, rest))


def with_marks(first, second):
    """Engine 2's notes `second` carrying the markings Engine 2 does not read
    (articulations, ornaments, arpeggios, slurs, lyrics, fingering) from
    Engine 1's notes `first` of the same staff bar: onset by onset, or in
    order of onset when both have as many onsets (Engine 2 placed them
    differently)."""
    at1, at2 = collections.defaultdict(list), collections.defaultdict(list)
    for n in first:
        at1[(n.grace, n.onset)].append(n)
    for n in second:
        at2[(n.grace, n.onset)].append(n)
    if len(at1) == len(at2):
        groups = zip(sorted(at1), sorted(at2))
    else:
        groups = ((k, k) for k in at2 if k in at1)
    carried = {}
    for k1, k2 in groups:
        for a, b in _pairs(at1[k1], at2[k2]):
            carried[id(b)] = replace(b, marks=b.marks | a.marks, slurs=b.slurs or a.slurs,
                                     lyrics=b.lyrics or a.lyrics, syllables=b.syllables or a.syllables,
                                     fingering=b.fingering or a.fingering)
    return [carried.get(id(n), n) for n in second]


def chords_differ(one, two):
    """Both readings have notes at the same onsets but not as many at each:
    a chord read with a note more or less. Engine 2 is right about three
    times as often as Engine 1 there (progress log, Stage 2.7)."""
    on1 = collections.Counter(n.onset for n in one[0] if not n.grace)
    on2 = collections.Counter(n.onset for n in two[0] if not n.grace)
    return set(on1) == set(on2) and on1 != on2


def out_of_step(first_notes, two_notes):
    """Staff bars where Engine 2's notes are a bar out of step with Engine 1's
    (Engine 2 read a barline more or fewer): two bars in a row, both
    differing from Engine 1's, each with Engine 2's notes the same as Engine
    1's in the bar before (or both the bar after); the run and a bar either
    side of it. Both arguments map (part, staff, bar) to notes."""
    sig1 = {k: _signature(v, []) for k, v in first_notes.items()}
    sig2 = {k: _signature(v, []) for k, v in two_notes.items() if v}

    def shifted(p, s, b, d):
        sig = sig2.get((p, s, b))
        return sig is not None and sig != sig1.get((p, s, b)) and sig == sig1.get((p, s, b + d))

    found = set()
    for p, s, b in sig2:
        for d in (-1, 1):
            if shifted(p, s, b, d) and shifted(p, s, b + 1, d):
                found |= {(p, s, b + k) for k in range(-1, 3)}
    return found


def combine(score, second_notes, second_rests, doubts=(), weights=WEIGHTS, read_where=None,
            prefer=("mixed", 1, 2), chords=(2, 1)):
    """Engine 1's `score` (an events.Score) with Engine 2's notes and rests,
    or Engine 1's notes with Engine 2's durations (mixed()), chosen in the
    staff bars where that reading has fewer faults; on a tie, the first of
    `prefer`, or of `chords` where chords_differ() (None: `prefer` there
    too). `doubts` are Engine 1's flags (anything with part, staff and
    bar). `read_where` is the set of (part, staff, bar) Engine 2 read; by
    default every staff bar either engine has music in. Under a clef with
    no pitch (percussion, tablature), Engine 1's reading stands: Engine 2
    was not trained on them."""
    first_notes, first_rests = _by_staff_bar(score.notes), _by_staff_bar(score.rests)
    two_notes, two_rests = _by_staff_bar(second_notes), _by_staff_bar(second_rests)
    if read_where is None:
        read_where = set(first_notes) | set(first_rests) | set(two_notes) | set(two_rests)
    signatures = events.SignaturesInForce(score)
    bottom_of = _clef_bottoms(score)
    with_clef = {(m.part, m.staff) for m in score.structure if m.kind == "clef"}
    doubted = set()
    for f in doubts:
        if f.staff is None:
            doubted |= {(f.part, s, f.bar) for s in range(1, 3)}
        else:
            doubted.add((f.part, f.staff, f.bar))
    notes = [n for n in score.notes if (n.part, n.staff, n.bar) not in read_where]
    rests = [r for r in score.rests if (r.part, r.staff, r.bar) not in read_where]
    out = Combined(notes, rests)
    misplaced = out_of_step(first_notes, two_notes)
    for where in sorted(read_where):
        one = (first_notes.get(where, []), first_rests.get(where, []))
        two = (two_notes.get(where, []), two_rests.get(where, []))
        chosen = one
        unpitched = where[:2] in with_clef and bottom_of(*where) is None
        unjudged = not (one[0] or one[1]) or not (two[0] or two[1]) or where in misplaced
        if unjudged and not (one[0] or one[1]):
            chosen = two          # an engine that wrote nothing here missed the bar
        elif not unjudged and not unpitched and _signature(*one) != _signature(*two):
            sb = StaffBar(where, one, two)
            readings = {1: one, 2: two}
            both = mixed(one, two)
            if both is not None and _signature(*both) != _signature(*one):
                readings["mixed"] = both
            found = {k: faults(*r, where, signatures, bottom_of, doubted if k == 1 else set())
                     for k, r in readings.items()}
            sb.faults = (found[1], found[2])
            order = chords if chords and chords_differ(one, two) else prefer
            sb.chosen = min((k for k in order if k in readings), key=lambda k: penalty(found[k], weights))
            chosen = readings[sb.chosen]
            if sb.chosen == 2:
                chosen = (with_marks(one[0], two[0]), two[1])
            out.disagree.append(sb)
        out.notes += chosen[0]
        out.rests += chosen[1]
    return out


RULE = "engines disagree"
ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth")
KEPT = {1: "kept Engine 1's reading", 2: "kept Engine 2's reading",
        "mixed": "kept Engine 1's notes with Engine 2's lengths"}


def _ordinal(i):
    return ORDINALS[i] if i < len(ORDINALS) else f"number {i + 1}"


def _length(note):
    """A note's written length in words, such as "a dotted eighth note"."""
    value = note.value.rstrip(".")
    dots = len(note.value) - len(value)
    if not value:
        return f"{float(note.duration):g} quarter notes"
    words = ("double dotted " if dots > 1 else "dotted " if dots else "") + value.replace("16th", "sixteenth")
    return ("an " if words[0] in "aeiou" else "a ") + words + " note"


def _quarters(onset):
    return f"{float(onset):g}"


def _count(n):
    return "no notes" if n == 0 else "1 note" if n == 1 else f"{n} notes"


def describe(one, two):
    """Where two readings of a staff bar first differ, in words, Engine 1's
    reading first, such as "the engines disagree on the third note: Engine 1
    reads F sharp 5, Engine 2 G 5"."""
    a, b = ([n for n in notes if not n.grace] for notes, _ in (one, two))
    if len(a) != len(b):
        return f"the engines disagree on the number of notes: Engine 1 reads {_count(len(a))}, Engine 2 {_count(len(b))}"
    order = lambda n: (n.onset, n.pitch.sounding())
    for i, (x, y) in enumerate(zip(sorted(a, key=order), sorted(b, key=order))):
        if x.pitch != y.pitch:
            return (f"the engines disagree on the {_ordinal(i)} note: Engine 1 reads {x.pitch.words()}, "
                    f"Engine 2 {y.pitch.words()}")
        if x.onset != y.onset:
            return (f"the engines disagree on where the {_ordinal(i)} note ({x.pitch.words()}) starts: Engine 1 reads "
                    f"{_quarters(x.onset)} quarter notes into the bar, Engine 2 {_quarters(y.onset)}")
        if x.duration != y.duration:
            return (f"the engines disagree on the length of the {_ordinal(i)} note ({x.pitch.words()}): "
                    f"Engine 1 reads {_length(x)}, Engine 2 {_length(y)}")
    return "the engines disagree on the grace notes"


def _first_onset(one, two):
    a = collections.Counter(n.key for n in one[0])
    b = collections.Counter(n.key for n in two[0])
    onsets = [k[0] for k in (a - b) + (b - a)]
    return min(onsets) if onsets else None


def disagreement_flags(combined):
    """A doubt (events.Flag, rule RULE) for each staff bar where the engines
    differ, giving Engine 1's reading first, then Engine 2's, and which
    reading was kept."""
    return [events.Flag(sb.where[0], sb.where[1], sb.where[2], RULE,
                        f"{describe(sb.first, sb.second)}; {KEPT[sb.chosen]}", _first_onset(sb.first, sb.second))
            for sb in combined.disagree]
