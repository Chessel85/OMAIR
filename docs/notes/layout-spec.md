# Staves, systems, parts and structure (Phase 1, Stage 1.2)

How the structure of a score is read from a vector PDF: staves, systems, bars, parts, and the clef, key and time signatures, repeats, endings and navigation marks. It works from the page's vector lines and the symbols of Stage 1.1 (`symbol-spec.md`), so it is the same for every engraver and for Type A and Type B pages.

- Code: `src/omr/pdf/layout.py` (one page) and `src/omr/pdf/structure.py` (the score).
- Command: `omr layout FILE...`.
- Check: `scripts/check_structure.py`.

## Staff lines and staves

- Horizontal lines are stroked lines and thin filled rectangles (at least 30 times as wide as tall). Hairlines stacked less than 0.25 points apart along the same span are one thick line: some printer drivers draw a staff line as five hairlines. Pieces at the same height that touch or are less than 2 points apart are one line.
- A staff is five lines that are:
  - equally spaced, within 10 percent;
  - no thicker than a third of the gap;
  - overlapping along at least half the shortest;
  - each at least 60 percent as long as the longest, so a short bracket line one space above a staff cannot take a staff line's place;
  - at least six staff spaces long.
- A symbol's staff is the staff whose span covers its x and which is nearest it vertically, within 10 staff spaces. Its step is its position on that staff: 0 on the bottom line, 8 on the top line, one step for each line and space.

## Systems

Two staves, one above the other and overlapping along the page, are in one system when:

- a vertical line crosses the gap between them (the line at the start of a system, a spanning barline, a bracket) and starts at a staff: within four staff spaces above the top of the upper staff, or of a staff higher up, since Verovio and LilyPond draw one line down a whole large system (Stage 1.3 fix);
- a brace is drawn beside both; or
- they have the same ends and their barlines (other than the one at the end of the system) fall at the same places, and the gap between them is at most 0.8 of the gap between systems. LilyPond draws nothing joining choir staves. The gap test is needed because two systems of repeated music can have their barlines in the same places.

The gap between systems on a page is its largest gap between staves, where the page shows two clearly different gaps (the larger at least 1.25 times the smaller). Otherwise it is the median of those values over the document. A page of one system, or of one-staff systems, shows only one kind of gap.

## Barlines and bars

- A barline of a staff is a vertical line, or a filled upright bar, that:
  - covers the staff from its top line to its bottom line, within 0.2 staff spaces;
  - runs no more than 1.5 staff spaces past the staff, except into the staff above or below;
  - is not a note stem. A stem has a notehead at its bottom end with the line at the notehead's right edge (stem up), or at its top end with the line at the notehead's left edge (stem down).
- A system's barline positions are those where at least half its staves have a barline. Positions less than 1.2 staff spaces apart form one barline group. A line at least 0.3 staff spaces wide is thick, which gives single, double, final, heavy-light and heavy-heavy groups.
- Dots in the second and third spaces of a staff, by the middle of their ink, just left of a group make it the end of a repeated section. Just right of it they make it the start of one.
- A bar ends at each barline group, with two exceptions:
  - a group before any note or rest of the system that is a start repeat (heavy-light, or dots after it) opens the first bar instead;
  - an empty stretch narrower than two staff spaces is not a bar.
- An empty bar with no rest drawn is still a bar. Notes after the last group make a last bar that is not closed.
- The first bar of a system includes everything from the start of the system: the clef, key and time before a start repeat.

## Parts

- Within a system, staves joined by a brace are one part, unless each has its own instrument name beside it: a brace can also group two instruments, such as two voices.
- Two staves with one name centred in the gap between them, and no name of their own, are also one part. This covers engravers that draw no brace.
- Every other staff is a part of its own.
- The system with the most staves (the first if several) sets the parts. A system with fewer staves (empty staves hidden) is matched to it in order, best agreeing on instrument names (short names allowed) and on the clef of each staff. Systems with the same number of staves map directly.
- A part's name is the text left of its staves in that system.

## Structure events

The events have the form the evaluation harness uses (`omr.evaluate.events`), so its rules apply unchanged. That includes leaving out restated clefs, keys and times (decision 11).

### Clefs

- A clef's value comes from its symbol and the line it names: `G 2`, `F 4`, `C 3` and so on, with ` octave -1` or ` octave +1` for an octave clef.
- LilyPond draws an octave clef as a plain clef with a small 8 or 15, as music digits or as text. The digits count as an octave mark if they are centred on the clef and touch its top or bottom. A bar number above the first clef of a system is further off and not centred.
- A clef with no note before it in its bar is at the start of that bar.
- A clef after the last note of its bar is at the start of the next bar.
- A clef with notes before and after it is within its bar. Its exact onset waits for Stage 1.3.
- A clef in an empty bar, nearer the end of the bar, is for the next bar.
- A clef after the last barline of a system is a courtesy clef and is left out.

### Key and time signatures

- A bar's signature region is its symbols before its first full-size note or rest, plus those after the last note of the bar before. An engraver may put a change before a start-repeat barline, after the last note of the previous bar. A small notehead (a metronome mark, cue or grace note) does not end the region.
- A key signature is a run of sharps or flats, each within 1.6 staff spaces of the one before, whose letters follow the key-signature order for the clef in force: F C G D A E B for sharps, B E A D G C F for flats. Naturals may come before the run, cancelling the old key. Naturals alone are a change to no sharps or flats.
- An accidental with a note on its step just after it is that note's accidental. A single accidental must be free of notes. A run of two or more that follows the order is a key signature even where a note sits on one of its steps, as long as at least one accidental of the run is free of notes; a chord's accidentals each have a note.
- A part's key is read from its first staff. A part with no key signature at the start of the score has no sharps or flats.
- A time signature is digits stacked above and below the middle line (by the middle of their ink, since SMuFL digits are centred on their origin and Emmentaler's stand on it), or a common or cut time symbol. Digits that are a clef's octave mark are left out.
- Signatures after the last barline of a system are courtesy signatures and are left out.

### Repeats, endings and navigation

- **Repeats**: from the barline groups. A forward repeat belongs to the bar it starts, a backward repeat to the bar it ends. Both are given for every part.
- **Endings**: a number such as "1." or "1, 2." above the top staff, at the left end of a horizontal line with a hook down at its start. The ending stops at the first hook down from the line, which is then a "stop". With no hook it reaches the end of its line and is a "discontinue". An ending that runs to the end of a system continues on the next.
- **Navigation**: segno and coda signs, and the words D.C., D.S., To Coda and Fine, at the bar they stand over.

## Results

`scripts/check_structure.py` compares the structure read from each PDF with the ground truth. A clef within a bar is compared by its bar and by whether it is at the start, since onsets need Stage 1.3. A ground-truth clef after the last note of a bar counts as at the start of the next bar, because the two print the same.

On the regression set (256 pairs, 43 scores):

- Exact pairs (MuseScore 4): 76 of 86 files structurally right (88.4 percent), and 82 of 86 right in parts, bars, clefs, keys and times (95.3 percent).
- Engraver-input pairs (MuseScore 3, LilyPond, Verovio): 131 of 170 right (77.1 percent), and 148 of 170 right in parts, bars, clefs, keys and times (87.1 percent).

On the development set (1,778 pairs, 300 scores; a few rules came from its MuseScore 4 failures):

- Exact pairs: 512 of 600 right (85.3 percent), and 560 of 600 in parts, bars, clefs, keys and times (93.3 percent).
- Engraver-input pairs: 884 of 1,178 right (75.0 percent), and 982 of 1,178 in the core items (83.4 percent), after the Stage 1.3 fix to joining large systems (before it: 807 and 895). Verovio (clefs, keys) and LilyPond (bars) are weakest; neither has been studied on this set yet.

On the regression set, every exact pair that is not right is one of the known limits below. For the engraver-input pairs, the PDF can legitimately differ from the reference it was made from, and most of the remaining mismatches are such differences:

- musicxml2ly wrote different bars for some scores.
- LilyPond draws an empty stretch after a repeat at the end of a line, and draws some endings with no closing hook.
- Verovio cannot set different time signatures in different parts.
- MuseScore 3 lays out some scores with extra bars.

## Known limits

- **Barlines that are not drawn, and barlines that are not bar ends.** A barline printed invisible (bar style "none") joins two bars on the page. A barline in the middle of a bar (MuseScore allows one) splits a bar on the page. Neither can be seen from the page alone. Stage 1.3's bar arithmetic can catch them, because the two halves of a split bar are each too short.
- **Repeat counts that are not printed.** A backward repeat "3 times" that the page does not say reads as a plain backward repeat.
- **Navigation words the ground truth stores as plain words.** "Fine", "D.C. al Fine" or a segno typed as text has no playback marker in the file, so the harness does not count it, but it is read as navigation. These are the remaining structure mismatches on exact pairs.
- **Clef onsets.** A clef within a bar gets its exact onset from Stage 1.3 (`read_pdf(path, notes=True)`); the structure alone gives a placeholder.
- **Multi-bar rests** are not yet expanded into their bars; none occurs in the regression set.
- **Percussion and tablature staves** (one-line and six-line staves) are not yet staves.
