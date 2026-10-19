#!/bin/sh
# Stage 2.3 render-scale test: the narrow and the wide run, one after the other.
# A finished run is skipped and a stopped one carries on from its last epoch.
# Pause with continue.txt (see scripts/train_detector.py).
cd "$(dirname "$0")/.."
for name in scale-narrow scale-wide; do
    run="$OMR_CORPUS_DIR/runs/detector/$name"
    if [ -f "$run/done" ]; then
        continue
    elif [ -f "$run/weights/last.pt" ]; then
        .venv/Scripts/python.exe scripts/train_detector.py train $name --resume || exit 1
    else
        .venv/Scripts/python.exe scripts/train_detector.py train $name --data $name.yaml --epochs 15 || exit 1
    fi
    touch "$run/done"
done
