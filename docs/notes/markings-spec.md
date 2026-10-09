# Text and markings (Phase 1, Stage 1.4)

How the text and markings of a score are read from a vector PDF: the page text (title, subtitle, composer, lyricist, rights), lyrics with their hyphens and melismas, chord symbols, tempo and expression text, rehearsal marks, metronome marks, dynamics, hairpins, articulations, fermatas, ornaments, breath marks, fingering, plucking letters and slurs. It works from the text runs and symbols of Stage 1.1 (`symbol-spec.md`), the staves and bars of Stage 1.2 (`layout-spec.md`), the notes of Stage 1.3 (`notation-spec.md`), and the page's lines and curves.

- Code: `src/omr/pdf/text.py` (sorting text into kinds, page by page) and `src/omr/pdf/markings.py` (attaching markings to bars, onsets and notes, system by system). Both are called by `omr.pdf.notation.read_notes`, so `omr.pdf.structure.read_pdf(path, notes=True)` gives them.
- Check: `scripts/check_markings.py`. It reads each PDF and scores it with the harness's own rules, so the marking figures are those `omr evaluate` would give. CI runs it on the regression set with a floor of 97 percent for ACC-6.
- Where the results go: directions (words, tempo marks, chord symbols, dynamics, hairpins, rehearsal and metronome marks) are `Marking`s in `score.markings`; marks, slurs and lyrics are on the notes; page text is in `score.text`. The harness compares the first two and ignores `score.text`, rehearsal and metronome marks; `check_markings.py` scores those itself.

## Text runs

- Stage 1.1 joins the characters of one font, size and line into a run, up to a gap of half an em. A run now also records where a new span of the PDF starts. Engravers set each lyric syllable as its own span, close to the next, so a run is split where a new span starts after any gap, and pieces that turn out not to be lyrics are joined again.
- A chord letter and what touches it on its line join into one run when the second piece is smaller or raised (a superscript 7), is a chord glyph of a music font (MuseScore 4 sets the flat, sharp, minor, diminished, half-diminished, augmented and major-seventh signs of chord symbols in Leland Text: `csymAccidentalFlat`, `csymMinor` and so on), or the two read together as a chord.
- Bold and italic are read from the font name.

## Page text

- **Above the music on page 1**: text more than 6.2 staff spaces above the first system's top staff is a credit. So is plain text whose right edge is at the right margin (within 0.6 staff spaces) more than 4 staff spaces above it: a composer's name can be set close over the music.
  - Text centred on the page (or on the systems), within 2 staff spaces: the **title** is the top line whose size is at least 0.65 of the largest centred size, with lines of that size just under it; other centred lines are **subtitles**. Size alone does not decide: some scores set the subtitle larger than the title.
  - Text at the right margin: **composer** (arrangers too, as MuseScore writes them).
  - Text at the left margin, left of the centre: **lyricist**.
  - Lines of one kind set one under another (less than 0.8 of the size apart) join into one credit.
- **Above the music on other pages**: text in the top tenth of the page and more than 6.2 staff spaces above the first system is a header or page number.
- **Below the music**: text in the bottom tenth of the page (and at least 3 staff spaces below the last staff), or more than 9 staff spaces below the last staff, is page text: a page number if it is only a number, otherwise rights on page 1 or text that names a copyright or licence, else a footer.
- Everything else belongs to the nearest system (by distance to its staves), including text far above a staff of high guitar notes.

## Text in a system

Each run is first tied to a staff: the staff it is on, or above the top staff, below the bottom staff, or in the gap between two staves, the nearer one. Then the first rule that fits gives its kind:

1. Left of the system: an **instrument name** (Stage 1.2 uses these).
2. A number after a metronome note (`= 120`, `= c. 80`): a **metronome mark**, with the beat unit from the note glyph. Brackets and a lone `=` around it are punctuation.
3. "N.C." over a staff: no chord (not words).
4. A number of up to four digits at the start of a system, above it: a **bar number**.
5. An ending number over the top staff, an italic tuplet number, or an octave mark's text: left to Stages 1.2 and 1.3.
6. Up to four characters inside a small box drawn over a staff: a **rehearsal mark**.
7. Other digits: **fingering** if a single upright digit 0 to 5 stands over or under a notehead (up to eight staff spaces, stacked over a chord) or just left of one at its height; a bar number if centred over a barline; otherwise nothing.
8. A dynamic spelt in letters (p, mf, sfz and the like) in a bold or italic font: a **dynamic**.
9. A single italic letter p, i, m, a or c by a notehead: a **plucking letter** (guitar right-hand fingering).
10. Rows of text over a staff that read as chord symbols: **chord symbols** (below).
11. Rows of syllables under (or over) a staff, under its noteheads: **lyrics** (below).
12. What is left over the top staff of a system, naming a tempo (Allegro, Lento, a tempo, Langsam and so on) or set in bold upright: a **tempo mark**. Everything else is **words** (expression and other staff text). Both are written as words.

### Chord symbols

- A row is text of one font and size on one baseline over one staff. If at least 0.6 of its runs read as chords, those runs are chord symbols. A lone letter A to G counts only in a row of two or more, or in the style of another chord row of the page (so a last chord alone on a system is still found, while a single "A" over a staff is not taken for a chord without support).
- A chord reads as a root A to G, an optional flat or sharp, a suffix built from the usual pieces (m, maj, dim, aug, sus, add, numbers, flats and sharps, brackets, °, ø, +), and an optional bass after a slash.
- Each run is tied to the staff it stands over: a chord row in the gap between two staves belongs to the staff below.
- The value is written in the harness's words: the root, then the printed suffix, or "major" when nothing follows the root, then " / " and the bass ("Am7" is "A m7", "C/E" is "C major / E"). `text.CHORD_KINDS` gives the MusicXML kind of each usual suffix (m7 is minor-seventh), for Stage 1.6.
- MuseScore often writes a chord kind without the text it prints ("minor-seventh" for a printed "m7", always so when it draws chord symbols with signs), and the harness compares chord symbols by text. Those chords then cannot match whatever is read. `check_markings.py` therefore also reports chord symbols **by meaning**: root and kind in the same bar.

### Lyrics

- Rows: text of one font and size under one staff (or over the top staff), on one baseline within a third of a staff space. Bold text is never a lyric.
- A row of three or more syllables, at least 0.6 of them under a notehead of the staff (the syllable's middle within two staff spaces of the notehead's, or its left edge at the notehead's), is a lyric row and sets a lyric style (font and size) for the page. A shorter row is lyrics if it is in a lyric style of the page and all its syllables stand under noteheads. On a page with no lyric style, a plain upright row under a staff whose syllables all stand under noteheads is lyrics too.
- Rows of one staff are verses, numbered from the top. A verse number set apart at the start ("1.") is kept in the first syllable's text, as MuseScore keeps it.
- **Hyphens** are a "-" run, a hyphen at the end of the syllable, or a short level line between two syllables at mid-letter height (above the baseline). **Extenders** (melismas) are level lines at the baseline after a syllable, at least 0.8 staff spaces long. A syllable is single, begin, middle or end by the hyphens before and after it.
- Each syllable goes to the chord of its staff whose noteheads' middle (or left edge) is nearest, within 2.5 staff spaces, preferring the stem-up chord where two are equally near. The lyric is on the chord's lowest note, as MuseScore writes it.

## Directions: bar and onset

- A direction's bar is the bar of the system at its x. Its onset is that of the nearest column of notes and rests on its staff in that bar (any staff if its own has none), or of the first columns of the next bar if they are within 3 staff spaces (text set a little left of a bar's first note can start before the barline): by the left edge of the noteheads for words, tempo marks and chord symbols, which engravers set from the note's left; by the middle of the noteheads for dynamics, which engravers centre under the note.
- A rehearsal mark stands over the barline at the start of its bar: its bar is the bar at its right edge (plus half a staff space), at onset 0.
- Staves: a dynamic or hairpin between two staves of one part (a piano) belongs to the upper staff; between two parts, to the nearer staff (a singer's dynamics stand above the staff, clear of the lyrics below).

## Dynamics

- Dynamic glyphs (`dynamicPiano`, `dynamicMezzo`, `dynamicForte`, `dynamicSforzando`, `dynamicZ`, `dynamicRinforzando` and the combined glyphs such as `dynamicMF`) next to each other on one baseline (gaps from -1 to 0.6 staff spaces: fonts kern m and f so they overlap) are one dynamic, read letter by letter ("m" and "f" make "mf").
- Dynamics in letters come from the text (above).
- A word such as più, meno, poco, molto, sempre or subito set next to a dynamic (on its line or stacked on it) is a dynamic of its own, as MuseScore writes it (MusicXML's other-dynamics).
- The value is the letters; MusicXML has elements for the usual ones, and the rest are other-dynamics (Stage 1.6 writes them).

## Hairpins

- A hairpin is two thin stroked lines, at least 1.5 staff spaces long and sloping by no more than 0.4 of their length, whose left ends and right ends are within 0.4 staff spaces of each other in x, and which meet at one end (within 0.25 staff spaces) and open at the other (0.4 to 3 staff spaces, at least 0.35 staff spaces wider than the closed end). Meeting on the left is a crescendo, on the right a diminuendo.
- A hairpin carried over a system break: the piece before the break is narrower than 0.9 staff spaces at its open end at the right margin (a crescendo) and has no end there; the piece after the break starts open (more than 0.25 staff spaces) near the start of the system and has no start. A diminuendo is the mirror image.
- The start is placed like words (at the column nearest its left end). The end is the onset of the first column at or after its right end, or the end of the last event in the bar if it reaches past the last column.

## Marks on notes

- **Articulations, fermatas, ornaments, bowings**: the glyph names (without Above or Below) map to the harness's marks: `articAccent` to accent, `articStaccato` to staccato, `articTenuto` to tenuto, `articStaccatissimo` (and its wedge and stroke) to staccatissimo, `articMarcato` to strong-accent, `articTenutoStaccato` to detached-legato, the combined glyphs to both marks, `fermata...` to fermata, `ornamentTrill` to trill-mark, `ornamentShortTrill` and `ornamentTremblement` to inverted-mordent, `ornamentMordent` to mordent, `ornamentTurn` to turn, `stringsUpBow` and `stringsDownBow` to up-bow and down-bow, and a few more (`markings.NOTE_MARKS`).
- A mark belongs to the chord whose noteheads' middle is within 1.1 staff spaces of the mark's middle (1.6 for fermatas and ornaments), the nearest vertically, within 4 staff spaces of its noteheads and stem (8 for a fermata). If the nearest such event is a rest (a fermata over a rest), the mark is not on a note. The mark goes on the chord's lowest note, as MuseScore writes it.
- **Staccato dots drawn as plain dots** (outlined pages, where a staccato dot looks like an augmentation dot): a dot that is not an augmentation dot and stands over or under a notehead, 0.6 to 2.6 staff spaces from it, is a staccato.
- **Breath marks and caesuras** belong to the chord before them on the staff they stand on.
- **Fingering** is text, or the fingering digits of a music font (`fingering0` to `fingering5`). Digits stacked over a chord go to its notes from the top note down (the lowest digit is the top note's); digits under it from the bottom note up; a digit just left of a notehead goes to that notehead. Each note gets "technical fingering". Plucking letters are placed the same way and give "technical pluck".
- **Arpeggios** are Stage 1.3 (`notation-spec.md`).

## Slurs

- Curves (Stage 1.3's primitives, at least 0.8 staff spaces wide) that are not ties. Each end goes to the chord whose noteheads and stem come within 1.5 staff spaces across and 2.5 staff spaces up or down of it, the nearest (horizontal distance counted twice). The left chord gets a slur start and the right chord a slur stop, on its lowest note.
- A curve with no chord at its left end that starts at or before the first chord of the system continues a slur from the system before (a stop only); one with no chord at its right end that reaches past the last chord runs on to the next system (a start only). Other curves with an end at no chord are left out.

## Category review

The kinds were chosen to match what MusicXML (and so Stage 1.6 and the harness) can hold, and reviewed against the ground truth of the regression and development sets:

- Title, subtitle, composer, lyricist and rights are MusicXML credit types. Headers, footers and page numbers are not written: MuseScore writes them from its own settings.
- Tempo and expression text are both written as words; the harness compares words only. Tempo marks are kept apart so that Stage 1.6 can give them a sound tempo with the metronome mark.
- Rehearsal marks, metronome marks, chord symbols, lyrics, part names, fingering and plucking letters each have a MusicXML element.
- Bar numbers, tuplet numbers, ending numbers and octave-mark text are not text for the reader; other stages read them.
- Navigation words (Fine, D.C. al Fine) are words as well as the navigation marks of Stage 1.2, as MuseScore writes them.
- Some scores enter text in an odd place: an attribution entered as a lyric, a title entered as staff text, a "più" written as a dynamic. The rules follow what the ground truth holds where a rule can tell (più next to a dynamic) and otherwise leave it (a single long "lyric" that is really an attribution is read as words).

## Results

`scripts/check_markings.py` reads each PDF and scores it with the harness's rules. ACC-6 is the recall of dynamics and hairpins together on exact pairs (MuseScore 4), as `omr evaluate` reports it. Note accuracy is unchanged by this stage.

On the regression set (256 pairs):

- **ACC-6: 99.4 percent** (356 of 358) on exact pairs; the target is 90 percent. Audiveris, the best baseline, reached 74.0 percent on the development sample.
- Exact pairs: dynamics 99.1 percent recall, 98.2 percent precision; hairpins 100 and 100; hairpin ends 98.5 and 98.5; words 90.3 and 86.8; chord symbols 98.8 and 98.8.
- Engraver-input pairs: dynamics 91.2 and 89.5; hairpins 95.8 and 94.6; words 85.9 and 69.2; chord symbols 98.0 and 98.6.
- Marks on matched notes, exact pairs: lyrics 94.0 percent, with 98.4 percent of the lyrics found also right in their hyphens and melismas; slur ends 92.2; fingering 92.5; plucking letters 77.8; staccato 95.0; accents, tenuto, fermatas, strong accents, trills and arpeggios 100; staccatissimo 93.8; breath marks 81.8.
- Page text, exact pairs: titles 92.9 percent, subtitles 86.7, composers, lyricists and rights 100, rehearsal marks 100 (precision 83.3), metronome marks 86.6, part names 94.8.
- The baselines score 0 percent on lyrics, words and chord symbols.

On the development set (1,778 pairs; report in `evaluations/markings-development.txt` on the corpus drive):

- **ACC-6: 93.1 percent** (10,458 of 11,238) on exact pairs, above the 90 percent target.
- Exact pairs: dynamics 94.1 percent recall (94.5 precision); hairpins 90.9 (92.3); hairpin ends 85.7 (86.3); chord symbols 80.5 (83.6), and 87.5 percent by meaning (root and kind); words 67.8 (66.7).
- Engraver-input pairs: dynamics 76.6 (72.5), hairpins 85.5 (86.2), words 68.8 (53.6), chord symbols 68.0 (69.1).
- Marks on matched notes, exact pairs: lyrics 95.7 percent (96.0 percent of them right in hyphens and melismas), staccato 99.9, arpeggios 97.2, fingering 95.1, slur ends 82.8. Engraver-input pairs: lyrics 95.9.
- Page text, exact pairs: titles 94.6 percent, subtitles 94.5, composers 88.7, lyricists 90.0, rights 99.1, rehearsal marks 66.1 (precision 97.7), metronome marks 83.0, part names 87.1.
- Words are the weakest kind on the development set: about a third are missed or misplaced (text placed far from its note, text the ground truth holds as another element, multi-line text). They are diagnostic figures (REC-4 to REC-6), not a gate target, and are the first thing to improve after Phase 1.

## Known limits

- **Slurs across two staves** (a slur from the left hand to the right hand) and **two slurs from one note** are often missed. Slurs are not part of the Stage 1.4 done condition.
- **Chord symbols** whose kind MuseScore writes without its printed text differ in words from the ground truth ("A minor-seventh" against "A m7"). This is a limit of the harness's text comparison; comparing chord symbols by root and kind would need a change to the evaluation spec, for the owner to decide. Roman numerals and figured bass entered as chord symbols are not read as chords.
- **Words** reach 68 percent recall on the development set (91 on the regression set).
- **Words in odd places**: text entered as a lyric but used for something else (an attribution), and words whose engraver sets them far from the note they belong to, are read as what they look like.
- **Lyrics over a staff that is not the top one** of a system are taken as lyrics of the staff above it, so they find no notes to go to.
- **Outlined text** on Type B pages (text drawn as shapes) is not read: there is no text layer.
- **Engraver-input pairs** carry markings the engraver did not draw, or drew elsewhere; their words precision is lower for that reason (LilyPond and Verovio set some words that MuseScore keeps as other elements, such as tempo text with a metronome mark).
