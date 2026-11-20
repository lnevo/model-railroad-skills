"""Masts on a CATS panel: binding them to block boundaries, sliding gaps into gantries, and choosing each one's clearest spot."""

from collections import defaultdict
import math

from .cats_grid import ENDS, OPPOSITE, neighbour, trim_columns
from .cats_px import GRID_PX, LOC_XY, SIG_PX, frill_box, overlaps, track_lines
from .core import SchematicError
from .draw import mast_piece

__all__ = [
    "SIG_LOCATION", "bind_masts", "gantry_look", "mast_gap", "INK_CLEAR", "POINT_ZONE", "SPOT_COST",
    "SPOT_PER_PX", "GANTRY_SHIFT", "GANTRY_SPAN", "mast_size", "move_of", "lamp_way", "box_gap",
    "points_zones", "spot_costs", "place_mast", "shift_gaps", "move_gap"
]


# a signal on a boundary edge: where it sits in its cell, on the right-hand side of a move entering by that edge
SIG_LOCATION = {"RIGHT": "UPRIGHT", "LEFT": "LOWLEFT", "TOP": "LEFTUP", "BOTTOM": "RIGHTLOW"}


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
                if sg["mast"] == name for spot in [mast_piece(sg, band["strands"], band["nodes"])]
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
