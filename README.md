# OMR

A free, offline optical music recognition tool. It converts sheet music PDFs and images into accurate MusicXML and braille music, and reports in plain text where it is unsure. Licensed under AGPL-3.0.

The project is at Phase 0 (foundations). Nothing recognises music yet. The `omr` command exists, but its `inspect`, `evaluate` and `convert` subcommands print "not implemented yet".

Design documents are in `docs/`: `requirements.md`, `solution-design.md` and `plans/phase0.md`.

## Set-up on Windows

You need Python 3.14 (from python.org), Git, and an NVIDIA GPU driver if you want GPU training.

In PowerShell, from the repository folder:

1. Create the environment: `py -3.14 -m venv .venv`
2. Activate it: `.venv\Scripts\Activate.ps1`
3. Install PyTorch from the CUDA 13.0 wheel index: `pip install -r requirements-torch.txt --index-url https://download.pytorch.org/whl/cu130`
4. Install the other dependencies: `pip install -r requirements.txt`
5. Install the project itself: `pip install -e .`

## Check that it works

- Run the smoke test: `python scripts/smoke_test.py`. It lists each dependency as OK or FAILED, says whether PyTorch sees the GPU, and ends with a one-line summary.
- Run the tests: `pytest`

## Layout

- `src/omr`: the Python package and command-line entry point.
- `tests`: the test suite.
- `scripts`: development scripts.
- `docs`: requirements, design, plans and notes.
- `corpus`: generated and collected test scores. Not in Git.
- `models`: model weights. Not in Git; released separately.

## Contributing

See `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.
