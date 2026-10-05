# Contributing

Thank you for helping. This project is developed so that it can be used and built without a GUI, and with a screen reader.

## Ground rules

- Licence: contributions are accepted under AGPL-3.0-or-later. Do not add code, data or model weights whose licence is incompatible. If unsure, ask first.
- Do not commit corpora, rendered pages or model weights. They are git-ignored.
- All tool output is plain text. Give locations in words, for example "Piece 12, bar 14, right hand".
- Every command ends with a clear exit status and a one-line summary.

## Workflow

1. Set up the environment by following `README.md`.
2. Make your change on a branch.
3. Run `pytest` and `python scripts/smoke_test.py`. Both must pass.
4. Open a pull request that says what changed and why.

## Reporting problems

Open an issue with what you did, what you expected and what happened. Paste plain-text output rather than screenshots.
