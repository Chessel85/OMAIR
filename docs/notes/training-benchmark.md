# Training-speed benchmark on the T500 (Stage 10)

Measured on 8 October 2026 on the development laptop: NVIDIA T500 with 2 GB, 4 cores, 32 GB RAM, PyTorch 2.14.1 with CUDA 13.0, Ultralytics 8.4.173. Plain headings and lists only.

Status: **measurements done by Sonnet and complete (a thermal check on a longer run is the one optional item left). The decisions are for Opus to make** (see the last section). The YOLO part ran in two sessions: the first stopped after 6 settings when the laptop ran low on memory, and the second (the same day, machine idle) ran the remaining settings plus repeats of the 640 and 800 pixel ones. The CPU inference test was run last.

## How it was measured

- Dataset: `scripts/make_detection_dataset.py`. 40 development scores, drawn by Verovio with a bounding box for every symbol, cut into 1024 pixel tiles with overlap. 513 training tiles and 112 validation tiles, split by score. 11 classes: notehead, stem, beam, flag, rest, clef, accidental, dots, meter, barline, dynamic. Written to `benchmark/detection` on the corpus drive. Staff spaces are about 14 to 20 pixels.
- Benchmark: `scripts/benchmark_training.py yolo` and `seq`. Raw logs are in `benchmark/results` on the corpus drive (`benchmark-yolo.log`, `benchmark-seq.log`, `benchmark-seq-part1.log`, `benchmark-onnx.log`). The second YOLO session overwrote `benchmark-yolo.log`; the 1024 pixel figures below come from the first session.
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
- Second session (machine idle, 1024 pixel settings dropped):
  - Nano, tile 640, batch 8, 4 workers: 181 seconds per epoch (2.8 per second). Card 1901 MB, PyTorch peak 2088 MB.
  - Nano, tile 640, batch 16: 359 seconds (1.4 per second). PyTorch peak 4073 MB. Spilling.
  - Nano, tile 640, batch 32: 458 seconds (1.1 per second). PyTorch peak 7922 MB. Spilling.
  - Nano, tile 800, batch 8: 462 seconds (1.1 per second). PyTorch peak 3236 MB. Spilling.
  - **Small model**, tile 640, batch 8: 730 seconds (0.7 per second). PyTorch peak 3771 MB. Spilling, and about 4 times slower than nano.
  - **Workers sweep**, nano 640 batch 8: 0 workers 192 seconds (2.7 per second), 2 workers 150 seconds (3.4), 4 workers 181 seconds (2.8, above), 8 workers 151 seconds (3.4). All peaks about 2080 MB.
- Not run: nano 1024 batch 16, small model at 1024.
- The two sessions differ by up to 17 percent for the same setting (nano 640 batch 8: 154 then 181 seconds), so treat all figures as plus or minus 20 percent.

What this says:

- Nothing at all failed with an out-of-memory error. Windows lets the card borrow system RAM, so a setting "runs" when it does not fit, at a 2 to 3 times penalty. The speed figures, not the lack of errors, show what fits.
- Batch 8 at 640 pixels works at full speed. Larger tiles or batches cost far more than their size: 1024 pixels at batch 4 is 3 times slower per tile than 640 at batch 8, though it has only 2.5 times the pixels.
- Rough run lengths at 2.8 to 3.4 tiles per second: 10,000 tiles per epoch takes about 50 to 60 minutes, so 50 epochs is about 42 to 50 hours. This is for nano. The small model at 0.7 tiles per second would take four times as long, about a week, and does not fit in 2 GB.
- Data loading is not the limit: 2 and 8 workers gave the same speed (150 seconds), 0 workers was only 5 to 25 percent slower, and 4 workers (181 seconds) was slower than 2, which is run-to-run noise. Use 2 workers.

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

## CPU inference through ONNX Runtime

`scripts/benchmark_onnx_cpu.py`, ONNX Runtime 1.30.0, CPU provider, default threads, one staff at a time, 256 tokens, random weights, FP32. The encoder (convolutions and 2 transformer layers) and the decoder were exported separately. The decoder has no key-value cache, so generating a staff repeats a pass for every new token. The whole-staff figure sums passes of lengths 1 to 256, interpolated from the lengths timed (1, 32, 64, 128, 256).

- 29.0 million parameters: encoder 153 ms; one decoder pass over 256 tokens 104 ms. **About 17 seconds per staff** without a cache.
- 37.4 million: encoder 144 ms; pass over 256 tokens 148 ms. About 24 seconds per staff.
- 45.8 million: encoder 146 ms; pass over 256 tokens 201 ms. About 32 seconds per staff.

What this says:

- Without a cache, a page of 10 staves takes about 3 minutes with the 29 million model and 4 minutes with the 37 million one. That is slow but usable for an offline tool, and this is the worst case. A decoder with a key-value cache costs roughly one single-token pass per token, which is about 25 to 50 ms, so about 6 to 13 seconds per staff for all three sizes plus the encoder. The cache is worth building before the model size is chosen on speed grounds.
- The 29 to 37 million difference is about 40 percent in decode time. Neither is ruled out. This is not a deciding factor on its own.
- Not measured: thread settings (ONNX Runtime used its default), INT8 quantisation (usually 1.5 to 3 times faster on CPU), and the real homr or SMT architecture. torch reported 4 threads on this 4 core, 8 thread laptop.
- To rerun, `pip install onnx` first (it is needed only for export, not added to the requirements files).

## For Opus to decide

- Fix the detector size, tile size and batch. The evidence points to nano at 640 pixels, batch 8. Is a 640 pixel tile big enough at the staff sizes used (staff space about 14 to 20 pixels, symbols mostly 15 to 60 pixels)? Would a smaller image scale with a 1024 tile be better than 1024 at full scale?
- Fix the sequence reader size. All three fit. Which suits the CPU inference target (OP-3)? Inference speed is now measured (see above): 17, 24 and 32 seconds per staff without a cache. A 29 million model with batch 8 is the cheapest in training and in inference.
- Set the expected time per run. Use about 3 tiles per second for the detector and 2.5 to 3 staves per second for the reader, and choose dataset sizes so that a run is no more than a few days (C-7). Say whether Kaggle is needed for anything.
- Decide what still needs measuring before the sizes are fixed: only a longer run for thermal throttling is left (the two YOLO sessions differed by up to 17 percent), and optionally INT8 and cached-decoder inference speed.
- Check the dataset labelling: classes follow Verovio's element boxes, so a notehead box is the head only and stems and beams have thin or diagonal boxes. This is fine for a speed test but the real training labels need review.

## Decisions for Phase 2 (made 9 October 2026, closing Stage 10)

Made by Claude from the measurements above. They are decisions of the plan, not of the owner, and the owner signs them off in the Phase 0 report. Each has a trigger for revisiting it.

### Symbol detector

- **Model: YOLO11 nano, tile 640 pixels, batch 8, FP16, 2 data-loading workers.** It is the only setting that fits in 2 GB at full speed (about 3 tiles per second). The small model spills out of the card and runs about 4 times slower, so it is ruled out for training on the laptop.
- **Scale:** the benchmark used 1024 pixel tiles with a staff space of 14 to 20 pixels. A 640 tile at that scale holds under half the area, so a whole staff is wider than one tile, and tiles must overlap. Symbols of 15 to 60 pixels are still large enough for a nano detector. To get more context per tile, render the training data at a staff space of about 10 to 12 pixels, which puts a typical staff in about 640 pixels at 1.5 times the area of the benchmark tile. This is not measured. **First task of Phase 2:** train two short runs (staff space 14 to 20 against 10 to 12) on the same scores and compare recall on small symbols (accidentals, dots, flags) before building the full set.
- **Run length:** 10,000 tiles per epoch at 3 tiles per second is about 55 minutes. A run of 40 to 50 epochs is therefore about 1.5 to 2 days. That meets C-7 ("a few days per run"). Use 20 epochs for experiments (under a day).
- **Labels:** the benchmark labels come from Verovio element boxes (a notehead box is the head only, stems and beams have thin or diagonal boxes). For real training, derive boxes per symbol class with a rule written down first (heads, accidentals, dots, rests, flags, clefs, meter digits, dynamics and so on from glyph boxes; stems, beams and barlines as thin boxes with a minimum width). This is a review item at the start of Phase 2, not a risk to the sizes.

### Sequence reader

- **Model: about 29 million parameters** (the convolutional encoder of about 17 million, two transformer encoder layers, a 4-layer decoder, width 512). Batch 4 to 8, FP16, **gradient checkpointing off** (it is only needed above batch 8 or at 512 tokens), 256 tokens per staff to begin with.
- **Why the smallest:** it trains fastest (about 3 staves per second), decodes about 40 percent faster on the CPU than the 37 million model, and leaves memory in hand. The measured homr transformer files (encoder 53 MB and decoder 47 MB as FP32 ONNX) imply about 25 million parameters in all, so a 20 to 40 million model is the same class as the starting weights, and the design's "start from homr weights and fine-tune" is plausible. **Phase 2 must check this first:** the fine-tuned architecture has to be the pretrained one. If the homr or SMT architecture is not close to 29 million, the size follows the pretrained model, within the 20 to 46 million range measured here.
- **Run length:** one pass over 100,000 staves is about 9 hours at 3 per second. A fine-tune of 3 to 5 passes is about 1 to 2 days. With 512 tokens per staff, about a third longer.
- **Inference on the CPU:** about 17 seconds per staff for the 29 million model with no key-value cache (measured with random weights). With a cache, estimated 6 to 13 seconds per staff, and INT8 quantisation usually gives 1.5 to 3 times more; neither is measured. Building the cache is the first inference task in Phase 2, before any decision to drop the sequence reader on speed grounds.

### Kaggle

- **Not needed** for any planned run. The free Kaggle quota stays an optional accelerator for detector experiments (C-5 forbids depending on it).

### Not measured, and why it is accepted

- A longer thermal check: the two YOLO sessions differed by up to 17 percent, so all run lengths above are plus or minus 20 percent. The run lengths have enough room in them that this does not change a decision.
- Convergence: all sequence reader figures are for random data, so they say nothing about how many passes are enough. Phase 2 measures this on the real data.
- INT8 and cached-decoder CPU speed (see above).
