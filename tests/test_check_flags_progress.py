"""Tests for check_flags.py's progress lines and kept results (going on
after a run is stopped)."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_flags  # noqa: E402


def test_durations_read_as_words():
    assert check_flags.duration(20) == "under a minute"
    assert check_flags.duration(60) == "1 minute"
    assert check_flags.duration(3 * 3600 + 5 * 60) == "3 hours 5 minutes"
    assert check_flags.duration(7200) == "2 hours"


def test_the_progress_line_gives_the_count_the_time_and_the_end():
    now = time.mktime((2026, 11, 3, 10, 0, 0, 0, 0, -1))
    line = check_flags.progress_line(10, 100, "os-x", "musescore4-base", 125, 60, now)
    assert line.startswith("10 of 100 done. os-x musescore4-base took 2 minutes.")
    assert "About 1 hour 30 minutes left, ending about 11:30." in line
    early = check_flags.progress_line(1, 100, "os-x", "lilypond", 30, None, now)
    assert early.endswith("Too early to say when the run will end.")
    last = check_flags.progress_line(100, 100, "os-x", "lilypond", 30, 60, now)
    assert last == "100 of 100 done. os-x lilypond took under a minute."


def test_kept_results_are_read_back_and_a_line_cut_short_is_left_out(tmp_path):
    kept = check_flags.kept_file(tmp_path / "dev.json")
    assert kept.name == "dev.pairs.jsonl"
    whole = {"score": "a", "job": "lilypond", "result": {"places": [], "flags": [], "bars": 4}}
    kept.write_text(json.dumps(whole) + "\n" + '{"score": "b", "job": "lily', encoding="utf-8")
    assert check_flags.read_kept(kept) == {("a", "lilypond"): whole["result"]}
    assert check_flags.read_kept(tmp_path / "none.jsonl") == {}


def test_the_estimate_leaves_out_time_paused():
    now = [0.0]
    clock = check_flags._Clock(clock=lambda: now[0])
    clock.paused = 300.0
    clock.finished = 3
    now[0] = 900.0
    assert clock.rate(3) == 200.0
    clock.finished = 2
    assert clock.rate(3) is None


def test_a_run_nearly_done_says_under_a_minute_left():
    now = time.mktime((2026, 11, 3, 10, 0, 0, 0, 0, -1))
    line = check_flags.progress_line(99, 100, "os-x", "lilypond", 5, 10, now)
    assert line.endswith("Under a minute left, ending about 10:00.")
