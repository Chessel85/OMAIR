"""Run independent jobs on several processor cores at once.

The owner's laptop has 4 cores (8 threads). Heavy jobs gain little from the
second thread on each core, and the chip slows down when hot, so the default is
3 workers, which leaves the machine usable during a batch. Results come back to
the main process, which alone writes the progress log, so log lines are never
mixed. With one worker the jobs run in the main process, with no pool, which
keeps tracebacks and debugging simple.
"""

import concurrent.futures as cf
import contextlib
import os

DEFAULT_WORKERS = 3


def max_workers():
    """The number of logical processors, the most workers it makes sense to ask for."""
    return os.cpu_count() or 1


def check_workers(workers):
    """Return workers if it is a usable count, else raise ValueError with a plain message."""
    if workers < 1:
        raise ValueError(f"the number of workers must be at least 1, not {workers}")
    if workers > max_workers():
        raise ValueError(f"this computer has {max_workers()} logical processors, so {workers} workers is too many")
    return workers


class _InProcess:
    """An executor that runs each job at once, in the main process."""

    def submit(self, function, *args, **kwargs):
        future = cf.Future()
        try:
            future.set_result(function(*args, **kwargs))
        except BaseException as error:  # handed back through the future, as a pool would
            future.set_exception(error)
        return future


@contextlib.contextmanager
def pool(workers):
    """An executor with `workers` processes, or one that runs in-process for 1."""
    check_workers(workers)
    if workers == 1:
        yield _InProcess()
        return
    executor = cf.ProcessPoolExecutor(max_workers=workers)
    try:
        yield executor
    except BaseException:
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    executor.shutdown(wait=True)


def finished(running, block):
    """Remove and return the finished items of `running` (a dict of future to
    job details), as (future, details) pairs. With block true, wait until at
    least one has finished."""
    if not running:
        return []
    if block:
        done, _ = cf.wait(running, return_when=cf.FIRST_COMPLETED)
    else:
        done = [f for f in running if f.done()]
    return [(f, running.pop(f)) for f in done]
