# Phase 2 Plan: Clean Raster Input to MusicXML

**Status: agreed, 17 October 2026.** The owner agreed the gate wording below at the start of Stage 2.0. Drafted from the solution design (section 6), the Phase 0 and Phase 1 plans and progress logs, `docs/notes/phase1-report.md` and the Phase 2 decisions in `docs/notes/training-benchmark.md`. Plain headings and lists only. Model suggestions follow the Phase 0 plan: Opus for design and judgement, Sonnet for implementation, escalate to Opus after two or three failed attempts.

## Goal and gate

Goal: read clean raster pages (Type C: a PDF holding a clean page image, or a PNG, JPEG or TIFF file) to at least 97 percent note accuracy (ACC-2), with confidence flags that catch the errors (ACC-4), the self-check by re-rendering (DEV-3), and the performance markings, lyrics and chord symbols (REC-4, REC-5 and REC-6 for raster input). The solution design estimates 8 to 12 weeks.

Gate as the solution design words it: "ACC-2 and ACC-4 are met." That leaves open what the raster corpus is and where ACC-4 is measured: the requirement measures ACC-4 on the exact pairs of the vector corpus. **Agreed wording:** "ACC-2 is met on the raster versions of the development set and the sealed check set, at both 300 dpi and 200 dpi in greyscale (each page of the pair's PDF rendered at that resolution), over all engravers, excluding pairs the owner agrees are faulty. ACC-4 is met on the exact pairs of those raster sets. The 150 dpi versions and the real Type C files obtained in Stage 2.0 are converted and their result reported, with any shortfall listed as a known limit." The owner has no real Type C files to give, so the real files are the 21 commercial PDFs rendered as images.

Why these choices:

- **Rendered pages as the corpus.** Every vector pair already has its ground truth. Rendering its PDF gives a raster pair with the same answer, for every engraver, at no cost. Real clean raster files are rare: the Phase 0 survey found almost none, and the commercial sample had one scan.
- **Over all engravers, not each one.** The raster path shares the notation assembly with the vector reader, which reads LilyPond at 94.9 percent and Verovio at 96.7 on the development set. A per-engraver 97 percent would need vector work first. Figures are still reported by engraver.
- **300 dpi and 200 dpi greyscale as the gate.** 300 dpi is what the Audiveris and homr wrappers used in Phase 0, so their figures compare directly.
- **Low resolution matters from the start.** Many users will be blind people photographing paper scores with a phone, and their photos will often be distant, angled or partly framed. A 12 megapixel phone photo of one page is about 280 to 320 dpi in pixels, but blur, compression and noise reduction leave detail nearer a clean 150 to 250 dpi. A two-page spread or a distant shot is nearer 150. So the clean 200 dpi set is gated as the stand-in for a good photo, and 150 dpi is reported as the early warning for Phase 4. On a typical score the staff space is about 21 to 24 pixels at 300 dpi, 14 to 16 at 200 and 10 to 12 at 150. Black-and-white versions are reported too, not gated.

What Phase 0 and Phase 1 showed that shapes this plan:

- **The vector reader is the best tool the project has.** 97.8 percent notes on the development set, against 86.3 for Audiveris and 55.9 for homr, both of which read rendered images. Its layout, structure, notation, markings, rules and writer do not care where the symbols came from.
- **So the main raster engine should feed the vector reader.** If the detector and the line finder produce the same symbols and lines that `symbols.py` and `evidence.py` produce from a PDF, the whole of Phase 1 runs unchanged on images, and every later fix serves both paths. This is Engine 1 in the design.
- **Labels come free from vector PDFs.** The vector reader knows every glyph's name and ink box and every line on the page. Rendering the same page gives pixel-exact training labels for MuseScore, LilyPond and Verovio alike, not only for Verovio as the design assumed.
- **The raster penalty can be measured exactly.** Reading the same pair from its PDF and from its image shows how many errors the image adds. That splits raster faults from assembly faults, which the vector work loop already handles.
- **Model sizes are fixed** (`training-benchmark.md`): YOLO11 nano at 640 pixel tiles, batch 8, about 1.5 to 2 days a full run; a sequence reader of about 29 million parameters, 1 to 2 days a fine-tune. Two things must be checked first: the render scale, and the starting weights' architecture. Stage 2.0 found the chosen starting weights, homr's, are 75 million parameters in PyTorch; they train in 2 GB only with the encoder frozen and staves of up to 128 tokens at batch 4 (about 2.5 staves a second).
- **Accuracy comes before speed.** The owner recorded at the Phase 0 sign-off that the 60 second raster target (OP-3) is low priority and not a Phase 2 blocker. It is measured and reported, not gated.
- **ACC-4 fell in Stage 1.8** (88.3 percent on the development set) because the confidence rules were not grown alongside the fixes. This plan grows them in every stage that changes the reading.

## Rules for the whole phase

- **An estimate before the bulk of each stage.** Once a stage's design or first small trial is done, and before its main build, export or training run, give the owner a short estimate in plain text: the Claude sessions the stage is likely to take, the length of each long run (rendering, training, full evaluations) and whether it runs overnight, and the disk space it will use. The owner agrees it before the bulk starts. Record it in `phase2-progress.md`, with the actual figures beside it at the end of the stage.
- **Say how each job uses the laptop.** The same estimate says, for each long job, how many CPU workers it uses and whether it uses the GPU. The defaults:
  - **CPU-bound jobs use the shared worker pool** (`src/omr/parallel.py`, 3 workers by default, leaving one core free): rendering and exporting scores, cutting tiles and staff crops, label checks, OCR, and every evaluation run. MuseScore already uses several threads, so expect about 1.7 times the one-worker speed, not 3 (`tool-commands.md`).
  - **Training uses the GPU**, one run at a time (the T500 has room for only one), with 2 data-loading workers. A CPU-heavy job alongside a training run slows both, so the estimate says whether they can overlap.
  - **Inference runs on the CPU** through ONNX Runtime, because OP-2 makes the GPU optional. Evaluation runs may use the GPU for speed, but the gate's timing figures come from the CPU, one file at a time.
- **The check set stays sealed:** render it in Stage 2.0, score it only at milestones and at the gate.

## Stage 2.0: Decisions and first measurements

**Model: Opus for the decisions, Sonnet for the rendering and runs.**

- **Gate wording.** Ask the owner to agree the proposed wording above, including the resolution and the faulty-pair rule.
- **Raster sets.** Write `scripts/make_raster_set.py`: render every pair of a set into a PDF holding the page images (so it is Type C), as greyscale jobs at 300, 200 and 150 dpi, with a black-and-white job at 300 dpi. The ground truth and the pair metadata are the vector pair's. Make the regression, development and check sets. The check set stays sealed: render it, but score it only at the gate.
- **Baselines on the raster sets.** Audiveris and homr already read rendered pages at 300 dpi, so their Phase 0 sample figures stand. Score the vector reader on the same 355 pairs for the raster penalty later. No new baseline runs are needed.
- **The raster ceiling.** Record the vector reader's figures on each set as the reference the raster path is measured against.
- **Real Type C files.** Ask the owner whether some can be had: PDFs of modern editions saved as page images, or music shared as PNG. If yes, put them in `sources/other` and run `run_survey.py inspect` on them. They have no ground truth, so they are reported by unflagged bars, as the commercial files were.
- **Type C and D in the inspector.** The split in `inspector-spec.md` is provisional. Check it on the rendered sets (all must be Type C) and on the real files. `omr convert` must accept Type C PDFs and PNG, JPEG and TIFF files (IN-2), where today it refuses them.
- **Starting weights.** Check the licences of the homr and SMT weights (the register has them as not yet checked), and the architecture and size of each. Look for detector weights trained on DeepScores with a usable licence. If there are none, start from the Ultralytics YOLO11 nano weights (AGPL) and rely on the project's own labels.
- **OCR.** Choose the OCR engine for text in images (Tesseract or PaddleOCR) and add it to the licence register. Ask the owner whether lyrics and chord symbols are in scope for raster input in this phase. The requirements assign them to vector input only (REC-5, REC-6), but they matter for the genres in REC-10.

Done when: the gate wording is agreed, the raster regression, development and check sets exist, the vector ceiling is recorded, the starting weights are chosen with their licences entered, and the owner has answered the Type C and OCR questions.

## Stage 2.1: Training-data generator

**Model: Opus for the label rule, Sonnet for the generator.** Builds on `src/omr/corpus/` and `src/omr/pdf/symbols.py`.

- **Label rule first.** Write `docs/notes/raster-labels-spec.md`: the detector classes (a grouping of the SMuFL names the vector reader uses: noteheads by kind, rests by value, clefs, accidentals, flags, dots, time-signature digits, dynamics, articulations, ornaments, tuplet numbers and so on), and how each box is made. Glyph classes take their ink box from `symbols.py`. Stems, barlines and beams, if they are classes at all, are thin boxes with a minimum width, or are left to the line finder (Stage 2.2). The rule decides which.
- **Source scores from the training pool only.** No score from the development, regression or check sets, and none of their near copies (the rules in `corpus-sampling.md`). Filter the 62,113 candidates by size and round trip, and export a few thousand through the existing jobs (MuseScore 3 and 4 in several fonts, LilyPond, Verovio). Overnight CPU batches, resumable, with the free-space check.
- **Detector data.** Render each page at a range of scales, staff space about 10 to 24 pixels (about 150 to 300 dpi on a typical score), so the detector does not depend on how close the camera was. Cut 640 pixel tiles with overlap, and write YOLO labels from the vector reader's symbols. About 10,000 tiles to start (one epoch of about 55 minutes). Clean variations only: resolution, slight blur, JPEG, greyscale and black-and-white, faint noise. Camera distortions belong to Phase 4.
- **Sequence-reader data.** Staff crops with their token sequence in homr's format, made by homr's own parser from the ground-truth MusicXML (not from the vector reader's output, which would teach its errors), with the vector reader's systems used only to find each staff's bars. About 100,000 staves.
- **Check the labels without sight.** A script that draws the boxes back onto the image is no use to the owner, so check them by numbers: every symbol on a page has one box inside the image, no two boxes of one class cover the same ink, and the boxes from a page agree with the ink found in the rendered image.

Done when: the label rule is written, the generator makes both datasets from the training pool, and the label checks pass on a sample of every job.

## Stage 2.2: Staff lines and lines in the image

**Model: Opus for the design, Sonnet for the code.**

- Find staff lines in the image and the staff space, with a small tilt corrected. Classical image processing is enough for clean pages (run lengths and projections, OpenCV).
- Find the vertical and long lines the vector reader uses as drawings: barlines, stems, ledger lines, beams, brackets, hairpin arms, tuplet brackets, ending and octave lines. Return them in the form `evidence.py` gives for a PDF, so `layout.py` and `notation.py` take them unchanged.
- Curves (slurs and ties) are the hard case. Decide here whether to trace them from the ink once noteheads are known, or to leave them to a detector class.
- **Check against the vector truth.** On rendered pages, compare the staves and lines found with those the vector reader reads from the same PDF. Report the share found and the position error in staff spaces.

Done when: on the raster regression set, every staff is found, and staff, barline and stem recall against the vector reading is at least 99 percent.

## Stage 2.3: Symbol detector (Engine 1)

**Model: Sonnet to train and run, Opus to read the results and decide.**

- **The render-scale test first** (from `training-benchmark.md`): short runs on the same scores, trained on one scale (staff space 14 to 20 pixels) against the full range (10 to 24), each scored on the 300, 200 and 150 dpi raster pages, comparing recall on small symbols (accidentals, dots, flags). If the range costs little at 300 dpi and gains at 150, train on the range. If small symbols are lost at 150 dpi in a 640 tile, the image can be enlarged before tiling, at the cost of more tiles a page.
- Train YOLO11 nano at 640 pixels, batch 8, FP16, 2 workers. Experiments at 20 epochs (under a day), the full run at 40 to 50 epochs (1.5 to 2 days), with checkpoints so a run can stop and resume, and a plain-text progress log.
- **Score the detector on its own** against the vector labels of the raster development pages: recall and precision by class, and the classes the vector reader most depends on (noteheads, accidentals, dots, rests, clefs, tuplet numbers). Write `scripts/check_detector.py`.
- Export to ONNX and time CPU inference a page, one at a time.

Done when: the detector reaches at least 99 percent recall on noteheads and at least 97 percent on accidentals, dots and rests on the 300 and 200 dpi raster development pages, its 150 dpi figures are recorded, and its CPU time a page is recorded.

## Stage 2.4: From detections to the vector reader

**Model: Opus for the design, Sonnet for the code.** This is the stage that joins the image to Phase 1.

- Build the page the vector reader expects from the detections and the lines: named symbols with an origin and an ink box, lines and shapes, and text runs once Stage 2.5 gives them. The symbol origin must follow SMuFL's anchor (a notehead's centre line, a clef's line), as `symbols.Symbol` documents.
- Carry each detection's confidence through. A symbol under a set confidence, or two classes close in score, becomes a doubt in `Score.doubts`, so the confidence report can flag it.
- `read_pdf` takes an image page through this route, and `omr convert` works end to end on Type C input.
- **First end-to-end figure.** Run the raster regression and development sets with `omr evaluate`, and report the raster penalty: the same pairs read from their PDFs and from their images.

Done when: `omr convert` runs on every raster regression pair, and note accuracy, the raster penalty and ACC-4 are measured on the raster development set. Escalate to Opus and to the owner if note accuracy is under 90 percent here.

## Stage 2.5: Text and markings in images

**Model: Sonnet, Opus to review the categories.**

- Find text regions (the detector, or the ink left after music symbols) and read them with the OCR engine chosen in Stage 2.0. Return text runs in the form `text.py` sorts, so its rules apply unchanged: title, composer, tempo, expression, instrument names, rehearsal marks.
- Dynamics in letters and glyphs, hairpins, articulations, fermatas and ornaments come from the detector and lines (REC-4). Measure ACC-6 on the raster sets beside the vector figures.
- Lyrics and chord symbols (REC-5, REC-6), which the owner put in scope for raster input in Stage 2.0. Lyric syllables go to `text.py`'s lyric rules with their position under the staff, so hyphens, melismas and verses are handled as for vector input.

Done when: text kinds, lyrics, chord symbols and ACC-6 are measured on the raster development set, with the vector figures beside them.

## Stage 2.6: Sequence reader (Engine 2)

**Model: Opus for the architecture check and the decoding, Sonnet for training.**

- **Check the starting weights first.** The fine-tuned model must be the pretrained one. The chosen weights are homr's (Stage 2.0): an encoder of 13.2 million parameters and a decoder of 46.9 million, about 60 million in all, above the 20 to 46 million range measured in Phase 0. Measured in Stage 2.0 (`scripts/benchmark_homr_finetune.py`): the whole model overflows 2 GB at every batch size, but with the encoder frozen, batch 4 at up to 128 tokens fits and trains about 2.5 staves a second, so 3 passes over 100,000 staves take about 1.4 days. Staves longer than 128 tokens are split or trained at batch 2. If the frozen encoder holds the accuracy back, the fallback is SMT (21.4 million, MIT), which needs more training on the project's own staves because it was trained on piano grand staves only.
- **Build the key-value cache and test INT8 before training.** Without a cache a staff takes about 17 seconds; with one the estimate is 6 to 13. This decides how the engine can be used on dense pages.
- Fine-tune on the staff crops from Stage 2.1, batch 4 to 8, FP16, 3 to 5 passes (1 to 2 days). Measure how many passes are enough on the real data.
- Turn its tokens into the project's score model, one staff at a time, placed in the systems and bars that Stages 2.2 to 2.4 found, so its output can be compared bar by bar.
- **Score it alone** on the raster development set, as a third baseline beside Audiveris and homr.

Done when: the sequence reader runs on every raster development pair, its accuracy alone is recorded, and its CPU time a staff with the cache (and with INT8, if used) is recorded.

## Stage 2.7: Reconciliation

**Model: Opus.**

- Compare the two engines bar by bar and staff by staff. Where they agree, confidence is high. Where they differ, keep both readings as candidates and let the musical rules choose (bar fullness, the other staves, key and accidentals, range), as section 4.5 of the design describes.
- A bar where the engines still disagree after the rules is flagged, with the two readings in the report in words ("the engines disagree on the third note, F sharp 5 or G 5").
- Measure what each part of the reconciliation adds: Engine 1 alone, Engine 2 alone, and both. If Engine 2 adds nothing on clean input, say so and keep it for Phase 4, where photos may need it more.
- Audiveris as a third opinion stays optional. Try it only if the two engines leave a clear gap that a third reading could close.

Done when: the combined reading is at least as good as the better engine on every engraver, and engine disagreement is a flag rule scored by `check_flags.py`.

## Stage 2.8: Self-check by re-rendering (DEV-3)

**Model: Opus for the design, Sonnet for the code.**

- Render the output MusicXML with Verovio, keeping the detected system breaks and staff sizes.
- Line up the rendering with the input system by system, and compare symbols: noteheads at the same places, the same accidentals, the same rests. On clean raster input, compare pixels as well.
- A bar that differs has its confidence lowered and is flagged.
- **Run it on the vector path too.** Stage 1.8 left mostly errors that break no rule (a shifted bar, a misread tuplet that still adds up). Those are exactly what a re-rendered page shows. Measure ACC-4 on the vector development set with and without the self-check.

Done when: the self-check runs inside `omr convert` for both paths, and its effect on ACC-4 is measured on the raster and vector development sets.

## Stage 2.9: Accuracy push

**Model: Opus for triage and every rule that decides rhythm, voices or structure; Sonnet for implementation, tests and runs.** Record progress in `phase2-progress.md` at the end of each session.

- **Triage the raster penalty first.** For the errors the image adds, sort them by cause: a missed or extra symbol (by class), a wrong class, a line not found, a curve, a text region. Write the ranking in `docs/notes/raster-triage.md`. Errors the vector reader also makes go to the vector ranking in `error-triage.md`, not here.
- **The work loop from Phase 1:** take the top cause, fix it with a test, run the affected files, re-run the full raster development set after each large fix, and re-rank. A detector fix usually means more or better training data for that class, so batch them into one retraining run where possible.
- **Grow the confidence rules alongside**, so that ACC-4 holds as the errors shrink.
- **Rules for the whole stage**, as in Phase 1: the check set stays sealed; every fix needs a test; raise the CI floors as figures rise; reference faults are the owner's call, with figures reported with and without such pairs.

Done when: the gate figures are met on the raster development set, or the owner stops the stage.

## Stage 2.10: CI, speed and the gate review

**Model: Opus.**

- **CI.** Add a raster job on the regression set: render the pages, run the converter with the released weights (GitHub Releases, AGPL, in the licence register), and fail below a floor. If the sequence reader makes this too slow for CI, run Engine 1 alone there and the full path at milestones.
- **Speed.** Measure seconds a page on the CPU, one file at a time, on the timing set, against the 60 second target (OP-3). Report pages by staff count. If dense pages are over, propose a qualifier or a cheaper setting to the owner; it does not block the gate.
- **Gate runs.** Run the raster development, regression and check sets, the vector sets for the shared code (to show no loss), and the real Type C files. Compare with the baselines.
- Write `docs/notes/phase2-report.md` and ask the owner for sign-off.

Done when: the gate (as agreed) is met and the report is signed off.

## Order and dependencies

1. Stage 2.0 first. The rest needs its raster sets and decisions. Stage 2.1 needs two of them in particular: the starting weights (their token format sets the sequence-reader data) and the training pool filter.
2. Stage 2.1, with Stage 2.2 alongside (it needs only the raster sets).
3. Stage 2.3 once Stage 2.1 has the detector data. The training runs are overnight and multi-day, so start them early and do other stages while they run.
4. Stage 2.4 once Stages 2.2 and 2.3 have first results. This gives the first end-to-end figure and is the main check on the plan.
5. Stage 2.5 alongside Stage 2.4.
6. Stage 2.6 can start after Stage 2.1, alongside 2.3 to 2.5. Only one training run fits on the GPU at a time.
7. Stage 2.7 needs 2.4 and 2.6. Stage 2.8 needs only 2.4 and can start early on the vector path.
8. Stage 2.9, then Stage 2.10.

Phase 3 (braille and reporting) overlaps Phase 2, as the design says. It is blocked on the owner's braille question (OI-1), not on this plan. The five open owner decisions on reference faults (`error-triage.md`, causes 14 to 17 and 19) change the figures for both paths and do not block Phase 2. Vector work can resume whenever the work loop is useful, because fixes to the shared assembly lift both paths.

## Risks specific to Phase 2

- **Engine 1 depends on near-perfect detection.** The vector reader was built for exact symbols. A missed dot or accidental becomes a note error, and a missed stem can break a beam group. Stage 2.4 measures this early; the doubts from low-confidence detections and Engine 2's independent reading are the fallbacks.
- **Curves and thin lines** (slurs, ties, hairpins, beams at a slope) are harder in an image than in a PDF. Stage 2.2 decides the approach.
- **The sequence reader may not help on clean input** and may be slow on the CPU. Stage 2.7 measures what it adds, and Stage 2.6 builds the cache and tests INT8 before training.
- **Overfitting to rendered pages.** Training and evaluation pages come from the same engravers and fonts. The sealed check set guards against fitting to particular scores, not to particular engravers. Real Type C files (Stage 2.0) and the commercial PDFs rendered as images are the check against that.
- **Starting-weight licences.** If the homr or SMT weights cannot be shipped under AGPL, the sequence reader trains from the project's own data only, which may take longer. Stage 2.0 settles this before any training.
- **Training runs take days on a laptop.** A wrong label rule or scale found late costs a run. The label checks (Stage 2.1) and the render-scale test (Stage 2.3) come before the full runs. Free Kaggle quota stays an optional accelerator.
- **Disk space.** Rendered tiles and staff crops add tens of gigabytes. Every writer uses `omr.paths` and the free-space check.
- **Low resolution may cost more than expected.** At 150 dpi a dot or a small accidental is only a few pixels. The 200 dpi gate and the 150 dpi figures show this from Stage 2.3 onward; if 200 dpi lags 300 dpi by more than a point or two, raise it with the owner then, not at the gate.
