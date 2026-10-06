"""Compare one output file with its ground truth (spec, "Metrics").

`compare` returns a plain dictionary of counts, ready for JSON. Percentages are
worked out only when reports add files together, from the counts, so overall
figures are micro-averages as the spec requires.
"""

import collections
import json
from fractions import Fraction
from pathlib import Path

from omr.evaluate import events, match as matching
from omr.evaluate.describe import Describer

STRUCTURE_KINDS = ("clef", "key", "time", "repeat", "ending", "navigation")
MARKING_KINDS = ("dynamic", "hairpin", "hairpin end", "words", "chord symbol")


def compare(truth_path, output_path, flags_path=None):
    """Compare two MusicXML files. Raises events.MusicXMLError if the ground
    truth cannot be read; an unreadable output is the caller's failed file."""
    truth = events.read(truth_path)
    output = events.read(output_path)
    flags = read_flags(flags_path) if flags_path and Path(flags_path).is_file() else None
    return compare_scores(truth, output, flags)


def compare_scores(truth, output, flags=None):
    result = matching.match(truth, output)
    say = Describer(truth)
    errors = list(_error_list(result, say))
    figures = {
        "notes": _note_counts(truth, output, result),
        "diagnostics": _diagnostics(truth, output, result),
        "structure": _structure(truth, output, result, say),
        "markings": _markings(truth, output, result, say),
        "note marks": _note_marks(result),
        "errors": errors,
    }
    if flags is not None:
        figures["flags"] = _flags(output, result, flags)
    return figures


def failed_file(truth_path, reason):
    """The figures for a file the recogniser could not convert: every note missing."""
    truth = events.read(truth_path)
    empty = events.Score(parts=[], bars=[], bar_counts=[])
    figures = compare_scores(truth, empty)
    figures["failed"] = reason
    return figures


# ------------------------------------------------------------------ notes


def _note_counts(truth, output, result):
    kinds = collections.Counter()
    for pair in result.errors:
        kinds[" and ".join(pair.differs)] += 1
        if pair.spelling_only:
            kinds["spelling only"] += 1
    return {
        "truth": len(truth.notes),
        "output": len(output.notes),
        "exact": len(result.exact),
        "missing": len(result.missing),
        "extra": len(result.extra),
        "wrong": len(result.errors),
        "wrong by kind": dict(kinds),
    }


def _diagnostics(truth, output, result):
    """Figures that explain the note accuracy (spec, "Note accuracy")."""
    pitch_duration = sounding = 0
    for _, _, t, o, _ in matching.groups(result, truth.notes, output.notes):
        pitch_duration += _intersection(t, o, lambda p: (p.pitch, p.duration_key))
        sounding += _intersection(t, o, lambda p: (p.onset_aligned, p.pitch.sounding(), p.duration_key))
    rests = 0
    for _, _, t, o, _ in matching.groups(result, truth.rests, output.rests):
        rests += _intersection(t, o, lambda p: (p.onset_aligned, p.note.duration))
    staff_right = sum(1 for t, o in result.exact if result.staff_map.get((o.part, o.staff)) == (t.part, t.staff))
    ties_right = sum(1 for t, o in result.exact if (t.tie_start, t.tie_stop) == (o.tie_start, o.tie_stop))
    most = max(len(truth.notes), len(output.notes))
    return {
        "pitch and duration": {"matched": pitch_duration, "of": most},
        "sounding pitch": {"matched": sounding, "of": most},
        "staff": {"right": staff_right, "of": len(result.exact)},
        "voice": {"right": len(result.exact) - _voice_errors(result), "of": len(result.exact)},
        "ties": {"right": ties_right, "of": len(result.exact)},
        "rests": {"matched": rests, "of": max(len(truth.rests), len(output.rests))},
    }


def _intersection(truth_placed, output_placed, key):
    a = collections.Counter(key(p) for p in truth_placed)
    b = collections.Counter(key(p) for p in output_placed)
    return sum((a & b).values())


def _voice_errors(result):
    """Within each bar, map each output voice to the ground-truth voice it
    shares most exact matches with; count matched notes that disagree."""
    pairs = collections.defaultdict(collections.Counter)
    for t, o in result.exact:
        pairs[(result.truth_segment.get(t.bar), t.part, o.voice)][t.voice] += 1
    return sum(sum(c.values()) - max(c.values()) for c in pairs.values())


# ------------------------------------------------------------------ structure


def _mapped_part(result, part, staff):
    target = result.staff_map.get((part, staff or 1))
    return target


def _structure(truth, output, result, say):
    mismatches, notes = [], []
    truth_staves = [p.staves for p in truth.parts]
    output_staves = [p.staves for p in output.parts]
    if len(truth.parts) != len(output.parts):
        mismatches.append(f"The ground truth has {len(truth.parts)} parts, the output has {len(output.parts)}.")
    elif truth_staves != output_staves:
        for n, (a, b) in enumerate(zip(truth_staves, output_staves)):
            if a != b:
                mismatches.append(f"{say.part(n)}: the ground truth has {a} staves, the output has {b}.")
    if len(truth.bars) != len(output.bars):
        mismatches.append(f"The ground truth has {len(truth.bars)} bars, the output has {len(output.bars)}.")

    def key(event, part, staff, bar, onset):
        if event.kind == "clef":
            return (event.kind, event.value, part, staff, bar, onset)
        return (event.kind, event.value, part, None, bar, None)

    truth_events = collections.Counter(
        key(e, e.part, e.staff, e.bar, e.onset) for e in truth.structure if e.kind in STRUCTURE_KINDS)
    output_events = collections.Counter()
    for e in output.structure:
        if e.kind not in STRUCTURE_KINDS:
            continue
        target = _mapped_part(result, e.part, e.staff)
        position = matching.to_truth_position(result, e.bar, e.onset)
        if target is None or position is None:
            output_events[(e.kind, e.value, None, None, None, None)] += 1
            continue
        output_events[key(e, target[0], target[1], position[0], position[1])] += 1
    only_truth = truth_events - output_events
    only_output = output_events - truth_events
    # A changed value at the same place (2/4 became 3/4) is one mismatch, not two.
    for item in sorted(only_truth, key=lambda i: _sort_key((i, 0))):
        kind, value, part, staff, bar, onset = item
        other = next((o for o in list(only_output) if o[0] == kind and o[2:] == item[2:]
                      and bar is not None), None)
        if other is not None and only_truth[item] == 1 and only_output[other] == 1:
            del only_output[other]
            only_truth[item] = 0
            where = say.place(part, staff, bar, onset if kind == "clef" else None)
            mismatches.append(f"{where}: the ground truth has {_structure_thing(say, kind, value)}, "
                              f"the output has {_structure_thing(say, kind, other[1])}.")
    only_truth = +only_truth
    for item, count in sorted(only_truth.items(), key=_sort_key):
        mismatches.append(_structure_words(say, item, "ground truth", "output", count))
    for item, count in sorted(only_output.items(), key=_sort_key):
        mismatches.append(_structure_words(say, item, "output", "ground truth", count))
    truth_symbols = {(m.part, m.bar, m.value) for m in truth.markings if m.kind == "time symbol"}
    output_symbols = set()
    for m in output.markings:
        if m.kind == "time symbol":
            target = _mapped_part(result, m.part, None)
            position = matching.to_truth_position(result, m.bar, m.onset)
            if target and position:
                output_symbols.add((target[0], position[0], m.value))
    for part, bar, value in sorted(truth_symbols ^ output_symbols):
        notes.append(f"{say.bar(bar)}, {say.part(part)}: the {value}-time symbol is drawn in only one of the files.")
    return {"correct": not mismatches, "mismatches": mismatches, "notes": notes}


def _sort_key(item):
    (kind, value, part, staff, bar, onset), _ = item
    return (bar if bar is not None else -1, part if part is not None else -1, kind, value)


def _structure_thing(say, kind, value):
    return {
        "clef": lambda: f"a {value} clef", "key": lambda: f"a key signature of {say.key(value)}",
        "time": lambda: f"a {value} time signature", "repeat": lambda: f"a {value} repeat barline",
        "ending": lambda: f"an ending ({value})", "navigation": lambda: f"a {say.navigation(value)} mark",
    }[kind]()


def _structure_words(say, item, has, lacks, count):
    kind, value, part, staff, bar, onset = item
    thing = _structure_thing(say, kind, value)
    times = f" ({count} times)" if count > 1 else ""
    if bar is None:
        return f"The {has} has {thing}{times} in a bar or part the {lacks} does not have."
    where = say.place(part, staff, bar, onset if kind == "clef" else None)
    return f"{where}: the {has} has {thing}{times}, the {lacks} does not."


# ------------------------------------------------------------------ markings


def _same_text(a, b):
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


def _markings(truth, output, result, say):
    """Recall and precision of dynamics, hairpins, text and chord symbols."""
    placed = collections.defaultdict(list)
    for m in output.markings:
        if m.kind not in MARKING_KINDS:
            continue
        target = _mapped_part(result, m.part, m.staff)
        position = matching.to_truth_position(result, m.bar, m.onset)
        if target is None or position is None:
            continue
        staff = target[1] if m.staff is not None else None
        placed[(m.kind, target[0], position[0])].append([m, staff, position[1], False])
    figures = {kind: {"truth": 0, "found": 0, "output": 0, "missed": []} for kind in MARKING_KINDS}
    for m in output.markings:
        if m.kind in figures:
            figures[m.kind]["output"] += 1
    for m in truth.markings:
        if m.kind not in MARKING_KINDS:
            continue
        figures[m.kind]["truth"] += 1
        beat = say.beat_length(m.bar)
        best = None
        for candidate in placed.get((m.kind, m.part, m.bar), []):
            other, staff, onset, used = candidate
            if used or abs(onset - m.onset) > beat:
                continue
            if m.staff is not None and staff is not None and staff != m.staff:
                continue
            if m.kind != "hairpin end" and not _same_text(other.value, m.value):
                continue
            if best is None or abs(onset - m.onset) < abs(best[2] - m.onset):
                best = candidate
        if best is None:
            figures[m.kind]["missed"].append(f"{say.place(m.part, m.staff, m.bar, m.onset)}: {say.marking(m)}")
        else:
            best[3] = True
            figures[m.kind]["found"] += 1
    return figures


def _note_marks(result):
    """Articulations, ornaments, fermatas, slur ends and lyrics on exactly matched notes."""
    figures = collections.defaultdict(lambda: {"truth": 0, "found": 0})
    for t, o in result.exact:
        for mark in t.marks:
            figures[mark]["truth"] += 1
            figures[mark]["found"] += mark in o.marks
        truth_slurs = collections.Counter(kind for kind, _ in t.slurs)
        output_slurs = collections.Counter(kind for kind, _ in o.slurs)
        figures["slur ends"]["truth"] += sum(truth_slurs.values())
        figures["slur ends"]["found"] += sum((truth_slurs & output_slurs).values())
        truth_lyrics = collections.Counter(text for _, text in t.lyrics if text)
        output_lyrics = collections.Counter(text for _, text in o.lyrics if text)
        figures["lyrics"]["truth"] += sum(truth_lyrics.values())
        figures["lyrics"]["found"] += sum((truth_lyrics & output_lyrics).values())
    return {k: v for k, v in sorted(figures.items()) if v["truth"]}


# ------------------------------------------------------------------ flags


def read_flags(path):
    """Read a flag file (spec, "Error flagging"). Returns a list of
    (part, bar, staff or None), each counted from 0 for part and bar."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("flags"), list):
        raise ValueError("the flag file must be {\"version\": 1, \"flags\": [...]}")
    flags = []
    for flag in data["flags"]:
        staff = flag.get("staff")
        flags.append((int(flag["part"]) - 1, int(flag["bar"]) - 1, int(staff) if staff is not None else None))
    return flags


def _flags(output, result, flags):
    flagged = collections.defaultdict(set)   # (output part, output bar) -> staves, or {None} for all
    for part, bar, staff in flags:
        flagged[(part, bar)].add(staff)
    output_parts_of = collections.defaultdict(set)   # truth part -> output parts mapped to it
    for (o_part, o_staff), (t_part, _) in result.staff_map.items():
        output_parts_of[t_part].add(o_part)
    truth_staff_to_output = {v: k for k, v in result.staff_map.items()}

    def covered_output(part, bar, staff):
        staves = flagged.get((part, bar))
        return bool(staves) and (None in staves or staff in staves)

    def neighbours(segment_index):
        bars = []
        for step in (-1, 1):
            i = segment_index + step
            while 0 <= i < len(result.segments):
                if result.segments[i].output:
                    bars.append(result.segments[i].output[0 if step == 1 else -1])
                    break
                i += step
        return bars

    def covered_truth(note):
        index = result.truth_segment.get(note.bar)
        if index is None:
            return False
        segment = result.segments[index]
        bars = segment.output or neighbours(index)
        target = truth_staff_to_output.get((note.part, note.staff))
        for o_part in output_parts_of.get(note.part, ()):
            for bar in bars:
                staff = target[1] if target and target[0] == o_part else None
                if covered_output(o_part, bar, staff):
                    return True
        return False

    error_bars = set()
    covered = total = 0
    for note in result.missing + [pair.truth for pair in result.errors]:
        total += 1
        covered += covered_truth(note)
        index = result.truth_segment.get(note.bar)
        if index is not None:
            for bar in result.segments[index].output:
                for o_part in output_parts_of.get(note.part, ()):
                    error_bars.add((o_part, bar))
    for note in result.extra:
        total += 1
        covered += covered_output(note.part, note.bar, note.staff)
        error_bars.add((note.part, note.bar))
    bars_total = sum(output.bar_counts) if output.bar_counts else 0
    return {
        "errors": total,
        "covered": covered,
        "bars flagged": len(flagged),
        "bars": bars_total,
        "flagged bars with an error": len(set(flagged) & error_bars),
    }


# ------------------------------------------------------------------ error list


def _error_list(result, say):
    """Every note error, in words, in bar order (spec, "Reports")."""
    items = []
    for pair in result.errors:
        t, o = pair.truth, pair.output
        kind = " and ".join(pair.differs) + " error"
        if pair.spelling_only:
            kind = "spelling error"
        items.append((t.bar, t.onset, {
            "kind": kind, "bar": t.bar,
            "where": say.place(t.part, t.staff, t.bar, t.onset),
            "expected": say.note(t, onset="onset" in pair.differs),
            "found": say.note(o, onset="onset" in pair.differs, bar=t.bar)}))
    for t in result.missing:
        items.append((t.bar, t.onset, {
            "kind": "missing note", "bar": t.bar,
            "where": say.place(t.part, t.staff, t.bar, t.onset), "expected": say.note(t), "found": "nothing"}))
    for o in result.extra:
        position = matching.to_truth_position(result, o.bar, o.onset)
        target = result.staff_map.get((o.part, o.staff))
        if position and target:
            where = say.place(target[0], target[1], position[0], position[1])
            bar = position[0]
        else:
            where = f"output bar {o.bar + 1}, which has no ground-truth partner"
            bar = -1
        items.append((bar, o.onset, {"kind": "extra note", "bar": bar, "where": where,
                                     "expected": "nothing", "found": say.note(o)}))
    items.sort(key=lambda x: (x[0], x[1]))
    return [item for _, _, item in items]
