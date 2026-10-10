"""Notes and rests from the page layouts (Stage 1.3): pitch, duration, onset
and voice, built from the symbols of Stage 1.1, the staves and bars of Stage
1.2, and the page's stems and beams.

The rules are in docs/notes/notation-spec.md. In short:

1. Stems are the vertical lines that touch a notehead at one end (the
   noteheads at the stem's right edge for a stem up, at its left edge for a
   stem down). Beams are filled four-sided shapes about half a staff space
   thick. A chord is a stem and the noteheads on it; noteheads with no stem
   (whole notes) at the same place are one chord.
2. A chord's notated value is its notehead (whole, half, black) halved for
   each beam or flag on its stem, and lengthened by its dots. A tuplet
   number over a bracket or a beam group scales the values under it.
3. A note or rest starts where the voice it continues ends. Events that
   stand one above the other on a staff start together (a column). Each
   column starts at the earliest end of the events before it, preferring an
   event with the same stem direction (or, for a rest, the same side of the
   staff), which keeps two voices apart.
4. Pitch comes from the staff step, the clef in force, the key signature of
   the part, and the accidentals already in the bar on that staff.

The result fills the notes and rests of the Score from omr.pdf.structure,
so the evaluation harness can compare it with a ground truth directly.
"""

import collections
import re
import statistics
from dataclasses import dataclass, field, replace
from fractions import Fraction

from omr.evaluate import events
from omr.pdf import evidence, layout as lay, structure

FLAG_COUNT = {f"flag{name}{way}": n for n, name in enumerate(
    ("8th", "16th", "32nd", "64th", "128th", "256th", "512th", "1024th"), 1) for way in ("Up", "Down")}
REST_LENGTH = {
    "restLonga": Fraction(16), "restDoubleWhole": Fraction(8), "restWhole": Fraction(4),
    "restWholeLegerLine": Fraction(4), "restHalf": Fraction(2), "restHalfLegerLine": Fraction(2),
    "restQuarter": Fraction(1), "rest8th": Fraction(1, 2), "rest16th": Fraction(1, 4),
    "rest32nd": Fraction(1, 8), "rest64th": Fraction(1, 16), "rest128th": Fraction(1, 32),
}
TYPE_NAME = {length: name for name, length in events.TYPE_LENGTH.items()}
TUPLET_GLYPHS = {f"tuplet{i}": str(i) for i in range(10)}
TUPLET_TEXT = re.compile(r"^\s*(\d{1,2})\s*(?::\s*(\d{1,2}))?\s*$")
LETTERS = "CDEFGAB"
BOTTOM_LINE = {"G": (2, 4), "F": (4, 2), "C": (0, 4)}    # sign: (letter of the bottom line on line 1 clef..., octave)


def is_head(name):
    return lay.is_note(name) or name.startswith("noteShape")


def head_kind(name):
    if "DoubleWhole" in name:
        return Fraction(8)
    if "Whole" in name:
        return Fraction(4)
    if "Half" in name:
        return Fraction(2)
    return Fraction(1)


def accidental_alter(name):
    if not name.startswith("accidental"):
        return None
    for key, alter in (("DoubleSharp", 2), ("SharpSharp", 2), ("DoubleFlat", -2), ("FlatFlat", -2),
                       ("NaturalSharp", 1), ("NaturalFlat", -1), ("Sharp", 1), ("Flat", -1), ("Natural", 0)):
        if key in name and "Quarter" not in name and "Three" not in name:
            return Fraction(alter)
    return None


# ------------------------------------------------------------ primitives

@dataclass
class Beam:
    x0: float
    x1: float
    y0: float      # middle of the beam at x0
    y1: float      # middle of the beam at x1
    thickness: float

    def y_at(self, x):
        if self.x1 - self.x0 < 0.01:
            return self.y0
        return self.y0 + (self.y1 - self.y0) * (x - self.x0) / (self.x1 - self.x0)


@dataclass
class Stem:
    x: float
    top: float
    bottom: float
    heads: list = field(default_factory=list)
    up: bool = True
    beams: list = field(default_factory=list)
    flags: int = 0

    @property
    def free_end(self):
        return self.top if self.up else self.bottom


@dataclass
class Head:
    symbol: object
    staff: object
    step: int
    small: bool
    stem: Stem | None = None
    accidental: Fraction | None = None

    @property
    def x(self):
        return self.symbol.x

    @property
    def y(self):
        return self.symbol.y

    @property
    def box(self):
        return self.symbol.box


@dataclass
class Event:
    """A chord (noteheads on one stem, or stemless noteheads together) or a rest."""

    staff: object
    x: float                 # left edge of the noteheads on the normal side of the stem, or of the rest
    right: float             # right edge of the ink, for dots
    heads: list = field(default_factory=list)
    rest: object = None      # the rest Symbol
    stem: Stem | None = None
    base: Fraction = Fraction(1)   # notated value before dots and tuplets
    dots: int = 0
    tuplet: tuple | None = None    # (actual, normal)
    small: bool = False
    grace: bool = False
    whole_bar: bool = False
    direction: int = 0       # +1 stem up (or a raised rest), -1 stem down (or a lowered rest), 0 neither
    onset: Fraction | None = None
    voice: int = 0
    bar: int = 0             # bar of the system

    @property
    def value(self):
        return self.base * (2 - Fraction(1, 2 ** self.dots))

    @property
    def duration(self):
        length = self.value
        if self.tuplet:
            length = length * self.tuplet[1] / self.tuplet[0]
        return length


def _subpaths(items):
    """The closed pieces of a filled path, as point lists."""
    out, current, last = [], [], None
    for item in items:
        kind = item[0]
        if kind == "re":
            r = item[1]
            out.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)])
            continue
        if kind == "qu":
            q = item[1]
            out.append([(p.x, p.y) for p in (q.ul, q.ur, q.lr, q.ll)])
            continue
        if kind != "l":
            return None
        p1, p2 = (item[1].x, item[1].y), (item[2].x, item[2].y)
        if last is None or abs(p1[0] - last[0]) > 0.05 or abs(p1[1] - last[1]) > 0.05:
            if current:
                out.append(current)
            current = [p1]
        current.append(p2)
        last = p2
    if current:
        out.append(current)
    return out


def _quad_beam(points, space):
    """A beam from a filled four-sided shape with upright ends, or None."""
    xs = [p[0] for p in points]
    x0, x1 = min(xs), max(xs)
    width = x1 - x0
    if width < 0.6 * space:
        return None
    left = [p[1] for p in points if abs(p[0] - x0) < 0.3]
    right = [p[1] for p in points if abs(p[0] - x1) < 0.3]
    if len(left) < 2 or len(right) < 2 or len(left) + len(right) < len(set(points)) - 1:
        return None
    t0, t1 = max(left) - min(left), max(right) - min(right)
    if not (0.25 * space <= t0 <= 0.9 * space and 0.25 * space <= t1 <= 0.9 * space):
        return None
    if abs(t0 - t1) > 0.3 * max(t0, t1):
        return None
    m0, m1 = (max(left) + min(left)) / 2, (max(right) + min(right)) / 2
    if abs(m1 - m0) > width:
        return None
    return Beam(x0, x1, m0, m1, (t0 + t1) / 2)


@dataclass
class Curve:
    """A tie or slur: its left and right ends. `level` if the ends are
    level (only those can be ties)."""

    left: tuple
    right: tuple
    box: tuple
    level: bool = True


@dataclass
class Shapes:
    """The drawn shapes of a page that Stages 1.3 and 1.4 read."""

    beams: list
    curves: list         # every curve (ties and slurs)
    dashed: list
    thin: list
    frames: list = field(default_factory=list)     # (x0, y0, x1, y1) of small stroked boxes
    hyphens: list = field(default_factory=list)    # (y, x0, x1) of short level lines

    @property
    def level_curves(self):
        return [c for c in self.curves if c.level]


def page_shapes(page, space):
    """The Shapes of the page, as the page is shown. Beams are filled
    four-sided shapes with upright ends, about half a staff space thick
    (rectangles for level beams), and thick stroked lines. Curves are
    shapes drawn with curves, at least one and a half staff spaces wide and
    flat, whose two ends are level (ties, and slurs between notes at one
    height). Dashed lines are level stroked lines drawn with a dash
    pattern, as (y, x0, x1): the lines of octave marks. Thin lines are
    stroked lines, level or sloping, as (x0, y0, x1, y1) left to right:
    among them the halves of tuplet brackets and of hairpins. Frames are
    small stroked boxes (round rehearsal marks); hyphens are short level
    lines (lyric hyphens and extenders, which can also be filled)."""
    turn = evidence._display_turn(page)
    found = {}
    curves = {}
    dashed = []
    thin = []
    frames = []
    hyphens = []
    for d in page.get_drawings():
        items = d["items"]
        if turn is not None:
            items = [(item[0], *(part * turn if hasattr(part, "transform") else part for part in item[1:]))
                     for item in items]
        rect = d["rect"] * turn if turn is not None else d["rect"]
        if "s" in d["type"] and "f" not in d["type"] and 1.2 * space <= rect.width <= 10 * space                 and 1.2 * space <= rect.height <= 5 * space and len(items) <= 12:
            frames.append((rect.x0, rect.y0, rect.x1, rect.y1))
        if rect.height <= 0.3 * space and 0.3 * space <= rect.width <= 40 * space and len(items) <= 4                 and not any(item[0] == "c" for item in items):
            hyphens.append(((rect.y0 + rect.y1) / 2, rect.x0, rect.x1))
        if any(item[0] == "c" for item in items):
            curve = _curve(items, space)
            if curve:
                curves[tuple(round(v, 1) for v in curve.box)] = curve
            continue
        if "f" in d["type"]:
            for points in _subpaths(items) or []:
                beam = _quad_beam(points, space)
                if beam:
                    found[(round(beam.x0, 1), round(beam.y0, 1), round(beam.x1, 1))] = beam
        width = d.get("width") or 0.0
        if "s" in d["type"] and (d.get("dashes") or "[] 0").replace(" ", "") not in ("[]0", ""):
            for item in items:
                if item[0] == "l" and abs(item[1].y - item[2].y) < 0.5 and abs(item[1].x - item[2].x) > 0.5:
                    dashed.append(((item[1].y + item[2].y) / 2, min(item[1].x, item[2].x), max(item[1].x, item[2].x)))
            continue
        if "s" in d["type"] and width < 0.25 * space:
            for item in items:
                if item[0] != "l":
                    continue
                (x0, y0), (x1, y1) = sorted(((item[1].x, item[1].y), (item[2].x, item[2].y)))
                # long sloping lines are kept too: the arms of a long hairpin
                if (0.5 * space <= x1 - x0 <= 30 * space or (x1 - x0 <= 100 * space and abs(y1 - y0) >= 0.1 * space)) \
                        and abs(y1 - y0) <= x1 - x0:
                    thin.append((x0, y0, x1, y1))
        if "s" in d["type"] and 0.25 * space <= width <= 0.9 * space:
            for item in items:
                if item[0] != "l":
                    continue
                p1, p2 = sorted(((item[1].x, item[1].y), (item[2].x, item[2].y)))
                if p2[0] - p1[0] >= 0.6 * space and abs(p2[1] - p1[1]) <= p2[0] - p1[0]:
                    beam = Beam(p1[0], p2[0], p1[1], p2[1], width)
                    found[(round(beam.x0, 1), round(beam.y0, 1), round(beam.x1, 1))] = beam
    return Shapes(list(found.values()), list(curves.values()), dashed, thin, frames, hyphens)


def _curve(items, space):
    """A curve at least 0.8 staff spaces wide and flat (a slur from a grace
    note can be that short). It is level, and can be a tie, if it is at
    least one and a half staff spaces wide and its ends are within three
    quarters of a staff space in height."""
    points = [p for item in items for p in evidence._item_points(item)]
    x0, y0, x1, y1 = evidence._bbox(points)
    width, height = x1 - x0, y1 - y0
    if width < 0.8 * space or height > 0.5 * width + space or height < 0.1 * space:
        return None
    left = min(points, key=lambda p: (p[0], p[1]))
    right = max(points, key=lambda p: (p[0], -p[1]))
    return Curve(left, right, (x0, y0, x1, y1), width >= 1.5 * space and abs(left[1] - right[1]) <= 0.75 * space)


# ----------------------------------------------------------------- chords

def _small_heads(heads):
    """Mark grace and cue noteheads. A font glyph is small when its size is
    clearly under the four staff spaces of a music font at full size. An
    outline has no font size, so its ink is compared with the usual ink of
    noteheads of the same shape on the page (heads of different shapes
    differ in height)."""
    heights = collections.defaultdict(list)
    for h in heads:
        heights[h.symbol.name].append(h.box[3] - h.box[1])
    usual = {name: statistics.median(v) for name, v in heights.items()}
    for h in heads:
        if h.symbol.source != "outline":
            h.small = h.symbol.size < 0.85 * 4 * h.staff.space
        else:
            h.small = h.box[3] - h.box[1] < 0.85 * usual[h.symbol.name]


def find_stems(verticals, heads, space, barline_xs):
    """Stems: vertical lines with a notehead at one end, the line at the
    notehead's right edge (stem up) or left edge (stem down). Every notehead
    touching the line along its length joins the stem (a chord)."""
    seen = set()
    stems = []
    by_x = sorted(heads, key=lambda h: h.box[0])
    for x, top, bottom, width in verticals:
        if width > 0.3 * space or bottom - top < 1.0 * space:
            continue
        key = (round(x, 1), round(top, 1), round(bottom, 1))
        if key in seen or any(abs(x - bx) < 0.3 for bx in barline_xs):
            continue
        seen.add(key)
        touching = []
        for h in by_x:
            if h.box[0] > x + 0.5 * space:
                break
            if not (top - 0.6 * space <= h.y <= bottom + 0.6 * space):
                continue
            tolerance = 0.3 * space * (0.7 if h.small else 1.0)
            if abs(h.box[2] - x) <= tolerance or abs(h.box[0] - x) <= tolerance:
                touching.append(h)
        if not touching:
            continue
        ys = [h.y for h in touching]
        above, below = min(ys) - top, bottom - max(ys)
        if max(above, below) < 0.8 * space:
            continue     # no free end: not a stem
        stem = Stem(x, top, bottom, touching, up=above > below)
        stems.append(stem)
    _share_heads(stems, space)
    for stem in stems:
        for h in stem.heads:
            h.stem = stem
    return [s for s in stems if s.heads]


def _share_heads(stems, space):
    """Settle noteheads that touch more than one stem. Identical noteheads
    drawn one on another (a unison in two voices) go to different stems. A
    single notehead at the end of a stem up and of a stem down is shared by
    both voices. Otherwise a notehead keeps the stem it ends."""
    touching = collections.defaultdict(list)
    for stem in stems:
        for h in stem.heads:
            touching[id(h)].append(stem)
    heads = {id(h): h for stem in stems for h in stem.heads}
    keep = collections.defaultdict(set)    # id(stem) -> ids of heads kept
    placed = collections.defaultdict(list)
    for h in heads.values():
        placed[(h.symbol.name, round(h.x, 1), round(h.y, 1))].append(h)
    for same in placed.values():
        candidates = []
        for stem in touching[id(same[0])]:
            if stem not in candidates:
                candidates.append(stem)
        for h in same[1:]:
            for stem in touching[id(h)]:
                if stem not in candidates:
                    candidates.append(stem)
        ends = [s for s in candidates if abs(same[0].y - (s.bottom if s.up else s.top)) <= 0.6 * space]
        # on the usual side: left of a stem up, right of a stem down
        usual = [s for s in ends if _usual_side(same[0], s, space)]
        if len(same) > 1 and len(ends) > 1:
            order = usual + [s for s in ends if s not in usual]
            for k, h in enumerate(same):
                keep[id(order[min(k, len(order) - 1)])].add(id(h))
            continue
        for h in same:
            if len(usual) > 1 and {s.up for s in usual} == {True, False}:
                for s in usual:
                    keep[id(s)].add(id(h))
            else:
                chosen = min(usual or ends or candidates, key=lambda s: abs(h.y - (s.bottom if s.up else s.top)))
                keep[id(chosen)].add(id(h))
    for stem in stems:
        stem.heads = [h for h in stem.heads if id(h) in keep[id(stem)]]


def hidden_stems(heads, stems, beams, space, verticals=()):
    """Stems for noteheads whose stem is not drawn (an engraver can hide
    one) but which a beam starts or ends at: the beam's end at the
    notehead's right edge above it (a stem up) or at its left edge below it
    (a stem down). A notehead that already has a stem the other way is
    shared by two voices (a unison drawn once), so the hidden stem gets a
    copy of it."""
    out = []
    for h in list(heads):
        if head_kind(h.symbol.name) > 2:
            continue
        for b in beams:
            found = None
            for x in (b.x0, b.x1):
                y = b.y_at(x)
                reach = 10 * space if h.stem is None else 5 * space
                up = abs(x - h.box[2]) <= 0.4 * space and h.y - reach < y < h.y - space
                down = abs(x - h.box[0]) <= 0.4 * space and h.y + space < y < h.y + reach
                if not (up or down) or (h.stem is not None and h.stem.up == up):
                    continue
                # a second note on a notehead with its own stem: the open
                # notehead a half note and a shorter note share
                if h.stem is not None and head_kind(h.symbol.name) != 2:
                    continue
                if any(abs(s.x - x) <= 0.4 * space and s.top <= y + 0.5 * space
                       and s.bottom >= y - 0.5 * space for s in stems + out):
                    continue
                # a second note on a notehead that has its own stem only
                # where no line at all is drawn at the beam's end
                if h.stem is not None and any(abs(vx - x) <= 0.6 * space and top <= y + 0.5 * space
                                              and bottom >= y - 0.5 * space for vx, top, bottom, _ in verticals):
                    continue
                found = (x, y, up)
                break
            if found:
                x, y, up = found
                head = h
                if h.stem is not None:
                    head = Head(h.symbol, h.staff, h.step, h.small)
                stem = Stem(x, min(y, h.y), max(y, h.y), [head], up=up)
                head.stem = stem
                out.append(stem)
                break
    return out


def _usual_side(head, stem, space):
    edge = head.box[2] if stem.up else head.box[0]
    return abs(edge - stem.x) <= 0.3 * space


def attach_beams(stems, beams, space):
    """The beams through each stem, away from its noteheads. A beam must
    end at a stem at one end at least: the strokes of a tremolo float
    between or across stems and are not beams."""
    def anchored(b, x):
        return any(abs(s.x - x) <= 0.4 * space and s.top - 0.4 * space <= b.y_at(x) <= s.bottom + 0.4 * space
                   for s in stems)
    beams = [b for b in beams if anchored(b, b.x0) or anchored(b, b.x1)]
    for stem in stems:
        reach = (stem.top - 0.4 * space, stem.bottom + 0.4 * space)
        for b in beams:
            if not (b.x0 - 0.3 * space <= stem.x <= b.x1 + 0.3 * space):
                continue
            y = b.y_at(min(max(stem.x, b.x0), b.x1))
            if reach[0] <= y <= reach[1]:
                # not at the noteheads' end
                heads_y = [h.y for h in stem.heads]
                if stem.up and y > min(heads_y) - 0.5 * space:
                    continue
                if not stem.up and y < max(heads_y) + 0.5 * space:
                    continue
                stem.beams.append(b)


def attach_flags(stems, flags, space):
    """Each flag to the stem whose free end it is at. Returns the flags no
    stem took."""
    left = []
    for flag in flags:
        best, best_d = None, None
        for stem in stems:
            if abs(flag.x - stem.x) > 0.6 * space:
                continue
            d = abs(flag.y - stem.free_end)
            if d <= 1.5 * space and (best_d is None or d < best_d):
                best, best_d = stem, d
        if best is not None:
            best.flags = max(best.flags, FLAG_COUNT[flag.name])
        else:
            left.append(flag)
    return left


def make_chords(heads, stems, space):
    """Events for the stems and for stemless noteheads."""
    out = []
    for stem in stems:
        normal = [h for h in stem.heads if (h.box[2] <= stem.x + 0.35 * space) == stem.up] or stem.heads
        kind = min(head_kind(h.symbol.name) for h in stem.heads)
        strokes = len(_beam_levels(stem, space)) + stem.flags
        # beams and flags decide (a beamed note with an open notehead is still
        # a sixteenth); a stem with neither takes the notehead's value
        base = Fraction(1, 2 ** strokes) if strokes else kind
        e = Event(stem.heads[0].staff, min(h.box[0] for h in normal), max(h.box[2] for h in stem.heads),
                  heads=list(stem.heads), stem=stem, base=base, small=all(h.small for h in stem.heads),
                  direction=1 if stem.up else -1)
        out.append(e)
    loose = sorted((h for h in heads if h.stem is None), key=lambda h: h.box[0])
    groups = []
    for h in loose:
        for g in groups:
            if g[0].staff is h.staff and abs(g[0].box[0] - h.box[0]) <= 0.5 * space:
                g.append(h)
                break
        else:
            groups.append([h])
    for g in groups:
        out.append(Event(g[0].staff, min(h.box[0] for h in g), max(h.box[2] for h in g), heads=g,
                         base=max(head_kind(h.symbol.name) for h in g), small=all(h.small for h in g)))
    for e in out:
        steps = collections.Counter(id(h.staff) for h in e.heads)
        if len(steps) > 1:   # a chord across two staves belongs to the staff of most of its noteheads
            e.staff = next(h.staff for h in e.heads if id(h.staff) == steps.most_common(1)[0][0])
    return out


def _beam_levels(stem, space):
    """Distinct beams on a stem (two shapes at one height are one beam)."""
    levels = []
    for b in sorted(stem.beams, key=lambda b: b.y_at(stem.x)):
        y = b.y_at(stem.x)
        if not levels or abs(y - levels[-1]) > 0.35 * space:
            levels.append(y)
    return levels


def make_rests(symbols, layout, space):
    out = []
    for s in symbols:
        if s.name not in REST_LENGTH:
            continue
        staff = layout.staff_of(s)
        if staff is None:
            continue
        middle = (s.box[1] + s.box[3]) / 2
        offset = (staff.middle - middle) / staff.space
        direction = 1 if offset >= 1.5 else -1 if offset <= -1.5 else 0
        out.append(Event(staff, s.box[0], s.box[2], rest=s, base=REST_LENGTH[s.name], direction=direction))
    return out


def attach_dots(evs, dots, space, repeat_zones):
    """Augmentation dots: right of a notehead or rest, level with it (a note
    on a line has its dot in the space above or below)."""
    by_event = collections.defaultdict(list)
    used = set()
    for d in dots:
        cx, cy = (d.box[0] + d.box[2]) / 2, (d.box[1] + d.box[3]) / 2
        if any(a <= cx <= b for a, b in repeat_zones):
            continue
        best, best_dx = None, None
        for e in evs:
            dx = d.box[0] - e.right
            if not (-0.2 * space <= dx <= 3.0 * space):
                continue
            if e.rest is not None:
                level = e.rest.box[1] - 0.3 * space <= cy <= e.rest.box[3] + 0.3 * space
            else:
                level = any(abs(cy - h.y) <= 0.65 * space for h in e.heads)
            if level and (best_dx is None or dx < best_dx):
                best, best_dx = e, dx
        if best is not None:
            by_event[id(best)].append(cx)
            used.add(id(d))
    for e in evs:
        xs = sorted(by_event.get(id(e), []))
        columns = 0
        last = None
        for x in xs:
            if last is None or x - last > 0.3 * space:
                columns += 1
                last = x
        e.dots = min(columns, 3)
    return used


def staccato_dots(dots, evs, space):
    """Dots that are not augmentation dots and stand over or under a
    notehead, clear of it: staccato marks drawn as plain dots (outlined
    music, where a staccato dot cannot be told from an augmentation dot by
    its shape)."""
    out = []
    for d in dots:
        cx, cy = (d.box[0] + d.box[2]) / 2, (d.box[1] + d.box[3]) / 2
        if any(e.rest is None and any(h.box[0] - 0.1 * space <= cx <= h.box[2] + 0.1 * space
                                      and 0.6 * space <= abs(cy - h.y) <= 2.6 * space for h in e.heads)
               for e in evs):
            out.append(d)
    return out


# ---------------------------------------------------------------- tuplets

@dataclass
class TupletMark:
    actual: int
    normal: int | None
    x: float
    y: float
    box: tuple


def tuplet_marks(page_layout):
    out = []
    for s in page_layout.symbols:
        if s.name in TUPLET_GLYPHS:
            out.append(TupletMark(int(TUPLET_GLYPHS[s.name]), None, (s.box[0] + s.box[2]) / 2,
                                  (s.box[1] + s.box[3]) / 2, s.box))
    # adjacent tuplet digits are one number
    out.sort(key=lambda m: m.x)
    merged = []
    for m in out:
        if merged and abs(m.y - merged[-1].y) < 2 and 0 <= m.box[0] - merged[-1].box[2] < 2:
            last = merged[-1]
            merged[-1] = TupletMark(int(f"{last.actual}{m.actual}"), None, (last.box[0] + m.box[2]) / 2,
                                    last.y, (last.box[0], last.box[1], m.box[2], m.box[3]))
        else:
            merged.append(m)
    for run in page_layout.text:
        match = TUPLET_TEXT.match(run.text)
        # tuplet numbers are italic; upright digits are fingering, string
        # numbers and the like
        if match and re.search(r"italic|oblique", run.font, re.I):
            out_box = run.box
            merged.append(TupletMark(int(match.group(1)), int(match.group(2)) if match.group(2) else None,
                                     (out_box[0] + out_box[2]) / 2, (out_box[1] + out_box[3]) / 2, out_box))
    return merged


def apply_tuplets(marks, evs, stems, lines, verticals, space, compound):
    """Give each tuplet number's events their ratio. The events are those
    under its bracket (thin lines either side of the number at its height,
    with hooks at their outer ends), or else those of the beam group the
    number stands over. Returns the numbers that found no events."""
    unused = []
    for m in marks:
        if not 1 < m.actual < 20:
            continue
        span = _bracket_span(m, lines, verticals, space)
        members = []
        if span:
            members = [e for e in evs if not e.grace and span[0] - 0.5 * space <= (e.x + e.right) / 2 <= span[1] + 0.5 * space
                       and _near_mark(e, m, space)]
            # a bracket belongs to one staff: the one nearest the number
            staves = {id(e.staff): e.staff for e in members}
            if len(staves) > 1:
                nearest = min(staves.values(), key=lambda st: 0 if st.top <= m.y <= st.bottom
                              else min(abs(m.y - st.top), abs(m.y - st.bottom)))
                members = [e for e in members if e.staff is nearest]
        else:
            members = _beam_group(m, evs, space)
        if len(members) < 2:
            unused.append(m)
            continue
        normal = m.normal or _normal(m.actual, compound)
        for e in members:
            if e.tuplet is None:
                e.tuplet = (m.actual, normal)
    return unused


def _normal(actual, compound):
    """The usual number of notes a tuplet of `actual` notes stands for: the
    power of two below it (3 in the time of 2, 5 or 6 or 7 in the time of
    4), and for a power of two, three quarters of it (2 in the time of 3,
    4 in the time of 3, 8 in the time of 6)."""
    if actual & (actual - 1) == 0:
        return 3 if actual == 2 else actual * 3 // 4
    normal = 1
    while normal * 2 < actual:
        normal *= 2
    return normal


def _near_mark(e, m, space):
    """The event is on the side of the staff the number is on, not far from it."""
    ys = [h.y for h in e.heads] or [(e.rest.box[1] + e.rest.box[3]) / 2]
    if e.stem is not None:
        ys += [e.stem.top, e.stem.bottom]
    return min(abs(y - m.y) for y in ys) <= 4 * space


def _bracket_span(m, lines, verticals, space):
    """(x0, x1) of a tuplet bracket around the number, or None. The bracket's
    two halves are thin lines near the number's height, one ending just
    before it and one starting just after it. They slope with the notes."""
    left = right = None
    for x0, y0, x1, y1 in lines:
        length = x1 - x0
        if not 0.5 * space <= length < 30 * space:
            continue
        if 0 <= m.box[0] - x1 <= 1.5 * space and abs(y1 - m.y) <= 1.5 * space:
            if left is None or x1 > left[2]:
                left = (x0, y0, x1, y1)
        if 0 <= x0 - m.box[2] <= 1.5 * space and abs(y0 - m.y) <= 1.5 * space:
            if right is None or x0 < right[0]:
                right = (x0, y0, x1, y1)
    if left is None or right is None:
        return None
    return left[0], right[2]


def _beam_group(m, evs, space):
    """The events joined by the beams nearest the number, under or over it."""
    stems = [e for e in evs if e.stem is not None and e.stem.beams]
    best, best_d = None, None
    for e in stems:
        for b in e.stem.beams:
            if b.x0 - 0.5 * space <= m.x <= b.x1 + 0.5 * space:
                # the gap between the beam and the number's ink
                d = max(0.0, abs(b.y_at(min(max(m.x, b.x0), b.x1)) - m.y) - (m.box[3] - m.box[1]) / 2)
                if d <= 3 * space and (best_d is None or d < best_d):
                    best, best_d = b, d
    if best is None:
        return []
    # the group: events connected to this beam through shared beams
    group = {id(e): e for e in stems if any(b is best for b in e.stem.beams)}
    changed = True
    while changed:
        changed = False
        beams = {id(b) for e in group.values() for b in e.stem.beams}
        for e in stems:
            if id(e) not in group and any(id(b) in beams for b in e.stem.beams):
                group[id(e)] = e
                changed = True
    return list(group.values())


# ------------------------------------------------------- hidden tuplets

HIDDEN_TUPLETS = {3: 2, 5: 4, 6: 4, 7: 4, 9: 8, 10: 8, 12: 8}


def beam_groups(evs):
    """Events joined by shared beams, as lists, left to right."""
    stemmed = [e for e in evs if e.stem is not None and e.stem.beams]
    parent = {id(e): id(e) for e in stemmed}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner = {}
    for e in stemmed:
        for b in e.stem.beams:
            if id(b) in owner:
                parent[root(id(e))] = root(owner[id(b)])
            else:
                owner[id(b)] = id(e)
    groups = collections.defaultdict(list)
    for e in stemmed:
        groups[root(id(e))].append(e)
    return [sorted(g, key=lambda e: e.x) for g in groups.values()]


def hidden_tuplets(evs, space, bar_length, cost):
    """Bar arithmetic (ACC-5) for tuplets whose number is not printed: when
    the bar does not add up, beam groups of 3, 5, 6, 7, 9, 10 or 12 notes of
    one value with no tuplet are read as tuplets (3 in the time of 2, 6 in
    the time of 4, and so on). The reading is kept if the bar then adds up
    better. Returns the cost of the reading kept."""
    groups = [g for g in beam_groups(evs) if len(g) in HIDDEN_TUPLETS and all(e.tuplet is None for e in g)
              and len({e.value for e in g}) == 1]
    if not groups:
        return cost
    for g in groups:
        for e in g:
            e.tuplet = (len(g), HIDDEN_TUPLETS[len(g)])
    new = assign_onsets(evs, space, bar_length)
    if new < cost:
        return new
    for g in groups:
        for e in g:
            e.tuplet = None
    return assign_onsets(evs, space, bar_length)


# --------------------------------------------------------------- rhythm

def _columns(staff_events, space):
    """Events of one staff and bar grouped into columns (events that start
    together), left to right."""
    columns = []
    for e in sorted(staff_events, key=lambda e: e.x):
        if columns and _same_column(columns[-1], e, space):
            columns[-1].append(e)
        else:
            columns.append([e])
    return columns


def _same_column(col, e, space):
    """The event starts with the column: at the same place, or set aside by
    a collision with a voice of the other stem direction (further when
    their noteheads are a unison or a second apart)."""
    gap = e.x - col[0].x
    if gap <= 0.6 * space:
        return True
    opposite = e.direction and all(o.direction != e.direction for o in col) and any(o.direction for o in col)
    if not opposite:
        return False
    if gap <= 1.4 * space:
        return True
    # Noteheads side by side and touching, as engravers set a collision: a
    # unison with the stem up on the left, or a second with the upper
    # note, stem up, on the right.
    return gap <= 1.8 * space and any(
        abs(h.box[0] - g.box[2]) <= 0.45 * space
        and ((h.step == g.step and o.direction == 1 and e.direction == -1)
             or (h.step == g.step + 1 and o.direction == -1 and e.direction == 1))
        for o in col for g in o.heads for h in e.heads)


def assign_onsets(staff_events, space, bar_length=None, reference=()):
    """Onsets of the events of one staff in one bar (rule 3). Columns start
    in order, each at the end of some event before it. When every voice runs
    on without a gap, the next column starts at the earliest end among the
    events still sounding. A voice can stop early (rests hidden by the
    engraver), so the choice is a search: the onsets are those that leave
    the fewest event ends with no column starting there before the end of
    the bar, and no column at or past the bar's end; among equals, the
    earliest. `reference` holds (x, onset) of columns on other staves of
    the system, read without doubt: a column at the same place should start
    at the same time. Returns the cost of the choice (0: every event ends
    where another starts or at the bar's end)."""
    columns = _columns(staff_events, space)
    if not columns:
        return 0
    starts = [min(e.x for e in col) for col in columns]
    known = []
    for x in starts:
        near = [(abs(rx - x), t) for rx, t in reference if abs(rx - x) <= 0.5 * space]
        known.append(min(near)[1] if near else None)
    durations = [[e.duration for e in col] for col in columns]
    directions = [[e.direction for e in col] for col in columns]
    here = [{e.direction for e in col} if all(e.direction for e in col) else set() for col in columns]
    limit = bar_length if bar_length else None
    # a state: (cost, onsets so far)
    # the first column starts the bar, unless other staves show it later
    # (a voice whose opening rests are hidden)
    states = [(0, (Fraction(0),))]
    if known[0]:
        states = [(2, (Fraction(0),)), (0, (known[0],))]
    for k in range(1, len(columns)):
        nxt = []
        for cost, onsets in states:
            t = onsets[-1]
            ends = {onsets[i] + d for i in range(k) for d in durations[i] if onsets[i] + d > t}
            # a column can also start where no event ends (a note missed or
            # a voice that starts late), at a cost: one step of a value in
            # the bar after the column before
            steps = {t + d for col in durations[:k + 1] for d in col if d > 0} - ends
            choices = [(c, 0) for c in sorted(ends)[:6]] + [(c, 1) for c in sorted(steps)[:4]]
            if known[k] is not None and known[k] > t and known[k] not in ends | steps:
                choices.append((known[k], 1))
            if not choices:
                choices = [(t + 1, 1)]
            for choice, unexplained in choices:
                skipped = sum(1 for i in range(k) for d in durations[i] if t < onsets[i] + d < choice)
                extra = skipped + unexplained + (5 if limit is not None and choice >= limit else 0)
                if known[k] is not None and choice != known[k]:
                    extra += 2
                # between equals, a column continues an event of its own stem
                # direction (two voices keep their stems apart)
                ending = {directions[i][j] for i in range(k) for j, d in enumerate(durations[i])
                          if onsets[i] + d == choice}
                if ending and here[k] and 0 not in ending and not ending & here[k]:
                    extra += 0.5
                nxt.append((cost + extra, onsets + (choice,)))
        nxt.sort()
        states = nxt[:40]
    best_cost, best = None, None
    for cost, onsets in states:
        t = onsets[-1]
        total = cost
        if limit is not None:
            total += sum(1 for i in range(len(columns)) for d in durations[i]
                         if t < onsets[i] + d < limit or onsets[i] + d > limit)
        if best_cost is None or (total, onsets) < (best_cost, best):
            best_cost, best = total, onsets
    for col, t in zip(columns, best):
        for e in col:
            e.onset = t
    _assign_voices(staff_events)
    return best_cost


def _rhythm_doubts(staff_events, bar_length):
    """The parts of the onset search's cost that point at a misread note
    (docs/notes/confidence-spec.md): a column that starts where no event
    before it ends, an event that ends where nothing starts and that later
    events pass over, and an event that runs past the bar's end. A voice
    that stops short of the end is not counted: engravers hide rests."""
    timed = [e for e in staff_events if e.onset is not None]
    if not timed:
        return []
    starts = {e.onset for e in timed}
    ends = {e.onset + e.duration for e in timed}
    last = max(starts)
    out = []
    late = sorted(t for t in starts if t and t not in ends)
    if late:
        out.append(("a note starts where no note before it ends", late[0]))
    gaps = sorted(e.onset for e in timed if e.onset + e.duration < last and e.onset + e.duration not in starts)
    if gaps:
        out.append(("a note ends where no note follows it", gaps[0]))
    over = sorted(e.onset for e in timed if not e.whole_bar and e.onset + e.duration > bar_length)
    if over:
        out.append(("a note runs past the end of the bar", over[0]))
    return out


def _column_conflicts(by_staff_bar, space):
    """(staff, bar of the system, reason, onset) for each staff whose events
    disagree in time with those of another staff of the system: one
    further right that starts earlier, or one at the same place that starts
    at a different time. Both staves are listed, since either may be wrong."""
    by_bar = collections.defaultdict(list)
    for (staff_id, k), group in by_staff_bar.items():
        # a whole-bar rest stands in the middle of the bar but starts it
        by_bar[k].append([e for e in group if not e.grace and not e.whole_bar and e.onset is not None])
    out = []
    for k, groups in by_bar.items():
        for i, a_group in enumerate(groups):
            for b_group in groups[i + 1:]:
                conflict = onset = None
                for a in a_group:
                    for b in b_group:
                        first, second = (a, b) if a.x <= b.x else (b, a)
                        gap = second.x - first.x
                        if gap <= 0.3 * space and a.onset != b.onset:
                            conflict = "notes in line with those of another staff start at a different time"
                        elif gap >= 1.5 * space and second.onset < first.onset:
                            conflict = "a note starts before one to its left on another staff"
                        if conflict:
                            onset = second.onset
                            break
                    if conflict:
                        break
                if conflict and a_group and b_group:
                    out += [(a_group[0].staff, k, conflict, onset), (b_group[0].staff, k, conflict, onset)]
    return out


def _assign_voices(staff_events):
    """Voices as chains: each event continues a voice that ends where it
    starts, preferring the same stem direction; stems up take the lower
    voice numbers."""
    voices = []   # [end, direction]
    for e in sorted(staff_events, key=lambda e: (e.onset, -e.direction)):
        best = None
        for v, (end, direction) in enumerate(voices):
            if end == e.onset:
                if best is None or (direction == e.direction and voices[best][1] != e.direction):
                    best = v
        if best is None:
            for v, (end, direction) in enumerate(voices):
                if end <= e.onset:
                    best = v
                    break
        if best is None:
            voices.append([Fraction(0), e.direction])
            best = len(voices) - 1
        voices[best] = [e.onset + e.duration, e.direction or voices[best][1]]
        e.voice = best


def mark_graces(evs, space):
    """Small chords are grace notes when a full-size note or rest follows
    them closely on their staff (allowing for the other grace notes in
    between). Small chords with nothing full-size after them are cue notes,
    which keep their own rhythm."""
    by_staff = collections.defaultdict(list)
    for e in evs:
        by_staff[id(e.staff)].append(e)
    for group in by_staff.values():
        group.sort(key=lambda e: e.x)
        for k, e in enumerate(group):
            e.grace = False
            if not e.small or e.rest is not None:
                continue
            between = 0
            for f in group[k + 1:]:
                if not f.small or f.rest is not None:
                    e.grace = f.x - e.x <= (4 + 2.5 * between) * space
                    break
                between += 1


def assign_graces(staff_events, space):
    """Grace notes take the onset of the next full-size event on their staff."""
    graces = sorted((e for e in staff_events if e.grace), key=lambda e: e.x)
    main = sorted((e for e in staff_events if not e.grace), key=lambda e: e.x)
    for g in graces:
        after = [e for e in main if e.x > g.x]
        target = after[0] if after else (main[-1] if main else None)
        g.onset = target.onset if target is not None else Fraction(0)
        g.voice = target.voice if target is not None else 0


# ------------------------------------------------------------------ pitch

def clef_bottom(value):
    """(letter index, octave) of the bottom staff line under a clef value
    such as "G 2" or "F 4 octave -1"; None for a clef with no pitch."""
    parts = value.split()
    if parts[0] not in ("G", "F", "C"):
        return None
    line = int(parts[1])
    letter, octave = {"G": (4, 4), "F": (3, 3), "C": (0, 4)}[parts[0]]   # the note on the clef's line
    position = letter + 7 * octave - 2 * (line - 1)
    if "octave" in value:
        position += 7 * int(parts[-1])
    return position


def pitch_of(clef, step):
    """(letter, octave) of a staff step under a clef value."""
    bottom = clef_bottom(clef)
    if bottom is None:
        bottom = clef_bottom("G 2")
    position = bottom + step
    return LETTERS[position % 7], position // 7


def key_alter(fifths, letter):
    if fifths > 0 and letter in "FCGDAEB"[:fifths]:
        return Fraction(1)
    if fifths < 0 and letter in "BEADGCF"[:-fifths]:
        return Fraction(-1)
    return Fraction(0)


def attach_accidentals(accidentals, heads, space):
    """Each accidental to the notehead on its step just to its right (a
    chord's accidentals stand in columns before it). Returns the
    accidentals no notehead took."""
    left = []
    for a in sorted(accidentals, key=lambda a: -a.x):
        alter = accidental_alter(a.symbol.name)
        best, best_d = None, None
        for h in heads:
            if h.staff is not a.staff or h.step != a.step or h.accidental is not None:
                continue
            d = h.box[0] - a.symbol.box[2]
            if -0.3 * space <= d <= 4.5 * space and (best_d is None or d < best_d):
                best, best_d = h, d
        if best is not None:
            best.accidental = alter
        else:
            left.append(a)
    return left


# ---------------------------------------------------------------- the score

def _signature_accidentals(page_layout, system, staff):
    """The accidentals of the staff that are key signatures (as
    structure.staff_keys reads them)."""
    out = set()
    for k in range(len(system.bars)):
        region = structure._signature_region(page_layout, system, staff, k)
        every = sorted((s for s in region if s.name in (structure.SHARP, structure.FLAT, structure.NATURAL)),
                       key=lambda s: s.x)
        if not every:
            continue
        every = structure._close_run(every, staff.space)
        notes = [(s.x, page_layout.step_of(s)) for s in page_layout.symbols
                 if lay.is_note(s.name) and page_layout.staff_of(s) is staff]
        free = [s for s in every if not any(0 < nx - s.x <= 3.5 * staff.space and ns == page_layout.step_of(s)
                                             for nx, ns in notes)]
        if len(every) >= 2 and free and structure._key_of(page_layout, staff, every) is not None:
            out.update(id(s) for s in every)
        elif structure._key_of(page_layout, staff, free) is not None:
            out.update(id(s) for s in free)
    return out


@dataclass
class _Acc:
    symbol: object
    staff: object
    step: int

    @property
    def x(self):
        return self.symbol.x


def _time_in_force(score, bar, part=0):
    """(bar length in quarter notes, compound) of a part's time signature in
    force at a bar. Parts can have different time signatures."""
    found = None
    for e in score.structure:
        if e.kind == "time" and e.part == part and e.bar <= bar:
            if found is None or e.bar >= found.bar:
                found = e
    if found is None:
        return Fraction(4), False
    beats, beat_type = found.value.split("/")
    beats, beat_type = int(beats), int(beat_type)
    return Fraction(4 * beats, beat_type), beat_type >= 8 and beats % 3 == 0 and beats > 3


def _key_in_force(score, part, bar):
    found = None
    for e in score.structure:
        if e.kind == "key" and e.part == part and e.bar <= bar:
            if found is None or e.bar >= found.bar:
                found = e
    return int(found.value) if found else 0


def read_notes(score, ordered, pages, layouts=()):
    """Fill score.notes and score.rests from the systems in score order
    (structure.assign_parts), with the page objects to read beams from,
    and with them the markings and text (Stage 1.4, omr.pdf.markings).
    `layouts` are all the page layouts, for the text of pages with no
    system (it goes to score.text)."""
    from omr.pdf import text

    bar_base = 0
    clefs_in_force = {}     # (part, staff) -> clef value
    clef_onsets = {}        # (part, staff, bar, rank) -> onset of a clef within a bar
    open_ties = {}          # (part, staff, letter, octave) -> alter, ties running into the next system
    shapes_by_page = {}
    text_by_page = {}
    lengths = collections.defaultdict(Fraction)
    first_page = min((pl.page for pl, _, _ in ordered), default=1)

    def page_text(pl, shapes):
        rect = pages[pl.page - 1].rect
        lines = shapes.hyphens + [(h.y, h.x0, h.x1) for h in pl.horizontals if h.thickness <= 0.3 * h_space(pl)]
        items = text.classify_page(pl, (rect.x0, rect.y0, rect.x1, rect.y1), pl.page == first_page,
                                   shapes.frames, lines)
        score.text.extend(i for i in items if i.system is None)
        return items

    for pl, system, mapping in ordered:
        if pl.page not in shapes_by_page:
            shapes_by_page[pl.page] = page_shapes(pages[pl.page - 1], h_space(pl))
            text_by_page[pl.page] = page_text(pl, shapes_by_page[pl.page])
        items = [i for i in text_by_page[pl.page] if i.system is system]
        _read_system(score, pl, system, mapping, bar_base, shapes_by_page[pl.page], items, clefs_in_force,
                     clef_onsets, lengths, open_ties)
        bar_base += len(system.bars)
    for pl in layouts:
        if pl.page not in text_by_page:
            for r in pl.text:
                score.text.append(text.TextItem("page text", r.text, r.box, pl.page, r.font, r.size))
    for k, bar in enumerate(score.bars):
        bar.length = lengths.get(k, Fraction(0))
    # clefs within a bar take the onset of the event they stand before
    fixed = []
    for e in score.structure:
        if e.kind == "clef" and e.onset != 0 and e.onset < 1:
            rank = int(e.onset * 1000)
            onset = clef_onsets.get((e.part, e.staff, e.bar, rank))
            if onset is not None:
                e = replace(e, onset=onset)
        fixed.append(e)
    score.structure = fixed
    return score


def h_space(pl):
    return statistics.median(s.space for s in pl.staves) if pl.staves else 5.0


def _read_system(score, pl, system, mapping, bar_base, shapes, items, clefs_in_force, clef_onsets, lengths,
                 open_ties):
    from omr.pdf import markings, rules

    beams, curves, dashed, thin = shapes.beams, shapes.level_curves, shapes.dashed, shapes.thin
    space = statistics.median(s.space for s in system.staves)
    members = {id(st): k for k, st in enumerate(system.staves)}

    def doubt(staff, k, rule, reason, onset=None):
        """Note a doubt (Stage 1.5, omr.pdf.rules) on a staff in bar k of
        the system, or at a place x when k is a float."""
        if isinstance(k, float):
            k = structure._bar_of(system, k)
        if k is None or id(staff) not in members:
            return
        part, number = mapping.staves[members[id(staff)]]
        score.doubts.append(rules.Flag(part, number, bar_base + k, rule, reason, onset))
    heads = []
    for s in pl.symbols:
        if is_head(s.name):
            staff = pl.staff_of(s)
            if staff is not None:
                staff, step = ledger_staff(s, staff, pl.staves, pl.horizontals)
                # a notehead well clear of the staff with no ledger lines is
                # text (a metronome mark), not a note
                if not -3 <= step <= 11 and not _ledgers_reach(s, staff, step, pl.horizontals):
                    continue
                if id(staff) in members:
                    heads.append(Head(s, staff, step, False))
    _small_heads(heads)
    barline_xs = [x for g in system.barlines for x, _ in g.lines]
    stems = find_stems(pl.verticals, heads, space, barline_xs)
    beam_list = [b for b in beams if system.x0 - space <= b.x0 <= system.x1 + space
                 and system.staves[0].top - 10 * space <= b.y0 <= system.staves[-1].bottom + 10 * space]
    stems += hidden_stems(heads, stems, beam_list, space, pl.verticals)
    attach_beams(stems, beam_list, space)
    flags = [s for s in pl.symbols if s.name in FLAG_COUNT and id(pl.staff_of(s)) in members]
    for flag in attach_flags(stems, flags, space):
        doubt(pl.staff_of(flag), flag.x, "stray symbol", "a flag is on no stem")
    chords = make_chords(heads, stems, space)
    rests = [r for r in make_rests(pl.symbols, pl, space) if id(r.staff) in members]
    evs = chords + rests
    mark_graces(evs, space)
    repeat_zones = [(g.x0 - 1.6 * space, g.x1 + 1.6 * space) for g in system.barlines
                    if g.repeat_before or g.repeat_after]
    dots = [s for s in pl.symbols if s.name == "augmentationDot" and id(pl.staff_of(s)) in members]
    used_dots = attach_dots(evs, dots, space, repeat_zones)
    time_length, compound = _time_in_force(score, bar_base)
    unused_marks = apply_tuplets([m for m in tuplet_marks(pl) if system.staves[0].top - 8 * space <= m.y
                   <= system.staves[-1].bottom + 8 * space and system.x0 <= m.x <= system.x1],
                  evs, stems, thin + [(h.x0, h.y, h.x1, h.y) for h in pl.horizontals if h.thickness <= 0.25 * space],
                  pl.verticals, space, compound)
    # accidentals and key signatures
    signature = set()
    for staff in system.staves:
        signature |= _signature_accidentals(pl, system, staff)
    accs = [_Acc(s, pl.staff_of(s), pl.step_of(s)) for s in pl.symbols
            if accidental_alter(s.name) is not None and id(pl.staff_of(s)) in members and id(s) not in signature]
    for a in attach_accidentals(accs, heads, space):
        doubt(a.staff, a.x, "stray symbol", "an accidental is before no note")
    tied_to, tied_from, start_next, stop_previous, tie_curves = find_ties(curves, heads, evs, system, space)
    octave_doubts = []
    octave_spans = octave_marks(pl, system, dashed, space, octave_doubts)
    for x0, x1, y, reason in octave_doubts:
        near = sorted(system.staves, key=lambda st: min(abs(y - st.top), abs(y - st.bottom)))[:2]
        bars = {structure._bar_of(system, x) for x in (x0, x1)} - {None}
        for k in range(min(bars, default=0), max(bars, default=-1) + 1):
            for staff in near:
                doubt(staff, k, "octave sign", reason)
    arpeggiated = arpeggios(pl, [e for e in evs if e.rest is None], space)
    # events by staff and bar
    by_staff_bar = collections.defaultdict(list)
    for e in evs:
        k = structure._bar_of(system, e.x + 0.01)
        if k is None:
            k = len(system.bars) - 1 if system.bars and e.x >= system.bars[-1].x0 else None
        if k is None:
            continue
        e.bar = k
        by_staff_bar[(id(e.staff), k)].append(e)
    costs, lengths_by = {}, {}
    for (staff_id, k), group in by_staff_bar.items():
        main = [e for e in group if not e.grace]
        part = mapping.staves[[id(st) for st in system.staves].index(staff_id)][0]
        bar_length, _ = _time_in_force(score, bar_base + k, part)
        whole = [e for e in main if e.rest is not None and e.rest.name in ("restWhole", "restDoubleWhole")]
        if len(main) == 1 and whole:
            whole[0].whole_bar = True
            whole[0].base = bar_length
        costs[(staff_id, k)] = assign_onsets(main, space, bar_length)
        if costs[(staff_id, k)]:
            printed = {id(e) for e in main if e.tuplet}
            costs[(staff_id, k)] = hidden_tuplets(main, space, bar_length, costs[(staff_id, k)])
            if any(e.tuplet and id(e) not in printed for e in main):
                doubt(main[0].staff, k, "unprinted tuplet", "a tuplet is read from the bar's length, "
                      "with no number printed")
        lengths_by[(staff_id, k)] = bar_length
    # a staff whose reading leaves doubt is read again with the columns of
    # the other staves of the bar that were read without doubt
    for (staff_id, k), group in by_staff_bar.items():
        if not costs.get((staff_id, k)):
            continue
        reference = [(min(e.x for e in col), col[0].onset)
                     for (other, j), g in by_staff_bar.items() if j == k and other != staff_id and costs.get((other, j)) == 0
                     for col in _columns([e for e in g if not e.grace], space)]
        if reference:
            assign_onsets([e for e in group if not e.grace], space, lengths_by[(staff_id, k)], reference)
    for (staff_id, k), group in by_staff_bar.items():
        assign_graces(group, space)
        for reason, onset in _rhythm_doubts([e for e in group if not e.grace], lengths_by[(staff_id, k)]):
            doubt(group[0].staff, k, "rhythm", reason, onset)
    if not mapping.certain:
        for staff in system.staves:
            for k in range(len(system.bars)):
                doubt(staff, k, "hidden staves", "some staves of this system are hidden, and which part this "
                      "staff belongs to is not certain")
    for staff, k, reason, onset in _column_conflicts(by_staff_bar, space):
        doubt(staff, k, "staves disagree", reason, onset)
    bar_numbers = [i.box for i in items if i.kind == "bar number"]
    for m in unused_marks:
        if any(b[0] <= m.x <= b[2] and b[1] <= m.y <= b[3] for b in bar_numbers):
            continue   # an italic bar number
        if any(c.box[0] - space <= m.x <= c.box[2] + space for c in pl.symbols if c.name in structure.CLEFS
               and system.staves[0].top - 4 * space <= c.y <= system.staves[-1].bottom + 4 * space):
            continue   # the 8 of an octave clef
        staff = min(system.staves, key=lambda st: 0 if st.top <= m.y <= st.bottom
                    else min(abs(m.y - st.top), abs(m.y - st.bottom)))
        doubt(staff, m.x, "stray symbol", f"a tuplet number {m.actual} is over no notes")
    # markings (Stage 1.4): directions go to score.markings, the rest onto the notes
    staccato = staccato_dots([d for d in dots if id(d) not in used_dots], evs, space)
    taken = {id(d) for d in staccato}
    for d in dots:
        cx = (d.box[0] + d.box[2]) / 2
        if id(d) not in used_dots and id(d) not in taken and not any(a <= cx <= b for a, b in repeat_zones):
            doubt(pl.staff_of(d), cx, "stray symbol", "a dot is beside no note")
    extras, head_marks = markings.read_system(score, pl, system, mapping, bar_base, evs, items, shapes,
                                              tie_curves, staccato)
    # pitch, in x order per staff
    alters = {}
    next_ties = {}
    for staff in system.staves:
        part, number = mapping.staves[members[id(staff)]]
        staff_clefs = sorted((s for s in pl.symbols if s.name in structure.CLEFS and pl.staff_of(s) is staff),
                             key=lambda s: s.x)
        clef_values = []
        for c in staff_clefs:
            value = structure.clef_value(c.name, pl.step_of(c))
            octave = structure._octave_digits(pl, c)
            if octave and " octave" not in value:
                value += f" octave {octave:+d}"
            clef_values.append((c.x, value))
        state = {}
        current_bar = None
        staff_events = sorted((e for e in evs if e.staff is staff and e.onset is not None),
                              key=lambda e: (e.bar, e.x))
        for e in staff_events:
            global_bar = bar_base + e.bar
            if e.bar != current_bar:
                state, current_bar = {}, e.bar
            voice = str(e.voice + 1 + 4 * (number - 1))
            lengths[global_bar] = max(lengths[global_bar], e.onset + (0 if e.grace else e.duration))
            if e.rest is not None:
                duration = events.WHOLE_BAR if e.whole_bar else e.duration
                score.rests.append(events.Rest(part, number, voice, global_bar, e.onset, duration))
                continue
            clef = clefs_in_force.get((part, number), "G 2")
            for x, value in clef_values:
                if x < e.x:
                    clef = value
            fifths = _key_in_force(score, part, global_bar)
            value_name = TYPE_NAME.get(e.base, "quarter") + "." * e.dots
            grace_order = 0
            if e.grace:
                same = sorted((g for g in staff_events if g.grace and g.bar == e.bar and g.onset == e.onset
                               and g.voice == e.voice), key=lambda g: g.x)
                grace_order = 1 + same.index(e)
            extra = extras.get(id(e))
            for n, h in enumerate(sorted(e.heads, key=lambda h: h.step)):
                letter, octave = pitch_of(clef, h.step)
                key = (letter, octave)
                if h.accidental is not None:
                    state[key] = h.accidental
                alter = state.get(key, key_alter(fifths, letter))
                # a tied note keeps the alteration of the note it is tied from
                if h.accidental is None:
                    if id(h) in tied_from and id(tied_from[id(h)]) in alters:
                        alter = alters[id(tied_from[id(h)])]
                    elif id(h) in stop_previous and (part, number, letter, octave) in open_ties:
                        alter = open_ties[(part, number, letter, octave)]
                alters[id(h)] = alter
                if id(h) in start_next:
                    next_ties[(part, number, letter, octave)] = alter
                shift = sum(n for st, x0, x1, n in octave_spans if st is h.staff and x0 <= h.x <= x1)
                pitch = events.Pitch(letter, alter, octave + shift)
                duration = Fraction(0) if e.grace else e.duration
                marks = set(head_marks.get(id(h), ()))
                if id(e) in arpeggiated:
                    marks.add("arpeggiate")
                slurs, lyrics, syllables = (), (), ()
                if n == 0 and extra is not None:
                    # marks, slurs and lyrics of a chord go on its lowest note, as MuseScore writes them
                    marks |= extra.marks
                    slurs = tuple(extra.slurs)
                    ordered_lyrics = sorted(extra.lyrics)
                    lyrics = tuple((str(v), t) for v, t, _, _ in ordered_lyrics)
                    syllables = tuple((str(v), syl, ext) for v, _, syl, ext in ordered_lyrics)
                score.notes.append(events.Note(part, number, voice, global_bar, e.onset, pitch, duration,
                                               value_name, grace_order,
                                               tie_start=id(h) in tied_to or id(h) in start_next,
                                               tie_stop=id(h) in tied_from or id(h) in stop_previous,
                                               cue=e.small and not e.grace,
                                               marks=frozenset(marks), slurs=slurs, lyrics=lyrics,
                                               syllables=syllables))
        if clef_values:
            clefs_in_force[(part, number)] = clef_values[-1][1]
        # onsets of clefs within bars, by the rank structure.staff_clefs gives them
        music = structure._music(pl, staff)
        for c in staff_clefs:
            k = structure._bar_of(system, c.x)
            if k is None:
                continue
            after = [e for e in staff_events if e.bar == k and not e.grace and e.x > c.x]
            if after:
                rank = sum(1 for x in music if structure._start(system, k) <= x < c.x)
                clef_onsets[(part, number, bar_base + k, rank)] = min(e.onset for e in after)
    open_ties.clear()
    open_ties.update(next_ties)


# ------------------------------------------------------------ ledger lines

def ledger_staff(symbol, staff, staves, horizontals):
    """(staff, step) of a notehead outside the staves: the staff whose ledger
    lines reach it. A note high above a lower staff can be nearer the staff
    above; its ledger lines tell which staff it belongs to."""
    step = staff.step(symbol.y)
    if -1 <= step <= 9 or _ledgers_reach(symbol, staff, step, horizontals):
        return staff, step
    for other in staves:
        if other is staff or min(other.x1, staff.x1) - max(other.x0, staff.x0) <= 0:
            continue
        other_step = other.step(symbol.y)
        if abs(other_step) > 30 or -1 <= other_step <= 9:
            continue
        if _ledgers_reach(symbol, other, other_step, horizontals):
            return other, other_step
    return staff, step


def _ledgers_reach(symbol, staff, step, horizontals):
    needed = range(10, step + 1, 2) if step > 9 else range(-2, step - 1, -2)
    x0, x1 = symbol.box[0], symbol.box[2]
    for st in needed:
        y = staff.bottom - st * staff.space / 2
        if not any(abs(h.y - y) <= 0.3 * staff.space and h.x0 <= x0 + 0.3 * staff.space
                   and h.x1 >= x1 - 0.3 * staff.space for h in horizontals):
            return False
    return True


# ------------------------------------------------------------------- ties

def find_ties(curves, heads, evs, system, space):
    """Ties between noteheads: a curve whose ends are level, starting at one
    notehead and ending at the next on the same staff step. A tie that runs
    to the end of the system continues on the next; one that starts before
    the first note of a system continues one from the system before.
    Returns (tied_to, tied_from, start_next, stop_previous, curves used):
    {id(head): head} for the first two, sets of ids for the others."""
    tied_to, tied_from = {}, {}
    start_next, stop_previous = set(), set()
    used = set()
    top = system.staves[0].top - 6 * space
    bottom = system.staves[-1].bottom + 6 * space
    first_x = {}
    last_x = {}
    for e in evs:
        first_x[id(e.staff)] = min(first_x.get(id(e.staff), e.x), e.x)
        last_x[id(e.staff)] = max(last_x.get(id(e.staff), e.right), e.right)
    for c in curves:
        if not (system.x0 - space <= c.box[0] <= system.x1 + space and top <= c.box[1] <= bottom):
            continue
        lefts = [h for h in heads if h.box[0] - 0.3 * space <= c.left[0] <= h.box[2] + 1.2 * space
                 and abs(c.left[1] - h.y) <= 1.3 * space]
        rights = [h for h in heads if h.box[0] - 1.2 * space <= c.right[0] <= h.box[2] + 0.3 * space
                  and abs(c.right[1] - h.y) <= 1.3 * space]
        pairs = [(a, b) for a in lefts for b in rights
                 if a.staff is b.staff and a.step == b.step and b.x > a.x + space]
        if pairs:
            a, b = min(pairs, key=lambda p: abs(c.left[1] - p[0].y) + abs(c.right[1] - p[1].y))
            tied_to[id(a)] = b
            tied_from[id(b)] = a
            used.add(id(c))
            continue
        if lefts and not rights:
            a = min(lefts, key=lambda h: abs(c.left[1] - h.y))
            if c.right[0] >= last_x.get(id(a.staff), system.x1) and c.right[0] >= system.x1 - 4 * space:
                start_next.add(id(a))
                used.add(id(c))
        elif rights and not lefts:
            b = min(rights, key=lambda h: abs(c.right[1] - h.y))
            if c.left[0] <= first_x.get(id(b.staff), system.x0) and b.x <= first_x.get(id(b.staff), b.x) + space:
                stop_previous.add(id(b))
                used.add(id(c))
    return tied_to, tied_from, start_next, stop_previous, used


# ---------------------------------------------------------- octave marks

OCTAVE_TEXT = re.compile(r"^\s*\(?\s*(8|15|22)\s*(va|vb|ma|mb|a|b)?\s*\)?\s*$")


def octave_marks(page_layout, system, dashed, space, doubts=None):
    """[(staff, x0, x1, octaves)]: octave marks (8va, 8vb, 15ma) over or
    under a staff of the system, and the notes they reach: as far as the
    dashed line that starts just after the mark (a mark with no line covers
    the note under it). The notes are written an octave (or two) away from
    the pitch they stand for, which the MusicXML pitch gives. Octave glyphs of
    the music font that are left out (no line and no suffix) are added to
    `doubts` as (x0, x1, y, reason), since a music font's glyph is not a
    plain digit, and so are marks with no "va" or "vb" between two staves,
    whose staff and direction are a guess."""
    marks = []
    for s in page_layout.symbols:
        name = s.name
        if name.startswith(("ottava", "quindicesima", "ventiduesima")) and "Suffix" not in name:
            amount = 2 if name.startswith("quind") else 3 if name.startswith("venti") else 1
            way = -1 if "Bassa" in name else 1 if "Alta" in name else 0
            marks.append((s.box, amount, way, True))
    for run in page_layout.text:
        match = OCTAVE_TEXT.match(run.text)
        if match:
            amount = {"8": 1, "15": 2, "22": 3}[match.group(1)]
            suffix = match.group(2) or ""
            way = -1 if suffix.endswith("b") else 1 if suffix else 0
            marks.append((run.box, amount, way, False))
    out = []
    top = system.staves[0].top - 8 * space
    bottom = system.staves[-1].bottom + 8 * space
    for box, amount, way, glyph in marks:
        if not (system.x0 - space <= box[0] <= system.x1 and top <= box[1] <= bottom):
            continue
        lines = sorted((d for d in dashed if box[2] - 0.5 * space <= d[1] <= box[2] + 2.5 * space
                        and box[1] - space <= d[0] <= box[3] + space), key=lambda d: d[1])
        if not lines:
            if box[2] - box[0] > 3 * space or way == 0:
                if glyph and doubts is not None:
                    doubts.append((box[0], box[2], (box[1] + box[3]) / 2, "an octave sign reaches no notes"))
                continue    # no line and no "va" or "vb": a digit, not an octave mark
            end = box[2] + 2 * space
        else:
            y, end = lines[0][0], lines[0][2]
            for d in sorted(dashed, key=lambda d: d[1]):
                if abs(d[0] - y) < 0.5 * space and end - 0.5 <= d[1] <= end + 1.5 * space:
                    end = max(end, d[2])
        middle = (box[1] + box[3]) / 2
        staff = min(system.staves, key=lambda st: min(abs(middle - st.top), abs(middle - st.bottom)))
        if way == 0:
            way = 1 if middle < staff.middle else -1
            if doubts is not None and system.staves[0].top < middle < system.staves[-1].bottom:
                doubts.append((box[0], end, middle, "an octave sign between two staves may belong to "
                               "either, so its direction is a guess"))
        out.append((staff, box[0] - 0.5 * space, end + 0.5 * space, way * amount))
    return out


# --------------------------------------------------------------- arpeggios

def arpeggios(page_layout, chords, space):
    """Ids of the chords with an arpeggio: a wavy line (drawn as a run of
    wiggle glyphs) left of the noteheads (and their accidentals). One line can span the
    chords of two voices or two staves (each chord can have one notehead);
    it needs two noteheads beside it in all."""
    wiggles = sorted((s for s in page_layout.symbols if "rpeggiato" in s.name), key=lambda s: s.box[1])
    lines = []     # [x0, top, x1, bottom] of runs of wiggle glyphs stacked one on another
    for w in wiggles:
        for line in lines:
            if abs(line[0] - w.box[0]) <= 0.5 * space and w.box[1] <= line[3] + 0.5 * space:
                line[3] = max(line[3], w.box[3])
                line[2] = max(line[2], w.box[2])
                break
        else:
            lines.append([w.box[0], w.box[1], w.box[2], w.box[3]])
    out = set()
    for x0, top, x1, bottom in lines:
        beside = [e for e in chords
                  if left_edge(e) - 5 * space <= x0 <= left_edge(e) - 0.2 * space
                  and any(top - space <= h.y <= bottom + space for h in e.heads)]
        heads = sum(1 for e in beside for h in e.heads if top - space <= h.y <= bottom + space)
        if heads >= 2:
            out.update(id(e) for e in beside)
    return out


def left_edge(e):
    return min(h.box[0] for h in e.heads)


# ------------------------------------------------------------ bar arithmetic

@dataclass
class BarFill:
    """A voice that does not fill its bar (ACC-5)."""

    part: int
    staff: int
    bar: int
    voice: str
    length: Fraction      # how far the voice reaches
    expected: Fraction    # the time signature's bar length


def unfilled_bars(score):
    """Voices whose notes and rests do not reach the end of the bar or run
    past it. A short first bar (a pickup) is not listed, nor two short bars
    side by side that together make one (a bar split at a repeat or a
    system break), nor a voice that only fills part of a bar whose other
    voices fill it (rests hidden by the engraver)."""
    reach = collections.defaultdict(Fraction)
    for n in score.notes:
        if not n.grace:
            key = (n.part, n.staff, n.bar, n.voice)
            reach[key] = max(reach[key], n.onset + n.duration)
    for r in score.rests:
        key = (r.part, r.staff, r.bar, r.voice)
        expected, _ = _time_in_force(score, r.bar, r.part)
        length = expected if r.duration == events.WHOLE_BAR else r.duration
        reach[key] = max(reach[key], r.onset + length)
    by_bar = collections.defaultdict(Fraction)
    for (part, staff, bar, voice), length in reach.items():
        by_bar[(part, bar)] = max(by_bar[(part, bar)], length)
    out = []
    for (part, staff, bar, voice), length in sorted(reach.items()):
        expected, _ = _time_in_force(score, bar, part)
        whole = by_bar[(part, bar)]
        if length > expected:
            out.append(BarFill(part, staff, bar, voice, length, expected))
            continue
        if length == expected or (length < whole and whole == expected):
            continue
        if bar == 0:
            continue
        neighbours = [by_bar.get((part, bar - 1)), by_bar.get((part, bar + 1))]
        if any(n is not None and n < expected and n + whole == expected for n in neighbours):
            continue
        out.append(BarFill(part, staff, bar, voice, length, expected))
    return out
