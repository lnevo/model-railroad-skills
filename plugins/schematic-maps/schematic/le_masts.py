"""Where a generated Layout Editor panel's mast icons stand: gantries, and spots clear of turnouts and other icons.

    le_masts.place(P, bands, ix)    # from le.place_masts, once every mast has its slot; ix: the panel's slots.Index

The CATS rules (references/cats-signals.md) carried over to Layout Editor (references/le-panel.md). There a mast's
slot is fixed by JMRI (an anchor, an end bumper or a turnout leg) and its icon is an image placed anywhere, so:

Gantries. Masts of one control point (the band's `control_points` entry holding the switch the mast governs, found
by following its protected track to the first turnout; else that switch alone) that govern the same direction and
stand within GANTRY_SPAN columns (first to last) form a gantry. Their boundary anchors slide along their own straight
track, between the same two points and so the same two blocks, until the boundaries stand in one column (one x): the
mast keeps its slot and its facing and protected blocks, and the panel keeps its width. An anchor moves at most
GANTRY_SHIFT columns and leaves each of its two tracks at least a column long (or as long as it was, if shorter),
with room for the icon on the side the train comes from; anchors are moved one at a time, each against where the
others stand by then, so two never meet or pass. A mast in a turnout leg or an end bumper cannot move; it still
counts toward the column. An anchor holding masts of two gantries stays. The column is the one most masts reach,
then the one where their icons stand clean in their first spot, then the least movement. The masts left over may
form a column of their own the same way.

Icons. Each icon stays on the right-hand side of the train, turned to its direction of travel (on a slope, along the
slope), before its boundary. The spots tried are GAP pixels from the rail (the icon's middle about 10 pixels out for
a dwarf), touching it, or WIDE (for a curve), from GAP pixels before the boundary back along the straight track
before it, ICON_STEP pixels at a time. Each spot is scored where JMRI will draw it (its stored, whole-pixel place)
and the cheapest taken (ICON_COST): over a turnout's legs or its control circle (which takes the clicks that throw
it), nearer another track than its own (it would read as that track's mast), a track line through it, over another
icon, a label or a shape; touching a line; the distance back. A touching spot costs less than reading as another
track's mast. A gantry's icons take one spot when it is clean for all of them, so they stand in one line.

A mast alone on an anchor (in no gantry) whose icon has no clean spot at all slides its anchor, the least it must,
until one is clean: the last resort, as a lone CATS mast moves out of a switch's cell. Then each moved anchor is
checked against the panel as JMRI reads it: same blocks for every mast, the anchor on its line between the same two
points, every track it ends still at least its minimum length; any failure stops.
"""
import math
from collections import defaultdict

from . import slots
from .core import SchematicError
from .label_check import _pt_seg as pt_seg, seg_box_gap
from .le import dot, mid, room_width, sub, to_xml

GANTRY_SHIFT = 3        # columns an anchor may slide along its track to line masts up (as cats.GANTRY_SHIFT)
GANTRY_SPAN = 3         # columns from a gantry's first mast to its last, at most: as far as an anchor may move
ICON_STEP = 2           # px between the spots tried back along the track (and between an anchor's trial places)
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
GRID = 64               # px per cell of the index that finds the track near a point
EPS = 1e-6


# ---------------------------------------------------------------- geometry

class Rect:
    """A turned rectangle: centre c, unit u along its length (half ha), half hw across."""

    def __init__(self, c, u, ha, hw):
        self.c, self.u, self.ha, self.hw = c, u, ha, hw
        self.n = (-u[1], u[0])

    def local(self, p):
        v = sub(p, self.c)
        return (dot(v, self.u), dot(v, self.n))

    def gap_seg(self, a, b):
        return seg_box_gap(self.local(a), self.local(b), (-self.ha, -self.hw, self.ha, self.hw))

    def gap_point(self, p):
        x, y = self.local(p)
        return math.hypot(max(abs(x) - self.ha, 0), max(abs(y) - self.hw, 0))

    def overlaps(self, o, margin=OVERLAP):
        d = sub(o.c, self.c)
        for ax in (self.u, self.n, o.u, o.n):
            r1 = abs(dot(ax, self.u)) * self.ha + abs(dot(ax, self.n)) * self.hw
            r2 = abs(dot(ax, o.u)) * o.ha + abs(dot(ax, o.n)) * o.hw
            if abs(dot(d, ax)) >= r1 + r2 + margin:
                return False
        return True


def label_rect(lb):
    """The room the drawing keeps for a label (le.room_width), as a Rect: what the icons are scored against."""
    w = room_width(lb["text"], lb["size"])
    return Rect((lb["xy"][0] + w / 2, lb["xy"][1] + lb["size"] / 2), (1.0, 0.0), w / 2, lb["size"] / 2)


def placed_rect(x, y, deg, size):
    """The turned rectangle of an icon stored at (x, y, degrees): its box, as JMRI turns it, is the bounds."""
    bw, bh = slots.icon_box(size, deg)
    th = math.radians(deg)
    return Rect((x + bw / 2, y + bh / 2), (math.sin(th), -math.cos(th)), size[1] / 2, size[0] / 2)


def icon_rect(p, d, size, back, across):
    """(rectangle, (x, y, degrees)) of an icon in that spot, where JMRI draws it: at its stored whole-pixel place."""
    x, y, deg = slots.icon_place(p, d, size, back, across)
    return placed_rect(x, y, deg, size), (x, y, deg)


def icon_rect_of(m):
    return placed_rect(*m["icon"], m["size"])


# ---------------------------------------------------------------- the panel

class PanelView:
    """A panel's drawn railroad, indexed once: its segments and turnouts by ident, and where a track end is."""

    def __init__(self, P):
        self.P = P
        self.turnouts = {t["ident"]: t for t in P.turnouts}
        self.segs = {s["ident"]: s for s in P.segments}

    def xy(self, end):
        ident, typ = end
        if typ == "POS_POINT":
            return tuple(self.P.points[ident]["xy"])
        return tuple(self.turnouts[ident]["pts"][typ[-1]])


class World:
    """The drawn panel for scoring: track lines by segment (indexed by grid cell), turnout bodies, fixed labels and
    shapes. update() redraws the tracks an anchor ends when it moves."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.track, self.cells, self.grid = {}, {}, defaultdict(set)
        for sid, s in ctx.segs.items():
            if not s["hidden"]:
                self._index(sid)
        self.bodies = {}            # turnout ident -> (centre, [(a, b)]) as Layout Editor draws it
        for t in ctx.P.turnouts:
            p = {k: tuple(v) for k, v in t["pts"].items()}
            cen = tuple(t["cen"])
            if t["type"] in ("RH_XOVER", "LH_XOVER"):
                lines = [(p["A"], p["B"]), (p["D"], p["C"]), (mid(p["A"], p["B"]), mid(p["D"], p["C"]))]
            elif t["type"] == "DOUBLE_XOVER":
                lines = [(p["A"], p["B"]), (p["D"], p["C"]), (p["A"], p["C"]), (p["B"], p["D"])]
            else:
                lines = [(cen, p[k]) for k in "ABC" if k in p]
            self.bodies[t["ident"]] = (cen, lines)
        # the room kept for a track's name is left out: le_labels places the names around the icons afterwards
        self.labels = [label_rect(lb) for lb in ctx.P.labels if "run" not in lb]
        self.shapes = [(tuple(sh["centre"]), sh["r"]) for sh in ctx.P.shapes]

    def _index(self, sid):
        s = self.ctx.segs[sid]
        if s["arc"]:
            q = s["arc"]["drawn"]
            pieces = list(zip(q, q[1:]))
        else:
            pieces = [tuple(self.ctx.xy(e) for e in s["ends"])]
        self.track[sid] = pieces
        xs = [p[0] for pc in pieces for p in pc]
        ys = [p[1] for pc in pieces for p in pc]
        cells = {(i, j) for i in range(int(min(xs) // GRID), int(max(xs) // GRID) + 1)
                 for j in range(int(min(ys) // GRID), int(max(ys) // GRID) + 1)}
        self.cells[sid] = cells
        for c in cells:
            self.grid[c].add(sid)

    def update(self, sids):
        for sid in sids:
            if sid in self.track:
                for c in self.cells.pop(sid):
                    self.grid[c].discard(sid)
                self._index(sid)

    def near(self, p, r=NEAR):
        """(track {seg: pieces}, bodies {turnout: body}, labels, shapes) within r px of p."""
        sids = set()
        for i in range(int((p[0] - r) // GRID), int((p[0] + r) // GRID) + 1):
            for j in range(int((p[1] - r) // GRID), int((p[1] + r) // GRID) + 1):
                sids |= self.grid.get((i, j), set())
        track = {k: self.track[k] for k in sorted(sids) if any(pt_seg(p, a, b) <= r for a, b in self.track[k])}
        bodies = {k: v for k, v in self.bodies.items() if math.dist(p, v[0]) <= r + 30}
        labels = [lb for lb in self.labels if math.dist(p, lb.c) <= r + lb.ha]
        shapes = [s for s in self.shapes if math.dist(p, s[0]) <= r + s[1]]
        return track, bodies, labels, shapes


def spot_cost(rect, near, own_segs, own_turnouts, placed):
    """(cost, [reasons]) of an icon in `rect` (ICON_COST's keys; the distance back and WIDE are the caller's)."""
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
        (own_d if sid in own_segs else other_d).append(min(pt_seg(rect.c, a, b) for a, b in pieces))
    for tid, (cen, lines) in bodies.items():
        if rect.gap_point(cen) < TURNOUT_R or any(rect.gap_seg(a, b) < CLEAR[1] for a, b in lines):
            why.append("turnout")
        dist = min([math.dist(rect.c, cen)] + [pt_seg(rect.c, a, b) for a, b in lines])
        (own_d if tid in own_turnouts else other_d).append(dist)
    if graze:
        why.append("graze")
    if own_d and other_d and min(other_d) < min(own_d) - 0.5:
        why.append("other")
    why += ["mast"] * sum(rect.overlaps(o) for o in placed)
    why += ["label"] * sum(rect.overlaps(lb) for lb in labels)
    why += ["label"] * sum(rect.gap_point(c) < r + CLEAR[0] for c, r in shapes)
    return sum(ICON_COST[w] for w in why), why


def control_points(title, opts):
    """{control point name: [switch labels]} from a band's `control_points` option, checked."""
    cps = (opts or {}).get("control_points") or {}
    if not isinstance(cps, dict):
        raise SchematicError(f"{title}: control_points must be an object of name: {{\"switches\": [...]}}")
    out = {}
    for name, cp in cps.items():
        sws = cp.get("switches") if isinstance(cp, dict) else None
        if not isinstance(sws, list) or not all(isinstance(sw, (str, int)) and not isinstance(sw, bool) and
                                                str(sw).strip() for sw in sws):
            raise SchematicError(f"{title}: control point {name}: switches must be a list of switch labels")
        out[name] = [str(sw).strip().rstrip("*") for sw in sws]
    return out


def _way(d):
    if abs(d[0]) >= 0.3:
        return "east" if d[0] > 0 else "west"
    return "south" if d[1] > 0 else "north"


class Masts(PanelView):
    """The masts of one panel being placed: the panel's indexes, built once, and the steps of `place`."""

    def __init__(self, P, bands, ix):
        super().__init__(P)
        self.bands, self.ix = bands, ix
        self.world = World(self)
        self.by_name = {m["mast"]: m for m in P.masts}
        self.before = {m["mast"]: ix.blocks(m["kind"], m["ident"], m["slot"]) for m in P.masts}
        self.d, self.facing, self.protects = {}, {}, {}
        self.on_anchor = defaultdict(list)
        for m in P.masts:
            name = m["mast"]
            self.d[name] = ix.travel(m["kind"], m["ident"], m["slot"])[1]      # the line's way: never changes
            if m["kind"] == "turnout":
                self.facing[name] = self.turnouts[m["ident"]]["conn"].get(m["slot"])
                self.protects[name] = None
            else:
                self.facing[name], self.protects[name] = ix.point_tracks(m["ident"], m["slot"])
            if m["kind"] == "anchor":
                self.on_anchor[m["ident"]].append(m)
        self.original = {}          # anchor ident -> (xy, {segment: length}) before it first moved
        self.first_len = {sid: math.dist(*(self.xy(e) for e in s["ends"]))    # before any anchor moved
                          for sid, s in self.segs.items()}
        self.picks = {}             # mast -> (back, across, why, cost, rect, place)
        self.gantry_anchors = set()  # anchors standing in a gantry's column: never slid again

    # ---- the drawn railroad
    def other_end(self, sid, here):
        e = self.segs[sid]["ends"]
        return e[1] if tuple(e[0]) == tuple(here) else e[0]

    def boundary(self, m):
        if m["kind"] == "turnout":
            return tuple(self.turnouts[m["ident"]]["pts"][m["slot"]])
        return tuple(self.P.points[m["ident"]]["xy"])

    def here(self, m):
        return (m["ident"], f"TURNOUT_{m['slot']}" if m["kind"] == "turnout" else "POS_POINT")

    def onward(self, end, sid):
        """The next track on from an anchor `end` reached along `sid`, or None (a turnout, a bumper, a join)."""
        if end[1] != "POS_POINT":
            return None
        pt = self.P.points[end[0]]
        if pt["type"] != "ANCHOR" or len(pt["conn"]) != 2:
            return None
        return pt["conn"][1] if pt["conn"][0] == sid else pt["conn"][0]

    def governs(self, m):
        """The turnout ident a mast governs: its own, or the first one along its protected track; None at a buffer
        stop, a join or the end of the track."""
        if m["kind"] == "turnout":
            return m["ident"]
        if m["kind"] != "anchor":
            return None
        sid, here = self.protects[m["mast"]], self.here(m)
        for _ in range(len(self.segs) + 1):
            if sid is None or self.segs[sid]["hidden"]:
                return None
            end = self.other_end(sid, here)
            if end[1].startswith("TURNOUT_"):
                return end[0]
            sid, here = self.onward(end, sid), end
        return None

    def run(self, m):
        """(straight px before the boundary, {segment idents of the mast's own track})."""
        p, d = self.boundary(m), self.d[m["mast"]]
        sid, here, cur, run, segs = self.facing[m["mast"]], self.here(m), p, 0.0, []
        while sid and sid not in segs and run < ICON_BACK + 60:
            segs.append(sid)
            s = self.segs[sid]
            if s["hidden"] or s["arc"]:
                break
            end = self.other_end(sid, here)
            far = self.xy(end)
            v = sub(far, cur)
            L = math.hypot(*v)
            if L < EPS or dot(v, (-d[0], -d[1])) / L < 0.999:
                break
            run += L
            sid, here, cur = self.onward(end, sid), end, far
        if self.protects[m["mast"]]:
            segs.append(self.protects[m["mast"]])
        return run, set(segs)

    def need(self, ident):
        """{segment: px} the room the icons of an anchor's masts need on the side each train comes from."""
        out = {}
        for q in self.on_anchor[ident]:
            sid = self.facing[q["mast"]]
            out[sid] = max(out.get(sid, 0), 2 * slots.GAP + q["size"][1])
        return out

    def least(self, sid, cell):
        """The shortest a track an anchor ends may become: a column, or as long as it was if shorter."""
        return min(cell, self.first_len[sid])

    def slide(self, ident, cell):
        """(a, unit, s, lo, hi) for an anchor that may slide along the straight line through it, from where every
        point stands now: a and the unit are the line from the far end of one of its tracks to the far end of the
        other, s the anchor's place on it, lo and hi how far it may go; None when it may not (an arc, a hidden
        track, a bend)."""
        pt = self.P.points[ident]
        if pt["type"] != "ANCHOR" or len(pt["conn"]) != 2:
            return None
        if any(self.segs[sid]["arc"] or self.segs[sid]["hidden"] for sid in pt["conn"]):
            return None
        (s1, a), (s2, b) = ((sid, self.xy(self.other_end(sid, (ident, "POS_POINT")))) for sid in pt["conn"])
        L = math.dist(a, b)
        if L < EPS:
            return None
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        m = tuple(pt["xy"])
        if abs(u[0] * (m[1] - a[1]) - u[1] * (m[0] - a[0])) > 0.5:
            return None
        s = dot(sub(m, a), u)
        need = self.need(ident)
        lo = min(s, max(self.least(s1, cell), need.get(s1, 0)))
        hi = max(s, L - max(self.least(s2, cell), need.get(s2, 0)))
        shift = GANTRY_SHIFT * cell
        return a, u, s, max(lo, s - shift), min(hi, s + shift)

    def move(self, ident, xy):
        pt = self.P.points[ident]
        if ident not in self.original:
            self.original[ident] = (tuple(pt["xy"]), {sid: self.first_len[sid] for sid in pt["conn"]})
        pt["xy"] = [xy[0], xy[1]]
        self.world.update(pt["conn"])

    # ---- gantries
    def gantries(self):
        P, bands = self.P, self.bands
        labels = {}
        for t in P.turnouts:
            nodes = bands[t["band"]][1]["nodes"]
            labels[t["ident"]] = sorted({(nodes[n].get("label") or n).rstrip("*") for n in t["nodes"]})
        cp_of = {}
        for bi, (title, _, opts) in enumerate(bands):
            for name, sws in control_points(title, opts).items():
                for sw in sws:
                    if (bi, sw) in cp_of and cp_of[(bi, sw)] != name:
                        raise SchematicError(f"{title}: switch {sw} is in control points {cp_of[(bi, sw)]} and "
                                             f"{name}")
                    cp_of[(bi, sw)] = name
        groups = defaultdict(list)
        for m in P.masts:
            tid = self.governs(m)
            if tid is None:
                continue
            cp = next((cp_of[(m["band"], lb)] for lb in labels[tid] if (m["band"], lb) in cp_of),
                      "switch " + "/".join(labels[tid]))
            groups[(m["band"], cp, _way(self.d[m["mast"]]))].append(m)
        clusters = []
        for key in sorted(groups, key=str):
            span = GANTRY_SPAN * P.cellx[key[0]]
            run = []
            for m in sorted(groups[key], key=lambda m: (self.boundary(m)[0], m["mast"])):
                if run and self.boundary(m)[0] - self.boundary(run[0])[0] > span:       # first to last
                    clusters.append((key, run))
                    run = []
                run.append(m)
            clusters.append((key, run))
        cluster_of = {m["mast"]: i for i, (_, cl) in enumerate(clusters) for m in cl}
        out = []
        for i, (key, cl) in enumerate(clusters):
            if len(cl) < 2:
                continue
            own = lambda m, i=i: all(cluster_of.get(q["mast"]) == i for q in self.on_anchor[m["ident"]])   # noqa
            left, mine = list(cl), []
            names = ", ".join(m["mast"] for m in cl)
            while len(left) > 1:            # the column most reach; then the rest may form a column of their own
                got = self.gantry(key, left, own)
                if len(got) < 2:
                    break
                mine.append(got)
                left = [m for m in left if m not in got]
            out += mine
            if not mine:
                self.P.log.append(f"{bands[key[0]][0]}: masts {names} ({key[1]} {key[2]} bound) form no gantry: no "
                                  "column two of them can reach")
            elif left:
                self.P.log.append(f"{bands[key[0]][0]}: mast{'s' if len(left) > 1 else ''} "
                                  f"{', '.join(m['mast'] for m in left)} could not join "
                                  f"a gantry of {key[1]} {key[2]} bound")
        return out

    def gantry(self, key, cl, own_anchor):
        """Line up one cluster's boundaries in one column; the masts that stand in it."""
        cell = self.P.cellx[key[0]]
        title = self.bands[key[0]][0]
        reach = {}
        for m in cl:
            slide = None
            if m["kind"] == "anchor" and own_anchor(m):
                slide = self.slide(m["ident"], cell)
                if slide and abs(slide[1][0]) < 0.3:        # too steep to line up across the panel
                    slide = None
            x = self.boundary(m)[0]
            if slide:
                a, u, _s, lo, hi = slide
                xs = sorted((a[0] + u[0] * lo, a[0] + u[0] * hi))
                reach[m["mast"]] = (xs[0], xs[1], slide)
            else:
                reach[m["mast"]] = (x, x, None)
        cols = {v for r in reach.values() for v in r[:2]}
        for lo, hi, slide in reach.values():
            if slide:
                cols |= {lo + k * ICON_STEP for k in range(int((hi - lo) / ICON_STEP) + 1)}
        near = {m["mast"]: self.world.near(self.boundary(m), NEAR + m["size"][1] + GANTRY_SHIFT * cell)
                for m in cl if reach[m["mast"]][2]}
        now = {m["mast"]: self.boundary(m)[0] for m in cl}

        def at(slide, col):
            a, u = slide[:2]
            return (col, a[1] + u[1] * (col - a[0]) / u[0])

        def unclean(m, col):
            r, _ = icon_rect(at(reach[m["mast"]][2], col), self.d[m["mast"]], m["size"], slots.GAP, slots.GAP)
            return bool(spot_cost(r, near[m["mast"]], set(self.P.points[m["ident"]]["conn"]), set(), [])[1])

        def score(col):
            got = [m for m in cl if reach[m["mast"]][0] - 0.05 <= col <= reach[m["mast"]][1] + 0.05]
            bad = sum(unclean(m, col) for m in got if reach[m["mast"]][2])
            return (-len(got), bad, round(sum(abs(col - now[m["mast"]]) for m in got), 3), col)
        col = min((score(c) for c in sorted(cols)), key=lambda t: t)[3]
        # move one anchor at a time, each against where the others stand by then: two never meet or pass
        planned = [m for m in cl if reach[m["mast"]][0] - 0.05 <= col <= reach[m["mast"]][1] + 0.05]
        for m in sorted(planned, key=lambda m: (abs(col - now[m["mast"]]), m["mast"])):
            if reach[m["mast"]][2] is None or abs(col - self.boundary(m)[0]) < 0.05:    # where it stands now
                continue
            slide = self.slide(m["ident"], cell)
            t = dot(sub(at(slide, col), slide[0]), slide[1]) if slide else None
            if t is not None and slide[3] - 0.1 <= t <= slide[4] + 0.1:     # the reach's own rounding
                t = min(max(t, slide[3]), slide[4])
            if t is None or not slide[3] <= t <= slide[4]:
                # an anchor moved before it now stands in the way: this one stays (logged as left out)
                self.P.log.append(f"{title}: mast {m['mast']}: its boundary cannot reach the gantry's column now that "
                                  "the anchors before it have moved; it stays")
                continue
            a, u = slide[:2]
            new = (a[0] + u[0] * t, a[1] + u[1] * t)
            moved = math.dist(new, self.boundary(m))
            self.move(m["ident"], new)
            self.P.log.append(f"{title}: mast {m['mast']}: its boundary moved {moved:.1f} px along its track, into "
                              f"the gantry of {key[1]} {key[2]} bound")
            self.P.anchors_moved.append((m["mast"], m["ident"], round(moved, 1)))
        got = [m for m in cl if abs(self.boundary(m)[0] - col) < 0.05]
        if len(got) > 1:            # a gantry's anchors are never slid again (lone_slides), even if its icons differ
            self.gantry_anchors |= {m["ident"] for m in got if m["kind"] == "anchor"}
        return got

    # ---- icons
    def options(self, m, run=None):
        run = self.run(m)[0] if run is None else run
        out = []
        for across in (slots.GAP, TOUCH, WIDE):
            for k in range(ICON_BACK // ICON_STEP + 1):
                back = slots.GAP + k * ICON_STEP
                if k and back + m["size"][1] > run:
                    break
                out.append((back, across))
        return out

    def best(self, m, others):
        """(cost, index, back, across, why, rect, place): the cheapest spot for m's icon where it stands now."""
        p, d = self.boundary(m), self.d[m["mast"]]
        near = self.world.near(p, NEAR + m["size"][1])
        run, own = self.run(m)
        mine = self.mine(m)
        scored = []
        for i, (back, across) in enumerate(self.options(m, run)):
            r, place = icon_rect(p, d, m["size"], back, across)
            c, why = spot_cost(r, near, own, mine, others)
            c += (ICON_COST["wide"] if across == WIDE else 0) + (back - slots.GAP) * ICON_PER_PX
            scored.append((c, i, back, across, why, r, place))
        return min(scored, key=lambda t: t[:2])

    @staticmethod
    def mine(m):
        """The turnout a mast's icon belongs to: its own legs are its track, not another's."""
        return {m["ident"]} if m["kind"] == "turnout" else set()

    def put(self, name, pick):
        cost, _i, back, across, why, r, place = pick
        self.picks[name] = (back, across, why, cost, r, place)

    def others(self, names):
        return [p[4] for k, p in self.picks.items() if k not in names]

    def icons(self, gantries):
        in_gantry = set()
        for g in gantries:
            names = [m["mast"] for m in g]
            common = set(self.options(g[0])).intersection(*(self.options(m) for m in g[1:]))
            for back, across in sorted(common, key=lambda o: (o[0], o[1] != slots.GAP)):
                rs = {m["mast"]: icon_rect(self.boundary(m), self.d[m["mast"]], m["size"], back, across) for m in g}
                if any(rs[a][0].overlaps(rs[b][0]) for i, a in enumerate(names) for b in names[i + 1:]):
                    continue
                costs = {}
                for m in g:
                    _run, own = self.run(m)
                    costs[m["mast"]] = spot_cost(rs[m["mast"]][0], self.world.near(self.boundary(m),
                                                                                  NEAR + m["size"][1]),
                                                 own, self.mine(m), self.others(names))
                if all(not c[1] for c in costs.values()):
                    for n in names:
                        self.put(n, (costs[n][0], 0, back, across, costs[n][1], *rs[n]))
                    in_gantry.update(names)
                    break
            else:
                self.P.log.append(f"gantry {', '.join(names)}: no one icon spot is clean for all of them; each icon "
                                  "takes its own")
        order = sorted((m for m in self.P.masts if m["mast"] not in in_gantry),
                       key=lambda m: (m["band"], round(self.boundary(m)[0], 1), round(self.boundary(m)[1], 1),
                                      m["mast"]))
        for m in order:                      # first pass: each against the icons placed before it
            self.put(m["mast"], self.best(m, self.others({m["mast"]})))
        for m in order:                      # second pass: each against all the others
            self.put(m["mast"], self.best(m, self.others({m["mast"]})))
        return in_gantry

    def lone_slides(self, in_gantry):
        """An anchor whose masts are in no gantry and whose icons have no clean spot where it stands slides, the
        least it must, to where every one of them has one: the last resort."""
        for ident, ms in sorted(self.on_anchor.items()):
            names = {m["mast"] for m in ms}
            if ident in self.gantry_anchors or names & in_gantry or all(not self.picks[n][2] for n in names):
                continue
            cell = self.P.cellx[ms[0]["band"]]
            slide = self.slide(ident, cell)
            who = ", ".join(m["mast"] for m in ms)
            if not slide:
                self.P.log.append(f"mast {who}: no clean icon spot, and its anchor {ident} cannot slide (an arc, a "
                                  "bend or a hidden track beside it)")
                continue
            a, u, s0, lo, hi = slide
            steps = sorted((t for k in range(1, int((hi - lo) / ICON_STEP) + 2)
                            for t in (s0 - k * ICON_STEP, s0 + k * ICON_STEP) if lo <= t <= hi),
                           key=lambda t: (abs(t - s0), t))
            start = tuple(self.P.points[ident]["xy"])
            fixed = self.others(names)
            for t in steps:
                self.P.points[ident]["xy"] = [a[0] + u[0] * t, a[1] + u[1] * t]
                self.world.update(self.P.points[ident]["conn"])
                picks = {}
                for m in ms:
                    picks[m["mast"]] = self.best(m, fixed + [p[5] for p in picks.values()])
                if all(not p[4] for p in picks.values()):
                    self.P.points[ident]["xy"] = list(start)
                    self.move(ident, (a[0] + u[0] * t, a[1] + u[1] * t))
                    for n, p in picks.items():
                        self.put(n, p)
                    who = (f"mast {ms[0]['mast']}: its" if len(ms) == 1 else
                           f"masts {', '.join(m['mast'] for m in ms)}: their")
                    self.P.log.append(f"{self.bands[ms[0]['band']][0]}: {who} boundary moved {abs(t - s0):.1f} px "
                                      "along its track: no icon spot was clean where it stood")
                    self.P.anchors_moved.append((", ".join(sorted(names)), ident, round(abs(t - s0), 1)))  # once
                    self.rescore(ident, start, names, in_gantry)
                    break
            else:
                self.P.points[ident]["xy"] = list(start)
                self.world.update(self.P.points[ident]["conn"])
                self.P.log.append(f"mast {who}: no clean icon spot anywhere its anchor {ident} may slide; it stays")

    def rescore(self, ident, start, moved, in_gantry):
        """After an anchor slid, place again the icons of the other masts near the tracks it ends (their spots were
        scored against those tracks where they were). A gantry's shared spot is kept while it stays clean."""
        reach = NEAR + ICON_BACK + 60
        here = tuple(self.P.points[ident]["xy"])
        conn = set(self.P.points[ident]["conn"])
        for m in self.P.masts:
            if m["mast"] in moved:
                continue
            p = self.boundary(m)
            if min(math.dist(p, start), math.dist(p, here)) > reach and not (self.run(m)[1] & conn):
                continue
            if m["mast"] in in_gantry:
                _run, own = self.run(m)
                why = spot_cost(self.picks[m["mast"]][4], self.world.near(p, NEAR + m["size"][1]), own,
                                self.mine(m), self.others({m["mast"]}))[1]
                if not why:
                    continue
                self.P.log.append(f"mast {m['mast']}: its gantry's spot is no longer clean after anchor {ident} "
                                  "slid; it takes its own")
            self.put(m["mast"], self.best(m, self.others({m["mast"]})))

    # ---- checks
    def verify(self):
        """Stop if a moved anchor changed what any mast means, or left its line, its order or a track too short."""
        if not self.original:
            return
        after = slots.Index(to_xml(self.P, "probe", probe=True))
        for m in self.P.masts:
            got = after.blocks(m["kind"], m["ident"], m["slot"])
            if got != self.before[m["mast"]]:
                raise SchematicError(f"mast {m['mast']}: sliding the boundary anchors changed its blocks from "
                                     f"{self.before[m['mast']]} to {got}")
        for ident, (was, lens) in sorted(self.original.items()):
            pt = self.P.points[ident]
            cell = self.P.cellx[pt["band"]]
            (s1, a), (s2, b) = ((sid, self.xy(self.other_end(sid, (ident, "POS_POINT")))) for sid in pt["conn"])
            L = math.dist(a, b)
            if L < EPS:
                raise SchematicError(f"anchor {ident}: the far ends of its two tracks meet")
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            for q, what in ((tuple(pt["xy"]), "now"), (was, "before")):
                if abs(u[0] * (q[1] - a[1]) - u[1] * (q[0] - a[0])) > 0.5:
                    raise SchematicError(f"anchor {ident}: {what} off the line between the ends of its tracks")
            t, t0 = dot(sub(pt["xy"], a), u), dot(sub(was, a), u)
            if not 0 < t < L or (t0 > 0) != (t > 0) or (t0 < L) != (t < L):
                raise SchematicError(f"anchor {ident}: slid past the end of its track")
            for sid, length in ((s1, t), (s2, L - t)):
                if length < EPS or length < min(cell, lens[sid]) - 0.01:
                    raise SchematicError(f"anchor {ident}: track {sid} left {length:.1f} px long, under its "
                                         f"{min(cell, lens[sid]):.1f} px minimum")
        return after

    def finish(self):
        for m in self.P.masts:
            back, across, why, _cost, r, (x, y, deg) = self.picks[m["mast"]]
            d = self.d[m["mast"]]
            v = sub(r.c, self.boundary(m))
            if not (dot(v, (-d[1], d[0])) > slots.GAP / 2 and dot(v, d) < 0 and deg == slots.icon_degrees(d)):
                raise SchematicError(f"mast {m['mast']}: its icon at {x}, {y} is not on the right-hand side of the "
                                     "train, before its boundary, turned to its direction")
            bw, bh = slots.icon_box(m["size"], deg)
            m.update(icon=(x, y, deg), box=(x, y, bw, bh), spot=(back, across, tuple(why)))
            if why:
                self.P.log.append(f"mast {m['mast']}: no clean spot for its icon ({', '.join(sorted(set(why)))})")
            elif (back, across) != (slots.GAP, slots.GAP):
                where = {TOUCH: ", touching the rail", WIDE: f", {WIDE} px from the rail"}.get(across, "")
                self.P.log.append(f"mast {m['mast']}: its icon stands {back} px back from its boundary{where}, clear "
                                  "of track, turnouts, labels and other icons")


def place(P, bands, ix):
    """Gantries, icons, lone anchors as a last resort, then the checks (module text); the labels are placed around
    the icons afterwards (le_labels). Sets P.gantries, P.anchors_moved, and each P.masts entry's icon, box and spot
    (back, across, reasons)."""
    for bi, (title, _, opts) in enumerate(bands):
        control_points(title, opts)                 # checked before any work
        if any(m["band"] == bi for m in P.masts) and not P.cellx.get(bi, 0) > 0:
            raise SchematicError(f"{title}: no column width recorded for the band")
    M = Masts(P, bands, ix)
    P.gantries = M.gantries()
    in_gantry = M.icons(P.gantries)
    M.lone_slides(in_gantry)
    M.verify()
    P.anchors_from = {ident: was for ident, (was, _lens) in M.original.items()}
    M.finish()
