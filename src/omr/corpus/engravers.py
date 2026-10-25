"""Exporters: one per engraver, all with the same interface.

Each exporter takes a MusicXML file and writes a PDF (and, for MuseScore 4, the
MusicXML of exactly what the PDF shows). Commands and the reasons for them are in
`docs/notes/tool-commands.md`.
"""

import glob
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

PROGRAM_FILES = os.environ.get("ProgramFiles", r"C:\Program Files")

MUSESCORE4_FONTS = {
    # requested name: (musicalSymbolFont, musicalTextFont)
    "Leland": ("Leland", "Leland Text"),
    "Bravura": ("Bravura", "Bravura Text"),
    "Petaluma": ("Petaluma", "Petaluma Text"),
    "Emmentaler": ("Emmentaler", "Emmentaler Text"),
    "Gonville": ("Gonville", "Gonville Text"),
    "MuseJazz": ("MuseJazz", "MuseJazz Text"),
    "Finale Maestro": ("Finale Maestro", "Finale Maestro Text"),
    "Finale Broadway": ("Finale Broadway", "Finale Broadway Text"),
}
MUSESCORE3_FONTS = ("Emmentaler", "Bravura", "Gonville", "MuseJazz")
# Font names as they appear inside the PDF, for the font check.
PDF_FONT_NAMES = {
    "Leland": "Leland",
    "Bravura": "Bravura",
    "Petaluma": "Petaluma",
    "Emmentaler": "MScore",
    "Gonville": "Gootville",
    "MuseJazz": "MuseJazz",
    "Finale Maestro": "FinaleMaestro",
    "Finale Broadway": "FinaleBroadway",
}


class ExportError(RuntimeError):
    """An export failed. The message says why."""


@dataclass
class ExportResult:
    pdf: Path
    musicxml: Path | None
    engraver: str
    version: str
    font: str


def _find(name, patterns):
    found = shutil.which(name)
    if found:
        return found
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    return None


def musescore4_path():
    return (
        _find("MuseScore4.exe", [os.path.join(PROGRAM_FILES, "MuseScore 4", "bin", "MuseScore4.exe")])
        or shutil.which("mscore4")
    )


def musescore3_path():
    found = shutil.which("MuseScore3.exe")
    if found:
        return found
    if os.name == "nt":
        try:
            done = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-AppxPackage *MuseScore* | Select-Object -First 1).InstallLocation"],
                capture_output=True, text=True, timeout=30,
            )
            folder = done.stdout.strip()
            candidate = os.path.join(folder, "bin", "MuseScore3.exe")
            if folder and os.path.isfile(candidate):
                return candidate
        except (OSError, subprocess.TimeoutExpired):
            pass
    return _find("MuseScore3.exe", [os.path.join(PROGRAM_FILES, "MuseScore 3", "bin", "MuseScore3.exe")])


def lilypond_paths():
    """Return (lilypond, command list for musicxml2ly) or None."""
    lily = _find("lilypond", [os.path.join(PROGRAM_FILES, "lilypond*", "bin", "lilypond.exe")])
    script = _find("musicxml2ly", [os.path.join(PROGRAM_FILES, "lilypond*", "bin", "musicxml2ly.py")])
    if not lily or not script:
        return None
    python = os.path.join(os.path.dirname(script), "python.exe")
    if script.endswith(".py") and os.path.isfile(python):
        return lily, [python, script]
    return lily, [script]


def _run(args, timeout, what):
    try:
        done = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ExportError(f"{what} timed out after {timeout} seconds")
    except OSError as error:
        raise ExportError(f"{what} could not start: {error}")
    if done.returncode != 0:
        tail = " ".join((done.stderr or done.stdout).split())[-300:]
        raise ExportError(f"{what} exited with status {done.returncode}: {tail}")
    return done


def _version(args):
    try:
        done = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=30)
        text = (done.stdout + done.stderr).strip()
        return text.splitlines()[0].strip() if text else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def set_staff_size(musicxml_bytes, staff_space_mm):
    """Set the MusicXML scaling element so the staff space is staff_space_mm.

    `millimeters` is the size of `tenths` tenths, and a staff space is 10 tenths,
    so 40 tenths is 4 staff spaces.
    """
    text = musicxml_bytes.decode("utf-8")
    scaling = "<scaling><millimeters>%g</millimeters><tenths>40</tenths></scaling>" % (staff_space_mm * 4)
    if re.search(r"<scaling>.*?</scaling>", text, re.S):
        text = re.sub(r"<scaling>.*?</scaling>", scaling, text, count=1, flags=re.S)
    elif "<defaults>" in text:
        text = text.replace("<defaults>", "<defaults>" + scaling, 1)
    else:
        text = re.sub(r"<part-list", lambda m: "<defaults>" + scaling + "</defaults><part-list", text, count=1)
    return text.encode("utf-8")


def export_musescore4(source, out_dir, font="Leland", staff_space_mm=None, timeout=300):
    """Export the PDF and its MusicXML with MuseScore 4 in the requested font.

    One run writes both files (a job file with two outputs) with the same style
    file, so the MusicXML holds exactly what the PDF shows, including the
    positions and system breaks of that layout. It is the pair's ground truth.
    """
    exe = musescore4_path()
    if not exe:
        raise ExportError("MuseScore 4 was not found")
    if font not in MUSESCORE4_FONTS:
        raise ExportError(f"MuseScore 4 font {font!r} is not one of {sorted(MUSESCORE4_FONTS)}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol, text_font = MUSESCORE4_FONTS[font]
    pdf = out_dir / "score.pdf"
    musicxml = out_dir / "score.musicxml"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data = Path(source).read_bytes()
        if staff_space_mm:
            data = set_staff_size(data, staff_space_mm)
        src = tmp / "score.musicxml"
        src.write_bytes(data)
        style = tmp / "style.mss"
        style.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<museScore version="4.70"><Style>'
            f"<musicalSymbolFont>{symbol}</musicalSymbolFont>"
            f"<musicalTextFont>{text_font}</musicalTextFont></Style></museScore>\n",
            encoding="utf-8",
        )
        job = tmp / "job.json"
        job.write_text(json.dumps([{"in": str(src), "out": [str(pdf), str(musicxml)]}]), encoding="utf-8")
        _run([exe, "-S", str(style), "-j", str(job)], timeout, "MuseScore 4 export")
    if not pdf.is_file():
        raise ExportError("MuseScore 4 reported success but wrote no PDF")
    if not musicxml.is_file():
        raise ExportError("MuseScore 4 reported success but wrote no MusicXML")
    return ExportResult(pdf, musicxml, "MuseScore 4", _version([exe, "--long-version"]), font)


def export_musescore3(source, out_dir, font="Emmentaler", timeout=300):
    """Export a PDF with MuseScore 3. The font is set in the uncompressed score."""
    exe = musescore3_path()
    if not exe:
        raise ExportError("MuseScore 3 was not found")
    if font not in MUSESCORE3_FONTS:
        raise ExportError(f"MuseScore 3 font {font!r} is not one of {MUSESCORE3_FONTS}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        mscx = tmp / "score.mscx"
        _run([exe, "-o", str(mscx), str(source)], timeout, "MuseScore 3 import")
        if font != "Emmentaler":
            text = mscx.read_text(encoding="utf-8")
            tag = f"<musicalSymbolFont>{font}</musicalSymbolFont>"
            if "<musicalSymbolFont>" in text:
                text = re.sub(r"<musicalSymbolFont>.*?</musicalSymbolFont>", tag, text, count=1)
            else:
                text = text.replace("<Style>", "<Style>" + tag, 1)
            mscx.write_text(text, encoding="utf-8")
        pdf = out_dir / "score.pdf"
        _run([exe, "-o", str(pdf), str(mscx)], timeout, "MuseScore 3 PDF export")
    if not pdf.is_file():
        raise ExportError("MuseScore 3 reported success but wrote no PDF")
    return ExportResult(pdf, None, "MuseScore 3", _version([exe, "--version"]), font)


def run_musescore3_convert(source, target, timeout=300):
    """Import with MuseScore 3 and write `target` (the format follows its extension)."""
    exe = musescore3_path()
    if not exe:
        raise ExportError("MuseScore 3 was not found")
    _run([exe, "-o", str(target), str(source)], timeout, "MuseScore 3 conversion")
    if not Path(target).is_file():
        raise ExportError("MuseScore 3 reported success but wrote no file")


def lilypond_music_share(source, ly, lily, timeout=300):
    """The share of the reference's notes found in the music musicxml2ly wrote
    to `ly` (lilypond_check.py). ExportError if the check cannot run."""
    from omr.corpus import lilypond_check

    ly = Path(ly)
    midi_ly = ly.with_name(ly.stem + "-midi.ly")
    try:
        midi_ly.write_text(lilypond_check.midi_version(ly.read_text(encoding="utf-8")), encoding="utf-8")
    except lilypond_check.CheckError as error:
        raise ExportError(f"the music check could not run: {error}")
    _run([lily, "-o", str(midi_ly.with_suffix("")), str(midi_ly)], timeout, "LilyPond MIDI")
    midis = sorted(midi_ly.parent.glob(midi_ly.stem + ".mid*"))
    if not midis:
        raise ExportError("LilyPond reported success but wrote no MIDI for the music check")
    try:
        return lilypond_check.share_found(source, midis[0])
    except (ValueError, IndexError, struct.error) as error:   # CheckError, MusicXMLError, a cut-short file
        raise ExportError(f"the music check could not read LilyPond's MIDI: {error}")


def lilypond_music_failure(share):
    """The failure reason for a share of notes found, or None if it is enough."""
    from omr.corpus import lilypond_check

    if share >= lilypond_check.MIN_NOTES_IN_BAR:
        return None
    return (f"musicxml2ly changed the music: {100 * share:.1f} percent of the reference's notes "
            f"are in LilyPond's MIDI within their bar, at least {100 * lilypond_check.MIN_NOTES_IN_BAR:g} needed")


def check_lilypond_music(source, ly, lily, timeout=300):
    """Raise ExportError unless musicxml2ly kept the reference's music."""
    failure = lilypond_music_failure(lilypond_music_share(source, ly, lily, timeout))
    if failure:
        raise ExportError(failure)


def export_lilypond(source, out_dir, timeout=300):
    """Export a PDF through musicxml2ly and LilyPond. A timeout is a failure,
    and so is music that musicxml2ly changed (check_lilypond_music)."""
    paths = lilypond_paths()
    if not paths:
        raise ExportError("LilyPond or musicxml2ly was not found")
    lily, converter = paths
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ly = tmp / "score.ly"
        _run([*converter, "-o", str(ly), str(source)], timeout, "musicxml2ly")
        check_lilypond_music(source, ly, lily, timeout)
        _run([lily, "-o", str(tmp / "score"), str(ly)], timeout, "LilyPond")
        made = tmp / "score.pdf"
        if not made.is_file():
            raise ExportError("LilyPond reported success but wrote no PDF")
        pdf = out_dir / "score.pdf"
        shutil.copyfile(made, pdf)
    return ExportResult(pdf, None, "LilyPond", _version([lily, "--version"]), "Emmentaler")


def fix_verovio_svg(svg):
    """Apply the SVG fixes PyMuPDF needs (see tool-commands.md)."""
    outer = re.search(r'<svg[^>]*viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    inner = re.search(r'<svg class="definition-scale"[^>]*viewBox="0 0 ([\d.]+) ([\d.]+)"[^>]*>', svg)
    if outer and inner:
        scale = float(outer.group(1)) / float(inner.group(1))
        svg = svg.replace(inner.group(0), f'<g transform="scale({scale})">', 1)
        # The inner svg's closing tag is the last "</svg>" before the final one.
        last = svg.rfind("</svg>")
        idx = svg.rfind("</svg>", 0, last)
        if idx != -1:
            svg = svg[:idx] + "</g>" + svg[idx + len("</svg>"):]
    return re.sub(r'(<[^>]*?)(\sstroke-width="[^"]*")', r'\1 stroke="black"\2', svg)


MEI_NS = "{http://www.music-encoding.org/ns/mei}"


def staff_key_changes(source):
    """Key changes after the first bar, as {staff number: {bar index: fifths}}, with
    staves numbered down the score as Verovio numbers them; also each staff's
    first key, {staff number: fifths}, and the bar count."""
    from omr.corpus.labels import read_musicxml

    changes, start, first, bars = {}, {}, 1, 0
    for part in read_musicxml(source).findall("part"):
        measures = part.findall("measure")
        bars = bars or len(measures)
        staves = max([int(s.text) for s in part.iter("staves")] or [1])
        changes.update({first + s: {} for s in range(staves)})
        current = {}
        for i, measure in enumerate(measures):
            for key in measure.iter("key"):
                if key.findtext("fifths") is None:
                    continue
                fifths = int(key.findtext("fifths"))
                local = [int(key.get("number"))] if key.get("number") else range(1, staves + 1)
                for s in local:
                    n = first + s - 1
                    if current.get(n) != fifths:
                        current[n] = fifths
                        if i > 0:
                            changes[n][i] = fifths
                        else:
                            start[n] = fifths
        first += staves
    return changes, start, bars


def fix_verovio_keys(mei, source):
    """Give each staff its own key changes (see tool-commands.md).

    Verovio applies the top part's key changes to every staff, so where parts change
    key differently (transposing instruments, a change in some parts only) the page
    shows the wrong keys. Returns None when every staff changes key alike.

    Verovio draws the naturals that cancel the old key only for a change to no
    sharps or flats made for the whole score, not for one staff. So at a bar where
    a staff changes to no sharps or flats, the whole score changes to none, and
    every staff whose key is not none is given its key again."""
    changes, start, bars = staff_key_changes(source)
    if len({tuple(sorted(c.items())) for c in changes.values()}) <= 1:
        return None
    ET.register_namespace("", MEI_NS[1:-1])
    root = ET.fromstring(mei)
    score = root.find(f".//{MEI_NS}score")
    measures = list(score.iter(f"{MEI_NS}measure"))
    if len(measures) != bars:
        raise ExportError(f"parts change key differently, and Verovio has {len(measures)} bars "
                          f"where the MusicXML has {bars}, so the keys cannot be placed")
    parents = {child: parent for parent in score.iter() for child in parent}
    first = score.find(f"{MEI_NS}scoreDef")
    for score_def in list(score.iter(f"{MEI_NS}scoreDef")):
        if score_def is first:
            continue
        for key in list(score_def.iter(f"{MEI_NS}keySig")):
            parents[key].remove(key)
        if len(score_def) == 0 and set(score_def.attrib) <= {"{http://www.w3.org/XML/1998/namespace}id"}:
            parents[score_def].remove(score_def)
    by_bar = {}
    for n, staff_changes in changes.items():
        for i, fifths in staff_changes.items():
            by_bar.setdefault(i, {})[n] = fifths
    current = {n: start.get(n, 0) for n in changes}
    for i, staves in sorted(by_bar.items()):
        current.update(staves)
        score_def = ET.Element(f"{MEI_NS}scoreDef")
        if 0 in staves.values():
            ET.SubElement(score_def, f"{MEI_NS}keySig", {"sig": "0"})
            staves = {n: fifths for n, fifths in current.items() if fifths != 0}
        group = ET.SubElement(score_def, f"{MEI_NS}staffGrp") if staves else None
        for n, fifths in sorted(staves.items()):
            staff_def = ET.SubElement(group, f"{MEI_NS}staffDef", {"n": str(n)})
            sig = "0" if fifths == 0 else f"{abs(fifths)}{'s' if fifths > 0 else 'f'}"
            ET.SubElement(staff_def, f"{MEI_NS}keySig", {"sig": sig})
        parent = parents[measures[i]]
        parent.insert(list(parent).index(measures[i]), score_def)
    return ET.tostring(root, encoding="unicode")


def export_verovio(source, out_dir):
    """Render with Verovio to SVG, then convert each page to PDF with PyMuPDF."""
    import pymupdf
    import verovio

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tk = verovio.toolkit()
    tk.setOptions({"svgViewBox": True, "svgRemoveXlink": True, "scale": 40})
    if not tk.loadFile(str(source)):
        raise ExportError("Verovio could not load the MusicXML file")
    fixed = fix_verovio_keys(tk.getMEI(), source)
    if fixed and not tk.loadData(fixed):
        raise ExportError("Verovio could not load the MEI with the keys fixed")
    version = tk.getVersion()
    doc = pymupdf.open()
    for page in range(1, tk.getPageCount() + 1):
        svg = fix_verovio_svg(tk.renderToSVG(page))
        svg_doc = pymupdf.open(stream=svg.encode("utf-8"), filetype="svg")
        doc.insert_pdf(pymupdf.open("pdf", svg_doc.convert_to_pdf()))
    doc.set_metadata({"creator": f"Verovio {version}", "producer": f"Verovio {version}"})
    pdf = out_dir / "score.pdf"
    doc.save(pdf)
    doc.close()
    return ExportResult(pdf, None, "Verovio", version, "Verovio")
