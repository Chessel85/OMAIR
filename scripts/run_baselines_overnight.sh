#!/bin/sh
# Stage 9: run Audiveris, then homr, over the baseline sample, 3 pairs at once, CPU only.
# Timings from this run are inflated by the parallel load; the one-at-a-time pilot gives clean ones.
# musicdiff is skipped here for speed; re-run it later with --predictions on the outputs.
. .venv/Scripts/activate
for r in audiveris homr; do
  omr evaluate --set development --set-root "$OMR_CORPUS_DIR/generated/baseline-sample" \
    --recogniser $r --workers 3 --cpu-only --no-musicdiff --timeout 900 \
    --out "$OMR_CORPUS_DIR/evaluations/baseline-sample-$r" > "$OMR_CORPUS_DIR/evaluations/baseline-sample-$r.log" 2>&1
done
