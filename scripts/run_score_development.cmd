@echo off
rem Score the raster development set from the saved detections
rem (scripts\run_detect_development.cmd must have run) and the saved OCR
rem readings, at 300 and 200 dpi, or at the one version given.
rem   run_score_development.cmd NAME [g300 or g200]
rem Results go to E:\OMAIRCorpus\evaluations\NAME-g300 and NAME-g200, with
rem progress in NAME-g300.log and NAME-g200.log there (one line a pair).
rem About 2 to 2.5 hours a version on 3 CPU workers, no GPU, once the OCR
rem readings are saved; about 6 to 6.5 hours a version the first time.
rem Start it from Task Scheduler, so it does not depend on a terminal or a
rem Claude Code session staying open.
rem
rem Pausing: write no in continue.txt in the repository's folder; the run
rem lets the pairs already started finish and waits, and carries on when
rem the file says yes again (it looks every 30 seconds). Ending the task
rem stops it; run this again to start over (detections and readings
rem already saved are read back, not made again).

if "%~1"=="" (
  echo Give the run a name, for example: run_score_development.cmd s25-dev
  exit /b 2
)
set VERSIONS=g300 g200
if not "%~2"=="" set VERSIONS=%~2

cd /d "%~dp0.."
set OMR_CORPUS_DIR=E:\OMAIRCorpus
set OMR_DETECTOR=E:\OMAIRCorpus\runs\detector\full\weights\best.pt
set OMR_DETECTIONS_DIR=E:\OMAIRCorpus\detections
set YOLO_OFFLINE=true
set YOLO_AUTOINSTALL=false
for %%v in (%VERSIONS%) do (
  ".venv\Scripts\omr.exe" evaluate --set development --set-root E:\OMAIRCorpus\generated\raster\development-%%v --recogniser omr --no-musicdiff --pausable --out E:\OMAIRCorpus\evaluations\%~1-%%v > "E:\OMAIRCorpus\evaluations\%~1-%%v.log" 2>&1
)
