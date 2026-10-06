"""Tests for the evaluation harness, with hand-made MusicXML pairs whose right
figures are worked out by hand in each test (spec, "Hand-made test pairs").

The builder writes small partwise MusicXML. Durations are in divisions; the
default of 12 divisions per quarter note allows triplets and sixteenths.
"""

import io
import json
from fractions import Fraction

import pytest

from omr.evaluate import events, harness, metrics, recognisers, report
from omr.log import ProgressLog

DIV = 12
TYPES = {48: "whole", 24: "half", 12: "quarter", 6: "eighth", 3: "16th", 36: "half", 18: "quarter", 9: "eighth"}


def note(pitch="C4", dur=12, voice=1, staff=1, chord=False, grace=False, typ=None, dots=None, tm=None,
         tie=None, alter=None, extra=""):
    """A note element. pitch like "C4", "F#5" or "Bb3"; tm is (actual, normal)."""
    step, rest = pitch[0], pitch[1:]
    if alter is None:
        alter = rest.count("#") - rest.count("b")
    octave = rest.replace("#", "").replace("b", "")
    typ = typ or TYPES.get(dur, "quarter")
    dots = (1 if dur in (36, 18, 9) else 0) if dots is None else dots
    parts = ["<note>"]
    if grace:
        parts.append("<grace/>")
    if chord:
        parts.append("<chord/>")
    parts.append(f"<pitch><step>{step}</step>" + (f"<alter>{alter}</alter>" if alter else "") + f"<octave>{octave}</octave></pitch>")
    if not grace:
        parts.append(f"<duration>{dur}</duration>")
    if tie:
        parts.append(f'<tie type="{tie}"/>')
    parts.append(f"<voice>{voice}</voice><type>{typ}</type>" + "<dot/>" * dots)
    if tm:
        parts.append(f"<time-modification><actual-notes>{tm[0]}</actual-notes><normal-notes>{tm[1]}</normal-notes></time-modification>")
    parts.append(f"<staff>{staff}</staff>{extra}</note>")
    return "".join(parts)


def rest(dur=12, voice=1, staff=1, whole_bar=False, typ=None):
    kind = '<rest measure="yes"/>' if whole_bar else "<rest/>"
    dots = "<dot/>" if dur in (36, 18, 9) else ""
    type_el = "" if whole_bar else f"<type>{typ or TYPES.get(dur, 'quarter')}</type>{dots}"
    return f"<note>{kind}<duration>{dur}</duration><voice>{voice}</voice>{type_el}<staff>{staff}</staff></note>"


def backup(dur):
    return f"<backup><duration>{dur}</duration></backup>"


def attributes(time="4/4", key=0, clefs=("G2",), staves=1, divisions=DIV, extra=""):
    beats, beat_type = time.split("/")
    clef_xml = "".join(f'<clef number="{i + 1}"><sign>{c[0]}</sign><line>{c[1]}</line></clef>' for i, c in enumerate(clefs))
    return (f"<attributes><divisions>{divisions}</divisions><key><fifths>{key}</fifths></key>"
            f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"
            + (f"<staves>{staves}</staves>" if staves > 1 else "") + f"{clef_xml}{extra}</attributes>")


def dynamic(mark, offset=0, staff=1):
    off = f"<offset>{offset}</offset>" if offset else ""
    return f"<direction><direction-type><dynamics><{mark}/></dynamics></direction-type>{off}<staff>{staff}</staff></direction>"


def score(*parts):
    """parts: (name, [measure contents...]) pairs; a measure is a string, or (attrs dict, string)."""
    plist = "".join(f'<score-part id="P{i}"><part-name>{name}</part-name></score-part>' for i, (name, _) in enumerate(parts))
    body = ""
    for i, (_, measures) in enumerate(parts):
        ms = ""
        for n, m in enumerate(measures, 1):
            attrs = ""
            if isinstance(m, tuple):
                attrs, m = m
            ms += f'<measure number="{n}"{attrs}>{m}</measure>'
        body += f'<part id="P{i}">{ms}</part>'
    return f'<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0"><part-list>{plist}</part-list>{body}</score-partwise>'


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def compare(tmp_path, truth, output, flags=None):
    t = write(tmp_path, "truth.musicxml", truth)
    o = write(tmp_path, "output.musicxml", output)
    f = None
    if flags is not None:
        f = write(tmp_path, "flags.json", json.dumps({"version": 1, "flags": flags}))
    return metrics.compare(t, o, f)


def four_quarters(pitches="C4 D4 E4 F4", first=None):
    return (first or attributes()) + "".join(note(p) for p in pitches.split())


def accuracy(fig):
    m, d = report.note_accuracy(fig["notes"])
    return Fraction(m, d)


# ------------------------------------------------------------------ reading


def test_reader_onsets_chords_backup_and_whole_bar_rests(tmp_path):
    xml = score(("Piano", [attributes(staves=2, clefs=("G2", "F4"))
                           + note("C4", 24) + note("E4", 24, chord=True) + note("G4", 24)
                           + backup(48) + note("C3", 48, voice=5, staff=2),
                           rest(48, whole_bar=True)]))
    s = events.read(write(tmp_path, "a.musicxml", xml))
    keys = sorted((n.bar, n.onset, n.pitch.words(), n.duration, n.staff) for n in s.notes)
    assert keys == [(0, 0, "C 3", 4, 2), (0, 0, "C 4", 2, 1), (0, 0, "E 4", 2, 1), (0, 2, "G 4", 2, 1)]
    assert s.rests[0].duration == events.WHOLE_BAR and s.rests[0].bar == 1
    assert [b.length for b in s.bars] == [4, 4]
    assert s.parts[0].staves == 2


def test_unreadable_files_raise_a_plain_error(tmp_path):
    with pytest.raises(events.MusicXMLError, match="not well-formed"):
        events.read(write(tmp_path, "bad.musicxml", "<score-partwise><part>"))
    with pytest.raises(events.MusicXMLError, match="no parts"):
        events.read(write(tmp_path, "empty.musicxml", "<score-partwise><part-list/></score-partwise>"))


# ------------------------------------------------------------------ the cases the spec lists


def test_identical_files_score_100_percent(tmp_path):
    xml = score(("Flute", [four_quarters(), four_quarters("G4 A4 B4 C5")]))
    fig = compare(tmp_path, xml, xml)
    assert accuracy(fig) == 1 and fig["structure"]["correct"] and fig["errors"] == []


def test_triplets_against_plain_eighths(tmp_path):
    # Truth: triplet eighths C D E at 0, 1/3, 2/3. Output: plain eighths at 0, 1/2, 1.
    # C differs in duration; D and E in onset and duration: 3 wrong, 0 exact.
    trip = attributes() + "".join(note(p, 4, typ="eighth", tm=(3, 2)) for p in ("C4", "D4", "E4")) + rest(36)
    plain = attributes() + "".join(note(p, 6) for p in ("C4", "D4", "E4")) + rest(6) + rest(24)
    fig = compare(tmp_path, score(("Flute", [trip])), score(("Flute", [plain])))
    assert fig["notes"]["exact"] == 0 and fig["notes"]["wrong"] == 3
    assert fig["notes"]["wrong by kind"] == {"duration": 1, "onset and duration": 2}


def test_triplet_starting_after_a_rest(tmp_path):
    # A triplet-eighth rest, then two triplet eighths at 1/3 and 2/3 of a beat.
    bar = attributes() + rest(4, typ="eighth") + note("D4", 4, typ="eighth", tm=(3, 2)) + note("E4", 4, typ="eighth", tm=(3, 2)) + rest(36)
    s = events.read(write(tmp_path, "t.musicxml", score(("Flute", [bar]))))
    assert [(n.onset, n.duration) for n in s.notes] == [(Fraction(1, 3), Fraction(1, 3)), (Fraction(2, 3), Fraction(1, 3))]


def test_tie_across_a_barline_counts_two_notes(tmp_path):
    # Two written notes; the output drops the tie: notes all right, ties 0 of 2.
    truth = score(("Flute", [attributes(time="2/4") + note("C4", 24, tie="start"), note("C4", 24, tie="stop")]))
    output = score(("Flute", [attributes(time="2/4") + note("C4", 24), note("C4", 24)]))
    fig = compare(tmp_path, truth, output)
    assert fig["notes"]["truth"] == 2 and accuracy(fig) == 1
    assert fig["diagnostics"]["ties"] == {"right": 0, "of": 2}


def test_grace_notes(tmp_path):
    # A grace note before a note and one before a chord. The output drops the first
    # and gives the second another value: 1 missing, 1 wrong (duration), 3 exact.
    truth = score(("Piano", [attributes(time="2/4") + note("D5", typ="eighth", grace=True) + note("C5", 12)
                             + note("B4", typ="eighth", grace=True) + note("G4", 12) + note("E4", 12, chord=True)]))
    output = score(("Piano", [attributes(time="2/4") + note("C5", 12)
                              + note("B4", typ="16th", grace=True) + note("G4", 12) + note("E4", 12, chord=True)]))
    fig = compare(tmp_path, truth, output)
    assert (fig["notes"]["exact"], fig["notes"]["missing"], fig["notes"]["wrong"]) == (3, 1, 1)
    assert fig["notes"]["wrong by kind"] == {"duration": 1}


def test_cross_staff_note_on_the_other_staff_is_a_staff_error_only(tmp_path):
    piano = attributes(staves=2, clefs=("G2", "F4"))
    truth = score(("Piano", [piano + note("C4") + note("D4", staff=2) + note("E4") + note("F4") + backup(48)
                             + note("C3", 48, voice=5, staff=2)]))
    output = score(("Piano", [piano + note("C4") + note("D4", staff=1) + note("E4") + note("F4") + backup(48)
                              + note("C3", 48, voice=5, staff=2)]))
    fig = compare(tmp_path, truth, output)
    assert accuracy(fig) == 1
    assert fig["diagnostics"]["staff"] == {"right": 4, "of": 5}


def test_pickup_bar_and_split_bar_are_bars(tmp_path):
    pickup = (' implicit="yes"', attributes() + note("G4"))
    split_first = attributes() + note("C4") + note("D4") + "<barline location=\"right\"><repeat direction=\"backward\"/></barline>"
    split_second = (' implicit="yes"', note("E4") + note("F4"))
    xml = score(("Flute", [pickup, four_quarters(first=" "), split_first, split_second]))
    s = events.read(write(tmp_path, "p.musicxml", xml))
    assert len(s.bars) == 4 and [b.length for b in s.bars] == [1, 4, 2, 2]
    fig = compare(tmp_path, xml, xml)
    assert accuracy(fig) == 1 and fig["structure"]["correct"]


def test_multi_bar_rest_with_and_without_the_count(tmp_path):
    counted = attributes(extra="<measure-style><multiple-rest>3</multiple-rest></measure-style>") + rest(48, whole_bar=True)
    plain = attributes() + rest(48, whole_bar=True)
    truth = score(("Flute", [counted, rest(48, whole_bar=True), rest(48, whole_bar=True), four_quarters(first=" ")]))
    output = score(("Flute", [plain, rest(48, whole_bar=True), rest(48, whole_bar=True), four_quarters(first=" ")]))
    fig = compare(tmp_path, truth, output)
    assert accuracy(fig) == 1 and fig["structure"]["correct"]
    assert fig["diagnostics"]["rests"] == {"matched": 3, "of": 3}


def test_missed_barline_costs_no_note_errors(tmp_path):
    bars = [four_quarters(), four_quarters("G4 A4 B4 C5", first=" "), four_quarters("D5 E5 F5 G5", first=" ")]
    truth = score(("Flute", bars))
    output = score(("Flute", [bars[0], bars[1] + bars[2]]))
    fig = compare(tmp_path, truth, output)
    assert accuracy(fig) == 1
    assert fig["structure"]["mismatches"] == ["The ground truth has 3 bars, the output has 2."]


def test_extra_barline_costs_no_note_errors(tmp_path):
    truth = score(("Flute", [four_quarters(), four_quarters("G4 A4 B4 C5", first=" ")]))
    output = score(("Flute", [four_quarters(), note("G4") + note("A4"), note("B4") + note("C5")]))
    fig = compare(tmp_path, truth, output)
    assert accuracy(fig) == 1 and len(fig["structure"]["mismatches"]) == 1


def test_piano_as_one_part_or_two_parts(tmp_path):
    truth = score(("Piano", [attributes(staves=2, clefs=("G2", "F4")) + four_quarters(first=" ") + backup(48)
                             + note("C3", 48, voice=5, staff=2)]))
    output = score(("Piano right", [four_quarters()]), ("Piano left", [attributes(clefs=("F4",)) + note("C3", 48)]))
    fig = compare(tmp_path, truth, output)
    assert accuracy(fig) == 1
    assert not fig["structure"]["correct"]
    assert "The ground truth has 1 parts, the output has 2." in fig["structure"]["mismatches"]


def test_unison_in_two_voices(tmp_path):
    # Two C4 quarters at the same onset; the output has one: 1 exact, 1 missing.
    truth = score(("Flute", [attributes() + note("C4", 48) + backup(48) + note("C4", 48, voice=2)]))
    output = score(("Flute", [attributes() + note("C4", 48)]))
    fig = compare(tmp_path, truth, output)
    assert (fig["notes"]["exact"], fig["notes"]["missing"]) == (1, 1)


def test_different_divisions_for_the_same_music(tmp_path):
    truth = score(("Flute", [four_quarters()]))
    output = score(("Flute", [attributes(divisions=2) + "".join(note(p, 2, typ="quarter") for p in "C4 D4 E4 F4".split())]))
    assert accuracy(compare(tmp_path, truth, output)) == 1


def test_empty_output_scores_zero(tmp_path):
    truth = score(("Flute", [four_quarters()]))
    output = score(("Flute", [attributes()]))
    fig = compare(tmp_path, truth, output)
    assert accuracy(fig) == 0 and fig["notes"]["missing"] == 4


# ------------------------------------------------------------------ decisions


def test_extra_notes_count_as_errors(tmp_path):
    # 4 notes right and 1 added: accuracy 4 / (4 + 1).
    truth = score(("Flute", [four_quarters()]))
    output = score(("Flute", [attributes() + note("C4") + note("A5", chord=True) + note("D4") + note("E4") + note("F4")]))
    fig = compare(tmp_path, truth, output)
    assert accuracy(fig) == Fraction(4, 5) and fig["notes"]["extra"] == 1


def test_spelling_counts_as_a_pitch_error(tmp_path):
    truth = score(("Flute", [four_quarters("C#4 D4 E4 F4")]))
    output = score(("Flute", [four_quarters("Db4 D4 E4 F4")]))
    fig = compare(tmp_path, truth, output)
    assert accuracy(fig) == Fraction(3, 4)
    assert fig["notes"]["wrong by kind"] == {"pitch": 1, "spelling only": 1}
    assert fig["diagnostics"]["sounding pitch"] == {"matched": 4, "of": 4}
    assert fig["errors"][0]["kind"] == "spelling error"


def test_onsets_are_strict_and_the_diagnostic_shows_the_cascade(tmp_path):
    # A missing dot on the first note moves the next two: 3 wrong, but pitch and duration of 2 still match.
    truth = score(("Flute", [attributes() + note("C4", 18) + note("D4", 6) + note("E4", 12) + note("F4", 12)]))
    output = score(("Flute", [attributes() + note("C4", 12) + note("D4", 6) + note("E4", 12) + note("F4", 12)]))
    fig = compare(tmp_path, truth, output)
    assert (fig["notes"]["exact"], fig["notes"]["wrong"]) == (0, 4)
    assert fig["diagnostics"]["pitch and duration"]["matched"] == 3


def test_voices_numbered_differently_and_chords_split_into_voices(tmp_path):
    truth = score(("Flute", [attributes() + note("C4", 48) + note("E4", 48, chord=True)]))
    output = score(("Flute", [attributes() + note("C4", 48, voice=2) + backup(48) + note("E4", 48, voice=3)]))
    fig = compare(tmp_path, truth, output)
    assert accuracy(fig) == 1
    assert fig["diagnostics"]["voice"]["right"] == 2   # both output voices map to the one ground-truth voice


# ------------------------------------------------------------------ markings, structure, flags


def test_dynamic_within_a_beat_is_found_further_is_missed(tmp_path):
    truth = score(("Flute", [attributes() + dynamic("p") + four_quarters(first=" "),
                             dynamic("f") + four_quarters("G4 A4 B4 C5", first=" ")]))
    output = score(("Flute", [attributes() + dynamic("p", offset=6) + four_quarters(first=" "),
                              dynamic("f", offset=24) + four_quarters("G4 A4 B4 C5", first=" ")]))
    fig = compare(tmp_path, truth, output)
    assert (fig["markings"]["dynamic"]["truth"], fig["markings"]["dynamic"]["found"]) == (2, 1)
    assert fig["markings"]["dynamic"]["missed"] == ["Bar 2, Flute, beat 1: dynamic f"]


def test_changed_time_signature_is_one_mismatch_in_words(tmp_path):
    truth = score(("Flute", [four_quarters()]))
    output = score(("Flute", [four_quarters(first=attributes(time="2/2"))]))
    fig = compare(tmp_path, truth, output)
    assert fig["structure"]["mismatches"] == [
        "Bar 1, Flute: the ground truth has a 4/4 time signature, the output has a 2/2 time signature."]


def test_flags_cover_errors_in_flagged_bars(tmp_path):
    # Errors in bars 1 and 3; bar 1 is flagged: 1 of 2 covered.
    truth = score(("Flute", [four_quarters(), four_quarters("G4 A4 B4 C5", first=" "), four_quarters("D5 E5 F5 G5", first=" ")]))
    output = score(("Flute", [four_quarters("C4 D4 E4 G4"), four_quarters("G4 A4 B4 C5", first=" "),
                              four_quarters("D5 E5 F5 A5", first=" ")]))
    fig = compare(tmp_path, truth, output, flags=[{"part": 1, "bar": 1}])
    assert fig["flags"] == {"errors": 2, "covered": 1, "bars flagged": 1, "bars": 3, "flagged bars with an error": 1}


def test_error_is_described_in_words(tmp_path):
    truth = score(("Piano", [attributes(staves=2, clefs=("G2", "F4")) + four_quarters("C4 D4 F#4 G4", first=" ")
                             + backup(48) + note("C3", 48, voice=5, staff=2)]))
    output = score(("Piano", [attributes(staves=2, clefs=("G2", "F4")) + four_quarters("C4 D4 G4 G4", first=" ")
                              + backup(48) + note("C3", 48, voice=5, staff=2)]))
    error = compare(tmp_path, truth, output)["errors"][0]
    assert f"{error['where']}: expected {error['expected']}, found {error['found']}" == \
        "Bar 1, Piano, right hand, beat 3: expected F sharp 4, quarter note, found G 4, quarter note"


# ------------------------------------------------------------------ test recognisers and the runner


def corpus_set(tmp_path, scores):
    """A tiny set folder with index.txt, as the corpus export writes it."""
    root = tmp_path / "set"
    lines = ["# status | id | job | font | pdf | ground-truth MusicXML or reason"]
    for i, xml in enumerate(scores):
        job = root / f"s{i}" / "musescore4-base"
        job.mkdir(parents=True)
        (job / "score.pdf").write_bytes(b"%PDF")
        (job / "score.musicxml").write_text(xml, encoding="utf-8")
        (job / "metadata.txt").write_text("engraver: MuseScore 4\nfont: Leland\nground truth: exact\n", encoding="utf-8")
        lines.append(f"pair | s{i} | musescore4-base | Leland | {job / 'score.pdf'} | {job / 'score.musicxml'}")
    lines.append("failure | s9 | lilypond | | | musicxml2ly timed out")
    (root / "index.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def long_score():
    bars = [attributes() + dynamic("p") + note("C4") + note("E4", chord=True) + note("D4") + note("E4") + note("F4")]
    for n in range(11):
        bars.append(dynamic("mf") + note("G4") + note("B4", chord=True) + note("A4") + note("B4") + note("C5"))
    return score(("Piano", bars))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_damaged_recogniser_scores_what_its_damage_implies(tmp_path, seed):
    truth = write(tmp_path, "truth.musicxml", long_score())
    expected = recognisers.damage(truth, tmp_path / "out", seed=seed)
    fig = metrics.compare(truth, tmp_path / "out" / "score.musicxml", tmp_path / "out" / "flags.json")
    n = fig["notes"]
    assert (n["missing"], n["extra"], n["wrong"]) == (expected["missing"], expected["extra"], expected["wrong"])
    assert n["wrong by kind"].get("spelling only", 0) == expected["spelling only"]
    assert len(fig["structure"]["mismatches"]) == expected["structure mismatches"] == 1
    assert fig["flags"]["covered"] == expected["covered"]
    assert fig["markings"]["dynamic"]["found"] == fig["markings"]["dynamic"]["truth"] - expected["dynamics removed"]


def test_runner_with_perfect_and_a_failing_recogniser(tmp_path):
    root = corpus_set(tmp_path, [long_score(), score(("Flute", [four_quarters()]))])
    log = ProgressLog("t", stream=io.StringIO())
    results, text = harness.run("development", "perfect", log, out_dir=tmp_path / "eval", workers=1,
                                with_musicdiff=False, set_root=root)
    assert len(results) == 2 and all(report.note_errors(r["notes"]) == 0 for r in results)
    assert "Summary: 2 files, note accuracy 100 percent" in text.read_text(encoding="utf-8")
    assert "1 failed exports in the index are skipped" in log.stream.getvalue()

    failing = 'python -c "import sys; sys.exit(3)"'
    results, text = harness.run("development", failing, log, out_dir=tmp_path / "eval2", workers=1,
                                with_musicdiff=False, set_root=root)
    assert all("exited with status 3" in r["failed"] for r in results)
    assert all(r["notes"]["exact"] == 0 and r["notes"]["missing"] == r["notes"]["truth"] for r in results)
    assert "Failed files (2)" in text.read_text(encoding="utf-8")


def test_unreadable_prediction_is_a_failed_file(tmp_path):
    root = corpus_set(tmp_path, [score(("Flute", [four_quarters()]))])
    predictions = tmp_path / "pred" / "s0" / "musescore4-base"
    predictions.mkdir(parents=True)
    (predictions / "score.musicxml").write_text("not xml", encoding="utf-8")
    log = ProgressLog("t", stream=io.StringIO())
    results, _ = harness.run("development", None, log, out_dir=tmp_path / "eval", predictions=tmp_path / "pred",
                             workers=1, with_musicdiff=False, set_root=root)
    assert "could not be read" in results[0]["failed"]


def test_percent_never_rounds_a_shortfall_up_to_100():
    assert report.percent(9999, 10000) == "99.9 percent"
    assert report.percent(5, 5) == "100 percent"
    assert report.percent(0, 0) == "no data"


def test_decimal_durations_and_divisions_are_read_exactly(tmp_path):
    # MusicXML allows decimals: 2.5 divisions per quarter, an eighth written as 1.25.
    bar = ("<attributes><divisions>2.5</divisions><time><beats>2</beats><beat-type>4</beat-type></time></attributes>"
           + note("C4", 12).replace("<duration>12</duration>", "<duration>2.5</duration>")
           + note("D4", 6).replace("<duration>6</duration>", "<duration>1.25</duration>")
           + note("E4", 6).replace("<duration>6</duration>", "<duration>1.25</duration>"))
    s = events.read(write(tmp_path, "d.musicxml", score(("Flute", [bar]))))
    assert [n.onset for n in s.notes] == [0, 1, Fraction(3, 2)]


def test_voice_numbers_are_local_to_each_output_part(tmp_path):
    # The ground truth has one piano part with a voice on each staff. The output
    # writes the two staves as two parts, each with its notes in voice 1.
    # These are two different voices, so the grouping is right: no voice errors.
    truth = score(("Piano", [attributes(staves=2, clefs=("G2", "F4")) + four_quarters(first=" ") + backup(48)
                             + "".join(note(p, voice=2, staff=2) for p in "C3 D3 E3 F3".split())]))
    output = score(("Piano right", [four_quarters()]),
                   ("Piano left", [attributes(clefs=("F4",)) + "".join(note(p) for p in "C3 D3 E3 F3".split())]))
    fig = compare(tmp_path, truth, output)
    assert accuracy(fig) == 1 and fig["diagnostics"]["voice"] == {"right": 8, "of": 8}


def test_one_wrong_note_in_a_run_of_identical_short_bars_does_not_shift_the_bars(tmp_path):
    # Found on the development set: two identical one-note bars, and the second
    # note's value is wrong. The bars must still pair one to one: 1 duration error,
    # no structural mismatch (an alignment cost in shares, not counts, joined bars here).
    def bars(last):
        return [attributes(time="2/4") + note("A4", 24), note("A4", 18) + note("D4", 6),
                note("E4", 6) + note("F#4", 6) + note("G4", 6) + note("A4", 6),
                note("B4", 24), note("B4", 24, typ=last), rest(24, whole_bar=True)]
    fig = compare(tmp_path, score(("Piano", bars("half"))), score(("Piano", bars("whole"))))
    assert fig["notes"]["wrong by kind"] == {"duration": 1}
    assert fig["structure"]["correct"]


def test_identical_notes_in_two_voices_pair_by_voice(tmp_path):
    # Found on the development set: the same note in voices 5 and 6, and the
    # output changes the voice-5 copy. The voice-6 copies must pair with each
    # other, so no voice error is invented.
    piano = attributes(staves=2, clefs=("G2", "F4"))
    def bar(first):
        return (piano + note("C5", 48) + backup(48) + note(first, 24, voice=5, staff=2) + note("C3", 24, voice=5, staff=2)
                + backup(48) + note("Ab3", 24, voice=6, staff=2) + note("F3", 24, voice=6, staff=2))
    fig = compare(tmp_path, score(("Piano", [bar("Ab3")])), score(("Piano", [bar("Ab4")])))
    assert fig["notes"]["wrong by kind"] == {"pitch": 1}
    assert fig["diagnostics"]["voice"] == {"right": 4, "of": 4}


def test_swapped_voice_numbers_with_a_unison_are_not_voice_errors(tmp_path):
    # Found on the development set: voices 1 and 2 swapped in the output, and both
    # voices end on the same B4. Whichever way the two B4s are paired, the
    # voices correspond, so there are no voice errors.
    def bar(upper, lower):
        return (attributes() + note("F4", 6, voice=upper) + note("G4", 6, voice=upper) + note("A4", 6, voice=upper)
                + note("B4", 30, voice=upper, typ="half", dots=0)
                + backup(48) + note("D4", 18, voice=lower) + note("B4", 30, voice=lower, typ="half", dots=0))
    fig = compare(tmp_path, score(("Alto", [bar(1, 2)])), score(("Alto", [bar(2, 1)])))
    assert accuracy(fig) == 1
    assert fig["diagnostics"]["voice"] == {"right": 6, "of": 6}


def test_swapped_voices_where_one_voice_has_two_copies_of_the_unison(tmp_path):
    # Found on the development set: B4 once in voice 1 and twice in voice 2
    # (a doubled note), voices swapped in the output. No voice errors.
    def bar(upper, lower):
        return (attributes() + note("F4", 6, voice=upper) + note("G4", 6, voice=upper) + note("A4", 6, voice=upper)
                + note("B4", 30, voice=upper, typ="half", dots=0)
                + backup(48) + rest(18, voice=lower) + note("B4", 30, voice=lower, typ="half", dots=0)
                + note("B4", 30, voice=lower, typ="half", dots=0, chord=True))
    fig = compare(tmp_path, score(("Alto", [bar(1, 2)])), score(("Alto", [bar(2, 1)])))
    assert accuracy(fig) == 1
    assert fig["diagnostics"]["voice"] == {"right": 6, "of": 6}


def test_a_real_voice_error_inside_a_unison_is_still_counted(tmp_path):
    # Two voices share a B4. In the output the lower voice's other note moves to
    # the upper voice: one voice error, and the unison must not hide it.
    def bar(d_voice):
        return (attributes() + note("F4", 18, voice=1) + note("B4", 30, voice=1, typ="half", dots=0)
                + backup(48) + note("D4", 18, voice=d_voice) + note("B4", 30, voice=2, typ="half", dots=0))
    fig = compare(tmp_path, score(("Alto", [bar(2)])), score(("Alto", [bar(1)])))
    assert fig["diagnostics"]["voice"] == {"right": 3, "of": 4}
