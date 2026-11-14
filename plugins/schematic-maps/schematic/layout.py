"""Lay out one band and test the result for lines that cross or lie on top of each other."""
import collections  # noqa: F401
import itertools

from .columns import Unsettled, overlaps, place, spans
from .core import JUNCTION, dedupe  # noqa: F401
from . import rules
from .orient import build, columns, orient
from .rows import Rows
from .sweep import sweep



def layout(g, opts, warnings):
    """Try the cheapest few orientations and keep the drawing with the fewest faults."""
    best = None
    for sig, T in orient(g):
        w = []
        band = layout_one(g, sig, T, opts, w)
        pos = band["x"]
        score = (end_violations(band["nodes"], pos, g, opts), len(faults(band)) + 3 * len(w), len(T))
        if best is None or score < best[0]:
            best = (score, band, w)
        if score[0] == 0 and score[1] == 0:
            break
    warnings.extend(best[2])
    return best[1]


def west_end_node(g, opts):
    """The track end named by the level's declared west end (`left_end`), or None."""
    name = opts.get("left_end")
    if not name:
        return None
    for e in g["edges"]:
        if name in e["names"]:
            for n in (e["u"], e["v"]):
                if g["nodes"][n]["kind"] == "end":
                    return n
    return None


def end_violations(nodes, pos, g, opts):
    """Layer 1 facts about the ends of a band that a drawing must keep: the declared west end is the leftmost track
    end and its track runs leftward from its switch, and a helix end marked east is right of centre, one marked west left of it. `pos` is the column (or x) of
    every node. Returns how many are broken; the orientation is chosen so that none is, before faults decide."""
    mid = (min(pos.values()) + max(pos.values())) / 2
    bad = 0
    west = west_end_node(g, opts)
    if west is not None and west in pos:
        ends = [pos[n] for n, d in nodes.items() if d["kind"] == "end" and n in pos]
        if pos[west] > mid or pos[west] > min(ends):        # the declared west end is the leftmost track end
            bad += 1
        if nodes[west]["ins"]:                              # and its track runs leftward from its switch
            bad += 1
    for n, d in nodes.items():
        if d["kind"] == "end" and d.get("side") and n in pos:
            if (d["side"] == "east") != (pos[n] > mid) and pos[n] != mid:
                bad += 1
    return bad


def mirrored(g, sig, T, opts):
    """The violations of the same fold drawn end for end: (nodes, columns, graph, options) for end_violations."""
    flipped = {n: -s_ for n, s_ in sig.items()}
    nodes, strands = build(g, flipped, T)
    return nodes, columns(nodes, strands), g, opts


def layout_one(g, sig, T, opts, warnings):
    nodes, strands = build(g, sig, T)
    col = columns(nodes, strands)
    if end_violations(nodes, col, g, opts) and end_violations(*mirrored(g, sig, T, opts)) < end_violations(nodes, col, g, opts):
        sig = {n: -s_ for n, s_ in sig.items()}
        nodes, strands = build(g, sig, T)
        col = columns(nodes, strands)
    order, snaps, enclosed, free, ev = sweep(nodes, strands, col, warnings.append)
    rule_pins = rules.level_legs(nodes, strands, opts) if opts.get("rules", True) else {}

    def settle(span_filter):
        """Rows and columns, repeated until no two runs clash on a row. Returns (band, rows)."""
        rows = Rows(nodes, strands, snaps, free, opts.get("level_leg"), opts.get("keep_close", ()), rule_pins)
        rows.spans = span_filter
        xcons, refused = set(), set()
        for _ in range(12):
            R = rows.optimise()
            try:
                x, need = place(nodes, strands, R, enclosed, opts, xcons)
            except Unsettled:               # a clearance rule that cannot hold with the new rows: keep the ones that can
                kept = set()
                for rule in sorted(xcons):
                    try:
                        place(nodes, strands, R, enclosed, opts, kept | {rule})
                        kept.add(rule)
                    except Unsettled:
                        refused.add(rule)
                xcons = kept
                x, need = place(nodes, strands, R, enclosed, opts, xcons)
            band = dict(nodes=nodes, strands=strands, R=R, x=x, need=need, turnbacks=T)
            clash, apart = set(), set()
            for a, b in overlaps(nodes, strands, R, x, need, order) - rows.extra:
                (sa, da), (sb, db) = ((strands[k]["src"][0], strands[k]["dst"][0]) for k in (a, b))
                stub = lambda p, q: nodes[p]["kind"] == "end" or nodes[q]["kind"] == "end"
                gap = lambda p, q: 1 + sum(nodes[t].get("sub") in ("link", "helix") for t in (p, q))    # room for the circles
                if ev[da] < ev[sb] and stub(da, sb):    # a ends before b starts and one is a stub: slide it along the row
                    apart.add((da, sb, gap(da, sb)))
                elif ev[db] < ev[sa] and stub(db, sa):
                    apart.add((db, sa, gap(db, sa)))
                else:
                    clash.add((a, b))
            more = (slope_rules(band, ev) | apart) - xcons - refused
            if not clash and not more:
                break
            rows.extra |= clash
            xcons |= more
        return band, rows

    band, rows = settle(None)
    if opts.get("rule_rows", True):         # R7: second pass, keeping rows apart only for runs that overlap
        sp = spans(nodes, strands, band["R"], band["x"], band["need"])
        again, rows2 = settle(sp)
        if extent(again, rows2) < extent(band, rows):      # kept only when it draws no worse and uses less room
            band, rows = again, rows2
    if rows.dropped:
        warnings.append(f"{rows.dropped} above/below rules dropped where the layout is not flat")
    return band


def extent(band, rows):
    """How good a drawing is, smaller being better: faults, dropped rules, rows used, then columns."""
    srow, x = band["R"]["srow"], band["x"]
    return (len(faults(band)), rows.dropped, max(srow.values()) - min(srow.values()), max(x.values()) - min(x.values()))


def slope_rules(band, ev):
    """Where a sloped leg cuts through another track, keep that track clear of the slope's columns."""
    strands = band["strands"]
    found = set()
    for _, k1, s1, k2, s2 in faults(band):
        for (ka, (a, b)), kb in (((k1, s1), k2), ((k2, s2), k1)):
            if ka not in strands or kb not in strands or a[0] == b[0] or a[1] == b[1]:
                continue
            pts = paths(band)[ka]
            src, dst = strands[ka]["src"][0], strands[ka]["dst"][0]
            k = int(round(abs(b[1] - a[1])))
            bs, bd = strands[kb]["src"][0], strands[kb]["dst"][0]
            if (a, b) == (pts[0], pts[1]):          # slope leaves switch src
                n, before, after = src, 0, k
            elif (a, b) == (pts[-2], pts[-1]):      # slope arrives at switch dst
                n, before, after = dst, k, 0
            else:
                continue
            if ev[bd] < ev[n] and bd != n:
                found.add((bd, n, before))
            elif ev[bs] > ev[n] and bs != n:
                found.add((n, bs, after))
    return found


def paths(band):
    """Every drawn line in grid units: id -> list of (column, row)."""
    nodes, strands, R, x, need = (band[k] for k in ("nodes", "strands", "R", "x", "need"))
    srow, nrow, diag = R["srow"], R["nrow"], R["diag"]
    out, turns = {}, collections.defaultdict(list)
    for sid, s in strands.items():
        u, v = s["src"][0], s["dst"][0]
        if sid in diag:
            out[sid] = [(x[u], nrow[u]), (x[v], nrow[v])]
            continue
        su, sv, _ = need[sid]
        r = srow[sid]
        pts = [(x[u], nrow[u])] if u in nrow else []
        pts += [(x[u] + su, r), (x[v] - sv, r)]
        if v in nrow:
            pts.append((x[v], nrow[v]))
        out[sid] = dedupe(pts)
        for t in (u, v):
            if nodes[t]["kind"].startswith("turn"):
                turns[t].append(r)
    for t, rs in turns.items():
        r1, r2 = sorted(rs)
        k = min(1.0, r2 - r1) / 2
        dx = -k if nodes[t]["kind"] == "turnR" else k
        out[t] = [(x[t], r1), (x[t] - dx, r1 + k), (x[t] - dx, r2 - k), (x[t], r2)]
    return out


def faults(band):
    """Lines that lie on top of each other or cross: (kind, id, segment, id, segment)."""
    strands = band["strands"]
    P = paths(band)

    def ends(k):
        return {strands[k]["src"][0], strands[k]["dst"][0]} if k in strands else {k}

    segs = [(k, a, b) for k, pts in P.items() for a, b in zip(pts, pts[1:]) if a != b]
    found = []
    for (k1, a, b), (k2, c, d) in itertools.combinations(segs, 2):
        if k1 == k2 or (k1 not in strands and k2 in strands and k1 in ends(k2)) or \
                (k2 not in strands and k1 in strands and k2 in ends(k1)):
            continue
        d1, d2 = (b[0] - a[0], b[1] - a[1]), (d[0] - c[0], d[1] - c[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        w = (c[0] - a[0], c[1] - a[1])
        if abs(den) < 1e-9:
            if abs(w[0] * d1[1] - w[1] * d1[0]) > 1e-9:
                continue
            L = d1[0] ** 2 + d1[1] ** 2
            t0, t1 = sorted(((p[0] - a[0]) * d1[0] + (p[1] - a[1]) * d1[1]) / L for p in (c, d))
            if min(t1, 1) - max(t0, 0) > 1e-6:
                found.append(("on top of each other", k1, (a, b), k2, (c, d)))
            continue
        t = (w[0] * d2[1] - w[1] * d2[0]) / den
        u = (w[0] * d1[1] - w[1] * d1[0]) / den
        if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
            at_end = (t < 1e-6 or t > 1 - 1e-6) and (u < 1e-6 or u > 1 - 1e-6)
            if at_end and ends(k1) & ends(k2):
                continue
            found.append(("cross", k1, (a, b), k2, (c, d)))
    return found


def check(band):
    nodes, strands = band["nodes"], band["strands"]

    def name(k):
        if k not in strands:
            return "turnback"
        s = strands[k]
        return (s["name"] or "track") + " " + "-".join(nodes[n].get("label") or "end" for n in (s["src"][0], s["dst"][0]))

    return sorted({f"{kind}: {name(k1)} and {name(k2)} near column {a[0]:.0f}, row {a[1]:.0f}"
                   for kind, k1, (a, _), k2, _ in faults(band)})


