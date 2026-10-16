# Error triage for Stage 1.8

Workstream A of Stage 1.8 (`docs/plans/phase1.md`). It sorts the errors of the worst development files and the near-miss structure failures into causes, says what change would make each file convert correctly, and ranks the causes by what a fix recovers. The ranking is the work list for Workstreams B to E. It is updated after each full development run.

Plain headings and lists only.

## How the triage is done

- **Tools.** `scripts/triage_errors.py RESULTS.json` sorts every note error of the worst files into patterns that point at a cause: notes on the wrong staff (a missing and an extra note at the same bar, beat, pitch and value on different staves), bars out of line, a bar's contents shifted (three or more notes of a bar moved by the same amount), rhythm, tuplet, dot, octave and accidental errors, grace notes, and missing and extra notes. `scripts/make_subset.py` makes a set of chosen pairs, so a fix can be checked on the files it affects in minutes. `scripts/check_lilypond_pairs.py` finds LilyPond pairs whose PDF may not show the ground truth.
- **Looking at the page.** For each large cause, pages were drawn as pictures and compared with the reference MusicXML and the reader's output, to decide whether the reader, the reference or the PDF is at fault.
- **Kinds of fault.** A reader fault is fixed in the reader. A fault in the reference (or the pair) is the owner's decision, under the plan's rule. Information the PDF does not hold is a known limit, with counts.

## Starting point (gate run, 16 October 2026)

- Development set: notes 96.66 percent (46,554 note errors in 1,778 files), structure 77.8 percent.
- The worst 100 files hold 32,671 errors (70.2 percent). Their errors by pattern: bar contents shifted 6,984, other rhythm 6,908, missing notes 5,200, notes in bars with no partner 3,539, notes on the wrong staff 3,466, tuplet values 1,589, accidentals 1,465, octaves 1,154, and smaller groups.
- Verovio holds 13,191 of them and LilyPond 9,593.

## Causes, ranked by errors recovered

Counts are note errors in the gate run unless they say otherwise. Each cause names the code it touches and whether it corrects a rule or needs a new one.

### Reader faults fixed

1. **Hidden staves matched to the wrong parts** (Verovio, and any engraver that hides empty staves). About 4,900 errors in 8 Verovio files, and their structure mismatches. Three faults in one rule, `structure.py` (`_match_staves`):
   - Shortened names did not match: only the first three letters were compared, so "Pno." did not match "Piano" and counted against it. Corrected: each word of the short name must stand for a word of the full name, in order ("Bk. Voc." for "Backing Vocals", "Tr. Fa" for "Trompes en Fa"), with numbers and roman numbers equal.
   - New rule: staves joined by a brace in the system must be neighbouring staves of one part, staves not joined must be in different parts, and a group of staves must start and end where a part does.
   - New rule (`symbols.py`, `brace_halves`): Verovio draws a brace as two curved halves, which the shape tests took for ties. Two narrow curved halves meeting end to end are now a brace.
   - Result on the 8 files: about 4,900 errors to about 500.
2. **A tuplet number over part of a beam group** (every engraver). The number took every note joined by the beam, so an eighth beamed to three triplet sixteenths became a triplet too. One choir score alone had 655 errors in each of its six engravings. New rule (`notation.py`, `_tuplet_run`): when the whole group cannot be a tuplet of that number, the number takes the unbroken run of notes centred under it that adds up to that many equal values. Result: 655 errors to 7 on that score.
3. **Beams across two staves** (piano figures passed between the hands). Each staff was read alone, so each hand's notes of the beam were packed together, and the hidden-tuplet rule then read each hand's three notes as a triplet. New rules (`notation.py`, `cross_staff_beams`): the two staves of such a bar are read together, and the reading is kept when the beam's notes follow one another; the hidden-tuplet rule leaves cross-staff beams alone. Result on one song: about 1,330 errors in three engravings to about 765. The rest of that song is other causes.
4. **Outlined rhythm slashes and drum noteheads not read** (Verovio). Slash notation and cross noteheads were not among the shapes matched, and a slash is drawn as a four-sided piece, which was skipped as a stem or beam. Corrected list and new rule (`symbols.py`). Result: 442 errors to 4 in one file, and 411 to 24 in another.

5. **Bars broken across a line** (LilyPond). LilyPond breaks a long bar across two systems with no barline at the end of the first, and prints the next bar number in brackets. The reader made two bars. New rule (`notation.py`, `join_split_bars`): where a system ends with no barline and the next starts with a bracketed bar number (or the two pieces add up to one bar), they are one bar, the second piece placed to end where the bar ends. On the 45 LilyPond near misses with a wrong bar count, 15 became structurally correct, with fewer note errors in each.
6. **Repeat play counts from verses.** The ground truth plays some repeats 3, 4 or 5 times; no engraver prints the count, but in these songs the repeated section has that many lines of lyrics. New rule (`notation.py`, `repeat_counts_from_verses`): a section with verses 1 to n, n above 2, is played n times. 17 of 47 files that failed only on this became structurally correct.
7. **Two endings drawn with one joined line.** Where two endings sit side by side, their lines touch and are joined, and the second number was lost. New rule (`structure.py`, `system_endings`): the ending starts at the hook down from the line left of its number. 8 more files structurally correct.
8. **One-line percussion staves not found.** Only five-line staves were found, so a percussion staff went missing, the parts after it were shifted, and its clef was given to the staff above. New rule (`layout.py`, `one_line_staves`): a single line with a percussion clef on it is a staff, kept as a five-line staff centred on its line; its line is line 1, as MusicXML counts it. Two development scores (12 files) went from 1,401 errors to 117, and the real-world upload with percussion from 531 to 0.
9. **Two systems taken as one** (LilyPond). Where systems sit close and the gaps inside a system (with lyrics) are wider than between systems, the barline rule joined two systems, giving twice the parts. New rule (`layout.py`, `_starts_system`): a staff with a bar number at its left end starts a system. One choir score went from 1,319 errors to 60.
10. **A unison between voices beside a dotted note.** When a dotted note (stem down) and a note of the other voice (stem up) share a pitch, the second head stands right of the dot; it was read as starting later. Corrected rule (`notation.py`, `_same_column`). One song went from about 570 errors over three engravings to 8.
11. **Staccato dots read as augmentation dots.** On a rising line of staccato notes, the dot under each note is level with the note before and was taken as its dot. New rule (`notation.py`, `attach_dots`): a dot straight over or under a note of the same voice is that note's staccato. Five scores went from 1,767 errors to 92.

### Reader faults still open

12. **Two parts with the same name, one hidden.** In a score with two Piano and two Harp parts, a system showing "Pno." and "Hrp." could be either pair (about 400 errors in one Verovio file). The reader marks those systems as uncertain, so they are flagged.
13. **Unprinted triplets mixed with plain notes.** Songs where the "3" is printed once and the later triplets are not, in two voices with quarter notes among them (about 150 errors on each engraving of one song). The hidden-tuplet rule only handles beam groups of one value.
14. **Smaller groups in the near misses, not yet looked at:** clefs read on the wrong line ("G 1", "G 5") in 10 scores, octave clefs read without their octave (11 files), keys (16 files), an organ score whose duplicated instrument names give two parts too many.

### Faults in the reference or the pair (the owner's decision)

15. **LilyPond pairs whose PDF does not show the ground truth.** musicxml2ly loses track of time in some scores ("Negative skip" warnings) and moves or drops notes, so the LilyPond PDF shows different music. One file was checked by eye: the LilyPond engraving runs to 6 pages against MuseScore's 2, with much of the music missing. 17 LilyPond pairs have 50 or more of these warnings and read at least 5 points worse than every other engraving of the same score. They hold 6,531 of the 12,322 LilyPond note errors. Without them LilyPond reads at 97.05 percent instead of 94.14, and the whole development set at 97.09 instead of 96.66. The list is in `evaluations/lilypond-pairs-development.txt` on the corpus drive. **Proposal:** drop these pairs, or redraw their scores, and add the warning count to the export check so new LilyPond pairs with many warnings are rejected.
16. **Verovio prints one key for every staff.** Where parts change key differently (transposing instruments, or a key change in some parts only), Verovio prints the same key signature on every staff, and the notes it prints follow that key, so the printed music differs from the ground truth. Seen in 3 files with about 1,300 errors (accidental errors and key mismatches). **Proposal:** treat these as faulty pairs, found by comparing the reference's key changes across parts.
17. **A barline in the middle of a bar.** A chant score's reference has one bar per line with a barline in the middle of each (MusicXML allows this). On the page it looks exactly like two bars, and MuseScore can draw the same picture from two bars, so the PDF cannot tell them apart. About 2,500 errors over the score's six engravings. **Proposal:** the harness treats a middle barline in the ground truth as a bar boundary.
18. **Navigation stored as words.** 14 scores (66 mismatches in near misses) have D.S., D.C., Fine, coda, segno or To Coda that the reader finds but the reference holds only as words (one even as the segno character in a words element). **Proposal:** the harness reads such words as navigation, as the reader does.

### Information the PDF does not hold

19. **Systems with every staff hidden.** Verovio draws nothing for systems where every staff is empty. In one file the last 16 bars (all rests) are missing from the PDF, so the bar count cannot be right.
20. **Repeat counts with no verses.** 2 scores play a repeat more than twice with no printed count and no verses to count.
