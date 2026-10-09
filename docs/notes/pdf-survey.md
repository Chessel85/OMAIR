# PDF-type survey (Stage 8, and Phase 1 Stage 1.0)

Survey of 7 October 2026, written by Sonnet from the counts in `survey/survey-counts.txt` on the corpus drive, with an analysis added on 9 October 2026 to close Phase 0. The commercial engraver sample (Sibelius, Finale and Dorico, from IMSLP) was added on 9 October 2026 for Phase 1 Stage 1.0, in its own section below.

## What was surveyed

- Tool: `scripts/run_survey.py` (`pdmx-sample`, `inspect`, `report`). It runs the same code as `omr inspect`. Records are in `survey/results.jsonl`, one per file, with the per-page evidence.
- 3,133 PDFs and 18,597 pages in all, none unreadable:
  - OpenScore string quartet and lieder PDFs: 983 files, 13,560 pages (MuseScore 4 and 3 output).
  - Mutopia: 150 files, 528 pages, a seeded sample of the 1,100 or so listed pieces. 94 are Public Domain and 56 CC BY-SA (internal use only). `scripts/collect_mutopia.py`, 3 seconds between requests, the site's robots.txt allows crawling.
  - PDMX: 2,000 files, 4,509 pages, a seeded sample (seed 20261007) of the 222,820 PDFs with no licence conflict. These are real MuseScore.com uploads.
- CPDL was not surveyed. cpdl.org answers automated requests with a Cloudflare challenge (HTTP 403), and the owner decided not to ask the site for access.
- IMSLP: 21 files, 680 pages, in `sources/other/imslp` (see "Commercial engraver sample"). Any PDFs put in `sources/other` are picked up by the next `inspect` run.

## Findings

- **Almost every page is Type A** (music fonts with vector staves): 99.9 percent of OpenScore pages, 97.2 percent of Mutopia and 99.6 percent of PDMX.
- **No real Type B (outlined glyphs) was found.** The only two B pages are matplotlib charts in the OpenScore repository, not scores. The outlined-glyph path matters only for engravers not in this sample.
- **One Type D page** (a photo or scan) in 4,509 PDMX pages: a 10-page file whose first page is a small photo, 34 percent of the page, with a paper-like background. The inspector called it D with low confidence, as it should.
- **Type N (no music) pages:** 8 in OpenScore, 15 in Mutopia, 16 in PDMX. They are title or text pages, and all high confidence.
- **Producers:** PDMX is all `Qt 5.9.8`, which is MuseScore's PDF writer. Mutopia is all Ghostscript, versions 8.15 to 9.20, so LilyPond output of several ages.
- **Music fonts, by share of files:**
  - OpenScore: Leland 98.7 percent, Bravura 9 percent, MScore 1 percent.
  - PDMX: MScore 99.5 percent (the MuseScore 3 font, mapped as SMuFL), with Bravura, MuseJazz, Gootville and Petaluma in under 1 percent each.
  - Mutopia: Emmentaler in several optical sizes (20, 18, 16, 14, 13, 11, 26 and 23) plus Emmentaler-Brace.
- **Font mapping tables for Phase 1 (legacy fonts, by files covered):** only Emmentaler, in 12 or so font names. Its size variants share one glyph layout, so one table should cover them. `PFAEmmentaler-NN` (8 files, 5 percent of Mutopia) and `feta-alphabet20` (2 files) are not on the legacy list and are classed "unknown, probably music" by position. They should be added to the list.
- **False "probably music" classes** (text fonts judged music by position on a staff): `Edwin-Italic` (a Zemlinsky quartet, pages 25 and 42, 20 staves on a page), `FreeSerifItalic`, `FreeSerif`, `LiberationSerif` and its italic. All are dynamics, tempo or lyric words on dense pages, with 11 to 33 percent of their glyphs on staves. The 10-glyph minimum and the quarter threshold let them through. A text font is listed wrongly and gets a warning, but the page type stays right. Raising the threshold would lose real music fonts (see the Opus review of the first Stage 8 task), so the better fix is to compare each font's glyph shapes with letters, not to move the number.
- **Speed:** 2,000 PDMX files took about 70 seconds on 3 workers, so vector PDFs inspect in well under a second a page.

## Commercial engraver sample (IMSLP, 9 October 2026)

### How it was collected

- IMSLP's edition notes were searched for editions typeset with Sibelius, Finale or Dorico (750 candidate PDFs), and 7 of each were chosen across piano, choir, chamber, orchestra and voice with piano. The owner approved the list. IMSLP answers scripted downloads with a bot check, so the owner downloaded the files by hand. 21 of 22 arrived. The missing one is a Dorico file in Leland, which would have added little.
- The program was read from each PDF's own metadata and fonts, not from IMSLP's notes, which were wrong once: a "Finale" edition was made with Sibelius 8.
- Licences are recorded per file in `sources/other/imslp/sample.json`. The files stay on the corpus drive.

### Results by program

- **Sibelius, 9 files.** Exported directly by Sibelius 5, 8 and 2021 (3 files): Type A, in Opus or Helsinki. Printed through the Windows PostScript driver, then Ghostscript or Acrobat Distiller (3 files): Type A, and in one of them the driver renamed the music font (for example "TTE26B52B8t00"). Printed through PDFCreator, or by an unknown route (2 files): Type B, the music drawn as outlines, with a few Opus glyphs left on 3 of 60 pages. One file is a scan of a print (Type C).
- **Finale, 6 files.** Type A in 5, in Maestro (Finale 2003 through Acrobat Distiller, and a recent Finale through macOS) or in a Maestro renamed by the Windows printer driver (3 files, through Ghostscript, or joined afterwards with pdfsam or pdftk). One printed through Ghostscript is Type B.
- **Dorico, 6 files.** Exported directly (5 files): Type A, in Bravura or Sebastian (SMuFL). One printed through Ghostscript is Type B, with only its Bravura Text glyphs left as a font.
- **In all:** 16 of 21 files are Type A, 4 are Type B (one page in a fifth file is also B: a decorative title page in The Planets), and 1 is Type C. By page, 85 percent A and 13 percent B. No Type 3 font occurred.

### What this shows

- **Type B is real.** 4 of the 20 notation files, from all three programs, are mostly outlined glyphs. Three were printed to PDF through a printer driver and Ghostscript or PDFCreator, not exported by the program; the fourth carries no record of how it was made. Ghostscript does not always outline (three Ghostscript files kept their fonts), so the producer alone cannot predict it. Phase 1 needs the outlined-glyph path for these, not only a "not supported" message.
- **Legacy fonts are the rule for Sibelius and Finale:** Opus and Helsinki (Sibelius), Maestro (Finale), with their companion fonts (OpusSpecial, HelsinkiSpecial, OpusText). Petrucci and November did not occur. Dorico uses SMuFL.
- **Printer drivers rename fonts** (TTE...t00, TT...t00), so the legacy name list cannot find them. The position test found all of them, and the letter-shape test confirmed they are not letters. Phase 1 must tell which legacy font a renamed font is from its glyph shapes, before it can use a mapping table.
- **Three inspector faults were found and fixed:** a Windows symbol font (Opus) was taken for SMuFL; a beam drawn exactly on a staff line hid the staff (Finale); and a landscape page stored sideways had no staves found. Before the fixes, 2 Sibelius files were called SMuFL and 2 Finale files had pages called "no music" or "Type B, low confidence". All three are in `inspector-spec.md`, with tests.
- **The legacy-font threshold holds.** On every one of 348 pages, the main music fonts have at least 30 percent of their glyphs on staves, against the threshold of a quarter, so none is missed. Companion fonts often have none on staves; a renamed companion font would be classed text (a known limit).

## What this survey cannot say

- 21 commercial files are a small sample, and all come from IMSLP, whose uploads are mostly older printed-to-PDF editions. The share of Type B among the PDFs a user will bring is not known, only that it is not rare.
- The PDMX sample is MuseScore.com uploads, which may differ from the PDFs people share elsewhere.
- No scan was tested beyond the one D page and one C file, and no Type 3 font occurred.

## Suggested next steps

1. Stage 1.1: mapping tables for Opus, Helsinki and Maestro (with their companion fonts), identification of renamed legacy fonts by glyph shape, and the outlined-glyph path for Type B.
2. Done: `PFAEmmentaler` and `feta-alphabet` are on the legacy font list.

## Analysis (9 October 2026, closing Stage 8 for Phase 0)

- **What the data supports.** For MuseScore and LilyPond output, which is all of the 3,133 files, the vector path of the design is right: 99.6 to 99.9 percent of pages are Type A, and the single Type D page was classed correctly with low confidence. Phase 1 can be built on Type A first, with Type B treated as a fallback that costs little until a source of outlined glyphs is found.
- **Font mapping tables, in order of files covered:** (1) SMuFL, no table needed (Leland, Bravura, Petaluma, MuseJazz, Gootville; and MScore, which the inspector already maps as SMuFL, 99.5 percent of PDMX files); (2) Emmentaler with its size variants (`PFAEmmentaler-NN`, `feta-alphabet`), one table, about 5 percent of Mutopia and nearly all LilyPond output of that era. Maestro, Opus, Petrucci and November are not yet covered by any evidence. They stay on the Phase 1 list on the design's word, last in order.
- **Unusual files:** the false "probably music" text fonts (Edwin-Italic, FreeSerif, LiberationSerif) occur on dense pages with dynamics, tempo or lyric words. The page type stays right and the font gets a warning. Phase 1 should replace the position test with a glyph-shape test against letters, as already noted. The 10-page file with a photo first page shows that a mixed C/D and A document is possible, so page type must stay per page.
- **Risks 1 and 2 of the design (outlined glyphs, legacy fonts):** not resolved. They need commercial engraver output. The owner accepted this on 7 October 2026. The consequence for the plan is that the Phase 1 gate in the solution design, which names the CPDL Sibelius and Finale pairs, cannot be met as written (CPDL is blocked by Cloudflare). The Phase 1 plan therefore starts with a task to get such files (an IMSLP list chosen with the owner, or the owner's own files) and changes the gate wording to match what was obtained.
- **Change to the Phase 1 plan:** none to its order. Add the Emmentaler table, the glyph-shape font test, and the Sibelius and Finale file collection as Phase 1 tasks (see `docs/plans/phase1.md`).
