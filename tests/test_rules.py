"""Tests for Stage 1.5: the musical rules layer and the confidence flags
(omr.pdf.rules, omr confidence)."""

import json
from fractions import Fraction
from pathlib import Path

import pytest

from omr.evaluate import events, metrics
from omr.pdf import notation, rules

ROOT = Path(__file__).parent.parent
REGRESSION = ROOT / "regression"
F = Fraction


def _note(step, octave, alter=0, bar=0, onset=0, duration=1, part=0, staff=1, **extra):
    return events.Note(part, staff, "1", bar, F(onset), events.Pitch(step, F(alter), octave), F(duration),
                       "quarter", **extra)


def _score(notes, names=("Piano",), key=0, time="4/4", bars=2):
    score = events.Score(parts=[events.Part(n, 1) for n in names],
                         bars=[events.Bar(str(k + 1), 1, 1) for k in range(bars)],
                         bar_counts=[bars] * len(names))
    for p in range(len(names)):
        score.structure.append(events.Marking("key", str(key), p, None, 0, F(0)))
        score.structure.append(events.Marking("time", time, p, None, 0, F(0)))
    score.notes = notes
    return score


# ------------------------------------------------------------------ rules

def test_key_spelling_flags_notes_far_from_the_key():
    notes = [_note("F", 4, 1), _note("B", 4, -1, onset=1),       # usual chromatic notes in C major
             _note("D", 4, 1, bar=1)]                             # D sharp in A flat major
    assert rules.key_spelling(_score(notes[:2])) == []
    flags = rules.key_spelling(_score(notes[2:], key=-4))
    assert [(f.bar, f.rule) for f in flags] == [(1, "key and accidentals")]
    assert "D sharp 4 is unlikely in the key" in flags[0].reason
    assert rules.key_spelling(_score([_note("F", 4, 2)], key=5)) == []   # F double sharp in G sharp minor


def test_range_of_part_names():
    assert rules.range_of("Soprano") == rules.RANGES["soprano"]
    assert rules.range_of("Violin I") == rules.RANGES["violin"]
    assert rules.range_of("Bass Clarinet in B flat") == rules.RANGES["clarinet"]
    assert rules.range_of("Alto Saxophone") == rules.RANGES["saxophone"]
    assert rules.range_of("Piano") is None and rules.range_of("") is None


def test_instrument_range_flags_a_soprano_low_note():
    flags = rules.instrument_range(_score([_note("C", 4), _note("C", 3, bar=1)], names=("Soprano",)))
    assert [(f.bar, f.onset) for f in flags] == [(1, 0)]
    assert "C 3 is below the range of Soprano" in flags[0].reason


def test_ties_need_the_same_pitch_where_the_note_ends():
    good = [_note("C", 4, duration=4, tie_start=True), _note("C", 4, bar=1, tie_stop=True)]
    assert rules.ties(_score(good)) == []
    bad = [_note("C", 4, duration=4, tie_start=True), _note("D", 4, bar=1, tie_stop=True)]
    reasons = sorted(f.reason for f in rules.ties(_score(bad)))
    assert reasons == ["a tie from C 4 reaches no note of the same pitch",
                       "a tie to D 4 comes from no note of the same pitch"]


def test_slurs_that_do_not_close():
    notes = [_note("C", 4, slurs=(("start", 1),)), _note("D", 4, onset=1, slurs=(("stop", 1),)),
             _note("E", 4, onset=2, slurs=(("start", 1),))]
    flags = rules.slurs(_score(notes))
    assert [(f.reason, f.onset) for f in flags] == [("a slur starts and does not stop", 2)]


def test_bar_fullness_words():
    notes = [_note("C", 4, duration=4), _note("C", 4, bar=1, duration=3)]
    score = _score(notes, bars=3)
    score.notes.append(_note("C", 4, bar=2, duration=4))
    flags = rules.bar_fullness(score)
    assert [f.bar for f in flags] == [1]
    assert "stops short of the end of the bar: it lasts 3 quarter notes where the bar holds 4" in flags[0].reason


# ------------------------------------------------------- reader doubts

class _Event:
    def __init__(self, onset, duration, whole_bar=False):
        self.onset, self.duration, self.whole_bar = F(onset), F(duration), whole_bar


def test_rhythm_doubts():
    fine = [_Event(0, 1), _Event(1, 1), _Event(2, 2)]
    assert notation._rhythm_doubts(fine, F(4)) == []
    # a voice that stops early is not a doubt: engravers hide rests
    assert notation._rhythm_doubts([_Event(0, 1), _Event(1, 1)], F(4)) == []
    late = [_Event(0, 1), _Event(F(3, 2), 1)]
    assert notation._rhythm_doubts(late, F(4)) == [("a note starts where no note before it ends", F(3, 2)),
                                                   ("a note ends where no note follows it", 0)]
    over = [_Event(0, 2), _Event(2, 3)]
    assert notation._rhythm_doubts(over, F(4)) == [("a note runs past the end of the bar", 2)]


# ------------------------------------------------------------------ output

def test_bar_flags_join_reasons_and_flag_file_reads_back(tmp_path):
    flags = [rules.Flag(0, 1, 3, "rhythm", "a note starts where no note before it ends", F(1)),
             rules.Flag(0, 1, 3, "bar fullness", "voice 1 stops short"),
             rules.Flag(0, 1, 3, "rhythm", "a note starts where no note before it ends", F(1)),
             rules.Flag(1, None, 0, "ties", "a tie")]
    joined = rules.bar_flags(flags)
    assert [(b.part, b.bar, len(b.reasons)) for b in joined] == [(1, 0, 1), (0, 3, 2)]
    assert all(0 <= b.confidence <= 1 for b in joined)
    path = tmp_path / "flags.json"
    path.write_text(json.dumps(rules.flag_file(flags)), encoding="utf-8")
    assert sorted(metrics.read_flags(path)) == [(0, 3, 1), (1, 0, None)]
    assert rules.as_harness_flags(flags, rules={"ties"}) == [(1, 0, None)]


def test_report_lines_give_places_in_words():
    from omr import confidence_report

    score = _score([], names=("Violin",), time="6/8", bars=4)
    score.bars[2] = events.Bar("3", 2, 1)
    flags = [rules.Flag(0, 1, 2, "rhythm", "a note runs past the end of the bar", F(3, 2))]
    lines = confidence_report.report_lines("x.pdf", score, flags)
    assert lines[1] == "Summary: 4 bars, 3 high confidence, 1 flagged."
    assert lines[3] == "- Page 2, system 1, bar 3, Violin, beat 4: a note runs past the end of the bar."


# ------------------------------------------------------- end to end

@pytest.mark.parametrize("score_id,job", [("pdmx-kyKcYH1Z2cK9", "musescore4-base"),
                                          ("pdmx-4viYqFUrsJaX", "musescore4-base")])
def test_flags_cover_the_errors_of_regression_pairs(score_id, job):
    pytest.importorskip("pymupdf")
    from omr.pdf import structure

    folder = REGRESSION / score_id
    truth = events.read(folder / job / "score.musicxml")
    found, _ = structure.read_pdf(folder / job / "score.pdf", notes=True)
    figures = metrics.compare_scores(truth, found, rules.as_harness_flags(rules.check(found)))
    f = figures["flags"]
    assert f["covered"] >= 0.9 * f["errors"]
    assert f["bars flagged"] <= 0.75 * f["bars"]


def test_confidence_command_writes_flag_file(tmp_path, capsys):
    pytest.importorskip("pymupdf")
    from omr.cli import main

    pdf = REGRESSION / "pdmx-kyKcYH1Z2cK9" / "musescore4-base" / "score.pdf"
    assert main(["confidence", str(pdf), "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Summary: 1 file read, 0 failed." in out
    assert metrics.read_flags(tmp_path / "score" / "flags.json") is not None
    assert (tmp_path / "score" / "confidence.txt").read_text(encoding="utf-8").startswith("File: score.pdf")
