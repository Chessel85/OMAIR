"""Page images read by the sequence reader, Engine 2 (Phase 2, Stage 2.6).

Engine 1 (omr.raster.reading and the vector reader) finds the staves,
systems, parts and bars. Engine 2 reads the notes and rests again from the
image: each part in each system is cut out as the training units were cut
(omr.corpus.sequence_units), read by homr's staff transformer
(omr.raster.sequence.OnnxReader), and its tokens are turned into MusicXML by
homr's own writer and read back into events, bar by bar, in the bars Engine 1
found for that system.

With OMR_ENGINE=sequence, read_pdf puts Engine 2's notes and rests in place
of Engine 1's on image pages, so the harness scores Engine 2 alone; the
structure, markings and text stay Engine 1's. Parts of more than two staves
are not read by it (homr's tokens have two staff positions), and their
notes stay Engine 1's.
"""

import functools
import os
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path

import numpy as np

from omr import paths
from omr.corpus.sequence_units import MARGIN_ABOVE, MARGIN_SIDES, _fit
from omr.evaluate import events
from omr.raster import sequence

ENGINE_ENV = "OMR_ENGINE"
MODEL_ENV = "OMR_SEQUENCE_MODEL"
THREADS_ENV = "OMR_SEQUENCE_THREADS"   # threads for the model; evaluation runs read 3 pairs at once
DEFAULT_MODEL = Path("runs") / "sequence" / "s26-cpu-best" / "onnx"   # s26-run1 best.pt, exported
DECODER = "decoder-int8.onnx"   # within half a point of FP32, 1.36 times as fast (progress log, 28 October 2026)


def wanted():
    """OMR_ENGINE asks for Engine 2's notes."""
    return os.environ.get(ENGINE_ENV, "").strip().lower() == "sequence"


def model_dir():
    configured = os.environ.get(MODEL_ENV)
    return Path(configured) if configured else paths.corpus_dir() / DEFAULT_MODEL


@functools.cache
def _reader(folder):
    folder = Path(folder)
    for name in ("encoder.onnx", DECODER):
        if not (folder / name).is_file():
            raise FileNotFoundError(f"the sequence reader's model {folder / name} was not found. "
                                    f"Set {MODEL_ENV} to the folder holding encoder.onnx and {DECODER}.")
    # every processor when converting alone, or where OMR_SEQUENCE_THREADS says
    return sequence.OnnxReader(folder / "encoder.onnx", folder / DECODER, int(os.environ.get(THREADS_ENV) or 0))


@dataclass
class Unit:
    """One part in one system of an image page, cut out for homr."""
    part: int
    numbers: list        # the part's staff numbers in this system, top to bottom
    first_bar: int       # the score's index of the system's first bar
    bars: int            # bars in the system
    image: object        # grey crop, fitted to homr's input size
    shifts: dict = field(default_factory=dict)   # staff number -> (steps, until): see clef_shifts


def units(assigned, use, score=None):
    """The Units of every image page, in score order. `assigned` is
    structure.assign_parts' result and `use` the pages read_pdf read (an
    image page's RasterPage carries its level image and Placement). With
    `score` (Engine 1's reading), a system too long for homr is cut into
    pieces (pieces())."""
    ordered, _ = assigned
    lengths = bar_lengths(score) if score is not None else {}
    changes = signature_changes(score) if score is not None else set()
    clefs = clef_list(score) if score is not None else {}
    out = []
    base = 0
    for pl, system, mapping in ordered:
        page = use[pl.page - 1]
        grey, place = getattr(page, "grey", None), getattr(page, "place", None)
        if grey is not None:
            for p in sorted({part for part, _ in mapping.staves}):
                pairs = [(st, n) for st, (part, n) in zip(system.staves, mapping.staves) if part == p]
                if len(pairs) > 2:
                    continue
                staves = [st for st, _ in pairs]
                numbers = [n for _, n in pairs]
                space = staves[0].space
                left = min(st.x0 for st in staves) - MARGIN_SIDES * space
                right = max(st.x1 for st in staves) + MARGIN_SIDES * space
                top, bottom = staves[0].top - MARGIN_ABOVE * space, staves[-1].bottom + MARGIN_ABOVE * space

                def cut(x0, x1):
                    a, b, c, d = place.to_pixels((x0, top, x1, bottom))
                    h, w = grey.shape
                    return grey[max(0, int(b)):min(h, int(d)), max(0, int(a)):min(w, int(c))]

                tokens = [sum(lengths.get((p, n, base + k), 0) for n in numbers) + 1 for k in range(len(system.bars))]
                last_change = min((k for k in range(1, len(system.bars)) if (p, base + k) in changes),
                                  default=len(system.bars))
                starts = pieces(tokens, last_change)
                header = header_end(pl, system, staves) if len(starts) > 1 else None
                if header is None:
                    starts = [0]
                for i, a in enumerate(starts):
                    end = starts[i + 1] if i + 1 < len(starts) else len(system.bars)
                    x1 = right if end == len(system.bars) else system.bars[end - 1].x1 + 0.5 * space
                    if a == 0:
                        crop = cut(left, x1)
                    else:
                        head, body = cut(left, header + 0.5 * space), cut(system.bars[a].x0, x1)
                        crop = np.hstack([head, body]) if head.size and body.size and len(head) == len(body) else body
                    if crop.size:
                        shifts = clef_shifts(clefs, p, numbers, base, base + a) if a else {}
                        out.append(Unit(p, numbers, base + a, end - a, _fit(crop), shifts))
        base += len(system.bars)
    return out


LONG = 105      # estimated symbols past which a system is cut: homr was trained on units of up to 128,
                # and the estimate runs about 15 percent under what it reads
PIECE = 85      # estimated symbols aimed at in each piece


def pieces(tokens, last_start=None):
    """The first bar of each piece a system's bars are cut into, from the
    estimated symbols of each bar; [0] if it is short enough. The fewest
    pieces of at most PIECE symbols (or of one bar each), cut so the
    longest is as short as it can be. A piece may not start after
    `last_start` (a key change: the system's own key, put in front of each
    piece, would be wrong; a clef change is made good by clef_shifts)."""
    header = 5
    if header + sum(tokens) <= LONG:
        return [0]
    last = len(tokens) - 1 if last_start is None else min(last_start, len(tokens) - 1)
    best = None
    for n in range(2, last + 2):
        found = _balanced(tokens, n, header, last)
        if found is not None and (best is None or found[0] < best[0]):
            best = found
        if best is not None and best[0] <= PIECE:
            break
    return best[1] if best else [0]


def _balanced(tokens, n, header, last):
    """(longest piece, starts) cutting `tokens` into n pieces, each piece
    starting no later than bar `last`, with the longest piece shortest; or None."""
    k = len(tokens)
    sums = [0]
    for t in tokens:
        sums.append(sums[-1] + t)
    # cost[j][i]: the longest piece when the first i bars are cut into j pieces
    inf = float("inf")
    cost = [[inf] * (k + 1) for _ in range(n + 1)]
    back = [[0] * (k + 1) for _ in range(n + 1)]
    cost[0][0] = 0
    for j in range(1, n + 1):
        for i in range(1, k + 1):
            for a in range(j - 1, i):
                if a > last:
                    break
                c = max(cost[j - 1][a], header + sums[i] - sums[a])
                if c < cost[j][i]:
                    cost[j][i], back[j][i] = c, a
    if cost[n][k] == inf:
        return None
    starts, i = [], k
    for j in range(n, 0, -1):
        i = back[j][i]
        starts.append(i)
    return cost[n][k], starts[::-1]


def bar_lengths(score):
    """{(part, staff, bar): symbols homr would write for Engine 1's notes
    and rests}: one for each, and one more for each note that joins a chord."""
    groups = {}
    for item in list(score.notes) + list(score.rests):
        key = (item.part, item.staff, item.bar)
        groups.setdefault(key, {}).setdefault(item.onset, 0)
        groups[key][item.onset] += 1
    return {key: sum(2 * n - 1 for n in onsets.values()) for key, onsets in groups.items()}


def signature_changes(score):
    """{(part, bar)} where Engine 1 found a key signature."""
    return {(m.part, m.bar) for m in score.structure if m.kind == "key"}


def clef_list(score):
    """{(part, staff): [((bar, onset), clef value)]} in order, from Engine 1."""
    clefs = {}
    for m in sorted((m for m in score.structure if m.kind == "clef"), key=lambda m: (m.bar, m.onset)):
        clefs.setdefault((m.part, m.staff), []).append(((m.bar, m.onset), m.value))
    return clefs


def _printed_bottom(value):
    """The bottom line of a clef as printed, leaving out its octave change."""
    return events.clef_bottom(" ".join(value.split()[:2]))


def clef_shifts(clefs, part, numbers, system_bar, piece_bar):
    """{staff: (steps, until)} for a piece starting at `piece_bar` with the
    system's opening clefs in front of it: where the clef in force at the
    piece's start differs, homr reads the piece's notes so many staff steps
    too low, until the next clef inside the piece ((bar, onset), or None)."""
    out = {}
    for n in numbers:
        found = clefs.get((part, n), [])
        opening = [v for at, v in found if at <= (system_bar, Fraction(0))]
        current = [v for at, v in found if at <= (piece_bar, Fraction(0))]
        later = [at for at, _ in found if at > (piece_bar, Fraction(0))]
        if not opening or not current:
            continue
        a, b = _printed_bottom(opening[-1]), _printed_bottom(current[-1])
        if a is not None and b is not None and a != b:
            out[n] = (b - a, later[0] if later else None)
    return out


def moved_by_steps(note, steps, fifths):
    """The note moved so many staff steps; an alteration the key gave the
    old letter becomes the one it gives the new letter."""
    old = note.pitch
    d = events.STEPS.index(old.step) + 7 * old.octave + steps
    step = events.STEPS[d % 7]
    alter = events.key_alter(fifths, step) if old.alter == events.key_alter(fifths, old.step) else old.alter
    return replace(note, pitch=events.Pitch(step, alter, d // 7))


def header_end(pl, system, staves):
    """The right edge of the clefs and key signatures at the start of the
    system on these staves, in page points, or None if none was found. An
    accidental with a notehead on its step just to its right belongs to that
    note, as in structure.staff_keys."""
    from omr.pdf import layout as lay, structure

    marks = (structure.SHARP, structure.FLAT, structure.NATURAL)
    edges = []
    for st in staves:
        heads = [(s.x, pl.step_of(s)) for s in pl.on_staff(st) if lay.is_note(s.name)]
        for s in structure.signature_region(pl, system, st, 0):
            if s.name in marks and any(0 < x - s.x <= 3.5 * st.space and step == pl.step_of(s) for x, step in heads):
                continue
            if s.name in structure.CLEFS or s.name in marks:
                edges.append(s.box[2])
    return max(edges) if edges else None


def unit_pixels(image):
    """A crop as homr's model takes it (sequence.staff_image, from an array)."""
    sequence.use_homr()
    from homr.staff_parsing import add_image_into_tr_omr_canvas

    return ((add_image_into_tr_omr_canvas(image).astype(np.float32) / 255.0 - sequence.MEAN) / sequence.STD)[None]


def tokens_to_score(symbols):
    """An events.Score of one part from homr's symbols, through homr's own
    MusicXML writer."""
    sequence.use_homr()
    from homr.music_xml_generator import XmlGeneratorArguments, generate_xml

    return events.from_root(generate_xml(XmlGeneratorArguments(), [symbols], ""))


def place(read, unit):
    """(notes, rests) of `read` (tokens_to_score's Score) moved into the
    unit's part, staves and bars, and whether its bar count matched the
    system's. With a different count, bars are matched in order from the
    first and the extra ones left out."""
    def moved(item):
        staff = unit.numbers[min(item.staff, len(unit.numbers)) - 1]
        return replace(item, part=unit.part, staff=staff, bar=unit.first_bar + item.bar)

    notes = [moved(n) for n in read.notes if n.bar < unit.bars]
    rests = [moved(r) for r in read.rests if r.bar < unit.bars]
    return notes, rests, len(read.bars) == unit.bars


def octave_shifts(score):
    """A function (note) -> octaves its clef shifts it: homr reads pitches as
    printed (its training tokens had octave clefs taken out)."""
    clefs = {}
    for m in sorted((m for m in score.structure if m.kind == "clef"), key=lambda m: (m.bar, m.onset)):
        clefs.setdefault((m.part, m.staff), []).append(m)

    def shift(note):
        change = 0
        for m in clefs.get((note.part, note.staff), []):
            if (m.bar, m.onset) > (note.bar, note.onset):
                break
            bits = m.value.split()
            change = int(bits[3]) if len(bits) > 3 and bits[2] == "octave" else 0
        return change
    return shift


def replace_notes(score, assigned, use, reader=None):
    """Put Engine 2's notes and rests in place of Engine 1's in every part
    of every system it reads. Returns counts: units read, units whose bar
    count differed from Engine 1's."""
    found = units(assigned, use, score)
    counts = {"units": len(found), "bar count differs": 0}
    if not found:
        return counts
    reader = reader or _reader(str(model_dir()))
    read_where = {(u.part, staff, u.first_bar + k) for u in found for staff in u.numbers for k in range(u.bars)}
    notes = [n for n in score.notes if (n.part, n.staff, n.bar) not in read_where]
    rests = [r for r in score.rests if (r.part, r.staff, r.bar) not in read_where]
    shift = octave_shifts(score)
    keys = events.SignaturesInForce(score)
    for unit in found:
        try:
            read = tokens_to_score(reader.read(unit_pixels(unit.image)))
        except (events.MusicXMLError, ValueError, KeyError, IndexError, ZeroDivisionError):
            counts["bar count differs"] += 1
            continue
        got_notes, got_rests, same = place(read, unit)
        for i, n in enumerate(got_notes):
            steps, until = unit.shifts.get(n.staff, (0, None))
            if steps and (until is None or (n.bar, n.onset) < until):
                got_notes[i] = moved_by_steps(n, steps, keys.key(n.part, n.bar))
        counts["bar count differs"] += not same
        notes += [replace(n, pitch=replace(n.pitch, octave=n.pitch.octave + shift(n))) for n in got_notes]
        rests += got_rests
    score.notes, score.rests = notes, rests
    return counts
