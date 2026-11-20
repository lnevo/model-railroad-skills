"""How much of the screen a CATS panel takes, and the --fit and --window sizes."""

import math

from .cats_grid import ENDS, band_of, band_spans
from .cats_px import GRID_PX, text_box
from .cats_xml import edge_meetings
from .core import SchematicError

__all__ = [
    "shown", "check_fit", "faults", "parse_size", "parse_fit", "parse_window", "summary"
]


def shown(P):
    """(columns, rows) of cells CATS lays out on screen: every column from 1 to the rightmost one with track or a
    label (column 0 is never used), and the rows from the top to the bottom one with track or a label
    (cats/gui/Screen.java findBounds); plus any columns a label's text runs into past the last one, since CATS
    cuts text off there and a fit must leave room for it."""
    cells = list(P.cells) + list(P.labels)
    reach = [math.ceil(text_box(c, loc, t, f)[2] / GRID_PX) - 1 for c, (t, loc, f) in P.labels.items()]
    return max([c[0] for c in cells] + reach), max(c[1] for c in cells) - min(c[1] for c in cells) + 1


def check_fit(P, cols, rows):
    """An error when the panel shows more than cols x rows cells (the screen at CATS's fixed grid size)."""
    have = shown(P)
    if have[0] > cols or have[1] > rows:
        raise SchematicError(f"the panel shows {have[0]} x {have[1]} cells, more than the {cols} x {rows} it must "
                             f"fit ({max(0, have[0] - cols)} columns and {max(0, have[1] - rows)} rows over)")
    return have


def faults(P, fit=None):
    """The desk faults of a finished panel P, one line each, [] when there are none:
      - two blocks landing in one cell: a block boundary CATS cannot hold, on a switch's points, on a crossing, or
        where two blocks in one cell reach the same edge (cats_xml.edge_meetings), so CATS would drop the points;
        named by the blocks and the switch, and the band the cell is drawn on (its own block keys, P.titles); a
        boundary met from both its cells is one fault;
      - with `fit` (cols, rows), a desk wider or taller than its window shows (shown), naming each band's columns
        (band_spans).
    The causes are the drawing's (two tracks too close at one cell per grid unit, a band too wide for the window),
    so the faults name them and leave the panel as it is. Stops when P is not finished (its blocks not yet named)
    or `fit` is not two whole numbers of at least 1."""
    if fit is not None:
        if not (isinstance(fit, (tuple, list)) and len(fit) == 2 and
                all(isinstance(v, int) and not isinstance(v, bool) and v >= 1 for v in fit)):
            raise SchematicError(f"fit must be (columns, rows), both whole numbers of at least 1, not {fit!r}")
    out, seen = [], set()
    for cell, edge, far, mine, theirs, bad in edge_meetings(P):
        if not bad:
            continue
        once = frozenset({(cell, edge), far})       # a boundary is met from both its cells: one fault
        if once in seen:
            continue
        seen.add(once)
        unnamed = sorted(str(b) for b in mine | theirs if b not in P.names)
        if unnamed:
            raise SchematicError(f"the panel's blocks are not named yet ({', '.join(unnamed)}): faults reads a "
                                 "finished panel")
        blocks = ", ".join(sorted({P.names[b] for b in mine | theirs}))
        point = P.points.get((cell, edge))
        # the band of what is drawn in this cell at that edge (its own block keys: a union root may be another
        # band's, a helix block drawn on two)
        raw = [k for t, k in P.cells[cell].items() if edge in ENDS[t]]
        bands = [P.titles[bi] for bi in sorted({band_of(P, k) for k in raw})]
        at = (f"on switch {point['switch']}'s points" if point else
              "on a crossing" if (cell, edge) in P.crossings else "where both reach one edge")
        out.append(f"{'; '.join(bands)}: blocks {blocks} land in one cell, {cell} edge {edge}, {at}; CATS would "
                   "drop the points")
    if fit is not None:
        cols, rows = shown(P)
        if cols > fit[0] or rows > fit[1]:
            out.append(f"the desk shows {cols} x {rows} cells, more than the {fit[0]} x {fit[1]} its window fits "
                       f"({max(0, cols - fit[0])} columns and {max(0, rows - fit[1])} rows over): {band_spans(P)}")
    return out


def parse_size(text, option="--fit", form="COLSxROWS", example="63x36"):
    """'AxB' as (a, b), both whole numbers of at least 1; an error naming the option otherwise."""
    try:
        a, b = (int(v) for v in text.lower().split("x"))
    except ValueError:
        raise SchematicError(f"{option} is {form}, such as {example}, not {text!r}") from None
    if a < 1 or b < 1:
        raise SchematicError(f"{option} is {form} with both at least 1, not {text!r}")
    return a, b


def parse_fit(text):
    """'COLSxROWS' as (cols, rows)."""
    return parse_size(text)


def parse_window(text):
    """'WIDTHxHEIGHT' in pixels as (width, height)."""
    return parse_size(text, "--window", "WIDTHxHEIGHT in pixels", "1900x1100")


def summary(P):
    blocks = len(set(P.names.values()))
    text = (f"{len(P.cells)} track cells, {len(P.points)} switch points, {len(P.crossings) // 2} crossings, "
            f"{blocks} blocks, {len(P.shared) // 2} logical joins, {len(P.labels)} labels")
    if P.block_info or P.route_io or P.signals:
        occupied = sum(1 for b in P.block_info.values() if b.get("occupied"))
        text += (f"; bound: {occupied} block sensors, {len(P.route_io)} switch points, {len(P.signals)} masts")
    return text
