"""Markings attached to the music (Stage 1.4): words, tempo marks, chord
symbols, rehearsal marks and dynamics as directions with a bar and an
onset; hairpins; and on the notes themselves articulations, fermatas,
ornaments, fingering, slurs and lyrics.

Called by omr.pdf.notation for each system once the notes have onsets. The
rules are in docs/notes/markings-spec.md.
"""

import collections
import re
from dataclasses import dataclass, field
from fractions import Fraction

from omr.evaluate import events
from omr.pdf import structure, text as tx

# SMuFL names (without "Above" or "Below") and the note marks they give,
# as the harness names them ("articulation accent", from MusicXML's
# <articulations><accent/>).
NOTE_MARKS = {
    "articAccent": ("articulation accent",),
    "articStaccato": ("articulation staccato",),
    "articStaccatissimo": ("articulation staccatissimo",),
    "articStaccatissimoWedge": ("articulation staccatissimo",),
    "articStaccatissimoStroke": ("articulation staccatissimo",),
    "articTenuto": ("articulation tenuto",),
    "articMarcato": ("articulation strong-accent",),
    "articTenutoStaccato": ("articulation detached-legato",),
    "articAccentStaccato": ("articulation accent", "articulation staccato"),
    "articMarcatoStaccato": ("articulation strong-accent", "articulation staccato"),
    "articTenutoAccent": ("articulation tenuto", "articulation accent"),
    "articStress": ("articulation stress",),
    "articUnstress": ("articulation unstress",),
    "fermata": ("fermata",), "fermataShort": ("fermata",), "fermataLong": ("fermata",),
    "fermataVeryShort": ("fermata",), "fermataVeryLong": ("fermata",),
    "ornamentTrill": ("ornament trill-mark",),
    "ornamentShortTrill": ("ornament inverted-mordent",),
    "ornamentMordent": ("ornament mordent",),
    "ornamentTremblement": ("ornament inverted-mordent",),
    "ornamentTurn": ("ornament turn",),
    "ornamentTurnInverted": ("ornament inverted-turn",),
    "ornamentTurnSlash": ("ornament vertical-turn",),
    "stringsUpBow": ("technical up-bow",),
    "stringsDownBow": ("technical down-bow",),
    "stringsHarmonic": ("technical harmonic",),
    "pluckedSnapPizzicato": ("technical snap-pizzicato",),
    "stringsThumbPosition": ("technical thumb-position",),
    "brassMuteOpen": ("technical open",),
    "brassMuteClosed": ("technical stopped",),
    "pluckedLeftHandPizzicato": ("technical stopped",),
}
BREATH_GLYPHS = ("breathMarkComma", "breathMarkTick", "breathMarkTickLike", "breathMarkSalzedo", "breathMarkUpbow")
CAESURA_GLYPHS = ("caesura", "caesuraThick", "caesuraShort", "caesuraCurved")
# dynamic glyphs and the letters they show
DYNAMIC_GLYPHS = {
    "dynamicPiano": "p", "dynamicMezzo": "m", "dynamicForte": "f", "dynamicRinforzando": "r",
    "dynamicSforzando": "s", "dynamicZ": "z", "dynamicNiente": "n", "dynamicPPPPPP": "pppppp",
    "dynamicPPPPP": "ppppp", "dynamicPPPP": "pppp", "dynamicPPP": "ppp", "dynamicPP": "pp", "dynamicMP": "mp",
    "dynamicMF": "mf", "dynamicPF": "pf", "dynamicFF": "ff", "dynamicFFF": "fff", "dynamicFFFF": "ffff",
    "dynamicFFFFF": "fffff", "dynamicFFFFFF": "ffffff", "dynamicFortePiano": "fp", "dynamicForzando": "fz",
    "dynamicSforzando1": "sf", "dynamicSforzandoPiano": "sfp", "dynamicSforzandoPianissimo": "sfpp",
    "dynamicSforzato": "sfz", "dynamicSforzatoPiano": "sfzp", "dynamicSforzatoFF": "sffz",
    "dynamicRinforzando1": "rf", "dynamicRinforzando2": "rfz",
}
# the dynamics MusicXML has an element for; others are <other-dynamics>
DYNAMIC_ELEMENTS = {"p", "pp", "ppp", "pppp", "ppppp", "pppppp", "f", "ff", "fff", "ffff", "fffff", "ffffff",
                    "mp", "mf", "sf", "sfp", "sfpp", "fp", "rf", "rfz", "sfz", "sffz", "fz", "n", "pf", "sfzp"}
MET_NOTES = {"metNoteDoubleWhole": "breve", "metNoteWhole": "whole", "metNoteHalfUp": "half",
             "metNoteHalfDown": "half", "metNoteQuarterUp": "quarter", "metNoteQuarterDown": "quarter",
             "metNote8thUp": "eighth", "metNote8thDown": "eighth", "metNote16thUp": "16th",
             "metNote16thDown": "16th"}


# words that are set with a dynamic as part of it
DYNAMIC_WORDS = {"più", "piu", "meno", "poco", "molto", "sempre", "subito", "sub.", "assai", "possibile"}


def _beside(box, boxes, space):
    """A box is next to another: on one line just before or after it, or
    stacked on it (MuseScore can set "più" over the p it goes with)."""
    return any(abs(tx.middle(box) - tx.middle(b)) <= 1.5 * space
               and max(b[0] - box[2], box[0] - b[2]) <= 1.2 * space for b in boxes)


def mark_base(name):
    return re.sub(r"(Above|Below|Turned)$", "", name)


@dataclass
class Extras:
    """What a chord gets beyond its notes: marks and slurs on its lowest
    note, lyrics, and marks on single noteheads (fingering)."""

    marks: set = field(default_factory=set)
    slurs: list = field(default_factory=list)       # ("start" or "stop", number)
    lyrics: list = field(default_factory=list)      # (verse, text, syllabic, extend)


# ------------------------------------------------------------- placing

class Placer:
    """Bar and onset for a place on a staff of a system: the column of
    notes and rests nearest to it in its bar."""

    def __init__(self, system, mapping, bar_base, evs):
        self.system = system
        self.bar_base = bar_base
        self.index = {id(st): k for k, st in enumerate(system.staves)}
        self.mapping = mapping
        self.by_bar = collections.defaultdict(list)       # (staff id, bar) -> events
        self.any_bar = collections.defaultdict(list)      # bar -> events
        for e in evs:
            if e.onset is None or e.grace:
                continue
            self.by_bar[(id(e.staff), e.bar)].append(e)
            self.any_bar[e.bar].append(e)

    def part_staff(self, staff):
        return self.mapping.staves[self.index[id(staff)]]

    def same_part(self, upper, lower):
        return self.part_staff(upper)[0] == self.part_staff(lower)[0]

    def staff_below(self, box):
        """The staff a dynamic or hairpin belongs to (omr.pdf.text.staff_for)."""
        return tx.staff_for(self.system, box, prefer="upper", same_part=self.same_part)[0]

    def bar_at(self, x):
        k = structure._bar_of(self.system, x)
        if k is None:
            bars = self.system.bars
            if not bars:
                return None
            k = len(bars) - 1 if x >= bars[-1].x0 else 0
        return k

    def place(self, x, staff, ref="left"):
        """(bar of the score, onset) for x on a staff. `ref` says which
        point of the events to compare with x: "left" (the left edge of the
        noteheads: words, chord symbols) or "centre" (their middle:
        dynamics, lyrics)."""
        k = self.bar_at(x)
        if k is None:
            return None
        candidates = self.by_bar.get((id(staff), k)) or self.any_bar.get(k)
        # text set a little left of the first note of a bar can start before its barline
        following = self.by_bar.get((id(staff), k + 1)) or self.any_bar.get(k + 1) or []
        following = [e for e in following if abs(_ref(e, ref) - x) <= 3 * staff.space]
        if not candidates and not following:
            return self.bar_base + k, Fraction(0)
        best = min(list(candidates or []) + following, key=lambda e: (abs(_ref(e, ref) - x), e.onset))
        return self.bar_base + best.bar, best.onset

    def end(self, x, staff):
        """(bar, onset) where something that stops at x ends: the onset of
        the first column at or after x in its bar, or the end of the bar's
        music if x is past the last column."""
        k = self.bar_at(x)
        if k is None:
            return None
        candidates = self.by_bar.get((id(staff), k)) or self.any_bar.get(k)
        if not candidates:
            return self.bar_base + k, Fraction(0)
        after = [e for e in candidates if _ref(e, "left") >= x - 0.5 * staff.space]
        if after:
            return self.bar_base + k, min(e.onset for e in after)
        return self.bar_base + k, max(e.onset + e.duration for e in candidates)


def _ref(e, ref):
    if e.rest is not None:
        box = e.rest.box
        return box[0] if ref == "left" else (box[0] + box[2]) / 2
    if ref == "left":
        return e.x
    return (min(h.box[0] for h in e.heads) + max(h.box[2] for h in e.heads)) / 2


def _chord_box(e):
    """(x0, y0, x1, y1) of a chord's noteheads and stem."""
    x0 = min(h.box[0] for h in e.heads)
    x1 = max(h.box[2] for h in e.heads)
    y0 = min(h.box[1] for h in e.heads)
    y1 = max(h.box[3] for h in e.heads)
    if e.stem is not None:
        x0, x1 = min(x0, e.stem.x), max(x1, e.stem.x)
        y0, y1 = min(y0, e.stem.top), max(y1, e.stem.bottom)
    return x0, y0, x1, y1


def _distance(box, x, y):
    dx = max(box[0] - x, 0, x - box[2])
    dy = max(box[1] - y, 0, y - box[3])
    return dx, dy


# ------------------------------------------------------------- the system

def read_system(score, pl, system, mapping, bar_base, evs, items, shapes, tie_curves, staccato_dots=()):
    """Add the system's directions to score.markings and return
    ({id(event): Extras}, {id(head): set of marks}) for the notes."""
    space = system.staves[0].space
    placer = Placer(system, mapping, bar_base, evs)
    chords = [e for e in evs if e.rest is None and e.heads and e.onset is not None]
    members = {id(st) for st in system.staves}
    extras = collections.defaultdict(Extras)
    head_marks = collections.defaultdict(set)

    def add(kind, value, staff, at, with_staff=True):
        if at is None:
            return
        part, number = placer.part_staff(staff)
        score.markings.append(events.Marking(kind, value, part, number if with_staff else None, at[0], at[1]))

    # ---- text
    dynamics = dynamic_groups(pl, system)
    dynamic_boxes = [box for _, box in dynamics] + [i.box for i in items if i.kind == "dynamic"]
    for item in items:
        if item.kind == "words" and item.text.lower() in DYNAMIC_WORDS and _beside(item.box, dynamic_boxes, space):
            # "più p": a word set with a dynamic is part of it (MusicXML's other-dynamics)
            staff = placer.staff_below(item.box)
            add("dynamic", item.text, staff, placer.place((item.box[0] + item.box[2]) / 2, staff, "centre"))
        elif item.kind in ("words", "tempo"):
            add("words", " ".join(item.text.split()), item.staff, placer.place(item.box[0], item.staff, "left"))
        elif item.kind == "chord symbol":
            add("chord symbol", item.value, item.staff, placer.place(item.box[0], item.staff, "left"))
        elif item.kind == "rehearsal":
            # a rehearsal mark stands over the barline at the start of its bar
            k = placer.bar_at(item.box[2] + 0.5 * space)
            if k is not None:
                add("rehearsal", item.text, item.staff, (bar_base + k, Fraction(0)), False)
        elif item.kind == "dynamic":
            staff = placer.staff_below(item.box)
            add("dynamic", item.text, staff, placer.place((item.box[0] + item.box[2]) / 2, staff, "centre"))
        elif item.kind == "metronome":
            unit = _metronome_unit(pl, item, space)
            add("metronome", f"{unit} = {item.text}", item.staff, placer.place(item.box[0], item.staff, "left"), False)
    # ---- dynamics drawn with music-font glyphs
    for value, box in dynamics:
        staff = placer.staff_below(box)
        add("dynamic", value, staff, placer.place((box[0] + box[2]) / 2, staff, "centre"))
    # ---- hairpins
    for kind, x0, x1, box, starts, ends in hairpins(shapes.thin, system):
        staff = placer.staff_below(box)
        if starts:
            add("hairpin", kind, staff, placer.place(x0, staff, "left"))
        if ends:
            add("hairpin end", "1", staff, placer.end(x1, staff))
    # ---- marks on notes
    by_staff = collections.defaultdict(list)
    for e in chords:
        by_staff[id(e.staff)].append(e)
    for s in pl.symbols:
        base = mark_base(s.name)
        marks = NOTE_MARKS.get(base)
        if marks is None and s.name in BREATH_GLYPHS:
            target = _breath_chord(s, chords, space, pl.staff_of(s))
            if target is not None:
                extras[id(target)].marks.add("articulation breath-mark")
            continue
        if marks is None and s.name in CAESURA_GLYPHS:
            target = _breath_chord(s, chords, space, pl.staff_of(s))
            if target is not None:
                extras[id(target)].marks.add("articulation caesura")
            continue
        if marks is None:
            continue
        staff = pl.staff_of(s)
        if staff is None or id(staff) not in members:
            continue
        reach = 1.6 if base.startswith(("fermata", "ornament")) else 1.1
        target = _marked_chord(s, chords, evs, space, reach, fermata=base.startswith("fermata"))
        if target is not None:
            extras[id(target)].marks.update(marks)
    for dot in staccato_dots:
        target = _marked_chord(dot, chords, evs, space, 0.8)
        if target is not None:
            extras[id(target)].marks.add("articulation staccato")
    # ---- fingering and plucking letters
    # fingering is text, or digits of a music font (fingering0 to fingering5)
    glyphs = [tx.TextItem("fingering", s.name[-1], s.box, pl.page, staff=pl.staff_of(s)) for s in pl.symbols
              if re.fullmatch(r"fingering[0-5]", s.name) and id(pl.staff_of(s)) in members]
    for kind, mark in (("fingering", "technical fingering"), ("pluck", "technical pluck")):
        found = [i for i in items if i.kind == kind] + (glyphs if kind == "fingering" else [])
        for head in _fingered_heads(found, chords, space):
            head_marks[id(head)].add(mark)
    # ---- slurs
    for c in shapes.curves:
        if id(c) in tie_curves or not _in_system(c.box, system, space):
            continue
        left, right = _slur_ends(c, chords, space)
        if left is None and right is None:
            continue
        if left is not None and right is not None and left is right:
            continue
        first_x = min((e.x for e in chords), default=system.x0)
        last_x = max((e.x for e in chords), default=system.x1)
        if left is None and c.left[0] > first_x + space:
            continue
        if right is None and c.right[0] < last_x - space:
            continue
        if left is not None:
            extras[id(left)].slurs.append(("start", "1"))
        if right is not None:
            extras[id(right)].slurs.append(("stop", "1"))
    # ---- lyrics
    taken = {}
    for item in sorted((i for i in items if i.kind == "lyric"), key=lambda i: i.box[0]):
        target = _lyric_chord(item, by_staff.get(id(item.staff), []), space)
        if target is None:
            continue
        key = (id(target), item.verse)
        if key in taken:
            continue
        taken[key] = item
        extras[id(target)].lyrics.append((item.verse, item.text, item.syllabic, item.extend))
    return extras, head_marks


def _in_system(box, system, space):
    return (system.x0 - space <= box[0] <= system.x1 + space
            and system.staves[0].top - 8 * space <= box[1] <= system.staves[-1].bottom + 8 * space)


def _metronome_unit(pl, item, space):
    notes = [s for s in pl.symbols if s.name in MET_NOTES and abs(s.box[2] - item.box[0]) < 3 * space
             and s.box[1] - space <= tx.middle(item.box) <= s.box[3] + space]
    if not notes:
        return "quarter"
    note = max(notes, key=lambda s: s.box[2])
    unit = MET_NOTES[note.name]
    dots = [s for s in pl.symbols if s.name in ("metAugmentationDot", "augmentationDot")
            and note.box[2] - 0.2 * space <= s.box[0] <= item.box[0]]
    return unit + ("." if dots else "")


# ------------------------------------------------------------- dynamics

def dynamic_groups(pl, system):
    """[(value, box)]: runs of dynamic glyphs side by side on one line,
    read as one dynamic ("m" and "f" make "mf")."""
    space = system.staves[0].space
    glyphs = sorted((s for s in pl.symbols if s.name in DYNAMIC_GLYPHS and _in_system(s.box, system, space)
                     and tx.system_of(pl, s.box) is system), key=lambda s: s.box[0])
    groups = []
    for s in glyphs:
        for g in groups:
            last = g[-1]
            # on one baseline; letters overlap where the font kerns them (m and f)
            if abs(last.y - s.y) <= 0.3 * space and -1.0 * space <= s.box[0] - last.box[2] <= 0.6 * space:
                g.append(s)
                break
        else:
            groups.append([s])
    out = []
    for g in groups:
        value = "".join(DYNAMIC_GLYPHS[s.name] for s in g)
        box = (min(s.box[0] for s in g), min(s.box[1] for s in g), max(s.box[2] for s in g), max(s.box[3] for s in g))
        out.append((value, box))
    return out


# ------------------------------------------------------------- hairpins

def hairpins(thin, system):
    """[(kind, x0, x1, box, starts, ends)]: hairpins of the system, from
    pairs of thin lines that meet at one end and open at the other (or,
    for a hairpin carried over a system break, that are closer at one end).
    `starts` is False for the continuation of a hairpin from the system
    before; `ends` is False for one that runs on to the next system."""
    space = system.staves[0].space
    top = system.staves[0].top - 8 * space
    bottom = system.staves[-1].bottom + 8 * space
    lines = [l for l in thin if system.x0 - space <= l[0] <= system.x1 + space and top <= l[1] <= bottom
             and l[2] - l[0] >= 1.5 * space and abs(l[3] - l[1]) <= 0.4 * (l[2] - l[0])]
    used = set()
    found = []
    for i, a in enumerate(lines):
        if i in used:
            continue
        for j in range(i + 1, len(lines)):
            b = lines[j]
            if j in used or abs(a[0] - b[0]) > 0.4 * space or abs(a[2] - b[2]) > 0.4 * space:
                continue
            gap0, gap1 = abs(a[1] - b[1]), abs(a[3] - b[3])
            narrow, wide = min(gap0, gap1), max(gap0, gap1)
            if not (0.4 * space <= wide <= 3 * space and wide - narrow >= 0.35 * space):
                continue
            if narrow > 0.25 * space and not (a[0] <= system.x0 + 4 * space or a[2] >= system.x1 - 2 * space):
                continue
            kind = "crescendo" if gap0 < gap1 else "diminuendo"
            x0, x1 = min(a[0], b[0]), max(a[2], b[2])
            box = (x0, min(a[1], a[3], b[1], b[3]), x1, max(a[1], a[3], b[1], b[3]))
            starts, ends = True, True
            # a continuation: no point where it starts (crescendo) or ends
            if kind == "crescendo" and narrow > 0.25 * space:
                starts = False
            if kind == "diminuendo" and narrow > 0.25 * space:
                ends = False
            if kind == "crescendo" and x1 >= system.x1 - 1.5 * space and wide < 0.9 * space:
                ends = False
            if kind == "diminuendo" and x0 <= system.x0 + 4 * space and wide < 0.9 * space:
                starts = False
            used.update((i, j))
            found.append((kind, x0, x1, box, starts, ends))
            break
    return found


# ------------------------------------------------------------- note marks

def _marked_chord(symbol, chords, evs, space, reach, fermata=False):
    """The chord a mark above or below a note belongs to: centred over its
    noteheads (within `reach` staff spaces), the nearest vertically. None
    if the nearest such event is a rest (a fermata over a rest)."""
    cx, cy = (symbol.box[0] + symbol.box[2]) / 2, tx.middle(symbol.box)
    best, best_d = None, None
    for e in evs:
        if e.onset is None:
            continue
        if e.rest is not None:
            box = e.rest.box
        else:
            box = _chord_box(e)
        hx = (box[0] + box[2]) / 2 if e.rest is not None else _ref(e, "centre")
        if abs(hx - cx) > reach * space:
            continue
        _, dy = _distance(box, cx, cy)
        if dy > (8 if fermata else 4) * space:
            continue
        d = dy + 2 * abs(hx - cx)
        if best_d is None or d < best_d:
            best, best_d = e, d
    if best is None or best.rest is not None:
        return None
    return best


def _breath_chord(symbol, chords, space, staff=None):
    """A breath mark or caesura belongs to the chord before it, on the
    staff it stands on if it stands on one."""
    cx, cy = (symbol.box[0] + symbol.box[2]) / 2, tx.middle(symbol.box)
    before = [e for e in chords if _chord_box(e)[2] <= cx + 0.2 * space and cx - _chord_box(e)[2] <= 8 * space
              and _distance(_chord_box(e), cx, cy)[1] <= 6 * space and e.staff.top - 6 * space <= cy <= e.staff.bottom + 2 * space
              and (staff is None or e.staff is staff)]
    if not before:
        return None
    return max(before, key=lambda e: (_chord_box(e)[2], -abs(e.staff.middle - cy)))


def _fingered_heads(found, chords, space):
    """The noteheads that fingering digits (or plucking letters) belong to.
    Digits stacked over or under a chord go to its notes in the same order,
    from the note nearest the digits; a digit just left of a notehead goes
    to that notehead."""
    out = []
    by_chord = collections.defaultdict(list)
    for item in found:
        cx, cy = (item.box[0] + item.box[2]) / 2, tx.middle(item.box)
        beside = [h for e in chords if e.staff is item.staff for h in e.heads
                  if 0 <= h.box[0] - item.box[2] <= 2.5 * space and abs(h.y - cy) <= 0.8 * space]
        if beside:
            out.append(min(beside, key=lambda h: h.box[0] - item.box[2]))
            continue
        over = [e for e in chords if e.staff is item.staff and abs(_ref(e, "centre") - cx) <= 1.2 * space
                and _distance(_chord_box(e), cx, cy)[1] <= 8 * space]
        if over:
            e = min(over, key=lambda e: (abs(_ref(e, "centre") - cx), _distance(_chord_box(e), cx, cy)[1]))
            by_chord[id(e)].append((item, e))
    for pairs in by_chord.values():
        e = pairs[0][1]
        heads = sorted(e.heads, key=lambda h: h.y)
        middle_y = (heads[0].y + heads[-1].y) / 2
        above = sorted((i for i, _ in pairs if tx.middle(i.box) < middle_y), key=lambda i: tx.middle(i.box))
        below = sorted((i for i, _ in pairs if tx.middle(i.box) >= middle_y), key=lambda i: -tx.middle(i.box))
        # digits over the chord: the lowest digit is the top note's, and so on down
        for n, _ in enumerate(reversed(above)):
            out.append(heads[min(n, len(heads) - 1)])
        for n, _ in enumerate(reversed(below)):
            out.append(heads[max(len(heads) - 1 - n, 0)])
    return out


def _slur_ends(curve, chords, space):
    """The chords at the two ends of a curve, or None at an end with none."""
    def at(point, side):
        best, best_d = None, None
        for e in chords:
            box = _chord_box(e)
            dx, dy = _distance(box, *point)
            if dx > 1.5 * space or dy > 2.5 * space:
                continue
            # the left end of a slur is at or right of its first note's left edge
            if side == "left" and point[0] > box[2] + 1.5 * space:
                continue
            d = 2 * dx + dy
            if best_d is None or d < best_d:
                best, best_d = e, d
        return best
    left = at(curve.left, "left")
    right = at(curve.right, "right")
    if left is not None and right is not None and _chord_box(right)[0] <= _chord_box(left)[0]:
        return None, None
    return left, right


def _lyric_chord(item, chords, space):
    cx = (item.box[0] + item.box[2]) / 2
    best, best_d = None, None
    for e in chords:
        if e.grace:
            continue
        d = min(abs(_ref(e, "centre") - cx), abs(e.x - item.box[0]))
        if d > 2.5 * space:
            continue
        key = (round(d / (0.3 * space)), -e.direction)
        if best_d is None or key < best_d:
            best, best_d = e, key
    return best
