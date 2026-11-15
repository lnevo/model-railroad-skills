"""A CATS Designer panel (XML) seeded from the solved bands: the same track on CATS's grid of cells.

    panel = cats.panel(sheet.bands)        # a Panel: cells, blocks, switches, joins, labels
    cats.write(panel, "OUT.xml")

Grid. A schematic grid point (column c, row r) becomes the CATS point (SCALE * c, SCALE * r) plus a margin; a
CATS point (X, Y) is the middle of the LEFT edge of cell (X, Y). One step from (X, Y) to (X + 1, Y + d) is
d = 0: cell (X, Y) HORIZONTAL; d = -1: cell (X, Y) UPPERSLASH and (X, Y - 1) LOWERSLASH; d = +1: cell (X, Y)
LOWERBACKSLASH and (X, Y + 1) UPPERBACKSLASH. So every 45 degree leg lands on whole cells, a switch's legs meet on
one cell edge (its points), and SCALE = 2 leaves a free row under every track for its name. A double crossover is
drawn as its X with a crossing edge in the middle; a turnback is a vertical run in one column.

Compact: `panel(bands, scale=1)` (the command's --cells-per-unit 1) is one cell per grid unit, to fit a screen at
CATS's fixed 30 pixel grid. There is no free row, so labels share cells with track and are placed together at the
end (place_labels) where they cover no track line, signal or label; OS blocks reach one cell (half a 45 degree
step) past the points; a one-unit level track between two switches gets a second cell in its grid column
(widened_columns), so their OS blocks still part; a double crossover between adjacent rows is one column wide with
its crossing on the edge between the rows. shown(P) is the cells CATS lays out on screen; check_fit tests it.

Blocks: one per strand (its track name, or the two switch numbers it joins), one OS block per switch (shared by
switches of the same number joined by a track), reaching one step past the points on every leg, so no block
boundary falls on a points or crossing edge. Each switch's points carry two ROUTEINFO, normal being leg B (the
straight leg as the band records it). No IOSPEC is written: binding sensors and turnouts is left to the Designer
or a later pass. Link ends with the same letter, and helix ends of the same track, on two drawn bands are joined
logically (SHARED); other ends get a label saying where they go. A turnback joining two tracks of different names
is two blocks, parted in the middle of its vertical run.

Bindings (optional, `panel(bands, bindings=...)`, the command's --bindings FILE.json) tie the panel to the
layout's devices; every name in them must exist in the panel, or it is an error:

    {"switches": {"LABEL" or "LABEL/ALIAS": {"block": "OS name", "normal": "B" or "C",
                                              "routes": {"B": {"ROUTECOMMAND": IO, "SELECTEDREPORT": IO}, "C": {..}}}},
     "blocks":   {"BLOCK": {"name": "layout name", "station": "..", "discipline": "CTC", "occupied": IO, "unoccupied": IO}},
     "masts":    {"MAST": {"name": "mast user name", "template": "physical signal template", "pantype": "LAMP2"}}}

IO is one CATS IOSPEC: {"DECADDR": .., "JMRIPREFIX": .., "USER_NAME": .., "command": "close" or "throw"} (also
JMRIDEVICE, EXIT_CMD, DELAY). A switch key is its label (every switch of that number) or label/alias (one of them; a key that
is not a whole label splits at its last /, and labels and aliases compare as text);
switches of one number given different `block`s keep apart. BLOCK is the panel's block name after the switches'
`block`s; two blocks given one `name` become one block. MAST is a mast of a band's `signals`
(field or planned; virtual masts are not drawn). It goes on the block boundary nearest where it stands on its run:
on the edge of the block it protects (the side toward the switch or end its move is heading for), facing out of
that block, on the right-hand side of the move.
"""
import copy
import math
import xml.etree.ElementTree as ET
from collections import defaultdict

from .core import SchematicError, dx_tracks
from .draw import mast_piece
from .layout import paths

SCALE = 2
OS_REACH = 1            # steps an OS block reaches past a switch's points on each leg
DISCIPLINES = ("CTC", "ABS", "APB-2", "APB-3", "DTC", "Unknown")    # the values CATS reads (cats/layout/Discipline.java)
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
# a signal on a boundary edge: where it sits in its cell, on the right-hand side of a move entering by that edge
SIG_LOCATION = {"RIGHT": "UPRIGHT", "LEFT": "LOWLEFT", "TOP": "LEFTUP", "BOTTOM": "RIGHTLOW"}
SIG_PANTYPES = ("LAMP1", "LAMP2", "LAMP3", "SEM1", "SEM2", "SEM3")
IOSPEC_KEYS = {"DECADDR", "JMRIPREFIX", "USER_NAME", "JMRIDEVICE", "EXIT_CMD", "DELAY"}
ROUTE_TAGS = ("SELECTEDREPORT", "NOTSELECTEDREPORT", "ROUTECOMMAND")


def neighbour(cell, edge):
    """The cell across `edge` of `cell`, and the same edge seen from there."""
    dx, dy = STEP[edge]
    return (cell[0] + dx, cell[1] + dy), OPPOSITE[edge]


def step_pieces(a, b):
    """The (cell, track) pieces of one unit step between CATS points a and b (either order)."""
    (x0, y0), (x1, y1) = sorted((a, b))
    d = y1 - y0
    if x1 - x0 != 1 or abs(d) > 1:
        raise SchematicError(f"step {a} to {b} is not one cell wide at 45 degrees or level")
    if d == 0:
        return [((x0, y0), "HORIZONTAL")]
    if d == -1:
        return [((x0, y0), "UPPERSLASH"), ((x0, y0 - 1), "LOWERSLASH")]
    return [((x0, y0), "LOWERBACKSLASH"), ((x0, y0 + 1), "UPPERBACKSLASH")]


def unit_steps(pts):
    """[(from, to)] unit steps along a polyline of CATS points."""
    out = []
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        dx, dy = xb - xa, yb - ya
        if dx == 0 and dy == 0:
            continue
        if dx == 0 or (dy and abs(dx) != abs(dy)):
            raise SchematicError(f"segment {(xa, ya)} to {(xb, yb)} is neither level nor at 45 degrees")
        n, sx, sy = abs(dx), (1 if dx > 0 else -1), (dy // abs(dx) if dy else 0)
        out += [((xa + i * sx, ya + i * sy), (xa + (i + 1) * sx, ya + (i + 1) * sy)) for i in range(n)]
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


def widened_columns(title, band, drawn, reach, log):
    """{grid column: extra cells} for a compact panel: a level track between two switches gets the cells it needs
    for their OS blocks to part (each reaching its `reach` cells), added to its first grid column. A column is left
    alone (logged) when a slope across it has no level track to give the extra cells to."""
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
        extra = lambda gx: sum(w for c, w in widen.items() if c + 1 <= gx)
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


def node_ref(d):
    if d["kind"] in ("switch", "dx") and d.get("label"):
        return d["label"]
    if d.get("sub") == "link" and d.get("label"):
        return "link " + d["label"]
    if d.get("sub") == "helix":
        return "helix"
    return "end"


def panel(bands, scale=SCALE, bindings=None):
    """A Panel from [(title, band, options)], bands stacked top to bottom, bound to the layout by `bindings`."""
    if not isinstance(scale, int) or scale < 1:
        raise SchematicError(f"the CATS scale is a whole number of cells per grid unit (1 or more), not {scale!r}")
    compact = scale == 1
    bindings = check_bindings(bindings or {})
    sw_bind = switch_bindings(bands, bindings["switches"])
    P = Panel()
    if compact:
        P.pending = []
    chains, turn_bounds = {}, {}     # (band, strand) -> its steps and their blocks; (band, turnback) -> its boundary
    top = 1 if compact else MARGIN + 1
    left_col = 1 if compact else MARGIN + 1
    ends = []                  # (band title, node, data, strand name, (cell, edge), block key of the end step)
    used_names = defaultdict(int)

    def unique(name):
        used_names[name] += 1
        return name if used_names[name] == 1 else f"{name} {used_names[name]}"

    for bi, (title, band, opts) in enumerate(bands):
        nodes, strands, x = band["nodes"], band["strands"], band["x"]
        drawn = paths(band)
        if not any(drawn.values()):
            raise SchematicError(f"{title}: the band draws no track")
        x0 = min(p[0] for v in drawn.values() for p in v)
        r0 = min(p[1] for v in drawn.values() for p in v)
        ox = left_col - math.floor(scale * x0)
        oy = top + 2 - math.floor(scale * r0)
        tag = f"b{bi}:"

        # the band title and which way is east
        left, right = opts.get("left", "West"), opts.get("right", "East")
        tx = 1 if compact else MARGIN
        P.label([((tx, top), "LOWLEFT"), ((tx, top - 1), "LOWLEFT")],
                f"{band_key_name(title).upper()}   {left.upper()} <-   -> {right.upper()}", "FONT_TITLE", rank=0)

        # OS blocks: a switch's own, or shared by switches of one number joined by a track
        def os_key(n):
            return ("os", tag + n)
        for n, d in nodes.items():
            if d["kind"] in ("switch", "dx"):
                P.blocks[os_key(n)] = None
        for sid, s in strands.items():
            u, v = s["src"][0], s["dst"][0]
            du, dv = nodes[u], nodes[v]
            if du["kind"] in ("switch", "dx") and dv["kind"] in ("switch", "dx") and du.get("label") and \
                    du.get("label") == dv.get("label"):
                bu, bv = (sw_bind.get((bi, n), {}).get("block") for n in (u, v))
                if not (bu and bv and bu != bv):        # bound to two blocks: they stay apart
                    P.union(os_key(u), os_key(v))

        # how far each switch's OS reaches along its tracks: in steps, or on a compact panel in cells (half a
        # 45 degree step), so that a one-unit slope between two switches can still part their OS blocks
        reach = {}
        for n, d in nodes.items():
            if d["kind"] == "switch":
                reach[n] = OS_REACH
            elif d["kind"] == "dx":
                (iu, _), (il, _) = dx_tracks(nodes, n)
                r1, r2 = sorted((band["R"]["srow"][iu], band["R"]["srow"][il]))
                reach[n] = (int(round(scale * (r2 - r1))) + 1) // 2 + OS_REACH     # the X, then past its points

        # a compact panel widens the grid columns of level tracks too short to part the OS blocks at their ends
        widen = widened_columns(title, band, drawn, reach, P.log) if compact else {}
        extra = lambda gx: sum(w for c, w in widen.items() if c + 1 <= gx)
        pt = lambda p: (ox + int(round(scale * p[0])) + extra(p[0]), oy + int(round(scale * p[1])))

        # strands
        turn_of, info = {}, {}
        for sid, s in strands.items():
            for t in (s["src"][0], s["dst"][0]):
                if nodes[t]["kind"].startswith("turn"):
                    turn_of.setdefault(t, []).append(sid)
        for sid, s in sorted(strands.items()):
            pts = stretched([pt(p) for p in drawn[sid]], free_ends(band, sid)) if widen else \
                [pt(p) for p in drawn[sid]]
            steps = unit_steps(pts)
            if not steps:
                raise SchematicError(f"{title}: track {s['name'] or sid} is drawn as a single point")
            pieces = strand_pieces(steps)
            u, v = s["src"][0], s["dst"][0]
            track_key = ("track", tag + sid)
            P.blocks.setdefault(track_key, None)
            owner = [track_key] * len(pieces)
            if compact:                         # a compact panel's reach is in cells, else in steps
                ru, rv = reach.get(u, 0), reach.get(v, 0)
            else:
                ru = sum(1 for pc in pieces if pc[3] <= reach.get(u, 0))
                rv = sum(1 for pc in pieces if len(steps) - pc[2] <= reach.get(v, 0))
            for i in range(min(ru, len(pieces))):
                owner[i] = os_key(u)
            for i in range(min(rv, len(pieces))):
                j = len(pieces) - 1 - i
                if owner[j] != track_key and owner[j] != os_key(v):
                    P.union(owner[j], os_key(v))
                owner[j] = os_key(v)
            if track_key not in owner:
                del P.blocks[track_key]
            for (cell, track, _, _), key in zip(pieces, owner):
                P.add(cell, track, key, f"track {s['name'] or sid}")
            if track_key in P.blocks:
                P.blocks[track_key] = s["name"] or f"{node_ref(nodes[u])}-{node_ref(nodes[v])}"
            for n, end_pt, nxt, key in ((u, pts[0], steps[0][1], owner[0]), (v, pts[-1], steps[-1][0], owner[-1])):
                d = nodes[n]
                if d["kind"] == "end":
                    ends.append((title, n, d, s["name"], touching(end_pt, nxt), key))
            info[sid] = dict(steps=steps, pieces=pieces, owner=owner, pts=pts)
            chains[(bi, sid)] = info[sid]

        # turnbacks: a vertical run in one column, part of the tracks they join
        for t, sids in sorted(turn_of.items()):
            line = drawn[t]
            (xa, ya), (xb, yb) = pt(line[0]), pt(line[-1])
            y1, y2 = sorted((ya, yb))
            col = xa if nodes[t]["kind"] == "turnR" else xa - 1
            keys = [info[k]["owner"][-1 if strands[k]["dst"][0] == t else 0] for k in sids]
            # the strand whose end is at the top of the run, first
            top_first = sorted(range(len(sids)), key=lambda i: info[sids[i]]["pts"][-1 if strands[sids[i]]["dst"][0] == t
                                                                                    else 0][1])
            names = {strands[k]["name"] for k in sids}
            split = len(sids) == 2 and "" not in names and None not in names and len(names) == 2 and y2 > y1
            mid = (y1 + y2) // 2
            if split:           # two named tracks: a boundary in the middle of the run
                hi, lo = keys[top_first[0]], keys[top_first[1]]
                turn_bounds[(bi, t)] = {sids[top_first[0]]: (((col, mid), "BOTTOM"), hi, lo),
                                        sids[top_first[1]]: (((col, mid + 1), "TOP"), lo, hi)}
            else:
                for k in keys[1:]:
                    P.union(keys[0], k)
                hi = lo = keys[0]
            first, last = ("LOWERBACKSLASH", "UPPERSLASH") if nodes[t]["kind"] == "turnR" else \
                ("LOWERSLASH", "UPPERBACKSLASH")
            P.add((col, y1), first, hi, "turnback")
            for y in range(y1 + 1, y2):
                P.add((col, y), "VERTICAL", hi if y <= mid else lo, "turnback")
            P.add((col, y2), last, lo, "turnback")

        # double crossovers: the X between the two through tracks
        for n, d in sorted(nodes.items()):
            if d["kind"] != "dx":
                continue
            (iu, _), (il, _) = dx_tracks(nodes, n)
            r1, r2 = sorted((band["R"]["srow"][iu], band["R"]["srow"][il]))
            xc, (y1, y2) = pt((x[n], 0))[0], (pt((0, r1))[1], pt((0, r2))[1])
            depth = y2 - y1
            a, b = xc - (depth + 1) // 2, xc - (depth + 1) // 2 + depth     # the X runs from point a to point b
            # its points need one level step beyond the X on each through track
            for yy in (y1, y2):
                for xx in range(a - OS_REACH, b + OS_REACH):
                    here = P.cells.get((xx, yy), {}).get("HORIZONTAL")
                    if here is None or P.find(here) != P.find(os_key(n)):
                        raise SchematicError(
                            f"double crossover {d.get('label') or n}: its through tracks must run level for "
                            f"{((depth + 1) // 2 + OS_REACH) / scale:g} grid units each side of it "
                            f"(rows {r1} and {r2}, column {x[n]:g})")
            for p, q in (((a, y1), (b, y2)), ((a, y2), (b, y1))):
                for st in unit_steps([p, q]):
                    for cell, track in step_pieces(*st):
                        P.add(cell, track, os_key(n), f"double crossover {d.get('label')}")
            h = depth // 2      # the middle of the X: a column edge when the X is an even number of rows deep,
            if depth % 2 == 0:  # else the edge between two rows
                P.crossings |= {((a + h - 1, y1 + h), "RIGHT"), ((a + h, y1 + h), "LEFT")}
            else:
                P.crossings |= {((a + h, y1 + h), "BOTTOM"), ((a + h, y1 + h + 1), "TOP")}
            for yy, xp, frog in ((y1, a, "LEFT"), (y2, a, "LEFT"), (y1, b, "RIGHT"), (y2, b, "RIGHT")):
                cell = (xp, yy) if frog == "LEFT" else (xp - 1, yy)
                routes = [(ENDS[t][1] if ENDS[t][0] == frog else ENDS[t][0], t == "HORIZONTAL")
                          for t in P.cells[cell] if frog in ENDS[t]]
                P.points[(cell, frog)] = dict(switch=d.get("label") or n, routes=sorted(routes))
            if d.get("label"):
                cands = [((xc, y1 - 1), "LOWCENT"), ((xc - 1, y1 - 1), "LOWCENT"), ((xc, y2 + 1), "UPCENT")]
                if compact:                     # over the X, in its top through track's cells, else under it
                    cands = [((xx, y1), "UPCENT") for xx in range(a, b)] + \
                        [((xx, y2), "LOWCENT") for xx in range(a, b)] + cands
                P.label(cands, d["label"], rank=1)

        # switch points
        for n, d in sorted(nodes.items()):
            if d["kind"] != "switch":
                continue
            legs = {}
            for port, sid in list(d["ins"].items()) + list(d["outs"].items()):
                c = info[sid]
                at_src = tuple(strands[sid]["src"]) == (n, port)
                a, b = c["steps"][0] if at_src else c["steps"][-1][::-1]
                legs[port] = (a, b)
            here = legs["A"][0]
            frog = touching(here, legs["B"][1])
            if touching(here, legs["C"][1]) != frog or touching(here, legs["A"][1]) == frog:
                raise SchematicError(f"switch {d.get('label') or n}: legs B and C do not leave the points on one side")
            cell, edge = frog
            routes, ports = [], {}
            normal = sw_bind.get((bi, n), {}).get("normal", "B")
            for port in ("B", "C"):
                a, b = legs[port]
                track = next(t for c_, t in step_pieces(a, b) if c_ == cell)
                e = ENDS[track]
                far = e[1] if e[0] == edge else e[0]
                routes.append((far, port == normal))
                ports[far] = port
            P.points[frog] = dict(switch=d.get("label") or n, routes=sorted(routes), node=(bi, n), ports=ports)
            shown = (d.get("label") or "") + (d.get("facing") or "")
            if shown:
                px, py = cell
                cands = [((px, py + 1), "UPCENT"), ((px, py - 1), "LOWCENT"), ((px + 1, py + 1), "UPCENT"),
                         ((px - 1, py + 1), "UPCENT"), ((px + 1, py - 1), "LOWCENT"), ((px - 1, py - 1), "LOWCENT")]
                if compact:     # beside the points, on the side away from the diverging leg first
                    heel = neighbour(cell, edge)[0]
                    up = any("TOP" in ENDS[t] for t in P.cells[cell])
                    down = any("BOTTOM" in ENDS[t] for t in P.cells[cell])
                    halves = ["LOWCENT", "UPCENT"] if up and not down else ["UPCENT", "LOWCENT"]
                    beyond = neighbour(heel, edge)[0]
                    cands = [(c_, h_) for h_ in halves for c_ in (heel, cell, beyond)] + cands
                P.label(cands, shown, rank=1)

        # track names, in a free cell below the strand's longest level run
        for sid, s in sorted(strands.items()):
            if not s["name"] or sid not in info:
                continue
            runs = [(a, b) for a, b in zip(info[sid]["pts"], info[sid]["pts"][1:]) if a[1] == b[1] and a != b]
            if not runs:
                continue
            a, b = max(runs, key=lambda r: (abs(r[1][0] - r[0][0]), -r[0][0]))
            xa, xb, y = min(a[0], b[0]), max(a[0], b[0]), a[1]
            mid = (xa + xb) // 2
            cols = sorted(range(xa, xb), key=lambda c: (abs(c - mid), c))
            cands = [((c, y + 1), "UPCENT") for c in cols] + [((c, y - 1), "LOWCENT") for c in cols]
            if compact:                         # in the track's own cells, over it first
                cands = [((c, y), "UPCENT") for c in cols] + [((c, y), "LOWCENT") for c in cols] + cands
            P.label(cands, s["name"].upper(), rank=3)

        top = max(c[1] for c in P.cells) + (COMPACT_GAP if compact else BAND_GAP)

    # end joins and end labels
    by_link, by_helix = defaultdict(list), defaultdict(list)
    for e in ends:
        d = e[2]
        if d.get("sub") == "link" and d.get("label"):
            by_link[d["label"]].append(e)
        elif d.get("sub") == "helix" and e[3]:
            by_helix[e[3]].append(e)
    joined = set()
    for group in list(by_link.values()) + list(by_helix.values()):
        if len(group) == 2 and group[0][0] != group[1][0]:
            (ca, cb) = group[0][4], group[1][4]
            P.shared[ca], P.shared[cb] = cb, ca
            ka, kb = group[0][5], group[1][5]
            if ka[0] == kb[0] == "track":       # one track drawn on two bands is one block
                P.union(ka, kb)
            joined |= {id(group[0]), id(group[1])}
    for e in ends:
        title, n, d, name, (cell, edge), _ = e
        if d.get("sub") not in ("link", "helix"):
            continue
        to = d.get("to") or ""
        text = (f"{d.get('label')}: TO {to.upper()}" if d.get("sub") == "link" else f"HELIX TO {to.upper()}").strip()
        if id(e) in joined:
            text += " (JOINED)"
        beyond = (cell[0] + (1 if edge == "RIGHT" else -1), cell[1])
        below = (cell[0], cell[1] + 1)
        # text runs to the right: beside an east end, under a west end (beside it, it would run over the track)
        cands = [(beyond, "LEFTCENT"), (below, "UPLEFT")] if edge == "RIGHT" else [(below, "UPLEFT"), ((cell[0], cell[1] - 1), "LOWLEFT")]
        if compact:     # also over or under the track running back from the end
            back = -1 if edge == "RIGHT" else 1
            cands += [((cell[0] + back * k, cell[1] + dy), loc) for k in range(8)
                      for dy, loc in ((0, "UPLEFT"), (0, "LOWLEFT"), (1, "UPLEFT"), (-1, "LOWLEFT"))]
        P.label(cands, text, rank=2)

    # block names: unique; an OS block after its switch numbers (several when tracks too short to part them merge it).
    # A block name bound to switches is one block wherever they are, and is never suffixed.
    by_bound = defaultdict(list)
    for key in P.blocks:
        if key[0] == "os" and sw_bind.get(node_of(key), {}).get("block"):
            by_bound[sw_bind[node_of(key)]["block"]].append(key)
    for keys in by_bound.values():
        for k in keys[1:]:
            P.union(keys[0], k)
    groups = defaultdict(list)
    for key in sorted(P.blocks):
        groups[P.find(key)].append(key)
    for root in sorted(groups, key=lambda r: (r[0] != "track", r)):
        keys = groups[root]
        labels = sorted({label_of(bands, k) for k in keys if k[0] == "os"} - {""}, key=number_order)
        bound = sorted({sw_bind[node_of(k)]["block"] for k in keys
                        if k[0] == "os" and sw_bind.get(node_of(k), {}).get("block")})
        if len(bound) > 1:
            raise SchematicError(f"switches {', '.join(labels)} share one OS block (the track between them is too "
                                 f"short to part them), but are bound to blocks {', '.join(bound)}")
        if bound:
            P.names[root] = bound[0]
            continue
        base = ("OS " + "-".join(labels) if labels else "OS") if any(k[0] == "os" for k in keys) else \
            (next(P.blocks[k] for k in keys) or "Track")
        if base in by_bound:
            raise SchematicError(f"switches are bound to block {base}, which is also the name of another block "
                                 "of the panel; bind them to a name of their own")
        if any(k[0] == "os" for k in keys):
            P.names[root] = unique(base)
            if len(labels) > 1:
                P.log.append(f"switches {', '.join(labels)} share one OS block: the tracks between them are too short "
                             "to hold a block of their own")
        else:
            P.names[root] = unique(base)
    bind_blocks(P, bindings["blocks"], set(by_bound))
    bind_routes(P, sw_bind)
    bind_masts(P, bands, bindings["masts"], chains, turn_bounds)
    if compact:
        place_labels(P)
    return P


# Label placement on a compact panel, where names share cells with track. CATS draws a label as a JLabel at its
# cell's LOC_NAME spot (cats/gui/frills/FrillLoc.java) and lets it spill over the cells beside it, so each label is
# measured at the default 30 pixel grid and put at the first candidate spot where it covers no track line, signal
# or other label. Text widths are estimates of the CATS fonts (11 point labels, 13 point bold titles).
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


def track_lines(P):
    """Every drawn track as a pixel line segment."""
    h = GRID_PX // 2
    mid = {"LEFT": (0, h), "RIGHT": (GRID_PX, h), "TOP": (h, 0), "BOTTOM": (h, GRID_PX)}
    out = []
    for (x, y), tracks in P.cells.items():
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


def crosses(box, line):
    """True when the line segment passes through the inside of the box (its ink: the box less a 2 pixel rim)."""
    x0, y0, x1, y1 = box[0] + 2, box[1] + 2, box[2] - 2, box[3] - 2
    ax, ay, bx, by = line
    for i in range(33):
        f = i / 32
        px, py = ax + (bx - ax) * f, ay + (by - ay) * f
        if x0 < px < x1 and y0 < py < y1:
            return True
    return False


def overlaps(a, b, pad=2):
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] and b[1] < a[3]


def place_labels(P):
    """Place a compact panel's pending labels, lower rank first: each at its first candidate that stays inside the
    drawing and covers no track, signal or placed label; else at the candidate with the fewest such clashes
    (logged)."""
    lines, signals = track_lines(P), signal_boxes(P)
    right = (max(c[0] for c in P.cells) + 1) * GRID_PX
    placed = []
    for _, _, cands, text, font in sorted(P.pending, key=lambda r: r[:2]):
        best = None
        for cell, loc in cands:
            if cell in P.labels or cell[0] < 1 or cell[1] < 1:
                continue
            box = text_box(cell, loc, text, font)
            if box[0] < GRID_PX or box[2] > right:
                continue
            clash = sum(crosses(box, ln) for ln in lines) + sum(overlaps(box, sb, 0) for sb in signals) + \
                sum(overlaps(box, pb) for pb in placed)
            if best is None or clash < best[0]:
                best = (clash, cell, loc, box)
            if clash == 0:
                break
        if best is None:
            P.log.append(f"no room for label {text!r}")
            continue
        clash, cell, loc, box = best
        if clash:
            P.log.append(f"label {text!r} at {cell} {loc} crosses {clash} track lines, signals or labels")
        P.labels[cell] = (text, loc, font)
        placed.append(box)
    P.pending = None


def node_of(key):
    """(band index, node) of an OS block key."""
    tag, n = key[1].split(":", 1)
    return int(tag[1:]), n


def check_io(io, where):
    """One IOSPEC binding: its attributes and its command."""
    if not isinstance(io, dict):
        raise SchematicError(f"{where}: an IOSPEC is an object with DECADDR, JMRIPREFIX, USER_NAME and command")
    unknown = set(io) - IOSPEC_KEYS - {"command"}
    if unknown:
        raise SchematicError(f"{where}: unknown IOSPEC field {', '.join(sorted(unknown))} "
                             f"(fields: {', '.join(sorted(IOSPEC_KEYS))}, command)")
    if io.get("DECADDR") in (None, ""):
        raise SchematicError(f"{where}: an IOSPEC needs a DECADDR")
    if io.get("command") not in ("close", "throw"):
        raise SchematicError(f"{where}: an IOSPEC command is close or throw, not {io.get('command')!r}")
    return {k: str(v) for k, v in io.items()}


def check_bindings(b):
    """The bindings with every field checked; unknown fields are errors (keys starting with _ are notes)."""
    def fields(obj, allowed, where):
        if not isinstance(obj, dict):
            raise SchematicError(f"{where}: expected an object")
        unknown = {k for k in obj if not k.startswith("_")} - set(allowed)
        if unknown:
            raise SchematicError(f"{where}: unknown field {', '.join(sorted(unknown))} (fields: {', '.join(allowed)})")
        return {k: v for k, v in obj.items() if not k.startswith("_")}
    b = fields(b, ("switches", "blocks", "masts"), "bindings")
    out = {"switches": {}, "blocks": {}, "masts": {}}
    section = lambda name: fields(b.get(name) or {}, [k for k in (b.get(name) or {})], f"bindings {name}")
    for key, e in section("switches").items():
        e = fields(e, ("block", "normal", "routes"), f"switch {key}")
        if e.get("normal", "B") not in ("B", "C"):
            raise SchematicError(f"switch {key}: normal is leg B or C, not {e['normal']!r}")
        routes = fields(e.get("routes", {}), ("B", "C"), f"switch {key} routes")
        e["routes"] = {port: [(tag, check_io(io, f"switch {key} leg {port} {tag}"))
                              for tag, io in fields(r, ROUTE_TAGS, f"switch {key} leg {port}").items()]
                       for port, r in routes.items()}
        out["switches"][key] = e
    for key, e in section("blocks").items():
        e = fields(e, ("name", "station", "discipline", "occupied", "unoccupied"), f"block {key}")
        if e.get("discipline") is not None and e["discipline"] not in DISCIPLINES:
            raise SchematicError(f"block {key}: discipline {e['discipline']!r} is not one CATS reads: "
                                 f"{', '.join(DISCIPLINES)}")
        for f in ("occupied", "unoccupied"):
            if f in e:
                e[f] = check_io(e[f], f"block {key} {f}")
        out["blocks"][key] = e
    for key, e in section("masts").items():
        e = fields(e, ("name", "template", "pantype"), f"mast {key}")
        if e.get("pantype") is not None and e["pantype"] not in SIG_PANTYPES:
            raise SchematicError(f"mast {key}: pantype is one of {', '.join(SIG_PANTYPES)}")
        out["masts"][key] = e
    return out


def switch_bindings(bands, switches):
    """{(band index, node): binding} for the switch keys, LABEL or LABEL/ALIAS. A key that names no switch is an
    error, and so is a switch named by two keys."""
    out, owner = {}, {}
    switch_nodes = [(bi, n, str(d.get("label") or ""), str(d.get("alias") or ""), d["kind"])
                    for bi, (_, band, _) in enumerate(bands) for n, d in band["nodes"].items()
                    if d["kind"] in ("switch", "dx")]
    for key, e in switches.items():
        hits = [(bi, n) for bi, n, lb, _, _ in switch_nodes if lb == key]       # the whole key is a label
        if not hits and "/" in key:                                            # else LABEL/ALIAS, at the last /
            label, _, alias = key.rpartition("/")
            hits = [(bi, n) for bi, n, lb, al, _ in switch_nodes if lb == label and al == alias]
        if not hits:
            raise SchematicError(f"bindings name switch {key}, which no drawn band has")
        for h in hits:
            if bands[h[0]][1]["nodes"][h[1]]["kind"] == "dx" and (e.get("routes") or "normal" in e):
                raise SchematicError(f"switch {key}: a double crossover takes a block binding only (no routes or normal)")
            if h in owner:
                d = bands[h[0]][1]["nodes"][h[1]]
                raise SchematicError(f"switch {d.get('label')}/{d.get('alias') or h[1]} is bound by both "
                                     f"{owner[h]} and {key}")
            owner[h] = key
            out[h] = e
    return out


def bind_blocks(P, blocks, switch_named=()):
    """Rename, merge and bind blocks. Blocks the bindings give one name (a block keyed in the bindings, or named by
    switch bindings, keeps its own name) become one block, logged; a rename onto the name of a block the bindings do
    not mention is an error."""
    root_of = {name: root for root, name in P.names.items()}       # block names are unique
    unknown = set(blocks) - set(root_of)
    if unknown:
        raise SchematicError(f"bindings name block {', '.join(sorted(unknown))}, which the panel does not have "
                             f"(blocks: {', '.join(sorted(root_of))})")
    explicit = set(blocks) | set(switch_named)
    groups = defaultdict(list)
    for name, root in sorted(root_of.items()):
        groups[blocks.get(name, {}).get("name") or name].append(name)
    for final, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        loose = [m for m in members if m not in explicit]
        if loose:
            raise SchematicError(f"bindings rename block {', '.join(m for m in members if m in blocks and m != final)} "
                                 f"to {final}, the name of block {', '.join(loose)}, which the bindings do not name")
        for m in members[1:]:
            P.union(root_of[members[0]], root_of[m])
        P.log.append(f"blocks {', '.join(members)} are one block, {final}")
    names, info = {}, {}
    for name, root in sorted(root_of.items()):
        r = P.find(root)
        final = blocks.get(name, {}).get("name") or name
        names[r] = final
        e = blocks.get(name)
        if e:
            have = info.setdefault(r, {})
            for f in ("station", "discipline", "occupied", "unoccupied"):
                if f in e:
                    if f in have and have[f] != e[f]:
                        raise SchematicError(f"blocks merged into {final} are bound with two different {f}s")
                    have[f] = e[f]
    P.names, P.block_info = names, info


def bind_routes(P, sw_bind):
    """Each bound switch's route IOSPECs on its points, by leg."""
    for at, pt in P.points.items():
        e = sw_bind.get(pt.get("node"))
        if not e or not e.get("routes"):
            continue
        P.route_io[at] = {edge: e["routes"].get(port, []) for edge, port in pt["ports"].items()}


def bind_masts(P, bands, masts, chains, turn_bounds):
    """Each bound mast on the block boundary nearest where it stands, on the edge of the block it protects."""
    known = {sg["mast"]: sg for _, _, o in bands for sg in o.get("signals") or ()}
    unknown = set(masts) - set(known)
    if unknown:
        raise SchematicError(f"bindings name mast {', '.join(sorted(unknown))}, which no band's signals have")
    for name, e in sorted(masts.items()):
        if known[name].get("kind") == "virtual":
            raise SchematicError(f"mast {name} is virtual (Dispatcher only): it is not drawn")
        hits = [(bi, sg, spot) for bi, (_, band, o) in enumerate(bands) for sg in o.get("signals") or ()
                if sg["mast"] == name for spot in [mast_piece(sg, band["strands"])]
                if spot is not None and (bi, spot[0]) in chains]
        if len(hits) != 1:
            raise SchematicError(f"mast {name}: " + ("it stands on no drawn track" if not hits else
                                                     "it stands on tracks of two drawn bands"))
        bi, sg, (k, at, piece_cm, start) = hits[0]
        strand = bands[bi][1]["strands"][k]
        c = chains[(bi, k)]
        n = len(c["steps"])
        # the pieces with their blocks and [start, end] in steps, oriented from the end its move is heading for
        seq = [(cell, track, a, b, P.find(o)) for (cell, track, a, b), o in zip(c["pieces"], c["owner"])]
        if strand["src"][0] == start:
            near, far = strand["src"][0], strand["dst"][0]
        elif strand["dst"][0] == start:
            seq = [(cell, track, n - b, n - a, o) for cell, track, a, b, o in reversed(seq)]
            near, far = strand["dst"][0], strand["src"][0]
        else:
            raise SchematicError(f"mast {name}: cannot tell which end of track {strand['name'] or k} it faces")
        cands = []
        for (cell, track, _, end, o), (cell2, track2, _, _, o2) in zip(seq, seq[1:]):
            if o != o2:                          # on the nearer block's piece, at the edge toward the next one
                edge = next(e for e in ENDS[track] if neighbour(cell, e)[0] == cell2 and
                            neighbour(cell, e)[1] in ENDS[track2])
                cands.append((end, (cell, edge)))
        live = lambda b: b is not None and P.find(b[1]) != P.find(b[2])     # halves later merged: no boundary
        tb = turn_bounds.get((bi, far), {}).get(k)
        if live(tb):                             # past the far end: this half's side of the cut
            cands.append((n + 0.5, tb[0]))
        other = next((v for s_, v in turn_bounds.get((bi, near), {}).items() if s_ != k), None)
        if live(other):                          # behind the near end: the other half's side, the block it enters
            cands.append((-0.5, other[0]))
        if not cands:
            raise SchematicError(f"mast {name}: no block boundary on its track {strand['name'] or k}")
        pos = n * at / piece_cm if piece_cm else 0.0
        i, (cell, edge) = min(cands, key=lambda c_: (abs(c_[0] - pos), c_[0]))
        if (cell, edge) in P.signals:
            raise SchematicError(f"masts {P.signals[(cell, edge)]['mast']} and {name} fall on one block boundary")
        heads = max(1, min(3, int(sg.get("heads") or 1)))
        P.signals[(cell, edge)] = dict(mast=name, name=e.get("name") or name, loc=SIG_LOCATION[edge],
                                       orient=OPPOSITE[edge], pantype=e.get("pantype") or f"LAMP{heads}",
                                       template=e.get("template"))


def number_order(label):
    digits = "".join(ch for ch in label if ch.isdigit())
    return (int(digits) if digits else 0, label)


def label_of(bands, key):
    tag, n = key[1].split(":", 1)
    band = bands[int(tag[1:])][1]
    return band["nodes"][n].get("label") or ""


def boundaries(P):
    """{(cell, edge): block root} of every edge where one block ends and another (or a joined end) begins."""
    out = {}
    for cell, tracks in P.cells.items():
        for edge in EDGE_ORDER:
            mine = {P.find(b) for t, b in tracks.items() if edge in ENDS[t]}
            if not mine:
                continue
            far, fedge = P.shared.get((cell, edge)) or neighbour(cell, edge)
            theirs = {P.find(b) for t, b in P.cells.get(far, {}).items() if fedge in ENDS[t]}
            if theirs and mine != theirs:
                if (cell, edge) in P.points or (cell, edge) in P.crossings or len(mine) > 1:
                    raise SchematicError(f"cell {cell} edge {edge}: a block boundary on switch points or a crossing; "
                                         "CATS would drop the points")
                out[(cell, edge)] = next(iter(mine))
    return out


def dangling(P, cell, edge):
    """True when no track continues across this edge of `cell`: a track end."""
    if (cell, edge) in P.shared:
        return False
    far, fedge = neighbour(cell, edge)
    return not any(fedge in ENDS[t] for t in P.cells.get(far, {}))


def lone_blocks(P, bounds):
    """{(cell, edge): block root} naming each block that has no boundary at one of its track ends."""
    have = set(bounds.values())
    out = {}
    for cell in sorted(P.cells, key=lambda c: (c[1], c[0])):
        for edge in EDGE_ORDER:
            blks = {P.find(b) for t, b in P.cells[cell].items() if edge in ENDS[t]}
            if len(blks) == 1 and dangling(P, cell, edge):
                blk = next(iter(blks))
                if blk not in have:
                    out[(cell, edge)] = blk
                    have.add(blk)
    missing = set(P.names) - have
    if missing:
        raise SchematicError("blocks with no boundary and no track end to name them on: " +
                             ", ".join(sorted(P.names[b] for b in missing)))
    return out


HEADER_FONTS = [
    ("FONT_LABEL", "Grid Labels", "-1", "11", "PLAIN"),
    ("FONT_TRAIN", "Train Identities", "-1", "11", "PLAIN"),
    ("ONCALL", "On Call Train", "-4144960", "11", "PLAIN"),
    ("ACTIVE", "Active Train", "-14336", "11", "PLAIN"),
    ("SELECTED", "Selected Train", "-16711681", "11", "PLAIN"),
    ("TIEDUP", "Tied Down Train", "-65281", "11", "PLAIN"),
    ("FONT_TITLE", "Panel Title", "-1", "13", "BOLD"),
]


def header_from(path):
    """The SIGNALTEMPLATE and JMRINAME elements of an existing CATS panel, to copy into a generated one: the
    physical signal templates its masts name, and the JMRI device prefixes its IOSPECs use."""
    try:
        src = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        raise SchematicError(f"{path}: cannot read it as a CATS panel ({e})") from None
    if src.tag != "DOCUMENT":
        raise SchematicError(f"{path}: not a CATS panel (its root is {src.tag})")
    return [el for el in src if el.tag in ("SIGNALTEMPLATE", "JMRINAME")]


def set_io(parent, tag, io):
    io = dict(io)
    ET.SubElement(ET.SubElement(parent, tag), "IOSPEC", **{k: v for k, v in io.items() if k != "command"}).text = \
        io["command"]


def to_xml(P, discipline="CTC", header=()):
    """The panel as a CATS Designer document (an ElementTree root). `header`: SIGNALTEMPLATE and JMRINAME
    elements to copy in (header_from)."""
    cols, rows = P.size()
    root = ET.Element("DOCUMENT", VERSION="3.1")
    for key, name, color, size, style in HEADER_FONTS:
        ET.SubElement(root, "FONTDEFINITION", FONTKEY=key, FONTNAME=name, FONTCOLOR=color, FONTSIZE=size,
                      FONTSTYLE=style)
    templates = set()
    for el in header:
        if el.tag == "SIGNALTEMPLATE":
            root.append(copy.deepcopy(el))
            templates.add(el.get("TEMPLATENAME"))
    missing = sorted({s["template"] for s in P.signals.values() if s["template"]} - templates)
    if missing:
        raise SchematicError(f"masts name signal template {', '.join(missing)}, which the panel has no "
                             "SIGNALTEMPLATE for (copy them in from a panel that has them)")
    ET.SubElement(root, "COMPRESSIONTAG")      # present = Compress Screen off
    ET.SubElement(root, "ROWWRAPTAG")          # present = Automatic Wrapping off
    for el in header:
        if el.tag == "JMRINAME":
            root.append(copy.deepcopy(el))
    plan = ET.SubElement(root, "TRACKPLAN", COLUMNS=str(cols), ROWS=str(rows))
    if discipline not in DISCIPLINES:
        raise SchematicError(f"discipline {discipline!r} is not one CATS reads: {', '.join(DISCIPLINES)}")
    bounds = boundaries(P)
    bounds.update(lone_blocks(P, bounds))
    stray = sorted(set(P.signals) - set(bounds))
    if stray:
        raise SchematicError("masts " + ", ".join(P.signals[s]["mast"] for s in stray) + " are not on a block boundary")
    for cell in sorted(set(P.cells) | set(P.labels), key=lambda c: (c[1], c[0])):
        sec = ET.SubElement(plan, "SECTION", X=str(cell[0]), Y=str(cell[1]))
        tracks = P.cells.get(cell, {})
        if tracks:
            grp = ET.SubElement(sec, "TRACKGROUP")
            for t in sorted(tracks, key=list(ENDS).index):
                ET.SubElement(grp, "TRACK").text = t
            for edge in EDGE_ORDER:
                if not any(edge in ENDS[t] for t in tracks):
                    continue
                se = ET.SubElement(sec, "SEC_EDGE", EDGE=edge)
                if (cell, edge) in P.signals:
                    sg = P.signals[(cell, edge)]
                    ss = ET.SubElement(se, "SECSIGNAL")
                    ss.text = sg["name"]
                    ET.SubElement(ss, "PANELSIGNAL", SIGLOCATION=sg["loc"], SIGORIENT=sg["orient"],
                                  SIGPANTYPE=sg["pantype"])
                    if sg["template"]:
                        ET.SubElement(ss, "PHYSIGNAL").text = sg["template"]
                if (cell, edge) in bounds:
                    if (cell, edge) in P.points or (cell, edge) in P.crossings:
                        raise SchematicError(f"cell {cell} edge {edge}: a block on switch points or a crossing")
                    # every boundary edge names its block in full: CATS keeps one Block per name (Block.findBlock)
                    blk = bounds[(cell, edge)]
                    bi = P.block_info.get(blk, {})
                    b = ET.SubElement(se, "BLOCK", NAME=P.names[blk])
                    if bi.get("station"):
                        b.set("STATION", bi["station"])
                    b.set("DISCIPLINE", bi.get("discipline") or discipline)
                    b.set("VISIBLE", "true")
                    if bi.get("occupied"):
                        set_io(b, "OCCUPIEDSPEC", bi["occupied"])
                    if bi.get("unoccupied"):
                        set_io(b, "UNOCCUPIEDSPEC", bi["unoccupied"])
                elif (cell, edge) in P.points:
                    sp = ET.SubElement(se, "SWITCHPOINTS")
                    io = P.route_io.get((cell, edge), {})
                    for rid, normal in P.points[(cell, edge)]["routes"]:
                        ri = ET.SubElement(sp, "ROUTEINFO", ROUTEID=rid)
                        if normal:
                            ri.set("NORMAL", "true")
                        for tag, spec in io.get(rid, []):
                            set_io(ri, tag, spec)
                elif (cell, edge) in P.crossings:
                    others = sorted(ENDS[t][1] if ENDS[t][0] == edge else ENDS[t][0] for t in tracks if edge in ENDS[t])
                    ET.SubElement(se, "CROSSINGEDGE", **{o: "NO_BLOCK" for o in others})
                if (cell, edge) in P.shared:
                    (fx, fy), fedge = P.shared[(cell, edge)]
                    ET.SubElement(se, "SHARED", X=str(fx), Y=str(fy)).text = fedge
        if cell in P.labels:
            text, loc, font = P.labels[cell]
            ET.SubElement(sec, "SEC_NAME", LOC_NAME=loc, NAME=text, FONT_NAME=font)
    ET.indent(root, "  ")
    return root


def write(P, out, discipline="CTC", header=()):
    root = to_xml(P, discipline, header)
    text = "<?xml version='1.0' encoding='UTF-8'?>\n" + ET.tostring(root, encoding="unicode") + "\n"
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def shown(P):
    """(columns, rows) of cells CATS lays out on screen: every column from 1 to the rightmost one with track or a
    label (column 0 is never used), and the rows from the top to the bottom one with track or a label
    (cats/gui/Screen.java findBounds)."""
    cells = list(P.cells) + list(P.labels)
    return max(c[0] for c in cells), max(c[1] for c in cells) - min(c[1] for c in cells) + 1


def check_fit(P, cols, rows):
    """An error when the panel shows more than cols x rows cells (the screen at CATS's fixed grid size)."""
    have = shown(P)
    if have[0] > cols or have[1] > rows:
        raise SchematicError(f"the panel shows {have[0]} x {have[1]} cells, more than the {cols} x {rows} it must "
                             f"fit ({max(0, have[0] - cols)} columns and {max(0, have[1] - rows)} rows over)")
    return have


def parse_fit(text):
    """'COLSxROWS' as (cols, rows)."""
    try:
        cols, rows = (int(v) for v in text.lower().split("x"))
    except ValueError:
        raise SchematicError(f"--fit is COLSxROWS, such as 63x36, not {text!r}") from None
    if cols < 1 or rows < 1:
        raise SchematicError(f"--fit is COLSxROWS with both at least 1, not {text!r}")
    return cols, rows


def summary(P):
    blocks = len(set(P.names.values()))
    text = (f"{len(P.cells)} track cells, {len(P.points)} switch points, {len(P.crossings) // 2} crossings, "
            f"{blocks} blocks, {len(P.shared) // 2} logical joins, {len(P.labels)} labels")
    if P.block_info or P.route_io or P.signals:
        occupied = sum(1 for b in P.block_info.values() if b.get("occupied"))
        text += (f"; bound: {occupied} block sensors, {len(P.route_io)} switch points, {len(P.signals)} masts")
    return text
