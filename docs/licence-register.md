# Licence register

Version 0.1, 5 October 2026. Covers requirement C-3.

This register records the licence of every dependency, dataset, model and tool used by the project. Like the other planning documents, it uses headings and lists only, so that it reads well with a screen reader.

This is a record of facts as found, not legal advice. Dataset, model and tool licences were looked up by web search on 5 October 2026 and the source is named in each entry. Search results are secondary, so check the primary page before a release. Where an entry says "Not confirmed", no source was found. Anything marked "owner to resolve" has a default that was adopted so work is not blocked, and the owner can change it.

## How to read an entry

Each entry is a heading with the name, followed by a list:

- Kind: dependency, dataset, model or tool.
- Version: the pinned version, where there is one.
- Licence: the licence as stated by the source.
- Use: "shipped" means the project distributes it or installs it for users. "Internal only" means it is used for development, comparison or corpus building and is never shipped.
- Source: where the licence information came from.
- Status: "ok", or "owner to resolve", with the reason.

The test in `tests/test_licence_register.py` fails if a package in `requirements.txt` or `requirements-torch.txt` has no entry whose heading is its name.

## Owner to resolve

These were settled by a default rule so that work is not blocked. Change any you disagree with:

- CPDL: Default rule adopted so work is not blocked. Change it if you prefer.
- Mutopia: Default rule adopted so work is not blocked. Change it if you prefer.
- homr weights: one of their training datasets may be non-commercial. Default: use them for the sequence reader, and settle this before anything trained from them is released.
- OLiMPiC: Default: internal only. Change it if you want to train on it and ship the result.

## Datasets

### PDMX

- Kind: dataset
- Version: 2024 release
- Licence: Each score is public domain (Public Domain Mark) or CC0. The dataset itself is CC BY. About 12 percent of scores had a conflict between the website licence and the licence inside the file, so use the no_license_conflict subset.
- Use: Used to build the corpus. Output may be committed (C-4), using only the no_license_conflict subset.
- Source: Web search, 5 Oct 2026: the PDMX paper (arxiv.org/abs/2409.10831) and github.com/pnlong/PDMX.
- Status: ok

### OpenScore

- Kind: dataset
- Version: Lieder corpus, string quartets and others
- Licence: CC0
- Use: Used to build the corpus. Output may be committed.
- Source: Web search, 5 Oct 2026: github.com/OpenScore/Lieder and openscore.cc.
- Status: ok

### CPDL

- Kind: dataset
- Version: current
- Licence: Per edition: CPDL licence (GPL-based), Creative Commons of various kinds, or public domain.
- Use: Real PDFs with MusicXML or source files (C-6). Default rule: only editions marked public domain, CC0 or CC BY may go in the public repository. Everything else stays in the git-ignored corpus folder. Check the site terms in Stage 8.
- Source: Web search, 5 Oct 2026: cpdl.org ChoralWiki licence pages. The licence of each edition is read at collection time.
- Status: owner to resolve. Default rule adopted so work is not blocked. Change it if you prefer.

### IMSLP

- Kind: dataset
- Version: a hand-picked sample of 21 files, October 2026
- Licence: Per file: public domain, CC0, or Creative Commons of various kinds (some non-commercial). The licence of each file is recorded in `sources/other/imslp/sample.json` on the corpus drive.
- Use: Survey of commercial engraver output (Sibelius, Finale, Dorico) in Phase 1 Stage 1.0. The files stay in the git-ignored corpus folder and are never committed. IMSLP answers scripted downloads with a bot check, so the owner downloaded the files by hand in a browser.
- Source: imslp.org file pages, 9 Oct 2026.
- Status: ok for local survey use.

### Mutopia

- Kind: dataset
- Version: current
- Licence: Per piece: public domain, CC BY or CC BY-SA.
- Use: LilyPond sources and PDFs for the corpus. Default rule: public domain and CC BY pieces may go in the public repository. CC BY-SA pieces stay local.
- Source: Web search, 5 Oct 2026: mutopiaproject.org/legal.html. Per-piece licences are recorded at collection time.
- Status: owner to resolve. Default rule adopted so work is not blocked. Change it if you prefer.

### DeepScores V2

- Kind: dataset
- Version: v2
- Licence: CC BY 4.0
- Use: Training data for symbol detection. Attribution required.
- Source: Web search, 5 Oct 2026: zenodo.org/records/4012193.
- Status: ok

### GrandStaff and Camera-GrandStaff

- Kind: dataset
- Version: current
- Licence: MIT (as published on Hugging Face, PRAIG/grandstaff)
- Use: Training and testing data for the raster path.
- Source: Web search, 5 Oct 2026: Hugging Face dataset page.
- Status: ok

### PrIMuS and Camera-PrIMuS

- Kind: dataset
- Version: current
- Licence: CC BY 4.0 (attribution to Calvo-Zaragoza and Rizo)
- Use: Training and testing data for the raster path. Attribution required.
- Source: Web search, 5 Oct 2026: result for Camera-PrIMuS. The plain PrIMuS page was not seen, but it is from the same authors.
- Status: ok

### OLiMPiC

- Kind: dataset
- Version: current
- Licence: CC BY-SA (the synthetic and scanned datasets and the Zeus weights). Code is MIT.
- Use: Internal evaluation and comparison only for now. Share-alike terms on data and weights would need a decision before anything trained on them is shipped.
- Source: Web search, 5 Oct 2026: github.com/ufal/olimpic-icdar24.
- Status: owner to resolve. Default: internal only. Change it if you want to train on it and ship the result.

### MUSCIMA++

- Kind: dataset
- Version: current
- Licence: Not applicable. Out of scope (handwritten music).
- Use: Not used.
- Source: solution-design.md lists it as out of scope.
- Status: ok

## Models and weights

### YOLO pretrained weights (Ultralytics)

- Kind: model
- Version: YOLO11 nano (`yolo11n.pt`), the size measured in the Phase 0 training benchmark
- Licence: AGPL-3.0, or the Ultralytics Enterprise Licence for those who buy it. The repository's licence section offers these two for "Ultralytics software and AI models"; it does not give the pretrained weights a licence of their own.
- Use: Chosen in Stage 2.0 as the starting point for the symbol detector (Engine 1), shipped after fine-tuning. Fine-tuned weights are AGPL too, which fits C-2. No detector weights trained on DeepScores with a stated licence were found, so the project's own labels (Stage 2.1) do the music-specific training.
- Source: github.com/ultralytics/ultralytics, licence section, checked 17 October 2026.
- Status: ok

### homr

- Kind: model
- Version: 0.7.0 (installed in Stage 9). For fine-tuning, the PyTorch checkpoint `pytorch_model_465` from the repository's "checkpoints" release, which matches the training code at commit ab369ac (15 October 2026).
- Licence: AGPL-3.0 for the code and the weights ("published under the AGPL as well", LICENSE_FAQ.md). The same page says the AGPL "can't grant more rights than the training data allows", and lists the transformer's training data: OpenScore Lieder and String Quartets (CC0), GrandStaff (MIT on Hugging Face), PDMX's no-licence-conflict subset (CC BY 4.0), the MuseTrainer library (public domain by its description) and Camera-PrIMuS, whose Hugging Face copy is listed as CC BY-NC 4.0. Every transformer checkpoint released so far includes PrIMuS. The segmentation models were trained on DeepScores V2 (CC BY 4.0).
- Size: encoder 13.2 million parameters (FP32 in the ONNX file), decoder 46.9 million (INT8 in the ONNX file), about 60 million in the ONNX files; the PyTorch training model is 75.0 million. Input a staff image of 256 by 1280 pixels; output six token streams (rhythm, pitch, lift, articulation, slur, staff position), up to 608 tokens.
- Use: Baseline in Phase 0, and chosen by the owner in Stage 2.0 as the starting point for the sequence reader (Engine 2), shipped after fine-tuning, if it trains on the laptop (Stage 2.6).
- Source: github.com/liebharc/homr README and LICENSE_FAQ.md, and the release asset list, checked 17 October 2026. Sizes measured from the installed ONNX files.
- Status: owner to resolve before a release. The weights are AGPL like the project, but one training dataset may be non-commercial. homr itself calls the question open. The project is never commercial, but the AGPL lets others use it commercially. Default: use the weights, and settle this before anything trained from them is released. SMT is the fallback.

### PP-OCRv5 Latin recognition model

- Kind: model
- Version: `latin_PP-OCRv5_rec_mobile.onnx` (8 MB), as RapidOCR 3.10.0 publishes it on ModelScope (RapidAI/RapidOCR, v3.10.0), converted from PaddleOCR's model.
- Licence: Apache-2.0 (PaddleOCR's models; RapidOCR's conversions are under the same licence)
- Use: Reads the text in page images (Stage 2.5), shipped. Kept in `models/ocr/` and named to RapidOCR by its path, so nothing is downloaded at run time.
- Source: RapidOCR's model list (`default_models.yaml` in the package) and github.com/RapidAI/RapidOCR licence section, checked 24 October 2026.
- Status: ok

### SMT (Sheet Music Transformer)

- Kind: model
- Version: `antoniorv6/smt-grandstaff` on Hugging Face, if used
- Licence: MIT (the model card's licence field, and the code repository)
- Size: 21.4 million parameters; a ConvNeXt encoder and a Transformer decoder; output in bekern (Humdrum kern) tokens. Trained on GrandStaff (piano grand staves) only.
- Use: Fallback starting point for the sequence reader, if homr's weights do not train in 2 GB or their licence question goes the wrong way.
- Source: huggingface.co/antoniorv6/smt-grandstaff and github.com/antoniorv6/SMT, checked 17 October 2026.
- Status: ok

### LEGATO

- Kind: model
- Version: `guangyangmusic/legato` (full model, about 107 million trained parameters), with the vision encoder from `meta-llama/Llama-3.2-11B-Vision`.
- Licence: MIT for LEGATO's code and weights. Both repositories are gated on Hugging Face: LEGATO by automatic approval, and Llama by Meta's manual approval under the Llama 3.2 Community Licence, which also bars its multimodal rights to people and companies in the EU. The owner was approved on 7 October 2026. `legato-1.5` needs separate manual approval and is not used.
- Use: Internal comparison baseline only, never shipped. Run in its own Python 3.12 environment under `tools/legato` on the corpus drive. The Llama licence needs "Built with Llama" and its notice if anything derived from it is ever distributed.
- Source: Hugging Face model cards and repository metadata, checked 7 October 2026.
- Status: ok

## External tools

### Audiveris

- Kind: tool
- Version: see `docs/notes/tool-commands.md` where installed
- Licence: AGPL-3.0
- Use: internal only. Baseline OMR. Runs as a separate external process only, never linked or bundled, so its licence stays separate.
- Source: solution-design.md section 4.3.
- Status: ok

### FreeDots

- Kind: tool
- Version: see `docs/notes/tool-commands.md` where installed
- Licence: GPL-3.0
- Use: internal only. Braille translator candidate for Phase 3. External process.
- Source: Web search, 5 Oct 2026: github.com/mlang/freedots.
- Status: ok

### Sao Mai Braille Music Translator

- Kind: tool
- Version: see `docs/notes/tool-commands.md` where installed
- Licence: Free to use, closed source. No open licence found.
- Use: internal only. Braille translator candidate for Phase 3. Cannot be bundled. External use only.
- Source: Web search, 5 Oct 2026: saomaicenter.org.
- Status: ok

### MuseScore 3

- Kind: tool
- Version: see `docs/notes/tool-commands.md` where installed
- Licence: GPL-3.0
- Use: internal only. Corpus export through the command line.
- Source: Upstream project licence, from memory.
- Status: ok

### MuseScore 4

- Kind: tool
- Version: see `docs/notes/tool-commands.md` where installed
- Licence: GPL-3.0
- Use: internal only. Corpus export through the command line.
- Source: Upstream project licence, from memory.
- Status: ok

### LilyPond

- Kind: tool
- Version: see `docs/notes/tool-commands.md` where installed
- Licence: GPL-3.0
- Use: internal only. Corpus export, through musicxml2ly.
- Source: Upstream project licence, from memory.
- Status: ok

### Dorico SE

- Kind: tool
- Version: see `docs/notes/tool-commands.md` where installed
- Licence: Proprietary, free tier
- Use: internal only. Parked. Not used in Phase 0 (not accessible with a screen reader).
- Source: docs/plans/phase0-progress.md.
- Status: ok

### Git

- Kind: tool
- Version: see `docs/notes/tool-commands.md` where installed
- Licence: GPL-2.0
- Use: internal only. Development tool.
- Source: Upstream project licence, from memory.
- Status: ok

### Temurin OpenJDK

- Kind: tool
- Version: see `docs/notes/tool-commands.md` where installed
- Licence: GPL-2.0 with Classpath Exception
- Use: internal only. Runs Audiveris and FreeDots.
- Source: Upstream project licence, from memory.
- Status: ok

## Music fonts used to render the corpus

These are used only to render test PDFs in Stage 5. The fonts are not shipped, so their licences do not constrain the project.

### Leland

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: SIL OFL 1.1
- Use: internal only. Rendering test files.
- Source: Not confirmed by search.
- Status: ok

### Bravura

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: SIL OFL 1.1
- Use: internal only. Rendering test files.
- Source: Not confirmed by search.
- Status: ok

### Petaluma

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: SIL OFL 1.1
- Use: internal only. Rendering test files.
- Source: Not confirmed by search.
- Status: ok

### Emmentaler

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: Not confirmed. LilyPond font, believed OFL or GPL with font exception.
- Use: internal only. Rendering test files.
- Source: Not confirmed by search.
- Status: ok

### Gonville

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: Not confirmed. Believed GPL with font exception.
- Use: internal only. Rendering test files.
- Source: Not confirmed by search.
- Status: ok

### MuseJazz

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: Not confirmed. Believed OFL.
- Use: internal only. Rendering test files.
- Source: Not confirmed by search.
- Status: ok

## Symbol data used at run time (Phase 1)

Stage 1.1 names music symbols with data that ships with an installed dependency or was written for the project. Nothing here is copied into the repository except facts (glyph names and code points).

### SMuFL reference outlines and glyph names (Verovio data)

- Kind: dataset
- Version: as installed with verovio 6.3.0
- Licence: The glyph outlines are from Bravura, Leland and Petaluma (SIL OFL 1.1) and Gootville and Leipzig (SIL OFL 1.1, as distributed with Verovio). Verovio itself is LGPL-3.0-only.
- Use: shipped (installed as part of the verovio package, read at run time from its data folder; not copied into the repository)
- Source: The font names and Verovio's own licence notes in its package. The font licences are as stated by their projects; not re-checked by search.
- Status: ok
- Note: `src/omr/pdf/smufl.py` reads the glyph names, bounding boxes and SVG outlines to name SMuFL code points and to draw reference shapes for matching renamed fonts and outlined symbols.

### SMuFL glyph names in the supplement

- Kind: dataset
- Version: SMuFL 1.4 names
- Licence: Facts (a glyph's standard name and code point). The SMuFL specification is published by the W3C Music Notation Community Group under the W3C Community Final Specification Agreement. No file from the specification is copied.
- Use: shipped (about 60 names written into `src/omr/pdf/smufl.py`)
- Source: SMuFL `glyphnames.json`, read during development on 9 October 2026 to check names; not stored in the repository.
- Status: ok

### Legacy music font tables (Sonata layout and Emmentaler)

- Kind: dataset
- Version: written 9 October 2026
- Licence: the project's own work (AGPL-3.0-or-later, as the code). A table of which character draws which symbol is a set of facts; no font data is copied.
- Use: shipped (in `src/omr/pdf/fonttables.py`)
- Source: Built by drawing each glyph of the installed Maestro font and of the Opus, Helsinki and Maestro subsets embedded in the IMSLP commercial sample, and the LilyPond Emmentaler font, and looking at each in context.
- Status: ok
- Note: The Maestro font installed on the development machine (`MAESTRO_.TTF`, Coda Music Technology) and the embedded commercial fonts are not shipped and not stored in the repository.

## Python dependencies

These are pinned in `requirements.txt` or `requirements-torch.txt` and installed by pip. None is bundled in the repository. Licences come from the package metadata in the installed environment, read on 5 October 2026. Re-check an entry when its version changes.

### anyio

- Kind: dependency
- Version: 4.15.1
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### certifi

- Kind: dependency
- Version: 2026.7.22
- Licence: MPL-2.0
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
- Note: Used unmodified, so MPL imposes nothing extra. Pulled in by requests and httpx.

### chardet

- Kind: dependency
- Version: 7.6.0
- Licence: 0BSD
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
- Note: Version 7 uses 0BSD. Older versions were LGPL, so the pin matters.

### charset-normalizer

- Kind: dependency
- Version: 3.5.2
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### cloudpickle

- Kind: dependency
- Version: 3.1.2
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### colorama

- Kind: dependency
- Version: 0.4.6
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### colorlog

- Kind: dependency
- Version: 6.12.0
- Licence: MIT
- Use: shipped (installed as a dependency of RapidOCR)
- Source: package metadata in the installed environment
- Status: ok

### contourpy

- Kind: dependency
- Version: 1.4.0
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### converter21

- Kind: dependency
- Version: 4.0.2
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
- Note: Pulled in by musicdiff.

### cycler

- Kind: dependency
- Version: 0.12.1
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### filelock

- Kind: dependency
- Version: 3.32.3
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### flatbuffers

- Kind: dependency
- Version: 25.12.19
- Licence: Apache-2.0
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### fonttools

- Kind: dependency
- Version: 4.66.1
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### fsspec

- Kind: dependency
- Version: 2026.7.0
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### h11

- Kind: dependency
- Version: 0.16.0
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### httpcore

- Kind: dependency
- Version: 1.0.9
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### httpx

- Kind: dependency
- Version: 0.28.1
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### idna

- Kind: dependency
- Version: 3.20
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### ImageIO

- Kind: dependency
- Version: 2.38.0
- Licence: BSD-2-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### iniconfig

- Kind: dependency
- Version: 2.3.0
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### Jinja2

- Kind: dependency
- Version: 3.1.6
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### joblib

- Kind: dependency
- Version: 1.6.0
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### jsonpickle

- Kind: dependency
- Version: 4.1.3
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### kiwisolver

- Kind: dependency
- Version: 1.5.1
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### lazy-loader

- Kind: dependency
- Version: 0.6
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### lxml

- Kind: dependency
- Version: 6.1.3
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### MarkupSafe

- Kind: dependency
- Version: 3.0.3
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### matplotlib

- Kind: dependency
- Version: 3.11.2
- Licence: Matplotlib licence (PSF-style, permissive)
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### more-itertools

- Kind: dependency
- Version: 11.1.0
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### mpmath

- Kind: dependency
- Version: 1.3.0
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### music21

- Kind: dependency
- Version: 10.5.0
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### musicdiff

- Kind: dependency
- Version: 6.0
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### networkx

- Kind: dependency
- Version: 3.6.1
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### numpy

- Kind: dependency
- Version: 2.5.3
- Licence: BSD-3-Clause, with 0BSD, MIT, Zlib and CC0 parts
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### nvidia-ml-py

- Kind: dependency
- Version: 13.615.71
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### omegaconf

- Kind: dependency
- Version: 2.4.0
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency of RapidOCR)
- Source: the package's repository (github.com/omry/omegaconf, LICENSE); its metadata gives none, checked 24 October 2026
- Status: ok

### onnxruntime

- Kind: dependency
- Version: 1.30.0
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### opencv-python

- Kind: dependency
- Version: 5.0.0.93
- Licence: Apache-2.0
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
- Note: The wheels also bundle FFmpeg under LGPL. We do not use video, but note it if wheels are ever redistributed.

### opencv-python-headless

- Kind: dependency
- Version: 5.0.0.93
- Licence: Apache-2.0
- Use: shipped (installed as a dependency of RapidOCR)
- Source: package metadata in the installed environment
- Status: ok
- Note: Installed beside opencv-python of the same version; both provide `cv2`, and the one installed last is used. They are the same library built with and without its window functions, which the project does not use.

### packaging

- Kind: dependency
- Version: 26.3
- Licence: Apache-2.0 or BSD-2-Clause (dual)
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### pikepdf

- Kind: dependency
- Version: 10.16.0
- Licence: MPL-2.0
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
- Note: MPL is file-level copyleft. MPL-2.0 section 3.3 allows combining with AGPL.

### pillow

- Kind: dependency
- Version: 12.3.0
- Licence: MIT-CMU (HPND-style, permissive)
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### pluggy

- Kind: dependency
- Version: 1.6.0
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### polars

- Kind: dependency
- Version: 1.44.2
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### polars-runtime-32

- Kind: dependency
- Version: 1.44.2
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### protobuf

- Kind: dependency
- Version: 7.36.2
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### psutil

- Kind: dependency
- Version: 7.2.2
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### pyclipper

- Kind: dependency
- Version: 1.4.0
- Licence: MIT
- Use: shipped (installed as a dependency of RapidOCR)
- Source: package metadata in the installed environment
- Status: ok

### Pygments

- Kind: dependency
- Version: 2.21.0
- Licence: BSD-2-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### pymupdf

- Kind: dependency
- Version: 1.28.2
- Licence: AGPL-3.0 (dual licensed with an Artifex commercial licence)
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
- Note: Core PDF reader. This is one reason the project is AGPL (C-2).

### pyparsing

- Kind: dependency
- Version: 3.3.3
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### pytest

- Kind: dependency
- Version: 9.1.1
- Licence: MIT
- Use: internal only (development)
- Source: package metadata in the installed environment
- Status: ok
- Note: Development only.

### python-dateutil

- Kind: dependency
- Version: 2.9.0.post0
- Licence: BSD-3-Clause or Apache-2.0 (dual)
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### PyYAML

- Kind: dependency
- Version: 6.0.3
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### RapidOCR

- Kind: dependency
- Version: 3.10.0 (installs on Python 3.14), with PP-OCRv5's Latin recognition model (`latin_PP-OCRv5_rec_mobile`), which the package fetches from ModelScope and the project keeps in `models/ocr/`. Its dependencies have their own entries (colorlog, omegaconf, opencv-python-headless, pyclipper, shapely, tqdm).
- Licence: Apache-2.0 for the code. The models are converted from PaddleOCR's and are Apache-2.0 too, copyright Baidu and the PaddleOCR authors.
- Use: Chosen in Stage 2.0 as the OCR engine for text in images (titles, tempo and expression text, lyrics, chord symbols), shipped. It runs on ONNX Runtime, which the project already uses, and needs neither PaddlePaddle (not available for Python 3.14) nor a separate program. homr uses it for the same job. The Latin model reads the raster regression set's text better than the default Chinese and English one (93.2 against 92.0 percent of text boxes exact at 300 dpi; `docs/notes/raster-text-spec.md`). Tesseract (Apache-2.0, a separate program) is the fallback if the Latin model reads lyrics poorly.
- Source: github.com/RapidAI/RapidOCR licence section, and the package metadata, checked 17 October 2026.
- Status: ok

### requests

- Kind: dependency
- Version: 2.34.2
- Licence: Apache-2.0
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### ruff

- Kind: dependency
- Version: 0.17.2
- Licence: MIT
- Use: internal only (development)
- Source: package metadata in the installed environment
- Status: ok
- Note: Development only. The linter, run in CI.

### scikit-image

- Kind: dependency
- Version: 0.26.0
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### scipy

- Kind: dependency
- Version: 1.18.1
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### setuptools

- Kind: dependency
- Version: 78.1.0
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### shapely

- Kind: dependency
- Version: 2.2.0
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency of RapidOCR)
- Source: package metadata in the installed environment
- Status: ok

### six

- Kind: dependency
- Version: 1.17.0
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### sympy

- Kind: dependency
- Version: 1.14.0
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### tifffile

- Kind: dependency
- Version: 2026.9.20
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### torch

- Kind: dependency
- Version: 2.14.1+cu130
- Licence: BSD-3-Clause (plus third-party licences listed in the wheel, all permissive)
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### torchvision

- Kind: dependency
- Version: 0.29.1
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### tqdm

- Kind: dependency
- Version: 4.70.1
- Licence: MPL-2.0 and MIT
- Use: shipped (installed as a dependency of RapidOCR)
- Source: package metadata in the installed environment
- Status: ok
- Note: MPL is file-level copyleft. MPL-2.0 section 3.3 allows combining with AGPL.

### typing_extensions

- Kind: dependency
- Version: 4.16.0
- Licence: PSF-2.0
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### ultralytics

- Kind: dependency
- Version: 8.4.173
- Licence: AGPL-3.0
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
- Note: YOLO training and inference. Its AGPL licence is the other reason for C-2.

### ultralytics-platform

- Kind: dependency
- Version: 0.1.80
- Licence: AGPL-3.0-only
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
- Note: Pulled in by ultralytics.

### ultralytics-thop

- Kind: dependency
- Version: 2.2.2
- Licence: AGPL-3.0
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
- Note: Pulled in by ultralytics.

### urllib3

- Kind: dependency
- Version: 2.8.0
- Licence: MIT
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

### verovio

- Kind: dependency
- Version: 6.3.0
- Licence: LGPL-3.0-only
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
- Note: Used through its Python bindings, as a library, which LGPL allows.

### webcolors

- Kind: dependency
- Version: 25.10.0
- Licence: BSD-3-Clause
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok
