"""Direction: which way is east on the railroad, and which way each switch faces.

The main route in layer 1 is listed in timetable order, west to east: each pair of switches on it says which way
east runs there. A level with no main route keeps the direction it is drawn with (east to the right, the declared
west end at the left). From there east is carried along every track, main route first and then by the shortest way, the
way a train would keep going. A switch whose points meet an eastward train first is R, else L. A crossover's
halves, which share one number, and a double crossover get no letter.

Where the railroad turns back on itself (a reversing loop, a wye, a crossover between tracks run opposite
ways) two ways can disagree; the main route wins, then the nearest way. Main track where the route itself
turns back is reported, so the owner can check it.
"""
import collections
import heapq

from .core import JUNCTION, TAU


SIDE_TRACK = 10000.0     # cm: any way along the main route beats any way that leaves it


def east(g, routes, node_ref):
    """{junction: +1 or -1}: a leg's side times this is +1 where the leg leaves eastward; and [conflicts].
    Every pair of switches joined by one track along the main route is a seed (a to b is eastward). East is
    carried from the seeds along the track, the main route first, then the nearest way; the first way to a
    switch wins."""
    N = g["nodes"]
    adj = collections.defaultdict(list)
    for e in g["edges"]:
        adj[e["u"]].append((e["up"], e["v"], e["vp"], e))
        adj[e["v"]].append((e["vp"], e["u"], e["up"], e))
    heap = []
    for a, b, *how in routes:
        try:
            na, nb = node_ref(a), node_ref(b)
        except Exception:                   # a helix or track name rather than a switch
            continue
        if N[na]["kind"] not in JUNCTION or N[nb]["kind"] not in JUNCTION or na == nb:
            continue
        if how:                             # "direct": the track that joins the two, however long (a loop)
            path = next(([(p, m, q)] for p, m, q, e in sorted(adj[na], key=lambda t: not t[3]["main"]) if m == nb), None)
        else:
            path = main_path(adj, N, na, nb)
        if path:                            # the first and last legs of the way along the main from a to b
            heap.append((0.0, len(heap), na, TAU[path[0][0]]))     # leaving a toward b is eastward
            heap.append((0.0, len(heap), nb, -TAU[path[-1][2]]))   # arriving at b from a: that leg is west
    heapq.heapify(heap)
    rail, conflicts, seq = {}, set(), len(heap)
    while heap:
        d, _, u, val = heapq.heappop(heap)
        if u in rail:
            if rail[u] != val and d == 0.0:
                conflicts.add(u)            # two seeds disagree: the route itself turns back here
            continue
        rail[u] = val
        for up, v, vp, e in adj[u]:
            if v not in rail and N[v]["kind"] in JUNCTION:
                seq += 1
                heapq.heappush(heap, (d + e["cm"] + (0 if e["main"] else SIDE_TRACK), seq, v, -val * TAU[up] * TAU[vp]))
    for e in g["edges"]:
        u, v = e["u"], e["v"]
        if u != v and u in rail and v in rail and rail[v] != -rail[u] * TAU[e["up"]] * TAU[e["vp"]] and e["main"]:
            conflicts.update((u, v))
    return rail, sorted(conflicts)


def main_path(adj, N, a, b):
    """The shortest way from a to b along main track: [(leg out, next node, leg in)], or None."""
    heap, seen, seq = [(0.0, 0, a, [])], set(), 0
    while heap:
        d, _, u, way = heapq.heappop(heap)
        if u == b:
            return way
        if u in seen:
            continue
        seen.add(u)
        for up, v, vp, e in adj[u]:
            if e["main"] and v not in seen and N[v]["kind"] in JUNCTION:
                seq += 1
                heapq.heappush(heap, (d + e["cm"], seq, v, way + [(up, v, vp)]))
    return None


def drawn(band, east_is_left):
    """{switch: +1 or -1} from the drawing alone, for switches the main route does not reach: east is right,
    or left on a band whose main runs east to the left."""
    flip = -1 if east_is_left else 1
    return {n: (d["sig"] or 1) * flip for n, d in band["nodes"].items() if d.get("kind") in JUNCTION}


def letters(N, rail):
    """{switch: "R" or "L"} for every switch that prints its own number."""
    count = collections.Counter(d.get("label") for d in N.values() if d["kind"] == "switch")
    return {n: ("R" if rail[n] * TAU["A"] == -1 else "L") for n, d in N.items()
            if d["kind"] == "switch" and n in rail and count[d.get("label")] == 1}


def east_left(band, rail):
    """True when most of a band's main-route switches are drawn with east to the left."""
    main = {n for s in band["strands"].values() if s["main"] for n in (s["src"][0], s["dst"][0])}
    votes = [d["sig"] == rail[n] for n, d in band["nodes"].items()
             if d.get("kind") in JUNCTION and n in rail and n in main and d.get("sig")]
    return bool(votes) and sum(votes) < len(votes) / 2


def main_runs(band, drawn):
    """[(row, x from, x to, east is right, [strands])] for each level stretch of drawn main track, when the band runs east to
    the left anywhere along its main; [] when east is to the right all along it (the page legend says so).
    `drawn` is the drawn path of each strand, as layout.paths gives it."""
    nodes, strands, rail = band["nodes"], band["strands"], band.get("rail", {})

    def east_right(k):
        s = strands[k]
        for n, leg, sign in ((s["src"][0], s["src"][1], 1), (s["dst"][0], s["dst"][1], -1)):
            if n in rail and nodes[n].get("sig") and leg in TAU:
                return rail[n] * TAU[leg] == sign
        return None

    pieces = []                             # (row, x from, x to, strand) for every level piece of a main strand
    for k, pts in drawn.items():
        if k in strands and strands[k]["main"]:
            for (c1, r1), (c2, r2) in zip(pts, pts[1:]):
                if r1 == r2 and c2 != c1:
                    pieces.append((r1, min(c1, c2), max(c1, c2), k))
    runs = []
    for row, a, b, k in sorted(pieces):
        way = east_right(k)
        if way is None:
            continue
        if runs and runs[-1][0] == row and runs[-1][3] == way and a <= runs[-1][2] + 1e-6:
            runs[-1] = (row, runs[-1][1], max(b, runs[-1][2]), way, runs[-1][4] + [k])    # pieces that meet or overlap are one run
        else:
            runs.append((row, a, b, way, [k]))
    return runs if any(not r[3] for r in runs) else []
