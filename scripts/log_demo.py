"""Show what a progress log looks like. Run: python scripts/log_demo.py"""

import sys

try:
    from omr.log import ProgressLog
except ModuleNotFoundError:
    sys.exit(
        "The omr package was not found. Activate the environment first: "
        r".venv\Scripts\Activate.ps1 (see README.md). Exit status 1."
    )


def main():
    log = ProgressLog("demo")
    log.info("Started.")
    log.warning("Odd file found.")
    return log.finish("2 files checked")


if __name__ == "__main__":
    sys.exit(main())
