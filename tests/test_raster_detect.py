"""Tests for the symbol detector's page reading and scoring (omr.raster.detect)."""

from types import SimpleNamespace

import numpy as np

from omr.corpus import raster_labels as rl
from omr.raster import detect

HEAD = rl.CLASS_INDEX["noteheadBlack"]
SHARP = rl.CLASS_INDEX["accidentalSharp"]
BRACE = rl.CLASS_INDEX["brace"]


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
    """Finds one symbol at a fixed place on the page, in whichever tiles hold
    it whole, or with `pieces`, also where a tile holds part of it (clipped to
    the tile, as the training labels are)."""

    def __init__(self, page_box, cls=HEAD, pieces=False):
        self.page_box = page_box
        self.cls = cls
        self.pieces = pieces
        self.origins = []

    def predict(self, tiles, **kwargs):
        out = []
        for _ in tiles:
            x, y = self.origins.pop(0)
            x0, y0, x1, y1 = (v - o for v, o in zip(self.page_box, (x, y, x, y)))
            inside = x0 >= 0 and y0 >= 0 and x1 <= detect.TILE and y1 <= detect.TILE
            touches = x1 > 0 and y1 > 0 and x0 < detect.TILE and y0 < detect.TILE
            if inside or (self.pieces and touches):
                boxes = [[max(x0, 0), max(y0, 0), min(x1, detect.TILE), min(y1, detect.TILE)]]
            else:
                boxes = []
            out.append(SimpleNamespace(boxes=SimpleNamespace(
                cls=FakeTensor([self.cls] * len(boxes)), xyxy=FakeTensor(boxes),
                conf=FakeTensor([0.9] * len(boxes)))))
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


def _read(model, h, w):
    model.origins = [(x, y) for y in detect.tile_origins(h) for x in detect.tile_origins(w)]
    return detect.detect_page(model, np.full((h, w), 255, np.uint8))


def test_a_cut_piece_of_a_symbol_another_tile_holds_whole_is_dropped():
    found = _read(FakeModel((620, 300, 640, 316), pieces=True), 1000, 1500)
    assert found == [(HEAD, (620, 300, 640, 316), 0.9)]


def test_a_symbol_bigger_than_the_overlap_is_joined_from_its_pieces():
    # A brace 500 pixels tall crossing the whole strip shared by the two tile rows: no tile holds it whole.
    found = _read(FakeModel((100, 300, 140, 800), cls=BRACE, pieces=True), 1000, 1500)
    assert found == [(BRACE, (100, 300, 140, 800), 0.9)]


def test_a_symbol_taller_than_a_tile_is_joined_across_three_tiles():
    found = _read(FakeModel((100, 300, 140, 1300), cls=BRACE, pieces=True), 1600, 1500)
    assert found == [(BRACE, (100, 300, 140, 1300), 0.9)]


def test_a_lone_piece_is_kept_when_its_partner_was_missed():
    pieces = [(BRACE, (100, 300, 140, 640), 0.8)]
    assert detect.join_pieces(pieces, []) == pieces


def test_pieces_of_two_neighbouring_symbols_are_not_joined():
    # Two cut noteheads of a chord, one above the other, touching only at an edge.
    pieces = [(HEAD, (630, 300, 640, 316), 0.8), (HEAD, (630, 315, 640, 331), 0.8)]
    assert sorted(detect.join_pieces(pieces, [])) == sorted(pieces)
    # Two cut braces side by side, overlapping along their length but not across.
    pieces = [(BRACE, (100, 300, 140, 640), 0.8), (BRACE, (150, 480, 190, 800), 0.8)]
    assert sorted(detect.join_pieces(pieces, [])) == sorted(pieces)



class PiecesOnlyModel:
    """Finds the given boxes (in tile pixels) in the first tile only, as if the
    tile that holds the symbol whole had missed it."""

    def __init__(self, boxes, cls):
        self.boxes, self.cls, self.first = boxes, cls, True

    def predict(self, tiles, **kwargs):
        out = []
        for _ in tiles:
            boxes = self.boxes if self.first else []
            self.first = False
            out.append(SimpleNamespace(boxes=SimpleNamespace(
                cls=FakeTensor([self.cls] * len(boxes)), xyxy=FakeTensor(boxes),
                conf=FakeTensor([0.9] * len(boxes)))))
        return out


def test_a_short_cut_piece_is_dropped_even_with_no_whole_copy():
    # Half a notehead at the first tile's inner edge: shorter than the overlap, so its symbol fits
    # whole in the next tile. It is not kept as a piece of a large symbol.
    grey = np.full((640, 1000), 255, np.uint8)
    assert detect.detect_page(PiecesOnlyModel([[630, 100, 640, 116]], HEAD), grey) == []
    # A clef-sized piece lying wholly inside the shared strip: the next tile would hold such a symbol whole.
    assert detect.detect_page(PiecesOnlyModel([[496, 100, 640, 155]], rl.CLASS_INDEX["gClef"]), grey) == []
    # A brace piece reaching across the whole overlap is kept.
    found = detect.detect_page(PiecesOnlyModel([[400, 100, 640, 140]], BRACE), grey)
    assert found == [(BRACE, (400, 100, 640, 140), 0.9)]
