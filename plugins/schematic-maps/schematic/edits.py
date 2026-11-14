"""Plan overrides applied to a graph (relabel, remove, switch, crossover, move, name, end), the main route, and the cut into levels."""
import collections
import heapq

from .core import SchematicError



def by_label(g, ref):
    """A junction by its plan part number (kept as alias) or its label."""
    hits = [n for n, d in g["nodes"].items() if d.get("alias") == ref]
    hits = hits or [n for n, d in g["nodes"].items() if d.get("label") == ref and d["kind"] != "end"]
    # a moved switch is labelled with a star (7*); its plain number still finds it
    hits = hits or [n for n, d in g["nodes"].items() if (d.get("label") or "").rstrip("*") == ref and d["kind"] != "end"]
    if len(hits) != 1:
        raise SchematicError(f"{len(hits)} junctions answer to {ref}")
    return hits[0]


def edge_at(g, n, port):
    return next(e for e in g["edges"] if (e["u"], e["up"]) == (n, port) or (e["v"], e["vp"]) == (n, port))


def far(e, n, port):
    return (e["v"], e["vp"]) if (e["u"], e["up"]) == (n, port) else (e["u"], e["up"])


def edge_between(g, a, b, port=None, unique=False):
    """The track between switches a and b (leaving a by `port` when given). With several, the longest, or with
    `unique` an error naming both and asking for the leg."""
    n0, n1 = by_label(g, a), by_label(g, b)
    hits = [e for e in g["edges"] if {e["u"], e["v"]} == {n0, n1}
            and (port is None or (e["u"], e["up"]) == (n0, port) or (e["v"], e["vp"]) == (n0, port))]
    if not hits:
        raise SchematicError(f"no track between {a} and {b}" + (f" leaving {a} by leg {port}" if port else ""))
    if unique and len(hits) > 1:
        raise SchematicError(f"{len(hits)} tracks join {a} and {b}; say which leg of {a} the track leaves by (A to D): "
                             "as 'port' on a switch or crossover side, as a third item of `onto`")
    return max(hits, key=lambda e: e["cm"]), n0, n1


def lift(g, x, p1, p2):
    """Take switch x out of the run through ports p1 and p2, leaving plain track there."""
    e1, e2 = edge_at(g, x, p1), edge_at(g, x, p2)
    a, b = far(e1, x, p1), far(e2, x, p2)
    g["edges"] = [e for e in g["edges"] if e is not e1 and e is not e2]
    g["edges"].append(dict(e1, id=e1["id"] + "+" + e2["id"], u=a[0], up=a[1], v=b[0], vp=b[1],
                           cm=round(e1["cm"] + e2["cm"], 1), names=e1["names"] or e2["names"]))


def set_in(g, x, t, n0, cm_from_first, points_toward_first, names=(None, None)):
    """Set switch x into track t (between n0 and its other end): A toward one end, B toward the other."""
    end0 = (t["u"], t["up"]) if t["u"] == n0 else (t["v"], t["vp"])
    end1 = (t["v"], t["vp"]) if t["u"] == n0 else (t["u"], t["up"])
    at = max(5.0, min(cm_from_first, t["cm"] - 5))
    g["edges"].remove(t)
    p0, p1 = ("A", "B") if points_toward_first else ("B", "A")
    g["edges"].append(dict(t, id=t["id"] + "a", u=end0[0], up=end0[1], v=x, vp=p0, cm=round(at, 1),
                           names=[names[0]] if names[0] else t["names"]))
    g["edges"].append(dict(t, id=t["id"] + "b", u=x, up=p1, v=end1[0], vp=end1[1], cm=round(t["cm"] - at, 1),
                           names=[names[1]] if names[1] else t["names"]))


def new_switch(g, label, alias, hand):
    nid = "NEW:" + alias
    g["nodes"][nid] = dict(kind="switch", label=label, alias=alias, hand=1 if hand == "R" else -1,
                           dirs={"A": [-1.0, 0.0], "B": [1.0, 0.0], "C": [1.0, 0.0]})
    return nid


def grow(g, n, port, spec, template, count):
    """Build what hangs off a new switch's leg: a track end, or another switch with its own legs."""
    count[0] += 1
    if "end" in spec:
        end = f"END:new{count[0]}"
        g["nodes"][end] = dict(kind="end", sub=spec.get("sub", "bumper"), label="")
        g["edges"].append(dict(template, id=f"n{count[0]}", u=n, up=port, v=end, vp="E", names=[spec["end"]],
                               cm=spec.get("cm", 60.0), link=False, main=False))
        return
    x = new_switch(g, spec["switch"], spec.get("alias", spec["switch"]), spec["hand"])
    g["edges"].append(dict(template, id=f"n{count[0]}", u=n, up=port, v=x, vp="A", names=[], cm=25.0,
                           link=False, main=False))
    grow(g, x, "B", spec["b"], template, count)
    grow(g, x, "C", spec["c"], template, count)


SOURCES = ("le_panel", "owner", "plan")


def need_hand_and_source(ed, who):
    """R10: a switch the edits add or move comes with its hand and its source, never a trial."""
    if ed.get("hand") not in ("R", "L"):
        raise SchematicError(f"switch {who}: no hand. Give 'hand': 'R' or 'L' in the plan overrides (read it from the "
                             "Layout Editor panel or the railroad); the tool does not try both")
    if ed.get("source") not in SOURCES:
        raise SchematicError(f"switch {who}: no source. Give 'source' as one of {', '.join(SOURCES)}")


def apply_edits(g, edits):
    """As-built changes and names on top of the plan."""
    N = g["nodes"]
    counter = [0]
    for ed in edits:
        op = ed["op"]
        if op == "relabel":         # plan part number -> the railroad's switch number
            for old, new in ed["map"].items():
                n = by_label(g, old)
                N[n]["alias"], N[n]["label"] = old, new
        elif op == "remove":        # switches that were not built: their straight route stays as track
            gone = [by_label(g, r) for r in ed["switches"]]
            for x in gone:
                c = next((e for e in g["edges"] if (e["u"], e["up"]) == (x, "C") or (e["v"], e["vp"]) == (x, "C")), None)
                if c is not None:
                    g["edges"].remove(c)
                    o = far(c, x, "C")[0]
                    if N[o]["kind"] == "end":
                        del N[o]
            for x in gone:
                lift(g, x, "A", "B")
                del N[x]
        elif op == "move":          # lift a switch out of one run and set it into another
            need_hand_and_source(ed, ed["switch"])
            x = by_label(g, ed["switch"])
            p1, p2 = ed["through"]
            leg = next(p for p in "ABC" if p not in (p1, p2))
            e3 = edge_at(g, x, leg)
            lift(g, x, p1, p2)
            if (e3["u"], e3["up"]) == (x, leg):
                e3["up"] = "C"
            else:
                e3["vp"] = "C"
            t, n0, _ = edge_between(g, *ed["onto"], unique=True)
            set_in(g, x, t, n0, ed["cm_from_first"], False)
            d = N[x]
            d["hand"] = {"R": 1, "L": -1}.get(ed.get("hand"), d["hand"])
            d["z"] = ed.get("z", d.get("z"))
            d["dirs"] = {"A": [-1.0, 0.0], "B": [1.0, 0.0], "C": [1.0, 0.0]}
            d["label"] += "*"
        elif op == "switch":        # a switch that is not in the plan, with whatever hangs off its diverging leg
            need_hand_and_source(ed, ed["label"])
            x = new_switch(g, ed["label"], ed.get("alias", ed["label"]), ed["hand"])
            t, n0, _ = edge_between(g, *ed["on"], ed.get("port"), unique=True)
            set_in(g, x, t, n0, ed["cm_from_first"], ed["points_toward"] == ed["on"][0], ed.get("names", (None, None)))
            grow(g, x, "C", ed["c"], t, counter)
        elif op == "crossover":     # two new switches joined by their diverging legs
            need_hand_and_source(ed, ed["label"])
            ids = []
            for k, side in enumerate(ed["sides"]):
                x = new_switch(g, ed["label"], ed["label"] + "ab"[k], ed["hand"])
                t, n0, _ = edge_between(g, *side["on"], side.get("port"), unique=True)
                set_in(g, x, t, n0, side["cm_from_first"], side["points_toward"] == side["on"][0],
                       side.get("names", (None, None)))
                ids.append(x)
            g["edges"].append(dict(id="x" + ed["label"], u=ids[0], up="C", v=ids[1], vp="C", names=[], cm=0.0,
                                   main=False, link=True))
        elif op == "name":          # track names, and which tracks are main
            for a, b, name, *rest in ed["tracks"]:
                t, n0, _ = edge_between(g, a, b, rest[0] if rest and rest[0] in "ABC" else None)
                names = name if isinstance(name, list) else ([name] if name else [])
                t["names"] = names if t["u"] == n0 else names[::-1]
                t["main"] = "main" in rest
        elif op == "flip":          # draw these switches' diverging side the other way up (schematic licence)
            for ref in ed["switches"]:
                N[by_label(g, ref)]["hand"] *= -1
                N[by_label(g, ref)]["flipped"] = True
        elif op == "end":           # what a track end is: found from the switch and port it hangs off
            for ref, port, name, sub, to in ed["ends"]:
                n = by_label(g, ref)
                t = edge_at(g, n, port)
                e = far(t, n, port)[0]
                t["names"], t["main"] = [name], t.get("main", False) or sub == "helix"
                N[e].update(sub=sub, to=to)
        else:
            raise SchematicError(f"unknown edit {op}")


def mark_main(g, routes):
    """Main track is what lies on the given routes (shortest way between each pair); everything else is secondary."""
    N = g["nodes"]

    def node(ref):
        for e in g["edges"]:
            for n in (e["u"], e["v"]):
                if N[n]["kind"] == "end" and (ref in e["names"] or N[n].get("label") == ref):
                    return n
        return by_label(g, ref)

    adj = collections.defaultdict(list)
    for e in g["edges"]:
        adj[e["u"]].append((e["v"], e))
        adj[e["v"]].append((e["u"], e))
        e["main"] = False
    for a, b, *how in routes:
        a, b = node(a), node(b)
        if how:                 # "direct": every track that runs straight between the two, however long
            for e in g["edges"]:
                if {e["u"], e["v"]} == {a, b}:
                    e["main"] = True
            continue
        dist, prev, heap = {a: 0.0}, {}, [(0.0, a)]
        while heap:
            d, n = heapq.heappop(heap)
            if n == b:
                break
            if d > dist[n]:
                continue
            for m, e in adj[n]:
                nd = d + e["cm"] + 1
                if nd < dist.get(m, 1e18):
                    dist[m], prev[m] = nd, (n, e)
                    heapq.heappush(heap, (nd, m))
        while b in prev:
            b, e = prev[b]
            e["main"] = True


def split_levels(g, spec):
    """Cut every run that joins two levels; each cut end becomes a lettered connector."""
    N = g["nodes"]
    z = {n: d.get("z") for n, d in N.items() if d["kind"] != "end"}
    for ref, to in spec.get("assign", {}).items():      # owner's choice of band for a junction
        z[by_label(g, ref)] = to
    for lo, hi, to in spec.get("treat", []):
        for n, v in z.items():
            if v is not None and lo <= v < hi:
                z[n] = to
    while any(v is None for v in z.values()):       # unknown height: take the nearest neighbour's
        progress = False
        for e in sorted(g["edges"], key=lambda e: e["cm"]):
            for a, b in ((e["u"], e["v"]), (e["v"], e["u"])):
                if a in z and b in z and z[a] is None and z[b] is not None:
                    z[a], progress = z[b], True
        if not progress:
            break
    names = spec["bands"]
    level = {n: next(i for i, b in enumerate(names) if (v if v is not None else 0) < b["below"]) for n, v in z.items()}
    letters = iter("ABCDEFGHJKLMNPQRSTUVWXYZ")
    for e in list(g["edges"]):
        if e["u"] in level and e["v"] in level and level[e["u"]] != level[e["v"]]:
            L = next(letters)
            g["edges"].remove(e)
            for k, (n, p) in enumerate(((e["u"], e["up"]), (e["v"], e["vp"]))):
                end = f"LINK:{L}{k}"
                other = e["v"] if k == 0 else e["u"]
                N[end] = dict(kind="end", sub="link", label=L, to=names[level[other]]["name"].split(",")[0])
                g["edges"].append(dict(e, id=f"{e['id']}{'xy'[k]}", u=n, up=p, v=end, vp="E", cm=round(e["cm"] / 2, 1)))
    parent = {n: n for n in N}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in g["edges"]:
        parent[find(e["u"])] = find(e["v"])
    groups = collections.defaultdict(list)
    for n in N:
        groups[find(n)].append(n)
    bands = []
    for members in groups.values():
        lv = collections.Counter(level[n] for n in members if n in level).most_common(1)[0][0]
        keep = set(members)
        bands.append((lv, len(members), names[lv]["name"],
                      dict(nodes={n: N[n] for n in members}, edges=[e for e in g["edges"] if e["u"] in keep])))
    bands.sort(key=lambda b: (b[0], -b[1]))
    return [(name, sub) for _, _, name, sub in bands]


