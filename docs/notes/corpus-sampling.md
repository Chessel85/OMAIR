# Corpus sampling rules

Version 0.3, 5 October 2026 (implemented; guitar added; see "Implementation notes" at the end). This is the Stage 5 sampling design in `docs/plans/phase0.md`. It says which scores go into the development set, the regression set and the training pool, and how each is exported. The export scripts implement these rules. If a rule changes, change it here first.

## Sources

- **PDMX** (Zenodo record 15571083, about 14 GB in all). It has `PDMX.csv` (metadata, about 225 MB), `mxl.tar.gz` (compressed MusicXML, about 1.9 GB), `pdf.tar.gz` (the PDFs from MuseScore.com, about 9.6 GB), `metadata.tar.gz`, `mid.tar.gz`, `data.tar.gz` and `subset_paths.tar.gz`. Download the CSV, `mxl.tar.gz` and `subset_paths.tar.gz` first. Leave `pdf.tar.gz` for later: those PDFs are real MuseScore.com exports from many MuseScore versions, which makes them useful for Stage 8, but they are not needed for the sampling.
- **OpenScore Lieder** (voice and piano) and **OpenScore String Quartets** (chamber), from their GitHub repositories. Both are CC0. The scores are MuseScore files and are converted to MusicXML by MuseScore 4.

All downloads go under the corpus folder from `omr.paths`, in `sources/pdmx` and `sources/openscore`.

What PDMX tells and does not tell, from its paper and record:

- About 254,000 scores. The "deduplicated" subset keeps one best arrangement per piece (about 103,000). The "no_license_conflict" subset (about 223,000) drops scores whose website licence and in-file licence disagree. The "all_valid" subset has every file format present.
- Each score is public domain or CC0 on MuseScore.com. That is the uploader's claim. It does not guarantee that the music itself is out of copyright, which matters for popular and jazz arrangements.
- About 67 percent of scores have no genre tag. Genre therefore cannot be the only basis for stratifying, and texture is computed from the MusicXML itself.
- More than half of PDMX is solo music, and over 90 percent has fewer than five parts. Choir, chamber and ensemble scores must be sought out, or they will be scarce.

The column names in `PDMX.csv` are checked once it is downloaded. The rules below name what they need (genre, licence conflict flag, deduplication flag, rating, title, composer); the script maps those to the real columns and stops with a clear message if one is missing.

## Filters

A score is a candidate only if all of these hold.

- **Licence (C-4).** PDMX: in the no_license_conflict subset, and in the deduplicated subset. OpenScore: always.
- **Valid.** PDMX: in the all_valid subset. The MusicXML parses.
- **Size.** Between 8 and 200 bars, at most 12 parts, and a compressed MusicXML file under 1 MB. Larger scores make exports slow (musicxml2ly ran for more than 30 minutes on a 610 KB uncompressed ragtime file before it was stopped), and they add little that smaller scores do not.
- **Specialised notation out (REC-9).** No tablature staves, no unpitched percussion staves, no figured bass. These are a later phase, and would only add noise to the Phase 1 numbers.
- **Round trip.** MuseScore 4 imports the MusicXML and exports it again. The re-exported file is the **reference MusicXML** for the score. MuseScore 3 then imports the reference and exports it again, and musicdiff compares the two. A score is dropped if musicdiff finds any difference in notes or rests, or cannot parse either file (musicdiff then returns no count, which is not a pass). This removes scores that MusicXML tools cannot read the same way, which is the plan's round-trip filter.

The reference MusicXML is the ground truth for every export of that score, and every engraver is fed the reference, not the original file. For MuseScore 4 this is exact, because its PDF and its MusicXML come from the same loaded score. For MuseScore 3, LilyPond and Verovio, the engraver's own reading of the file may still lose something. Each pair records this in its metadata (`ground_truth: reference, exact` or `ground_truth: reference, engraver input`), so that Stage 6 can report those engravers separately.

## Labels computed for each candidate

### Texture (from the MusicXML part list)

Each part is a voice if its name or instrument sound says voice, soprano, alto, tenor, bass, baritone, mezzo, choir, chorus or vocal (in English, German, French or Italian), and a keyboard if it says piano, organ, harpsichord, keyboard, clavier or klavier. The first matching rule gives the texture.

1. **Choir:** two or more voice parts, or one part on two staves with lyrics on both staves (hymn layout).
2. **Voice with piano:** one voice part and one keyboard part, and nothing else.
3. **Piano:** one keyboard part and nothing else.
4. **Single line:** one part, one staff, not a keyboard.
5. **Chamber:** 2 to 5 parts, not matched above.
6. **Small ensemble:** 6 to 12 parts, not matched above.

### Genre

- PDMX genre tags are mapped to the seven REC-10 genres: classical, popular, jazz, folk, sacred, choral and educational. The mapping is written in this file once the distinct tag values are known from the CSV, as a list of "tag: genre" lines. Tags that fit none are "other".
- **Choral** is assigned to choir-texture scores that are not tagged sacred.
- **Educational** is assigned from the title or tags when they contain exercise, étude, etude, study, scale, lesson, method, beginner, grade or sight-reading, as whole words.
- Untagged scores get the genre "unlabelled". They can fill texture quotas but not genre quotas.
- OpenScore scores are classical.

### Features

Read from the reference MusicXML: has lyrics, has chord symbols, has more than one voice on a staff, has tuplets, has grace notes, has repeats or endings, has a key or time signature change, has dynamics or hairpins, has a guitar part (classical guitar in standard notation; bass guitar and electric guitar do not count). These make sure the sets exercise REC-2 to REC-6, not just a spread of genres.

## Splitting into pools

No piece may appear in more than one pool, including in different arrangements, because a model trained on one arrangement would be tested on a near copy.

1. Each candidate gets a **work key**: the composer and title, lower-cased, with punctuation, accents and words like "arr.", "for piano", "easy", "version" and opus or catalogue numbers removed. Two scores with the same work key are the same work.
2. Each work key gets a number from 0 to 1: the SHA-256 hash of the seed and the work key, read as a fraction.
3. A number below 0.03 makes the work regression-eligible. From 0.03 to below 0.15 it is development-eligible. Everything else is the training pool.

This split depends only on the seed and the work key, so it does not change when candidates are added or removed, and it can be recomputed at any time.

The work key alone does not keep the pools apart. Uploaders write the composer in many ways ("J. S. Bach (1685-1750)", "Johann Pachelbel Arranged by Melanie Dean", "Misc Praise Songs"), so arrangements of one piece get different keys and land in different pools. Measured on 6 October 2026, at least 12 development pieces had copies in the training pool (Amazing Grace, Canon in D, Joy to the World and others). The near-copy rules below close that gap. The key itself is kept, so the selected sets did not have to be redrawn because of it.

### Near copies

A score is a near copy of a selected piece if, after cleaning both:

- the titles are the same, and the title is distinctive, or the composers match, or either composer is unknown; or
- its title contains the selected title as a phrase ("Pachelbel's Canon in D (woodwind)" contains "Canon in D"), and the selected title has at least two distinctive words or the composers match.

Cleaning: the title loses catalogue numbers, the noise words of the work key and the composer's own surname. The composer string loses dates and bracketed text, is cut at the first arranger, editor or lyricist word (arr, arranged, transcribed, lyrics, words and so on), and becomes the surname of the last name left. Strings such as "Misc", "Traditional", "Anon" or "Unknown" count as no composer. A title made only of form names, keys, tempo words and numbers ("Prelude in C minor", "Song 1") is generic, because many different pieces share it, so it needs the composer to match. The word lists are in `src/omr/corpus/labels.py`.

The rules are used in two places:

- **Drawing the sets:** a candidate that is a near copy of a piece already chosen is skipped (step 6 below).
- **The training pool:** every training-pool score that is a near copy of a development or regression piece is removed (see "Training pool").

The rules lean towards removing too much. In a sample of removed scores, nearly all were true copies, and the rest were other settings of the same words (another "Amazing Grace" hymn tune).

**Seed: 20261005.** It is stored in `src/omr/corpus/config.py` (which holds every number in these rules) and in the metadata of every exported pair.

## Drawing the sets

Both sets are drawn by the same procedure from their own eligible pool.

1. Shuffle the eligible candidates with a random generator seeded with the seed.
2. Fill the texture quotas one texture at a time, in the order choir, chamber, small ensemble, voice with piano, single line, piano (scarce textures first, so that common ones do not use up candidates with useful features).
3. Within a texture, at each step take the candidate that helps the most unmet minimums, in this order of importance: priority features (guitar) first, then genre minimums, then the other feature minimums. Ties are broken by shuffled order.
4. OpenScore may fill at most 40 percent of the voice-with-piano and chamber quotas, so that MuseScore.com styles of writing are represented as well.
5. If a quota cannot be filled, take what there is, and write the shortfall to the log and to the selection file. Do not relax the filters to fill it.
6. Skip a candidate that shares a work key with a chosen score, or is a near copy of one.

### Development set: 300 scores

Texture quotas: single line 45, voice with piano 50, piano 70, choir 50, chamber 50, small ensemble 35.

Genre minimums: 20 of each of the seven genres.

Feature minimums: lyrics 60, chord symbols 30, several voices on a staff 40, tuplets 25, grace notes 20, repeats or endings 40, key or time changes 25, dynamics or hairpins 80, guitar 15.

### Regression set: 50 scores

The regression set is committed to the repository (Stage 7), so it has stricter rules.

- At most 64 bars and at most 3 pages in the MuseScore 4 export.
- Texture quotas: single line 8, voice with piano 8, piano 10, choir 8, chamber 8, small ensemble 8.
- Genre minimums: 3 of each genre. Feature minimums: lyrics 10, chord symbols 5, several voices on a staff 8, tuplets 5, repeats or endings 8, dynamics or hairpins 15, guitar 3.
- **Copyright check.** An uploader's CC0 claim is not enough for the public repository. A PDMX score may go in only if its composer is in `scripts/public_domain_composers.txt` (composers who died before 1956, plus "traditional" and "anonymous"), or it is an original work by the uploader marked CC0 with no named composer. Popular and jazz scores in particular will mostly come from ragtime, early jazz and pre-1930 song. The list starts with the composers found in the candidates, and the owner reviews it.
- The script writes the 50 titles, composers and sources as a plain list, and the owner reads it before it is committed.

### Training pool

Everything else that passes the filters, less the near copies of every development and regression piece. It is not exported in Phase 0, except the small sample Stage 10 needs.

`scripts/build_corpus.py training` writes the pool (`work/training-pool.txt`) and the removed near copies (`work/training-near-copies.txt`) under the corpus folder. It also warns if any selected score is a near copy of another selected score, in the same set or the other. Run it again whenever a selection file changes.

On 6 October 2026: 62,400 training candidates by metadata (60,996 PDMX, 1,404 OpenScore), 287 removed as near copies, 62,113 kept. These are metadata counts. The size, notation and round-trip filters have not yet been applied to the training pool, so the usable number will be lower.

## Exports

Every development and regression score is exported as a pair (PDF and the reference MusicXML) through these engravers. The command lines are in `docs/notes/tool-commands.md`.

Base exports, for every score (the plan's done condition):

- MuseScore 4 with its default font (Leland).
- MuseScore 3 with its default font (Emmentaler, which appears in the PDF as "MScore").
- LilyPond, through musicxml2ly, with Emmentaler.
- Verovio, through its SVG output converted to PDF, which gives Type B pages.

Font variants, one extra MuseScore 4 export and one extra MuseScore 3 export per score:

- MuseScore 4 rotates through Bravura, Petaluma, Gonville, MuseJazz, Finale Maestro, Finale Broadway and Emmentaler, in that order, across the set sorted by texture and then by the shuffled order. This spreads every font across every texture.
- MuseScore 3 (version 3.3.4) has only Emmentaler, Bravura, Gonville and MuseJazz. It rotates through Bravura, Gonville and MuseJazz the same way.
- Each MuseScore 4 variant also gets one of three staff sizes (staff space 1.5, 1.75 and 2.0 millimetres), rotating independently, so that the same font is seen at more than one size. The size is set in the `scaling` element of the MusicXML fed to MuseScore, because that overrides the style file. Only the scaling changes, so the notes in the reference are unaffected.

That makes 6 exports per score: about 1,800 pairs for the development set and 300 for the regression set.

Every export is checked with the inspector's JSON output before it is accepted: the music font must be the one requested, and every page must be Type A (MuseScore and LilyPond) or Type B (Verovio). MuseScore uses Bravura without any error when a requested font is missing, so without this check a wrong font would go unnoticed.

## Metadata for each pair

A small text file beside each pair, with one "name: value" line each: source (PDMX or OpenScore) and source path, work key, title, composer, set (development or regression), texture, genre, features, engraver, engraver version, font, staff size, ground truth (as above), seed, and the date of export.

## What is committed

- These rules, the config script with the seed, the composer list, and the selection files (one line per selected score: source path, set, texture and genre). Selection files hold no music, so they can be committed whatever the licence.
- The regression set itself, as described in Stage 7.
- Nothing else from the corpus.

## Implementation notes

Added on 5 October 2026 when the generator was written. The code is in `src/omr/corpus/` and the driver is `scripts/build_corpus.py` (`candidates`, `composers`, `select SET`, `export SET`, `report`).

- **Columns used from `PDMX.csv`:** `subset:no_license_conflict`, `subset:deduplicated`, `subset:all_valid`, `song_length.bars`, `n_tracks`, `title` (then `song_name`), `composer_name` (then `artist_name`), `genres`, `tags`, `mxl`, `is_original` and `license`. The metadata prefilter keeps 8 to 200 bars and 1 to 12 tracks. About 72,000 of 254,000 rows pass; the pool split then leaves about 11,000 to extract and parse.
- **Genre tag mapping.** The `genres` column joins tags with hyphens, for example `classical-soundtrack`. The distinct tags are: religiousmusic is sacred; jazz is jazz; folk, worldmusic and country are folk; classical is classical; pop, rock, rbfunksoul, hiphop, disco, metal, electronic, reggaeska and soundtrack are popular; anything else (comedy, newage and so on) is other. When a score has several tags, the first of sacred, jazz, folk, classical, popular wins. The mapping is `PDMX_TAG_GENRE` in `config.py`.
- **Voice and keyboard detection** uses the `instrument-sound` identifiers MuseScore writes (voice.soprano, keyboard.piano and so on). Only when a part has no sound identifier does the part name decide. This stops a bass guitar counting as a bass voice.
- **OpenScore** repositories already contain `.mxl` files beside the MuseScore files, so those are used as the source MusicXML instead of converting the MuseScore files. The MuseScore 4 round trip still runs on them. String quartets longer than 200 bars are dropped by the size rule, which leaves very few chamber scores from that source.
- **Public-domain composer list** (`scripts/public_domain_composers.txt`). A composer string matches if a listed phrase occurs in it as whole words. A string that also mentions an arranger, editor, transcriber or lyricist (words such as arr, arranged, by, after, text, lyrics) never matches, because the arranger's work may still be in copyright. The list is a first draft of composers with confidently known death dates. The owner must review it.
- **Round trip results are cached** in `work/roundtrip/` under the corpus folder, one record per candidate, and the reference MusicXML is kept there. Selection is lazy: the best candidate is chosen first and checked, and a failure only costs the check for that candidate. Each record carries the version of the check that made it (`CHECK_VERSION` in `roundtrip.py`). A passing record from an older version is checked again before use. Version 2 (6 October 2026) rejects files musicdiff cannot parse. Version 1 had passed two such development scores, which were replaced.
- **"Exact" ground truth** means exact in notes and rests. A sample of 63 scores showed MuseScore 4 re-reading its own reference with no note or rest differences. One score lost some "dim." text marks, and two swapped the order of dynamics on the same beat. At the start of Stage 6, each MuseScore 4 pair gets its own MusicXML (written from the same input as its PDF) as its ground truth, with the comparison against the shared reference recorded in its metadata.
- **Page limit.** The regression page limit uses the page count of the MuseScore 4 export in the default font.
- **Uniqueness.** No two scores in a set share a work key or are near copies of each other (the draw skips them). Across the two sets, `build_corpus.py training` checks for near copies and warns. On 6 October 2026 it found none.
- **Failed exports are not retried** on a re-run unless `--retry-failures` is given, because timeouts and wrong-font results would only fail again. Each failure is in the log, in a `failure.txt` beside the job, and in `index.txt`.
- **Exports run in parallel.** `export SET --workers N` runs up to N exports at once, each in its own process (default 3; `--workers 1` runs them one at a time in the main process). Only the main process writes the log, so each line is still one whole event, but lines can finish out of order; each names its score and job. Free space is checked before each score's jobs start, and a stop lets the running jobs finish, so the run resumes as before. The measured speed-up is in `docs/notes/tool-commands.md`.
- **Layout under the corpus folder:** `sources/` (downloads), `work/` (candidate cache and round-trip records), `generated/<set>/<score id>/reference.musicxml`, `generated/<set>/<score id>/<job>/score.pdf` and `metadata.txt`, and `generated/<set>/index.txt`. The selection files are in `docs/corpus-selection/`.

## Guitar and tablature (decision of 5 October 2026)

- Classical guitar in standard notation is explicitly in scope. A solo guitar part on one staff has the texture "single line", and guitar is a priority feature with a minimum in both sets, so the minimums are met before any genre or other feature. Guitar with other instruments is "chamber".
- Scores with a tablature staff stay excluded, as REC-9 puts tablature in a later phase. This includes guitar scores that show notation and tab together. If tab becomes in scope earlier, the decision must be made together with the Stage 6 evaluation design, because the ground truth would contain the tab staff.
- The guitar composers Sor, Giuliani, Carulli, Carcassi, Aguado and Tárrega are in `scripts/public_domain_composers.txt`, so guitar scores can enter the committed regression set.
