# OMR

A free, offline optical music recognition tool. It converts sheet music PDFs and images into accurate MusicXML and braille music, and reports in plain text where it is unsure. Licensed under AGPL-3.0.

Phase 1 (vector PDFs) is closed, and the project is in Phase 2 (clean page images). For vector PDFs it names the symbols of a vector PDF and reads its structure, its notes (pitch, rhythm, voices, ties, grace notes) and its text and markings (title and composer, lyrics, chord symbols, tempo and expression text, dynamics, hairpins, articulations, slurs, fingering), and flags the bars that may be wrong, but does not yet write MusicXML. `scripts/check_notes.py`, `scripts/check_markings.py` and `scripts/check_flags.py` measure what it reads and flags against the ground truth. For page images (`src/omr/raster`) it finds the staff lines, barlines, stems, beams and curves, finds the symbols with a detector, reads the text with OCR, and hands them to the same reader; `scripts/check_raster_lines.py`, `scripts/check_detector.py` and `scripts/check_ocr.py` check each part against the vector reading. The `omr` command has these subcommands:

- `omr inspect FILE`: says what kind of PDF each page is (vector music with font glyphs or outlines, a clean image, or a photo or scan) and which music font it uses.
- `omr symbols FILE`: names every music symbol in a vector PDF (from its music font, or by shape where the symbols are outlines) and counts any that cannot be named.
- `omr layout FILE`: reports the parts, systems and bars of a vector PDF, and its clef, key and time changes, repeats and endings, in words.
- `omr confidence FILE`: reads the notes of a vector PDF and reports, in words, the bars that may be wrong and why (the confidence report). With `--out FOLDER` it also writes the flag file the evaluation harness reads.
- `omr evaluate --set SET --recogniser NAME_OR_COMMAND`: runs a recogniser over a corpus set and reports its accuracy against the ground truth, in plain text. The metrics are defined in `docs/notes/evaluation-spec.md`.
- `omr convert FILE`: reads a vector PDF and writes MusicXML, braille (a placeholder until the braille code is chosen), the confidence report and the flag file, named after the PDF. `--out FOLDER` chooses where they go; `--musicxml`, `--braille`, `--report` and `--flags` name each file for a single PDF. Scanned pages and images are not read yet.

Development conventions, including the accessibility rules for output and logs, are in `docs/conventions.md`.

Design documents are in `docs/`: `requirements.md`, `solution-design.md`, and a plan and progress log for each phase in `docs/plans` (the current ones are `phase2.md` and `phase2-progress.md`). Specs for each part are in `docs/notes`.

The GitHub repository is called OMAIR (https://github.com/Chessel85/OMAIR). The Python package and command are called `omr`.

## Set-up on Windows

You need Python 3.14 (from python.org), Git, and an NVIDIA GPU driver if you want GPU training.

In PowerShell, from the repository folder:

1. Create the environment: `py -3.14 -m venv .venv`
2. Activate it: `.venv\Scripts\Activate.ps1`
3. Install PyTorch from the CUDA 13.0 wheel index: `pip install -r requirements-torch.txt --index-url https://download.pytorch.org/whl/cu130`
4. Install the other dependencies: `pip install -r requirements.txt`
5. Install the project itself: `pip install -e .`

Every new terminal window needs step 2 again before you run `python`, `pytest` or `omr`. When the environment is active, the prompt starts with `(.venv)`. If you see "No module named 'omr'", the environment is not active.

## Check that it works

- Run the smoke test: `python scripts/smoke_test.py`. It lists each dependency as OK or FAILED, says whether PyTorch sees the GPU, and ends with a one-line summary.
- Check the external tools: `python scripts/check_environment.py`. It lists MuseScore, LilyPond, Java and the other tools as FOUND or MISSING with their paths, and ends with a one-line summary. Working command lines are in `docs/notes/tool-commands.md`.
- Run the tests: `pytest`

## Layout

- `src/omr`: the Python package and command-line entry point.
- `tests`: the test suite.
- `scripts`: development scripts.
- `docs`: requirements, design, plans and notes.
- `corpus`: the default location of generated and collected test scores. Not in Git. See the next section for putting it on another drive.
- `models`: model weights. Not in Git; released separately. The OCR model for page images goes in `models/ocr/latin_PP-OCRv5_rec_mobile.onnx` (from RapidOCR's model list on ModelScope, RapidAI/RapidOCR v3.10.0, `onnx/PP-OCRv5/rec/`), or set `OMR_OCR_MODEL` to its file. The symbol detector's weights are named by `OMR_DETECTOR`.

## Where the corpus lives

The corpus can take a lot of disk space. Set the environment variable `OMR_CORPUS_DIR` to the folder to use, for example in PowerShell: `[Environment]::SetEnvironmentVariable('OMR_CORPUS_DIR','E:\OMAIRCorpus','User')`. Open a new terminal afterwards. If the variable is not set, the `corpus` folder in the repository is used. If the variable is set and the folder does not exist, for example because the drive is unplugged, scripts stop with a message instead of writing somewhere else. Scripts also stop if the drive has less than 100 GB free. The code is in `src/omr/paths.py`.

## Contributing

See `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.
