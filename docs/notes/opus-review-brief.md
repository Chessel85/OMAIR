# Review brief for Stages 4 and 5

Written 6 October 2026 by Sonnet, for an Opus review. The plan (`docs/plans/phase0.md`) says Opus reviews the Stage 4 inspector and the Stage 5 sampling after Sonnet implements them. This note says what was built, where it departs from the specifications, and where mistakes are most likely. It states what was checked and what was not.

## What to review, in order of importance

1. **Stage 4 classification rules** against `docs/notes/inspector-spec.md` (Phase 1 builds on them).
2. **Stage 5 sampling and pool split** against `docs/notes/corpus-sampling.md`. A leak between pools, or a wrong ground truth, would be silent and would affect Stage 6 onwards.
3. **The engraver exports and the checks on them.**

Run `python -m pytest` first. 70 tests pass on Windows. Tests do not run the engraver programs, except that the test PDFs in `tests/data/inspect/` were made with them.

## Stage 4: PDF inspector

Files: `src/omr/pdf/evidence.py` (extraction), `src/omr/pdf/classify.py` (rules), `src/omr/inspect.py` (files, report, JSON), `src/omr/cli.py` (the command), `tests/test_inspect.py`, and test PDFs in `tests/data/inspect/` (made by `scripts/make_inspect_testdata.py` from Bach BWV 66.6).

Done and checked:

- All expected results in the spec's Tests section hold. Eight MuseScore font exports are Type A with SMuFL fonts, LilyPond is Type A with the legacy font and no Unicode values, Verovio is Type B, and the built raster, rotated, text-only, hidden-text and background cases behave as specified.
- A vector page takes 0.01 to 0.12 seconds.
- The owner read a report with NVDA and found it fine.
- The first full corpus run (2,058 exports attempted, all inspected, 2,034 made) exposed two problems, both fixed.

Departures from the spec, all written back into the spec:

- **SMuFL font test.** It uses at least 80 percent of glyphs in the Private Use Area (U+E000 to U+F8FF) and at least 20 percent in the standard SMuFL range. Bravura and Petaluma, as MuseScore 4 writes them, draw noteheads from U+F4BE.
- **Staff-line grouping** uses overlap with the longer line. The shorter-line version let ledger lines join a staff and made false six-line staves.
- **Sparse pages.** A page with staves and 3 to 9 music glyphs (or repeated shapes) is Type A (or B) with medium confidence. Without this, the last page of a score was called low-confidence Type B.
- The example in the spec said 8 staves. The chorale has 12.

Where mistakes are most likely (not tested, or only lightly tested):

- **Legacy font names by prefix.** "Ash", "Jazz", "Opus" and "Pori" are prefixes of ordinary text font names. A text font that starts with one of them would be classed legacy. Stage 8 should show how often.
- **The "unknown, probably music" class** has no test file. Its tests (10 glyphs inside staves, under half letters) are written but never exercised.
- **One-line staves (percussion).** The heuristic (5 or more glyph centres within 8 points of a line) is untested.
- **Fingerprinting outlined shapes** rounds to 0.05 of a staff space. Rounding at a boundary could split identical shapes. It worked on the Verovio test (19 distinct shapes, one repeated 157 times), but not on other engravers' outlined output.
- **Type C and D thresholds** (background range 40, dark border 30 percent, tilt 0.3 degrees) are the spec's starting values and have been tested only on synthetic pages built from a MuseScore render. Real scans are untested. The measured tilt is the correction angle, so its sign is opposite to the page rotation.
- **Runs of 10 or more equally spaced lines** are split into staves of five. This is a guess for stacked staves with no gap between them.
- **Image input** (PNG, JPEG, TIFF) is converted to a one-page PDF with PyMuPDF, so the dpi comes from the file's metadata or a 72 dpi default.
- **Several other Python-level checks** (merging line pieces, the thickness test of a third of the staff space) are exercised only through the engraver test files.

## Stage 5: corpus generator

Files: `src/omr/corpus/` (`config.py` has every number, `labels.py`, `sources.py`, `roundtrip.py`, `select.py`, `generate.py`, `engravers.py`), the driver `scripts/build_corpus.py`, `scripts/public_domain_composers.txt`, the selection files in `docs/corpus-selection/`, and `tests/test_corpus.py`.

Results, on `E:\OMAIRCorpus\generated`:

- Development: 300 scores, 1,778 pairs, 22 failures.
- Regression: 43 scores, 256 pairs, 2 failures.
- All 24 failures are LilyPond or its converter `musicxml2ly`. They are logged and recorded; they are not retried unless asked.
- Shortfalls against the rules are in the header of each selection file and in `docs/plans/phase0-progress.md`.

How a score is chosen, in brief: metadata filters from `PDMX.csv`, then the hash-based pool split on the work key with seed 20261005, then parsing of only the development and regression pools, then greedy drawing in texture order, with a round-trip check applied lazily to each pick.

Departures from the spec, all written into `corpus-sampling.md` under "Implementation notes" and "Guitar and tablature":

- **OpenScore** `.mxl` files in the repositories are used directly, instead of converting MuseScore files.
- **Guitar** is a priority feature (minimum 15 in development, 3 in regression). Scores with a tablature staff stay excluded, by the owner's decision.
- **Part detection** uses instrument-sound identifiers, with the part name only as a fallback.
- **Public-domain composer check** matches whole-word phrases and refuses composer strings that mention an arranger, editor or lyricist.

Where mistakes are most likely:

- **The work key is approximate.** It uses the last word of the composer and the title with some noise words and catalogue numbers removed. Two arrangements of one piece that are titled differently could land in different pools. Nothing has measured how often. The spec's claim "no piece in more than one pool" depends on it. A useful check: find near-duplicate titles by the same composer that sit in different pools.
- **Ground truth for the font variants.** Every engraver is fed `reference.musicxml`, which is MuseScore 4's export of the source file. The metadata says `reference, exact` for MuseScore 4 pairs, but that PDF comes from MuseScore 4 re-importing its own export, not from the original load. This is probably identical but was not verified. MuseScore 3, LilyPond and Verovio are marked `reference, engraver input`.
- **The round-trip filter** keeps a score only if MuseScore 4's export, re-imported and re-exported by MuseScore 3, has zero differences in notes and rests by musicdiff (`DetailLevel.NotesAndRests`). Whether this is too strict or too loose has not been examined. In the regression draw about a quarter of picked candidates were rejected by it or by the page limit (15 of 58). In the development draw it was under a tenth (about 23 of 323).
- **The staff size** of the MuseScore 4 variants (1.5, 1.75 or 2.0 mm) is set through the MusicXML `scaling` element. The export check verifies the font and page types, not the staff size. The inspector reports the staff space, so a check is easy to add.
- **The export check for LilyPond** accepts any music font whose name starts with "Emmentaler", and for Verovio checks only the page type.
- **The regression page limit** is measured on the MuseScore 4 export with the default font.
- **Genre and texture labels.** The genre mapping from PDMX tags and the keyword rules for educational scores are heuristic. About a fifth of the development set (61 of 300) has no genre ("unlabelled"), which can fill texture quotas but not genre quotas.
- **Copyright of the regression set.** The composer list is the owner's responsibility. It was reviewed once and has had names added since (guitar composers, damaged spellings). Titles in `docs/corpus-selection/regression.txt` need the owner's read before they are committed to the repository in Stage 7. Dates in the list's comments come from memory and were not checked against a source.
- **Seed and reproducibility.** The selection depends on the candidate cache, which depends on the data files and on the labels code. Changing the labels (as the guitar change did) changes the selection. The selection files are the record.
- **Cache files** under `work/` are rebuilt by `build_corpus.py candidates --refresh`.

## Housekeeping

- CI installs PyMuPDF, OpenCV, numpy, Verovio and music21 so the tests run. CI has not yet been confirmed green after the last pushes; check it.
- The licence register has no entry for any new dependency, since none was added. A font-reading library (fontTools) will be needed in Phase 1 and must be added to the register then.
- `.gitignore` entries `corpus/`, `renders/` and `models/` are anchored to the repository root.
- The corpus, caches, logs and downloads are on the corpus drive or git-ignored. Nothing from them is committed except the two selection files.

## Open decisions for the owner (not for the reviewer)

- Review of `scripts/public_domain_composers.txt` and the regression titles, then whether to extend the list and redraw the regression set to fill the shortfalls (jazz, sacred, educational, popular, small ensemble).
- Whether to download the PDMX PDFs (9.6 GB) for Stage 8.
- Whether tablature enters scope earlier than the plan says.
