"""Tests for the symbol detector's page reading and scoring (omr.raster.detect)."""

from types import SimpleNamespace

import numpy as np

from omr.corpus import raster_labels as rl
from omr.raster import detect

HEAD = rl.CLASS_INDEX["noteheadBlack"]
SHARP = rl.CLASS_INDEX["accidentalSharp"]


def test_merge_keeps_the_most_confident_box_of_one_class():
    found = [(HEAD, (10, 10, 30, 26), 0.6), (HEAD, (11, 10, 31, 26), 0.9), (SHARP, (10, 10, 30, 26), 0.5)]
    kept = detect.merge(found)
    assert sorted(kept, key=lambda d: d[0]) == [(HEAD, (11, 10, 31, 26), 0.9), (SHARP, (10, 10, 30, 26), 0.5)]


def test_a_box_cut_by_an_inner_tile_edge_is_dropped():
    assert detect._cut((0, 100, 20, 120), x=480, y=0, w=2000, h=2000)
    assert not detect._cut((0, 100, 20, 120), x=0, y=0, w=2000, h=2000)       # the page's own edge
    assert detect._cut((620, 100, 640, 120), x=0, y=0, w=2000, h=2000)
    assert not detect._cut((620, 100, 640, 120), x=1360, y=0, w=2000, h=2000)  # the last tile


def test_match_counts_found_missed_and_other_class():
    labels = [rl.Label("noteheadBlack", (10, 10, 30, 26)), rl.Label("accidentalSharp", (50, 5, 60, 30)),
              rl.Label("augmentationDot", (100, 10, 106, 16))]
    found = [(HEAD, (11, 10, 31, 26), 0.9), (rl.CLASS_INDEX["accidentalNatural"], (50, 5, 60, 30), 0.8),
             (HEAD, (300, 10, 320, 26), 0.7)]
    rows = detect.match(labels, found)
    assert rows["noteheadBlack"] == {"truth": 1, "found": 2, "matched": 1, "other class": 0}
    assert rows["accidentalSharp"] == {"truth": 1, "found": 0, "matched": 0, "other class": 1}
    assert rows["augmentationDot"] == {"truth": 1, "found": 0, "matched": 0, "other class": 0}


class FakeModel:
    """Finds one notehead at a fixed place on the page, in whichever tiles hold it whole."""

    def __init__(self, page_box):
        self.page_box = page_box
        self.origins = []

    def predict(self, tiles, **kwargs):
        out = []
        for _ in tiles:
            x, y = self.origins.pop(0)
            x0, y0, x1, y1 = (v - o for v, o in zip(self.page_box, (x, y, x, y)))
            inside = x0 >= 0 and y0 >= 0 and x1 <= detect.TILE and y1 <= detect.TILE
            boxes = [[x0, y0, x1, y1]] if inside else []
            out.append(SimpleNamespace(boxes=SimpleNamespace(
                cls=FakeTensor([HEAD] * len(boxes)), xyxy=FakeTensor(boxes), conf=FakeTensor([0.9] * len(boxes)))))
        return out


class FakeTensor(list):
    def tolist(self):
        return list(self)


def test_detect_page_puts_a_symbol_in_the_overlap_back_once_at_page_scale():
    grey = np.full((1000, 1500), 255, np.uint8)
    model = FakeModel((500, 300, 520, 316))        # in the overlap of the first two tiles across
    model.origins = [(x, y) for y in detect.tile_origins(1000) for x in detect.tile_origins(1500)]
    found = detect.detect_page(model, grey)
    assert found == [(HEAD, (500, 300, 520, 316), 0.9)]
