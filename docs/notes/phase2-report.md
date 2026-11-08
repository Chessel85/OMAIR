# Phase 2 report: clean raster input to MusicXML

Gate review for `docs/plans/phase2.md` (Stage 2.10), 8 November 2026. Plain headings and lists only.

## Decision

Waiting for the owner's sign-off. On 6 November 2026 the owner stopped Stage 2.9 and asked to close Phase 2 with any shortfall recorded as a known limit, then move on to correcting distorted images (Phase 4) for real-world testing, with a full sweep of every step from the start later, earliest steps first.

## Summary

- **ACC-2 (notes, target 97 percent) is met** on both gated sets at both gated resolutions: development set 98.4 percent at 300 dpi and 98.5 at 200 dpi, sealed check set 98.7 at both. Every engraver is over 97 percent too (the lowest is Verovio at 97.8 on the development set at 200 dpi), though the gate asks only for all engravers together.
- **ACC-4 (flagging) is not met, narrowly.** The flags catch enough of the errors: 94.3 to 96.7 percent of note errors on exact pairs are in flagged bars, against 90. But they flag 10.6 to 11.5 percent of bars, against a limit of 10. Stage 2.9 found that no choice of rules brings this under the limit; it needs fewer errors.
- **The check set agrees with the development set.** It is 585 pairs never looked at while the raster path was built. It reads 0.2 to 0.3 points better, so the fixes are general.
- **The image costs about half a point.** The same development pairs read from their PDFs give 99.0 percent; from 300 dpi images 98.4.
- **Against the baselines**, on the Phase 0 sample of 355 pairs read from 300 dpi images (the input Audiveris and homr had): 98.8 percent of notes against 86.3 for Audiveris and 55.9 for homr; 82.3 percent of files structurally correct against 22.5 and 17.7.
- **No loss on the vector path.** The shared code improved both paths: the vector development set reads 99.0 percent (97.8 at the Phase 1 gate), the check set 98.8 (97.7), the regression set 98.8 (98.4); structure 93.9, 91.5 and 94.5 percent (80.4, 83.1 and 80.5).
- **Speed:** 18.6 seconds a page at 300 dpi and 17.6 at 200, on the CPU one file at a time with both engines, against the 60 second target (OP-3, reported, not gated). The slowest page took about 32 seconds. The vector path takes 0.56.
- **The one real scan fails.** Of the 21 commercial files, the 20 rendered from PDFs convert; the Liszt scan does not (no staves found).

## What was run

All with the code of commit 5d5c1cb plus the resume option for `omr evaluate`, frozen in a copy, both engines on image pages, on the CPU with 3 workers, the symbol detector's results saved beforehand on the GPU. Results in `evaluations/s38-gate` on the corpus drive; the run script is `run-gate.sh` there. About 33 hours, 6 to 8 November 2026, against the estimate of 26 to 30. No file failed in any scored run.

- **Development set:** 1,764 pairs at 300 and 200 dpi, greyscale.
- **Sealed check set:** 585 pairs at 300 and 200 dpi, scored once for this review.
- **Regression set:** 254 pairs at 300, 200 and 150 dpi, and black and white at 300.
- **Baseline sample:** the 355 Phase 0 pairs, scored from the 300 dpi development outputs with musicdiff. 2 of them are LilyPond pairs no longer in the development set (rejected by the export check of 25 October 2026), so they count as failed; over the other 353 the figure is 99.0 percent.
- **Vector sets:** development, regression and check, read from the PDFs.
- **Commercial files:** `omr convert` on the 21 IMSLP files rendered at 300 dpi.
- **Timing set:** the 16 pairs of the Phase 1 timing set, rendered at 300 and 200 dpi, read one file at a time on the CPU alone (`--workers 1 --cpu-only`), both engines, the detector run live from its ONNX file, nothing saved beforehand. `evaluations/s38-gate/timing-g300` and `timing-g200`, 14 and 13 minutes.

The pairs whose PDF does not show the ground truth (the faulty LilyPond pairs) were decided on 25 October 2026: the export check rejects them, so none are in these sets, and no further pairs were set aside.

## ACC-2: note accuracy (target 97 percent)

- **Development set, 300 dpi:** 98.4 percent. LilyPond 98.0, MuseScore 3 98.5, MuseScore 4 98.8, Verovio 97.9.
- **Development set, 200 dpi:** 98.5 percent. LilyPond 98.1, MuseScore 3 98.7, MuseScore 4 98.8, Verovio 97.8.
- **Check set, 300 dpi:** 98.7 percent. LilyPond 99.1, MuseScore 3 98.9, MuseScore 4 98.6, Verovio 98.4.
- **Check set, 200 dpi:** 98.7 percent. LilyPond 99.0, MuseScore 3 99.0, MuseScore 4 98.5, Verovio 98.4.
- **Reported, not gated:**
  - Regression set: 97.3 percent at 300 dpi, 97.4 at 200, 96.8 at 150, 94.6 in black and white. One score, pdmx-N4apPPkuiAtX, reads 77 to 99 percent across its engravings on every version and pulls these down.
  - 150 dpi: 0.5 to 0.6 points below 300 and 200 on the regression set. LilyPond suffers most (93.5 percent).
  - Black and white: Verovio falls to 84.4 percent (97.9 in greyscale), and its structure to 55.8 percent. The other engravers lose under a point. Not looked into; Verovio draws thinner lines than the others, which may break up when the page is cut to one bit.
- **Structure (reported):** 80.7 and 80.2 percent of development files structurally correct at 300 and 200 dpi, 82.1 and 81.0 on the check set, against 93.9 and 91.5 from the PDFs. The image costs far more here than in notes.

## ACC-4: flagging (target: 90 percent of note errors in flagged bars, with at most 10 percent of bars flagged, exact pairs)

- **Development set:** 96.7 percent with 11.5 percent of bars flagged at 300 dpi; 94.3 with 11.4 at 200.
- **Check set:** 95.5 percent with 10.6 percent of bars flagged at 300 dpi; 95.5 with 11.4 at 200.
- **Over all pairs** (engraver-input pairs as well): 87.7 to 93.1 percent, with 12.2 to 14.9 percent of bars flagged.
- **Why it is over the limit:** the largest share of flags on images comes from "the engines disagree" (Stage 2.7), which flags a bar where the two readings differ (5.6 percent of bars on its own at 300 dpi). Stage 2.8 found that within 10 percent of bars no subset of the rules reaches 90 percent recall; Stage 2.9 brought the share of bars flagged at 200 dpi from 13.6 to 11.3 percent by removing errors, and was stopped by the owner there.
- **Vector path, for comparison:** development 95.3 percent with 4.0 flagged (met), regression 96.1 with 7.5 (met), check set 78.1 with 3.6 (not met; 75.0 at the Phase 1 gate).

## Markings, lyrics and chord symbols on images (REC-4 to REC-6, reported)

Recall on exact pairs of the development set at 300 dpi, then 200 dpi, then from the PDFs:

- Dynamics: 87.3, 87.2, 94.1 percent. Hairpins: 74.8, 58.0, 90.9. So ACC-6 (dynamics and hairpins together, target 90) is 83.3 and 77.8 percent on images, 93.1 from the PDFs. Hairpins at 200 dpi are the weak point: their thin wedge lines are lost.
- Lyrics: 87.4, 84.2, 95.8 percent.
- Chord symbols: 72.1, 71.5, 80.5 percent.
- Words (tempo and expression text): 60.7, 60.9, 68.4 percent.
- Slurs (both ends right): 80.4, 78.8, 83.2 percent.
- Rests, as a diagnostic: 86.6, 80.1, 97.0 percent. Rests are the largest single gap between image and PDF.
- The check set gives the same picture (dynamics 84.2 and 84.5, hairpins 77.7 and 62.2, lyrics 89.2 and 85.4 percent).

## Speed (OP-3, reported, not gated)

Measured on the owner's laptop (8 logical processors, the GPU hidden), one file at a time, both engines, the symbol detector run from its ONNX file through Ultralytics, the sequence reader and the OCR through ONNX Runtime. Each file's time includes loading the models. The staves on each page were counted from the vector PDF the page was rendered from (`scripts/timing_table.py`, new), and a file's time was shared over its pages by their staves.

- **300 dpi:** 45 pages in 839 seconds, 18.6 seconds a page on average. By staves a page: 1 to 4 staves (4 pages) about 7 seconds, 5 to 8 (10 pages) about 17, 9 to 12 (29 pages) about 21, 13 to 15 (2 pages) about 23. The slowest page about 32 seconds.
- **200 dpi:** 45 pages in 793 seconds, 17.6 seconds a page on average, about a second a page less at every staff count.
- **No page is over 60 seconds,** so no qualifier or cheaper setting is needed for pages like these. Dense orchestral pages were not in the timing set; in the commercial run, with 3 files at once and saved detections, The Planets averaged about 59 seconds a page, so a large score on a slower computer may pass the target.
- The 16 files read at 95.0 percent at 300 dpi and 95.3 at 200, against 92.5 for the vector reader on the same pairs at the Phase 1 gate; one LilyPond pair (pdmx-1oK7weKrpRUs) reads at 54 percent and holds most of the errors.

## Commercial files

The 21 commercial PDFs, each rendered as page images at 300 dpi, converted with `omr convert` (both engines). With no ground truth, the measure is the share of bars where no staff is flagged ("high confidence" in the report), as in Phase 1. It is a rough guide, not an accuracy figure, and the flag rules on images flag more than on PDFs.

- **20 of 21 converted.** The Liszt "Carousel" file, the one real scan, failed: no staves were found. Real scans are the kind of page Phase 4 is for.
- **Read well (70 percent or more of bars unflagged):** Woodwind quartet (Scarlatti) 92 percent, Jagdlied 91, trumpet and trombone duet 89, Bologne quartets 77, Mozart fugue 75, Eine kleine Nachtmusik 71, Mozart clarinet concerto 70.
- **Middling (30 to 69):** Andante 59, `concert_komplet` 54, Symphony No. 3 53, Mozart Fantasia 31.
- **Poor (under 30):** Valse Russe 21, Mendelssohn concerto 21, Tchaikovsky 15, Carnaval de Venise 11, Golliwogg 8, Debussy Images 6, Mozart Ave verum 5, Wilbye madrigal 5, The Planets 3.
- **Against Phase 1's vector figures:** files printed with the music as outlines now read far better from their images (Mozart fugue 4 to 75 percent, clarinet concerto 23 to 70), since the image path does not need the outlines' shapes. Direct exports read worse from the image than from the PDF (Valse Russe 90 to 21, Carnaval de Venise 78 to 11), mostly flags from the engines disagreeing on dense orchestral systems. The bar counts agree with the Phase 1 PDF reading in 13 of the 20 files.
- **The Planets took 3 hours 8 minutes** (191 pages), the Mendelssohn concerto 67 minutes.

## CI

A new job, `raster` in `.github/workflows/tests.yml`, renders the regression set in the repository (254 pairs, 444 pages) as greyscale page images at 300 dpi (`scripts/make_raster_set.py` with `--source-root`, `--out` and `--versions`, new), reads their notes with `scripts/check_notes.py`, and fails below 96.0 percent.

- **Engine 1 alone.** The sequence reader's weights cannot be published until the homr licence question is settled (licence register), so CI runs the detector path without Engine 2, as the plan allows. A trial on the laptop, without the corpus drive, gave 96.8 percent (97.6 on exact pairs; LilyPond 93.6, Verovio 98.0) in 31 minutes on 2 workers, against 97.3 with both engines. Both engines are run at milestones, as here.
- **The detector's weights** come from a GitHub release, `detector-weights-1`, asset `detector.onnx` (10.7 MB, AGPL, in the licence register). The release is not yet published: the owner chose on 8 November 2026 not to publish it yet. The job is ready in `docs/notes/ci-raster-job.yml`, to be added to `tests.yml` once the release is published.

## Known limits carried forward

- **Flagging on images:** 10.6 to 11.5 percent of bars flagged on exact pairs, against 10 (ACC-4). The recall is met.
- **Structure on images:** about 81 percent of files structurally correct, against about 93 from the PDFs.
- **Markings on images:** hairpins (58 percent at 200 dpi), rests (80 to 87 percent), words and chord symbols, all below their PDF figures.
- **Black and white:** Verovio pages read at 84 percent.
- **150 dpi:** about half a point below 200 dpi in notes, hairpins at 70 percent; the early warning for phone photos (Phase 4).
- **Real scans:** the one real scan in the commercial sample finds no staves.
- **Detector faults parked in Stage 2.9** (`docs/notes/raster-triage.md`): collision rests, augmentation dots and time signature digits; fixing them needs retraining.
- **The sequence reader's weights** (Engine 2) come from homr's, whose training data includes a non-commercial set; the licence register has this as the owner's to resolve before anything trained from them is released. Until then they cannot be published, so CI runs Engine 1 alone.
- **Everything carried from Phase 1** (`phase1-report.md`) still applies to the shared assembly, apart from what the figures above show has improved.

## Where to resume raster work

- The triage method and ranking are in `docs/notes/raster-triage.md`, with `scripts/triage_raster.py` (the cause of each error the image adds) and the work loop in `phase2.md`, Stage 2.9.
- The flag rules and their worth on images: `scripts/check_flags.py` with a raster set root.
- The check set stays sealed: score it only at milestones.
