"""Text on a vector PDF page sorted into kinds (Stage 1.4): title,
subtitle, composer, lyricist, rights, headers and page numbers, instrument
names, bar numbers, lyrics, chord symbols, rehearsal marks, tempo marks,
metronome marks, dynamics, fingering, and words (expression and other staff
text). Every item inside a system is tied to the staff it belongs to.

The rules are in docs/notes/markings-spec.md, "Text". The text runs come
from Stage 1.1 (omr.pdf.symbols); notes and markings are attached to the
music by omr.pdf.markings.
"""

import re
import statistics
from dataclasses import dataclass

from omr.pdf import notation, structure

# Text more than this many staff spaces above the first system of page 1
# is a credit (title, composer); text more than BELOW_SYSTEM below the last
# system of a page is page text.
ABOVE_SYSTEM = 6.2
BELOW_SYSTEM = 9.0

ACCIDENTAL = r"(?:b|#|♭|♯)"
CHORD_SUFFIX = (r"(?:maj|Maj|ma|MA|M|min|mi|m|-|dim|°|o|aug|\+|ø|sus|add|alt|omit|no|"
                r"[0-9]|b|#|♭|♯|\(|\)|,|/(?=[0-9#b♭♯])|Δ|\^|\s)*")
CHORD = re.compile(rf"^\(?[A-G]{ACCIDENTAL}?({CHORD_SUFFIX})(?:/([A-G]){ACCIDENTAL}?)?\)?$")
NO_CHORD = re.compile(r"^N\.?\s*C\.?$")
DYNAMIC_TEXT = re.compile(r"^(?:p{1,5}|f{1,5}|m[pf]|s?fz|sf+|sfp{1,2}|sffz|fp|rfz?|fz|n)$")
TEMPO_WORDS = re.compile(
    r"\b(?:grave|largo|larghetto|lento|adagi\w*|andant\w*|moderato|allegr\w*|vivace|vivo|presto|"
    r"prestissimo|tempo|maestoso|langsam|mäßig|massig|mässig|schnell|lebhaft|rasch|ruhig|bewegt|"
    r"slow|fast|moderately|briskly|lively|swing|ballad|march|valse|waltz|polka|menuetto?|minuet)\b", re.I)
DIGITS = re.compile(r"^\(?\d{1,3}\)?[.:]?(?::\d{1,2})?$")
PAGE_NUMBER = re.compile(r"^[-–]?\s*\d{1,4}\s*[-–]?$")
# the share of the page height at its top and bottom where headers and footers are
MARGIN_ZONE = 0.1
FINGERING = re.compile(r"^[0-5]$")
PLUCK = re.compile(r"^[pimac]$")
HYPHENS = ("-", "–", "—", "‐")
VERSE_NUMBER = re.compile(r"^\d{1,2}[.)]$")
METRONOME = re.compile(r"^\s*\(?\s*=\s*(?:c\.|ca\.|circa)?\s*(\d{2,3})(?:\s*[-–]\s*\d{2,3})?\s*\)?\s*$")


@dataclass
class TextItem:
    """One piece of text and what it is. `staff` is the layout Staff it
    belongs to (None for page text); `system` its System."""

    kind: str
    text: str
    box: tuple
    page: int
    font: str = ""
    size: float = 0.0
    staff: object = None
    system: object = None
    verse: int = 0             # lyrics: the line of verse, from 1
    syllabic: str = "single"   # lyrics: single, begin, middle or end
    extend: bool = False       # lyrics: an extender line follows (a melisma)
    hyphen_after: bool = False # lyrics: a hyphen follows
    value: str = ""            # chord symbols: the chord in the harness's words
    baseline: float = 0.0      # y of the text's baseline
    group: int = 0             # pieces of one run split at span breaks (omr.pdf.text._pieces)
    piece: int = 0


def is_italic(font):
    return bool(re.search(r"italic|oblique|ita\b|bdita|-it\b|it$", font, re.I))


def is_bold(font):
    return bool(re.search(r"bold|bd|black|heavy|semibold|demi", font, re.I))


def middle(box):
    return (box[1] + box[3]) / 2


# ------------------------------------------------------------- placement

def system_of(pl, box):
    """The system of a page nearest a box, by the distance from the box's
    middle to the system's staves."""
    y = middle(box)

    def distance(system):
        top, bottom = system.staves[0].top, system.staves[-1].bottom
        return 0 if top <= y <= bottom else min(abs(y - top), abs(y - bottom))
    return min(pl.systems, key=distance)


def staff_for(system, box, prefer="nearest", same_part=None):
    """The staff of a system a box belongs to, and where it is: "above",
    "below" or "on". Text in the gap between two staves goes to the nearer
    staff; with `prefer="upper"` (dynamics, hairpins, lyrics) to the staff
    above, as engravers put them below the staff they belong to. If
    `same_part(upper, lower)` is given, "upper" applies only between two
    staves of one part (a piano's): a singer's dynamics stand above the
    staff, clear of the lyrics below it."""
    y = middle(box)
    staves = system.staves
    for k, staff in enumerate(staves):
        if staff.top - 0.5 * staff.space <= y <= staff.bottom + 0.5 * staff.space:
            return staff, "on"
    if y < staves[0].top:
        return staves[0], "above"
    if y > staves[-1].bottom:
        return staves[-1], "below"
    for k in range(len(staves) - 1):
        upper, lower = staves[k], staves[k + 1]
        if upper.bottom < y < lower.top:
            if prefer == "upper" and (same_part is None or same_part(upper, lower)):
                return upper, "below"
            if prefer == "lower":
                return lower, "above"
            if y - upper.bottom <= lower.top - y:
                return upper, "below"
            return lower, "above"
    return staves[0], "on"


# ------------------------------------------------------------- the page

@dataclass
class _Run:
    """A text run, with music-font glyphs that belong to it (a flat in a
    chord symbol) folded in."""

    text: str
    box: tuple
    font: str
    size: float
    y: float
    group: int = 0      # pieces of one Stage 1.1 run split at span breaks share a group
    piece: int = 0


# a new span any gap (in ems) after the text before it starts a new piece:
# lyric syllables are separate spans, set close together
SPAN_GAP = 0.02


def _pieces(r, group):
    """A Stage 1.1 text run split where a new span starts after a gap."""
    cuts = [(i, x, gap) for i, x, gap in getattr(r, "breaks", ()) if gap > SPAN_GAP * r.size]
    if not cuts:
        return [_Run(r.text.strip(), r.box, r.font, r.size, r.y, group)]
    out = []
    start, x0 = 0, r.box[0]
    for n, (i, x, gap) in enumerate(cuts + [(len(r.text), r.box[2] + 0, 0)]):
        right = x - gap if i < len(r.text) else r.box[2]
        piece = r.text[start:i].strip()
        if piece:
            out.append(_Run(piece, (x0, r.box[1], right, r.box[3]), r.font, r.size, r.y, group, len(out)))
        start, x0 = i, x
    return out


CHORD_GLYPHS = {"csymAccidentalFlat": "b", "csymAccidentalSharp": "#", "accidentalFlat": "b",
                "accidentalSharp": "#", "csymDiminished": "°", "csymHalfDiminished": "ø",
                "csymAugmented": "+", "csymMajorSeventh": "Δ", "csymMinor": "m"}


def _runs(pl):
    """The page's text runs, split where the PDF starts a new span after a
    gap (omr.pdf.text._pieces), with a chord letter and what touches it on
    its line joined (a raised suffix, a flat drawn in a music font)."""
    runs = [piece for g, r in enumerate(pl.text, 1) if r.text.strip() for piece in _pieces(r, g)]
    # glyphs of a music font used in chord symbols, next to a run
    space = statistics.median(s.space for s in pl.staves) if pl.staves else 5.0
    for s in pl.symbols:
        if s.name in CHORD_GLYPHS and (s.name.startswith("csym") or pl.staff_of(s) is None
                                       or not -6 <= pl.step_of(s) <= 14):
            runs.append(_Run(CHORD_GLYPHS[s.name], s.box, "chord glyph", s.size / 4 * 2.5, s.box[3]))
    out = []
    for r in sorted(runs, key=lambda r: r.box[0]):
        joined = False
        for o in out:
            gap = r.box[0] - o.box[2]
            same_line = o.box[1] - 0.4 * o.size <= middle(r.box) <= o.box[3] + 0.2 * o.size
            if not same_line or not -0.1 * o.size <= gap <= 0.12 * o.size:
                continue
            # a chord symbol set in pieces: "D" and a raised "7", a flat glyph,
            # or pieces that together read as a chord
            chordish = re.match(r"^\(?[A-G]", o.text) and (r.font == "chord glyph" or o.font == "chord glyph"
                                                           or r.size < o.size - 0.5 or r.y < o.y - 0.5
                                                           or chord_value(o.text + r.text))
            if chordish:
                o.text += r.text
                o.box = (min(o.box[0], r.box[0]), min(o.box[1], r.box[1]), max(o.box[2], r.box[2]),
                         max(o.box[3], r.box[3]))
                if o.font == "chord glyph":
                    o.font, o.size, o.y = r.font, r.size, r.y
                joined = True
                break
        if not joined:
            out.append(r)
    return [r for r in out if r.font != "chord glyph" or len(r.text) > 1]


def classify_page(pl, page_rect, first_page, frames=(), hyphen_lines=()):
    """The TextItems of one page layout. `page_rect` is (x0, y0, x1, y1) of
    the page as shown; `frames` are rectangles drawn round text (rehearsal
    marks); `hyphen_lines` are short level lines (lyric hyphens and
    extenders) as (y, x0, x1)."""
    items = []
    runs = _runs(pl)
    if not pl.systems:
        for r in runs:
            items.append(TextItem("page text", r.text, r.box, pl.page, r.font, r.size))
        return items
    space = statistics.median(s.space for s in pl.staves)
    left_margin = min(s.x0 for s in pl.systems)
    right_margin = max(s.x1 for s in pl.systems)
    first_top = pl.systems[0].staves[0].top
    last_bottom = pl.systems[-1].staves[-1].bottom
    height = page_rect[3] - page_rect[1]
    in_system = []
    page_runs = []
    for r in runs:
        y = middle(r.box)
        plain = not is_bold(r.font) and not is_italic(r.font)
        if y < first_top:
            # above the music: on page 1 the credits, elsewhere a header;
            # a composer's name can be set at the right margin close over
            # the first system
            at_right = abs(r.box[2] - right_margin) < 0.6 * space and plain and not TEMPO_WORDS.search(r.text)
            far = r.box[3] < first_top - ABOVE_SYSTEM * space
            page = (far and (first_page or r.box[3] < page_rect[1] + MARGIN_ZONE * height)) \
                or (first_page and at_right and r.box[3] < first_top - 4 * space)
        elif y > last_bottom:
            # below the music: a footer in the bottom margin, or far below
            page = r.box[1] > page_rect[3] - MARGIN_ZONE * height and r.box[1] > last_bottom + 3 * space \
                or r.box[1] > last_bottom + BELOW_SYSTEM * space
        else:
            page = False
        if page:
            page_runs.append(r)
        else:
            in_system.append((r, system_of(pl, r.box)))
    items += _page_text(pl, page_runs, page_rect, first_page, first_top, last_bottom, left_margin, right_margin, space)
    items += _system_text(pl, in_system, frames, hyphen_lines)
    return items


def _page_text(pl, runs, page_rect, first_page, first_top, last_bottom, left_margin, right_margin, space):
    """Credits above the first system of page 1; headers above the music of
    other pages; footers (rights, page numbers) below it."""
    items = []
    centre = (left_margin + right_margin) / 2
    above = [r for r in runs if middle(r.box) < first_top]
    below = [r for r in runs if middle(r.box) >= first_top]
    for r in below:
        if PAGE_NUMBER.match(r.text):
            kind = "page number"
        elif r.box[1] > last_bottom:
            kind = "rights" if first_page or re.search(r"©|copyright|\(c\)|licen|cc0|cc-by|public domain|rights",
                                                       r.text, re.I) else "footer"
        else:
            kind = "page text"
        items.append(TextItem(kind, r.text, r.box, pl.page, r.font, r.size))
    if not first_page:
        for r in above:
            items.append(TextItem("page number" if PAGE_NUMBER.match(r.text) else "header", r.text, r.box, pl.page,
                                  r.font, r.size))
        return items
    # page 1: text centred on the page is the title (the top line of the
    # largest text, and the lines of that size just under it) or a
    # subtitle; text at the right margin is the composer (or arranger), at
    # the left margin the lyricist.
    page_centre = (page_rect[0] + page_rect[2]) / 2
    centred = [r for r in above if min(abs((r.box[0] + r.box[2]) / 2 - c) for c in (centre, page_centre)) < 2 * space
               or (r.box[0] < centre < r.box[2] and r.box[2] - r.box[0] > (right_margin - left_margin) / 2)]
    largest = max((r.size for r in centred), default=0)
    title_size = next((r.size for r in sorted(centred, key=lambda r: r.box[1]) if r.size >= 0.65 * largest), 0)
    groups = []
    title_done = False
    for r in sorted(above, key=lambda r: r.box[1]):
        if r in centred:
            kind = "title" if not title_done and abs(r.size - title_size) < 0.1 else "subtitle"
            if kind == "subtitle" and any(g.kind == "title" for g in groups):
                title_done = True
        elif abs(r.box[2] - right_margin) < 1.5 * space or (r.box[0] > centre and r.box[2] > right_margin - 6 * space):
            kind = "composer"
        elif r.box[0] < left_margin + 3 * space and r.box[2] < centre:
            kind = "lyricist"
        else:
            kind = "page text"
        if PAGE_NUMBER.match(r.text) and kind not in ("title", "subtitle"):
            kind = "page number"
        # lines of one credit set one under another join into one
        if groups and groups[-1].kind == kind and kind != "page text" \
                and r.box[1] - groups[-1].box[3] < 0.8 * r.size and abs(groups[-1].size - r.size) < 0.6:
            g = groups[-1]
            g.text += " " + r.text
            g.box = (min(g.box[0], r.box[0]), g.box[1], max(g.box[2], r.box[2]), r.box[3])
            continue
        groups.append(TextItem(kind, r.text, r.box, pl.page, r.font, r.size))
    return items + groups


def _system_text(pl, runs, frames, hyphen_lines):
    """Text inside the region of a system."""
    items = []
    rest = []
    heads_by_staff = {}
    for s in pl.symbols:
        if notation.is_head(s.name) and pl.staff_of(s) is not None:
            heads_by_staff.setdefault(id(pl.staff_of(s)), []).append(s)
    metronome_notes = [s for s in pl.symbols if s.name.startswith("metNote") or
                       (notation.is_head(s.name) and pl.staff_of(s) is not None
                        and not -3 <= pl.step_of(s) <= 11)]
    for r, system in runs:
        space = system.staves[0].space
        text = r.text
        staff, where = staff_for(system, r.box)
        item = TextItem("words", text, r.box, pl.page, r.font, r.size, staff, system,
                        baseline=r.y, group=r.group, piece=r.piece)
        # left of the system: an instrument name (or a bar number)
        if r.box[2] <= system.x0 + 0.5 * space and where != "above":
            item.kind = "instrument name"
        elif r.box[2] <= system.x0 + 0.5 * space and not DIGITS.match(text):
            item.kind = "instrument name"
        elif METRONOME.match(text) and any(abs(m.box[2] - r.box[0]) < 2.5 * space and
                                           m.box[1] - space <= middle(r.box) <= m.box[3] + space
                                           for m in metronome_notes):
            item.kind = "metronome"
            item.text = METRONOME.match(text).group(1)
        elif text in ("(", ")", "[", "]") or re.fullmatch(r"[(\[]?\s*=\s*[)\]]?", text):
            item.kind = "punctuation"
        elif NO_CHORD.match(text) and where == "above":
            item.kind = "no chord"
        elif DIGITS.match(text) and re.fullmatch(r"\d{1,4}", text) and r.box[0] <= system.x0 + 2 * space \
                and where == "above":
            item.kind = "bar number"
        elif structure.ENDING_TEXT.match(text) and where == "above" and staff is system.staves[0] \
                and not FINGERING.match(text):
            item.kind = "ending"
        elif notation.TUPLET_TEXT.match(text) and is_italic(r.font):
            item.kind = "tuplet"
        elif notation.OCTAVE_TEXT.match(text) and not FINGERING.match(text):
            item.kind = "octave"
        elif _framed(r.box, frames, space) and len(text) <= 4 and where == "above":
            item.kind = "rehearsal"
        elif DIGITS.match(text):
            item.kind = _digits_kind(r, system, staff, where, heads_by_staff, space)
        elif DYNAMIC_TEXT.match(text) and (is_italic(r.font) or is_bold(r.font)):
            item.kind = "dynamic"
            staff, where = staff_for(system, r.box, prefer="upper")
            item.staff = staff
        elif PLUCK.match(text) and _by_head(r.box, heads_by_staff.get(id(staff), []), space) \
                and is_italic(r.font) and not is_bold(r.font):
            item.kind = "pluck"
        rest.append(item) if item.kind == "words" else items.append(item)
    # chord symbols are rows above a staff whose text reads as chords
    chords, rest = _chord_symbols(rest)
    items += chords
    # lyrics are rows of syllables under a staff, set under its noteheads
    lyrics, rest = _lyrics(rest, heads_by_staff, hyphen_lines)
    items += lyrics
    rest = _rejoin(rest)
    # tempo marks: over the top staff, naming a tempo or set in bold upright
    for item in rest:
        if item.staff is item.system.staves[0] and _staff_side(item) == "above" and (
                TEMPO_WORDS.search(item.text) or is_bold(item.font) and not is_italic(item.font)):
            item.kind = "tempo"
        items.append(item)
    return items


def _rejoin(items):
    """Join again the pieces of one run (split at span breaks for lyrics)
    that are not lyrics: words set as several spans."""
    out = []
    last = {}
    for item in sorted(items, key=lambda i: i.box[0]):
        group = getattr(item, "group", 0)
        before = last.get(group) if group else None
        if before is not None and before.piece + 1 == item.piece and before.kind == item.kind == "words":
            gap = item.box[0] - before.box[2]
            before.text += (" " if gap > 0.2 * item.size else "") + item.text
            before.box = (before.box[0], min(before.box[1], item.box[1]), item.box[2], max(before.box[3], item.box[3]))
            before.piece = item.piece
            continue
        out.append(item)
        if group:
            last[group] = item
    return out


def _staff_side(item):
    if middle(item.box) < item.staff.top:
        return "above"
    if middle(item.box) > item.staff.bottom:
        return "below"
    return "on"


def _framed(box, frames, space):
    return any(f[0] - 0.2 * space <= box[0] and box[2] <= f[2] + 0.2 * space and f[1] - 0.2 * space <= box[1]
               and box[3] <= f[3] + 0.2 * space and (f[2] - f[0]) < (box[2] - box[0]) + 4 * space
               and (f[3] - f[1]) < (box[3] - box[1]) + 3 * space for f in frames)


def _near_head(box, heads, distance):
    cx, cy = (box[0] + box[2]) / 2, middle(box)
    return any(abs((h.box[0] + h.box[2]) / 2 - cx) <= distance and abs(h.y - cy) <= distance for h in heads)


def _by_head(box, heads, space):
    """Fingering stands over or under a notehead (stacked over a chord, up
    to eight staff spaces away), or just left of it at its height."""
    cx, cy = (box[0] + box[2]) / 2, middle(box)
    for h in heads:
        hx = (h.box[0] + h.box[2]) / 2
        if abs(hx - cx) <= 1.2 * space and abs(h.y - cy) <= 8 * space:
            return True
        if 0 <= h.box[0] - box[2] <= 2.5 * space and abs(h.y - cy) <= 1.2 * space:
            return True
    return False


def _digits_kind(r, system, staff, where, heads_by_staff, space):
    """Digits: fingering (single upright digits by a notehead), a bar
    number (at the start of a system, or italic over a barline), or other."""
    text = r.text
    if FINGERING.match(text) and not is_italic(r.font) and _by_head(r.box, heads_by_staff.get(id(staff), []), space):
        return "fingering"
    if re.fullmatch(r"\d{1,4}", text) and staff is system.staves[0] and where == "above" \
            and r.box[0] <= system.x0 + 2 * space:
        return "bar number"
    if re.fullmatch(r"\(?\d{1,4}\)?", text) and (is_italic(r.font) or where == "above") and any(
            abs((r.box[0] + r.box[2]) / 2 - g.x) < 2 * space for g in system.barlines):
        return "bar number"
    if FINGERING.match(text) and _near_head(r.box, heads_by_staff.get(id(staff), []), 3.5 * space):
        return "fingering"
    return "digits"


# ------------------------------------------------------------- lyrics

def _lyrics(items, heads_by_staff, hyphen_lines):
    """Rows of upright text under a staff whose runs stand under its
    noteheads are lyrics. Returns (lyric items, the rest)."""
    # rows: text of one style under one staff, on one baseline (within a
    # third of a staff space)
    styles = {}
    for item in items:
        if is_bold(item.font):
            continue
        # lyrics are set below the staff they belong to (or above the top staff)
        staff, where = staff_for(item.system, item.box, prefer="upper")
        if where not in ("below", "above"):
            continue
        style = (item.font, round(item.size * 2))
        styles.setdefault((id(item.system), id(staff), style), []).append((item, staff))
    rows = []
    for (_, _, style), members in styles.items():
        members.sort(key=lambda m: m[0].baseline)
        row = [members[0]]
        for m in members[1:]:
            if m[0].baseline - row[-1][0].baseline > m[1].space / 3:
                rows.append((style, row))
                row = []
            row.append(m)
        rows.append((style, row))
    lyric_ids = set()
    found = []
    by_staff = {}

    def aligned_share(members):
        staff = members[0][1]
        heads = heads_by_staff.get(id(staff), [])
        words = [i for i, _ in members if i.text not in HYPHENS]
        aligned = [i for i in words if _under_head(i, heads, staff.space)]
        return len(words), len(aligned)

    # a row of three or more syllables, most under noteheads, sets a lyric
    # style for the page; shorter rows in that style are lyrics too if
    # their syllables stand under noteheads
    lyric_styles = set()
    for style, members in rows:
        words, aligned = aligned_share(members)
        if words >= 3 and aligned >= 0.6 * words:
            lyric_styles.add(style)
    for style, members in rows:
        words, aligned = aligned_share(members)
        if not words:
            continue
        plain = not is_italic(style[0])
        if words >= 3 and aligned >= 0.6 * words or style in lyric_styles and aligned == words \
                or not lyric_styles and plain and aligned == words and _staff_side(members[0][0]) == "below":
            by_staff.setdefault((id(members[0][0].system), id(members[0][1])), []).append(members)
    for (system_id, staff_id), row_list in by_staff.items():
        row_list.sort(key=lambda m: statistics.median(i.baseline for i, _ in m))
        for verse, members in enumerate(row_list, 1):
            ordered = sorted(members, key=lambda m: m[0].box[0])
            staff = ordered[0][1]
            space = staff.space
            syllables = []
            number = ""
            for item, st in ordered:
                if item.text in HYPHENS:
                    if syllables:
                        syllables[-1].hyphen_after = True
                    lyric_ids.add(id(item))
                    continue
                text = " ".join(item.text.split())
                if not syllables and VERSE_NUMBER.match(text):
                    # a verse number set apart: MuseScore keeps it in the first syllable's text
                    number = text
                    lyric_ids.add(id(item))
                    continue
                if not syllables and number:
                    text = f"{number} {text}"
                lyric = TextItem("lyric", text, item.box, item.page, item.font, item.size, staff, item.system,
                                 verse=verse, baseline=item.baseline)
                syllables.append(lyric)
                lyric_ids.add(id(item))
            baseline = statistics.median(s.baseline for s in syllables) if syllables else 0
            for a, b in zip(syllables, syllables[1:] + [None]):
                gap_end = b.box[0] if b is not None else a.system.x1 + space
                for y, x0, x1 in hyphen_lines:
                    if not (a.box[2] - 0.2 * space <= x0 and x1 <= gap_end + 0.2 * space):
                        continue
                    if a.box[1] - 0.2 * space <= y <= a.baseline - 0.15 * a.size:
                        a.hyphen_after = True     # a hyphen drawn as a line, at mid-letter height
                    elif abs(y - baseline) <= 0.35 * space and x1 - x0 >= 0.8 * space:
                        a.extend = True           # an extender line at the baseline
            previous_hyphen = False
            for s in syllables:
                if s.text.endswith(HYPHENS):
                    s.text = s.text.rstrip("".join(HYPHENS))
                    s.hyphen_after = True
                s.syllabic = {(False, False): "single", (False, True): "begin", (True, True): "middle",
                              (True, False): "end"}[(previous_hyphen, s.hyphen_after)]
                previous_hyphen = s.hyphen_after
            found += [s for s in syllables if s.text]
    return found, [i for i in items if id(i) not in lyric_ids]


def _under_head(item, heads, space, tight=False):
    """A syllable stands under a notehead: its middle within two staff
    spaces of the notehead's middle (MuseScore centres a syllable on its
    note), or its left edge at the notehead's (a syllable that starts a
    melisma is set from the note's left)."""
    cx = (item.box[0] + item.box[2]) / 2
    reach = (1.2 if tight else 2.0) * space
    for h in heads:
        hx = (h.box[0] + h.box[2]) / 2
        if abs(hx - cx) <= reach or abs(h.box[0] - item.box[0]) <= 0.6 * space:
            return True
    return False


# ------------------------------------------------------- chord symbols

def chord_value(text):
    """The chord symbol in the harness's words (omr.evaluate.events reads a
    <harmony> as root, alteration, then the kind's printed text, or "major"
    when nothing is printed after the root, then " / " and the bass), or
    None if the text is not a chord symbol."""
    text = text.replace("♭", "b").replace("♯", "#").strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    match = CHORD.match(text)
    if not match:
        return None
    root = text[0]
    rest = text[1:]
    if rest[:1] in ("b", "#") and not rest[:2] in ("b5", "b9") or rest[:2] in ("b ", "# "):
        root += rest[0]
        rest = rest[1:]
    bass = None
    slash = re.search(r"/([A-G])[b#]?$", rest)
    if slash:
        bass = slash.group(1)
        rest = rest[:slash.start()]
    suffix = rest.strip()
    value = f"{root} {suffix or 'major'}"
    if bass:
        value += f" / {bass}"
    return value


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
    suffix not in CHORD_KINDS (Stage 1.6 then writes it as printed)."""
    main, _, bass = value.partition(" / ")
    root, _, suffix = main.partition(" ")
    return root, CHORD_KINDS.get(suffix.strip(), suffix.strip() if "-" in suffix and suffix.islower() else None),         (bass or None)


def _chord_symbols(items):
    """Rows of text above a staff that read as chord symbols: most of the
    row reads as chords. A lone letter (A to G) counts only in a row of
    two or more, or in the style (font and size) of another chord row on
    the page."""
    rows = {}
    over = {}      # the staff each item stands over: chord symbols sit over their own staff
    for item in items:
        staff, where = staff_for(item.system, item.box, prefer="lower")
        if is_italic(item.font) or is_bold(item.font) or where != "above":
            continue
        over[id(item)] = staff
        key = (id(item.system), id(staff), round(item.baseline / (0.5 * staff.space)), item.font,
               round(item.size * 2))
        rows.setdefault(key, []).append(item)
    chosen = set()
    found = []
    styles = set()
    for key, members in rows.items():
        values = [chord_value(i.text) for i in members]
        if len(members) >= 2 and sum(v is not None for v in values) >= 0.6 * len(members):
            styles.add(key[3:])
    for key, members in rows.items():
        values = [chord_value(i.text) for i in members]
        share = sum(v is not None for v in values) / len(values)
        for item, value in zip(members, values):
            if value is None:
                continue
            single_letter = re.fullmatch(r"[A-G][b#]?", item.text.replace("♭", "b").replace("♯", "#"))
            if share >= 0.6 and (len(members) >= 2 or not single_letter or key[3:] in styles):
                item.kind = "chord symbol"
                item.value = value
                item.staff = over[id(item)]
                chosen.add(id(item))
                found.append(item)
    return found, [i for i in items if id(i) not in chosen]
