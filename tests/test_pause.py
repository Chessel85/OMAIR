"""Tests for pausing long runs with continue.txt (omr.pause)."""

import threading

from omr import pause


class Log:
    def __init__(self):
        self.lines = []

    def info(self, text):
        self.lines.append(text)


def test_only_yes_lets_a_run_go_on(tmp_path):
    control = tmp_path / "continue.txt"
    assert not pause.may_continue(control)        # no file
    control.write_text("no\n", encoding="utf-8")
    assert not pause.may_continue(control)
    control.write_text(" Yes \n", encoding="utf-8")
    assert pause.may_continue(control)


def test_make_control_writes_yes_but_keeps_an_existing_file(tmp_path):
    control = tmp_path / "continue.txt"
    pause.make_control(control)
    assert pause.may_continue(control)
    control.write_text("no\n", encoding="utf-8")
    pause.make_control(control)
    assert not pause.may_continue(control)


def test_a_paused_run_waits_until_the_file_says_yes(tmp_path):
    control = tmp_path / "continue.txt"
    control.write_text("no\n", encoding="utf-8")
    log = Log()
    waiting = threading.Thread(target=pause.wait_while_paused, args=(log, control, 0.01))
    waiting.start()
    waiting.join(0.1)
    assert waiting.is_alive()
    control.write_text("yes\n", encoding="utf-8")
    waiting.join(5)
    assert not waiting.is_alive()
    assert log.lines[0].startswith("paused") and log.lines[1].startswith("carrying on")
