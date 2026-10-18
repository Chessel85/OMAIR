"""Training units for the sequence reader (homr) from vector pairs (Phase 2,
Stage 2.1): one part in one system, cropped as homr crops a staff, with its
tokens from the ground-truth MusicXML through homr's own parser.

The rules are in docs/notes/raster-labels-spec.md, "Sequence-reader data".
homr's source is in tools/dl/homr-src on the corpus drive (AGPL-3.0).
"""

import sys
import xml.etree.ElementTree as ET
from collections import Counter

from omr import paths
from omr.pdf import layout as lay
from omr.pdf import structure

SHORT_TOKENS = 128    # units up to this length train at batch 4 with the encoder frozen
MARGIN_SIDES = 2      # staff spaces left and right of the staff, as homr's inference crops
MARGIN_ABOVE = 4      # staff spaces above the top staff and below the bottom one
HOMR_SIZE = (256, 1280)   # homr shrinks every staff image to fit this (height, width), so it is saved no larger


def homr():
    """homr's parser and token helpers, imported from its source folder."""
    base = paths.corpus_dir() / "tools" / "dl" / "homr-src"
    for folder in (base / "libs", base / "repo"):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    from homr.circle_of_fifths import strip_naturals
    from training.omr_datasets.convert_lieder import MeasureCutter, contains_only_supported_clefs
    from training.omr_datasets.music_xml_parser import music_xml_string_to_tokens
    from training.transformer.training_vocabulary import token_lines_to_str

    return {"parse": music_xml_string_to_tokens, "cutter": MeasureCutter, "clefs_ok": contains_only_supported_clefs,
            "strip_naturals": strip_naturals, "to_text": token_lines_to_str}


def as_printed(root):
    """Rewrite MusicXML so its pitches are where the notes are printed, for
    homr's vocabulary, which has no octave clefs or octave lines: a clef's
    octave change and every octave-shift direction are removed, and the
    notes they reach are moved by the octaves they were shifted (spec,
    "Octave clefs and octave lines"). Changes `root` in place."""
    for part in root.iter("part"):
        clef_shift, line_shift = {}, {}
        for measure in part.findall("measure"):
            for el in list(measure):
                if el.tag == "attributes":
                    for clef in el.findall("clef"):
                        change = clef.find("clef-octave-change")
                        # a treble clef with an 8 below sounds an octave under its notes as printed
                        clef_shift[clef.get("number", "1")] = -int(change.text) if change is not None else 0
                        if change is not None:
                            clef.remove(change)
                elif el.tag == "direction":
                    staff = el.findtext("staff") or "1"
                    for kind in el.findall("direction-type"):
                        shift = kind.find("octave-shift")
                        if shift is None:
                            continue
                        amount = {"8": 1, "15": 2, "22": 3}.get(shift.get("size", "8"), 1)
                        # "down" is 8va: the notes are printed an octave below their pitch
                        way = shift.get("type")
                        line_shift[staff] = -amount if way == "down" else amount if way == "up" else 0
                        kind.remove(shift)
                elif el.tag == "note":
                    pitch = el.find("pitch")
                    if pitch is None:
                        continue
                    staff = el.findtext("staff") or "1"
                    moved = clef_shift.get(staff, 0) + line_shift.get(staff, 0)
                    if moved:
                        octave = pitch.find("octave")
                        octave.text = str(int(octave.text) + moved)
    return root


def printed_notes(measure):
    """Notes with a pitch that are printed, in one MusicXML measure (all staves)."""
    return sum(1 for n in measure.findall("note")
               if n.find("pitch") is not None and n.get("print-object") != "no")


def system_starts(measures):
    """Bar indexes where MuseScore starts a new system, from its print elements."""
    starts = [0]
    for i, m in enumerate(measures):
        p = m.find("print")
        if i and p is not None and (p.get("new-system") == "yes" or p.get("new-page") == "yes"):
            starts.append(i)
    return starts


def make_units(doc, pages, rendered, truth, score_id, job, out, split):
    """Write the homr units of one pair under `out`: images/<split>/,
    tokens/<split>/ and a list for the pair in lists/<split>/ (joined into
    index files at the end of the run). Returns counts, including the units
    dropped and why."""
    h = homr()
    counts = Counter()
    layouts = lay.read_document(doc, pages)
    ordered, parts = structure.assign_parts(layouts)
    root = as_printed(ET.parse(truth).getroot())
    xml_parts = root.findall("part")
    staves_seen = sum(len(m.staves) for _, _, m in ordered)
    try:
        voices = h["parse"](ET.tostring(root, encoding="unicode"))
    except Exception as error:
        counts[f"units dropped: homr could not read the MusicXML ({str(error)[:60]})"] += staves_seen
        return counts
    if len(voices) != len(parts) or len(xml_parts) != len(parts):
        counts["units dropped: the parts differ from the MusicXML"] += staves_seen
        return counts
    measures = [p.findall("measure") for p in xml_parts]
    bars = [sum(b.multirest for b in system.bars) for _, system, _ in ordered]
    if sum(bars) != len(measures[0]):
        counts["units dropped: the bar count differs from the MusicXML"] += staves_seen
        return counts
    if job.startswith("musescore4"):
        starts = [sum(bars[:i]) for i in range(len(bars))]
        if starts != system_starts(measures[0]):
            counts["units dropped: the systems differ from the MusicXML's"] += staves_seen
            return counts
    cutters = [h["cutter"](list(v)) for v in voices]
    lines = []
    base = 0
    for (pl, system, mapping), count in zip(ordered, bars):
        tokens = [c.extract_measures(count) for c in cutters]
        for p in sorted({part for part, _ in mapping.staves}):
            counts["units seen"] += 1
            staves = [st for st, (part, _) in zip(system.staves, mapping.staves) if part == p]
            reason = _unit_problem(pl, system, staves, measures[p][base:base + count], tokens[p], h)
            if reason:
                counts[f"units dropped: {reason}"] += 1
                continue
            if pl.page not in rendered:
                counts["units dropped: the page was not rendered"] += 1
                continue
            image, zoom, _ = rendered[pl.page]
            space = staves[0].space
            x0 = (min(st.x0 for st in staves) - MARGIN_SIDES * space) * zoom
            x1 = (max(st.x1 for st in staves) + MARGIN_SIDES * space) * zoom
            y0 = (staves[0].top - MARGIN_ABOVE * space) * zoom
            y1 = (staves[-1].bottom + MARGIN_ABOVE * space) * zoom
            ih, iw = image.shape
            crop = image[max(0, int(y0)):min(ih, int(y1)), max(0, int(x0)):min(iw, int(x1))]
            symbols = h["strip_naturals"](tokens[p])
            try:
                text = h["to_text"](symbols)
            except KeyError:
                counts["units dropped: a duration homr has no token for"] += 1
                continue
            length = len(symbols) + 2   # with the start and end tokens
            stem = f"{score_id}-{job}-s{pl.page}-{system.index}-p{p}"
            image_path = out / "images" / split / f"{stem}.png"
            token_path = out / "tokens" / split / f"{stem}.tokens"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(_png(_fit(crop)))
            token_path.write_text(text, encoding="utf-8")
            lines.append(f"{image_path},{token_path},{length}\n")
            counts["units"] += 1
            if length > SHORT_TOKENS:
                counts[f"units over {SHORT_TOKENS} tokens"] += 1
        base += count
    listing = out / "lists" / split / f"{score_id}-{job}.txt"
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text("".join(lines), encoding="utf-8")
    return counts


def _unit_problem(pl, system, staves, measures, tokens, h):
    """Why a unit cannot be used, or None."""
    if len(staves) > 2:
        return "a part of more than two staves"
    if any(b.multirest > 1 for b in system.bars):
        return "a multi-bar rest"
    if not h["clefs_ok"](tokens):
        return "a clef homr cannot write"
    ids = {id(st) for st in staves}
    for bar, measure in zip(system.bars, measures):
        heads = sum(1 for s in pl.symbols if lay.is_note(s.name) and not s.name.startswith("noteheadParenthesis")
                    and id(pl.staff_of(s)) in ids and bar.x0 <= s.x <= bar.x1)
        if heads != printed_notes(measure):
            return "the noteheads differ from the MusicXML"
    notes = sum(1 for s in tokens if s.rhythm.startswith("note"))
    if notes != sum(printed_notes(m) for m in measures):
        return "the tokens' notes differ from the MusicXML"
    return None


def _fit(image):
    """The image shrunk to fit homr's input size, if it is larger."""
    import cv2

    h, w = image.shape
    scale = min(1.0, HOMR_SIZE[0] / h, HOMR_SIZE[1] / w)
    if scale >= 1.0:
        return image
    return cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)


def _png(image):
    import cv2

    ok, data = cv2.imencode(".png", image)
    return data.tobytes()
