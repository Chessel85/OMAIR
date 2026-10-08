#!/bin/sh
# Stage 9 follow-up runs, in order (about 4 to 5 hours):
#  1. clean timings: Audiveris and homr over the 16-pair timing set, one at a time, CPU only;
#  2. Audiveris again on the 17 pairs it failed, after the wrapper fix (pages it cannot read
#     are skipped, large pages read at a lower resolution), then merged with the first outputs;
#  3. Audiveris and homr over the 40 real-world MuseScore.com pairs, 3 at once;
#  4. musicdiff and OMR-NED over the baseline-sample outputs, scored from the saved files.
# Each step writes to evaluations/ under the corpus folder, with a .log beside it.
. .venv/Scripts/activate
E="$OMR_CORPUS_DIR/evaluations"
G="$OMR_CORPUS_DIR/generated"
run() { name=$1; shift; omr evaluate --set development "$@" --out "$E/$name" > "$E/$name.log" 2>&1; }

for r in audiveris homr; do
  run baseline-timing-$r --set-root "$G/baseline-timing" --recogniser $r --workers 1 --cpu-only --no-musicdiff --timeout 1800
done

run baseline-sample-audiveris-retry --set-root "$G/baseline-sample-audiveris-retry" --recogniser audiveris \
  --workers 3 --cpu-only --no-musicdiff --timeout 1800
python scripts/make_baseline_subsets.py merge "$E/baseline-sample-audiveris" "$E/baseline-sample-audiveris-retry" \
  "$E/baseline-sample-audiveris-merged-outputs"

for r in audiveris homr; do
  run realworld-$r --set-root "$G/realworld" --recogniser $r --workers 3 --cpu-only --no-musicdiff --timeout 900
done

run baseline-sample-audiveris-final --set-root "$G/baseline-sample" --predictions "$E/baseline-sample-audiveris-merged-outputs" --workers 3
run baseline-sample-homr-final --set-root "$G/baseline-sample" --predictions "$E/baseline-sample-homr" --workers 3
echo done > "$E/followup.done"
