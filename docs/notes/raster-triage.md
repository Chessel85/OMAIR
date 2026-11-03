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

## The work loop, round 2 (1 November 2026)

Fixes, each found on a pair and checked there first, then on the triage sample:

- `os-lc6189616` and `pdmx-3Q4Q7xxgEuv7` (lines; worse with Engine 1 alone after round 1): once noteheads no longer masked the level-line search, the flat top and bottom of half and whole noteheads were taken as short ledger lines. A level line lying inside a notehead's box, sticking out of it by no more than 0.05 staff spaces on either side, is the head's rim (`lines._head_rim`). Real ledger lines stick out past the detected box by 0.2 to 0.4 spaces on both sides on MuseScore 3 (measured on `pdmx-bEG6fz8chqsR`) but only 0.1 under Verovio's chords, rims by -0.1 or less; the first margin, 0.15, dropped Verovio's ledger lines (see the rerun below). With the image's lines alone: 77 to 18 and 71 to 16 errors, better than before round 1 (42 and 25).
- `pdmx-7BVm2bkhL5Go` (symbols, LilyPond drums): cross noteheads are now cut to the ink inside their boxes, leaving out rows inked most of the way across (staff and ledger lines), so the stem at a head's tip is at its edge (`names.trim_to_ink`). Detected boxes were 0.28 spaces too wide on each side, 0.02 after. Combined reading: LilyPond 384 to 52 errors (Engine 1 alone 359 to 34, under the PDF reading's 98); the same piece's other engravings, outside the sample, MuseScore 3 343 to 66 and 371 to 122, MuseScore 4 179 to 39 and 269 to 89, Verovio unchanged.
- `pdmx-QkFxjWipz93Z` and `pdmx-bEG6fz8chqsR` (Engine 2): Engine 2 reads a crop 4 staff spaces past a part's outer staff lines, and notes beyond that come out at the crop's edge (a run of D5s for octaves up to E6 on a bass staff, B2s for low notes on a treble staff). Engine 2's notes 9 or more steps above the part's top staff or below its bottom one now count as out of range against it (`combine.REACH`); Engine 1's limit stays 12 steps. Combined: 248 to 98 and 339 to 245.
- `pdmx-bEG6fz8chqsR` (lines): ledger lines through a notehead, or with a flat touching one end, were lost, and notes six or seven ledger lines down lost their staff. For the level-line search each notehead's box is cleared and its rows redrawn where ink lies just outside the box on both sides (`lines.through_heads`), and two rows of a short line (3 staff spaces at most) join when one lies inside the other with an end in common and 80 percent of the span (level lines only: it moved a hairpin's arm in the test). With both, 192 errors (339 before round 2).
- `pdmx-AcZ5nsmxvJxs` (lines): MuseScore 3's octave line at 200 dpi has dashes half a space long with gaps of one pixel, under the 0.2 space the dashed-line search wanted, so its notes read an octave low. Gaps of a pixel are allowed. Combined 161 to 107, the lines swap 129 to 65.

Found on the way: 10 Verovio development pairs and 3 check pairs (all three resolutions and black and white) were made into images on 17 October from PDFs re-exported on 25 October when their key changes were fixed ("keys fixed" in their metadata), so the image and the truth disagree (`pdmx-x8AfoFXDkxGH`: the image prints a sharp where the PDF and the truth have a flat; `pdmx-WojYayVMxXkk` is another). They are remade.

Looked at and left for the detector list: double-dotted chords in MuseScore 4 (`pdmx-m7LEvVuSNSLH`), where the columns of dots give extra detected dots; tuplet numbers MuseScore 4 writes as text (`pdmx-TQZXkjDhLjeG`), which the text reading misses but the detector finds, so they cost the text swap and not the whole reading.

Triage rerun, `evaluations/s36-triage-g200-e`: combined reading 4,202 to 3,392 errors (98.18 to 98.53 percent of notes right); Engine 1 alone 7,080 to 6,275; the symbols swap 4,878 to 4,475; the lines swap 4,576 to 4,075; errors the image adds 3,225 to 2,415. Leaving out the remade Verovio pairs, combined 659 fewer errors and the lines swap 446 fewer. Pairs worse with both engines, each looked at:

- `pdmx-Euz4ubE4Jq2x`, `os-sq8437358`, `pdmx-zqEDhMsuu93i`, `pdmx-iXeWP9A5EXgB` (all Verovio): Verovio's ledger lines under chords stick out of the head's box by only 0.1 staff spaces, inside the rim margin of 0.15, so they were dropped and the notes above them lost (a chord F3, C4, F4 on a bass staff read without its F4; Engine 1 then doubted, and Engine 2, with the wrong clef, chosen). The margin is now 0.05. Combined: 20 to 1, 19 to 7, 107 to 74 (94 in run c), 8 to 5; the rim pairs and `pdmx-bEG6fz8chqsR` unchanged.
- `pdmx-TTzehLqU5izw` (lines): the steps of a sloping beam joined by one end into a short thick level line, which the reader, given it as a line, took for a second beam at a stem, so an eighth read as a sixteenth. A level line lying within a found beam is now dropped (`lines._in_beam`). 5 to 0.
- `pdmx-ygdcXBBw6fje` (lines): the rows of long, shallow cross-staff beams joined by one end. The join is now for runs of 3 staff spaces or fewer (ledger lines). The lines swap 87 to 63 (71 in run c). Engine 1 alone stays 53 worse than run c, in bars with a sixteenth rest printed on another chord (the collision already on the detector list): there, scraps of level line found inside the collided notehead used to set the second voice's timing right by chance, and the rim and notehead rules now drop them.
- `pdmx-KbWx8rTYY93p` (Engine 2's reach): a bass staff turning treble halfway through a bar was judged under the treble clef for the whole bar (the clef "at the bar's start" was the last one in it), and with the tighter limit its C3s counted against Engine 2's right reading. A note now counts as out of range only if outside the staff under every clef in force in the bar. Combined 19 to 15 (13 in run c).

Triage rerun with these four corrections, `evaluations/s36-triage-g200-f`: combined reading 3,316 errors (98.56 percent of notes right); Engine 1 alone 6,043; the lines swap 3,845; errors the image adds 2,336. Against run c, leaving out the remade pairs: combined 735 fewer, Engine 1 alone 878 fewer, the lines swap 676 fewer; worse only `pdmx-ygdcXBBw6fje` (above) and pairs by 7 errors or fewer. Against run e, `pdmx-wrbTBKxwZW9M` is 8 worse: a bar of ties and voices read wrongly either way (6 errors with the beam's level lines kept, 8 without), the rest in bars the PDF reading also gets wrong.

- `pdmx-jiVBTaknDNuh` (text, then Engine 1): MuseScore 4 prints a quadruplet's 4 in italic in a gap of its bracket, and the detector misses it (44 of the 55 tuplet 4s in the sample), so four quarters in the time of three read as plain quarters in nearly every bar. Where a bracket's halves (level lines, nearly level thin lines, or the span of a curve when a half is traced with its hook) end and start again 0.8 to 3 staff spaces apart at one height, with ink between and no notehead or tuplet number there, the ink is read by OCR, and a single digit 2 to 9 read with a score of 0.9 or more is a tuplet number (`reading.bracket_numbers`). Needing a half on both sides keeps out an octave line's 8 and a volta's number. On page 1, 6 of the 7 missed numbers found, no false ones on 8 pages of other pairs. Engine 1 alone 218 to 138, combined 237 to 171. Two more faults kept the vector reader from finding these brackets: a half traced with its hook as one curve (the reader looks for brackets among straight lines), now made a straight line once its number is read (`reading._straighten`); and a gently sloping half read in two pieces, a level one and a sloping one, so the bracket seemed to start after its first note, now followed outwards through pieces that carry on from its end (`notation._continued`, which PDFs pass through too). With both: Engine 1 alone 84, the lines swap 101 to 50, combined 109; five other pairs, the PDF reading included, unchanged. The text swap is unchanged, as it takes the PDF's symbols. Left on this pair: Engine 2 chosen where Engine 1, right, has a doubt in the bar (the fourth part, bars 13 and 21, 20 errors).


More fixes, found while checking the bracket numbers and the pairs left over:

- `pdmx-QkFxjWipz93Z` (symbols, then Engine 1): the ledger lines of neighbouring notes passed as the two halves of a bracket, and a stem with ledger stubs in the gap between them was read by OCR as a 4 (92 percent sure), making a bar of sixteenths four in the time of three. A would-be half centred on a notehead and at most 1.5 staff spaces wider than it is a ledger line, not a bracket (`reading._ledger`). Engine 1 alone 86 to 76, as in run f; `pdmx-jiVBTaknDNuh` keeps its gain.
- `pdmx-jiVBTaknDNuh` (combining): the doubts that sent bars 13 and 21 of the fourth part to Engine 2 were unsure staccatos. The combining's weights were set in Stage 2.7 on the flag file's rules, which leave markings out, but the reading counted every flag of Engine 1. Only the flag file's rules count now (`sequence_reading.combine_notes`). Bar 21 is Engine 1's again; bar 13 keeps a "staves disagree" flag, so Engine 2 there. Combined 109 to 99; `pdmx-AcZ5nsmxvJxs` MuseScore 3 variant 107 to 104.

Triage rerun with both, `evaluations/s36-triage-g200-i`: combined reading 3,122 errors (98.65 percent of notes right); Engine 1 alone 6,043 to 5,907; the lines swap 3,845 to 3,795; the PDF reading unchanged at 2,306 (the bracket pieces in `notation._continued` change nothing there). Against run f no pair is worse with Engine 1 alone, and with both engines only `os-lc6895581` (5 errors) and two pairs by 1. There Engine 1 reads a B as B flat in a bar whose only doubt is an unsure pedal mark, which used to send the bar to Engine 2 by luck.

- `pdmx-QkFxjWipz93Z` (combining, range): octaves eight to ten ledger lines over a bass staff are really there, and Engine 1 reads them, but its notes past six ledger lines counted against it, more of them than against Engine 2's run of D5s at its crop's edge, so Engine 2 was kept. Range is now judged on Engine 2's reading only: Engine 1 reads ledger lines from the image. In Stage 2.7 the range rule chose wrongly more often than rightly (15 against 31) before Engine 2's reach was added. All five engravings of the pair, combined: 158 to 139, 150 to 133, 95 to 67, 98 to 66, 150 to 89. Triage rerun, `evaluations/s36-triage-g200-j`: combined 3,122 to 3,088, no pair worse.

Looked at and left: `pdmx-iqZcDKbuJuSA` MuseScore 4 variant, where Engine 2 leaves the upper notes out of whole-note chords and the chord rule keeps its reading (combined 33, Engine 1 alone 21). In the Stage 2.7 rows (`s32-combine-all-c`), where both readings fill the bar and one only is right, the reading with more notes is Engine 1's in 2,212 staff bars and Engine 2 is right in 1,580 of them, so Engine 1's extra notes are mostly stray and the rule stays.

- `pdmx-AcZ5nsmxvJxs` (combining): in a bar of an eighth rest and twelve 32nd notes, Engine 2 saw only the rest, and Engine 1's right reading lost on a doubt. A reading with no notes where the other has some now has a fault ("silent"). In Stage 2.7, where only Engine 1 had a note at an onset it was right 178 times against 36. Triage rerun, `evaluations/s36-triage-g200-k`: combined 3,088 to 3,080 (`pdmx-AcZ5nsmxvJxs` 11 better; `pdmx-bgcj8AadN88c` Verovio 3 worse, with notes in two bars that the PDF reading has too).

- `os-lc5057804` (Engine 2, octave signs): homr reads pitches as printed and does not read octave signs, so under an 8va line Engine 2 read an octave low, and won the bars where Engine 1 had a doubt (here "an octave sign between two staves may belong to either"). Engine 1 now keeps on each note the octaves a sign moved it (`Note.shifted`, not compared), and each of Engine 2's notes takes the shift of Engine 1's note nearest it in time in the same staff bar (`sequence_reading.octave_signs`). MuseScore 3: combined 57 to 13, under Engine 1's 20. Triage rerun, `evaluations/s36-triage-g200-l`: combined 3,080 to 3,047; `pdmx-bUDYXQtSaaJi` MuseScore 4 12 worse, where Engine 1 (and the PDF reading) took an 8 between two systems for an 8vb under the upper system's bass staff, and Engine 2 now copies it.
- `pdmx-bUDYXQtSaaJi` (octave signs, PDF reading too): an octave mark between two systems now belongs to the nearer one (`notation.octave_marks`), so the 8 over the lower system's top staff is an 8va there and not an 8vb on the upper one's bass staff. PDF reading 30 to 2, Engine 1 alone 54 to 26, combined 48 to 20.
- `pdmx-bEG6fz8chqsR` (lines): two more ways a ledger line under a low note was lost. Its rows end a pixel apart, so neither lay inside the other and they did not join; and a natural touching one row makes that row 0.8 spaces longer, under the 80 percent the join needs. Each row alone was then dropped as a slice of something thicker. Rows of a short line now nest to within 2 pixels, and may differ at the far end by up to a staff space if they still share 65 percent. Lines swap 203 to 175, Engine 1 alone 215 to 188, combined 179 to 156.
- `os-lc6117552` (symbols): the detector found a sharp at 35 percent on a tremolo stroke, free of notes on its step, and the reader took it for a key change to one sharp, so five bars of three flats lost their flats. An accidental detected with less than 0.5 confidence is now left out of key signatures (`structure.KEY_SURE`). Combined 38 to 0, Engine 1 alone 52 to 14.

Looked at and left for the detector list: `pdmx-SxQW82buWPXe` MuseScore 3 variant, where the detector reads the 5 of 5/8 as an 8 (80 percent sure) and the 1 of 1/8 as a 4, so the bars and their notes go out of line (27 bars against 24, 37 notes extra). Reading time signature digits by OCR as a check is a possible later step; `pdmx-8paH5cERYZWm` MuseScore 3 variant, a cadenza-like bar that both engines read past its end.

Triage rerun with the looser ledger join, `evaluations/s36-triage-g200-m`: the lines swap 3,795 to 3,453 errors, Engine 1 alone 5,907 to 5,565, combined 3,047 to 2,983 (98.71 percent of notes right). Most of the gain is on Verovio, whose ledger rows often end a pixel apart (`pdmx-WojYayVMxXkk` 73 fewer with Engine 1 alone, `pdmx-3M2FCkVcJu2Z` 43); no pair is worse by more than 2.

Triage rerun with the octave mark between systems and the sure key signatures, `evaluations/s36-triage-g200-n`: combined 2,983 to 2,917 errors (98.73 percent of notes right); Engine 1 alone 5,565 to 5,499; the PDF reading 2,306 to 2,278 (the octave mark rule is in the vector reader); no pair worse.

Against run f, the night's fixes together: combined 3,316 to 2,917 errors, Engine 1 alone 6,043 to 5,499, the lines swap 3,845 to 3,425, the symbols swap 4,475 to 4,408, the PDF reading 2,306 to 2,278.

- `pdmx-TQZXkjDhLjeG` (lines): a sextuplet bracket between two staves, its hooks pointing down, was given to the upper staff, whose groups of six sixteenths took the ratio. A bracket's hooks are about a staff space long, under the vertical lines' least length of 0.8 spaces, so the reader found none. For each tuplet number between two bracket halves, the ink at the halves' outer ends is now followed up or down for a hook (`reading.bracket_hooks`). The lines swap 71 to 27, Engine 1 alone 82 to 38, combined 82 to 38.

Triage rerun with the bracket hooks, `evaluations/s36-triage-g200-o`: the lines swap 3,425 to 3,350, Engine 1 alone 5,499 to 5,424, combined 2,917 to 2,850 (98.76 percent of notes right); no pair worse. Against run f, all the night's fixes: combined 3,316 to 2,850, Engine 1 alone 6,043 to 5,424, the lines swap 3,845 to 3,350.

Left on the list: `pdmx-ygdcXBBw6fje` (collision rests, detector), `pdmx-m7LEvVuSNSLH` and `pdmx-rGgnvo4oUibj` (augmentation dots missed or taken for noteheads, detector).

### Round 3 (2 November 2026)

- `pdmx-C1P12SpiRUyB` MuseScore 3 variant (symbols, detector): the modern 2/1 after the incipit's cut time has its 1 inside the treble clef. The detector found the 2 alone in the treble staves (so cut time stayed in force) and read the 1 as a 4 in the bass staves, so the notes were fitted to bars of 2/2 or 2/4 and put a beat or two early. Time signatures on page images are now checked against the notes (`omr.raster.metre`, in `raster-reading-spec.md`): where a time signature leaves a quarter or more of its bars unfilled, other values are tried, and one that at least halves the unfilled bars is kept. The symbols swap 92 to 5. Not caught: `pdmx-SxQW82buWPXe` (a 5/8 read as 8/8 for one bar in a run of changing metres).
- `pdmx-iqZcDKbuJuSA` MuseScore 4 variant (Engine 2): where the engines differ only in their chords, Engine 2 is preferred, and here it drops the top notes of three-note chords on a bass staff. Split by which engine has the extra notes, on the Stage 2.7 rows (`evaluations/s32-combine-all-c`): where Engine 1 has more, Engine 1 is right in 249 staff bars and Engine 2 in 252; where Engine 2 has more, Engine 2 in 667 and Engine 1 in 151. So the preference is left as it is.

Triage rerun with the time signature check, `evaluations/s36-triage-g200-p`: the symbols swap 4,408 to 4,289, Engine 1 alone 5,424 to 5,327, combined 2,850 to 2,806 errors (98.78 percent of notes right); no pair worse. Besides C1P12 (combined 49 to 10), `pdmx-3i2MPmmDHz2f` gains 4.

- `pdmx-dNVu4Bv7QyDP` MuseScore 4 (lines): "a tempo" over each staff is drawn on a white ground, which cuts the barline in the image; the pieces stop between the staves and were not taken as a barline, so two bars ran together in all four parts (24 notes). Vertical pieces at the same x with a text box over the gap are now joined (`lines.across_text`, in `raster-lines-spec.md`).

Triage rerun with the joins across text, `evaluations/s36-triage-g200-q`: the lines swap 3,350 to 3,275, Engine 1 alone 5,327 to 5,254, combined 2,806 to 2,687 errors (98.83 percent of notes right). `pdmx-wrbTBKxwZW9M` MuseScore 4 gains 91 and `os-lc5105228` Verovio 14, besides dNVu's 24. One pair worse, `pdmx-ygdcXBBw6fje` MuseScore 3 (combined 10 more, Engine 1 alone 50), with no join made on it: the join returned the vertical lines sorted top down, and the reader's choices downstream depend on their order. The lines now keep the order they came in, and a join also needs the gap to be mostly white down the line's column (an up and a down stem on one notehead have the notehead between them); ygdc reads as before. The order counts in `notation.find_stems`, which makes the stems in the order of the lines, and `_share_heads` then settles a notehead touching two stems partly by that order. That is settled below (`pdmx-wrbTBKxwZW9M`).
- `pdmx-1ju9j9N3tc1a` MuseScore 3 (symbols and lines): pages 4 and 5, level, hold a cadenza whose long beams all rise one way, and the tilt search measured them as tilted by 1.4 degrees. The image was turned, and every symbol read from it lay about half a staff space off: noteheads missed their stems and beams, and the bars came apart (144 against 141). The tilt is now measured on thin ink only (`lines.tilt`, in `raster-lines-spec.md`). The symbols swap 196 to 101 (the PDF reading 80). Pages whose tilt changes are detected again, as their saved detections are keyed by the turned image.

Triage rerun with all three (time check, joins across text keeping the order, thin-ink tilt), `evaluations/s36-triage-g200-r`: against run p, the symbols swap 4,289 to 4,194, the lines swap 3,350 to 3,246, Engine 1 alone 5,327 to 5,223, combined 2,806 to 2,710 errors (98.82 percent of notes right); no pair worse. Against run q, 1ju9 gains 58 and ygdc's loss is gone, but wrbT's gain of 91 is gone too: no join is made on it, so the gain in run q came from the lines being sorted top down.

- `pdmx-wrbTBKxwZW9M` MuseScore 4 (the PDF reading too): one notehead holds two voices, a dotted quarter stem up and a beamed eighth stem down. Both events stand at the same place, so the dot went to whichever came first, and that was the order of the stems, which was the order of the lines. With the eighth dotted every bar of the pattern came apart (the PDF reading 117 errors, 24 with the lines in the other order). The dot now goes to the longer note, and `find_stems` takes the lines left to right, so the reading no longer depends on their order (`notation-spec.md`). The PDF reading 117 to 0; the lines swap 124 to 30.

Triage rerun, `evaluations/s36-triage-g200-s`: against run r, the PDF reading 2,278 to 2,156, symbols 4,194 to 4,063, lines 3,246 to 3,152, Engine 1 alone 5,223 to 5,122, combined 2,710 to 2,619 errors (98.86 percent of notes right). Pairs changed besides wrbT: 3 slightly better in the symbols swap, ygdc 1 worse in it; against run p no pair is worse.
