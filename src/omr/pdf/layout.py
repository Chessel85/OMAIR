"""Staves, systems and bars on a vector page, and where each symbol sits
(Stage 1.2). Works from the page's vector lines and the symbols of Stage 1.1,
so it is the same for every engraver and for Type A and Type B pages.

The rules are in docs/notes/layout-spec.md. In short:

1. Staff lines are long horizontal lines (stroked, or thin filled
   rectangles). Pieces on one line are joined, and a stack of hairlines drawn
   as one thick line (some printer drivers do this) counts as one line.
2. A staff is five equally spaced lines that overlap along the page.
3. Staves are joined into a system by a vertical line that crosses the gap
   between them (the line at the start of a system, a spanning barline, a
   bracket), or by a brace drawn beside both.
4. A barline is a vertical line that covers a staff from its top line to its
   bottom line, at the same place in most staves of the system, and is not
   a note stem. Barlines close together form one barline group (double,
   final, repeat).
5. A bar ends at a barline group with a note or rest before it in the system;
   a group before the first note (a start repeat after the clef) starts the
   first bar instead.
"""

import re
import statistics
from dataclasses import dataclass, field

from omr.pdf import evidence, geometry

NOTE_NAMES = ("noteheadBlack", "noteheadHalf", "noteheadWhole", "noteheadDoubleWhole",
              "noteheadXBlack", "noteheadXHalf", "noteheadXWhole", "noteheadDiamondBlack",
              "noteheadDiamondHalf", "noteheadDiamondWhole", "noteheadSlashHorizontalEnds",
              "noteheadTriangleUpBlack", "noteheadSquareBlack", "noteheadCircleX",
              "noteQuarterUp", "noteQuarterDown", "noteHalfUp", "noteHalfDown",
              "note8thUp", "note8thDown", "note16thUp", "note16thDown")
REST_NAMES = ("restWhole", "restHalf", "restQuarter", "rest8th", "rest16th", "rest32nd", "rest64th",
              "rest128th", "restDoubleWhole", "restLonga", "restWholeLegerLine", "restHalfLegerLine",
              "repeat1Bar", "repeat2Bars", "restHBar", "restHBarLeft", "restHBarMiddle", "restHBarRight")
DOT_NAMES = ("augmentationDot", "repeatDot", "articStaccatoAbove", "articStaccatoBelow")
BRACE_NAMES = ("brace", "braceSmall", "braceLarge", "braceLarger")


def is_note(name):
    return name.startswith("notehead") or name in NOTE_NAMES


def is_rest(name):
    return name in REST_NAMES


def is_head(name):
    return is_note(name) or name.startswith("noteShape")


# numbers read as text: a tuplet's ("3", "3:2") and an octave mark's ("8va", "15mb")
TUPLET_TEXT = re.compile(r"^\s*(\d{1,2})\s*(?::\s*(\d{1,2}))?\s*$")
OCTAVE_TEXT = re.compile(r"^\s*\(?\s*(8|15|22)\s*(va|vb|ma|mb|a|b)?\s*\)?\s*$")


@dataclass
class Staff:
    page: int
    top: float          # y of the top line
    space: float        # gap between lines
    x0: float
    x1: float
    system: int = -1    # index of its system on the page
    lines: int = 5      # 1 for a one-line (percussion) staff, kept as a five-line staff centred on its line

    @property
    def bottom(self):
        return self.top + 4 * self.space

    @property
    def middle(self):
        return self.top + 2 * self.space

    def step(self, y):
        """Staff position of a y: 0 on the bottom line, 8 on the top line, a
        step for each line and space, rounded. A one-line staff's line is
        its bottom line, as MusicXML counts it, so it is 0 there."""
        return round(self.exact_step(y))

    def exact_step(self, y):
        step = (self.bottom - y) / (self.space / 2)
        return step - 4 if self.lines == 1 else step


@dataclass
class Barline:
    """A group of vertical lines at one bar boundary."""

    x0: float
    x1: float
    lines: list                 # [(x, thick)] left to right
    repeat_before: bool = False # dots on the left: the end of a repeated section
    repeat_after: bool = False  # dots on the right: the start of one

    @property
    def x(self):
        return (self.x0 + self.x1) / 2

    @property
    def kind(self):
        thick = [t for _, t in self.lines]
        if len(thick) == 1:
            return "heavy" if thick[0] else "single"
        if thick == [False, True]:
            return "final"
        if thick == [True, False]:
            return "heavy-light"
        if all(not t for t in thick):
            return "double"
        return "heavy-heavy"


@dataclass
class Bar:
    x0: float
    x1: float
    start: Barline | None = None    # the barline group the bar starts after, if any
    end: Barline | None = None      # the barline group that ends it
    multirest: int = 1              # bars a multi-bar rest stands for


@dataclass
class System:
    page: int
    index: int
    staves: list
    x0: float
    x1: float
    barlines: list = field(default_factory=list)
    bars: list = field(default_factory=list)


def bar_start(system, k):
    """Where bar k's content starts: the first bar includes everything from
    the start of the system (clef, key and time before a start repeat)."""
    return system.x0 if k == 0 else system.bars[k].x0


def bar_of(system, x):
    """Index of the bar of the system that holds x, or None if x is after the
    last barline (courtesy signatures)."""
    for k, bar in enumerate(system.bars):
        if bar_start(system, k) - 0.01 <= x < bar.x1 or (k == len(system.bars) - 1 and bar.end is None and x >= bar.x0):
            return k
    return None


@dataclass
class PageLayout:
    page: int
    staves: list
    systems: list
    symbols: list           # Stage 1.1 Symbols
    text: list              # Stage 1.1 TextRuns
    attached: dict = field(default_factory=dict)   # id(symbol) -> (staff, step)
    horizontals: list = field(default_factory=list)  # joined horizontal lines (_Line)
    verticals: list = field(default_factory=list)    # (x, top, bottom, width)
    _by_staff: dict = field(default=None, repr=False, compare=False)

    def on_staff(self, staff):
        """The symbols attached to a staff, in page order: built once, after
        `attached` is filled, so that each bar and staff is not a scan of
        the whole page."""
        if self._by_staff is None:
            self._by_staff = {}
            for s in self.symbols:
                found = self.attached.get(id(s))
                if found:
                    self._by_staff.setdefault(id(found[0]), []).append(s)
        return self._by_staff.get(id(staff), [])

    def staff_of(self, symbol):
        found = self.attached.get(id(symbol))
        return found[0] if found else None

    def step_of(self, symbol):
        found = self.attached.get(id(symbol))
        return found[1] if found else None

    def staff_space(self):
        """The page's usual staff space: the median of its staves', or 5
        points on a page with no staff."""
        return statistics.median(s.space for s in self.staves) if self.staves else 5.0


def nearest_system(systems, y):
    """The system whose staves are nearest the height y."""
    def distance(system):
        top, bottom = system.staves[0].top, system.staves[-1].bottom
        return 0 if top <= y <= bottom else min(abs(y - top), abs(y - bottom))
    return min(systems, key=distance)


# ---------------------------------------------------------------- lines

@dataclass
class _Line:
    y: float
    x0: float
    x1: float
    thickness: float

    @property
    def length(self):
        return self.x1 - self.x0


SHORT_PIECE = 15.0   # points: a ledger line is shorter; so is a staff line too short to count (find_staves)


def horizontal_lines(candidates):
    """Join horizontal pieces into lines. `candidates` are (y, x0, x1,
    thickness) from evidence.read_drawings. Hairlines stacked less than 0.25
    points apart along the same span are one thick line; pieces at the same
    height that touch or nearly touch (2 points) are one line. Two short
    pieces (both under SHORT_PIECE) must touch: the ledger lines of two
    neighbouring notes can lie under 2 points apart, and five of them
    joined make a false staff."""
    stacked = []
    for y, x0, x1, t in sorted(candidates, key=lambda c: (round(c[1]), round(c[2]), c[0])):
        last = stacked[-1] if stacked else None
        if last and abs(last[1] - x0) < 0.5 and abs(last[2] - x1) < 0.5 and 0 <= y - last[4] <= 0.25:
            last[4] = y                     # extend the stack downwards
            last[3] = max(last[3], t)
        else:
            stacked.append([y, x0, x1, t, y])
    pieces = [_Line((top + bottom) / 2, x0, x1, (bottom - top) + t) for top, x0, x1, t, bottom in stacked]
    pieces.sort(key=lambda l: (round(l.y * 2) / 2, l.x0))
    lines = []
    for piece in pieces:
        for line in reversed(lines[-80:]):
            join = 0.25 if max(line.length, piece.length) < SHORT_PIECE else 2.0
            if abs(line.y - piece.y) <= 0.3 and piece.x0 <= line.x1 + join and piece.x1 >= line.x0 - join:
                if piece.length > line.length:
                    line.thickness = piece.thickness
                line.x0, line.x1 = min(line.x0, piece.x0), max(line.x1, piece.x1)
                break
        else:
            lines.append(_Line(piece.y, piece.x0, piece.x1, piece.thickness))
    return lines


def find_staves(lines, page_number):
    """Five-line staves: five lines, equally spaced (within 10 percent), each
    no thicker than a third of the gap, overlapping along at least half of the
    shortest, and at least six staff spaces long.

    The inspector counts staves by its own rules (omr.pdf.evidence.find_staves),
    on purpose: it classifies the page and counts six-line and one-line staves
    too, where this finder places each five-line staff for the reader."""
    lines = sorted((l for l in lines if l.length >= 15), key=lambda l: l.y)
    used = set()
    staves = []
    for i, first in enumerate(lines):
        if i in used:
            continue
        best = None
        for j in range(i + 1, len(lines)):
            gap = lines[j].y - first.y
            if gap > 15:
                break
            if gap < 2 or not _overlap(first, lines[j]):
                continue
            run = [i, j]
            for k in range(3):
                want = first.y + (k + 2) * gap
                nxt = _find_line(lines, run[-1] + 1, want, 0.1 * gap, first)
                if nxt is None:
                    break
                run.append(nxt)
            if len(run) == 5 and _sixth_line_fits_better(lines, run, gap, first):
                break    # a line one space below fits the staff better than this top one
            if len(run) == 5:
                chosen = [lines[k] for k in run]
                longest = max(l.length for l in chosen)
                if all(l.thickness <= gap / 3 and l.length >= 0.6 * longest for l in chosen):
                    x0 = statistics.median(l.x0 for l in chosen)
                    x1 = statistics.median(l.x1 for l in chosen)
                    if x1 - x0 >= 6 * gap:
                        best = (run, gap, x0, x1)
                        break
        if best:
            run, gap, x0, x1 = best
            used.update(run)
            ys = [lines[k].y for k in run]
            space = (ys[4] - ys[0]) / 4
            staves.append(Staff(page_number, ys[0], space, x0, x1))
    staves.sort(key=lambda s: (s.top, s.x0))
    return staves


def _sixth_line_fits_better(lines, run, gap, first):
    """Five lines and a sixth one space below them: a staff has five, so one
    end line is something else, such as a dashed line one space over the
    staff (MuseScore 3). The top line is dropped when its ends match the
    middle four less well than the sixth line's do."""
    sixth = _find_line(lines, run[-1] + 1, first.y + 5 * gap, 0.1 * gap, first)
    if sixth is None:
        return False
    middle = [lines[k] for k in run[1:]]
    x0, x1 = statistics.median(l.x0 for l in middle), statistics.median(l.x1 for l in middle)
    misfit = lambda l: abs(l.x0 - x0) + abs(l.x1 - x1)
    return misfit(lines[run[0]]) > misfit(lines[sixth])


def _overlap(a, b):
    shorter = min(a.length, b.length)
    return shorter > 0 and min(a.x1, b.x1) - max(a.x0, b.x0) >= 0.5 * shorter


def _find_line(lines, start, y, tolerance, anchor):
    """The line nearest the height y, preferring one thin enough to be a
    staff line: a beam can lie on the bottom line (LilyPond)."""
    found = []
    for k in range(start, len(lines)):
        if lines[k].y > y + tolerance:
            break
        if abs(lines[k].y - y) <= tolerance and _overlap(anchor, lines[k]):
            found.append(k)
    if not found:
        return None
    return min(found, key=lambda k: (lines[k].thickness > 10 * tolerance / 3, abs(lines[k].y - y)))


# ------------------------------------------------------------ vertical lines

def vertical_lines(page):
    """(x, top, bottom, width) of every vertical line: stroked lines, and
    filled rectangles at least three times as tall as wide. As the page is shown."""
    out = []
    for d in evidence.shown_drawings(page):
        items = d["items"]
        width = d.get("width") or 0.0
        if "s" in d["type"]:
            for item in items:
                if item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p1.x - p2.x) < 0.2 and abs(p1.y - p2.y) > 1:
                        out.append(((p1.x + p2.x) / 2, min(p1.y, p2.y), max(p1.y, p2.y), width))
                elif item[0] == "re":
                    r = item[1]
                    if r.height > 3 * max(r.width, 0.01) and r.height > 1:
                        out.append(((r.x0 + r.x1) / 2, r.y0, r.y1, r.width + width))
        if "f" in d["type"] and not any(item[0] == "c" for item in items):
            points = [p for item in items for p in geometry.item_points(item)]
            x0, y0, x1, y1 = geometry.bbox(points)
            if y1 - y0 > 3 * max(x1 - x0, 0.01) and y1 - y0 > 1 and _upright(points, x0, x1):
                out.append(((x0 + x1) / 2, y0, y1, x1 - x0))
    return out


def _upright(points, x0, x1):
    """The filled shape is an upright bar, not a slanted beam: its corners lie
    on its left and right edges."""
    return all(abs(p[0] - x0) < 0.3 or abs(p[0] - x1) < 0.3 for p in points)


# ---------------------------------------------------------------- systems

def staff_barlines(staves, verticals, notes):
    """{id(staff): [(x, width)]}: the vertical lines that cover each staff
    from its top line to its bottom line, are not note stems, and do not run
    far past the staff except into the staff above or below."""
    order = sorted(staves, key=lambda s: s.top)
    out = {}
    for k, staff in enumerate(order):
        space = staff.space
        above = _neighbour(order[:k][::-1], staff)
        below = _neighbour(order[k + 1:], staff)
        found = []
        for x, top, bottom, width in verticals:
            if not (staff.x0 + 0.5 * space < x <= staff.x1 + 0.5 * space):
                continue
            if top > staff.top + 0.2 * space or bottom < staff.bottom - 0.2 * space:
                continue
            if top < staff.top - 1.5 * space and not (above and top <= above.bottom + 0.6 * space):
                continue
            if bottom > staff.bottom + 1.5 * space and not (below and bottom >= below.top - 0.6 * space):
                continue
            if _is_stem(x, top, bottom, notes, space):
                continue
            found.append((x, width))
        out[id(staff)] = sorted(found)
    return out


def _neighbour(candidates, staff):
    """The nearest staff in `candidates` (in order of distance) that overlaps `staff` along the page."""
    for other in candidates:
        if min(other.x1, staff.x1) - max(other.x0, staff.x0) > 0.5 * min(other.x1 - other.x0, staff.x1 - staff.x0):
            return other
    return None


BAR_NUMBER = re.compile(r"^\(?\d+\)?$")


CLEF_NAMES = ("gClef", "fClef", "cClef", "gClef8vb", "gClef8va", "fClef8vb", "cClef8vb")


def _starts_system(staff, text, symbols=()):
    """A bar number just above the left end of the staff: engravers number
    the first bar of each system, so the staff starts a system. The 8 under
    an octave clef of the staff above is not a bar number."""
    space = staff.space
    clefs = [s.box for s in symbols if s.name in CLEF_NAMES]

    def under_clef(box):
        return any(c[0] - space <= (box[0] + box[2]) / 2 <= c[2] + space and c[1] < box[1] <= c[3] + 2 * space
                   for c in clefs)

    return any(BAR_NUMBER.match(run.text.strip()) and staff.top - 4 * space <= run.box[3] <= staff.top + 0.5 * space
               and staff.x0 - 3 * space <= run.box[2] <= staff.x0 + 3 * space and not under_clef(run.box)
               for run in text)


def join_systems(staves, verticals, symbols, barlines, page_number, system_gap=None, text=()):
    """Group the staves into systems (rule 3). `barlines` is staff_barlines().
    `system_gap` is the gap between systems (system_gaps); staves joined only
    by their barlines must be clearly closer than that, and not when the
    lower staff has a bar number at its start (`text` is the page's text)."""
    parent = list(range(len(staves)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(len(staves)), key=lambda i: staves[i].top)
    for a, b in zip(order, order[1:]):
        upper, lower = staves[a], staves[b]
        if min(upper.x1, lower.x1) - max(upper.x0, lower.x0) < 0.5 * min(upper.x1 - upper.x0, lower.x1 - lower.x0):
            continue
        space = upper.space
        # a line that crosses the gap and starts at a staff (this one, or one
        # higher up when the line joins a whole system)
        starts = [st.top for st in staves if st.top <= upper.top]
        bridged = any(
            top <= upper.bottom + 0.5 * space and bottom >= lower.top - 0.5 * space
            and any(st_top - 4 * space <= top <= st_top + space for st_top in starts)
            and min(upper.x0, lower.x0) - 3 * space <= x <= max(upper.x1, lower.x1) + space
            for x, top, bottom, _ in verticals)
        if not bridged:
            bridged = any(
                s.name in BRACE_NAMES and s.box[1] <= upper.middle and s.box[3] >= lower.middle
                and s.box[2] <= min(upper.x0, lower.x0) + space
                for s in symbols)
        if (not bridged and system_gap and lower.top - upper.bottom <= ALIGNED_GAP * system_gap
                and not _starts_system(lower, text, symbols)):
            bridged = _aligned(upper, lower, barlines)
        if bridged:
            parent[root(b)] = root(a)
    groups = {}
    for i in order:
        groups.setdefault(root(i), []).append(staves[i])
    systems = []
    for index, members in enumerate(sorted(groups.values(), key=lambda g: g[0].top)):
        for staff in members:
            staff.system = index
        systems.append(System(page_number, index, members,
                              statistics.median(s.x0 for s in members), statistics.median(s.x1 for s in members)))
    return systems


ALIGNED_GAP = 0.8


def _aligned(upper, lower, barlines):
    """Two staves with the same ends whose barlines (other than the one at the
    end of the system) fall at the same places, at least one: one system
    whose engraver drew no line joining the staves (LilyPond choir staves).
    The caller also requires the gap between them to be clearly smaller than
    the gap between systems, since two systems of repeated music can have
    their barlines in the same places."""
    if abs(upper.x0 - lower.x0) > 1.5 or abs(upper.x1 - lower.x1) > 1.5:
        return False
    a = [x for x, _ in barlines[id(upper)] if x < upper.x1 - upper.space]
    b = [x for x, _ in barlines[id(lower)] if x < lower.x1 - lower.space]
    if not a or len(a) != len(b):
        return False
    return all(abs(x - y) <= 0.6 for x, y in zip(a, b))


def _gaps(staves):
    order = sorted(staves, key=lambda s: s.top)
    return [b.top - a.bottom for a, b in zip(order, order[1:]) if _neighbour([b], a)]


def system_gaps(staves_by_page):
    """The gap between systems on each page: the page's largest gap between
    staves where the page has two clearly different gaps (within systems and
    between them), else the median of those values over the document (a page
    of one system, or of one-staff systems, shows only one kind of gap)."""
    own = []
    for staves in staves_by_page:
        gaps = _gaps(staves)
        own.append(max(gaps) if gaps and max(gaps) >= 1.25 * min(gaps) else None)
    known = [g for g in own if g is not None]
    fallback = statistics.median(known) if known else None
    return [g if g is not None else fallback for g in own]


# --------------------------------------------------------------- barlines

def find_barlines(system, barlines):
    """Barline groups of a system (rule 4): positions where at least half the
    staves have a barline, joined into groups when close."""
    space = statistics.median(s.space for s in system.staves)
    hits = sorted((x, w, k) for k, staff in enumerate(system.staves) for x, w in barlines[id(staff)])
    positions = []
    for x, width, k in hits:
        if positions and abs(positions[-1][0] - x) <= 0.6:
            positions[-1][1].add(k)
            positions[-1][2] = max(positions[-1][2], width)
        else:
            positions.append([x, {k}, width])
    needed = max(1, (len(system.staves) + 1) // 2)
    positions = [(x, w) for x, staves_hit, w in positions if len(staves_hit) >= needed]
    groups = []
    for x, w in positions:
        thick = w >= 0.3 * space
        if groups and x - groups[-1].x1 <= 1.2 * space:
            groups[-1].lines.append((x, thick))
            groups[-1].x1 = x
        else:
            groups.append(Barline(x, x, [(x, thick)]))
    return groups


def _is_stem(x, top, bottom, notes, space):
    """The line is a note stem: a notehead sits at its bottom end with the
    line at the notehead's right edge (stem up), or at its top end with the
    line at its left edge (stem down). Notes are (x, y, ink box)."""
    for nx, ny, box in notes:
        if abs(ny - bottom) <= 0.6 * space and box[2] - 0.3 * space <= x <= box[2] + 0.15 * space:
            return True
        if abs(ny - top) <= 0.6 * space and box[0] - 0.15 * space <= x <= box[0] + 0.3 * space:
            return True
    return False


def mark_repeats(barline, dots, staff_list):
    """Set the repeat flags from dots in the two spaces either side of the
    middle line of a staff, just left or right of the group."""
    for staff in staff_list:
        space = staff.space
        for side in ("before", "after"):
            lo, hi = (barline.x0 - 1.6 * space, barline.x0) if side == "before" else (barline.x1, barline.x1 + 1.6 * space)
            steps = {round(staff.exact_step(y)) for x, y in dots if lo <= x <= hi
                     and abs(staff.exact_step(y) - round(staff.exact_step(y))) < 0.4}
            if {3, 5} <= steps:
                setattr(barline, f"repeat_{side}", True)


# -------------------------------------------------------------------- bars

def make_bars(system, music_xs, counts=()):
    """Bars of a system (rule 5). `music_xs` are the x of the notes and rests
    in it, `counts` (x, y, digit) of digits over a staff: a multi-bar rest's
    count, which MuseScore draws over an empty bar (the rest itself is lines).
    Such a bar stands for that many bars: the first keeps its width, the
    others are slivers before its end barline."""
    bars = []
    start_x, start_line = system.x0, None
    for i, group in enumerate(system.barlines):
        empty = not any(start_x < x < group.x0 for x in music_xs)
        # at the end of the system the next bar is on the next one: taken to have music
        next_x = system.barlines[i + 1].x0 if i + 1 < len(system.barlines) else system.x1
        next_has_music = group.x1 >= system.x1 - 1 or any(group.x1 < x < next_x for x in music_xs)
        if empty and not bars and (group.repeat_after or group.kind == "heavy-light"):
            pass    # a start repeat after the clef: it opens the first bar
        elif empty and bars and group.x0 - start_x < 2 * system.staves[0].space:
            pass    # too narrow to be a bar (a double line drawn as two groups)
        elif (empty and bars and start_line is not None and start_line.kind != "single"
              and next_has_music and not _count(counts, start_x, group.x0)):
            # LilyPond draws an empty bar after a double or end-repeat barline,
            # before a start repeat or a change; it joins the next bar, which
            # keeps its signatures. MuseScore and Verovio draw one holding only
            # a key or time change. Kept: a bar before another empty one (bars
            # of hidden rests, which a score can have), and a bar with digits
            # over the staff (MuseScore draws a multi-bar rest as lines, its
            # count in time signature digits).
            start_line = group
            continue
        else:
            n = _count(counts, start_x, group.x0) if empty else 0
            if n > 1:
                # the first bar keeps the clef, key and time; the rest are slivers before the barline
                edges = [start_x] + [group.x0 - 0.01 * (n - i) for i in range(1, n)] + [group.x0]
                bars.extend(Bar(edges[i], edges[i + 1], start_line if i == 0 else None,
                                group if i == n - 1 else None) for i in range(n))
            else:
                bars.append(Bar(start_x, group.x0, start_line, group))
        start_x, start_line = group.x1, group
    if any(x > start_x for x in music_xs):
        bars.append(Bar(start_x, system.x1, start_line, None))
    return bars


def _count(counts, x0, x1):
    """The number written over the bar from x0 to x1: its digits nearest the
    top of the page (the count is repeated over every staff), left to right.
    0 if none."""
    inside = [(x, y, d) for x, y, d in counts if x0 < x < x1]
    if not inside:
        return 0
    top = min(y for _, y, _ in inside)
    digits = sorted((x, d) for x, y, d in inside if y - top < 2.0)
    return int("".join(d for _, d in digits))


# ---------------------------------------------------------------- the page

def attach(staves, symbols):
    """{id(symbol): (staff, step)}: each symbol on the staff that is nearest to
    it vertically among those whose span covers its x."""
    out = {}
    for s in symbols:
        best, best_d = None, None
        for staff in staves:
            if not (staff.x0 - 6 * staff.space <= s.x <= staff.x1 + 3 * staff.space):
                continue
            if staff.top <= s.y <= staff.bottom:
                d = 0.0
            else:
                d = min(abs(s.y - staff.top), abs(s.y - staff.bottom))
            if best_d is None or d < best_d:
                best, best_d = staff, d
        if best is not None and best_d <= 10 * best.space:
            out[id(s)] = (best, best.step(s.y))
    return out


def page_lines(page):
    _, _, candidates, _ = evidence.read_drawings(page)
    return horizontal_lines(candidates)


PERCUSSION_CLEFS = ("unpitchedPercussionClef1", "unpitchedPercussionClef2")


def one_line_staves(lines, staves, symbols, page_number):
    """One-line staves (percussion): a single line at least six staff spaces
    long, outside every five-line staff, with a percussion clef on it near
    its start. Each is kept as a five-line staff centred on its line, with
    the page's staff space, so that its notes, rests and barlines are read as
    on any staff (a note on the line is on the middle line)."""
    if not staves:
        return []
    space = statistics.median(s.space for s in staves)
    found = []
    for clef in (s for s in symbols if s.name in PERCUSSION_CLEFS):
        middle = (clef.box[1] + clef.box[3]) / 2
        if any(st.top - 0.5 * space <= middle <= st.bottom + 0.5 * space for st in staves + found):
            continue
        near = [l for l in lines if abs(l.y - middle) <= 0.5 * space and l.length >= 6 * space
                and l.thickness <= space / 3 and l.x0 - space <= clef.box[0] <= l.x0 + 6 * space]
        if near:
            line = max(near, key=lambda l: l.length)
            found.append(Staff(page_number, line.y - 2 * space, space, line.x0, line.x1, lines=1))
    return found


def read_document(doc, pages):
    """Layouts of the pages of a document, from their Stage 1.1 PageSymbols."""
    lines = [page_lines(doc[p.page - 1]) for p in pages]
    staves = [find_staves(l, p.page) for l, p in zip(lines, pages)]
    for l, p, found in zip(lines, pages, staves):
        found.extend(one_line_staves(l, found, p.symbols, p.page))
        found.sort(key=lambda s: (s.top, s.x0))
    gaps = system_gaps(staves)
    return [read_layout(p, doc[p.page - 1], s, g, l) for p, s, g, l in zip(pages, staves, gaps, lines)]


def read_layout(page_symbols, page, staves=None, system_gap=None, lines=None):
    """The layout of one page from its Stage 1.1 PageSymbols."""
    number = page_symbols.page
    if lines is None:
        lines = page_lines(page)
    if staves is None:
        staves = find_staves(lines, number)
    if system_gap is None:
        system_gap = system_gaps([staves])[0]
    symbols = page_symbols.symbols
    verticals = vertical_lines(page)
    notes = [(s.x, s.y, s.box) for s in symbols if is_note(s.name)]
    barlines = staff_barlines(staves, verticals, notes)
    systems = join_systems(staves, verticals, symbols, barlines, number, system_gap, page_symbols.text)
    layout = PageLayout(number, staves, systems, symbols, page_symbols.text,
                        horizontals=lines, verticals=verticals)
    if not staves:
        return layout
    layout.attached = attach(staves, symbols)
    # by the middle of the ink: fonts differ in where a dot's origin is
    dots = [((s.box[0] + s.box[2]) / 2, (s.box[1] + s.box[3]) / 2) for s in symbols if s.name in DOT_NAMES]
    for system in systems:
        members = {id(st) for st in system.staves}
        system.barlines = find_barlines(system, barlines)
        for group in system.barlines:
            mark_repeats(group, dots, system.staves)
        music = [s.x for s in symbols if (is_note(s.name) or is_rest(s.name))
                 and id(layout.staff_of(s)) in members]
        counts = [(s.x, s.y, s.name[-1]) for s in symbols if s.name.startswith("timeSig") and s.name[-1].isdigit()
                  and id(layout.staff_of(s)) in members and s.box[3] <= layout.staff_of(s).top]
        system.bars = make_bars(system, music, counts)
    return layout
