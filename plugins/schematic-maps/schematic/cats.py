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
end (place_labels) where they cover no track line, signal or label (a yard's parallel tracks in one column, end
labels beside their ends); one empty column is kept on the left; OS blocks reach a whole step past the points
where the track holds it, else one cell (half a 45 degree step); masts' gaps slide along their tracks so a
control point's masts stand in one column per direction and out of switch cells (shift_gaps), and each mast is
drawn at its clearest spot (spot_costs, place_mast; references/cats-signals.md); a one-unit level track between
two switches gets a second cell in its grid column (widened_columns), so their OS blocks still part; a double crossover between adjacent rows is one column wide with
its crossing on the edge between the rows. shown(P) is the cells CATS lays out on screen; check_fit tests it.

Blocks: one per strand (its track name, or the two switch numbers it joins), one OS block per switch (shared by
switches of the same number joined by a track), reaching one step past the points on every leg (further where a
compact panel slides a mast's gap), so no block boundary falls on a points or crossing edge. Each switch's points carry two ROUTEINFO, normal being leg B (the
straight leg as the band records it). No IOSPEC is written: binding sensors and turnouts is left to the Designer
or a later pass. Link ends with the same letter, and helix ends of the same track, on two drawn bands are joined
logically (SHARED); a helix track joined so is one block, or with `helix_blocks="apart"` a block on each band, parted
at the join. Other ends get a label saying where they go. A turnback joining two tracks of different names
is two blocks, parted in the middle of its vertical run.

Bindings (optional, `panel(bands, bindings=...)`, the command's --bindings FILE.json) tie the panel to the
layout's devices; every name in them must exist in the panel, or it is an error:

    {"switches": {"LABEL" or "LABEL/ALIAS": {"block": "OS name", "normal": "B" or "C", "label": "shown text",
                                              "corners": {"A": block, "B": .., "C": .., "D": .., "X": middle},
                                              "routes": {"B": {"ROUTECOMMAND": IO, "SELECTEDREPORT": IO}, "C": {..}}}},
     "blocks":   {"BLOCK": {"name": "layout name", "station": "..", "discipline": "CTC", "occupied": IO, "unoccupied": IO}},
     "masts":    {"MAST": {"name": "mast user name", "template": "physical signal template", "pantype": "LAMP2",
                           "orient": "LEFT", "RIGHT", "TOP" or "BOTTOM" (optional: the way the lamps point),
                           "location": a SIGLOCATION such as "LEFTLOW" (optional: where in its cell)}}}

IO is one CATS IOSPEC: {"DECADDR": .., "JMRIPREFIX": .., "USER_NAME": .., "command": "close" or "throw"} (also
JMRIDEVICE, EXIT_CMD, DELAY). A switch key is its label (every switch of that number) or label/alias (one of them; a key that
is not a whole label splits at its last /, and labels and aliases compare as text);
switches of one number given different `block`s keep apart. A double crossover's binding moves all four of its
points: route B along each through track, C into the X (normal B unless it says C). Its `corners` (in place of `block`) give it a block per band leg and one for the middle of the X; the X is then drawn two cells deep (a compact panel opens a row between its tracks, other slopes jogging across it) so each corner parts from the middle on a plain edge. BLOCK is the panel's block name after the switches'
`block`s; two blocks given one `name` become one block. MAST is a mast of a band's `signals`
(field or planned; virtual masts are not drawn). It goes on the block boundary nearest where it stands on its run:
on the edge of the block it protects (the side toward the switch or end its move is heading for), facing out of
that block, on the right-hand side of the move.
"""
import copy
import math
import xml.etree.ElementTree as ET
from collections import defaultdict

from .core import SchematicError, dx_tracks, node_ref
from .draw import mast_piece
from .layout import paths
from .cats_grid import MARGIN, BAND_GAP, COMPACT_GAP, ENDS, OPPOSITE, STEP, EDGE_ORDER, neighbour, step_pieces, unit_steps, strand_pieces, parallel_runs, stacked_runs, free_ends, stretched, column_shift, widened_columns, touching, Panel, band_key_name, trim_columns, column_plain, drop_column

SCALE = 2
OS_REACH = 1            # steps an OS block reaches past a switch's points on each leg
DISCIPLINES = ("CTC", "ABS", "APB-2", "APB-3", "DTC", "Unknown")    # the values CATS reads (cats/layout/Discipline.java)
# a signal on a boundary edge: where it sits in its cell, on the right-hand side of a move entering by that edge
SIG_LOCATION = {"RIGHT": "UPRIGHT", "LEFT": "LOWLEFT", "TOP": "LEFTUP", "BOTTOM": "RIGHTLOW"}
SIG_PANTYPES = ("LAMP1", "LAMP2", "LAMP3", "SEM1", "SEM2", "SEM3")
IOSPEC_KEYS = {"DECADDR", "JMRIPREFIX", "USER_NAME", "JMRIDEVICE", "EXIT_CMD", "DELAY"}
ROUTE_TAGS = ("SELECTEDREPORT", "NOTSELECTEDREPORT", "ROUTECOMMAND")


HELIX_BLOCKS = ("one", "apart")


def panel(bands, scale=SCALE, bindings=None, max_cols=None, helix_blocks="one"):
    """A Panel from [(title, band, options)], bands stacked top to bottom, bound to the layout by `bindings`.
    `max_cols`: take out columns of plain level track until no track reaches past that column (trim_columns).
    `helix_blocks`: a helix track drawn on two bands is one block ("one"), or a block on each band ("apart": the
    logical join between them is a block boundary, as where the layout parts its detection at the helix)."""
    if helix_blocks not in HELIX_BLOCKS:
        raise SchematicError(f"helix_blocks is one of {', '.join(HELIX_BLOCKS)}, not {helix_blocks!r}")
    if not isinstance(scale, int) or isinstance(scale, bool) or not (scale == 1 or (scale >= 2 and scale % 2 == 0)):
        raise SchematicError(f"the CATS scale is 1 or an even number of cells per grid unit, not {scale!r}")
    compact = scale == 1
    at = lambda v: math.floor(scale * v + 0.5)          # one rounding everywhere: half up
    bindings = check_bindings(bindings or {})
    sw_bind = switch_bindings(bands, bindings["switches"])
    P = Panel()
    if compact:
        P.pending = []
    chains, turn_bounds = {}, {}     # (band, strand) -> its steps and their blocks; (band, turnback) -> its boundary
    top = 1 if compact else MARGIN + 1
    left_col = 2 if compact else MARGIN + 1     # a compact panel keeps one empty column on the left
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
        for sid, line in drawn.items():         # track and switches must land on whole cells (turnback runs may not)
            if sid in strands and any(scale * v != at(v) for p in line for v in p):
                raise SchematicError(f"{title}: track {strands[sid]['name'] or sid} has a point between cells at "
                                     f"{scale} cell(s) per grid unit (a half grid unit); draw it at 2")
        for n, d in nodes.items():
            if d["kind"] == "dx" and scale * x[n] != at(x[n]):
                raise SchematicError(f"{title}: double crossover {d.get('label') or n} is centred between cells at "
                                     f"{scale} cell(s) per grid unit; draw it at 2")
        # the drawing's left and top extent: floor, since a turnback's half unit beyond its tracks' ends fills
        # the cell before them (strand points themselves are whole cells, checked above)
        x0 = min(p[0] for v in drawn.values() for p in v)
        r0 = min(p[1] for v in drawn.values() for p in v)
        ox = left_col - math.floor(scale * x0)
        oy = top + 2 - math.floor(scale * r0)
        tag = f"b{bi}:"

        # the band title and which way is east
        left, right = opts.get("left", "West"), opts.get("right", "East")
        tx = left_col if compact else MARGIN
        P.label([((tx, top), "LOWLEFT"), ((tx, top - 1), "LOWLEFT")],
                f"{band_key_name(title).upper()}   {left.upper()} <-   -> {right.upper()}", "FONT_TITLE", rank=0)

        # OS blocks: a switch's own, or shared by switches of one number joined by a track
        def os_key(n):
            return ("os", tag + n)
        # a double crossover bound with `corners`: a block per corner (keyed by its band leg) and one for the
        # middle of its X, in place of its one OS block
        corners = {n: sw_bind[(bi, n)]["corners"] for n in nodes if sw_bind.get((bi, n), {}).get("corners")}
        for n in corners:
            if nodes[n]["kind"] != "dx":
                raise SchematicError(f"switch {nodes[n].get('label') or n}: corners are for a double crossover")

        def okey(n, port):
            """The block key a strand's end at node n, leg `port`, takes inside the switch's OS reach."""
            return ("corner", tag + n, port) if n in corners else os_key(n)
        for n, d in nodes.items():
            if n in corners:
                for port in "ABCD":
                    P.blocks[okey(n, port)] = None
                P.blocks[("xmid", tag + n)] = None
            elif d["kind"] in ("switch", "dx"):
                P.blocks[os_key(n)] = None
        for sid, s in strands.items():
            u, v = s["src"][0], s["dst"][0]
            du, dv = nodes[u], nodes[v]
            if u in corners or v in corners:
                continue
            if du["kind"] in ("switch", "dx") and dv["kind"] in ("switch", "dx") and du.get("label") and \
                    du.get("label") == dv.get("label"):
                bu, bv = (sw_bind.get((bi, n), {}).get("block") for n in (u, v))
                if not (bu and bv and bu != bv):        # bound to two blocks: they stay apart
                    P.union(os_key(u), os_key(v))

        # rows opened for double crossovers with corners: their X must be two cells deep, so that each corner's
        # diagonal piece parts from the middle on an edge of its own (CATS parts a block neither at points nor
        # where two blocks meet one side of a crossing); the drawn rows below move down, and slopes across an
        # opened row take a jog step there
        opened = {}
        for n in corners:
            (iu, _), (il, _) = dx_tracks(nodes, n)
            r1, r2 = sorted((band["R"]["srow"][iu], band["R"]["srow"][il]))
            if at(r2 - r1) < 2:
                opened[r1] = max(opened.get(r1, 0), 2 - at(r2 - r1))
        rshift = lambda gy: sum(k for r, k in opened.items() if gy > r)
        open_rows = frozenset(oy + at(r) + rshift(r) + i for r, k in opened.items() for i in range(1, k + 1))
        for r in opened:
            P.log.append(f"{title}: {sum(opened.values())} row(s) opened below grid row {r:g} for a double "
                         "crossover's corner blocks")

        # how far each switch's OS reaches along its tracks: in steps, or on a compact panel in cells (half a
        # 45 degree step), so that a one-unit slope between two switches can still part their OS blocks
        reach = {}
        for n, d in nodes.items():
            if d["kind"] == "switch":
                reach[n] = OS_REACH
            elif d["kind"] == "dx":
                (iu, _), (il, _) = dx_tracks(nodes, n)
                r1, r2 = sorted((band["R"]["srow"][iu], band["R"]["srow"][il]))
                depth = at(r2 - r1) + rshift(r2) - rshift(r1)
                reach[n] = (depth + 1) // 2 + OS_REACH     # the X, then past its points

        # a compact panel widens the grid columns of level tracks too short to part the OS blocks at their ends
        widen = widened_columns(title, band, drawn, reach, P.log) if compact else {}
        extra = column_shift(widen)
        pt = lambda p: (ox + at(p[0]) + extra(p[0]), oy + at(p[1]) + rshift(p[1]))

        # strands
        turn_of, info = {}, {}
        for sid, s in strands.items():
            for t in (s["src"][0], s["dst"][0]):
                if nodes[t]["kind"].startswith("turn"):
                    turn_of.setdefault(t, []).append(sid)
        for sid, s in sorted(strands.items()):
            pts = stretched([pt(p) for p in drawn[sid]], free_ends(band, sid))
            if pts is None:         # widened_columns keeps such columns narrow; a guard, not a fallback
                raise SchematicError(f"{title}: track {s['name'] or sid} crosses a widened column with no place "
                                     "for its extra cell")
            steps = unit_steps(pts, open_rows)
            if not steps:
                raise SchematicError(f"{title}: track {s['name'] or sid} is drawn as a single point")
            pieces = strand_pieces(steps)
            u, v = s["src"][0], s["dst"][0]
            track_key = ("track", tag + sid)
            P.blocks.setdefault(track_key, None)
            owner = [track_key] * len(pieces)
            ru = sum(1 for pc in pieces if pc[3] <= reach.get(u, 0))           # whole steps
            rv = sum(1 for pc in pieces if len(steps) - pc[2] <= reach.get(v, 0))
            if compact and ru + rv > len(pieces):
                # too short for whole steps: a compact panel's OS ends one cell past the points instead (mid-slope),
                # first at the end where that parts the blocks, so most boundaries stay on level edges
                for side in ("u", "v"):
                    if ru + rv > len(pieces):
                        if side == "u":
                            ru = min(ru, reach.get(u, 0))
                        else:
                            rv = min(rv, reach.get(v, 0))
            ku, kv = okey(u, s["src"][1]), okey(v, s["dst"][1])
            for i in range(min(ru, len(pieces))):
                owner[i] = ku
            for i in range(min(rv, len(pieces))):
                j = len(pieces) - 1 - i
                if owner[j] != track_key and owner[j] != kv:
                    P.union(owner[j], kv)
                owner[j] = kv
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
            mine = (lambda k: k[0] == "corner" and k[1] == tag + n) if n in corners else \
                (lambda k: P.find(k) == P.find(os_key(n)))
            for yy in (y1, y2):
                for xx in range(a - OS_REACH, b + OS_REACH):
                    here = P.cells.get((xx, yy), {}).get("HORIZONTAL")
                    if here is None or not mine(here):
                        raise SchematicError(
                            f"double crossover {d.get('label') or n}: its through tracks must run level for "
                            f"{((depth + 1) // 2 + OS_REACH) / scale:g} grid units each side of it "
                            f"(rows {r1} and {r2}, column {x[n]:g})")
            if n in corners:
                # each point's corner is the leg whose through track leaves it: the X's first piece from a point
                # is that corner's, the pieces at the crossing are the middle's
                corner_at = {(xp, yy): P.cells[(xp - 1 if xp == a else xp, yy)]["HORIZONTAL"]
                             for xp in (a, b) for yy in (y1, y2)}
                if len({k[2] for k in corner_at.values()}) != 4:
                    raise SchematicError(f"double crossover {d.get('label') or n}: its four points are not on four "
                                         "legs")
            for p, q in (((a, y1), (b, y2)), ((a, y2), (b, y1))):
                pieces = [pc for st in unit_steps([p, q]) for pc in step_pieces(*st)]
                if pieces[0][0][0] != p[0]:
                    pieces = pieces[::-1]
                for i, (cell, track) in enumerate(pieces):
                    if n not in corners:
                        key = os_key(n)
                    elif i == 0:
                        key = corner_at[p]
                    elif i == len(pieces) - 1:
                        key = corner_at[q]
                    else:
                        key = ("xmid", tag + n)
                    P.add(cell, track, key, f"double crossover {d.get('label')}")
            h = depth // 2      # the middle of the X: a column edge when the X is an even number of rows deep,
            if depth % 2 == 0:  # else the edge between two rows
                P.crossings |= {((a + h - 1, y1 + h), "RIGHT"), ((a + h, y1 + h), "LEFT")}
            else:
                P.crossings |= {((a + h, y1 + h), "BOTTOM"), ((a + h, y1 + h + 1), "TOP")}
            # each of its four points: route B along its through track, C into the X (one turnout moves all four)
            normal = sw_bind.get((bi, n), {}).get("normal", "B")
            for yy, xp, frog in ((y1, a, "LEFT"), (y2, a, "LEFT"), (y1, b, "RIGHT"), (y2, b, "RIGHT")):
                cell = (xp, yy) if frog == "LEFT" else (xp - 1, yy)
                ports = {ENDS[t][1] if ENDS[t][0] == frog else ENDS[t][0]: "B" if t == "HORIZONTAL" else "C"
                         for t in P.cells[cell] if frog in ENDS[t]}
                P.points[(cell, frog)] = dict(switch=d.get("label") or n, node=(bi, n), ports=ports,
                                              routes=sorted((far, port == normal) for far, port in ports.items()))
            if d.get("label"):
                cands = [((xc, y1 - 1), "LOWCENT"), ((xc - 1, y1 - 1), "LOWCENT"), ((xc, y2 + 1), "UPCENT")]
                if compact:                     # over the X, in its top through track's cells, else under it
                    cands = [((xx, y1), "UPCENT") for xx in range(a, b)] + \
                        [((xx, y2), "LOWCENT") for xx in range(a, b)] + cands
                P.label(cands, str(sw_bind.get((bi, n), {}).get("label") or d["label"]), rank=1)

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
            shown = str(sw_bind.get((bi, n), {}).get("label") or d.get("label") or "") + (d.get("facing") or "")
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
        named = []                              # (xa, xb, y, text, candidates)
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
                named.append((xa, xb, y, s["name"].upper(), cands))
            else:
                P.label(cands, s["name"].upper(), rank=3)
        groups = parallel_runs(named)           # a compact panel names a yard's parallel tracks in one column
        for group in stacked_runs([g[0] for g in groups if len(g) == 1]):    # and lone tracks above one another
            if len(group) > 1:                  # (say a main's two stretches) centred in one column
                lo, hi = max(g[0] for g in group), min(g[1] for g in group)
                mid = (lo + hi) // 2
                P.label([(c, ("UPCENT", "LOWCENT")) for c in sorted(range(lo, hi), key=lambda c: (abs(c - mid), c))],
                        [(g[2], g[3], g[4]) for g in group], rank=3)
            else:
                P.label(group[0][4], group[0][3], rank=3)
        for group in groups:
            if len(group) == 1:
                continue
            lo, hi = max(g[0] for g in group), min(g[1] for g in group)
            mid = (lo + hi) // 2
            P.label(sorted(range(lo, hi), key=lambda c: (abs(c - mid), c)),
                    [(g[2], g[3], g[4]) for g in group], rank=3)

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
    helix_groups = {id(g) for g in by_helix.values()}
    for group in list(by_link.values()) + list(by_helix.values()):
        if len(group) == 2 and group[0][0] != group[1][0]:
            (ca, cb) = group[0][4], group[1][4]
            P.shared[ca], P.shared[cb] = cb, ca
            ka, kb = group[0][5], group[1][5]
            apart = helix_blocks == "apart" and id(group) in helix_groups
            if ka[0] == kb[0] == "track" and not apart:     # one track drawn on two bands is one block
                P.union(ka, kb)
            joined |= {id(group[0]), id(group[1])}
    end_labels = []                             # (title, edge, cell, text, candidates, sub, level run)
    for e in ends:
        title, n, d, name, (cell, edge), _ = e
        if d.get("sub") not in ("link", "helix"):
            continue
        to = d.get("to") or ""
        text = (f"{d.get('label')}: TO {to.upper()}" if d.get("sub") == "link" else f"HELIX TO {to.upper()}").strip()
        if id(e) in joined and not compact:     # compact: no room, and the logical join is in the panel anyway
            text += " (JOINED)"
        beyond = (cell[0] + (1 if edge == "RIGHT" else -1), cell[1])
        below = (cell[0], cell[1] + 1)
        # text runs to the right: beside an east end, under a west end (beside it, it would run over the track)
        cands = [(beyond, "LEFTCENT"), (below, "UPLEFT")] if edge == "RIGHT" else [(below, "UPLEFT"), ((cell[0], cell[1] - 1), "LOWLEFT")]
        if compact:
            # beside the end on its own row, as the schematic does; else over (a connector) or under (a helix, whose
            # track name goes over) the level track at its end, never past it; then the rows beside
            back = -1 if edge == "RIGHT" else 1
            run = 1
            while "HORIZONTAL" in P.cells.get((cell[0] + back * run, cell[1]), {}):
                run += 1
            halves = ("UPLEFT", "LOWLEFT") if d.get("sub") == "link" else ("LOWLEFT", "UPLEFT")
            cands = [(beyond, "LEFTCENT" if edge == "RIGHT" else "RIGHTCENT")] + \
                [((cell[0] + back * k, cell[1]), loc) for loc in halves for k in range(run)] + \
                [((cell[0] + back * k, cell[1] + dy), loc) for k in range(8)
                 for dy, loc in ((1, "UPLEFT"), (-1, "LOWLEFT"))]
        end_labels.append((title, edge, cell, text, cands, d.get("sub"), run if compact else 0))
    # ends of parallel tracks on one side, in rows next to each other, are named alike: one column and spot
    groups = []
    for e in sorted(end_labels, key=lambda e: (e[0], e[1], e[2][0], e[5] or "", e[2][1])):
        g = groups[-1] if groups else None
        if compact and g and g[-1][:2] == e[:2] and g[-1][2][0] == e[2][0] and g[-1][5] == e[5] and \
                e[2][1] - g[-1][2][1] == 1:
            g.append(e)
        else:
            groups.append([e])
    for g in groups:
        if len(g) == 1:
            P.label(g[0][4], g[0][3], rank=2)
            continue
        (title, edge, (x, _), _, _, sub, _) = g[0]
        back, run = (-1 if edge == "RIGHT" else 1), min(e[6] for e in g)
        halves = ("UPLEFT", "LOWLEFT") if sub == "link" else ("LOWLEFT", "UPLEFT")
        cols = [(x - back, ("LEFTCENT" if edge == "RIGHT" else "RIGHTCENT",))] + \
            [(x + back * k, (loc,)) for loc in halves for k in range(run)]
        P.label(cols, [(e[2][1], e[3], e[4]) for e in g], rank=2)

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
        cornered = {sw_bind[node_of(k)]["corners"][k[2]] if k[0] == "corner" else
                    sw_bind[node_of(k)]["corners"].get("X") or f"OS {label_of(bands, ('os', k[1])) or 'X'} X"
                    for k in keys if k[0] in ("corner", "xmid")}
        if cornered:
            if len(cornered) > 1 or any(k[0] == "os" for k in keys):
                raise SchematicError(f"double crossover blocks {', '.join(sorted(cornered))} run into each other or "
                                     "into another switch's OS block: the tracks between them are too short")
            P.names[root] = cornered.pop()
            continue
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
    bind_masts(P, bands, bindings["masts"], chains, turn_bounds, compact, max_cols=max_cols)
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


SPILL_RANKS = (0, 2)    # band titles and end labels may run past the last track column; shown() counts them


def place_labels(P):
    """Place a compact panel's pending labels, lower rank first: each at its first candidate that stays inside the
    drawing and covers no track, signal or placed label; else at the candidate with the fewest such clashes,
    inside the drawing if any is (logged). Band titles and end labels may run past the last track column."""
    lines, signals = track_lines(P), signal_boxes(P)
    right = (max(c[0] for c in P.cells) + 1) * GRID_PX
    placed = []
    def clashes(box):
        return sum(crosses(box, ln) for ln in lines) + sum(overlaps(box, sb, 0) for sb in signals) + \
            sum(overlaps(box, pb) for pb in placed)

    queue = sorted(P.pending, key=lambda r: r[:2])
    while queue:
        rank, seq, cands, text, font = queue.pop(0)
        if isinstance(text, list):      # a group of names [(row, text, own candidates)]: one common column and
            for col in cands:           # spot, a column (over or under the track) or (column, spots)
                even = len({len(t) for _, t, _ in text}) == 1     # names of unequal length start in one line
                col, locs = (col, ("UPCENT", "LOWCENT") if even else ("UPLEFT", "LOWLEFT", "UPCENT", "LOWCENT")) \
                    if isinstance(col, int) else col
                for loc in locs:
                    spots = [((col, y), text_box((col, y), loc, t, font)) for y, t, _ in text]
                    if all(c not in P.labels for c, _ in spots) and \
                            all(b[0] >= GRID_PX and (b[2] <= right or rank in SPILL_RANKS) for _, b in spots) and \
                            not any(clashes(b) for _, b in spots) and \
                            not any(overlaps(a[1], b[1]) for i, a in enumerate(spots) for b in spots[i + 1:]):
                        for (c, b), (_, t, _) in zip(spots, text):
                            P.labels[c] = (t, loc, font)
                            placed.append(b)
                        break
                else:
                    continue
                break
            else:                       # no common column: each on its own
                queue[:0] = [(rank, seq, own, t, font) for _, t, own in text]
            continue
        best = None
        spill = rank in SPILL_RANKS
        for cell, loc in cands:
            if cell in P.labels or cell[0] < 1 or cell[1] < 1:
                continue
            box = text_box(cell, loc, text, font)
            if box[0] < GRID_PX:
                continue
            past = box[2] > right and not spill      # past the last track column: only if nothing else will do
            clash = clashes(box)
            if best is None or (past, clash) < best[0]:
                best = ((past, clash), cell, loc, box)
            if (past, clash) == (False, 0):
                break
        if best is None:
            P.log.append(f"no room for label {text!r}")
            continue
        (past, clash), cell, loc, box = best
        if clash:
            P.log.append(f"label {text!r} at {cell} {loc} crosses {clash} track lines, signals or labels")
        if past:
            P.log.append(f"label {text!r} at {cell} {loc} runs past the last track column")
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
        e = fields(e, ("block", "normal", "routes", "label", "corners"), f"switch {key}")
        if "corners" in e:
            c = fields(e["corners"], ("A", "B", "C", "D", "X"), f"switch {key} corners")
            if set("ABCD") - set(c) or not all(isinstance(v, str) and v.strip() for v in c.values()) or \
                    len(set(c.values())) != len(c):
                raise SchematicError(f"switch {key}: corners names a block for each leg A to D (and X, the middle of "
                                     "the X, if wanted), all different")
            if "block" in e:
                raise SchematicError(f"switch {key}: give corners or block, not both")
            e["corners"] = c
        if "label" in e and (not isinstance(e["label"], str) or not e["label"].strip()):
            raise SchematicError(f"switch {key}: label is the text shown at its points, a non-empty string")
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
        e = fields(e, ("name", "template", "pantype", "orient", "location"), f"mast {key}")
        if e.get("pantype") is not None and e["pantype"] not in SIG_PANTYPES:
            raise SchematicError(f"mast {key}: pantype is one of {', '.join(SIG_PANTYPES)}")
        if e.get("orient") is not None and e["orient"] not in OPPOSITE:
            raise SchematicError(f"mast {key}: orient is one of {', '.join(OPPOSITE)}")
        if e.get("location") is not None and e["location"] not in LOC_XY:
            raise SchematicError(f"mast {key}: location is one of {', '.join(LOC_XY)}")
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


def bind_masts(P, bands, masts, chains, turn_bounds, compact=False, gantry=True, max_cols=None):
    """Each bound mast on the block boundary nearest where it stands, on the edge of the block it protects. On a
    compact panel the gaps of a control point's masts are first slid along their tracks into one column per
    direction and out of switch cells (shift_gaps), and each mast is drawn at its clearest spot (place_mast).
    `max_cols`: columns are taken out (trim_columns) once the gaps are set and before the spots are chosen."""
    known = {sg["mast"]: sg for _, _, o in bands for sg in o.get("signals") or ()}
    unknown = set(masts) - set(known)
    if unknown:
        raise SchematicError(f"bindings name mast {', '.join(sorted(unknown))}, which no band's signals have")
    plans = []
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
        if strand["src"][0] == start:
            rev, near, far = False, strand["src"][0], strand["dst"][0]
        elif strand["dst"][0] == start:
            rev, near, far = True, strand["dst"][0], strand["src"][0]
        else:
            raise SchematicError(f"mast {name}: cannot tell which end of track {strand['name'] or k} it faces")
        n = len(chains[(bi, k)]["steps"])
        pl = dict(name=name, e=e, sg=sg, bi=bi, k=k, rev=rev, near=near, far=far,
                  pos=n * at / piece_cm if piece_cm else 0.0, label=strand["name"] or k)
        pl["gap"] = mast_gap(P, chains, turn_bounds, pl)
        plans.append(pl)
    gantries = shift_gaps(P, bands, chains, plans) if compact and gantry else []
    spots = {}                                   # mast -> (cell, edge), followed through any column taken out
    for pl in plans:
        spots[pl["name"]] = mast_gap(P, chains, turn_bounds, pl, pl["gap"]["pair"])["at"]
        pl["heads"] = max(1, min(3, int(pl["sg"].get("heads") or 1)))
    if max_cols is not None:                     # before the spots are chosen, so they see the final track
        trim_columns(P, max_cols, spots)
    lines = track_lines(P)
    gantry_of = {pl["name"]: g for g in gantries for pl in g}
    boxes = []
    for pl in sorted(plans, key=lambda p: p["name"]):
        e = pl["e"]
        cell, edge = spots[pl["name"]]
        if (cell, edge) in P.signals:
            raise SchematicError(f"masts {P.signals[(cell, edge)]['mast']} and {pl['name']} fall on one block boundary")
        heads = pl["heads"]
        loc, orient = SIG_LOCATION[edge], OPPOSITE[edge]
        if compact:
            g = gantry_of.get(pl["name"])
            if g and "look" not in pl:          # the gantry's first mast: one look for all, clear of masts placed
                look = gantry_look(P, g, spots, boxes, lines)
                for q in g:
                    q["look"] = look
            loc, orient = pl.get("look") or place_mast(P, cell, edge, heads, boxes, lines=lines)[1:]
        if e.get("orient"):                      # the bindings choose the way the lamps point (and maybe the spot)
            orient = e["orient"]
            loc = e.get("location") or (place_mast(P, cell, edge, heads, boxes, [orient], lines)[1] if compact
                                        else SIG_LOCATION[OPPOSITE[orient]])
        elif e.get("location"):
            loc = e["location"]
        boxes.append(frill_box(cell, loc, *mast_size(heads, orient)))
        P.signals[(cell, edge)] = dict(mast=pl["name"], name=e.get("name") or pl["name"], loc=loc,
                                       orient=orient, pantype=e.get("pantype") or f"LAMP{heads}",
                                       template=e.get("template"))


def gantry_look(P, g, spots, boxes, lines):
    """(SIGLOCATION, SIGORIENT) shared by a gantry's masts: the cheapest spot clear of track, points and masts
    already placed for every one of them, with their feet (bases) in one line; None when there is none."""
    costs = [spot_costs(P, *spots[pl["name"]], pl["heads"], boxes, lines) for pl in g]
    common = set(costs[0]).intersection(*costs[1:])
    fine = [k for k in common if all(not {"ink", "points", "mast"} & set(c[k][1]) for c in costs)]
    if not fine:
        return None

    def feet(k):
        xs = []
        for pl in g:
            bx = frill_box(spots[pl["name"]][0], k[0], *mast_size(pl["heads"], k[1]))
            xs.append(bx[0] if k[1] != "LEFT" else bx[2])
        return max(xs) - min(xs)
    look = min(fine, key=lambda k: (feet(k) > 2, sum(c[k][0] for c in costs), list(LOC_XY).index(k[0])))
    # the gantry's masts must not overlap one another either
    placed = [frill_box(spots[pl["name"]][0], look[0], *mast_size(pl["heads"], look[1])) for pl in g]
    if any(overlaps(a, b_, 1) for i, a in enumerate(placed) for b_ in placed[i + 1:]):
        return None
    return look


def mast_gap(P, chains, turn_bounds, pl, pair=None):
    """Where a mast stands: {"at": (cell, edge), "pair": (protected block, block behind), "b": the chain index of
    the gap (between pieces b - 1 and b) or None at a turnback}. Without `pair`, the boundary nearest the mast's
    place on its run; with it, the boundary between those two blocks (after shift_gaps moved it)."""
    c = chains[(pl["bi"], pl["k"])]
    n = len(c["steps"])
    seq = [(cell, track, a, b, P.find(o)) for (cell, track, a, b), o in zip(c["pieces"], c["owner"])]
    if pl["rev"]:
        seq = [(cell, track, n - b, n - a, o) for cell, track, a, b, o in reversed(seq)]
    cands = []
    for t, ((cell, track, _, end, o), (cell2, track2, _, _, o2)) in enumerate(zip(seq, seq[1:])):
        if o != o2:                              # on the nearer block's piece, at the edge toward the next one
            edge = next(e for e in ENDS[track] if neighbour(cell, e)[0] == cell2 and
                        neighbour(cell, e)[1] in ENDS[track2])
            cands.append((end, (cell, edge), (o, o2), len(seq) - 1 - t if pl["rev"] else t + 1))
    live = lambda b: b is not None and P.find(b[1]) != P.find(b[2])     # halves later merged: no boundary
    tb = turn_bounds.get((pl["bi"], pl["far"]), {}).get(pl["k"])
    if live(tb):                                 # past the far end: this half's side of the cut
        cands.append((n + 0.5, tb[0], (P.find(tb[1]), P.find(tb[2])), None))
    other = next((v for s_, v in turn_bounds.get((pl["bi"], pl["near"]), {}).items() if s_ != pl["k"]), None)
    if live(other):                              # behind the near end: the other half's side, the block it enters
        cands.append((-0.5, other[0], (P.find(other[1]), P.find(other[2])), None))
    if pair is not None:
        cands = [cd for cd in cands if cd[2] == pair]
        if not cands:
            raise SchematicError(f"mast {pl['name']}: its gap between blocks {P.names.get(pair[0], pair[0])} and "
                                 f"{P.names.get(pair[1], pair[1])} is no longer on its track {pl['label']}")
    if not cands:
        raise SchematicError(f"mast {pl['name']}: no block boundary on its track {pl['label']}")
    _, at, pr, b = min(cands, key=lambda c_: (abs(c_[0] - pl["pos"]), c_[0]))
    return {"at": at, "pair": pr, "b": b}


# Mast spots on a compact panel. What CATS draws (cats/gui/frills): a LightFrill is `heads` filled 8 pixel ovals in
# a row toward SIGORIENT and its base (a filled 8 pixel triangle pointing at the heads) behind them, in a box of
# (heads + 1) * 8 by 8 pixels set at its SIGLOCATION in its cell (FrillLoc), always in the cell of the block it
# protects. Track is a 2 pixel line between edge midpoints (RailFrill); at switch points the route not lined stops
# PointGap = 5 pixels short of the points edge (PtsEdge), which is all the dispatcher sees of the points; and a click
# anywhere in a switch's cell that no signal box takes throws it (GridTile.startMouse, Section.sectionMouse), while
# a click in a signal box sets a route there. So a mast reads best (references/cats-signals.md): lamps pointing the
# way the move goes across the screen, on its right-hand side, near its gap, clear of every track line by a few
# pixels, off the points' gap, and out of switch cells altogether.
INK_CLEAR = (3, 5, 7.5)         # pixels from a lamp's middle to a track line's: through it, on its rim, too close
POINT_ZONE = (9, 3, 6)          # pixels into the points cell, out past its edge, and along it: the points' gap
SPOT_COST = {"ink": 10, "mast": 10, "points": 5, "other": 15, "graze": 4, "side": 2, "turned": 2, "gap": 2, "tilted": 1, "close": 1}
SPOT_PER_PX = {"far": 1 / 15, "spill": 1 / 20, "back": 1 / 2}
GANTRY_SHIFT = 3                # cells a gap may slide along its track to line masts up
GANTRY_SPAN = 1                 # masts of one control point and direction this many columns apart form a gantry


def mast_size(heads, orient):
    long_ = heads * SIG_PX + SIG_PX
    return (SIG_PX, long_) if orient in ("TOP", "BOTTOM") else (long_, SIG_PX)


def move_of(P, cell, edge):
    """(dx, dy): the way a move entering `cell` across `edge` runs in it, edge middle to its track's other end."""
    h = GRID_PX / 2
    mid = {"LEFT": (0, h), "RIGHT": (GRID_PX, h), "TOP": (h, 0), "BOTTOM": (h, GRID_PX)}
    t = next(t for t in P.cells[cell] if edge in ENDS[t])
    far = ENDS[t][1] if ENDS[t][0] == edge else ENDS[t][0]
    return mid[far][0] - mid[edge][0], mid[far][1] - mid[edge][1]


def lamp_way(move):
    dx, dy = move
    return ("RIGHT" if dx > 0 else "LEFT") if dx else ("BOTTOM" if dy > 0 else "TOP")


def box_gap(box, line):
    """Pixels from the box to the nearest point of the line segment (0 when the line enters it)."""
    ax, ay, bx, by = line
    best = None
    for i in range(33):
        f = i / 32
        px, py = ax + (bx - ax) * f, ay + (by - ay) * f
        dx = max(box[0] - px, 0, px - box[2])
        dy = max(box[1] - py, 0, py - box[3])
        d = math.hypot(dx, dy)
        best = d if best is None else min(best, d)
    return best


def points_zones(P, cell):
    """Pixel boxes of the points gaps in and next to `cell`."""
    deep, out, half = POINT_ZONE
    zones = []
    for (pc, pe) in P.points:
        if abs(pc[0] - cell[0]) > 1 or abs(pc[1] - cell[1]) > 1:
            continue
        X, Y, g = pc[0] * GRID_PX, pc[1] * GRID_PX, GRID_PX
        zones.append({"LEFT": (X - out, Y + g / 2 - half, X + deep, Y + g / 2 + half),
                      "RIGHT": (X + g - deep, Y + g / 2 - half, X + g + out, Y + g / 2 + half),
                      "TOP": (X + g / 2 - half, Y - out, X + g / 2 + half, Y + deep),
                      "BOTTOM": (X + g / 2 - half, Y + g - deep, X + g / 2 + half, Y + g + out)}[pe])
    return zones


def spot_costs(P, cell, edge, heads, boxes=(), lines=None, orients=None):
    """{(SIGLOCATION, SIGORIENT): (cost, [reasons])} for a mast on `edge` of `cell`, every spot and the ways its
    lamps may point (`orients`, else the move's way across the screen and, on a slope, up or down the way it
    climbs). The cheapest reads best; the reasons are SPOT_COST's keys. `lines`: the panel's track_lines, when
    the caller has them (they are worked out here otherwise); only those near the cell count."""
    lines = [ln for ln in (track_lines(P) if lines is None else lines)
             if abs(ln[0] - cell[0] * GRID_PX) <= 2 * GRID_PX and abs(ln[1] - cell[1] * GRID_PX) <= 2 * GRID_PX]
    move = move_of(P, cell, edge)
    way = lamp_way(move)
    ways = orients or ([way, lamp_way((0, move[1]))] if move[0] and move[1] else [way])
    h = GRID_PX / 2
    ex, ey = {"LEFT": (0, h), "RIGHT": (GRID_PX, h), "TOP": (h, 0), "BOTTOM": (h, GRID_PX)}[edge]
    ex, ey = ex + cell[0] * GRID_PX, ey + cell[1] * GRID_PX
    zones = points_zones(P, cell)
    t = next(t for t in P.cells[cell] if edge in ENDS[t])
    own = next(ln for ln in track_lines(P, {cell: {t: None}}))
    lines = lines if own in lines else lines + [own]
    X0, Y0 = cell[0] * GRID_PX, cell[1] * GRID_PX
    out = {}
    for orient in ways:
        size = mast_size(heads, orient)
        for loc in LOC_XY:
            box = frill_box(cell, loc, *size)
            why = []
            # the lamps and the base are 8 pixel discs (near enough): a line through one's middle, over its rim, or
            # within a few pixels of it
            units = [(box[0] + SIG_PX * (i + 0.5), box[1] + SIG_PX / 2) if size[0] > size[1] else
                     (box[0] + SIG_PX / 2, box[1] + SIG_PX * (i + 0.5)) for i in range(heads + 1)]
            gaps = [min(box_gap((ux, uy, ux, uy), ln) for ux, uy in units) for ln in lines]
            why += ["ink"] * sum(g < INK_CLEAR[0] for g in gaps)                   # a line through the lamps
            why += ["gap"] if gaps[lines.index(own)] < INK_CLEAR[0] else []          # ... and it hides its own gap
            why += ["graze"] if any(INK_CLEAR[0] <= g < INK_CLEAR[1] for g in gaps) else []
            why += ["close"] if any(INK_CLEAR[1] <= g < INK_CLEAR[2] for g in gaps) else []
            why += ["points"] if any(overlaps(box, z, 0) for z in zones) else []
            why += ["mast"] * sum(overlaps(box, b, 1) for b in boxes)
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            if ((cx - ex) * -move[1] + (cy - ey) * move[0]) / math.hypot(*move) <= 2:
                why.append("side")                              # not on the move's right-hand side
            if orient != way:                   # up or down on a slope reads nearly as well as along it
                why.append("turned" if not (move[0] and move[1]) else "tilted")
            cost = sum(SPOT_COST[w] for w in why)
            bx, by = {"RIGHT": (box[0] + SIG_PX / 2, cy), "LEFT": (box[2] - SIG_PX / 2, cy),
                      "BOTTOM": (cx, box[1] + SIG_PX / 2), "TOP": (cx, box[3] - SIG_PX / 2)}[orient]
            cost += math.hypot(bx - ex, by - ey) * SPOT_PER_PX["far"]          # the mast's foot near its gap
            foot = [box_gap((bx, by, bx, by), ln) for ln in lines]
            if lines and min(foot) < foot[lines.index(own)] - 0.5:
                why.append("other")                                           # it would read as another track's
                cost += SPOT_COST["other"]
            back = {"LEFT": X0 - box[0], "RIGHT": box[2] - X0 - GRID_PX, "TOP": Y0 - box[1],
                    "BOTTOM": box[3] - Y0 - GRID_PX}[edge]
            cost += max(0, back) * SPOT_PER_PX["back"]                        # over the gap into the block behind
            spill = max(0, X0 - box[0]) + max(0, box[2] - X0 - GRID_PX) + max(0, Y0 - box[1]) + \
                max(0, box[3] - Y0 - GRID_PX)
            cost += spill * SPOT_PER_PX["spill"]
            out[(loc, orient)] = (round(cost, 3), why)
    return out


def place_mast(P, cell, edge, heads, boxes=(), orients=None, lines=None):
    """(cost, SIGLOCATION, SIGORIENT): the clearest spot for a compact panel's mast (spot_costs)."""
    costs = spot_costs(P, cell, edge, heads, boxes, lines, orients)
    (loc, orient), (cost, _) = min(costs.items(), key=lambda kv: (kv[1][0], list(LOC_XY).index(kv[0][0])))
    return cost, loc, orient


def shift_gaps(P, bands, chains, plans):
    """Slide masts' gaps along their tracks (each between the same two blocks, so a mast protects the same block)
    so that the masts of one control point and direction a column apart stand in one column, like signals on a
    gantry, and none stands in a switch's cell, where it would take clicks meant for the points. A gap moves at
    most GANTRY_SHIFT cells, never onto points or a crossing, and each block keeps at least one cell of the track.
    Returns the gantries: lists of the plans that share a column."""
    cp_of = {}
    for bi, (_, _, o) in enumerate(bands):
        for name, cp in (o.get("control_points") or {}).items():
            for s in cp.get("switches", ()):
                cp_of[(bi, str(s))] = name

    def piece(pl, b):
        return chains[(pl["bi"], pl["k"])]["pieces"][b if pl["rev"] else b - 1]

    def options(pl):
        """{b': (column, in a switch cell, cells moved)} for the gap of `pl`, its own place included."""
        c, b = chains[(pl["bi"], pl["k"])], pl["gap"]["b"]
        roots = [P.find(o) for o in c["owner"]]
        A, B = roots[b - 1], roots[b]
        out = {}
        for nb in range(max(1, b - GANTRY_SHIFT), min(len(roots) - 1, b + GANTRY_SHIFT) + 1):
            if nb < b and any(r != A for r in roots[nb - 1:b]):
                continue
            if nb > b and any(r != B for r in roots[b:nb + 1]):
                continue
            (c1, t1, _, _), (c2, t2, _, _) = c["pieces"][nb - 1], c["pieces"][nb]
            e1 = next((e for e in ENDS[t1] if neighbour(c1, e)[0] == c2), None)
            if e1 is None:
                continue
            e2 = OPPOSITE[e1]
            if any((cc, ee) in P.points or (cc, ee) in P.crossings or
                   sum(ee in ENDS[t] for t in P.cells[cc]) != 1 for cc, ee in ((c1, e1), (c2, e2))):
                continue
            cell = piece(pl, nb)[0]
            out[nb] = (cell[0], len(P.cells[cell]) > 1, abs(nb - b))
        return out

    groups = defaultdict(list)
    for pl in plans:
        if pl["gap"]["b"] is None:
            continue
        sg = pl["sg"]
        toward = str(sg.get("toward") or "")
        where = cp_of.get((pl["bi"], toward), "switch " + toward) if toward else "mast " + pl["name"]   # else alone
        groups[(pl["bi"], where, sg.get("dir"))].append(pl)
    gantries = []
    for key in sorted(groups, key=str):
        members = sorted(groups[key], key=lambda p: (piece(p, p["gap"]["b"])[0][0], p["name"]))
        clusters, run = [], [members[0]]
        for a, b_ in zip(members, members[1:]):
            if piece(b_, b_["gap"]["b"])[0][0] - piece(a, a["gap"]["b"])[0][0] > GANTRY_SPAN:
                clusters.append(run)
                run = []
            run.append(b_)
        clusters.append(run)
        for cl in clusters:
            # masts sharing a gap move together, so a gap shared with a mast of another cluster stays put
            shared = lambda pl: [q for q in plans if q is not pl and q["k"] == pl["k"] and q["bi"] == pl["bi"]
                                 and q["gap"]["b"] == pl["gap"]["b"]]
            opts = {}
            for pl in list(cl):
                own, b = options(pl), pl["gap"]["b"]
                if b not in own:                 # its own gap fails the checks: leave the mast where it stands
                    P.log.append(f"mast {pl['name']}: its gap stays where it is (no room to move it)")
                    cl.remove(pl)
                    continue
                opts[pl["name"]] = {b: own[b]} if any(q not in cl for q in shared(pl)) else own
            if not cl:
                continue
            best = None
            for col in sorted({o[0] for os_ in opts.values() for o in os_.values()}):
                pick, score = {}, [0, 0, 0]
                for pl in cl:
                    os_ = opts[pl["name"]]
                    here = {nb: o for nb, o in os_.items() if o[0] == col}
                    if not here:
                        score[0] += 1
                        here = os_
                    nb = min(here, key=lambda nb: (here[nb][1], here[nb][2], nb))
                    pick[pl["name"]] = nb
                    score[1] += here[nb][1]
                    score[2] += here[nb][2]
                if best is None or tuple(score) < best[0]:
                    best = (tuple(score), col, pick)
            (unaligned, _, _), col, pick = best
            for pl in cl:
                move_gap(P, chains, pl, pick[pl["name"]], plans)
            if len(cl) > 1:
                aligned = [pl for pl in cl if piece(pl, pl["gap"]["b"])[0][0] == col]
                if len(aligned) > 1:
                    gantries.append(aligned)
                if unaligned:
                    P.log.append(f"masts {', '.join(pl['name'] for pl in cl if pl not in aligned)} could not join "
                                 f"the gantry of {', '.join(pl['name'] for pl in aligned)} in column {col}")
    return gantries


def move_gap(P, chains, pl, nb, plans):
    """Move the gap of `pl` (and of any mast sharing it) to chain index nb, giving the cells between to the block
    on the other side."""
    c, b = chains[(pl["bi"], pl["k"])], pl["gap"]["b"]
    if nb == b:
        return
    lo, hi, key = (nb, b, c["owner"][b]) if nb < b else (b, nb, c["owner"][b - 1])
    for j in range(lo, hi):
        cell, track, _, _ = c["pieces"][j]
        c["owner"][j] = key
        P.cells[cell][track] = key
    for q in plans:
        if q["bi"] == pl["bi"] and q["k"] == pl["k"] and q["gap"]["b"] == b:
            q["gap"] = dict(q["gap"], b=nb)
    P.log.append(f"mast {pl['name']}: its gap moved {abs(nb - b)} cell(s) along track {pl['label']}")


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
    """The SIGNALTEMPLATE, JMRINAME and COLORDEFINITION elements of an existing CATS panel, to copy into a generated
    one: the physical signal templates its masts name, the JMRI device prefixes its IOSPECs use, and its colours.
    The colours matter for blocks with no occupancy sensors: CATS paints such dark territory in the DARK colour,
    grey unless the panel says otherwise (cats/layout/items/Track.java setBlock, gui/PaletteFactory.java)."""
    try:
        src = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        raise SchematicError(f"{path}: cannot read it as a CATS panel ({e})") from None
    if src.tag != "DOCUMENT":
        raise SchematicError(f"{path}: not a CATS panel (its root is {src.tag})")
    return [el for el in src if el.tag in ("SIGNALTEMPLATE", "JMRINAME", "COLORDEFINITION")]


def set_io(parent, tag, io):
    io = dict(io)
    ET.SubElement(ET.SubElement(parent, tag), "IOSPEC", **{k: v for k, v in io.items() if k != "command"}).text = \
        io["command"]


def to_xml(P, discipline="CTC", header=(), window=None):
    """The panel as a CATS Designer document (an ElementTree root). `header`: SIGNALTEMPLATE and JMRINAME
    elements to copy in (header_from). `window`: (width, height) in pixels of the window CATS opens the panel in,
    placed at the screen's top left; CATS has no zoom, so a window smaller than the panel crops it."""
    cols, rows = P.size()
    root = ET.Element("DOCUMENT", VERSION="3.1")
    if window:
        w, h = window
        if w < 1 or h < 1:
            raise SchematicError(f"window {w}x{h}: both sides must be at least 1 pixel")
        root.set("WIDTH", str(int(w)))
        root.set("HEIGHT", str(int(h)))
        root.set("X", "0")
        root.set("Y", "0")
    for key, name, color, size, style in HEADER_FONTS:
        ET.SubElement(root, "FONTDEFINITION", FONTKEY=key, FONTNAME=name, FONTCOLOR=color, FONTSIZE=size,
                      FONTSTYLE=style)
    for el in header:
        if el.tag == "COLORDEFINITION":
            root.append(copy.deepcopy(el))
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


def write(P, out, discipline="CTC", header=(), window=None):
    root = to_xml(P, discipline, header, window)
    text = "<?xml version='1.0' encoding='UTF-8'?>\n" + ET.tostring(root, encoding="unicode") + "\n"
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    return text


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
