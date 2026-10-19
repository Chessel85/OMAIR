# OMAIR explained: how a PDF becomes MusicXML

This document explains, for a musician rather than a programmer, how OMAIR reads a sheet music PDF and writes it out as MusicXML. It covers the different kinds of PDF, the strategy used for each, and worked examples given in words. It uses headings and lists throughout, with no tables or pictures. A short glossary of technical words is at the end.

The project's design documents (`requirements.md`, `solution-design.md` and the specs in `docs/notes`) hold the full detail. This document is the overview that ties them together.

## The idea in one paragraph

A PDF of sheet music can hold the music in two very different ways. It can hold it as **instructions**: "draw a black notehead here, a treble clef there, a line from this point to that one". Or it can hold it as a **photograph**: a grid of grey dots with no idea what any of them mean. Reading the first kind is like being handed the engraver's own file: nothing has to be guessed, only understood. Reading the second kind is like transcribing by ear: you have to recognise everything first, and you can mishear. OMAIR's central decision is to treat these two kinds differently. It reads the instructions directly wherever they exist, and only uses image recognition, the AI part, where there is nothing better. Both routes then share the same musical reasoning: the same rules for pitch, rhythm, voices and bar arithmetic, the same checks, and the same MusicXML writer.

## The four kinds of PDF page

OMAIR looks at every page on its own, because one file can mix kinds: a scanned title page in front of engraved music, for example. Each page is given one of four types, named A to D, or marked as having no music.

### Type A: music written in a music font

This is what MuseScore, Sibelius, Finale, Dorico and LilyPond produce when you export a PDF directly.

- Every notehead, clef, rest, accidental, dynamic and articulation is stored as a **character in a font**, exactly as the letters of a word are stored in a text document. The difference is that the font is a music font. Where a text font has the letter "A", a music font has, say, a black notehead or a treble clef.
- Each character comes with its exact position on the page.
- Staff lines, stems, barlines and beams are not characters. They are stored as drawn lines and filled shapes, again with exact positions.
- Titles, tempo marks, lyrics and chord symbols are stored as real text, which can be read directly.

There is one complication: music fonts do not all use the same alphabet.

- **SMuFL fonts.** Modern fonts follow a shared standard called SMuFL (Standard Music Font Layout), in which every symbol has a fixed character number. A black notehead is always the same number, whether the font is Leland, Bravura or Petaluma. MuseScore 3 and 4 and Dorico use SMuFL fonts. For these, the character number alone tells OMAIR what each symbol is.
- **Older fonts.** Sibelius (Opus and Helsinki), Finale (Maestro) and LilyPond (Emmentaler) use their own older layouts. In Opus, for example, the black notehead sits on the key for the character "Ï". For these, OMAIR keeps a **translation table** for each font family, which says which character means which symbol. Opus, Helsinki and Maestro happen to share one layout (that of an old Adobe font called Sonata), so one table covers all three.
- **Renamed fonts.** When a PDF is made by "printing" to PDF through a Windows printer driver, the driver often renames the fonts to meaningless codes such as "TTE26B52B8t00". OMAIR can no longer tell which table to use from the name, so it draws each character and compares its shape with known reference shapes, and picks the table whose shapes fit.

### Type B: music drawn as outlines

Sometimes the music font has been turned into plain drawn shapes, usually because the file was printed to PDF through a printer driver rather than exported. The page looks identical, but a notehead is no longer the character "black notehead": it is just "a filled oval-ish shape with these curves, at this position".

OMAIR handles this by recognising shapes:

- Every curved filled shape on the page is given a **fingerprint** based on its exact outline. Identical shapes have identical fingerprints, so a page with 300 black noteheads has 300 copies of one fingerprint. Each distinct shape only has to be identified once.
- Each distinct shape is compared with reference drawings of about 100 symbols from five SMuFL fonts (Bravura, Leland, Petaluma, Gootville and Leipzig). The best match above a set similarity is accepted.
- Shapes that are clearly not symbols are left out by their form: straight four-sided pieces are stems, barlines and beams; a thin crescent is a tie or slur.

Once each shape has a name, a Type B page is treated exactly like a Type A page.

### Type C: a clean picture of the page

The PDF holds an image of the page, or the input is an image file such as PNG or JPEG, but the image is clean: white background, level staff lines, no shadows. This is what you get when engraved music is saved as a picture rather than as a PDF, or from a good flatbed scan of a clean print. There are no characters and no lines in the file, only pixels. This page needs image recognition.

### Type D: a photo or scan of a physical page

A photo taken with a phone, or a scan of a page from a book. As well as needing image recognition, it may be tilted, curved near the spine of the book, unevenly lit, or surrounded by the table, a thumb, the facing page, or blocks of printed text. It needs tidying up before it can be read like a Type C page.

### Pages with no music

Title pages, text pages and blank pages are noted and passed over.

### How common each kind is

A survey of over 3,000 PDFs (OpenScore, Mutopia and a large sample of MuseScore.com uploads) found almost every page to be Type A. MuseScore and LilyPond output is nearly all Type A.

A smaller sample of 21 commercial editions from IMSLP, made with Sibelius, Finale and Dorico, was more mixed: 16 files Type A, 4 Type B and 1 a scan. Files exported directly by the program were Type A; most of the Type B files had been printed to PDF through a printer driver.

So the instructions route (Types A and B) covers most born-digital PDFs, and the image route (Types C and D) covers pictures, scans and phone photos.

## Step 1: deciding what kind of page it is

The first thing OMAIR does with a file is inspect each page, without any AI, and decide its type from the evidence. You can see this step on its own with the command `omr inspect`.

The clues it gathers for each page:

- **Fonts.** Which fonts are used, how many characters each draws, and whether each font is a music font. A SMuFL font is recognised by its character numbers. An older font is recognised by its name, or, if renamed, by where its characters sit: a music font's characters sit on the staves, while a text font's are words above or below them. As a final test, OMAIR draws the characters and checks whether they look like ordinary letters, because a text font used for dynamics or tempo words can also land on a staff.
- **Staves.** Groups of five horizontal lines, evenly spaced and of similar length. A staff is the strongest single sign that a page holds music.
- **Repeated outlined shapes.** Curved shapes that appear many times with the same fingerprint, which is the sign of Type B.
- **Images.** How much of the page is covered by pictures.

The decision, simplified:

- Mostly covered by an image, with few or no music characters or repeated shapes: Type C or D.
- Plenty of music-font characters: Type A.
- Plenty of repeated outlined shapes, more than music characters: Type B.
- None of these: no music.

To tell a clean picture (C) from a photo or scan (D), OMAIR looks at the image for three signs of a physical page: an uneven background (shadows, yellowed paper), a dark border (the table or the book's edge showing), and tilted staff lines. Any of these makes it Type D.

**Example.** For a MuseScore 4 export of a Bach chorale, the inspector reports, in part:

- "Type A, high confidence: 239 music glyphs in Leland and 12 staves found from vector lines."
- "Leland: SMuFL music font, 239 glyphs."
- "Edwin-Roman: text font, 54 glyphs."

## The instructions route: reading Type A and Type B pages

This is the part of OMAIR that is built and working. It runs as a chain of steps, each building on the one before. There is no AI in it at all: it is geometry, translation tables and musical rules. It reads a page in about half a second.

### Step 2: naming every symbol

Each music character on the page is turned into a named symbol, using the standard SMuFL names, such as "noteheadBlack", "gClef", "accidentalSharp", "restQuarter" or "dynamicMF". As described above, the name comes from the character number (SMuFL fonts), from a translation table (older fonts), from shape comparison (renamed fonts), or from shape matching (Type B outlines).

Each symbol keeps an exact anchor point. For a notehead, that is its centre line, which tells you which line or space it is on. For a clef, it is the line the clef names: the G clef curls round the G line, the F clef's dots sit either side of the F line.

The size of the symbol is also kept. A notehead noticeably smaller than normal is a grace note, a cue note, or the little note in a metronome mark.

### Step 3: finding staves, systems, bars and parts

From the drawn lines, OMAIR works out the layout of the score.

- **Staff lines and staves.** A staff is five horizontal lines that are equally spaced, thin, of similar length and at least six staff spaces long. The gap between lines, the **staff space**, becomes the ruler for everything else: distances are measured in staff spaces, not centimetres, so the rules work at any size of print.
- **Staff steps.** Every symbol is given a step on its staff: 0 for the bottom line, 1 for the bottom space, 2 for the second line, and so on up to 8 for the top line. Ledger-line notes go below 0 or above 8.
- **Systems.** Staves are grouped into systems when a line runs down through them at the left, when a brace joins them, or (for choir scores in LilyPond, which draws nothing joining the staves) when their barlines all line up.
- **Barlines.** A barline is a vertical line that covers a staff from top line to bottom line. The tricky part is telling barlines from note stems, which are also vertical lines. A stem has a notehead at one end, on the right side of the stem if it goes up, or the left side if it goes down. A barline does not.
- **Bar types and repeats.** A thick line marks a final or double barline. Two dots in the middle spaces just before a barline mark the end of a repeated section; just after, the start of one.
- **Parts.** Staves joined by a brace are one part, such as a piano. A single staff is a part of its own. The part's name is the text to the left of its staves. When later systems hide empty staves, OMAIR matches each system to the full list of parts using the instrument names and clefs.

### Step 4: clefs, key signatures and time signatures

- **Clefs.** A clef symbol plus the line it sits on gives its meaning: treble clef on the second line, bass clef on the fourth, a C clef on the third line for alto. A small 8 above or below makes it an octave clef.
- **Key signatures.** A run of sharps or flats at the start of a bar is a key signature if their positions follow the standard order: for sharps F, C, G, D, A, E, B, and for flats B, E, A, D, G, C, F. So two sharps on the F line and the C space of a treble staff are D major (or B minor). Naturals before them cancel the previous key.
- **Time signatures.** Two digits stacked above and below the middle line, or the common time and cut time symbols.
- **Endings, segno, coda and D.C.** A "1." or "2." above the top staff at the start of a bracket line marks an ending. Segno and coda signs, and the words D.C., D.S., To Coda and Fine, are read where they stand.

### Step 5: working out the notes

This is where the musical knowledge really comes in. For each notehead, OMAIR works out its pitch and its written length.

#### Pitch

Pitch comes from five things, applied in this order:

1. **The staff step** of the notehead.
2. **The clef in force.** In the treble clef, step 0 (the bottom line) is E4, step 4 (the middle line) is B4, and step 8 (the top line) is F5. In the bass clef, step 0 is G2 and step 8 is A3.
3. **The key signature.** If the key has F sharp, every F is raised unless told otherwise.
4. **Accidentals earlier in the bar.** An accidental belongs to the notehead just to its right on the same step, and lasts for later notes on that line or space until the barline, as in normal reading.
5. **Ties and octave lines.** A note tied across a barline keeps its accidental. Notes under an "8va" line are an octave higher than written.

**Worked example.** A piece in G major, treble clef. A black notehead sits on the top line, which is step 8.

- Treble clef, step 8: F5.
- The key signature has one sharp, on the F line: so F sharp 5.
- Earlier in the same bar, a natural sign stood in front of another notehead on the top line: so this note is F natural 5 instead, because the natural lasts to the barline.
- In the next bar, the natural has expired, and a notehead on the top line is F sharp 5 again.

#### Written length

Length comes from what is attached to the notehead:

- **The notehead.** Black is a quarter note, open (white) with a stem is a half note, open without a stem is a whole note.
- **The stem**, found as a thin vertical line touching the notehead on its right (stem up) or left (stem down). All the noteheads on one stem form a chord.
- **Beams and flags.** Each beam or flag on the stem halves the length: one makes an eighth, two a sixteenth, three a thirty-second.
- **Dots.** A dot to the right adds half; two dots add three quarters.
- **Tuplets.** A small italic number, such as 3, over or under a group gives the tuplet. A 3 alone means three in the time of two; a 5, 6 or 7 means that many in the time of four.

**Worked example.** A black notehead with a stem up, two beams crossing the stem, and a dot to its right. Black notehead: quarter. Two beams: halved twice, a sixteenth. One dot: a dotted sixteenth, which is three thirty-seconds long.

#### Grace notes and cue notes

Small noteheads followed closely by a normal-sized note are grace notes, attached to that note. Small notes with no normal note after them are cue notes, which keep their own rhythm.

### Step 6: rhythm, onsets and voices

Knowing each note's length is not quite enough. OMAIR also has to work out **when** each note starts within the bar (its onset) and **which voice** it belongs to. This is the hardest part of reading a page, especially for piano music where two or three voices share a staff.

The method works one staff and one bar at a time.

1. **Columns.** Notes and rests that stand one above the other start together, like a chord. They are grouped into columns. Engravers sometimes shift a note slightly sideways when two voices collide, so the rule allows for that.
2. **Fitting the columns in time.** The columns are placed in order. Each column should start exactly when some note before it ends. If every voice runs on without a gap, that rule alone gives the answer. But engravers often hide rests, a voice may stop part-way through a bar, and a note might have been missed, so OMAIR tries the possible arrangements and gives each a penalty score: a point for a note whose end has nothing starting after it, a point for a column that starts where nothing ends, and a heavy penalty for anything that spills past the end of the bar. The arrangement with the lowest penalty wins. A score of zero means everything fits perfectly.
3. **Helping each other.** If one staff in a bar is uncertain, the other staves of the same bar help: things that stand at the same place across the page should sound at the same time.
4. **Voices.** Finally, notes are chained into voices: each note continues a voice that ends where it starts, preferring notes with the same stem direction.

**Worked example.** A bar in 3/4 on a piano right-hand staff. A dotted half note has its stem up. Under it are three quarter notes with their stems down.

- Column one holds the dotted half note and the first quarter note. Column two holds the second quarter note. Column three holds the third.
- Column one starts on beat 1. The first quarter ends on beat 2, so column two starts there. The second quarter ends on beat 3, so column three starts there.
- Every note ends either where another starts or at the end of the bar. The penalty is zero, so this reading is accepted.
- The stem-up dotted half becomes voice 1. The three stem-down quarters chain together into voice 2.

#### Bar arithmetic

Each voice in a bar should add up to the time signature. When a bar does not add up, OMAIR tries one common explanation first: unmarked triplets. A beamed group of three equal notes with no "3" printed, in a bar that is too long, is tried as a triplet, and the reading is kept if the bar then adds up. A bar that still does not add up is noted for the confidence report (step 9). A short first bar (a pickup), and two short bars that together make one (a bar split at a repeat), are allowed.

### Step 7: ties, slurs and other curves

Curved lines are ties or slurs. A curve that joins two noteheads on the same step, with its ends level, is a tie. Other curves are slurs, which are attached to the notes under their two ends. A wavy vertical line beside a chord is an arpeggio sign.

### Step 8: text and markings

The text in the PDF is real text, so it is read exactly. The job is to decide what each piece of text **is**, which OMAIR does from where it stands and what it looks like.

- **On the first page, above the music:** text centred over the page is the title (the top line of the largest size) and subtitles; text at the right margin is the composer or arranger; text at the left margin is the lyricist.
- **At the top and bottom of other pages:** headers, footers, page numbers and copyright lines.
- **To the left of a system:** instrument names.
- **Over the top staff:** tempo marks (a word such as Allegro, Lento or a tempo, or bold upright text), metronome marks ("quarter note = 120"), rehearsal marks (a letter or number in a box), and expression text ("dolce", "rit.").
- **Rows of short words under a staff, under its noteheads:** lyrics. Hyphens between syllables and the extender line after a held syllable are read, and several rows give several verses.
- **Rows of text over a staff that read as chords:** chord symbols. "Am7" is read as root A, minor seventh; "C/E" is C major with E in the bass.
- **Single digits by a notehead:** fingering. A single italic p, i, m or a is guitar right-hand fingering.
- **Dynamics:** symbols such as p, mf and sfz in the music font, or the same letters in bold italic text. Hairpins (crescendo and diminuendo wedges) are found from pairs of thin lines that open or close.
- **Articulations, fermatas and ornaments:** symbols near a notehead, attached to that note: staccato, accent, tenuto, trill, mordent, turn and so on.

### Step 9: checking itself and saying where it is unsure

Because the owner cannot look at the output, OMAIR checks its own reading with musical rules and writes a plain-text **confidence report** naming the bars that may be wrong. You can run this step on its own with `omr confidence`.

The checks include:

- **Rhythm.** A note starts where no earlier note ends, or a note runs past the end of the bar.
- **Bar fullness.** A voice that does not add up to the time signature.
- **Staves disagree.** Two notes that stand one above the other on different staves but have been placed at different times.
- **Unprinted tuplet.** A group read as a triplet only because the bar would not otherwise add up.
- **Ties.** A tie with no note of the same pitch at its other end.
- **Stray symbols.** A flag not on a stem, an accidental with no note after it, a dot that belongs to nothing.
- **Octave signs.** An 8va line whose staff or direction is a guess.
- **Hidden staves.** A system where it was not certain which staff belongs to which part.
- **Also worth checking:** a note spelt oddly for its key (D sharp in A flat major), a note outside the normal range of the named instrument, a slur that starts but never stops.

**Example report lines:**

- "Summary: 64 bars, 61 high confidence, 3 flagged."
- "Page 2, system 1, bar 14, Violin, beat 2.5: a note starts where no note before it ends."

On the test scores, the flagged bars hold roughly nine out of ten of the reading errors while only about one bar in twenty is flagged, so the report points you to a small number of bars that are worth checking.

### Step 10: writing the MusicXML

Finally, everything read is written as a MusicXML 4.0 file: the title and composer, the parts, every bar with its clef, key and time changes, repeats and endings, every note and rest in every voice with its pitch, length, ties, tuplets, grace notes, lyrics, articulations and slurs, and the dynamics, hairpins, tempo marks, words and chord symbols.

The writer is built as the exact reverse of the reader the test system uses: if the MusicXML file is read back in, it must give exactly the same notes and structure that OMAIR read from the page. So the accuracy measured on the reading carries over unchanged to the file.

The command `omr convert` runs all of these steps on a PDF and writes the MusicXML file, the confidence report, a flag file for the test system, and a braille file (a placeholder until the braille code is chosen).

### How well the instructions route reads

These figures are from scores the reader was never tuned on, as well as the development scores.

- **Notes:** about 98 percent of notes right (pitch, onset and length all correct). MuseScore output reads at about 98.5 to 99 percent.
- **Structure:** about 80 to 84 percent of files have every bar, part, clef, key, time, repeat and ending exactly right. Many of the rest have only one or two mismatches.
- **Dynamics and hairpins:** about 93 percent.
- **For comparison:** on the same test scores, Audiveris (the engine behind MuseScore's PDF import) gets about 86 percent of notes right, and homr (an open-source AI reader) about 56 percent.
- **Commercial files:** PDFs exported directly from Sibelius, Finale and Dorico mostly read well. Files printed to PDF through a Windows printer driver mostly do not yet, and the reasons are still to be investigated.

## The image route: reading Type C pages

This route is being built now (Phase 2 of the project). The steps below describe the design; the section "Where the image route stands" says which parts exist.

### The strategy: turn the picture back into instructions

The instructions route is the best reader the project has. Everything after step 2 (staves, bars, pitch, rhythm, voices, text, checking and writing) does not care where its symbols and lines came from. So the main strategy for images is:

**Look at the picture, work out the symbols and lines that would have been in the PDF, and hand those to the instructions route as if they had come from a PDF.**

This means every improvement to the musical reasoning helps both routes at once. It also means the image route only has to do one new job: recognise symbols and lines in pixels.

### Step A: level the page and measure it

- The picture is turned very slightly if needed so that the staff lines are exactly level.
- The staff space is measured in pixels, from the most common gap between dark lines going down the page. A typical score at 300 dots per inch has a staff space of about 21 to 24 pixels; at 150 dots per inch, about 10 to 12.

### Step B: find the lines

Staff lines, barlines, stems, ledger lines, beams, hairpins, tuplet brackets, ending brackets, ties and slurs are found with classical image processing, without AI. The method follows runs of dark pixels along rows and down columns, joins them up, and checks their shape: a staff line is long, thin and level; a stem is thin and upright with a notehead at one end; a beam is thick and may slope. The lines are then written out in exactly the form a PDF would have given, so steps 3 onwards take them unchanged.

### Step C: find the symbols with a trained detector (Engine 1)

This is where AI comes in. A **symbol detector** is a neural network that looks at a piece of the page and draws a box round every symbol it recognises, with a name and a confidence. The model used is a small version of a well-known detector called YOLO ("you only look once"), chosen because it can be trained on the project's laptop.

The detector knows about 100 kinds of symbol, called classes, grouped by what they look like:

- noteheads by kind (black, half, whole, and others such as cross noteheads);
- rests by value;
- flags, augmentation dots and staccato dots;
- sharps, flats, naturals, double sharps and double flats (the same class whether they are accidentals or part of a key signature, because the reasoning steps tell those apart by position);
- clefs;
- time signature digits;
- one class per dynamic (p, pp, mf, sfz and so on);
- articulations, fermatas, ornaments, pedal marks and the like.

Lines are deliberately not detector classes: they are left to step B.

#### How the detector learns

A detector learns from examples: thousands of pictures in which every symbol has already been boxed and named. Making those by hand would take years. OMAIR makes them automatically, using the instructions route:

1. Take a MuseScore, LilyPond or Verovio PDF. The instructions route already knows exactly what every symbol is and where it is.
2. Turn the PDF page into a picture, at a range of sizes from about 150 to 300 dots per inch, so that the detector works whether a page was scanned finely or coarsely.
3. Cut the picture into tiles 640 pixels square, and write down the box and name of every symbol in each tile.
4. Add small, realistic imperfections: slight blur, JPEG compression, faint noise, greyscale and pure black and white.

This gives perfectly labelled training pictures at no cost. The current training set has over 11,000 tiles from 1,000 scores, none of them from the scores used for testing. Training runs overnight on the laptop's graphics card and takes from many hours to about two days.

The labels are checked by numbers rather than by eye: every symbol on a page has exactly one box inside the picture, no two boxes of one class cover the same ink, and the boxes agree with where the ink actually is.

### Step D: hand the detections to the instructions route

The detector's boxes become named symbols with anchor points, just like the symbols of step 2. Together with the lines from step B, they form a page that the instructions route reads from step 3 onwards. A symbol the detector was unsure of, or where two names scored nearly the same, becomes a doubt that the confidence report can flag.

**Example.** The detector draws a box round a black notehead with confidence 0.98, and a box just to its left labelled "sharp" with confidence 0.55. The notehead is used as normal. The sharp is used too, but because the detector was not confident, the bar is flagged: "the sharp before this note is uncertain".

### Step E: read the text with OCR

Text in a picture is not stored as text, so it is read with OCR (optical character recognition, the same technology that reads scanned documents). The text found is then sorted by the same rules as step 8: title, composer, tempo, lyrics, chord symbols and so on.

### Step F: a second opinion from a sequence reader (Engine 2)

The detector-plus-rules approach depends on finding nearly every symbol. A missed dot or accidental becomes a wrong note. As a second, independent opinion, OMAIR will also use a **sequence reader**: a different kind of neural network that looks at a whole staff at once and writes out the music directly as a sequence, much as a person reads a line of music from left to right. The starting point is the network from the homr project, which will be retrained on the project's own scores.

The two readers work in very different ways, so they tend to make different mistakes.

### Step G: compare the two readings

The two readings are compared bar by bar.

- Where they agree, confidence is high.
- Where they differ, both readings are kept, and the musical rules choose between them: which one makes the bar add up, agrees with the other staves, fits the key, and stays in the instrument's range.
- Where they still disagree, the bar is flagged with both readings in words. For example: "Page 1, bar 6: the engines disagree on the third note, F sharp 5 or G 5. Chose F sharp 5 because the key is D major."

This is like asking two people to transcribe the same passage independently, and then checking their disagreements against the rules of harmony and rhythm.

### Step H: check by re-engraving

As a final check, OMAIR will engrave its own MusicXML back into a page, with the same system breaks as the original, and compare it with the input, system by system. Noteheads, accidentals and rests should all be in the same places. A bar that looks different is flagged. This catches errors that break no musical rule, such as a whole bar shifted by a beat, which still adds up but is wrong. It will be used on the instructions route as well.

### Where the image route stands

- **Built:** turning image PDFs into test sets; the training-data generator; levelling the page; finding staff lines, barlines, stems, beams and curves. Every staff is found, and over 99 percent of barlines and stems. With the lines found from the picture, and the symbols still taken from the PDF, about 96.5 percent of notes come out right, against about 98 percent when everything comes from the PDF. So the line finding costs a point or two.
- **In progress:** training the symbol detector. A first pair of trial trainings, to choose the best range of picture sizes, has just finished, and the full training run comes next.
- **Still to come:** joining the detector to the instructions route, text by OCR, the sequence reader, comparing the two readers, and the re-engraving check.
- **The target:** at least 97 percent of notes right on clean pictures at both 300 and 200 dots per inch. 200 dots per inch is used as a stand-in for a good phone photo, because blur and compression leave a 12 megapixel photo with about that much real detail.

## The photo route: Type D pages

This is planned for a later phase (Phase 4). A photo or scan is first tidied up into something like a clean Type C picture, and then read by the image route. The tidying steps are:

1. **Find the page.** Find its edges, and split a two-page spread at the spine.
2. **Flatten it.** Correct the angle of the camera, and flatten the curve near the spine of a book. Staff lines are a great help here: they are known to be straight and evenly spaced, so any bend in them shows exactly how the page is curved. Ordinary text documents have nothing so reliable.
3. **Even out the lighting**, removing shadows and the grey of the paper.
4. **Keep only the music.** A small trained detector finds the music systems and discards blocks of printed text, pictures, the table, the spine and fingers. Text near a system is kept, because it may be a title, tempo mark, lyric or chord symbol.

The training pictures for this will also be made automatically: engraved pages placed on photographs of real desks and book pages, with text blocks added, and bent, tilted and shadowed in the computer. A smaller set of real phone photos of printed test pages will be used to measure how well it works.

## How accuracy is measured without looking

The owner cannot check the output by eye, so accuracy is measured entirely by software against a collection of scores with known answers (the corpus).

- **Pairs of PDF and answer.** Public-domain scores are taken as MusicXML from PDMX and OpenScore. Each is engraved to PDF by several programs: MuseScore 4, MuseScore 3 (in several music fonts), LilyPond and Verovio. Each PDF, paired with the MusicXML it came from, is a test with a known answer. For image tests, the same PDFs are turned into pictures at 300, 200 and 150 dots per inch.
- **Different engravers on purpose.** Each program lays out music differently and uses different fonts, so the reader is tested on variety, not on one house style.
- **Sets kept apart.** A development set of 300 scores is used while improving the reader. A sealed check set of 100 other scores is scored only at milestones, to show that the improvements are general and not tuned to particular pieces. Training material for the AI comes from yet other scores.
- **Comparing note by note.** OMAIR's output is compared with the answer note by note and bar by bar: right pitch, right onset, right length; right bars, parts, clefs, keys, times and repeats; right dynamics and markings. It also measures whether the flagged bars are the ones that really hold the errors.

Real-world PDFs without answers, such as the commercial IMSLP editions, are judged by how many bars pass all of OMAIR's own checks. That is a rough guide, not a true accuracy figure.

## And then braille

Braille music is produced from the MusicXML, not from the page. A wrong note in the MusicXML would become a wrong note in braille, which is why nearly all the effort goes into reading the page accurately. Which braille music code and format to use by default is still to be decided with braille-reading musicians and the MuseScore community. Until then, the braille output is a placeholder, produced through an adapter that can drive existing MusicXML-to-braille translators.

## Glossary

- **Anchor point:** the exact point a symbol is positioned by. For a notehead, its centre line; for a clef, the line it names.
- **Corpus:** the collection of test scores with known answers.
- **Detector:** a neural network that draws a named box round each symbol it recognises in a picture.
- **Dots per inch (dpi):** how finely a page has been turned into pixels. 300 dpi is a fine scan; 150 dpi is coarse.
- **Engine:** one complete method of reading a picture. Engine 1 is the detector plus the musical rules; Engine 2 is the sequence reader.
- **Engraver:** the program that laid out and printed the music: MuseScore, Sibelius, Finale, Dorico, LilyPond or Verovio.
- **Glyph:** one character of a font, whether a letter or a music symbol.
- **MusicXML:** the standard file format for exchanging sheet music between programs. MuseScore, Sibelius, Finale and Dorico can all open it.
- **OCR:** optical character recognition, reading printed text from a picture.
- **Onset:** the moment within a bar that a note starts.
- **Outlines:** symbols stored as drawn shapes rather than as font characters (Type B).
- **Pixel:** one dot of a picture.
- **SMuFL:** Standard Music Font Layout, the shared standard that gives every music symbol a fixed character number in modern music fonts.
- **Staff space:** the gap between two staff lines. OMAIR measures all distances in staff spaces, so its rules work at any size of print.
- **Staff step:** a note's position on the staff: 0 for the bottom line, 1 for the bottom space, up to 8 for the top line.
- **Translation table:** a list saying which character of an older music font stands for which symbol.
- **Vector PDF:** a PDF that stores the music as instructions (characters, lines and shapes) rather than as a picture. Types A and B.
