# Opus review of Stage 8, first task: findings

Review of 7 October 2026 of the uncommitted change to the "unknown, probably music" font rule (`classify_fonts` and `_mostly_inside_staves` in `src/omr/pdf/evidence.py`, the spec in `docs/notes/inspector-spec.md`, and the four `test_unknown_font_*` tests in `tests/test_inspect.py`). Findings are in order of importance. Each one says whether it was confirmed by running something or found by reading the code.

## Summary

- The code does what the spec says, and 186 of 186 tests pass. The new tests are real: the first fails on the old letter rule, and the half-and-half test fails if the half condition is removed or lowered.
- The main weakness is the threshold. Requiring half of a font's glyphs to sit inside a staff misses real music fonts on about 1 page in 9, and a miss can be silent: the page comes out as Type B with high confidence and no warning (finding 1).
- One regression: on a page where the staff finder makes a false staff out of repeated "cresc." lines, a text font is now classed as probably music. The old letter rule would have rejected it (finding 2). It is rare and easy to fix.
- The "glyph centre" is not the centre of the ink. It is the middle of the font's ascender-to-descender box, so it sits a fixed distance from the baseline that depends on the font's metrics (finding 3).
- The tests do not pin the "no margin" decision (finding 4).
- Page rotation and crop boxes are not a problem: staves and glyphs are in the same coordinate space (finding 5).
- Recommendation: lower the threshold to a quarter, keep the 10-glyph minimum, ignore staff boxes of the wrong height, count a glyph if either its origin or its centre is inside, and warn about any unclassified font with many glyphs on staves.

## Evidence used

- A survey script (kept outside the repository) ran the inspector's own functions over 500 PDFs drawn at random from `E:\OMAIRCorpus\generated` (2,034 PDFs) and the OpenScore string quartet PDFs (983), 4,148 pages with staves in all. For every font with at least 10 glyphs on a page, it counted the glyphs inside a staff by the new rule, with a one-space margin, by glyph origin instead of centre, and with the origin moved up or down by up to 1.5 staff spaces.
- The corpus has no Sibelius or Finale legacy fonts. The only real legacy font is LilyPond's Emmentaler (52 files). The SMuFL fonts are used as stand-ins: MuseScore, like Sibelius and Finale, draws stems, beams, slurs and staff lines as lines and puts noteheads, clefs, accessories, rests, flags, dynamics and articulations in the music font. So the share of SMuFL glyphs inside staves is a fair guide to what a legacy font would show. That is an assumption, not a measurement.
- Mutation tests: the new tests were run against altered copies of `evidence.py` in a scratch folder (the old rule, no half condition, a one-space and a two-space margin, no 10-inside minimum, a third, a quarter). The working tree was not changed.

## Findings

### 1. Half is too strict, and a miss can be silent (design weakness, confirmed by running)

For pages whose main music font is SMuFL or legacy (3,955 pages), the share of glyphs inside a staff has a median of 0.66. The share of pages that would fail the rule at each threshold:

- Half: 451 pages (11 percent).
- 0.4: 141 pages (3.6 percent).
- A third: 54 pages (1.4 percent).
- A quarter: 14 pages (0.4 percent).

The rule works page by page, so a font needs to pass on only one page of a file to be listed. The number of files (445) whose main music font never passes on any page:

- Half: 11 files (2.5 percent).
- 0.4: 5 files.
- A third: 4 files.
- A quarter: 1 file.

The pages that fail are the expected ones: violin parts with long high passages on ledger lines (four single-page Dvořák parts at shares of 0.22 to 0.48), and dense scores with many dynamics, articulations and flags outside the staff.

Emmentaler, the one real legacy font, shows the same picture: median share 0.67, 55 of 278 pages fail at half (20 percent) and 9 at a third; 2 of 52 files never pass at half, none at a third. The repository's own `tests/data/inspect/lilypond.pdf` sits at 0.58, only just over the line.

Text fonts are far from any of these thresholds. Of 7,737 text-font entries (a font with at least 10 glyphs on a page), none has 10 or more glyphs inside staves and a share of a fifth or more, except the false-staff case in finding 2. Down to a tenth, the only two others are also on pages with false staves. Lyrics, chord symbols, tempo text, titles and measure numbers all sit outside the five lines.

What a miss costs: with `is_legacy_name` disabled, the LilyPond output of `pdmx-5zrh8nmuVjih` (Emmentaler at a share of 0.33) comes out as "Type B, high confidence, 24 outlined shapes repeated", with no warning. So a missed legacy font is not only unlisted; the page is mislabelled with high confidence and nothing tells the survey to look at it. On a page with no outlined shapes the result would be "Type B, low confidence", which does warn, but without naming the font.

Recommended fix:

- Lower the threshold to a quarter, and keep "at least 10 glyphs inside". On this sample that misses 1 file in 445 and accepts no text font once finding 2 is fixed. A third is the cautious alternative (4 files missed).
- Add a weaker warning that cannot be missed: on any page with staves, name every font that is not classed as music but has at least 10 glyphs inside staves, with its share, for example "font with glyphs on the staff: NAME (12 of 40)". This is cheap and is what the survey needs to grow the legacy list.
- Put the inside count in the JSON output for each font, so the survey can be re-thresholded without re-running.
- The half-and-half test (12 inside, 20 outside, share 0.375) must change with the threshold; for a quarter, use for example 10 inside and 40 outside.

What would settle the threshold: in the Stage 8 survey, the fonts already on the legacy list (Opus, Maestro, Petrucci, Engraver and so on) are known positives. Record the inside share for every font on every page, then measure what share of files with a listed legacy font would also pass rule 3 at each threshold, and what share of text fonts would. Pick the lowest threshold at which text fonts stay rare. This uses real Sibelius and Finale output and needs no extra collection.

### 2. False staves from repeated lines let a text font through (regression, confirmed by running)

Page 63 of the Hugo Wolf string quartet (`sources\openscore\StringQuartets\scores\Wolf,_Hugo\String_Quartet\sq8823783.pdf`, staff space 3.2 points) has a "staff" 135 points tall, from x 74 to 374. It is made of five equally spaced horizontal lines that are not staff lines: probably the "cresc." extension lines of the four instruments plus one more line. The four "cresc." words and six tuplet "3"s in Edwin-Italic sit on those lines, so 39 of the font's 57 glyphs (68 percent) are "inside a staff", and Edwin-Italic is classed "unknown font, probably music". The old rule rejected it because every glyph is a letter, digit, full stop or space.

How common: in the 500-file sample, 57 of 47,192 staff boxes (on 20 of 4,148 pages) are more than a third away from four times the page's median staff space. Some are 210 to 255 points tall. Every text-font false accept found in the survey, down to a share of a tenth, is on one of these pages.

Recommended fix: in `_glyphs_in_staves` (or better in `find_staves`, which would also correct the staff count), ignore a box whose height is not within about 25 percent of four times the page's median staff space. Add a test: five equally spaced long lines far apart with text on them, which must stay text.

### 3. The glyph centre is a font-metric box, not the ink (limitation, confirmed by running)

`get_texttrace` gives every character in a span the same box height: the font's ascender to descender, scaled by the size. In the test PDFs every Bravura glyph box is 19.9 points tall, every Emmentaler box 19.8. So the "centre" is the baseline moved by a fixed amount that depends only on the font's metrics:

- Bravura (and the other MuseScore 4 SMuFL fonts): 0, because SMuFL fonts have equal ascender and descender.
- MScore (MuseScore 3): 1.3 points above the baseline, about a quarter of a staff space.
- Emmentaler: 3.0 points above, about 0.6 of a staff space.

A legacy font with lopsided metrics could put the centre of every glyph a staff space or more away from the symbol. Moving the glyph origins of the survey fonts by a fixed amount shows the effect at the half threshold: page failures rise from 11 percent to 18 percent at one space up and 27 percent at one space down, and to 29 and 41 percent at one and a half spaces. A lower threshold softens this as well: at a quarter, one and a half spaces up fails 3.6 percent of pages.

Music fonts are designed with the baseline at the symbol's staff position (SMuFL requires it, and Sibelius and Finale fonts follow the same habit as far as is known; this last point is from reading, not checked on real files). So the glyph origin is the more reliable point for music, while the centre is better for text. Measured: counting by origin instead of centre makes little difference for SMuFL fonts and a small one for Emmentaler (pages failing at half fall from 55 to 37 of 278; files never passing from 2 to 1 of 52).

Recommended fix: count a glyph as inside if either its origin or its centre is inside. This cannot hurt a music font, and text fonts barely sit inside staves by either measure. `read_text_glyphs` already reads the origin; it only needs keeping. Note it in the spec.

### 4. The tests do not pin the "no margin" decision (test gap, confirmed by running)

The mutation runs:

- The old letter rule: the first test fails. Good.
- No half condition, or a third, or a quarter: the half-and-half test fails. Good, but see finding 1: it pins the threshold between 0.375 and 0.5.
- A one-space or two-space margin outside the staff: all four tests pass. The "above" glyphs are 40 points above the top line, far beyond any margin, so the spec's "no margin, so fingerings and lyrics do not count" has no test.
- No "at least 10 inside" minimum: all four tests pass. The "fewer than 10" test has 9 glyphs in all, so it tests the 10-glyph minimum on the whole font, not the 10-inside minimum.

Recommended fix: add a test with glyphs about half a staff space above the top line, as fingerings would be, which must not count; and a test with, say, 15 glyphs of which 9 are inside, which must be text. If finding 3 is taken up, place the test glyphs so that origin and centre fall on different sides of a staff line.

### 5. Coordinates, rotation and crop boxes (sound, confirmed by running)

Staff boxes come from `get_drawings` and glyph centres from `get_texttrace`. A test page was rotated by 0, 90, 180 and 270 degrees, with and without a crop box offset by 30 and 40 points. In every case the staff box and the glyph centres moved together (both are in the unrotated page space relative to the crop box) and the font was classed the same.

Not covered, by reading: a landscape page drawn on a portrait page with a rotation in the content stream has vertical staff lines. `read_drawings` takes only horizontal lines as staff candidates, so no staves are found and no font can pass rule 3. This was already true of the old rule.

### 6. Other failure modes (mostly by reading)

- Multiple staves per system: each five-line staff is its own box, and the space between staves is outside every box. Confirmed by the survey: lyrics and text between staves do not count.
- Pages with only one-line staves (percussion) or only six-line staves (tablature) have no five-line boxes, so a legacy percussion or tablature font on such a page can never pass. Percussion on five-line staves is fine. A possible later fix is to give one-line staves a box of two staff spaces each side; not needed now.
- Legacy companion fonts that sit outside the staff, such as chord-symbol, ornament, metronome-mark and figured-bass fonts (Sibelius has Opus Chords, Opus Ornaments, Opus Metronome, Opus Figured Bass and others), will be classed text. That is acceptable for Stage 8: the main music font of the same family sits on the staff and will be listed, and the family name can then be added to the list. The warning in finding 1 would also catch some of them.
- Text fonts that do sit inside staves: guitar and keyboard fingerings placed beside noteheads, time signatures set in a text font, "G.P." or "tacet" on empty bars. If such a font is used for little else, it will be classed probably music. That costs a warning, and its glyphs are added to the page's music glyph count. Neither changes a page that already has a real music font. None was seen in the corpus apart from finding 2, but the corpus is all MuseScore, LilyPond and Verovio output.
- A font used for both music and text: the share of its glyphs inside staves falls with every text glyph, so a lower threshold (finding 1) is the protection here too.
- Spaces count as glyphs. They make a text font less likely to pass, which is the safe direction.
- A secondary Bravura font on a MuseScore 3 page (`pdmx-ABouJmCXK9ao`, page 3) with 16 noteheads at U+F4BC and U+F4BE and one standard-range glyph fails the SMuFL test and is classed probably music. That is a sensible result and the old rule did the same; it is noted because it adds "Bravura" to the unknown list now and then.
- Type 3 fonts: their ascender and descender may be missing or wrong, which would make the centre unreliable. Not tested; the origin (finding 3) avoids the problem.

## Not changed by this review

No source, test or spec file was changed. Scratch scripts and survey results are in the session scratch folder, not in the repository.


## Follow-up, 7 October 2026

The owner asked for findings 1 to 4 to be fixed, plus the warning and the JSON count. Done: threshold lowered to a quarter, origin or centre test, staff boxes filtered by height, `glyphs_on_staves` in the JSON, the text-font warning, and tests for no margin, the 10-inside minimum, the quarter threshold and the false staff (190 tests pass; removing the staff-height filter or the origin test makes the matching test fail). Not done: finding 6 items (one-line staves, companion fonts, Type 3), which the survey will show.
