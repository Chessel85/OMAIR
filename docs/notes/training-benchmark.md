# Training-speed benchmark on the T500 (Stage 10)

Measured on 8 October 2026 on the development laptop: NVIDIA T500 with 2 GB, 4 cores, 32 GB RAM, PyTorch 2.14.1 with CUDA 13.0, Ultralytics 8.4.173. Plain headings and lists only.

Status: **measurements done by Sonnet, partly complete. The decisions are for Opus to make** (see the last section). The YOLO part stopped after 6 of its 13 planned settings, because Claude Code stopped the background job when the laptop ran critically low on memory. It was not restarted, as instructed.

## How it was measured

- Dataset: `scripts/make_detection_dataset.py`. 40 development scores, drawn by Verovio with a bounding box for every symbol, cut into 1024 pixel tiles with overlap. 513 training tiles and 112 validation tiles, split by score. 11 classes: notehead, stem, beam, flag, rest, clef, accidental, dots, meter, barline, dynamic. Written to `benchmark/detection` on the corpus drive. Staff spaces are about 14 to 20 pixels.
- Benchmark: `scripts/benchmark_training.py yolo` and `seq`. Raw logs are in `benchmark/results` on the corpus drive (`benchmark-yolo.log`, `benchmark-seq.log`, `benchmark-seq-part1.log`).
- YOLO: pretrained YOLO11 weights, FP16 (amp), 2 epochs per setting, the second epoch reported, no validation, no caching. Ultralytics always accumulates gradients up to a nominal batch of 64, so small batches are already covered.
- "Card memory" is what `nvidia-smi` reports for the whole card, including the CUDA context. It stops at about 1900 MB because the card is full. "PyTorch allocated peak" is what PyTorch asked for. When that is above 2048 MB, Windows is moving GPU memory into system RAM, which is far slower.
- Sequence reader stand-in: a convolutional encoder (4 stages, 128 by 1024 staff crop in, 256 tokens out), 2 transformer encoder layers, and a decoder of 4, 6 or 8 layers (width 512, 8 heads), FP16, AdamW, with and without gradient checkpointing. Random data, 10 timed steps each, so speed and memory only.

## Environment problem found and fixed

- `requirements-torch.txt` pinned `torchvision==0.29.1`, which installed the CPU build next to the CUDA PyTorch. Every YOLO run then failed in non-maximum suppression with a confusing dispatch error.
- Fixed: the file now pins `torchvision==0.29.1+cu130`, and the venv has it. The README install command already uses the CUDA 13.0 index. Anyone with an older venv should reinstall torchvision.

## YOLO results (nano model, 513 tiles per epoch)

- Nano, tile 640, batch 8: 154 seconds per epoch (3.3 tiles per second). Card full at 1903 MB, PyTorch peak 2088 MB. **The only setting that is close to fitting.**
- Nano, tile 640, batch 16: 330 seconds per epoch (1.6 per second). PyTorch peak 4073 MB. Spilling into system memory.
- Nano, tile 640, batch 32: 474 seconds per epoch (1.1 per second). PyTorch peak 7922 MB. Spilling.
- Nano, tile 800, batch 8: 484 seconds per epoch (1.1 per second). PyTorch peak 3236 MB. Spilling.
- Nano, tile 1024, batch 4: 479 seconds per epoch (1.1 per second). PyTorch peak 2671 MB. Spilling.
- Nano, tile 1024, batch 8: 984 seconds per epoch (0.5 per second). PyTorch peak 5228 MB. Spilling.
- Not run: nano 1024 batch 16, small model at 640 and 1024, and the data loading sweep (0, 2 and 8 workers).

What this says:

- Nothing at all failed with an out-of-memory error. Windows lets the card borrow system RAM, so a setting "runs" when it does not fit, at a 2 to 3 times penalty. The speed figures, not the lack of errors, show what fits.
- Batch 8 at 640 pixels works at full speed. Larger tiles or batches cost far more than their size: 1024 pixels at batch 4 is 3 times slower per tile than 640 at batch 8, though it has only 2.5 times the pixels.
- Rough run lengths at 3.3 tiles per second: 10,000 tiles per epoch takes about 50 minutes, so 50 epochs is about 42 hours. This is for nano only, and the small model was not measured.
- Not known: how much CPU data loading limits the speed. The workers sweep did not run. The GPU looked busy throughout, which suggests the GPU is the limit, but that is not measured.

## Sequence reader stand-in results (256 tokens unless stated)

Parameter counts: 29.0 million (4 decoder layers), 37.4 million (6), 45.8 million (8). The encoder alone is about 17 million, so 20 million was not reachable with this encoder.

- 29.0 million, checkpointing on: batch 1 to 16 give 2.9 to 3.6 staves per second. Card peak 725 MB at batch 1, 1017 MB at batch 8, 1647 MB at batch 16.
- 29.0 million, checkpointing off: 3.1 to 3.9 staves per second. Card peak 1169 MB at batch 8, 1893 MB at batch 16 (PyTorch peak 1743 MB, still inside the card).
- 37.4 million, checkpointing on: 2.0 to 2.9 staves per second. Card peak 1095 MB at batch 8, 1717 MB at batch 16.
- 37.4 million, checkpointing off: 2.6 to 3.2 staves per second up to batch 8 (card peak 1463 MB). At batch 16 it spills (PyTorch peak 2105 MB) and falls to 2.1 per second.
- 45.8 million, checkpointing on: 1.8 to 2.4 staves per second. Card peak 1181 MB at batch 8, 1787 MB at batch 16.
- 45.8 million, checkpointing off: 2.7 to 2.8 staves per second at batches 4 and 8 (card peak 1677 MB at batch 8). At batch 16 it spills (PyTorch peak 2468 MB) and falls to 1.7.
- 37.4 million with 512 tokens, checkpointing on: 1.5 to 1.9 staves per second. Card peak 1155 MB at batch 8, 1853 MB at batch 16.
- 37.4 million with 512 tokens, checkpointing off: 1.8 to 2.3 staves per second. Batch 8 peak 1771 MB. Batch 16 spills (2811 MB) and falls to 1.4.

What this says:

- Every size fits in 2 GB at batch 8 or lower, with or without checkpointing. Checkpointing saves about 25 to 30 percent of memory and costs about 10 to 25 percent of speed. It is only needed above batch 8, or for longer sequences.
- Speed is flat from batch 4 upward, so the GPU is saturated. Bigger batches add nothing. Use batch 4 to 8.
- Throughput is about 3 staves per second for the 29 million model and about 2.5 for 37 million. One pass over 100,000 staves takes about 9 hours at 3 per second and about 11 hours at 2.5. Doubling the sequence length costs about a third of the speed.
- Caveats: the data was random, so there is no data loading cost here and nothing about convergence. It is not the homr or SMT architecture, and the real encoder and token counts may differ. Staff crops of 128 by 1024 may be smaller or larger than the real ones. The speed figures on a hot laptop may drop (the laptop lowers its clock under load, see `tool-commands.md`).

## For Opus to decide

- Fix the detector size, tile size and batch. The evidence points to nano at 640 pixels, batch 8. Is a 640 pixel tile big enough at the staff sizes used (staff space about 14 to 20 pixels, symbols mostly 15 to 60 pixels)? Would a smaller image scale with a 1024 tile be better than 1024 at full scale?
- Fix the sequence reader size. All three fit. Which suits the CPU inference target (OP-3), given inference speed was not measured here? A 29 million model with batch 8 is the cheapest in training time.
- Set the expected time per run. Use about 3.3 tiles per second for the detector and 2.5 to 3 staves per second for the reader, and choose dataset sizes so that a run is no more than a few days (C-7). Say whether Kaggle is needed for anything.
- Decide what still needs measuring before the sizes are fixed: the small YOLO model at 640, the data loading sweep, a longer run for thermal throttling, and an inference speed test on the CPU through ONNX Runtime. The command to finish the YOLO part is `python scripts/benchmark_training.py yolo` (about 2 hours more; edit `YOLO_SETTINGS` first to drop the 1024 settings and keep the small model at 640, and the workers sweep). Close other heavy programs first, because the earlier run was stopped for low memory.
- Check the dataset labelling: classes follow Verovio's element boxes, so a notehead box is the head only and stems and beams have thin or diagonal boxes. This is fine for a speed test but the real training labels need review.
