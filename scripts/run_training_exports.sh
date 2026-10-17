#!/bin/sh
# Stage 2.1 run 1: draw the raster engines' training scores, then export them.
# Both steps resume where they stopped. Logs are in logs/.
set -e
cd "$(dirname "$0")/.."
.venv/Scripts/python.exe scripts/build_corpus.py training-draw
.venv/Scripts/python.exe scripts/build_corpus.py training-export
