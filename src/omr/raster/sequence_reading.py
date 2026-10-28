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
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from omr import paths
from omr.corpus.sequence_units import MARGIN_ABOVE, MARGIN_SIDES, _fit
from omr.evaluate import events
from omr.raster import sequence

ENGINE_ENV = "OMR_ENGINE"
MODEL_ENV = "OMR_SEQUENCE_MODEL"
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
    return sequence.OnnxReader(folder / "encoder.onnx", folder / DECODER)


@dataclass
class Unit:
    """One part in one system of an image page, cut out for homr."""
    part: int
    numbers: list        # the part's staff numbers in this system, top to bottom
    first_bar: int       # the score's index of the system's first bar
    bars: int            # bars in the system
    image: object        # grey crop, fitted to homr's input size


def units(assigned, use):
    """The Units of every image page, in score order. `assigned` is
    structure.assign_parts' result and `use` the pages read_pdf read (an
    image page's RasterPage carries its level image and Placement)."""
    ordered, _ = assigned
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
                space = staves[0].space
                box = (min(st.x0 for st in staves) - MARGIN_SIDES * space, staves[0].top - MARGIN_ABOVE * space,
                       max(st.x1 for st in staves) + MARGIN_SIDES * space, staves[-1].bottom + MARGIN_ABOVE * space)
                x0, y0, x1, y1 = place.to_pixels(box)
                h, w = grey.shape
                crop = grey[max(0, int(y0)):min(h, int(y1)), max(0, int(x0)):min(w, int(x1))]
                if crop.size:
                    out.append(Unit(p, [n for _, n in pairs], base, len(system.bars), _fit(crop)))
        base += len(system.bars)
    return out


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
    found = units(assigned, use)
    counts = {"units": len(found), "bar count differs": 0}
    if not found:
        return counts
    reader = reader or _reader(str(model_dir()))
    read_where = {(u.part, staff, u.first_bar + k) for u in found for staff in u.numbers for k in range(u.bars)}
    notes = [n for n in score.notes if (n.part, n.staff, n.bar) not in read_where]
    rests = [r for r in score.rests if (r.part, r.staff, r.bar) not in read_where]
    shift = octave_shifts(score)
    for unit in found:
        try:
            read = tokens_to_score(reader.read(unit_pixels(unit.image)))
        except (events.MusicXMLError, ValueError, KeyError, IndexError, ZeroDivisionError):
            counts["bar count differs"] += 1
            continue
        got_notes, got_rests, same = place(read, unit)
        counts["bar count differs"] += not same
        notes += [replace(n, pitch=replace(n.pitch, octave=n.pitch.octave + shift(n))) for n in got_notes]
        rests += got_rests
    score.notes, score.rests = notes, rests
    return counts
