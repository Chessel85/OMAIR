# OMR to MusicXML and Braille Music: Solution Design

Version 0.2, 5 October 2026.

This document is written for screen readers (NVDA is the reference). It uses headings and lists throughout and contains no tables or ASCII diagrams. Requirement IDs, such as OUT-2 or C-6, refer to `requirements.md`.

## 1. Summary

The project is a free, open-source tool (AGPL-3.0) that converts sheet music PDFs and images into accurate MusicXML and braille music. It runs fully offline on an ordinary laptop. It aims to beat existing tools on accuracy, and it reports in plain text where it is unsure.

The central design decisions are:

1. **Treat different inputs differently.** A PDF exported from engraving software usually still contains the music as font glyphs: each notehead, clef and rest is a character from a music font, stored at an exact position. Reading those characters directly is close to lossless and needs no image recognition. That is the biggest accuracy gain available, and it is the focus of Phase 1. Image recognition is only needed for PDFs that contain page images, and for scans and photos.
2. **Make AI part of the product, alongside explicit rules.** Neural networks handle what rules do badly: finding symbols in noisy images, finding the music area on a photographed page, and flattening curved pages. Explicit musical rules then check and correct the result, for example by requiring that each voice in a bar adds up to the time signature, and that pitches stay consistent with the key signature.
3. **Use several recognition methods and compare them.** Where independent methods agree, confidence is high. Where they disagree, the musical rules choose between them, and anything left unresolved goes into the confidence report.
4. **Verify without sight.** The system renders its own MusicXML back to an image and compares that image with the input. Together with a ground-truth corpus, this means accuracy is measured by software, not by eye.
5. **Keep braille output pluggable.** Braille quality depends mostly on MusicXML quality. Braille is produced through an adapter layer that can drive existing translators. The default braille code and file format are an open decision (OI-1), to be made with the MuseScore community and braille-reading musicians.
6. **Run fully offline and at no cost (OP-1, C-5, C-7).** All models run locally, and no cloud or paid AI service is used at run time. Training is also done on the development laptop. This keeps the models deliberately small, and it means the system starts from pretrained weights and fine-tunes them instead of training from scratch.

## 2. Literature and technology review

### 2.1 How OMR works

OMR (Optical Music Recognition) is usually split into four stages:

1. Image preparation: deskew, remove noise, convert to black and white.
2. Symbol detection: find staff lines, noteheads, stems, beams, rests, clefs, accidentals and so on.
3. Notation assembly: link the symbols into musical objects. For example, a notehead plus a stem plus a beam makes an eighth note, and an accidental belongs to the note on its right.
4. Encoding: work out pitch, duration, voice and timing, then write MusicXML.

The reference survey is Calvo-Zaragoza, Hajič and Pacha, "Understanding Optical Music Recognition" (ACM Computing Surveys, 2020). Since about 2018 the field has had two main approaches:

- **Pipeline (modular) systems.** These detect symbols with object detectors or segmentation networks, then assemble them with rules or graphs.
  - Strengths: they are interpretable, every symbol has its own confidence, and errors can be traced to a cause.
  - Weakness: assembly is hard to get right for dense polyphonic music.
- **End-to-end systems.** A neural network reads an image of a staff, a system or a page and writes out a sequence of musical tokens directly, much as handwriting recognition writes out text.
  - Strength: they learn context, so they handle complex rhythms well.
  - Weaknesses: they need very large training sets, they can produce plausible but wrong music ("hallucination"), and their confidence is harder to pin to a location.

### 2.2 Notable systems

Open source:

- **Audiveris** (Java, AGPL). The most mature open-source pipeline OMR, and the engine behind MuseScore's PDF import. It relies heavily on rules and uses a neural network to classify symbols. It is reasonable on clean engravings and fragile on photos.
- **oemer** (Python). Segmentation networks (U-Net style) followed by rule-based assembly. It handles camera photos. Accuracy is moderate.
- **homr** (Python). Uses oemer-style segmentation to locate staves, then a transformer based on Polyphonic-TrOMR to read each staff. It targets camera photos and outputs MusicXML, covering pitch and rhythm but not dynamics or articulations. Of the existing open-source code, it is the closest to the raster path of this project.
- **Sheet Music Transformer (SMT) and SMT++** (Ríos-Vila, Calvo-Zaragoza and others, 2024 to 2025). End-to-end transformers for polyphonic and pianoform music. SMT++ reads a full page without a separate layout step. They are trained largely on synthetic data, using curriculum learning.
- **LEGATO** (2025). A large pretrained end-to-end model for full-page and multi-page typeset scores. It outputs ABC notation, which converts to MusicXML. It was trained on more than 200,000 page images derived from PDMX and reports state-of-the-art results. It is too large for a 2 GB GPU, and its CPU speed decides whether it can serve as a run-time engine or only as a development baseline.
- **OLiMPiC / LMX** (Mayer, Straka, Hajič and Pecina, 2024). End-to-end pianoform OMR using "linearised MusicXML" (LMX), an output format that maps cleanly back to MusicXML. It is relevant if the project trains its own end-to-end model.

Commercial tools, listed for comparison only: PhotoScore, SmartScore, PlayScore 2, ScanScore, Newzik and the Soundslice scanner. None of them meets the accuracy target.

### 2.3 Datasets

- **PDMX** (Public Domain MusicXML, 2024). About 250,000 public-domain or freely licensed MuseScore scores, with metadata that includes genre. It is the main source of ground truth.
- **OpenScore** (the Lieder corpus, string quartets and others). High-quality transcriptions under CC0.
- **CPDL** (Choral Public Domain Library). Many editions publish the PDF together with MusicXML or the original Sibelius or Finale file. This makes CPDL the main source of real Sibelius and Finale ground truth (C-6).
- **Mutopia.** LilyPond sources and PDFs.
- **DeepScores V2.** About 255,000 synthetic pages with a bounding box for every symbol. It is the standard dataset for training symbol detectors.
- **GrandStaff and Camera-GrandStaff; PrIMuS and Camera-PrIMuS; OLiMPiC.** Collections of systems and incipits, clean and camera-distorted, for training and testing the raster path.
- **MUSCIMA++.** Handwritten music. Not in scope.

The most important dataset is the one the project generates itself. MusicXML from PDMX or OpenScore is rendered by several engravers (section 2.4), which gives exact pairs of PDF and MusicXML. **Verovio** writes SVG in which every graphical element carries the ID of the note it belongs to, so it gives pixel-exact symbol labels for training. Photo-style distortions are added on top.

### 2.4 Engraver diversity without Sibelius or Finale

Sibelius and Finale are not available to the project (C-6), yet their PDFs are common and must be supported (IN-1). The corpus therefore combines several sources:

- **MuseScore 4 and MuseScore 3,** with several notation fonts: Leland, Bravura, Emmentaler, Gonville, Petaluma, MuseJazz, and the SMuFL versions of Finale Maestro and Finale Broadway. MuseScore 3 and 4 also lay out pages differently. Batch export from the command line produces matching PDF and MusicXML pairs automatically.
- **Dorico SE** (free, with limits on the number of players), which uses its own engraving engine and Bravura.
- **LilyPond** (free), with its own engraving engine and the Emmentaler font, fed through musicxml2ly.
- **Verovio**, which also supplies the training labels.
- **Real Sibelius and Finale PDFs from CPDL and IMSLP.**
  - Where MusicXML is published alongside the PDF, the pair is ground truth.
  - Where it is not, the PDF is still useful for three things: building font mapping tables (for example Opus and legacy Maestro), measuring the mix of PDF types, and testing with ground-truth-free checks (the bar arithmetic rules and the re-render check).

### 2.5 Vector PDF extraction

Engraving software usually writes music symbols as text in a music font. Common fonts are:

- MuseScore: Leland, Bravura, Emmentaler.
- Sibelius: Opus, Helsinki and others.
- Finale: Maestro (legacy encoding, or the SMuFL version from Finale 27 onwards).
- Dorico: Bravura.

SMuFL fonts give every symbol a fixed code point. Staff lines, stems, barlines and beams are drawn as lines and filled shapes.

**PyMuPDF** lists every glyph with its font, code point and exact position, and every line and filled shape. This gives:

- exact noteheads, rests, clefs, accidentals, dynamics and articulations;
- exact staff-line positions, so pitch comes from geometry with no ambiguity;
- real text (titles, tempo marks, lyrics, chord symbols, instrument names) without OCR.

The hard cases are:

- **Non-SMuFL fonts** (legacy Maestro, Opus, Emmentaler) need one mapping table per font. Each table is built once, and can be learned automatically from CPDL pairs or from MuseScore renders.
- **Outlined glyphs.** Some exports turn glyphs into outlines (plain shapes) or use Type 3 fonts. Each distinct shape is fingerprinted and identical shapes are grouped together, so each unique shape only needs labelling once. Labelling is automatic, by matching against reference renderings.
- **Assembly** is still required: which stem belongs to which notehead, what a beam implies, and how notes form chords and voices. But it starts from exact data.

No published OMR system is known to use this approach systematically. It is the project's main advantage for born-digital input.

### 2.6 Photos and scans

- **Page detection and dewarping.** Find the page edges, correct the perspective, and flatten the curve near the spine. Options include classical geometry and learned dewarping models (DocTr, DewarpNet, UVDoc). Staff lines must be straight and evenly spaced, which makes them a strong guide to curvature. Ordinary text documents have nothing as reliable.
- **Layout analysis.** Separate music systems from text blocks, pictures, page numbers, the spine shadow and the surface the book rests on. A small object detector (from the YOLO family, or RT-DETR) does this, trained on composites: rendered music placed on real page and desk backgrounds, with added text blocks.
- **Illumination correction and binarisation.** Sauvola or Otsu thresholding, or a small learned model for uneven lighting.

### 2.7 Braille music

- **Standards.**
  - The *New International Manual of Braille Music Notation* (Krolick, 1997) is the international basis.
  - National codes and formatting rules differ: in North America, the BANA *Music Braille Code 2015*; in the UK, RNIB and UKAAF guidance; elsewhere, other national authorities.
  - The default is an open decision (OI-1).
- **Existing translators from MusicXML to braille:**
  - Sao Mai Braille and SM Music Braille: free and widely used. A macOS version (SM BungSang) appeared in 2026.
  - FreeDots: open source, Java, with MIDI playback.
  - The OpenSheetMusicDisplay braille module: open source, documented in 2026.
  - music21's `braille` module: Python, covering part of the code.
  - Commercial tools, for comparison only: GOODFEEL and BME2.
- **Implication.** Wrong notes in the MusicXML give wrong braille. Most of the project's effort therefore goes into recognition accuracy, while braille is produced through an adapter that can call any of these translators. Whether to adapt an existing translator or write a dedicated one is decided in Phase 3. That decision rests on a comparison judged by braille-reading musicians.

### 2.8 Measuring accuracy

- **musicdiff** (Python, built on the work of Foscarin et al.) gives note-level differences between two scores. It is used in both the test reports and the evaluation harness.
- **OMR-NED and TEDn** (tree edit distance on MusicXML) are the standard research metrics. They are reported so that results can be compared with published work.
- **Project metrics** measure pitch, onset and duration accuracy, per note and per bar, plus structural correctness and how well the confidence flags match the real errors (requirements ACC-1 to ACC-6).

## 3. Technologies

Everything listed here is free, runs offline, and works from the command line or a text editor.

- **Language: Python 3.14.** It has the strongest ecosystem for both machine learning and music, and it works well with a screen reader.
- **PDF handling: PyMuPDF** (AGPL) extracts glyphs, vector shapes and embedded images, and rasterises pages. **pikepdf** is used for low-level inspection.
- **Image processing: OpenCV and scikit-image.**
- **Machine learning:**
  - **PyTorch** for training.
  - **ONNX Runtime** for inference on the CPU, with optional CUDA acceleration for small models on the T500.
  - **Ultralytics YOLO** (AGPL) or **RT-DETR** for detection.
  - **Hugging Face** for pretrained transformer weights.
- **Music representation:**
  - **music21** (BSD) for the internal score model, MusicXML writing and analysis.
  - **partitura** as an alternative if music21 proves too slow.
- **Rendering:** the MuseScore 3 and 4 command line, Dorico SE, LilyPond, and **Verovio** (LGPL, Python bindings).
- **Evaluation:** musicdiff, pytest and the project's own metric scripts.
- **OCR, for text in images only:** Tesseract or PaddleOCR. Both run locally. Vector PDFs need no OCR.
- **Braille:** an adapter layer over music21 braille, the OpenSheetMusicDisplay braille module, FreeDots and Sao Mai, with the choice driven by configuration.
- **Infrastructure:**
  - A public GitHub repository and issue tracker.
  - GitHub Actions for tests and the regression set.
  - GitHub Releases for model weight files.
  - Corpora kept outside the repository.
- **Training compute: the development laptop, at no cost (C-5, C-7).** See section 4.9 for how training fits within a 2 GB GPU. Free Kaggle (about 30 GPU hours a week) or Colab quotas are an optional accelerator only.

## 4. Solution architecture

The system is a pipeline of separate stages. Each stage passes on its results with confidence scores, and keeps alternative interpretations wherever it is unsure, so that a later stage can still correct an earlier one.

### 4.1 Stage 1: Ingest and classify

The input can be PDF, PNG, JPEG or TIFF. Each page is classified as one of four types:

- **Type A: vector PDF with music-font glyphs.** Goes to the vector path.
- **Type B: vector PDF with outlined glyphs.** Goes to the vector path, with shape fingerprinting.
- **Type C: a PDF with a clean embedded page image, or a clean digital image.** Goes to the raster path.
- **Type D: a photo or scan of a physical page.** Goes to page preparation, then the raster path.

If a page mixes types, its music content decides the type.

### 4.2 Stage 2: Page preparation (Type D only)

1. Find the page or pages, and split two-page spreads at the spine.
2. Correct the perspective and dewarp, using straight staff lines as the target.
3. Correct the illumination and binarise.
4. Run layout analysis: keep the music systems and discard text blocks, pictures and background. Text near a system is kept, because it may be a title, tempo mark, lyric or chord symbol.

### 4.3 Stage 3: Recognition

**Vector path (Types A and B):**

1. Extract glyphs, lines and filled shapes, with their exact positions.
2. Map each glyph to a symbol, using SMuFL code points or the per-font mapping tables.
3. Find the staves, then the systems, then the parts.
4. Attach every symbol to a staff and work out its vertical position in staff steps.
5. Sort the text into categories: title, tempo, expression, lyric, chord symbol and instrument name.

**Raster path (Types C and D):**

1. Detect the staff lines and remove them, recording their positions.
2. **Engine 1, the symbol detector:** an object detector that gives each symbol a bounding box and a confidence score. It starts from DeepScores-trained weights and is fine-tuned on the project's renders.
3. **Engine 2, the sequence reader:** an end-to-end transformer that reads each staff or system. It starts from homr or SMT weights and is fine-tuned. Its size is limited so that it runs on a CPU within the OP-3 time targets.
4. **Audiveris (optional)** runs as a separate external process and gives a third opinion. Running it as a separate process keeps the licensing simple.

### 4.4 Stage 4: Notation assembly

This stage builds a graph of musical objects from the symbols:

- Noteheads connect to stems, stems to flags or beams, and accidentals and dots to their notes.
- Notes that share a stem form a chord.
- Ties, slurs, tuplets and grace notes are identified.
- **Pitch** comes from staff position, clef, key signature, the accidentals in force in the bar, and octave lines.
- **Duration** comes from the notehead type, flags or beams, dots and tuplets.
- **Voices** are assigned from stem direction, horizontal alignment and rests.
- Lyrics attach to notes, and chord symbols to beats.

### 4.5 Stage 5: Musical reasoning and correction

This stage applies explicit musical rules and scores each candidate reading:

- **Bar arithmetic.** Each voice must add up to the time signature, allowing for pickup bars, cadenzas and repeat endings.
- **Vertical alignment.** Events that sound together must be aligned across staves and parts.
- **Key and accidental consistency.** An accidental lasts until the barline, and a key signature persists until a change is marked.
- **Range plausibility.** An implausibly high or low note points to a wrong clef or a missed octave line.
- **Repetition.** Repeated bars and sequences are common. A bar that nearly matches its neighbours probably matches them exactly.
- **Engine agreement.** Candidates from the different engines are combined.

**Method.** Each uncertain decision keeps its top few candidates, with probabilities. A search picks the combination that satisfies the rules with the highest total probability. Beam search is used in general, and integer linear programming for difficult bars. A bar is flagged if its best reading still breaks a rule, or if the engines strongly disagree about it.

### 4.6 Stage 6: Self-check by re-rendering (DEV-3)

1. Render the output MusicXML with Verovio, using the layout detected on the input (system breaks and staff sizes).
2. Align the rendering with the original page, system by system.
3. Compare the symbols, and for clean input also the pixels. Bars that differ have their confidence lowered.

### 4.7 Stage 7: Output

- **MusicXML 4.0 (OUT-1).** Contains:
  - structure, pitch, duration, voices, ties and tuplets;
  - where recognised: dynamics, hairpins, articulations, slurs, text, lyrics and chord symbols;
  - beaming where available, though nothing depends on it.
- **Braille (OUT-2).** Produced through the adapter layer. The code, formatting and file format are set in configuration, with the defaults to be decided under OI-1.
- **MIDI (OUT-5).** For listening checks. The output can also be opened in MuseScore 4, which has built-in screen-reader support, for bar-by-bar review with NVDA.
- **Confidence report (OUT-3 and OUT-4).** Plain text that reads well with a screen reader. Examples:
  - "Summary: 64 bars, 61 high confidence, 3 flagged."
  - "Page 2, system 3, bar 14, right hand: the voices add up to 7 eighth notes in 4/4. Most likely a missing dot on beat 2. Confidence: low."
  - "Page 1, bar 6: the engines disagree on the third note, F sharp 5 or G 5. Chose F sharp 5 because the key is D major."

### 4.8 Stage 8: Evaluation harness (DEV-1, DEV-2)

- Runs the pipeline over the corpus and compares the output with the ground truth.
- Reports per-file and overall metrics, broken down by engraver, font, genre and texture. The breakdown shows where accuracy falls short.
- Runs a fixed regression set in GitHub Actions on every change. The set contains only public-domain material, in keeping with C-4.

### 4.9 Training on the development laptop

All training runs on the laptop: an NVIDIA T500 GPU with 2 GB of memory, a 4-core (8-thread) CPU and 32 GB of RAM. Training is designed around those limits.

How much training each part needs:

- **The vector path (Phase 1) needs no training.** It uses geometry, font tables and rules. Most born-digital PDFs will go through this path.
- **Rendering training data is CPU work.** The training images come from rendering scores in MuseScore and Verovio. The 4 cores handle this in overnight batches.
- **The symbol detector and the layout detector are small detection models** with a few million parameters, such as YOLO nano or small. Fine-tuning them from pretrained weights fits in 2 GB, with these techniques:
  - training on image tiles (for example 640 to 1024 pixels) instead of whole pages;
  - small batches, combined with gradient accumulation;
  - mixed precision (FP16). The T500 has no tensor cores, but it runs FP16 at twice its FP32 speed, and FP16 halves memory use.
- **The sequence reader is the heaviest model.** It is kept small: a compact image encoder with a small transformer decoder, in the region of 20 to 40 million parameters. Each staff is cropped and processed separately, so the input images stay small. The model starts from homr or SMT weights and is fine-tuned, not trained from scratch. It also uses gradient checkpointing (which saves memory by recomputing some values instead of storing them), FP16, and batch sizes of 1 to 4 with accumulation.
- **Large models (LEGATO, SMT++ at full size) are not trained.** They appear only as development baselines, run on the CPU if their speed allows.

Practical arrangements:

- **Runs are long and unattended.** A fine-tuning run is expected to take from several hours to a few days. Runs save checkpoints regularly so they can be stopped and resumed, which allows overnight running and recovery from interruptions. Progress goes to a plain-text log that can be read with NVDA.
- **The GPU is benchmarked in Phase 0.** The actual training speed on the T500 is measured early, and model sizes are fixed to fit within a few days per run (C-7).
- **Training uses less data and more of the musical rules.** Synthetic data is chosen carefully rather than in bulk: the training set focuses on the symbols and layouts where the evaluation harness shows errors. The musical-rules layer (Stage 5) corrects a good share of the errors that a smaller model makes.

### 4.10 Interfaces

- **Command line (AX-1).** For example: `omr convert score.pdf --musicxml score.musicxml --braille score.brf --report score.txt`. The tool also has an `omr inspect` command, which describes a PDF's type and fonts, and an `omr evaluate` command, which runs the harness.
- **Later options:** a watch-folder mode, a MuseScore plugin, or a simple accessible front end.

## 5. Resources

### 5.1 People and roles

- **Project owner.** Sets direction and priorities, decides which errors matter most, generates and curates the corpus, liaises with the MuseScore and blind-musician communities, and supplies photos and scans in Phase 4.
- **Claude, through Claude Code.** Design, code, tests, training scripts and analysis of results.
- **Braille-reading musicians** (volunteers from the MuseScore accessibility community, RNIB networks and similar groups). They decide the braille code (OI-1) and judge braille quality in Phase 3. Several reviewers are needed, because the owner does not read braille.
- **Optional sighted helper.** Occasional spot checks of hard cases.
- **Open-source contributors.** Welcome once the project is public. They will need a contributing guide and clear module boundaries.

### 5.2 Data

- **Generated corpus (the main corpus).** Scores selected from PDMX and OpenScore, sampled across genres and textures (REC-10). Each score is batch-exported through the MuseScore 3 and 4 command line in several fonts and styles, and through Dorico SE, LilyPond and Verovio. Every export is a matching pair of PDF and MusicXML. This is scripted, so no manual downloading is needed.
  - Development set: about 300 scores.
  - Regression set: about 50 scores.
  - Training material: thousands of scores, for the raster path.
- **Real-world corpus.**
  - Sibelius and Finale editions from CPDL that come with MusicXML or source files.
  - PDFs from IMSLP and CPDL without ground truth, used for the ground-truth-free checks.
  - Optionally, scores the owner downloads from MuseScore.com, kept locally (C-4).
- **Photo corpus (Phase 4).** Printed pages from the generated corpus, photographed with a phone in varied conditions (flat, open book, angled, dim light), plus some scans. 50 to 100 images is enough for evaluation, because the training data for photos is synthetic.
- **Licence register.** Records the licence of every dataset, model and dependency (C-3).

### 5.3 Hardware and accounts

- **Development laptop:** 4-core (8-thread) CPU and 32 GB of RAM.
- **GPU:** NVIDIA T500 with 2 GB of memory (Turing generation, CUDA 13.2 driver). It does all the training, within the limits described in section 4.9. It cannot train or run large transformers. For inference, the CPU through ONNX Runtime is the default, and the GPU is optional.
- **Accounts:** a GitHub account (public repository). A free Kaggle account is optional.
- **Disk space:** 100 to 200 GB for corpora, renders and models.

### 5.4 Software

Python, Git, MuseScore 3 and 4, Dorico SE, LilyPond, Verovio, Audiveris (as a baseline) and at least one braille translator (Sao Mai or FreeDots). All are free.

## 6. Plan

Durations are rough effort estimates, not calendar dates. Each phase ends with a measurable gate.

### Phase 0: Foundations (about 2 to 3 weeks)

- Set up the repository, the AGPL-3.0 licence, the Python environment, the tests and continuous integration.
- Write the PDF inspector (`omr inspect`).
- Write the corpus generator: PDMX and OpenScore scores, batch-exported through MuseScore, Dorico SE, LilyPond and Verovio.
- Write the evaluation harness (`omr evaluate`), including musicdiff and the project metrics.
- Start the licence register.
- Run baselines with Audiveris and homr, and with LEGATO if its CPU speed allows.
- Collect real Sibelius and Finale PDFs from CPDL and IMSLP, and measure the mix of PDF types and fonts.
- Benchmark training speed on the T500 with a short detector fine-tuning run.
- **Gate:** baseline numbers are recorded, the PDF-type mix is known, the OP-3 speed targets are confirmed, and model sizes are fixed so that training fits on the laptop.

### Phase 1: Vector PDF to MusicXML (about 6 to 10 weeks)

- Glyph extraction, font mapping tables (SMuFL first, then legacy Maestro, Opus and Emmentaler), and detection of staves, systems and parts.
- Notation assembly: pitch, duration, voices, lyrics and chord symbols.
- The musical-rules layer and the first version of the confidence report.
- The MusicXML writer, plus basic braille output through the adapter (music21 braille).
- **Gate:** ACC-1 is met on the vector corpus, including the CPDL Sibelius and Finale pairs.

### Phase 2: Clean raster input (about 8 to 12 weeks)

- The synthetic training-data generator (Verovio and MuseScore renders, with labels).
- Fine-tune the symbol detector and the sequence reader, and build the reconciliation step.
- The self-check by re-rendering.
- **Gate:** ACC-2 and ACC-4 are met.

### Phase 3: Braille and reporting quality (about 3 to 6 weeks, overlapping Phase 2)

- Resolve OI-1 with the MuseScore community and braille-reading musicians.
- Compare the translators on the corpus, with the braille readers judging.
- Decide whether to adapt an existing translator or build a dedicated one, and implement the chosen formatting.
- Refine the wording of the confidence report.

### Phase 4: Photos and scans (about 8 to 12 weeks)

- Page detection, dewarping and illumination correction.
- Layout analysis that separates music from text and background.
- Camera-style augmentation and fine-tuning, evaluated on the photo corpus.
- **Gate:** ACC-3 is met.

### Phase 5 (future): Older engravings

This phase starts only after the gates for Phases 1 to 4 are met (IN-4).

### Immediate next steps

1. Create the repository skeleton and the PDF inspector.
2. Build the corpus generator on PDMX, with MuseScore 4 batch export.
3. Build the evaluation harness and run the baselines.
4. In parallel, the project owner raises the braille question (OI-1) with the MuseScore community.

## 7. Risks and issues

1. **Risk: vector PDFs vary more than expected** (outlined glyphs, unusual fonts, unusual drawing order).
   - *Mitigation:* the inspector measures this in Phase 0, using real CPDL and IMSLP files. Shape fingerprinting covers outlined glyphs. The raster path is the fallback.
2. **Risk: little ground truth for Sibelius and Finale output** (C-6).
   - *Mitigation:* CPDL editions that include MusicXML or source files. MuseScore's SMuFL Finale fonts. Ground-truth-free checks on other real PDFs.
3. **Risk: polyphony and voice assignment are hard** (piano music, cross-staff beaming, voices that appear and disappear).
   - *Mitigation:* a rule-based voice solver plus engine agreement. Texture is widened gradually, and doubtful voices are reported.
4. **Risk: the broad range of genres widens the scope** (REC-10). Lyrics, chord symbols, lead sheets, choral layouts and ensemble scores all add work.
   - *Mitigation:* the corpus is sampled across genres, and metrics are reported per genre. Lyrics and chord symbols come almost free on the vector path. Tablature and percussion are deferred (REC-9).
5. **Risk: nobody can visually confirm the output.**
   - *Mitigation:* ground-truth comparison, the self-check by re-rendering, MIDI playback, screen-reader review in MuseScore 4, and calibrated confidence flags.
6. **Risk: the core team does not read braille.**
   - *Mitigation:* braille-reading reviewers are recruited early through the MuseScore and blind-musician communities. Existing, proven translators are reused. Braille stays pluggable until OI-1 is resolved.
7. **Risk: offline operation on a laptop limits model size** (OP-1, OP-2).
   - *Mitigation:* small, quantised models running on ONNX Runtime. The vector path needs no neural models at all. LEGATO-sized models are used only as development baselines, unless their CPU speed proves acceptable.
8. **Risk: laptop-only training limits model quality and makes iteration slow** (C-7).
   - *Mitigation:*
     - The vector path needs no training.
     - Models are small and fine-tuned from pretrained weights.
     - Training uses tiles and per-staff crops, FP16 and gradient checkpointing.
     - Runs go overnight and resume from checkpoints.
     - Training data is targeted at the observed errors.
     - The rules layer compensates for the smaller models.
     - Free Kaggle quota is available if a run proves too slow.
9. **Risk: end-to-end models hallucinate.**
   - *Mitigation:* their output is never accepted alone. It is always cross-checked against the detected noteheads and the musical rules.
10. **Risk: licence incompatibility** (C-2, C-3). Some research weights and datasets are for non-commercial use only, which conflicts with redistribution under AGPL.
    - *Mitigation:* the licence register. Non-commercial components are used only for internal comparison and never shipped.
11. **Risk: copyright of test material** (C-4).
    - *Mitigation:* the public repository holds only public-domain or freely licensed material. MuseScore.com downloads and other copyrighted scores stay in a git-ignored local folder.
12. **Risk: tools change quickly** (new OMR models appear often).
    - *Mitigation:* the engines sit behind a common interface, so a better model can be added as another engine.
13. **Risk: the development tools themselves may not be accessible** (AX-3).
    - *Mitigation:* command line and text throughout. No workflow needs a GUI.

## 8. Open decisions

- **OI-1: braille music code, formatting and file format.** The project owner is consulting the MuseScore community. This blocks Phase 3, but not Phases 0 to 2.
- **OI-2: speed targets.** Closed at the end of Phase 0: confirmed (see `docs/notes/phase-0-report.md`).
- **OI-3: error-flagging target.** To be refined in Phase 1.
