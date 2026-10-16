# Phase 1 report: vector PDF to MusicXML

Stage 1.7, 16 October 2026. Gate review for `docs/plans/phase1.md`. The owner chose option 1 below: Stage 1.8, an accuracy push, is planned in `phase1.md`, and the gate will be reviewed again in Stage 1.9.

## Summary

- **The gate is not met.** Note accuracy is 96.7 percent on the development set and 98.4 percent on the regression set, against 99. Structural correctness is 77.8 and 80.5 percent, against 95.
- **Speed is far inside the target.** About 0.6 seconds a page on the CPU, against 10 (OP-3).
- **ACC-6 (dynamics and hairpins) and ACC-4 (flagging) meet their targets** on the development and regression sets.
- **Against the baselines,** on the same 355-pair sample: 97.4 percent note accuracy against 86.3 for Audiveris and 55.9 for homr. Structural correctness is 71.8 percent against 22.5 and 17.7.
- **Commercial engraver files:** files exported directly by Sibelius, Finale or Dorico mostly read with high confidence. Files printed to PDF through a printer driver mostly do not.

## What was run

The runs are in `scripts/run_phase1_gate.sh`. Results are in `evaluations/` on the corpus drive, in folders whose names start with `gate-`.

- **Timing:** the 16-pair timing set (45 pages), one file at a time, CPU only, as the baselines were timed.
- **Regression set:** 256 pairs, 3 at once.
- **Real-world pairs:** the 40 MuseScore.com uploads, 3 at once.
- **Development set:** all 1,778 pairs, 3 at once, without musicdiff.
- **Baseline sample:** the 355 pairs, scored from the development outputs with musicdiff, for a like-for-like comparison with `baselines.md`.
- **Commercial engraver files:** `omr convert` on the 21 IMSLP files from Stage 1.0, in `gate-commercial-omr`. These files have no ground truth, so only the confidence report can be judged.

No file failed in any run. The whole run took about an hour.

## Speed (OP-3)

- **Timing set:** 0.60 seconds a page overall, median 0.65, slowest 4.2 (a one-page Verovio file). Audiveris took a median of 21 seconds a page on the same pages, and homr 27.
- **Development set:** 0.55 seconds a page overall over 10,927 pages, slowest 7.8 seconds. These timings were taken with 3 files at once, so they are a little slow.
- **Real-world pairs:** 0.56 seconds a page.
- No profiling is needed.

## ACC-1: note accuracy (target 99 percent)

- **Development set:** 96.7 percent. By engraver: MuseScore 3 98.2 (base) and 98.1 (variant), MuseScore 4 98.1 and 98.1, LilyPond 94.1, Verovio 93.1. 1,273 of 1,778 files reach 99 percent.
- **Regression set:** 98.4 percent. MuseScore 99.2 to 99.5, Verovio 98.7, LilyPond 93.7.
- **Real-world pairs:** 93.0 percent. Without the faulty pair `real-cf113e2176a3`, 96.2 percent. That is the 8-part choir piece where the PDF lacks a part; see `baselines.md`. 29 of 40 files reach 99 percent.
- **Baseline sample:** 97.4 percent.
- **Errors on the development set:** onset errors are the largest group (16,995 notes), then pitch (5,031), duration (4,455), missing (8,010) and extra (6,532). The causes are known limits listed in `notation-spec.md`: tuplets, three voices on a staff, cross-staff tuplets, tremolos, and LilyPond and Verovio octave marks.
- **Gap:** MuseScore output is within a point of the target. LilyPond and Verovio are 5 to 6 points short.

## ACC-1: structural correctness (target 95 percent)

- **Development set:** 77.8 percent. By engraver: MuseScore 84.0 to 85.3, Verovio 71.0, LilyPond 55.4.
- **Regression set:** 80.5 percent.
- **Real-world pairs:** 65.0 percent. In 7 of the 14 failing files, the only mismatch is a clef the output has and the ground truth lacks, or a percussion clef named differently. In `real-ce2b3cb1299f`, every note is right while the clefs differ, so the clefs the reader found must be the printed ones. The PDMX MusicXML seems to leave out some clef changes the PDF shows. If those 7 files are counted as right, the figure is 82.5 percent. The other 6 files have not been checked one by one.
- **Baseline sample:** 71.8 percent.
- **Development mismatches, in files with at least one of each kind:** bar count 131, clef 127, key signature 83, repeat 75, navigation 74, time signature 72, ending 69, parts 36, other 64.
- **The harness figure is stricter than the Stage 1.2 check.** The harness also compares repeats, endings and navigation marks. On exact pairs the Stage 1.2 check gives 85.3 percent and the harness gives 85.0.
- **Gap:** this is the larger shortfall, about 10 points even on MuseScore output.

## ACC-6 and ACC-4

- **ACC-6 (dynamics and hairpins, target 90 percent, exact pairs):** development 93.1 percent, regression 99.4, baseline sample 95.0. Met.
- **ACC-4 (target: 90 percent of note errors in flagged bars, with at most 10 percent of bars flagged, exact pairs):** development 92.4 percent with 4.8 percent of bars flagged, regression 94.4 with 5.5. Met.
- **On the baseline sample, ACC-4 is 74.2 percent** (6.1 percent of bars flagged). The sample is stratified by genre and texture, so it gives more weight to the kinds of score where errors come in blocks the rules do not name. The target holds on the full set, not on every subset.
- **Real-world pairs:** 45.6 percent, because of the one-line percussion staves described in Stage 1.5.

## Comparison with the baselines (355-pair sample)

- **Note accuracy:** omr 97.4 percent; Audiveris 86.3; homr 55.9; the better of the two for each file 89.1.
- **Files at 99 percent or better:** omr 268 of 355; Audiveris 59 of 354; homr 100 of 340.
- **Structurally correct:** omr 71.8 percent; Audiveris 22.5; homr 17.7.
- **Mean OMR-NED (lower is better):** in notes and rests, omr 0.046, Audiveris 0.226, homr 0.256. In all objects, omr 0.128, Audiveris 0.340, homr 0.419.
- **Real-world pairs:** omr 93.0 percent; Audiveris 80.5; homr 63.9. Structurally correct: omr 65.0 percent; Audiveris 35.0; homr 30.0.
- **Text:** the baselines score 0 on lyrics, words and chord symbols. omr scores 95.7, 67.8 and 80.5 percent on exact pairs.
- **Speed:** omr about 0.6 seconds a page; Audiveris 21; homr 27.

## Sibelius, Finale and Dorico output (the gate's inspection item)

20 of the 21 files converted. The 21st is the scan (Type C), and it was refused with the planned message. With no ground truth, the measure here is the share of bars where no staff is flagged ("high confidence" in the report). It is a rough guide to quality, not an accuracy figure.

- **Exported directly by the program, Type A:** Dorico Valse Russe 90 percent, Jagdlied 88, Eine kleine Nachtmusik 87, Carnaval de Venise 77; Sibelius 2021 duet 100, Sibelius 5 (`concert_komplet`) 68; Finale on macOS (Bologne quartets) 73. One file breaks this pattern: Dorico 6.2's The Planets, 31 parts and 191 pages, has 0 percent. Its many hidden staves are a likely cause, but it has not been checked.
- **Printed to PDF through the Windows printer driver, fonts kept (most of them renamed):** Mozart Ave verum (Finale) 0 percent, read as 20 parts where the score has far fewer; Golliwogg (Finale) 6; Debussy Images (Sibelius) 9; Mendelssohn concerto (Sibelius through Distiller) 8; Tchaikovsky (Sibelius) 31; Mozart Fantasia (Finale) 38.
- **Printed to PDF with the music as outlines (Type B):** Mozart fugue (Finale) 4 percent; Mozart clarinet concerto 20; Wilbye madrigal (Sibelius) 25; Scarlatti woodwind quartet (Dorico through Ghostscript) 66.
- **Older exports:** Finale 2003 (Maestro, through Distiller) 30 percent; Sibelius 8 (Opus) 20.
- **What this shows:** symbols are named in all of these files (Stage 1.1), but structure and rhythm often fail on the printed-to-PDF ones. The likely causes are not yet known. Two examples are the part count in the Ave verum and the systems in The Planets. This is the commonest kind of file on IMSLP, so it matters for users.

## Options for the owner

1. **Keep working before sign-off.** Add stages aimed at the two gaps. Structure first: bar counts, clefs, repeats, endings and navigation, using the development mismatches. Then LilyPond and Verovio notes, and the printed-to-PDF commercial files. The figures say MuseScore notes are close; structure on every engraver, and the other engravers' notes, are not.
2. **Sign off with the shortfall as known limits.** The gate would be changed to the figures reached. Phase 2 (scanned pages) would start with these limits carried forward.
3. **Change the gate's scope.** For example, measure ACC-1 on MuseScore output and the real uploads only, and treat LilyPond and Verovio as stress tests. Even then, notes are 98.1 percent and structure about 85 percent on the development set, so the gate would still not be met.

Recommendation: option 1, with structure as the first target. It is the larger gap, the mismatch counts show where to start, and a reader that gets bars, repeats and endings wrong also gives the braille reader the wrong layout. Before that, the real-world clef artefacts should be confirmed. If the PDMX MusicXML leaves out printed clef changes, the real-world structure figure should be corrected in the harness or the pairs.
