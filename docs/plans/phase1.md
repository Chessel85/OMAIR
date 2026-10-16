# Phase 1 Plan (draft): Vector PDF to MusicXML

Version 0.2, 16 October 2026: Stages 1.8 (accuracy push) and 1.9 (gate review again) added after the first gate review. Drafted on 9 October 2026 from what Phase 0 showed. Gate wording agreed by the owner; the rest still needs review. Plain headings and lists only. Model suggestions follow the Phase 0 plan: Opus for design and judgement, Sonnet for implementation, escalate to Opus after two or three failed attempts.

## Goal and gate

Goal: ACC-1 on vector PDFs (at least 99 percent note accuracy, at least 95 percent of files structurally correct), with text (lyrics, words, chord symbols), the first confidence report, and a MusicXML writer. The solution design estimates 6 to 10 weeks.

Gate as the solution design words it: "ACC-1 is met on the vector corpus, including the CPDL Sibelius and Finale pairs." CPDL is blocked by Cloudflare and no Sibelius or Finale files are in hand. **Proposed wording:** "ACC-1 is met on the generated vector corpus (MuseScore 3 and 4, LilyPond, Verovio) and on the real MuseScore.com uploads, and the Sibelius and Finale output obtained in Stage 1.0 has been inspected and its result reported, with any shortfall listed as a known limit." The owner agreed this wording on 9 October 2026.

What Phase 0 showed that shapes this plan:

- Almost every page is Type A. No Type B was found. The vector path is the main path.
- The best baseline is 86.3 percent (Audiveris). All baselines lose most on rhythm and tuplets, text, unusual fonts and multi-staff systems.
- Only Emmentaler needs a mapping table so far.
- Only 18 to 32 percent of files are structurally correct for every tool, even with restated signatures ignored (spec decision 11).

## Stage 1.0: Decisions and open risks first

**Model: Opus for the spec change, Sonnet for the file collection.**

- Spec decision 11 on restated clefs, keys and time signatures (see `docs/notes/baselines.md`). Rescore the three baselines from saved outputs.
- Get commercial engraver PDFs: an IMSLP list chosen with the owner, or the owner's own files in `sources/other`. Run `run_survey.py inspect` and `report`. Record the share of Type B and legacy fonts. Calibrate the legacy-font threshold on them. Test a Type 3 font.
- Replace the position-based "probably music" font test with a glyph-shape test against letters.
- Add a CI job on the regression set for the real recogniser, once it exists.

Done when: the spec decision is recorded, the survey has some commercial engraver files (or the owner has said none can be had), and the font test no longer warns on the known text fonts.

## Stage 1.1: Glyph extraction and font mapping

**Model: Sonnet to implement, Opus to review.** Builds on `src/omr/pdf/evidence.py`.

- Map glyphs to symbols through SMuFL code points first (MScore, Leland, Bravura, Petaluma, MuseJazz, Gootville, Finale SMuFL fonts).
- Add the Emmentaler table (one table for its size variants).
- Add tables for the legacy fonts Stage 1.0 found: Opus and Helsinki (Sibelius) and Maestro (Finale), each with its companion fonts (OpusSpecial, HelsinkiSpecial, OpusText and the like). Petrucci and November did not occur, so they wait.
- Tell which legacy font a renamed font is (printer drivers rename them, for example "TTE26B52B8t00") from its glyph shapes, so the right table can be used.
- Handle outlined glyphs (Type B) by shape matching. Stage 1.0 found them in 4 of 20 commercial files, from all three programs. Where the route is known, the score was printed to PDF, not exported.

Done when: every symbol class in the corpus is mapped, and a count of unmapped glyphs is reported per file.

## Stage 1.2: Staves, systems and parts

**Model: Opus for the design, Sonnet for the code.**

- Staves from staff lines (the inspector's grouping), then systems, then parts, including systems of three or more staves and parts that continue across pages. These are where homr fails.
- Handle repeats, pickup bars, multi-bar rests, and staves that appear and disappear.
- Attach every symbol to a staff and a staff step.

Done when: structure (parts, bars, clefs, keys, times) is right on the regression set under the Stage 1.0 rule.

## Stage 1.3: Notation assembly

**Model: Opus for the rhythm and voice logic, Sonnet for the rest.**

- Pitch (clef, key, accidentals, octave clefs, a main error source for the baselines), duration (flags, beams, dots, tuplets), ties, slurs, voices and chords.
- Bar arithmetic (ACC-5) to repair rhythm: each voice must fill its bar, which catches most missed or invented tuplets.
- Grace notes, cross-staff notes and arpeggios.

Done when: note accuracy is at least 95 percent on the development set, with tuplet and onset errors reported separately as they were for Audiveris.

## Stage 1.4: Text and markings

**Model: Sonnet, Opus to review the categories.**

- Sort text into title, composer, tempo, expression, lyric, chord symbol, instrument name and rehearsal mark from the text layer. The baselines score 0 percent here, so the whole gain is the project's.
- Dynamics and hairpins to at least 90 percent (ACC-6; Audiveris reaches 74 percent). Articulations, fermatas, ornaments, fingering.
- Lyrics aligned to notes, with hyphens and melismas.

Done when: lyrics, words and chord symbols are found on the regression set, and ACC-6 is measured.

## Stage 1.5: Musical rules layer and confidence report

**Model: Opus.**

- The first musical-rules layer: bar fullness, key and accidental consistency, instrument range, ties and slurs matching.
- The first confidence report, in the format the harness already reads, so that ACC-4 is measured. Flag bars by staff.

Done when: the harness measures ACC-4 on the vector corpus, and a first target is proposed (OI-3).

## Stage 1.6: MusicXML writer and basic braille

**Model: Sonnet.**

- The MusicXML writer, round-tripped through the harness.
- Basic braille through the music21 adapter. This is a placeholder until OI-1 is answered.
- Report output in plain text with locations in words (AX-2).

Done when: `omr convert` runs from PDF to MusicXML and braille, with a one-line summary and a clear exit status.

## Stage 1.7: Speed and the gate review

**Model: Opus.**

- Measure seconds a page on the CPU against OP-3 (10 seconds). Profile if it is over.
- Run `omr evaluate` on the development and regression sets and on the real uploads. Compare with the baselines in `baselines.md`.
- Write the Phase 1 report and ask the owner for sign-off.

Done when: the gate (as agreed) is met and the report is signed off.

Outcome (16 October 2026): runs done, gate not met. Speed is 0.6 seconds a page. Notes are 96.7 percent and structure 77.8 percent on the development set. See `docs/notes/phase1-report.md`. The owner chose to keep working (Stage 1.8) and to review the gate again afterwards (Stage 1.9).

## Stage 1.8: Accuracy push to ACC-1

**Model: Opus for triage, design and every rule that decides rhythm, voices or structure; Sonnet for implementation, tests and runs.** This is a long stage over several sessions. Record progress in `phase1-progress.md` at the end of each session.

Aim: meet ACC-1 outright on every engraver, not on average. That means at least 99 percent note accuracy and at least 95 percent of files structurally correct on the development set, the regression set and the real uploads, for LilyPond and Verovio as well as MuseScore. It also means the commercial files read as well as the generated ones.

### Starting point

- **Development set:** notes 96.7 percent and structure 77.8 percent. MuseScore is at 98.1 percent notes and 84 to 85 percent structure, LilyPond at 94.1 and 55.4, Verovio at 93.1 and 71.0.
- **Regression set:** notes 98.4 percent, structure 80.5 percent.
- **Real uploads:** notes 93.0 percent (96.2 without the faulty pair), structure 65.0 percent.
- **Errors are concentrated.** The worst 100 of 1,778 files hold 70 percent of the note errors. 60 percent of all errors happen in an engraving where another engraving of the same score was read more accurately; LilyPond and Verovio account for about 23,000 of those.
- **Structure failures are often near misses.** 195 of the 395 failing files have only one or two mismatches. 207 fail on one kind only: clef 48, bar count 41, repeat 30, ending 28, key 17, navigation 11, parts 10, time 9, other 13.
- **A lead to check first:** several of the worst files have nearly equal counts of missing and extra notes (for example 568 and 568). That pattern suggests whole bars or voices placed out of line, probably by a bar-count or staff-matching fault, rather than misread notes. If so, one structure fix could repair hundreds of notes.
- **Tools:** `scripts/analyse_errors.py RESULTS.json` (concentration, engraver gap, mismatch kinds, near misses, worst files). The last full analysis is `evaluations/errors-development.txt` on the corpus drive. The gate runs are `scripts/run_phase1_gate.sh`, with results in `evaluations/gate-*`.

### Rules for the whole stage

- **Hold-out set.** A rule-based reader can still overfit to the files it was tuned on. Before any fix, ask the owner to agree a sealed check set: about 100 scores drawn by seed from the training pool and exported by all six jobs, the same way as the development set (`scripts/build_corpus.py`; the rules are in `corpus-sampling.md`). Those scores then leave the training pool. Score the check set only at milestones and at the gate, never to diagnose a fault. Report it beside the development figures. If the owner declines, split the development scores in two by seed instead: diagnose on one half and report both halves.
- **Every fix needs a test.** Add a unit test or a regression pair that fails before the fix. Keep `check_regression.py`, `check_notes.py`, `check_markings.py`, `check_flags.py` and `check_convert.py` passing. Raise the CI floors (`--min-accuracy`, `--min-acc6`, `--min-recall`) as the figures rise, so no gain is lost.
- **Fast loops, full runs at milestones.** Use `omr evaluate` filters (`--engraver`, `--limit`) or `check_notes.py` and `check_structure.py` on the affected files for each change. Run the full development set (about 45 minutes on 3 workers) after each workstream. Any drop on another engraver or another error kind must be explained before going on.
- **Reference faults are the owner's call.** Where the reference MusicXML is wrong or cannot be matched from the page, do not bend the reader to it. Write the case up with examples and propose a fix to the harness, the spec or the pairs. Examples: missing clef changes in PDMX, navigation stored as plain words, chord kinds without text, a part hidden in the PDF. Do not change `evaluation-spec.md` until the owner agrees. Report figures both with and without such pairs until then.
- **Speed must stay under 2 seconds a page** on the timing set, one file at a time.

### Workstream A: triage (first, Opus)

- Classify every error in the worst 100 development files, and in every structure failure with one or two mismatches, as one of: a reader fault, a fault in the reference file, or information the PDF does not hold. Group the reader faults by cause, with counts of notes and files affected.
- Check the lead above (equal missing and extra counts) first.
- Write the result in `docs/notes/error-triage.md`, ranked by notes and files a fix would recover. That ranking sets the order of Workstreams B to E. Each cause should name the code it touches (`layout.py`, `structure.py`, `notation.py`, `markings.py`, `rules.py`, `musicxml.py`).
- Settle the real-world clef artefact: compare the printed clefs with the PDMX MusicXML in all 7 files. Propose the fix to the owner if PDMX is at fault.

### Workstream B: structure (Opus to design, Sonnet to build)

Target: at least 95 percent structurally correct on every engraver.

- **Bar counts:** multi-bar rests, mid-bar barlines, invisible barlines (from the bar arithmetic and the other staves), pickup and split bars, and LilyPond bar counts. Use bar arithmetic to merge or split bars where the barlines disagree with the music.
- **Clefs and keys:** Verovio clefs and keys, clef changes inside a bar, courtesy clefs and keys at system ends, and key changes to C.
- **Repeats, endings and navigation:** endings across systems, repeat counts in words ("3 times"), segno, coda, Fine and D.C. as glyphs or words. Where the reference stores them as plain words, follow the reference-fault rule.
- **Parts:** one-line percussion staves, six-line tablature staves, hidden staves in large scores, and staves matched to parts in more than one way.

### Workstream C: notes (Opus for rhythm and voices, Sonnet for the rest)

Target: at least 99 percent on every engraver.

- **Close the engraver gap first.** For each LilyPond and Verovio file that reads worse than the same score's MuseScore engraving, find the drawing habit the reader mishandles: octave marks, beams, stems, rests, tuplet brackets, or system and staff joins. These are the 23,000 errors that the same music proves readable.
- **Tuplets:** cross-staff tuplets, nested tuplets, unprinted tuplets by bar arithmetic, and tuplet numbers that are hidden or far from their notes.
- **Voices:** three or more voices on a staff, voices that start and stop mid-bar, and rests shared between voices.
- **The rest:** stems hidden with no beam, tremolos (notes and the marking), cross-staff beams and notes, a bare 8 between two staves, and grace notes before rests.
- Grow the confidence rules alongside, so that ACC-4 stays at least 90 percent with at most 10 percent of bars flagged as the errors shrink.

### Workstream D: commercial files

Target: on direct exports, at least 90 percent of bars unflagged and no wrong part counts. On printed-to-PDF files, at least 80 percent of bars unflagged.

- **Find out why printed-to-PDF files fail:** the Ave verum read as 20 parts, The Planets with no unflagged bars, and the low share on the driver-printed Sibelius and Finale files. Possible causes are renamed fonts, outlines, split text runs and different line drawing; triage first.
- **Make ground truth for a few files.** Unflagged bars are a rough guide, not an accuracy figure. Ask the owner whether ground truth can be made for 3 to 5 commercial files, for example by checking our MusicXML against the page bar by bar in MuseScore. If yes, add them to the check set as commercial pairs.
- **More files:** if the owner can get more Sibelius, Finale or Dorico PDFs (another IMSLP list, or the owner's own), add them to the survey and this workstream.

### Workstream E: markings and the MusicXML writer (Sonnet, after B and C)

These are not part of ACC-1, but they shape the output a braille reader gets.

- **Markings known limits:** slurs across two staves, two slurs from one note, outlined text on Type B pages, words (67.8 percent recall on exact pairs), tremolo and wavy-line ornaments (0 percent), breath marks and caesuras.
- **Writer known limits:** beams, part groups, instruments and transposition, barline styles, and the four-voice limit.

### Done when

On both the development set and the sealed check set, every engraver has at least 99 percent note accuracy and at least 95 percent structural correctness. The regression set meets the same. The real uploads meet it, excluding pairs the owner agrees are faulty. ACC-6 and ACC-4 still meet their targets, speed is under 2 seconds a page, and the commercial targets above are met or each shortfall is explained. Where a target is not reachable because the PDF does not hold the information, the triage note says so with counts, and the owner agrees the limit.

## Stage 1.9: Gate review again

**Model: Opus.**

- Run `scripts/run_phase1_gate.sh`, adding the check set and the commercial files, and run `scripts/analyse_errors.py` on the results.
- Update `docs/notes/phase1-report.md` to the new position, with the comparison against the baselines, and ask the owner for sign-off.

Done when: the gate (as agreed) is met and the report is signed off.

## Order and dependencies

1. Stage 1.0 first. The other stages need its spec decision.
2. Stages 1.1 and 1.2 together, then 1.3.
3. Stage 1.4 can start once 1.2 gives staves and positions.
4. Stage 1.5 after 1.3. Stage 1.6 can start early with fake data.
5. Stage 1.7, then Stage 1.8 (Workstream A first; B and C in the order the triage sets; D alongside; E last), then Stage 1.9.

## Risks specific to Phase 1

- **The 99 percent target is far from any baseline.** Reading the vector PDF should remove most picture-reading errors, but this is not yet shown. Measure note accuracy after Stage 1.3 and escalate early if it is under 95 percent.
- **Commercial engraver output could break the assumptions** (outlined glyphs, legacy fonts). Stage 1.0 measures this first.
- **Structural correctness at 95 percent depends on the Stage 1.0 rule.**
- **Phase 2 items that do not block Phase 1:** the render-scale test, the key-value cache and INT8 inference, and the check of the starting weights' architecture, all listed in `docs/notes/training-benchmark.md`.
