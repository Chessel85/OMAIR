# Phase 1 Plan (draft): Vector PDF to MusicXML

Version 0.1 draft, 9 October 2026, drafted from what Phase 0 showed. Needs the owner's review. Plain headings and lists only. Model suggestions follow the Phase 0 plan: Opus for design and judgement, Sonnet for implementation, escalate to Opus after two or three failed attempts.

## Goal and gate

Goal: ACC-1 on vector PDFs (at least 99 percent note accuracy, at least 95 percent of files structurally correct), with text (lyrics, words, chord symbols), the first confidence report, and a MusicXML writer. The solution design estimates 6 to 10 weeks.

Gate as the solution design words it: "ACC-1 is met on the vector corpus, including the CPDL Sibelius and Finale pairs." CPDL is blocked by Cloudflare and no Sibelius or Finale files are in hand. **Proposed wording:** "ACC-1 is met on the generated vector corpus (MuseScore 3 and 4, LilyPond, Verovio) and on the real MuseScore.com uploads, and the Sibelius and Finale output obtained in Stage 1.0 has been inspected and its result reported, with any shortfall listed as a known limit." The owner needs to agree this.

What Phase 0 showed that shapes this plan:

- Almost every page is Type A. No Type B was found. The vector path is the main path.
- The best baseline is 86.3 percent (Audiveris). All baselines lose most on rhythm and tuplets, text, unusual fonts and multi-staff systems.
- Only Emmentaler needs a mapping table so far.
- Only 9 to 25 percent of files are structurally correct for every tool, mostly because of restated signatures.

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
- Add tables for Maestro, Opus, Petrucci and November only if Stage 1.0 finds files that use them, in order of files covered.
- Handle outlined glyphs (Type B) by shape matching only if Stage 1.0 shows they occur. Otherwise give a clear "not supported" message.

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

## Order and dependencies

1. Stage 1.0 first. The other stages need its spec decision.
2. Stages 1.1 and 1.2 together, then 1.3.
3. Stage 1.4 can start once 1.2 gives staves and positions.
4. Stage 1.5 after 1.3. Stage 1.6 can start early with fake data.
5. Stage 1.7 last.

## Risks specific to Phase 1

- **The 99 percent target is far from any baseline.** Reading the vector PDF should remove most picture-reading errors, but this is not yet shown. Measure note accuracy after Stage 1.3 and escalate early if it is under 95 percent.
- **Commercial engraver output could break the assumptions** (outlined glyphs, legacy fonts). Stage 1.0 measures this first.
- **Structural correctness at 95 percent depends on the Stage 1.0 rule.**
- **Phase 2 items that do not block Phase 1:** the render-scale test, the key-value cache and INT8 inference, and the check of the starting weights' architecture, all listed in `docs/notes/training-benchmark.md`.
