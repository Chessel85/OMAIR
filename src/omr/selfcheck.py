"""The self-check by re-rendering (Stage 2.8, DEV-3): the music read is
written as MusicXML, drawn again by Verovio with the page's system breaks,
and the drawing compared with the page bar by bar and staff by staff. A
staff bar whose noteheads, rests, dots, flags or accidentals differ from
the page's is flagged ("self-check"), with the first difference in words.

What is compared, on each side, for each staff bar: its columns, left to
right (noteheads and rests a column apart in time; a column is one onset
across the system's staves). For each column on the staff: each head's
staff position and kind (black, half, whole, breve), each rest's kind,
whether the column has a dot and which flag it has. Accidentals are
compared on the heads both sides have: a head the drawing gives an
accidental must have one on the page, and an accidental on the page must
give the alteration the drawing's note has (so a courtesy accidental and a
key signature's accidental beside a head do not count). Grace and cue
notes (heads under 0.85 of the usual height) are left out, and so
are bars with a multi-bar rest.

Horizontal spacing differs between engravers, so only the order of the
columns and what each holds are compared, not distances. The check sees
what the reader saw: a symbol the reader missed is missing on both sides.
What it catches is music placed or assembled wrongly from symbols read
rightly: a note in the wrong bar, a wrong length, a head read on the wrong
line through a clef, an alteration the page does not print.

Design and measured figures: docs/notes/selfcheck-spec.md.
"""

import os
import re
import statistics
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from omr.evaluate import events
from omr.pdf import layout as lay

RULE = "self-check"
SVG = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}href"
MEI = "{http://www.music-encoding.org/ns/mei}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

GRACE_SIZE = 0.85          # a head under this share of the usual size is a grace or cue note
COLUMN_GAP = 0.5           # spaces: heads and rests closer than this in x are one column
UNISON_GAP = 1.65          # spaces: heads on one line of a staff this close are one column (two voices' unison)
SECOND_GAP = 1.35          # spaces: heads a step apart on one staff this close are one column (a second)
THIRD_GAP = 0.0            # spaces: heads two steps apart on one staff this close are one column (voices pushed apart)
DOT_REACH = 3.0            # spaces right of a column's last head that its dots may be
ACCIDENTAL_REACH = 3.5     # spaces left of a head that its accidental may be
FAR_OFF = 5.0              # spaces off its own staff past which a drawn note is taken as on the nearest
GAP_REACH = 8.0            # spaces: a page head off its staff this near the next may belong to it

ALTERS = {"accidentalSharp": 1, "accidentalFlat": -1, "accidentalNatural": 0,
          "accidentalDoubleSharp": 2, "accidentalDoubleFlat": -2}
MEI_ALTERS = {"s": 1, "f": -1, "n": 0, "x": 2, "ss": 2, "ff": -2}


def enabled():
    """The self-check runs unless OMR_SELFCHECK is set to 0."""
    return os.environ.get("OMR_SELFCHECK", "1").strip() != "0"


# ------------------------------------------------------------------ items

@dataclass
class Item:
    """A head, rest, dot, flag or accidental on one staff of a bar, in
    staff spaces from the system's left (x) and staff positions (step: 0 on
    the bottom line, as layout.Staff.step counts)."""
    kind: str              # "head", "rest", "dot", "flag", "accidental"
    x: float
    step: int = 0
    value: str = ""        # head kind, rest name, flag name
    alter: int | None = None   # for a head in the drawing: its alteration; for an accidental: what it gives
    printed: bool = False      # for a head in the drawing: it has an accidental drawn
    other: tuple | None = None # for a head on the page between two staves of a part: (slot, step) on the other
    strokes: int | None = None # for a head with a stem: its beams and flags (on the page) or the ones its value needs


@dataclass
class Signature:
    """What one column holds on one staff."""
    steps: tuple
    rests: tuple
    dotted: bool
    flags: tuple
    kinds: dict     # step -> head kinds there
    strokes: tuple = ()   # the beams and flags of its stemmed heads

    def same_heads(self, other):
        """The same steps, and the page's kinds at each among the drawing's
        (one head the page shares between two voices of a unison may be two
        heads in the drawing)."""
        return self.steps == other.steps and all(k <= other.kinds.get(s, set()) or other.kinds.get(s, set()) <= k
                                                 for s, k in self.kinds.items())


@dataclass
class Column:
    x: float
    by_staff: dict = field(default_factory=dict)   # slot -> [Item] (heads and rests)


def head_kind(name):
    for word, kind in (("DoubleWhole", "breve"), ("Breve", "breve"), ("Whole", "whole"),
                       ("Half", "half"), ("Black", "black")):
        if word in name:
            return kind
    return name


def flag_kind(name):
    return re.sub(r"(Up|Down)$", "", name)


def rest_kind(name):
    # a breve rest is taken as a whole-bar rest, which long bars draw with it
    return "restWhole" if name in ("restWhole", "restWholeLegerLine", "restDoubleWhole") else (
        "restHalf" if name == "restHalfLegerLine" else name)


# ------------------------------------------------------------------ the page

def page_bars(score, ordered):
    """{(bar, slot): [Item]} from the page, and the bars to leave out, for
    each system whose bars line up with the score's."""
    by_system = {}
    for k, bar in enumerate(score.bars):
        by_system.setdefault((bar.page, bar.system), []).append(k)
    slots = _slots(score)
    found, skip = {}, set()
    for pl, system, mapping in ordered:
        bars = by_system.get((pl.page, system.index + 1), [])
        if len(bars) != len(system.bars):
            skip.update(bars)
            continue
        for k, bar in enumerate(system.bars):
            if bar.multirest > 1:
                skip.update(bars[k:k + bar.multirest])
        space = system.staves[0].space
        symbols = [s for st in system.staves for s in pl.on_staff(st)]
        usual = _usual_heights(symbols)
        spans = [(st.top, st.bottom) for st in system.staves]
        heads = [(s, nearest_staff(spans, s.y)) for s in symbols if lay.is_head(s.name)]
        for s in symbols:
            k = lay.bar_of(system, s.x)
            if k is None:
                continue
            n = nearest_staff(spans, s.y)
            if s.name == "augmentationDot":
                # a dot is on the staff of the note it follows (it can stand nearer another staff)
                n = min(((s.x - h.x, m) for h, m in heads if 0 < s.x - h.x <= DOT_REACH * space
                         and abs(s.y - h.y) <= 0.75 * space), default=(0, n))[1]
            slot = slots.get(mapping.staves[n]) if n < len(mapping.staves) else None
            if slot is None:
                continue
            item = _page_item(s, system.staves[n].step(s.y), (s.x - system.x0) / space, usual)
            if item is not None and item.kind == "head":
                item.strokes = pl.strokes.get(id(s))
            if item is not None and item.kind in ("head", "accidental", "dot"):
                item.other = _other_staff(system.staves, mapping.staves, slots, n, s.y)
            if item is not None:
                found.setdefault((bars[k], slot), []).append(item)
    return found, skip


def _off_staff(span, y):
    top, bottom = span
    return max(top - y, y - bottom, 0) / ((bottom - top) / 4)


def nearest_staff(spans, y):
    """The staff (top, bottom) nearest a height: inside it, or the nearer by
    its nearest line, the upper on a tie (to a quarter space), so that both
    sides place a note between two staves alike."""
    def distance(i):
        top, bottom = spans[i]
        space = (bottom - top) / 4
        return round(max(top - y, y - bottom, 0) / space * 4) / 4
    return min(range(len(spans)), key=lambda i: (distance(i), i))


def _other_staff(staves, places, slots, n, y):
    """(slot, step) on the neighbouring staff, for a head in the gap between
    two staves: the page's spacing and the drawing's differ, and a part's
    high or low notes can stand nearer the next staff, so either may hold it
    (`_placed` chooses by the drawing)."""
    staff = staves[n]
    m = n + 1 if y > staff.bottom else n - 1 if y < staff.top else None
    if m is None or not 0 <= m < len(staves) or m >= len(places):
        return None
    other = staves[m]
    far = max(other.top - y, y - other.bottom)
    if far > GAP_REACH * staff.space:
        return None
    return slots.get(places[m]), other.step(y)


def _usual_heights(symbols):
    """{name: the median ink height} for names used at least three times
    (Verovio's outlines all have one font size, so ink is compared)."""
    heights = {}
    for s in symbols:
        heights.setdefault("notehead" if lay.is_head(s.name) else s.name, []).append(s.box[3] - s.box[1])
    return {name: statistics.median(h) for name, h in heights.items() if len(h) >= 3}


def _small(s, usual):
    typical = usual.get("notehead" if lay.is_head(s.name) else s.name)
    return bool(typical) and s.box[3] - s.box[1] < GRACE_SIZE * typical


def _page_item(s, step, x, usual):
    name = s.name
    if lay.is_head(name):
        if _small(s, usual):
            return None
        return Item("head", x, step, head_kind(name))
    if lay.is_rest(name):
        if name.startswith("restHBar") or name.startswith("repeat"):
            return Item("multirest", x)
        return Item("rest", x, step, rest_kind(name))
    if name == "augmentationDot":
        return Item("dot", x, step)
    if name.startswith("flag") and ("Up" in name or "Down" in name):
        if _small(s, usual):
            return None
        return Item("flag", x, step, flag_kind(name))
    if name in ALTERS:
        if _small(s, usual):
            return None
        return Item("accidental", x, step, name, ALTERS[name])
    return None


def _slots(score):
    """(part, staff number) -> the staff's place from the top of the score."""
    slots, n = {}, 0
    for p, part in enumerate(score.parts):
        for number in range(1, part.staves + 1):
            slots[(p, number)] = n
            n += 1
    return slots


# ------------------------------------------------------------------ the drawing

def render(score):
    """The Verovio SVG pages and MEI of the score as the converter writes it,
    with its system and page breaks; None if Verovio cannot load it."""
    import verovio
    from omr import musicxml

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "selfcheck.musicxml"
        musicxml.write(score, path)
        tk = verovio.toolkit()
        tk.setOptions({"breaks": "encoded", "condense": "none", "header": "none", "footer": "none",
                       "mmOutput": False,
                       # a page wide enough that no system is squeezed: Verovio fits each system
                       # to the page, and a crowded one brings notes under a space apart
                       "pageWidth": 100000, "adjustPageHeight": True})
        if not tk.loadFile(str(path)):
            return None
        pages = [tk.renderToSVG(p) for p in range(1, tk.getPageCount() + 1)]
        return pages, tk.getMEI()


def _strokes(dur):
    """Beams or flags a note of MEI value `dur` has (None for a whole note or longer)."""
    try:
        n = int(dur)
    except (TypeError, ValueError):
        return None
    if n <= 1:
        return None
    return max(0, n.bit_length() - 3)   # 2 and 4: none, 8: one, 16: two ...


def mei_notes(mei):
    """({note id: (alteration, accidental written)}, {note id: the staff
    from 0 that a cross-staff note is drawn on}, {note id: the beams or
    flags its value needs}) from Verovio's MEI."""
    out, cross = {}, {}
    root = ET.fromstring(mei)
    durs = {}
    for chord in root.iter(MEI + "chord"):
        for note in chord.iter(MEI + "note"):
            durs[note.get(XML_ID)] = chord.get("dur")
    for note in root.iter(MEI + "note"):
        if note.get("dur"):
            durs[note.get(XML_ID)] = note.get("dur")
    strokes = {note_id: _strokes(dur) for note_id, dur in durs.items()}
    for note in root.iter(MEI + "note"):
        if note.get("staff"):     # a cross-staff note: drawn on another staff
            cross[note.get(XML_ID)] = int(note.get("staff").split()[0]) - 1
        alter, written = note.get("accid.ges") or note.get("accid"), note.get("accid") is not None
        for accid in note.iter(MEI + "accid"):
            if accid.get("accid"):
                alter, written = accid.get("accid"), True
            elif accid.get("accid.ges") and alter is None:
                alter = accid.get("accid.ges")
        out[note.get(XML_ID)] = (MEI_ALTERS.get(alter, 0) if alter else 0, written)
    for chord in root.iter(MEI + "chord"):
        if chord.get("staff"):
            for note in chord.iter(MEI + "note"):
                cross.setdefault(note.get(XML_ID), int(chord.get("staff").split()[0]) - 1)
    return out, cross, strokes


def drawn_bars(pages, mei):
    """{(bar, slot): [Item]} from the drawing, and the number of bars."""
    from omr.pdf import smufl

    notes, cross, strokes = mei_notes(mei)
    found = {}
    bar = 0
    for svg in pages:
        root = ET.fromstring(svg)
        for measure in root.iter(SVG + "g"):
            if measure.get("class") != "measure":
                continue
            staves = [g for g in measure if g.tag == SVG + "g" and g.get("class") == "staff"]
            lines = [_staff_lines(g) for g in staves]
            if not staves or None in lines:
                bar += 1
                continue
            space = (lines[0][1] - lines[0][0]) / 4
            x0 = _measure_left(staves[0])
            uses = []
            for slot, g in enumerate(staves):
                start = len(uses)
                _collect(g, None, False, uses)
                uses[start:] = [(slot,) + u for u in uses[start:]]
            heads = [u[-1] for u in uses if u[1] == "head"]
            usual = statistics.median(heads) if heads else 0
            for own, kind, code, x, y, note_id, scale in uses:
                # a note stays on the staff it was written on, unless the MEI says it is drawn on another
                if kind == "head" and note_id in cross and 0 <= cross[note_id] < len(lines):
                    slot = cross[note_id]
                elif _off_staff(lines[own], y) > FAR_OFF:
                    slot = nearest_staff(lines, y)
                else:
                    slot = own
                top, bottom = lines[slot]
                step = round((bottom - y) / ((bottom - top) / 8))
                name = smufl.name_of(code) or "" if code is not None else ""
                ix = (x - x0) / space
                if kind in ("head", "flag", "accidental") and usual and scale < GRACE_SIZE * usual:
                    continue
                if kind == "head":
                    alter, written = notes.get(note_id, (0, False))
                    item = Item("head", ix, step, head_kind(name), alter, written, strokes=strokes.get(note_id))
                elif kind == "rest":
                    item = Item("rest", ix, step, rest_kind(name))
                elif kind == "multirest":
                    item = Item("multirest", ix)
                elif kind == "dot":
                    item = Item("dot", ix, step)
                elif kind == "flag":
                    item = Item("flag", ix, step, flag_kind(name))
                else:
                    continue
                found.setdefault((bar, slot), []).append(item)
            bar += 1
    return found, bar


def _staff_lines(g):
    ys = []
    for path in g:
        if path.tag == SVG + "path":
            m = re.match(r"M\s*([-\d.]+)\s+([-\d.]+)\s+L", path.get("d", ""))
            if m:
                ys.append(float(m.group(2)))
    if len(ys) < 2:
        return None
    return min(ys), max(ys) if len(ys) >= 5 else min(ys) + 4 * (max(ys) - min(ys))


def _measure_left(staff):
    for path in staff:
        if path.tag == SVG + "path":
            m = re.match(r"M\s*([-\d.]+)", path.get("d", ""))
            if m:
                return float(m.group(1))
    return 0.0


TRANSLATE = re.compile(r"translate\(\s*([-\d.]+)[ ,]+([-\d.]+)\s*\)(?:\s*scale\(\s*([-\d.]+))?")


def _use(g):
    for use in g.iter(SVG + "use"):
        m = TRANSLATE.search(use.get("transform", ""))
        href = use.get(XLINK, "")
        code = re.match(r"#([0-9A-F]{4,5})-", href)
        if m and code:
            return int(code.group(1), 16), float(m.group(1)), float(m.group(2)), float(m.group(3) or 1)
    return None


def smufl_code(name):
    from omr.pdf import smufl
    return smufl.code_of(name)


def _collect(g, note_id, in_grace, out):
    """(kind, code, x, y, note id, scale) for the heads, rests, dots and flags under g."""
    for child in g:
        if child.tag != SVG + "g":
            continue
        cls = child.get("class", "")
        if cls in ("note",):
            _collect(child, child.get("id"), in_grace, out)
        elif cls == "notehead":
            found = _use(child)
            if found:
                out.append(("head", found[0], found[1], found[2], note_id, found[3]))
        elif cls in ("rest", "mRest"):
            found = _use(child)
            if found:
                # a whole-bar rest is drawn as a breve rest in a long bar
                code = smufl_code("restWhole") if cls == "mRest" else found[0]
                out.append(("rest", code, found[1], found[2], None, found[3]))
            for dots in child.iter(SVG + "g"):
                if dots.get("class") == "dots":
                    for e in dots.iter(SVG + "ellipse"):
                        out.append(("dot", None, float(e.get("cx", 0)), float(e.get("cy", 0)), None, 1.0))
        elif cls in ("multiRest", "mRpt", "mRpt2", "multiRpt"):
            out.append(("multirest", None, 0.0, 0.0, None, 1.0))
        elif cls == "dots":
            for e in child.iter(SVG + "ellipse"):
                out.append(("dot", None, float(e.get("cx", 0)), float(e.get("cy", 0)), None, 1.0))
        elif cls == "flag":
            found = _use(child)
            if found:
                out.append(("flag", found[0], found[1], found[2], None, found[3]))
        elif cls in ("accid", "keySig", "keyAccid", "clef", "meterSig", "artic", "verse", "syl",
                     "dir", "dynam", "tempo", "harm", "fing", "fermata", "ornam", "trill", "mordent", "turn",
                     "label", "labelAbbr"):
            continue
        else:
            _collect(child, note_id, in_grace, out)


# ------------------------------------------------------------------ comparing

def columns(items):
    """The heads and rests of a bar (all staves: {slot: [Item]}) grouped into
    columns, left to right, with each column's dots, flags and accidentals."""
    music = [(slot, it) for slot, its in items.items() for it in its
             if it.kind == "head" or (it.kind == "rest" and it.value != "restWhole")]
    music.sort(key=lambda si: si[1].x)
    parent = list(range(len(music)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, (si, a) in enumerate(music):
        for j in range(i + 1, len(music)):
            sj, b = music[j]
            dx = b.x - a.x
            if dx > max(UNISON_GAP, SECOND_GAP, THIRD_GAP):
                break
            apart = abs(a.step - b.step)
            near = (UNISON_GAP, SECOND_GAP, THIRD_GAP)[apart] if apart <= 2 else 0.0
            if dx <= COLUMN_GAP or (si == sj and a.kind == b.kind == "head" and dx <= near):
                parent[root(j)] = root(i)
    groups = {}
    for i, (slot, it) in enumerate(music):
        groups.setdefault(root(i), []).append((slot, it))
    cols = []
    for members in groups.values():
        col = Column(min(it.x for _, it in members))
        for slot, it in members:
            col.by_staff.setdefault(slot, []).append(it)
        cols.append(col)
    cols.sort(key=lambda c: c.x)
    return cols


def without_repeat_dots(items):
    """The items less a repeat sign's dots: two dots one above the other in
    the second and third spaces (the page reader may name them as
    augmentation dots). Taken out on both sides alike, as a dotted chord in
    those spaces looks the same."""
    dots = [it for it in items if it.kind == "dot"]
    drop = {id(a) for a in dots for b in dots if a is not b and abs(a.x - b.x) < 0.3 and {a.step, b.step} == {3, 5}}
    return [it for it in items if id(it) not in drop]


def _dot_of(dot, its):
    """Whether a dot is an augmentation dot of the column: past a head, on
    its line or the space above or below, or past a rest (a staccato sits
    over or under the head, not past it)."""
    return any(dot.x >= it.x + (1.0 if it.kind == "head" else 0.8)
               and abs(dot.step - it.step) <= (1 if it.kind == "head" else 3) for it in its)


def staff_signature(cols, slot, others):
    """The staff's columns as comparable tuples: (heads, rests, dotted,
    flags), and the heads of each, for the accidental check."""
    mine = [c for c in cols if slot in c.by_staff]
    out, heads = [], []
    for n, c in enumerate(mine):
        its = c.by_staff[slot]
        hs = tuple(sorted({it.step for it in its if it.kind == "head"}))
        kinds = {}
        for it in its:
            if it.kind == "head":
                kinds.setdefault(it.step, set()).add(it.value)
        rs = sorted({it.value for it in its if it.kind == "rest"})
        left = min(it.x for it in its)
        right = max(it.x for it in its)
        nxt = mine[n + 1].x if n + 1 < len(mine) else float("inf")
        dotted = any(d.x <= min(right + DOT_REACH, nxt) and _dot_of(d, its) for d in others if d.kind == "dot")
        flags = sorted({f.value for f in others if f.kind == "flag" and left - 0.3 <= f.x <= right + 1.6})
        strokes = tuple(sorted({it.strokes for it in its if it.kind == "head" and it.strokes is not None}))
        out.append(Signature(hs, tuple(rs), dotted, tuple(flags), kinds, strokes))
        heads.append([it for it in its if it.kind == "head"])
    return out, heads


def compare_staff(page_items, drawn_items, page_cols, drawn_cols):
    """None if the staff bar matches, else the first difference in words.
    The items are (slot, [Item]); the columns those of the whole bar."""
    slot_page = page_items[0]
    slot_drawn = drawn_items[0]
    page_sig, page_heads = staff_signature(page_cols, slot_page, page_items[1])
    drawn_sig, drawn_heads = staff_signature(drawn_cols, slot_drawn, drawn_items[1])
    page_whole = sum(1 for it in page_items[1] if it.kind == "rest" and it.value == "restWhole")
    drawn_whole = sum(1 for it in drawn_items[1] if it.kind == "rest" and it.value == "restWhole")
    if page_whole != drawn_whole:
        return (f"drawn again from the music read, this staff bar has {_wholes(drawn_whole)} "
                f"where the page has {_wholes(page_whole)}")
    if len(page_sig) != len(drawn_sig):
        return (f"drawn again from the music read, this staff bar has {_count(len(drawn_sig))} "
                f"where the page has {_count(len(page_sig))}")
    for n, (p, d) in enumerate(zip(page_sig, drawn_sig)):
        # the converter writes no beams, so the drawing flags notes the page beams:
        # only a flag on the page is compared
        if (not set(p.flags) <= set(d.flags) or not p.same_heads(d) or (p.rests, p.dotted) != (d.rests, d.dotted)
                or (p.strokes and d.strokes and p.strokes != d.strokes)):
            return f"drawn again from the music read, the {_ordinal(n + 1)} note or rest differs from the page: {_differ(p, d)}"
    accidentals = [it for it in page_items[1] if it.kind == "accidental"]
    for n, (ph, dh) in enumerate(zip(page_heads, drawn_heads)):
        for d in dh:
            near = [a for a in accidentals if a.step == d.step and 0 < min(h.x for h in ph if h.step == d.step) - a.x
                    <= ACCIDENTAL_REACH] if any(h.step == d.step for h in ph) else []
            if near:
                given = max(near, key=lambda a: a.x).alter
                if given != d.alter:
                    return (f"drawn again from the music read, the {_ordinal(n + 1)} note has "
                            f"{_alter_words(d.alter)} where the page prints a {_alter_name(given)}")
            elif d.printed:
                return (f"drawn again from the music read, the {_ordinal(n + 1)} note needs a "
                        f"{_alter_name(d.alter)} that the page does not print")
    return None


def check(score, ordered):
    """The self-check's flags for a score read with notes, with the systems
    in score order (structure.assign_parts)."""
    drawn = render(score)
    if drawn is None:
        return []
    found, count = drawn_bars(*drawn)
    if count != len(score.bars):
        return []
    page, skip = page_bars(score, ordered)
    slots = _slots(score)
    slot_of = {v: k for k, v in slots.items()}
    # staves under a clef with no pitch (percussion, tablature) are not compared
    unpitched = {slots.get((m.part, m.staff)) for m in score.structure
                 if m.kind == "clef" and events.clef_bottom(m.value) is None}
    # a clef replaced at the same point by another (an incipit's old clef): the drawing
    # may use the other one, so the staff is not compared up to its next clef
    clefs_at = {}
    for m in score.structure:
        if m.kind == "clef":
            clefs_at.setdefault((slots.get((m.part, m.staff)), m.bar, m.onset), set()).add(m.value)
    double_clef = set()
    for (slot, bar, onset), values in clefs_at.items():
        if len(values) > 1:
            later = [b for (s2, b, o2) in clefs_at if s2 == slot and (b, o2) > (bar, onset)]
            double_clef.update((slot, k) for k in range(bar, min(later, default=len(score.bars)) + 1))
    page_by_bar, drawn_by_bar = {}, {}
    for (k, slot), its in page.items():
        page_by_bar.setdefault(k, {})[slot] = without_repeat_dots(its)
    for (k, slot), its in found.items():
        drawn_by_bar.setdefault(k, {})[slot] = without_repeat_dots(its)
    flags = []
    for bar in sorted(page_by_bar):
        if bar in skip:
            continue
        page_all = page_by_bar[bar]
        drawn_all = {slot: its for slot, its in drawn_by_bar.get(bar, {}).items() if slot in page_all}
        if any(it.kind == "multirest" for its in list(page_all.values()) + list(drawn_all.values()) for it in its):
            continue
        page_all = _placed(page_all, drawn_all)
        for slot, reason in sorted(_compare_bar(page_all, drawn_all).items()):
            # slash heads (rhythm slashes) are written as notes, so they are not compared
            slashes = any(it.kind == "head" and "Slash" in it.value for it in page_all.get(slot, []))
            if reason and slot not in unpitched and (slot, bar) not in double_clef and not slashes:
                part, number = slot_of[slot]
                flags.append(events.Flag(part, number, bar, RULE, reason))
    return flags


def _compare_bar(page_all, drawn_all):
    """{slot: None or the first difference} for one bar."""
    page_music = {s: [i for i in its if i.kind in ("head", "rest")] for s, its in page_all.items()}
    drawn_music = {s: [i for i in its if i.kind in ("head", "rest")] for s, its in drawn_all.items()}
    page_cols, drawn_cols = columns(page_music), columns(drawn_music)
    return {slot: compare_staff((slot, page_all[slot]), (slot, drawn_all.get(slot, [])), page_cols, drawn_cols)
            for slot in page_all}


def _placed(page_all, drawn_all):
    """The bar with each head between two staves put on the staff where the
    drawing has a head at that place: on the other staff when the drawing
    has one there and none where the page reader put it. Its accidental
    and its dot go with it."""
    if not any(it.other for its in page_all.values() for it in its):
        return page_all
    drawn_steps = {slot: {it.step for it in its if it.kind == "head"} for slot, its in drawn_all.items()}
    out = {slot: [] for slot in page_all}
    moved = []
    for slot, its in page_all.items():
        for it in its:
            if (it.kind == "head" and it.other and it.other[0] in out
                    and it.other[1] in drawn_steps.get(it.other[0], ()) and it.step not in drawn_steps.get(slot, ())):
                out[it.other[0]].append(Item("head", it.x, it.other[1], it.value))
                moved.append((slot, it))
            else:
                out[slot].append(it)
    for slot, head in moved:
        for a in list(out[slot]):
            if not a.other or a.other[0] not in out:
                continue
            if ((a.kind == "accidental" and a.step == head.step and 0 < head.x - a.x <= ACCIDENTAL_REACH)
                    or (a.kind == "dot" and abs(a.step - head.step) <= 1 and 0 < a.x - head.x <= DOT_REACH)):
                out[slot].remove(a)
                out[a.other[0]].append(Item(a.kind, a.x, a.other[1], a.value, a.alter))
    return out


# ------------------------------------------------------------------ words

def _wholes(n):
    return "no whole rest" if n == 0 else "a whole rest" if n == 1 else f"{n} whole rests"


def _count(n):
    return "1 note or rest" if n == 1 else f"{n} notes or rests"


ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"]


def _ordinal(n):
    return ORDINALS[n - 1] if n <= len(ORDINALS) else f"{n}th"


def _differ(p, d):
    ph, pr, pdot, pf = p.steps, p.rests, p.dotted, p.flags
    dh, dr, ddot, df = d.steps, d.rests, d.dotted, d.flags
    if pr != dr or bool(ph) != bool(dh):
        return f"the page has {_what(ph, pr)}, the drawing {_what(dh, dr)}"
    if ph != dh:
        return f"heads on the page at {_steps(ph)}, in the drawing at {_steps(dh)}"
    if not p.same_heads(d):
        return f"the page has {_kinds(p)} heads, the drawing {_kinds(d)}"
    if pdot != ddot:
        return "the page has a dot, the drawing none" if pdot else "the drawing has a dot, the page none"
    if p.strokes and d.strokes and p.strokes != d.strokes:
        return f"the page has {_strokes_words(p.strokes)}, the drawing {_strokes_words(d.strokes)}"
    return f"the page has {_flags(pf)}, the drawing {_flags(df)}"


REST_WORDS = {"restWhole": "whole", "restHalf": "half", "restQuarter": "quarter", "rest8th": "eighth",
              "rest16th": "sixteenth", "rest32nd": "32nd", "rest64th": "64th", "restDoubleWhole": "double whole"}


def _what(heads, rests):
    if rests:
        return "a " + " and ".join(REST_WORDS.get(r, r) for r in rests) + " rest"
    return f"{len(heads)} head{'' if len(heads) == 1 else 's'}"


def _steps(steps):
    return ", ".join(step_words(s) for s in steps)


def _kinds(sig):
    return ", ".join(k for s in sig.steps for k in sorted(sig.kinds.get(s, ())))


def _strokes_words(strokes):
    def one(n):
        return "no beam or flag" if n == 0 else "1 beam or flag" if n == 1 else f"{n} beams or flags"
    return " and ".join(one(n) for n in strokes)


def _flags(flags):
    return ", ".join(f.replace("flag", "") + " flag" for f in flags) if flags else "no flag"


def step_words(step):
    """A staff position in words: line 1 is the bottom line."""
    if 0 <= step <= 8:
        return f"line {step // 2 + 1}" if step % 2 == 0 else f"space {step // 2 + 1}"
    if step > 8:
        return f"{(step - 8) / 2:g} lines above the staff"
    return f"{-step / 2:g} lines below the staff"


def _alter_name(alter):
    return {1: "sharp", -1: "flat", 0: "natural", 2: "double sharp", -2: "double flat"}.get(alter, "accidental")


def _alter_words(alter):
    return "no alteration" if alter == 0 else f"a {_alter_name(alter)}"
