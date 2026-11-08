# Phase 3 Plan: Braille and Reporting Quality

**Status: parked by the owner, 8 November 2026,** until after Phase 4. The draft below has not been agreed; its questions for the owner are still open. Drafted from the solution design (sections 2.7, 4.7 and 6), the requirements (OUT-2 to OUT-4, OI-1), `docs/notes/musicxml-spec.md` (the braille placeholder of Stage 1.6), `docs/notes/confidence-spec.md` (the report), and the Phase 1 and Phase 2 reports. Plain headings and lists only. Model suggestions follow the earlier plans: Opus for design and judgement, Sonnet for implementation, escalate to Opus after two or three failed attempts.

## Goal and gate

Goal: braille music that braille-reading musicians judge fit to play from (OUT-2, quality), in the code, formatting and file format chosen under OI-1, made reliably from every file the reader converts; and a confidence report a blind musician can act on without help (OUT-3, OUT-4). The solution design estimates 3 to 6 weeks of effort, but much of the phase waits on people: the community's answer to OI-1 and the reviewers' judgements. Calendar time will be longer than effort.

The solution design gives Phase 3 no gate. **Proposed wording,** for the owner to agree in Stage 3.0:

1. **OI-1 is closed.** The default braille code, formatting and file format are recorded in the requirements and the design, and the other codes and formats the adapter offers are listed.
2. **The translator is chosen by the reviewers.** At least three braille-reading musicians have compared the candidate translators on the review sample, and the choice to adapt one or build a dedicated one is recorded with their reasons.
3. **Braille is made for every file.** On the ground-truth MusicXML of the development set, every file gives braille, and everything in the score that the braille leaves out is listed in the report (nothing is dropped silently).
4. **The machine check agrees.** Reading the braille back into notes gives at least 99.5 percent of the MusicXML's notes (pitch, duration, bar) on the ground-truth MusicXML of the development set.
5. **The reviewers accept the result.** On the review sample made with the final translator, the reviewers find no error in notes, rhythm or structure that the translator introduced, and their formatting points are settled (fixed, or recorded as a known limit with their agreement).
6. **The owner agrees the report wording.**

Why these choices:

- **Ground-truth MusicXML as the input for the braille figures.** Braille made from the reader's output carries the reader's errors. Feeding the corpus's own MusicXML splits translator faults from recognition faults, as the raster penalty split image faults from assembly faults in Phase 2. Braille from the reader's output is measured too (Stage 3.6), and should follow ACC-1 and ACC-2.
- **A machine check as well as people.** No one on the core team reads braille, and reviewers' time is scarce. A back-translator that reads braille music into notes lets every change be checked on thousands of files, so reviewers spend their time on what software cannot judge: readability, formatting and the conventions a player expects. This is the "verify without sight" principle of the design (section 1, point 4) applied to braille.
- **99.5 percent, not 100.** Some things have no settled braille form in a given code, or the back-translator may not cover them at first. The figure is a floor for the gate; the reviewers' finding of no translator-made errors in the sample is the real test.
- **At least three reviewers.** Braille readers differ by country, by training and by instrument, and the owner cannot settle a disagreement by reading the braille. Three gives a majority.

## Where things stand

- **Braille today** is the Stage 1.6 placeholder: `src/omr/braille.py`, an adapter with one translator (music21's braille module) and two formats (Braille ASCII `.brf`, and Unicode braille text), 40-cell lines, no pagination.
  - It translates 1,747 of the 1,778 development files. music21 fails inside its own code on the rest.
  - It leaves out start repeats (1,948 times on the development set), rests of unusual lengths (798), rehearsal marks (399), Fine, D.C., D.S. and segno, some fingerings and chords, and drops characters from text in 839 files. Everything left out is listed in the report.
  - 186 files lose the bar-over-bar layout (music21 writes the parts one after another), and 33 parts are left out.
- **OI-1 is open.** The owner has been asking the MuseScore community since Phase 0. The answer decides the code (for example BANA's Music Braille Code 2015 in North America, the UK's RNIB and UKAAF practice, or the international manual), the formatting (bar over bar, section by section, line by line, open score) and the file format (BRF and its character table, Unicode braille, page size).
- **The confidence report** (Stage 1.5, extended in Phase 2) gives a summary line and one line per flagged part, staff and bar, with page, system, bar, part, beat and reasons in words. Its wording was written by Claude and has not yet been reviewed by the owner as a user. On page images it is long: 10.6 to 11.5 percent of bars are flagged, so a 100-bar piece for piano and voice can carry 30 or more flags.
- **The owner is the first user of the report.** A blind musician using NVDA is exactly who it is for, so the owner can judge its wording directly. The braille needs others.

## Rules for the whole phase

- **An estimate before the bulk of each stage,** as in Phase 2: Claude sessions, long runs, laptop use, disk. Recorded in `phase3-progress.md` with actuals at the end of the stage.
- **People's time is the scarce thing.** Every request to the community or the reviewers is drafted by Claude in plain text, short, with one clear question or task, for the owner to send. Material for reviewers is prepared fully before it is sent, so a reviewer is never asked twice for the same thing.
- **Only public-domain or freely licensed scores go to reviewers** (C-4). The development set's PDMX and OpenScore scores qualify; MuseScore.com uploads and the commercial files do not.
- **Reviewers' names stay out of the repository** unless they ask to be credited. Their comments are collated in `docs/notes/braille-review.md` by reviewer letter (A, B, C), with the originals kept on the corpus drive.
- **Braille changes never change the MusicXML or the flags.** Every braille or report change is checked to leave `check_notes.py`, `check_flags.py` and the harness figures byte-identical, as in the Phase 2 code review.
- **Translators that cannot run from the command line** may be compared, but cannot be in the workflow or the product (AX-1, `docs/conventions.md`).

## Stage 3.0: Decisions, the panel and the survey

**Model: Opus.**

- **OI-1.** Ask the owner what the MuseScore community has said so far. Then, with the owner, turn the open question into a short list of concrete choices for the community and the reviewers, each with a recommended default:
  - the music code (North American, UK, international, or another national code), and whether the default should follow the user's locale;
  - the formatting of each texture: single line, keyboard (bar over bar or section by section), voice and piano, choir (open score or short score), ensemble (score, or one braille part per instrument);
  - the literary braille code for titles, words and lyrics (for example Unified English Braille grade 1 or grade 2 for English, and what to do for other languages);
  - the file format: BRF and its character table, Unicode braille text, or both; line length and lines per page; braille and print page numbers; a title page;
  - what to include by default: lyrics, chord symbols, dynamics and hairpins, fingering, slurs, bar numbers.
  If the community has no answer yet, the phase still starts: Stages 3.1 and 3.5 do not need it, and the survey and the review sample can be prepared for the most likely code. The adapter keeps the code configurable (OUT-2), so the default can follow later.
- **The reviewer panel.** Claude drafts a short call for volunteers (what the project is, what a reviewer would do, how much time it takes, that it is free and open source) for the owner to post: the MuseScore forum and accessibility channels, and blind-musician networks the owner knows (for example RNIB music networks, NFB and the DAISY music braille community). Aim for three to five reviewers, ideally from more than one country and more than one instrument family (keyboard, voice or choir, a melody instrument).
- **The translator survey.** Install and try each candidate on the command line, on the regression set's ground-truth MusicXML. For each record: licence and whether it can be bundled, offline use, command line, platforms, the codes and formats it supports, its formatting options, how recently it was maintained, speed, failures, and what it leaves out. Candidates:
  - **music21's braille module** (BSD, already used). Based on a North American transcription manual; check which edition and how far it follows today's BANA code.
  - **FreeDots** (GPL-3.0, Java, already in the licence register). External process only.
  - **Sao Mai Braille Music Translator** (free, closed source, Windows). Cannot be bundled; check whether it has a command line at all.
  - **The OpenSheetMusicDisplay braille module** (JavaScript). Check its licence and whether it can run under Node from the command line.
  - **MuseScore 4's own braille output,** if it has one that its command line can reach (MuseScore 4.7.5 is installed). Check.
  - **liblouis** (LGPL) for the literary parts (titles, words, lyrics) in the chosen literary code, whatever does the music.
  - Anything else the community or the reviewers name, including the tools of the DAISY music braille work if they are public.
  Results go into `docs/notes/braille-survey.md`, the licence register and `docs/notes/tool-commands.md`.
- **Code manuals.** Find which braille music code manuals are free to download (BANA publishes its codes; check the UK and international ones) and keep them on the corpus drive. Claude's knowledge of the codes must be checked against them, not trusted.
- **Requirements.** Propose to the owner two additions to `requirements.md`, to be agreed or declined: a braille accuracy requirement in the ACC group matching gate item 4, and an output requirement for one braille part per instrument from an ensemble score, which ensemble players need.
- **Gate wording.** Ask the owner to agree the wording above, or change it.

Done when: the owner has answered the OI-1 question (or agreed to proceed with a provisional default), the call for reviewers has gone out, the survey is written with each candidate's licence entered, and the gate wording is agreed.

## Stage 3.1: The review sample and the machine checks

**Model: Opus for the back-translator design, Sonnet for the code.** Needs no OI-1 answer for the core of the music code, which the codes share.

- **The review sample.** Choose about 30 public-domain scores from the development set's ground truth, covering the textures and genres of REC-10 and the things braille finds hard. Short pieces or excerpts (one or two braille pages each), since reviewers' time is the limit. At least:
  - single melody lines (folk tune, hymn tune, a wind or string part);
  - voice and piano with lyrics, and with more than one verse;
  - piano solo, with two voices in a hand and with cross-staff notes;
  - choir in four parts, with lyrics;
  - a string quartet or small ensemble;
  - a lead sheet with chord symbols;
  - repeats, first and second endings, D.C., D.S., coda and segno;
  - tuplets, grace notes, ties across bars, multi-bar rests, key and time changes, clef changes, octave lines;
  - dynamics, hairpins, articulations, slurs, fermatas, ornaments, fingering.
  Record it in `docs/notes/braille-sample.md` with why each piece is there. The owner agrees the list.
- **The completeness check.** For every file, every musical element in the MusicXML is either in the braille or listed as left out. Built on the adapter's existing list of what the translator left out, made exact by comparing counts by kind (notes, rests, repeats, endings, navigation marks, dynamics, text, lyrics, chord symbols) between the MusicXML and the back-translation.
- **The back-translator.** A reader of braille music, `src/omr/braille_read.py`, that turns braille text back into the harness's events (part, bar, onset, duration, pitch), so `metrics.compare_scores` can compare it with the MusicXML exactly as it compares the reader's output with ground truth. It covers first what every code shares: note and rest values (resolving the shared cells for whole and sixteenth, half and thirty-second and so on from the time signature and bar fullness), octave marks and the rules for when they are needed, accidentals and key and time signatures, dots, bar lines, ties, chords written as intervals, in-accords for voices, and repeats. Then lyrics and other text, dynamics and markings, in the chosen code. Its figures are given by element, so a gap in the back-translator is not mistaken for a translator fault.
- **Format checks.** Line length, lines per page, page numbering, valid characters for the chosen table, no empty pages, title page present.
- **Trust in the back-translator.** If Claude writes the back-translator from the same understanding of the code as a translator fix, both can share a mistake. Guard against this by testing the back-translator on braille not made by this project: transcriptions from the code manual's own examples, and any freely available reference transcriptions the reviewers can point to.
- **`scripts/check_braille.py`**, a check in the style of `check_convert.py`: for a set, each file's translation, completeness, back-translated note agreement by element, format faults, and time, with a one-line summary.

Done when: the sample is chosen and agreed; the back-translator reads music21's output on the regression set, its agreement figures are recorded by element, and it passes on the manual's examples it covers; `check_braille.py` runs on the development set.

## Stage 3.2: The translator comparison

**Model: Sonnet for the runs and the packets, Opus for reading the results.** Needs the panel (Stage 3.0) and the sample (Stage 3.1).

- **Machine comparison.** Run every surveyed candidate that has a command line on the development set's ground-truth MusicXML: files translated, files failed, what each leaves out (by kind and count), back-translated agreement (where the back-translator covers the candidate's code), format faults, and time a file. Written to `docs/notes/braille-survey.md`.
- **Review packets.** For each sample piece and each candidate that gets through the machine comparison (at most three, to spare the reviewers), the braille file, labelled by letter so reviewers do not know which translator made it, plus a short description of the piece in words, its MIDI for listening, and its MusicXML for reviewers who use a braille music editor. One packet a reviewer, sent as a zip by email or a shared folder, whichever the reviewers prefer.
- **The questionnaire.** Plain text, short. For each piece and each version: errors found (bar and what is wrong), how easy it is to read, formatting faults, what a transcriber would do differently, and a rating from 1 to 5. Then overall: which version they would want to play from and why, and what matters most to them that none of the versions does.
- **Collating.** The owner forwards the replies; Claude collates them in `docs/notes/braille-review.md`: each error found, whether it is the translator's or the MusicXML's (the machine check and the ground truth tell which), and the formatting points, grouped and counted across reviewers.
- **While the reviewers read**, which may take weeks, Claude works on Stage 3.5, or on Phase 4 if the owner prefers.

Done when: at least three reviewers have returned the questionnaire and their comments are collated.

## Stage 3.3: Adapt or build

**Model: Opus, with the owner deciding.**

- Weigh the candidates on, in this order: what the reviewers said; the machine figures; coverage of what the corpus needs (repeats and navigation, several voices, keyboard and choral formats, lyrics, chord symbols); the chosen code; whether it can be bundled under AGPL and runs offline on Windows, Linux and macOS from the command line; and whether the project can fix its faults.
- The options:
  - **Adopt one translator as it is,** calling it as an external process where its licence requires, and send fixes upstream.
  - **Adapt one.** music21's module is the likely candidate if it does well enough: it is Python and BSD, already used, and its faults can be fixed in the project or upstream. The adapter's `_prepare` step already works round several of them.
  - **Build a dedicated translator** from the project's own score model. This avoids a round trip through MusicXML, and lets the braille carry the confidence flags directly, but it is the most work and needs the reviewers longest.
  - **Combine:** one translator for the music and liblouis for the literary text, or different translators for different textures if no one translator does all well.
- Claude writes the case for each in `docs/notes/braille-spec.md`, with a recommendation and a rough estimate in sessions for the implementation; the owner decides; the reviewers are told the outcome.

Done when: the decision is recorded in `braille-spec.md` with its reasons, and the implementation estimate is agreed.

## Stage 3.4: Implement the chosen code and formatting

**Model: Opus for every rule of the code, Sonnet for the code and tests.** The bulk of the phase. Its size depends on the decision in Stage 3.3.

- **Close the gaps the corpus shows,** worst first by count on the development set, each with a test and a back-translator case: start repeats and endings, D.C., D.S., Fine, coda and segno, rehearsal marks, rests and notes of unusual lengths, the characters dropped from text, the files that fail outright, and the parts that are left out.
- **Formats by texture,** as OI-1 decides: bar over bar or section by section for keyboard, open or short score for choir, one braille part per instrument for ensembles (a `--braille-part` option, if the owner agrees the requirement), with music line numbers or bar numbers as the code wants.
- **Text** in the chosen literary code: titles, composer and lyricist, words, lyrics with their verses and hyphens, chord symbols.
- **Page format:** line length, lines per page, braille and print page numbers, a title page, and transcriber's notes, all set in configuration with the OI-1 defaults. The command line gains the options needed (for example `--braille-code`, `--braille-lines`, `--braille-cells`), with the defaults shown in `omr convert --help`.
- **Confidence in the braille.** How a braille reader finds the flagged bars is a question for the reviewers in Stage 3.2: a transcriber's note listing them at the start, a mark in the music, or nothing in the braille and the braille page and line given in the report instead. Implement what they choose.
- **The work loop:** fix, `check_braille.py` on the regression set (and the sample), the back-translator figures and completeness, then the development set at the end of each session. The CI job on the regression set (Stage 3.6) catches regressions.
- **A second review round** on the sample made with the implemented translator, sent to the same reviewers with a list of what changed since their comments. Fix what they find; what is left is a known limit with their agreement.

Done when: gate items 3 and 4 are met on the development set's ground-truth MusicXML, and the second review round finds no translator-made errors in notes, rhythm or structure.

## Stage 3.5: The confidence report as a user reads it

**Model: Opus for the wording, Sonnet for the code.** Needs no OI-1 answer and no reviewers, so it can start at once.

- **The owner reads real reports.** Claude picks about ten reports from the gate runs (vector and image, short and long, few flags and many, a failed file) and the owner reads them with NVDA and says what is unclear, too long, or missing. Claude adds its own list of likely faults for the owner to agree or reject:
  - **Length.** Runs of flags on the same staff in neighbouring bars said once ("Bars 12 to 15, Violin: ...") rather than bar by bar; a short version of the report by default and the full one on request.
  - **Order.** Score order today. Perhaps by part, so a player reads their own part's flags together.
  - **Words.** Terms a musician would not know ("Engine 1", "Engine 2", "staff bar", "drawn again by Verovio", "self-check") put into plain musical language, keeping the detail the owner finds useful.
  - **Confidence.** Words (likely right, doubtful, probably wrong) instead of or beside numbers.
  - **What to do next.** How to find a flagged bar in MuseScore 4 with NVDA (its go-to-bar command), and, once Stage 3.4 settles it, on which braille page and line it falls.
  - **The summary.** Whether "61 high confidence, 3 flagged" says enough, or should give the share and the worst parts.
  - **Failed files.** Messages that say why and what to try (for example a scan with no staves found: a clearer or flatter image; that becomes Phase 4's work).
  - **The terminal messages** of `omr convert` held to the same standard.
- **Check that only the words change.** The flag file and `check_flags.py` figures stay identical; the report's tests are updated. `confidence-spec.md` is updated in place to describe the new report.
- **Two rounds** with the owner: a first rewrite on the sample reports, then the owner reads a fresh set from other files.

Done when: the owner agrees the wording (gate item 6), the flag figures are unchanged, and the tests pass.

## Stage 3.6: Braille from the reader's output, CI and the gate review

**Model: Opus.**

- **Braille from the reader's output.** The Phase 2 gate runs already hold the reader's MusicXML for the development set (vector, and images at 300 and 200 dpi), so no new reading is needed. Make braille from those files and from the ground truth, back-translate both, and report how many notes of the braille made from the reader's output differ from the braille made from the ground truth. This is the accuracy a braille reader actually gets, and should follow the note accuracy of ACC-1 and ACC-2. Report failures and omissions too.
- **CI.** Add `check_braille.py` on the regression set's ground-truth MusicXML to `.github/workflows/tests.yml`, with floors for files translated and back-translated agreement, and the chosen translator installed in the job (or Engine-1-style, the bundled translator only, if an external one cannot be installed on GitHub's runners).
- **Docs.** Close OI-1 in `requirements.md` and section 8 of the design; set the default code and format in OUT-2; update section 2.7, 3 and 4.7 of the design to the chosen translator; replace the braille section of `musicxml-spec.md` with a pointer to `braille-spec.md`; update the `omr convert` help and any README usage.
- **Gate review.** Write `docs/notes/phase3-report.md`: each gate item with its figure or finding, the reviewers' verdict in summary, the report changes, known limits carried forward, and the time the phase took against the estimate. Ask the owner for sign-off.

Done when: the gate is met as agreed and the report is signed off.

## Order and dependencies

1. Stage 3.0 first, but its people-facing parts (the OI-1 question and the call for reviewers) go out on day one, because the answers take longest.
2. Stage 3.5 can start at once and fill the waits. It needs only the owner.
3. Stage 3.1 alongside, once the survey has the candidates installed.
4. Stage 3.2 once the sample, the machine checks and at least three reviewers are in place.
5. Stage 3.3 once the reviewers' comments are collated.
6. Stage 3.4, with its second review round at the end.
7. Stage 3.6 last.

**Phase 3 and Phase 4 together.** On 6 November 2026 the owner wanted to move to correcting distorted images (Phase 4) next. Phase 3's Claude work is perhaps 15 to 25 sessions, but it sits between long waits for the community and the reviewers. One way to run both: send the OI-1 question and the call for reviewers now, do Stage 3.5 and the survey and Stage 3.1, then work on Phase 4 while the reviewers read, coming back to Stages 3.3 and 3.4 when their comments arrive. The owner chooses.

## Rough effort, for the Stage 3.0 estimate

These are first guesses, to be replaced by stage estimates as each starts.

- Stage 3.0: 1 to 2 Claude sessions, plus the owner's time with the community.
- Stage 3.1: 3 to 5 sessions (the back-translator is most of it).
- Stage 3.2: 1 to 2 sessions, then the reviewers' time (likely 2 to 4 weeks).
- Stage 3.3: 1 session.
- Stage 3.4: 4 to 12 sessions, depending on adapt or build, then a second review round.
- Stage 3.5: 2 to 3 sessions, with the owner reading reports between them.
- Stage 3.6: 1 to 2 sessions. Braille for the development set takes under a second a file on 3 workers, so each full run is minutes, not hours; the three sets of reader output from the Phase 2 gate runs together under an hour.
- Disk: small. Braille files are a few kilobytes each; review packets and manuals well under a gigabyte.
- No training and no GPU use is expected in this phase, so it can share the laptop with Phase 4 training runs.

## Risks specific to Phase 3

- **OI-1 may not be answered, or the answers may split by country.** The adapter keeps the code configurable; the default can follow the majority of the reviewers, with the others offered as options. The phase proceeds on a provisional default rather than waiting.
- **Reviewers may be hard to find or slow.** The call goes out on day one; material is short and complete; the machine checks screen everything first, so reviewers see only versions worth their time. If fewer than three come forward, the owner decides whether to proceed with fewer and record it.
- **Reviewers may disagree.** Points raised by one reviewer are recorded; changes follow the majority, or become options.
- **Claude's knowledge of the braille codes may be wrong in detail.** Every rule is checked against the published manual, and the back-translator is tested on transcriptions not made by the project.
- **The translators may be unmaintained or limited.** The survey records maintenance; adapting music21 in the project, or building a dedicated translator, remain open in Stage 3.3.
- **Recognition errors become braille errors.** Phase 3 does not change this; it makes the flagged bars findable in the braille and keeps the braille figures from the reader's output in view (Stage 3.6).
- **Licences.** Sao Mai cannot be bundled; FreeDots is GPL and runs only as an external process. A translator the project cannot ship can be compared but not be the default. Recorded in the licence register.
- **Scope.** Reading braille into MusicXML (the reverse direction) is not in scope, except as the back-translator used for checking. Braille for percussion, tablature and figured bass follows REC-9 and stays later.

## Questions for the owner before Stage 3.0

1. Where does the MuseScore community discussion on OI-1 stand, and is there a code you or they lean towards?
2. Do you know any braille-reading musicians who might review, or channels where the call should go?
3. Phase 3 first, or alongside Phase 4 as suggested above?
4. Do you agree the proposed gate wording, and the two proposed requirements (braille accuracy, one braille part per instrument)?
