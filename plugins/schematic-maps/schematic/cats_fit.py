"""How much of the screen a CATS panel takes, and the --fit and --window sizes."""

import math

from .cats_px import GRID_PX, text_box
from .core import SchematicError


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
