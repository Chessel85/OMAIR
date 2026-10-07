"""Runs inside the LEGATO environment (Python 3.12), not the project one.

usage: python legato_infer.py REPO OUT_DIR IMAGE...

Loads LEGATO once, reads each page image on the CPU, and writes `pageNNN.abc`
and `pageNNN.xml` (ABC converted with LEGATO's own cleaning and abc2xml) to
OUT_DIR. A page that fails to convert gets only its `.abc` file and a line on
standard error.
"""

import subprocess
import sys
import time
from pathlib import Path


def main(argv):
    repo, out, images = Path(argv[0]), Path(argv[1]), [Path(a) for a in argv[2:]]
    sys.path.insert(0, str(repo))
    import torch
    from PIL import Image
    from transformers import AutoProcessor, GenerationConfig
    from legato.models import LegatoModel
    from utils.convert import cleanup_abc

    torch.set_num_threads(3)
    started = time.time()
    model = LegatoModel.from_pretrained("guangyangmusic/legato").to("cpu").eval()
    processor = AutoProcessor.from_pretrained("guangyangmusic/legato")
    config = GenerationConfig(max_length=2048, num_beams=10, repetition_penalty=1.1)
    print(f"model loaded in {time.time() - started:.0f} s", file=sys.stderr, flush=True)

    for image in images:
        started = time.time()
        inputs = processor(images=[Image.open(image).convert("RGB")], truncation=True, return_tensors="pt")
        with torch.no_grad():
            tokens = model.generate(**inputs, generation_config=config, use_model_defaults=False)
        abc = processor.batch_decode(tokens.tolist(), skip_special_tokens=True)[0]
        (out / f"{image.stem}.abc").write_text(abc, encoding="utf-8")
        print(f"{image.name}: read in {time.time() - started:.0f} s", file=sys.stderr, flush=True)
        try:
            clean = cleanup_abc(abc)
            done = subprocess.run([sys.executable, str(repo / "utils" / "abc2xml.py"), "-"],
                                  input=clean.encode("utf-8"), capture_output=True, check=True)
            (out / f"{image.stem}.xml").write_bytes(done.stdout)
        except Exception as error:
            print(f"{image.name}: ABC to MusicXML failed: {error}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
