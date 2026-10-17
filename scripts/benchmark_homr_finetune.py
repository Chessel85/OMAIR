"""Can homr's sequence reader be fine-tuned on the laptop's GPU? (Phase 2, Stage 2.0)

Loads homr's own PyTorch model (training/architecture in the homr source) with
a released checkpoint, and runs a few training steps on random staff images and
token sequences at several batch sizes, one setting per child process so an
out-of-memory failure ends only that setting. Reports the parameters, the GPU
memory used on the whole card (as the Phase 0 benchmark did) and the seconds a
step. The data is random, so this measures memory and speed, not learning.

The homr source, its checkpoint and its training libraries are outside the
repository, on the corpus drive:

    <corpus>/tools/dl/homr-src/repo    git clone of github.com/liebharc/homr
    <corpus>/tools/dl/homr-src/ckpt    the unpacked checkpoint (.pth)
    <corpus>/tools/dl/homr-src/libs    timm, x-transformers, safetensors (pip --target)

usage: python scripts/benchmark_homr_finetune.py [--steps N] [--only N,N...]
"""

import argparse
import json
import subprocess
import sys
import time

from omr import paths
from omr.log import ProgressLog

# (label, batch, sequence length, encoder frozen)
SETTINGS = [
    ("batch 1, 608 tokens", 1, 608, False),
    ("batch 2, 608 tokens", 2, 608, False),
    ("batch 4, 608 tokens", 4, 608, False),
    ("batch 4, 256 tokens", 4, 256, False),
    ("batch 8, 256 tokens", 8, 256, False),
    ("batch 4, 608 tokens, encoder frozen", 4, 608, True),
    ("batch 8, 608 tokens, encoder frozen", 8, 608, True),
    ("batch 2, 608 tokens, encoder frozen", 2, 608, True),
    ("batch 8, 128 tokens", 8, 128, False),
    ("batch 4, 128 tokens, encoder frozen", 4, 128, True),
    ("batch 8, 128 tokens, encoder frozen", 8, 128, True),
    ("batch 16, 128 tokens, encoder frozen", 16, 128, True),
]


def homr_dir():
    return paths.require_corpus_dir() / "tools" / "dl" / "homr-src"


def one_setting(batch, length, frozen, steps):
    """Runs in the child process. Returns a dict of figures."""
    base = homr_dir()
    sys.path[:0] = [str(base / "repo"), str(base / "libs")]
    import torch

    from homr.transformer.configs import Config
    from training.architecture.transformer.tromr_arch import TrOMR

    config = Config()
    model = TrOMR(config)
    checkpoint = next((base / "ckpt").rglob("*.pth"))
    missing, unexpected = model.load_state_dict(torch.load(checkpoint, weights_only=True, map_location="cpu"),
                                                strict=False)
    if frozen:
        model.freeze_encoder()
    model = model.cuda().train()
    params = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    optimiser = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-5)
    scaler = torch.amp.GradScaler("cuda")
    vocab = {"rhythms": config.num_rhythm_tokens, "pitchs": config.num_pitch_tokens,
             "lifts": config.num_lift_tokens, "articulations": config.num_articulation_tokens,
             "slurs": config.num_slur_tokens, "positions": config.num_position_tokens}
    total = torch.cuda.mem_get_info()[1]
    peak_used, times = 0, []
    for _ in range(steps):
        inputs = torch.rand(batch, 1, config.max_height, config.max_width, device="cuda")
        tokens = {k: torch.randint(3, n, (batch, length), device="cuda") for k, n in vocab.items()}
        mask = torch.ones(batch, length, dtype=torch.bool, device="cuda")
        torch.cuda.synchronize()
        start = time.perf_counter()
        with torch.autocast("cuda", dtype=torch.float16):
            loss = model(inputs=inputs, mask=mask, **tokens)["loss"]
        optimiser.zero_grad(set_to_none=True)
        scaler.scale(loss).backward()
        scaler.step(optimiser)
        scaler.update()
        torch.cuda.synchronize()
        times.append(time.perf_counter() - start)
        peak_used = max(peak_used, total - torch.cuda.mem_get_info()[0])
    later = times[2:] or times
    return {"parameters": params, "trainable": trainable, "missing keys": len(missing),
            "unexpected keys": len(unexpected), "card GB": round(total / 1024**3, 2),
            "used GB": round(peak_used / 1024**3, 2),
            "torch peak GB": round(torch.cuda.max_memory_reserved() / 1024**3, 2),
            "seconds a step": round(sum(later) / len(later), 2), "loss": round(float(loss), 2),
            "shared memory": peak_used >= total * 0.98}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--steps", type=int, default=6)
    parser.add_argument("--only", help="run only these settings, numbered from 1, as 2,5")
    parser.add_argument("--child", nargs=3, type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        batch, length, frozen = args.child
        print(json.dumps(one_setting(batch, length, bool(frozen), args.steps)))
        return 0
    out = paths.require_corpus_dir() / "benchmark" / "results"
    out.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("benchmark_homr_finetune", out / "homr-finetune.txt")
    chosen = [SETTINGS[int(n) - 1] for n in args.only.split(",")] if args.only else SETTINGS
    for label, batch, length, frozen in chosen:
        started = time.time()
        child = subprocess.run([sys.executable, __file__, "--steps", str(args.steps), "--child",
                                str(batch), str(length), str(int(frozen))],
                               capture_output=True, text=True, timeout=1800)
        lines = child.stdout.strip().splitlines()
        if child.returncode == 0 and lines:
            r = json.loads(lines[-1])
            log.info(f"{label}: {r['used GB']} of {r['card GB']} GB used on the card "
                     f"(torch peak {r['torch peak GB']}), {r['seconds a step']} seconds a step; "
                     f"{r['parameters'] / 1e6:.1f} million parameters, {r['trainable'] / 1e6:.1f} million trained; "
                     f"checkpoint keys missing {r['missing keys']}, unexpected {r['unexpected keys']}"
                     + ("; the card was full, so it may have spilled into shared memory" if r["shared memory"] else "")
                     + f" ({time.time() - started:.0f} s in all).")
        else:
            reason = "out of GPU memory" if "out of memory" in child.stderr.lower() else (child.stderr.strip().splitlines() or ["no output"])[-1]
            log.warning(f"{label}: failed, {reason}.")
    return log.finish(f"{len(chosen)} settings tried")


if __name__ == "__main__":
    sys.exit(main())
