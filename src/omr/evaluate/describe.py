"""Locations and musical things in words, for the reports (AX-2).

Locations use the ground truth's printed bar numbers and, where the ground
truth records its layout, the page and system, for example
"Bar 14 (page 2, system 3), Piano, right hand, beat 3".
"""

from fractions import Fraction

from omr.evaluate.events import TYPE_LENGTH

KEYBOARD_WORDS = ("piano", "pianoforte", "organ", "harpsichord", "keyboard", "celesta", "clavichord", "harmonium")
NAVIGATION_WORDS = {"dacapo": "D.C.", "dalsegno": "D.S.", "fine": "Fine", "tocoda": "To Coda",
                    "segno": "segno", "coda": "coda"}
VALUE_WORDS = {"16th": "sixteenth", "32nd": "thirty-second", "64th": "sixty-fourth", "128th": "128th"}


def fraction_words(value):
    """2 -> "2", 5/2 -> "2.5", 4/3 -> "1 and 1/3"."""
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    if value.denominator in (2, 4, 8, 16):
        return f"{float(value):g}"
    whole, part = divmod(value.numerator, value.denominator)
    rest = Fraction(part, value.denominator)
    return f"{whole} and {rest}" if whole else str(rest)


class Describer:
    def __init__(self, truth):
        self.truth = truth
        self.beat = {}
        current = Fraction(1)
        times = {}
        for event in truth.structure:
            if event.kind == "time" and event.part == 0:
                times.setdefault(event.bar, event.value)
        for bar in range(len(truth.bars)):
            if bar in times:
                try:
                    current = Fraction(4, int(times[bar].split("/")[1]))
                except (ValueError, IndexError, ZeroDivisionError):
                    pass
            self.beat[bar] = current

    def beat_length(self, bar):
        return self.beat.get(bar, Fraction(1))

    def part(self, part):
        if part is None or part >= len(self.truth.parts):
            return "an unknown part"
        name = self.truth.parts[part].name
        return name or f"part {part + 1}"

    def staff(self, part, staff):
        if part is None or part >= len(self.truth.parts) or staff is None:
            return ""
        count = self.truth.parts[part].staves
        if count == 1:
            return ""
        name = self.truth.parts[part].name.lower()
        if count == 2 and any(word in name for word in KEYBOARD_WORDS):
            return "right hand" if staff == 1 else "left hand"
        if count == 2:
            return "upper staff" if staff == 1 else "lower staff"
        return f"staff {staff}"

    def bar(self, bar):
        if bar is None or bar < 0 or bar >= len(self.truth.bars):
            return "an unknown bar"
        info = self.truth.bars[bar]
        number = info.number or f"at position {bar + 1}"
        if self.truth.bars[-1].page > 1 or self.truth.bars[-1].system > 1:
            return f"Bar {number} (page {info.page}, system {info.system})"
        return f"Bar {number}"

    def beat_words(self, bar, onset):
        return "beat " + fraction_words(1 + Fraction(onset) / self.beat_length(bar))

    def place(self, part, staff, bar, onset=None):
        pieces = [self.bar(bar)]
        if part is not None:
            pieces.append(self.part(part))
            staff_words = self.staff(part, staff)
            if staff_words:
                pieces.append(staff_words)
        if onset is not None:
            pieces.append(self.beat_words(bar, onset))
        return ", ".join(pieces)

    def key(self, fifths):
        n = int(fifths)
        if n == 0:
            return "no sharps or flats"
        kind = "sharp" if n > 0 else "flat"
        return f"{abs(n)} {kind}{'s' if abs(n) > 1 else ''}"

    def navigation(self, value):
        return NAVIGATION_WORDS.get(value, value)

    def marking(self, m):
        if m.kind == "dynamic":
            return f"dynamic {m.value}"
        if m.kind == "hairpin":
            return f"{m.value} hairpin"
        if m.kind == "hairpin end":
            return "end of a hairpin"
        if m.kind == "words":
            return f"text \"{m.value}\""
        return f"{m.kind} {m.value}"

    def value(self, note):
        base = note.value.rstrip(".")
        dots = len(note.value) - len(base)
        words = VALUE_WORDS.get(base, base) or "unknown value"
        if dots:
            words = ("dotted " if dots == 1 else "double-dotted " if dots == 2 else f"{dots}-dotted ") + words
        if note.grace:
            return f"{words} grace note"
        if base in TYPE_LENGTH:
            plain = TYPE_LENGTH[base] * (2 - Fraction(1, 2 ** dots))
            if plain and note.duration != plain:
                ratio = note.duration / plain
                return f"{'triplet ' if ratio == Fraction(2, 3) else ''}{words} note" + (
                    "" if ratio == Fraction(2, 3) else f" in a tuplet ({fraction_words(ratio)} of its usual length)")
        if not base:
            return f"note lasting {fraction_words(note.duration)} quarter notes"
        return f"{words} note"

    def note(self, note, onset=False, bar=None):
        text = f"{note.pitch.words()}, {self.value(note)}"
        if onset:
            text += f", at {self.beat_words(bar if bar is not None else note.bar, note.onset)}"
        return text
