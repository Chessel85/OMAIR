import pytest

from omr.cli import main


def test_convert_says_not_implemented(capsys):
    assert main(["convert"]) == 2
    assert "not implemented yet" in capsys.readouterr().out


def test_evaluate_needs_a_set_and_a_recogniser(capsys):
    assert main(["evaluate"]) == 2
    assert main(["evaluate", "--set", "regression"]) == 2
