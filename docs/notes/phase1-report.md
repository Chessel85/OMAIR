# Phase 1 report: vector PDF to MusicXML

Gate review for `docs/plans/phase1.md` (Stage 1.9), 17 October 2026. Plain headings and lists only.

## Decision

Phase 1 is closed. The owner signed it off on 17 October 2026 with the shortfall below carried forward as known limits: the gate (ACC-1) is not met, but the remaining errors are spread over many small causes, each worth less than the last, so further work in Phase 1 has a poor return. Work on the vector reader can resume at any time from the ranking in `docs/notes/error-triage.md`. Phase 2 (clean raster input) shares the notation assembly, the musical rules and the MusicXML writer with the vector path, so fixes there serve both.

## Summary

- **Notes: about 98 percent against 99.** Development set 97.8 percent, sealed check set 97.7, regression set 98.4, real uploads 96.5. Without the LilyPond pairs whose PDF does not show the ground truth (see below), the development set reads at 98.3 and the check set at 98.5.
- **Structure: 80 to 84 percent against 95.** Development set 80.4 percent, check set 83.1, regression set 80.5, real uploads 65.0. This is the larger gap.
- **The check set agrees with the development set.** It is 100 new scores (593 pairs) that were never looked at while the reader was tuned. Its note accuracy is within 0.1 point of the development set's and its structure is 2.7 points better, so the Stage 1.8 fixes are general, not fitted to the development files.
- **Speed is far inside the target:** 0.56 seconds a page on the CPU, against 10 (OP-3).
- **ACC-6 (dynamics and hairpins) is met:** 93.1 percent on the development and check sets, 99.4 on the regression set.
- **ACC-4 (flagging) is met on the regression set only.** See its section below.
- **Against the baselines,** on the 355-pair sample: 97.4 percent note accuracy (at the first review; the reader has improved since) against 86.3 for Audiveris and 55.9 for homr. Structure 71.8 percent against 22.5 and 17.7.

## What was run

- **Development set:** all 1,778 pairs, `evaluations/s18-run3-development` on the corpus drive, with `errors-s18-run3.txt` and `triage-s18-run3.txt` beside it.
- **Sealed check set:** all 593 pairs, `evaluations/s18-check`, scored once for this review.
- **Regression set:** 256 pairs, `evaluations/s18-run3-regression`.
- **Real uploads:** the 40 MuseScore.com pairs, `evaluations/s18-run3-realworld`.
- **Commercial files:** `omr convert` on the 21 IMSLP files, `evaluations/s18-commercial-omr`.
- No file failed in any run.

## ACC-1: note accuracy (target 99 percent)

- **Development set:** 97.8 percent. MuseScore 4 98.7 and 98.8, MuseScore 3 98.8 and 98.8, Verovio 96.7, LilyPond 94.9.
- **Check set:** 97.7 percent. MuseScore 3 99.0, MuseScore 4 98.5, Verovio 97.2, LilyPond 93.5. The errors are concentrated: the worst 20 of 593 files hold 62 percent of them, and the worst single file (a faulty LilyPond pair) 18 percent.
- **Regression set:** 98.4 percent.
- **Real uploads:** 96.5 percent. 
- **The faulty LilyPond pairs.** musicxml2ly, which turns the reference into LilyPond input, loses track of time in some scores and moves or drops notes, so the LilyPond PDF shows different music. Pairs with 50 or more of its "Negative skip" warnings that read at least 5 points worse than every other engraving of the same score are counted as faulty: 17 in the development set and 8 in the check set. The lists are `evaluations/lilypond-pairs-development.txt` and `lilypond-pairs-check.txt`. Without them, LilyPond reads at 97.9 percent (development) and 98.6 (check). Whether to drop them is one of the open owner decisions.
- **What is left:** MuseScore output is within about a point of the target. Verovio is 2 to 3 points short and LilyPond 1 to 5, depending on the faulty pairs. The causes still open are listed under known limits.

## ACC-1: structural correctness (target 95 percent)

- **Development set:** 80.4 percent. **Check set:** 83.1 percent; MuseScore 88.5, Verovio 78.0, LilyPond 65.6 (71.8 without the faulty pairs).
- **Regression set:** 80.5 percent. **Real uploads:** 65.0 percent. In 7 of the 14 failing real uploads, the only mismatch is a clef the reader found on the page that the PDMX reference leaves out.
- **What fails:** bar counts, clefs, keys, repeats, endings and navigation, in roughly that order, and many failing files have only one or two mismatches. Part of the gap is the reference rather than the reader: middle barlines, navigation stored as plain words, unprinted repeat counts and missing clef changes. Those are owner decisions (below).

## ACC-6 and ACC-4

- **ACC-6 (target 90 percent, exact pairs):** development 93.1, check 93.1, regression 99.4. Met.
- **ACC-4 (target: 90 percent of note errors in flagged bars, with at most 10 percent of bars flagged, exact pairs):** regression 94.1 percent with 5.4 percent of bars flagged, met. Development 88.3 percent with 4.3 percent flagged, and check 75.0 with 3.1 percent flagged, not met.
- **Why it fell on the development set** (92.4 percent at the first review): the Stage 1.8 fixes removed mostly errors that broke a rule, and so were flagged. What remains is more often a reading that is wrong but consistent, for example a whole bar shifted or a misread tuplet that still adds up. The confidence rules were not grown alongside the fixes, as the plan asked. The flagging rate is low (3 to 5 percent of bars), so there is room to flag more.

## Sibelius, Finale and Dorico output

20 of the 21 files converted. The 21st is a scan (Type C), and it was refused with the planned message. With no ground truth, the measure is the share of bars where no staff is flagged ("high confidence" in the report). It is a rough guide to quality, not an accuracy figure. Workstream D was not started, so changes here come from the general fixes.

- **Exported directly by the program, Type A:** Sibelius 2021 duet 100 percent; Dorico Valse Russe 90, Jagdlied 88, Eine kleine Nachtmusik 87, Carnaval de Venise 78; Finale on macOS (Bologne quartets) 77; Sibelius 5 (`concert_komplet`) 68. Dorico 6.2's The Planets (191 pages, many hidden staves) rose from 0 to 20 percent, but is read as 36 parts where it has 31.
- **Printed to PDF through the Windows printer driver:** Mozart Ave verum (Finale) 0 percent, still read as 20 parts; Golliwogg (Finale) 9; Debussy Images (Sibelius) 10; Mendelssohn concerto (Sibelius through Distiller) 16; Tchaikovsky (Sibelius) 31; Mozart Fantasia (Finale) 43.
- **Printed with the music as outlines (Type B):** Mozart fugue (Finale) 4 percent; Mozart clarinet concerto 23; Wilbye madrigal (Sibelius) 25; Scarlatti woodwind quartet (Dorico through Ghostscript) 66.
- **Older exports:** Finale 2003 (Maestro, through Distiller) 30 percent; Sibelius 8 (Opus) 23.
- **What this shows:** direct exports mostly read well. Printed-to-PDF files, the commonest kind on IMSLP, mostly do not, and their causes are not yet known.

## Known limits carried forward

- **Notes:** unprinted triplets mixed with plain notes; three or more voices on a staff; tremolos; cross-staff tuplets; LilyPond and Verovio octave marks; two parts with the same name where one is hidden.
- **Structure:** clefs read on the wrong line, octave clefs read without their octave, key signatures in some Verovio files, and duplicated instrument names giving extra parts.
- **Flagging:** ACC-4 below target on the development and check sets.
- **Commercial files:** files printed to PDF through a printer driver mostly read poorly (above). Their causes have not been looked into (Workstream D was not started).
- **Markings:** words 48 percent recall on the check set's exact pairs, tremolo marks 0, scoops and non-arpeggio brackets 0, breath marks 72. Writer limits: beams, part groups, transposition, barline styles, four voices at most (Workstream E was not started).
- **Not in the PDF:** systems where every staff is hidden (Verovio draws nothing), and repeat play counts no engraver prints.

## Open owner decisions

These change the figures, not the reader, and do not block Phase 2. Details and counts are in `docs/notes/error-triage.md`, causes 14 to 17 and 19.

1. Drop or redraw the faulty LilyPond pairs, and reject new pairs with many musicxml2ly warnings at export.
2. Treat Verovio files that print one key for parts in different keys as faulty pairs.
3. Count a barline in the middle of a reference bar as a bar boundary.
4. Read D.S., D.C., Fine, coda and segno stored as plain words in the reference as navigation.
5. Compare a repeat's play count only where the page prints one.

## Where to resume vector work

- The ranked causes and the method are in `docs/notes/error-triage.md`, with the tools `scripts/triage_errors.py`, `scripts/make_subset.py` and `scripts/check_lilypond_pairs.py`.
- The work loop is in `phase1.md`, Stage 1.8: fix the top cause with a test, re-run the full development set, re-rank.
- The check set stays sealed: score it only at milestones, never to diagnose.
