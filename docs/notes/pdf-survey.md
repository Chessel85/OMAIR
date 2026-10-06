# PDF-type survey (Stage 8, partial)

Survey of 7 October 2026. Written by Sonnet from the counts in `survey/survey-counts.txt` on the corpus drive. The Opus analysis the plan asks for is still to do, and so is the Sibelius and Finale half of the survey (see "What this survey cannot say").

## What was surveyed

- Tool: `scripts/run_survey.py` (`pdmx-sample`, `inspect`, `report`). It runs the same code as `omr inspect`. Records are in `survey/results.jsonl`, one per file, with the per-page evidence.
- 3,133 PDFs and 18,597 pages in all, none unreadable:
  - OpenScore string quartet and lieder PDFs: 983 files, 13,560 pages (MuseScore 4 and 3 output).
  - Mutopia: 150 files, 528 pages, a seeded sample of the 1,100 or so listed pieces. 94 are Public Domain and 56 CC BY-SA (internal use only). `scripts/collect_mutopia.py`, 3 seconds between requests, the site's robots.txt allows crawling.
  - PDMX: 2,000 files, 4,509 pages, a seeded sample (seed 20261007) of the 222,820 PDFs with no licence conflict. These are real MuseScore.com uploads.
- CPDL was not surveyed. cpdl.org answers automated requests with a Cloudflare challenge (HTTP 403), and the owner decided not to ask the site for access. IMSLP was not surveyed either: its list is chosen by hand with the owner and nothing was chosen. Any PDFs put in `sources/other` are picked up by the next `inspect` run.

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

## What this survey cannot say

- **No Sibelius, Finale, Dorico, Notion or Capella files.** All three sources are MuseScore or LilyPond output. So the main Phase 0 risk questions are still open: the share of Type B pages from commercial engravers, and which legacy fonts (Opus, Maestro, Petrucci, November) are common. The legacy-font threshold also remains uncalibrated for them.
- The PDMX sample is MuseScore.com uploads, which may differ from the PDFs people share through IMSLP, so it cannot stand for the whole internet.
- No scan was tested beyond the one D page, and no Type 3 font.

## Suggested next steps

1. Get real Sibelius and Finale PDFs by another route: files the owner has, the IMSLP list chosen by hand, or other sources whose terms allow it. Then rerun `run_survey.py inspect` and `report`.
2. Add `PFAEmmentaler-*` and `feta-alphabet20` to the legacy font list.
3. Opus analyses these counts and decides whether the Phase 1 plan changes.
