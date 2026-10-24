@echo off
rem Stage 2.4: score the raster development set at 300 and 200 dpi from the
rem saved detections (scripts\run_detect_development.cmd must have run).
rem About 3 hours on 3 CPU workers, no GPU.
rem Start it from Task Scheduler, so it does not depend on a terminal or a
rem Claude Code session staying open.
rem
rem The scoring cannot pause or resume: end the task to stop it, and run
rem this again to start both versions over.
rem Progress: E:\OMAIRCorpus\evaluations\s24-dev-g300.log and -g200.log
rem (one line a pair).

cd /d "%~dp0.."
set OMR_CORPUS_DIR=E:\OMAIRCorpus
set OMR_DETECTOR=E:\OMAIRCorpus\runs\detector\full\weights\best.pt
set OMR_DETECTIONS_DIR=E:\OMAIRCorpus\detections
set YOLO_OFFLINE=true
set YOLO_AUTOINSTALL=false
for %%v in (g300 g200) do (
  ".venv\Scripts\omr.exe" evaluate --set development --set-root E:\OMAIRCorpus\generated\raster\development-%%v --recogniser omr --no-musicdiff --out E:\OMAIRCorpus\evaluations\s24-dev-%%v > "E:\OMAIRCorpus\evaluations\s24-dev-%%v.log" 2>&1
)
