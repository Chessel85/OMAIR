@echo off
rem Fine-tune the sequence reader (Stage 2.6) on the GPU, with 2 data-loading
rem workers, from homr's checkpoint 465, or carry on a stopped run.
rem   run_train_sequence.cmd NAME [--resume]
rem Progress goes to E:\OMAIRCorpus\runs\sequence\NAME\progress.txt (a line
rem every 500 steps and one at each check); everything printed, warnings
rem included, to train.log beside it. Start it with conhost --headless or
rem from Task Scheduler, so it does not depend on a terminal or a Claude Code
rem session staying open.
rem
rem Pausing: write no in continue.txt in the repository's folder; training
rem waits within 20 steps and carries on when the file says yes again.
rem Ending the process stops it; run this again with --resume to carry on
rem from the last 1,000-step save. If training fails, it is carried on from
rem that save by itself, up to 3 times.

if "%~1"=="" (
  echo Give the run a name, for example: run_train_sequence.cmd s26-run1
  exit /b 2
)
cd /d "%~dp0.."
set OMR_CORPUS_DIR=E:\OMAIRCorpus
set RUN=E:\OMAIRCorpus\runs\sequence\%~1
if not exist "%RUN%" mkdir "%RUN%"
".venv\Scripts\python.exe" scripts\train_sequence.py %* >> "%RUN%\train.log" 2>&1
set CODE=%errorlevel%
set TRIES=0
:again
if %CODE%==0 exit /b 0
if not exist "%RUN%\last.pt" exit /b 1
if %TRIES% geq 3 exit /b 1
set /a TRIES+=1
echo %date% %time% training failed; carrying on from the last save (try %TRIES% of 3) >> "%RUN%\train.log"
".venv\Scripts\python.exe" scripts\train_sequence.py %~1 --resume >> "%RUN%\train.log" 2>&1
set CODE=%errorlevel%
goto again
