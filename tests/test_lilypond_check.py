"""The LilyPond music check (src/omr/corpus/lilypond_check.py)."""

import struct

import pytest

from omr.corpus import engravers, lilypond_check
from omr.corpus.lilypond_check import GRID


def number(value):
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.insert(0, 0x80 | (value & 0x7F))
        value >>= 7
    return bytes(out)


def track(events):
    """events: (delta ticks, event bytes)."""
    body = b"".join(number(d) + e for d, e in events) + b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + body


def midi_file(path, tracks, division=384):
    path.write_bytes(b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), division) + b"".join(tracks))
    return path


def test_read_midi_merges_tracks_and_skips_percussion_and_note_offs(tmp_path):
    first = track([
        (0, b"\xff\x51\x03\x07\xa1\x20"),     # a tempo, a meta event
        (0, b"\x90\x3c\x50"),                 # C4 at 0
        (0, b"\x40\x50"),                     # E4 at 0, running status
        (384, b"\x3c\x00"),                   # a note-on at velocity 0 is a note off
        (0, b"\x43\x50"),                     # G4 at one quarter
    ])
    second = track([
        (192, b"\x91\x3c\x50"),               # C4 at an eighth, another channel
        (0, b"\x99\x24\x50"),                 # a drum on the percussion channel
        (192, b"\x91\x3c\x50"),               # C4 at one quarter
    ])
    notes = lilypond_check.read_midi(midi_file(tmp_path / "a.mid", [first, second]))
    assert notes == {(0, 60), (0, 64), (GRID, 67), (GRID // 2, 60), (GRID, 60)}


def test_a_bar_shifted_as_a_whole_counts_and_a_moved_note_does_not():
    reference = {0: {(0, 60), (GRID, 62)}, 1: {(2 * GRID, 64), (3 * GRID, 65)}}
    # Bar 1 comes half a quarter late as a whole: its notes still count.
    late = {(0, 60), (GRID, 62), (2 * GRID + 48, 64), (3 * GRID + 48, 65)}
    assert lilypond_check.notes_in_bar(reference, late) == (4, 4)
    # One note of bar 1 moved inside the bar: it is missing.
    moved = {(0, 60), (GRID, 62), (2 * GRID, 64), (3 * GRID + 48, 65)}
    assert lilypond_check.notes_in_bar(reference, moved) == (3, 4)


def test_midi_version_writes_midi_from_the_printed_score_at_written_pitch():
    ly = "\\score { << \\transposition bes \\new Staff { c'4 } >> \\layout {} }\n"
    made = lilypond_check.midi_version(ly)
    assert "\\layout {}" not in made and lilypond_check.MIDI_BLOCK in made
    assert "\\transposition" not in made
    with pytest.raises(lilypond_check.CheckError):
        lilypond_check.midi_version("\\score { c'4 }")


def test_a_pair_needs_99_percent_of_its_notes():
    assert engravers.lilypond_music_failure(0.99) is None
    assert engravers.lilypond_music_failure(1.0) is None
    reason = engravers.lilypond_music_failure(0.874)
    assert reason.startswith("musicxml2ly changed the music: 87.4 percent")
    assert "at least 99 needed" in reason
