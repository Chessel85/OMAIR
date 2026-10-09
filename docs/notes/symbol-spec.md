# Symbol naming (Phase 1, Stage 1.1)

How every music glyph on a vector PDF page is given a SMuFL name. Code: `src/omr/pdf/symbols.py` (reading a page), `smufl.py` (names and reference shapes), `fonttables.py` (legacy font tables), `shapes.py` (drawing and comparing shapes). Command: `omr symbols FILE...`.

## What a symbol is

- Every glyph of a music font becomes a symbol with a SMuFL name, a position, a size and an ink box.
- The position is the glyph's origin as the page is shown. For SMuFL fonts and the legacy fonts this is the point SMuFL anchors the symbol at: a notehead's centre line, the line a clef names, the line a whole rest hangs from. Measured on Opus, Helsinki, Maestro, Leland and Emmentaler pages: clef and notehead origins fall on a staff step in every font (mean distance 0.00 to 0.07 of a step).
- The one exception is the Sonata whole rest, whose origin is the line below the one it hangs from. Its position is moved up one staff space so that it matches SMuFL.
- The size is the em in points: four staff spaces for a music font at its design size. A notehead much smaller than that is a cue, grace or tempo note.
- The ink box is found by drawing each distinct glyph once from the embedded font program.
- Letters, digits and punctuation in a SMuFL text font (MuseJazz Text, Bravura Text) and punctuation in Emmentaler are text, not symbols. Text fonts give text runs: characters on one line in one font and size, with no gap of more than half an em.
- Two names are used that are not SMuFL glyphs, because a drawing contains them: `lineHook` (the hook at the end of a dashed line) and `ottavaSuffixAlta` and `ottavaSuffixBassa` (the "va" and "vb" after the "8" of an ottava).

## How a font is named

Each font is decided once per document, in this order:

1. **SMuFL fonts** (the inspector's SMuFL class, or a font whose every glyph is a SMuFL code point, such as a page whose only Bravura glyphs are its braces): the code point gives the name.
   - Names come from the SMuFL fonts installed with Verovio, plus a supplement of about 60 names for glyphs Verovio does not draw.
   - Code points from U+F400 up are each font's own glyphs and are named only for a font Verovio has. An optional glyph that only restyles a standard one (Oversized, Large, Larger, Narrow, Straight, Short, Light) is named as the standard glyph; MuseScore 4 draws noteheads in Bravura as `noteheadBlackOversized`. "Small" is kept, because it marks cue size.
2. **Legacy fonts known by name**: Emmentaler and its sizes (`Emmentaler-NN`, `PFAEmmentaler-NN`, `feta-alphabetNN`, `Emmentaler-Brace`) use the Emmentaler table. Opus, Helsinki, Maestro and the other Sibelius and Finale font families use the Sonata table, and their "Special" companions use the Sonata companion table. Their "Text" companions are text.
3. **Fonts whose embedded glyph names are Emmentaler's** (`noteheads.s2`, `clefs.G` and so on): the Emmentaler table.
4. **Renamed fonts**: printer drivers rename fonts (`TTE26B52B8t00`, `TT188t00`). A font that is legacy or probably music by the inspector's position test, or whose name has this form, is identified by its glyph shapes (below).
5. Anything else is text.

## Font tables

### Emmentaler

- Emmentaler has no character codes: every glyph is U+FFFD, and the glyph names in the embedded font program (CFF charset or TrueType glyph order) identify the symbols.
- The table maps LilyPond glyph names to SMuFL names. It includes the names of LilyPond before 2.12 (`accidentals.2` for a sharp, `accidentals.M2` for a flat), the `_change` clefs (smaller clefs for a change), `.figbass` accidentals, every brace size (`brace0` to `brace575`), and shape-note heads (named as a black, half or whole notehead).
- Digits are time-signature digits and the letters f, m, n, p, r, s and z are dynamics, by name or by their character codes.

### Sonata layout (Opus, Helsinki, Maestro)

- These are 8-bit fonts on the layout of Adobe's Sonata: the same byte means the same symbol in all three. The byte is read from the text layer: a Windows symbol-font code (U+F020 to U+F0FF) less U+F000, or a Unicode character from the Mac Roman set (a filled notehead is "Œ", U+0153, Mac Roman 0xCF).
- The table was built by drawing every glyph of the installed Maestro font and every glyph used in the Opus, Helsinki and Maestro subsets of the commercial sample, and looking at each in context on the page.
- The companion table covers OpusSpecial and HelsinkiSpecial: braces, bracket ends, the system divider, tremolo strokes, the arpeggio segment, ledger lines, let-ring ties, the rhythm dot, ottava pieces and grace-note slashes.
- Where the programs differ, the difference is in use, not shape. Finale also uses the rhythm dot for staccato, and Opus and Helsinki draw the wedge staccatissimo on other bytes. The table names the shape, and later stages read the use from position.
- Bytes not in the table are counted as unmapped, not guessed.

## Shapes

- A glyph is drawn in grey, cropped to its ink, centred in a square and reduced to 24 by 24 pixels. Two shapes are compared by correlation after a slight blur, so that thin strokes a pixel apart (an accent, a flag) still overlap. The ink's width, height and position against the origin are kept in staff spaces: a quarter of an em for a font glyph, and the page's measured staff space for an outline.
- Reference shapes are the SMuFL glyphs of Bravura, Leland, Petaluma, Gootville and Leipzig, drawn from the SVG outlines Verovio installs. A shape is compared with the reference of a name in every font that has it, and the best fit counts. A fit also needs the size to agree within 45 percent in width and in height.

### Renamed fonts

- Each glyph the font uses is drawn and compared with the reference for the symbol each table gives its byte. A glyph fits at a similarity of at least 0.6.
- The table with the largest share of glyph uses that fit is chosen if the share is at least one half. Otherwise the font is not identified and its glyphs are counted as unmapped.
- Opus, Helsinki and Maestro share one layout, so "which font" comes down to "which table". The program is guessed as Sibelius if a Sibelius font or a companion font is on the page, and as Finale otherwise.
- Measured on the 9 renamed fonts of the commercial sample: all identified. Main fonts fit at 0.6 to 1.0 of glyph uses, companion fonts at 1.0, and 13 glyphs in all were left unmapped.

### Outlined symbols (Type B)

Pages are matched by shape where the music is drawn as outlines, which is where outlined shapes repeated more than music-font glyphs (the inspector's Type B rule), or where there are staves with almost no music glyphs. On other pages only braces are looked for among the outlines, because MuseScore 3 draws its braces that way.

- Filled shapes with curves, up to 8 staff spaces in each direction, are matched against about 100 candidate symbols (noteheads, rests, accidentals, clefs, flags, dots, time and tuplet digits, dynamics, articulations, fermatas, ornaments, braces, brackets, pedal marks, bowings, wiggles). The best fit is taken at a similarity of at least 0.75. Identical shapes (the same fingerprint) are matched once.
- Shapes that are not symbols are left out:
  - Four-sided pieces with no curves are stems, barlines and beams.
  - A crescent of two or three curves is a tie or short slur.
  - A long band, at least 2.4 times as wide as tall with little ink for its size, is a slur. A fermata is about twice as wide as tall and is kept.
- Some symbols get their own tests:
  - A small level rectangle on a staff line is a whole or half rest drawn without curves. A whole rest hangs below a line and a half rest sits on one, whichever edge is nearer a line.
  - A tall, narrow shape is a brace at any height.
  - An upright wiggle is an arpeggio: SMuFL draws it level, so the shape is also compared turned a quarter turn.
- Where two SMuFL glyphs have the same shape, only one name is used: an accent above or below, and every dot (rhythm, staccato, repeat). Later stages tell them apart by position. A staccatissimo wedge is named as the plain staccatissimo it means.
- The origin of a named outline sits in its ink box where the origin sits in the reference's.
- Text drawn as outlines is not read yet. Its letters are mostly left unmatched.

## Results

### Outlined symbols

Checked by `scripts/check_outlines.py`:

- On the 43 Verovio PDFs of the regression set, against Verovio's own list of the glyphs it drew: 99.3 percent of glyphs found and 98.6 percent of named symbols right. The same without Leipzig among the references, the font Verovio draws in, so that the matcher meets shapes it has not seen (`--fonts Bravura,Leland,Petaluma,Gootville`).
- On 11 commercial Type A files in Opus, Helsinki, Maestro and renamed fonts (5 pages each), turned into outlines and checked against their font glyphs (`--type-a`): 98.5 percent of glyphs found and 98.7 percent of named symbols right.
- Weak spots: arpeggio segments (named, but placed roughly), bracket ends in the Sonata style, tenuto lines (plain rectangles, left out), and text drawn as outlines.

### Corpus survey

`scripts/run_survey.py symbols`, then `symbols-report`, writes `survey/symbols-counts.txt` on the corpus drive. It covers all 3,410 survey and regression files: OpenScore, Mutopia, the PDMX sample, the IMSLP commercial sample and the regression set.

- 9.24 million symbols named.
- 26 font glyphs unmapped. 22 are Leland's own optional glyph U+F631, which has no standard name. The other 4 were two Bravura glyphs whose names have since been added to the supplement.
- 2,459 outlined shapes not matched, 1,884 of them in one Type B commercial file. They are bracket ends, outlined text, and slurs of unusual shape.
- 51 files (1.5 percent) have any unmapped glyph or shape. Every Mutopia file is fully mapped.

## Known limits

- The Sonata table covers the bytes seen in the sample and the common Maestro glyphs. Rarer glyphs of fonts not in the sample (Petrucci, Engraver, Jazz, Broadway Copyist) are counted as unmapped until a file uses them.
- A Type 3 font has not been seen and is not handled.
- Outlined text (titles, lyrics on a Type B page) is not read as text.
