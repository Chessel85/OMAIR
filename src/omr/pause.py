"""Pausing long runs by hand: continue.txt in the repository's folder.

While the file says "yes", a run goes on; otherwise it waits where it is and
carries on when the file says "yes" again. Training (scripts/train_detector.py),
the detector check (scripts/check_detector.py), the detection pass
(scripts/detect_pages.py) and `omr evaluate --pausable` look at it.
"""

import time

from omr import paths

CONTROL = paths.REPO_ROOT / "continue.txt"
WAIT = 30   # seconds between looks while paused


def may_continue(control=CONTROL):
    try:
        return control.read_text(encoding="utf-8").strip().lower() == "yes"
    except OSError:
        return False


def make_control(control=CONTROL):
    """Make the file, saying "yes", if there is none."""
    if not control.is_file():
        control.write_text("yes\n", encoding="utf-8")


def wait_while_paused(log, control=CONTROL, wait=WAIT):
    """Hold the run while the file does not say "yes"."""
    if may_continue(control):
        return
    log.info(f"paused: {control} does not say yes. Write yes in it to carry on.")
    paused = time.time()
    while not may_continue(control):
        time.sleep(wait)
    log.info(f"carrying on after {(time.time() - paused) / 60:.0f} minutes paused.")
