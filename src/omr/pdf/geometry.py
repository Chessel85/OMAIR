"""Geometry of what PyMuPDF draws on a page: the turn from stored to shown
coordinates, the points of a drawing item, and the box round points."""


def display_turn(page):
    """The matrix that turns the page's stored coordinates into the way it is
    shown, or None if it is not rotated. A landscape score is often stored as
    a portrait page with a rotation, so its staff lines are vertical as stored."""
    return page.rotation_matrix if page.rotation % 360 else None


def bbox(points):
    """(x0, y0, x1, y1) round the points."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def item_points(item):
    """The points of a drawing item from page.get_drawings(): a line's or
    curve's points, a rectangle's corners, a quad's four corners."""
    kind = item[0]
    if kind == "re":
        r = item[1]
        return [(r.x0, r.y0), (r.x1, r.y1)]
    if kind == "qu":
        q = item[1]
        return [(p.x, p.y) for p in (q.ul, q.ur, q.lr, q.ll)]
    return [(p.x, p.y) for p in item[1:]]
