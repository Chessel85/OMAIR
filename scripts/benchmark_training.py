"""Stage 10 training-speed benchmark on the development laptop's GPU.

Two parts, each writing plain-text lines to <corpus>/benchmark/results:

  python scripts/benchmark_training.py yolo   fine-tune YOLO on the detection dataset
                                              (make it first with make_detection_dataset.py)
  python scripts/benchmark_training.py seq    a stand-in sequence reader (synthetic data)

Each YOLO setting runs in its own child process, so an out-of-memory failure
only ends that setting. GPU memory is the figure nvidia-smi reports for the
whole card (it includes the CUDA context, which is what has to fit in 2 GB).
Options: --quick runs a shorter list. See docs/notes/training-benchmark.md.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from omr import paths
from omr.log import ProgressLog

# (model, image size, batch, data loading workers)
YOLO_SETTINGS = [
    ("yolo11n.pt", 640, 8, 4),
    ("yolo11n.pt", 640, 16, 4),
    ("yolo11n.pt", 640, 32, 4),
    ("yolo11n.pt", 800, 8, 4),
    ("yolo11n.pt", 1024, 4, 4),
    ("yolo11n.pt", 1024, 8, 4),
    ("yolo11n.pt", 1024, 16, 4),
    ("yolo11s.pt", 640, 8, 4),
    ("yolo11s.pt", 1024, 4, 4),
    ("yolo11s.pt", 1024, 8, 4),
    ("yolo11n.pt", 640, 8, 0),
    ("yolo11n.pt", 640, 8, 2),
    ("yolo11n.pt", 640, 8, 8),
]
YOLO_QUICK = [YOLO_SETTINGS[0], YOLO_SETTINGS[4], YOLO_SETTINGS[10]]

# (label, decoder layers, model width, sequence length)
SEQ_MODELS = [("small", 4, 512, 256), ("medium", 6, 512, 256), ("large", 8, 512, 256),
              ("medium-long", 6, 512, 512)]
SEQ_BATCHES = [1, 2, 4, 8, 16]
STAFF_HEIGHT, STAFF_WIDTH = 128, 1024     # one cropped staff
VOCAB = 400


def gpu_memory_mb():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout
    return int(out.split()[0])


class MemoryWatcher(threading.Thread):
    """Poll the card's memory use once a second and keep the peak."""

    def __init__(self):
        super().__init__(daemon=True)
        self.peak = 0
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            self.peak = max(self.peak, gpu_memory_mb())
            time.sleep(1)


# ---------------------------------------------------------------- YOLO

def yolo_one(model_name, imgsz, batch, workers, epochs, out_dir):
    """Child process: train and print one JSON line with the epoch times."""
    import torch
    from ultralytics import YOLO

    weights = out_dir.parent / "weights" / model_name
    model = YOLO(str(weights))
    times, starts = [], {}

    def start(trainer):
        starts["t"] = time.time()

    def end(trainer):
        times.append(time.time() - starts["t"])

    model.add_callback("on_train_epoch_start", start)
    model.add_callback("on_train_epoch_end", end)
    data = out_dir.parent / "detection" / "data.yaml"
    model.train(data=str(data), epochs=epochs, imgsz=imgsz, batch=batch, workers=workers, device=0,
                amp=True, plots=False, val=False, cache=False, project=str(out_dir / "runs"),
                name=f"{weights.stem}-{imgsz}-{batch}-{workers}", exist_ok=True, verbose=False,
                pretrained=True, fraction=1.0)
    print("RESULT " + json.dumps({
        "epoch_seconds": times,
        "torch_peak_allocated_mb": torch.cuda.max_memory_allocated() / 2**20,
        "torch_peak_reserved_mb": torch.cuda.max_memory_reserved() / 2**20,
    }), flush=True)


def run_yolo(args, log, out_dir):
    settings = YOLO_QUICK if args.quick else YOLO_SETTINGS
    tiles = len(list((out_dir.parent / "detection" / "images" / "train").glob("*.png")))
    log.info(f"Training tiles: {tiles}. Each setting runs {args.epochs} epochs; the last epoch is reported.")
    rows = []
    for model, imgsz, batch, workers in settings:
        label = f"{model[:-3]}, tile {imgsz}, batch {batch}, workers {workers}"
        watcher = MemoryWatcher()
        watcher.start()
        began = time.time()
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", __file__, "yolo-one", model, str(imgsz), str(batch),
             str(workers), str(args.epochs)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        watcher.stop.set()
        result = None
        for line in proc.stdout.splitlines():
            if line.startswith("RESULT "):
                result = json.loads(line[7:])
        if result and result["epoch_seconds"]:
            epoch = result["epoch_seconds"][-1]
            rows.append((label, epoch, watcher.peak, result))
            log.info(f"{label}: {epoch:.1f} s per epoch ({tiles / epoch:.1f} tiles per second), "
                     f"card memory peak {watcher.peak} MB, PyTorch allocated peak "
                     f"{result['torch_peak_allocated_mb']:.0f} MB.")
        else:
            text = (proc.stdout or "") + (proc.stderr or "")
            reason = "ran out of GPU memory" if "out of memory" in text.lower() else "failed"
            tail = " ".join(text.strip().splitlines()[-2:])[:200]
            log.warning(f"{label}: {reason} after {time.time() - began:.0f} s. {tail}")
    return rows


# ---------------------------------------------------------------- sequence reader

def build_seq_model(layers, width, torch):
    nn = torch.nn
    from torch.utils.checkpoint import checkpoint

    def block(cin, cout, stride):
        return nn.Sequential(nn.Conv2d(cin, cout, 3, stride, 1, bias=False), nn.BatchNorm2d(cout),
                             nn.ReLU(inplace=True), nn.Conv2d(cout, cout, 3, 1, 1, bias=False),
                             nn.BatchNorm2d(cout), nn.ReLU(inplace=True))

    class Reader(nn.Module):
        def __init__(self):
            super().__init__()
            # 128 x 1024 staff crop -> 4 x 64 = 256 tokens of size `width`
            self.encoder = nn.Sequential(block(1, 64, 2), block(64, 128, 2), block(128, 256, 2),
                                         block(256, 512, 2), nn.Conv2d(512, width, 1))
            self.encoder_layers = nn.TransformerEncoder(
                nn.TransformerEncoderLayer(width, 8, width * 4, 0.1, batch_first=True, norm_first=True), 2)
            self.embed = nn.Embedding(VOCAB, width)
            self.position = nn.Parameter(torch.zeros(1024, width))
            self.layers = nn.ModuleList(
                nn.TransformerDecoderLayer(width, 8, width * 4, 0.1, batch_first=True, norm_first=True)
                for _ in range(layers))
            self.out = nn.Linear(width, VOCAB)
            self.use_checkpoint = True

        def forward(self, image, tokens):
            feat = self.encoder(image).flatten(2).transpose(1, 2)
            memory = self.encoder_layers(feat)
            x = self.embed(tokens) + self.position[:tokens.shape[1]]
            mask = torch.nn.Transformer.generate_square_subsequent_mask(tokens.shape[1], device=tokens.device)
            for layer in self.layers:
                if self.use_checkpoint and self.training:
                    x = checkpoint(layer, x, memory, mask, use_reentrant=False)
                else:
                    x = layer(x, memory, tgt_mask=mask)
            return self.out(x)

    return Reader()


def seq_step_stats(label, layers, width, length, batch, checkpointing, log):
    import torch

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    model = build_seq_model(layers, width, torch).cuda()
    model.use_checkpoint = checkpointing
    params = sum(p.numel() for p in model.parameters()) / 1e6
    opt = torch.optim.AdamW(model.parameters(), 1e-4)
    scaler = torch.amp.GradScaler()
    image = torch.randn(batch, 1, STAFF_HEIGHT, STAFF_WIDTH, device="cuda")
    tokens = torch.randint(0, VOCAB, (batch, length), device="cuda")
    name = f"{label} ({params:.1f} M parameters, {length} tokens, batch {batch}, checkpointing {'on' if checkpointing else 'off'})"
    watcher = MemoryWatcher()
    try:
        watcher.start()
        times = []
        for step in range(13):
            torch.cuda.synchronize()
            began = time.time()
            with torch.autocast("cuda", dtype=torch.float16):
                logits = model(image, tokens)
                loss = torch.nn.functional.cross_entropy(logits.reshape(-1, VOCAB).float(), tokens.reshape(-1))
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            torch.cuda.synchronize()
            if step >= 3:
                times.append(time.time() - began)
        watcher.stop.set()
        step_s = sum(times) / len(times)
        result = (name, step_s, batch / step_s, torch.cuda.max_memory_allocated() / 2**20, watcher.peak, params)
        log.info(f"{name}: {step_s * 1000:.0f} ms per step, {batch / step_s:.1f} staves per second, "
                 f"PyTorch peak {result[3]:.0f} MB, card peak {watcher.peak} MB.")
        return result
    except torch.cuda.OutOfMemoryError:
        watcher.stop.set()
        log.warning(f"{name}: ran out of GPU memory.")
        return None
    finally:
        del model, opt
        torch.cuda.empty_cache()


def run_seq(args, log):
    import torch

    rows = []
    wanted = args.models.split(",") if args.models else None
    for label, layers, width, length in SEQ_MODELS:
        if wanted and label not in wanted:
            continue
        for checkpointing in (True, False):
            for batch in SEQ_BATCHES:
                result = seq_step_stats(label, layers, width, length, batch, checkpointing, log)
                if result:
                    rows.append((label, length, batch, checkpointing) + result[1:])
                else:
                    break  # a bigger batch will not fit either
    return rows


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "yolo-one":
        model, imgsz, batch, workers, epochs = sys.argv[2:7]
        yolo_one(model, int(imgsz), int(batch), int(workers), int(epochs),
                 paths.require_corpus_dir() / "benchmark" / "results")
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["yolo", "seq"])
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--models", help="seq only: comma-separated model labels to run (default all)")
    args = ap.parse_args()
    corpus = paths.require_corpus_dir()
    paths.check_free_space(corpus)
    out_dir = corpus / "benchmark" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = ProgressLog(f"benchmark-{args.part}", out_dir / f"benchmark-{args.part}.log")
    log.info(f"GPU memory in use before the run: {gpu_memory_mb()} MB of 2048 MB.")
    rows = run_yolo(args, log, out_dir) if args.part == "yolo" else run_seq(args, log)
    return log.finish(f"{len(rows)} settings measured")


if __name__ == "__main__":
    sys.exit(main())
