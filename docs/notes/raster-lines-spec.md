# Lines in page images (Phase 2, Stage 2.2)

How the staff lines and the other lines of a clean page image are found and handed to the vector reader, and how they are checked against the vector reading. The plan is `docs/plans/phase2.md`, Stage 2.2.

## Principles

- **The reader stays as it is.** The vector reader takes its lines from a PDF's drawings, in four places: `evidence.read_drawings` (level lines, for staves, ledger lines and endings), `layout.vertical_lines` (barlines, stems, brackets), `notation.page_shapes` (beams, curves, thin and dashed lines, frames, hyphens) and `symbols.py` (braces and glyphs drawn as outlines). The line finder gives the image's lines in the same form, as PyMuPDF drawing dictionaries in page points, so the first three take them unchanged. `symbols.py` is not fed: in the raster path its symbols come from the detector (Stage 2.3).
- **Lines come after symbols.** In Engine 1 the detector runs first, and the line finder uses its boxes: a line almost wholly inside a symbol's box (a clef's upright stroke, the strokes of a sharp, the inside of a notehead) is part of the symbol, and symbol ink is taken away before beams are looked for. For this stage's check the vector reader's symbols and ink boxes stand for the detector's, which are trained to the same boxes (`raster-labels-spec.md`).
- **Classical image processing.** Clean pages need no learning for lines: runs of ink along the rows and columns, joined across, with tests on their ends. Runs are found with numpy; OpenCV fills beam shapes, bridges gaps and labels pieces of ink.
- **Code:** `src/omr/raster/lines.py` (finding lines, in pixels), `src/omr/raster/page.py` (the page image, pixels to points, drawings, `RasterPage`), `src/omr/raster/check.py` (the check) and the driver `scripts/check_raster_lines.py`.

## The page image

- The largest image on the PDF page, as greyscale, and the rectangle it fills, which gives the scale from pixels to points. A colour image is turned to grey; a 1-bit image reads as 0 and 255.
- **Ink** is every pixel darker than 170 (out of 255). Darker than half grey would lose the faint edges of thin lines at low resolution; 170 keeps them. At low resolution (a staff space under 12 pixels, which is 150 dpi for most staff sizes) level lines are looked for in pixels darker than 200: a thin staff line there (MuseScore 3 draws them 0.31 points thick, two thirds of a pixel at 150 dpi) is a pair of rows at grey 170 or so, and whole lines were lost. The lighter level is not used above that, where it cost notes.
- **Staff space**, in pixels: the commonest white run between black runs down the columns, plus the commonest black run (the staff line thickness). Every size below is in staff spaces.

## Tilt

- Before anything else the page is turned level. The tilt is the angle whose row sums are sharpest (the sum of their squares, largest when the staff lines lie along rows), searched within 2 degrees each way in steps of 0.2 degrees on a quarter-size image, then of 0.02 degrees on a half-size one. About 0.1 to 0.3 seconds a page.
- A tilt under 0.04 degrees is left alone. Every rendered page checked measures 0.
- The lines are those of the level page, so the symbols must come from the same level image: in Engine 1 the detector reads the image after this turn.

## Level lines

- Runs of ink along each row, at least half a staff space long.
- Runs on neighbouring rows are joined while both ends stay within 0.1 staff spaces (at least 2 pixels) of the run above, or while the two overlap along 90 percent of the longer (a break of a pixel or two near one end of one row of a staff line). The line's ends are the medians of its runs.
- **Kept if** all of these hold:
  - At most 0.3 staff spaces thick (in rows). Thicker is a beam or a symbol.
  - **Not a stair step.** A sloping thing (a slur, a hairpin arm, a sloping beam) gives a short run in each row, each shifted along from the last. At its end the row above or below carries the ink on unbroken past the end by two pixels or more, while the run's own middle row stops. A line at least 3 staff spaces long must step at both ends, as every row of a sloping beam or line does, so a bracket's hook over one end of a staff line does not reject the line; a shorter one at either end (the short runs at a curve's tapering ends).
  - **Not a slice.** A level beam cut by a staff line leaves runs above and below the line. The row above or below a slice is ink along at least 90 percent of its length.
  - **Not tapering,** for lines under 4 staff spaces (the ones taken away as ledger lines). Every row is ink along at least 75 percent of the line's length. The thick middle of a short tie joins into a level piece whose rows grow shorter towards its outer edge; taken away, it cut the tie in two. Staff lines are not tested, as a tilt left under 0.04 degrees can leave an edge row part full.
  - **Not inside a symbol.** Less than 90 percent of its length lies in a symbol box.
  - **Not a dash** of a dashed line (below).
- **Position to a fraction of a pixel.** At up to 64 places along the line, the centroid of the darkness across it (one pixel beyond its rows on each side) and the darkness summed across it; the line's centre and thickness are the medians, using only places where nothing touches the line when there are at least three. Whole pixels are not enough: a 0.43 point staff line is 1 to 3 rows at 300 dpi depending on where it falls, and the reader's staff test allows only 10 percent unevenness in the gaps.
- Given to the reader as a stroked line with its thickness as the stroke width.

## Staff lines taken away

- Before vertical lines, beams and curves are looked for, the level lines at least 4 staff spaces long are taken away, except their pixels with ink both just above and just below (a barline, a stem, a notehead or beam across the line).
- Both, not either: a staff line in the narrow gap between two beams of a group goes, so the beams stay apart. A beam lying along a line loses the line's rows there, which moves its edge by the line's thickness; the beam rules allow for that.

## Vertical lines

- The same, down the columns, on the ink with the staff lines taken away. At least 0.8 staff spaces long, at most 0.7 staff spaces wide.
- **Side by side.** Lines whose columns touch and whose lengths overlap by at least 80 percent of the longer are one line. The edge columns of a stem can end a pixel or two away from its middle ones; as a separate line the reader took it for a second stem and split the chord. The columns of a notehead beside a stem are much shorter than it and stay apart.
- **Not inside a symbol**, as for level lines, but flags are left out of that test: a stem with a flag lies inside the flag's box at one end and the notehead's at the other, and would otherwise be lost.
- Centre and width to a fraction of a pixel, as for level lines.
- Given to the reader as stroked lines. Barlines, stems, the upright parts of brackets and the hooks of tuplet brackets and endings are all vertical lines; the reader tells them apart.

## Beams

- Found on the ink with the staff lines, the vertical lines and every symbol box (flags too) taken away.
- Runs down each column 0.3 to 0.95 staff spaces long, joined along the page while their top and bottom each move by at most 0.2 staff spaces (at least 3 pixels, a staff line's thickness) from the last column, a little more across a gap. A gap of up to 0.35 staff spaces is allowed, where a stem was taken away.
- **One beam** if at least 0.6 staff spaces long, present in at least 60 percent of its columns, with a straight middle (a fitted line within 0.12 staff spaces in 90 percent of the columns) and an even thickness, sloping at most 45 degrees. The edges are the middle line less and plus half the median thickness: a fit to each edge would follow a staff line touching it here and there.
- **Cut and joined.** A band of runs can carry on across a stem's gap into the next group's beam, which slopes another way: a band that is not one beam is cut at its gaps and the pieces joined again, left to right, while they still make one. Beams that carry on from each other (within 0.35 staff spaces, edges where the first leads, slopes within 0.08) are joined: a note of another voice touching a beam can cut it.
- **On stems.** A beam has a stem at each end, a short one (at most 1.6 staff spaces, a partial beam) at one: a vertical line that reaches the beam and ends within 2.5 staff spaces of it (a stem ends at its outermost beam; a slur crossing the middle of a stem or a barline does not count). The stem must lie at the end: its near edge at most 0.2 staff spaces (at least 3 pixels) beyond the end, as the stem was taken away and the beam found stops beside it, or its middle up to a staff space inside. A stem further out is the next note's: carried out to it, a partial beam (a dotted quaver and semiquaver) became a whole one and changed both notes. This keeps the thick middle of a slur from being taken for a beam. Two exceptions, both needing a **solid** shape (at least 95 percent ink inside, at most 15 percent in the rows just outside its top and bottom edges, tested before the stems are taken away), which a slur's curved, tapering middle is not:
  - A beam longer than 1.6 staff spaces with a stem at one end only: the stem at the other end can be hidden (the reader finds hidden stems from the noteheads).
  - A beam with no stem at all, at least 1.5 staff spaces long and 0.4 thick: the beams of a two-note tremolo float between the notes (whole notes have no stems at all). Thinner bands, such as the middle of a tie, are not taken.
- The beam is then carried out to the outer edge of each stem it has, as the stems were taken away and the beam found stops short of them.
- **One each.** Two pieces of one beam carried out to the same stems are one beam.
- **Middle to a fraction of a pixel,** from the darkness, as for lines. A beam drawn on a staff line is also a level line to the reader, and a beam centre a fraction of a point off moved the staff line and lost the staff.
- Given to the reader as a filled four-sided shape with upright ends, which is what `notation._quad_beam` reads.

## Thin sloping lines and curves

- Found on the ink left when the staff lines, vertical lines, beams, short level lines and symbols are taken away. A gap where a stem or barline was taken away is bridged first (a closing 3 pixels high and 0.35 staff spaces wide).
- **Slanted crossings put back.** A staff line is kept only under ink both just above and just below the same column, so a slur crossing it at a slant was cut at every line. Where the leftover ink is just above the line and, within half a staff space along it with nothing between, just below (or the other way), the line's pixels between the two are put back.
- Each piece of ink at least 0.8 staff spaces wide (the narrowest curve the reader takes), with runs down its columns of at most 0.4 staff spaces, is followed column by column:
  - **Two runs** in more than 30 percent of its columns: a hairpin's two arms. Each arm is fitted to the first and the last run in each column where there are two, and must be straight. Where the arms run together at the closed end, a column holds one run, which bent the fit and threw both arms out (Verovio's hairpins were not found at all); so each arm is carried on along its own line to the point where the two meet, within the piece's ink and half a staff space beyond it.
  - **One run:** straight (within 0.08 staff spaces of a fitted line) and sloping at most 45 degrees, a thin line; otherwise a curve.
- **Hairpin arms found apart.** The closed end of a hairpin can be taken as short level lines first, so its arms come out as two separate thin lines, each starting 1.5 to 3 staff spaces late, and the hairpin rule (`markings.hairpins`, which needs the arms to start within 0.4 staff spaces of each other) rejected them. Two thin lines whose ends at one side are within 0.5 staff spaces along and 0.4 to 3 staff spaces apart across, and that close in on each other towards the other side and meet within 4 staff spaces beyond it, are carried on to where they meet.
- **Level pieces of a thin line.** A level line lying within 0.25 staff spaces of a thin line at both its ends is a piece of that line (a nearly level hairpin arm, or its closed end), and is not given as a level line.
- **Pieces joined.** Two curves are one when the second starts within half a staff space of the first's end (or overlaps it by up to 0.3), within 0.3 staff spaces of the height the first's end leads to, with end slopes within 0.5 of each other. A long slur crossing stems and lines can still be cut.
- **Pale ends followed.** The thin tapering ends of ties and slurs are paler than the ink level, so a trace stopped up to a staff space short. Each end is followed on, column by column for up to a staff space, through pixels darker than 230, along the direction of its last half staff space (within 0.1 staff spaces, at least 2 pixels), across gaps of up to 0.4 staff spaces (a stem, barline or staff line taken away, with the pixels beside it). Pale pixels next to other ink (the soft edge of a staff line or stem) do not count, or ends ran on along them.
- **Decision on curves:** traced from the ink, not a detector class. The detector labels from Stage 2.1 leave curves out on purpose, the reader needs only a curve's ends and box (`notation._curve`), and on clean pages the leftover ink is mostly curves.
- Thin lines are given to the reader as stroked lines, curves as filled shapes whose top and bottom edges are Bezier pieces through points along the trace.

## Dashed lines

- Octave and pedal lines. At least four thin runs 0.2 to 1.5 staff spaces long on one row (within a pixel), evenly spaced (gaps 0.2 to 1.5 staff spaces, within 0.25 of the first gap), on the ink with the staff lines and symbols taken away.
- Given to the reader as one stroked line with a dash pattern, as engravers draw them, and its dashes are not level lines.

## Still to come

- **Curves** are 82.5 percent found at 300 dpi, 76.6 at 200 and 68.8 at 150 (run `s22-run5`). Long slurs crossing many stems and lines can still come out in pieces, and at low resolution ends fall short more often. Ties and slurs do not count in note accuracy, but they do in the MusicXML.
- **Small staves at 150 dpi.** A staff at 7.7 pixels a space can be missed (2 regression pairs).
- **Extra beams at 150 dpi** (about 7,300 on the regression set, against 1,900 at 300 dpi).
- **Verovio beams** are 64.7 percent found at 300 dpi and 64.1 at 200 on the development set (run `s22-dev`), against 92 to 99 percent for the other engravers; half the misses are in 10 of its 300 pairs.
- **Staves lost at 200 dpi in one score** (pdmx-JQFGUynvuWVR, both MuseScore 3 versions: 36 to 42 of 78 staves missed).

## The check

- Each pair of a raster set is read twice with the symbols of its vector PDF: with the PDF's own drawings, and with the lines of its image (`RasterPage`). Both readings run the whole reader, so the staves, barlines and stems compared are the ones the reader settles on, and both are scored against the ground truth: the difference is the notes lost to the image's lines alone.
- **Staves** match when on the same page with the top line within 0.3 staff spaces and each end within 0.6. **Barlines** match when on the same system within 0.5 staff spaces along it. **Stems** match within 0.3 staff spaces across and 0.5 at each end. The share found is against the vector reading; the largest position error is reported in staff spaces.
- **Beams and curves** are compared as the reader's `page_shapes` gives them, matching when each end is within half a staff space. The vector page's curves include symbols drawn as outlines (Verovio draws every symbol so), so only curves not lying mostly inside a symbol's box count. These two are diagnostics, not part of the done condition.
- `python scripts/check_raster_lines.py regression g300 g200 g150` writes `results.jsonl` (one line per pair) and `summary.txt` (totals, and by engraver) to `evaluations/<name>-regression-<version>` on the corpus drive. About 6 minutes a version for the regression set on 3 workers, and about 2 hours 20 minutes a version for the development set. The check set is refused: it stays sealed.
- **Done when** (plan): on the raster regression set, every staff is found, and staff, barline and stem recall against the vector reading is at least 99 percent.
