"""CATS panel grid: cells, edges and steps, the Panel record, and column edits."""

import math
from collections import defaultdict

from .core import SchematicError


MARGIN = 2              # cells left of and above the drawing, for labels
BAND_GAP = 4            # empty rows between bands
COMPACT_GAP = 3         # the same on a compact panel (one cell per grid unit)
ENDS = {
    "HORIZONTAL": ("LEFT", "RIGHT"),
    "VERTICAL": ("TOP", "BOTTOM"),
    "UPPERSLASH": ("LEFT", "TOP"),
    "LOWERSLASH": ("RIGHT", "BOTTOM"),
    "UPPERBACKSLASH": ("RIGHT", "TOP"),
    "LOWERBACKSLASH": ("LEFT", "BOTTOM"),
}
OPPOSITE = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "BOTTOM", "BOTTOM": "TOP"}
STEP = {"LEFT": (-1, 0), "RIGHT": (1, 0), "TOP": (0, -1), "BOTTOM": (0, 1)}
EDGE_ORDER = ("LEFT", "RIGHT", "TOP", "BOTTOM")


def neighbour(cell, edge):
    """The cell across `edge` of `cell`, and the same edge seen from there."""
    dx, dy = STEP[edge]
    return (cell[0] + dx, cell[1] + dy), OPPOSITE[edge]


def step_pieces(a, b):
    """The (cell, track) pieces of one unit step between CATS points a and b (either order). A jog step (one cell
    wide, two rows deep: a 45 degree step across a row opened for a double crossover, opened_rows) has a VERTICAL
    piece in the opened row between its two halves."""
    (x0, y0), (x1, y1) = sorted((a, b))
    d = y1 - y0
    if x1 - x0 != 1 or abs(d) > 2:
        raise SchematicError(f"step {a} to {b} is not one cell wide at 45 degrees or level")
    if d == 0:
        return [((x0, y0), "HORIZONTAL")]
    if d == -1:
        return [((x0, y0), "UPPERSLASH"), ((x0, y0 - 1), "LOWERSLASH")]
    if d == 1:
        return [((x0, y0), "LOWERBACKSLASH"), ((x0, y0 + 1), "UPPERBACKSLASH")]
    if d == -2:
        return [((x0, y0), "UPPERSLASH"), ((x0, y0 - 1), "VERTICAL"), ((x0, y0 - 2), "LOWERSLASH")]
    return [((x0, y0), "LOWERBACKSLASH"), ((x0, y0 + 1), "VERTICAL"), ((x0, y0 + 2), "UPPERBACKSLASH")]


def unit_steps(pts, opened=frozenset()):
    """[(from, to)] unit steps along a polyline of CATS points. `opened`: cell rows opened between two drawn rows
    (opened_rows); a slope one row steeper than 45 degrees for each opened row it crosses takes a jog step there."""
    out = []
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        dx, dy = xb - xa, yb - ya
        if dx == 0 and dy == 0:
            continue
        sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        jogs = abs(dy) - abs(dx) if dy else 0
        crossed = sum(1 for r in opened if min(ya, yb) < r < max(ya, yb))
        if dx == 0 or (dy and jogs != 0 and not (0 < jogs <= crossed)):
            raise SchematicError(f"segment {(xa, ya)} to {(xb, yb)} is neither level nor at 45 degrees")
        if not dy:
            out += [((xa + i * sx, ya), (xa + (i + 1) * sx, ya)) for i in range(abs(dx))]
            continue
        x, y = xa, ya
        while x != xb:
            jog = jogs > 0 and (y + sy) in opened
            ny = y + (2 if jog else 1) * sy
            jogs -= jog
            out.append(((x, y), (x + sx, ny)))
            x, y = x + sx, ny
        if (x, y) != (xb, yb):
            raise SchematicError(f"segment {(xa, ya)} to {(xb, yb)}: its jogs do not fall on the opened rows")
    return out


def strand_pieces(steps):
    """[(cell, track, start, end)] of a strand's unit steps, in order along it; start and end are measured in steps
    (a 45 degree step is two pieces of half a step each)."""
    out = []
    for i, (a, b) in enumerate(steps):
        ps = step_pieces(a, b)
        if a[0] > b[0]:
            ps = ps[::-1]
        for h, (cell, track) in enumerate(ps):
            out.append((cell, track, i + h / len(ps), i + (h + 1) / len(ps)))
    return out


def parallel_runs(named):
    """Groups of named level runs [(xa, xb, y, ...)] that are a yard's parallel tracks: on rows at most two apart,
    each overlapping the next by at least half of both runs; the rest alone. In order of row."""
    out = []
    for r in sorted(named, key=lambda r: (r[2], r[0])):
        for g in out:
            q = g[-1]
            lo, hi = max(q[0], r[0]), min(q[1], r[1])
            if 0 < r[2] - q[2] <= 2 and hi - lo >= max(q[1] - q[0], r[1] - r[0]) / 2:
                g.append(r)
                break
        else:
            out.append([r])
    return out


def stacked_runs(named):
    """Groups of named level runs [(xa, xb, y, ...)] on any rows that share at least half of the shorter run's
    columns, each with the first group it fits all of; the rest alone. In order of row."""
    out = []
    for r in sorted(named, key=lambda r: (r[2], r[0])):
        for g in out:
            if all(min(q[1], r[1]) - max(q[0], r[0]) >= min(q[1] - q[0], r[1] - r[0]) / 2 for q in g):
                g.append(r)
                break
        else:
            out.append([r])
    return out


def free_ends(band, sid):
    """(start, end): whether level track may be added at each end of a strand without meeting another track there:
    a track end, or a switch's A leg (alone on its side of the points)."""
    nodes = band["nodes"]
    ok = lambda end: nodes[end[0]]["kind"] == "end" or (nodes[end[0]]["kind"] == "switch" and end[1] == "A")
    s = band["strands"][sid]
    return ok(s["src"]), ok(s["dst"])


def stretched(pts, free=(False, False)):
    """The polyline (CATS points) with each slope made wider than it is deep by a widened column given level track
    for the difference: at the bend where it leaves or meets a level run, else in its middle, else at a `free` end
    of the strand (free_ends). None when there is no such place (a one-row slope from switch points to switch
    points)."""
    q = [pts[0]] + [b for a, b in zip(pts, pts[1:]) if b != a]
    segs = list(zip(q, q[1:]))
    level = lambda i: 0 <= i < len(segs) and segs[i][0][1] == segs[i][1][1]
    out = [q[0]]
    for i, (a, b) in enumerate(segs):
        w, dy = b[0] - a[0], b[1] - a[1]
        f = abs(w) - abs(dy)
        if dy == 0 or f <= 0:            # level, or 45 degrees already (steeper is unit_steps' error)
            out.append(b)
            continue
        sx, sy = (1 if w > 0 else -1), (1 if dy > 0 else -1)
        if level(i - 1):
            out += [(a[0] + sx * f, a[1]), b]
        elif level(i + 1):
            out += [(b[0] - sx * f, b[1]), b]
        elif abs(dy) >= 2:
            k = abs(dy) // 2
            m = (a[0] + sx * k, a[1] + sy * k)
            out += [m, (m[0] + sx * f, m[1]), b]
        elif i == 0 and free[0]:
            out += [(a[0] + sx * f, a[1]), b]
        elif i == len(segs) - 1 and free[1]:
            out += [(b[0] - sx * f, b[1]), b]
        else:
            return None
    return out


def column_shift(widen):
    """The extra cells left of grid x, given {grid column: extra cells}."""
    return lambda gx: sum(w for c, w in widen.items() if c + 1 <= gx)


def widened_columns(title, band, drawn, reach, log):
    """{grid column: extra cells} for a compact panel: a level track between two switches gets the cells it needs
    for their OS blocks to part (each reaching its `reach` cells), added to its first grid column. A column is left
    alone (logged) when a slope across it has no level track to give the extra cells to. The check stretches the
    same points panel() draws, less its constant offset (stretched depends only on differences)."""
    nodes, strands = band["nodes"], band["strands"]
    sw = lambda n: nodes[n]["kind"] in ("switch", "dx")
    widen = {}
    for sid, s in sorted(strands.items()):
        u, v = s["src"][0], s["dst"][0]
        line = drawn.get(sid) or []
        if not line or not (sw(u) and sw(v)) or len({p[1] for p in line}) != 1:
            continue
        short = reach.get(u, 0) + reach.get(v, 0) - int(round(abs(line[-1][0] - line[0][0])))
        if short > 0:
            c = math.floor(min(p[0] for p in line))
            widen[c] = max(widen.get(c, 0), short)
    while widen:
        extra = column_shift(widen)
        bad = set()
        for sid, line in sorted(drawn.items()):
            if sid in strands and line and \
                    stretched([(p[0] + extra(p[0]), p[1]) for p in line], free_ends(band, sid)) is None:
                lo, hi = min(p[0] for p in line), max(p[0] for p in line)
                bad |= {c for c in widen if lo <= c < hi}
        if not bad:
            break
        for c in sorted(bad):
            log.append(f"{title}: grid column {c:g} is not widened (a one-row slope from switch to switch "
                       "crosses it), so the switches at the ends of its short track share one OS block")
            del widen[c]
    return widen


def touching(point, other):
    """(cell, edge) of a step's piece that ends at `point`; `other` is the step's other point."""
    return ((point[0], point[1]), "LEFT") if other[0] > point[0] else ((point[0] - 1, point[1]), "RIGHT")


class Panel:
    def __init__(self):
        self.cells = defaultdict(dict)      # cell -> {track: block key}
        self.blocks = {}                    # block key -> name
        self.points = {}                    # (cell, edge) -> {"switch": label, "routes": [(edge, normal)]}
        self.crossings = set()              # (cell, edge)
        self.shared = {}                    # (cell, edge) -> (cell, edge)
        self.labels = {}                    # cell -> (text, loc, font)
        self.names = {}                     # block root -> unique block name, set when the panel is complete
        self.log = []
        self.pending = None                 # compact panels: label requests, placed at the end
        self._parent = {}
        # bindings (empty without them)
        self.block_info = {}                # block root -> {"station", "discipline", "occupied", "unoccupied"}
        self.route_io = {}                  # (cell, edge) of points -> {route edge: [(tag, IO)]}
        self.signals = {}                   # (cell, edge) -> {"name", "loc", "orient", "pantype", "template"}

    def add(self, cell, track, block, what):
        if track in self.cells[cell]:
            raise SchematicError(f"{what}: cell {cell} already holds a {track} track")
        self.cells[cell][track] = block

    # union-find over block keys
    def find(self, k):
        while self._parent.get(k, k) != k:
            k = self._parent[k]
        return k

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self._parent[max(a, b)] = min(a, b)

    def label(self, cands, text, font="FONT_LABEL", rank=9):
        """Put `text` in the first candidate (cell, loc) with no label, preferring cells with no track. On a compact
        panel (one cell per grid unit) the labels are placed together at the end instead, by place_labels, lower
        `rank` first, where nothing drawn is in their way."""
        if self.pending is not None:
            self.pending.append((rank, len(self.pending), cands, text, font))
            return None
        free = [c for c in cands if c[0] not in self.labels and c[0][0] >= 1 and c[0][1] >= 1]
        pick = next((c for c in free if c[0] not in self.cells), None) or (free[0] if free else None)
        if pick is None:
            self.log.append(f"no room for label {text!r}")
            return None
        self.labels[pick[0]] = (text, pick[1], font)
        return pick[0]

    def size(self):
        cells = list(self.cells) + list(self.labels)
        return max(c[0] for c in cells) + MARGIN, max(c[1] for c in cells) + MARGIN


def band_key_name(title):
    return title.split(",")[0].strip()


def trim_columns(P, max_cols, spots=None):
    """Take out whole columns until no track reaches past column `max_cols`, the rightmost first: a column goes
    when every cell in it is empty or a level track of the same block as the cells on both sides (so no gap,
    switch, mast, join or turnback is in it, and no block loses its last cell). It shortens level runs on the
    panel only, never the sheet, to keep a margin on the screen. An error when no such column is left."""
    while max(c[0] for c in P.cells) > max_cols:
        xs = sorted({c[0] for c in P.cells}, reverse=True)
        col = next((x for x in xs[1:] if column_plain(P, x) and
                    not any(c[0] == x for c, _ in (spots or {}).values())), None)    # nor a mast still to place
        if col is None:
            raise SchematicError(f"the panel's track reaches column {xs[0]}, past {max_cols}, and no column of plain "
                                 "level track is left to take out")
        drop_column(P, col)
        for k, (cell, edge) in (spots or {}).items():      # masts still to place follow their cells
            if cell[0] > col:
                spots[k] = ((cell[0] - 1, cell[1]), edge)
        P.log.append(f"column {col} taken out (level track in every row) to keep the track within {max_cols} columns")


def column_plain(P, x):
    """True when every cell in column x is a level track whose block goes on through both its neighbours, and no
    empty cell in it parts two track ends that would meet without it."""
    for (cx, y), tracks in P.cells.items():
        if cx != x:
            continue
        if set(tracks) != {"HORIZONTAL"}:
            return False
        b = P.find(tracks["HORIZONTAL"])
        for nx, edge in ((x - 1, "RIGHT"), (x + 1, "LEFT")):
            touch = [P.find(k) for t, k in P.cells.get((nx, y), {}).items() if edge in ENDS[t]]
            if touch != [b]:
                return False
    rows = {y for (cx, y) in P.cells if cx in (x - 1, x + 1)} - {y for (cx, y) in P.cells if cx == x}
    for y in rows:                               # an empty cell between two track ends would join them
        if any("RIGHT" in ENDS[t] for t in P.cells.get((x - 1, y), {})) and \
                any("LEFT" in ENDS[t] for t in P.cells.get((x + 1, y), {})):
            return False
    taken = [k for k in list(P.points) + list(P.crossings) + list(P.shared) + list(P.signals) if k[0][0] == x]
    return not taken and not any(c[0] == x for c in P.labels)


def drop_column(P, x):
    """Remove column x, moving everything right of it one column left (labels still to place included)."""
    mv = lambda c: (c[0] - 1, c[1]) if c[0] > x else c
    mk = lambda k: (mv(k[0]), k[1])
    P.cells = defaultdict(dict, {mv(c): t for c, t in P.cells.items() if c[0] != x})
    P.points = {mk(k): v for k, v in P.points.items()}
    P.crossings = {mk(k) for k in P.crossings}
    P.shared = {mk(k): mk(v) for k, v in P.shared.items()}
    P.signals = {mk(k): v for k, v in P.signals.items()}
    P.route_io = {mk(k): v for k, v in P.route_io.items()}
    P.labels = {mv(c): v for c, v in P.labels.items()}
    if P.pending is not None:
        out = []
        for rank, seq, cands, text, font in P.pending:
            if isinstance(text, list):
                col = lambda c: c - 1 if c > x else c
                cands = [col(c) if isinstance(c, int) else (col(c[0]), c[1]) for c in cands
                         if (c if isinstance(c, int) else c[0]) != x]
                text = [(y, t, [(mv(c), loc) for c, loc in own if c[0] != x]) for y, t, own in text]
            else:
                cands = [(mv(c), loc) for c, loc in cands if c[0] != x]
            out.append((rank, seq, cands, text, font))
        P.pending = out
