"""Pair the output's notes with the ground truth's (spec, "Matching").

Step 1 pairs staves, step 2 lines up bars, step 3 counts exact matches (a
multiset intersection, which has only one answer), and step 4 pairs the notes
left over to name each error. Step 4 pairs as many notes as it can, so the
counts have one answer whatever its costs choose.

A misread clef counts as one error (spec, "Clef errors"): where the output
reads a staff with a different clef from the ground truth, its notes there are
moved by the difference and matched again, and the correction is kept only if
it puts at least CLEF_MIN_GAIN notes right.
"""

import collections
import dataclasses
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
from scipy.optimize import linear_sum_assignment

JOIN_PENALTY = 1.5     # extra cost for joining two bars against one, in notes and rests
BAND_MARGIN = 20       # bars either side of the diagonal searched, beyond the difference in counts
PROPERTY_COST = 1      # step 4: cost for each of pitch, onset and duration that differs
ORDER_MARGIN = 0.3     # similarity gained for each moved staff before the parts are called out of order
CLEF_MIN_GAIN = 2      # notes a clef correction must put right to be kept (it costs one error)
STEPS = "CDEFGAB"
CLEF_REFERENCE = {"G": ("G", 4, 2), "F": ("F", 3, 4), "C": ("C", 4, 3)}   # pitch on the clef's line, usual line


@dataclass
class Segment:
    """Ground-truth bars lined up with output bars. Either list may be empty
    (a missing or extra bar), and either may hold two bars (a joined pair).
    `truth_offsets` and `output_offsets` move each bar's onsets into one frame."""

    truth: list
    output: list
    truth_offsets: list
    output_offsets: list


@dataclass
class ErrorPair:
    truth: object
    output: object
    differs: tuple       # some of "pitch", "onset", "duration"
    spelling_only: bool  # the pitch differs only in spelling


@dataclass
class Match:
    staff_map: dict                      # output (part, staff) -> truth (part, staff)
    segments: list
    exact: list = field(default_factory=list)       # (truth note, output note)
    errors: list = field(default_factory=list)      # ErrorPair
    missing: list = field(default_factory=list)     # truth notes
    extra: list = field(default_factory=list)       # output notes
    truth_segment: dict = field(default_factory=dict)   # truth bar -> segment index
    output_segment: dict = field(default_factory=dict)  # output bar -> segment index
    clef_corrections: list = field(default_factory=list)  # ClefCorrection, one error each
    output: object = None            # the output Score matched, with notes moved by clef corrections
    original: dict = field(default_factory=dict)   # id of a moved note -> the note as the output wrote it
    strict_exact: int = 0            # exact matches and extra notes with no clef correction
    strict_extra: int = 0            # (the strict note accuracy diagnostic)

    def as_written(self, note):
        """An output note as the output wrote it, before any clef correction."""
        return self.original.get(id(note), note)


@dataclass
class ClefCorrection:
    """A run of notes on one output staff read with a different clef from the ground truth."""

    truth_staff: tuple       # (part, staff) in the ground truth
    output_staff: tuple      # (part, staff) in the output
    truth_clef: str          # clef values as the reader writes them, such as "G 2 octave -1"
    output_clef: str
    shift: int               # diatonic steps added to the output's notes
    first_bar: int           # ground-truth bars of the first and last notes
    last_bar: int
    output_bar: int          # output bar of the first note
    indices: list = field(default_factory=list)   # positions of its notes in output.notes
    gained: int = 0          # exact matches the correction gained


# Step 1: staves


def map_staves(truth, output):
    """Pair output staves with ground-truth staves: in order if the counts
    agree, otherwise by the overlap of their pitches plus a bonus for the same
    first clef."""
    truth_staves, output_staves = truth.staves(), output.staves()
    if len(truth_staves) == len(output_staves):
        return dict(zip(output_staves, truth_staves))
    if not truth_staves or not output_staves:
        return {}
    similarity = _staff_similarity(truth, output)
    rows, cols = linear_sum_assignment(-similarity)
    return {output_staves[j]: truth_staves[i] for i, j in zip(rows, cols)}


def staves_out_of_order(truth, output):
    """When the staff counts agree, the (output staff, truth staff) pairs that
    pairing by similarity would choose instead of pairing in order, if it is
    clearly better: on average at least ORDER_MARGIN more similar for each
    staff that moves. An empty list means the order looks right."""
    truth_staves, output_staves = truth.staves(), output.staves()
    if len(truth_staves) != len(output_staves) or len(truth_staves) < 2:
        return []
    similarity = _staff_similarity(truth, output)
    rows, cols = linear_sum_assignment(-similarity)
    moved = [(i, j) for i, j in zip(rows, cols) if i != j]
    gain = similarity[rows, cols].sum() - np.trace(similarity)
    if not moved or gain < ORDER_MARGIN * len(moved):
        return []
    return [(output_staves[j], truth_staves[i]) for i, j in sorted(moved, key=lambda m: m[1])]


def _staff_similarity(truth, output):
    """For each (truth staff, output staff): the overlap of their pitch
    histograms, plus 0.2 if their first clefs are the same."""
    truth_staves, output_staves = truth.staves(), output.staves()

    def profile(score):
        pitches = collections.defaultdict(collections.Counter)
        for note in score.notes:
            pitches[(note.part, note.staff)][note.pitch.sounding()] += 1
        clefs = {}
        for event in score.structure:
            if event.kind == "clef":
                clefs.setdefault((event.part, event.staff), event.value)
        return pitches, clefs

    truth_pitches, truth_clefs = profile(truth)
    output_pitches, output_clefs = profile(output)
    similarity = np.zeros((len(truth_staves), len(output_staves)))
    for i, t in enumerate(truth_staves):
        for j, o in enumerate(output_staves):
            a, b = truth_pitches[t], output_pitches[o]
            total = max(sum(a.values()), sum(b.values()))
            overlap = sum((a & b).values()) / total if total else 0.0
            same_clef = 0.2 if truth_clefs.get(t) and truth_clefs.get(t) == output_clefs.get(o) else 0.0
            similarity[i, j] = overlap + same_clef
    return similarity


# Step 2: bars


def _bar_events(score, staff_map=None):
    """For each bar, a list of (part in the truth's numbering, onset, rest of key)."""
    events = [[] for _ in range(max(len(score.bars), max(score.bar_counts, default=0)))]
    for item in list(score.notes) + list(score.rests):
        if staff_map is None:
            part = item.part
        else:
            target = staff_map.get((item.part, item.staff))
            if target is None:
                continue
            part = target[0]
        key = item.key
        if key[0] == "rest":
            events[item.bar].append((part, key[1], ("rest", key[2])))
        else:
            events[item.bar].append((part, key[0], key[1:]))
    return events


def _bar_length(score, bar):
    return score.bars[bar].length if bar < len(score.bars) else Fraction(0)


def _counter(events_by_bar, bars, offsets):
    counter = collections.Counter()
    for bar, offset in zip(bars, offsets):
        for part, onset, rest in events_by_bar[bar]:
            counter[(part, onset + offset, rest)] += 1
    return counter


def _unmatched(a, b):
    """Events in either bar with no exact partner in the other: the note and
    rest errors that pairing these bars would leave."""
    return sum(a.values()) + sum(b.values()) - 2 * sum((a & b).values())


def _offsets(score, bars):
    return [Fraction(0)] + ([_bar_length(score, bars[0])] if len(bars) == 2 else [])


def _summaries(score, events_by_bar):
    """Each bar's events, alone and joined to the next bar, built once."""
    count = len(events_by_bar)
    single = [_counter(events_by_bar, [b], [Fraction(0)]) for b in range(count)]
    joined = [_counter(events_by_bar, [b, b + 1], _offsets(score, [b, b + 1])) for b in range(count - 1)]
    return single, joined


def align_bars(truth, output, staff_map):
    """Line up the bars by dynamic programming (spec, "Step 2: bars").

    The search stays in a band around the diagonal. A path that leaves the band
    needs at least 2 * (band + 1) - |n - m| moves that change the offset (a
    missing, extra or joined bar), each costing at least 1. So if the best path
    in the band costs no more than that, no path outside can beat it; otherwise
    the band is doubled and the search repeated."""
    truth_summaries = _summaries(truth, _bar_events(truth))
    output_summaries = _summaries(output, _bar_events(output, staff_map))
    n, m = len(truth_summaries[0]), len(output_summaries[0])
    band = abs(n - m) + BAND_MARGIN
    while True:
        segments, total = _align(truth, output, truth_summaries, output_summaries, band)
        if band >= max(n, m) or total <= 2 * (band + 1) - abs(n - m):
            return segments
        band *= 2


def _align(truth, output, truth_summaries, output_summaries, band):
    """One banded alignment. Returns (segments, total cost)."""
    (truth_single, truth_joined), (output_single, output_joined) = truth_summaries, output_summaries
    n, m = len(truth_single), len(output_single)
    infinity = float("inf")
    cost = np.full((n + 1, m + 1), infinity)
    step = {}
    cost[0, 0] = 0.0

    def pair_cost(truth_bars, output_bars):
        a = truth_single[truth_bars[0]] if len(truth_bars) == 1 else truth_joined[truth_bars[0]]
        b = output_single[output_bars[0]] if len(output_bars) == 1 else output_joined[output_bars[0]]
        extra = JOIN_PENALTY if len(truth_bars) + len(output_bars) > 2 else 0.0
        return _unmatched(a, b) + extra

    def unpaired_cost(single, bar):
        return max(1, sum(single[bar].values()))

    for i in range(n + 1):
        for j in range(max(0, i - band), min(m, i + band) + 1):
            here = cost[i, j]
            if here == infinity:
                continue
            moves = []
            if i < n and j < m:
                moves.append((1, 1))
            if i + 1 < n and j < m:
                moves.append((2, 1))
            if i < n and j + 1 < m:
                moves.append((1, 2))
            if i < n:
                moves.append((1, 0))
            if j < m:
                moves.append((0, 1))
            for di, dj in moves:
                if abs((i + di) - (j + dj)) > band:
                    continue
                truth_bars = list(range(i, i + di))
                output_bars = list(range(j, j + dj))
                if di and dj:
                    c = pair_cost(truth_bars, output_bars)
                elif di:
                    c = unpaired_cost(truth_single, i)
                else:
                    c = unpaired_cost(output_single, j)
                new, old = here + c, cost[i + di, j + dj]
                # On equal costs a one-to-one pairing wins (joins can reach a cell first).
                if new < old - 1e-12 or (new <= old + 1e-12 and (di, dj) == (1, 1)):
                    cost[i + di, j + dj] = new
                    step[(i + di, j + dj)] = (di, dj)
    segments = []
    i, j = n, m
    while i or j:
        di, dj = step[(i, j)]
        truth_bars = list(range(i - di, i))
        output_bars = list(range(j - dj, j))
        segments.append(Segment(truth_bars, output_bars, _offsets(truth, truth_bars) if truth_bars else [],
                                _offsets(output, output_bars) if output_bars else []))
        i, j = i - di, j - dj
    segments.reverse()
    return segments, float(cost[n, m])


# Steps 3 and 4: notes


def _differences(a, b):
    differs = []
    if a.pitch != b.pitch:
        differs.append("pitch")
    if a.onset_aligned != b.onset_aligned:
        differs.append("onset")
    if a.duration_key != b.duration_key:
        differs.append("duration")
    return tuple(differs)


@dataclass(frozen=True)
class _Placed:
    """A note with its onset moved into its segment's frame."""

    note: object
    onset_aligned: Fraction

    @property
    def pitch(self):
        return self.note.pitch

    @property
    def duration_key(self):
        note = self.note
        return ("grace", note.value, note.grace) if note.grace else note.duration

    @property
    def key(self):
        return (self.onset_aligned, self.pitch, self.duration_key)


def _pair_exact(truth_placed, output_placed, truth_staff_of):
    """Multiset intersection on the key. Among notes with the same key, pair
    those on the same staff and voice first, so staff and voice errors are not invented."""
    by_key_truth = collections.defaultdict(list)
    by_key_output = collections.defaultdict(list)
    for p in truth_placed:
        by_key_truth[p.key].append(p)
    for p in output_placed:
        by_key_output[p.key].append(p)
    exact, left_truth, left_output = [], [], []
    for key in set(by_key_truth) | set(by_key_output):
        ts, os_ = by_key_truth.get(key, []), by_key_output.get(key, [])
        used = set()
        pairs = []
        waiting = list(ts)
        # Round 1: same staff and same voice label; round 2: same staff; round 3: any.
        # Every round pairs only identical keys, so the count of exact matches is
        # the same whatever the rounds choose; they only avoid inventing staff or voice errors.
        tests = (
            lambda t, o: truth_staff_of(o.note) == (t.note.part, t.note.staff) and o.note.voice == t.note.voice,
            lambda t, o: truth_staff_of(o.note) == (t.note.part, t.note.staff),
            lambda t, o: True,
        )
        for test in tests:
            still = []
            for t in waiting:
                choice = next((k for k, o in enumerate(os_) if k not in used and test(t, o)), None)
                if choice is None:
                    still.append(t)
                else:
                    used.add(choice)
                    pairs.append((t, os_[choice]))
            waiting = still
        left_truth += waiting
        exact += pairs
        left_output += [o for k, o in enumerate(os_) if k not in used]
    return exact, left_truth, left_output


def _name_errors(left_truth, left_output):
    """Step 4: pair the leftovers to name each error. As many notes are paired
    as possible, so the counts have one answer (a wrong note is one error, and
    the group has max(leftover truth, leftover output) errors); the costs only
    choose which notes pair."""
    if not left_truth or not left_output:
        return [], left_truth, left_output
    costs = np.array([[PROPERTY_COST * len(_differences(t, o)) for o in left_output] for t in left_truth])
    rows, cols = linear_sum_assignment(costs)   # a rectangular matrix pairs min(n, m) notes
    errors = []
    for i, j in zip(rows, cols):
        differs = _differences(left_truth[i], left_output[j])
        spelling = differs == ("pitch",) and left_truth[i].pitch.sounding() == left_output[j].pitch.sounding()
        errors.append(ErrorPair(left_truth[i].note, left_output[j].note, differs, spelling))
    paired_truth, paired_output = set(rows), set(cols)
    missing = [t for i, t in enumerate(left_truth) if i not in paired_truth]
    extra = [o for j, o in enumerate(left_output) if j not in paired_output]
    return errors, missing, extra


def match(truth, output):
    """Match an output Score against a ground-truth Score, counting each
    misread clef as one error (spec, "Clef errors")."""
    staff_map = map_staves(truth, output)
    strict = _match_notes(truth, output, staff_map)
    strict.strict_exact, strict.strict_extra = len(strict.exact), len(strict.extra)
    kept = _clef_regions(truth, output, strict)
    while kept:
        moved, original = _move(output, kept)
        result = _match_notes(truth, moved, staff_map)
        before = collections.Counter(id(o) for _, o in strict.exact)
        after = collections.Counter(id(original.get(id(o), o)) for _, o in result.exact)
        for c in kept:
            ids = [id(output.notes[i]) for i in c.indices]
            c.gained = sum(after[i] for i in ids) - sum(before[i] for i in ids)
        good = [c for c in kept if c.gained >= CLEF_MIN_GAIN]
        if len(good) == len(kept):
            result.clef_corrections, result.original = kept, original
            result.strict_exact, result.strict_extra = strict.strict_exact, strict.strict_extra
            return result
        kept = good
    return strict


def _match_notes(truth, output, staff_map):
    """Steps 2 to 4 for one output Score."""
    segments = align_bars(truth, output, staff_map)
    result = Match(staff_map, segments, output=output)
    for index, segment in enumerate(segments):
        for bar in segment.truth:
            result.truth_segment[bar] = index
        for bar in segment.output:
            result.output_segment[bar] = index

    def truth_staff_of(note):
        return staff_map.get((note.part, note.staff))

    for _, _, truth_placed, output_placed, unmapped in groups(result, truth.notes, output.notes):
        result.extra += unmapped            # notes on a staff with no ground-truth partner
        exact, left_truth, left_output = _pair_exact(truth_placed, output_placed, truth_staff_of)
        result.exact += [(t.note, o.note) for t, o in exact]
        errors, missing, extra = _name_errors(left_truth, left_output)
        result.errors += errors
        result.missing += [p.note for p in missing]
        result.extra += [p.note for p in extra]
    return result


# Clef errors


def _clef_line(value):
    """The diatonic number (step + 7 * octave) of a clef's bottom line, or None
    for a clef with no pitch (percussion, tablature)."""
    bits = value.split()
    if not bits or bits[0] not in CLEF_REFERENCE:
        return None
    step, octave, usual_line = CLEF_REFERENCE[bits[0]]
    line = int(bits[1]) if len(bits) > 1 and bits[1].isdigit() else usual_line
    change = int(bits[3]) if len(bits) > 3 and bits[2] == "octave" else 0
    return STEPS.index(step) + 7 * (octave + change) - 2 * (line - 1)


def _clefs_by_staff(score):
    clefs = collections.defaultdict(list)
    for event in score.structure:
        if event.kind == "clef":
            clefs[(event.part, event.staff)].append(((event.bar, event.onset), event.value))
    for events in clefs.values():
        events.sort(key=lambda e: e[0])
    return clefs


def _clef_at(events, bar, onset):
    """The clef in effect at a position: the last one at or before it."""
    value = None
    for position, clef in events:
        if position > (bar, onset):
            break
        value = clef
    return value


def _clef_regions(truth, output, strict):
    """The runs of output notes read with a different clef from the ground
    truth at the same place, in the order of each output staff. A run ends at
    a note where the clefs agree, or where either clef changes."""
    truth_clefs, output_clefs = _clefs_by_staff(truth), _clefs_by_staff(output)
    regions, current = [], {}
    order = sorted(range(len(output.notes)), key=lambda i: (
        output.notes[i].part, output.notes[i].staff, output.notes[i].bar, output.notes[i].onset))
    for i in order:
        note = output.notes[i]
        staff = (note.part, note.staff)
        target = strict.staff_map.get(staff)
        position = to_truth_position(strict, note.bar, note.onset)
        if target is None or position is None:
            continue
        written = _clef_at(output_clefs.get(staff, []), note.bar, note.onset)
        right = _clef_at(truth_clefs.get(target, []), *position)
        a, b = (_clef_line(right), _clef_line(written)) if written and right else (None, None)
        if a is None or b is None or a == b:
            current.pop(staff, None)
            continue
        region = current.get(staff)
        if region is None or (region.truth_clef, region.output_clef) != (right, written):
            region = ClefCorrection(target, staff, right, written, a - b, position[0], position[0], note.bar)
            current[staff] = region
            regions.append(region)
        region.last_bar = position[0]
        region.indices.append(i)
    return regions


def _move(output, corrections):
    """A copy of the output with each correction's notes moved by its shift.
    Returns the copy and {id of a moved note: the note as written}."""
    shift_of = {i: c.shift for c in corrections for i in c.indices}
    notes, original = [], {}
    for i, note in enumerate(output.notes):
        if i not in shift_of:
            notes.append(note)
            continue
        number = STEPS.index(note.pitch.step) + 7 * note.pitch.octave + shift_of[i]
        pitch = dataclasses.replace(note.pitch, step=STEPS[number % 7], octave=number // 7)
        moved = dataclasses.replace(note, pitch=pitch)
        notes.append(moved)
        original[id(moved)] = note
    return dataclasses.replace(output, notes=notes), original


def groups(result, truth_items, output_items):
    """For each segment and ground-truth part (a matching group), yield
    (segment index, part, truth items placed, output items placed, output
    items whose staff has no partner). Works for notes and for rests."""
    truth_by_bar = collections.defaultdict(list)
    for item in truth_items:
        truth_by_bar[item.bar].append(item)
    output_by_bar = collections.defaultdict(list)
    for item in output_items:
        output_by_bar[item.bar].append(item)
    for index, segment in enumerate(result.segments):
        truth_placed = collections.defaultdict(list)
        output_placed = collections.defaultdict(list)
        unmapped = []
        for bar, offset in zip(segment.truth, segment.truth_offsets):
            for item in truth_by_bar[bar]:
                truth_placed[item.part].append(_Placed(item, item.onset + offset))
        for bar, offset in zip(segment.output, segment.output_offsets):
            for item in output_by_bar[bar]:
                target = result.staff_map.get((item.part, item.staff))
                if target is None:
                    unmapped.append(item)
                else:
                    output_placed[target[0]].append(_Placed(item, item.onset + offset))
        parts = sorted(set(truth_placed) | set(output_placed))
        if not parts and unmapped:
            yield index, None, [], [], unmapped
        for n, part in enumerate(parts):
            yield index, part, truth_placed[part], output_placed[part], unmapped if n == 0 else []


def to_truth_position(result, output_bar, onset):
    """The ground-truth (bar, onset) that an output position lines up with, or
    None if the output bar has no ground-truth partner."""
    index = result.output_segment.get(output_bar)
    if index is None:
        return None
    segment = result.segments[index]
    if not segment.truth:
        return None
    aligned = onset + segment.output_offsets[segment.output.index(output_bar)]
    bar, offset = segment.truth[0], segment.truth_offsets[0]
    for b, o in zip(segment.truth, segment.truth_offsets):
        if aligned >= o:
            bar, offset = b, o
    return bar, aligned - offset
