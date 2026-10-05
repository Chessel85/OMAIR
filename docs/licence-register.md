# Licence register

Version 0.1, 5 October 2026. Covers requirement C-3.

This register records the licence of every dependency, dataset, model and tool used by the project. Like the other planning documents, it uses headings and lists only, so that it reads well with a screen reader.

This is a record of facts as found, not legal advice. Anything marked "owner to resolve" needs a decision from the owner. Licences marked "not verified" were written from memory and must be checked against the source before anything depends on them.

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

These need a decision or a check, roughly in order of importance:

- PDMX: Check each licence value in the metadata, and decide which are allowed. Share-alike and no-derivatives values need a decision.
- CPDL: Decide which CPDL licences may be stored in the public repository.
- Mutopia: Decide whether CC BY-SA pieces may be committed.
- DeepScores V2: Verify on the dataset page before any use.
- GrandStaff and Camera-GrandStaff: Find the licence. If none is stated, treat as internal comparison only.
- PrIMuS and Camera-PrIMuS: Verify. If it is non-commercial, it is internal comparison only and never shipped (C-3). Weights trained on it may be affected too.
- OLiMPiC: Find the licence.
- homr: Verify the licence of the code and of the weights separately.
- SMT (Sheet Music Transformer): Check the code and weights licences. If non-commercial, internal comparison only, never shipped.
- LEGATO: Check the licence. If non-commercial, internal comparison only, never shipped.
- pikepdf: MPL is file-level copyleft and is compatible with AGPL. Owner may want to confirm.
- All Python dependencies: licences were read from package metadata, which is sometimes vague. A fuller check can wait until the first release.

## Datasets

### PDMX

- Kind: dataset
- Version: 2024 release
- Licence: Per score: public domain or Creative Commons. The metadata carries a licence for each score.
- Use: Used to build the corpus. Only scores with a free licence may be kept in the public repository (C-4).
- Source: solution-design.md section 2.3. Not yet checked against the dataset page.
- Status: owner to resolve. Check each licence value in the metadata, and decide which are allowed. Share-alike and no-derivatives values need a decision.

### OpenScore

- Kind: dataset
- Version: Lieder corpus, string quartets and others
- Licence: CC0
- Use: Used to build the corpus. Output may be committed.
- Source: solution-design.md says CC0. Not yet checked against the repository.
- Status: ok

### CPDL

- Kind: dataset
- Version: current
- Licence: Per edition. Editions use the CPDL licence, Creative Commons or public domain, and some are not free.
- Use: Real PDFs with MusicXML or source files (C-6). Keep only free editions in the repository, and check the site terms (Stage 8).
- Source: solution-design.md section 2.3. The licence of each edition must be read at collection time.
- Status: owner to resolve. Decide which CPDL licences may be stored in the public repository.

### Mutopia

- Kind: dataset
- Version: current
- Licence: Per piece: public domain, CC BY or CC BY-SA.
- Use: LilyPond sources and PDFs for the corpus.
- Source: solution-design.md. Per-piece licences must be recorded at collection time.
- Status: owner to resolve. Decide whether CC BY-SA pieces may be committed.

### DeepScores V2

- Kind: dataset
- Version: v2
- Licence: Believed to be CC BY 4.0 (not verified).
- Use: Training data for symbol detection.
- Source: Recollection, not verified.
- Status: owner to resolve. Verify on the dataset page before any use.

### GrandStaff and Camera-GrandStaff

- Kind: dataset
- Version: current
- Licence: Unknown (not verified).
- Use: Training and testing data for the raster path.
- Source: No licence found yet.
- Status: owner to resolve. Find the licence. If none is stated, treat as internal comparison only.

### PrIMuS and Camera-PrIMuS

- Kind: dataset
- Version: current
- Licence: Believed to be CC BY-NC-SA 4.0, which is non-commercial (not verified).
- Use: Training and testing data for the raster path.
- Source: Recollection, not verified.
- Status: owner to resolve. Verify. If it is non-commercial, it is internal comparison only and never shipped (C-3). Weights trained on it may be affected too.

### OLiMPiC

- Kind: dataset
- Version: current
- Licence: Unknown (not verified).
- Use: Training and testing data for the raster path.
- Source: No licence found yet.
- Status: owner to resolve. Find the licence.

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
- Version: n/a
- Licence: AGPL-3.0
- Use: Starting point for the symbol detector. Fine-tuned weights are AGPL too, which fits C-2.
- Source: solution-design.md and recollection. Not yet checked.
- Status: ok

### homr

- Kind: model
- Version: to be pinned in Stage 9
- Licence: Believed to be AGPL-3.0 (not verified).
- Use: Baseline in Stage 9, and a possible starting point for the sequence reader.
- Source: solution-design.md and recollection. Not yet checked.
- Status: owner to resolve. Verify the licence of the code and of the weights separately.

### SMT (Sheet Music Transformer)

- Kind: model
- Version: to be pinned
- Licence: Unknown. Research weights are often non-commercial.
- Use: Possible starting point for the sequence reader.
- Source: solution-design.md and recollection. Not yet checked.
- Status: owner to resolve. Check the code and weights licences. If non-commercial, internal comparison only, never shipped.

### LEGATO

- Kind: model
- Version: to be pinned
- Licence: Unknown. Research weights are often non-commercial.
- Use: Baseline only, if its licence allows internal use.
- Source: solution-design.md and recollection. Not yet checked.
- Status: owner to resolve. Check the licence. If non-commercial, internal comparison only, never shipped.

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
- Licence: Believed GPL or LGPL (not verified)
- Use: internal only. Braille translator candidate for Phase 3. External process.
- Source: Not yet checked.
- Status: ok

### Sao Mai Braille Music Translator

- Kind: tool
- Version: see `docs/notes/tool-commands.md` where installed
- Licence: Unknown (not verified)
- Use: internal only. Braille translator candidate for Phase 3. External process.
- Source: Not yet checked.
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

These are used only to render test PDFs in Stage 5. The fonts are not shipped. The licences below are from memory and have not been checked.

### Leland

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: SIL OFL 1.1 (not verified)
- Use: internal only. Rendering test files.
- Source: recollection.
- Status: ok

### Bravura

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: SIL OFL 1.1 (not verified)
- Use: internal only. Rendering test files.
- Source: recollection.
- Status: ok

### Emmentaler

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: GPL-3.0 with font exception, or SIL OFL 1.1 (not verified)
- Use: internal only. Rendering test files.
- Source: recollection.
- Status: ok

### Gonville

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: GPL-2.0 or later with font exception (not verified)
- Use: internal only. Rendering test files.
- Source: recollection.
- Status: ok

### Petaluma

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: SIL OFL 1.1 (not verified)
- Use: internal only. Rendering test files.
- Source: recollection.
- Status: ok

### MuseJazz

- Kind: tool
- Version: as bundled with MuseScore or LilyPond
- Licence: SIL OFL 1.1 (not verified)
- Use: internal only. Rendering test files.
- Source: recollection.
- Status: ok

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
- Status: owner to resolve. MPL is file-level copyleft and is compatible with AGPL. Owner may want to confirm.
- Note: MPL is file-level copyleft and is compatible with AGPL. Owner may want to confirm.

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

### requests

- Kind: dependency
- Version: 2.34.2
- Licence: Apache-2.0
- Use: shipped (installed as a dependency)
- Source: package metadata in the installed environment
- Status: ok

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
