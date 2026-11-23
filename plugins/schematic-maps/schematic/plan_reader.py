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

Lengths (edge `cm`) are measured in export pixels and turned into centimetres at the export's scale. With a
parts list that scale is fitted: one factor for both axes, from every matched switch, so an export made at any
size gives plan lengths. The fit stops the run when the two axes disagree by more than SCALE_AXES_TOLERANCE (the
export is then not a uniform copy of the plan). Without parts the scale is PX_PER_CM, the size the exports read so
far were made at; the notes say which scale was used.
"""
import collections
import math
import xml.etree.ElementTree as ET

PX_PER_CM = 12 / 2.54     # the exports read so far: 12 px per inch of plan (within 0.5 % of the fitted scale)
NEAR_CM = 5.0           # two free track ends this close that face each other are one track the plan did not snap
NEAR_ANGLE = 30         # degrees: each end's direction of travel must point at the other end within this
SCALE_AXES_TOLERANCE = 0.03     # largest relative difference between the x and y scale fitted against the parts
SCALE_SEARCH_LIMIT = 0.10       # an export whose spread is this far from PX_PER_CM is searched at its own scale


class PlanError(ValueError):
    pass


def fit(a, b):
    """Least squares b = s * a + o: (s, o)."""
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    s = sum((p - ma) * (q - mb) for p, q in zip(a, b)) / sum((p - ma) ** 2 for p in a)
    return s, mb - s * ma


def spread(points):
    """Root mean square distance of `points` from their centre."""
    cx, cy = sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)
    return math.sqrt(sum((p[0] - cx) ** 2 + (p[1] - cy) ** 2 for p in points) / len(points))


def uniform_scale(matched):
    """One scale for both axes from [((x, y) on the export, (u, v) on the plan)]: least squares (x, y) = s (u, v) + o.
    Stops when the axes fitted alone disagree by more than SCALE_AXES_TOLERANCE, or the points are too few or too
    close together to fit."""
    if len(matched) < 3:
        raise PlanError(f"only {len(matched)} switches matched the parts; at least 3 are needed to fit the export's scale")
    mine, plan = [m for m, _ in matched], [p for _, p in matched]
    if min(spread(plan), spread(mine)) <= 0:
        raise PlanError("the matched switches all sit on one spot; the export's scale cannot be fitted")
    xs, ys = [p[0] for p in plan], [p[1] for p in plan]
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        raise PlanError("the matched switches lie on one line; the export's scale cannot be fitted on both axes")
    sx, _ = fit(xs, [m[0] for m in mine])
    sy, _ = fit(ys, [m[1] for m in mine])
    cu, cv = sum(xs) / len(xs), sum(ys) / len(ys)
    cx, cy = sum(m[0] for m in mine) / len(mine), sum(m[1] for m in mine) / len(mine)
    s = (sum((u - cu) * (x - cx) + (v - cv) * (y - cy) for (x, y), (u, v) in matched) /
         sum((u - cu) ** 2 + (v - cv) ** 2 for _, (u, v) in matched))
    if s <= 0:
        raise PlanError(f"the export's fitted scale is {s:.4f}; it must be above 0 (is it the same plan?)")
    if abs(sx - sy) > SCALE_AXES_TOLERANCE * s:
        raise PlanError(f"the export is not a uniform copy of the plan: its x scale fits {sx:.4f} and its y scale "
                        f"{sy:.4f} times the parts, more than {SCALE_AXES_TOLERANCE:.0%} apart")
    return s


def unit(dx, dy):
    n = math.hypot(dx, dy) or 1.0
    return [dx / n, dy / n]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def number(el, attr):
    """The element's attribute as a finite number, or a PlanError naming the element and the attribute."""
    raw = el.get(attr)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = None
    if v is None or not math.isfinite(v):
        raise PlanError(f"{el.tag} {el.get('ident')!r}: {attr}={raw!r} is not a number")
    return v


def turnout_point(t, leg):
    """Where leg A, B, C or D of a <layoutturnout> meets its track, in export px. The export gives the centre and
    B and C; A is B (C on a crossover) mirrored through the centre, D is B mirrored."""
    cx, cy = number(t, "xcen"), number(t, "ycen")
    if leg == "B":
        return number(t, "xb"), number(t, "yb")
    if leg == "C":
        return number(t, "xc"), number(t, "yc")
    o = turnout_point(t, "B" if (leg == "A" and "XOVER" not in (t.get("type") or "")) else ("C" if leg == "A" else "B"))
    return 2 * cx - o[0], 2 * cy - o[1]


def read(path, skip=None, parts=None, z_range=None, main_section="Mainline"):
    """The track graph of an AnyRail export; `parts` is the parts list (see above), not a file name."""
    panel = ET.parse(path).getroot().find("LayoutEditor")
    tos = {t.get("ident"): t for t in panel.iter("layoutturnout")}
    segs = {s.get("ident"): s for s in panel.iter("tracksegment")}
    pps = {p.get("ident"): p for p in panel.iter("positionablepoint")}
    others = {el.get("ident"): el for tag in ("levelxing", "layoutSlip", "layoutturntable") for el in panel.iter(tag)}
    nodes, portmap, edges, cuts, cut_ends, dangling, unplaced = {}, {}, [], {}, {}, set(), set()
    walked, end_dir = set(), {}      # track pieces a switch's track runs over; the way each free end faces (out of the track)
    pt = turnout_point

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
        elif ty in ("LH_XOVER", "RH_XOVER"):     # a single crossover: two turnouts joined by a short link
            a, b, c, d = (pt(t, leg) for leg in "ABCD")
            m1, m2 = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), ((c[0] + d[0]) / 2, (c[1] + d[1]) / 2)
            # The crossing route is A-C on a right-handed crossover and B-D on a left-handed one (the diagonal JMRI
            # draws slants that way on the default shape, and on a left-handed export). Each turnout has its points at
            # the leg that route starts from, goes straight to the other leg of its track, and the link joins the two.
            pa, pb = ((a, b), (c, d)) if ty == "RH_XOVER" else ((b, a), (d, c))      # (points leg, straight leg) per track
            legs = ("AB", "CD") if ty == "RH_XOVER" else ("BA", "DC")
            for k, (m, (p, q), far) in enumerate(((m1, pa, m2), (m2, pb, m1)), 1):
                nodes[f"{ident}.{k}"] = dict(
                    kind="switch", label="", xy=list(m), district=district, xover=ident,
                    hand=1 if cross((q[0] - p[0], q[1] - p[1]), (far[0] - p[0], far[1] - p[1])) > 0 else -1,
                    dirs={"A": unit(p[0] - m[0], p[1] - m[1]), "B": unit(q[0] - m[0], q[1] - m[1]),
                          "C": unit(far[0] - m[0], far[1] - m[1])})
                portmap[(ident, legs[k - 1][0])] = (f"{ident}.{k}", "A")
                portmap[(ident, legs[k - 1][1])] = (f"{ident}.{k}", "B")
            edges.append(dict(u=f"{ident}.1", up="C", v=f"{ident}.2", vp="C", names=[], cm=math.dist(m1, m2), link=False,
                              main=False, district=district, hidden=False))
        else:
            raise PlanError(f"unsupported turnout type {ty} at {ident}")

    def cut_reason(name):
        el = others.get(name)
        if el is None:
            return "part not read"
        if el.tag == "levelxing":
            return "level crossing (diamond) not read"
        if el.tag == "layoutturntable":
            return "turntable not read"
        return f"{(el.get('slipType') or 'slip').lower().replace('_', ' ')} not read"

    def num(el, attr):
        try:
            return number(el, attr)
        except PlanError:
            return None

    def cut_point(name, ty):
        """Where a leg of a part that is not read meets its track, in export px: the part's own leg point, or None
        when the export does not give it."""
        el = others.get(name)
        if el is None:
            return None
        cx, cy = num(el, "xcen"), num(el, "ycen")
        if cx is None or cy is None:
            return None
        if el.tag == "layoutturntable":
            ray = next((r for r in el.iter("raytrack") if r.get("index") == ty.rsplit("_", 1)[-1]), None)
            ang, r = (num(ray, "angle") if ray is not None else None), num(el, "radius")
            if ang is None or r is None:
                return cx, cy
            return cx + r * math.sin(math.radians(ang)), cy - r * math.cos(math.radians(ang))
        xa, ya, xb, yb = (num(el, k) for k in ("xa", "ya", "xb", "yb"))
        if None in (xa, ya, xb, yb):
            return cx, cy
        return {"A": (xa, ya), "B": (xb, yb), "C": (2 * cx - xa, 2 * cy - ya),
                "D": (2 * cx - xb, 2 * cy - yb)}.get(ty[-1], (cx, cy))

    def where(name, ty):
        """The leg's point in export px, or None when the export does not place it."""
        if ty.startswith("TURNOUT") and (name, ty[-1]) in portmap:
            return pt(tos[name], ty[-1])
        if name in pps:
            p = pps[name]
            return number(p, "x"), number(p, "y")
        if name in tos:
            return pt(tos[name], ty[-1])
        return cut_point(name, ty)

    def seg_pts(s):
        """The segment's known points in order (an end the export does not place is left out)."""
        ends = [where(s.get("connect1name"), s.get("type1")), where(s.get("connect2name"), s.get("type2"))]
        if None in ends:
            unplaced.add(next(s.get(f"connect{i + 1}name") for i, e in enumerate(ends) if e is None))
        mid = [(float(c.get("x")), float(c.get("y"))) for c in s.iter("controlpoint")]
        return [p for p in [ends[0]] + mid + [ends[1]] if p is not None], None in ends

    def seg_px(s):
        pts, partial = seg_pts(s)
        chord = math.dist(pts[0], pts[-1]) if pts else 0.0
        poly = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
        px = (chord + poly) / 2      # a Bezier lies between its chord and its control polygon
        return max(px, PX_PER_CM) if partial else px     # a missing end leaves a stub of about a centimetre at least

    def ends_of(s):
        return [(s.get("connect1name"), s.get("type1")), (s.get("connect2name"), s.get("type2"))]

    def facing(seg, n):
        """The unit direction the track leaves `seg` at its end `n`, or None when the export does not place enough of it."""
        pts, partial = seg_pts(seg)
        if partial or len(pts) < 2:
            return None
        if seg.get("connect2name") == n:
            return unit(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
        return unit(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])

    def follow(seg, frm):
        px, blocks, dashed = seg_px(seg), [seg.get("blockname")], seg.get("dashed") == "yes"
        walked.add(seg.get("ident"))
        while True:
            n, ty = next(e for e in ends_of(seg) if e[0] != frm)
            if ty.startswith("TURNOUT") and (n, ty[-1]) in portmap:
                return portmap[(n, ty[-1])], px, blocks, dashed
            pp = pps.get(n)
            if pp is None:          # a crossing, slip, turntable or odd turnout: the track is cut here
                cuts.setdefault(n, cut_reason(n))
                key = f"END:{n}:{ty}"
                known = seg_pts(seg)[0]        # a part with no position: the end sits where its track last was known
                cut_ends[key] = list(cut_point(n, ty) or (known[-1] if known else (0.0, 0.0)))
                return (key, "E"), px, blocks, dashed
            nxt = [x for x in (pp.get("connect1name"), pp.get("connect2name")) if x and x != seg.get("ident")]
            if nxt and nxt[0] not in segs:      # the export names a track piece it does not hold: the track ends here
                dangling.add(n)
                nxt = []
            if pp.get("type") == "END_BUMPER" or not nxt:
                end_dir["END:" + n] = facing(seg, n)
                return ("END:" + n, "E"), px, blocks, dashed
            frm, seg = n, segs[nxt[0]]
            walked.add(seg.get("ident"))
            px += seg_px(seg)
            dashed = dashed or seg.get("dashed") == "yes"
            if seg.get("blockname") != blocks[-1]:
                blocks.append(seg.get("blockname"))

    seen = set()
    for s in segs.values():
        for n, ty in ends_of(s):
            if not ty.startswith("TURNOUT") or (n, ty[-1]) not in portmap or portmap[(n, ty[-1])] in seen:
                continue
            start = portmap[(n, ty[-1])]
            (v, vp), px, blocks, dashed = follow(s, n)
            seen.update((start, (v, vp)))
            if v in cut_ends:
                nodes[v] = dict(kind="end", sub="cut", label="", xy=cut_ends[v])
            elif v.startswith("END:"):
                ex, ey = float(pps[v[4:]].get("x")), float(pps[v[4:]].get("y"))
                nodes[v] = dict(kind="end", sub="bumper", label="", xy=[ex, ey])
            district = collections.Counter(b for b in blocks if b).most_common(1)
            district = district[0][0].split("_", 2)[-1] if district else ""
            edges.append(dict(u=start[0], up=start[1], v=v, vp=vp, names=[], cm=px, link=False,
                              main=main_section in district, district=district, hidden=dashed))

    # two track ends on the same spot are one track drawn in two pieces: join them
    ends = [n for n, d in nodes.items() if d["kind"] == "end" and d.get("sub") != "cut"]
    joined = 0
    for i, a in enumerate(ends):
        for b in ends[i + 1:]:
            if a in nodes and b in nodes and math.dist(nodes[a]["xy"], nodes[b]["xy"]) < 1.5 * PX_PER_CM:
                ea = next(e for e in edges if e["v"] == a)
                eb = next(e for e in edges if e["v"] == b)
                edges.remove(eb)
                ea.update(v=eb["u"], vp=eb["up"], cm=ea["cm"] + eb["cm"], hidden=ea["hidden"] or eb["hidden"])
                del nodes[a], nodes[b]
                joined += 1
    # two free ends that face each other across a small gap are one track the plan did not quite snap: join them too
    joins = []
    free = [n for n, d in nodes.items() if d["kind"] == "end" and d.get("sub") != "cut" and end_dir.get(n)]
    near = sorted((math.dist(nodes[a]["xy"], nodes[b]["xy"]), a, b) for i, a in enumerate(free) for b in free[i + 1:]
                  if math.dist(nodes[a]["xy"], nodes[b]["xy"]) <= NEAR_CM * PX_PER_CM)

    def toward(n, m):
        """Does the track at end n head at end m, within NEAR_ANGLE degrees?"""
        d = unit(nodes[m]["xy"][0] - nodes[n]["xy"][0], nodes[m]["xy"][1] - nodes[n]["xy"][1])
        return end_dir[n][0] * d[0] + end_dir[n][1] * d[1] >= math.cos(math.radians(NEAR_ANGLE))

    for gap, a, b in near:
        if a in nodes and b in nodes and toward(a, b) and toward(b, a):
            ea = next(e for e in edges if e["v"] == a)
            eb = next(e for e in edges if e["v"] == b)
            edges.remove(eb)
            ea.update(v=eb["u"], vp=eb["up"], cm=ea["cm"] + eb["cm"] + gap, hidden=ea["hidden"] or eb["hidden"])
            joins.append(dict(gap_cm=round(gap / PX_PER_CM, 1), xy=[round(c, 1) for c in nodes[a]["xy"]]))
            del nodes[a], nodes[b]
    only = bool(skip) and skip.startswith("+")       # "+Name" keeps only those sections; "Name" leaves them out
    if skip:
        text = skip.lstrip("+")
        drop = {n for n, d in nodes.items() if d["kind"] != "end" and (text in d.get("district", "")) != only}
        edges = [e for e in edges if e["u"] not in drop and e["v"] not in drop and (text in e["district"]) == only]
        nodes = {n: d for n, d in nodes.items() if n not in drop}
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        parent[find(e["u"])] = find(e["v"])
    size = collections.Counter(find(n) for n, d in nodes.items() if d["kind"] != "end")
    if not size:
        raise PlanError(f"no switches left after the section filter {skip!r}" if skip else "the export has no switches")
    keep = {g for g in size if any(find(e["u"]) == g for e in edges)}       # every piece with a switch and some track
    nodes = {n: d for n, d in nodes.items() if find(n) in keep}
    edges = [e for e in edges if e["u"] in nodes]
    order = sorted((n for n, d in nodes.items() if d["kind"] != "end"), key=lambda n: (nodes[n]["xy"][1], nodes[n]["xy"][0]))
    for i, n in enumerate(order, 1):
        nodes[n]["label"] = str(i)
    notes = [f"joined {joined} pairs of track ends that met"]
    notes += [f"joined two track ends {j['gap_cm']} cm apart that face each other" for j in joins]
    px_per_cm = PX_PER_CM
    if parts:           # label junctions with the plan's part numbers and heights
        plan = []
        for i, p in enumerate(parts):
            e = [q for q in p["eps"] if abs(q["x"]) < 5000]
            if len(e) >= 3 and (z_range is None or z_range[0] <= max(q["z"] for q in e) <= z_range[1]):
                plan.append((i, sum(q["x"] for q in e) / len(e), sum(q["y"] for q in e) / len(e), max(q["z"] for q in e)))
        if not plan:
            raise PlanError("no switch parts in parts.json" + (f" within heights {z_range}" if z_range else ""))
        seed = spread([nodes[n]["xy"] for n in order if "xover" not in nodes[n]]) / spread([(u, v) for _, u, v, _ in plan]) / PX_PER_CM
        seed = 1.0 if abs(seed - 1) < SCALE_SEARCH_LIMIT else seed
        mine = [(n, nodes[n]["xy"][0] / PX_PER_CM / seed, nodes[n]["xy"][1] / PX_PER_CM / seed)
                for n in order if "xover" not in nodes[n]]      # a single crossover is two nodes but one part: not matched
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

        for tol in (4, 6, 6, 4):        # the export is not exactly to the plan's scale: refit and rematch
            got = pairs(tol)
            if len(got) < 2 or len({g[5] for g in got}) < 2 or len({g[6] for g in got}) < 2:
                raise PlanError("too few switches line up with parts.json to fit its scale; is it the same plan?")
            sx, ox = fit([g[5] for g in got], [g[3] for g in got])
            sy, oy = fit([g[6] for g in got], [g[4] for g in got])
        mine_xy = {n: (x, y) for n, x, y in mine}
        plan_xy = {i: (u, v) for i, u, v, _ in plan}
        cand = sorted((math.hypot(x - (sx * u + ox), y - (sy * v + oy)), n, i, z)
                      for n, x, y in mine for i, u, v, z in plan)
        used_n, used_i, hits, matched = set(), set(), 0, []
        for dist, n, i, z in cand:          # nearest first, one plan part per junction
            if dist > 10:
                break
            if n in used_n or i in used_i:
                continue
            used_n.add(n)
            used_i.add(i)
            hits += 1
            nodes[n]["label"], nodes[n]["z"] = f"T{i}", round(z, 1)
            matched.append((mine_xy[n], plan_xy[i]))
        px_per_cm = PX_PER_CM * seed * uniform_scale(matched)
        notes.append(f"scale correction {round(sx, 4)} {round(sy, 4)}")
        notes.append(f"matched {hits} of {len(mine)} junctions to plan parts")
        notes.append(f"lengths at {px_per_cm:.4f} px per cm, fitted to the parts" +
                     (f" (export searched at {seed:.3f} times the usual size)" if seed != 1.0 else ""))
    else:
        notes.append(f"lengths at {px_per_cm:.4f} px per cm, the usual export size (no parts to fit it to)")
    for e in edges:     # `cm` held export pixels until the scale was known
        e["cm"] = round(e["cm"] / px_per_cm, 1)
    for i, e in enumerate(edges):
        e["id"] = f"e{i}"
    kinds = collections.Counter(d["kind"] for d in nodes.values())
    notes.append(f"{dict(kinds)} {len(edges)} edges; districts: "
                 f"{dict(collections.Counter(e['district'] for e in edges).most_common())}")
    cut_list = [dict(part=n, reason=r, ends=sum(k.startswith(f"END:{n}:") and k in nodes for k in cut_ends))
                for n, r in sorted(cuts.items())]
    for c in cut_list:
        notes.append(f"track cut at {c['part']}: {c['reason']} ({c['ends']} track ends left)")
    if unplaced:
        notes.append(f"position unknown for {len(unplaced)} track parts the export does not place; "
                     "their track ends where it was last known")
    if dangling:
        notes.append(f"{len(dangling)} track points name a track piece the export does not hold; the track ends there")
    def bare_pieces():
        """Track no switch's track runs over, grouped into pieces by the points they share: [{cm, segments}]."""
        rest = [s for i, s in segs.items() if i not in walked]
        parent = {}

        def root(x):
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for s in rest:
            parent[root(s.get("connect1name"))] = root(s.get("connect2name"))
        pieces = {}
        for s in rest:
            p = pieces.setdefault(root(s.get("connect1name")), dict(cm=0.0, segments=0))
            p["cm"] += seg_px(s) / PX_PER_CM
            p["segments"] += 1
        return [dict(cm=round(p["cm"], 1), segments=p["segments"]) for p in sorted(pieces.values(), key=lambda p: -p["cm"])]

    out = dict(nodes=nodes, edges=edges, notes=notes, cuts=cut_list)
    if joins:
        out["joins"] = joins
    left = bare_pieces()
    if left:
        out["left_out"] = left
        notes += [f"left out: a piece with no switches, {p['cm']} cm of track" for p in left]
    return out
