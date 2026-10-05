# OMR to MusicXML and Braille Music: Requirements Catalogue

Version 0.1, 5 October 2026.

This document lists what the system must do and the constraints it must work within. The solution design (`solution-design.md`) describes how the system meets these requirements, and refers to them by ID.

## How to read this catalogue

Every requirement has these fields:

| Field | Meaning |
| --- | --- |
| ID | Never changes or gets reused. |
| Priority | **Must** (the project fails without it), **Should** (important, but can come later), or **Could** (desirable if effort allows). |
| Phase | The phase in which it is first delivered (see the plan in the solution design). |
| Source | The vision statement (VS), a decision by the project owner (PO), or the design (D). |

The ID prefixes are:

| Prefix | Meaning |
| --- | --- |
| IN | Inputs |
| REC | Recognition content |
| OUT | Outputs |
| ACC | Accuracy |
| OP | Operation |
| AX | Accessibility |
| DEV | Development and verification |
| C | Project constraints |

## Inputs

| ID | Name | Requirement | Priority | Phase | Source |
| --- | --- | --- | --- | --- | --- |
| IN-1 | Vector PDFs from engraving software | Accept PDFs exported from engraving software, including MuseScore, Sibelius, Finale, Dorico and LilyPond. | Must | 1 | VS |
| IN-2 | Raster PDFs and images | Accept PDFs that contain page images, and PNG, JPEG and TIFF image files. | Must | 2 | VS |
| IN-3 | Photos and scans | Accept photos and scans of printed music, including open-book spreads. Isolate the music from text blocks, graphics, the surface the book rests on, and the centre line of the pages. | Must | 4 | VS |
| IN-4 | Older engravings | Accept older, pre-digital engravings. | Could | 5 | VS |
| IN-5 | Multi-page documents | Accept multi-page documents and keep bar numbering, parts and repeats continuous across pages. | Must | 1 | D |

## Recognition content

| ID | Name | Requirement | Priority | Phase | Source |
| --- | --- | --- | --- | --- | --- |
| REC-1 | Structure | Recognise the structure of the score: parts, staves, systems, bars, clefs, key signatures, time signatures, repeats, first and second endings, and navigation marks (D.C., D.S., coda, segno). | Must | 1 | VS |
| REC-2 | Notes and rests | Recognise every note's pitch, its position (onset) in the bar and its duration. This includes chords, rests, dots, ties, tuplets and grace notes. | Must | 1 | VS |
| REC-3 | Voices | Recognise multiple voices on one staff, and notes that cross from one staff to another. | Must | 1 | VS |
| REC-4 | Performance markings | Recognise dynamics, hairpins (crescendo and diminuendo), articulations, slurs, fermatas, ornaments, and tempo and expression text. | Should | 1 for vector input, 2 for raster input | VS |
| REC-5 | Lyrics | Recognise lyrics, attached to the correct notes. | Should | 1 for vector input | PO (broad range of genres) |
| REC-6 | Chord symbols | Recognise chord symbols, as used in popular music, jazz and lead sheets. | Should | 1 for vector input | PO (broad range of genres) |
| REC-7 | Score text | Recognise the title, composer, lyricist, part and instrument names, and rehearsal marks. | Should | 1 | D |
| REC-8 | Beaming and layout | Recognise beaming and other cosmetic layout. | Could | Not assigned | VS (not essential) |
| REC-9 | Specialised notations | Recognise percussion notation, guitar tablature and fretboard diagrams, and figured bass. | Could | Later phase | D |
| REC-10 | Breadth | Cover a broad range of genres and textures. Genres include classical, popular, jazz, folk, sacred, choral and educational music. Textures include a single melody line, voice with piano, piano, choir, chamber music and small ensembles. | Must | All | PO |

## Outputs

| ID | Name | Requirement | Priority | Phase | Source |
| --- | --- | --- | --- | --- | --- |
| OUT-1 | MusicXML | Produce valid MusicXML 4.0 that imports into MuseScore 4 without errors. | Must | 1 | VS |
| OUT-2 | Braille music | Produce braille music. The braille code, formatting conventions and file format must be configurable. The default code and file format are **not yet decided**. The project owner will consult the MuseScore community and braille-reading musicians. See open item OI-1. | Must | 1 (basic), 3 (quality) | VS |
| OUT-3 | Confidence report | Produce a plain-text confidence report that gives the location of every low-confidence item: page, system, bar, staff or part, beat, and the issue. | Must | 1 | VS |
| OUT-4 | Report summary | The report must open with a summary: the number of bars, the share recognised with high confidence, and the number of flagged items. | Must | 1 | D |
| OUT-5 | MIDI | Produce MIDI for listening checks. | Could | 1 | D |

## Accuracy

Note accuracy means the proportion of notes whose pitch, onset and duration all match the ground truth. File structure is correct when the parts, the number of bars, the clefs, the key and time signatures, and the repeats all match.

| ID | Name | Requirement | Priority | Phase | Source |
| --- | --- | --- | --- | --- | --- |
| ACC-1 | Vector PDFs | At least 99 percent note accuracy, and at least 95 percent of files structurally correct. | Must | 1 | VS and D |
| ACC-2 | Clean raster input | At least 97 percent note accuracy. | Must | 2 | VS and D |
| ACC-3 | Photos and scans | At least 93 to 95 percent note accuracy on photos and scans taken in reasonable conditions. | Must | 4 | VS and D |
| ACC-4 | Error flagging | At least 90 percent of the actual note errors must fall in bars that the confidence report flags. | Should | 1 | D (target to be refined) |
| ACC-5 | Musical context | Use musical context to improve accuracy. For example, the notes of each voice in a bar must add up to the time signature. | Must | 1 | VS |
| ACC-6 | Performance markings | At least 90 percent recall of dynamics and hairpins on vector input. | Should | 1 | D |

## Operation

| ID | Name | Requirement | Priority | Phase | Source |
| --- | --- | --- | --- | --- | --- |
| OP-1 | Fully offline | The system runs fully offline. It makes no network calls at run time and depends on no paid or cloud service. | Must | All | PO |
| OP-2 | Laptop hardware | The system runs on an ordinary laptop with a 6-core CPU, 32 GB of RAM, and either no GPU or a small one (2 GB, for example an NVIDIA T500). A GPU is optional and only speeds things up. | Must | All | VS |
| OP-3 | Speed | A vector PDF page converts in under 10 seconds. A raster page or a photo converts in under 60 seconds, on the CPU alone. | Should | Not assigned | D (targets to be confirmed) |
| OP-4 | Operating systems | Windows 11 is the primary platform. Linux and macOS are desirable. | Should | Not assigned | D |

## Accessibility

| ID | Name | Requirement | Priority | Phase | Source |
| --- | --- | --- | --- | --- | --- |
| AX-1 | Screen-reader operation | Every function works with a screen reader (NVDA is the reference) through a command-line interface. No step needs sight or a GUI. | Must | All | VS |
| AX-2 | Screen-reader-friendly text | Reports, messages and documentation are plain text or Markdown that reads well with a screen reader. They contain no ASCII-art diagrams, use no tables where a list would do, and give locations in words. | Must | All | VS and PO |
| AX-3 | Accessible development | A blind developer can carry out the development workflow: setting up, running tests, running the evaluation and reading the results. | Must | 0 | VS |

## Development and verification

| ID | Name | Requirement | Priority | Phase | Source |
| --- | --- | --- | --- | --- | --- |
| DEV-1 | Evaluation harness | An evaluation harness compares the output against ground-truth MusicXML across the corpus and reports the ACC metrics. | Must | 0 | VS |
| DEV-2 | Regression set | A fixed regression set runs automatically on every change. | Must | 0 | D |
| DEV-3 | Self-check by re-rendering | The system checks itself by rendering its own output and comparing it with the input. | Should | 2 | D |
| DEV-4 | Baselines | Measure baseline accuracy for existing open-source OMR tools on the same corpus. | Should | 0 | D |

## Project constraints

| ID | Name | Requirement | Priority | Source |
| --- | --- | --- | --- | --- |
| C-1 | Free and open source | The project is free and open source and will never be used to make money. | Must | PO |
| C-2 | Licence | The project licence is AGPL-3.0. This is required because key dependencies (PyMuPDF, Ultralytics) are AGPL, and it is compatible with all the other planned dependencies. | Must | D, following C-1 |
| C-3 | Licence-compatible components | Every bundled dependency, model weight file and dataset must have a licence compatible with redistribution under C-2. Components licensed for non-commercial use only may be used for internal comparison, but must not be shipped. A licence register records each one. | Must | D |
| C-4 | Copyrighted scores | Copyrighted scores, including most user uploads on MuseScore.com, must not be committed to the public repository. They stay in a local, git-ignored folder. | Must | D |
| C-5 | No-cost development | Development uses only free tools and incurs no cost. Training runs on the development laptop. Free cloud GPU quotas (Kaggle, Colab) may optionally speed training up, but nothing may depend on paid compute. | Must | VS and PO |
| C-7 | Trainable on the development laptop | Every model the system ships must be trainable or fine-tunable on the development laptop (2 GB GPU, 6-core CPU, 32 GB RAM) within a few days per run. | Must | PO |
| C-6 | Available engraving software | The project has access to MuseScore (versions 3 and 4) and to the free engravers Dorico SE, LilyPond and Verovio. Sibelius and Finale are not available, so ground truth for their output must come from published editions that provide both a PDF and a MusicXML or source file. | Must | PO |

## Open items

| ID | Topic | Question | Owner | Impact |
| --- | --- | --- | --- | --- |
| OI-1 | Braille music code | Which braille music code, formatting conventions and output file format (for example BRF, Unicode braille text, or both) should be the default? | The project owner, through the MuseScore community | Blocks the Phase 3 decisions on braille, but not Phase 1. |
| OI-2 | Speed targets | The OP-3 targets need confirming once baseline timings exist (Phase 0). | Not assigned | Affects OP-3. |
| OI-3 | Error-flagging target | The ACC-4 target needs refining once the first measurements exist (Phase 1). | Not assigned | Affects ACC-4. |
