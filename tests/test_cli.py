import pytest

from omr.cli import main


def test_convert_says_not_implemented(capsys):
    assert main(["convert"]) == 2
    assert "not implemented yet" in capsys.readouterr().out


def test_evaluate_needs_a_set_and_a_recogniser(capsys):
    assert main(["evaluate"]) == 2
    assert main(["evaluate", "--set", "regression"]) == 2


def test_symbols_reports_each_file_and_a_summary(capsys):
    pytest.importorskip("pymupdf")
    from pathlib import Path

    pdf = Path(__file__).parent / "data" / "inspect" / "lilypond.pdf"
    assert main(["symbols", str(pdf)]) == 0
    out = capsys.readouterr().out
    assert "0 glyphs or shapes unmapped" in out
    assert "Emmentaler table" in out
    assert out.strip().splitlines()[-1].startswith("Summary: 1 file read, 0 failed")


def test_symbols_reports_a_missing_file_as_failed(capsys):
    assert main(["symbols", "no-such-file.pdf"]) == 1
    assert "Failed:" in capsys.readouterr().out


def test_layout_reports_parts_bars_and_changes_in_words(capsys):
    pytest.importorskip("pymupdf")
    from pathlib import Path

    pdf = Path(__file__).parent / "data" / "inspect" / "ms4_leland.pdf"
    assert main(["layout", str(pdf)]) == 0
    out = capsys.readouterr().out
    assert "4 parts, 10 bars" in out
    assert "- Part 1 (Soprano): 1 staff." in out
    assert "Bar 1, part 1: treble clef." in out
