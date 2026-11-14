"""Label placer: no label sits on a line, a symbol or another label (rule R12, draw-time part).

Each label is asked for with an ordered list of allowed positions. Obstacles are registered first (every
drawn line, every symbol, the helix marks, the station brackets); labels are then placed hardest first
(fewest free positions), each taking its first free position. A label with no free position takes the
least bad one and is reported, and the strands named in its `room` are recorded in `short`: the sheet gives them
another cell and lays the band out again (sheet.build), which is the layout part of R12.

The count of free positions is kept up to date as obstacles are added: placing a label only re-tests the
positions of the labels whose candidate boxes it can touch, so a large sheet solves in a moment.

Positions are SVG text anchors: (x, baseline y, text-anchor).
"""
import math

from .label_check import BELOW, CAP, _pt_seg, boxes_overlap, seg_box_gap, text_width

PAD = 1.2


def text_box(x, y, anchor, s, size, weight, spacing=0.0):
    w = text_width(s, size, weight, spacing)
    x0 = x - (w / 2 if anchor == "middle" else w if anchor == "end" else 0)
    return (x0, y - CAP * size, x0 + w, y + BELOW * size)


class Placer:
    def __init__(self):
        self.lines = []       # (a, b, width)
        self.boxes = []       # symbols and placed labels
        self.asks = []
        self.unplaced = []
        self.short = set()    # strands whose labels found no free position: they claim more grid room

    def line(self, a, b, w):
        self.lines.append((a, b, w))

    def box(self, b):
        self.boxes.append(b)

    def clear(self, box, pad=PAD):
        if any(seg_box_gap(a, b, box) < w / 2 + pad for a, b, w in self.lines):
            return False
        return not any(boxes_overlap(box, o, pad) for o in self.boxes)

    def cost(self, box):
        c = sum(1 for a, b, w in self.lines if seg_box_gap(a, b, box) < w / 2 + PAD)
        return c + sum(1 for o in self.boxes if boxes_overlap(box, o, PAD))

    def ask(self, what, s, size, cands, weight="normal", extra="", spacing=0.0, emit=None, room=()):
        """cands: [(x, y, anchor)] in order of preference. `room`: the strands that get longer when the label
        finds no free position (R12, layout part)."""
        self.asks.append(dict(what=what, s=s, size=size, cands=cands, weight=weight, extra=extra,
                              spacing=spacing, emit=emit, room=tuple(room)))

    def solve(self):
        """Place every label asked for; returns [(ask, (x, y, anchor))].

        Free positions are counted once, then only updated for the labels a newly placed box can touch."""
        todo = []
        for a in self.asks:
            bs = [text_box(x, y, an, a["s"], a["size"], a["weight"], a["spacing"]) for x, y, an in a["cands"]]
            ok = [self.clear(b) for b in bs]
            todo.append([a, bs, ok])
        out = []
        while todo:
            i = min(range(len(todo)), key=lambda j: (sum(todo[j][2]), j))
            a, bs, ok = todo.pop(i)
            k = next((j for j, f in enumerate(ok) if f), None)
            if k is None:
                k = min(range(len(bs)), key=lambda j: (self.cost(bs[j]), j))
                self.unplaced.append(f"{a['what']} {a['s']}")
                self.short.update(a["room"])
            placed = bs[k]
            self.boxes.append(placed)
            out.append((a, a["cands"][k]))
            for t in todo:                  # only a position this box overlaps can have stopped being free
                for j, b in enumerate(t[1]):
                    if t[2][j] and boxes_overlap(b, placed, PAD):
                        t[2][j] = False
        return out


def dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def seg_point(a, b, p):
    return _pt_seg(p, a, b)
