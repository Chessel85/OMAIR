"""The sequence reader, Engine 2 (Phase 2, Stage 2.6): homr's staff
transformer, fine-tuned on the project's staff units.

homr's source, checkpoint 465 and training libraries are on the corpus drive
in tools/dl/homr-src (AGPL-3.0); this module imports them from there, as
omr.corpus.sequence_units does. It holds what training and the CPU tests
share: the staff units as tensors, the model with its starting weights, the
ONNX export (the decoder with homr's key-value cache, and an INT8 copy), and
greedy reading through ONNX Runtime.
"""

import random
import sys

import numpy as np

from omr import paths

MEAN, STD = 0.7931, 0.1738   # homr's image normalisation


def homr_dir():
    return paths.require_corpus_dir() / "tools" / "dl" / "homr-src"


def use_homr():
    """Put homr's source and libraries on the import path."""
    base = homr_dir()
    for folder in (base / "libs", base / "repo"):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))


def sequence_dir():
    return paths.require_corpus_dir() / "generated" / "training" / "sequence"


def read_index(path):
    """[(image path, tokens path)] from a homr index file."""
    return [tuple(line.strip().split(",")) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def staff_image(path):
    """A staff image as homr's model takes it: grey, on homr's 256 by 1280
    canvas, normalised; float32 of shape (1, 256, 1280)."""
    import cv2

    use_homr()
    from homr.staff_parsing import add_image_into_tr_omr_canvas

    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"cannot read {path}")
    image = add_image_into_tr_omr_canvas(image)
    return ((image.astype(np.float32) / 255.0 - MEAN) / STD)[None]


def truth_symbols(path):
    use_homr()
    from training.transformer.training_vocabulary import read_tokens

    return read_tokens(str(path))


class Units:
    """Staff units for torch's DataLoader: the image and homr's six token
    branches with their mask, padded to homr's full length (the collate
    function cuts each batch to its longest unit)."""

    def __init__(self, entries):
        self.entries = entries

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, i):
        import torch

        use_homr()
        from training.transformer.training_vocabulary import to_decoder_branches

        image, tokens = self.entries[i]
        try:
            pixels = staff_image(image)
            b = to_decoder_branches(truth_symbols(tokens))
        except (ValueError, KeyError):
            # an unreadable image, or a mark homr's vocabulary has no token for (falloff,
            # plop, let ring: 0.15 percent of units); the next unit stands in, as homr's
            # loader does for an image and its token check does for the rest
            return self[(i + 1) % len(self)]
        return {"inputs": torch.from_numpy(pixels), "rhythms": b.rhythms, "pitchs": b.pitchs,
                "lifts": b.lifts, "articulations": b.articulations, "slurs": b.slurs,
                "positions": b.positions, "mask": b.mask}


def collate(items):
    import torch

    batch = {k: torch.stack([item[k] for item in items]) for k in items[0]}
    longest = int(batch["mask"].sum(dim=1).max())
    for k in batch:
        if k != "inputs":
            batch[k] = batch[k][:, :longest]
    return batch


def load_model(weights=None):
    """homr's training model with checkpoint 465, or with `weights` (a state
    dict saved by scripts/train_sequence.py) put over it."""
    import torch

    use_homr()
    from homr.transformer.configs import Config
    from training.architecture.transformer.tromr_arch import TrOMR

    model = TrOMR(Config())
    checkpoint = next((homr_dir() / "ckpt").rglob("*.pth"))
    missing, unexpected = model.load_state_dict(torch.load(checkpoint, weights_only=True, map_location="cpu"),
                                                strict=False)
    if missing or unexpected:
        raise ValueError(f"checkpoint 465 does not fit homr's model: {len(missing)} keys missing, "
                         f"{len(unexpected)} unexpected")
    if weights is not None:
        model.load_state_dict(weights)
    return model


def symbol_text(symbol):
    return f"{symbol.rhythm} {symbol.pitch} {symbol.lift} {symbol.articulation} {symbol.slur} {symbol.position}"


def edit_distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


def symbol_errors(read, truth):
    """Symbols to change, add or remove to turn what was read into the truth."""
    return edit_distance([symbol_text(s) for s in read], [symbol_text(s) for s in truth])


def sample(entries, n, seed=20261025):
    return sorted(random.Random(seed).sample(entries, min(n, len(entries))))


def export_onnx(model, out_dir):
    """Write encoder.onnx and decoder.onnx (with homr's key-value cache, as
    homr's own training/onnx/convert.py exports it) and decoder-int8.onnx
    (dynamic INT8 weights, as homr quantises its released decoder). Returns
    the three paths."""
    import torch

    use_homr()
    from homr.transformer.configs import Config
    from training.architecture.transformer.decoder import get_score_wrapper, init_cache

    class DecoderWrapper(torch.nn.Module):
        """homr's own (training/onnx/convert.py), whose module also imports
        the segmentation model's libraries."""

        def __init__(self, net):
            super().__init__()
            self.model = net

        def forward(self, rhythms, pitchs, lifts, articulations, slurs, context, cache_len, *cache):
            out = self.model(rhythms=rhythms, pitchs=pitchs, lifts=lifts, articulations=articulations, slurs=slurs,
                             context=context, cache_len=cache_len, mask=None, cache=cache,
                             return_center_of_attention=True)
            # the six branches' logits, the hidden state (left out), the attention, then the cache
            return (*out[:6], out[7], *out[8:])

    config = Config()
    out_dir.mkdir(parents=True, exist_ok=True)
    encoder_path, decoder_path, int8_path = (out_dir / "encoder.onnx", out_dir / "decoder.onnx",
                                             out_dir / "decoder-int8.onnx")
    encoder = model.encoder.eval().float().cpu()
    torch.onnx.export(encoder, torch.randn(1, 1, config.max_height, config.max_width), str(encoder_path),
                      export_params=True, opset_version=17, do_constant_folding=True,
                      input_names=["input"], output_names=["output"], dynamo=False)
    net = get_score_wrapper(config, attn_flash=False)
    net.load_state_dict({k[len("net."):]: v for k, v in model.decoder.state_dict().items() if k.startswith("net.")},
                        strict=True)
    wrapped = DecoderWrapper(net.eval()).eval()
    cache, cache_in, cache_out, dynamic, cache_len = init_cache(0, torch.device("cpu"))
    tokens = [torch.zeros((1, 1), dtype=torch.long) for _ in range(5)]
    context = torch.randn((1, 1280, config.encoder_dim))
    dynamic["context"] = {1: "cache_exists"}
    torch.onnx.export(wrapped, (*tokens, context, torch.tensor([cache_len]).long(), *cache), str(decoder_path),
                      input_names=["rhythms", "pitchs", "lifts", "articulations", "slurs", "context", "cache_len",
                                   *cache_in],
                      output_names=["out_rhythms", "out_pitchs", "out_lifts", "out_positions", "out_articulations",
                                    "out_slurs", "attention", *cache_out],
                      dynamic_axes=dynamic, opset_version=18, do_constant_folding=True, export_params=True,
                      dynamo=False)
    quantise_int8(decoder_path, int8_path)
    return encoder_path, decoder_path, int8_path


def quantise_int8(source, target):
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from onnxruntime.quantization.shape_inference import quant_pre_process

    prepared = target.with_name(target.stem + "-prepared.onnx")
    quant_pre_process(str(source), str(prepared))
    quantize_dynamic(str(prepared), str(target), weight_type=QuantType.QInt8)
    prepared.unlink()


class OnnxReader:
    """Greedy reading of one staff at a time on the CPU through ONNX Runtime,
    with homr's own cached decoding loop (homr/transformer/decoder_inference.py)."""

    def __init__(self, encoder_path, decoder_path, threads=0):
        import onnxruntime as ort

        use_homr()
        from homr.transformer.configs import Config
        from homr.transformer.decoder_inference import ScoreDecoder

        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        cpu = ["CPUExecutionProvider"]
        self.config = Config()
        self.encoder = ort.InferenceSession(str(encoder_path), options, providers=cpu)
        self.decoder = ScoreDecoder(ort.InferenceSession(str(decoder_path), options, providers=cpu),
                                    fp16=False, use_gpu=False, config=self.config)

    def encode(self, image):
        return self.encoder.run(["output"], {"input": image[None].astype(np.float32)})[0]

    def decode(self, context):
        start = np.array([[self.config.bos_token]], dtype=np.int64)
        nonote = np.array([[self.config.nonote_token]], dtype=np.int64)
        return self.decoder.generate(start, nonote, context=context)

    def read(self, image):
        return self.decode(self.encode(image))
