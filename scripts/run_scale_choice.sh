#!/bin/sh
# Stage 2.3 page-scale choice: the full run's weights scored on the fixed draw
# of 120 development pairs, as rendered and at 17, 20 and 22 pixels a staff
# space, one run after the other. A finished run (its summary.txt) is skipped.
# Pause with continue.txt (see src/omr/pause.py).
cd "$(dirname "$0")/.."
weights="$OMR_CORPUS_DIR/runs/detector/full/weights/best.pt"
for space in rendered 17 20 22; do
    name="s23-full-$space"
    [ -f "$OMR_CORPUS_DIR/evaluations/$name/summary.txt" ] && continue
    if [ "$space" = rendered ]; then
        .venv/Scripts/python.exe scripts/check_detector.py "$weights" development g300 g200 g150 --sample 120 --name "$name" || exit 1
    else
        .venv/Scripts/python.exe scripts/check_detector.py "$weights" development g300 g200 g150 --sample 120 --space "$space" --name "$name" || exit 1
    fi
done
