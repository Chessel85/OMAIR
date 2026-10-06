"""The regression check (Stage 7): comparing figures, and the whole check on a small set."""

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

from omr import paths
from omr.evaluate import harness

SCRIPT = paths.REPO_ROOT / "scripts" / "check_regression.py"
spec = importlib.util.spec_from_file_location("check_regression", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_repository_set_and_baseline_agree():
    pairs, failures = harness.read_pairs("regression", check.SET_ROOT)
    assert len(pairs) == 256 and failures == 2
    assert all(p.pdf.is_file() and p.truth.is_file() for p in pairs)
    baseline = check.read_baseline(check.BASELINE)
    assert set(baseline) == {"perfect", "damaged"}
    for figures in baseline.values():
        assert figures["files evaluated"] == len(pairs)
    assert baseline["perfect"]["note accuracy"] == 100.0


def test_compare_passes_equal_and_small_changes():
    base = {"files evaluated": 5, "files failed": 0, "note accuracy": 98.0}
    assert check.compare("r", base, dict(base), 0.1) == ([], [])
    worse, better = check.compare("r", base, {**base, "note accuracy": 97.95}, 0.1)
    assert worse == [] and better == []


def test_compare_flags_worse_and_reports_better():
    base = {"files evaluated": 5, "files failed": 0, "note accuracy": 98.0}
    worse, _ = check.compare("r", base, {**base, "note accuracy": 97.0}, 0.1)
    assert len(worse) == 1 and "note accuracy fell from 98 to 97" in worse[0]
    worse, _ = check.compare("r", base, {**base, "files failed": 1}, 0.1)
    assert len(worse) == 1 and "files failed rose" in worse[0]
    worse, _ = check.compare("r", base, {**base, "files evaluated": 4}, 0.1)
    assert len(worse) == 1 and "set has changed" in worse[0]
    worse, better = check.compare("r", base, {**base, "note accuracy": 99.0}, 0.1)
    assert worse == [] and len(better) == 1


def test_compare_flags_figures_with_no_baseline_or_value():
    base = {"note accuracy": 98.0}
    assert check.compare("r", base, {"note accuracy": 98.0, "new figure": 1.0}, 0.1)[0]
    assert check.compare("r", base, {"note accuracy": None}, 0.1)[0]


def test_baseline_round_trips(tmp_path):
    data = {"perfect": {"note accuracy": 100.0, "note errors in flagged bars": None}}
    check.write_baseline(tmp_path / "b.txt", data)
    assert check.read_baseline(tmp_path / "b.txt") == data


@pytest.fixture
def small_set(tmp_path, monkeypatch):
    """Two scores of the real regression set, with their own baseline."""
    root = tmp_path / "set"
    lines = (check.SET_ROOT / "index.txt").read_text(encoding="utf-8").splitlines()
    ids = []
    for line in lines:
        if line.startswith("pair") and line.split(" | ")[1] not in ids:
            ids.append(line.split(" | ")[1])
    keep = ids[:2]
    for score in keep:
        shutil.copytree(check.SET_ROOT / score, root / score)
    kept = [l for l in lines if l.startswith("#") or l.split(" | ")[1] in keep]
    (root / "index.txt").write_text("\n".join(kept) + "\n", encoding="utf-8")
    monkeypatch.setattr(check, "SET_ROOT", root)
    monkeypatch.setattr(check, "BASELINE", root / "baseline.txt")
    return root


def run_check(*args):
    return check.main(["--workers", "1", *args])


def test_worse_recogniser_fails_and_same_one_passes(small_set, monkeypatch):
    assert run_check("--recogniser", "perfect", "--update") == 0
    assert run_check("--recogniser", "perfect") == 0
    # A change that makes the stand-in recogniser worse: "perfect" now damages the notes.
    monkeypatch.setitem(harness.BUILT_IN, "perfect", harness.BUILT_IN["damaged"])
    assert run_check("--recogniser", "perfect") == 1


def test_missing_baseline_is_an_error(small_set):
    assert run_check("--recogniser", "perfect") == 1
