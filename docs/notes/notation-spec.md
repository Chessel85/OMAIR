# Notation assembly (Phase 1, Stage 1.3)

How the notes and rests of a score are read from a vector PDF: pitch, duration, onset, voice, ties, grace notes and arpeggios. It works from the symbols of Stage 1.1 (`symbol-spec.md`), the staves, systems and bars of Stage 1.2 (`layout-spec.md`), and the page's stems, beams and curves. It is the same for every engraver and for Type A and Type B pages.

- Code: `src/omr/pdf/notation.py`, called by `omr.pdf.structure.read_pdf(path, notes=True)`.
- Check: `scripts/check_notes.py`. It reads each PDF and compares the result with the ground truth through the harness's own comparison (`omr.evaluate.metrics.compare_scores`), so the figures are those `omr evaluate` would give. No MusicXML is written yet (that is Stage 1.6).

## Primitives

- **Noteheads** are the symbols named `notehead...` (and `noteShape...`). Each has a staff and a staff step from Stage 1.2, with one correction: a notehead beyond the staff (below step -1 or above step 9) belongs to the staff whose ledger lines reach it. A high note above a lower staff can be nearer the staff above, and only its ledger lines tell. A notehead more than a staff space and a half clear of the staff with no ledger lines (a metronome mark drawn with a notehead) is not a note.
- **Small noteheads** (grace and cue notes): a font glyph whose size is under 85 percent of the four staff spaces of a full-size music font. An outlined notehead has no font size, so its ink height is compared with the usual height of noteheads of the same shape on the page (black and half noteheads differ in height in some fonts).
- **Stems** are vertical lines (stroked, or thin filled rectangles), no wider than 0.3 staff spaces and at least one staff space long, not at a barline, with a notehead touching them: the line at the notehead's right edge (stem up) or left edge (stem down), within 0.3 staff spaces. Every notehead touching the line along its length joins the stem, so a stem and its noteheads are a chord. A stem needs a free end at least 0.8 staff spaces beyond its noteheads; the direction is the end that reaches further.
- **Noteheads on two stems**: two identical noteheads drawn one on another (a unison in two voices) go to different stems. A single notehead at the end of a stem up and of a stem down, on the usual side of each (left of a stem up, right of a stem down), is shared by both voices. Otherwise a notehead keeps the stem it ends.
- **Beams** are filled four-sided shapes with upright ends (level beams are rectangles), 0.25 to 0.9 staff spaces thick and at least 0.6 staff spaces long, and stroked lines that thick. A beam counts for a stem when it crosses the stem away from the noteheads, and it must end at a stem at one end at least: tremolo strokes float between or across stems and are not beams. Two shapes at one height on a stem are one beam.
- **Hidden stems**: where a beam ends at a stemless notehead (at its right edge above it, or its left edge below it), the stem is taken as hidden and the notehead joins the beam. Where the notehead already has a stem the other way and no line at all is drawn at the beam's end, it is a unison of two voices drawn once, and the beamed note is a second note on that notehead.
- **Flags** are the `flag...` glyphs at a stem's free end.
- **Augmentation dots** are dots right of a notehead or rest (up to three staff spaces), level with a notehead (within 0.65 staff spaces: a note on a line has its dot in the space above or below). Dots by a repeat barline are repeat dots. Each column of dots is one dot.
- **Rests** are the `rest...` glyphs. A rest whose ink is centred 1.5 staff spaces or more above or below the middle line belongs to the upper or lower voice.
- **Curves** (ties and slurs) are shapes drawn with curves, at least 0.8 staff spaces wide and flat. Only a curve at least 1.5 staff spaces wide whose two ends are level can be a tie; the others are slurs (Stage 1.4, `markings-spec.md`).
- **Thin lines** (tuplet brackets, the arms of hairpins) and **dashed lines** (octave marks) are stroked lines, level or sloping, with or without a dash pattern. Sloping lines are kept up to 100 staff spaces long (a long hairpin), level ones up to 30.

## Duration

- A chord's notated value: halved once for each beam or flag on its stem. Beams and flags decide even where the notehead is open (a beamed sixteenth drawn with a half notehead). A stem with neither takes the notehead's value (black a quarter, half, whole, double whole).
- Dots lengthen it (one dot by half, two by three quarters).
- **Tuplets.** A tuplet number is a `tuplet` digit glyph, or italic digits in the text layer (upright digits are fingering, string numbers and the like), possibly "3:2". Its events are those under its bracket (thin lines either side of the number, ending just before and starting just after it), on the staff nearest the number, or else the beam group nearest the number (within three staff spaces of the number's ink). A tuplet needs two events. The ratio is the one printed ("3:2"), or for a number alone: the power of two below it (3 in the time of 2; 5, 6 or 7 in the time of 4; 9 in the time of 8), and for a power of two three quarters of it (2 in the time of 3, 4 in the time of 3).
- **Whole-bar rests**: a whole rest alone on its staff in a bar lasts the whole bar.
- **Grace notes**: small chords followed closely by a full-size note or rest on their staff (within four staff spaces, plus 2.5 for each grace note between). They take the onset of that note and are numbered in order before it. Small chords with nothing full-size after them are **cue notes**, which keep their own rhythm.

## Onset and voices

The notes and rests of one staff in one bar are read together.

- **Columns.** Events that stand one above the other start together. Two events are in one column if they are within 0.6 staff spaces, or if they have opposite stem directions and are within 1.4 staff spaces (a voice set aside by a collision), or within 1.8 staff spaces with their noteheads touching as engravers set a collision: a unison with the stem up on the left, or a second with the upper note, stem up, on the right.
- **Onsets.** Columns start in order, each at the end of some event before it. When every voice runs on without a gap, the next column starts at the earliest end among the events still sounding, and that rule alone is exact. A voice can stop early or start late (the engraver hides its rests), and a note can be missed, so the onsets are chosen by a small search over the columns. A choice costs:
  - 1 for each event whose end has no column starting there before the end of the bar (a voice that stops early);
  - 1 for a column that starts where no event ends (a note missed, or a voice that starts late);
  - 5 for a column at or after the end of the bar (by the time signature of the staff's own part: parts can have different time signatures);
  - 0.5 for a column that continues only events of the other stem direction, which keeps two voices apart between otherwise equal readings.
  The cheapest reading is kept; among equals, the earliest. Cost 0 means every event ends where another starts or at the end of the bar.
- **Other staves.** A staff whose reading costs more than 0 is read again with the columns of the other staves of the bar that cost 0 as a reference: a column at the same place (within 0.5 staff spaces) should start at the same time (2 if it does not). This places a voice whose opening rests are hidden.
- **Voices** are chains: each event continues a voice that ends where it starts, preferring the same stem direction. Voices are numbered from 1 on the first staff of a part and from 5 on the second, as MuseScore does; the harness compares voice groupings, not numbers.

## Bar arithmetic (ACC-5)

- **Hidden tuplets.** When a staff's bar does not add up (cost above 0), beam groups of 3, 5, 6, 7, 9, 10 or 12 notes of one value, with no tuplet number, are read as tuplets (3 in the time of 2, 6 in the time of 4, and so on). The reading is kept if the bar then adds up better.
- **Unfilled bars** (`unfilled_bars`): each voice whose notes and rests do not reach the end of the bar, or run past it, is listed. A short first bar (a pickup), two short bars side by side that make one (a bar split at a repeat), and a voice that fills only part of a bar whose other voices fill it (hidden rests) are not listed. This is the bar-fullness rule of the confidence report (`confidence-spec.md`). `check_notes.py` scores it alone as a flag file. The reader also notes its doubts about rhythm, staves that disagree in time, unprinted tuplets, stray symbols and octave signs as it reads; they are described in `confidence-spec.md`.

## Pitch

- The **clef** in force is the last clef on the staff before the note, or the last of the staff in the system before; a small 8 or 15 at a LilyPond clef is an octave clef (as in Stage 1.2).
- The **key** is the part's key signature in force at the bar (Stage 1.2).
- **Accidentals** (`accidental...` glyphs other than key signatures) belong to the notehead on their step just to their right (up to 4.5 staff spaces, so that a chord's accidentals can stand in columns). An accidental holds for later notes on that step and octave on that staff to the end of the bar.
- **Ties**: a curve from one notehead to the next on the same staff step. A tied note with no accidental keeps the alteration of the note it is tied from, also across a barline and across a system break (a tie that runs to the end of a system continues on the first note of the same pitch in the next). Ties also give the notes' tie start and stop.
- **Octave marks** (8va, 8vb, 15ma): a `ottava`, `quindicesima` or `ventiduesima` glyph, or such text, with a dashed line starting just after it. The notes of the nearest staff from the mark to the end of the line (or of the line's continuation) are written an octave (or two) away from the pitch they stand for, which the MusicXML pitch gives. A plain mark is "alta" above the staff and "bassa" below it.

## Other marks

- **Arpeggios**: a wavy line (a stack of `wiggleArpeggiato...` or `arpeggiato...` glyphs) whose left edge is up to 5 staff spaces left of a chord's noteheads (room for accidentals), beside them, gives every chord beside it the "arpeggiate" mark, if it stands beside two noteheads or more in all. One line can span chords of two voices or two staves. (The glyph is drawn turned, so its ink box from the font is not where the ink is; its left edge is.)
- **Clefs within a bar** get the onset of the first event after them (Stage 1.2 gave them a placeholder).
- Cross-staff notes: a notehead keeps the staff it is drawn on (as the harness reads MusicXML), and a chord across two staves belongs to the staff of most of its noteheads.

## Results

`scripts/check_notes.py` reads each PDF and scores it with the harness. Note accuracy is M / (T + E + C), as in the evaluation spec.

On the development set (1,778 pairs, 300 scores; report in `evaluations/notes-development.txt` on the corpus drive):

- All pairs: **96.7 percent**. The Stage 1.3 done condition (at least 95 percent) is met.
- Exact pairs (MuseScore 4): 98.1 percent over 600 files. Engraver-input pairs: 95.9 percent over 1,178 files.
- By engraver: MuseScore 3 98.2 and 98.1 percent (base and variant), MuseScore 4 98.1 and 98.1, LilyPond 94.1, Verovio 93.1.
- For comparison, the best baseline, Audiveris, scored 86.3 percent on a 355-pair sample of the same set (`baselines.md`).
- **Onset and tuplet errors**, reported separately as they were for Audiveris. Exact pairs: 8,792 errors, of which 8,039 wrong notes (onset differs in 5,951, duration only in 1,146, pitch only in 933), 396 missing and 355 extra. Tuplets: 1,060 notes read as tuplets that are not and 932 tuplet notes read as plain notes, 24.8 percent of the wrong notes (Audiveris: 13 percent of a much larger number). Engraver-input pairs: 37,725 errors, onset in 16,230 wrong notes, tuplets 17.5 percent of wrong notes.
- **Bar arithmetic as flags.** Flagging each voice that does not fill its bar marks 1.6 percent of bars on exact pairs; those bars hold 63.1 percent of the note errors, and 57.7 percent of them have an error. On engraver-input pairs: 2.5 percent of bars, 44.8 percent of errors, 63.5 percent precision. This is a first measure towards ACC-4 (Stage 1.5).
- Most of what is left on LilyPond and Verovio comes with a structure mismatch (bars or parts that differ from the reference, `layout-spec.md`). Where the bars line up, LilyPond reads 97.4 percent and Verovio 94.6 percent (measured before the system-joining fix below).

On the regression set (256 pairs): 98.4 percent overall; exact pairs 99.2 percent, engraver-input pairs 97.9 percent (MuseScore 3 99.5, MuseScore 4 99.2, Verovio 98.7, LilyPond 93.7, where some LilyPond PDFs leave out beams the reference has). CI runs `check_notes.py --min-accuracy 98.0` on it.

A Stage 1.2 fix came out of this work: a vertical line at the start of a system now joins all the staves it crosses, not only those within four staff spaces of its top. Verovio and LilyPond draw one such line for a whole large system, and 8-part scores had been read as one or two staves per system. This raised LilyPond from 69.6 to 94.1 percent and Verovio from 78.5 to 93.1 percent in note accuracy.

## Known limits

- **Cross-staff tuplets.** A triplet whose notes are split between two staves (piano arpeggios) is not always found.
- **Several voices with the same stem direction** (three voices on a staff) can get wrong onsets where the voices start and stop mid-bar; the search keeps the readings consistent but cannot always tell which voice a note continues.
- **Stems that are not drawn** are found only where a beam ends at the notehead. A hidden-stem note with a flag, or with no beam, is read as a quarter note.
- **A whole staff in cue-size notes** (an ossia or a reduced part) is read with its rhythm, but grace notes inside it are not told apart.
- **Octave marks** are read from a mark and its dashed line. LilyPond's lines, drawn as separate short strokes, and Verovio's outlined marks are not read yet.
- **Tremolos** are not read: two-note tremolo strokes are left out (the notes keep their written value, as in MusicXML), single-note tremolo strokes are left out too.
- **Bars split by a mid-bar barline, or joined by an invisible one** (Stage 1.2 limits) are flagged by bar arithmetic but not merged or split; the harness's bar alignment absorbs one such join or split.
- **Multi-bar rests, slashes and percussion staves** are not read (Stage 1.2 limits).
- Slurs, articulations, dynamics and text are Stage 1.4 (`markings-spec.md`).
