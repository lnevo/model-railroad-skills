"""Signal mast slots on a JMRI Layout Editor panel, resolved the way JMRI resolves them.

    ix = slots.Index(layout_editor_element)
    ix.masts()                          # [{mast, kind, ident, slot, facing, protects}] for every mast bound in a slot
    ix.blocks("anchor", "A12", "east")  # (facing block, [protected blocks]) a mast in that slot would get
    ix.candidates()                     # every slot on the panel: (kind, ident, slot)

The facing block is the block a train is in when it reads the mast; the protected blocks are the ones it guards.
Signal Mast Logic discovery and the Dispatcher System both start from these, never from the mast icon. The rules
follow JMRI's LayoutBlockManager.getFacingBlockByBeanByPanel and getProtectingBlocksByBeanByPanel,
LayoutEditorTools.isAtWestEndOfAnchor and LayoutTurnout.getProtectedBlocks (JMRI 5.16):

Anchor or end bumper. JMRI asks whether the point's connect1 track lies at the west end of the point: it compares
the far end of connect1 with the far end of connect2 (for an end bumper, with the bumper itself). If the x gap is
more than twice the y gap the track is horizontal and west is left; if the y gap is more than twice the x gap it is
vertical and west is up the panel; otherwise it counts as horizontal. An east bound mast faces the west track and
protects the east track; a west bound mast the other way round. A bumper has only connect1: the right slot (the
train's direction into the bumper) faces its track and protects nothing; the other has no facing block, so
discovery cannot use it.

Turnout leg. A mast on leg X faces the block of the track on leg X. A plain turnout (right, left hand or wye) mast
protects the turnout's block, except when the track on its leg is in the turnout's own block: then a mast on A
protects the blocks of B and C (if both differ from the turnout's), and a mast on B or C protects the block of A
(if it differs). A crossover keeps a block per leg (B, C, D default to A's) and JMRI pairs them by type: on a double
or right hand crossover A and C go together, on a double or left hand crossover B and D, and on the other single
crossover legs each protects its own leg block, the same own-block exceptions applied.

Level crossings, slips, turntables, traversers and edge connectors are not read (a panel with a mast on one stops).
"""
import math

from .core import SchematicError

LEGS = "ABCD"
XOVERS = ("DOUBLE_XOVER", "RH_XOVER", "LH_XOVER")


class Index:
    def __init__(self, le):
        self.segs = {s.get("ident"): s for s in le.findall("tracksegment")}
        self.points = {p.get("ident"): p for p in le.findall("positionablepoint")}
        self.turnouts = {t.get("ident"): t for t in le.findall("layoutturnout")}
        self.le = le
        for tag in ("levelxing", "layoutSlip", "layoutturntable", "layouttraverser"):
            for el in le.findall(tag):
                if any(k.lower().endswith("signalmast") or k.startswith("signal") for k in el.attrib) or \
                        any("Mast" in c.tag for c in el):
                    raise SchematicError(f"{tag} {el.get('ident')} carries a mast; only anchors, end bumpers and "
                                         "turnouts are read")

    # ---- coordinates, as LayoutTurnoutView.getCoordsA..D and PositionablePoint
    def coords(self, name, kind):
        if kind == "POS_POINT":
            p = self.points[name]
            return (float(p.get("x")), float(p.get("y")))
        if not kind.startswith("TURNOUT_"):
            raise SchematicError(f"connection type {kind} is not read")
        return self.leg_coords(self.turnouts[name], kind[-1])

    @staticmethod
    def leg_coords(t, leg):
        g = lambda a: float(t.get(a))      # noqa: E731
        cen = (g("xcen"), g("ycen"))
        b = (g("xb"), g("yb"))
        c = (g("xc"), g("yc"))
        disp_b = (b[0] - cen[0], b[1] - cen[1])
        disp_a = (c[0] - cen[0], c[1] - cen[1])          # JMRI's dispA is the C offset
        xover = t.get("type") in XOVERS
        if xover and t.get("ver") == "2":
            return (g(f"x{leg.lower()}"), g(f"y{leg.lower()}"))
        if leg == "A":
            if xover:
                return (cen[0] - disp_a[0], cen[1] - disp_a[1])
            if t.get("type") == "WYE_TURNOUT":
                return (cen[0] - (disp_b[0] + disp_a[0]) / 2, cen[1] - (disp_b[1] + disp_a[1]) / 2)
            return (cen[0] - disp_b[0], cen[1] - disp_b[1])
        if leg == "B":
            return b
        if leg == "C":
            return c
        return (cen[0] - disp_b[0], cen[1] - disp_b[1])

    def far_end(self, seg, here):
        """The coordinates of the end of track `seg` that is not the point `here`."""
        s = self.segs[seg]
        if s.get("connect1name") == here:
            return self.coords(s.get("connect2name"), s.get("type2"))
        return self.coords(s.get("connect1name"), s.get("type1"))

    def west_end(self, seg, pid):
        """LayoutEditorTools.isAtWestEndOfAnchor: does track `seg` reach point `pid` from the west (north)?"""
        p = self.points[pid]
        if p.get("type") == "EDGE_CONNECTOR":
            raise SchematicError(f"edge connector {pid}: its direction is not in the file; not read")
        c1, c2 = p.get("connect1name"), p.get("connect2name")
        if seg == c1:
            other = c2
        elif seg == c2:
            other = c1
        else:
            return False
        a = self.far_end(seg, pid)
        b = self.far_end(other, pid) if other else self.coords(pid, "POS_POINT")
        dx, dy = a[0] - b[0], a[1] - b[1]
        if abs(dy) > 2.0 * abs(dx):
            return not dy > 0.0
        return not dx > 0.0

    def block(self, seg):
        return self.segs[seg].get("blockname") if seg and seg in self.segs else None

    # ---- what a mast in a slot gets
    def point_tracks(self, pid, slot):
        """(facing track, protected track) of a mast in the east or west slot of point pid."""
        p = self.points[pid]
        c1, c2 = p.get("connect1name"), p.get("connect2name")
        west = self.west_end(c1, pid) if c1 else False
        if slot == "east":
            return (c1, c2) if west else (c2, c1)
        return (c2, c1) if west else (c1, c2)

    def blocks(self, kind, ident, slot):
        if kind in ("anchor", "end bumper"):
            f, pr = self.point_tracks(ident, slot)
            protects = [self.block(pr)] if pr and self.block(pr) else []
            return self.block(f), protects
        t = self.turnouts[ident]
        return self.block(t.get(f"connect{slot.lower()}name")), self.turnout_protects(t, slot)

    def turnout_protects(self, t, slot):
        own = t.get("blockname")
        if not own:
            return []
        lb = {"A": own, **{L: t.get(f"block{L.lower()}name") or own for L in "BCD"}}
        seg = {L: self.block(t.get(f"connect{L.lower()}name")) if t.get(f"connect{L.lower()}name") else False
               for L in LEGS}           # False: nothing connected on that leg
        ttype = t.get("type")
        out = []
        if ttype in XOVERS:
            if ttype in ("DOUBLE_XOVER", "RH_XOVER") and slot in "AC":
                if slot == "A":
                    if seg["A"] is not False:
                        if seg["A"] == own:
                            if lb["B"] != own and lb["C"] != own:
                                out += [lb["B"], lb["C"]]
                        else:
                            out.append(own)
                elif seg["C"] is not False:
                    if seg["C"] == lb["C"]:
                        if lb["C"] != own and lb["C"] != lb["D"]:
                            out += [own, lb["D"]]
                    else:
                        out.append(lb["C"])
            if ttype in ("DOUBLE_XOVER", "LH_XOVER") and slot in "BD":
                if slot == "B":
                    if seg["B"] is not False:
                        if seg["B"] == lb["B"]:
                            if own != lb["B"] and lb["B"] != lb["D"]:
                                out += [own, lb["D"]]
                        else:
                            out.append(lb["B"])
                elif seg["D"] is not False:
                    if seg["D"] == lb["D"]:
                        if lb["B"] != lb["D"] and lb["C"] != lb["D"]:
                            out += [lb["B"], lb["C"]]
                    else:
                        out.append(lb["D"])
            if ttype == "RH_XOVER" and slot in "BD":
                if slot == "B":
                    if seg["B"] is not False and seg["B"] == lb["B"]:
                        if lb["B"] != own:
                            out.append(own)
                    else:
                        out.append(lb["B"])
                else:
                    if seg["D"] is not False and seg["D"] == lb["D"]:
                        if lb["C"] != lb["D"]:
                            out.append(lb["C"])
                    else:
                        out.append(lb["D"])
            if ttype == "LH_XOVER" and slot in "AC":
                if slot == "A":
                    if seg["A"] is not False and seg["A"] == own:
                        if lb["B"] != own:
                            out.append(lb["B"])
                    else:
                        out.append(own)
                else:
                    if seg["C"] is not False and seg["C"] == lb["C"]:
                        if lb["C"] != lb["D"]:
                            out.append(lb["D"])
                    else:
                        out.append(lb["C"])
            return out
        if seg["A"] is False:
            return out
        if slot == "A":
            if seg["A"] == own:
                if seg["B"] is not False and seg["C"] is not False and seg["B"] != own and seg["C"] != own:
                    out += [seg["B"], seg["C"]]
            else:
                out.append(own)
        elif slot in "BC":
            if seg[slot] is not False and seg[slot] == own:
                if seg["A"] != own:
                    out.append(seg["A"])
            else:
                out.append(own)
        return out

    # ---- the panel's slots
    def candidates(self):
        out = []
        for pid, p in self.points.items():
            if p.get("type") == "ANCHOR" and p.get("connect1name") and p.get("connect2name"):
                out += [("anchor", pid, "east"), ("anchor", pid, "west")]
            elif p.get("type") == "END_BUMPER" and p.get("connect1name"):
                out += [("end bumper", pid, "east"), ("end bumper", pid, "west")]
        for tid, t in self.turnouts.items():
            for L in LEGS:
                if t.get(f"connect{L.lower()}name"):
                    out.append(("turnout", tid, L))
        return out

    def masts(self):
        """Every mast bound in a slot: its slot, facing block and protected blocks."""
        out = []
        for pid, p in self.points.items():
            for slot in ("east", "west"):
                m = p.get(f"{slot}boundsignalmast")
                if m:
                    kind = "end bumper" if p.get("type") == "END_BUMPER" else "anchor"
                    f, pr = self.blocks(kind, pid, slot)
                    out.append(dict(mast=m, kind=kind, ident=pid, slot=slot, facing=f, protects=pr))
        for tid, t in self.turnouts.items():
            for L in LEGS:
                el = t.find(f"signal{L}Mast")
                if el is not None and (el.text or "").strip():
                    f, pr = self.blocks("turnout", tid, L)
                    out.append(dict(mast=el.text.strip(), kind="turnout", ident=tid, slot=L, facing=f, protects=pr,
                                    turnout=t.get("turnoutname")))
        return out

    # ---- where a train runs at a slot
    def travel(self, kind, ident, slot):
        """(point, unit direction of travel) at a slot: the train runs along the facing track into the point."""
        if kind == "turnout":
            t = self.turnouts[ident]
            p = self.leg_coords(t, slot)
            seg = t.get(f"connect{slot.lower()}name")
            here = ident
        else:
            pt = self.points[ident]
            p = (float(pt.get("x")), float(pt.get("y")))
            seg = self.point_tracks(ident, slot)[0]
            here = ident
        q = self.near_end(seg, here, slot if kind == "turnout" else None, p)
        d = (p[0] - q[0], p[1] - q[1])
        n = math.hypot(*d)
        if n < 1e-9:
            raise SchematicError(f"{kind} {ident} slot {slot}: its track has no length")
        return p, (d[0] / n, d[1] / n)

    def near_end(self, seg, here, leg, p):
        """A point on track `seg` a little way back from p: on a circle arc, along the arc; else the far end."""
        s = self.segs[seg]
        far = self.far_end(seg, here) if leg is None else self._far_from_leg(s, here, leg)
        if s.get("arc") == "yes" and s.get("circle") == "yes":
            ends = [self.coords(s.get("connect1name"), s.get("type1")),
                    self.coords(s.get("connect2name"), s.get("type2"))]
            pts = arc_points(ends[0], ends[1], float(s.get("angle") or 90) or 90.0, s.get("flip") == "yes", 24)
            if math.dist(pts[0], p) > math.dist(pts[-1], p):
                pts = pts[::-1]
            return pts[1]
        return far

    def _far_from_leg(self, s, tid, leg):
        if s.get("connect1name") == tid and s.get("type1") == f"TURNOUT_{leg}":
            return self.coords(s.get("connect2name"), s.get("type2"))
        return self.coords(s.get("connect1name"), s.get("type1"))


def arc_points(p1, p2, angle, flip, n=12):
    """Layout Editor's circle arc from connect1 at p1 to connect2 at p2 (as le.arc_points)."""
    a1, a2 = (p2, p1) if flip else (p1, p2)
    half = math.radians(angle) / 2
    a, o = a2[0] - a1[0], a2[1] - a1[1]
    r = math.hypot(a, o) / 2 / math.sin(half)
    start = math.atan2(a, o) - half
    c = (a2[0] - math.cos(start) * r, a2[1] + math.sin(start) * r)
    ext = math.radians(angle)
    pts = [(c[0] + r * math.cos(start + ext * i / n), c[1] - r * math.sin(start + ext * i / n)) for i in range(n + 1)]
    return pts[::-1] if not flip else pts


ICON = (12, 17)       # px, a dwarf mast icon upright (JMRI's AAR-1946 SL-1-low aspect images); a high one is 12 x 40
GAP = 4               # px from the rail to the icon's near edge, and from the boundary back to its end


def icon_place(p, d, size=ICON):
    """(x, y, degrees) of a mast icon for a train running in direction d into the boundary at p: beside the track on
    the right-hand side of that train, just before the boundary, turned to the direction of travel (JMRI's own
    placement: east bound 90, west bound 270, south bound 180), x and y its top left corner as JMRI stores it."""
    deg = math.degrees(math.atan2(d[0], -d[1])) % 360
    near = round(deg / 90) * 90
    deg = (near if abs(deg - near) <= 3 else round(deg)) % 360      # a mast just off the level reads level
    w, h = size                     # upright: w across the track, h along it
    right = (-d[1], d[0])           # the right-hand side of the train (y grows down)
    c = (p[0] - d[0] * (GAP + h / 2) + right[0] * (GAP + w / 2), p[1] - d[1] * (GAP + h / 2) + right[1] * (GAP + w / 2))
    th = math.radians(deg)
    bw = w * abs(math.cos(th)) + h * abs(math.sin(th))
    bh = w * abs(math.sin(th)) + h * abs(math.cos(th))
    return round(c[0] - bw / 2), round(c[1] - bh / 2), deg
