# Musical rules and the confidence report (Phase 1, Stage 1.5)

How the PDF reader decides which bars may be wrong, how it says so, and how well the flags find the real errors (ACC-4). It works on the score read by Stages 1.2 to 1.4 (`layout-spec.md`, `notation-spec.md`, `markings-spec.md`).

- Code: `src/omr/pdf/rules.py` (the rules, joining flags by bar, the flag file) and `src/omr/confidence_report.py` (the report in words). The reader's own doubts are noted in `src/omr/pdf/notation.py` and kept in `Score.doubts`, which the harness does not compare.
- Command: `omr confidence FILE...` prints the confidence report. With `--out FOLDER` it also writes `FOLDER/<file name>/flags.json` (the flag file, `evaluation-spec.md`, "Error flagging") and `confidence.txt`.
- Check: `scripts/check_flags.py` reads each PDF, flags it, and scores the flags with the harness's own rule (`metrics.compare_scores` with flags, through `metrics.error_places`). It reports flagging recall, the share of bars flagged and the share of flagged bars with an error, for exact and engraver-input pairs, rule by rule. CI runs it on the regression set with a floor of 92 percent on exact pairs.

## Doubts noted while reading

The reader notes these for a staff in a bar as it reads (`notation._read_system`):

- **Rhythm.** After the onset search (`notation-spec.md`, rule 3), the bar is checked for three things: a column that starts where no earlier event ends, an event that ends where nothing starts while later events pass over that point, and an event that runs past the bar's end (whole-bar rests aside). The search's total cost is not used: most of it comes from voices that stop short (engravers hide rests) or from the stem-direction preference, and on the regression set a cost of 0.5 or a short voice alone almost never meant an error.
- **Staves disagree.** In a bar of a system, an event of one staff that stands in line with an event of another staff (within 0.3 staff spaces) but starts at a different time, or one that stands at least 1.5 staff spaces to the right of another but starts earlier. Both staves are flagged, since either may be wrong. Grace notes and whole-bar rests (which stand in the middle of the bar) are left out.
- **Unprinted tuplet.** A beam group read as a tuplet from the bar's length, with no number printed (bar arithmetic, ACC-5).
- **Stray symbol.** A flag on no stem, an accidental before no note, a dot beside no note that is neither an augmentation dot nor a staccato, a tuplet number over no notes (italic bar numbers and the 8 of an octave clef are not tuplet numbers), and an octave glyph of the music font that reaches no notes.
- **Octave sign.** An octave sign with no "va" or "vb" between two staves: which staff it belongs to and which way it goes are guesses, so both staves are flagged for the bars it spans.
- **Hidden staves.** A system with fewer staves than the score, where another matching of its staves to the parts fits the names and clefs as well (`structure._match_staves` counts the best matchings). Every staff of the system is flagged in every bar.

## Rules on the whole score

`rules.check` adds these to the doubts:

- **Bar fullness** (ACC-5): a voice that does not fill its bar or runs past it (`notation.unfilled_bars`, which leaves out pickups, bars split at a repeat or system break, and voices whose rests are hidden).
- **Ties**: a tie start with no note of the same pitch starting where it ends (in the bar, or at the start of the next bar when it ends the bar), and a tie stop with no such note ending where it starts.
- **Key and accidentals**: a note spelled more than five fifths beyond the seven letters of its key on the line of fifths (D sharp in A flat major). This leaves room for the raised and lowered notes of major and minor keys.
- **Instrument range**: a note outside the written range of the part's instrument or voice, when the part name says what it is (`rules.RANGES`, generous by a step or two; a word such as "bass" in "bass clarinet" gives way to the instrument).
- **Slurs**: a slur that starts and does not stop in its part, or stops with no start.

## The flag file and the report

- Flags are joined into one per part, staff and bar, with every reason given there (`rules.bar_flags`).
- Only the rules that point at note errors go into the flag file (`rules.FLAG_RULES`): rhythm, bar fullness, staves disagree, unprinted tuplet, ties, stray symbol, octave sign and hidden staves. Key and accidentals, instrument range and slurs flag bars that seldom hold a wrong note (under 10 percent on the development set), and adding them gains less than half a point of recall for about a fifth more flagged bars. The report still lists them, as things also worth checking.
- Each flag in the file has the part, bar and staff, the reasons joined by semicolons, and a confidence: the chance that the bar is right as read, the product over its rules of one minus the rule's precision (`rules.RULE_PRECISION`, the share of the rule's flagged bars that held a note error on the exact pairs of the development set).
- The report (OUT-3, OUT-4) opens with the file name and a summary line, for example "Summary: 64 bars, 61 high confidence, 3 flagged." A bar is high confidence when no part has a flag in it; the flagged count is the number of flags (one per part, staff and bar). Then each flag in score order: page, system, bar, part (and "upper staff", "lower staff" or "staff N" for a part with several), the beat where the flag knows it (counted in the time signature's beat), and the reasons, for example "Page 2, system 1, bar 14, Violin, beat 2.5: a note starts where no note before it ends." Then "Also worth checking:" with the report-only rules in the same form.

## Results

Figures from `check_flags.py`. Exact pairs are MuseScore 4; engraver-input pairs are MuseScore 3, LilyPond and Verovio, whose ground truth is the engraver's input.

- **Regression set** (256 pairs): exact pairs 94.4 percent of note errors in flagged bars, with 5.5 percent of bars flagged and 46.4 percent of flagged bars holding an error. Engraver-input pairs 91.7 percent, 7.0 percent of bars, 41.3 percent.
- **Development set** (1,778 pairs, report in `evaluations/flags-development.txt` on the corpus drive): exact pairs 92.4 percent, 4.8 percent of bars flagged, 28.5 percent of flagged bars with an error. Engraver-input pairs 77.0 percent, 8.5 percent, 30.8 percent. By job: MuseScore 3 95.6 and 93.4 percent, MuseScore 4 90.6 and 94.2, LilyPond 75.7, Verovio 68.7.
- **Real-world uploads** (40 MuseScore.com files, report in `evaluations/flags-realworld.txt`): 45.6 percent, 12.4 percent of bars flagged, 42.9 percent with an error. One file holds 531 of the 1,048 errors: two one-line percussion staves that the reader does not read (a Stage 1.2 limit), so the output has no part a flag could name. Without that file, 92.5 percent.
- **Rules on the development set, exact pairs** (recall alone, bars flagged, flagged bars with an error): rhythm 62.2, 1.7, 64.3 percent; bar fullness 63.1, 1.6, 57.7; staves disagree 38.8, 1.3, 48.7; unprinted tuplet 14.8, 0.5, 25.5; ties 13.3, 1.0, 19.5; stray symbol 4.0, 0.5, 13.2; octave sign 1.0, 0.1, 16.5; hidden staves 2.1, 0.7, 3.4 (12.3, 1.9, 16.5 on engraver-input pairs). Rhythm, bar fullness and staves disagree overlap a good deal; each one taken away costs 4 to 17 points.
- Bar fullness alone, the only flag Stage 1.3 had, covered 63.1 percent of exact-pair errors on the development set.

## The ACC-4 target (OI-3)

- At least 90 percent of note errors in flagged bars, **with at most 10 percent of bars flagged**, measured on the exact pairs of the vector corpus, as ACC-6 is. Engraver-input pairs and the real-world uploads are reported beside it but do not count, since their ground truth can differ from what is printed.
- Errors in parts or staves that the output does not have at all cannot be flagged by the flag file's rules. They still count against the target today; counting them apart is left for later.
- Today's figures meet it on exact pairs: 92.4 percent with 4.8 percent of bars flagged on the development set, and 94.4 with 5.5 on the regression set.
- The share of flagged bars with an error (about 30 percent) is not part of the target yet. It shows how much a reader would check for nothing: about two flagged bars in three are right.

## Known limits

- Errors the rules cannot see: a bar whose notes all fit in time but are wrong (a duration misread in both voices, a missed dot that a missed rest makes up for), a wrong pitch with nothing odd about it, and a whole passage under a missed octave line whose sign was not seen.
- Staves matched to the wrong part where the matching was not in doubt (single-staff parts with no names and the same clefs) are not flagged; their notes come out as missing in one part and extra in another.
- Parts the reader does not find (one-line percussion staves, tablature) are outside the flag file, which can only name the output's own parts and bars.
- The engraver-input figures for LilyPond and Verovio are lower because their errors come in large blocks (bar counts, hidden staves, clefs) that no bar-level rule catches.
- The confidence figures come from the development set's exact pairs and are not yet checked for calibration on other sets.
