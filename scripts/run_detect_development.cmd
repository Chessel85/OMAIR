@echo off
rem Stage 2.4: save the detector's detections for the raster development set
rem at 300 and 200 dpi (about 21,800 pages, about 6 hours on the GPU).
rem Start it from Task Scheduler, so it does not depend on a terminal or a
rem Claude Code session staying open.
rem
rem Pausing: write no in continue.txt in the repository folder; the pass
rem waits before its next score. Write yes to carry on.
rem Stopping: end the task. Run this again to resume; pages already saved
rem are skipped.
rem Progress: E:\OMAIRCorpus\detections\progress.log (one line a score),
rem and E:\OMAIRCorpus\detections\development-pass.out for any error.

cd /d "%~dp0.."
set OMR_CORPUS_DIR=E:\OMAIRCorpus
set YOLO_OFFLINE=true
set YOLO_AUTOINSTALL=false
".venv\Scripts\python.exe" scripts\detect_pages.py development g300 g200 >> "E:\OMAIRCorpus\detections\development-pass.out" 2>&1
