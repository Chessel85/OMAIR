"""Import every dependency and report, in plain text, what was found."""

import importlib
import sys

MODULES = [
    ("PyTorch", "torch"),
    ("PyMuPDF", "pymupdf"),
    ("pikepdf", "pikepdf"),
    ("OpenCV", "cv2"),
    ("scikit-image", "skimage"),
    ("ONNX Runtime", "onnxruntime"),
    ("Ultralytics", "ultralytics"),
    ("music21", "music21"),
    ("musicdiff", "musicdiff"),
    ("Verovio", "verovio"),
    ("pytest", "pytest"),
]


def main():
    print(f"Python {sys.version.split()[0]}")
    failed = []
    for label, module in MODULES:
        try:
            mod = importlib.import_module(module)
            print(f"OK: {label} {getattr(mod, '__version__', '(version unknown)')}")
        except Exception as exc:
            print(f"FAILED: {label} could not be imported: {exc}")
            failed.append(label)
    if "PyTorch" not in failed:
        import torch

        if torch.cuda.is_available():
            print(f"GPU: PyTorch sees {torch.cuda.get_device_name(0)}, CUDA {torch.version.cuda}.")
        else:
            print("GPU: PyTorch does not see a GPU.")
    if failed:
        print(f"Summary: {len(failed)} dependency(ies) failed: {', '.join(failed)}.")
        return 1
    print("Summary: all dependencies imported.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
