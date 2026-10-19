"""Train the symbol detector (Phase 2, Stage 2.3).

YOLO11 nano at 640 pixel tiles, batch 8, FP16, 2 data-loading workers, on
the GPU (docs/notes/training-benchmark.md). The tiles are the Stage 2.1
detector data (generated/training/detector on the corpus drive). Runs are
written to <corpus>/runs/detector/<name>; the weights of every epoch's end
are kept there (weights/last.pt), so a stopped run carries on with --resume.
A plain-text progress log, one line an epoch, is written beside them.

Pausing: training looks at continue.txt in the repository's folder about
once a minute. While it says "yes", training goes on; otherwise it waits,
with the model kept on the GPU, and carries on from the same batch when the
file says "yes" again. The file is made, saying "yes", when a run starts
without one. To stop altogether (to restart the laptop), end the run and
carry it on later with --resume, from the last finished epoch.

Augmentation keeps the labels' meaning: no flips (a flipped clef or flat is
another symbol, or none), no colour changes beyond brightness, and no
change of scale unless --scale-aug is given, so the render-scale test
compares the scales the tiles were rendered at.

usage: python scripts/train_detector.py lists
           write the render-scale test's tile lists (scale-narrow and scale-wide)
       python scripts/train_detector.py train NAME [--data YAML] [--epochs N] [--fraction F]
           [--scale-aug S] [--resume]

e.g.   python scripts/train_detector.py train scale-narrow --data scale-narrow.yaml --epochs 15
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

from omr import paths
from omr.corpus import raster_labels as rl
from omr.log import ProgressLog

WEIGHTS = "benchmark/weights/yolo11n.pt"   # on the corpus drive
NARROW = (14.0, 20.0)                      # staff space in pixels, the render-scale test's narrow range
CONTROL = paths.REPO_ROOT / "continue.txt"   # training goes on while it says "yes", and waits otherwise
CONTROL_BATCHES = 20                         # batches between looks at it (about a minute)
CONTROL_WAIT = 30                            # seconds between looks while paused


def may_continue():
    try:
        return CONTROL.read_text(encoding="utf-8").strip().lower() == "yes"
    except OSError:
        return False


def wait_while_paused(log):
    """Hold training while continue.txt does not say "yes". The model stays
    on the GPU, and training carries on from the same batch."""
    if may_continue():
        return
    log.info(f"paused: {CONTROL} does not say yes. Write yes in it to carry on.")
    paused = time.time()
    while not may_continue():
        time.sleep(CONTROL_WAIT)
    log.info(f"carrying on after {(time.time() - paused) / 60:.0f} minutes paused.")


def detector_dir():
    return paths.require_corpus_dir() / "generated" / "training" / "detector"


def tile_spaces(root):
    """{page key: staff space in pixels} for the pages that were cut into tiles."""
    wanted = {t.stem.rsplit("-", 2)[0] for split in ("train", "val") for t in (root / "detector" / "images" / split).iterdir()}
    spaces = {}
    for f in (root / "pages").glob("*/*/page-*.json"):
        key = f"{f.parent.parent.name}-{f.parent.name}-p{f.stem.split('-')[1]}"
        if key in wanted:
            spaces[key] = json.loads(f.read_text(encoding="utf-8"))["staff space px"]
    return spaces


def write_lists(log):
    """scale-narrow.txt: the training tiles rendered at a staff space of 14 to
    20 pixels; scale-wide.txt: as many tiles drawn at random from all of
    them (10 to 24). Both validate on every validation tile."""
    det = detector_dir()
    spaces = tile_spaces(det.parent)
    train = sorted((det / "images" / "train").iterdir())
    narrow = [t for t in train if NARROW[0] <= spaces[t.stem.rsplit("-", 2)[0]] <= NARROW[1]]
    wide = sorted(random.Random(20261018).sample(train, len(narrow)))
    for name, chosen in (("scale-narrow", narrow), ("scale-wide", wide)):
        (det / f"{name}.txt").write_text("".join(f"{t.as_posix()}\n" for t in chosen), encoding="utf-8")
        write_yaml(det / f"{name}.yaml", f"{name}.txt")
        log.info(f"{name}: {len(chosen)} training tiles.")
    in_range = sum(NARROW[0] <= spaces[t.stem.rsplit("-", 2)[0]] <= NARROW[1] for t in wide)
    log.info(f"scale-wide holds {in_range} tiles in the narrow range.")


def write_yaml(path, train):
    names = "\n".join(f"  {i}: {c}" for i, c in enumerate(rl.CLASSES))
    path.write_text(f"path: {path.parent.as_posix()}\ntrain: {train}\nval: images/val\nnames:\n{names}\n",
                    encoding="utf-8")


def train(args, log):
    from ultralytics import YOLO

    root = paths.require_corpus_dir()
    run = root / "runs" / "detector" / args.name
    last = run / "weights" / "last.pt"
    started = {}

    def epoch_start(trainer):
        started["t"] = time.time()

    def epoch_end(trainer):
        if trainer.epoch >= trainer.epochs:
            return   # the closing validation of the best weights, not an epoch
        m = trainer.metrics or {}
        log.info(f"epoch {trainer.epoch + 1} of {trainer.epochs}: {(time.time() - started['t']) / 60:.1f} minutes; "
                 f"validation precision {m.get('metrics/precision(B)', 0):.3f}, recall {m.get('metrics/recall(B)', 0):.3f}, "
                 f"mAP50 {m.get('metrics/mAP50(B)', 0):.3f}, mAP50-95 {m.get('metrics/mAP50-95(B)', 0):.3f}.")

    def batch_end(trainer):
        started["batches"] = started.get("batches", 0) + 1
        if started["batches"] % CONTROL_BATCHES == 0:
            wait_while_paused(log)

    if not CONTROL.is_file():
        CONTROL.write_text("yes\n", encoding="utf-8")
    if args.resume:
        if not last.is_file():
            log.error(f"there is no run to carry on at {last}")
            return
        model = YOLO(str(last))
    else:
        model = YOLO(str(root / WEIGHTS))
    model.add_callback("on_train_epoch_start", epoch_start)
    model.add_callback("on_fit_epoch_end", epoch_end)
    model.add_callback("on_train_batch_end", batch_end)
    paths.check_free_space(root)
    if args.resume:
        log.info(f"carrying on {args.name} from {last}.")
        model.train(resume=True)
        return
    data = detector_dir() / args.data
    log.info(f"training {args.name} on {data}, {args.epochs} epochs, fraction {args.fraction}, scale {args.scale_aug}.")
    model.train(data=str(data), epochs=args.epochs, imgsz=rl.TILE, batch=8, workers=2, device=0, amp=True,
                fraction=args.fraction, project=str(run.parent), name=args.name, exist_ok=True,
                fliplr=0.0, flipud=0.0, hsv_h=0.0, hsv_s=0.0, degrees=0.0, scale=args.scale_aug,
                max_det=1000, plots=False, verbose=False, seed=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["lists", "train"])
    parser.add_argument("name", nargs="?", help="the run's name (train)")
    parser.add_argument("--data", default="data.yaml", help="the YAML file in the detector data folder")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--fraction", type=float, default=1.0, help="share of the training tiles used, for a trial")
    parser.add_argument("--scale-aug", type=float, default=0.0, help="YOLO's random scale gain (0 for none)")
    parser.add_argument("--resume", action="store_true", help="carry on a stopped run")
    args = parser.parse_args()
    log_path = paths.REPO_ROOT / "logs" / f"train-detector{'-' + args.name if args.name else ''}.log"
    log = ProgressLog("train_detector", log_path)
    if args.command == "lists":
        write_lists(log)
        return log.finish("tile lists written")
    if not args.name:
        log.error("a run needs a name")
        return log.finish("nothing trained")
    train(args, log)
    return log.finish(f"run {args.name} ended")


if __name__ == "__main__":
    sys.exit(main())
