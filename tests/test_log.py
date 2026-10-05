import io
import re

from omr.log import ProgressLog

LINE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d (INFO|WARNING|ERROR) demo: .+$")


def make(tmp_path=None):
    stream = io.StringIO()
    path = tmp_path / "run.log" if tmp_path else None
    return ProgressLog("demo", path=path, stream=stream), stream


def test_each_event_is_one_plain_line():
    log, stream = make()
    log.info("Started.\nSecond  line")
    log.warning("Slow file")
    lines = stream.getvalue().splitlines()
    assert len(lines) == 2
    assert all(LINE.match(line) for line in lines)
    assert "Started. Second line" in lines[0]


def test_finish_returns_zero_without_errors():
    log, stream = make()
    log.warning("Odd")
    assert log.finish("3 files checked") == 0
    last = stream.getvalue().splitlines()[-1]
    assert "Summary: 3 files checked (succeeded, 0 error(s), 1 warning(s))." in last


def test_finish_returns_one_after_an_error():
    log, stream = make()
    log.error("Bad file")
    assert log.finish("1 file checked") == 1
    assert "failed, 1 error(s)" in stream.getvalue().splitlines()[-1]


def test_lines_are_also_written_to_the_file(tmp_path):
    log, stream = make(tmp_path)
    log.info("Hello")
    log.finish("done")
    assert (tmp_path / "run.log").read_text(encoding="utf-8").splitlines() == stream.getvalue().splitlines()
