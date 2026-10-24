"""Text in page images read by OCR (Phase 2, Stage 2.5).

Each text box the detector found is read alone by RapidOCR's recogniser
(PP-OCRv5 Latin), and becomes a symbols.TextRun with its italic, bold, size
and baseline measured from the ink, so omr.pdf.text sorts it as it sorts the
text of a vector PDF. The font name is "image" with "-Bold", "-Italic" or
"-BoldItalic" added, which text.is_bold and text.is_italic read.

With OMR_DETECTIONS_DIR set, each page's readings are saved in its "ocr"
folder, keyed by the crops and the model file, as the detections are.

The rules are in docs/notes/raster-text-spec.md.
"""

import functools
import hashlib
import json
import multiprocessing
import os
from pathlib import Path

import numpy as np

MODEL_ENV = "OMR_OCR_MODEL"
THREADS_ENV = "OMR_OCR_THREADS"
DEFAULT_MODEL = Path("models") / "ocr" / "latin_PP-OCRv5_rec_mobile.onnx"
MARGIN = 0.15        # staff spaces of image round a box
LEAST_SCORE = 0.5    # a reading under this recognition score is dropped
INK = 128            # grey levels below this are ink

# italic: the lean (across per unit up) that makes the ink's columns tallest
SLANTS = np.linspace(-0.1, 0.4, 26)
ITALIC_SLANT = 0.12
ITALIC_GAIN = 1.05
STYLE_LETTERS = 3   # letters needed to measure a lean or a stroke; shorter text is plain
BOLD_STROKE = 0.112  # median ink run over the font size, from which text is bold

# shares of the font size in a typical serif font
X_HEIGHT = 0.45
ASCENDER = 0.70
DESCENDER = 0.22
# the box of a PDF text run: the font's height, the baseline this far down
BOX_ABOVE = 0.77
T_HEIGHT = 0.60   # a t is shorter than the other ascenders
TALL = set("bdfhkl!?()[]{}/\\|'\"&%$#@ßij")   # with capitals, digits and accented letters
LOW = set("gjpqyç;,()[]{}/|")


def model_path():
    """The OCR model: OMR_OCR_MODEL, or models/ocr in the repository."""
    from omr import paths

    configured = os.environ.get(MODEL_ENV)
    return Path(configured) if configured else paths.REPO_ROOT / DEFAULT_MODEL


@functools.cache
def _engine(path):
    if not Path(path).is_file():
        raise FileNotFoundError(f"the OCR model {path} was not found. Set {MODEL_ENV} to the model file.")
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    # one thread in a worker of the pool, which runs one job a core, or
    # where OMR_OCR_THREADS says (evaluation runs start a converter a core)
    threads = int(os.environ.get(THREADS_ENV) or (1 if multiprocessing.parent_process() is not None else -1))
    return RapidOCR(params={
        "Global.log_level": "error", "Global.use_det": False, "Global.use_cls": False,
        "Rec.lang_type": LangRec.LATIN, "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.MOBILE, "Rec.model_path": str(path), "Rec.rec_batch_num": BATCH,
        "EngineConfig.onnxruntime.intra_op_num_threads": threads,
        "EngineConfig.onnxruntime.inter_op_num_threads": threads})


BATCH = 1   # crops a call to the model: larger batches are padded to their widest crop, and slower


def reader(path=None, saved_in=None):
    """A function [grey crop] -> [(text, score)] that runs the OCR model
    (loaded once a process) on a page's crops. Readings are saved in the
    folder `saved_in`, or with it None in OMR_DETECTIONS_DIR/ocr if set;
    with it False, never."""
    from omr.raster import reading

    path = str(path or model_path())

    def run(crops):
        from rapidocr.ch_ppocr_rec.typings import TextRecInput

        if not crops:
            return []
        engine = _engine(path)
        # each crop prepared as RapidOCR prepares a whole image
        images = [engine.preprocess_img(engine.load_img(c))[0] for c in crops]
        out = engine._load_rec_model()(TextRecInput(img=images))
        return [(t.strip(), float(p)) for t, p in zip(out.txts, out.scores)]

    folder = os.environ.get(reading.DETECTIONS_ENV) if saved_in is None else saved_in
    return saving(run, Path(folder) / "ocr", path) if folder else run


def saving(run, folder, model):
    """`run`, with each page's readings saved in one file in `folder` and
    read back when the same crops are read with the same model."""
    def cached(crops):
        if not crops:
            return []
        file = saved_file(folder, crops, model)
        try:
            return [(text, score) for text, score in json.loads(file.read_text(encoding="utf-8"))]
        except (OSError, ValueError):
            pass
        found = run(crops)
        file.parent.mkdir(parents=True, exist_ok=True)
        part = file.with_name(f"{file.stem}.{os.getpid()}.part")   # so a reader never sees half a file
        part.write_text(json.dumps([list(r) for r in found], ensure_ascii=False), encoding="utf-8")
        part.replace(file)
        return found
    return cached


def saved_file(folder, crops, model):
    """The file a page's readings are saved in: named by the crops'
    contents and the model file's contents."""
    from omr.raster import reading

    key = hashlib.sha256()
    key.update(reading._model_digest(str(model)).encode())
    for crop in crops:
        key.update(f"{crop.shape}".encode())
        key.update(np.ascontiguousarray(crop).tobytes())
    name = key.hexdigest()
    return Path(folder) / name[:2] / f"{name}.json"


# ------------------------------------------------------------- style

def slant(ink):
    """(lean, gain): the shear that makes the ink's columns tallest, and
    how much taller than upright."""
    h = ink.shape[0]
    ys, xs = np.nonzero(ink)
    best, best_a, level = -1.0, 0.0, 0.0
    for a in SLANTS:
        cols = np.round(xs - a * (h - 1 - ys)).astype(int)
        hist = np.bincount(cols - cols.min()).astype(float)
        score = float((hist ** 2).sum())
        if abs(a) < 1e-9:
            level = score
        if score > best:
            best, best_a = score, float(a)
    return best_a, best / level if level else 1.0


def stroke(ink):
    """The median horizontal run of ink, in pixels."""
    padded = np.pad(ink.astype(np.int8), ((0, 0), (1, 1)))
    d = np.diff(padded, axis=1)
    starts, ends = np.nonzero(d == 1), np.nonzero(d == -1)
    runs = ends[1] - starts[1]
    return float(np.median(runs)) if runs.size else 0.0


def share(text):
    """(top, bottom): how far the letters of `text` reach above and below
    the baseline, as shares of the font size."""
    letters = [c for c in text if not c.isspace()]
    if any(c in TALL or c.isupper() or c.isdigit() or ord(c) > 127 for c in letters):
        top = ASCENDER
    else:
        top = T_HEIGHT if "t" in letters else X_HEIGHT
    if letters and all(c in ".,-–—_:;'\"`" for c in letters):
        top = X_HEIGHT
    bottom = DESCENDER if any(c in LOW for c in letters) else 0.0
    return top, bottom


def measure(ink, text):
    """(size, baseline row, stroke, lean, gain) of a box's ink in pixels,
    given what OCR read in it; None if it holds no ink."""
    rows = np.nonzero(ink.any(axis=1))[0]
    if rows.size == 0:
        return None
    top_row, bottom_row = rows[0], rows[-1] + 1
    up, down = share(text)
    size = (bottom_row - top_row) / (up + down)
    # style is measured on letters: the strokes of a lone digit (1, 4, 7)
    # lean too, and the detector gives tuplet numbers their own class; a
    # lone round capital (C, G) has thick sides, and is a chord symbol
    if sum(c.isalpha() for c in text) < STYLE_LETTERS:
        return size, bottom_row - down * size, 0.0, 0.0, 1.0
    lean, gain = slant(ink)
    return size, bottom_row - down * size, stroke(ink), lean, gain


def font_name(size, stroke_px, lean, gain):
    """"image", with "-Bold", "-Italic" or "-BoldItalic" as the ink shows."""
    italic = lean >= ITALIC_SLANT and gain >= ITALIC_GAIN
    bold = size > 0 and stroke_px / size >= BOLD_STROKE
    return "image" + ("-" if bold or italic else "") + ("Bold" if bold else "") + ("Italic" if italic else "")


def style(ink, text, px_per_pt):
    """(font name, size in points, baseline row) of a box's ink alone; None
    if it holds no ink."""
    measured = measure(ink, text)
    if measured is None:
        return None
    size, baseline, stroke_px, lean, gain = measured
    return font_name(size, stroke_px, lean, gain), size / px_per_pt, baseline


SAME_LINE = 0.25   # staff spaces between baselines of text on one line
SIZE_SPAN = 1.25   # sizes on one line within this ratio are one size


def common_sizes(sizes, baselines, space):
    """Each size replaced by the median of the text on its line: sizes
    measured from ink vary by several percent between words of one font
    size, and the text rules group lyric rows by size to half a point.
    A line is the runs whose baselines lie within SAME_LINE staff spaces
    of the first, and whose sizes are within SIZE_SPAN of each other."""
    out = list(sizes)
    left = sorted(range(len(sizes)), key=lambda k: baselines[k])
    while left:
        first = left[0]
        line = [k for k in left if baselines[k] - baselines[first] <= SAME_LINE * space]
        small = min(sizes[k] for k in line)
        line = [k for k in line if sizes[k] <= SIZE_SPAN * small]
        middle = float(np.median([sizes[k] for k in line]))
        for k in line:
            out[k] = middle
        left = [k for k in left if k not in line]
    return out


# ------------------------------------------------------------- the page

def clean(text):
    """OCR's reading tidied: a hyphen OCR adds after a lyric syllable is
    left to the hyphen lines the line finder gives."""
    text = text.strip()
    if len(text) > 1 and text[-1] in "-–" and text[-2].isalpha():
        text = text[:-1]
    return text


def read_regions(grey, place, regions, space_px, read=None):
    """symbols.TextRuns for the page's text regions (boxes in page points),
    read from the level grey image. `read` is a function as `reader` gives."""
    from omr.pdf.symbols import TextRun

    read = read or reader()
    margin = int(MARGIN * space_px)
    boxes, crops = [], []
    for region in regions:
        x0, y0, x1, y1 = place.to_pixels(region)
        crop = grey[max(0, int(y0) - margin):int(y1) + margin + 1, max(0, int(x0) - margin):int(x1) + margin + 1]
        if crop.size:
            boxes.append((region, (x0, y0, x1, y1)))
            crops.append(crop)
    found = []
    for (region, (x0, y0, x1, y1)), (text, score) in zip(boxes, read(crops)):
        text = clean(text)
        if not text or score < LEAST_SCORE:
            continue
        top = max(0, int(round(y0)))
        inner = grey[top:int(round(y1)) + 1, max(0, int(round(x0))):int(round(x1)) + 1]
        measured = measure(inner < INK, text)
        if measured is not None:
            found.append((region, text, top, measured))
    sizes = common_sizes([m[0] for _, _, _, m in found], [top + m[1] for _, _, top, m in found], space_px)
    runs = []
    for (region, text, top, (_, base_row, stroke_px, lean, gain)), size_px in zip(found, sizes):
        size = size_px * place.sy
        baseline = place.y0 + (top + base_row) * place.sy
        box = (region[0], baseline - BOX_ABOVE * size, region[2], baseline + (1 - BOX_ABOVE) * size)
        runs.append(TextRun(text, region[0], baseline, box, font_name(size_px, stroke_px, lean, gain), size))
    return runs
