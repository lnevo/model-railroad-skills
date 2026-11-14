"""Panel reader: a JMRI Layout Editor panel to the same logical graph the plan reader makes.

The panel is the as-built record: switch hands and legs, track ends, and (through the anchors it passes)
where masts stand. It is not to scale, so lengths come from the block lengths the reader supplies.

Graph:
  nodes: id -> {kind: switch, hand: +1 (C on the right of travel A->B, screen coordinates) / -1,
                label, xy, dirs: {port: [dx, dy]}}  |  {kind: end, sub: bumper, label}
  edges: [{id, u, up, v, vp, names, cm, main, link, anchors}]   ports: A points, B normal, C reverse, E end
Each edge also lists the anchors it passes ("anchors": [ident, cm from u, the segment on u's side, the
segment on v's side]), so masts on block boundaries can be found on it. A double crossover is two switches
(ident + "a", ident + "b") joined by a link edge.
"""
import csv

import xml.etree.ElementTree as ET

from .plan_reader import PlanError, cross, unit


def load_numbers(path):
    """Switch numbers by Layout Editor ident, from a CSV with the columns le_ident and switch."""
    return {r["le_ident"]: r["switch"] for r in csv.DictReader(open(path, newline=""))}


def load_lengths(path):
    """Block lengths in inches by block user name, from a CSV with the columns user_name and inches."""
    return {r["user_name"]: float(r["inches"]) for r in csv.DictReader(open(path, newline="")) if r["inches"]}


def find_panel(root, name=None):
    """The panel to read: the one called `name`, or the first that is not JMRI's generated Dispatcher panel."""
    panels = [p for p in root.iter("LayoutEditor") if (p.get("name") == name if name else p.get("name") != "Dispatcher System")]
    if not panels:
        raise PlanError("no Layout Editor panel found" + (f" called {name}" if name else ""))
    return panels[0]


def read(tables, numbers=None, lengths=None, panel_name=None):
    """The panel's logical graph. `numbers` maps a turnout's ident to the railroad's switch number, `lengths`
    maps a block's user name to its length in inches (a missing block counts as zero)."""
    root = ET.parse(tables).getroot()
    panel = find_panel(root, panel_name)
    number = numbers or {}
    inches = lengths or {}

    tos = {t.get("ident"): t for t in panel.iter("layoutturnout")}
    segs = {s.get("ident"): s for s in panel.iter("tracksegment")}
    pps = {p.get("ident"): p for p in panel.iter("positionablepoint")}

    nodes, portmap = {}, {}  # portmap: (LE ident, LE leg) -> (node, port)
    edges = []

    def pt(t, leg):
        return (float(t.get("x" + leg.lower())), float(t.get("y" + leg.lower())))

    def add_switch(nid, label, pa, pb, pc):
        """pa, pb, pc: screen points of the points end, normal leg, reverse leg."""
        c = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
        travel = (pb[0] - pa[0], pb[1] - pa[1])
        hand = 1 if cross(travel, (pc[0] - pa[0], pc[1] - pa[1])) > 0 else -1
        nodes[nid] = dict(kind="switch", hand=hand, label=label, xy=list(c), dirs={
            "A": unit(pa[0] - c[0], pa[1] - c[1]), "B": unit(pb[0] - c[0], pb[1] - c[1]),
            "C": unit(pc[0] - c[0], pc[1] - c[1])})

    for ident, t in tos.items():
        ty, label = t.get("type"), number.get(ident, ident)
        if ty in ("LH_TURNOUT", "RH_TURNOUT", "WYE_TURNOUT"):
            add_switch(ident, label, pt(t, "A"), pt(t, "B"), pt(t, "C"))
            for leg in "ABC":
                portmap[(ident, leg)] = (ident, leg)
        elif ty == "DOUBLE_XOVER":      # tracks A-B and D-C, both crossings; A and D are the mirrors of C and B
            b, c = pt(t, "B"), pt(t, "C")
            mid = (float(t.get("xcen")), float(t.get("ycen")))
            a, d = (2 * mid[0] - c[0], 2 * mid[1] - c[1]), (2 * mid[0] - b[0], 2 * mid[1] - b[1])
            nodes[ident] = dict(kind="dx", label=label, xy=list(mid),
                                hand=1 if cross((b[0] - a[0], b[1] - a[1]), (d[0] - a[0], d[1] - a[1])) > 0 else -1,
                                dirs={k: unit(p[0] - mid[0], p[1] - mid[1]) for k, p in zip("ABCD", (a, b, c, d))})
            for leg in "ABCD":
                portmap[(ident, leg)] = (ident, leg)
        elif ty in ("RH_XOVER", "LH_XOVER"):
            # tracks A-B and D-C; RH joins A to C, LH joins B to D
            a, b, c, d = (pt(t, leg) for leg in "ABCD")
            if ty == "RH_XOVER":   # top: points A, normal B; bottom: points C, normal D
                top, bot = ("A", "B", a, b, c), ("C", "D", c, d, a)
            else:                  # top: points B, normal A; bottom: points D, normal C
                top, bot = ("B", "A", b, a, d), ("D", "C", d, c, b)
            for half, (pl, nl, pp_, np_, far) in (("a", top), ("b", bot)):
                nid = ident + half
                mid = ((pp_[0] + np_[0]) / 2, (pp_[1] + np_[1]) / 2)
                add_switch(nid, label, pp_, np_, ((mid[0] + far[0]) / 2, (mid[1] + far[1]) / 2))
                portmap[(ident, pl)] = (nid, "A")
                portmap[(ident, nl)] = (nid, "B")
            edges.append(dict(u=ident + "a", up="C", v=ident + "b", vp="C", names=[], cm=0.0,
                              main=False, link=True))
        else:
            raise PlanError(f"unsupported turnout type {ty} at {ident}")

    def ends_of(s):
        return [(s.get("connect1name"), s.get("type1")), (s.get("connect2name"), s.get("type2"))]

    def follow(seg, frm):
        """Walk from turnout frm along seg to the next turnout or track end."""
        blocks, main_ = [seg.get("blockname")], [seg.get("mainline") == "yes"]
        passed = []
        while True:
            n, ty = next(e for e in ends_of(seg) if e[0] != frm)
            if ty.startswith("TURNOUT"):
                return portmap[(n, ty[-1])], blocks, main_, passed
            pp = pps[n]
            if pp.get("type") == "END_BUMPER":
                return ("END:" + n, "E"), blocks, main_, passed
            nxt = [x for x in (pp.get("connect1name"), pp.get("connect2name")) if x and x != seg.get("ident")]
            if not nxt:
                return ("END:" + n, "E"), blocks, main_, passed
            passed.append([n, round(sum(inches.get(b, 0) for b in blocks if b) * 2.54, 1), seg.get("ident"), nxt[0]])
            frm, seg = n, segs[nxt[0]]
            if seg.get("blockname") != blocks[-1]:
                blocks.append(seg.get("blockname"))
            main_.append(seg.get("mainline") == "yes")

    seen = set()
    for s in segs.values():
        for n, ty in ends_of(s):
            if not ty.startswith("TURNOUT"):
                continue
            start = portmap[(n, ty[-1])]
            if start in seen:
                continue
            (v, vp), blocks, main_, passed = follow(s, n)
            seen.add(start)
            seen.add((v, vp))
            if v.startswith("END:"):
                nodes[v] = dict(kind="end", sub="bumper", label="")
            names = [b for b in blocks if b and not b.startswith("OS ")]
            cm = sum(inches.get(b, 0) for b in blocks if b) * 2.54
            edges.append(dict(u=start[0], up=start[1], v=v, vp=vp, names=names, cm=round(cm, 1),
                              main=sum(main_) * 2 > len(main_), link=False, anchors=passed))
    for i, e in enumerate(edges):
        e["id"] = f"e{i}"
    return dict(nodes=nodes, edges=edges)

