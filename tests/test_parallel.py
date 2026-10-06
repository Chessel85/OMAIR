"""Tests for the shared worker pool."""

import os

import pytest

from omr import parallel


@pytest.mark.parametrize("workers", [1, 2])
def test_pool_returns_every_result(workers):
    with parallel.pool(workers) as pool:
        running = {pool.submit(pow, n, 2): n for n in range(6)}
        results = {}
        while running:
            for future, n in parallel.finished(running, block=True):
                results[n] = future.result()
    assert results == {n: n * n for n in range(6)}


def test_one_worker_runs_in_this_process_and_hands_back_errors():
    with parallel.pool(1) as pool:
        assert pool.submit(os.getpid).result() == os.getpid()
        future = pool.submit(int, "not a number")
    with pytest.raises(ValueError):
        future.result()


def test_finished_without_blocking_returns_nothing_for_an_empty_dict():
    assert parallel.finished({}, block=False) == []
    assert parallel.finished({}, block=True) == []


def test_worker_count_is_checked():
    with pytest.raises(ValueError, match="at least 1"):
        parallel.check_workers(0)
    with pytest.raises(ValueError, match="logical processors"):
        parallel.check_workers(parallel.max_workers() + 1)
    assert parallel.check_workers(1) == 1
