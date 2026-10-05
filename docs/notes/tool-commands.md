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

## Java (Eclipse Temurin OpenJDK 25.0.4.1)

- Installed by the owner from `OpenJDK25U-jdk_x64_windows_hotspot_25.0.4.1_1.msi`.
- It went in as a per-user install: `C:\Users\chess\AppData\Local\Programs\Eclipse Adoptium\jdk-25.0.4.101-hotspot\bin\java.exe`. It was not on the PATH in the shell that was already open, so `check_environment.py` also looks in that folder. Needed for Audiveris and FreeDots (Stage 9).

## Not installed

- **Dorico SE:** parked. It is not accessible with a screen reader, so it is not installed and not used for now. Stage 5 proceeds with MuseScore 4, MuseScore 3, LilyPond and Verovio. Revisit if Dorico becomes usable.

## NVIDIA

- `nvidia-smi` works. GPU: NVIDIA T500, driver 596.71, which reports CUDA 13.2.
