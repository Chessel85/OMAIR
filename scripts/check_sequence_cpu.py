"""The sequence reader on the CPU: speed with homr's key-value cache, and
whether the INT8 decoder is good enough (Phase 2, Stage 2.6).

Exports the model to ONNX (the encoder, the cached decoder in FP32, and an
INT8 copy of the decoder, as homr quantises its released one), then reads
validation staff units one at a time through ONNX Runtime on the CPU with
both decoders. Reports the seconds a staff (encoder and decoder apart), the
symbol error rate of each against the true tokens, and how often the two
decoders read a staff differently. The units are drawn from the units of up
to 128 tokens and, in proportion, from the longer ones.

The weights are homr's checkpoint 465, or --weights (best.pt or last.pt from
scripts/train_sequence.py). Results go to <corpus>/runs/sequence/<name>:
the ONNX files in onnx/ and the log in cpu-check.txt.

usage: python scripts/check_sequence_cpu.py NAME [--weights PT] [--units N] [--threads N]
"""

import argparse
import sys
import time
from pathlib import Path

from omr import paths
from omr.log import ProgressLog
from omr.raster import sequence


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name")
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--units", type=int, default=60)
    parser.add_argument("--threads", type=int, default=0, help="ONNX Runtime threads (0 for its default)")
    args = parser.parse_args()
    import torch

    run = paths.require_corpus_dir() / "runs" / "sequence" / args.name
    run.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("check_sequence_cpu", run / "cpu-check.txt")
    weights = None
    if args.weights:
        weights = torch.load(args.weights, weights_only=False, map_location="cpu")
        weights = weights.get("model", weights)
    model = sequence.load_model(weights)
    started = time.time()
    encoder, decoder, int8 = sequence.export_onnx(model, run / "onnx")
    log.info(f"exported {args.weights or 'checkpoint 465'} in {time.time() - started:.0f} s: encoder "
             f"{encoder.stat().st_size / 1e6:.0f} MB, decoder {decoder.stat().st_size / 1e6:.0f} MB, "
             f"INT8 decoder {int8.stat().st_size / 1e6:.0f} MB.")

    data = sequence.sequence_dir()
    short = sequence.read_index(data / "index-val.txt")
    long = sequence.read_index(data / "index-val-long.txt")
    n_long = round(args.units * len(long) / (len(short) + len(long)))
    units = sequence.sample(short, args.units - n_long, seed=2) + sequence.sample(long, n_long, seed=2)
    readers = {"FP32": sequence.OnnxReader(encoder, decoder, args.threads),
               "INT8": sequence.OnnxReader(encoder, int8, args.threads)}
    seconds = {"encoder": 0.0, "FP32": 0.0, "INT8": 0.0}
    errors = {"FP32": 0, "INT8": 0}
    symbols = differ = 0
    readers["FP32"].read(sequence.staff_image(units[0][0]))   # the first run of a session is slow
    readers["INT8"].read(sequence.staff_image(units[0][0]))
    for image_path, tokens in units:
        image = sequence.staff_image(image_path)
        truth = sequence.truth_symbols(tokens)
        symbols += len(truth)
        t = time.perf_counter()
        context = readers["FP32"].encode(image)
        seconds["encoder"] += time.perf_counter() - t
        read = {}
        for kind, reader in readers.items():
            t = time.perf_counter()
            read[kind] = reader.decode(context)
            seconds[kind] += time.perf_counter() - t
            errors[kind] += sequence.symbol_errors(read[kind], truth)
        differ += [sequence.symbol_text(s) for s in read["FP32"]] != [sequence.symbol_text(s) for s in read["INT8"]]
    n = len(units)
    log.info(f"{n} staff units ({n_long} over 128 tokens), {symbols / n:.0f} symbols a staff on average, "
             f"ONNX Runtime threads {args.threads or 'default'}.")
    log.info(f"encoder {seconds['encoder'] / n:.2f} s a staff.")
    for kind in ("FP32", "INT8"):
        log.info(f"{kind} decoder: {seconds[kind] / n:.2f} s a staff ({1000 * seconds[kind] / symbols:.0f} ms a symbol), "
                 f"{(seconds['encoder'] + seconds[kind]) / n:.2f} s with the encoder; "
                 f"symbol error rate {100 * errors[kind] / symbols:.2f} percent.")
    log.info(f"the two decoders read {differ} of {n} staves differently; INT8 is "
             f"{seconds['FP32'] / max(seconds['INT8'], 1e-9):.2f} times as fast in the decoder.")
    return log.finish(f"CPU check of {args.name}")


if __name__ == "__main__":
    sys.exit(main())
