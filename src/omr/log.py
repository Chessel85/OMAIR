"""Shared progress log for scripts and long-running jobs.

Every line is plain text, one event per line, with a time stamp and a level
word at the start, so that it reads the same way in a terminal, a log file and
NVDA. The last line of a run is always a one-line summary (see `finish`).
"""

import sys
import time

LEVELS = ("INFO", "WARNING", "ERROR")


class ProgressLog:
    """Write one plain-text line per event to the screen and, optionally, a file."""

    def __init__(self, name, path=None, stream=None):
        self.name = name
        self.stream = stream if stream is not None else sys.stdout
        self.file = open(path, "a", encoding="utf-8") if path else None
        self.warnings = 0
        self.errors = 0

    def _write(self, level, message):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"{stamp} {level} {self.name}: {' '.join(str(message).split())}"
        print(line, file=self.stream, flush=True)
        if self.file:
            print(line, file=self.file, flush=True)

    def info(self, message):
        self._write("INFO", message)

    def warning(self, message):
        self.warnings += 1
        self._write("WARNING", message)

    def error(self, message):
        self.errors += 1
        self._write("ERROR", message)

    def finish(self, summary):
        """Write the closing summary line and return the exit status (0 or 1)."""
        status = 1 if self.errors else 0
        outcome = "failed" if status else "succeeded"
        self._write(
            "INFO",
            f"Summary: {summary} ({outcome}, {self.errors} error(s), {self.warnings} warning(s)).",
        )
        self.close()
        return status

    def close(self):
        if self.file:
            self.file.close()
            self.file = None
