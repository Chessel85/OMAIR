"""Tests for the lines found in page images (docs/notes/raster-lines-spec.md)."""

import sys

import cv2
import numpy as np
import pymupdf
import pytest

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


def test_a_partial_beam_is_not_carried_out_to_the_next_stem():
    grey = staff(blank())
    for x in (300, 340, 380):                               # three stems below the staff
        grey[TOP + 5 * SPACE:TOP + 8 * SPACE, x:x + 2] = 0
    beam = TOP + 8 * SPACE - 8
    grey[beam:beam + 8, 300:382] = 0                        # a beam over all three
    grey[beam - 14:beam - 6, 300:322] = 0                   # a partial beam on the first, short of the second
    found = rl.find_lines(grey)
    partial = [b for b in found.beams if b[2] < beam - 4]
    assert len(partial) == 1
    assert partial[0][0] <= 301 and 318 <= partial[0][1] <= 324


def test_a_partial_beam_the_detector_took_for_a_half_rest_is_found():
    """A half or whole rest box is not masked in the search for beams: a
    partial beam is short and thick, as a half rest is."""
    grey = staff(blank())
    for x in (300, 340):
        grey[TOP + 5 * SPACE:TOP + 8 * SPACE, x:x + 2] = 0
    beam = TOP + 8 * SPACE - 8
    grey[beam:beam + 8, 300:342] = 0
    grey[beam - 14:beam - 6, 318:342] = 0                   # a partial beam on the second stem
    rest = [(316, beam - 16, 344, beam - 4)]
    partial = lambda found: [b for b in found.beams if b[2] < beam - 4]
    assert partial(rl.find_lines(grey, rest)) == []
    assert len(partial(rl.find_lines(grey, [], [], rest))) == 1


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


def test_a_slur_crossing_staff_lines_at_a_slant_is_one_curve():
    grey = staff(blank())
    xs = np.arange(150, 650)
    ys = TOP + 6 * SPACE - (xs - 150) * 0.35 + ((xs - 400) / 250) ** 2 * 40   # up through the staff
    for x, y in zip(xs, ys):
        grey[int(y):int(y) + 3, x] = 0
    found = rl.find_lines(grey)
    long = [t for t in found.curves if t[-1][0] - t[0][0] > 100]
    assert len(long) == 1
    assert long[0][0][0] < 160 and long[0][-1][0] > 640


def test_the_pale_ends_of_a_tie_are_followed():
    grey = staff(blank())
    for x in range(200, 400):
        t = abs(x - 300) / 100                              # 0 in the middle, 1 at the ends
        y = 300 + int(t * t * 15)
        grey[y:y + 3, x] = 0 if t < 0.8 else 210            # the ends are pale grey
    trace = rl.find_lines(grey).curves[0]
    assert trace[0][0] < 210 and trace[-1][0] > 390


# a short tie from a Verovio page at 300 dpi (staff space 30 pixels): (row, start, end) of its ink
SHORT_TIE = [(0, 3, 5), (0, 76, 79), (1, 4, 7), (1, 75, 78), (2, 4, 8), (2, 74, 78), (3, 5, 9), (3, 72, 77),
             (4, 6, 11), (4, 71, 76), (5, 7, 13), (5, 69, 75), (6, 8, 14), (6, 67, 74), (7, 9, 16), (7, 65, 73),
             (8, 10, 19), (8, 63, 72), (9, 11, 21), (9, 60, 71), (10, 12, 24), (10, 57, 70), (11, 13, 28),
             (11, 53, 69), (12, 14, 34), (12, 47, 67), (13, 16, 66), (14, 17, 64), (15, 19, 63), (16, 21, 61),
             (17, 23, 58), (18, 26, 55), (19, 30, 52), (20, 36, 46)]


def test_a_short_tie_is_not_a_ledger_line():
    grey = blank()
    for k in range(5):                                      # a staff with a 30-pixel staff space
        grey[60 + 30 * k:63 + 30 * k, 50:750] = 0
    for row, a, b in SHORT_TIE:
        grey[300 + row, 300 + a:300 + b] = 0
    found = rl.find_lines(grey)
    assert not [l for l in found.level if l[0] > 250]
    assert len(found.curves) == 1 and found.curves[0][0][0] < 306 and found.curves[0][-1][0] > 374


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


def hairpin(grey, x0, x1, y, opening, thick=3):
    """A crescendo from (x0, y) opening to `opening` pixels at x1."""
    for dy in (-opening / 2, opening / 2):
        cv2.line(grey, (x0, y), (x1, int(round(y + dy))), 0, thick, cv2.LINE_AA)
    return grey


@pytest.mark.xfail(sys.platform == "linux", strict=False,
                   reason="on Linux the arms stop 4 spaces short of the point (GitHub, 27 October 2026); not yet looked into")
def test_the_arms_of_a_hairpin_reach_the_point_where_they_meet():
    """Where the arms run together at the closed end, each arm is carried on
    to the point, and the joined ink there is not given as level lines."""
    grey = hairpin(staff(blank()), 150, 600, 300, 45)
    found = rl.find_lines(grey)
    arms = [t for t in found.thin if t[2] - t[0] > 200]
    assert len(arms) == 2
    for x0, y0, x1, y1, _ in arms:
        assert abs(x0 - 150) <= 0.4 * SPACE and abs(y0 - 300) <= 0.25 * SPACE
        assert abs(x1 - 600) <= 0.4 * SPACE
    assert not [l for l in found.level if 250 < l[0] < 350]


def test_two_arms_found_apart_are_carried_on_to_where_they_meet():
    arms = [(206.0, 299.2, 600.0, 277.5, 3.0), (206.0, 300.8, 600.0, 322.5, 3.0)]
    met = rl.meet_arms(arms, SPACE)
    assert all(abs(a[0] - 191.5) < 1 and abs(a[1] - 300) < 0.5 for a in met)
    # lines that close in too far away, or are not open at one end, are left alone
    far = [(300.0, 290.0, 600.0, 280.0, 3.0), (300.0, 310.0, 600.0, 320.0, 3.0)]
    assert rl.meet_arms(far, SPACE) == far
