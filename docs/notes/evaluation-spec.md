# Evaluation harness specification (`omr evaluate`)

Version 1, 6 October 2026, for Stage 6 of `docs/plans/phase0.md`. It covers DEV-1 and the metrics for ACC-1 to ACC-6 in `requirements.md`. The owner accepted the decisions listed at the end on 6 October 2026. This is the specification the harness implements and the code review checks against.

## Purpose and principles

The harness compares a recogniser's MusicXML with the ground-truth MusicXML of each pair, and reports how close they are. Every later accuracy number in the project comes from it, so it must be exact, explainable and tested.

- **One answer per question.** Each metric has one definition, written here. The code implements that definition, and the tests check it with cases where the right value is known in advance.
- **What is on the page counts.** Notes are compared as written: written pitch, notes in written order, repeats not expanded, each tied note counted separately. A braille transcriber and a screen-reader user read the written score.
- **Errors are counted the way a person fixing the file would count them.** One wrong note is one error, not a missing note plus an extra note.
- **Accuracy does not depend on heuristics.** Exact matches are found first by a rule with only one answer. Heuristic pairing is used only afterwards, to name the kind of each error.
- **Locations are given in words** (AX-2), for example "bar 14 (page 2, system 3), Piano, upper staff, beat 3".

## Inputs

- **The pairs.** `generated/<set>/index.txt` under the corpus folder lists each pair: its PDF and its ground-truth MusicXML (for MuseScore 4 its own `score.musicxml`, otherwise the shared `reference.musicxml`). The pair's `metadata.txt` gives the engraver, font, genre, texture and ground-truth kind (exact or engraver input). Failures in the index (mostly LilyPond) are not pairs and are skipped, and the report says how many.
- **The recogniser.** Any command that takes a PDF and writes MusicXML (see "Recogniser interface").
- **Or existing predictions.** A folder of MusicXML files already made, one per pair, so that a slow recogniser need not be run twice.

## Reading a MusicXML file into events

The harness reads both files with its own reader, built on the standard XML library, not music21. Every position is an exact fraction, so there is no rounding. music21 is used only by musicdiff.

### Bars

- A **bar** is one `measure` element of a part, in written order. A pickup bar (`implicit="yes"`, often numbered 0) is a bar. So is the second half of a bar split at a repeat or a system break. Repeats and endings are not expanded.
- A **multi-bar rest** counts as the bars it stands for. MusicXML always writes each of those bars as its own `measure` element (the `multiple-rest` count only tells an engraver to draw them as one), so they are counted as written.
- **Bar length** is how far the bar's content reaches: the largest end position of any note, rest or `forward` in the bar. It is used to join two bars when a barline is missing.
- The printed number (`number` attribute) and, in the ground truth, the page and system (from `print` elements with `new-page` and `new-system`) are kept for the report. MuseScore 4 ground truth writes these, because its MusicXML comes from the same layout as its PDF.

### Notes

Each note element that is visible (`print-object` is not "no") becomes one **note event** with:

- **Part and staff.** The part is the `part` element. The staff is the note's `staff` element, or 1. A cross-staff note has the staff it is drawn on.
- **Voice**, from the `voice` element.
- **Onset**: its position from the start of the bar, in quarter notes, as an exact fraction. It is worked out from `duration`, `backup` and `forward`, divided by `divisions`. A chord note (`chord` element) has the onset of the chord's first note. A grace note has no duration, so its onset is that of the note that follows it, and it also gets an order number among the grace notes before that note (1, 2, 3).
- **Pitch**: the written pitch, from `step`, `alter` and `octave`. The spelling is kept, so C sharp and D flat are different pitches. A percussion note uses `display-step` and `display-octave`. Written pitch is compared because transposing parts are read as written.
- **Duration**: the notated value, from `type`, `dot` and `time-modification` (so a triplet eighth is 1/3 of a quarter note). If `type` is missing, the `duration` value is used instead. A grace note's duration is its notated type and dots, with zero length. The slash (acciaccatura or appoggiatura) is not part of the duration.
- **Other attributes**, which are compared separately and are not part of note accuracy: tie start and stop, staff, voice, stem direction, beams, cue size, notations (articulations, fermatas, ornaments, slurs), and lyrics.

### Rests and markings

- **Rests** become rest events with part, staff, voice, onset and duration. A whole-bar rest (`rest measure="yes"`, or a rest with no type that fills the bar) has duration "whole bar". Rests are not in note accuracy. They help align bars and are reported as their own figure.
- **Structure events**: clefs, key signatures, time signatures, repeat barlines, endings and navigation marks (segno, coda, D.C., D.S., Fine, To Coda), each with its bar and onset.
- **Performance markings**: dynamics (each child of `dynamics`, such as p, mf or sfz) and hairpins (`wedge` start and stop), each with part, staff if given, bar and onset (including `offset`).

## Matching

Matching runs in four steps, each limited to what the step before allowed.

### Step 1: staves

- Both files are listed as staves in score order (part 1 staff 1, part 1 staff 2, part 2 staff 1, and so on).
- If the counts agree, staves are paired in order.
- If they differ, staves are paired by best total similarity: the overlap of their pitch histograms, plus a bonus for the same clef. SciPy's `linear_sum_assignment` does the pairing. A staff left unpaired has all its notes counted as missing (ground truth) or extra (prediction).
- A **matching group** is one ground-truth part with the predicted staves paired to its staves. Notes are matched within the group, not within a staff, so that a note placed on the other staff of a piano part is still found. The wrong staff is then reported as a staff error, not a note error. A piano written as one part with two staves in one file, and as two parts in the other, also matches this way.

### Step 2: bars

The ground-truth bars and the predicted bars are lined up in one sequence for the whole score (bars are shared by all parts) by dynamic programming, like an edit distance. Costs are counted in events (notes and rests, all groups together), so the alignment chosen is the one that leaves the fewest note and rest errors. The allowed moves and their costs:

- Pair one ground-truth bar with one predicted bar: the number of events in either bar with no exactly equal partner in the other.
- Join two ground-truth bars against one predicted bar, or the reverse: the same count for the joined bars, plus 1.5. The second bar's onsets are moved on by the first bar's length. This handles a missing or extra barline without turning every note into an error. The extra 1.5 means a join is chosen only when it saves at least two errors.
- Leave out a ground-truth bar (a missing bar) or a predicted bar (an extra bar): the number of events in it, and at least 1.
- When two alignments cost the same, one-to-one pairing is preferred.
- An earlier version used shares (1 minus the share of events in common). On the development set it joined two bars wrongly: two identical one-note bars, the second with a wrong note value, cost as much as a missing bar, so joining neighbouring bars came out cheaper. Counting events fixes this, and a test reproduces the case.
- To keep this fast, the search stays within a band around the diagonal, as wide as the difference in bar counts plus 20 bars.

The result is a list of aligned bar pairs (one-to-one, two-to-one, one-to-two, or unpaired). A missing or misplaced barline is a structural error, and it costs no note errors when the notes themselves are right.

### Step 3: exact note matches

Within each aligned bar pair and matching group, a note is an **exact match** when its onset, pitch and duration all equal those of a predicted note. Exact matches are counted as a multiset intersection on (onset, pitch, duration, grace order). This count has only one answer, so it does not depend on any heuristic. Two identical notes (a unison in two voices) match two identical predicted notes. Among identical notes, pairs are chosen with the same staff and the same voice number first, then the same staff, then any. This never changes the count of exact matches; it only avoids inventing staff or voice errors.

- Voice, staff and chord grouping play no part, so voices numbered differently, a chord split into two voices or two voices merged into chords make no difference to note accuracy.
- Onsets are strict, as the requirement says. A missing dot early in a bar moves the later notes of that voice, and they count as onset errors. The diagnostic figure "pitch and duration accuracy" (onset ignored within the bar) shows when this is happening.

### Step 4: naming the remaining errors

The notes left over after step 3 are paired to name each error. This step does not change the accuracy.

- The cost of pairing a ground-truth note with a predicted note in the same bar pair and group is 0.4 for each of pitch, onset and duration that differs. A pair that differs in all three is not allowed. Leaving a note unpaired costs 1.
- SciPy's `linear_sum_assignment` finds the cheapest pairing.
- Each pair is named by what differs: a pitch error (the report also says if it is only a spelling difference, such as C sharp for D flat), a duration error, an onset error, or a combination. An unpaired ground-truth note is a **missing note**, and an unpaired predicted note is an **extra note**.

## Metrics

All metrics are reported per file and overall. Overall figures add up the counts over all files first and then divide (a micro-average), so a long piece counts more than a short one. The per-file spread (median, lowest 10 files) is reported as well.

### Note accuracy (ACC-1 to ACC-3)

- Let T be the number of ground-truth notes, M the number of exact matches, and E the number of extra notes (step 4).
- The **errors** are the T minus M ground-truth notes not matched exactly, plus the E extra notes. A wrong note counts once.
- **Note accuracy = M / (T + E)**, which is the number of correct notes divided by the correct notes plus the errors. It is 100 percent only if every note is right and nothing is added.
- Also reported: recall (M / T), precision (M / number of predicted notes), and the count of each kind of error.
- Diagnostic figures, not used for the targets:
  - pitch and duration accuracy (onset ignored within the bar) and sounding-pitch accuracy (spelling ignored): the notes that match on those properties, divided by the larger of the ground-truth and output note counts;
  - rest accuracy: rests matching in onset and duration, divided by the larger of the two rest counts;
  - staff, voice and tie accuracy: the share of exact matches with the right staff, voice grouping, or tie start and stop.
- **Voice accuracy** compares groupings, not voice numbers. Within each bar, each predicted voice is mapped to the ground-truth voice it shares most exact matches with, and a matched note whose voices do not correspond under that mapping is a voice error. Two output voices may map to the same ground-truth voice, so merging voices into chords, or splitting a chord into voices, is not a voice error. Identical notes (a unison in two voices) could be paired either way, so the mapping is taken from the notes that pair unambiguously. A predicted voice that appears only among identical notes is mapped to the ground-truth voices those notes leave over once the other voices are mapped. A group of identical notes then counts only the voice errors that no pairing of the group avoids.

### Structural correctness (ACC-1)

A file is **structurally correct** when all of these match exactly:

- the number of parts, and the number of staves in each part;
- the number of bars;
- the clefs on each staff, with their bar and onset;
- the key signatures of each part, with their bar (the fifths value; the mode is ignored);
- the time signatures, with their bar (beats and beat type; a common-time or cut-time symbol equals 4/4 or 2/2 for this test, and a different symbol is reported only as a note);
- repeat barlines (forward or backward, and the times count), endings (their numbers and where they start and stop), and navigation marks (segno, coda, D.C., D.S., Fine, To Coda).

Every mismatch is listed in words, for example "Bar 17: the ground truth has a backward repeat barline, the output has none". The overall figure is the share of files that are structurally correct. ACC-1 asks for at least 95 percent.

### Performance markings (ACC-6 and REC-4)

- A ground-truth **dynamic** is found if the output has the same dynamic (same text, such as mf) in the same matching group, in the aligned bar, with an onset no more than one beat away (a beat is the time signature's lower number), on the same staff if both files give one.
- A ground-truth **hairpin** is found if the output has a hairpin of the same kind (crescendo or diminuendo) whose start meets the same rule. Whether its end is also right is reported separately.
- **Marking recall = markings found / ground-truth markings.** ACC-6 asks for at least 90 percent on vector input. Precision is reported too.
- Articulations, fermatas, ornaments, technical marks (such as fingering), arpeggios, slurs and lyrics are scored on exactly matched notes: the share of ground-truth marks of each kind that the matched predicted note also has. A slur is scored by its ends: each slur start or stop on a ground-truth note must be on the matched note too. A lyric must have the same text. Tempo and expression text and chord symbols are scored the same way as dynamics, by text, bar and onset. These are diagnostic figures for REC-4 to REC-6.
- Pairs whose ground truth is "engraver input" (MuseScore 3, LilyPond, Verovio) may show markings the engraver did not draw. Marking figures are therefore reported separately for exact and engraver-input pairs, and only exact pairs count for ACC-6.

### Error flagging (ACC-4)

The recogniser may write a **flag file** beside its MusicXML, `flags.json`:

- It contains `{"version": 1, "flags": [...]}`. Each flag has `"part"` (the part's position in the output, from 1), `"bar"` (the bar's position in the output, from 1, counted as in "Bars" above), and optionally `"staff"` (from 1), `"reason"` (text) and `"confidence"` (a number from 0 to 1).
- Flags refer to the output's own bars, because the recogniser does not know the ground truth. The harness maps them through the bar alignment.
- A note error is **covered** if a flag names its part and bar (and its staff, if the flag gives one). For a missing or wrong note, that is the predicted bar aligned to the note's ground-truth bar. For an extra note, it is the bar the extra note is in. An error in a ground-truth bar with no predicted bar is covered if a flag names the predicted bar just before or just after the gap.
- **Flagging recall = covered errors / all note errors.** ACC-4 asks for at least 90 percent.
- Because flagging every bar would score 100 percent, the report also gives the share of bars flagged and the share of flagged bars that really contain an error. OI-3 refines the target with these figures.
- A missing flag file means no flags. The human-readable confidence report (OUT-3) is separate, and the recogniser writes it however it likes.

### Comparison with published work

- **musicdiff** is run on each pair at two detail levels, notes and rests, and all objects. It gives its edit counts and its **OMR-NED** (OMR normalised edit distance, the edit distance divided by the total number of symbols). OMR-NED is reported as a mean over files, as in published papers.
- **TEDn** (tree edit distance on MusicXML, Hajič and others, 2016) is not in musicdiff. The implementer looks for an existing implementation with a licence the register allows. If none is found, TEDn is left out of Stage 6 and recorded as an open item (see the decisions).
- These figures are for comparison only. The targets use the project metrics above.

## Recogniser interface

- A recogniser is a command template, for example `python my_omr.py {pdf} {out}`. The harness fills in the pair's PDF and an output folder, and the command writes `{out}/score.musicxml` and, optionally, `{out}/flags.json`. On Windows the template is run as one command line, with each filled-in path quoted. The test recognisers also get `{truth}`, the ground-truth file; a real recogniser must never use it.
- Built-in names: `perfect` and `damaged` (below), and later `omr` (the project's own pipeline) and the Stage 9 baselines.
- The harness times each run (wall clock) and records it. With `--cpu-only`, it hides the GPU from the recogniser (`CUDA_VISIBLE_DEVICES` set to empty), for the OP-2 timings in Stage 9.
- Each run has a time limit (default 600 seconds). A run that fails, times out or writes no MusicXML is a **failed file**. Its notes all count as missing, it is not structurally correct, and the report lists it with the reason. The report also gives the accuracy over completed files only.
- Runs use the shared worker pool (`omr.parallel`, `--workers N`, default 3), one pair per job, as `docs/conventions.md` requires. The comparison of a pair also runs in the worker.

## Test recognisers

- **Perfect.** Copies the pair's ground-truth MusicXML. It must score 100 percent on every metric, with every file structurally correct and an OMR-NED of 0. Anything less is a bug in the reader or the matching.
- **Damaged.** Copies the ground truth and applies known damage, chosen by a fixed random seed. It writes what it did to `damage.json`, with the metric values that damage implies, worked out from the damage alone and not by running the harness. The harness tests check that the harness gives exactly those values. Kinds of damage, each applied to notes or bars chosen so that its effect is known exactly:
  - change the pitch of a note (one pitch error);
  - respell a note enharmonically (one pitch error, and a spelling-only error in the diagnostics);
  - delete a note that is part of a chord (one missing note);
  - add a note to a chord (one extra note);
  - change the duration of the last note of a voice in a bar (one duration error, with no later onsets moved);
  - renumber the voices in a bar (no note errors, voice accuracy unchanged);
  - move a chord's notes into a second voice (no note errors);
  - remove a barline by joining two bars (no note errors, one structural error in the bar count);
  - delete a dynamic or a hairpin (one marking missed);
  - remove a clef, key or time change (one structural error).
- The damaged recogniser also writes a flag file that flags a known share of the damaged bars, so the flagging recall has a known value.

## Hand-made test pairs

Small MusicXML pairs written for the tests, with the right metric values worked out by hand in a comment in each test. They must include:

- triplets and other tuplets, including a tuplet that starts after a rest;
- ties across a barline (two notes, each counted);
- grace notes, before a note and before a chord, and a grace note missing in the output;
- a cross-staff note in a piano part, drawn on the other staff in the output (no note error, one staff error);
- a pickup bar and a split bar at a repeat;
- a multi-bar rest (its bars written out, with the `multiple-rest` count) against the same bars without the count;
- a missed barline and an extra barline;
- the same piano music as one part with two staves and as two parts;
- a unison in two voices;
- a different number of divisions in the two files for the same music;
- an empty output file and a file that cannot be parsed.

## Reports

- **Per file**, in plain text: the summary first ("pdmx-abc, MuseScore 4, Bravura: note accuracy 97.8 percent, 12 errors in 6 bars, structurally correct"), then the structural mismatches, then the errors bar by bar, in words. For example: "Bar 14 (page 2, system 3), Piano, upper staff, beat 3: expected F sharp 5 quarter note, found G 5 quarter note (pitch error)." The text report lists at most 50 errors per file and says how many more are in the JSON.
- **Overall**, in plain text, as headings and lists: the totals against the targets (ACC-1, ACC-4, ACC-6), then each figure broken down by engraver, font, genre, texture and ground-truth kind (exact or engraver input), then the lowest 10 files, and the failed files.
- **JSON**, with every count and every error, for later analysis and for the Stage 7 regression baseline.
- The command ends with the usual one-line summary, and exit status 0 unless something failed to run.

## Command line

- `omr evaluate --set development --recogniser perfect`: run a recogniser over a set and report.
- `--predictions FOLDER`: compare existing outputs instead of running a recogniser.
- `--engraver`, `--font`, `--genre`, `--texture`, `--limit N`: run on a subset.
- `--workers N`, `--cpu-only`, `--timeout SECONDS`, `--no-musicdiff` (musicdiff is the slowest step, about as slow as the rest put together).
- `python scripts/check_harness.py --set regression` runs both test recognisers over a set and checks every pair's figures (the Stage 6 done condition). `--only perfect` or `--only damaged` runs one of them, and `--no-musicdiff` skips musicdiff.
- `--out FOLDER`: where the reports go (default `evaluations/<date>-<recogniser>-<set>` under the corpus folder; the regression set's results go in the repository, Stage 7).

## Decisions

Accepted by the owner on 6 October 2026.

1. **Extra notes count as errors** (note accuracy = M / (T + E)). The alternative, M / T, ignores added notes, so a recogniser could add notes without losing accuracy.
2. **Spelling counts.** C sharp in place of D flat is a pitch error, because braille music and a sighted reader both show the spelling. Sounding-pitch accuracy is reported alongside.
3. **Onsets are strict,** as the requirement says, so one missing dot can make the rest of a voice in that bar wrong. The pitch-and-duration figure shows how often this happens.
4. **Grace notes are in note accuracy,** matched by pitch, position before their main note and notated value. REC-2 lists them.
5. **Failed files count as zero** in the overall figures, and accuracy over completed files is reported as well. A file the tool cannot convert is a failure for the user.
6. **Navigation marks are part of structural correctness.** The requirement lists repeats, and the marks decide the order in which the music is played.
7. **TEDn** waits if no usable implementation exists, and is recorded as an open item. OMR-NED from musicdiff is reported meanwhile.
