"""Write an events.Score as MusicXML 4.0 (Stage 1.6, OUT-1).

The Score is the one `omr.pdf.structure.read_pdf(path, notes=True)` gives.
The writer is the inverse of the harness's reader (`omr.evaluate.events`):
reading the written file back gives the same notes, rests, markings and
structure, which `tests/test_musicxml.py` and `scripts/check_convert.py`
check. The rules and known limits are in docs/notes/musicxml-spec.md.
"""

import datetime
import math
import xml.etree.ElementTree as ET
from dataclasses import replace
from fractions import Fraction

from omr import __version__
from omr.evaluate import events

HEADER = ('<?xml version="1.0" encoding="UTF-8"?>\n'
          '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
          '"http://www.musicxml.org/dtds/partwise.dtd">\n')
# MusicXML's dynamics elements; any other dynamic is other-dynamics
DYNAMICS = {"p", "pp", "ppp", "pppp", "ppppp", "pppppp", "f", "ff", "fff", "ffff", "fffff", "ffffff",
            "mp", "mf", "sf", "sfp", "sfpp", "fp", "rf", "rfz", "sfz", "sffz", "fz", "n", "pf", "sfzp"}
ACCIDENTALS = {Fraction(-2): "flat-flat", Fraction(-1): "flat", Fraction(0): "natural",
               Fraction(1): "sharp", Fraction(2): "double-sharp"}
# the words written for a jump the page shows as a sign or as no text the reader kept
JUMP_WORDS = {"dacapo": "D.C.", "dalsegno": "D.S.", "fine": "Fine", "tocoda": "To Coda"}
JUMP_SOUND = {"dacapo": ("dacapo", "yes"), "dalsegno": ("dalsegno", "segno"), "fine": ("fine", "yes"),
              "tocoda": ("tocoda", "coda")}
CREDIT_PLACE = {"title": ("center", "top"), "subtitle": ("center", "top"), "composer": ("right", "top"),
                "lyricist": ("left", "top"), "rights": ("center", "bottom")}
MAX_VOICES = 4   # voices a staff may have in a bar


# ------------------------------------------------------------ durations

def _denominators(score):
    for n in score.notes:
        yield n.onset.denominator
        yield n.duration.denominator
    for r in score.rests:
        yield r.onset.denominator
        if r.duration != events.WHOLE_BAR:
            yield r.duration.denominator
    for m in score.markings + score.structure:
        yield Fraction(m.onset).denominator
    for b in score.bars:
        yield Fraction(b.length).denominator
    for e in score.structure:
        if e.kind == "time":
            yield _time_length(e.value).denominator


def divisions(score):
    """Divisions of a quarter note that make every onset and duration whole."""
    return max(math.lcm(*_denominators(score), 1), 1)


def _time_length(value):
    beats, _, beat_type = value.partition("/")
    try:
        return Fraction(sum(int(b) for b in beats.split("+")) * 4, int(beat_type))
    except (ValueError, ZeroDivisionError):
        return Fraction(4)


def rest_value(duration):
    """(type, dots, (actual, normal) or None) that notate a rest's duration:
    a plain or dotted value if one fits, else the tuplet of a plain value."""
    for dots in (0, 1, 2, 3):
        for name, length in events.TYPE_LENGTH.items():
            if length * (2 - Fraction(1, 2 ** dots)) == duration:
                return name, dots, None
    for name, length in events.TYPE_LENGTH.items():
        if duration <= length < 2 * duration:
            ratio = length / duration
            return name, 0, (ratio.numerator, ratio.denominator)
    return "quarter", 0, None


def _value_parts(value):
    name = value.rstrip(".")
    return (name if name in events.TYPE_LENGTH else "quarter"), len(value) - len(value.rstrip("."))


# ------------------------------------------------------------- elements

def _sub(parent, tag, content=None, **attrs):
    element = ET.SubElement(parent, tag, {k.replace("_", "-"): str(v) for k, v in attrs.items()})
    if content is not None:
        element.text = str(content)
    return element


class _Bar:
    """One part's bar while it is written: the position in divisions, and
    what goes where."""

    def __init__(self, measure, div):
        self.measure = measure
        self.div = div
        self.pos = Fraction(0)

    def ticks(self, quarters):
        return int(quarters * self.div)

    def move_to(self, onset, voice=None, staff=None):
        if onset > self.pos:
            forward = _sub(self.measure, "forward")
            _sub(forward, "duration", self.ticks(onset - self.pos))
            if voice is not None:
                _sub(forward, "voice", voice)
            if staff is not None:
                _sub(forward, "staff", staff)
        elif onset < self.pos:
            backup = _sub(self.measure, "backup")
            _sub(backup, "duration", self.ticks(self.pos - onset))
        self.pos = onset


class Writer:
    def __init__(self, score, title=None):
        self.score = score
        self.div = divisions(score)
        self.title = title
        # restated clefs, keys and times are left out (spec decision 11)
        self.changes = events.signature_changes(score)
        self.changes_at = {}     # (part, bar) -> its changes, in order
        for e in self.changes:
            self.changes_at.setdefault((e.part, e.bar), []).append(e)
        self.time_symbols = {}   # (part, bar) -> the first time symbol there
        for m in score.markings:
            if m.kind == "time symbol":
                self.time_symbols.setdefault((m.part, m.bar), m.value)
        self.jumps = self._jump_words()
        self.merged = set()    # (part, bar, staff) whose voices were merged to MAX_VOICES
        self.left_out = []     # notes and rests not written, as no voice had room (_merge_voices)
        self.signatures = events.SignaturesInForce(score)

    def _bar_count(self, part):
        counts = self.score.bar_counts
        return counts[part] if part < len(counts) else len(self.score.bars)

    # ------------------------------------------------------- the document

    def root(self):
        root = ET.Element("score-partwise", version="4.0")
        self._header(root)
        part_list = _sub(root, "part-list")
        for p, part in enumerate(self.score.parts):
            sp = _sub(part_list, "score-part", id=f"P{p + 1}")
            _sub(sp, "part-name", part.name.strip())
        by_part_bar = self._sorted_events()
        for p in range(len(self.score.parts)):
            part = _sub(root, "part", id=f"P{p + 1}")
            for b in range(self._bar_count(p)):
                self._bar(part, p, b, by_part_bar.get((p, b), {}))
        return root

    def _header(self, root):
        texts = [t for t in self.score.text if t.kind in CREDIT_PLACE and t.text.strip()]
        titles = [t.text for t in texts if t.kind == "title"]
        title = " ".join(titles[0].split()) if titles else self.title
        if title:
            _sub(_sub(root, "work"), "work-title", title)
        ident = _sub(root, "identification")
        for kind in ("composer", "lyricist"):
            for t in texts:
                if t.kind == kind:
                    _sub(ident, "creator", " ".join(t.text.split()), type=kind)
        for t in texts:
            if t.kind == "rights":
                _sub(ident, "rights", " ".join(t.text.split()))
        encoding = _sub(ident, "encoding")
        _sub(encoding, "software", f"omr {__version__}")
        _sub(encoding, "encoding-date", datetime.date.today().isoformat())
        for t in texts:
            credit = _sub(root, "credit", page=t.page)
            _sub(credit, "credit-type", t.kind)
            justify, valign = CREDIT_PLACE[t.kind]
            _sub(credit, "credit-words", " ".join(t.text.split()), justify=justify, valign=valign)

    def _sorted_events(self):
        """{(part, bar): {"voices": {(staff, voice): [notes and rests]}, "items": [...]}}"""
        out = {}

        def slot(part, bar):
            return out.setdefault((part, bar), {"voices": {}, "items": []})

        for n in self.score.notes:
            slot(n.part, n.bar)["voices"].setdefault((n.staff, n.voice), []).append(n)
        for r in self.score.rests:
            slot(r.part, r.bar)["voices"].setdefault((r.staff, r.voice), []).append(r)
        # items woven into the music at their onset: clefs within a bar, directions, chord symbols
        for e in self.changes:
            if e.kind == "clef" and e.onset > 0:
                slot(e.part, e.bar)["items"].append(e)
            elif e.kind == "navigation":
                slot(e.part, e.bar)["items"].append(e)
        for m in self.score.markings:
            if m.kind != "time symbol":
                slot(m.part, m.bar)["items"].append(m)
        for (part, bar), content in out.items():
            for staff in {st for st, _ in content["voices"]}:
                if sum(1 for st, _ in content["voices"] if st == staff) > MAX_VOICES:
                    self.left_out.extend(_merge_voices(content["voices"], staff))
                    self.merged.add((part, bar, staff))
        return out

    # ------------------------------------------------------------ one bar

    def _bar(self, part_el, p, b, content):
        number = self.score.bars[b].number if b < len(self.score.bars) else str(b + 1)
        measure = _sub(part_el, "measure", number=number or str(b + 1))
        bar = _Bar(measure, self.div)
        if p == 0 and 0 < b < len(self.score.bars):
            here, before = self.score.bars[b], self.score.bars[b - 1]
            if here.page != before.page:
                _sub(measure, "print", new_page="yes")
            elif here.system != before.system:
                _sub(measure, "print", new_system="yes")
        structure = list(self.changes_at.get((p, b), ()))
        self._left_barline(measure, structure)
        self._attributes(measure, p, b, structure)
        voices = content.get("voices", {})
        items = list(content.get("items", ()))
        jumps = self.jumps
        order = sorted(voices, key=lambda sv: (sv[0], _voice_number(sv[1])))
        primary = {}
        for staff, voice in order:
            primary.setdefault(staff, (staff, voice))
        # each item goes in a voice of its staff with an event at its onset, else
        # the staff's first voice (a clef cannot be moved by an offset)
        home = {}
        for i in items:
            staff = _item_staff(i)
            starting = [k for k in order if k[0] == staff and any(e.onset == i.onset for e in voices[k])]
            home[id(i)] = starting[0] if starting else primary.get(staff, order[0] if order else None)
        written = set()
        for key in order:
            staff, voice = key
            mine = [i for i in items if home[id(i)] == key]
            self._voice(bar, p, b, staff, voice, voices[key], mine, jumps)
            written.update(id(i) for i in mine)
            if key != order[-1]:
                bar.move_to(Fraction(0))
        for item in items:   # a bar with no notes or rests at all
            if id(item) not in written:
                self._item(bar, item, jumps, offset=item.onset - bar.pos)
        self._right_barline(measure, structure)

    def _attributes(self, measure, p, b, structure):
        part = self.score.parts[p]
        keys = [e for e in structure if e.kind == "key"]
        times = [e for e in structure if e.kind == "time"]
        clefs = sorted((e for e in structure if e.kind == "clef" and e.onset == 0), key=lambda e: e.staff or 1)
        if not (b == 0 or keys or times or clefs):
            return
        attributes = _sub(measure, "attributes")
        if b == 0:
            _sub(attributes, "divisions", self.div)
        for e in keys[-1:]:
            _sub(_sub(attributes, "key"), "fifths", int(e.value))
        for e in times[-1:]:
            beats, _, beat_type = e.value.partition("/")
            symbol = self.time_symbols.get((p, b))
            time = _sub(attributes, "time", **({"symbol": symbol} if symbol else {}))
            _sub(time, "beats", beats)
            _sub(time, "beat-type", beat_type)
        if b == 0 and part.staves > 1:
            _sub(attributes, "staves", part.staves)
        for e in clefs:
            self._clef(attributes, e, part.staves)

    def _clef(self, attributes, e, staves):
        clef = _sub(attributes, "clef", **({"number": e.staff} if staves > 1 or (e.staff or 1) != 1 else {}))
        words = e.value.split()
        _sub(clef, "sign", words[0])
        if len(words) > 1 and words[1].isdigit():
            _sub(clef, "line", words[1])
        if "octave" in words:
            _sub(clef, "clef-octave-change", int(words[words.index("octave") + 1]))

    def _left_barline(self, measure, structure):
        forward = any(e.kind == "repeat" and e.value.startswith("forward") for e in structure)
        starts = [e for e in structure if e.kind == "ending" and e.value.startswith("start")]
        if not (forward or starts):
            return
        barline = _sub(measure, "barline", location="left")
        if forward:
            _sub(barline, "bar-style", "heavy-light")
        for e in starts[:1]:
            numbers = e.value.split()[1:]
            _sub(barline, "ending", ", ".join(numbers) + "." if numbers else None,
                 number=", ".join(numbers) or "1", type="start")
        if forward:
            _sub(barline, "repeat", direction="forward")

    def _right_barline(self, measure, structure):
        backward = [e for e in structure if e.kind == "repeat" and e.value.startswith("backward")]
        ends = [e for e in structure if e.kind == "ending" and e.value.split()[0] in ("stop", "discontinue")]
        if not (backward or ends):
            return
        barline = _sub(measure, "barline", location="right")
        if backward:
            _sub(barline, "bar-style", "light-heavy")
        for e in ends[:1]:
            kind, *numbers = e.value.split()
            _sub(barline, "ending", number=", ".join(numbers) or "1", type=kind)
        if backward:
            _sub(barline, "repeat", direction="backward")

    # -------------------------------------------------------------- voices

    def _voice(self, bar, p, b, staff, voice, evs, items, jumps):
        """Write one voice of one staff, with the items woven in before the
        first event at or after their onset."""
        groups = _groups(evs)
        pending = sorted(items, key=_item_order)
        state = {}           # accidentals in force: (step, octave) -> alter
        tuplet = None        # [ratio, notated so far, smallest value, first note] of an open tuplet
        last_note = None
        for k, group in enumerate(groups):
            first = group[0]
            while pending and pending[0].onset <= first.onset:
                item = pending.pop(0)
                if item.onset >= bar.pos:
                    bar.move_to(item.onset, voice, staff)
                self._item(bar, item, jumps, offset=item.onset - bar.pos, voice=voice)
            bar.move_to(first.onset, voice, staff)
            ratio = self._ratio(first)
            # a tuplet is complete when its notes fill a whole number of its
            # smallest value; one that is not keeps no bracket marks, which
            # make MuseScore move the notes after it
            starts = ratio is not None and (tuplet is None or tuplet[0] != ratio)
            if tuplet is not None and (ratio is None or tuplet[0] != ratio):
                _tuplet_unmark(tuplet[3])
                tuplet = None
            for n, e in enumerate(group):
                el = self._event(bar, p, b, e, chord=n > 0, state=state, ratio=ratio)
                if n == 0 and starts:
                    _tuplet_mark(el, "start")
                    tuplet = [ratio, Fraction(0), None, el]
                last_note = el
            if tuplet is not None and not getattr(first, "grace", 0):
                notated = first.duration * ratio[0] / ratio[1]
                base = events.TYPE_LENGTH[self._value(first)[0]]
                tuplet[1] += notated
                tuplet[2] = base if tuplet[2] is None else min(tuplet[2], base)
                if tuplet[1] >= ratio[0] * tuplet[2] and tuplet[1] % tuplet[2] == 0:
                    _tuplet_mark(last_note, "stop")
                    tuplet = None
            if not getattr(first, "grace", 0):
                bar.pos = first.onset + self._length(p, b, first)
        if tuplet is not None:
            _tuplet_unmark(tuplet[3])
        for item in pending:
            if item.kind == "clef" and item.onset > bar.pos:
                bar.move_to(item.onset, voice, staff)
            self._item(bar, item, jumps, offset=item.onset - bar.pos, voice=voice)

    def _length(self, p, b, e):
        if isinstance(e, events.Rest) and e.duration == events.WHOLE_BAR:
            time = self.signatures.time(p, b)
            length = _time_length(time) if time is not None else None
            if length is None:
                bar = self.score.bars[b] if b < len(self.score.bars) else None
                length = bar.length if bar is not None and bar.length else Fraction(4)
            return length
        return e.duration

    def _value(self, e):
        """(type, dots, (actual, normal) or None) of a note or rest."""
        if isinstance(e, events.Rest):
            return rest_value(e.duration)
        name, dots = _value_parts(e.value)
        if e.grace:
            return name, dots, None
        notated = events.TYPE_LENGTH[name] * (2 - Fraction(1, 2 ** dots))
        if e.duration and notated != e.duration:
            ratio = notated / e.duration
            return name, dots, (ratio.numerator, ratio.denominator)
        return name, dots, None

    def _ratio(self, e):
        if isinstance(e, events.Rest) and e.duration == events.WHOLE_BAR:
            return None
        return self._value(e)[2]

    def _event(self, bar, p, b, e, chord, state, ratio):
        note = _sub(bar.measure, "note")
        if isinstance(e, events.Rest):
            whole = e.duration == events.WHOLE_BAR
            _sub(note, "rest", **({"measure": "yes"} if whole else {}))
            _sub(note, "duration", bar.ticks(self._length(p, b, e)))
            _sub(note, "voice", e.voice)
            if not whole:
                name, dots, _ = self._value(e)
                _sub(note, "type", name)
                for _ in range(dots):
                    _sub(note, "dot")
                _time_modification(note, ratio)
            _staff(note, self.score.parts[p], e.staff)
            return note
        if e.grace:
            _sub(note, "grace", slash="no")
        if e.cue:
            _sub(note, "cue")
        if chord:
            _sub(note, "chord")
        pitch = _sub(note, "pitch")
        _sub(pitch, "step", e.pitch.step)
        if e.pitch.alter:
            _sub(pitch, "alter", _number(e.pitch.alter))
        _sub(pitch, "octave", e.pitch.octave)
        if not e.grace:
            _sub(note, "duration", bar.ticks(e.duration))
        if not e.cue:
            if e.tie_stop:
                _sub(note, "tie", type="stop")
            if e.tie_start:
                _sub(note, "tie", type="start")
        _sub(note, "voice", e.voice)
        name, dots, _ = self._value(e)
        _sub(note, "type", name)
        for _ in range(dots):
            _sub(note, "dot")
        shown = self._accidental(p, b, e, state)
        if shown is not None:
            _sub(note, "accidental", shown)
        _time_modification(note, ratio)
        _staff(note, self.score.parts[p], e.staff)
        self._notations(note, e)
        for (number, text), (_, syllabic, extend) in zip(e.lyrics, e.syllables or [(None, "single", False)] * len(e.lyrics)):
            lyric = _sub(note, "lyric", number=number)
            _sub(lyric, "syllabic", syllabic)
            _sub(lyric, "text", " ".join(text.split()))   # spaces as the harness reads them
            if extend:
                _sub(lyric, "extend")
        return note

    def _accidental(self, p, b, e, state):
        """The accidental to print: where the pitch differs from the key and
        the accidentals earlier in the bar. A tied-over note prints none."""
        key = (e.pitch.step, e.pitch.octave)
        expected = state.get(key, events.key_alter(self.signatures.key(p, b), e.pitch.step))
        if e.tie_stop:
            return None
        if e.pitch.alter == expected:
            return None
        state[key] = e.pitch.alter
        return ACCIDENTALS.get(e.pitch.alter)

    def _notations(self, note, e):
        children = []
        # a cue note may not have a tie element, but may have tied notations
        for kind in ("stop", "start"):
            if (kind == "stop" and e.tie_stop) or (kind == "start" and e.tie_start):
                children.append(("tied", None, {"type": kind}))
        for kind, number in e.slurs:
            children.append(("slur", None, {"type": kind, "number": number}))
        groups = {"articulations": [], "ornaments": [], "technical": []}
        for mark in sorted(e.marks):
            group, _, name = mark.partition(" ")
            if mark == "fermata":
                children.append(("fermata", None, {"type": "upright"}))
            elif mark == "arpeggiate":
                children.append(("arpeggiate", None, {}))
            elif mark == "non-arpeggiate":
                children.append(("non-arpeggiate", None, {"type": "bottom"}))
            elif group + "s" in groups:
                groups[group + "s"].append(name)
            elif group == "technical":
                groups["technical"].append(name)
        existing = note.find("notations")
        if not children and not any(groups.values()):
            return
        notations = existing if existing is not None else _sub(note, "notations")
        for tag, text, attrs in children:
            _sub(notations, tag, text, **attrs)
        for group, names in groups.items():
            if names:
                holder = _sub(notations, group)
                for name in names:
                    # fingering and plucking letters: one element for each digit or letter read
                    for text in [t for k, t in e.fingering if k == name] or [None]:
                        _sub(holder, name, text)

    # --------------------------------------------------------------- items

    def _jump_words(self):
        """{id(navigation event): words marking, id(words marking): navigation
        event}: a jump (D.C., Fine) goes with the words the reader found for it,
        in its bar or the bar either side (words over a barline can be read
        into the next bar), so that no words are made up."""
        from omr.pdf import structure

        out = {}
        words = [m for m in self.score.markings if m.kind == "words"]
        for e in self.score.structure:
            if e.kind != "navigation" or e.value not in JUMP_SOUND:
                continue
            near = sorted((w for w in words if abs(w.bar - e.bar) <= 1 and id(w) not in out
                           and any(value == e.value and pattern.match(w.value)
                                   for pattern, value in structure.NAVIGATION_TEXT)),
                          key=lambda w: (abs(w.bar - e.bar), w.part != e.part, w.part))
            if near:
                out[id(e)] = near[0]
                out[id(near[0])] = e
        return out

    def _item(self, bar, item, jumps, offset, voice=None):
        if item.kind == "navigation" and id(item) in jumps:
            return   # written with its words
        if item.kind == "clef":
            attributes = _sub(bar.measure, "attributes")
            self._clef(attributes, item, self.score.parts[item.part].staves)
            return
        if item.kind == "chord symbol":
            self._harmony(bar, item, offset)
            return
        placement = "below" if item.kind in ("dynamic", "hairpin", "hairpin end") else "above"
        direction = _sub(bar.measure, "direction", placement=placement)
        kind = _sub(direction, "direction-type")
        sound = None
        if item.kind == "dynamic":
            dynamics = _sub(kind, "dynamics")
            if item.value in DYNAMICS:
                _sub(dynamics, item.value)
            else:
                _sub(dynamics, "other-dynamics", item.value)
        elif item.kind == "hairpin":
            _sub(kind, "wedge", type=item.value, number="1")
        elif item.kind == "hairpin end":
            _sub(kind, "wedge", type="stop", number=item.value or "1")
        elif item.kind == "words":
            _sub(kind, "words", item.value)
            jump = jumps.get(id(item))
            if jump is not None:
                sound = JUMP_SOUND[jump.value]
        elif item.kind == "rehearsal":
            _sub(kind, "rehearsal", item.value, enclosure="square")
        elif item.kind == "metronome":
            unit, _, per = item.value.partition(" = ")
            metronome = _sub(kind, "metronome")
            _sub(metronome, "beat-unit", unit.rstrip("."))
            if unit.endswith("."):
                _sub(metronome, "beat-unit-dot")
            _sub(metronome, "per-minute", per)
            try:
                name = unit.rstrip(".")
                quarters = events.TYPE_LENGTH.get(name, Fraction(1)) * (Fraction(3, 2) if unit.endswith(".") else 1)
                sound = ("tempo", _number(Fraction(per) * quarters))
            except (ValueError, ZeroDivisionError):
                pass
        elif item.kind == "navigation":
            if item.value in ("segno", "coda"):
                _sub(kind, item.value)
                sound = (item.value, item.value)
            else:
                _sub(kind, "words", JUMP_WORDS.get(item.value, item.value))
                sound = JUMP_SOUND.get(item.value)
        else:
            _sub(kind, "words", item.value)
        if offset:
            _sub(direction, "offset", bar.ticks(offset))
        if voice is not None:
            _sub(direction, "voice", voice)
        if item.staff is not None:
            _sub(direction, "staff", item.staff)
        if sound is not None:
            _sub(direction, "sound", **{sound[0]: sound[1]})

    def _harmony(self, bar, item, offset):
        from omr.pdf import text as pdf_text

        root, kind, bass = pdf_text.chord_kind(item.value)
        main = item.value.partition(" / ")[0]
        suffix = main.partition(" ")[2].strip()
        harmony = _sub(bar.measure, "harmony", placement="above")
        root_el = _sub(harmony, "root")
        step, alter = _root(root)
        _sub(root_el, "root-step", step)
        if alter:
            _sub(root_el, "root-alter", alter)
        if suffix in KINDS or not suffix:
            # "C major" is a C with nothing printed after it; a kind name is written as itself
            _sub(harmony, "kind", suffix or "major")
        else:
            _sub(harmony, "kind", kind if kind in KINDS else "other", text=suffix)
        if bass:
            step, alter = _root(bass)
            bass_el = _sub(harmony, "bass")
            _sub(bass_el, "bass-step", step)
            if alter:
                _sub(bass_el, "bass-alter", alter)
        if offset:
            _sub(harmony, "offset", bar.ticks(offset))
        if item.staff is not None:
            _sub(harmony, "staff", item.staff)


def _spans(evs):
    """[(start, end)] of a voice's chords; a grace note is a point."""
    out = []
    for g in _groups(evs):
        e = g[0]
        length = e.duration if isinstance(e.duration, Fraction) else Fraction(0)
        out.append((e.onset, e.onset + (0 if getattr(e, "grace", 0) else length), g))
    return out


def _fits(evs, into):
    """Whether `evs` can join the voice `into`: no chord of one overlaps a
    chord of the other, unless the two start and end together (they join as
    one chord; rests never do)."""
    for a0, a1, ga in _spans(evs):
        for b0, b1, gb in _spans(into):
            together = ((a0, a1) == (b0, b1) and not any(isinstance(e, events.Rest) for e in ga + gb)
                        and ga[0].value == gb[0].value and getattr(ga[0], "grace", 0) == getattr(gb[0], "grace", 0))
            if not together and a0 < b1 and b0 < a1:
                return False
            if not together and a0 == b0 and (a0 == a1 or b0 == b1):
                return False   # a grace note at the same onset as another chord
    return True


def _merge_voices(voices, staff):
    """Fold a staff's voices into at most MAX_VOICES (MuseScore takes four a
    staff and stops on a file with more): each chord of an extra voice joins
    the first kept voice it fits into. Returns the notes and rests that fit
    nowhere, which are not written. Only garbled bars have so many voices."""
    keys = sorted((k for k in voices if k[0] == staff), key=lambda k: _voice_number(k[1]))
    kept, extra = keys[:MAX_VOICES], keys[MAX_VOICES:]
    left_out = []
    for key in extra:
        for group in _groups(voices.pop(key)):
            target = next((k for k in kept if _fits(group, voices[k])), None)
            if target is None:
                left_out.extend(group)
            else:
                voices[target].extend(replace(e, voice=target[1]) for e in group)
    return left_out


# MusicXML's kind values
KINDS = {"major", "minor", "augmented", "diminished", "dominant", "major-seventh", "minor-seventh",
         "diminished-seventh", "augmented-seventh", "half-diminished", "major-minor", "major-sixth",
         "minor-sixth", "dominant-ninth", "major-ninth", "minor-ninth", "dominant-11th", "major-11th",
         "minor-11th", "dominant-13th", "major-13th", "minor-13th", "suspended-second",
         "suspended-fourth", "Neapolitan", "Italian", "French", "German", "pedal", "power", "Tristan",
         "other", "none"}


def _root(text):
    text = (text or "C").replace("♭", "b").replace("♯", "#")
    step = text[:1].upper() if text[:1].upper() in events.STEPS else "C"
    alter = text[1:].count("#") - text[1:].count("b")
    return step, alter


def _voice_number(voice):
    try:
        return int(voice)
    except ValueError:
        return 99


def _item_staff(item):
    return item.staff if item.staff is not None else 1


def _item_order(item):
    # clefs first, then directions, then chord symbols, as engravers write them
    rank = 0 if item.kind == "clef" else 2 if item.kind == "chord symbol" else 1
    return (item.onset, rank)


def _groups(evs):
    """The voice's events as chords, in time order: notes with the same onset,
    duration, value and grace order sound as one chord; grace notes come
    before the note they lead to."""
    groups = {}
    for e in evs:
        if isinstance(e, events.Rest):
            key = (e.onset, 1, 0, "rest", id(e))
        else:
            key = (e.onset, 0 if e.grace else 1, e.grace, e.duration, e.value)
        groups.setdefault(key, []).append(e)
    ordered = sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], str(kv[0][3:])))
    return [sorted(g, key=lambda n: getattr(n, "pitch", None) and n.pitch.sounding() or 0) for _, g in ordered]


def _tuplet_mark(note, kind):
    notations = note.find("notations")
    if notations is None:
        notations = ET.Element("notations")
        # notations come after the staff and beam elements, before lyrics
        lyrics = [i for i, child in enumerate(note) if child.tag == "lyric"]
        note.insert(lyrics[0] if lyrics else len(note), notations)
    if not any(t.get("type") == kind for t in notations.findall("tuplet")):
        _sub(notations, "tuplet", type=kind)


def _tuplet_unmark(note):
    """Take the start mark off an incomplete tuplet's first note."""
    notations = note.find("notations")
    for t in notations.findall("tuplet"):
        notations.remove(t)
    if not len(notations):
        note.remove(notations)


def _time_modification(note, ratio):
    if ratio is not None:
        tm = _sub(note, "time-modification")
        _sub(tm, "actual-notes", ratio[0])
        _sub(tm, "normal-notes", ratio[1])


def _staff(note, part, staff):
    if part.staves > 1:
        _sub(note, "staff", staff)


def _number(value):
    value = Fraction(value)
    return str(value.numerator) if value.denominator == 1 else f"{float(value):g}"


def to_string(score, title=None):
    return _document(Writer(score, title))


def _document(writer):
    root = writer.root()
    ET.indent(root, space=" ")
    return HEADER + ET.tostring(root, encoding="unicode") + "\n"


def write(score, path, title=None):
    """Write `score` to `path` as uncompressed MusicXML 4.0. Returns the
    notes and rests left out (see _merge_voices); normally none."""
    writer = Writer(score, title)
    text = _document(writer)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return writer.left_out


# ------------------------------------------------------------ round trip

def _items(score, merged=()):
    """What a round trip must keep, as counters by kind. Voices are not
    compared in the staff bars in `merged` (see _merge_voices)."""
    import collections

    def voice(e):
        return None if (e.part, e.bar, e.staff) in merged else e.voice

    def key(n):
        # a grace note's order is left out: the harness counts it from the last
        # note, not from a rest, so grace notes before a rest read back another order
        return n.key[:4] if n.grace else n.key

    # systems by their order on the page: MusicXML cannot skip a system number
    systems, previous = [], None
    for b in score.bars:
        rank = 1 if previous is None or b.page != previous.page else systems[-1] + (b.system != previous.system)
        systems.append(rank)
        previous = b

    return {
        "notes": collections.Counter(
            (n.part, n.staff, voice(n), n.bar, key(n), n.tie_start, n.tie_stop, n.cue, n.marks, n.slurs,
             tuple((k, " ".join(t.split())) for k, t in n.lyrics), n.syllables, n.fingering) for n in score.notes),
        "rests": collections.Counter((r.part, r.staff, voice(r), r.bar, r.key) for r in score.rests),
        # the kinds the harness reads (rehearsal and metronome marks are checked by scripts/check_convert.py)
        "markings": collections.Counter((m.kind, m.value, m.part, m.staff, m.bar, m.onset) for m in score.markings
                                        if m.kind in ("dynamic", "hairpin", "hairpin end", "words", "chord symbol")),
        "structure": collections.Counter(
            (e.kind, e.value, e.part, e.staff, e.bar, e.onset if e.kind == "clef" else None)
            for e in events.signature_changes(score) if e.kind != "navigation"),
        # a jump is written with its words, which may be a bar away
        "navigation": collections.Counter(e.value for e in score.structure if e.kind == "navigation"),
        # pages counted from the first bar's: MusicXML starts on the first page with music
        "bars": collections.Counter((k, b.number, b.page - score.bars[0].page, systems[k])
                                    for k, b in enumerate(score.bars)),
        "parts": collections.Counter((k, p.name.strip(), p.staves) for k, p in enumerate(score.parts)),
    }


def added_words(score):
    """[(bar, words)]: the words the writer adds for the jumps (D.C., Fine)
    the reader found with no words near them (JUMP_WORDS)."""
    paired = Writer(score).jumps
    return [(e.bar, JUMP_WORDS[e.value]) for e in score.structure
            if e.kind == "navigation" and e.value in JUMP_WORDS and id(e) not in paired]


def round_trip_differences(score, back):
    """{what: (lost, added)} between a Score and the Score read back from its
    MusicXML, each a list of items; empty when the round trip keeps
    everything. The words written for a jump the reader found with no words
    (JUMP_WORDS) are not counted as added."""
    jumps = set(added_words(score))
    writer = Writer(score)
    writer._sorted_events()
    out = {}
    before, after = _items(score, writer.merged), _items(back, writer.merged)
    not_written = _items(events.Score(parts=score.parts, notes=[e for e in writer.left_out if isinstance(e, events.Note)],
                                      rests=[e for e in writer.left_out if isinstance(e, events.Rest)]), writer.merged)
    for what in ("notes", "rests"):
        before[what] -= not_written[what]
    for what in before:
        lost = list((before[what] - after[what]).elements())
        added = [i for i in (after[what] - before[what]).elements()
                 if not (what == "markings" and i[0] == "words" and (i[4], i[1]) in jumps)]
        if lost or added:
            out[what] = (lost, added)
    return out
