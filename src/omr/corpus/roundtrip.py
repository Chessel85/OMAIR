"""The round-trip filter and the reference MusicXML (spec, 'Filters').

MuseScore 4 imports the source MusicXML and exports it again: that file is the
reference MusicXML. MuseScore 3 then imports the reference and exports it, and
musicdiff compares the two. Any difference in notes or rests drops the score.
Results are cached, so a re-run does not repeat the slow steps.
"""

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from omr.corpus import engravers, sources


@dataclass
class RoundTrip:
    ok: bool
    reason: str
    reference: str | None = None  # path of the kept reference MusicXML
    pages: int = 0                # pages in the MuseScore 4 PDF (default font)
    version: int = 1              # CHECK_VERSION when the record was made


# Version 2 treats a musicdiff parse failure as a failure (version 1 passed it),
# so a passing record from an older version is checked again.
CHECK_VERSION = 2


def cache_dir():
    folder = sources.work_dir() / "roundtrip"
    folder.mkdir(exist_ok=True)
    return folder


def check(candidate, timeout=240):
    """Run (or read from the cache) the round trip for one candidate."""
    folder = cache_dir()
    record = folder / f"{candidate.id}.json"
    if record.is_file():
        cached = RoundTrip(**json.loads(record.read_text(encoding="utf-8")))
        if not cached.ok or cached.version >= CHECK_VERSION:
            return cached
    result = _run(candidate, folder, timeout)
    result.version = CHECK_VERSION
    record.write_text(json.dumps(result.__dict__), encoding="utf-8")
    return result


def compare_notes(first, second, diff=None):
    """None if musicdiff finds no difference in notes or rests, else the reason.

    musicdiff returns None (not 0) when a file fails to parse, so only an
    explicit 0 is a pass.
    """
    if diff is None:
        from musicdiff import diff
    from musicdiff.detaillevel import DetailLevel

    try:
        edits = diff(str(first), str(second), visualize_diffs=False, detail=DetailLevel.NotesAndRests)
    except Exception as error:
        return f"musicdiff failed: {error}"
    if edits is None:
        return "musicdiff could not parse one of the files"
    if edits != 0:
        return f"musicdiff found {edits} differences in notes or rests"
    return None


def _run(candidate, folder, timeout):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source = tmp / "source.musicxml"
        _to_plain_xml(candidate.mxl, source)
        try:
            first = engravers.export_musescore4(source, tmp / "ms4", timeout=timeout)
            if not first.musicxml:
                return RoundTrip(False, "MuseScore 4 wrote no MusicXML")
            pages = len(pymupdf.open(first.pdf))
            again = tmp / "ms3.musicxml"
            engravers.run_musescore3_convert(first.musicxml, again, timeout=timeout)
        except engravers.ExportError as error:
            return RoundTrip(False, f"export failed: {error}")
        except Exception as error:
            return RoundTrip(False, f"could not read the PDF or MusicXML: {error}")
        failure = compare_notes(first.musicxml, again)
        if failure:
            return RoundTrip(False, failure, pages=pages)
        kept = folder / f"{candidate.id}.reference.musicxml"
        shutil.copyfile(first.musicxml, kept)
        return RoundTrip(True, "ok", str(kept), pages)


def _to_plain_xml(path, target):
    """The engravers read plain MusicXML more reliably than compressed .mxl."""
    from omr.corpus import labels
    import xml.etree.ElementTree as ET

    root = labels.read_musicxml(path)
    ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True)
