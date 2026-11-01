# Raster penalty triage (Stage 2.9)

The errors that reading a page image adds to reading the same page from its PDF, sorted by cause. Errors the PDF reading makes too are not here: they belong to the vector ranking in `error-triage.md`.

## Method

`scripts/triage_raster.py SET VERSION` reads each pair of a raster set six ways, from the saved detections and Engine 2 readings:

- vector: the pair's PDF alone;
- symbols: the symbols found in the image, with the PDF's lines and text;
- lines: the lines found in the image, and the staves they give, with the PDF's symbols and text;
- text: the text read from the image, with the PDF's symbols and lines;
- engine 1: the whole image reading with Engine 1 alone;
- both: the whole image reading with the two engines combined, as `omr convert` reads an image.

Each reading is scored against the ground truth, and its note errors are counted for each staff bar of the truth. A staff bar where "both" has more errors than "vector" carries part of the raster penalty. Its cause is the swap, or the swaps, that bring errors there. It is "engine 2" when Engine 1 alone has no more errors there than the PDF, so the combining took Engine 2's reading wrongly, and "together" when only the whole Engine 1 reading does. For a staff bar the symbols spoil, the detections there are matched against the labels the detector was trained on. Labels it missed, labels found as another class, labels at the wrong height and detections with no label are listed by class.

## First ranking: development set at 200 dpi, every 6th pair (1 November 2026)

Run `evaluations/s36-triage-g200` (294 pairs, 230,447 notes, 43 minutes on 3 workers).

Note errors by reading:

- vector 2,306 (99.00 percent of notes right);
- symbols 4,887 (97.88);
- lines 7,037 (96.95);
- text 4,403 (98.09);
- engine 1 9,557 (95.85);
- both 4,094 more than vector in the staff bars it spoils, 5,063 in all (97.80).

Engine 2 saves more than it costs: Engine 1 alone loses 7,251 notes to the image, the combined reading 2,757.

Errors the image adds in the combined reading, 4,094 in 1,175 staff bars, by cause:

1. Symbols alone: 1,201 (29 percent). With the other swaps as well: 1,523 (37 percent).
2. Engine 2 chosen wrongly: 1,129 (28 percent). Mostly pitch, onset and missing notes, in long runs of bars on one staff.
3. Lines alone: 1,042 (25 percent). With the other swaps as well: 1,536 (38 percent). Mostly pitch, then duration and missing notes.
4. Text, alone or with the other swaps: 479 (12 percent). Mostly onsets and durations together.

The loss is concentrated. 138 of the 294 pairs have any error added. The worst 5 pairs hold 38 percent of the added errors, the worst 10 hold 57 percent, the worst 20 hold 73 percent and the worst 50 hold 91 percent. By engraver: MuseScore 3 1,807, MuseScore 4 1,085, LilyPond 782, Verovio 420.

Detector faults in the staff bars that the symbols spoil (errors shared among the faults found there). Missed sixteenth rests 154 errors, extra black noteheads 120, extra dots 53, missed dots 42, missed black noteheads 37, extra half noteheads 36, extra flats 34, cross noteheads read as text 22 or missed 18, double flats read as flats 17, tuplet 4 read as 5 or 6 26. Together these explain under half of the symbol errors. In 741 errors the symbols spoil, no detector fault lies in the staff bar. The cause there is in turning detections into symbols (anchors, sizes, flag directions, beams taken for rests) or lies outside the bar.

The detector over all these pages, worst by faults: text boxes (missed 1,840 of 56,083), black noteheads (149 missed, 436 extra of 196,538), staccatissimo (166 of 188 missed or misclassed), tuplet 4 (55 of 55), double flats (34 of 38), tenuto, half and whole rests.

## The worst pairs, with what each points at

- `pdmx-ygdcXBBw6fje` MuseScore 3 base (354 added): symbols. Missed sixteenth rests and half noteheads shift the onsets of two staves.
- `pdmx-7BVm2bkhL5Go` LilyPond (287 added): symbols, mostly durations on two staves, with few detector faults in the bars. Cross noteheads and double sharps are missed. The rest points at the step from detections to symbols.
- `pdmx-XKU7wW67bJ8y` MuseScore 3 base (278 added): Engine 2. Every onset is wrong on one staff from bar 31 to the end; the combining takes Engine 2's reading where it is out of step.
- `pdmx-jiVBTaknDNuh` MuseScore 4 variant (275 added): text. The text read from the image changes onsets and durations on the first staff from bar 1.
- `pdmx-QkFxjWipz93Z` MuseScore 4 variant (259 added): Engine 2. Pitches and missing notes on one part from bar 25.
- `pdmx-bEG6fz8chqsR` MuseScore 3 base (241 added): lines. Pitches on one staff from bar 10, as if a clef or the staff's place were wrong.
- `pdmx-WEpfyNr7yQWL` MuseScore 3 variant (134 added): lines. Durations on the first staff, most likely beams.
- `pdmx-xsKosKgjGnpL` LilyPond (131 added): Engine 2 and lines. Missing and extra notes.

## What this means for the work loop

- Most of the loss is in a few pairs, each with a single fault running over many bars. So the loop is: take the worst pair, find its fault, fix it with a test, rerun the triage sample (about 45 minutes) and rank again.
- Engine 2 being chosen wrongly is a combining fault (`omr.raster.combine`). It needs a better rule for when Engine 2 is out of step or an octave out, not a retrained model.
- Detector faults are about a third of the symbol share, so about a tenth of the penalty. They are worth one retraining run only once the other causes are fixed, with the classes above given more training tiles.
- The text and line causes are fixes in the image reading (`omr.raster.text`, `omr.raster.lines`), shared by both engines.

## The work loop, round 1 (1 November 2026)

What the worst pairs turned out to be, and what was done:

- `pdmx-XKU7wW67bJ8y` (Engine 2): the guitar staff's 3/4 was lost because a 4 detected at 0.33 confidence, 3.4 staff spaces after the real digits, was taken as the time signature nearest the music, and a single digit is no time signature. With no bar length, the fullness rule could not see Engine 2 placing the second voice after the bass note, past the end of the bar. Fixed twice over: a last group of digits that is not a whole signature gives way to the group before it (`structure.staff_times`), and the combining takes the other parts' time signature where a part has none (`combine.time_in_force`).
- `pdmx-QkFxjWipz93Z` (Engine 2): octaves E5 and E6 on a bass staff read by Engine 2 as a single B6. Both readings had the same range faults, and the tie went to Engine 2 because the chords had different note counts. "Chords differ" now needs one reading's pitches at each onset to lie among the other's (`combine.chords_differ`).
- `pdmx-jiVBTaknDNuh` (text): MuseScore 4 writes the 4 of quadruplets as text, so the text swap loses them. On the image they must come from the detector, which misses the tuplet 4 class (55 of 55 labels missed or misread). For the detector list.
- `pdmx-bEG6fz8chqsR` (lines): ledger lines through or touching a notehead lay 90 percent inside the notehead's box, so the image's line finder took them as part of the symbol, and notes far below the staff lost their ledger lines and their staff. Noteheads no longer mask the level-line search (`lines.find_lines`, `head_boxes`). Some ledger lines are still lost where a natural or a tie touches them.
- `pdmx-WEpfyNr7yQWL` (lines): the curl of a down flag was taken as a short stem, and the lowest note of a chord attached to it, losing its flag. A vertical line further than 0.4 staff spaces into a flag's box is now part of the flag.
- `pdmx-xsKosKgjGnpL` (lines): LilyPond sets beams on the staff lines. A beam whose top is the top staff line, with nothing above it, lost the line's rows when the staff lines were taken away and was then too thin to be a beam, so sixteenths read as eighths. Column runs in the beam search now take back the rows of a staff line they touch, and a run too tall for one beam is cut at the line rows inside it (`lines.fit_to_lines`).
- `pdmx-ygdcXBBw6fje` (symbols): sixteenth rests printed on top of the other staff's chord (a collision in the engraving) are not detected, so the second voice's notes move earlier. For the detector list, and possibly a rule placing a voice by the notes of the other staff at the same x.
- `pdmx-7BVm2bkhL5Go` (symbols): on a LilyPond drum staff the detected cross noteheads are about 0.3 staff spaces wider on each side than their ink (the training labels have only 1 pixel of padding, so the detector learned it, perhaps from fonts with wider cross heads), so stems and beams at their edges are missed and sixteenths read as quarters; also double sharps missed. To do: trim a detected notehead's box to the ink inside it.

The detector list so far (for one retraining run if detector faults come to the top): tuplet 4, rests in collisions, double flats, staccatissimo, cross noteheads, tenuto.

Triage rerun with the first four fixes (time digits, time in force, chords, ledger lines), `evaluations/s36-triage-g200-b`: combined reading 5,063 to 4,464 errors (97.80 to 98.06 percent), Engine 1 alone 9,557 to 8,480; errors the image adds 4,094 to 3,485; the PDF reading unchanged; 32 pairs better, 8 worse by 6 errors or fewer.

The beam fix first let every column run that touches a staff line take its rows back. On the line check (regression set, 200 dpi) that cost the guitar piece `pdmx-4viYqFUrsJaX` 44 notes in two engravings: a sloping beam crossing the lines grew in some columns only and no longer fitted as one beam. Only runs too thin for a beam take the rows back now.

Line check, regression set at 200 dpi (`evaluations/s36-lines-base` against `s36-lines-new2`, the PDF's symbols with the image's lines): notes lost to the image's lines 1,057 to 834 of 72,960; beams found 93.98 to 94.95 percent; extra stems 267 to 101; 62 pairs better, 6 worse by 4 notes or fewer.

Triage rerun with all six fixes, `evaluations/s36-triage-g200-c`: combined reading 5,063 to 4,202 errors (97.80 to 98.18 percent of notes right); Engine 1 alone 9,557 to 7,080; the lines swap 7,037 to 4,576; errors the image adds 4,094 to 3,225. The PDF reading is unchanged. 41 pairs better and 6 worse with both engines (by 6 errors or fewer); Engine 1 alone is worse on `pdmx-3Q4Q7xxgEuv7` (31) and `os-lc6189616` (24), not yet looked at. Ranking now: symbols 36 percent, Engine 2 chosen wrongly 23, lines 21, the rest mixed.
