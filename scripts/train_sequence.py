"""Fine-tune the sequence reader, homr's staff transformer (Phase 2, Stage 2.6).

Starts from homr's checkpoint 465. The encoder is frozen and the decoder is
trained, at batch 4 on the staff units of up to 128 tokens, in FP16, with 2
data-loading workers: what fits the 2 GB card (phase2-progress.md, Stage 2.0).
The units are the Stage 2.1 data (generated/training/sequence on the corpus
drive). The learning rate warms up over the first steps, then falls on a
cosine to nothing at the end of the last pass.

Every --check-every steps the run is checked on fixed validation units: the
loss with the true tokens fed in, on --check-units units, and the symbol
error rate of greedy reading (symbols to change, add or remove, over the true
symbols), on --read-units units. The weights with the lowest symbol error
rate are kept as best.pt. The run stops early if that rate has not improved
for --patience checks. Step 0 is checked too, so homr's own figure on these
staves is the first line. Everything goes to <corpus>/runs/sequence/<name>:
progress.txt (one line every 500 steps and one a check), last.pt (weights,
optimiser and place, saved every 1,000 steps) and best.pt (weights only).

Pausing: training looks at continue.txt in the repository's folder every 20
steps (under a minute). While it says "yes", training goes on; otherwise it
waits, with the model kept on the GPU, and carries on from the same step when
the file says "yes" again. The file is made, saying "yes", when a run starts
without one. To stop altogether, end the run and carry it on later with
--resume, from the last 1,000-step save.

usage: python scripts/train_sequence.py NAME [--passes N] [--lr X] [--resume] [--steps N]
"""

import argparse
import math
import random
import sys
import time

from omr import paths, pause
from omr.log import ProgressLog
from omr.raster import sequence

BATCH = 4
WORKERS = 2
CONTROL_STEPS = 20
LOG_STEPS = 500
SAVE_STEPS = 1000
WARMUP = 1000
LOADER_TIMEOUT = 600   # seconds a batch may take to load before the run fails rather than hangs


def learning_rate(step, total, peak):
    if step < WARMUP:
        return peak * (step + 1) / WARMUP
    return peak * 0.5 * (1 + math.cos(math.pi * min(1.0, (step - WARMUP) / max(1, total - WARMUP))))


def check(model, units, readings, log, step):
    """Loss with the true tokens on `units` (a DataLoader) and the symbol
    error rate of greedy reading on `readings` ([(image, tokens)])."""
    import torch

    model.eval()
    loss, batches = 0.0, 0
    with torch.no_grad():
        for batch in units:
            batch = {k: v.cuda(non_blocking=True) for k, v in batch.items()}
            with torch.autocast("cuda", dtype=torch.float16):
                loss += float(model(**batch)["loss"])
            batches += 1
        errors = symbols = exact = 0
        for image, tokens in readings:
            truth = sequence.truth_symbols(tokens)
            read = model.generate(torch.from_numpy(sequence.staff_image(image))[None].cuda())
            wrong = sequence.symbol_errors(read, truth)
            errors += wrong
            symbols += len(truth)
            exact += wrong == 0
    model.train()
    model.encoder.eval()
    rate = 100 * errors / max(1, symbols)
    log.info(f"check at step {step}: validation loss {loss / max(1, batches):.4f}; greedy reading of "
             f"{len(readings)} units: symbol error rate {rate:.2f} percent, {exact} units read exactly.")
    return rate


def train(args, log):
    import torch
    from torch.utils.data import DataLoader

    root = paths.require_corpus_dir()
    run = root / "runs" / "sequence" / args.name
    last, best = run / "last.pt", run / "best.pt"
    data = sequence.sequence_dir()
    train_units = sequence.read_index(data / "index-train.txt")
    val_units = sequence.read_index(data / "index-val.txt")
    steps_a_pass = len(train_units) // BATCH
    total = args.steps or steps_a_pass * args.passes

    model = sequence.load_model()
    model.freeze_encoder()
    model.decoder.note_mask.requires_grad = False   # a fixed table in homr, though stored as a parameter
    model = model.cuda()
    model.train()
    model.encoder.eval()
    trained = [p for p in model.parameters() if p.requires_grad]
    optimiser = torch.optim.AdamW(trained, lr=args.lr, weight_decay=0.05)
    scaler = torch.amp.GradScaler("cuda")
    step, best_rate, since_best = 0, None, 0
    if args.resume:
        if not last.is_file():
            log.error(f"there is no run to carry on at {last}")
            return 1
        saved = torch.load(last, weights_only=False, map_location="cuda")
        model.load_state_dict(saved["model"])
        optimiser.load_state_dict(saved["optimiser"])
        scaler.load_state_dict(saved["scaler"])
        step, best_rate, since_best, total = saved["step"], saved["best rate"], saved["since best"], saved["total"]
        log.info(f"carrying on {args.name} from step {step} of {total}.")
    else:
        log.info(f"training {args.name}: {len(train_units)} training units ({steps_a_pass} steps a pass), "
                 f"{total} steps, batch {BATCH}, peak learning rate {args.lr}; "
                 f"{sum(p.numel() for p in trained) / 1e6:.1f} million parameters trained.")

    check_units = DataLoader(sequence.Units(sequence.sample(val_units, args.check_units)), batch_size=BATCH,
                             collate_fn=sequence.collate, num_workers=WORKERS, timeout=LOADER_TIMEOUT)
    readings = sequence.sample(val_units, args.read_units, seed=1)

    def save():
        torch.save({"model": model.state_dict(), "optimiser": optimiser.state_dict(), "scaler": scaler.state_dict(),
                    "step": step, "best rate": best_rate, "since best": since_best, "total": total},
                   last.with_suffix(".tmp"))
        last.with_suffix(".tmp").replace(last)

    def checked():
        nonlocal best_rate, since_best
        rate = check(model, check_units, readings, log, step)
        if best_rate is None or rate < best_rate:
            best_rate, since_best = rate, 0
            torch.save(model.state_dict(), best)
        else:
            since_best += 1
        return since_best >= args.patience

    pause.make_control()
    paths.check_free_space(root)
    if step == 0 and checked():
        return 0
    started, losses, stopped = time.time(), [], False
    while step < total and not stopped:
        done_this_pass = step % steps_a_pass
        order = list(range(len(train_units)))
        random.Random(step // steps_a_pass).shuffle(order)
        order = order[done_this_pass * BATCH:]
        loader = DataLoader(sequence.Units([train_units[i] for i in order]), batch_size=BATCH, drop_last=True,
                            collate_fn=sequence.collate, num_workers=WORKERS, pin_memory=True,
                            timeout=LOADER_TIMEOUT)
        for batch in loader:
            batch = {k: v.cuda(non_blocking=True) for k, v in batch.items()}
            for group in optimiser.param_groups:
                group["lr"] = learning_rate(step, total, args.lr)
            with torch.autocast("cuda", dtype=torch.float16):
                loss = model(**batch)["loss"]
            optimiser.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(optimiser)
            torch.nn.utils.clip_grad_norm_(trained, 1.0)
            scaler.step(optimiser)
            scaler.update()
            losses.append(loss.item())
            step += 1
            if step % LOG_STEPS == 0:
                rate = len(losses) * BATCH / (time.time() - started)
                log.info(f"step {step} of {total} (pass {step / steps_a_pass:.2f}): training loss "
                         f"{sum(losses) / len(losses):.4f}, {rate:.2f} units a second, "
                         f"about {(total - step) * BATCH / rate / 3600:.1f} hours left; "
                         f"GPU memory peak {torch.cuda.max_memory_reserved() / 1024**3:.2f} GB.")
                started, losses = time.time(), []
            if step % SAVE_STEPS == 0:
                save()
            if step % args.check_every == 0 or step == total:
                stopped = checked()
                save()
                started, losses = time.time(), []
                if stopped:
                    log.info(f"stopping early: no better symbol error rate in {args.patience} checks.")
            if step % CONTROL_STEPS == 0:
                paused = time.time()
                pause.wait_while_paused(log)
                started += time.time() - paused
            if stopped or step >= total:
                break
    save()
    log.info(f"best symbol error rate {best_rate:.2f} percent, weights in {best}.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name")
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--steps", type=int, default=0, help="stop after this many steps instead (a trial)")
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--check-every", type=int, default=5000)
    parser.add_argument("--check-units", type=int, default=1000)
    parser.add_argument("--read-units", type=int, default=200)
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run = paths.require_corpus_dir() / "runs" / "sequence" / args.name
    run.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("train_sequence", run / "progress.txt")
    code = train(args, log)
    return log.finish(f"run {args.name}") or code


if __name__ == "__main__":
    sys.exit(main())
