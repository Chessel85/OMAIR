# Text and markings in page images (Phase 2, Stage 2.5)

How the words on a clean page image are read, so that `text.py` sorts them as it sorts the text of a vector PDF, and how the markings that the image path misses are found. The plan is `docs/plans/phase2.md`, Stage 2.5. The page steps this joins are in `raster-reading-spec.md`, the detector's `text` class in `raster-labels-spec.md`, the lines in `raster-lines-spec.md`.

## Principles

- **The text rules stay as they are.** `text.py` takes a page's text as `symbols.TextRun`s: the text, its box, its origin and baseline, a font name and a size. A raster page gives the same: one `TextRun` for each text region the detector found, read by OCR, with the font name and size measured from the ink. Nothing in `text.py`, `markings.py` or the writer knows the words came from an image.
- **The detector finds the text, OCR only reads it.** The detector's `text` class already gives one box for each text run (title, tempo, expression, lyric syllable, chord symbol, fingering, rehearsal mark, instrument name), kept in `PageSymbols.text_regions`. OCR runs on each box alone, in recognition mode, without its own text finder.
- **Style from the ink.** An image has no font names, and the text rules use them: italic for expression text, tuplet and bar numbers and against fingering; bold for tempo marks; the size for titles and for lyric rows; the baseline for lyric extenders. Each is measured from the box's ink and written into a font name that `text.is_italic` and `text.is_bold` read.
- **Code:** `src/omr/raster/text.py` (OCR, style and the `TextRun`s), called from `reading.read_page` once the lines are found; `scripts/check_ocr.py` measures it.

## The OCR engine

- **RapidOCR 3.10** on ONNX Runtime (Apache-2.0; `docs/licence-register.md`), with PP-OCRv5's Latin recognition model (`latin_PP-OCRv5_rec_mobile`, 8 MB, Apache-2.0). Recognition only: `use_det=False`, `use_cls=False`.
- **Why the Latin model:** on 13 raster regression pairs at 300 dpi (1,402 text boxes), the default model (PP-OCRv6 small, Chinese and English) read 92.0 percent of boxes exactly and got 4.7 percent of characters wrong; the Latin model 93.2 and 4.2. The default reads a capital O as a zero and lowercase "so" as "SO", and drops accents' neighbours ("d`a" as "da"). At 200 dpi the Latin model reads 91.4 percent of boxes exactly (7.1 percent of characters wrong), at 150 dpi 90.2 (7.0).
- **The crop:** the box with 0.15 staff spaces of the image round it. Wider margins take in noteheads and staff lines and read worse (0.5 staff spaces: 89.3 percent exact; 1.0: 79.9). White padding added round the crop changes nothing.
- **Speed:** 32 ms a box with one thread, as in a worker of the pool, where each worker's ONNX Runtime session uses one thread. A page's crops go to the recogniser one at a time: in batches each is padded to the widest in its batch, which made batches of 32 slower (46 ms a box). A page holds 30 text boxes on average (median 15, one page in ten over 70; lyrics make the most), so about a second a page in a worker, and up to 4 or 5 on a page of lyrics.
- **Offline:** the Latin model is not carried in the RapidOCR package. It is kept in `models/ocr/latin_PP-OCRv5_rec_mobile.onnx` in the repository's folder (not in Git, released with the detector's weights) and named to RapidOCR by its path, so nothing is downloaded at run time (OP-2). `OMR_OCR_MODEL` names another file.
- **Saved readings:** with `OMR_DETECTIONS_DIR` set, a page's readings are saved in one file in its `ocr` folder, keyed by the crops and the model file, and read back by later runs, as the detections are. One file a page, not one a box: thousands of small files are slow to write on Windows.
- **What OCR gets wrong, from the trial:** a first letter cut off where the detector's box starts late ("Moll" as "oll", "the Nameless" as "ameless"); a full stop or hyphen added after a lyric syllable; ligatures written out ("fl" for the single character "ﬂ", which is right). `text.py` reads the hyphens between syllables from short level lines, which the line finder gives, so a hyphen OCR reads at the end of a syllable is taken off.
- **Unread boxes:** a box OCR reads as nothing, or with a recognition score under 0.5, gives no `TextRun`. Its ink stays masked for the line finder.

## Style from the ink

- **Italic.** The strokes of italic letters lean right by about a fifth of their height. The box's ink is sheared by a range of slants (minus 0.1 to 0.4 across per unit up), and the slant that makes the columns of ink tallest and fewest is the letters' lean. Italic is a lean of at least 0.12 that gains at least 5 percent over upright, measured only on text of at least three letters: the strokes of a lone digit (1, 4, 7) lean too, and italic digits are read as tuplet numbers, so guitar fingering made false triplets (110 note errors more on one regression pair). Shorter text is upright; the detector gives tuplet numbers their own class. On 26 raster regression pairs (1,249 boxes matched to one vector run of three or more letters) the test told every italic run from every upright one, but the draw held only 20 italic runs; on 13 pairs read through the converter, 665 runs were all right.
- **Bold.** The median horizontal run of ink, over the font size: 0.077 to 0.103 for plain text (10th to 90th percentile), 0.120 to 0.160 for bold (15 runs). Bold from 0.112, measured, like the lean, only on text of at least three letters: a lone round capital (C, G) has thick sides, and as bold it was taken for a tempo mark, not a chord symbol.
- **Size.** The ink's height is 0.59 to 0.90 of the font size, depending on the letters: "ao" has neither ascenders nor descenders, "Ty" both. Once OCR has read the letters, the size is the ink's height over the share those letters fill in a typical serif font (x-height 0.45, ascenders and capitals 0.70, descenders 0.22 of the size).
- **Baseline, origin and box.** The baseline is the bottom of the ink, or, where the text has a letter with a descender, the bottom less the descender's share. The origin is the box's left edge on the baseline. The box is the font's height, as a PDF's text run is: from 0.77 of the size above the baseline to 0.23 below, across the detector's box.
- **Font name:** `"image"`, with `"-Bold"`, `"-Italic"` or `"-BoldItalic"` added, which `text.is_bold` and `text.is_italic` read.
- **Word gaps.** `TextRun.breaks` is left empty: the detector gives each lyric syllable its own box, so a run is not split further.

## Chord symbols

- The label rule joins chord-symbol glyphs (csym flats and sharps, the diminished circle) to the text box they touch, so OCR reads them with the letters. The Latin model has no ♭ or ♯: it reads them as "b", "#" or nothing, which `text.chord_value` takes for the first two. The share read right is measured on the development set (4,128 chord symbols on exact pairs); a small detector class or a shape test for the two signs is the fallback.

## Hairpins

- **Found 12.2 percent of the time on images, against 90.9 from PDFs** (development set at 300 dpi, exact pairs), so they carry most of the ACC-6 loss that is not text.
- **The cause:** near a hairpin's closed end its two arms run together in the image. The line finder's two-run columns start only where the arms part, so each arm starts 1.4 to 1.8 staff spaces late, and the joined ink is given as short level lines. The hairpin rule (`markings.hairpins`) needs both arms to start within 0.4 staff spaces of each other and to meet within 0.25 staff spaces, so it rejects them.
- **The fix, in the line finder** (`raster-lines-spec.md`, "Thin sloping lines and curves"): the arms are carried on to the point where they meet, whether found in one piece of ink or as two lines, and level pieces lying along a thin line are not given as level lines. The vector rule then takes them unchanged.

## Other markings

- Dynamics come from the detector as whole marks (`raster-reading-spec.md`). They are found 87.1 percent of the time on images against 94.1 from PDFs; the rest is for the triage.
- Staccatissimo (33.2 percent against 100) and tenuto (94.3 against 100) are lower on images for causes not yet looked into; they go to the triage, not here.
- Words (expression text) and fingering read 0 percent until this stage, since the text was not read.

## Measures

- **OCR against the vector text:** `scripts/check_ocr.py` (from the trial script): for each raster page, each text box read against the vector runs whose middles it holds, as exact boxes and the character error rate, by engraver and by text kind (as `text.py` sorts the vector runs), and the vector runs in no text box.
- **Style against the vector fonts:** the same script counts italic and bold right and wrong, and the size error.
- **In the score:** `omr evaluate` on the raster development set at 300 and 200 dpi: ACC-6, lyrics, chord symbols, words, title and composer, tempo, against the vector figures from Stage 1.8 run 3.
- **The vector reading does not change.** Every change is in `src/omr/raster/`; the vector regression set is compared byte for byte, as in Stage 2.4.
