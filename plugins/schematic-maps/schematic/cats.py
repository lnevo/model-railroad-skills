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
from .cats_px import GRID_PX, TEXT_PX, SIG_PX, LOC_XY, frill_box, text_box, track_lines, signal_boxes, crosses, overlaps
from .cats_labels import SPILL_RANKS, place_labels
from .cats_fit import shown, check_fit, parse_size, parse_fit, parse_window, summary
from .cats_bind import DISCIPLINES, SIG_PANTYPES, IOSPEC_KEYS, ROUTE_TAGS, node_of, check_io, check_bindings, switch_bindings, bind_blocks, bind_routes, number_order, label_of
from .cats_masts import SIG_LOCATION, bind_masts, gantry_look, mast_gap, INK_CLEAR, POINT_ZONE, SPOT_COST, SPOT_PER_PX, GANTRY_SHIFT, GANTRY_SPAN, mast_size, move_of, lamp_way, box_gap, points_zones, spot_costs, place_mast, shift_gaps, move_gap
from .cats_xml import boundaries, dangling, lone_blocks, HEADER_FONTS, header_from, set_io, to_xml, write

SCALE = 2
OS_REACH = 1            # steps an OS block reaches past a switch's points on each leg


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

