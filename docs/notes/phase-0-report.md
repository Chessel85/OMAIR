# Phase 0 report

Version 0.1, 9 October 2026. Written by Claude (Sonnet 5.5) to close Stage 11 of `docs/plans/phase0.md`. The owner has not yet signed it off; the decisions that need the owner are listed at the end. Plain headings and lists only.

## Summary

- All four gate conditions are met, with two caveats: the Sibelius and Finale gap in the PDF survey (accepted by the owner on 7 October 2026), and the raster speed target (new, see below).
- Phase 0 also delivered AX-3 (accessible development), DEV-1 (evaluation harness), DEV-2 (regression set) and DEV-4 (baselines).
- 202 tests pass. CI runs on Windows and Linux, including the regression job.

## What was done, by stage

- **Stage 0, prerequisites:** done. Dorico SE parked (not accessible with a screen reader).
- **Stage 1, skeleton:** done. Python 3.14, all dependencies have wheels, AGPL-3.0, corpus on the separate drive through `omr.paths`.
- **Stage 2, CI and conventions:** done. The owner confirmed the workflow is text based and fine with NVDA.
- **Stage 3, licence register:** done, 66 dependencies and the datasets, models and tools.
- **Stage 4, PDF inspector:** done, read with NVDA, reviewed. A vector page takes 0.01 to 0.12 seconds.
- **Stage 5, corpus generator:** done. Development set 300 scores, 1,778 pairs. Regression set 43 scores (of 50 planned), 256 pairs. LilyPond failed on 24 scores in all.
- **Stage 6, evaluation harness:** done and reviewed. The perfect recogniser scores 100 percent and the damaged one scores what its damage implies. Spec decisions 8 to 10 (one error per wrong note, voice merging, a misread clef counts once) came from the review.
- **Stage 7, regression set and CI:** done. A worse stand-in fails CI, an unchanged one passes.
- **Stage 8, real-world files and survey:** done without CPDL (Cloudflare) and without Sibelius or Finale files. 3,133 PDFs surveyed.
- **Stage 9, baselines:** done. Audiveris, homr and LEGATO, results below.
- **Stage 10, training benchmark:** done. Sizes fixed in `docs/notes/training-benchmark.md`.
- **Stage 11:** this report and `docs/plans/phase1.md`.

## Baseline numbers (gate item 1)

All figures use note accuracy with the clef rule. Detail, breakdowns and failure analysis are in `docs/notes/baselines.md`.

- **Audiveris 5.11.0:** 86.3 percent on the 355-pair development sample (1 failure); 80.5 percent on 40 real MuseScore.com uploads. 9.0 percent of files structurally correct. Dynamics and hairpins 74 percent. No text.
- **homr 0.7.0:** 55.9 percent on the sample (61.5 over the 340 files completed; 15 failed, 13 by timeout); 63.9 percent on real uploads. Fails on more than two staves in a system and on long files. No markings, no text.
- **LEGATO:** 83.4 percent on 28 MuseScore 4 pairs (55 pages), a different and smaller sample. Dynamics 77.5 percent, hairpins 81.2. No text. A development baseline only (licence). The last 7 of its 35 queued pairs were not run.
- **The target is far away.** ACC-1 asks for 99 percent. The best tool reaches 86.3 percent, or 89.1 percent taking the better of Audiveris and homr for each file. Only 17 percent of Audiveris files reach 99 percent.
- **Where the project can win:** read the vector PDF directly (the baselines all work from a picture and lose up to 25 points on unusual fonts and small staves); text from the text layer (lyrics, words and chord symbols are 0 percent in all three); bar arithmetic for rhythm; multi-part and long scores; dynamics and hairpins.
- **Caveats:** OMR-NED is computed for Audiveris (0.226 in notes and rests) and homr (0.256), not LEGATO. TEDn is not computed (spec decision 7, open).

## PDF-type survey (gate item 2)

Detail in `docs/notes/pdf-survey.md`.

- 3,133 files and 18,597 pages from OpenScore, Mutopia and a seeded PDMX sample. 99.6 to 99.9 percent of pages are Type A. One Type D page. No real Type B.
- Legacy font tables needed so far: Emmentaler only (one table for its size variants).
- **Known gap:** no Sibelius, Finale, Dorico or Notion files. The share of outlined glyphs and legacy fonts from commercial engravers is unknown. The owner accepted this on 7 October 2026 as an open risk, to be revisited before the Phase 1 gate.

## Speed targets (gate item 3, closes OI-2)

Measured on the CPU alone, one file at a time (OP-2):

- Audiveris 21 seconds a page (median), homr 27, LEGATO 18.4 minutes (average).
- The inspector reads the evidence of a vector page in 0.01 to 0.12 seconds.
- Stand-in sequence reader (29 million parameters), ONNX Runtime, no key-value cache: about 17 seconds per staff, so about 3 minutes for a 10-staff page. With a cache the estimate is 6 to 13 seconds per staff (not measured).

Conclusions:

- **Vector PDF, under 10 seconds a page: confirmed.** The vector path is geometry and rules, with no model. Nothing measured suggests it is at risk. It is a target, not yet demonstrated by project code.
- **Raster page, under 60 seconds: confirmed as a target, but at risk.** Audiveris and homr (26 to 27 seconds a page) show an image tool can meet it. The project's own sequence reader would cost an estimated 6 to 13 seconds per staff with a cache, plus the detector, so a page of 6 staves is near the limit and a page of 12 is well over, before INT8. Phase 2 must build the cache and test INT8 early. If dense pages still miss the target, the owner should choose between a qualifier ("a page of up to about 8 staves") and a smaller model.
- `requirements.md` is updated: OP-3 is marked confirmed with this caveat, and OI-2 is closed. `requirements.html` and `solution-design.html` were not regenerated (the repository does not record how they were built).

## Model sizes (gate item 4)

Full reasoning in `docs/notes/training-benchmark.md`.

- **Detector:** YOLO11 nano, 640 pixel tiles, batch 8, FP16. About 3 tiles per second, 10,000 tiles an epoch in about 55 minutes, 40 to 50 epochs in 1.5 to 2 days. The small model does not fit in 2 GB and is 4 times slower.
- **Sequence reader:** about 29 million parameters (4-layer decoder), batch 4 to 8, FP16, no checkpointing. About 3 staves per second, 100,000 staves in about 9 hours, a fine-tune in 1 to 2 days.
- **Kaggle:** not needed.
- **To check first in Phase 2:** the architecture of the starting weights (homr's transformer files imply about 25 million parameters, which fits), and the render scale for the detector.
- Run lengths carry plus or minus 20 percent (thermal variation, random-data measurement).

## Problems found, and changes to the plans

- **The Phase 1 gate in the solution design names the CPDL Sibelius and Finale pairs.** CPDL is unavailable, so the gate cannot be met as worded. `docs/plans/phase1.md` proposes new wording.
- **Restated clefs, keys and times count as structural mismatches.** This is why only 9 to 25 percent of files are structurally correct for every tool. Ignoring restatements lifts Audiveris from 9.0 to 22.5 percent. It needs a spec decision before Phase 1 measures the structural half of ACC-1.
- **Wrapper faults look like tool weakness.** Two Audiveris faults cost 6 points before they were found. Rule for later: read the failures before trusting an average.
- **A low-memory event** stopped one overnight LEGATO run. Run long jobs with other programs closed.
- **Regression set is short:** 43 of 50 scores, with genre shortfalls (listed in `phase0-progress.md`). It does not block anything.
- **Dorico SE is parked.** Only MuseScore 3 and 4, LilyPond and Verovio are in the corpus.
- **TEDn not computed.** Open, not blocking.
- **Environment:** the torchvision pin for the GPU build was wrong and is fixed.

## Gate check

- Baseline accuracy recorded: yes.
- Mix of PDF types and fonts known: yes for MuseScore and LilyPond output; unknown for commercial engravers (accepted risk).
- OP-3 confirmed, OI-2 closed: yes, with the raster caveat.
- Model sizes fixed to fit the laptop: yes.

## For the owner to decide at sign-off

1. Accept the report and the gate as met, with the Sibelius and Finale gap.
2. Agree the decisions made on the owner's behalf: the model sizes, the render-scale test, and the OP-3 wording.
3. Decide the restated-signature rule (proposal in `docs/notes/baselines.md`). Recommended: yes, ignore restatements.
4. Agree the changed wording of the Phase 1 gate (in `docs/plans/phase1.md`).
5. Decide whether to regenerate the two HTML documents.
