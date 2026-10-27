"""Read a MusicXML file into the events the harness compares.

The rules are in docs/notes/evaluation-spec.md, "Reading a MusicXML file into
events". Every position is an exact fraction of a quarter note, measured from
the start of the bar. Bars are counted in written order, repeats not expanded.
"""

import bisect
import collections
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path

# Notated length of each note type, in quarter notes.
TYPE_LENGTH = {
    "maxima": Fraction(32), "long": Fraction(16), "breve": Fraction(8), "whole": Fraction(4),
    "half": Fraction(2), "quarter": Fraction(1), "eighth": Fraction(1, 2), "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8), "64th": Fraction(1, 16), "128th": Fraction(1, 32),
    "256th": Fraction(1, 64), "512th": Fraction(1, 128), "1024th": Fraction(1, 256),
}
WHOLE_BAR = "whole bar"  # the duration of a whole-bar rest
SIGNATURE_KINDS = ("clef", "key", "time")
NAVIGATION_SOUNDS = ("dacapo", "dalsegno", "fine", "tocoda")
# Jump words, as the PDF reader finds them (omr.pdf.structure uses this list).
NAVIGATION_TEXT = (
    (re.compile(r"^\s*D\.?\s*S\.?", re.I), "dalsegno"),
    (re.compile(r"^\s*D\.?\s*C\.?|^\s*da\s+capo", re.I), "dacapo"),
    (re.compile(r"^\s*to\s+coda", re.I), "tocoda"),
    (re.compile(r"^\s*fine\s*$", re.I), "fine"),
)
# The sign typed as words: Unicode, and the music font's own characters (SMuFL),
# which MuseScore writes.
NAVIGATION_SIGNS = {"\U0001D10B": "segno", "\U0001D10C": "coda", "": "segno", "": "segno",
                    "": "coda", "": "coda"}
MARKUP = re.compile(r"<[^>]*>")   # formatting tags left in words, such as <font size="17">

STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
STEPS = "CDEFGAB"
SHARP_ORDER = "FCGDAEB"   # the order of sharps in a key signature; flats go the other way
CLEF_REFERENCE = {"G": ("G", 4, 2), "F": ("F", 3, 4), "C": ("C", 4, 3)}   # pitch on the clef's line, usual line


class MusicXMLError(ValueError):
    """The file cannot be read as MusicXML. The message says why."""


@dataclass(frozen=True)
class Pitch:
    step: str
    alter: Fraction
    octave: int

    def sounding(self):
        """The pitch in semitones (MIDI numbering), which ignores spelling."""
        return (self.octave + 1) * 12 + STEP_SEMITONES[self.step] + self.alter

    def words(self):
        names = {Fraction(-2): " double flat", Fraction(-1): " flat", Fraction(0): "",
                 Fraction(1): " sharp", Fraction(2): " double sharp"}
        accidental = names.get(self.alter, f" altered by {float(self.alter):g} semitones")
        return f"{self.step}{accidental} {self.octave}"


@dataclass(frozen=True)
class Note:
    """One visible notehead. `key` is what note accuracy compares."""

    part: int            # position of the part, from 0
    staff: int           # staff within the part, from 1
    voice: str
    bar: int             # position of the bar, from 0
    onset: Fraction      # quarter notes from the start of the bar
    pitch: Pitch
    duration: Fraction   # notated length in quarter notes (0 for a grace note)
    value: str           # notated type and dots, for example "eighth." (used for grace notes and reports)
    grace: int = 0       # 0, or the grace note's order before its main note (1, 2, ...)
    tie_start: bool = False
    tie_stop: bool = False
    cue: bool = False
    marks: frozenset = frozenset()   # articulations, fermata, ornaments, arpeggiate
    slurs: tuple = ()                # ("start" or "stop", number) pairs
    lyrics: tuple = ()               # (number, text) pairs
    syllables: tuple = ()            # (number, syllabic, extend) for each lyric; not compared
    fingering: tuple = ()            # ("fingering" or "pluck", text) pairs; not compared

    @property
    def key(self):
        if self.grace:
            return (self.onset, self.pitch, "grace", self.value, self.grace)
        return (self.onset, self.pitch, self.duration)


@dataclass(frozen=True)
class Rest:
    part: int
    staff: int
    voice: str
    bar: int
    onset: Fraction
    duration: object     # Fraction, or WHOLE_BAR

    @property
    def key(self):
        return ("rest", self.onset, self.duration)


@dataclass(frozen=True)
class Marking:
    """A dynamic, hairpin, text direction or chord symbol, or a structure event."""

    kind: str            # "dynamic", "hairpin", "hairpin end", "words", "chord symbol", "clef", ...
    value: str
    part: int
    staff: int | None
    bar: int
    onset: Fraction


@dataclass
class Bar:
    number: str          # the printed number (the `number` attribute)
    page: int
    system: int
    length: Fraction = Fraction(0)   # how far the bar's content reaches


@dataclass
class Part:
    name: str
    staves: int


@dataclass(frozen=True)
class Flag:
    """A bar that may be wrong: a doubt the PDF reader noted while reading,
    or a rule it fails (omr.pdf.rules)."""
    part: int            # from 0
    staff: int | None    # from 1, or None for the whole part
    bar: int             # from 0, in score order
    rule: str
    reason: str
    onset: Fraction | None = None   # quarter notes from the start of the bar, when known


@dataclass
class Score:
    parts: list = field(default_factory=list)
    bars: list = field(default_factory=list)       # from the first part
    notes: list = field(default_factory=list)
    rests: list = field(default_factory=list)
    markings: list = field(default_factory=list)   # performance markings and text
    structure: list = field(default_factory=list)  # clefs, keys, times, repeats, endings, navigation
    bar_counts: list = field(default_factory=list) # bars in each part, normally all equal
    text: list = field(default_factory=list)       # page text (title, composer, ...) read from a PDF; not compared
    doubts: list = field(default_factory=list)     # doubts noted while reading a PDF (Flag); not compared
    hidden_first_bar: bool = False                 # bar 1 cannot be seen on the page (decision 17)

    def staves(self):
        """Every staff in score order, as (part, staff) pairs."""
        return [(p, s) for p, part in enumerate(self.parts) for s in range(1, part.staves + 1)]


def read_root(path):
    """The root element of a .musicxml, .xml or compressed .mxl file."""
    path = Path(path)
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                names = [n for n in z.namelist()
                         if n.lower().endswith((".xml", ".musicxml")) and not n.startswith("META-INF")]
                if not names:
                    raise MusicXMLError("the compressed file holds no MusicXML")
                return ET.fromstring(z.read(names[0]))
        return ET.parse(path).getroot()
    except ET.ParseError as error:
        raise MusicXMLError(f"the file is not well-formed XML: {error}")
    except OSError as error:
        raise MusicXMLError(f"the file could not be read: {error}")


def read(path):
    """Read a MusicXML file into a Score."""
    return from_root(read_root(path))


def from_root(root):
    """Read a parsed MusicXML root element into a Score."""
    if root.tag == "score-timewise":
        raise MusicXMLError("timewise MusicXML is not supported; convert it to partwise first")
    if root.tag != "score-partwise":
        raise MusicXMLError(f"the root element is {root.tag!r}, not score-partwise")
    names = {sp.get("id"): (sp.findtext("part-name") or "").strip() for sp in root.iter("score-part")}
    score = Score()
    parts = root.findall("part")
    if not parts:
        raise MusicXMLError("the file has no parts")
    for index, part in enumerate(parts):
        _read_part(score, index, names.get(part.get("id"), ""), part)
    navigation_from_words(score)
    score.hidden_first_bar = _hidden_first_bar(parts)
    return score


def _hidden_first_bar(parts):
    """Whether the first measure of every part holds only hidden rests (or
    nothing) and draws no barline at its end, and a second measure follows:
    a bar the page does not show (decision 17)."""
    for part in parts:
        measures = part.findall("measure")
        if len(measures) < 2:
            return False
        first = measures[0]
        if any(n.find("rest") is None or n.get("print-object") != "no" for n in first.findall("note")):
            return False
        right = [b for b in first.findall("barline") if b.get("location", "right") == "right"]
        if not right or any(b.findtext("bar-style") != "none" for b in right):
            return False
    return True


def with_ending_ends_alike(score):
    """`score` with each ending's end read as "stop", with or without its
    closing hook ("discontinue"): engravers choose the hook (spec decision 16)."""
    if not any(e.kind == "ending" and e.value.startswith("discontinue") for e in score.structure):
        return score
    return replace(score, structure=[
        replace(e, value="stop" + e.value[len("discontinue"):])
        if e.kind == "ending" and e.value.startswith("discontinue") else e for e in score.structure])


def without_hidden_first_bar(score):
    """`score` with a first bar the page does not show joined to the next
    (spec decision 17). What was in it (clef, key, time, words, chord
    symbols) goes to the start of the next bar."""
    if not score.hidden_first_bar or len(score.bars) < 2:
        return score

    def moved(items):
        return [replace(e, bar=e.bar - 1) if e.bar else replace(e, onset=Fraction(0)) for e in items]

    return replace(
        score, bars=score.bars[1:], notes=moved(score.notes), rests=moved(score.rests),
        markings=moved(score.markings), structure=moved(score.structure),
        bar_counts=[max(count - 1, 0) for count in score.bar_counts], hidden_first_bar=False)


def navigation_value(text):
    """The navigation mark that words stand for, or None."""
    text = MARKUP.sub("", text).strip()
    if text in NAVIGATION_SIGNS:
        return NAVIGATION_SIGNS[text]
    return next((value for pattern, value in NAVIGATION_TEXT if pattern.match(text)), None)


def navigation_from_words(score):
    """Jump words and signs written only as words are navigation marks (cause 17
    in docs/notes/error-triage.md), one for each time they are printed, as the
    PDF reader reads them. Words beside a mark of the same value in the same
    part and bar (D.C. with its sound) add nothing."""
    marked = collections.Counter((e.part, e.bar, e.value) for e in score.structure if e.kind == "navigation")
    for m in score.markings:
        if m.kind != "words":
            continue
        value = navigation_value(m.value)
        if not value:
            continue
        if marked[(m.part, m.bar, value)]:
            marked[(m.part, m.bar, value)] -= 1
        else:
            score.structure.append(Marking("navigation", value, m.part, None, m.bar, m.onset))


def without_trailing_empty_bars(score):
    """`score` without the bars after its last note (spec decision 14). Those
    bars hold only rests or nothing in every part, and an engraver may leave
    them off the page (Verovio hides a system whose staves are all empty).
    Everything in them goes too. A score with no notes is kept whole."""
    if not score.notes:
        return score
    kept = max(n.bar for n in score.notes) + 1
    if len(score.bars) <= kept and all(count <= kept for count in score.bar_counts):
        return score
    return replace(
        score, bars=score.bars[:kept], rests=[r for r in score.rests if r.bar < kept],
        markings=[m for m in score.markings if m.bar < kept],
        structure=[e for e in score.structure if e.bar < kept],
        bar_counts=[min(count, kept) for count in score.bar_counts])


def restated(score):
    """The clef, key and time signature events of `score` that restate the value
    already in force, in the same part and staff (spec decision 11). A key
    signature with no staff number applies to every staff of its part."""
    found = []
    in_force = {}    # (kind, part) -> {staff or None: value}
    signatures = [e for e in score.structure if e.kind in SIGNATURE_KINDS]
    for e in sorted(signatures, key=lambda e: (e.part, e.bar, e.onset)):
        state = in_force.setdefault((e.kind, e.part), {})
        if e.staff is None:
            staves = range(1, score.parts[e.part].staves + 1) if e.part < len(score.parts) else [1]
            if all(state.get(s, state.get(None)) == e.value for s in staves):
                found.append(e)
            state.clear()
            state[None] = e.value
        else:
            if state.get(e.staff, state.get(None)) == e.value:
                found.append(e)
            state[e.staff] = e.value
    return found


def signature_changes(score):
    """The structure events with restated clefs, keys and times left out."""
    restatements = collections.Counter(restated(score))
    kept = []
    for e in score.structure:
        if restatements[e]:
            restatements[e] -= 1
        else:
            kept.append(e)
    return kept


class SignaturesInForce:
    """The key and the time signature in force in each part at any bar,
    from the score's structure as it stands when this is made: each lookup
    is a bisection, not a scan of the whole structure. Where a part has two
    of a kind at one bar, the later in the structure counts."""

    def __init__(self, score):
        by_bar = {}    # (kind, part) -> {bar: value}
        for e in score.structure:
            if e.kind in ("key", "time"):
                by_bar.setdefault((e.kind, e.part), {})[e.bar] = e.value
        self._starts = {where: sorted(values) for where, values in by_bar.items()}
        self._values = {where: [by_bar[where][b] for b in starts] for where, starts in self._starts.items()}

    def _value(self, kind, part, bar):
        starts = self._starts.get((kind, part), ())
        k = bisect.bisect_right(starts, bar)
        return self._values[(kind, part)][k - 1] if k else None

    def key(self, part, bar):
        """The fifths of the key signature in force, 0 if there is none."""
        value = self._value("key", part, bar)
        return int(value) if value is not None else 0

    def time(self, part, bar):
        """The text of the time signature in force, such as "6/8", or None."""
        return self._value("time", part, bar)


def clef_bottom(value):
    """The diatonic number (step + 7 * octave) of the bottom staff line under
    a clef value such as "G 2" or "F 4 octave -1", or None for a clef with no
    pitch (percussion, tablature)."""
    bits = value.split()
    if not bits or bits[0] not in CLEF_REFERENCE:
        return None
    step, octave, usual_line = CLEF_REFERENCE[bits[0]]
    line = int(bits[1]) if len(bits) > 1 and bits[1].isdigit() else usual_line
    change = int(bits[3]) if len(bits) > 3 and bits[2] == "octave" else 0
    return STEPS.index(step) + 7 * (octave + change) - 2 * (line - 1)


def key_alter(fifths, step):
    """The alteration a key signature of so many fifths gives a letter."""
    if fifths > 0 and step in SHARP_ORDER[:fifths]:
        return Fraction(1)
    if fifths < 0 and step in SHARP_ORDER[::-1][:-fifths]:
        return Fraction(-1)
    return Fraction(0)


# printed chord suffixes and the MusicXML kind they stand for
CHORD_KINDS = {
    "": "major", "major": "major", "M": "major", "maj": "major", "Δ": "major",
    "m": "minor", "min": "minor", "mi": "minor", "-": "minor",
    "7": "dominant", "maj7": "major-seventh", "Maj7": "major-seventh", "M7": "major-seventh",
    "ma7": "major-seventh", "Δ7": "major-seventh", "^7": "major-seventh",
    "m7": "minor-seventh", "min7": "minor-seventh", "mi7": "minor-seventh", "-7": "minor-seventh",
    "dim": "diminished", "°": "diminished", "o": "diminished",
    "dim7": "diminished-seventh", "°7": "diminished-seventh", "o7": "diminished-seventh",
    "m7b5": "half-diminished", "m7(b5)": "half-diminished", "-7(b5)": "half-diminished", "-7b5": "half-diminished",
    "ø": "half-diminished", "ø7": "half-diminished",
    "aug": "augmented", "+": "augmented", "aug7": "augmented-seventh", "+7": "augmented-seventh",
    "7#5": "augmented-seventh", "6": "major-sixth", "m6": "minor-sixth", "-6": "minor-sixth",
    "9": "dominant-ninth", "maj9": "major-ninth", "Δ9": "major-ninth", "m9": "minor-ninth", "-9": "minor-ninth",
    "11": "dominant-11th", "m11": "minor-11th", "-11": "minor-11th", "13": "dominant-13th",
    "maj13": "major-13th", "m13": "minor-13th", "sus4": "suspended-fourth", "sus": "suspended-fourth",
    "sus2": "suspended-second", "5": "power", "mmaj7": "major-minor", "mMaj7": "major-minor",
    "m(maj7)": "major-minor", "mΔ7": "major-minor", "-Δ7": "major-minor", "mM7": "major-minor",
}


def chord_kind(value):
    """(root, MusicXML kind, bass) of a chord symbol in the harness's words
    ("A m7" gives ("A", "minor-seventh", None)); the kind is None for a
    suffix not in CHORD_KINDS (the MusicXML writer then writes it as printed)."""
    main, _, bass = value.partition(" / ")
    root, _, suffix = main.partition(" ")
    return (root, CHORD_KINDS.get(suffix.strip(), suffix.strip() if "-" in suffix and suffix.islower() else None),
            bass or None)


def _number(text, default=0):
    try:
        return Fraction(text.strip()) if text and text.strip() else Fraction(default)
    except (ValueError, ZeroDivisionError):
        return Fraction(default)


def _notated(note, divisions, duration):
    """(length in quarter notes, value text) from type, dots and time modification."""
    kind = note.findtext("type")
    dots = len(note.findall("dot"))
    if kind and kind.strip() in TYPE_LENGTH:
        base = TYPE_LENGTH[kind.strip()]
        length = base * (2 - Fraction(1, 2 ** dots))
        modification = note.find("time-modification")
        if modification is not None:
            actual = _number(modification.findtext("actual-notes"), 1)
            normal = _number(modification.findtext("normal-notes"), 1)
            if actual and normal:
                length = length * normal / actual
        return length, kind.strip() + "." * dots
    return duration / divisions if divisions else Fraction(0), ""


def _middle_barlines(measure, divisions):
    """The positions of the barlines drawn inside the bar (location "middle"),
    in order. Only those strictly inside the bar's content count."""
    found = []
    position = reach = Fraction(0)
    for element in measure:
        tag = element.tag
        if tag == "attributes":
            divisions = _number(element.findtext("divisions"), divisions) or divisions
        elif tag == "backup":
            position -= _number(element.findtext("duration")) / divisions
        elif tag == "forward":
            position += _number(element.findtext("duration")) / divisions
        elif tag == "note" and element.find("chord") is None and element.find("grace") is None:
            position += _number(element.findtext("duration")) / divisions
        elif tag == "barline" and element.get("location") == "middle":
            found.append(position)
        reach = max(reach, position)
    return sorted({p for p in found if 0 < p < reach})


def _read_part(score, part_index, name, part):
    divisions = 1
    staves = 1
    page, system = 1, 1
    first_part = part_index == 0
    bar_index = 0
    for measure in part.findall("measure"):
        # A barline in the middle of the bar starts a new bar (cause 16 in
        # docs/notes/error-triage.md): the page cannot tell it from a bar end.
        cuts = _middle_barlines(measure, divisions)
        starts = [Fraction(0)] + cuts

        def place(at):
            """(bar index, position from that bar's start) for a position in the measure."""
            piece = bisect.bisect_right(cuts, at)
            return bar_index + piece, at - starts[piece]

        grace_count = {}    # voice -> grace notes seen in this bar since its last main note
        position = Fraction(0)
        last_onset = Fraction(0)
        reach = [Fraction(0)] * len(starts)
        for element in measure:
            tag = element.tag
            if tag == "print" and first_part:
                if element.get("new-page") == "yes" and bar_index > 0:
                    page, system = page + 1, 1
                elif element.get("new-system") == "yes" and bar_index > 0:
                    system += 1
            elif tag == "attributes":
                divisions = _number(element.findtext("divisions"), divisions) or divisions
                staves = max(staves, int(_number(element.findtext("staves"), 1)))
                _read_attributes(score, part_index, *place(position), element)
            elif tag == "backup":
                position -= _number(element.findtext("duration")) / divisions
            elif tag == "forward":
                piece = place(position)[0] - bar_index
                position += _number(element.findtext("duration")) / divisions
                reach[piece] = max(reach[piece], position - starts[piece])
            elif tag == "note":
                duration = _number(element.findtext("duration"))
                is_chord = element.find("chord") is not None
                onset = last_onset if is_chord else position
                if not is_chord:
                    last_onset = position
                    if element.find("grace") is None:
                        position += duration / divisions
                bar, start = place(onset)
                piece = bar - bar_index
                reach[piece] = max(reach[piece], position - starts[piece])
                if element.get("print-object") != "no":
                    _read_note(score, part_index, bar, start, divisions, duration, element, grace_count)
            elif tag == "direction":
                _read_direction(score, part_index, *place(position), divisions, element)
            elif tag == "harmony":
                _read_harmony(score, part_index, *place(position), divisions, element)
            elif tag == "barline":
                _read_barline(score, part_index, *place(position), element)
        for piece, length in enumerate(reach):
            if first_part:
                number = measure.get("number", "")
                if piece:
                    number += " after its middle barline" + (f" {piece}" if len(cuts) > 1 else "")
                score.bars.append(Bar(number, page, system, length))
            elif bar_index < len(score.bars):
                score.bars[bar_index].length = max(score.bars[bar_index].length, length)
            bar_index += 1
    score.parts.append(Part(name, staves))
    score.bar_counts.append(bar_index)


def _step(text):
    step = (text or "").strip()
    if step not in STEP_SEMITONES:
        raise MusicXMLError(f"a note has the step {step!r}; a step must be one of A to G")
    return step


def _whole_number(text, what, default=None):
    """An integer attribute or element, or a plain error if it is not one."""
    if text is None or not text.strip():
        return default
    try:
        return int(text.strip())
    except ValueError:
        raise MusicXMLError(f"{what} is {text.strip()!r}, not a whole number")


def _read_note(score, part_index, bar_index, onset, divisions, duration, element, grace_count):
    staff = int(_number(element.findtext("staff"), 1))
    voice = (element.findtext("voice") or "1").strip()
    if element.find("rest") is not None:
        rest = element.find("rest")
        kind = element.findtext("type")
        if rest.get("measure") == "yes" or not kind:
            length = WHOLE_BAR
        else:
            length, _ = _notated(element, divisions, duration)
        score.rests.append(Rest(part_index, staff, voice, bar_index, onset, length))
        return
    pitch_element = element.find("pitch")
    if pitch_element is not None:
        pitch = Pitch(_step(pitch_element.findtext("step")), _number(pitch_element.findtext("alter")),
                      int(_number(pitch_element.findtext("octave"), 4)))
    else:
        unpitched = element.find("unpitched")
        if unpitched is None:
            return
        pitch = Pitch(_step(unpitched.findtext("display-step", "C")), Fraction(0),
                      int(_number(unpitched.findtext("display-octave"), 4)))
    length, value = _notated(element, divisions, duration)
    grace = 0
    if element.find("grace") is not None:
        if element.find("chord") is None:
            grace_count[voice] = grace_count.get(voice, 0) + 1
        grace = max(grace_count.get(voice, 1), 1)
        length = Fraction(0)
    elif element.find("chord") is None:
        grace_count[voice] = 0
    ties = {t.get("type") for t in element.findall("tie")}
    marks, slurs, fingering = set(), [], []
    for notations in element.findall("notations"):
        for child in notations:
            if child.tag in ("articulations", "ornaments", "technical"):
                marks.update(f"{child.tag[:-1] if child.tag.endswith('s') else child.tag} {m.tag}" for m in child)
                fingering.extend((m.tag, (m.text or "").strip()) for m in child
                                 if m.tag in ("fingering", "pluck") and (m.text or "").strip())
            elif child.tag in ("fermata", "arpeggiate", "non-arpeggiate"):
                marks.add(child.tag)
            elif child.tag == "slur" and child.get("type") in ("start", "stop"):
                slurs.append((child.get("type"), child.get("number", "1")))
            elif child.tag == "tied":
                ties.add(child.get("type"))
            elif child.tag == "dynamics":
                for dynamic in child:
                    score.markings.append(Marking("dynamic", _dynamic_text(dynamic), part_index, staff, bar_index, onset))
    lyrics = tuple((ly.get("number", "1"), " ".join("".join(t.text or "" for t in ly.findall("text")).split()))
                   for ly in element.findall("lyric"))
    syllables = tuple((ly.get("number", "1"), (ly.findtext("syllabic") or "single").strip(),
                       ly.find("extend") is not None) for ly in element.findall("lyric"))
    score.notes.append(Note(
        part_index, staff, voice, bar_index, onset, pitch, length, value, grace,
        "start" in ties, "stop" in ties, element.find("cue") is not None or
        (element.find("type") is not None and element.find("type").get("size") == "cue"),
        frozenset(marks), tuple(slurs), lyrics, syllables, tuple(fingering)))


def _dynamic_text(element):
    if element.tag == "other-dynamics":
        return (element.text or "").strip()
    return element.tag


def _offset(element, divisions):
    return _number(element.findtext("offset")) / divisions if divisions else Fraction(0)


def _staff_of(element):
    text = element.findtext("staff")
    return int(_number(text)) if text else None


def _read_direction(score, part_index, bar_index, position, divisions, element):
    onset = position + _offset(element, divisions)
    staff = _staff_of(element)
    for kind in element.findall("direction-type"):
        for child in kind:
            if child.tag == "dynamics":
                for dynamic in child:
                    score.markings.append(Marking("dynamic", _dynamic_text(dynamic), part_index, staff, bar_index, onset))
            elif child.tag == "wedge":
                wedge = child.get("type")
                if wedge in ("crescendo", "diminuendo"):
                    score.markings.append(Marking("hairpin", wedge, part_index, staff, bar_index, onset))
                elif wedge == "stop":
                    score.markings.append(Marking("hairpin end", child.get("number", "1"), part_index, staff, bar_index, onset))
            elif child.tag == "words" and (child.text or "").strip():
                score.markings.append(Marking("words", " ".join(child.text.split()), part_index, staff, bar_index, onset))
            elif child.tag in ("segno", "coda"):
                score.structure.append(Marking("navigation", child.tag, part_index, None, bar_index, onset))
    sound = element.find("sound")
    if sound is not None:
        for name in NAVIGATION_SOUNDS:
            if sound.get(name):
                score.structure.append(Marking("navigation", name, part_index, None, bar_index, onset))


def _read_harmony(score, part_index, bar_index, position, divisions, element):
    root = element.find("root")
    if root is None:
        return
    alter = int(_number(root.findtext("root-alter")))
    text = root.findtext("root-step", "").strip() + {-1: "b", 1: "#"}.get(alter, "")
    kind = element.find("kind")
    if kind is not None:
        text += " " + (kind.get("text") if kind.get("text") is not None else (kind.text or "").strip())
    bass = element.find("bass")
    if bass is not None:
        text += " / " + bass.findtext("bass-step", "").strip()
    score.markings.append(Marking("chord symbol", text.strip(), part_index, _staff_of(element),
                                  bar_index, position + _offset(element, divisions)))


def _read_attributes(score, part_index, bar_index, position, element):
    for clef in element.findall("clef"):
        value = f"{clef.findtext('sign', '').strip()} {clef.findtext('line', '').strip()}".strip()
        change = int(_number(clef.findtext("clef-octave-change")))
        if change:
            value += f" octave {change:+d}"
        staff = _whole_number(clef.get("number"), "a clef number", 1)
        score.structure.append(Marking("clef", value, part_index, staff, bar_index, position))
    for key in element.findall("key"):
        if key.findtext("fifths") is not None:
            staff = _whole_number(key.get("number"), "a key signature's staff number")
            fifths = _whole_number(key.findtext("fifths"), "a key signature's fifths value", 0)
            score.structure.append(Marking("key", str(fifths), part_index, staff, bar_index, position))
    for time in element.findall("time"):
        if time.findtext("beats") is not None:
            value = f"{time.findtext('beats').strip()}/{time.findtext('beat-type', '').strip()}"
            score.structure.append(Marking("time", value, part_index, None, bar_index, position))
            if time.get("symbol") in ("common", "cut"):
                score.markings.append(Marking("time symbol", time.get("symbol"), part_index, None, bar_index, position))


def _read_barline(score, part_index, bar_index, position, element):
    repeat = element.find("repeat")
    if repeat is not None:
        # The play count (times) is not compared: no engraver prints it (decision 15).
        score.structure.append(Marking("repeat", repeat.get("direction", ""), part_index, None, bar_index, position))
    ending = element.find("ending")
    if ending is not None:
        value = f"{ending.get('type', '')} {' '.join((ending.get('number') or '').replace(',', ' ').split())}"
        score.structure.append(Marking("ending", value.strip(), part_index, None, bar_index, position))
    for name in ("segno", "coda"):
        if element.find(name) is not None:
            score.structure.append(Marking("navigation", name, part_index, None, bar_index, position))
