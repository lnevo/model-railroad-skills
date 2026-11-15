"""Where a generated Layout Editor panel's mast icons stand: gantries, and spots clear of turnouts and other icons.

    G = le_masts.gantries(P, bands, ix)     # slide boundary anchors so one control point's masts form a column
    le_masts.icons(P, slots.Index(le.to_xml(P, "probe")), G)     # each icon in its clearest spot

The CATS rules (references/cats-signals.md) carried over to Layout Editor (references/le-panel.md). There a mast's
slot is fixed by JMRI (an anchor, an end bumper or a turnout leg) and its icon is an image placed anywhere, so:

Gantries. Masts of one control point (the band's `control_points` entry holding the switch the mast governs, found
by following its protected track to the first turnout; else that switch alone) that govern the same direction and
stand within GANTRY_SPAN columns of each other form a gantry. Their boundary anchors slide along their own straight
track, between the same two blocks, so the boundaries stand in one column (one x): the mast keeps its slot and its
facing and protected blocks, and the panel keeps its width. An anchor moves at most GANTRY_SHIFT columns, never past
the next point on its track, and each block keeps at least a column of track (and the room for the icon on the side
the train comes from). A mast in a turnout leg or an end bumper cannot move; it still counts toward the column, so
anchors line up with it when they can reach it. An anchor holding masts of two gantries stays where it is. The column
is the one most masts reach, then the one with the least movement.

Icons. Each icon stays on the right-hand side of the train, turned to its direction of travel (on a slope, along the
slope), before its boundary. The spots tried are GAP pixels from the rail (the icon's middle about 10 pixels out for
a dwarf) or touching it, from GAP pixels before the boundary back along the straight track before it, ICON_STEP
pixels at a time. Each spot is scored (ICON_COST) and the cheapest taken: over a turnout's legs or its control
circle (which takes the clicks that throw it), nearer another track than its own (it would read as that track's
mast), a track line through it, over another icon, a label or a shape; touching a line; and the distance back. A
touching spot costs less than reading as another track's mast. A gantry's icons take one spot when it is clean for
all of them, so they stand in one line.
"""
import math
from collections import defaultdict

from . import slots
from .core import SchematicError

GANTRY_SHIFT = 3        # columns an anchor may slide along its track to line masts up (as cats.GANTRY_SHIFT)
GANTRY_SPAN = 1.5       # masts of one control point and direction this many columns apart form a gantry
ICON_STEP = 2           # px between the spots tried back along the track
ICON_BACK = 40          # px an icon may stand further back than GAP
TOUCH = 1.5             # px from the rail to the icon's near side in the touching spot
WIDE = 2 * slots.GAP    # px from the rail to the icon's near side in the spot further out (2 GAP), for a curve
TURNOUT_R = 8           # px around a turnout's centre: its control circle, where a click throws it
CLEAR = (1, 3)          # px from an icon to a track line's middle: through it, touching it
ICON_COST = {"turnout": 20, "other": 15, "ink": 10, "mast": 10, "label": 10, "graze": 4, "wide": 3}
HARD = {"turnout", "other", "ink", "mast", "label"}
ICON_PER_PX = 1 / 8     # per px the icon stands further back than GAP
OVERLAP = 0.5           # px two boxes must be apart not to overlap
NEAR = 90               # px around a boundary within which lines, turnouts and labels are scored
EPS = 1e-6


# ---------------------------------------------------------------- geometry

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _pt_seg(p, a, b):
    v = _sub(b, a)
    n = _dot(v, v)
    t = 0.0 if n < EPS else max(0.0, min(1.0, _dot(_sub(p, a), v) / n))
    return math.dist(p, (a[0] + t * v[0], a[1] + t * v[1]))


def _seg_box_gap(a, b, hx, hy):
    """Distance from segment ab to the box [-hx, hx] x [-hy, hy] (0 when they meet)."""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    meets = True
    for p_, q_ in ((-dx, a[0] + hx), (dx, hx - a[0]), (-dy, a[1] + hy), (dy, hy - a[1])):
        if abs(p_) < EPS:
            if q_ < 0:
                meets = False
                break
            continue
        r = q_ / p_
        if p_ < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            meets = False
            break
    if meets:
        return 0.0
    box = lambda p: math.hypot(max(abs(p[0]) - hx, 0), max(abs(p[1]) - hy, 0))     # noqa: E731
    return min(box(a), box(b), *(_pt_seg((sx * hx, sy * hy), a, b) for sx in (-1, 1) for sy in (-1, 1)))


class Rect:
    """A turned rectangle: centre c, unit u along its length (half ha), half hw across."""

    def __init__(self, c, u, ha, hw):
        self.c, self.u, self.ha, self.hw = c, u, ha, hw
        self.n = (-u[1], u[0])

    def local(self, p):
        v = _sub(p, self.c)
        return (_dot(v, self.u), _dot(v, self.n))

    def gap_seg(self, a, b):
        return _seg_box_gap(self.local(a), self.local(b), self.ha, self.hw)

    def gap_point(self, p):
        x, y = self.local(p)
        return math.hypot(max(abs(x) - self.ha, 0), max(abs(y) - self.hw, 0))

    def overlaps(self, o, margin=OVERLAP):
        d = _sub(o.c, self.c)
        for ax in (self.u, self.n, o.u, o.n):
            r1 = abs(_dot(ax, self.u)) * self.ha + abs(_dot(ax, self.n)) * self.hw
            r2 = abs(_dot(ax, o.u)) * o.ha + abs(_dot(ax, o.n)) * o.hw
            if abs(_dot(d, ax)) >= r1 + r2 + margin:
                return False
        return True


def label_rect(lb, x=None):
    w = 0.6 * lb["size"] * len(lb["text"])
    x = lb["xy"][0] if x is None else x
    return Rect((x + w / 2, lb["xy"][1] + lb["size"] / 2), (1.0, 0.0), w / 2, lb["size"] / 2)


def icon_rect(p, d, size, back, across):
    deg = slots.icon_degrees(d)
    th = math.radians(deg)
    w, h = size
    return Rect(slots.icon_centre(p, d, size, back, across), (math.sin(th), -math.cos(th)), h / 2, w / 2)


# ---------------------------------------------------------------- the panel as lines

class World:
    """The drawn panel for scoring: track lines by segment, turnout bodies, labels and shapes."""

    def __init__(self, P):
        self.turnout = {t["ident"]: t for t in P.turnouts}
        self.track = {}             # segment ident -> [(a, b)] straight pieces as drawn
        for s in P.segments:
            if s["hidden"]:
                continue
            if s["arc"]:
                q = s["arc"]["drawn"]
                self.track[s["ident"]] = list(zip(q, q[1:]))
            else:
                self.track[s["ident"]] = [tuple(self.xy(P, e) for e in s["ends"])]
        self.bodies = {}            # turnout ident -> (centre, [(a, b)]) as Layout Editor draws it
        for t in P.turnouts:
            p = {k: tuple(v) for k, v in t["pts"].items()}
            cen = tuple(t["cen"])
            if t["type"] in ("RH_XOVER", "LH_XOVER"):
                lines = [(p["A"], p["B"]), (p["D"], p["C"]),
                         (_mid(p["A"], p["B"]), _mid(p["D"], p["C"]))]
            elif t["type"] == "DOUBLE_XOVER":
                lines = [(p["A"], p["B"]), (p["D"], p["C"]), (p["A"], p["C"]), (p["B"], p["D"])]
            else:
                lines = [(cen, p[k]) for k in "ABC" if k in p]
            self.bodies[t["ident"]] = (cen, lines)
        # a track's name is left out: it slides along its track out of the icons' way afterwards (names_yield)
        self.labels = [label_rect(lb) for lb in P.labels if "run" not in lb]
        self.shapes = [(tuple(sh["centre"]), sh["r"]) for sh in P.shapes]

    def xy(self, P, end):
        return end_xy(P, self.turnout, end)

    def near(self, p, r=NEAR):
        """(track {seg: pieces}, bodies {turnout: body}, labels, shapes) within r px of p."""
        close = lambda a, b: _pt_seg(p, a, b) <= r       # noqa: E731
        track = {k: v for k, v in self.track.items() if any(close(a, b) for a, b in v)}
        bodies = {k: v for k, v in self.bodies.items() if math.dist(p, v[0]) <= r + 30}
        labels = [lb for lb in self.labels if math.dist(p, lb.c) <= r + lb.ha]
        shapes = [s for s in self.shapes if math.dist(p, s[0]) <= r + s[1]]
        return track, bodies, labels, shapes


def end_xy(P, turnouts, end):
    """The panel point of a track end (ident, type): a point's place or a turnout's leg."""
    ident, typ = end
    if typ == "POS_POINT":
        return tuple(P.points[ident]["xy"])
    return tuple(turnouts[ident]["pts"][typ[-1]])


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


# ---------------------------------------------------------------- gantries

def _labels_of(P, bands):
    out = {}
    for t in P.turnouts:
        nodes = bands[t["band"]][1]["nodes"]
        out[t["ident"]] = sorted({(nodes[n].get("label") or n).rstrip("*") for n in t["nodes"]})
    return out


def _governs(ix, m):
    """The turnout ident a mast governs: its own, or the first one along its protected track; None at a buffer stop,
    a join or the end of the track."""
    if m["kind"] == "turnout":
        return m["ident"]
    if m["kind"] != "anchor":
        return None
    seg = ix.point_tracks(m["ident"], m["slot"])[1]
    here = m["ident"]
    for _ in range(len(ix.segs) + 1):
        s = ix.segs.get(seg)
        if s is None or s.get("hidden") == "yes":
            return None
        ends = [(s.get("connect1name"), s.get("type1")), (s.get("connect2name"), s.get("type2"))]
        name, typ = ends[1] if ends[0][0] == here else ends[0]
        if typ and typ.startswith("TURNOUT_"):
            return name
        p = ix.points.get(name)
        if p is None or p.get("type") != "ANCHOR" or not p.get("connect2name"):
            return None
        seg = p.get("connect2name") if p.get("connect1name") == seg else p.get("connect1name")
        here = name
    return None


def _way(d):
    if abs(d[0]) >= 0.3:
        return "east" if d[0] > 0 else "west"
    return "south" if d[1] > 0 else "north"


def _slide(P, ident, cell, need):
    """(a, unit, s, lo, hi) for an anchor that may slide along the straight line through it: a and the unit are the
    line from the far end of one of its tracks to the far end of the other, s the anchor's place on it, lo and hi
    how far it may go; None when it may not (an arc, a hidden track, a bend). `need` {segment: px} is the room an
    icon needs on that side."""
    pt = P.points[ident]
    if pt["type"] != "ANCHOR" or len(pt["conn"]) != 2:
        return None
    segs = {s["ident"]: s for s in P.segments if s["ident"] in pt["conn"]}
    if any(s["arc"] or s["hidden"] for s in segs.values()):
        return None
    turnouts = {t["ident"]: t for t in P.turnouts}
    far = []
    for sid in pt["conn"]:
        s = segs[sid]
        end = s["ends"][1] if s["ends"][0] == (ident, "POS_POINT") else s["ends"][0]
        far.append((sid, end_xy(P, turnouts, end)))
    (s1, a), (s2, b) = far
    L = math.dist(a, b)
    if L < EPS:
        return None
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    m = tuple(pt["xy"])
    if abs(u[0] * (m[1] - a[1]) - u[1] * (m[0] - a[0])) > 0.5:
        return None
    s = _dot(_sub(m, a), u)
    lo = min(s, max(cell, need.get(s1, 0)))
    hi = max(s, L - max(cell, need.get(s2, 0)))
    shift = GANTRY_SHIFT * cell
    return a, u, s, max(lo, s - shift), min(hi, s + shift)


def gantries(P, bands, ix):
    """Slide the boundary anchors of each gantry into one column (module text). Returns the gantries: lists of
    P.masts entries that stand in one column. Every mast keeps its slot and its facing and protected blocks."""
    labels = _labels_of(P, bands)
    cp_of = {}
    for bi, (_, _, opts) in enumerate(bands):
        for name, cp in ((opts or {}).get("control_points") or {}).items():
            for sw in cp.get("switches", ()):
                cp_of[(bi, str(sw).rstrip("*"))] = name
    before = {m["mast"]: ix.blocks(m["kind"], m["ident"], m["slot"]) for m in P.masts}
    groups = defaultdict(list)
    world = World(P)
    for m in P.masts:
        p, d = ix.travel(m["kind"], m["ident"], m["slot"])
        m["_p"], m["_d"] = p, d
        tid = _governs(ix, m)
        if tid is None:
            continue
        cp = next((cp_of[(m["band"], lb)] for lb in labels[tid] if (m["band"], lb) in cp_of),
                  "switch " + "/".join(labels[tid]))
        groups[(m["band"], cp, _way(d))].append(m)
    clusters = []
    for key in sorted(groups, key=str):
        members = sorted(groups[key], key=lambda m: (m["_p"][0], m["mast"]))
        span = GANTRY_SPAN * P.cellx[key[0]]
        run = [members[0]]
        for a, b in zip(members, members[1:]):
            if b["_p"][0] - a["_p"][0] > span:
                clusters.append((key, run))
                run = []
            run.append(b)
        clusters.append((key, run))
    cluster_of = {}
    for i, (_, cl) in enumerate(clusters):
        for m in cl:
            cluster_of[m["mast"]] = i
    on_anchor = defaultdict(list)
    for m in P.masts:
        if m["kind"] == "anchor":
            on_anchor[m["ident"]].append(m)
    out = []
    for i, (key, cl) in enumerate(clusters):
        if len(cl) < 2:
            continue
        cell = P.cellx[key[0]]
        reach = {}
        for m in cl:
            slide = None
            if m["kind"] == "anchor" and all(cluster_of.get(q["mast"]) == i for q in on_anchor[m["ident"]]):
                need = {}
                for q in on_anchor[m["ident"]]:
                    seg = ix.point_tracks(q["ident"], q["slot"])[0]
                    need[seg] = max(need.get(seg, 0), 2 * slots.GAP + q["size"][1])
                slide = _slide(P, m["ident"], cell, need)
                if slide and abs(slide[1][0]) < 0.3:        # too steep to line up across the panel
                    slide = None
            if slide:
                a, u, s, lo, hi = slide
                xs = sorted((a[0] + u[0] * lo, a[0] + u[0] * hi))
                reach[m["mast"]] = (xs[0], xs[1], slide)
            else:
                reach[m["mast"]] = (m["_p"][0], m["_p"][0], None)
        cols = {v for r in reach.values() for v in (r[0], r[1])} | {m["_p"][0] for m in cl}
        for lo, hi, slide in reach.values():
            if slide:
                cols |= {lo + k * ICON_STEP for k in range(int((hi - lo) / ICON_STEP) + 1)}
        near = {m["mast"]: world.near(m["_p"], NEAR + m["size"][1] + GANTRY_SHIFT * cell) for m in cl
                if reach[m["mast"]][2]}

        def unclean(m, col):
            """Would the icon of a sliding mast, in its first spot with its boundary in column col, touch
            anything (track, a turnout, a label)?"""
            a, u, _s, _lo, _hi = reach[m["mast"]][2]
            p = (col, a[1] + u[1] * (col - a[0]) / u[0])
            r = icon_rect(p, m["_d"], m["size"], slots.GAP, slots.GAP)
            return bool(spot_cost(r, near[m["mast"]], set(P.points[m["ident"]]["conn"]), set(), [])[1])

        def score(col):
            got = [m for m in cl if reach[m["mast"]][0] - 0.05 <= col <= reach[m["mast"]][1] + 0.05]
            bad = sum(unclean(m, col) for m in got if reach[m["mast"]][2])
            return (-len(got), bad, round(sum(abs(col - m["_p"][0]) for m in got), 3), col), got
        (neg, _, _, col), got = min((score(c) for c in sorted(cols)), key=lambda t: t[0])
        if -neg < 2:
            continue
        for m in got:
            slide = reach[m["mast"]][2]
            if slide is None or abs(col - m["_p"][0]) < 0.05:
                continue
            a, u, _s, _lo, _hi = slide
            new = (col, a[1] + u[1] * (col - a[0]) / u[0])
            moved = math.dist(new, P.points[m["ident"]]["xy"])
            P.points[m["ident"]]["xy"] = [new[0], new[1]]
            P.log.append(f"{bands[key[0]][0]}: mast {m['mast']}: its boundary moved {moved:.0f} px along its track, "
                         f"into the gantry of {key[1]} {key[2]} bound")
            P.anchors_moved.append((m["mast"], m["ident"], round(moved, 1)))
        if len(got) < len(cl):
            P.log.append(f"{bands[key[0]][0]}: masts {', '.join(m['mast'] for m in cl if m not in got)} could not "
                         f"join the gantry of {', '.join(m['mast'] for m in got)}")
        out.append(got)
    # an anchor standing alone (in no gantry) slides too, the least it must, when its icon's first spot is not clean
    # where it stands, as a lone CATS mast moves out of a switch's cell
    in_gantry = {m["mast"] for g in out for m in g}
    for ident, ms in sorted(on_anchor.items()):
        if any(m["mast"] in in_gantry for m in ms):
            continue
        cell = P.cellx[ms[0]["band"]]
        need = {}
        for q in ms:
            seg = ix.point_tracks(q["ident"], q["slot"])[0]
            need[seg] = max(need.get(seg, 0), 2 * slots.GAP + q["size"][1])
        slide = _slide(P, ident, cell, need)
        if not slide:
            continue
        a, u, s0, lo, hi = slide
        near = {m["mast"]: world.near(m["_p"], NEAR + m["size"][1] + GANTRY_SHIFT * cell) for m in ms}
        conn = set(P.points[ident]["conn"])

        def dirty(t):
            p = (a[0] + u[0] * t, a[1] + u[1] * t)
            return any(spot_cost(icon_rect(p, m["_d"], m["size"], slots.GAP, slots.GAP), near[m["mast"]], conn,
                                 set(), [])[1] for m in ms)
        if not dirty(s0):
            continue
        steps = sorted((t for k in range(1, int((hi - lo) / ICON_STEP) + 2) for t in (s0 - k * ICON_STEP,
                                                                                      s0 + k * ICON_STEP)
                        if lo <= t <= hi), key=lambda t: (abs(t - s0), t))
        t = next((t for t in steps if not dirty(t)), None)
        if t is None:
            continue
        P.points[ident]["xy"] = [a[0] + u[0] * t, a[1] + u[1] * t]
        who = (f"mast {ms[0]['mast']}: its" if len(ms) == 1 else
               f"masts {', '.join(m['mast'] for m in ms)}: their")
        P.log.append(f"{bands[ms[0]['band']][0]}: {who} boundary moved {abs(t - s0):.0f} px along its track, so the "
                     "icons stand clear")
        for m in ms:
            P.anchors_moved.append((m["mast"], ident, round(abs(t - s0), 1)))
    for m in P.masts:
        m.pop("_p", None)
        m.pop("_d", None)
    if P.anchors_moved:
        from .le import to_xml
        after = slots.Index(to_xml(P, "probe"))
        for m in P.masts:
            got = after.blocks(m["kind"], m["ident"], m["slot"])
            if got != before[m["mast"]]:
                raise SchematicError(f"mast {m['mast']}: sliding the boundary anchors changed its blocks from "
                                     f"{before[m['mast']]} to {got}")
    return out


# ---------------------------------------------------------------- icons

def _other_end(s, here, leg=None):
    """The end (name, type) of track element s that is not `here` (a turnout's leg `leg`, or a point)."""
    ends = [(s.get("connect1name"), s.get("type1")), (s.get("connect2name"), s.get("type2"))]
    mine = (lambda e: e == (here, f"TURNOUT_{leg}")) if leg else (lambda e: e[0] == here)     # noqa: E731
    return ends[1] if mine(ends[0]) else ends[0]


def _facing(ix, m, p, d):
    """(straight px before the boundary, [segment idents of the track the train comes along])."""
    if m["kind"] == "turnout":
        seg = ix.turnouts[m["ident"]].get(f"connect{m['slot'].lower()}name")
        leg = m["slot"]
    else:
        seg = ix.point_tracks(m["ident"], m["slot"])[0]
        leg = None
    here, cur, run, segs = m["ident"], p, 0.0, []
    while seg and seg not in segs and run < ICON_BACK + 60:
        s = ix.segs[seg]
        segs.append(seg)
        if s.get("hidden") == "yes" or s.get("arc") == "yes":
            break
        name, typ = _other_end(s, here, leg)
        far = ix.coords(name, typ)
        v = _sub(far, cur)
        L = math.hypot(*v)
        if L < EPS or _dot(v, (-d[0], -d[1])) / L < 0.999:
            break
        run += L
        pt = ix.points.get(name) if typ == "POS_POINT" else None
        if pt is None or pt.get("type") != "ANCHOR" or not pt.get("connect2name"):
            break
        seg = pt.get("connect2name") if pt.get("connect1name") == seg else pt.get("connect1name")
        here, cur, leg = name, far, None
    return run, segs


def spot_cost(rect, near, own_segs, own_turnouts, placed):
    """(cost, [reasons]) of an icon in `rect` (ICON_COST's keys; the distance back is added by the caller)."""
    track, bodies, labels, shapes = near
    why = []
    graze = False
    own_d, other_d = [], []
    for sid, pieces in track.items():
        g = min(rect.gap_seg(a, b) for a, b in pieces)
        if g < CLEAR[0]:
            why.append("ink")
        elif g < CLEAR[1]:
            graze = True
        dist = min(_pt_seg(rect.c, a, b) for a, b in pieces)
        (own_d if sid in own_segs else other_d).append(dist)
    for tid, (cen, lines) in bodies.items():
        if rect.gap_point(cen) < TURNOUT_R or any(rect.gap_seg(a, b) < CLEAR[1] for a, b in lines):
            why.append("turnout")
        dist = min([math.dist(rect.c, cen)] + [_pt_seg(rect.c, a, b) for a, b in lines])
        (own_d if tid in own_turnouts else other_d).append(dist)
    if graze:
        why.append("graze")
    if own_d and other_d and min(other_d) < min(own_d) - 0.5:
        why.append("other")
    why += ["mast"] * sum(rect.overlaps(o) for o in placed)
    why += ["label"] * sum(rect.overlaps(lb) for lb in labels)
    why += ["label"] * sum(rect.gap_point(c) < r + CLEAR[0] for c, r in shapes)
    return sum(ICON_COST[w] for w in why), why


def icons(P, ix, gantries_=()):
    """Place every mast's icon in its clearest spot (module text): sets each P.masts entry's icon (x, y, degrees),
    box and spot (back, across, reasons)."""
    world = World(P)
    plan = {}
    for m in P.masts:
        p, d = ix.travel(m["kind"], m["ident"], m["slot"])
        run, segs = _facing(ix, m, p, d)
        if m["kind"] != "turnout":
            other = [s for s in (ix.point_tracks(m["ident"], m["slot"])[1],) if s]
            segs = segs + other
        h = m["size"][1]
        opts = []
        for across in (slots.GAP, TOUCH, WIDE):
            for k in range(ICON_BACK // ICON_STEP + 1):
                back = slots.GAP + k * ICON_STEP
                if k and back + h > run:
                    break
                opts.append((back, across))
        plan[m["mast"]] = dict(m=m, p=p, d=d, opts=opts, own=set(segs),
                               turnouts={m["ident"]} if m["kind"] == "turnout" else set(),
                               near=world.near(p, NEAR + h))
    rects = {}

    def best(name, others):
        e = plan[name]
        scored = []
        for i, (back, across) in enumerate(e["opts"]):
            r = icon_rect(e["p"], e["d"], e["m"]["size"], back, across)
            c, why = spot_cost(r, e["near"], e["own"], e["turnouts"], others)
            if across == WIDE:
                c += ICON_COST["wide"]
            scored.append((c + (back - slots.GAP) * ICON_PER_PX, i, back, across, why, r))
        return min(scored, key=lambda t: t[:2])

    def put(name, pick):
        cost, _i, back, across, why, r = pick
        rects[name] = r
        plan[name]["pick"] = (back, across, why, cost)

    in_gantry = set()
    for g in gantries_:
        names = [m["mast"] for m in g]
        common = set(plan[names[0]]["opts"]).intersection(*(plan[n]["opts"] for n in names[1:]))
        choice = None
        for back, across in sorted(common, key=lambda o: (o[0], o[1] != slots.GAP)):
            rs = {n: icon_rect(plan[n]["p"], plan[n]["d"], plan[n]["m"]["size"], back, across) for n in names}
            if any(rs[a].overlaps(rs[b]) for i, a in enumerate(names) for b in names[i + 1:]):
                continue
            costs = {n: spot_cost(rs[n], plan[n]["near"], plan[n]["own"], plan[n]["turnouts"], list(rects.values()))
                     for n in names}
            if all(not c[1] for c in costs.values()):
                choice = (back, across, rs, costs)
                break
        if choice:
            back, across, rs, costs = choice
            for n in names:
                put(n, (costs[n][0], 0, back, across, costs[n][1], rs[n]))
            in_gantry.update(names)
    order = sorted((n for n in plan if n not in in_gantry),
                   key=lambda n: (plan[n]["m"]["band"], round(plan[n]["p"][0], 1), round(plan[n]["p"][1], 1), n))
    for n in order:                      # first pass: each against the icons placed before it
        put(n, best(n, list(rects.values())))
    for n in order:                      # second pass: each against all the others
        put(n, best(n, [r for k, r in rects.items() if k != n]))
    for m in P.masts:
        e = plan[m["mast"]]
        back, across, why, _cost = e["pick"]
        x, y, deg = slots.icon_place(e["p"], e["d"], m["size"], back, across)
        bw, bh = slots.icon_box(m["size"], deg)
        m.update(icon=(x, y, deg), box=(x, y, bw, bh), spot=(back, across, tuple(why)))
        if why:
            P.log.append(f"mast {m['mast']}: no clean spot for its icon ({', '.join(sorted(set(why)))})")
        elif (back, across) != (slots.GAP, slots.GAP):
            where = {TOUCH: ", touching the rail", WIDE: f", {WIDE} px from the rail"}.get(across, "")
            P.log.append(f"mast {m['mast']}: its icon stands {back} px back from its boundary{where}, clear of track, "
                         "turnouts, labels and other icons")


def names_yield(P):
    """Slide each track's name along its level run, to the nearest place clear of every mast icon, other label,
    turnout and other track, when an icon covers it where it was drawn (the middle of the run). A name with no such
    place stays and is logged."""
    world = World(P)
    icons_ = [icon_rect_of(m) for m in P.masts]
    others = lambda lb: [label_rect(o) for o in P.labels if o is not lb]      # noqa: E731
    for lb in P.labels:
        if "run" not in lb:
            continue
        r = label_rect(lb)
        if not any(r.overlaps(i) for i in icons_):
            continue
        (ax, ay), (bx, _by) = lb["run"]
        w = 0.6 * lb["size"] * len(lb["text"])
        lo, hi = min(ax, bx) + 2, max(ax, bx) - w - 2
        x0 = lb["xy"][0]
        track, bodies, _labels, _shapes = world.near((x0 + w / 2, ay), NEAR + w)
        fixed = others(lb)
        own = [k for k, v in track.items() if any(abs(a[1] - ay) < 0.5 and abs(b[1] - ay) < 0.5 for a, b in v)]

        def clear(x):
            q = label_rect(lb, x)
            if any(q.overlaps(i) for i in icons_) or any(q.overlaps(o) for o in fixed):
                return False
            if any(q.gap_point(c) < TURNOUT_R or any(q.gap_seg(a, b) < CLEAR[0] for a, b in lines)
                   for c, lines in bodies.values()):
                return False
            return not any(q.gap_seg(a, b) < CLEAR[0] for k, v in track.items() if k not in own for a, b in v)
        steps = sorted((x for k in range(int(hi - lo) + 2) for x in (x0 - k, x0 + k) if lo <= x <= hi),
                       key=lambda x: (abs(x - x0), x))
        x = next((x for x in steps if clear(x)), None)
        if x is None:
            P.log.append(f"track name {lb['text']}: a mast icon covers it and its track has no clear place for it")
            continue
        lb["xy"][0] = x
        P.names_moved.append((lb["text"], round(x - x0, 1)))
        P.log.append(f"track name {lb['text']}: moved {x - x0:+.0f} px along its track, clear of the mast icons")


def icon_rect_of(m):
    """The turned rectangle of a placed mast's icon (its box, as JMRI turns it, is the rectangle's bounds)."""
    x, y, deg = m["icon"]
    bw, bh = m["box"][2:]
    th = math.radians(deg)
    w, h = m["size"]
    return Rect((x + bw / 2, y + bh / 2), (math.sin(th), -math.cos(th)), h / 2, w / 2)
