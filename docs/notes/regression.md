# Regression set and automatic runs (Stage 7, DEV-2)

## What it is

- `regression/` in the repository holds the fixed regression set: 43 scores, 256 PDF and MusicXML pairs, 32.5 MB. It is a copy of `generated/regression` on the corpus drive, made by `scripts/make_regression_snapshot.py`, because CI cannot reach that drive. All the scores are by composers on the public-domain list (C-4). The size is far below GitHub's limits (100 MB for one file, and the repository should stay under 1 GB).
- `regression/index.txt` lists every pair, with paths relative to the index, so `omr evaluate --set regression --set-root regression ...` works on any machine. Two LilyPond failures are listed as failures and skipped, as on the corpus drive.
- `regression/baseline.txt` is the recorded result, in plain text, one line per figure: `recogniser | figure | value`. Because it is plain text, a change in accuracy shows up in an ordinary `git diff`.

## What the check does

`python scripts/check_regression.py` runs the harness over the repository's set with each stand-in recogniser (`perfect`, and `damaged` with its fixed seed), works out the figures, and compares them with the baseline. It takes about one minute.

- The figures are: files evaluated and failed, note accuracy (overall and by engraver), files structurally correct, recall of dynamics and hairpins, and the share of note errors in flagged bars.
- It fails, with exit status 1, if a percentage is worse than the baseline by more than the margin (0.1 points by default, `--margin`), if more files fail or the harness has errors, or if the number of files changes.
- A figure that is better does not fail. The check says so, so that the gain can be recorded.
- Until a real recogniser exists, the stand-ins stand for it. The `perfect` baseline guards the harness and the set; the `damaged` baseline guards the metric code, because its figures are fixed by the damage. When Stage 9 gives a real recogniser, add it with `--recogniser "COMMAND" --update` and its figures join the baseline.
- CI runs the check as the job "Regression set" in `.github/workflows/tests.yml`, on every push and pull request. The ordinary tests (`tests/test_regression.py`) also check the comparison logic and the whole check on a two-score copy.

## Updating the baseline on purpose

Do this only when a change is meant to alter the figures (a better recogniser, a corrected metric, a changed set).

1. Run `python scripts/check_regression.py` and read why it fails or what is better.
2. If the change is intended, run `python scripts/check_regression.py --update`. It rewrites only the recognisers it ran, so `--recogniser NAME --update` leaves the others alone.
3. Look at `git diff regression/baseline.txt`. Every changed line should be one you expected.
4. Commit the baseline in the same commit as the change that caused it, and say why in the message.

If the set itself changes (scores added or removed, after the composer list is extended), regenerate it on the corpus drive, run `python scripts/make_regression_snapshot.py --replace`, and then update the baseline. The check fails on a changed number of files until you do.
