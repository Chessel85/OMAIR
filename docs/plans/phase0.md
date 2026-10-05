# Phase 0 Plan: Foundations

Version 0.1, 5 October 2026.

This plan breaks Phase 0 of the solution design (`solution-design.md`, section 6) into stages. Requirement IDs, such as DEV-1 or OP-3, refer to `requirements.md`. Like the solution design, it uses headings and lists only, so that it reads well with a screen reader.

Phase 0 covers about 2 to 3 weeks of effort. Nothing in it recognises music. Its job is to build the tools that measure everything later, and to settle the facts the later phases depend on.

## How to read the model recommendations

Each stage names a recommended model for the work, with a reason.

- **Opus** is recommended where the work is judgement-heavy: defining what "correct" means, designing something that Phase 1 will build on, interpreting results, or debugging problems with no obvious cause.
- **Sonnet** is recommended where the work is well specified and mostly mechanical: scaffolding, scripts, glue code, configuration, running tools and reporting what happened.
- Several stages are split, with Opus designing or reviewing and Sonnet implementing. A sensible pattern is to have Opus write a short specification into the repository first, then have Sonnet implement it and Opus review the result.
- If Sonnet is stuck on a stage after two or three attempts, escalate that piece to Opus instead of continuing.

## Phase 0 goal and gate

The gate, from the solution design, is that all four of these are true:

1. Baseline accuracy numbers for existing OMR tools are recorded.
2. The mix of PDF types and fonts in real-world files is known.
3. The OP-3 speed targets are confirmed (this closes OI-2).
4. Model sizes are fixed so that training fits on the laptop (C-7).

Phase 0 also delivers the requirements assigned to it: AX-3 (accessible development), DEV-1 (evaluation harness), DEV-2 (regression set) and DEV-4 (baselines).

## Stage 0: Prerequisites and environment check

**Recommended model: Sonnet.** This is a checklist, and the only judgement is in reading the results.

Owner actions, which Claude cannot do:

- Install Python 3.14 from python.org. The installed version is currently 3.13.3, and the design now specifies 3.14.
- Install Git, MuseScore 3, MuseScore 4, Dorico SE, LilyPond and a Java runtime (for Audiveris and FreeDots).
- Confirm that the free Dorico SE player limit does not stop it exporting the scores planned for the corpus.
- Create the GitHub account and the empty public repository, if not already done.

Claude actions:

- Write a script, `scripts/check_environment.py`, that reports in plain text which tools are found, their versions, and the path of each. It exits with a clear message for each missing item.
- Check that MuseScore 3 and 4 can run from the command line without opening a window, and record the exact command lines that work on this machine.
- Check that the NVIDIA driver reports CUDA 13.2 and that `nvidia-smi` works.

Done when: the script reports every required tool as found, and the working MuseScore command lines are recorded in `docs/notes/tool-commands.md`.

## Stage 1: Repository skeleton, licence and environment

**Recommended model: Sonnet.** Standard project scaffolding.

- Create the repository layout: source package `omr`, `tests`, `scripts`, `docs`, `corpus` (git-ignored, see C-4) and `models` (git-ignored, weights are released separately).
- Add `omr.paths`, the one place that decides where the corpus lives. The corpus folder is set by the environment variable `OMR_CORPUS_DIR`, and defaults to `corpus` in the repository so that CI and a fresh clone work. A configured folder must already exist, so an unplugged drive stops a job instead of silently filling the system drive. The module also provides a free-space check. Every script that reads or writes corpus data uses it. On the owner's machine the variable points at `E:\OMAIRCorpus`, on a separate 2 TB drive, because the system drive has limited free space.
- Add the AGPL-3.0 licence text, a README, a contributing guide and a code of conduct.
- Create the virtual environment with Python 3.14 and a pinned dependency file. Install PyTorch from the CUDA 13.0 wheel index, which has Python 3.14 Windows wheels. Install the other dependencies from PyPI: PyMuPDF, pikepdf, OpenCV, scikit-image, ONNX Runtime, Ultralytics, music21, musicdiff, Verovio and pytest.
- Write a smoke test that imports every dependency and reports in plain text whether PyTorch sees the GPU.
- Add the `.gitignore` entries for corpora, renders, model weights, logs and the environment.
- Set up the `omr` command-line entry point with empty `inspect`, `evaluate` and `convert` subcommands, each of which prints a clear "not implemented yet" message.

Done when: a fresh clone can be set up by following the README alone, the smoke test passes, and the corpus location and free-space checks have tests.

Risk to check here: if any dependency has no Python 3.14 wheel on Windows, record it and fall back to Python 3.13 for the whole project. Do not mix versions.

## Stage 2: Continuous integration and accessible development conventions

**Recommended model: Sonnet.** Well-documented configuration, with a small design element for the conventions.

Covers AX-3.

- Add a GitHub Actions workflow that runs the tests on Windows and Linux for every push and pull request.
- Write the conventions document, `docs/conventions.md`, covering:
  - all tool output is plain text, with locations given in words (AX-2);
  - long-running jobs write a plain-text progress log, one line per event, readable with NVDA;
  - every command exits with a clear status and a one-line summary at the end;
  - no step in the development workflow needs a GUI.
- Add a shared logging helper that all later scripts use, so the log format is the same everywhere.
- Ask the owner to try the full set-up and test workflow with NVDA, and record anything that is awkward. Fix those first.

Done when: CI is green, and the owner has confirmed the set-up, test and results-reading workflow works with NVDA.

## Stage 3: Licence register

**Recommended model: Sonnet to draft, owner to decide.** Collecting licence facts is mechanical. Anything unclear is a decision for the owner, and a legal reading is not something to automate.

Covers C-3.

- Create `docs/licence-register.md`, with one entry for each dependency, dataset and model: its name, version, licence, whether it is shipped or used only internally, and the source of the information.
- Pre-fill it from the solution design: PyMuPDF and Ultralytics (AGPL), music21 (BSD), Verovio (LGPL), Audiveris (AGPL, external process only), and the datasets PDMX, OpenScore, CPDL, Mutopia, DeepScores V2, GrandStaff and PrIMuS.
- Mark the non-commercial-only items (this is likely for some research weights, including possibly LEGATO and SMT) as "internal comparison only, never shipped".
- Add a test that fails if a dependency in the pinned file has no register entry.

Done when: every pinned dependency has an entry, and unclear licences are listed for the owner to resolve.

## Stage 4: PDF inspector (`omr inspect`)

**Recommended model: Opus for the design and the type-classification rules, Sonnet for the command-line wrapper and report formatting.**

Opus is recommended for the core because Phase 1 builds directly on this code, and because telling a font-glyph PDF from an outlined-glyph PDF from an image PDF involves judgement about messy real files.

- Opus writes a specification first: the four page types (A, B, C and D in the design), what evidence decides each one, and what the inspector reports for each page.
- The inspector reports, for each page, in plain text:
  - the page type and the reason for it;
  - the fonts in use, whether each is a known music font (SMuFL code points or a legacy font), and how many glyphs use it;
  - the number of vector lines and filled shapes, which indicates staff lines, stems and beams;
  - the number and size of embedded images;
  - for outlined glyphs, the number of distinct shapes found.
- Add a summary at the top of the report: pages, types found and the main fonts.
- Test it against the MuseScore, Dorico, LilyPond and Verovio exports from Stage 5, and against real files from Stage 8.
- Write a machine-readable output option (JSON) as well, so that Stage 8 can analyse many files automatically.

Done when: the inspector classifies the generated corpus correctly (the engraver is known for those files, so the right answer is known), and its output reads well with a screen reader.

## Stage 5: Corpus generator

**Recommended model: Opus for the sampling design, Sonnet for the export scripts.** Opus for debugging any engraver that fails in a way Sonnet cannot sort out.

This is the largest stage.

Sampling design, with Opus:

- Choose the sampling rules for selecting scores from PDMX and OpenScore, so that the development set (about 300 scores) and the regression set (about 50 scores) cover the genres and textures in REC-10: classical, popular, jazz, folk, sacred, choral and educational; single line, voice with piano, piano, choir, chamber and small ensembles.
- Choose the filters: only public-domain or freely licensed scores (C-4), a size limit so that exports are quick, and exclusion of scores that MusicXML tools cannot round-trip.
- Fix the split between the development, regression and training pools, so that no score appears in more than one. Record the random seed so that the selection can be reproduced.
- Write the selection rules to `docs/notes/corpus-sampling.md`.

Implementation, with Sonnet:

- Download PDMX metadata and OpenScore, and apply the selection.
- Write one exporter for each engraver, all behind a common interface:
  - MuseScore 4 and MuseScore 3 through the command line, in several fonts and styles (Leland, Bravura, Emmentaler, Gonville, Petaluma, MuseJazz, and the SMuFL Finale fonts);
  - Dorico SE;
  - LilyPond, through `musicxml2ly`;
  - Verovio, through its Python bindings.
- Each exporter produces a matching PDF and MusicXML pair, and a small metadata file recording the source score, engraver, version, font and style.
- Handle failures without stopping the run. Record each failure and its reason in the log, and retry only where it makes sense.
- Make the generator resumable, so that an overnight batch that is interrupted carries on where it stopped.
- Write the corpus under the corpus folder from `omr.paths` (`OMR_CORPUS_DIR`, which is `E:\OMAIRCorpus` on the owner's machine), with a text index file that lists every pair. Downloads (the PDMX archive and OpenScore) and scratch exports go there too, never to the system drive.
- Before starting, and again between scscores, check that the corpus folder exists and that the drive has more than a set margin free (100 GB by default). If not, stop cleanly with a plain-text message, so that an interrupted run can be resumed.
- Report the corpus size in the log at the end of each run.

Notes for the owner: Dorico SE may have no usable command-line export. If so, Dorico files may need a semi-manual step, and the plan should drop to a smaller Dorico sample rather than block the stage.

Done when: the corpus folder is on the separate drive, the development set and the regression set exist, each with exports from at least MuseScore 4, MuseScore 3, LilyPond and Verovio, and the index lists every pair and every failure.

## Stage 6: Evaluation harness (`omr evaluate`)

**Recommended model: Opus for the metric definitions and the matching logic, Sonnet for the data plumbing and report formatting.**

Covers DEV-1 and the metrics for ACC-1 to ACC-6.

Opus designs and specifies:

- Note matching. How a recognised note is paired with a ground-truth note, when bars differ in length, when voices are ordered differently, and when a chord is split or merged. This is the part that is easy to get wrong, and an error here would corrupt every later accuracy number.
- Note accuracy exactly as defined in the requirements: the share of notes whose pitch, onset and duration all match.
- Structural correctness: parts, number of bars, clefs, key and time signatures, and repeats.
- Performance-marking recall (ACC-6).
- Error-flagging recall (ACC-4): the share of real note errors that fall in bars the confidence report flags. This needs a defined format for the report that the harness can read.
- What counts as a bar for the purposes of repeated and pickup bars.
- How `musicdiff`, OMR-NED and TEDn are used alongside the project metrics, so that results can be compared with published work.

Sonnet implements:

- The harness that runs the pipeline (or a stand-in command) over the corpus and compares each output with its ground truth.
- Per-file and overall results, broken down by engraver, font, genre and texture.
- Plain-text and JSON reports, with locations in words (for example "Piece 12, bar 14, right hand").
- A test suite with hand-made pairs where the correct metric values are known in advance, including awkward cases: tuplets, ties across barlines, grace notes, and cross-staff notes.
- A stand-in "perfect" recogniser (returns the ground truth) and a "damaged" one (adds known errors), so the harness itself is tested: the first must score 100 percent, and the second must score what the known damage implies.

Done when: the perfect recogniser scores 100 percent, the damaged recogniser scores the expected values, and Opus has reviewed the metric code against the definitions in the requirements.

## Stage 7: Regression set and automatic runs

**Recommended model: Sonnet.** This applies the harness from Stage 6 to a fixed set.

Covers DEV-2.

- Select the regression set of about 50 scores from the corpus, public-domain only, small enough to be stored in the repository or fetched by a script. Check the sizes against GitHub limits. The regression set is copied into the repository (not left on the corpus drive), because CI has no access to the owner's corpus drive.
- Add a GitHub Actions job that runs the harness on the regression set on every change, and fails if accuracy drops below the last recorded baseline by more than a set margin.
- Store the current results in a plain-text file in the repository, so changes in accuracy show up in ordinary diffs.
- Write down how to update the baseline deliberately.

Done when: a change that makes the stand-in recogniser worse makes CI fail, and a change that does not affect it passes.

## Stage 8: Real-world files and the PDF-type survey

**Recommended model: Sonnet to collect and run, Opus to analyse.**

Covers part of the Phase 0 gate (the mix of PDF types and fonts) and risks 1 and 2 in the solution design.

- Write a polite, rate-limited collection script for CPDL (output goes to the corpus folder from `omr.paths`), and a list of IMSLP files chosen by hand with the owner. Check each site's terms, and collect only what is public domain or freely licensed (C-4).
- For CPDL editions, keep the PDF together with any MusicXML or source file (Sibelius, Finale), because those pairs are real Sibelius and Finale ground truth (C-6).
- Run `omr inspect` over everything, using the JSON output.
- Opus analyses the result: the share of each page type, the fonts found, which fonts need mapping tables, how many files have outlined glyphs, and which files are unusual enough to cause trouble. It writes the findings as plain text in `docs/notes/pdf-survey.md`.
- Add anything surprising to the risk list, and decide whether the Phase 1 plan needs to change.

Done when: at least a few hundred real PDFs have been inspected, the survey is written up, and the list of font mapping tables needed for Phase 1 is in order of how many files each would cover.

## Stage 9: Baselines (DEV-4)

**Recommended model: Sonnet to install and run the tools, Opus to interpret the numbers.**

Covers DEV-4.

- Install Audiveris and homr, and install LEGATO if its licence allows internal use (Stage 3 records this).
- Write a thin wrapper for each tool behind the common engine interface, so the harness can run them like any other recogniser.
- Run each tool on the development set, and on the real-world pairs from Stage 8. Record timings for every file, on the CPU alone (OP-2).
- LEGATO is tested only on a small sample first, to see whether its CPU speed is usable. If a page takes many minutes, run it on a small subset and note that it is a development baseline only.
- Opus analyses where each tool fails, by engraver, font, genre and texture, and writes `docs/notes/baselines.md`. The aim is to learn where the project can win, not just to record numbers.

Done when: baseline accuracy and timing figures for each tool are recorded, broken down in the same way as the harness reports.

## Stage 10: Training-speed benchmark on the T500

**Recommended model: Sonnet to run the benchmark, Opus to turn the measurements into decisions.**

Covers the C-7 part of the gate.

- Generate a small detection dataset from the corpus (written to the corpus folder from `omr.paths`), using Verovio output with symbol labels.
- Run a short YOLO fine-tuning with the techniques in section 4.9 of the design: tiles, small batches with gradient accumulation, and FP16.
- Measure and log in plain text: time per epoch, peak GPU memory, the largest tile and batch size that fit in 2 GB, and how CPU data loading limits the speed.
- Repeat with a stand-in sequence-reader model of 20 to 40 million parameters, using gradient checkpointing, so that its speed and memory are known too.
- Opus uses the numbers to fix the model sizes, the tile size and the expected time per run, so that a run takes no more than a few days (C-7). If a model does not fit, Opus proposes changes, such as a smaller encoder or shorter sequences, or recommends using the free Kaggle quota for that run.

Done when: the benchmark results are in `docs/notes/training-benchmark.md`, and the model sizes for Phase 2 are written down.

## Stage 11: Speed targets and the gate review

**Recommended model: Opus.** This is a judgement and a decision, not a mechanical task.

- Use the baseline timings from Stage 9 to confirm or revise the OP-3 targets (10 seconds for a vector PDF page and 60 seconds for a raster page, on the CPU alone). Update `requirements.md` and close OI-2.
- Check every gate item against the evidence.
- Write a short Phase 0 report in `docs/notes/phase-0-report.md`:
  - what was done;
  - the baseline numbers;
  - the PDF-type survey result;
  - the fixed model sizes;
  - problems found, and any changes to the Phase 1 plan or the requirements.
- Draft the Phase 1 plan in this folder, using what Phase 0 has shown.
- Present the report to the owner for sign-off.

Done when: the owner has signed off the report, and the gate conditions are met.

## Order of work and dependencies

Stages that can run in parallel are listed together.

1. Stage 0, then Stage 1.
2. Stages 2 and 3, in parallel, once Stage 1 is done.
3. Stages 4 and 5, in parallel. Stage 4 needs files to test against, so its first version can use a handful of hand-made exports until Stage 5 is further on.
4. Stage 6, once there is some corpus from Stage 5.
5. Stages 7 and 8, in parallel, once Stage 6 and Stage 4 are done.
6. Stage 9, once Stages 6 and 8 are done.
7. Stage 10, which needs only Stages 1 and 5, so it can run alongside Stages 6 to 9. It is a good overnight job.
8. Stage 11, last.

The owner's braille discussion with the MuseScore community (OI-1) runs alongside all of this. It is not needed for Phase 0, but starting it now means the answer is ready for Phase 3.

## Where Opus matters most

If effort has to be rationed, spend Opus on these, in this order:

1. The metric definitions and matching logic in Stage 6. An error here is silent and affects every result in the project.
2. The type-classification rules in Stage 4, because Phase 1 builds on them.
3. The analysis in Stages 8, 9 and 10, because the decisions in the gate come from them.
4. The sampling design in Stage 5.

Everything else is well suited to Sonnet.

## Risks specific to Phase 0

- **A dependency lacks Python 3.14 support on Windows.** Checked in Stage 1. The fallback is Python 3.13 for the whole project.
- **Dorico SE or MuseScore 3 cannot be driven from the command line.** The fallback is a smaller sample from that engraver, with manual exports by the owner.
- **LEGATO or another baseline is too slow or too large to run.** It is then run on a small sample only, or dropped, and the reason is recorded.
- **The licence of a baseline or dataset prevents even internal use.** The register (Stage 3) shows this early. The item is dropped from the plan.
- **Too few real Sibelius and Finale pairs exist.** The survey (Stage 8) measures this. The ground-truth-free checks in the solution design cover the gap.
- **The T500 is slower than the plan assumes.** Stage 10 finds this early, while changing the model sizes still costs nothing.
