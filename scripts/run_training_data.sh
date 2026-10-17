#!/bin/sh
# Stage 2.1 run 2: once run 1 (run_training_exports.sh) has finished, make the
# training data from the exported pairs. Resumes where it stopped.
cd "$(dirname "$0")/.."
until grep -q "build-corpus-training-export: Summary" logs/run-training-exports.out 2>/dev/null; do
    sleep 300
done
.venv/Scripts/python.exe scripts/make_training_data.py --set training
