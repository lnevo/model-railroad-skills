"""Mileposts: small numbered ticks along the main route, counted in scale miles from one switch.

Layer 1 (facts the plan does not hold):
    milepost_origin   {"switch": "1", "milepost": 0.0}   the switch where the count starts, and its number
    scale_ratio       87.1                               the model scale (HO); one model inch is that many real inches
    helix_length_in   690 or {"Track name": 690, ...}    track length through a helix, to carry the count between levels
    milepost_route    [[a, b], [a, b, "direct"], ...]    the way the count runs, like main_route (default: main_route)
Layer 3 (the look): `mileposts` true, or {"step": 0.25}. Off by default; with it off nothing is computed or drawn.

The count runs along the route, in its order, so a milepost grows the way the route is listed (timetable east).
Each pair a, b in the route is the shortest way over main track between them, taking a cross-over between the two halves of one numbered switch (every straight track joining the
two for "direct"); the count at b is the count at a plus that way's length. A pair whose far end is known and whose
near end is not counts backwards, which gives negative mileposts west of the origin. Where the same helix track
name ends on two levels, the far end continues from the near one by the helix length; a count that has no helix
length stops at the helix, so one level can be numbered first.

Length of a track is the measured one when layer 1 lists it (`track_lengths_in`, as capacity does), else the
plan's. Ticks sit where the count crosses a multiple of the step, along the drawn track in proportion to the
length counted on it, moved to the nearest level stretch, so on a stretched schematic they are not evenly spaced
on paper. Without a `step`, the smallest of 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5 or 10 miles that gives no band
more than 8 ticks (fewer on a short band: one per 4 grid columns) is used for the whole sheet.
"""
import heapq
import math

from . import capacity, edits
from .core import SchematicError

MILE_IN = 63360.0
STEPS = (0.05, 0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)
MAX_TICKS = 8
CELLS_PER_TICK = 4      # a band holds about one tick per this many grid columns, up to MAX_TICKS
MARGIN = 8.0            # px a tick keeps from the ends of its level stretch
EPS = 1e-9


def preference(opts):
    """The `mileposts` preference as a dict, or None when off. `true` or {} takes the defaults."""
    m = opts.get("mileposts")
    if m is None or m is False:
        return None
    m = {} if m is True else m
    if not isinstance(m, dict) or set(m) - {"step"}:
        raise SchematicError(f"mileposts must be true or {{\"step\": miles}}, not {m!r}")
    step = m.get("step")
    if step is not None and (isinstance(step, bool) or not isinstance(step, (int, float)) or step <= 0):
        raise SchematicError(f"mileposts step must be a number of miles above 0, not {step!r}")
    return m


def _first(optlist, key):
    return next((o[key] for o in optlist if o.get(key) is not None), None)


def _number(value, what, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (positive and value <= 0):
        raise SchematicError(f"{what} must be a number{' above 0' if positive else ''}, not {value!r}")
    return float(value)


def _key(measured, names):
    """The upper-case key of `track_lengths_in` that a track's names answer to (a joined name "A / B" answers to either)."""
    for name in names:
        for part in [name] + name.split(" / "):
            if part.upper() in measured:
                return part.upper()
    return None


def edge_inches(graph, measured):
    """{edge id: inches}: the measured length of a named track shared among the pieces that carry its name in
    proportion to the plan's lengths, else the plan's own."""
    plan = {e["id"]: e["cm"] / 2.54 for e in graph["edges"]}
    keys = {e["id"]: _key(measured, e["names"]) for e in graph["edges"]}
    total = {}
    for eid, k in keys.items():
        if k:
            total[k] = total.get(k, 0.0) + plan[eid]
    pieces = {}
    for k in keys.values():
        if k:
            pieces[k] = pieces.get(k, 0) + 1
    return {eid: (plan[eid] if not keys[eid] else measured[keys[eid]] * (plan[eid] / total[keys[eid]] if total[keys[eid]]
                                                                         else 1.0 / pieces[keys[eid]]))
            for eid in plan}


def edge_miles(inches, ratio):
    return inches * ratio / MILE_IN


def _adjacency(g):
    """{node: [(other node, edge)]} over the tracks a route may take: main track, and the cross-over between the two
    halves of one numbered switch."""
    N, adj = g["nodes"], {}
    for e in g["edges"]:
        if e["main"] or (N[e["u"]].get("label") and N[e["u"]].get("label") == N[e["v"]].get("label")):
            adj.setdefault(e["u"], []).append((e["v"], e))
            adj.setdefault(e["v"], []).append((e["u"], e))
    return adj


def _way(adj, a, b, direct):
    """[(edge, from node, to node)]: the tracks from a to b, or None. `direct` takes the one straight track that
    joins the two."""
    if direct:
        hits = [e for v, e in adj.get(a, ()) if v == b and (e["u"], e["v"]) in ((a, b), (b, a))]
        return [(min(hits, key=lambda e: (e["cm"], e["id"])), a, b)] if hits else None
    heap, seen, seq = [(0.0, 0, a, [])], set(), 0
    while heap:
        d, _, u, way = heapq.heappop(heap)
        if u == b:
            return way
        if u in seen:
            continue
        seen.add(u)
        for v, e in adj.get(u, ()):
            if v not in seen:
                seq += 1
                heapq.heappush(heap, (d + e["cm"], seq, v, way + [(e, u, v)]))
    return None


def _candidates(g, ref):
    return edits.end_nodes(g, ref) or [edits.by_label(g, ref)]


def _best_way(g, adj, a, b, direct):
    """(from node, to node, way) of the shortest way between any ends the two references answer to: a helix track
    named on two levels has an end at each, and the route means the one the other end of the pair can reach."""
    found = []
    for na in _candidates(g, a):
        for nb in _candidates(g, b):
            way = _way(adj, na, nb, direct)
            if way:
                found.append((sum(e["cm"] for e, _, _ in way), len(found), na, nb, way))
    if not found:
        raise SchematicError(f"milepost route {a} to {b} finds no main track between them")
    _, _, na, nb, way = min(found, key=lambda f: f[:2])
    return na, nb, way


def compute(graphs, optlist):
    """Per input graph (after its edits and main marks): {"edges": {edge id: (near node, count there, miles, u)},
    "origin": node or None}. `optlist` is each input's merged options."""
    origin = _first(optlist, "milepost_origin")
    if not isinstance(origin, dict) or "switch" not in origin:
        raise SchematicError('mileposts need layer 1 milepost_origin: {"switch": "1", "milepost": 0.0}')
    start_at = _number(origin.get("milepost", 0.0), "milepost_origin milepost")
    ratio = _first(optlist, "scale_ratio")
    if ratio is None:
        raise SchematicError("mileposts need layer 1 scale_ratio, a number above 0 (87.1 for HO)")
    ratio = _number(ratio, "scale_ratio", True)
    helix_in = _first(optlist, "helix_length_in")
    ends = {}                                   # helix track name (upper case) -> {(input, end node): its edge}
    for i, g in enumerate(graphs):
        for e in g["edges"]:
            for n in (e["u"], e["v"]):
                if g["nodes"][n].get("sub") == "helix" and e["names"]:
                    ends.setdefault(e["names"][0].upper(), {})[(i, n)] = e["id"]
    if isinstance(helix_in, dict):
        lengths = {k.upper(): _number(v, f"helix_length_in {k!r}", True) for k, v in helix_in.items()}
        for k in lengths:
            if k not in ends:
                raise SchematicError(f"helix_length_in names {k}, which is not a helix track (helix tracks: "
                                     f"{', '.join(sorted(ends)) or 'none'})")
    elif helix_in is not None:
        lengths = {k: _number(helix_in, "helix_length_in", True) for k in ends}
    else:
        lengths = {}
    tables = [{"edges": {}, "origin": None} for _ in graphs]
    adjs = [_adjacency(g) for g in graphs]
    inches = [edge_inches(g, capacity.measured(o)) for g, o in zip(graphs, optlist)]
    home = next(i for i, o in enumerate(optlist) if o.get("milepost_origin"))
    start = edits.by_label(graphs[home], str(origin["switch"]))
    known = {(home, start): start_at}
    tables[home]["origin"] = start
    routes = [(i, a, b, bool(how)) for i, o in enumerate(optlist)
              for a, b, *how in (o.get("milepost_route") or o.get("main_route") or ())]
    ways = {(i, a, b, d): _best_way(graphs[i], adjs[i], a, b, d) for i, a, b, d in routes}
    changed = True
    while changed:
        changed = False
        for i, a, b, direct in routes:
            na, nb, way = ways[(i, a, b, direct)]
            miles = [edge_miles(inches[i][e["id"]], ratio) for e, _, _ in way]
            if (i, na) in known:
                at = known[(i, na)]
                for (e, x, y), m in zip(way, miles):
                    tables[i]["edges"].setdefault(e["id"], (x, at, m, e["u"]))
                    at += m
                    if (i, y) not in known:
                        known[(i, y)], changed = at, True
            elif (i, nb) in known:
                at = known[(i, nb)]
                for (e, x, y), m in reversed(list(zip(way, miles))):
                    at -= m
                    tables[i]["edges"].setdefault(e["id"], (x, at, m, e["u"]))
                    if (i, x) not in known:
                        known[(i, x)], changed = at, True
        for name, group in ends.items():        # the same helix track on two levels: the far end carries on
            if name not in lengths:
                continue
            miles = edge_miles(lengths[name], ratio)
            for p, eid in sorted(group.items()):
                rec = tables[p[0]]["edges"].get(eid)
                if p not in known or rec is None:
                    continue
                sign = 1 if rec[0] != p[1] else -1     # the count runs into the helix here, or out of it
                for q in sorted(group):
                    if q != p and q not in known:
                        known[q], changed = known[p] + sign * miles, True
    return tables


def number(v):
    """A milepost as printed: no trailing zeros."""
    return f"{round(v, 4):g}"


def local_span(sid, s):
    """The share of its own (possibly half) edge a strand covers, as (at its start, at its end), 0 at the edge's `u`."""
    e0, _ = s["ends"]
    src = s["cut_from"] if s["src"][0].startswith("CUT:") else s["src"][0]     # a detail cut replaced the far end
    if sid.endswith(".0"):
        return (0.5, 0.0) if src.startswith("turn:") else (0.0, 0.5)
    if sid.endswith(".1"):
        return (1.0, 0.5) if not src.startswith("turn:") else (0.5, 1.0)
    return (0.0, 1.0) if src == e0 else (1.0, 0.0)


def span(band, sid):
    """(count at the strand's start, count at its end) or None when the strand is not on the counted route."""
    table = band.get("mp")
    s = band["strands"][sid]
    if not table:
        return None
    eid, half = s["edge"], None
    if eid not in table and eid[-1:] in "xy" and eid[:-1] in table:
        eid, half = eid[:-1], eid[-1]
    if eid not in table:
        return None
    near, at, miles, u = table[eid]
    f0, f1 = local_span(sid, s)
    if half == "x":
        f0, f1 = f0 / 2, f1 / 2
    elif half == "y":
        f0, f1 = 1 - f0 / 2, 1 - f1 / 2
    at_u = near == u
    count = (lambda f: at + miles * f) if at_u else (lambda f: at + miles * (1 - f))
    a, b = count(f0), count(f1)
    if "cut_cm" in s:                    # a detail sheet cut the track short: only the part kept is drawn
        whole = s["cm"] / 2 if sid.endswith((".0", ".1")) else s["cm"]
        share = min(1.0, s["cut_cm"] / whole) if whole else 1.0
        if s["dst"][0].startswith("CUT:"):
            b = a + (b - a) * share
        else:
            a = b + (a - b) * share
    return a, b


def ticks(band, sid, step):
    """[(share along the strand from its start, count)] where the count crosses a multiple of the step."""
    sp = span(band, sid)
    if sp is None or band["strands"][sid].get("hidden"):
        return []
    a, b = sp
    lo, hi = min(a, b), max(a, b)
    if hi - lo < EPS:
        return []
    st = band["strands"][sid]
    low_end = st["src"][0] if a <= b else st["dst"][0]
    high_end = st["dst"][0] if a <= b else st["src"][0]
    first = band.get("mp_origin") == low_end           # the count starts here: its own number is drawn too
    last = band.get("mp_origin") != high_end           # ...once, on the strand that leaves the origin
    out = []
    k = math.ceil(lo / step - EPS)
    while k * step <= hi + EPS:
        v = round(k * step, 6)
        if lo + EPS < v < hi - EPS or (last and abs(v - hi) < EPS) or (first and abs(v - lo) < EPS):
            out.append(((v - a) / (b - a), v))
        k += 1
    return out


def placed(band, sid, step, pts):
    """[((x, y, lowest x, highest x), count)]: the ticks of one drawn run (screen points) that a level stretch can hold."""
    out = []
    for share, value in ticks(band, sid, step):
        spot = level_spot(pts, share, MARGIN)
        if spot is not None:
            out.append((spot, value))
    return out


def choose_step(per, opts):
    """The step for the whole sheet: the preference's, else the smallest that leaves every band at most 8 ticks as drawn
    (fewer on a short band: one per 4 grid columns). `per` is [[(title, band, opts)]] per input."""
    from . import draw, layout
    pref = preference(opts) or {}
    if pref.get("step"):
        return float(pref["step"])
    runs = []
    for bands in per:
        for title, band, o in bands:
            cell = o.get("band_cell", {}).get(draw.band_key(title), o["cell"])
            drawn = layout.paths(band)
            runs.append((band, {sid: [(c * cell, r * o["rowh"]) for c, r in drawn[sid]]
                                for sid in band["strands"] if sid not in band["R"]["diag"]},
                         max(band["x"].values()) - min(band["x"].values())))
    for step in STEPS:
        if all(sum(len(placed(band, sid, step, pts)) for sid, pts in px.items())
               <= min(MAX_TICKS, max(2, int(width / CELLS_PER_TICK))) for band, px, width in runs):
            return step
    return STEPS[-1]


def level_spot(pts, share, margin):
    """Where a tick goes on a drawn run (screen points): `share` of the way along it, moved onto the nearest level
    stretch and kept `margin` px from its ends. Returns (x, y, lowest x, highest x) of that stretch, or None when
    the run has no level stretch long enough."""
    segs, d0 = [], 0.0
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L and abs(b[1] - a[1]) < 0.01 and L > 2 * margin:
            segs.append((d0 + margin, d0 + L - margin, a, b))
        d0 += L
    if not segs:
        return None
    want = d0 * share
    lo, hi, a, b = min(segs, key=lambda sg: 0 if sg[0] <= want <= sg[1] else min(abs(want - sg[0]), abs(want - sg[1])))
    want = min(max(want, lo), hi)
    sign = 1 if b[0] > a[0] else -1
    x0, x1 = sorted((a[0] + sign * margin, b[0] - sign * margin))
    along = want - (lo - margin)                     # distance from the stretch's own start
    return a[0] + sign * along, a[1], x0, x1
