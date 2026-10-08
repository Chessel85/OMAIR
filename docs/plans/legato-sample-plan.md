# LEGATO sample plan (Stage 9)

Version 0.1, 7 October 2026. Like the other plans, it uses headings and lists only.

## Purpose

Record a LEGATO baseline for Stage 9 on a spread of real scores. LEGATO is a development baseline only (never shipped, see the licence register). It takes about 20 minutes a page on the CPU, so it cannot run over the whole baseline sample. It runs a night at a time over a queue of about 35 scores, and results build up over several nights.

## What has been set up

- LEGATO is installed under `E:\OMAIRCorpus\tools\legato` (its own Python 3.12 environment, the code, and 21 GB of weights). `python -m omr.baselines legato PDF OUT` runs it, and `omr evaluate --recogniser legato` can use it.
- One-file test on 7 October: 57 minutes for 3 pages (1210, 1184 and 1010 seconds a page) with 3 threads. Note accuracy 99.3 percent under the clef rule (420 of 422 notes right, plus one clef error); 73.9 percent strict (see "Clef errors" below).
- `scripts/run_legato_sample.py` builds the queue, runs it until a time limit, and reports status. `scripts/run_legato_night.sh` is the one command that starts a night.

## The queue

- Made from the 60-score baseline sample, one pair per score, always the MuseScore 4 base export (Leland font). Using one engraver keeps the cost down. Engraver and font effects are already measured with the other tools.
- Scores of more than 4 pages are left out: 25 of 60. The queue holds 35 pairs and 67 pages, about 23 hours, so three nights.
- The order is a seeded round robin over genre and texture groups (19 groups), so that every night covers a spread, and any prefix of the queue is a fair sample.
- The queue is in `generated/legato-sample/queue.txt` on the corpus drive. It already exists. Rebuild it only before the first night, with `python scripts/run_legato_sample.py queue`.

## Progress

- Night 1 (7 to 8 October 2026, 10.5 hour limit): 12 pairs done, 74.3 percent note accuracy, about 19.5 minutes a page (faster than the 21 assumed). Pair 12 is suspect (a cut-short output), and pairs 13 to 35 were falsely marked failed at 06:41 (instant "no output", at the time of a memory shortage). See `docs/notes/baselines.md`.
- Before night 2: delete the `failure.txt` files and the pair 12 result under `evaluations/legato-sample-preds`, or the runner skips them. The night script now uses `--hours 10.5`.

## Starting a night

Last thing at night, in a terminal in the repository folder:

1. Make sure `OMR_CORPUS_DIR` is set and the E: drive is plugged in.
2. Stop the laptop sleeping. Plug in the mains, and set sleep to "never" while plugged in for the night. A sleeping laptop stalls the run, as noted for the earlier overnight runs. Do not close the lid unless closing it is set to do nothing.
3. Run: `sh scripts/run_legato_night.sh`
4. Leave it running. It uses 3 of the 4 cores. It stops by itself after 8.5 hours, and will not start a file that would not finish before then. It plans on 21 minutes a page.

The next night, run the same command. Finished pairs are skipped.

## In the morning

- The progress log has one line per event: `E:\OMAIRCorpus\evaluations\legato-sample.log`. The last line is a summary, such as "5 pairs (9 pages) done this run, 5 done in all, 30 still queued".
- Quick status: `python scripts/run_legato_sample.py status`
- A file that fails writes `failure.txt` beside its result with the reason. It is not retried. A file that takes more than twice its expected time is stopped and counted as failed.
- Each result is saved as it finishes, in `evaluations/legato-sample-preds/<id>/musescore4-base/`, with `score.musicxml` and `seconds.txt`.

## Scoring (a daytime job, not part of the night run)

After any night, score what exists. The command skips musicdiff for speed:

`omr evaluate --set development --set-root "$OMR_CORPUS_DIR/generated/legato-sample" --predictions "$OMR_CORPUS_DIR/evaluations/legato-sample-preds" --no-musicdiff --out "$OMR_CORPUS_DIR/evaluations/legato-sample"`

The index in `generated/legato-sample/index.txt` lists only the finished pairs, so no file is counted as failed because it has not been reached yet.

## Timings

Timings from the night runs are usable for OP-2 as the CPU-alone figure for LEGATO: one file at a time, 3 threads, nothing else heavy running. Do not run other heavy jobs, such as the Audiveris or homr timing run, during a LEGATO night. The model load takes about 6 seconds a file, which is small beside the reading.

## Clef errors (decision of 7 October 2026)

- The owner decided that a misread clef counts as one mistake, for all models. It is decision 10 in `docs/notes/evaluation-spec.md` ("Clef errors"), and the harness applies it, so the night runs are scored with it automatically.
- On the one-file test, LEGATO read a tenor part's octave-down treble clef as a plain treble clef. The clef rule moves those 110 notes back an octave: 108 are then right, and the clef counts as one error. Note accuracy is 99.3 percent; strict note accuracy (no clef rule) stays in the diagnostics at 73.9 percent.
- Other mistakes that move many notes (a missed octave line, key signature or triplet) still count every note. Note any file where one of these moves a whole part.

## Risks and fallbacks

- **LEGATO is slower on some scores than 21 minutes a page.** Dense pages give longer outputs (up to 2,048 tokens). The time limit protects the night. The estimate can be changed with `--minutes-per-page`.
- **Output that will not convert to MusicXML.** LEGATO's own repository lists many such failures for some other models and sets. Those pairs are logged as failures with the reason. Their share is a result in itself, not something to hide.
- **Not enough nights.** Stop whenever there are enough finished pairs, and say how many were scored.
- **Greedy decoding.** Beam size 1 would be several times faster. If time is short, it can run as a labelled variant on a small subset. It is not in this plan.
- **The drive or laptop fails overnight.** The run is resumable. A partly finished file is rerun from the start.
