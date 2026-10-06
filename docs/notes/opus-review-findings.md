# Opus review of Stages 4 and 5: findings

Review of 6 October 2026, done against `docs/notes/opus-review-brief.md`, `docs/notes/inspector-spec.md` and `docs/notes/corpus-sampling.md`. Findings are in order of importance within each stage. Each one says what was checked and whether it was confirmed by running something, or found by reading the code.

## Summary

- Tests: 70 of 70 passed at the start of the review, 107 after the fixes. CI is green on the last push (run 37433122749, Windows and Linux).
- Two bugs, both now fixed: the round-trip filter treated a musicdiff parse failure as a pass (Stage 5, finding 1), and legacy font names caught companion text fonts (Stage 4, finding 1). The first had let 2 unreadable references into the development set. They have been replaced and the new scores exported.
- One design weakness, now fixed: the work key let arrangements of the same piece into different pools (Stage 5, finding 2). At least 12 development pieces had copies in the training pool. Near copies are now skipped in the draw and removed from the training pool (287 of 62,400).
- Confirmed sound: every MuseScore 4 staff-size variant (343 of 343) came out at exactly the requested staff space; the ground-truth sample check is in Stage 5, finding 3.

## Stage 5: corpus generator

### 1. A musicdiff parse failure counts as a pass (bug, confirmed by reading musicdiff)

`musicdiff.diff()` returns `None` when either file fails to parse, and 0 only when the scores are identical. `roundtrip._run` tests `if edits:`, so `None` falls through to "ok" and the score is kept with an unchecked reference.

**Fixed on 6 October 2026.**

- `roundtrip.compare_notes` passes only on an explicit 0. `None` is rejected with "musicdiff could not parse one of the files".
- Each round-trip record now carries a check version (`CHECK_VERSION = 2`). A passing record from an older version is run again before it is used. Failures are kept as they are.
- All 343 selected scores were re-checked: the MuseScore 3 half of the round trip on the reference, with the fixed comparison. 341 passed. Two development scores failed, both because music21 cannot parse the reference: `pdmx-vW3TwoLx3R1f` (Serenad, Josephson) and `pdmx-HYVdZRJ5M3Et` (Es verdad, Oltra). Their records were marked failed and the other 341 were stamped version 2. The old records are kept in `work/roundtrip-before-v2/`.
- The development set was redrawn. The draw repeated itself up to the first bad score, so 4 scores went out (the 2 bad ones, plus `pdmx-L6i5eRMMCg6S` and `pdmx-U5stbPPjgoPt` as knock-on changes) and 4 came in. The new scores were exported (24 pairs, no failures). The dropped folders were moved to `work/dropped-development/`. The regression set had no bad scores and is unchanged. (The near-copy redraw in finding 2 later brought `pdmx-U5stbPPjgoPt` back.)

### 2. The work key splits arrangements of one piece across pools (design weakness, measured)

The key uses the last word of the composer string. PDMX composer strings often end in dates, arrangers or uploader text, so the last word is often not the composer:

- "Wolfgang Amadeus Mozart 1756-1791" gives `1791`, "J. S. Bach (1685-1750)" gives `1750`.
- "Johann Pachelbel Arranged by Melanie Dean" gives `dean`.
- "Misc Praise Songs" gives `songs`.

35 of the 343 selected scores have an empty or numeric composer word.

Measured over the 222,820 PDMX rows that pass the licence and validity subsets, by matching titles with the existing noise removal:

- **Development and regression selections: no shared piece.** Stage 6 results are not affected.
- **Within the development set:** "All through the night" was selected twice (keys `1931|...` and `graves|...`).
- **Development against the training pool:** 35 selected scores share a title with a score in another pool. About two thirds are clearly the same piece. The largest: Amazing Grace (35 copies in the training pool and 3 in the regression pool), Canon in D (23), Joy to the World (15), Adeste Fideles (11), O Holy Night (7), The Christmas Song (6), When the Saints (6), Over the Rainbow (5). The rest are different pieces with generic titles ("Falling", "Song 1").

This mattered once training data is drawn (the Stage 10 sample and Phase 1 training). Nothing had been trained, so nothing was contaminated.

**Fixed on 6 October 2026**, keeping the work key and the pool split as they were:

- New near-copy rules (`labels.clean_composer`, `labels.piece_title` and `labels.NearCopyIndex`): the composer is reduced to a real surname (dates, brackets and arranger credits removed), and titles match exactly or as a phrase inside a longer title. Generic and one-word titles need the composer to match as well. The rules are in `corpus-sampling.md` under "Near copies".
- **The draw** now skips a near copy of a piece already chosen. Redrawing changed 2 development scores: the second "All through the night" and "Amazing Grace in G" (a second Amazing Grace) went out. `pdmx-U5stbPPjgoPt` and `pdmx-R4GRa9enYji3` came in, and the new one was exported (6 pairs). Sacred fell from 19 to 18 against a minimum of 20. The regression set did not change.
- **The training pool** is built by `scripts/build_corpus.py training`. Of 62,400 training candidates by metadata, 287 are removed as near copies and 62,113 kept. A random sample of the removed scores was nearly all true copies. The few others were different settings of the same words, which is the safe direction.
- **Exact title matching alone was not enough.** It removed only 121 scores and missed "Pachelbel's Canon in D", "Amazing Grace 3 Trombones", "All I Want For Christmas Is You" and similar. Matching any title that contained the selected words was too loose: "Falling" caught 44 scores such as "Can't Help Falling in Love". The phrase rule with two distinctive words sits between them.
- No selected score is now a near copy of another, within a set or across the two sets.

The pool is large enough: removing near copies costs half a percent. The size, notation and round-trip filters have not yet been run on the training pool, so the usable number is not known yet. On the development and regression pools, the size, notation and parse checks kept 10,286 of about 11,000 metadata candidates (about 94 percent), and the round trip then rejected under a tenth of the development picks. Applied to the training pool, that suggests roughly 50,000 usable scores. This is an estimate, not a count. Whether it is enough is a Phase 1 question.

### 3. Ground truth for MuseScore 4 pairs (checked on a sample)

**Decision of 6 October 2026: each MuseScore 4 job will keep its own MusicXML as the pair's answer key, compared with the shared reference and recorded in the metadata. This is the first task of Stage 6.**

The brief asked whether a MuseScore 4 PDF made from `reference.musicxml` matches the reference, given that the reference is MuseScore 4's own export of the source, not the loaded source. Each job also re-exports MusicXML and then deletes it, so the check is cheap to add permanently.

Sample: all 43 regression scores and 20 development scores, re-imported by MuseScore 4 (re-exported MusicXML compared with the reference by musicdiff, notes and rests and full detail) and by MuseScore 3 (compared at notes and rests, with `None` reported separately).

Results (all 63 scores):

- **Notes and rests: no differences** for every score that could be parsed, in both directions. The "reference, exact" label holds for notes and rests.
- **Other content: 3 of 63 differ.** Two swap the order of two dynamics on the same beat (harmless). One (`pdmx-te3axYLtXXV1`) loses 5 of 8 "dim." text expressions when MuseScore 4 re-reads its own export, so its PDF shows fewer than the reference holds. "Exact" therefore means exact for notes and rests, not for every text mark. Stage 6 should score text expressions with that in mind, or each job could keep its own re-exported MusicXML (it is written and then deleted at present).
- **One score could not be parsed at all** (`pdmx-vW3TwoLx3R1f`): music21 rejects a metronome mark with an empty beat unit. This is finding 1 happening in the selected set.

### 4. Smaller points

- **Staff size: confirmed correct.** All 343 MuseScore 4 variants measure exactly 1.5, 1.75 or 2.0 mm. The base exports range from 0.95 to 2.16 mm (median 1.76), because they keep the source file's scaling. A staff-size check in `generate.check_pdf` would cost nothing and guard against a MuseScore update.
- **Catalogue numbers merge different pieces.** "Prelude BWV 846" and "Prelude BWV 847" both become `bach|prelude`. This is safe for leakage but means a set can hold only one Bach prelude. Acceptable; noted.
- **Hymn-layout rule.** A one-part piano score with lyrics on both staves (common in beginner song arrangements) is classed choir and then "choral". Requiring the part not to be a keyboard by sound would separate hymn layouts written as voice parts from piano songs, but MuseScore hymns are often a single piano part, so this needs a look at real cases before changing.
- **The development draw's rejection rate** (about 23 of 323) and the regression's (15 of 58, mostly page limit) look reasonable. Whether the filter is too strict was not examined further.

## Stage 4: PDF inspector

### 1. Legacy names catch companion text fonts (bug, confirmed)

The prefix match classes these as legacy music fonts (checked with `is_legacy_name`): Opus Text, Opus Text Std, Reprise Text, Inkpen2 Text, Engraver Text NCS, JazzText, and Engravers MT and EngraversGothic BT (ordinary Microsoft Office fonts), and AshleyScriptMTStd.

Consequence: Sibelius and Finale PDFs set tempo marks, expressions and sometimes titles in these fonts. Their glyphs count as music glyphs, which inflates counts, and a title page with 10 or more glyphs in one of them is called Type A with medium confidence instead of No music. Stage 8 would see it in exactly the Sibelius and Finale PDFs it is meant to survey.

**Fixed on 6 October 2026.** `is_legacy_name` now never classes a name containing "text" or "times" as legacy. A listed name must also end at a word boundary: the next character must not be a lower-case letter. So "EngraverFontSet", "Opus Std" and "Emmentaler-20" match, but "Engravers MT" and "AshleyScript" do not. `tests/test_inspect.py` checks 18 names. One limit remains: an embedded name written entirely in lower case (such as "opusstd") no longer matches. Whether Opus Chords and Opus Figured Bass count as music is left for Stage 8.

### 2. "Unknown, probably music" will miss most legacy fonts (design weakness, by reading)

**Decision of 6 October 2026: not changed now. It is the first task of Stage 8, before the survey runs.**

The class needs fewer than half of the glyphs to be letters, digits or punctuation. Legacy 8-bit music fonts (the Sibelius and Finale families and their imitators) put their symbols on ordinary character codes: a notehead is "q" or "Ï", both of which count as letters. Such a font with an unlisted name will therefore be classed text, which is the very case the class exists for. No test exercises the class.

Suggested rule: classify by position instead. A font is probably music if at least 10 glyphs, and at least half of its glyphs, have their centre between the top and bottom lines of a staff (the current test allows a staff space beyond them, which catches fingerings and lyrics). Text rarely sits inside a staff. Build a test page with a renamed copy of a legacy font, or by drawing letters onto staff lines.

### 3. Smaller points

- **One-line staves** count any long horizontal line with 5 or more glyph centres within 8 points, from any font, text fonts included. A header rule under a title, or a staff line left over from a run of 7 to 9 lines (which the run code neither counts nor marks), would count. It does not change the type, but Stage 8's percussion numbers would be inflated. Use only music-font glyphs.
- **Thickness test.** When one line in a run is too thick, the whole run is skipped (`i = hi`), so a real staff next to a thick line of the same spacing is lost. Unlikely in engraver output; worth a note for scans converted to vectors.
- **Rule order.** A vector page with a full-page background image and a sparse last page (3 to 9 music glyphs) meets rule 1 first and is called C or D. Rare; the spec's own example of a paper-texture background implies it should be A.
- The bilevel note sets C confidence to medium, which it already is. Harmless.
- The remaining items in the brief's list (shape-fingerprint rounding, C and D thresholds, stacked staves, image dpi) are as described there and are Stage 8 matters. Nothing more was found.
