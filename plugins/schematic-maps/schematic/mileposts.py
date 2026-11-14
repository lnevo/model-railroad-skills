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
more than 8 ticks (fewer on a short band: one per 10 grid columns) is used for the whole sheet.
"""
import heapq
import math

from . import edits
from .capacity import measured_length
from .core import SchematicError

MILE_IN = 63360.0
STEPS = (0.05, 0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)
MAX_TICKS = 8
CELLS_PER_TICK = 10     # a band holds about one tick per this many grid columns, up to MAX_TICKS
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


def _node(g, ref):
    """A junction by number, or the track end of a helix or named track (as `edits.mark_main` finds it)."""
    N = g["nodes"]
    for e in g["edges"]:
        for n in (e["u"], e["v"]):
            if N[n]["kind"] == "end" and (ref in e["names"] or N[n].get("label") == ref):
                return n
    return edits.by_label(g, ref)


def edge_miles(e, measured, ratio):
    """Scale miles in one track: its measured length when listed, else the plan's."""
    inches = None
    for name in e["names"]:
        inches = measured_length(measured, name)
        if inches is not None:
            break
    if inches is None:
        inches = e["cm"] / 2.54
    return inches * ratio / MILE_IN


def _way(g, a, b, direct):
    """[(edge, from node, to node)]: the main tracks from a to b, or None."""
    if direct:
        hits = [e for e in g["edges"] if e["main"] and {e["u"], e["v"]} == {a, b}]
        if not hits:
            return None
        e = min(hits, key=lambda e: (e["cm"], e["id"]))
        return [(e, a, b)]
    heap, seen, seq = [(0.0, 0, a, [])], set(), 0
    adj, N = {}, g["nodes"]
    for e in g["edges"]:
        # main track, and the cross-over between the two halves of one numbered switch, which a route may take
        if e["main"] or (N[e["u"]].get("label") and N[e["u"]].get("label") == N[e["v"]].get("label")):
            adj.setdefault(e["u"], []).append((e["v"], e))
            adj.setdefault(e["v"], []).append((e["u"], e))
    while heap:
        d, _, u, way = heapq.heappop(heap)
        if u == b:
            return way
        if u in seen:
            continue
        seen.add(u)
        for v, e in adj.get(u, ()):
            if v not in seen and (v == b or g["nodes"][v]["kind"] != "end"):
                seq += 1
                heapq.heappush(heap, (d + e["cm"], seq, v, way + [(e, u, v)]))
    return None


def compute(graphs, optlist):
    """Per input graph (after its edits and main marks): {"edges": {edge id: (near node, count there, miles, u)},
    "origin": node or None}. `optlist` is each input's merged options."""
    origin = _first(optlist, "milepost_origin")
    if not isinstance(origin, dict) or "switch" not in origin:
        raise SchematicError('mileposts need layer 1 milepost_origin: {"switch": "1", "milepost": 0.0}')
    ratio = _first(optlist, "scale_ratio")
    if ratio is None or isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio <= 0:
        raise SchematicError(f"mileposts need layer 1 scale_ratio above 0 (87.1 for HO), not {ratio!r}")
    helix_in = _first(optlist, "helix_length_in")
    known, tables, ways = {}, [], {}
    for g, o in zip(graphs, optlist):
        tables.append({"edges": {}, "origin": None})
    home = next(i for i, o in enumerate(optlist) if o.get("milepost_origin"))
    start = edits.by_label(graphs[home], str(origin["switch"]))
    known[(home, start)] = float(origin.get("milepost", 0.0))
    tables[home]["origin"] = start
    routes = []
    for i, (g, o) in enumerate(zip(graphs, optlist)):
        for entry in o.get("milepost_route") or o.get("main_route") or ():
            a, b, *how = entry
            routes.append((i, a, b, bool(how)))
    measured = [{k.upper(): float(v) for k, v in o.get("track_lengths_in", {}).items()} for o in optlist]
    ends = {}
    for i, g in enumerate(graphs):
        for e in g["edges"]:
            for n in (e["u"], e["v"]):
                if g["nodes"][n].get("sub") == "helix" and e["names"]:
                    ends.setdefault(e["names"][0], set()).add((i, n))
    changed = True
    while changed:
        changed = False
        for i, a, b, direct in routes:
            g = graphs[i]
            na, nb = _node(g, a), _node(g, b)
            key = (i, na, nb, direct)
            if key not in ways:
                ways[key] = _way(g, na, nb, direct)
            way = ways[key]
            if not way:
                continue
            miles = [edge_miles(e, measured[i], ratio) for e, _, _ in way]
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
        for name, group in ends.items():       # the same helix track on two levels: the far end carries on
            length = helix_in.get(name) if isinstance(helix_in, dict) else helix_in
            if length is None:
                continue
            ratio_miles = float(length) * ratio / MILE_IN
            for p in sorted(group):
                for q in sorted(group):
                    if p != q and p in known and q not in known:
                        known[q], changed = known[p] + ratio_miles, True
    return tables


def number(v):
    """A milepost as printed: no trailing zeros."""
    return f"{round(v, 4):g}"


def local_span(sid, s):
    """The share of its own (possibly half) edge a strand covers, as (at its start, at its end), 0 at the edge's `u`."""
    e0, e1 = s["ends"]
    if sid.endswith(".0"):
        return (0.5, 0.0) if s["src"][0].startswith("turn:") else (0.0, 0.5)
    if sid.endswith(".1"):
        return (1.0, 0.5) if not s["src"][0].startswith("turn:") else (0.5, 1.0)
    return (0.0, 1.0) if s["src"][0] == e0 else (1.0, 0.0)


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
    return count(f0), count(f1)


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


def choose_step(per, opts):
    """The step for the whole sheet: the preference's, else the smallest that leaves every band 8 ticks or fewer.
    `per` is [[(title, band, opts)]] per input."""
    pref = preference(opts) or {}
    if pref.get("step"):
        return float(pref["step"])
    for step in STEPS:
        fits = True
        for bands in per:
            for _, band, _ in bands:
                n = len({v for sid in band["strands"] for _, v in ticks(band, sid, step)})
                width = max(band["x"].values()) - min(band["x"].values())
                fits = fits and n <= min(MAX_TICKS, max(2, int(width / CELLS_PER_TICK)))
        if fits:
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
