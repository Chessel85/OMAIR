"""Stand-in recognisers that test the harness itself (spec, "Test recognisers").

`perfect` copies the ground truth. `damaged` copies it with known damage and
writes `damage.json`: what it changed and the figures that damage implies,
worked out from the damage alone, never by running the harness. Each kind of
damage goes in its own bar, so that no two can interact.

Run as: python -m omr.evaluate.recognisers perfect|damaged PDF OUT --truth FILE [--seed N]
"""

import argparse
import copy
import json
import random
import shutil
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from omr.evaluate import events

STEPS = "CDEFGAB"
STEP_GAP = {"C": 2, "D": 2, "E": 1, "F": 2, "G": 2, "A": 2, "B": 1}   # semitones to the next step up


def perfect(truth, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(truth, out / "score.musicxml")


class _Damage:
    def __init__(self, root, rng):
        self.root = root
        self.rng = rng
        self.parts = root.findall("part")
        self.used_bars = set()
        self.log = []
        self.expected = {"pitch": 0, "spelling only": 0, "duration": 0, "missing": 0, "extra": 0,
                         "structure mismatches": 0, "bars joined": 0, "dynamics removed": 0}
        self.error_bars = {}    # bar position -> number of note errors there

    def candidates(self, test, reserve_after=None):
        """(part index, bar index, measure, note) for visible pitched notes passing `test`,
        in bars not used yet, in a shuffled order."""
        found = []
        for p, part in enumerate(self.parts):
            for b, measure in enumerate(part.findall("measure")):
                if b in self.used_bars or (reserve_after is not None and b >= reserve_after):
                    continue
                notes = measure.findall("note")
                for note in notes:
                    if (note.get("print-object") != "no" and note.find("pitch") is not None
                            and note.find("grace") is None and note.find("cue") is None and test(note, notes)):
                        found.append((p, b, measure, note))
        self.rng.shuffle(found)
        return found

    def take(self, kind, bar, note_errors, words):
        self.used_bars.update({bar - 1, bar, bar + 1})
        self.log.append({"kind": kind, "bar": bar + 1, "what": words})
        if note_errors:
            self.error_bars[bar] = self.error_bars.get(bar, 0) + note_errors


def _pitch(note):
    p = note.find("pitch")
    return p.findtext("step"), Fraction(p.findtext("alter") or "0"), int(p.findtext("octave"))


def _set_pitch(note, step, alter, octave):
    p = note.find("pitch")
    p.find("step").text = step
    alter_el = p.find("alter")
    if alter:
        if alter_el is None:
            alter_el = ET.Element("alter")
            p.insert(1, alter_el)
        alter_el.text = str(alter)
    elif alter_el is not None:
        p.remove(alter_el)
    p.find("octave").text = str(octave)


def _same_onset_pitches(note, notes):
    """Pitches of the notes sounding with `note` as one chord (itself included)."""
    index = notes.index(note)
    start = index
    while start > 0 and notes[start].find("chord") is not None:
        start -= 1
    end = index + 1
    while end < len(notes) and notes[end].find("chord") is not None:
        end += 1
    return {_pitch(n) for n in notes[start:end] if n.find("pitch") is not None}


def _plain_bar(measures, index):
    """No barline, clef, key or time change: joining it changes nothing but the bar count."""
    measure = measures[index]
    if measure.find("barline") is not None:
        return False
    for attributes in measure.findall("attributes"):
        if any(attributes.find(tag) is not None for tag in ("clef", "key", "time", "staves")):
            return False
    return True


def _join_point(parts):
    """The first of two plain bars to join, searched from three bars before the end."""
    count = min(len(part.findall("measure")) for part in parts)
    for first in range(count - 3, 5, -1):
        if all(_plain_bar(part.findall("measure"), first) and _plain_bar(part.findall("measure"), first + 1)
               for part in parts):
            return first
    return None


def damage(truth, out, seed=1, flag_share=0.5):
    """Copy `truth` to OUT/score.musicxml with known damage and write
    OUT/damage.json and OUT/flags.json."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(events.read_root(truth))
    root = tree.getroot()
    rng = random.Random(seed)
    d = _Damage(root, rng)
    join_at = _join_point(d.parts)   # the join comes after every other damage

    # 1. A pitch an octave higher, where no note of the same chord already has that pitch.
    for p, b, measure, note in d.candidates(lambda n, ns: True, join_at):
        step, alter, octave = _pitch(note)
        if (step, alter, octave + 1) not in _same_onset_pitches(note, measure.findall("note")):
            _set_pitch(note, step, alter, octave + 1)
            d.expected["pitch"] += 1
            d.take("pitch", b, 1, f"part {p + 1}: {step}{alter or ''}{octave} raised an octave")
            break
    # 2. An enharmonic respelling (C sharp written as D flat).
    for p, b, measure, note in d.candidates(lambda n, ns: True, join_at):
        step, alter, octave = _pitch(note)
        new_step = STEPS[(STEPS.index(step) + 1) % 7]
        new_alter = alter - STEP_GAP[step]
        new_octave = octave + (1 if step == "B" else 0)
        if abs(new_alter) <= 2 and (new_step, new_alter, new_octave) not in _same_onset_pitches(note, measure.findall("note")):
            _set_pitch(note, new_step, new_alter, new_octave)
            d.expected["pitch"] += 1
            d.expected["spelling only"] += 1
            d.take("respelling", b, 1, f"part {p + 1}: {step}{alter or ''}{octave} respelled")
            break
    # 3. Delete a chord note (it has <chord/>, so no timing moves).
    for p, b, measure, note in d.candidates(lambda n, ns: n.find("chord") is not None, join_at):
        measure.remove(note)
        d.expected["missing"] += 1
        d.take("missing", b, 1, f"part {p + 1}: a chord note deleted")
        break
    # 4. Add a note to a chord, two octaves above one of its notes.
    for p, b, measure, note in d.candidates(lambda n, ns: n.find("chord") is None, join_at):
        notes = measure.findall("note")
        step, alter, octave = _pitch(note)
        if (step, alter, octave + 2) in _same_onset_pitches(note, notes):
            continue
        added = copy.deepcopy(note)
        for tag in ("tie", "lyric", "notations", "beam"):
            for child in added.findall(tag):
                added.remove(child)
        added.insert(0, ET.Element("chord"))
        _set_pitch(added, step, alter, octave + 2)
        position = list(measure).index(note)
        # after the whole chord that starts at `note`
        children = list(measure)
        position += 1
        while position < len(children) and children[position].tag == "note" and children[position].find("chord") is not None:
            position += 1
        measure.insert(position, added)
        d.expected["extra"] += 1
        d.take("extra", b, 1, f"part {p + 1}: a note added to a chord")
        break
    # 5. Change the notated type of a note but keep its <duration>, so no onset moves.
    longer = {"16th": "eighth", "eighth": "quarter", "quarter": "half", "half": "whole"}
    for p, b, measure, note in d.candidates(
            lambda n, ns: (n.findtext("type") or "") in longer and n.find("time-modification") is None, join_at):
        note.find("type").text = longer[note.findtext("type")]
        d.expected["duration"] += 1
        d.take("duration", b, 1, f"part {p + 1}: a note's value doubled")
        break
    # 6. Swap the voice numbers in one bar of one part (no note errors).
    for p, part in enumerate(d.parts):
        done = False
        for b, measure in enumerate(part.findall("measure")):
            if b in d.used_bars or (join_at is not None and b >= join_at):
                continue
            voices = sorted({n.findtext("voice") for n in measure.findall("note") if n.findtext("voice")})
            if len(voices) >= 2:
                swap = {voices[0]: voices[1], voices[1]: voices[0]}
                for n in measure.findall("note"):
                    if n.findtext("voice") in swap:
                        n.find("voice").text = swap[n.findtext("voice")]
                d.take("voices swapped", b, 0, f"part {p + 1}: voices {voices[0]} and {voices[1]} swapped")
                done = True
                break
        if done:
            break
    # 7. Remove one dynamic.
    removed = False
    for p, part in enumerate(d.parts):
        for b, measure in enumerate(part.findall("measure")):
            if b in d.used_bars or (join_at is not None and b >= join_at):
                continue
            for direction in measure.findall("direction"):
                types = direction.findall("direction-type")
                if len(types) == 1 and len(types[0]) == 1 and types[0][0].tag == "dynamics" and len(types[0][0]) == 1:
                    measure.remove(direction)
                    d.expected["dynamics removed"] += 1
                    d.take("dynamic removed", b, 0, f"part {p + 1}: a dynamic removed")
                    removed = True
                    break
            if removed:
                break
        if removed:
            break
    # 8. Join two bars near the end in every part (a missed barline: one structural error, no note errors).
    if join_at is not None:
        for part in d.parts:
            measures = part.findall("measure")
            first, second = measures[join_at], measures[join_at + 1]
            for child in list(second):
                if child.tag not in ("print", "barline"):
                    first.append(child)
            part.remove(second)
        d.expected["bars joined"] += 1
        d.expected["structure mismatches"] += 1
        d.log.append({"kind": "bars joined", "bar": join_at + 1, "what": f"bars {join_at + 1} and {join_at + 2} joined"})

    tree.write(out / "score.musicxml", encoding="utf-8", xml_declaration=True)
    flagged = sorted(d.error_bars)[: max(0, round(len(d.error_bars) * flag_share))]
    flags = [{"part": p + 1, "bar": bar + 1, "reason": "test flag"}
             for bar in flagged for p in range(len(d.parts))]
    (out / "flags.json").write_text(json.dumps({"version": 1, "flags": flags}, indent=1), encoding="utf-8")
    e = d.expected
    wrong = e["pitch"] + e["duration"]
    errors = wrong + e["missing"] + e["extra"]
    expected = dict(e, wrong=wrong, errors=errors,
                    covered=sum(d.error_bars[b] for b in flagged),
                    bars_flagged=len(flags))
    (out / "damage.json").write_text(json.dumps({"seed": seed, "changes": d.log, "expected": expected}, indent=1),
                                     encoding="utf-8")
    return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stand-in recognisers for testing the harness.")
    parser.add_argument("kind", choices=("perfect", "damaged"))
    parser.add_argument("pdf", help="Not read; present so the command looks like a real recogniser.")
    parser.add_argument("out")
    parser.add_argument("--truth", required=True)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    if args.kind == "perfect":
        perfect(args.truth, args.out)
    else:
        damage(args.truth, args.out, seed=args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
