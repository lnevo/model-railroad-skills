"""Plan reader: AnyRail's "export to JMRI" XML to a logical track graph.

The export is a Layout Editor file holding only track: every turnout (and double crossover), the runs
between them, and the track ends. It has no heights and no switch numbers; both can come from a parts file
(see below), and the plan overrides rename and correct the rest.

Graph (a dict; save it as JSON):
  nodes: id -> {kind: switch|dx|end, label, xy, hand (+1 / -1), dirs {port: unit vector}, district, ...}
  edges: [{id, u, up, v, vp, names, cm, link, main, district, hidden}]   ports: A points, B straight, C
         diverging, E end (a double crossover has A, B, C, D)

The section a track belongs to is the export's block name after its second underscore (AnyRail's section
name). `skip` keeps one group of sections: "+Name" keeps only track in sections whose name contains Name,
"Name" leaves it out. Two track ends on the same spot are one track drawn in two pieces and are joined.

The optional parts list is a list of plan parts, each {"eps": [{"x", "y", "z"}, ...]} in centimetres:
a part with three or more end points is a switch. Switches are matched to parts by position (with a
least-squares fit of offset and scale, since the export is not exactly to the plan's scale); a matched
switch is labelled T<index> and given the part's height `z`. `z_range` = (low, high) restricts the parts to
one group of heights, for plans that stack levels on top of each other.
"""
import collections
import math
import xml.etree.ElementTree as ET

PX_PER_CM = 120 / 25.4   # AnyRail's export: 120 px per inch of plan


class PlanError(ValueError):
    pass


def unit(dx, dy):
    n = math.hypot(dx, dy) or 1.0
    return [dx / n, dy / n]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def read(path, skip=None, parts=None, z_range=None, main_section="Mainline"):
    """The track graph of an AnyRail export; `parts` is the parts list (see above), not a file name."""
    panel = ET.parse(path).getroot().find("LayoutEditor")
    tos = {t.get("ident"): t for t in panel.iter("layoutturnout")}
    segs = {s.get("ident"): s for s in panel.iter("tracksegment")}
    pps = {p.get("ident"): p for p in panel.iter("positionablepoint")}
    nodes, portmap, edges = {}, {}, []

    def pt(t, leg):
        cx, cy = float(t.get("xcen")), float(t.get("ycen"))
        if leg == "B":
            return float(t.get("xb")), float(t.get("yb"))
        if leg == "C":
            return float(t.get("xc")), float(t.get("yc"))
        o = pt(t, "B" if (leg == "A" and "XOVER" not in t.get("type")) else ("C" if leg == "A" else "B"))
        return 2 * cx - o[0], 2 * cy - o[1]

    for ident, t in tos.items():
        ty = t.get("type")
        district = (t.get("blockname") or "").split("_", 2)[-1]
        if ty in ("LH_TURNOUT", "RH_TURNOUT", "WYE_TURNOUT"):
            a, b, c = pt(t, "A"), pt(t, "B"), pt(t, "C")
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            nodes[ident] = dict(kind="switch", label="", xy=list(mid), district=district,
                                hand=1 if cross((b[0] - a[0], b[1] - a[1]), (c[0] - a[0], c[1] - a[1])) > 0 else -1,
                                dirs={k: unit(p[0] - mid[0], p[1] - mid[1]) for k, p in zip("ABC", (a, b, c))})
            for leg in "ABC":
                portmap[(ident, leg)] = (ident, leg)
        elif ty == "DOUBLE_XOVER":      # tracks A-B and D-C, both crossings
            a, b, c, d = (pt(t, leg) for leg in "ABCD")
            mid = (float(t.get("xcen")), float(t.get("ycen")))
            nodes[ident] = dict(kind="dx", label="", xy=list(mid), district=district,
                                hand=1 if cross((b[0] - a[0], b[1] - a[1]), (d[0] - a[0], d[1] - a[1])) > 0 else -1,
                                dirs={k: unit(p[0] - mid[0], p[1] - mid[1]) for k, p in zip("ABCD", (a, b, c, d))})
            for leg in "ABCD":
                portmap[(ident, leg)] = (ident, leg)
        else:
            raise PlanError(f"unsupported turnout type {ty} at {ident}")

    def where(name, ty):
        if ty.startswith("TURNOUT"):
            return pt(tos[name], ty[-1])
        p = pps[name]
        return float(p.get("x")), float(p.get("y"))

    def seg_cm(s):
        pts = [where(s.get("connect1name"), s.get("type1"))]
        pts += [(float(c.get("x")), float(c.get("y"))) for c in s.iter("controlpoint")]
        pts.append(where(s.get("connect2name"), s.get("type2")))
        chord = math.dist(pts[0], pts[-1])
        poly = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
        return (chord + poly) / 2 / PX_PER_CM      # a Bezier lies between its chord and its control polygon

    def ends_of(s):
        return [(s.get("connect1name"), s.get("type1")), (s.get("connect2name"), s.get("type2"))]

    def follow(seg, frm):
        cm, blocks, dashed = seg_cm(seg), [seg.get("blockname")], seg.get("dashed") == "yes"
        while True:
            n, ty = next(e for e in ends_of(seg) if e[0] != frm)
            if ty.startswith("TURNOUT"):
                return portmap[(n, ty[-1])], cm, blocks, dashed
            pp = pps[n]
            nxt = [x for x in (pp.get("connect1name"), pp.get("connect2name")) if x and x != seg.get("ident")]
            if pp.get("type") == "END_BUMPER" or not nxt:
                return ("END:" + n, "E"), cm, blocks, dashed
            frm, seg = n, segs[nxt[0]]
            cm += seg_cm(seg)
            dashed = dashed or seg.get("dashed") == "yes"
            if seg.get("blockname") != blocks[-1]:
                blocks.append(seg.get("blockname"))

    seen = set()
    for s in segs.values():
        for n, ty in ends_of(s):
            if not ty.startswith("TURNOUT") or portmap[(n, ty[-1])] in seen:
                continue
            start = portmap[(n, ty[-1])]
            (v, vp), cm, blocks, dashed = follow(s, n)
            seen.update((start, (v, vp)))
            if v.startswith("END:"):
                ex, ey = float(pps[v[4:]].get("x")), float(pps[v[4:]].get("y"))
                nodes[v] = dict(kind="end", sub="bumper", label="", xy=[ex, ey])
            district = collections.Counter(b for b in blocks if b).most_common(1)
            district = district[0][0].split("_", 2)[-1] if district else ""
            edges.append(dict(u=start[0], up=start[1], v=v, vp=vp, names=[], cm=round(cm, 1), link=False,
                              main=main_section in district, district=district, hidden=dashed))

    # two track ends on the same spot are one track drawn in two pieces: join them
    ends = [n for n, d in nodes.items() if d["kind"] == "end"]
    joined = 0
    for i, a in enumerate(ends):
        for b in ends[i + 1:]:
            if a in nodes and b in nodes and math.dist(nodes[a]["xy"], nodes[b]["xy"]) < 1.5 * PX_PER_CM:
                ea = next(e for e in edges if e["v"] == a)
                eb = next(e for e in edges if e["v"] == b)
                edges.remove(eb)
                ea.update(v=eb["u"], vp=eb["up"], cm=round(ea["cm"] + eb["cm"], 1), hidden=ea["hidden"] or eb["hidden"])
                del nodes[a], nodes[b]
                joined += 1
    only = bool(skip) and skip.startswith("+")       # "+Name" keeps only those sections; "Name" leaves them out
    if skip:
        text = skip.lstrip("+")
        drop = {n for n, d in nodes.items() if d["kind"] != "end" and (text in d.get("district", "")) != only}
        edges = [e for e in edges if e["u"] not in drop and e["v"] not in drop and (text in e["district"]) == only]
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        parent[find(e["u"])] = find(e["v"])
    size = collections.Counter(find(n) for n, d in nodes.items() if d["kind"] != "end")
    keep = size.most_common(1)[0][0]
    nodes = {n: d for n, d in nodes.items() if find(n) == keep}
    edges = [e for e in edges if e["u"] in nodes]
    order = sorted((n for n, d in nodes.items() if d["kind"] != "end"), key=lambda n: (nodes[n]["xy"][1], nodes[n]["xy"][0]))
    for i, n in enumerate(order, 1):
        nodes[n]["label"] = str(i)
    notes = [f"joined {joined} pairs of track ends that met"]
    if parts:           # label junctions with the plan's part numbers and heights
        plan = []
        for i, p in enumerate(parts):
            e = [q for q in p["eps"] if abs(q["x"]) < 5000]
            if len(e) >= 3 and (z_range is None or z_range[0] <= max(q["z"] for q in e) <= z_range[1]):
                plan.append((i, sum(q["x"] for q in e) / len(e), sum(q["y"] for q in e) / len(e), max(q["z"] for q in e)))
        mine = [(n, nodes[n]["xy"][0] / PX_PER_CM, nodes[n]["xy"][1] / PX_PER_CM) for n in order]
        best = (-1, 0, 0)
        for _, x, y in mine[:6]:
            for _, u, v, _ in plan:
                ox, oy = x - u, y - v
                hits = sum(min(math.hypot(a - ox - u2, b - oy - v2) for _, u2, v2, _ in plan) < 4 for _, a, b in mine)
                if hits > best[0]:
                    best = (hits, ox, oy)
        hits, ox, oy = best
        sx = sy = 1.0

        def pairs(tol):
            out = []
            for n, x, y in mine:
                i, dist, z, u, v = min(((i, math.hypot(x - (sx * u + ox), y - (sy * v + oy)), z, u, v)
                                        for i, u, v, z in plan), key=lambda t: t[1])
                if dist < tol:
                    out.append((n, i, z, x, y, u, v))
            return out

        def fit(a, b):      # least squares b = s * a + o
            ma, mb = sum(a) / len(a), sum(b) / len(b)
            s_ = sum((p - ma) * (q - mb) for p, q in zip(a, b)) / sum((p - ma) ** 2 for p in a)
            return s_, mb - s_ * ma

        for tol in (4, 6, 6, 4):        # the export is not exactly to the plan's scale: refit and rematch
            got = pairs(tol)
            sx, ox = fit([g[5] for g in got], [g[3] for g in got])
            sy, oy = fit([g[6] for g in got], [g[4] for g in got])
        cand = sorted((math.hypot(x - (sx * u + ox), y - (sy * v + oy)), n, i, z)
                      for n, x, y in mine for i, u, v, z in plan)
        used_n, used_i, hits = set(), set(), 0
        for dist, n, i, z in cand:          # nearest first, one plan part per junction
            if dist > 10:
                break
            if n in used_n or i in used_i:
                continue
            used_n.add(n)
            used_i.add(i)
            hits += 1
            nodes[n]["label"], nodes[n]["z"] = f"T{i}", round(z, 1)
        notes.append(f"scale correction {round(sx, 4)} {round(sy, 4)}")
        notes.append(f"matched {hits} of {len(mine)} junctions to plan parts")
    for i, e in enumerate(edges):
        e["id"] = f"e{i}"
    kinds = collections.Counter(d["kind"] for d in nodes.values())
    notes.append(f"{dict(kinds)} {len(edges)} edges; districts: "
                 f"{dict(collections.Counter(e['district'] for e in edges).most_common())}")
    return dict(nodes=nodes, edges=edges, notes=notes)
