# Opus review of Stage 6: findings

Review of 6 October 2026, done against `docs/notes/review-brief-stage6.md` and `docs/notes/evaluation-spec.md`. Findings are in order of importance. Each says whether it was confirmed by running a case or found by reading the code. The cases were run with the builders in `tests/test_evaluate.py`.

## Summary

- Tests: 158 of 158 passed at the start of the review, 175 after all the fixes. `scripts/check_harness.py --set regression` passes before and after: 512 of 512 checks (perfect and damaged, 256 pairs each). After the fixes the development set passes too: 3,556 of 3,556 checks (1,778 pairs, without musicdiff).
- One place where the spec contradicted itself: step 4 changed note accuracy (finding 1). Fixed as the owner decided.
- One spec sentence the code did not follow: merging two voices into chords is counted as a voice error (finding 2). The owner decided it should be; the spec now says so.
- Three bugs, all confirmed and fixed: grace note order numbers carried over from the previous bar (finding 3); a bad flag file or an odd output could stop the whole run (finding 4); and some output errors were reported as flag file errors (part of finding 4).
- Findings 5 to 7 were recommendations. The owner asked for all of them, and all are done, except the dynamics read twice (finding 6), which needs no change.
- The damaged recogniser covers 7 of the 10 kinds of damage the spec lists (finding 5).
- Confirmed sound, by reading and by the probes: the rounds for identical notes never change the exact-match count; bar alignment prefers a join over a wrong bar whenever the second bar has at least one event; pairing two bars is never dearer than leaving both unpaired; the reader's handling of chords, backup, forward, invisible notes, divisions changes, tuplets and whole-bar rests matches the spec.

## 1. Step 4 changes note accuracy (spec contradiction, confirmed)

The spec says step 4 "does not change the accuracy". It does, because E, the number of extra notes, is whatever step 4 leaves unpaired. For each matching group, errors = T + O − 2M − P, where P is the number of pairs step 4 makes. So the accuracy depends on the step 4 costs and on the rule that a pair differing in all three properties is not allowed.

Confirmed with one wrong note in a bar of four quarter notes (C4 E4 G4 C5):

- The output has A5 quarter at beat 2 in place of E4: one pitch error, accuracy 3 of 4.
- The output has an eighth rest and then A5 eighth at beat 2.5 in place of E4: pitch, onset and duration all differ, so it is not paired. One missing and one extra note, accuracy 3 of 5.

Both are one wrong note to a person fixing the file. This also answers the brief's question: step 4 never changes M, but it does change E and the error count. A smaller effect: the Hungarian costs (0.4 per property, 1 for unpaired) do not always give the most pairs, so in a crowded bar the count can depend on the costs too.

Two ways to make the definition match the principle "accuracy does not depend on heuristics":

- **Recommended:** count errors per bar pair and group as the larger of the leftover ground-truth notes and the leftover output notes. This has one answer, it treats any wrong note as one error, and it is what step 4 gives whenever it pairs as much as it can. Step 4 then only names the errors, and a note it leaves unpaired is named "missing" or "extra" without changing the count.
- Or keep the code, and change the spec to say that E comes from step 4 and why.

**Fixed on 6 October 2026, with the first way (owner decision; spec decision 8).** Step 4 now uses a rectangular assignment, which always pairs the smaller of the two leftover counts, with cost 1 for each property that differs. A pair may differ in all three properties and is named "pitch, onset and duration error". The spec's step 4 and note accuracy sections say this. Tests: `test_a_wrong_note_counts_once_even_when_nothing_matches` (the case above, now 3 of 4) and `test_errors_in_a_bar_are_the_larger_leftover_count`.

## 2. Merging voices into chords is a voice error in the code, not in the spec (confirmed)

The spec says "merging voices into chords, or splitting a chord into voices, is not a voice error". Splitting works as written. Merging does not: two ground-truth voices (E4 whole note in voice 1, C4 whole note in voice 2) written as one chord in voice 1 give voice accuracy 1 of 2. This is what the spec's own mapping rule gives, since each output voice maps to one ground-truth voice.

Counting it seems right to me: braille and a screen reader both present voices separately, and losing that is a real error. If the owner agrees, change the spec sentence to "splitting a chord into voices is not a voice error; merging two voices into chords is" and add a test. Otherwise the mapping has to change.

**Settled on 6 October 2026: merging counts (owner decision; spec decision 9).** No code change. The spec sentence is corrected, and `test_two_voices_merged_into_chords_are_voice_errors` covers it.

## 3. Grace note order numbers carry over from the previous bar (bug, confirmed)

`events._read_part` keeps `grace_count` for the whole part, and only a main note resets it. A grace note after the last note of a bar (the end of a trill, for example) therefore numbers the next bar's first grace note 2, not 1.

Confirmed: bar 1 ends with a grace G4 after the last note, bar 2 starts with a grace A4 before B4. The truth reader numbers them 1 and 2. An output without the closing grace note numbers A4 as 1, so A4 is a wrong note as well as G4 missing: 2 errors for 1 missing grace note.

Fix: reset `grace_count` at the start of each bar. Grace notes after a main note in the same bar (the spec's "order among the grace notes before that note") also share the count with grace notes before the next note. That is consistent in both files, so it is not urgent, but a test with a closing grace note in mid-bar would show whether it matters.

**Fixed on 6 October 2026.** The count starts again in each bar, and the spec's reading rules say how the order number is counted. Test: `test_grace_note_order_starts_again_in_each_bar` (the case above, now 1 missing note and no other errors).

## 4. One bad output can stop the whole run (bug, confirmed)

`harness.evaluate_pair` catches `MusicXMLError` and `ValueError` only. Anything else escapes the worker, `future.result()` raises in the main process, and the evaluation of every pair stops.

Confirmed:

- A flag entry without `"part"` raises `KeyError`, and a flag that is not an object raises `AttributeError`. `read_flags` should check each entry and raise `ValueError` with a plain message.
- An output with a lower-case step (`<step>d</step>`) raises `KeyError` in `Pitch.sounding` during step 4. The reader should check the step (A to G) and raise `MusicXMLError`.
- An output whose clef has `number="x"` raises `ValueError` in the reader, which the harness reports as "the flag file could not be read". The reader's own `int()` calls (`clef number`, `key number`) should go through `_number` or raise `MusicXMLError`.

Also, a flag file that cannot be read makes the whole file a failure, so all its notes count as missing although the MusicXML is fine. Recommend: score the notes, treat the flags as absent, and say in the report that the flag file could not be read. Finally, `evaluate_pair` should catch any other exception from comparing an output and record it as a failed file with the error text, so that one strange output never stops a run of 1,778 pairs.

**Fixed on 6 October 2026.**

- `read_flags` checks every entry (an object, with `part` and `bar` whole numbers from 1, and `staff` likewise if given) and raises `ValueError` with the flag's number.
- A flag file that cannot be read now counts as no flags. The notes are still scored, the file's report gives the reason, and the overall report says how many flag files could not be read.
- The reader checks each step (A to G), clef number, key staff number and fifths value, and raises `MusicXMLError` with a plain message, so the output is a failed file with the right reason.
- Any other error while comparing a pair is recorded as a harness error for that pair ("the harness failed on this pair", with the error), the run goes on, and the command ends with an error status. The overall report lists these under "Pairs the harness could not evaluate". A harness error is not counted against the recogniser, because it is the harness's fault.
- Tests: `test_bad_flag_file_counts_as_no_flags_and_the_notes_are_still_scored` (3 cases), `test_odd_output_is_a_failed_file_with_a_plain_reason` (3 cases) and `test_a_harness_error_on_one_pair_does_not_stop_the_run`.

## 5. The damaged recogniser does 7 of the spec's 10 kinds of damage (gap, by reading)

Not implemented: moving a chord's notes into a second voice, deleting a hairpin, and removing a clef, key or time change. The hand-made tests cover a chord split into voices and a changed time signature, but not on real scores. Either add them or remove them from the spec's list.

**Done on 6 October 2026.** All three are added, each in its own bar: a chord's other notes are moved to a new voice with a `backup` (no note errors, voice accuracy unchanged), a hairpin is removed where no other hairpin of the same kind starts in that bar and part (one hairpin missed), and a clef, key or time change after the first bar is removed (one structural error). `check_harness.py` now checks hairpins as well. On the 256 regression pairs: a chord split on 94 pairs, a hairpin removed on 23, and a change removed on 53. The spec's damage list now describes the duration damage as implemented (the notated value changes, the `duration` stays).

For the damage that is implemented, two effects hold on the corpus but not in every possible file:

- The join assumes the first bar's content ends where the bar ends. The reader offsets the second bar by the first bar's reach, but the appended content starts wherever the last voice of the first bar stopped. A bar whose last-written voice is shorter than the bar (with no `forward` to the end) would put the second bar's notes early, and every one would be an error.
- The pitch change avoids clashing with its own chord only. If another voice or the other staff of a piano has the new pitch at the same onset with the same value, the counts still come out as one pitch error, so the expected figures hold. No change needed.

## 6. Questions the brief asked, with recommendations

- **Staff pairing by order when the counts agree.** I recommend keeping it, because similarity pairing can swap two similar parts (first and second violin in unison passages) and turn a correct file into hundreds of errors. But add a structural check: when similarity pairing disagrees with order pairing by a clear margin, list "the parts appear to be in a different order" as a structural mismatch, so the cause is visible in the report rather than hidden behind the note errors.

  **Done on 6 October 2026.** Pairing stays in order. When similarity pairing is better by at least 0.3 for each staff that moves, the structure lists "The parts seem to be in a different order: output part 1 looks like Cello; ...". Test: `test_parts_in_a_different_order_are_a_structural_mismatch`, which also checks that two parts with the same music in the right order give no such line.
- **The band** (difference in bar counts plus 20). Confirmed it can matter: 60 distinct bars, an output that drops the first 30 and adds 30 wrong bars at the end, scores 30 exact matches where the best alignment gives 60. That needs a recogniser to lose and then add the same number of bars, so it is unlikely. A cheap guard: if the cheapest path touches the edge of the band, run again with a band twice as wide.

  **Done on 6 October 2026, with an exact test instead of the edge guard.** The edge guard failed in the simplest case: when no bars in the band match, the plain diagonal costs the same as any other path and never reaches the edge. Instead: a path that leaves the band needs at least 2 × (band + 1) − (difference in bar counts) missing, extra or joined bars, each costing at least 1. If the best path in the band costs no more than that, nothing outside can beat it. Otherwise the band doubles, up to the whole table. Perfect and nearly perfect outputs never widen. A full-width search on the largest development score (152 bars, 5,857 notes) takes about 2 seconds. Test: `test_band_widens_when_the_best_path_needs_it`.
- **Ties in the alignment.** The spec says one-to-one pairing wins a tie. The code keeps the first cost that reaches a cell, and joins from the row before reach a cell before the diagonal does, so a join wins a tie. A single join costs a whole number plus 1.5, so it cannot tie with a path of pairs alone; only paths with two joins can. This does not matter in practice, but the code and the spec disagree. Fix by preferring (1, 1) when costs are equal.

  **Done on 6 October 2026.** A one-to-one pairing now replaces an equal-cost move into the same cell. No test, because a tie needs two joins against a run of pairs, which is hard to build by hand. The regression and development checks pass with it.
- **Structure per part.** A missing repeat in a 10-part score gives 10 lines. Recommend grouping a mismatch found in every part into one line ("all 10 parts"). Repeats, endings, navigation marks and time signatures belong to the whole score, so one line is what a reader wants. Structural correctness itself is unchanged. The same applies to piano written as two parts against one: the second output part's repeats and time signatures are counted twice against the one ground-truth part.

  **Done on 6 October 2026.** A mismatch that every part has in the same bar is one line ("Bar 17, all 10 parts: ..."). Clefs stay per staff. The output's structure events are counted per output part and the largest count kept, so a part written as two is not counted twice. Tests: `test_a_mismatch_in_every_part_is_one_line`, `test_piano_as_two_parts_does_not_count_its_repeats_twice`.
- **Dynamics in `notations` and in `direction`.** Both are read and both are counted. A file with both forms for one dynamic counts it twice; in the ground truth that adds one truth marking, in an output it lowers precision. MuseScore writes only `direction`, so this is not urgent.
- **Flags for a ground-truth bar with no output bar.** The code follows the spec. The errors in such a bar are not added to "flagged bars with an error", so that share is a little low. Minor.

  **Done on 6 October 2026** (with the last point in finding 7). A flagged bar now counts as having an error when one of its flags covers an error by the coverage rule, including the bars beside a gap.

## 7. Smaller points

- The spec asks for marking figures to be reported separately for exact and engraver-input pairs. Only the ACC-6 line is restricted to exact pairs; the other marking and note-mark figures mix both.
- The spec asks for the per-file spread (median and lowest 10 files). The overall report gives the lowest 10 but no median.
- The per-file summary does not give "N errors in M bars" as in the spec's example.
- "flagged bars with an error" counts a bar when the flag names one staff and the error is on another.

**All four done on 6 October 2026.** The overall report has a "Markings found, by ground-truth kind" section, with exact and engraver-input pairs given separately for every marking and note mark, and a "Per-file note accuracy" line (median, lowest, highest). The per-file summary and the log line say "12 note errors in 6 bars". Flagged bars count an error only when a flag covers it, by staff (finding 6). Tests: `test_reports_give_errors_in_bars_the_median_and_markings_by_ground_truth_kind`, `test_a_flag_on_another_staff_does_not_make_a_bar_count_as_having_an_error`.
