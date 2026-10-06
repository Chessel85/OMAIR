# Review brief for Stage 6

The review is done. Its findings, and what was done about each, are in `docs/notes/opus-review-findings-stage6.md`. This brief describes the harness as it was handed to the reviewer.

Written 6 October 2026, for an Opus review in a fresh session. The plan (`docs/plans/phase0.md`, Stage 6) is done when the perfect recogniser scores 100 percent, the damaged recogniser scores the expected values, and Opus has reviewed the metric code against the definitions. This note says what was built, what was checked, and where mistakes are most likely.

The definitions are in `docs/notes/evaluation-spec.md`. The owner accepted its decisions on 6 October 2026. Review the code against that file, and report any place where the code and the spec disagree, or where the spec itself is wrong.

## What to review, in order of importance

1. **Matching** (`src/omr/evaluate/match.py`): staff pairing, bar alignment, exact matches and error naming. An error here is silent and changes every later accuracy number.
2. **Reading** (`src/omr/evaluate/events.py`): onsets, durations, chords, grace notes, backup and forward, tuplets, invisible notes, and multi-part files.
3. **Metrics** (`src/omr/evaluate/metrics.py`): note accuracy M / (T + E), structural correctness, marking recall, flag coverage and the diagnostics.
4. **The damaged recogniser** (`src/omr/evaluate/recognisers.py`): does each kind of damage really have the effect it claims, in every case, or only in the cases tested?
5. The runner, reports and command line (`harness.py`, `report.py`, `describe.py`, `src/omr/cli.py`): plain-text output, locations in words, failed files.

Run `python -m pytest` first (158 tests pass on Windows). Then `python scripts/check_harness.py --set regression` (about 3 minutes) runs both test recognisers over the 256 regression pairs and checks each pair's figures.

## What was checked

- The perfect recogniser scores 100 percent on every figure, every file structurally correct, and OMR-NED 0, on all 256 regression pairs. The development set (1,778 pairs) is recorded in `docs/plans/phase0-progress.md`.
- The damaged recogniser scores exactly its expected values on every regression pair. Each pair gets a pitch change, an enharmonic respelling, a deleted chord note, an added chord note, a changed note value, swapped voice numbers, a removed dynamic, and two bars joined near the end. Each damage is in its own bar, and the join comes after all the others.
- Hand-made pairs in `tests/test_evaluate.py`, with the right values worked out by hand: triplets against plain eighths, a triplet after a rest, a tie across a barline, grace notes, a cross-staff note, a pickup and a split bar, a multi-bar rest, a missed and an extra barline, piano as one or two parts, a unison in two voices, different divisions, decimal durations, an empty and an unreadable output, extra notes, a spelling error, an onset cascade, merged voices, dynamics inside and outside the one-beat window, a changed time signature, flag coverage, and the wording of an error.
- Speed: the largest development score (5,857 notes) reads and matches in about 2 seconds. musicdiff takes as long again or longer.

## Where mistakes are most likely

- **Bar alignment costs.** Costs are counted in unmatched notes and rests; a join adds 1.5, and a missing bar costs its event count (at least 1). The first version used shares and joined bars wrongly on one development score (two identical one-note bars, the second with a wrong value); a test now reproduces it. Check that a wrong bar cannot be preferred over a join, or a join over a correct pairing, in realistic cases (for example several empty bars in a row, or long runs of identical bars, where many alignments cost the same).
- **The band** in the alignment is the difference in bar counts plus 20. A recogniser that loses a whole page of bars early and adds bars later could need more.
- **Staff pairing by order** when the counts agree. If a recogniser writes the parts in another order, every note becomes an error. The spec accepts this; decide whether it should.
- **Identical notes** (a unison in two voices) are paired by same staff and voice number first, then staff, then any. The first version paired by staff only and invented voice errors on one development score. Pairing by voice number is not enough when the numbers are swapped, so the voice figure also treats a group of identical notes as pairable either way (five tests cover these cases, including one where a real voice error sits next to a unison and must still be counted). Check that the rounds can never change the exact-match count, and that the voice figure cannot hide a real voice error inside a unison.
- **Step 4 pairing** can pair two unrelated notes that share only one property, which names the error oddly but does not change the accuracy. Check that it really never changes M, E or the error count.
- **Grace notes**: the order number counts grace notes since the voice's last main note. Check grace notes in several voices, and a grace note at the end of a bar.
- **Voices**: a voice label in MusicXML is local to its part, so voice accuracy groups output notes by output part and voice label. (This was wrong in the first version and was found while writing this brief; `test_voice_numbers_are_local_to_each_output_part` covers it.) Check cross-staff voices.
- **Structure**: repeats, endings, time and key events are compared per part, so a missing repeat in a 10-part score gives 10 mismatch lines. Check whether that is what the reader of the report wants.
- **Markings**: dynamics inside `notations` on a note are read as well as those in `direction`. Check for double counting if a file has both.
- **Flags**: the rule for an error in a ground-truth bar with no output bar (the neighbouring output bars count).
- **Musicdiff findings** (`docs/notes/corpus-sampling.md`): music21 reads one note an octave higher when an octave line and a hairpin swap order, and musicdiff stops with a recursion error on one score. OMR-NED figures inherit these problems; the project metrics do not.

## Known gaps

- TEDn is not computed (open item, decision 7 in the spec).
- The regression baseline file and the CI job are Stage 7.
- No real recogniser has been run yet. The first will be the Stage 9 baselines.
