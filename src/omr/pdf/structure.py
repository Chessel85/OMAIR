"""The structure of a score from its page layouts (Stage 1.2): parts, bars,
clefs, key and time signatures, repeats, endings and navigation marks.

The result is an omr.evaluate.events.Score with parts, bars and structure
events (no notes yet), so the harness's own rules (restatements, decision 11)
apply to it unchanged. The rules are in docs/notes/layout-spec.md, "From
layout to structure".
"""

import re
import statistics
from dataclasses import dataclass, field
from fractions import Fraction

from omr.evaluate import events
from omr.pdf import layout as lay

CLEFS = {
    # SMuFL name: (sign, octave change)
    "gClef": ("G", 0), "gClefChange": ("G", 0), "gClef8vb": ("G", -1), "gClef8va": ("G", 1),
    "gClef15mb": ("G", -2), "gClef15ma": ("G", 2), "fClef": ("F", 0), "fClefChange": ("F", 0),
    "fClef8vb": ("F", -1), "fClef8va": ("F", 1), "cClef": ("C", 0), "cClefChange": ("C", 0),
    "cClef8vb": ("C", -1), "unpitchedPercussionClef1": ("percussion", 0),
    "unpitchedPercussionClef2": ("percussion", 0), "6stringTabClef": ("TAB", 0),
}
SHARP, FLAT, NATURAL = "accidentalSharp", "accidentalFlat", "accidentalNatural"
TIME_DIGITS = {f"timeSig{i}": str(i) for i in range(10)}
TIME_SYMBOLS = {"timeSigCommon": "4/4", "timeSigCutCommon": "2/2"}
NAVIGATION_GLYPHS = {"segno": "segno", "segnoSerpent1": "segno", "coda": "coda", "codaSquare": "coda"}
NAVIGATION_TEXT = (
    (re.compile(r"^\s*D\.?\s*S\.?", re.I), "dalsegno"),
    (re.compile(r"^\s*D\.?\s*C\.?|^\s*da\s+capo", re.I), "dacapo"),
    (re.compile(r"^\s*to\s+coda", re.I), "tocoda"),
    (re.compile(r"^\s*fine\s*$", re.I), "fine"),
)
# "1.", "2", "1, 2.", "1.-3.": ending numbers
ENDING_TEXT = re.compile(r"^\s*\d+\s*(?:[,.\-–]\s*\d+\s*)*\.?\s*$")


@dataclass
class SystemParts:
    """How a system's staves map to the score's parts: for each staff of the
    system, (part index, staff number in the part from 1)."""

    system: object
    staves: list = field(default_factory=list)


# ------------------------------------------------------------------ parts

def staff_groups(system, symbols, text=()):
    """Staves of a system grouped into instruments: staves joined by a brace
    are one part unless each has its own instrument name (a brace can also
    group two instruments), and two staves with one name centred in the gap
    between them and no name of their own are one part (engravers that draw
    no brace). Every other staff is a part of its own."""
    staves = system.staves
    joined = [False] * len(staves)     # joined[k]: staff k and k + 1 are one part
    on_staff, in_gap = set(), set()
    for run in text:
        if run.box[2] > system.x0 + 0.5 * staves[0].space:
            continue
        middle = (run.box[1] + run.box[3]) / 2
        for k, staff in enumerate(staves):
            if staff.top - staff.space <= middle <= staff.bottom + staff.space:
                on_staff.add(k)
            elif k + 1 < len(staves) and staff.bottom + staff.space < middle < staves[k + 1].top - staff.space:
                in_gap.add(k)
    for brace in (s for s in symbols if s.name in lay.BRACE_NAMES):
        for k in range(len(staves) - 1):
            space = staves[k].space
            if not staves[k].x0 - 5 * space <= brace.box[2] <= staves[k].x0 + space:
                continue
            if brace.box[1] - space <= staves[k].middle and brace.box[3] + space >= staves[k + 1].middle:
                # a brace over two named staves groups two instruments (two voices)
                if not (k in on_staff and k + 1 in on_staff):
                    joined[k] = True
    for k in in_gap:
        if k not in on_staff and k + 1 not in on_staff:
            joined[k] = True
    groups = [[0]] if staves else []
    for k in range(1, len(staves)):
        if joined[k - 1]:
            groups[-1].append(k)
        else:
            groups.append([k])
    return groups


def _initial_clef(page_layout, staff):
    """The name of the first clef on a staff, near its start, or None."""
    clefs = [s for s in page_layout.symbols if s.name in CLEFS and page_layout.staff_of(s) is staff
             and s.x <= staff.x0 + 6 * staff.space]
    return min(clefs, key=lambda s: s.x).name if clefs else None


def _names_at_left(page_layout, system):
    """{staff index: text} for text runs left of the system, by the staff
    whose middle is nearest the run's middle."""
    out = {}
    for run in page_layout.text:
        if run.box[2] > system.x0 + 0.5 * system.staves[0].space:
            continue
        middle = (run.box[1] + run.box[3]) / 2
        nearest = min(range(len(system.staves)), key=lambda k: abs(system.staves[k].middle - middle))
        staff = system.staves[nearest]
        if abs(staff.middle - middle) <= 6 * staff.space:
            out.setdefault(nearest, []).append(run.text)
    return {k: " ".join(v) for k, v in out.items()}


def assign_parts(layouts):
    """[(page layout, system, SystemParts)] in score order, and the part list
    [(name, staves)]. The system with the most staves (the first if several)
    sets the parts; a system with fewer staves (empty staves hidden) is matched
    to it by instrument names where it has them, else by the clef of each staff."""
    systems = [(pl, sy) for pl in layouts for sy in pl.systems]
    if not systems:
        return [], []
    master_pl, master = max(systems, key=lambda ps: len(ps[1].staves))
    groups = staff_groups(master, master_pl.symbols, master_pl.text)
    names = _names_at_left(master_pl, master)
    parts = []
    master_slots = []      # for each master staff: (part, staff number)
    master_clefs = []
    for p, group in enumerate(groups):
        name = " ".join(names[k] for k in group if k in names)
        parts.append((name, len(group)))
        for n, k in enumerate(group, 1):
            master_slots.append((p, n))
            master_clefs.append(_initial_clef(master_pl, master.staves[k]))
    master_names = [names.get(k, "") for k in range(len(master.staves))]
    out = []
    for pl, sy in systems:
        mapping = SystemParts(sy)
        if len(sy.staves) == len(master.staves):
            mapping.staves = list(master_slots)
        else:
            chosen = _match_staves(pl, sy, master_names, master_clefs)
            mapping.staves = [master_slots[k] for k in chosen]
        out.append((pl, sy, mapping))
    return out, parts


def _match_staves(page_layout, system, master_names, master_clefs):
    """Indices of the master staves that the system's staves are, in order:
    the in-order choice that best agrees on names (short names allowed) and
    clefs."""
    names = _names_at_left(page_layout, system)
    clefs = [_initial_clef(page_layout, st) for st in system.staves]
    n, m = len(system.staves), len(master_names)
    if n > m:
        return list(range(m)) + [m - 1] * (n - m)

    def score(i, j):
        s = 0.0
        if names.get(i) and master_names[j]:
            s += 2.0 if _same_name(names[i], master_names[j]) else -2.0
        if clefs[i] and master_clefs[j]:
            s += 1.0 if clefs[i] == master_clefs[j] else -1.0
        return s

    # best[i][j]: the best total for the first i system staves within the first j master staves
    best = [[float("-inf")] * (m + 1) for _ in range(n + 1)]
    take = [[False] * (m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        best[0][j] = 0.0
    for i in range(1, n + 1):
        for j in range(i, m + 1):
            skip = best[i][j - 1]
            use = best[i - 1][j - 1] + score(i - 1, j - 1)
            if use >= skip:
                best[i][j], take[i][j] = use, True
            else:
                best[i][j] = skip
    chosen, i, j = [], n, m
    while i > 0:
        if take[i][j]:
            chosen.append(j - 1)
            i -= 1
        j -= 1
    return chosen[::-1]


def _same_name(short, full):
    a = re.sub(r"[^a-z0-9]", "", short.lower())
    b = re.sub(r"[^a-z0-9]", "", full.lower())
    return bool(a) and bool(b) and (a == b or b.startswith(a[:3]) or a.startswith(b[:3]))


# ---------------------------------------------------------- per staff

def _start(system, k):
    """Where bar k's content starts: the first bar includes everything from
    the start of the system (clef, key and time before a start repeat)."""
    return system.x0 if k == 0 else system.bars[k].x0


def _bar_of(system, x):
    """Index of the bar of the system that holds x, or None if x is after the
    last barline (courtesy signatures)."""
    for k, bar in enumerate(system.bars):
        if _start(system, k) - 0.01 <= x < bar.x1 or (k == len(system.bars) - 1 and bar.end is None and x >= bar.x0):
            return k
    return None


def _music(page_layout, staff):
    """The x of the notes and rests of a staff, at full size: a small
    notehead is a metronome mark, a cue or a grace note, which can stand over
    a time signature or before the first note."""
    return sorted(s.x for s in page_layout.symbols
                  if (lay.is_note(s.name) or lay.is_rest(s.name)) and page_layout.staff_of(s) is staff
                  and s.size >= 3 * staff.space)


def clef_value(name, step):
    sign, octave = CLEFS[name]
    if sign in ("G", "F", "C"):
        line = max(1, min(5, round(step / 2) + 1))
        value = f"{sign} {line}"
    elif sign == "TAB":
        value = "TAB 5"
    else:
        value = "percussion"
    if octave:
        value += f" octave {octave:+d}"
    return value


def staff_clefs(page_layout, system, staff):
    """[(bar index in system, at start, rank, value)]: the clefs of a staff.
    A clef after the last note of its bar belongs to the start of the next
    bar; one after the last note of the system is a courtesy clef and is left
    out (the next system shows it)."""
    music = _music(page_layout, staff)
    out = []
    for s in sorted((s for s in page_layout.symbols if s.name in CLEFS and page_layout.staff_of(s) is staff),
                    key=lambda s: s.x):
        k = _bar_of(system, s.x)
        if k is None:
            continue
        bar = system.bars[k]
        before = any(_start(system, k) <= x < s.x for x in music)
        after = any(s.x < x < bar.x1 for x in music)
        value = clef_value(s.name, page_layout.step_of(s))
        octave = _octave_digits(page_layout, s)
        if octave and " octave" not in value:
            value += f" octave {octave:+d}"
        if not before and not after and k + 1 < len(system.bars) and s.x > (_start(system, k) + bar.x1) / 2:
            out.append((k + 1, True, 0, value))   # in an empty bar, near its end: for the next bar
        elif not before:
            out.append((k, True, 0, value))
        elif not after:
            if k + 1 < len(system.bars):
                out.append((k + 1, True, 0, value))
        else:
            rank = sum(1 for x in music if _start(system, k) <= x < s.x)
            out.append((k, False, rank, value))
    return out


def _at_clef(clef, box):
    """A box is an octave mark of the clef: centred on it, and touching its
    top or bottom (a bar number above the first clef of a system is further
    off and not centred)."""
    width = clef.box[2] - clef.box[0]
    gap = 0.15 * (clef.box[3] - clef.box[1])
    centre = (clef.box[0] + clef.box[2]) / 2
    if abs((box[0] + box[2]) / 2 - centre) > 0.3 * width:
        return False
    return -gap <= box[1] - clef.box[3] <= gap or -gap <= clef.box[1] - box[3] <= gap


def _clef_digits(page_layout, clef):
    """Small music digits that are an octave mark of a clef."""
    return [s for s in page_layout.symbols if s.name in TIME_DIGITS and s.size < 0.8 * clef.size
            and _at_clef(clef, s.box)]


def _octave_digits(page_layout, clef):
    """The octave change shown by a small 8 or 15 at a clef (LilyPond writes
    an octave clef this way), drawn as music digits or as text: -1 for an 8
    below, +2 for a 15 above; 0 if none."""
    marks = [(TIME_DIGITS[d.name], d.box) for d in _clef_digits(page_layout, clef)]
    marks += [(run.text.strip(), run.box) for run in page_layout.text
              if run.text.strip() in ("8", "15", "22") and _at_clef(clef, run.box)]
    if not marks:
        return 0
    marks.sort(key=lambda m: m[1][0])
    octaves = {"8": 1, "15": 2, "22": 3}.get("".join(m[0] for m in marks), 0)
    below = statistics.mean(m[1][1] for m in marks) > (clef.box[1] + clef.box[3]) / 2
    return -octaves if below else octaves


def _signature_region(page_layout, system, staff, k):
    """The symbols of a staff that can be bar k's key or time signature:
    those before its first note or rest, and those after the last note or
    rest of the bar before (an engraver puts a change before a start-repeat
    barline, after the last note of the previous bar)."""
    music = _music(page_layout, staff)
    start, end = _start(system, k), system.bars[k].x1
    inside = [x for x in music if start <= x < end]
    first = min(inside) if inside else end
    lo = start
    if k > 0:
        before = [x for x in music if _start(system, k - 1) <= x < system.bars[k - 1].x1]
        if before:
            lo = max(before) + 0.01
    return [s for s in page_layout.symbols if page_layout.staff_of(s) is staff and lo - 0.01 <= s.x < first]


LETTERS = {"G": 4, "F": 3, "C": 0}
SHARP_ORDER = (3, 0, 4, 1, 5, 2, 6)   # F C G D A E B, as letters C=0 ... B=6
FLAT_ORDER = (6, 2, 5, 1, 4, 0, 3)    # B E A D G C F


def _letter(clef, step):
    """The letter (C=0 ... B=6) of a staff step under a clef value such as "G 2"."""
    parts = clef.split()
    if parts[0] not in LETTERS:
        return None
    line = int(parts[1])
    return (LETTERS[parts[0]] + step - 2 * (line - 1)) % 7


def _clef_before(page_layout, staff, x):
    clefs = [s for s in page_layout.symbols if s.name in CLEFS and page_layout.staff_of(s) is staff and s.x < x]
    if not clefs:
        return None
    last = max(clefs, key=lambda s: s.x)
    return clef_value(last.name, page_layout.step_of(last))


def staff_keys(page_layout, system, staff):
    """[(bar index, fifths)]: key signatures in each bar's signature region:
    a run of sharps or of flats whose letters follow the order of a key
    signature under the clef in force (F C G D A E B for sharps, B E A D G C
    F for flats), possibly after naturals cancelling the old key; or naturals
    alone (a change to no sharps or flats). A system that starts with no
    accidentals has no sharps or flats. An accidental with a notehead just
    to its right on its step belongs to that note."""
    out = []
    notes = [(s.x, page_layout.step_of(s)) for s in page_layout.symbols
             if lay.is_note(s.name) and page_layout.staff_of(s) is staff]
    for k in range(len(system.bars)):
        region = _signature_region(page_layout, system, staff, k)
        every = sorted((s for s in region if s.name in (SHARP, FLAT, NATURAL)), key=lambda s: s.x)
        if not every:
            if k == 0:
                # A system that starts with no key signature has no sharps or
                # flats: a change to C at a system break shows only as courtesy
                # naturals at the end of the system before, which are left out.
                out.append((0, 0))
            continue
        every = _close_run(every, staff.space)
        free = [s for s in every if not any(0 < nx - s.x <= 3.5 * staff.space and ns == page_layout.step_of(s)
                                             for nx, ns in notes)]
        # A run of two or more that follows the key-signature order is a key
        # signature even where a note sits on an accidental's step just after
        # it; a single accidental must be free of notes (it is otherwise the
        # first note's own accidental).
        # (A chord's accidentals each have a note on their step: then at least
        # one accidental of the run must be free of notes.)
        whole = _key_of(page_layout, staff, every) if len(every) >= 2 and free else None
        fifths = whole if whole is not None else _key_of(page_layout, staff, free)
        if fifths is not None:
            out.append((k, fifths))
    return out


def _close_run(accidentals, space):
    """The accidentals from the first while each is close to the one before:
    a key signature's accidentals are evenly spaced, about a staff space apart."""
    run = accidentals[:1]
    for s in accidentals[1:]:
        if s.x - run[-1].x > 1.6 * space:
            break
        run.append(s)
    return run


def _key_of(page_layout, staff, accidentals):
    """The fifths of a run of accidentals if it is a key signature, else None."""
    if not accidentals:
        return None
    clef = _clef_before(page_layout, staff, accidentals[0].x + 0.01)
    sharps = [s for s in accidentals if s.name == SHARP]
    flats = [s for s in accidentals if s.name == FLAT]
    if sharps and flats:
        return None
    signs = sharps or flats
    if not signs:
        return 0
    if any(s.name == NATURAL and s.x > signs[0].x for s in accidentals):
        return None    # naturals after the new signs: not a key signature
    order = SHARP_ORDER if sharps else FLAT_ORDER
    if clef:
        letters = [_letter(clef, page_layout.step_of(s)) for s in signs]
        if None not in letters and tuple(letters) != order[:len(letters)]:
            return None
    return len(signs) if sharps else -len(signs)


def staff_times(page_layout, system, staff):
    """[(bar index, "beats/beat-type")]: time signatures in each bar's
    signature region: digits stacked above and below the middle line, or a
    common or cut time symbol."""
    out = []
    for k in range(len(system.bars)):
        region = _signature_region(page_layout, system, staff, k)
        symbols = [s for s in region if s.name in TIME_SYMBOLS]
        if symbols:
            out.append((k, TIME_SYMBOLS[symbols[0].name]))
            continue
        at_clefs = {id(d) for c in region if c.name in CLEFS for d in _clef_digits(page_layout, c)}
        digits = sorted((s for s in region if s.name in TIME_DIGITS and id(s) not in at_clefs), key=lambda s: s.x)
        if not digits:
            continue
        x0 = digits[0].x
        group = sorted((s for s in digits if s.x <= x0 + 3 * staff.space), key=lambda s: s.x)
        # by the middle of the ink: SMuFL digits are centred on their origin,
        # Emmentaler's stand on it
        upper = "".join(TIME_DIGITS[s.name] for s in group if staff.exact_step((s.box[1] + s.box[3]) / 2) > 4)
        lower = "".join(TIME_DIGITS[s.name] for s in group if staff.exact_step((s.box[1] + s.box[3]) / 2) < 4)
        if upper and lower:
            out.append((k, f"{int(upper)}/{int(lower)}"))
    return out


# ------------------------------------------------------- endings and text

def system_endings(page_layout, system, horizontals):
    """[(start bar, end bar, numbers, closed)]: volta brackets over the system:
    a number such as "1." or "1, 2." above the top staff, at the left end of a
    horizontal line with a hook down at its start."""
    top = system.staves[0]
    space = top.space
    out = []
    for run in page_layout.text:
        match = ENDING_TEXT.match(run.text)
        if not match or run.box[3] > top.top + 0.5 * space or run.box[3] < top.top - 8 * space:
            continue
        if not system.x0 - space <= run.box[0] <= system.x1:
            continue
        numbers = " ".join(re.findall(r"\d+", run.text))
        lines = [h for h in horizontals if run.box[0] - 2 * space <= h.x0 <= run.box[0] + 0.5 * space
                 and run.box[1] - 2 * space <= h.y <= run.box[1] + 0.5 * space and h.length >= 2 * space
                 and h.thickness <= 0.3 * space]   # a beam is thicker
        if not lines:
            continue
        line = max(lines, key=lambda h: h.length)
        # A volta's number is at its left end, under a hook down from the
        # line; a tuplet bracket's number is in its middle.
        if run.box[0] - line.x0 > 1.5 * space:
            continue
        if not any(abs(x - line.x0) <= 0.6 and t <= line.y + 0.5 and b >= line.y + space
                   for x, t, b, _ in page_layout.verticals):
            continue
        # The ending stops at the first hook down from its line: the line may
        # have been joined with the next ending's line drawn just after it.
        hooks = sorted(x for x, t, b, _ in page_layout.verticals
                       if line.x0 + space <= x <= line.x1 + 0.6 and t <= line.y + 0.5 and b >= line.y + space)
        stop_x = hooks[0] if hooks else line.x1
        closed = bool(hooks)
        start = _bar_of(system, line.x0 + 0.5 * space)
        end = _bar_of(system, stop_x - 0.5 * space)
        if start is None:
            continue
        # A volta starts at the start of a bar (in the first bar of a system,
        # anywhere after the clef and key); a line over a fingering need not.
        if start > 0 and abs(line.x0 - system.bars[start].x0) > 1.5 * space:
            continue
        if end is None:
            end = len(system.bars) - 1
        out.append((start, end, numbers, closed))
    return out


def _continued_ending(page_layout, system, horizontals):
    """(end bar, "stop" or "discontinue") of an ending carried over from the
    previous system: a horizontal line above the top staff that starts in
    the system's first bar (after the clef and key) with no number at its
    start. (None, None) if there is none."""
    top = system.staves[0]
    space = top.space
    numbered = [run.box[0] for run in page_layout.text if ENDING_TEXT.match(run.text)]
    lines = [h for h in horizontals if h.x0 < system.bars[0].x1 and h.length >= 2 * space
             and top.top - 8 * space <= h.y < top.top - 0.5 * space
             and not any(abs(x - h.x0) <= 1.5 * space for x in numbered)]
    if not lines:
        return None, None
    line = max(lines, key=lambda h: h.length)
    hooks = [x for x, t, b, _ in page_layout.verticals
             if abs(x - line.x1) <= 0.6 and t <= line.y + 0.5 and b >= line.y + space]
    end = _bar_of(system, line.x1 - 0.5 * space)
    return (len(system.bars) - 1 if end is None else end), ("stop" if hooks else "discontinue")


def system_navigation(page_layout, system):
    """[(bar index, value)]: segno and coda signs and jump words over the system."""
    out = []
    top, bottom = system.staves[0], system.staves[-1]
    for s in page_layout.symbols:
        if s.name in NAVIGATION_GLYPHS and top.top - 8 * top.space <= s.y <= bottom.bottom + 8 * top.space:
            k = _bar_of(system, s.x)
            if k is not None:
                out.append((k, NAVIGATION_GLYPHS[s.name]))
    for run in page_layout.text:
        middle = (run.box[1] + run.box[3]) / 2
        if not top.top - 8 * top.space <= middle <= bottom.bottom + 8 * top.space:
            continue
        for pattern, value in NAVIGATION_TEXT:
            if pattern.match(run.text):
                k = _bar_of(system, min(run.box[2], system.x1 - 0.1))
                if k is not None:
                    out.append((k, value))
                break
    return out


# ------------------------------------------------------------------ score

def read_structure(layouts):
    """The score structure (an events.Score with no notes) from page layouts."""
    score = events.Score()
    ordered, parts = assign_parts(layouts)
    score.parts = [events.Part(name, staves) for name, staves in parts]
    bar_base = 0
    open_ending = None
    for pl, system, mapping in ordered:
        horizontals = getattr(pl, "horizontals", [])
        for k, bar in enumerate(system.bars):
            score.bars.append(events.Bar(str(bar_base + k + 1), pl.page, system.index + 1))
        for staff, (part, number) in zip(system.staves, mapping.staves):
            for k, start, rank, value in staff_clefs(pl, system, staff):
                onset = Fraction(0) if start else Fraction(rank, 1000)
                score.structure.append(events.Marking("clef", value, part, number, bar_base + k, onset))
        seen_parts = {}
        for staff, (part, number) in zip(system.staves, mapping.staves):
            if part in seen_parts:
                continue
            seen_parts[part] = staff
            for k, fifths in staff_keys(pl, system, staff):
                score.structure.append(events.Marking("key", str(fifths), part, None, bar_base + k, Fraction(0)))
            for k, value in staff_times(pl, system, staff):
                score.structure.append(events.Marking("time", value, part, None, bar_base + k, Fraction(0)))
        part_list = range(len(score.parts))
        for k, bar in enumerate(system.bars):
            if bar.start is not None and bar.start.repeat_after:
                for p in part_list:
                    score.structure.append(events.Marking("repeat", "forward", p, None, bar_base + k, Fraction(0)))
            if bar.end is not None and bar.end.repeat_before:
                for p in part_list:
                    score.structure.append(events.Marking("repeat", "backward", p, None, bar_base + k, Fraction(0)))
        endings = system_endings(pl, system, horizontals)
        if open_ending and system.bars and not any(start == 0 for start, _, _, _ in endings):
            numbers, last_bar = open_ending
            open_ending = None
            end, kind = _continued_ending(pl, system, horizontals)
            if end is None:   # no continuation: the ending stopped at the end of the last system
                end, kind = last_bar - bar_base, "discontinue"
            for p in part_list:
                score.structure.append(events.Marking("ending", f"{kind} {numbers}", p, None, bar_base + end, Fraction(0)))
        for start, end, numbers, closed in endings:
            reaches_end = end == len(system.bars) - 1 and not closed
            for p in part_list:
                score.structure.append(events.Marking("ending", f"start {numbers}", p, None, bar_base + start, Fraction(0)))
            if reaches_end and system is not ordered[-1][1]:
                open_ending = (numbers, bar_base + end)
                continue
            kind = "stop" if closed else "discontinue"
            for p in part_list:
                score.structure.append(events.Marking("ending", f"{kind} {numbers}", p, None, bar_base + end, Fraction(0)))
        for k, value in system_navigation(pl, system):
            score.structure.append(events.Marking("navigation", value, 0, None, bar_base + k, Fraction(0)))
        bar_base += len(system.bars)
    for p in range(len(score.parts)):
        if not any(e.kind == "key" and e.part == p and e.bar == 0 for e in score.structure):
            score.structure.append(events.Marking("key", "0", p, None, 0, Fraction(0)))
    score.bar_counts = [len(score.bars)] * len(score.parts)
    return score


def read_pdf(path):
    """(Score, [PageLayout]) for a vector PDF."""
    import pymupdf

    from omr.pdf import symbols

    doc = pymupdf.open(str(path))
    try:
        pages = symbols.read_document(doc)
        layouts = lay.read_document(doc, pages)
        return read_structure(layouts), layouts
    finally:
        doc.close()
