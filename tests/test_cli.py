import pytest

from omr.cli import main


@pytest.mark.parametrize("command", ["evaluate", "convert"])
def test_stub_commands_say_not_implemented(command, capsys):
    assert main([command]) == 2
    assert "not implemented yet" in capsys.readouterr().out
