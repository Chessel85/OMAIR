# Tool command lines

Checked on 5 October 2026 on the development laptop (Windows 11). All commands run without opening a window and exit with status 0. Run `python scripts/check_environment.py` to see which tools are present.

## MuseScore 4 (4.7.5)

- Path: `C:\Program Files\MuseScore 4\bin\MuseScore4.exe`
- Convert, with the output format chosen by the extension: `MuseScore4.exe -o out.pdf in.musicxml`
- Works for `.pdf`, `.mscz` and `.musicxml` output. Converting a `.mscz` back to `.musicxml` also works.
- A one-bar test score took about 1 to 2 seconds.
- Version: `MuseScore4.exe --long-version`

## MuseScore 3 (3.3.4, Microsoft Store package)

- Path: `MuseScore3.exe` in the `bin` folder of the Store package. The folder name contains the version, so it changes on update. Find it with `(Get-AppxPackage *MuseScore*).InstallLocation`. `check_environment.py` does this.
- Same command form: `MuseScore3.exe -o out.pdf in.musicxml`
- The Store install can be run directly from its path, with no need for the Store app execution alias. PDF, `.mscz` and `.musicxml` output all work.
- It prints progress such as "success!" to standard error.
- Version: `MuseScore3.exe --version`

## LilyPond (2.26.0)

- Not on the PATH. Installed in `C:\Program Files\lilypond-2.26.0\bin`.
- `lilypond.exe` is there. `musicxml2ly` is a Python script, `musicxml2ly.py`, run with the `python.exe` that ships in the same folder: `python.exe musicxml2ly.py -o out.ly in.musicxml`
- Checked: it converted a one-bar MusicXML file to `.ly`. Rendering it with `lilypond.exe -o out in.ly` also worked and produced a PDF.

- musicxml2ly can be very slow on large files. On a 610 KB MusicXML file (the Maple Leaf Rag as written by music21) it ran for more than 30 minutes before it was stopped. The corpus generator must run it with a time limit (5 minutes is suggested) and record a timeout as a failure.
- LilyPond PDFs use the font Emmentaler-20 with no usable Unicode values: every music character comes out as U+FFFD, and only the glyph ID identifies the symbol.

## Music fonts and staff size in MuseScore

Checked on 5 October 2026 with a Bach chorale.

MuseScore 4:

- Choose the music font with a style file: `MuseScore4.exe -S style.mss -o out.pdf in.musicxml`. The style file needs only `<museScore version="4.70"><Style>` containing `<musicalSymbolFont>Bravura</musicalSymbolFont>` and `<musicalTextFont>Bravura Text</musicalTextFont>`.
- Fonts that work: Leland (the default), Bravura, Petaluma, Emmentaler, Gonville, MuseJazz, Finale Maestro and Finale Broadway.
- An unknown font name falls back to Bravura with exit status 0 and no message. Check the font in the PDF afterwards (`omr inspect --json`).
- Some fonts appear in the PDF under another name: Emmentaler as "MScore", Gonville as "Gootville", Finale Maestro as "FinaleMaestro". Finale Broadway exports also use a few Bravura glyphs.
- Staff size: the `scaling` element in the MusicXML overrides the style file, so set it there. `millimeters` is the size of 40 tenths, which is 4 staff spaces, so a 2.0 mm staff space is `<millimeters>8</millimeters>` with `<tenths>40</tenths>`. Setting `Spatium` in the style file had no effect when the MusicXML had a `scaling` element.

MuseScore 3 (3.3.4):

- The `-S` style file is loaded, but the music font in it is ignored.
- What works: convert to an uncompressed score first (`MuseScore3.exe -o score.mscx in.musicxml`), add `<musicalSymbolFont>Bravura</musicalSymbolFont>` just inside the score's `<Style>` element, then `MuseScore3.exe -o out.pdf score.mscx`.
- Fonts available in 3.3.4: Emmentaler (the default, shown in the PDF as "MScore"), Bravura, Gonville ("Gootville") and MuseJazz. Leland, Petaluma and the Finale fonts are not present and fall back to Bravura without an error.

## Verovio (6.3.0, Python bindings)

Verovio writes SVG, not PDF. The corpus converts the SVG to PDF with PyMuPDF, which needs two fixes first, or the page comes out blank or without stems and barlines:

- Set the options `svgViewBox: True` and `svgRemoveXlink: True`.
- Replace the inner `<svg class="definition-scale" ... viewBox="0 0 W H">` element with `<g transform="scale(S)">`, where S is the outer view box width divided by W, and its closing `</svg>` with `</g>`. PyMuPDF ignores the inner view box.
- Add `stroke="black"` to every element that has a `stroke-width` attribute. Verovio sets the stroke colour in a CSS style block, which PyMuPDF ignores.
- Then `pymupdf.open(stream=svg_bytes, filetype="svg").convert_to_pdf()` gives a one-page PDF. Join the pages with `insert_pdf`.
- Set the PDF creator to the Verovio version, because the converted file has no metadata.

The music symbols in the result are filled outlines, not font characters, so these are Type B pages. Text (titles, lyrics) stays as real text in Times.

## Running several exports at once

Measured on 6 October 2026, on mains power with the Balanced power plan. The processor is an Intel Core i7-1185G7, with 4 cores, 8 threads and 32 GB of memory. The test was the 6 export jobs for each of the first 4 development scores (24 jobs), run through `generate.run_export` into a scratch folder on the corpus drive.

- 1 worker: 93 seconds.
- 3 workers: 56 seconds, about 1.7 times faster.
- 4 workers: 54 seconds, hardly better than 3.
- Every job succeeded in every run, and every PDF had the same number of pages as the Stage 5 export made one at a time. So MuseScore 3, MuseScore 4, LilyPond and Verovio can all run as several copies at once without clashing.

The gain is smaller than the core count suggests, for two reasons, both measured with `typeperf`:

- One job at a time already kept the processor 30 to 35 percent busy, about 2.5 to 3 of the 8 threads, because MuseScore uses several threads of its own.
- With 3 workers the processor was 65 to 75 percent busy, but its clock speed fell from about 140 percent of the base speed to about 115 percent. That is the laptop's power limit.

So the default is 3 workers (`omr.parallel.DEFAULT_WORKERS`). It gives nearly all of the gain and leaves the machine usable during a batch.

## Java (Eclipse Temurin OpenJDK 25.0.4.1)

- Installed by the owner from `OpenJDK25U-jdk_x64_windows_hotspot_25.0.4.1_1.msi`.
- It went in as a per-user install: `C:\Users\chess\AppData\Local\Programs\Eclipse Adoptium\jdk-25.0.4.101-hotspot\bin\java.exe`. It was not on the PATH in the shell that was already open, so `check_environment.py` also looks in that folder. Needed for Audiveris and FreeDots (Stage 9).

## Not installed

- **Dorico SE:** parked. It is not accessible with a screen reader, so it is not installed and not used for now. Stage 5 proceeds with MuseScore 4, MuseScore 3, LilyPond and Verovio. Revisit if Dorico becomes usable.

## NVIDIA

- `nvidia-smi` works. GPU: NVIDIA T500, driver 596.71, which reports CUDA 13.2.
