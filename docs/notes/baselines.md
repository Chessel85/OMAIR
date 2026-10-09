# Baselines (Stage 9, DEV-4)

Analysis of 7 October 2026. It covers Audiveris 5.11.0 and homr 0.7.0. LEGATO is a development baseline only, at about 18 minutes a page on the CPU, and its results come from two overnight sample runs (`docs/plans/legato-sample-plan.md`), covered in its own section below. All figures use the evaluation spec as of decision 10 (a misread clef is one error).

## What was run

- **Development baseline sample:** 60 development scores, 355 pairs, a seeded stratified sample over the 30 genre and texture groups (`scripts/make_baseline_sample.py`). Run on the night of 6 October with 3 workers, CPU only, a 900-second limit and no musicdiff. Then rescored with the clef rule from the saved outputs.
- **Audiveris retries:** the first run lost 17 Audiveris files to two wrapper faults (see "Wrapper fixes"). After the fix, those 17 pairs were run again (`generated/baseline-sample-audiveris-retry`, 1,800-second limit) and merged with the rest. The Audiveris figures below are the merged ones.
- **Real-world pairs:** 40 real MuseScore.com uploads (`scripts/make_realworld_sample.py`, set `generated/realworld`). Each PDF from the Stage 8 PDMX survey sample is paired with the MusicXML that PDMX gives for the same upload. Only works outside the training pool were used, with the corpus filters, and only PDFs whose pages are all Type A. That left 90 eligible files, and 40 were drawn by seed. They are all MuseScore 3 PDFs (Qt 5.9.8) in the MScore font, mostly one page (26 of 40), and mostly single line or piano (26 of 40). CPDL and the Sibelius and Finale pairs are not available (Stage 8 decision), so these are the only real-world pairs.
- **Clean timings:** 16 pairs of the baseline sample (4 from each engraver, short and long, 45 pages), run one at a time with nothing else running, on the CPU alone (`generated/baseline-timing`).
- **Analysis:** `scripts/analyse_baselines.py NAME=results.json ...` gives the breakdowns below that the harness report does not: failures by kind, spread of per-file accuracy, error mix, tuplets, clef errors, base against variant exports, staff size, pages, score features, structural mismatch kinds, head to head, and seconds per page.
- **Where the results are**, under `evaluations/` on the corpus drive: `baseline-sample-audiveris-clefrule` and `-homr-clefrule` (the first run, rescored), `baseline-sample-audiveris-retry`, `baseline-sample-audiveris-final` and `baseline-sample-homr-final` (the whole sample with the retries merged, scored again with musicdiff), `realworld-audiveris` and `realworld-homr`, and `baseline-timing-audiveris` and `-homr`.

## Wrapper fixes

Two of the 17 Audiveris failures in the first run were wrapper faults, not recognition faults. Both are fixed in `src/omr/baselines/run.py`, with tests.

- **One unreadable page stopped the whole file.** In batch mode, a page where Audiveris finds no staff system (for example a nearly blank last page) makes it abandon the book and write nothing. The wrapper now runs again without the failing pages (`-sheets`), and says which pages it skipped.
- **Large pages were dropped.** Audiveris refuses a page image over 20 million pixels, which a page larger than about A3 reaches at 300 dpi. The wrapper now lowers the resolution for such a file just enough to fit.
- The failure message now gives Audiveris's own warnings, not the Java start-up warning that used to hide them.

With the fixes, 16 of the 17 read. The last is a 28-page file that ran out of time at 30 minutes. The fixes raise Audiveris from 80.0 to 86.3 percent on the sample. Rule for later baselines: read a tool's failures before trusting its average, because a wrapper fault looks just like a weak tool.

## Headline figures

### Development baseline sample (355 pairs)

- **Audiveris:** note accuracy 86.3 percent. 1 file failed (a timeout). Per-file median 92.0 percent. 59 of 354 files reach 99 percent and 132 reach 95 percent. 32 files (9.0 percent) are structurally correct. Dynamics and hairpins recall, exact pairs: 74.0 percent (dynamics 77.7, hairpins 65.6).
- **homr:** note accuracy 55.9 percent, or 61.5 percent over the 340 completed files. 15 failed: 13 timeouts and 1 crash (OpenCV, on a one-page file). Per-file median 91.8 percent. 100 of 340 files reach 99 percent and 155 reach 95 percent. 40 files (11.3 percent) are structurally correct. It writes no dynamics or hairpins.
- **Better of the two for each file:** 89.1 percent. Audiveris is better by more than 5 points on 155 files, homr on 94, and they are within 5 points on 106.

### Real-world pairs (40 MuseScore.com uploads)

- **Audiveris:** 80.5 percent, none failed, per-file median 93.0 percent, 11 of 40 at 99 percent, 30 percent structurally correct.
- **homr:** 63.9 percent, 1 failed (a 30-page file, timeout), per-file median 99.7 percent, 23 of 39 at 99 percent, 22.5 percent structurally correct.
- **One pair is faulty:** `real-cf113e2176a3`, an 8-part choir piece. Both tools miss the same 531 notes and get nearly every other note right, and both find 7 parts where the MusicXML has 8. The PDF almost certainly lacks a part the MusicXML has (MuseScore lets an uploader hide a staff). Without it, Audiveris scores 82.5 percent and homr 64.2 percent. Real uploads can differ from their own data in this way, so a real-world pair where every recogniser misses the same notes should be checked before it is counted.
- On these simpler files the order is the same: Audiveris is steadier, homr is near perfect on short single-staff files and poor on long or multi-part ones. Most Audiveris errors here are missing notes (61.5 percent of its errors), most of them in two chamber files where it found only a bar or two.

### Timing on the CPU alone (OP-2)

- **Audiveris:** median 21 seconds a page (13 to 50), 26 seconds a page overall. A one-page file takes about 21 seconds, of which several seconds are Java start-up. Verovio pages are the slowest (40 to 50 seconds), because they fit more systems on a page.
- **homr:** median 27 seconds a page (20 to 29), 27 seconds a page overall, very even.
- **LEGATO:** 18.4 minutes a page on average over 28 pairs and 55 pages (median 16.8 minutes per pair, range 13.8 to 31.3). One file at a time, 3 threads, nothing else heavy running, so this is usable for OP-2. See "LEGATO" below.
- Under the overnight load (3 at once) both took 2 to 3 times as long. homr's 13 timeouts are all 18- to 35-page files. At 27 seconds a page, those take 8 to 16 minutes even alone, so they are a real speed limit, not an accident of the load.

## Where the baselines fail

### Both tools

- **No text at all.** Lyrics, words (tempo and expression text), chord symbols and fingering are 0 percent for both tools. In a vector PDF all of this is in the text layer.
- **Rhythm more than pitch.** For Audiveris, onset errors (8,194) outnumber pitch errors (5,734). About 13 percent of its wrong notes are tuplet mistakes: 1,077 notes read as tuplets that are not, and 1,611 tuplet notes read as plain notes. For homr it is 17 percent. One missed triplet bracket shifts every later note in the bar.
- **Octave clefs.** Most clef errors involve the small 8 on a treble clef. The commonest Audiveris clef errors are a plain treble clef read as an octave-down one (68), the reverse (49), and a plain treble read as octave-up (28). homr's commonest is an octave-down treble read as plain (73). Under the clef rule each is one error, but before the rule they cost Audiveris 18,304 notes and homr 10,262.
- **Structure is rarely right.** Only 9 to 11 percent of files are structurally correct. Part of this is how the harness counts (see "Restated signatures"), but not all of it.

### Audiveris

- **Unusual fonts and small staves.** MuseJazz 62.6 percent, Petaluma 71.3, Finale Broadway 74.4, against 89 to 91 for Bravura, Emmentaler, Gonville, Leland and Finale Maestro. Staff size 1.5 mm gives 72.7 percent against 87.0 at the default. So the variant exports score lower than the base ones: MuseScore 3 variant 81.1 against base 90.1, and MuseScore 4 variant 83.1 against base 89.0.
- **Engraver matters little once the font is common.** LilyPond 88.0, MuseScore 3 85.5, MuseScore 4 86.0, Verovio 87.1.
- **Invented endings.** 85 files have volta endings that are not in the score, more often in files with lyrics (38 percent of them) than without (17 percent). Lyric lines or verse numbers are a likely trigger.
- **Guitar** is weak: 71.2 percent over 12 files, against 86.7 for the rest.
- Genre and texture make less difference than font: everything falls between 81 and 94 percent.
- Dynamics and hairpins are found three times in four. Hairpin ends are worse (about half are found).

### homr

- **More than two staves in a system.** homr was built for single staves and grand staves. On a string quartet it wrote one part of 410 bars where the score has 4 parts of 163 bars. 25 of the 29 three-part files got the wrong number of parts. Chamber scores score 40.8 percent and small ensembles 43.0, against 86.9 for piano and 87.4 for single line.
- **Long files.** One-page files score 92.6 percent, files of 5 pages or more 48.2 percent. homr reads one page at a time. When it finds a different number of parts on a later page, the joined file goes out of step from there on. The wrapper cannot fix this, because it comes from homr reading the parts wrongly on that page.
- **Missing and extra notes, not wrong ones.** Of homr's errors, 49 percent are missing notes and 31 percent extra notes. Only 20 percent are wrong notes. When it reads a staff, it reads it well.
- **No markings:** no dynamics, hairpins or text. Files with dynamics score 45.8 percent, against 72.3 without. That gap probably reflects that those files are longer and have more parts, not the dynamics themselves.

## Restated signatures (a harness question for the owner)

The harness counts a clef, key signature or time signature that the output restates, with the same value as the one already in force, as a structural mismatch. Audiveris writes the key signature again at many systems, and homr writes the clef and key on every page it joins. This is the main reason so few files are structurally correct: 285 of 354 Audiveris files have a key-signature mismatch.

An experiment (not a spec change) dropped restatements from both files before comparing. Audiveris then has 80 structurally correct files (22.5 percent, against 9.0), and homr 63 (17.7 percent, against 11.3). Files with a key-signature mismatch fall from 269 to 122 for Audiveris (counted on the first-run outputs). Note accuracy does not change.

A restatement is not a change in the music, so the proposal is to add a spec decision: **a clef, key or time signature equal to the one already in force is ignored in both files**. A restated signature is still a fault in the MusicXML for a braille reader if it is printed, but that is a matter for output quality, not structure. This needs the owner's agreement, and Opus should review it, as with the clef rule. If agreed, the rescoring needs no new runs.

## Where the project can win

In order of the size of the gain:

1. **Read the vector PDF, not a picture of it.** Nearly every page is Type A (Stage 8). Both baselines render the page to an image and lose the exact glyphs. Reading glyph codes and positions removes the font and staff-size effects (Audiveris loses up to 25 points on MuseJazz and small staves), and makes the octave-clef and tuplet-digit errors simple lookups, not guesses.
2. **Text from the text layer.** Lyrics, words, chord symbols and fingering are 0 percent for both baselines and are free in a vector PDF. Lyrics matter for the choral and vocal genres in the corpus (141 of 355 files have lyrics).
3. **Rhythm by bar arithmetic (ACC-5).** Onset and tuplet errors are the largest group of wrong notes for Audiveris. Checking that each voice fills its bar would catch most missed or invented tuplets.
4. **Multi-part and long scores.** Systems of three or more staves, and parts that continue across pages, are where homr fails. Audiveris handles them, but at 85 percent.
5. **Dynamics and hairpins (ACC-6).** Audiveris reaches 74 percent against the 90 percent target, homr none. In vector PDFs these are glyphs and lines, so they should be found nearly exactly.
6. **Speed.** Both baselines take 20 to 30 seconds a vector page. The inspector already reads the evidence of a vector page in 0.01 to 0.12 seconds.

## What this means for the gate and Stage 11

- **ACC-1 (99 percent note accuracy on vector PDFs) is far beyond the baselines.** The best is 86.3 percent, and 89.1 percent taking the better tool for each file. Only 17 percent of Audiveris files reach 99 percent. The target stands, because the project reads vector PDFs directly, but no existing tool shows it is reachable.
- **OP-3 (10 seconds a vector page, 60 seconds a raster page).** The baselines take 20 to 30 seconds a page, and they treat every page as an image. A vector reader does not need image recognition, so 10 seconds a vector page looks safe. 60 seconds a raster page is above what both image tools take (26 to 27 seconds a page on this laptop), so it also looks achievable, with room for a heavier model. LEGATO, at about 18 minutes a page, shows that a large model of that kind is ruled out on the CPU. These figures are for Stage 11, which confirms OP-3 and closes OI-2.
- **Real-world pairs are few and simple.** They are 40 MuseScore 3 uploads in one font. Sibelius and Finale output is still not measured (the Stage 8 decision).

## LEGATO (two nights, 7 to 9 October 2026)

A development baseline only, run on a small sample. 28 of the 35 queued pairs were read (55 pages): MuseScore 4 base export (Leland) only, one file at a time, 3 threads, scored with `--no-musicdiff` and the clef rule into `evaluations/legato-sample-final`. The 7 pairs left in the queue (12 pages, the longest ones) were not run, by the owner's decision to close Phase 0. The sample is not the Audiveris and homr sample (that one had 355 pairs over all engravers and fonts), so the comparison is rough.

- **Overall:** note accuracy 83.4 percent, 25.0 percent structurally correct (7 of 28), median file 93.4 percent, lowest 49.2, highest 100. Strict note accuracy 82.8 percent. For comparison, Audiveris 86.3 percent and homr 55.9 percent on their own sample. The first night's partial figure (74.3 percent over 12 pairs) is superseded; pair 12, run again, scored 83.5 percent where the disturbed first run gave 49.2.
- **Errors (all 28):** 7,581 notes; 6,916 exactly right, 404 wrong, 261 missing, 708 extra, 2 clef errors. Of the wrong notes, 295 are pitch only. Staff (99.8 percent), voice (99.3) and tie (98.7) are high. Rests are weak (83.8). Extra notes outnumber missing ones, which is unlike Audiveris and homr.
- **Markings:** dynamics 77.5 percent and hairpins 81.2 percent of exact pairs, fermatas 93.5, accents and staccato 100 (few), slur ends 91.0, trill marks 100 (8). Lyrics 0 of 1,370, words 1 of 106, chord symbols 0 of 138, because LEGATO writes no text.
- **By genre (few files each):** sacred 96.0 percent (4), jazz 93.4 (2), popular 86.6 (5), unlabelled 87.0 (4), folk 82.6 (5), classical 75.1 (5), educational 66.2 (3). By texture: piano 90.1 (9), single line 87.5 (9), voice with piano 75.6 (6), chamber 91.7 (2), small ensemble 68.8 (1), choir 55.9 (1). With these counts the groups say little.
- **Structure:** 7 of 28 structurally correct. Most mismatches are restated clefs and signatures, as for the other two tools (see the restated-signatures question above).
- **Speed:** over the 28 pairs, 18.4 minutes a page on average (55 pages), median 16.8 per pair, range 13.8 to 31.3. One file at a time with nothing else heavy running, so this is usable for OP-2. A 10-staff page is therefore about 18 minutes, which rules a model of this kind out for the shipped product on the CPU alone.
- **Reading:** LEGATO is a better reader than homr on the notes it reads (83.4 against 55.9 percent), close to Audiveris (on different samples). Only one font was tested, so nothing is known about font effects. It is 40 to 50 times slower than the others and writes no text. It confirms that a large image-to-sequence model can reach about Audiveris level, not 99 percent.

### What went wrong on the first night

- Pair 12 was logged as done at 06:41:03 on 8 October with only 39 of 64 bars, and pairs 13 to 35 were marked "failed after 0 minutes" at the same second, with the reason "no output". This came with a critical memory shortage that stopped Claude Code's background shell. The cause is not confirmed. The false failures were cleared and the pairs were run again on the second night, with no problem.
- Lesson: an instant "no output" for many pairs in a row is a disturbance of the machine, not a set of failed files. The runner could treat it as a stop (a change to make if LEGATO is run again).

## Not done, or left open

- LEGATO over the last 7 pairs of its sample (12 pages). Not run: Phase 0 is closed without them.
- The restated-signatures decision (above).
- Audiveris and homr are not added to the regression baseline in CI. CI does not have the tools, and a run takes about half a minute a page. The regression baseline stays with the stand-in recognisers.
- TEDn is still not computed (spec decision 7).

## Comparison with published work

OMR-NED from musicdiff over the baseline sample (0 is perfect; lower is better), from `baseline-sample-audiveris-final` and `-homr-final`:

- **Audiveris:** mean 0.226 in notes and rests, and 0.340 in all objects, over 354 files.
- **homr:** mean 0.256 in notes and rests, and 0.419 in all objects, over 340 files.

These are means of per-file figures over completed files. That is why homr looks much closer to Audiveris here than in note accuracy: its 15 failures are left out, and each of its many good short files counts as much as one of its poor long ones. Note accuracy pools the notes, so the long files weigh more. Both measures are kept, so results can be compared with published work. TEDn is still not computed.
