"""Tests for the sequence reader's helpers (Stage 2.6) that need neither homr nor the GPU."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import torch

from omr.raster import sequence


def symbol(rhythm, pitch="_"):
    return SimpleNamespace(rhythm=rhythm, pitch=pitch, lift="_", articulation="_", slur="_", position="upper")


def test_edit_distance_counts_changes_additions_and_removals():
    assert sequence.edit_distance("abc", "abc") == 0
    assert sequence.edit_distance("abc", "abd") == 1
    assert sequence.edit_distance("abc", "ab") == 1
    assert sequence.edit_distance("", "abc") == 3


def test_symbol_errors_compare_every_branch():
    truth = [symbol("clef_G2"), symbol("note_4", "C4"), symbol("barline")]
    assert sequence.symbol_errors(truth, truth) == 0
    assert sequence.symbol_errors([symbol("clef_G2"), symbol("note_4", "D4"), symbol("barline")], truth) == 1
    assert sequence.symbol_errors(truth[:2], truth) == 1


def test_collate_cuts_the_batch_to_its_longest_unit():
    def unit(length):
        mask = torch.zeros(608, dtype=torch.bool)
        mask[:length] = True
        item = {k: torch.zeros(608, dtype=torch.long)
                for k in ("rhythms", "pitchs", "lifts", "articulations", "slurs", "positions")}
        return {"inputs": torch.zeros(1, 256, 1280), **item, "mask": mask}

    batch = sequence.collate([unit(5), unit(9)])
    assert batch["rhythms"].shape == (2, 9)
    assert batch["mask"].shape == (2, 9)
    assert batch["inputs"].shape == (2, 1, 256, 1280)


def test_sample_is_fixed_and_sorted():
    entries = [(f"{i}.png", f"{i}.tokens") for i in range(100)]
    assert sequence.sample(entries, 10) == sequence.sample(entries, 10)
    assert sequence.sample(entries, 10) == sorted(sequence.sample(entries, 10))
    assert len(sequence.sample(entries, 500)) == 100


def test_learning_rate_warms_up_then_falls_to_nothing():
    path = Path(__file__).parent.parent / "scripts" / "train_sequence.py"
    spec = importlib.util.spec_from_file_location("train_sequence", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    peak, total = 3e-5, 10000
    assert script.learning_rate(0, total, peak) < peak / 100
    assert abs(script.learning_rate(script.WARMUP - 1, total, peak) - peak) < 1e-12
    assert script.learning_rate(total // 2, total, peak) < peak
    assert script.learning_rate(total, total, peak) < 1e-12
