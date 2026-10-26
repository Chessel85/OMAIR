"""Staff lines and the other lines of a page image (Stage 2.2).

The vector reader takes its lines from a PDF's drawings. This module finds
the same lines in an image, in pixels; omr.raster.page turns them into
drawings, so layout.py and notation.py read them unchanged.

The rules are in docs/notes/raster-lines-spec.md. In short:

1. Ink is every pixel darker than INK_BELOW. The staff space comes from the
   commonest black and white runs down the columns. A tilted page is turned
   level first (level, called by omr.raster.page).
2. Level lines are runs along the rows, at least half a staff space long,
   joined down the rows while both ends stay put; vertical lines are the
   same down the columns. A line counts if it is thin, is not a stair step
   of something sloping or a slice of something thicker, and does not lie
   almost wholly inside a symbol's box (the inside of a notehead, a clef's
   stroke, a sharp). Centres and thicknesses are measured to a fraction of
   a pixel from the grey levels.
3. Beams are found on the ink left when the staff lines, the vertical lines
   and the symbols are taken away: runs down the columns 0.3 to 0.95 staff
   spaces long, joined along the page into straight bands of even
   thickness, which must sit on stems (or be solid, for hidden stems and
   tremolos).
4. What is left is traced, with staff lines put back where a curve crosses
   them at a slant: straight pieces are thin lines (hairpins, brackets),
   bowed ones curves (ties, slurs). Curve pieces that carry on from each
   other are joined, and each curve is followed out through its paler
   tapering ends. Evenly spaced short dashes on one row make a dashed line.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

INK_BELOW = 170          # grey level: darker pixels are ink
LEVEL_INK_BELOW = 200    # for level lines at low resolution: a thin staff line is a pair of light grey rows
LOW_RESOLUTION_SPACE = 12   # pixels: a smaller staff space is low resolution (150 dpi)
INSIDE_SHARE = 0.9       # a line this much inside a symbol box is part of the symbol
LEVEL_MAX_THICK = 0.3    # staff spaces
VERTICAL_MAX_WIDTH = 0.7
LEVEL_MIN_LENGTH = 0.5
VERTICAL_MIN_LENGTH = 0.8
BEAM_THICK = (0.3, 0.95)
BEAM_MIN_LENGTH = 0.6
TRACE_MIN_WIDTH = 0.8    # staff spaces: the narrowest curve the reader takes
TRACE_MAX_THICK = 0.4
CURVE_END_INK = 230     # grey level: the thin tapering end of a curve is paler than ink
STRAIGHT_WITHIN = 0.08   # staff spaces from a fitted line


@dataclass
class Lines:
    """The lines of one page image, in pixels. Level lines are (y, x0, x1,
    thickness), vertical lines (x, top, bottom, width), beams (x0, x1, top0,
    bottom0, top1, bottom1): the top and bottom edge at each end. Edges are
    pixel edges, so a run of pixels 10 to 12 spans 10 to 13."""

    space: float
    level: list = field(default_factory=list)
    vertical: list = field(default_factory=list)
    beams: list = field(default_factory=list)
    thin: list = field(default_factory=list)     # (x0, y0, x1, y1, thickness) of sloping thin lines
    curves: list = field(default_factory=list)   # (x, top, bottom) along each curve, left to right
    dashed: list = field(default_factory=list)   # (y, x0, x1, thickness) of level dashed lines
    tilt: float = 0.0                            # degrees the image was turned to level it


def ink_of(grey):
    return grey < INK_BELOW


# ---------------------------------------------------------------- runs

def runs(ink):
    """(row, start, end) of every run of ink along the rows, end exclusive."""
    h, w = ink.shape
    padded = np.zeros((h, w + 2), np.int8)
    padded[:, 1:-1] = ink
    step = np.diff(padded, axis=1)
    rows, starts = np.nonzero(step == 1)
    _, ends = np.nonzero(step == -1)
    return rows, starts, ends


def staff_space(ink):
    """(staff space, line thickness) in pixels, from the commonest black run
    and the commonest white run between black runs down the columns."""
    cols, starts, ends = runs(ink[:, ::3].T)
    black = ends - starts
    same = cols[1:] == cols[:-1]
    white = (starts[1:] - ends[:-1])[same]
    if not len(black) or not len(white):
        return None, None
    thick = int(np.bincount(black[black < 50]).argmax()) if (black < 50).any() else 1
    white = white[(white > thick) & (white < 200)]
    if not len(white):
        return None, thick
    gap = int(np.bincount(white).argmax())
    return float(gap + thick), float(thick)


def join_runs(rows, starts, ends, tol, gap=0):
    """Join runs on neighbouring rows whose start and end are each within
    `tol` of the last run joined, or which overlap it along 90 percent of the
    longer of the two. Returns (first row, last row, start, end)
    per joined line: the start and end are the medians of the runs."""
    order = np.lexsort((starts, rows))
    open_lines = []   # [last row, last start, last end, first row, starts, ends]
    done = []
    current_row = None
    for k in order:
        r, s, e = int(rows[k]), int(starts[k]), int(ends[k])
        if r != current_row:
            current_row = r
            still = []
            for line in open_lines:
                (still if line[0] >= r - 1 - gap else done).append(line)
            open_lines = still
        best = None
        for line in open_lines:
            if line[0] >= r:
                continue
            same_ends = abs(line[1] - s) <= tol and abs(line[2] - e) <= tol
            # or nearly the same span: a break of a pixel or two near one end
            same_span = min(line[2], e) - max(line[1], s) >= 0.9 * max(line[2] - line[1], e - s)
            if same_ends or same_span:
                if best is None or abs(line[1] - s) + abs(line[2] - e) < abs(best[1] - s) + abs(best[2] - e):
                    best = line
        if best is None:
            open_lines.append([r, s, e, r, [s], [e]])
        else:
            best[0], best[1], best[2] = r, s, e
            best[4].append(s)
            best[5].append(e)
    done += open_lines
    return [(line[3], line[0], int(np.median(line[4])), int(np.median(line[5]))) for line in done]


# ---------------------------------------------------------------- symbols

def box_mask(shape, boxes, pad=1):
    """A mask of the symbol boxes (x0, y0, x1, y1 in pixels)."""
    mask = np.zeros(shape, bool)
    h, w = shape
    for x0, y0, x1, y1 in boxes:
        a, b = max(int(y0) - pad, 0), min(int(np.ceil(y1)) + pad, h)
        c, d = max(int(x0) - pad, 0), min(int(np.ceil(x1)) + pad, w)
        if a < b and c < d:
            mask[a:b, c:d] = True
    return mask


def _inside(mask, rows, cols):
    """The share of the pixels at (rows, cols) that lie in the mask."""
    return float(mask[rows, cols].mean()) if len(rows) else 0.0


# ---------------------------------------------------------------- lines

def _centre(dark, lo, hi, across):
    """(centre, thickness) of a line to a fraction of a pixel. At each
    position in `across` along the line, the centroid of the darkness over
    pixels lo-1 to hi+1 across it and the darkness summed across it; the
    medians of those, so ink touching the line in a few places does not move
    it. `dark` is the darkness image, oriented so the line runs along its rows."""
    a, b = max(lo - 1, 0), min(hi + 2, dark.shape[0])
    strip = dark[a:b][:, across].astype(np.float64)
    totals = strip.sum(axis=0)
    good = totals > 0
    clear = good & (strip[0] < 128) & (strip[-1] < 128)   # nothing touching the line here
    if clear.sum() >= 3:
        good = clear
    if not good.any():
        return (lo + hi + 1) / 2, float(hi - lo + 1)
    centres = (strip[:, good] * (np.arange(b - a)[:, None] + 0.5)).sum(axis=0) / totals[good]
    return a + float(np.median(centres)), float(np.median(totals[good]) / 255)


def _along(x0, x1):
    """Up to 64 positions along a line, away from its ends."""
    inner = max((x1 - x0) // 8, 0)
    return np.unique(np.linspace(x0 + inner, x1 - 1 - inner, num=min(64, max(x1 - x0 - 2 * inner, 1))).astype(int))


def _stair_step(ink, top, bottom, x0, x1, both):
    """A row run of a curve, a sloping line or a sloping beam, not a level
    line: at its ends the row above or below carries the ink on unbroken
    past the end by two pixels or more, while the run's own middle row stops
    there. With `both`, at both ends (every row of a sloping beam or line
    steps at both ends, while a bracket's hook can sit over one end of a
    staff line); otherwise at either end (the short runs at a curve's ends)."""
    h, w = ink.shape
    middle = (top + bottom) // 2

    def steps(row):
        right = x1 + 2 <= w and not ink[middle, x1:x1 + 2].any() and ink[row, x1 - 1:x1 + 2].all()
        left = x0 >= 2 and not ink[middle, x0 - 2:x0].any() and ink[row, x0 - 2:x0 + 1].all()
        return left, right

    ends = [steps(row) for row in (top - 1, bottom + 1) if 0 <= row < h]
    left = any(e[0] for e in ends)
    right = any(e[1] for e in ends)
    return (left and right) if both else (left or right)


def _slice(ink, top, bottom, x0, x1):
    """A slice of something thicker (a level beam cut by a staff line): the
    row above or below is ink along nearly all its length."""
    h = ink.shape[0]
    return any(0 <= row < h and ink[row, x0:x1].mean() >= 0.9 for row in (top - 1, bottom + 1))


def _tapers(ink, top, bottom, x0, x1):
    """The rows of a short level line differ in length: one of them is ink
    along less than 75 percent of the line. A ledger line's rows are all
    full; the thick middle of a tie, whose rows grow shorter towards its
    outer edge, is not a line."""
    return any(ink[row, x0:x1].mean() < 0.75 for row in range(top, bottom + 1))


def level_lines(ink, dark, space, mask):
    """(level lines, their pixels as (top row, bottom row, x0, x1))."""
    rows, starts, ends = runs(ink)
    keep = ends - starts >= LEVEL_MIN_LENGTH * space
    tol = max(2, round(0.1 * space))
    out, pixels = [], []
    for top, bottom, x0, x1 in join_runs(rows[keep], starts[keep], ends[keep], tol):
        thick = bottom - top + 1
        if thick > max(LEVEL_MAX_THICK * space, 2):
            continue
        if _stair_step(ink, top, bottom, x0, x1, x1 - x0 >= 3 * space) or _slice(ink, top, bottom, x0, x1):
            continue
        if x1 - x0 < 4 * space and _tapers(ink, top, bottom, x0, x1):
            continue
        y = (top + bottom) // 2
        xs = np.arange(x0, x1)
        if mask is not None and _inside(mask, np.full(len(xs), y), xs) >= INSIDE_SHARE:
            continue
        centre, thickness = _centre(dark, top, bottom, _along(x0, x1))
        out.append((centre, float(x0), float(x1), thickness))
        pixels.append((top, bottom, x0, x1))
    return out, pixels


def merge_side_by_side(groups):
    """Join vertical lines whose columns touch and whose lengths overlap by
    at least 80 percent of the longer: the edge columns of one stem can end
    a pixel or two away from its middle ones and form a line of their own,
    which the reader would take as a second stem. (The columns of a
    notehead beside a stem are much shorter than it, and stay apart.)"""
    groups = sorted(groups, key=lambda g: (g[0], g[2]))
    out = []
    for left, right, top, bottom in groups:
        for k in range(len(out) - 1, max(len(out) - 200, 0) - 1, -1):
            l2, r2, t2, b2 = out[k]
            if left > r2 + 1 or right < l2 - 1:
                continue
            overlap = min(b2, bottom) - max(t2, top)
            if overlap >= 0.8 * max(b2 - t2, bottom - top):
                out[k] = (min(l2, left), max(r2, right), min(t2, top), max(b2, bottom))
                break
        else:
            out.append((left, right, top, bottom))
    return out


def vertical_lines(ink, dark, space, mask):
    """(vertical lines, their pixels as (left col, right col, top, bottom))."""
    cols, starts, ends = runs(ink.T)
    keep = ends - starts >= VERTICAL_MIN_LENGTH * space
    tol = max(2, round(0.1 * space))
    out, pixels = [], []
    for left, right, top, bottom in merge_side_by_side(join_runs(cols[keep], starts[keep], ends[keep], tol)):
        width = right - left + 1
        if width > max(VERTICAL_MAX_WIDTH * space, 2):
            continue
        x = (left + right) // 2
        ys = np.arange(top, bottom)
        if mask is not None and _inside(mask, ys, np.full(len(ys), x)) >= INSIDE_SHARE:
            continue
        centre, width = _centre(dark.T, left, right, _along(top, bottom))
        out.append((centre, float(top), float(bottom), width))
        pixels.append((left, right, top, bottom))
    return out, pixels


def remove_staff_lines(ink, level_pixels, space):
    """The ink with the long thin level lines taken away, except where other
    ink lies both just above and just below them (a barline, a stem, a
    notehead or beam across the line). A line in the narrow gap between two
    beams goes, so the beams stay apart."""
    out = ink.copy()
    h = ink.shape[0]
    for top, bottom, a, b in level_pixels:
        if b - a < 4 * space:
            continue
        above = ink[max(top - 1, 0), a:b] if top > 0 else np.zeros(b - a, bool)
        below = ink[min(bottom + 1, h - 1), a:b] if bottom < h - 1 else np.zeros(b - a, bool)
        clear = ~(above & below)
        out[top:bottom + 1, a:b] &= ~clear
    return out


def erase_verticals(ink, vertical_pixels):
    out = ink.copy()
    for left, right, top, bottom in vertical_pixels:
        out[top:bottom, max(left - 1, 0):right + 2] = False
    return out


def beams(rest, space):
    """Beams on the ink with staff lines, vertical lines and symbols taken away."""
    cols, starts, ends = runs(rest.T)
    length = ends - starts
    keep = (length >= BEAM_THICK[0] * space) & (length <= BEAM_THICK[1] * space)
    cols, starts, ends = cols[keep], starts[keep], ends[keep]
    gap = max(2, round(0.35 * space))   # a stem taken away leaves a gap
    tol = max(3, round(0.2 * space))   # a staff line taken away from an edge moves it by its thickness
    open_bands = []   # [last col, last top, last bottom, [cols], [tops], [bottoms]]
    done = []
    current = None
    for k in np.lexsort((starts, cols)):
        c, t, b = int(cols[k]), int(starts[k]), int(ends[k])
        if c != current:
            current = c
            still = []
            for band in open_bands:
                (still if band[0] >= c - 1 - gap else done).append(band)
            open_bands = still
        best = None
        for band in open_bands:
            if band[0] < c and abs(band[1] - t) <= tol + (c - band[0] - 1) // 2 \
                    and abs(band[2] - b) <= tol + (c - band[0] - 1) // 2:
                if best is None or abs(band[1] - t) < abs(best[1] - t):
                    best = band
        if best is None:
            open_bands.append([c, t, b, [c], [t], [b]])
        else:
            best[0], best[1], best[2] = c, t, b
            best[3].append(c)
            best[4].append(t)
            best[5].append(b)
    done += open_bands
    out = []
    for _, _, _, cs, ts, bs in done:
        out += _band_beams(np.array(cs, float), np.array(ts, float), np.array(bs, float), space)
    return out


def _beam_fit(cs, ts, bs, space):
    """(x0, x1, top0, bottom0, top1, bottom1) if the columns make one beam:
    long enough, mostly present, with a straight middle and an even
    thickness; else None. The edges are the middle line less and plus half
    the median thickness (a staff line touching an edge here and there
    moves it by its own thickness, which a fit to each edge would follow)."""
    x0, x1 = cs.min(), cs.max() + 1
    if x1 - x0 < BEAM_MIN_LENGTH * space or len(cs) < 0.6 * (x1 - x0):
        return None
    middle = (ts + bs) / 2
    thick = float(np.median(bs - ts))
    fit = np.polyfit(cs, middle, 1) if len(set(cs)) > 1 else np.array([0.0, middle.mean()])
    if abs(fit[0]) > 1:
        return None
    if np.percentile(np.abs(np.polyval(fit, cs) - middle), 90) > max(2.0, 0.12 * space):
        return None
    if np.percentile(np.abs((bs - ts) - thick), 75) > max(2.0, 0.15 * space):
        return None
    m0, m1 = np.polyval(fit, [x0, x1])
    return (float(x0), float(x1), float(m0 - thick / 2), float(m0 + thick / 2),
            float(m1 - thick / 2), float(m1 + thick / 2))


def join_beams(found, space):
    """Join beams that carry on from each other: the second starts within
    0.35 staff spaces of the first's end, with its top and bottom where the
    first's edges lead and much the same slope (a beam can be cut where a
    note of another voice touches it)."""
    tol = max(2.0, 0.15 * space)
    out = sorted(found)
    joined = True
    while joined:
        joined = False
        for i, a in enumerate(out):
            ax0, ax1, at0, ab0, at1, ab1 = a
            slope = (at1 - at0) / max(ax1 - ax0, 1)
            for j, b in enumerate(out):
                bx0, bx1, bt0, bb0, bt1, bb1 = b
                if j == i or not 0 <= bx0 - ax1 <= 0.35 * space:
                    continue
                lead = bx0 - ax1
                if abs(at1 + slope * lead - bt0) > tol or abs(ab1 + slope * lead - bb0) > tol:
                    continue
                if abs((bt1 - bt0) / max(bx1 - bx0, 1) - slope) > 0.08:
                    continue
                out[i] = (ax0, bx1, at0, ab0, bt1, bb1)
                del out[j]
                joined = True
                break
            if joined:
                break
    return out


def refine_beam(beam, dark):
    """The beam with its middle and thickness measured to a fraction of a
    pixel, as for level lines: at columns along it, the centroid of the
    darkness from one pixel above to one below, and the darkness summed;
    the median shift of the middle and the median thickness, using only
    columns where nothing touches the beam when there are enough."""
    x0, x1, t0, b0, t1, b1 = beam
    h = dark.shape[0]
    inner = (x1 - x0) * 0.15
    cols = np.unique(np.linspace(x0 + inner, x1 - 1 - inner, num=32).astype(int))
    shifts, thicks, clear = [], [], []
    for c in cols:
        f = (c + 0.5 - x0) / max(x1 - x0, 1)
        top, bottom = t0 + f * (t1 - t0), b0 + f * (b1 - b0)
        a, b = max(int(np.floor(top)) - 1, 0), min(int(np.ceil(bottom)) + 1, h)
        strip = dark[a:b, c].astype(np.float64)
        total = strip.sum()
        if total <= 0:
            continue
        centre = a + float((strip * (np.arange(b - a) + 0.5)).sum() / total)
        shifts.append(centre - (top + bottom) / 2)
        thicks.append(total / 255)
        clear.append(strip[0] < 128 and strip[-1] < 128)
    if not shifts:
        return beam
    shifts, thicks, clear = np.array(shifts), np.array(thicks), np.array(clear)
    if clear.sum() >= 3:
        shifts, thicks = shifts[clear], thicks[clear]
    d, half = float(np.median(shifts)), float(np.median(thicks)) / 2
    measured = ((b0 - t0) + (b1 - t1)) / 4
    if not 0.6 * measured <= half <= 1.5 * measured or abs(d) > measured:
        return beam     # the darkness disagrees with the pixels: keep what was measured
    m0, m1 = (t0 + b0) / 2 + d, (t1 + b1) / 2 + d
    return (x0, x1, m0 - half, m0 + half, m1 - half, m1 + half)


def _solid(beam, ink):
    """The beam's shape is solid ink with clear paper along its top and
    bottom: at least 95 percent ink inside, at most 15 percent in the rows
    just outside each edge. A slur's thick middle is curved and tapers, so
    it fails one or the other."""
    x0, x1, t0, b0, t1, b1 = beam
    h = ink.shape[0]
    count = in_ink = edge_count = edge_ink = 0
    for c in range(int(x0) + 1, int(x1) - 1):
        f = (c + 0.5 - x0) / max(x1 - x0, 1)
        top, bottom = t0 + f * (t1 - t0), b0 + f * (b1 - b0)
        a, b = int(np.ceil(top)), int(np.floor(bottom))
        if a >= b:
            continue
        col = ink[max(a, 0):min(b, h), c]
        count += len(col)
        in_ink += int(col.sum())
        for row in (a - 2, b + 1):
            if 0 <= row < h:
                edge_count += 1
                edge_ink += int(ink[row, c])
    return count > 0 and in_ink >= 0.95 * count and edge_ink <= 0.15 * max(edge_count, 1)


def one_each(found, space):
    """Beams less those that repeat another: two pieces of one beam, each
    reaching out to the same stems, cover the same span at the same height."""
    out = []
    for b in sorted(found, key=lambda b: b[0] - b[1]):     # longest first
        x0, x1, t0, b0, t1, b1 = b
        same = False
        for c in out:
            overlap = min(x1, c[1]) - max(x0, c[0])
            if (overlap >= 0.8 * (x1 - x0) and abs((t0 + b0) / 2 - (c[2] + c[3]) / 2) <= 0.25 * space
                    and abs((t1 + b1) / 2 - (c[4] + c[5]) / 2) <= 0.25 * space):
                same = True
                break
        if not same:
            out.append(b)
    return out


def _stem_at(x, top, bottom, vertical_pixels, space, outward):
    """The vertical line (left, right, top, bottom) at the beam end x that
    reaches the beam edge from top to bottom and ends within 2.5 staff
    spaces of it: a stem, which ends at its outermost beam (a slur crossing
    the middle of a stem or a barline is not a beam). `outward` is -1 at the
    left end, 1 at the right. The stem was taken away, so the beam found
    stops at its near edge, give or take the pixel erased beside it; a stem
    further out belongs to the next note (a partial beam stops short of it).
    A stem up to a staff space inside the end is the beam's too. None if
    there is none."""
    best = None
    for v in vertical_pixels:
        left, right, v_top, v_bottom = v
        d = abs((left + right + 1) / 2 - x)
        beyond = (left - x) if outward > 0 else (x - right - 1)
        if beyond > max(3, 0.2 * space) or d > 1.0 * space:
            continue
        if v_top > bottom + 0.2 * space or v_bottom < top - 0.2 * space:
            continue
        if min(abs(v_top - top), abs(v_bottom - bottom)) <= 2.5 * space and (best is None or d < best[0]):
            best = (d, v)
    return best[1] if best else None


def on_stems(beam, vertical_pixels, space, ink):
    """The beam reaching to the outer edge of the stem at each end, or None
    if it is not on stems: a beam has a stem at each end, a short one (a
    partial beam) at one. A longer one with a stem at one end only must be
    solid (_solid): the stem at its other end can be hidden (the reader
    finds those from the noteheads). The stems were taken away, so the beam
    found stops short of them."""
    x0, x1, t0, b0, t1, b1 = beam
    first = _stem_at(x0, t0, b0, vertical_pixels, space, -1)
    last = _stem_at(x1, t1, b1, vertical_pixels, space, 1)
    one = bool(first) != bool(last)
    if not ((first and last) or (one and (x1 - x0 <= 1.6 * space or _solid(beam, ink)))):
        return None
    slope_t = (t1 - t0) / max(x1 - x0, 1)
    slope_b = (b1 - b0) / max(x1 - x0, 1)
    if first and first[0] < x0:
        t0, b0 = t0 - slope_t * (x0 - first[0]), b0 - slope_b * (x0 - first[0])
        x0 = float(first[0])
    if last and last[1] + 1 > x1:
        t1, b1 = t1 + slope_t * (last[1] + 1 - x1), b1 + slope_b * (last[1] + 1 - x1)
        x1 = float(last[1] + 1)
    return (x0, x1, t0, b0, t1, b1)


def _band_beams(cs, ts, bs, space):
    """The beams in a band of joined runs. A band can run across a stem's
    gap into the next beam group, which slopes another way, so it is cut at
    its gaps and the pieces joined again, left to right, while they still
    make one straight beam."""
    whole = _beam_fit(cs, ts, bs, space)
    if whole is not None:
        return [whole]
    cuts = np.nonzero(np.diff(cs) > 1)[0] + 1
    if not len(cuts):
        return []
    pieces = np.split(np.arange(len(cs)), cuts)
    out = []
    current = pieces[0]
    for piece in pieces[1:]:
        joined = np.r_[current, piece]
        if _beam_fit(cs[joined], ts[joined], bs[joined], space) is not None:
            current = joined
            continue
        fit = _beam_fit(cs[current], ts[current], bs[current], space)
        if fit is not None:
            out.append(fit)
        current = piece
    fit = _beam_fit(cs[current], ts[current], bs[current], space)
    if fit is not None:
        out.append(fit)
    return out


def erase_beams(ink, found):
    out = ink.copy()
    for x0, x1, t0, b0, t1, b1 in found:
        corners = np.array([[x0, t0 - 1], [x1, t1 - 1], [x1, b1 + 1], [x0, b0 + 1]], np.int32)
        cv2.fillPoly(out.view(np.uint8), [corners], 0)
    return out


def erase_level(ink, level_pixels, space):
    """The ink with the short level lines (ledger lines, brackets) taken
    away; staff lines were taken away already, keeping what crosses them."""
    out = ink.copy()
    for top, bottom, x0, x1 in level_pixels:
        if x1 - x0 < 4 * space:
            out[max(top - 1, 0):bottom + 2, x0:x1] = False
    return out


def _fit(xs, ys):
    """(slope, intercept, largest distance from the line) of points."""
    if len(set(xs.tolist())) < 2:
        return 0.0, float(ys.mean()), float(np.abs(ys - ys.mean()).max())
    slope, intercept = np.polyfit(xs, ys, 1)
    return float(slope), float(intercept), float(np.abs(np.polyval((slope, intercept), xs) - ys).max())


def bridge_crossings(left, ink, level_pixels, space):
    """The leftover ink with the staff line put back where a curve or a thin
    line crosses it at a slant: its ink is just above the line and, a little
    along, just below (or the other way), with nothing between. Staff lines
    are kept only under ink both just above and just below the same column,
    so such a crossing was cut. Only the columns between the two sides are
    put back, within half a staff space."""
    out = left.copy()
    h = left.shape[0]
    reach = max(2, round(0.5 * space))
    for top, bottom, a, b in level_pixels:
        if b - a < 4 * space or top < 1 or bottom >= h - 1:
            continue
        above, below = left[top - 1, a:b], left[bottom + 1, a:b]
        last = None     # (column, side) of the last ink seen along the line
        for c in np.nonzero(above | below)[0]:
            side = 0 if above[c] and below[c] else (1 if above[c] else 2)
            if last and side and last[1] and side != last[1] and 0 < c - last[0] <= reach:
                out[top:bottom + 1, a + last[0]:a + c + 1] |= ink[top:bottom + 1, a + last[0]:a + c + 1]
            last = (c, side)
    return out


def _end_slope(trace, side, space):
    """The slope of a trace's middle over its last half staff space at one
    end: side 1 is the right end, -1 the left."""
    n = max(3, round(0.5 * space))
    points = trace[-n:] if side > 0 else trace[:n]
    xs = np.array([p[0] for p in points])
    mids = np.array([(p[1] + p[2]) / 2 for p in points])
    return float(np.polyfit(xs, mids, 1)[0]) if len(set(xs.tolist())) > 1 else 0.0


def extend_curve(trace, pale, space):
    """The curve carried on at each end through paler ink (pale), as far as
    a staff space: the thin tapering ends of ties and slurs are lighter than
    the ink level, so a trace stops short. Each step follows the direction
    of the last half staff space, and a gap of 0.4 staff spaces (a staff
    line, stem or barline taken away, with the pixels beside it) is
    crossed."""
    h, w = pale.shape
    near = max(2, round(0.1 * space))
    gap = max(3, round(0.4 * space))
    for end in (1, -1):
        slope = _end_slope(trace, end, space)
        last = trace[-1] if end > 0 else trace[0]
        start = int(last[0])
        y, at = (last[1] + last[2]) / 2, 0     # the last middle found, and its step
        added, missed = [], 0
        for step in range(1, int(space) + 1):
            c = start + end * step
            want = y + slope * end * (step - at)
            if not 0 <= c < w:
                break
            a, b = max(int(want) - near, 0), min(int(want) + near + 1, h)
            rows = np.nonzero(pale[a:b, c])[0]
            if not len(rows):
                missed += 1
                if missed > gap:
                    break
                continue
            missed = 0
            top, bottom = float(a + rows[0]), float(a + rows[-1] + 1)
            added.append((c + 0.5, top, bottom))
            y, at = (top + bottom) / 2, step
        trace = (trace + added) if end == 1 else (added[::-1] + trace)
    return trace


def join_curves(curves, space):
    """Curves that carry on from each other made one: the second starts
    within half a staff space of the first's end (or overlaps it a little),
    at the height the first's end leads to, in much the same direction. A
    long slur crossing staff lines and stems can be cut in pieces."""
    out = sorted(curves, key=lambda t: t[0][0])
    joined = True
    while joined:
        joined = False
        for i, a in enumerate(out):
            ax, ay = a[-1][0], (a[-1][1] + a[-1][2]) / 2
            sa = _end_slope(a, 1, space)
            for j, b in enumerate(out):
                if j == i:
                    continue
                bx, by = b[0][0], (b[0][1] + b[0][2]) / 2
                if not -0.3 * space <= bx - ax <= 0.5 * space or b[-1][0] <= ax:
                    continue
                if abs(by - (ay + sa * (bx - ax))) > 0.3 * space or abs(_end_slope(b, -1, space) - sa) > 0.5:
                    continue
                out[i] = [p for p in a if p[0] < bx] + b
                del out[j]
                joined = True
                break
            if joined:
                break
    return out


def traces(left, space):
    """Sloping thin lines and curves in the ink left when the staff lines,
    vertical lines, level lines, beams and symbols are taken away. A gap
    where a stem was taken away is bridged first. Each piece of ink at least
    TRACE_MIN_WIDTH wide is followed column by column: with one run in each
    column it is a single line, with two (a hairpin's arms) it is two. A
    straight line is a thin line; a single bowed one is a curve."""
    bridge = max(3, round(0.35 * space))
    joined = cv2.morphologyEx(left.view(np.uint8), cv2.MORPH_CLOSE, np.ones((3, bridge), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    thin, curves = [], []
    within = max(1.5, STRAIGHT_WITHIN * space)
    for k in range(1, count):
        x, y, w, h, _ = stats[k]
        if w < TRACE_MIN_WIDTH * space or h > 0.6 * w + 2 * space:
            continue
        piece = labels[y:y + h, x:x + w] == k
        cols, starts, ends = runs(piece.T)
        if not len(cols):
            continue
        per_col = np.bincount(cols, minlength=w)
        lengths = ends - starts
        if np.median(lengths) > TRACE_MAX_THICK * space:
            continue
        mids = (starts + ends) / 2
        if (per_col >= 2).mean() > 0.3:
            thin += [(x + x0, y + y0, x + x1, y + y1, thick)
                     for x0, y0, x1, y1, thick in _arms(cols, mids, lengths, per_col, within, space)]
            continue
        single = per_col[cols] == 1
        xs, ys = cols[single].astype(float), mids[single]
        if len(xs) < 0.5 * w:
            continue
        slope, b, off = _fit(xs, ys)
        thick = float(np.median(lengths[single]))
        if off <= within:
            if abs(slope) <= 1:
                thin.append((x + xs.min(), y + slope * xs.min() + b, x + xs.max() + 1,
                             y + slope * (xs.max() + 1) + b, thick))
            continue
        tops = starts[single].astype(float)
        bottoms = ends[single].astype(float)
        curves.append([(x + c + 0.5, y + t, y + e) for c, t, e in zip(xs, tops, bottoms)])
    return thin, curves


HAIRPIN_REACH = 4.0   # staff spaces: how far a hairpin's arms are carried on to where they meet


def _arms(cols, mids, lengths, per_col, within, space):
    """The two arms of a hairpin, (x0, y0, x1, y1, thickness) in the piece's
    pixels: the first and the last run in each column where they are apart.
    Where the arms run together at the closed end, a column holds one run;
    so each arm is carried on along its own line to the point where the two
    meet, within the piece's ink (and half a staff space beyond it)."""
    apart = per_col[cols] >= 2
    cs, ms, ls = cols[apart], mids[apart], lengths[apart]
    first = np.unique(cs, return_index=True)[1]
    last = np.r_[first[1:] - 1, len(cs) - 1]
    fits = []
    for pick in (first, last):
        xs, ys = cs[pick].astype(float), ms[pick]
        slope, b, off = _fit(xs, ys)
        if off > within or abs(slope) > 1:
            return []
        fits.append((slope, b, float(xs.min()), float(xs.max()) + 1, float(np.median(ls[pick]))))
    (s0, b0, lo, hi, t0), (s1, b1, _, _, t1) = fits
    if abs(s0 - s1) > 1e-9:
        meet = (b1 - b0) / (s0 - s1)
        # the joined ink at the closed end belongs to the piece
        if float(cols.min()) - 0.5 * space <= meet < lo:
            lo = meet
        elif hi < meet <= float(cols.max()) + 1 + 0.5 * space:
            hi = meet
    return [(lo, s * lo + b, hi, s * hi + b, t) for s, b, _, _, t in ((s0, b0, lo, hi, t0), (s1, b1, lo, hi, t1))]


def meet_arms(thin, space):
    """Thin lines (x0, y0, x1, y1, thickness) with the arms of hairpins
    found as two lines carried on to where they meet. Two lines are arms
    when one pair of their ends lies within 0.5 staff spaces across and
    1.5 apart, and they close in on each other towards the other end and
    meet within HAIRPIN_REACH staff spaces beyond it (the closed end was
    taken as level lines, so each arm starts late)."""
    out = list(thin)
    for i, a in enumerate(out):
        for j in range(i + 1, len(out)):
            b = out[j]
            sa, sb = _slope(a), _slope(b)
            if sa is None or sb is None or abs(sa - sb) < 0.01:
                continue
            for open_end, near in ((2, 0), (0, 2)):   # open at the right (meet at the left), or the other way
                if abs(a[open_end] - b[open_end]) > 0.5 * space:
                    continue
                ya, yb = a[open_end + 1], b[open_end + 1]
                if not 0.4 * space <= abs(ya - yb) <= 3 * space:
                    continue
                meet = (b[1] - sb * b[0] - a[1] + sa * a[0]) / (sa - sb)
                start = min(a[near], b[near]) if near == 0 else max(a[near], b[near])
                beyond = start - meet if near == 0 else meet - start
                if not 0 < beyond <= HAIRPIN_REACH * space:
                    continue
                ym = a[1] + sa * (meet - a[0])
                if near == 0:
                    out[i], out[j] = (meet, ym, a[2], a[3], a[4]), (meet, ym, b[2], b[3], b[4])
                else:
                    out[i], out[j] = (a[0], a[1], meet, ym, a[4]), (b[0], b[1], meet, ym, b[4])
                a = out[i]
                break
    return out


def _slope(t):
    return (t[3] - t[1]) / (t[2] - t[0]) if t[2] - t[0] > 0 else None


def _along_thin(line, thin, space):
    """The level line (y, x0, x1, thickness) lies along a sloping thin
    line at both its ends: a piece of that line taken as level."""
    y, x0, x1, _ = line
    for tx0, ty0, tx1, ty1, _ in thin:
        if tx1 - tx0 <= 0 or x0 < tx0 - 0.5 * space or x1 > tx1 + 0.5 * space:
            continue
        at = lambda x: ty0 + (ty1 - ty0) * (min(max(x, tx0), tx1) - tx0) / (tx1 - tx0)
        if abs(at(x0) - y) <= 0.25 * space and abs(at(x1) - y) <= 0.25 * space:
            return True
    return False


def dashed_lines(ink, space):
    """Level dashed lines (octave and pedal lines): at least four thin dashes
    0.2 to 1.5 staff spaces long on one row, evenly spaced with gaps of 0.2
    to 1.5 staff spaces."""
    rows, starts, ends = runs(ink)
    length = ends - starts
    keep = (length >= 0.2 * space) & (length <= 1.5 * space)
    dashes = [(top, bottom, x0, x1) for top, bottom, x0, x1 in
              join_runs(rows[keep], starts[keep], ends[keep], max(1, round(0.05 * space)))
              if bottom - top + 1 <= max(0.25 * space, 2)]
    by_row = {}
    for d in dashes:
        by_row.setdefault((d[0] + d[1]) // 2, []).append(d)
    out, used = [], set()
    for row in sorted(by_row):
        line = sorted(d for r in (row - 1, row, row + 1) for d in by_row.get(r, []) if d not in used)
        run = []
        for d in line + [None]:
            if d is not None and run:
                gap = d[2] - run[-1][3]
                if 0.2 * space <= gap <= 1.5 * space and (len(run) < 2 or abs(gap - (run[1][2] - run[0][3])) <= 0.25 * space):
                    run.append(d)
                    continue
            if len(run) >= 4:
                used.update(run)
                thick = float(np.median([b - t + 1 for t, b, _, _ in run]))
                y = float(np.median([(t + b + 1) / 2 for t, b, _, _ in run]))
                out.append((y, float(run[0][2]), float(run[-1][3]), thick))
            run = [d] if d is not None else []
    return out


def _in_dashed(line, dashed, space):
    y, x0, x1, _ = line
    return any(abs(y - dy) <= 0.2 * space and dx0 - 1 <= x0 and x1 <= dx1 + 1 for dy, dx0, dx1, _ in dashed)


def _on_staff_line(thin, level, space):
    """A nearly level thin trace lying on a staff line: a leftover scrap of
    the line, which the reader would join to it and move it."""
    x0, y0, x1, y1, _ = thin
    if abs(y1 - y0) > 0.1 * space:
        return False
    y = (y0 + y1) / 2
    return any(lx1 - lx0 >= 4 * space and abs(ly - y) <= 0.3 * space and lx0 <= x0 and x1 <= lx1
               for ly, lx0, lx1, _ in level)


TILT_LIMIT = 2.0        # degrees searched each way
TILT_MIN = 0.04         # degrees: smaller tilts are left alone


def _sharpness(dark, angle):
    h, w = dark.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rows = cv2.warpAffine(dark, m, (w, h), flags=cv2.INTER_LINEAR).sum(axis=1, dtype=np.float64)
    return float((rows ** 2).sum())


def tilt(grey):
    """Degrees to turn the page by (counterclockwise) to level it: the angle
    whose row sums are sharpest, which is when the staff lines lie along
    rows. Searched in steps of 0.2 degrees on a quarter-size image, then of
    0.02 degrees on a half-size one."""
    dark = (255 - grey).astype(np.float32)
    h, w = dark.shape
    quarter = cv2.resize(dark, (max(w // 4, 1), max(h // 4, 1)), interpolation=cv2.INTER_AREA)
    coarse = max(np.arange(-TILT_LIMIT, TILT_LIMIT + 1e-9, 0.2), key=lambda a: _sharpness(quarter, a))
    half = cv2.resize(dark, (max(w // 2, 1), max(h // 2, 1)), interpolation=cv2.INTER_AREA)
    return float(max(np.arange(coarse - 0.2, coarse + 0.2 + 1e-9, 0.02), key=lambda a: _sharpness(half, a)))


def level(grey):
    """(the page image turned level, the angle turned by in degrees). A tilt
    under TILT_MIN is left alone and the angle given as 0."""
    angle = tilt(grey)
    if abs(angle) < TILT_MIN:
        return grey, 0.0
    h, w = grey.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(grey, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=255), angle


def find_lines(grey, symbol_boxes=(), flag_boxes=(), rest_boxes=()):
    """The Lines of a greyscale page image (rows of 0 to 255). `symbol_boxes`
    are the ink boxes of the page's symbols and text, in pixels: lines
    almost wholly inside them are part of a symbol. `flag_boxes` are the
    boxes of flags, which hold the end of a stem: they are not used for that
    test, but their ink is not a beam. `rest_boxes` are the boxes of half
    and whole rests, taken as symbols except in the search for beams: the
    detector can take a partial beam for one, and a real rest has no stem
    at its end to make it a beam."""
    ink = ink_of(grey)
    space, _ = staff_space(ink)
    if space is None:
        return Lines(space=0.0)
    boxes = list(symbol_boxes) + list(rest_boxes)
    mask = box_mask(ink.shape, boxes) if boxes else None
    beam_mask = box_mask(ink.shape, symbol_boxes) if len(rest_boxes) and len(symbol_boxes) else None
    found = Lines(space=space)
    dark = 255 - grey
    level_ink = grey < LEVEL_INK_BELOW if space < LOW_RESOLUTION_SPACE else ink
    found.level, level_pixels = level_lines(level_ink, dark, space, mask)
    clean = remove_staff_lines(ink, level_pixels, space)
    found.vertical, vertical_pixels = vertical_lines(clean, dark, space, mask)
    rest = erase_verticals(clean, vertical_pixels)
    if len(rest_boxes):
        if beam_mask is not None:
            rest &= ~beam_mask
    elif mask is not None:
        rest &= ~mask
    if len(flag_boxes):
        rest &= ~box_mask(ink.shape, flag_boxes)
    on = []
    for b in join_beams(beams(rest, space), space):
        stemmed = on_stems(b, vertical_pixels, space, clean)
        if stemmed:
            on.append(stemmed)
        elif b[1] - b[0] >= 1.5 * space and (b[3] - b[2] + b[5] - b[4]) / 2 >= 0.4 * space and _solid(b, clean):
            on.append(b)     # a beam of a two-note tremolo floats between the notes
    found.beams = [refine_beam(b, dark) for b in one_each(on, space)]
    left = erase_beams(rest, found.beams)
    if len(rest_boxes):
        left &= ~mask
    left = erase_level(left, level_pixels, space)
    left = bridge_crossings(left, ink, level_pixels, space)
    found.thin, found.curves = traces(left, space)
    # pale pixels at the edge of other ink (a staff line, a stem) are not a curve's end
    other = cv2.dilate((ink & ~left).view(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    pale = ((grey < CURVE_END_INK) & ~ink & ~other) | left
    found.curves = [extend_curve(c, pale, space) for c in join_curves(found.curves, space)]
    found.thin = [t for t in found.thin if not _on_staff_line(t, found.level, space)]
    found.thin = meet_arms(found.thin, space)
    found.level = [l for l in found.level if not _along_thin(l, found.thin, space)]
    found.dashed = dashed_lines(clean & ~mask if mask is not None else clean, space)
    found.level = [l for l in found.level if not _in_dashed(l, found.dashed, space)]
    return found
