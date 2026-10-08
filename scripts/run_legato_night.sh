#!/bin/sh
# Stage 9: one night of LEGATO over the sample queue, CPU only, one file at a time (3 threads).
# Safe to run again the next night: finished pairs are skipped. See docs/plans/legato-sample-plan.md.
. .venv/Scripts/activate
python scripts/run_legato_sample.py run --hours 10.5
