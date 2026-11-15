"""A CATS Designer panel (XML) seeded from the solved bands: the same track on CATS's grid of cells.

    panel = cats.panel(sheet.bands)        # a Panel: cells, blocks, switches, joins, labels
    cats.write(panel, "OUT.xml")

Grid. A schematic grid point (column c, row r) becomes the CATS point (SCALE * c, SCALE * r) plus a margin; a
CATS point (X, Y) is the middle of the LEFT edge of cell (X, Y). One step from (X, Y) to (X + 1, Y + d) is
d = 0: cell (X, Y) HORIZONTAL; d = -1: cell (X, Y) UPPERSLASH and (X, Y - 1) LOWERSLASH; d = +1: cell (X, Y)
LOWERBACKSLASH and (X, Y + 1) UPPERBACKSLASH. So every 45 degree leg lands on whole cells, a switch's legs meet on
one cell edge (its points), and SCALE = 2 leaves a free row under every track for its name. A double crossover is
drawn as its X with a crossing edge in the middle; a turnback is a vertical run in one column.

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

    def label(self, cands, text, font="FONT_LABEL"):
        """Put `text` in the first candidate (cell, loc) with no label, preferring cells with no track."""
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
    if scale % 2:
        raise SchematicError("the CATS scale must be even, so a double crossover's X lands on whole cells")
    bindings = check_bindings(bindings or {})
    sw_bind = switch_bindings(bands, bindings["switches"])
    P = Panel()
    chains, turn_bounds = {}, {}     # (band, strand) -> its steps and their blocks; (band, turnback) -> its boundary
    top = MARGIN + 1
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
        ox = MARGIN + 1 - int(round(scale * x0))
        oy = top + 2 - int(round(scale * r0))
        pt = lambda p: (ox + int(round(scale * p[0])), oy + int(round(scale * p[1])))
        tag = f"b{bi}:"

        # the band title and which way is east
        left, right = opts.get("left", "West"), opts.get("right", "East")
        P.label([((MARGIN, top), "LOWLEFT"), ((MARGIN, top - 1), "LOWLEFT")],
                f"{band_key_name(title).upper()}   {left.upper()} <-   -> {right.upper()}", "FONT_TITLE")

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

        # how far each switch's OS reaches along its tracks, in steps
        reach = {}
        for n, d in nodes.items():
            if d["kind"] == "switch":
                reach[n] = OS_REACH
            elif d["kind"] == "dx":
                (iu, _), (il, _) = dx_tracks(nodes, n)
                r1, r2 = sorted((band["R"]["srow"][iu], band["R"]["srow"][il]))
                reach[n] = int(round(scale * (r2 - r1))) // 2 + OS_REACH     # the X, then past its points

        # strands
        turn_of, info = {}, {}
        for sid, s in strands.items():
            for t in (s["src"][0], s["dst"][0]):
                if nodes[t]["kind"].startswith("turn"):
                    turn_of.setdefault(t, []).append(sid)
        for sid, s in sorted(strands.items()):
            pts = [pt(p) for p in drawn[sid]]
            steps = unit_steps(pts)
            if not steps:
                raise SchematicError(f"{title}: track {s['name'] or sid} is drawn as a single point")
            u, v = s["src"][0], s["dst"][0]
            track_key = ("track", tag + sid)
            P.blocks.setdefault(track_key, None)
            owner = [track_key] * len(steps)
            ru, rv = reach.get(u, 0), reach.get(v, 0)
            for i in range(min(ru, len(steps))):
                owner[i] = os_key(u)
            for i in range(min(rv, len(steps))):
                j = len(steps) - 1 - i
                if owner[j] != track_key and owner[j] != os_key(v):
                    P.union(owner[j], os_key(v))
                owner[j] = os_key(v)
            if track_key not in owner:
                del P.blocks[track_key]
            for (a, b), key in zip(steps, owner):
                for cell, track in step_pieces(a, b):
                    P.add(cell, track, key, f"track {s['name'] or sid}")
            if track_key in P.blocks:
                P.blocks[track_key] = s["name"] or f"{node_ref(nodes[u])}-{node_ref(nodes[v])}"
            for n, end_pt, nxt, key in ((u, pts[0], steps[0][1], owner[0]), (v, pts[-1], steps[-1][0], owner[-1])):
                d = nodes[n]
                if d["kind"] == "end":
                    ends.append((title, n, d, s["name"], touching(end_pt, nxt), key))
            info[sid] = dict(steps=steps, owner=owner, pts=pts)
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
            h = (y2 - y1) // 2
            # the X spans h cells each side of its centre, and its points need one level step beyond that
            for yy in (y1, y2):
                for xx in range(xc - h - OS_REACH, xc + h + OS_REACH):
                    here = P.cells.get((xx, yy), {}).get("HORIZONTAL")
                    if here is None or P.find(here) != P.find(os_key(n)):
                        raise SchematicError(
                            f"double crossover {d.get('label') or n}: its through tracks must run level for "
                            f"{(h + OS_REACH) / scale:g} grid units each side of it (rows {r1} and {r2}, column {x[n]:g})")
            for a, b in (((xc - h, y1), (xc + h, y2)), ((xc - h, y2), (xc + h, y1))):
                for st in unit_steps([a, b]):
                    for cell, track in step_pieces(*st):
                        P.add(cell, track, os_key(n), f"double crossover {d.get('label')}")
            P.crossings |= {((xc - 1, y1 + h), "RIGHT"), ((xc, y1 + h), "LEFT")}     # the middle of the X
            for yy, xp, frog in ((y1, xc - h, "LEFT"), (y2, xc - h, "LEFT"), (y1, xc + h, "RIGHT"), (y2, xc + h, "RIGHT")):
                cell = (xp, yy) if frog == "LEFT" else (xp - 1, yy)
                routes = [(ENDS[t][1] if ENDS[t][0] == frog else ENDS[t][0], t == "HORIZONTAL")
                          for t in P.cells[cell] if frog in ENDS[t]]
                P.points[(cell, frog)] = dict(switch=d.get("label") or n, routes=sorted(routes))
            if d.get("label"):
                P.label([((xc, y1 - 1), "LOWCENT"), ((xc - 1, y1 - 1), "LOWCENT"), ((xc, y2 + 1), "UPCENT")],
                        d["label"])

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
                P.label([((px, py + 1), "UPCENT"), ((px, py - 1), "LOWCENT"), ((px + 1, py + 1), "UPCENT"),
                         ((px - 1, py + 1), "UPCENT"), ((px + 1, py - 1), "LOWCENT"), ((px - 1, py - 1), "LOWCENT")],
                        shown)

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
            P.label([((c, y + 1), "UPCENT") for c in cols] + [((c, y - 1), "LOWCENT") for c in cols], s["name"].upper())

        top = max(c[1] for c in P.cells) + BAND_GAP

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
        P.label(cands, text)

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
    return P


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
        steps, owner = c["steps"], [P.find(o) for o in c["owner"]]
        if strand["src"][0] == start:            # orient the run from the end its move is heading for
            near, far = strand["src"][0], strand["dst"][0]
        elif strand["dst"][0] == start:
            steps, owner = [(b, a) for a, b in reversed(steps)], owner[::-1]
            near, far = strand["dst"][0], strand["src"][0]
        else:
            raise SchematicError(f"mast {name}: cannot tell which end of track {strand['name'] or k} it faces")
        n = len(steps)
        cands = [(i, touching(steps[i][0], steps[i - 1][0])) for i in range(1, n) if owner[i] != owner[i - 1]]
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


def summary(P):
    blocks = len(set(P.names.values()))
    text = (f"{len(P.cells)} track cells, {len(P.points)} switch points, {len(P.crossings) // 2} crossings, "
            f"{blocks} blocks, {len(P.shared) // 2} logical joins, {len(P.labels)} labels")
    if P.block_info or P.route_io or P.signals:
        occupied = sum(1 for b in P.block_info.values() if b.get("occupied"))
        text += (f"; bound: {occupied} block sensors, {len(P.route_io)} switch points, {len(P.signals)} masts")
    return text
