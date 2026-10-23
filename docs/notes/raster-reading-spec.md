# Reading page images with the vector reader (Phase 2, Stage 2.4)

How a clean page image (Type C) is turned into the page the vector reader expects, from the detector's symbols (Stage 2.3) and the line finder's lines (Stage 2.2), so that layout, structure, notation, markings, the rules and the writer run unchanged. The plan is `docs/plans/phase2.md`, Stage 2.4. The detector's classes are in `raster-labels-spec.md`, the lines in `raster-lines-spec.md`.

## Principles

- **The reader stays as it is.** It takes a page's symbols from `symbols.PageSymbols` and its lines from the page's drawings. A raster page gives both: a `PageSymbols` built from the detections, and a `RasterPage` whose drawings are the lines found. Nothing after `symbols.read_document` knows whether a page was vector or raster.
- **Per page, not per file.** A PDF can mix vector and image pages. A page is read as an image when it has no music symbols of its own and its largest image covers at least half of it (the inspector's raster test, `classify.BIG_IMAGE`). PNG, JPEG and TIFF files are opened as one-page image PDFs (`inspect.open_document`), so they take the same route.
- **Type D pages too.** A page the inspector calls Type D (tilt, uneven background) is read the same way; the result is worse, and Phase 4 is where photos are handled. The convert message says so.
- **Code:** `src/omr/raster/names.py` (detections to `Symbol`s: names, anchors, sizes, doubts), `src/omr/raster/reading.py` (the steps on a page, and the detector model), with the page image and `RasterPage` in `src/omr/raster/page.py`.

## The steps on a page

1. **The image, level.** The largest image on the page, in grey, turned level (`lines.level`). Everything below uses the level image, so symbols and lines agree.
2. **Staff space**, in pixels, from the runs of ink (`lines.staff_space`), before any symbol is known. A page with no staff space has no music: it gives an empty `PageSymbols`.
3. **Detection.** The page is scaled to 20 pixels a staff space and read by the detector in tiles (`detect.detect_page`, confidence 0.25), the setting chosen in Stage 2.3. Boxes come back in the level image's pixels.
4. **Symbols** from the detections (below), in page points: the image fills its rectangle on the page (`page.Placement`).
5. **Lines**, found with the symbol boxes, the flag boxes and the text boxes masked (`lines.find_lines`), and given to the reader as drawings (`page.drawings`, `RasterPage`).
6. **Flag directions and clefs** from the lines (below): flags need their stems, clefs the staff lines.
7. **Evidence** (`evidence.gather`) is read from the `RasterPage`, so the staves and staff space in `PageSymbols.evidence` come from the image's lines, as they come from a PDF's.

## Detections to symbols

- **One name a class.** Each detector class is given one SMuFL name the reader knows (`names.NAMES`). The reader cares about the kind, not the font's own variant: `noteheadX` becomes `noteheadXBlack`, `percussionClef` `unpitchedPercussionClef1`, `dynamicP` `dynamicPiano`, `octave8` `ottava` (the reader decides above or below from its position), `pedalPed` `keyboardPedalPed`, `arpeggio` one tall `wiggleArpeggiatoUp`. Dynamics come as one glyph for the whole mark (`dynamicMF`), which `markings.DYNAMIC_GLYPHS` reads as its letters.
- **No symbol** for `text` (its boxes are kept as text regions for Stage 2.5 and masked for the line finder), `dynamicOther` and `ornamentOther` (masked only: the reader would not know what they say).
- **Above or below.** Marks whose SMuFL name says which side of the note they are on (staccato, staccatissimo, accent, marcato, tenuto, fermata) take the side from the nearest notehead in their column (centres within 1.5 staff spaces across): above it is `...Above`, else `...Below`; with no notehead near, `...Above`. A fermata below is drawn turned over, so the side also picks the right reference shape.
- **Flags** need their direction, since a flag's origin is the stem's end, at the top of an up flag and the bottom of a down flag (`notation.attach_flags` measures from it). Every flag starts as `flag...Up`. Once lines are found, its stem is a vertical line within 0.6 staff spaces of its left edge that reaches into its height, and the stem's notes are the noteheads beside it (within 1.5 staff spaces across) along its length. A flag whose middle is below theirs is turned to `flag...Down`. The stem's ends cannot decide it: a stem is about as long as its flag, so both its ends lie near the flag's ends. The direction does not change the flag's count.
- **Bracket ends:** of the two in a column, the upper is `bracketTop`, the lower `bracketBottom`; one alone is `bracketTop`.
- **Origin by SMuFL's anchor** (a notehead's left edge and centre line, a G clef's G line, a flat's line through its bowl, a whole rest's top). The reader takes a symbol's staff step from its origin, so an origin a quarter of a staff space out moves the note a step. The origin is placed in the detection's box where the vector reader finds it in real fonts, measured on training-pool PDFs of every job by `scripts/measure_anchors.py` into `src/omr/raster/anchors.json` (64 names; about 1,000 to 340,000 glyphs each from 715 PDFs).
  - Fonts mostly agree within a few hundredths of the box's height. The exceptions are the handwritten styles: a MuseJazz flat is 3.4 staff spaces tall with its origin 65 percent down its box, against about 2.5 and 72 percent in the other fonts. Placed by Bravura's figure, a MuseJazz key signature of three flats moved a step down and was not read. So the share down the box is a straight line in the box's height, fitted through the median of each font (each with at least 10 glyphs) and kept within their range; the detector's box tells a tall handwritten glyph from an ordinary one without knowing the font.
  - **Clefs are snapped to a staff line.** Fonts differ by up to a quarter of a staff space in where a clef's line lies in its box (the G clef at 58 to 65 percent down), which is half a step: LilyPond's treble clefs came out 0.25 staff spaces above the G line and some were read on the line above. A clef always sits on a line, so once the lines are found its origin moves to the nearest staff line (a level line at least four staff spaces long) within half a staff space.
  - The share across the box is the median (0 for nearly every name: the left edge).
  - A name not in the table (too few glyphs in the draw) is placed as in the Bravura reference glyph's ink box (`shapes.reference`), as outlined symbols are (`symbols.outline_symbols`), and one with no reference at its box's bottom left.
- **Drawn at any length:** arpeggios, trill and glissando lines, braces and bracket ends are anchored at their box's bottom left and given full size.
- **Size.** The reader uses a symbol's size (the font's em) to tell grace and cue notes, clef changes and a clef's octave digits from full-size ones. A detection has no font, so its size is four staff spaces times its box height over a full-size height, with heights at least 90 percent of that taken as full size, so small detector errors do not make a small note. The full-size height is the name's median box height on the page, where the page has at least 5 of them and that median is not itself under 90 percent of the font table's height; else the table's: the full height of that name in the font that draws it smallest (`anchors.json`, "full"; Finale Maestro's noteheads are 1.0 staff spaces tall against 1.2 in most fonts). The page's own height is needed because the detector's boxes are padded (the label rule's minimum size and padding): MuseScore 3's noteheads come out 1.3 staff spaces tall and its grace noteheads 0.94, which against the table's 1.0 were full size. Against Bravura's heights, LilyPond's bass clefs (3.2 staff spaces against 3.7) were read as clef changes.
- **Metronome-mark notes.** The label rule labels the notehead of a metronome mark's note as an ordinary notehead. Once the lines are found, a notehead away from the staff, with a text region starting within 2.5 staff spaces of its right edge at its height, is renamed `metNoteQuarterUp` (`metNoteHalfUp`, `metNoteWhole`), as the vector reader's text stage would take it. Away from the staff is at least 2 staff spaces from every staff line, or outside the staff by at least 0.75 staff spaces with no ledger line (a level line shorter than 4 staff spaces) within 0.6 staff spaces of its middle, which a real note there would stand on: LilyPond sets a tempo mark about a staff space above the staff. Left as a notehead, it counted as the first note of its bar, so the time signature after it was not read (a change to 3/4 at a system's start, under "Presto assai ♩ = ...", and the opening time signature of six regression pairs).
- **Partial beams taken for rests.** The detector can take a partial beam (short and thick) for a half or whole rest. Those two rests' boxes are masked as symbols everywhere except in the search for beams; a real rest has no stem at its end, so the beam rules do not take it. A half or whole rest whose middle lies inside a beam found is then dropped. Verovio's partial beams were read this way, making semiquavers quavers.
- **Time signature digits.** The detector can add a part box over a digit it found (half a 2 inside the 2, one wide box over the two digits of 11, a small box across a 2 and the 4 below it). A time digit that more confident time digits cover by at least half its box is dropped, as a digit too many changes the time (42/4, 2/22).
- **Digit strokes are not barlines.** Where the detector misses one of two 1s stacked in a time signature (11 over 16), the two upright strokes reach the height of the staff and were taken for a barline, splitting the time signature over two bars. A vertical line lying at least 40 percent inside the boxes of time signature digits is dropped.
- **Source** is `"detector"`, and the font name `"detector"`. `notation._small_heads` then uses the size, as for font glyphs.

## Two classes over one symbol

- The detector can find two classes over the same ink (a sharp and a natural, a quarter and an eighth rest), since boxes are merged only within a class. Boxes of different classes overlapping by an IoU of at least 0.5 are one symbol: the more confident is kept.

## Confidences as doubts

- Each `Symbol` from a detection carries its confidence and, where there is one, a doubt (`Symbol.doubt`, the reason in words). A symbol has a doubt when:
  - its confidence is under 0.5, or
  - a box of another class over it (as above) was within 0.15 of its confidence: "a sharp or a natural".
- The thresholds are a starting point, to be set on the raster regression set by the flags' precision and the note errors they catch (ACC-4).
- `notation._read_system` turns the doubts of the symbols it reads into flags in their bar, as it does for its own: rule `"unsure symbol"` for the classes that change notes (noteheads, rests, accidentals, dots, flags, clefs, time signature digits, tuplet numbers), which goes into the flag file; rule `"unsure marking"` for the rest, which the confidence report lists as worth checking.

## Tuplet numbers

- In a PDF, the vector reader takes tuplet numbers from tuplet glyphs and italic digits, and leaves upright digits (fingering, string numbers) alone. The detector cannot tell a fingering 3 from a tuplet 3, and does find guitar fingering as tuplet numbers, some at over 0.8 confidence. So the events a detected number gives a tuplet are marked (`Event.tuplet_detected`), and when their bar does not add up, those tuplets are taken off and left off if the bar then adds up better (`notation.detected_tuplets`), before unprinted tuplets are tried. Vector pages are not affected.

## Saved detections

- Detection is the slow step (about 3 seconds a page on the CPU, 1.3 on the GPU). For evaluation runs the detections of each page are saved once, by a pass on the GPU, and read back by the scoring runs, so fixes in the joining code are tested in minutes.
- The folder is set by `OMR_DETECTIONS_DIR`; with it unset, the detector runs on every page. A page's file is `<folder>/<2 characters>/<key>.json`, the key a SHA-256 of the model file's contents, the page scale, the detector's least confidence, and the level image's size and pixels (`reading.saved_file`). So a changed image or model is never read from an old file, and a page not yet saved is detected and saved as it is read.
- The file holds the detections as `[class index, [x0, y0, x1, y1] in the level image's pixels, confidence]`. It is written under another name and then renamed, so a run in another process never reads half a file.
- **The pass:** `scripts/detect_pages.py SET VERSION...` (default model `runs/detector/full/weights/best.pt`, default folder `detections` in the corpus folder). Levelling and the staff space are done in the worker pool, the detector in the main process on the GPU. Pages already saved are skipped, so a stopped pass can be started again; `continue.txt` pauses it.
- **Scoring from it:** `omr evaluate --set regression --set-root <corpus>/generated/raster/regression-g300 --recogniser omr` with `OMR_DETECTIONS_DIR` set to the folder and `OMR_DETECTOR` to the same model file as the pass (the key is the model's contents, so the `.onnx` file, which gives the same boxes, does not find the `.pt` file's detections).
- Checked: one regression pair converted from saved detections and with the detector gives the same MusicXML byte for byte (3 seconds against 13).

## The detector model

- `OMR_DETECTOR` names the model file; with it unset, `runs/detector/full/weights/best.onnx` in the corpus folder. ONNX on the CPU is what `omr convert` uses (OP-2); a `.pt` file runs on the GPU for evaluation passes and gives the same boxes (Stage 2.3).
- The model is loaded once per process.

## Still to come

- Text in images (Stage 2.5): the text regions are kept but not read, so titles, tempo, lyrics and other words are missing, and the structure and markings figures read low until then.
