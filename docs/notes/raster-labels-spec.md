# Training labels for the raster engines (Phase 2, Stage 2.1)

How the training data for the symbol detector (Engine 1) and the sequence reader (Engine 2) is made from vector PDFs: which scores, which detector classes, how each box is made, how pages are rendered and cut, how staves get their tokens, and how the labels are checked without looking at them. The plan is `docs/plans/phase2.md`, Stage 2.1.

## Principles

- **The vector reader is the labeller.** Every label comes from what `symbols.py` (glyphs and their ink boxes), `evidence.py` (staves) and the ground-truth MusicXML say about a PDF. Nothing is labelled by hand.
- **A class is what a symbol looks like, not how it was drawn.** The same mark must get the same label whether the engraver drew it as one glyph, several glyphs, a text character or a filled path. Where engravers differ, the rules below merge or split to the form most of them use.
- **Two SMuFL names share a class when they look alike and the reader can tell them apart from where they stand.** Above and below versions of an articulation, up and down flags, and the left and right brackets of a parenthesis pair are examples. Stage 2.4 gives each detection its exact SMuFL name from its position.
- **Lines are not detector classes.** Staff lines, ledger lines, stems, barlines, beams, tremolo strokes, slurs, ties, hairpins, the upright part of brackets, tuplet brackets, ending and octave lines, pedal lines, straight glissando lines and grace-note slashes are drawings in the vector reader. Stage 2.2 finds them in the image. The detector sees them as background.
- **A truth file for every page.** The generator writes a truth file for each rendered page with its scale, its variations, its staves and every box with its class and the names it came from, so a page can be rendered again exactly and its labels read without the vector reader.
- **Code:** `src/omr/corpus/raster_labels.py` (classes, joins, boxes, rendering, tiles, checks), `src/omr/corpus/sequence_units.py` (homr units), and the driver `scripts/make_training_data.py`. The scores are drawn and exported by `scripts/build_corpus.py training-draw` and `training-export`.

## Source scores

- **Training pool only.** Scores come from `work/training-pool.txt`, which already excludes the development, regression and check sets and their near copies (`corpus-sampling.md`, "Keeping the training pool clean").
- **Filters.** The same filters as the selected sets (size, specialised notation, round trip), applied in that order so the slow round trip runs only on scores that pass the cheap checks.
- **Draw.** 1,000 scores, round robin over the genre and texture groups as in the development set's draw, with the same seed, so every texture and genre is present. The number is a setting, so more can be drawn later without changing the ones already drawn.
- **Exports.** The same 6 jobs as the selected sets (MuseScore 4 base and variant with the font and staff-size rotation, MuseScore 3 base and variant, LilyPond, Verovio), through the existing export code with its inspector check, free-space check and resume. Output goes to `generated/training` on the corpus drive.
- **Known overlap with homr's own training data.** homr was trained on all OpenScore Lieder and on 500 PDMX files drawn with a fixed seed. The selected sets hold 23 Lieder (16 development, 4 regression, 3 check) and 1 development PDMX file from that draw. Engine 2 figures (Stages 2.6 and 2.7) are reported with and without these 24 scores.

## Detector classes

Each class lists the SMuFL names it takes. A name not listed belongs to no class: its ink is left unlabelled, and the label check counts it (see "Checking the labels").

### Noteheads

- `noteheadBlack`: noteheadBlack, and the notehead part of metNote...Up glyphs in metronome marks (other engravers draw those notes with ordinary noteheads). The notehead part is the foot of the glyph, one staff space high and at most 1.2 wide; the stem above it is left out, like other stems.
- `noteheadHalf`: noteheadHalf.
- `noteheadWhole`: noteheadWhole.
- `noteheadDoubleWhole`: noteheadDoubleWhole, noteheadDoubleWholeSquare.
- `noteheadX`: noteheadXBlack, noteheadXHalf, noteheadXWhole, noteheadCircleX.
- `noteheadSlash`: noteheadSlashHorizontalEnds.
- `noteheadSlashWhite`: noteheadSlashWhiteHalf, noteheadSlashWhiteWhole.
- `noteheadOther`: every other notehead... and noteShape... name (diamonds, triangles, squares).

Grace and cue noteheads are in the same classes as full-size ones. Stage 2.4 tells them apart by box height against the staff space, as the vector reader does by font size.

### Rests

- `restDoubleWhole`, `restWhole`, `restHalf`, `restQuarter`, `rest8th`, `rest16th`, `rest32nd`, and `rest64th` (64th and shorter).
- restWholeLegerLine and restHalfLegerLine go to `restWhole` and `restHalf`. Their box is 1.3 staff spaces wide (a plain rest's width), centred on the glyph, so the short line beside it is left to the line finder, as it is where Verovio draws it as a line.
- restLonga and other rests belong to no class.

### Flags and dots

- `flag8th`, `flag16th`, `flag32nd`, and `flag64th` (64th and shorter). Up and down share a class.
- `augmentationDot`: augmentationDot, repeatDot and metAugmentationDot. They look the same; the reader already places repeat dots by the barline beside them.
- `staccato`: articStaccatoAbove and articStaccatoBelow.

### Accidentals and parentheses

- `accidentalSharp`, `accidentalFlat`, `accidentalNatural`, `accidentalDoubleSharp`, `accidentalDoubleFlat`. Key-signature accidentals are in the same classes; the reader tells them apart by position.
- `parenLeft` and `parenRight`: accidentalParens..., accidentalBracket..., noteheadParenthesis... and keyboardPedalParens..., by side.

### Clefs

- `gClef`, `gClef8vb`, `gClef8va`, `fClef`, `fClef8vb`, `cClef`, `percussionClef` (unpitchedPercussionClef1).
- Small clefs (clef changes) are in the same classes.
- LilyPond draws an octave clef as a clef with a separate small 8 (or 15) below or above it. The two are joined into one box of the octave clef's class, as the reader joins them.
- Clefs with 15 belong to no class until the generated data holds enough of them to train.

### Time signatures

- `timeSig0` to `timeSig9`, `timeSigCommon`, `timeSigCutCommon`.

### Tuplet numbers

- `tuplet0` to `tuplet9`, one box for each digit.
- Verovio draws them as tuplet glyphs. MuseScore and LilyPond write them as italic digits in the text layer, which the reader takes as tuplet numbers (`notation-spec.md`, "Duration"). Each such digit gets its own box from the character's ink, not from the text run.
- A colon in "3:2" belongs to no class.

### Dynamics

One class per dynamic as it is read, not per letter: `dynamicP`, `dynamicPP`, `dynamicPPP`, `dynamicPPPP` (four or more), `dynamicMP`, `dynamicMF`, `dynamicF`, `dynamicFF`, `dynamicFFF`, `dynamicFFFF` (four or more), `dynamicSF`, `dynamicSFZ`, `dynamicSFP`, `dynamicSFFZ`, `dynamicFZ`, `dynamicFP`, `dynamicRF`, `dynamicRFZ`, and `dynamicOther` for the rest.

- MuseScore 4 draws "mf" as one glyph; MuseScore 3 and LilyPond draw an "m" glyph and an "f" glyph side by side. The letters are joined with the reader's own rule (`markings.dynamic_groups`), and the joined box takes the class of the dynamic it spells.
- The value comes from `markings.DYNAMIC_GLYPHS` (sforzando1 is "sf", sforzato is "sfz", and so on).

### Articulations, ornaments and other marks

- `staccatissimo`: articStaccatissimo... and articStaccatissimoWedge..., above and below.
- `accent`, `marcato`, `tenuto`, `fermata` (all fermata shapes, above and below), each taking its above and below names.
- `breathMark` (breathMarkComma), `caesura` (caesura...).
- `ornamentTrill`, `ornamentMordent`, `ornamentShortTrill`, `ornamentTurn`, `ornamentTurnInverted`; other ornament... names go to `ornamentOther`.
- `arpeggio`: a column of wiggleArpeggiato... glyphs (with or without the arrow) is joined into one box, as the reader joins them. The joins between glyphs fall at different places in each engraver, so single glyphs would make inconsistent boxes. The glyphs are drawn turned, so the font's boxes are not where the ink is: the box is taken from the column's left edge and shrunk to the ink found in the rendered page.
- `trillLine`: a row of wiggleTrill glyphs, joined the same way. `wavyGlissando`: a run of wiggleGlissando glyphs, joined.
- `upBow`, `downBow` (strings...).
- `pedalPed`: keyboardPedalPed, and LilyPond's separate P, e, d and dot glyphs joined into one box. `pedalUp`: keyboardPedalUp.
- `segno`, `coda`.
- `octave8` and `octave15`: the ottava or quindicesima glyph with its suffix glyphs (alta, bassa, va, vb), or the same mark written as text, joined into one box.
- `brace`, and `bracketEnd` (bracketTop and bracketBottom, which are mirror images).

### Text

- `text`: one box for each text run from `symbols.py` (titles, tempo, expression, lyrics, chord symbols, fingering, rehearsal marks, instrument names), shrunk to the ink found in the rendered page. Chord-symbol glyphs (csym...) join the text run they touch.
- **Text drawn as outlines.** Verovio prints "MEI engraved with Verovio" at the foot of every page as filled shapes, and the vector reader matches some of its letters to music symbols. A row of shapes clear of the staves that holds a shape the reader could not name is text, together with any letters on that row that the reader did match. Its box is widened along the line while ink goes on within a staff space, to take in the logo, which the reader skips.
- Stage 2.5 reads these boxes with OCR. The text kinds are decided there by `text.py`'s rules, so the detector needs no class per kind.

## How a box is made

- **Glyph boxes** are the ink box `symbols.py` gives each symbol, in points, scaled to the page's pixels. Joined symbols take the union of their boxes. Measured against the rendered ink, these boxes are within two pixels of it at 24 pixels a staff space.
- **Shrunk to the ink:** text runs, tuplet digits (from the character's box in the text layer), octave marks written as text, arpeggios and LilyPond's joined octave clefs, whose boxes from the text layer or the font are not tight.
- **Minimum size.** Each side of a box is at least half a staff space, grown evenly about its centre. A dot is then about 5 pixels at the smallest scale, rather than 4.
- **Padding.** One pixel on every side, for anti-aliasing.
- **Duplicates.** Two boxes of one class covering the same ink (intersection over union above 0.8) are one box. This happens where an engraver draws a unison notehead twice.

## Detector data

- **Scales.** Each page is rendered at a staff space drawn at random from 10 to 24 pixels (about 150 to 300 dpi on a typical score), taken from the page's own staff space in points. Each page is rendered at one scale, so the scales spread across scores. Greyscale, 8 bits.
- **Variations** (all keep the labels exact): slight Gaussian blur, JPEG compression at quality 50 to 95, faint noise, and a share of pages turned black and white at a threshold. Each is drawn at random for each page, and the choice is written in the truth file. No camera distortions; those are Phase 4.
- **Tiles.** 640 pixel squares, with an overlap of 160 pixels between neighbours. A box is kept in a tile if at least half of it lies inside, clipped to the tile. Tiles with no box are mostly dropped (one in ten is kept as background).
- **Amount.** 2 percent of pages are cut into tiles, drawn at random across scores and jobs, so every score and engraver contributes: about 10,000 tiles from the 1,000 training scores. Validation takes 10 percent of the scores, so no score is in both. The share is a setting.
- **Format.** YOLO: an image folder and a label folder, a `data.yaml` with the class list in the order above, and a class list file the label checks and Stage 2.4 also read.

## Sequence-reader data

- **The unit is homr's:** one part in one system, which is one staff, or both staves of a grand staff (homr's "upper" and "lower" positions). Parts of three staves or more are left out. The crop is the unit's staves with homr's own inference margins: 2 staff spaces left and right, 4 above the top staff and below the bottom one. It is saved no larger than 256 by 1280 pixels, the size homr shrinks every staff to.
- **Tokens come from the ground truth**, through homr's own MusicXML parser (`training/omr_datasets/music_xml_parser.py`, AGPL-3.0), so they use its vocabulary exactly. They are not taken from the vector reader's output, which would teach its errors.
- **The bars of each unit** come from the vector reader's systems, which must add up to the ground truth's bars; for MuseScore 4 pairs they must also start where the system breaks in the pair's own MusicXML start. A unit is kept only if, in each of its bars, the noteheads found on its staves equal the notes the ground truth prints there. Counting noteheads does not depend on reading the rhythm, so the check does not favour easy staves. Systems with a multi-bar rest are left out. homr's own splitter (`MeasureCutter`) gives each unit its tokens, with the clef, key and time signature that start the line.
- **Octave clefs and octave lines.** homr's vocabulary has neither. In a trial on the 300 MuseScore 4 development pairs, its parser refused 68 files for an octave clef and 12 for an octave line. Such staves are tokenised as they look: a treble clef with an 8 below becomes a plain treble clef, and every note keeps its written position, so its pitch is an octave higher than it sounds. Stage 2.6 restores the octave from the clef or line that Engine 1 and the line finder read.
- **Length.** In the same trial, units needed a median of 22 tokens, 113 at the 95th percentile and 382 at most; 3.5 percent were over 128 and 0.1 percent over 256. Units up to 128 tokens train at batch 4 with the encoder frozen. Longer units are kept in a separate list, to train at batch 2.
- **Scale and variations.** Staff space drawn from 10 to 24 pixels, with the same variations as the detector data.
- **Amount.** About 100,000 units. 1,000 scores in 6 jobs give about 150,000 before the checks.
- **Format.** homr's: an image file and a token file for each unit, and index files with an "image,tokens" line for each (`index-train.txt` and `index-val.txt`, and `index-train-long.txt` and `index-val-long.txt` for units over 128 tokens), so homr's data loader reads them unchanged.

## Checking the labels

The owner cannot look at boxes drawn on a page, so every check is a number, written to a plain-text report for each job (engraver and font) with the worst pages named.

- **Inside the image.** Every box lies inside its page with a positive width and height. Any failure is a fault.
- **No double labels.** No two boxes of one class cover the same ink after the duplicate rule. Any left is a fault.
- **Boxes fit the ink.** With the staff lines removed from the rendered page, the ink found around each box's ink box (before the minimum size and padding) must reach within 2 pixels plus a tenth of a staff space of each of its edges, and the box must hold some ink. The tenth allows for `symbols.py` measuring a glyph's ink from a drawing at 12 pixels a staff space. Here ink is any pixel darker than 200 of 255, because thin strokes (Verovio's sharps) render pale grey at small scales. Reported as the share of boxes that fit, by class and job, with those within 0.3 staff spaces counted apart. A class under 98 percent in any job is investigated before training.
- **No unlabelled symbols.** On a page whose symbols are font glyphs (MuseScore, LilyPond), the page is rendered again with its drawings removed, which leaves the ink of every glyph and no lines. Visible glyph ink outside every box is split into connected pieces. The ink the rule leaves out on purpose (glyphs with no class, which are listed by name, and the stems of metronome-mark notes) and slivers two pixels thin at a box's edge are not counted. The pieces are counted by job with their page, position and size, and the share of glyph ink they make up is reported. Any job over 0.5 percent is investigated before training, because unlabelled symbols teach the detector to miss them. On a page drawn in outlines (Verovio), the shapes the vector reader could not name are counted instead.
- **Tokens agree.** For each sequence unit, the number of notes in its tokens equals the noteheads counted in its bars, and the unit's token file parses with homr's tokenizer.
- **A sample of every job.** The checks run on every page that is generated. Stage 2.1 is done when they pass on a sample of every job.

## What is written

Under `generated/training` on the corpus drive:

- The exported pairs, as for the selected sets.
- `pages/`: one truth file (JSON) for each rendered page, with the scale, the variations, the staves, and every symbol and text run with its name, class and box in pixels.
- `detector/`: the YOLO dataset.
- `sequence/`: the homr dataset.
- `label-check.txt`: the report of the checks above.
