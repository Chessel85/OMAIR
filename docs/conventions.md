# Development conventions

These conventions meet AX-2 and AX-3. They exist so that a blind developer using NVDA can set up, test, run and read the results of everything in this project without a GUI. They apply to every script, command and document, including those written by Claude.

## Output

- All tool output is plain text. No ASCII art, no progress bars that redraw a line, no colour-only signals, and no tables where a list would do.
- Locations are given in words, for example "Piece 12, bar 14, right hand", never as coordinates or a picture.
- Every message says what happened and, for a failure, what to do next.
- Reports are written as headings and lists, in Markdown or plain text.

## Long-running jobs

- A job that takes more than a few seconds writes a progress log, one line per event, to the screen and to a file under `logs/` (git-ignored).
- Each line starts with the date, the time, a level word (INFO, WARNING or ERROR) and the name of the job, so that a screen reader reads the useful part first after the stamp.
- Jobs report a failure on one item and carry on with the rest, where that makes sense. Each failure is logged with its reason.
- Jobs that may be interrupted are resumable.
- Jobs made of many independent items (exports, evaluating many files) run them on several processor cores with `omr.parallel`, and take a `--workers N` option (default 3; 1 runs the items one at a time, which is easiest for debugging). Only the main process writes the log, so lines may finish out of order, and each line names its item.

## Exit status

- Every command ends with a one-line summary that starts with "Summary:" and says how many items were done, how many failed and how many warnings were raised.
- Exit status 0 means success. 1 means one or more failures. 2 means the command is not implemented or was used wrongly.

## Shared logging helper

Scripts use `omr.log.ProgressLog`, so the format is the same everywhere:

- `log = ProgressLog("job-name", path="logs/job-name.log")`
- `log.info("...")`, `log.warning("...")` and `log.error("...")` each write one line.
- `return log.finish("12 files converted")` writes the closing summary and returns the exit status.

## No GUI in the workflow

- Setting up, testing, evaluating and reading results must all work from a terminal.
- A step that needs a GUI is a defect in the workflow. Record it in `docs/plans/phase0-progress.md` and look for a command-line route.
- Where a tool has no command line (for example Dorico SE), it is parked or replaced, not worked around with a GUI step.

## Continuous integration

- `.github/workflows/tests.yml` runs the tests on Windows and Linux for every push and pull request.
- A failed run is read from the job log, which is plain text. Run `pytest` locally first.
