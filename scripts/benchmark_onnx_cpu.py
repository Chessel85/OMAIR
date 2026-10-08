"""CPU inference speed of the stand-in sequence reader through ONNX Runtime (Stage 10).

  python scripts/benchmark_onnx_cpu.py

Exports the encoder and the decoder of each stand-in model from benchmark_training.py
(random weights; speed does not depend on them) and times them on the CPU with one
staff at a time. The decoder is timed for a full pass over N tokens. Greedy decoding
without a key-value cache repeats a pass for every new token, so the estimate for a
whole staff adds up passes for lengths 1..N (interpolated from the lengths timed).
Lines are written to <corpus>/benchmark/results/benchmark-onnx.log.
"""

import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_training import SEQ_MODELS, STAFF_HEIGHT, STAFF_WIDTH, VOCAB, build_seq_model  # noqa: E402

from omr import paths  # noqa: E402
from omr.log import ProgressLog  # noqa: E402

LENGTHS = [1, 32, 64, 128, 256]


def timed(session, feeds, repeats=10):
    session.run(None, feeds)
    session.run(None, feeds)
    times = []
    for _ in range(repeats):
        began = time.perf_counter()
        session.run(None, feeds)
        times.append(time.perf_counter() - began)
    return float(np.median(times))


def main():
    import onnxruntime as ort
    import torch

    torch.backends.mha.set_fastpath_enabled(False)  # the fused eval kernels do not export
    corpus = paths.require_corpus_dir()
    out_dir = corpus / "benchmark" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = ProgressLog("benchmark-onnx", out_dir / "benchmark-onnx.log")
    log.info(f"onnxruntime {ort.__version__}, torch {torch.__version__}, threads available "
             f"{torch.get_num_threads()}.")
    count = 0
    for label, layers, width, length in SEQ_MODELS:
        if length != 256:
            continue
        model = build_seq_model(layers, width, torch).eval()
        params = sum(p.numel() for p in model.parameters()) / 1e6

        class Encoder(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.m = model

            def forward(self, image):
                return self.m.encoder_layers(self.m.encoder(image).flatten(2).transpose(1, 2))

        class Decoder(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.m = model

            def forward(self, tokens, memory):
                m = self.m
                x = m.embed(tokens) + m.position[:tokens.shape[1]]
                mask = torch.nn.Transformer.generate_square_subsequent_mask(tokens.shape[1])
                for layer in m.layers:
                    x = layer(x, memory, tgt_mask=mask)
                return m.out(x)

        image = torch.randn(1, 1, STAFF_HEIGHT, STAFF_WIDTH)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                enc_path = Path(tmp) / "enc.onnx"
                with torch.no_grad():
                    memory = Encoder()(image)
                    torch.onnx.export(Encoder(), (image,), str(enc_path), input_names=["image"],
                                      output_names=["memory"], opset_version=17, dynamo=False)
                    # the traced mask and reshapes fix the length, so export one decoder per length
                    for n in LENGTHS:
                        torch.onnx.export(Decoder(), (torch.randint(0, VOCAB, (1, n)), memory),
                                          str(Path(tmp) / f"dec{n}.onnx"), input_names=["tokens", "memory"],
                                          output_names=["logits"], opset_version=17, dynamo=False)
                opts = ort.SessionOptions()
                enc = ort.InferenceSession(str(enc_path), opts, providers=["CPUExecutionProvider"])
                dec = {n: ort.InferenceSession(str(Path(tmp) / f"dec{n}.onnx"), opts,
                                               providers=["CPUExecutionProvider"]) for n in LENGTHS}
                enc_s = timed(enc, {"image": image.numpy()})
                mem = memory.numpy()
                dec_s = {n: timed(dec[n], {"tokens": np.random.randint(0, VOCAB, (1, n)).astype(np.int64),
                                        "memory": mem}) for n in LENGTHS}
        except Exception as error:  # report and carry on with the next model
            log.warning(f"{label}: export or run failed: {type(error).__name__}: {error}")
            continue
        full = np.interp(np.arange(1, length + 1), LENGTHS, [dec_s[n] for n in LENGTHS]).sum()
        log.info(f"{label} ({params:.1f} M parameters): encoder {enc_s * 1000:.0f} ms per staff; decoder pass "
                 + ", ".join(f"{n} tokens {dec_s[n] * 1000:.0f} ms" for n in LENGTHS)
                 + f"; greedy decoding of {length} tokens without a cache about {(enc_s + full):.1f} s per staff.")
        count += 1
    return log.finish(f"{count} models measured")


if __name__ == "__main__":
    sys.exit(main())
