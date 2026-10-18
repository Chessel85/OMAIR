"""Tests for the lines found in page images (docs/notes/raster-lines-spec.md)."""

import cv2
import numpy as np
import pymupdf

from omr.raster import lines as rl
from omr.raster import page as rp

SPACE = 20      # staff space in pixels
LINE = 2        # staff line thickness in pixels
TOP = 100       # top staff line row


def blank(h=400, w=800):
    return np.full((h, w), 255, np.uint8)


def staff(grey, top=TOP, x0=50, x1=750):
    for k in range(5):
        y = top + k * SPACE
        grey[y:y + LINE, x0:x1] = 0
    return grey


def test_staff_space_from_the_runs():
    space, thick = rl.staff_space(rl.ink_of(staff(blank())))
    assert space == SPACE and thick == LINE


def test_staff_lines_are_level_lines_to_a_fraction_of_a_pixel():
    grey = staff(blank())
    grey[TOP - 1, 50:750] = 170        # a faint row above the first line moves its centre up
    found = rl.find_lines(grey)
    ys = sorted(round(y, 2) for y, x0, x1, t in found.level if x1 - x0 > 500)
    assert len(ys) == 5
    assert 100.7 < ys[0] < 101.0
    assert ys[1:] == [121.0, 141.0, 161.0, 181.0]


def test_a_sloping_line_is_not_a_level_line():
    grey = staff(blank())
    for x in range(100, 400):              # a shallow slope: runs of about 20 pixels on each row
        y = 300 + (x - 100) // 20
        grey[y:y + 2, x] = 0
    found = rl.find_lines(grey)
    assert not [l for l in found.level if l[0] > 250]
    assert any(abs(y0 - 301) < 2 and abs(y1 - 316) < 2 for x0, y0, x1, y1, t in found.thin)


def test_a_beam_cut_by_a_staff_line_leaves_no_slices():
    grey = staff(blank())
    grey[TOP + SPACE - 5:TOP + SPACE + 6, 300:400] = 0     # a level beam across the second line
    found = rl.find_lines(grey)
    assert not [l for l in found.level if 300 <= l[1] and l[2] <= 401]


def test_barlines_and_stems_are_vertical_lines():
    grey = staff(blank())
    grey[TOP:TOP + 4 * SPACE + LINE, 400:403] = 0           # a barline
    grey[TOP - 2 * SPACE:TOP + 2 * SPACE, 200:202] = 0      # a stem
    found = rl.find_lines(grey)
    xs = sorted(round(x) for x, top, bottom, w in found.vertical)
    assert xs == [201, 402]


def test_a_line_inside_a_symbol_belongs_to_it_but_a_stem_with_a_flag_does_not():
    grey = staff(blank())
    grey[TOP:TOP + 3 * SPACE, 200:202] = 0                  # a stroke of a symbol
    grey[TOP:TOP + 3 * SPACE, 500:502] = 0                  # a stem
    symbol = (190, TOP - 5, 215, TOP + 3 * SPACE + 5)
    head = (480, TOP + 2 * SPACE, 503, TOP + 3 * SPACE + 5)
    flag = (500, TOP - 5, 515, TOP + 2 * SPACE)
    found = rl.find_lines(grey, [symbol, head], [flag])
    assert [round(x) for x, *_ in found.vertical] == [501]


def test_a_beam_between_two_stems():
    grey = staff(blank())
    grey[TOP + 5 * SPACE:TOP + 8 * SPACE, 300:302] = 0      # stems below the staff
    grey[TOP + 5 * SPACE:TOP + 8 * SPACE, 400:402] = 0
    for x in range(300, 402):                               # a beam sloping down at their ends
        y = TOP + 8 * SPACE - 10 + (x - 300) // 10
        grey[y:y + 10, x] = 0
    found = rl.find_lines(grey)
    assert len(found.beams) == 1
    x0, x1, t0, b0, t1, b1 = found.beams[0]
    assert x0 <= 304 and x1 >= 398
    assert abs((b0 - t0) - 10) <= 1


def test_a_short_band_with_no_stems_is_not_a_beam():
    grey = staff(blank())
    grey[300:310, 300:325] = 0
    assert rl.find_lines(grey).beams == []


def test_a_solid_beam_floating_between_notes_is_a_beam():
    grey = staff(blank())
    grey[300:310, 300:400] = 0                              # a two-note tremolo's beam
    grey[320:323, 330:350] = 0                              # a thin band (a tie's middle) is not
    beams = rl.find_lines(grey).beams
    assert len(beams) == 1 and beams[0][0] <= 301 and beams[0][1] >= 399


def test_a_curve_is_traced():
    grey = staff(blank())
    xs = np.arange(200, 400)
    ys = 300 + ((xs - 300) / 100) ** 2 * 15                 # a tie-like arc
    for x, y in zip(xs, ys):
        grey[int(y):int(y) + 3, x] = 0
    found = rl.find_lines(grey)
    assert len(found.curves) == 1
    trace = found.curves[0]
    assert trace[0][0] < 202 and trace[-1][0] > 398


def test_a_tilted_page_is_turned_level():
    grey = staff(blank())
    m = cv2.getRotationMatrix2D((400, 200), 0.8, 1.0)
    tilted = cv2.warpAffine(grey, m, (800, 400), borderValue=255)
    assert abs(rl.tilt(tilted) + 0.8) <= 0.04
    levelled, angle = rl.level(tilted)
    assert abs(angle + 0.8) <= 0.04
    assert len([l for l in rl.find_lines(levelled).level if l[2] - l[1] > 500]) == 5
    assert rl.level(grey) == (grey, 0.0)


def test_drawings_are_in_page_points():
    found = rl.Lines(space=20.0, level=[(100.0, 50.0, 750.0, 2.0)], vertical=[(400.0, 100.0, 182.0, 3.0)],
                     beams=[(300.0, 400.0, 250.0, 260.0, 260.0, 270.0)])
    place = rp.Placement((400, 800), pymupdf.Rect(0, 0, 200, 100))     # 4 pixels to a point
    drawn = rp.drawings(found, place)
    level, vertical, beam = drawn
    assert level["type"] == "s" and level["items"][0][1] == pymupdf.Point(12.5, 25)
    assert abs(level["width"] - 0.5) < 1e-9
    assert vertical["items"][0][2] == pymupdf.Point(100, 45.5)
    assert beam["type"] == "f" and len(beam["items"]) == 4


def test_a_raster_page_gives_its_own_drawings_and_passes_the_rest_on():
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    raster = rp.RasterPage(page, [{"type": "s"}])
    assert raster.get_drawings() == [{"type": "s"}]
    assert raster.rotation == 0
    assert raster.rect == page.rect
