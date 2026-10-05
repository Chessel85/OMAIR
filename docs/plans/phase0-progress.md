# Phase 0 progress log

Last updated 5 October 2026 (Stage 3 session). This file records what has been done against `phase0.md`, so that work can resume in a new session. Update it at the end of each working session.

## Repository facts

- Local folder: `C:\Users\chess\github\OMR`. Remote: https://github.com/Chessel85/OMAIR (public). The names differ on purpose. The Python package and command are called `omr`.
- Branch `main` tracks `origin/main`. First commit `a0deef9`.
- Python 3.14.7 is installed alongside 3.13.3. The project environment is `.venv` in the repository folder (git-ignored).
- Commit messages end with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Shell notes for Windows: `git commit -F -` with a here-string does not work in PowerShell, so write the message to a file and use `git commit -F <file>`.

## Stage status

- **Stage 0, prerequisites: done** (Dorico SE parked). `scripts/check_environment.py` is written and reports Python, Git, MuseScore 3 and 4, LilyPond, musicxml2ly, Java, Dorico SE and nvidia-smi. Working command lines are in `docs/notes/tool-commands.md`. Both MuseScore versions convert headlessly. `nvidia-smi` reports the T500 with CUDA 13.2. **Dorico SE is parked**: it is not accessible with a screen reader, so it is dropped from Phase 0 for now and the script treats it as optional. Java (Temurin OpenJDK 25.0.4.1, installed by the owner from `OpenJDK25U-jdk_x64_windows_hotspot_25.0.4.1_1.msi` as a per-user install) is found by the script. All required tools are found. LilyPond renders a PDF from the converted file. The script exits with status 0.
- **Stage 1, skeleton: done**, with one gap (see below).
- **Stage 2, CI and conventions: done.** Added `.github/workflows/tests.yml` (Windows and Linux, Python 3.14, every push and pull request), `docs/conventions.md`, the shared logging helper `src/omr/log.py` and `tests/test_log.py`. Local tests pass (7 of 7). Pushed, and CI passed on Windows and Linux. Added `scripts/log_demo.py` and a README note about activating the environment in each new terminal, after the owner hit "No module named 'omr'" in a window without it. The owner found the log output fine and the timestamp tolerable. The owner confirmed the workflow is text based and fine with NVDA, so the remaining set-up, test and CI-reading checks were accepted without a full walk-through. Fix anything awkward if it turns up later.
- **Stage 3, licence register: done.** `docs/licence-register.md` has an entry for each of the 66 pinned dependencies (from package metadata) and for the datasets, models, tools and fonts (looked up by web search on 5 October 2026, source named per entry). `tests/test_licence_register.py` fails if a pinned dependency has no entry (9 of 9 tests pass). Three items were settled by default rules the owner can change: CPDL (only public domain, CC0 or CC BY editions in the public repo), Mutopia (same; CC BY-SA stays local) and OLiMPiC (CC BY-SA, internal only). LEGATO is a never-shipped baseline (gated weights, Llama encoder). Emmentaler, Gonville and MuseJazz licences are unconfirmed but they are not shipped.
- Stages 4 to 11: not started.

## Stage 1 details

Done:

- Layout: `src/omr`, `tests`, `scripts`, `docs`, `corpus` and `models` (the last two git-ignored).
- AGPL-3.0 `LICENSE`, `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `.gitignore`, `pyproject.toml`.
- `omr` command with `inspect`, `evaluate` and `convert` stubs. Each prints "not implemented yet" and exits with status 2. Test: `tests/test_cli.py`.
- `scripts/smoke_test.py` imports every dependency and reports whether PyTorch sees the GPU.
- Dependencies: `requirements.in` (direct, unpinned), `requirements.txt` (pinned), `requirements-torch.txt` (PyTorch and torchvision, installed from the CUDA 13.0 index).
- Checked: all dependencies have Python 3.14 Windows wheels, so the fallback to 3.13 is not needed. Smoke test passes, PyTorch sees the NVIDIA T500 (driver 596.71) with CUDA 13.0, and 3 of 3 tests pass. The README steps were followed in a fresh environment and worked.

Fresh-clone check: repeated in a later session by cloning https://github.com/Chessel85/OMAIR.git into a temporary folder and following the README. All dependencies installed, the smoke test passed with the GPU seen, and 3 of 3 tests passed. Stage 1 is fully done. Stage 2 CI on Linux will cover other machines.

## Open points for the owner

- Stage 0 owner actions still to confirm (Dorico SE is parked, so its install and player-limit check are no longer needed; Stage 5 uses the other engravers, per the plan's fallback of a smaller or no Dorico sample): MuseScore 4 (`C:\Program Files\MuseScore 4`) and Git are installed, and the GitHub repository is done. MuseScore 3.3.4 is installed as a Microsoft Store package, with `MuseScore3.exe` in `C:\Program Files\WindowsApps\64051MuseScoreBVBA.MuseScoreNotationSoftware_3.3.4.0_x64__pz631wrhsw9tj\bin`. The folder name contains the version, so it changes on update. `check_environment.py` should find it with `Get-AppxPackage *MuseScore*` rather than a fixed path, and Stage 0 must test that the command line works from a Store install. LilyPond 2.26.0 is installed in `C:\Program Files\lilypond-2.26.0` (not on the PATH; the script finds it). Java is installed (see Stage status). Dorico SE is parked (inaccessible with a screen reader). Git is installed and the repository exists.
- Package and README titles still say OMR. The owner is happy with the local/remote name difference.

## Next steps

1. Stages 4 and 5 (in parallel, Opus for the design parts).
