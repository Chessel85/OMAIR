# MusicXML writer, basic braille and omr convert (Phase 1, Stage 1.6)

How the score read from a vector PDF is written as MusicXML (OUT-1) and as basic braille (OUT-2), and what `omr convert` does. The writer works on the `Score` that Stages 1.2 to 1.5 read (`layout-spec.md`, `notation-spec.md`, `markings-spec.md`, `confidence-spec.md`).

- Code: `src/omr/musicxml.py` (the writer, and the round-trip comparison), `src/omr/braille.py` (the braille adapter) and `src/omr/convert.py` (the command).
- Command: `omr convert FILE...` writes, for each PDF, `name.musicxml`, `name.brf`, `name-report.txt` (the confidence report) and `name-flags.json` (the flag file) beside the PDF, or in `--out FOLDER`. With one FILE, `--musicxml`, `--braille`, `--report` and `--flags` name each output; `--no-braille` leaves braille out; `--braille-format brf|unicode` chooses the braille file format.
- Harness: `omr evaluate --recogniser omr` runs `omr convert` on each pair and scores the MusicXML and flag file it writes.
- Check: `scripts/check_convert.py` (below). CI runs it on the regression set, with the MusicXML 4.0 schema fetched from the W3C repository.

## The writer's rule

The writer is the inverse of the harness's reader (`omr.evaluate.events`): reading the written file back must give the same notes, rests, markings, structure, bars and parts. So the harness scores the written file exactly as it scores the score in memory, and the figures of Stages 1.3 to 1.5 carry over to `omr evaluate` unchanged.

## What is written

- **Header.** The title as `work-title`, the composer and lyricist as `creator`, the rights, the software and date, and each title, subtitle, composer, lyricist and rights text as a `credit` with its `credit-type` and page.
- **Parts.** One `score-part` for each part, with its name, and the number of staves.
- **Bars.** One `measure` for each bar, numbered as the reader numbered it. A new system or page is a `print` element, so the harness reads the same page and system for each bar. Pages are counted from the first page with music, as MusicXML has no way to say that the music starts on page 2 (after a title page); the report's page numbers come from the PDF itself.
- **Divisions.** One value for the whole score, the least that makes every onset and length a whole number.
- **Clefs, keys and times.** In the bar where they change. A clef, key or time that restates the one in force is left out (spec decision 11), since engravers repeat them at each system and MuseScore would print them in the middle of a line. A clef inside a bar goes before the first note at its onset, in a voice of its staff that has a note there.
- **Repeats and endings.** Barlines with `repeat` and `ending` (start at the left barline; stop or discontinue at the right).
- **Notes and rests.** Each voice of each staff in turn, with `backup` between voices and `forward` over gaps. Notes with the same onset, length and value in a voice are one chord. Grace notes come before their note. Ties, cue size, time modification (from the notated value against the length read), dots, lyrics with their syllabic and extender, slurs, articulations, ornaments, fermatas, arpeggios, and technical marks. A fingering or plucking letter keeps its digit or letter (Stage 1.4 now keeps them in `Note.fingering`, which the harness does not compare).
- **Rest values.** The reader gives a rest's length only. It is written as the plain or dotted value of that length, or else the tuplet of the plain value just above it (a third of a quarter is a triplet eighth).
- **Accidentals.** Printed where the pitch differs from the key and from the accidentals earlier in the bar on the same line or space, as engravers print them. A note tied over prints none.
- **Tuplet brackets.** A run of notes with the same time modification gets `tuplet` start and stop marks when it fills a whole number of its smallest value (three triplet eighths, or a triplet quarter and eighth). An incomplete run (two triplet eighths, which only a misread bar has) keeps its time modification but no marks: with the marks, MuseScore moves the notes after it.
- **Directions.** Dynamics (`other-dynamics` for words such as "più p"), hairpins, words, tempo text, rehearsal marks, metronome marks (with a `sound` tempo in quarter notes a minute), segno and coda, and chord symbols as `harmony` (root, alteration, the MusicXML kind with the printed suffix as its text, and the bass). Each goes before the first note at or after its onset in a voice of its staff, with an `offset` where it falls inside a note.
- **Jumps.** D.C., D.S., Fine and To Coda go with the words the reader found for them, in their bar or the bar either side (words over a barline can be read into the next bar), as a `sound` on that direction. Only when no such words were found does the writer add the usual words ("Fine"), so that the jump shows.
- **At most four voices a staff.** MuseScore takes four voices a staff and does not open a file with more. The reader gives more only in garbled bars (6 staff bars in 14,150 on the regression set). There, each chord of an extra voice joins the first of the four voices it fits in without overlapping (or as more notes of a chord that starts and ends with it). A chord that fits nowhere is left out, and `omr convert` lists it in the report and warns.

## Braille

Braille is a placeholder until OI-1 is answered. `omr.braille` is an adapter with one translator (music21's braille module) and two file formats: Braille ASCII (`.brf`, the North American table; the default, chosen by the file name) and Unicode braille text (`--braille-format unicode`, or any other file name). Lines are 40 cells.

The adapter reads the written MusicXML with music21 and prepares it for music21's translator, which stops on some scores:

- Text (titles, words, lyrics, part names) keeps only the characters music21's braille alphabet has. Curly quotes and dashes become plain ones; other characters (`"`, `#`, `=`, `;`, `?`, symbols) are dropped, and listed.
- A fingering music21 cannot write is dropped (its own warning code fails on it), and counted.
- A voice that runs past its bar's end gets an empty voice of the same number in the next bar, since music21 ties the overflow into it.
- If music21 still cannot write the score whole, each part is written on its own (so keyboard music loses the bar-over-bar layout). A part with a bar too long for a 40-cell line is tried with 80 and then 160 cells, and a part music21 still cannot write is left out and named.

Everything music21 leaves out (it cannot write start repeats, rehearsal marks, Fine and D.C. marks, and some unusual lengths) is listed in words in the report, as "kind: details" ("rehearsal mark: A"), and `omr convert` warns.

## omr convert

For each file, `omr convert` prints what it read ("Read: 3 pages, 4 parts, 29 bars, 420 notes."), the confidence summary, any warning, and the outputs written, then ends with "Summary: N files converted, N failed, N warnings." (AX-2, `docs/conventions.md`). The report is the confidence report of Stage 1.5, with what was left out of the MusicXML or the braille added at the end, all with locations in words.

Exit status: 0 when every file is converted; 1 when a file could not be read (not a PDF, no staves found, as in a scan, or an unreadable file), an output could not be written, or no braille could be made (the MusicXML and report are still written); 2 when the command is used wrongly (for example `--musicxml` with two files). A warning (something left out) does not change the status.

## The check

`scripts/check_convert.py` reads each pair's PDF, writes the MusicXML and flag file, and checks:

- **Round trip**: the harness's reader gives back the same notes (with ties, marks, slurs, lyrics, syllables and fingering), rests, markings, structure, bars and parts (`musicxml.round_trip_differences`). Rehearsal and metronome marks, which the harness's reader does not read, are compared through `check_markings.truth_extras`. The words added for jumps, voice numbers in bars whose voices were merged, and notes left out there are allowed for.
- **Figures**: `metrics.compare` on the written file and flag file (as `omr evaluate` does) gives the same notes, structure, markings, marks on notes and flag figures as `metrics.compare_scores` on the score in memory (as `check_notes.py` does). The split of wrong notes by kind is left out: when two notes could match either of two, which pairing the harness keeps depends on the order the notes are listed in.
- **Schema**: the file is valid against the MusicXML 4.0 schema (`--schema`, default the corpus folder's `tools/musicxml-4.0-schema`, fetched from https://github.com/w3c/musicxml at tag v4.0, with its two imports pointed at the local copies).
- **Braille** (`--braille`): whether music21 translates the file, and what it leaves out, by kind. A file music21 cannot translate is listed but does not fail the check.

## Results

**Regression set** (256 pairs): every pair passes the round trip, the figures and the schema. 8 notes and rests in 3 files are left out to keep four voices a staff (all in garbled bars; none was a right note). Writing takes about 0.06 seconds a file (reading the PDF takes 1.4). Braille: 255 of 256 files translated, about 0.7 seconds a file; music21 fails inside its own code on every part of one LilyPond guitar file. Left out of the braille, by kind and count: start repeats 160, characters dropped from text in 112 files, rehearsal marks 44, Fine 18, D.C. al Fine 10, D.S. al Fine 5, segno 4, rests of unusual lengths 9, notes of unusual lengths 3, fingerings 5, chords 2; 22 files lost the bar-over-bar layout, 5 needed longer lines and 4 parts were left out.

**MuseScore 4** (4.7.5, `MuseScore4.exe -j` on all 256 written files, exporting MusicXML again): every file opens and exports with no error. Scored against the ground truth, MuseScore's export keeps 72,616 of the 72,640 right notes; the 24 it moves are in two files of one score, in bars the reader misread.

**Development set** (1,778 pairs, report in `evaluations/convert-development.txt` on the corpus drive): the first run found 60 pairs, in 20 scores, with round-trip differences, all of them small writer faults now fixed (lyric text and part names with spaces the harness trims, ties on cue-size notes) or limits of what MusicXML can say, which the comparison now allows for (a system number the reader skips, and the order of grace notes before a rest, which the harness counts from the last note). The 20 scores were checked again after the fixes, and every pair passes the round trip, the figures and the schema. 157 notes and rests in 29 files are left out for the four-voice limit. Writing takes about 0.16 seconds a file. Braille: 1,747 of 1,778 files translated; music21 leaves out start repeats 1,948 times, rests of unusual lengths 798, rehearsal marks 399, and drops characters from text in 839 files; 186 files lost the bar-over-bar layout and 33 parts were left out.

**The harness end to end:** `omr evaluate --set regression --set-root regression --recogniser omr --no-musicdiff` runs `omr convert` on each of the 256 pairs and scores the files it writes: note accuracy 98.4 percent (exact pairs 99.2), 80.5 percent of files structurally correct, ACC-6 99.4 percent, ACC-4 94.4 percent of note errors in flagged bars with 5.5 percent of bars flagged, no failures. These are the figures of Stages 1.3 to 1.5, so nothing is lost in writing.

## Known limits

- **No beams or stem directions.** The Score does not keep them, so the MusicXML has none and MuseScore beams by its own rules. Braille does not need them.
- **No layout.** No staff size, page size, positions of text or system breaks within a page other than `print`, and no credit positions (only justification). MuseScore lays the score out afresh.
- **No part groups, instruments or transposition.** Brackets and braces between parts, MIDI instruments and transposing instruments are not read yet.
- **Barlines** other than repeats are not written (double and final barlines).
- **Accidentals** are worked out, not copied: a cautionary accidental printed in the PDF is not written, and one the PDF leaves out by another convention is.
- **Chord symbols** keep only the bass letter, as the reader's words do.
- **Braille** is music21's basic translation: the code, formatting and file format wait for OI-1; no page numbers or pagination in the BRF; text characters outside music21's alphabet are dropped; the things listed above are left out.
- **Pickup bars** are not marked `implicit`.
