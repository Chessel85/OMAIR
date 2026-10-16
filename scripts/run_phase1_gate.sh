#!/bin/sh
# Stage 1.7 runs, in order (about an hour on 3 workers):
#  1. clean timings: omr over the 16-pair timing set, one at a time, CPU only, as the baselines were timed;
#  2. the regression set, 3 at once;
#  3. the 40 real-world MuseScore.com pairs, 3 at once;
#  4. the full development set, 3 at once, without musicdiff;
#  5. the baseline sample scored from the development outputs (no new reading), with musicdiff,
#     for a like-for-like comparison with Audiveris, homr and LEGATO.
# Each step writes to evaluations/ under the corpus folder, with a .log beside it.
. .venv/Scripts/activate
E="$OMR_CORPUS_DIR/evaluations"
G="$OMR_CORPUS_DIR/generated"
run() { name=$1; shift; omr evaluate --set development "$@" --out "$E/$name" > "$E/$name.log" 2>&1; }

run gate-timing-omr --set-root "$G/baseline-timing" --recogniser omr --workers 1 --cpu-only --no-musicdiff
omr evaluate --set regression --set-root regression --recogniser omr --workers 3 --no-musicdiff \
  --out "$E/gate-regression-omr" > "$E/gate-regression-omr.log" 2>&1
run gate-realworld-omr --set-root "$G/realworld" --recogniser omr --workers 3 --no-musicdiff
run gate-development-omr --recogniser omr --workers 3 --no-musicdiff
run gate-baseline-sample-omr --set-root "$G/baseline-sample" --predictions "$E/gate-development-omr" --workers 3
echo done > "$E/gate.done"
