"""Braille music from MusicXML through a translator adapter (Stage 1.6, OUT-2).

The braille code, formatting and default file format are not decided yet
(OI-1), so this is a placeholder: one translator (music21's braille module)
and two file formats, chosen by the file name or by `fmt`:

- "brf": Braille ASCII (North American table), the file embossers and
  braille displays read. Cells with dots 7 or 8 lose those dots.
- "unicode": Unicode braille cells (U+2800 to U+28FF) in UTF-8 text.

See docs/notes/musicxml-spec.md, "Braille".
"""

import contextlib
import io
import re
import warnings
from pathlib import Path

# Braille ASCII: the character for each six-dot cell, by its dot bits (dot 1 = 1, ... dot 6 = 32)
BRAILLE_ASCII = " A1B'K2L@CIF/MSP\"E3H9O6R^DJG>NTQ,*5<-U8V.%[$+X!&;:4\\0Z7(_?W]#Y)="
FORMATS = ("brf", "unicode")
LINE_LENGTH = 40   # cells in a braille line
ENGINES = ("music21",)


class BrailleError(Exception):
    """The translator could not make braille. The message says why."""


def format_for(path, fmt=None):
    """The format to write: `fmt` if given, else by the file name (.brf for
    Braille ASCII, anything else Unicode braille)."""
    if fmt:
        if fmt not in FORMATS:
            raise ValueError(f"the braille format must be one of {', '.join(FORMATS)}, not {fmt!r}")
        return fmt
    return "brf" if Path(path).suffix.lower() == ".brf" else "unicode"


def to_brf(text):
    """Unicode braille text as Braille ASCII. Characters that are not braille
    cells (spaces, line ends) are kept."""
    out = []
    for c in text:
        code = ord(c)
        if 0x2800 <= code <= 0x28FF:
            out.append(BRAILLE_ASCII[(code - 0x2800) & 0x3F])
        else:
            out.append(c)
    return "".join(out)


# characters music21's braille alphabet lacks, and what is written instead
TEXT_SUBSTITUTES = {"\u2018": "'", "\u2019": "'", "\u2013": "-", "\u2014": "-", "\u2010": "-",
                    "\u00a0": " ", "\u2026": "..."}


def _music21(musicxml_path):
    """(Unicode braille, [things music21 left out, in its words])."""
    from music21 import braille, converter

    said = io.StringIO()
    with warnings.catch_warnings(), contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
        warnings.simplefilter("ignore")   # music21's import warnings would clutter the screen
        score = converter.parse(str(musicxml_path), format="musicxml", forceSource=True)
        if score.metadata is not None and score.metadata.movementName == Path(musicxml_path).name:
            score.metadata.movementName = None   # music21 names an untitled movement after its file
        dropped, fingerings = _prepare(score)
        try:
            text, notes = braille.translate.objectToBraille(score, maxLineLength=LINE_LENGTH), []
        except Exception:   # music21 stops on some scores: try each part on its own
            said.seek(0)
            said.truncate()   # its warnings come again, part by part
            text, notes = _part_by_part(score)
    left_out = [_words(line.split("WARNING:", 1)[1]) for line in said.getvalue().splitlines()
                if "cannot be transcribed" in line and "WARNING:" in line]
    if dropped:
        left_out.append(f"characters in text with no braille here: {' '.join(sorted(dropped))}")
    if fingerings:
        left_out.append(f"fingering music21 cannot write: {fingerings}")
    return text, left_out + notes


def _part_by_part(score):
    """(braille, notes) written part by part, for a score music21 cannot
    write whole. A part whose bar is longer than a line is tried with longer
    lines; a part music21 still cannot write is left out and named."""
    from music21 import braille

    texts, notes = [], []
    for n, part in enumerate(score.parts):
        name = part.partName or f"part {n + 1}"
        for length in (LINE_LENGTH, 2 * LINE_LENGTH, 4 * LINE_LENGTH):
            try:
                texts.append(braille.translate.partToBraille(part, maxLineLength=length))
                if length > LINE_LENGTH:
                    notes.append(f"line length: {name} has lines up to {length} cells, as music21 cannot "
                                 f"split one of its bars over {LINE_LENGTH}-cell lines")
                break
            except braille.text.BrailleTextException:
                continue
            except Exception as error:   # music21's own failure on this part
                notes.append(f"part: {name}, which music21 could not write "
                             f"({' '.join(str(error).split())[:120]})")
                break
        else:
            notes.append(f"part: {name}, as music21 cannot fit one of its bars on a line")
    if len(score.parts) > 1 and texts:
        notes.append("layout: the parts are written one after another, not bar over bar, as music21 "
                     "could not write the score whole")
    if not texts:
        raise BrailleError("music21 could not write any part of the score in braille")
    return "\n\n".join(texts), notes


def _prepare(score):
    """Make a score music21's braille translator can take: text with only
    the characters its alphabet has (returns the characters dropped), and an
    empty voice in the next bar for a voice that runs past its bar's end
    (music21 ties the overflow into a voice of the same number)."""
    from music21 import expressions, stream
    from music21.braille import lookup
    from music21.common import stringTools

    from music21.braille import basic

    dropped = set()
    fingerings = 0

    def clean(value):
        out = []
        for c in value:
            for d in TEXT_SUBSTITUTES.get(c, c):
                if d.lower() in lookup.alphabet or stringTools.stripAccents(d).lower() in lookup.alphabet:
                    out.append(d)
                else:
                    dropped.add(d)
        return " ".join("".join(out).split())

    if score.metadata is not None:
        for name in ("title", "movementName", "composer", "lyricist"):
            try:
                value = getattr(score.metadata, name)
                if value:
                    setattr(score.metadata, name, clean(str(value)))
            except (AttributeError, ValueError, TypeError):
                pass
    for t in score.recurse().getElementsByClass(expressions.TextExpression):
        t.content = clean(t.content)
    for n in score.recurse().notes:
        for lyric in n.lyrics:
            if lyric.text:
                lyric.text = clean(lyric.text) or "-"
    for n in score.recurse().notes:
        for art in list(n.articulations):
            if "Fingering" in art.classes:
                try:
                    basic.transcribeNoteFingering(art.fingerNumber)
                except Exception:   # music21 stops on a fingering it cannot write
                    n.articulations.remove(art)
                    fingerings += 1
    for part in score.parts:
        if part.partName:
            part.partName = clean(part.partName)
        measures = list(part.getElementsByClass(stream.Measure))
        for m, following in zip(measures, measures[1:]):
            length = m.barDuration.quarterLength
            present = {str(v.id) for v in following.voices}
            for v in m.voices:
                if v.highestTime > length and str(v.id) not in present:
                    following.insert(0, stream.Voice(id=v.id))
                    present.add(str(v.id))
    return dropped, fingerings


def _words(message):
    """One of music21's warnings, "<music21.repeat.Fine 'Fine'> cannot be
    transcribed to braille.", in words, as "kind: details" ("fine mark: Fine")."""
    message = " ".join(message.replace("cannot be transcribed to braille.", "").split())
    found = re.search(r"Barline <music21\.bar\.Repeat direction=(\w+)>", message)
    if found:
        return f"repeat barline: {found.group(1)}"
    found = re.search(r"Rest of duration <music21\.duration\.Duration ([\d./]+)>", message)
    if found:
        return f"rest of an unusual length: {found.group(1)} quarter notes"
    found = re.search(r"Duration <music21\.duration\.Duration ([\d./]+)> of note <music21\.note\.Note (\S+?)>", message)
    if found:
        return f"note of an unusual length: {found.group(2)}, {found.group(1)} quarter notes"
    found = re.search(r"<music21\.chord\.Chord ([^>]+)>", message)
    if found:
        return f"chord: {found.group(1)}"
    found = re.search(r"<music21\.[\w.]*?(\w+)(?: '(.*?)')?>", message)
    if found:
        kind = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", found.group(1)).lower()
        kind = kind if kind.endswith("mark") else kind + " mark"
        return f"{kind}: {found.group(2)}" if found.group(2) else kind
    return message


def translate(musicxml_path, engine="music21"):
    """(Unicode braille text, [things the translator left out]) for the
    score in a MusicXML file."""
    if engine not in ENGINES:
        raise ValueError(f"the braille translator must be one of {', '.join(ENGINES)}, not {engine!r}")
    try:
        text, left_out = _music21(musicxml_path)
    except BrailleError:
        raise
    except Exception as error:   # the translator's own failure, reported in words
        words = " ".join(str(error).split())[:200] or type(error).__name__
        raise BrailleError(f"music21 could not translate the score into braille ({words})")
    return text.replace("\r\n", "\n").rstrip("\n") + "\n", left_out


def write(musicxml_path, out_path, fmt=None, engine="music21"):
    """Translate `musicxml_path` and write the braille to `out_path`.
    Returns (braille lines written, [things the translator left out])."""
    fmt = format_for(out_path, fmt)
    text, left_out = translate(musicxml_path, engine)
    if fmt == "brf":
        Path(out_path).write_bytes(to_brf(text).replace("\n", "\r\n").encode("ascii", "replace"))
    else:
        Path(out_path).write_text(text, encoding="utf-8")
    return text.count("\n"), left_out
