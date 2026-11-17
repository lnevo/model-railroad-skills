"""CATS screen geometry: pixel sizes of the 30 pixel grid, and boxes and lines in it."""

import math

from .cats_grid import ENDS

__all__ = [
    "GRID_PX", "TEXT_PX", "SIG_PX", "LOC_XY", "frill_box", "text_box", "track_lines", "signal_boxes",
    "crosses", "overlaps"
]


# CATS lays out labels at its default 30 pixel grid; text widths are estimates of the CATS fonts (11 point
# labels, 13 point bold titles).
GRID_PX = 30
TEXT_PX = {"FONT_LABEL": (8, 14), "FONT_TITLE": (10, 17)}     # pixels per character, line height
SIG_PX = 8                                                        # CATS SignalFrill radius
LOC_XY = {"LEFTUP": ("L", "OU"), "LEFTCENT": ("L", "C"), "LEFTLOW": ("L", "OL"), "LOWLEFT": ("OL", "LO"),
          "LOWCENT": ("C", "LO"), "LOWRIGHT": ("OR", "LO"), "RIGHTLOW": ("R", "OL"), "RIGHTCENT": ("R", "C"),
          "RIGHTUP": ("R", "OU"), "UPRIGHT": ("OR", "UP"), "UPCENT": ("C", "UP"), "UPLEFT": ("OL", "UP"),
          "CENT": ("C", "C")}


def frill_box(cell, loc, w, h):
    """(x0, y0, x1, y1) in pixels of a w x h item at `loc` in `cell`, as CATS's FrillLoc places it."""
    g, X, Y = GRID_PX, cell[0] * GRID_PX, cell[1] * GRID_PX
    hx, vy = LOC_XY[loc]
    x = {"L": X + 1, "OL": X + g // 4, "C": X + (g - w) // 2, "OR": X + 3 * g // 4 - w, "R": X + g - w - 1}[hx]
    y = {"UP": Y + 1, "OU": Y + g // 4, "C": Y + (g - h) // 2 - 1, "OL": Y + 3 * g // 4 - h, "LO": Y + g - h - 1}[vy]
    return x, y, x + w, y + h


def text_box(cell, loc, text, font):
    per, h = TEXT_PX.get(font, TEXT_PX["FONT_LABEL"])
    return frill_box(cell, loc, int(math.ceil(per * len(text))) + 4, h)


def track_lines(P, cells=None):
    """Every drawn track (of `cells`, else the panel's) as a pixel line segment."""
    h = GRID_PX // 2
    mid = {"LEFT": (0, h), "RIGHT": (GRID_PX, h), "TOP": (h, 0), "BOTTOM": (h, GRID_PX)}
    out = []
    for (x, y), tracks in (P.cells if cells is None else cells).items():
        for t in tracks:
            (ax, ay), (bx, by) = (mid[e] for e in ENDS[t])
            out.append((x * GRID_PX + ax, y * GRID_PX + ay, x * GRID_PX + bx, y * GRID_PX + by))
    return out


def signal_boxes(P):
    out = []
    for (cell, _), sg in P.signals.items():
        heads = int(sg["pantype"][-1])
        long_ = heads * SIG_PX + SIG_PX
        w, h = (long_, SIG_PX) if sg["orient"] in ("LEFT", "RIGHT") else (SIG_PX, long_)
        out.append(frill_box(cell, sg["loc"], w, h))
    return out


def crosses(box, line, rim=2):
    """True when the line segment passes through the inside of the box (its ink: the box less a `rim`)."""
    x0, y0, x1, y1 = box[0] + rim, box[1] + rim, box[2] - rim, box[3] - rim
    ax, ay, bx, by = line
    for i in range(33):
        f = i / 32
        px, py = ax + (bx - ax) * f, ay + (by - ay) * f
        if x0 < px < x1 and y0 < py < y1:
            return True
    return False


def overlaps(a, b, pad=2):
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] and b[1] < a[3]
