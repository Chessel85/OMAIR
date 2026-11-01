# Self-check by re-rendering (Stage 2.8, DEV-3)

The music read from a page is written as MusicXML, drawn again by Verovio, and the drawing compared with the page bar by bar and staff by staff. A staff bar whose drawing differs from the page is flagged with the rule "self-check", and the first difference is given in words in the confidence report, for example: "drawn again from the music read, the third note or rest differs from the page: heads on the page at line 2, in the drawing at space 2".

Code: `src/omr/selfcheck.py`; flag rule "self-check", precision 0.23 (`confidence-spec.md`). It runs inside `omr convert` (through `confidence_report.read_file`) and in `scripts/check_flags.py`, for PDFs and page images alike, from `read_pdf(..., notes=True, selfcheck=True)`. Setting `OMR_SELFCHECK=0` turns it off. Tests: `tests/test_selfcheck.py`.

## Why it is there

The rules layer flags bars that break a rule (a voice that does not fill its bar, staves that do not line up in time). An error that breaks no rule is not flagged: a note a step out, a bar's notes in the wrong order, a rest of the wrong length in a voice that still adds up. The page itself shows what is right. Drawing the music read and comparing it with the page catches the errors of putting the music together from symbols that were read rightly.

It cannot catch a symbol the reader did not see: the comparison is between the symbols the reader found on the page and the symbols Verovio draws from the music read, so a missed symbol is missing on both sides.

## How

1. **Draw.** `musicxml.write` writes the score to a temporary file, as the converter writes it. Verovio loads it with the system and page breaks it holds (`breaks: encoded`, all staves shown) and draws SVG. Verovio's SVG names every element (`measure`, `staff`, `note`, `notehead`, `accid`, `rest`, `dots`, `flag`) and gives each glyph as a SMuFL code at a position, so no reading of the drawing is needed. Its MEI gives each note's alteration and whether it has an accidental drawn.
2. **Bars and staves.** The drawing's bars are the score's bars in order; if the counts differ, nothing is flagged. The page's bars are taken from the page layout system by system, where a system has as many bars as the score gives it (bars joined across a line break and multi-bar rests are left out). Staves are matched by part and staff number.
3. **Items** in each staff bar, both sides: noteheads (staff position and kind: black, half, whole, breve), rests (kind), augmentation dots, flags; on the page also accidentals (the alteration each gives). Grace and cue notes are left out on both sides: a head, flag or accidental under 0.85 of the usual ink height for its kind on the page (Verovio's outline pages give every glyph one font size, so the ink is measured), or drawn at under 0.85 of the usual scale. A note drawn on the staff it belongs to stays there in the drawing unless it is drawn more than 5 spaces off it (a cross-staff note). On the page a head is on the nearest staff; a head between two staves can be moved to the other staff when the drawing has a head at that place there and none at the first (a part's high notes nearer the staff above, close staves); its accidental and its dot go with it. A repeat sign's two dots are left out on both sides.
4. **Columns.** The heads and rests of a bar, across its staves, are grouped into columns: closer than half a space in x, or heads on one staff on the same line or space within 1.65 spaces (two voices' unison, which MuseScore 3 draws side by side), or a step apart within 1.35 spaces (a second: one head's width, closer than any two notes one after the other, which Verovio spaces 1.5 spaces apart at the closest). Whole rests stand apart (their place in the bar says nothing of time). Spacing differs between engravers, so only the order of the columns and what they hold is compared.
5. **Compare, staff by staff.** The number of whole rests; the number of columns; then for each column the staff positions of its heads, the kinds of head at each position (one head the page shares between two voices may be two in the drawing), the rests, and whether a dot follows: a dot past a head (at least a space right of its left edge) on its line or the space next to it, or past a rest (a staccato dot sits over or under the head, and Verovio's pages give staccato dots the same glyph as rhythm dots). The beams and flags on each stemmed head's stem: on the page the count the reader found (`notation` keeps it in the page layout, `PageLayout.strokes`), in the drawing the count the note's written value needs (from the MEI's `dur`), compared where both sides have a stemmed head; this is what checks the length of beamed notes. A flag glyph on the page must be in the drawing; a flag in the drawing need not be on the page, since the converter writes no beams and Verovio then flags every short note. Accidentals: an accidental on the page must give the alteration the drawn note has (a courtesy accidental, or a key signature's sharp beside the first note, gives what the note already has); a drawn accidental must have one on the page.

## Left out

- Staves under a clef with no pitch (percussion, tablature), and staff bars with slash noteheads (the converter writes rhythm slashes as ordinary notes).
- A staff bar where two different clefs stand at the same point (an incipit's old clef and the modern one): the drawing may use the other clef.

## Known false flags

- Two-note tremolos (half-note heads joined by strokes, read as two notes in the time of one): the converter writes them as plain short notes, so the drawing has black heads where the page has half heads.
- Errors in rests and voices that the harness does not count as note errors (a whole-bar rest in a voice that has notes, a dotted rest read without its dot) are real, but count against the rule's measured precision, which counts note errors only.

## Comparing pixels

The plan also asked for comparing pixels on clean image pages. It is not done. The drawing is Verovio's engraving, spaced differently from the page, so pixels cannot be compared directly; what a pixel check could add is ink on the page that no symbol, line or text the reader found explains (a symbol the detector missed, which the symbol comparison cannot see). On image pages the flags already hold about 97 percent of the note errors on exact pairs; what is over the limit there is the share of bars flagged, which such a check would only raise. It stays an option for Stage 2.9, if the triage of the raster penalty finds missed symbols to be a large cause.

## Figures

From `scripts/check_flags.py`, which reports each rule alone and the flag file without it (`E:/OMAIRCorpus/evaluations/s35-selfcheck`). ACC-4 is the share of note errors in flagged bars; exact pairs are the MuseScore 4 ones.

- **Vector development set** (1,764 pairs, round 3, final code, none failed): exact pairs 88.8 percent with 3.0 percent of bars flagged without the self-check, 95.7 percent with 3.9 percent flagged with it; all pairs 79.7 to 84.7 percent, 3.8 to 4.7 percent flagged. The rule alone flags 1.3 percent of bars, 22.9 percent of them holding a note error (its precision in `rules.RULE_PRECISION`, 0.23). Comparing beams added 1.1 points to the rule's own recall (38.0 to 39.1 percent) and nothing to the flag file's.
- **Raster development set at 200 dpi, both engines** (1,764 pairs, round 2, with beams compared, none failed): exact pairs 96.6 percent with 12.2 percent of bars flagged without the self-check, 97.0 percent with 13.6 percent flagged with it; all pairs 87.0 to 87.4 percent, 15.2 to 17.3 percent flagged. The rule alone flags 5.4 percent of bars on exact pairs, 26.8 percent of them holding a note error. On images "engines disagree" already flags most of the bars the self-check flags, so the gain is small; what is over the limit there is the share of bars flagged, which needs fewer errors (Stage 2.9).
- **Regression set, vector:** exact pairs 93.9 to 96.1 percent, 5.3 to 7.5 percent flagged. **Raster at 300 dpi, both engines:** 98.3 to 98.9 percent, 20.6 to 21.7 percent flagged.
- **Time:** drawing and comparing take about 0.3 to 4 seconds a score (a 79-bar orchestral score, 4 seconds), beside the reading itself.
