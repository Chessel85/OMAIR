# Phase 0 progress log

Last updated 5 October 2026. This file records what has been done against `phase0.md`, so that work can resume in a new session. Update it at the end of each working session.

## Repository facts

- Local folder: `C:\Users\chess\github\OMR`. Remote: https://github.com/Chessel85/OMAIR (public). The names differ on purpose. The Python package and command are called `omr`.
- Branch `main` tracks `origin/main`. First commit `a0deef9`.
- Python 3.14.7 is installed alongside 3.13.3. The project environment is `.venv` in the repository folder (git-ignored).
- Commit messages end with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Shell notes for Windows: `git commit -F -` with a here-string does not work in PowerShell, so write the message to a file and use `git commit -F <file>`.

## Stage status

- **Stage 0, prerequisites: not started.** `scripts/check_environment.py` is not written.
- **Stage 1, skeleton: done**, with one gap (see below).
- Stages 2 to 11: not started.

## Stage 1 details

Done:

- Layout: `src/omr`, `tests`, `scripts`, `docs`, `corpus` and `models` (the last two git-ignored).
- AGPL-3.0 `LICENSE`, `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `.gitignore`, `pyproject.toml`.
- `omr` command with `inspect`, `evaluate` and `convert` stubs. Each prints "not implemented yet" and exits with status 2. Test: `tests/test_cli.py`.
- `scripts/smoke_test.py` imports every dependency and reports whether PyTorch sees the GPU.
- Dependencies: `requirements.in` (direct, unpinned), `requirements.txt` (pinned), `requirements-torch.txt` (PyTorch and torchvision, installed from the CUDA 13.0 index).
- Checked: all dependencies have Python 3.14 Windows wheels, so the fallback to 3.13 is not needed. Smoke test passes, PyTorch sees the NVIDIA T500 (driver 596.71) with CUDA 13.0, and 3 of 3 tests pass. The README steps were followed in a fresh environment and worked.

Gap: the "fresh clone" check was done by building a new environment in this working folder, not by cloning on another machine. Stage 2 CI on Linux will cover this further.

## Open points for the owner

- Stage 0 owner actions still to confirm: MuseScore 4 (`C:\Program Files\MuseScore 4`) and Git are installed, and the GitHub repository is done. MuseScore 3.3.4 is installed as a Microsoft Store package, with `MuseScore3.exe` in `C:\Program Files\WindowsApps\64051MuseScoreBVBA.MuseScoreNotationSoftware_3.3.4.0_x64__pz631wrhsw9tj\bin`. The folder name contains the version, so it changes on update. `check_environment.py` should find it with `Get-AppxPackage *MuseScore*` rather than a fixed path, and Stage 0 must test that the command line works from a Store install. Java, LilyPond and Dorico SE were not found on the path (Dorico SE may be elsewhere).
- Package and README titles still say OMR. The owner is happy with the local/remote name difference.

## Next steps

1. Stage 0: write `scripts/check_environment.py`, find the working MuseScore 3 and 4 command lines, record them in `docs/notes/tool-commands.md`, and check `nvidia-smi`.
2. Stage 2 (CI and conventions) and Stage 3 (licence register) in parallel.
