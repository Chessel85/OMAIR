# PDF inspector specification (`omr inspect`)

Version 0.2, 5 October 2026 (implemented; see the changes in the Stage 4 notes of `docs/plans/phase0-progress.md`). This is the Stage 4 design in `docs/plans/phase0.md`. It says what the inspector measures on each page, how it decides the page type, and what it reports. Phase 1 builds on the same evidence, so the extraction code should live in a module that Phase 1 can import (`omr.pdf.evidence`), with the classifier (`omr.pdf.classify`) and the report writer (`omr.inspect`) kept separate.

## Purpose

- Tell each page's type, so that `omr convert` can later route it to the right path.
- Measure the mix of PDF types and fonts in real files (Stage 8 and the Phase 0 gate).
- Confirm what an engraver really produced. MuseScore falls back to Bravura without an error when a requested font is missing, so the corpus generator (Stage 5) checks every export with the inspector's JSON output.

## Page types

These are the four types in section 4.1 of the solution design, plus one outcome for pages without music.

- **Type A: vector music with font glyphs.** The music symbols are characters in a font, and the page has staff lines drawn as vector lines or thin shapes.
- **Type B: vector music with outlined glyphs.** The music symbols are filled vector shapes (outlines), not characters. The same shape is repeated many times, once for every notehead of the same kind.
- **Type C: clean raster music.** The music is in an embedded image (or the input is an image file), and the image looks like a clean digital rendering: white background, level staff lines, no page edges or shadows.
- **Type D: photo or scan.** The music is in an image that shows signs of a physical page: tilted or curved staff lines, uneven background, dark borders or shadows.
- **No music (N).** No staves, no music glyphs and no large image. Title pages, text pages, blank pages. N is reported but is not a routing type.

If a page mixes kinds of content, its music decides the type (solution design, section 4.1). A vector title above a scanned page of music is Type C or D. A vector page with a paper-texture background image is Type A or B.

## Evidence gathered for each page

All of this comes from PyMuPDF without rendering the page, except the raster measures for C and D. The inspector must not use OCR.

### Text glyphs

- Source: `page.get_texttrace()`. It gives every character with its font, Unicode value, glyph ID, bounding box and render type.
- Ignore spans whose render type is 3 (invisible) or whose opacity is 0. These are usually an OCR text layer over a scan. Count them separately and report "hidden text layer, probably OCR".
- Strip the subset prefix from font names (six capital letters and a plus sign, as in `UTYSZR+Emmentaler-20`).
- For each font, record the font type from `page.get_fonts(full=True)` (Type0, Type1, TrueType, Type3), the number of glyphs drawn, the number in the Private Use Area (U+E000 to U+F8FF), the number with no usable Unicode value (U+FFFD or control codes), and the number of distinct glyph IDs.

### Music font identification

Each font is put into exactly one class. Apply the tests in this order.

1. **SMuFL music font.** At least 5 glyphs, at least 80 percent of them in the Private Use Area (U+E000 to U+F8FF) and at least 10 percent, or at least 10 glyphs, in the SMuFL standard range (U+E000 to U+F3FF). The wider range is needed because Bravura and Petaluma, as written by MuseScore 4, draw most noteheads from U+F4BE, which is outside the standard range. The standard-range share can be low: on a percussion-heavy page of a 35-page score in Petaluma, only 15 percent of the glyphs (19 of 118) were in it, because nearly all were U+F4BE noteheads. A real SMuFL page always has some standard-range glyphs, such as clefs, rests and accidentals. This is decided by code points, not by name: MuseScore 3 and 4 write Emmentaler as a font called "MScore", and Gonville as "Gootville", both with SMuFL code points. Fonts whose name ends in "Text" (BravuraText, LelandText, MuseJazzText) are SMuFL text fonts, used for metronome marks and similar. Report them as "SMuFL text font" and count their glyphs separately from the main music font.
2. **Known legacy music font.** The name matches the legacy list below. These need a mapping table in Phase 1. Report the font as "legacy, mapping table needed".
3. **Unknown, probably music.** Not in either class above, but at least 10 of its glyphs have their centre inside a staff (see staves below), and fewer than half of its glyphs are letters, digits or punctuation. Report it as "unknown font, probably music" and list it, so that Stage 8 can grow the legacy list.
4. **Text font.** Everything else.

Legacy list (match on the name after the subset prefix, ignoring case, spaces and hyphens, as a prefix that ends at a word boundary: the next character must not be a lower-case letter, so "Engravers MT" and "AshleyScript" do not match; a name containing "text" or "times" is never legacy, because Opus Text, Reprise Text, Engraver Text and Maestro Times are the text companions of these fonts): Emmentaler, Feta, Opus, Helsinki, Reprise, Inkpen2, Norfolk, Maestro, Petrucci, Jazz, Engraver, Broadway Copyist, Sonata, Tamburo, Seville, Toccata, Pori, Ash. Stage 8 will extend it. A font whose name is on the list but which passes test 1 is SMuFL (for example the SMuFL Finale Maestro that MuseScore 4 writes as "FinaleMaestro").

Glyphs with no usable Unicode value still count. LilyPond's Emmentaler arrives with every character as U+FFFD, so for legacy fonts the glyph ID is the key. Phase 1 will need the glyph names from the embedded font program, which PyMuPDF does not expose; that is a Phase 1 question, not an inspector one.

Type 3 fonts are fonts whose glyphs are small drawing procedures. They are treated as fonts like any other. If such a font is classed "unknown, probably music", the report says so, because Phase 1 would need to fingerprint its glyph procedures.

### Vector lines and shapes

- Source: `page.get_drawings()`.
- Count stroked line segments in three groups: horizontal (vertical change under 0.2 points), vertical (horizontal change under 0.2 points) and other.
- Count filled shapes (drawn with fill, or with fill and stroke) in three groups: rectangles, straight-sided polygons and curved shapes (any shape with a Bézier segment).
- Engravers differ in how they draw the same thing. In the probe files, MuseScore draws staff lines as stroked lines, LilyPond as stroked lines with some filled rectangles, and Verovio (through the SVG route in Stage 5) as filled rectangles. The rules below must therefore never depend on stroke against fill.

### Staves

A staff is the strongest single sign of music on a vector page.

1. Collect horizontal line candidates: stroked horizontal segments, and filled rectangles or polygons that are at least 30 times as wide as they are tall. Each candidate has a y position (centre), a left x, a right x and a thickness.
2. Merge candidates that share a y position (within 0.3 points) and touch or overlap along x. Engravers often draw one staff line in pieces.
3. Group candidates whose x ranges overlap by at least 80 percent of the longer one. (Using the shorter one let short ledger lines join a staff and turn a five-line run into a six-line run.) Within each group, sort by y and find runs of 5 lines with equal gaps (each gap within 10 percent of their median). Each run is a five-line staff.
4. Also record one-line runs that carry glyphs (percussion) and six-line runs (tablature), reported separately. They do not change the type.
5. The staff space is the median gap inside the five-line staves. Report it in points and in millimetres. In the probe files it was about 5.0 points (1.75 mm) for MuseScore 3 and 4 and LilyPond, and 7.2 points for Verovio at scale 40.

A line thickness above a third of the staff space rules a candidate out (it is a beam or a box, not a staff line).

### Outlined shapes

1. Take filled shapes that contain at least one curve and whose bounding box is no larger than 4 staff spaces in either direction and no more than 4 times as wide as it is tall. This keeps noteheads, accidentals, rests and clefs, and leaves out ties, slurs and beams. If no staff was found, use 5 points as the staff space.
2. Fingerprint each shape: move it so that the top left of its bounding box is at zero, divide every coordinate by the staff space, round to 0.05, and hash the sequence of segment types and points.
3. Count the shapes, the distinct fingerprints, and the number of instances of the five most common fingerprints.

In the Verovio probe of a Bach chorale, 201 curved shapes had 21 distinct fingerprints, and one fingerprint (the black notehead) appeared 157 times. The MuseScore and LilyPond exports each had 2 curved filled shapes, which were ties or slurs, and the size test leaves them out.

### Images

- Source: `page.get_image_info(xrefs=True)` for where each image is drawn, plus `page.get_images(full=True)` for the stream details.
- For each image record its pixel size, its drawn size on the page, the effective resolution in dots per inch, bits per component, colour space and compression filter (for example DCTDecode, which is JPEG, or CCITTFaxDecode and JBIG2Decode, which are typical of bilevel scans).
- Compute image coverage: the area of the union of all drawn image rectangles, as a share of the page area. Scanners sometimes split a page into strips, which is why the union is used.
- Images covering less than 10 percent of the page each (logos, small pictures) are listed but do not count towards coverage.

### Document facts

- Page count, page size and rotation.
- The producer and creator from the PDF metadata. These usually name the engraver (for example "MuseScore Studio Version: 4.7.5" or "LilyPond 2.26.0"). Report them as "Made by", and treat them as a hint only. They are never used to decide the type, because they are easily missing or wrong.

## Decision rules

Apply these in order. The first rule that matches decides the type. Every decision carries a one-sentence reason in plain words that names the numbers behind it, and a confidence of high, medium or low.

Definitions used below:

- "music glyphs" is the number of visible glyphs in fonts classed SMuFL music, legacy or unknown-probably-music (text fonts and SMuFL text fonts excluded);
- "repeated shapes" is the number of outlined-shape instances whose fingerprint occurs at least 5 times on the page;
- "staves" is the number of five-line staves found from vector evidence.

The rules:

1. **Raster.** Image coverage is at least 50 percent, and music glyphs are under 10, and repeated shapes are under 10. The type is C or D (see the next section).
2. **Type A.** Music glyphs are at least 10, and at least as many as repeated shapes. Confidence is high if staves are 1 or more, otherwise medium. A sparse page is also Type A, with medium confidence, if staves are 1 or more and music glyphs are 3 or more (added after the first corpus run: the last page of a score often has only a few notes).
3. **Type B.** Repeated shapes are at least 10, and more than music glyphs. Confidence is high if staves are 1 or more, otherwise medium. As for Type A, 3 or more repeated shapes are enough, with medium confidence, when staves are found.
4. **Vector, symbols not found.** Staves are 1 or more, but neither music glyphs nor repeated shapes reach 3. This is reported as Type B with low confidence and the reason "staves found but no music symbols identified". It catches outlines that are not repeated (for example every notehead drawn at a slightly different scale) and must be looked at by hand in Stage 8.
5. **Raster, partial.** Image coverage is between 10 and 50 percent and none of the above matched. The type is C or D with low confidence, reason "music may be in a smaller image".
6. **No music.** Anything else.

Mixed pages. If a page is A or B and the other kind of evidence is also present (music glyphs and repeated shapes both 10 or more), add the note "mixed: both font glyphs and outlined shapes". If a page is A or B and image coverage is 50 percent or more, add the note "large image also present, possibly a background".

## Telling C from D

This split is provisional in Phase 0. It only has to be good enough for the Stage 8 survey, and it will be revised in Phase 2 (raster path) and Phase 4 (photos). It is the one part of the inspector that renders anything.

Render the page at 100 dpi in greyscale (for an image file, scale the image to the same size). Measure:

1. **Background.** Split the page into a 4 by 4 grid. In each cell take the 90th percentile of brightness (the paper colour). The page is uneven if the largest and smallest cell values differ by more than 40 out of 255.
2. **Dark border.** The page has a dark border if more than 30 percent of the pixels in the outer 3 percent of the page, on any side, are darker than 100 out of 255.
3. **Tilt.** Find the staff lines in the image with a horizontal projection over a band in the middle of the page, trying angles from minus 3 to plus 3 degrees in steps of 0.1 degree. The page is tilted if the best angle is more than 0.3 degrees from level.
4. **Bilevel scan.** All large images are 1 bit per pixel, or use CCITT or JBIG2 compression.

The decision:

- Type D if the page is uneven, has a dark border, or is tilted. The reason names which.
- Otherwise Type C. If it is a bilevel scan, add the note "clean bilevel scan of a printed page" and set the confidence to medium, because such pages came from paper and may still need deskewing.
- C and D decisions are never given high confidence in Phase 0.

The thresholds are starting values. Stage 8 calibrates them on real IMSLP scans and on known Type C pages (a MuseScore PDF rasterised at 300 dpi and wrapped in a PDF, which the tests can build). If the thresholds change, change them here as well as in the code.

## Input files

- PDF files are inspected page by page.
- PNG, JPEG and TIFF files are one page each, always Type C or D (multi-page TIFF gives one page per frame).
- Several files may be given in one command. Folders are not searched; Stage 8 passes the file list.
- An encrypted or damaged file is reported as a failure with its reason, and the command carries on with the next file.

## Command line

- `omr inspect FILE [FILE ...]` writes the plain-text report to the screen.
- `--json PATH` also writes the full results as JSON to PATH.
- `--pages 1-3,7` limits the pages, numbered from 1.
- `--brief` gives only the summary of each file, which suits a quick check of many files.
- Exit status follows `docs/conventions.md`: 0 if every file was read, 1 if any failed, 2 for wrong usage. The last line is the "Summary:" line.

## Plain-text report

The report follows `docs/conventions.md`: headings and lists, no tables, numbers in words where it helps, one fact per line. The summary comes first. Pages with the same type and the same fonts may be grouped ("Pages 2 to 9: same as page 1") so that a long score does not repeat itself.

An example, for a MuseScore 4 export:

    File: bach_ms4.pdf
    Summary: 1 page. Type A on 1 page. Music font: Leland (SMuFL). Made by MuseScore Studio Version 4.7.5.

    Page 1
    Type A, high confidence: 239 music glyphs in Leland and 12 staves found from vector lines.
    Staves: 12 five-line staves. Staff space 5.0 points, 1.75 millimetres.
    Fonts:
    - Leland: SMuFL music font, 239 glyphs.
    - Edwin-Roman: text font, 54 glyphs.
    - Edwin-Italic: text font, 2 glyphs.
    Vector lines: 461 stroked, of which 237 horizontal and 224 vertical.
    Filled shapes: 32, of which 2 curved (ties or slurs).
    Outlined shapes: none.
    Images: none.

    Summary: 1 file inspected, 0 failed, 0 warnings.

A warning is raised, and counted in the summary line, for: an "unknown, probably music" font; a Type B page with low confidence; a mixed page; a page with a hidden text layer.

## JSON output

One object per file, in a list. Field names are fixed, because Stage 5 and Stage 8 depend on them. Add fields freely; do not rename or remove them without updating those stages.

- `file`, `pages` (count), `producer`, `creator`, `error` (null, or the reason the file could not be read).
- `summary`: `types` (a count per type letter), `music_fonts` (a list of names with classes and glyph counts, over the whole file).
- `page_results`: a list with, for each page:
  - `page` (from 1), `width_pt`, `height_pt`, `rotation`;
  - `type` (one of "A", "B", "C", "D", "N"), `confidence` ("high", "medium" or "low"), `reason` (the sentence), `notes` (a list of strings);
  - `fonts`: a list with `name`, `font_type`, `class` ("smufl", "smufl_text", "legacy", "unknown_music" or "text"), `glyphs`, `pua_glyphs`, `unmapped_glyphs`, `distinct_glyph_ids`;
  - `hidden_text_glyphs`;
  - `lines`: `horizontal`, `vertical`, `other`;
  - `filled`: `rectangles`, `polygons`, `curved`;
  - `staves`: `five_line`, `one_line`, `six_line`, `staff_space_pt`;
  - `outlined_shapes`: `count`, `distinct`, `top_repeats` (a list of up to five counts), `repeated_instances`;
  - `images`: a list with `width_px`, `height_px`, `drawn_width_pt`, `drawn_height_pt`, `dpi`, `bits`, `colour_space`, `filter`; and `image_coverage` (0 to 1);
  - `raster_measures` (C and D only): `background_range`, `dark_border`, `tilt_degrees`, `bilevel`.

## Speed

A vector page must be inspected in well under a second, with no rendering. Raster measures render only pages that rule 1 or rule 5 sends to C or D. Stage 8 runs the inspector over hundreds of files, so it must not be slow.

## Tests

Test files must be public domain and small. The Bach chorale "Christus, der ist mein Leben" (BWV 66.6, from the music21 corpus, BSD and public domain) exported through each engraver is about 35 to 50 kilobytes per PDF, so a set can live in `tests/data/inspect/`.

Expected results, which the tests check:

- MuseScore 4, default: Type A, high; Leland, SMuFL.
- MuseScore 4 with Bravura, Petaluma, Gonville (reported as Gootville), MuseJazz, Finale Maestro and Finale Broadway: Type A, high; the named font, SMuFL. The Finale Broadway export also uses a few Bravura glyphs, which is expected.
- MuseScore 3, default: Type A, high; MScore (Emmentaler), SMuFL.
- LilyPond: Type A, high; Emmentaler-20, legacy, glyphs without Unicode values.
- Verovio, through the Stage 5 SVG-to-PDF route: Type B, high; many repeated shapes; text in Times.
- A MuseScore page rasterised at 300 dpi and wrapped in a PDF (built in the test): Type C.
- The same image rotated by 2 degrees on a grey background (built in the test): Type D.
- A text-only page (built in the test): No music.
- A raster page with a hidden text layer added (built in the test): Type C, with the hidden-text note.

Done when (from the plan): every file in the generated corpus is classified as its engraver implies, and the owner has read a report with NVDA and found it clear.

## Open points for later stages

- Stage 8 extends the legacy font list and calibrates the C and D thresholds.
- First task of Stage 8: replace the letter test in "Unknown, probably music" (test 3 under "Music font identification") with a position test. Legacy 8-bit music fonts put their symbols on letters and punctuation (a treble clef on "&", a notehead on "q"), so the letter test classes them as text. The new test: at least 10 glyphs, and at least half of the font's glyphs, centred between the top and bottom lines of a staff. See `docs/notes/opus-review-findings.md`, Stage 4, finding 2.
- Phase 1 needs glyph names from embedded fonts (for LilyPond and other legacy fonts), which needs a small font-reading dependency such as fontTools (MIT). Add it to the licence register when it is added.
- Systems (staves joined by a barline or brace) are not detected by the inspector. Phase 1 does that.
