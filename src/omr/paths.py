"""Where the corpus lives, and checks that it is safe to write there.

The corpus can be large, so it may sit on a separate drive. Set the
environment variable OMR_CORPUS_DIR to its folder. If the variable is not set,
the corpus is the `corpus` folder in the repository, which is what CI and a
fresh clone use.
"""

import os
import shutil
from pathlib import Path

ENV_VAR = "OMR_CORPUS_DIR"
DEFAULT_MIN_FREE_GB = 100
REPO_ROOT = Path(__file__).resolve().parents[2]


class CorpusDirError(RuntimeError):
    """The corpus folder is missing or the drive is too full. The message says what to do."""


def corpus_dir():
    """Return the corpus folder. Does not check that it exists."""
    configured = os.environ.get(ENV_VAR)
    return Path(configured) if configured else REPO_ROOT / "corpus"


def require_corpus_dir():
    """Return the corpus folder, or raise CorpusDirError if it cannot be used.

    A folder named by OMR_CORPUS_DIR must already exist, so that an unplugged
    drive stops the job instead of silently writing somewhere else. The default
    folder in the repository is created if needed.
    """
    path = corpus_dir()
    if os.environ.get(ENV_VAR):
        if not path.is_dir():
            raise CorpusDirError(
                f"The corpus folder {path} does not exist. Is the drive connected? "
                f"It is set by the environment variable {ENV_VAR}."
            )
    else:
        path.mkdir(parents=True, exist_ok=True)
    return path


def free_gb(path):
    """Return the free space, in gigabytes, on the drive that holds path."""
    return shutil.disk_usage(path).free / 1024**3


def check_free_space(path, min_free_gb=DEFAULT_MIN_FREE_GB):
    """Raise CorpusDirError if the drive holding path has less than min_free_gb free."""
    free = free_gb(path)
    if free < min_free_gb:
        raise CorpusDirError(
            f"Only {free:.0f} GB free on the drive holding {path}. "
            f"The limit is {min_free_gb} GB. Free some space or lower the limit."
        )
    return free
