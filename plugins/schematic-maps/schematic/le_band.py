"""One band of a Layout Editor panel drawn from the solved grid (Band): its switches as Layout Editor turnouts and
crossovers, each strand as track segments with rounded bends, cut into its blocks, its ends, turnbacks and helix
circles, and the room kept for its labels. le._draw builds one Band per band and moves it into place; the rules are
in le's module text. Import le, not this module: le imports it once its own names are defined.
"""
import math
from collections import defaultdict

from . import le_labels, stations
from .core import SchematicError, crossover_halves, crossover_name, crossover_notes, through_leg, tidy
from .draw import band_key
from .layout import paths
from .le import (  # le's own names (le imports this module last)
    add, arc_points, BEND, clean, cross, crossover_numbers, crossover_pairs, dot, double_corners, EPS, flip_toward,
    HELIX_R,
    LABEL_SIZE, LEG, mid, MIN_BLOCK, NoRoom, NUMBER_SIZE, PAIR_TOLERANCE, room_width, ROUND_SLACK, shift, sub, unit,
    xover_blocks,
)


class Band:
    """One band drawn into the panel, in its own pixels (moved into place afterwards)."""

    def __init__(self, P, bi, title, band, names, defaults, joined, cellx, row, turned, ends, opts=None, drawn=None):
        self.P, self.bi, self.title, self.band = P, bi, title, band
        self.opts = opts or {}
        self.names, self.defaults, self.joined, self.ends = names, defaults, joined, ends
        self.nodes, self.strands = band["nodes"], band["strands"]
        drawn = drawn if drawn is not None else paths(band)
        x0 = min(p[0] for v in drawn.values() for p in v)
        y0 = min(p[1] for v in drawn.values() for p in v)
        k = -1 if turned else 1
        self.turned = turned
        self.row = row          # px per grid row: a crossover's run is per row deep (run_across)
        self.px = lambda p: (k * (p[0] - x0) * cellx, k * (p[1] - y0) * row)    # noqa: E731
        self.drawn = drawn
        self.poly = {sid: clean([self.px(p) for p in drawn[sid]]) for sid in self.strands}
        for sid, pts in self.poly.items():
            if len(pts) < 2:
                raise SchematicError(f"{title}: track {self.strands[sid]['name'] or sid} is drawn as a single point")
        self.conn = {}          # (node, port) -> connection: (turnout dict, leg) or point ident
        self.leg_pt = {}        # (node, port) -> xy where the strand starts
        self.internal = set()   # strands drawn inside a crossover
        self.placed = {}        # crossover half node -> (x of its half's point, h): its piece runs x-h to x+h
        self.provisional = set()    # nodes of self.placed placed for now only (tight_first)
        self.no_room = set()        # crossover half nodes drawn as two plain turnouts: no room for the crossover
        self.mine = []          # this band's turnouts
        # single crossover half node -> its link leg (B or C, toward its other half): core.crossover_halves
        said = []
        halves = crossover_halves(self.nodes, self.strands, said)
        self.xlink = {n: got[0] for n, got in halves.items()}
        P.log.extend(f"{title}: {m}" for m in said + crossover_notes(self.nodes, halves))
        for name, pairs in sorted(crossover_numbers(band).items()):
            if len(pairs) > 1:
                P.log.append(f"{title}: crossovers " + " and ".join(
                    f"{self.nodes[u].get('label')}/{self.nodes[v].get('label')}" for _sid, u, v in pairs)
                    + f" both take number {name}")

    # ---- names
    def blocks_of(self, sid):
        got = self.names.get("blocks", {}).get(sid)
        if got is not None:
            if isinstance(got, str):
                got = [got]
            if not got:
                raise SchematicError(f"{self.title}: no block named for track {sid}")
            return list(got)
        return list(self.defaults[(self.bi, sid)])

    def least_of(self, block):
        """The shortest a block may be drawn: MIN_BLOCK, or room for the icon of a mast that faces it (a train in
        that block reads the mast, so its icon stands beside that block's track, before the boundary)."""
        from .slots import GAP, ICON
        icons = [m.get("icon") or ICON for m in self.names.get("masts") or [] if m.get("facing") == block]
        return max([MIN_BLOCK] + [2 * GAP + h for _w, h in icons])

    def room_at(self, first, second):
        """(px, px) of straight track a mast at the boundary from block `first` to `second` needs for its icon on
        each side: before it for a mast facing `first`, after it for one facing `second` (from the names' masts)."""
        from .slots import GAP, ICON
        need = [0.0, 0.0]
        for m in self.names.get("masts") or []:
            for i, (f, p) in enumerate(((first, second), (second, first))):
                if m.get("facing") == f and list(m.get("protects") or []) == [p]:
                    need[i] = max(need[i], 2 * GAP + (m.get("icon") or ICON)[1])
        return tuple(need)

    def shares_of(self, sid, blocks):
        """The real lengths of a strand's blocks, when the names give one for every block of it (else None: equal
        blocks; logged when only some are given)."""
        lengths = self.names.get("lengths") or {}
        got = [lengths.get(b) for b in blocks]
        if len(blocks) < 2 or not any(v is not None for v in got):
            return None
        if all(v is not None for v in got):
            for b in blocks:                # a block's length weighs on each track it is drawn on
                strands = self.P.length_strands.setdefault(b, set())
                strands.add((self.bi, sid))
                if len(strands) == 2:
                    self.P.log.append(f"{self.title}: block {b}'s length is used on more than one track; each track "
                                      "weighs its blocks by the whole length")
        if any(v is None for v in got):
            self.P.log.append(f"{self.title}: track {self.strands[sid]['name'] or sid}: lengths given for "
                              f"{', '.join(b for b, v in zip(blocks, got) if v is not None)} but not for "
                              f"{', '.join(b for b, v in zip(blocks, got) if v is None)}; its blocks are drawn equal")
            return None
        return got

    def os_of(self, n):
        got = self.names.get("os", {}).get(n)
        return got or f"OS {self.nodes[n].get('label') or n}"

    def normal_of(self, n):
        """Switch n's normal leg: as the names give it, else a crossover half's through leg (the one that is not
        its link to the other half), else B."""
        default = through_leg(self.xlink[n]) if n in self.xlink else "B"
        got = self.names.get("normal", {}).get(n, default)
        if got not in ("B", "C"):
            raise SchematicError(f"{self.title}: switch {self.nodes[n].get('label') or n}: normal leg {got!r} "
                                 "is not B or C")
        return got

    # ---- the drawn line of a strand from one of its ends
    def away(self, n, port):
        sid = self.port_strand(n, port)
        pts = self.poly[sid]
        return pts if tuple(self.strands[sid]["src"]) == (n, port) else pts[::-1]

    def through(self, n):
        """The legs of crossover half n on its through track: its points (A) and its normal leg (through_leg)."""
        return ("A", through_leg(self.xlink[n]))

    def port_strand(self, n, port):
        d = self.nodes[n]
        return d["ins"].get(port) or d["outs"].get(port)

    def ports(self, n):
        d = self.nodes[n]
        return sorted(set(d["ins"]) | set(d["outs"]), key=str)

    def build(self):
        self.crossovers()
        for n, d in sorted(self.nodes.items()):
            if d["kind"] == "switch" and (self.bi, n) not in self.P.turnout_of:
                self.turnout(n)
            elif d["kind"] == "dx":
                self.double(n)
        for n, d in sorted(self.nodes.items()):
            if d["kind"] == "end":
                self.end(n)
            elif d["kind"].startswith("turn"):
                for port in self.ports(n):
                    pts = self.away(n, port)
                    self.conn[(n, port)] = self.P.point("ANCHOR", pts[0])
                    self.leg_pt[(n, port)] = pts[0]
        for sid in sorted(self.strands):
            if sid not in self.internal:
                self.strand(sid)
        for n, d in sorted(self.nodes.items()):
            if d["kind"].startswith("turn"):
                self.turnback(n)
        self.labels()

    # ---- switches
    def add_turnout(self, nodes, ttype, cen, pts, conn_ports, blocks, continuing="2", at=None):
        """`at`: where the drawn legs meet, when the centre stands elsewhere (leg_b); labels go by it."""
        P = self.P
        t = dict(ident=P.ident("TO"), type=ttype, cen=list(cen), at=list(at if at is not None else cen),
                 pts={k: list(v) for k, v in pts.items()}, conn={},
                 blocks=blocks, continuing=continuing, ver="1",
                 name=None, nodes=nodes, band=self.bi)
        names = {self.names.get("turnouts", {}).get(n) for n in nodes} - {None}
        if len(names) > 1:
            raise SchematicError(f"{self.title}: one turnout for switches {', '.join(nodes)} given two names "
                                 f"{sorted(names)}")
        if names:
            t["name"] = names.pop()
            P.turnout_names.add(t["name"])     # how many carry each name: plan_shared, check_shared
        P.blocks.update(blocks.values())
        for (n, port), leg in conn_ports.items():
            self.conn[(n, port)] = (t, leg)
            self.leg_pt[(n, port)] = pts[leg]
        for n in nodes:
            P.turnout_of[(self.bi, n)] = (t["ident"], {port: leg for (m, port), leg in conn_ports.items() if m == n})
        P.turnouts.append(t)
        self.mine.append(t)
        return t

    def node_point(self, n):
        pts = {tuple(round(v, 3) for v in self.away(n, p)[0]) for p in self.ports(n)}
        if len(pts) != 1:
            raise SchematicError(f"{self.title}: switch {self.nodes[n].get('label') or n}: its legs do not meet "
                                 f"at one point {sorted(pts)}")
        return pts.pop()

    def first_len(self, n, port):
        pts = self.away(n, port)
        return math.dist(pts[0], pts[1])

    def direction(self, n, port):
        pts = self.away(n, port)
        return unit(sub(pts[1], pts[0]))

    def turnout(self, n):
        d = self.nodes[n]
        c = junction = self.node_point(n)
        dirs = {p: self.direction(n, p) for p in "ABC"}
        L = min([LEG] + [0.4 * self.first_len(n, p) for p in "ABC"])
        normal = self.normal_of(n)
        os_block = self.os_of(n)
        blocks = {"A": os_block}
        if dot(dirs["A"], dirs["B"]) < -1 + EPS:
            straight, other = "B", "C"
        elif dot(dirs["A"], dirs["C"]) < -1 + EPS:
            straight, other = "C", "B"
        else:
            straight = None
        want_b = self.names.get("leg_b", {}).get(n)
        if straight:
            A = add(c, dirs[straight], -L)
            on_b, on_c = (other, straight) if want_b == other else (straight, other)
            B, C = add(c, dirs[on_b], L), add(c, dirs[on_c], L)
            ttype = "RH_TURNOUT" if cross(dirs[on_b], dirs[on_c]) > 0 else "LH_TURNOUT"
            conn = {(n, "A"): "A", (n, on_b): "B", (n, on_c): "C"}
            continuing = "2" if normal == on_b else "4"
            if on_b != straight:
                # Layout Editor finds point A of a plain turnout as the centre less leg B's offset, so with the
                # drawn diverging leg as leg B the centre stands midway between A and B: all three legs still end
                # where the drawn track starts
                c = mid(A, B)
                self.P.log.append(f"{self.title}: switch {d.get('label') or n}: its drawn diverging leg is Layout "
                                  "Editor leg B (leg_b), so its centre stands midway between legs A and B")
        else:            # neither leg straight on: a wye, its points opposite the middle of the two legs
            B, C = add(c, dirs["B"], L), add(c, dirs["C"], L)
            m = mid(sub(B, c), sub(C, c))
            if math.hypot(*m) < 1e-3 * L:
                raise SchematicError(f"{self.title}: switch {d.get('label') or n}: legs B and C leave in opposite "
                                     "directions and neither runs straight on from leg A; Layout Editor has no "
                                     "turnout of that shape")
            A = sub(c, m)
            if dot(unit(m), dirs["A"]) > -1 + 1e-3:
                self.P.log.append(f"{self.title}: switch {d.get('label') or n} drawn as a wye with a bent leg A")
            ttype = "WYE_TURNOUT"
            on_b, on_c = ("C", "B") if want_b == "C" else ("B", "C")
            if want_b == "C":
                B, C = C, B
            conn = {(n, "A"): "A", (n, on_b): "B", (n, on_c): "C"}
            continuing = "2" if normal == on_b else "4"
        self.add_turnout([n], ttype, c, {"A": A, "B": B, "C": C}, conn, blocks, continuing, at=junction)

    def share_name(self, u, v):
        """A crossover's halves drawn as two plain turnouts: when the names give both one turnout name, that name
        is one turnout drawn twice (P.split_names), as for a split crossover, so check_shared accepts it."""
        given = self.names.get("turnouts", {})
        if given.get(u) and given.get(u) == given.get(v):
            self.P.split_names.add(given[u])

    def crossovers(self):
        """Two switches of one number joined C to C, or halves lettered A and B joined B to C (core.crossover_halves):
        one single crossover, each half's through legs (A and its normal leg) on its own track."""
        split = self.P.split_crossovers.get(band_key(self.title), set())
        if split:
            self.split_moves(split)
        for sid, u, v in crossover_pairs(self.band):
            du = self.nodes[u]
            label = crossover_name(du["label"])     # the crossover's number (halves lettered A and B: without it)
            if (self.bi, u) in self.P.turnout_of or (self.bi, v) in self.P.turnout_of:
                continue
            level = all(abs(self.direction(n, p)[1]) < EPS for n in (u, v) for p in self.through(n))
            if not level:
                self.P.log.append(f"{self.title}: switches {label} are not drawn on two level tracks; "
                                  "drawn as two turnouts, not a crossover")
                self.share_name(u, v)
                continue
            top, tp, bot, bp = self.halves(u, v)
            if abs(tp[1] - bp[1]) < EPS:
                continue
            if label in split:        # two plain turnouts on its one name (turnout, later)
                name = self.names.get("turnouts", {}).get(u)
                if name:
                    self.P.split_names.add(name)
                continue
            try:
                self.too_deep(label, abs(bp[1] - tp[1]))
                self.tight_first(top, bot)
                tp, bp, _h = self.crossover_points(label, top, tp, bot, bp)
            except NoRoom as e:
                self.no_room |= {top, bot}
                self.P.xover_turnouts |= {(self.bi, top), (self.bi, bot)}    # let_in_mast_room may slide it its run
                self.P.log.append(f"{e}; drawn as two turnouts on its one turnout, not a crossover")
                name = self.names.get("turnouts", {}).get(u)
                if name:
                    self.P.split_names.add(name)
                continue
            # whole pixels, so the four points JMRI rebuilds from B, C and the centre are exactly the ones written
            tp, bp = self.whole_pixels(label, top, tp, bot, bp)
            h = abs(bp[0] - tp[0])
            self.short_of_run(label, h, abs(bp[1] - tp[1]))
            self.placed[top], self.placed[bot] = (tp[0], h), (bp[0], h)
            self.provisional -= {top, bot}
            self.no_room -= {top, bot}
            # JMRI's shape for a single crossover (LayoutTurnoutView keeps no other on load): each track's piece of
            # it, A-B and D-C, is twice the run of its diagonal, centred on that half's point
            pts = {"A": (tp[0] - h, tp[1]), "B": (tp[0] + h, tp[1]), "D": (bp[0] - h, bp[1]), "C": (bp[0] + h, bp[1])}
            conn = {}
            for n, left, right in ((top, "A", "B"), (bot, "D", "C")):
                for p in self.through(n):
                    conn[(n, p)] = left if self.direction(n, p)[0] < 0 else right
                if sorted(conn[(n, p)] for p in self.through(n)) != sorted((left, right)):
                    self.P.log.append(f"{self.title}: switch {label}: both through legs on one side")
                    break
            else:
                given = sorted(self.nodes[n].get("label") or n for n in (top, bot)
                               if n in self.names.get("normal", {}))
                if given:
                    raise SchematicError(f"{self.title}: names give normal for {', '.join(given)}, drawn as half of "
                                         f"single crossover {label}, whose closed route is both through tracks; "
                                         "remove that normal entry")
                ttype = "RH_XOVER" if bp[0] > tp[0] else "LH_XOVER"
                blocks = {"A": self.os_of(top), "B": self.os_of(top), "C": self.os_of(bot), "D": self.os_of(bot)}
                self.add_turnout([top, bot], ttype, mid(tp, bp), pts, conn, blocks)
                self.internal.add(sid)

    def too_deep(self, label, deep):
        """Raise NoRoom for a crossover `deep` px deep, more than one row, on a band with a crossover run: JMRI draws a
        single crossover with each track's piece twice its run across (crossover_points), so one two rows deep at the
        band's angle would take four runs of each track; drawn as two turnouts on its one name instead, its diagonal
        leg to leg is set to the run (le.let_in_mast_room slides it)."""
        if self.run() is not None and deep > self.row + EPS:
            raise NoRoom(f"{self.title}: switch {label}: drawn {deep / self.row:g} rows deep, so a crossover JMRI can "
                         f"draw at its run would take {2 * self.run_across(deep):.0f} px of each track")

    def short_of_run(self, label, h, deep):
        """On a band with a crossover run, log a single crossover drawn h px across, in whole pixels, short of its run
        (run_across) by more than PAIR_TOLERANCE, with its angle: crossover_points found no room for it
        (le.let_in_mast_room slides one on a solved band, so the final drawing logs only one it could not mend)."""
        run = self.run_across(deep)
        if run is not None and h < run - PAIR_TOLERANCE:
            self.P.log.append(f"{self.title}: switch {label}: crossover drawn {h:.1f} px across, "
                              f"{math.degrees(math.atan2(deep, h)):.1f} degrees: no room for {run:.1f} px")

    def over_room(self, n, x, h):
        """px by which a crossover half at node n, its point at x and its piece x-h to x+h, reaches past its room
        (room_toward) on either side; 0 when it does not."""
        worst = 0.0
        for p in self.through(n):
            side = 1 if self.direction(n, p)[0] > 0 else -1
            reach = (x + side * h - self.node_point(n)[0]) * side
            slack = 0.5 if self.partner(n, p) else 0.0     # room_toward keeps half a px there for this rounding
            worst = max(worst, reach - self.room_toward(n, p) - slack)
        return worst

    def whole_pixels(self, label, top, tp, bot, bp):
        """The halves' points rounded to whole pixels (so the four points JMRI rebuilds are the ones written), then
        checked: a piece that rounding takes past its room (room_toward: its far switch's leg and the least block
        beyond) by under ROUND_SLACK px is logged with the px; past its first piece's far end, or by more, stops.
        Rounding is not moved off the nearest pixel: approved panels hold these points."""
        tp, bp = (round(tp[0]), tp[1]), (round(bp[0]), bp[1])
        h = abs(bp[0] - tp[0])
        for n, x in ((top, tp[0]), (bot, bp[0])):
            for p in self.through(n):
                side = 1 if self.direction(n, p)[0] > 0 else -1
                end = x + side * h
                if (self.away(n, p)[1][0] - end) * side <= 0:
                    raise SchematicError(f"{self.title}: switch {label}: rounded to whole pixels, its crossover "
                                         f"reaches past the far end of its track toward leg {p}")
            over = self.over_room(n, x, h)
            if over > ROUND_SLACK:
                raise SchematicError(f"{self.title}: switch {label}: rounded to whole pixels, its crossover reaches "
                                     f"{over:.2f} px past the room its track gives it")
            if over > 1e-6:
                self.P.log.append(f"{self.title}: switch {label}: rounded to whole pixels, its crossover reaches "
                                  f"{over:.2f} px past the room its track gives it (its far switch's leg and the least "
                                  "block beyond that much shorter)")
        return tp, bp

    def move_node(self, n, dx):
        """Move node n dx px along its row: the end at n of each of its tracks' drawn lines."""
        for p in self.ports(n):
            sid = self.port_strand(n, p)
            pts = list(self.poly[sid])
            k = 0 if tuple(self.strands[sid]["src"]) == (n, p) else -1
            pts[k] = (pts[k][0] + dx, pts[k][1])
            self.poly[sid] = pts

    def split_moves(self, split):
        """Place the halves of the split crossovers (P.split_crossovers): a tight pair's halves on their shared track
        2 LEG and the track's least length apart (about their middle); then each crossover's other half slid along
        its row so its diagonal runs P.crossover_run across. Stops when a moved half's track is left shorter than a
        leg and MIN_BLOCK."""
        pairs = {}
        for _sid, u, v in crossover_pairs(self.band):
            if crossover_name(self.nodes[u].get("label")) in split:
                pairs[crossover_name(self.nodes[u]["label"])] = (u, v)
        # each half's first piece each way, before anything moves: a move must leave the half short of its far end
        was = {(n, p): (self.away(n, p)[1], self.direction(n, p)) for pair in pairs.values() for n in pair
               for p in self.ports(n)}
        inner, moved = {}, set()
        for a, b in self.P.tight_crossovers.get(band_key(self.title), []):
            if a not in split:
                continue
            shared = [(n, p) for n in pairs[a] for p in self.through(n) if self.partner(n, p)]
            if len(shared) != 1:
                raise SchematicError(f"{self.title}: crossovers {a} and {b} share no one track")
            n, p = shared[0]
            far = self.partner(n, p)[0]
            sid = self.port_strand(n, p)
            least = max(self.least_of(blk) for blk in self.blocks_of(sid))
            d = self.first_len(n, p)
            way = 1 if self.direction(n, p)[0] > 0 else -1
            pull = max(0.0, (d - (2 * LEG + least)) / 2)
            self.move_node(n, way * pull)
            self.move_node(far, -way * pull)
            inner[a], inner[b] = n, far
            moved |= {n, far}
        for label, (u, v) in sorted(pairs.items()):
            top, tp, bot, bp = self.halves(u, v)
            keep = inner.get(label, top)
            other = bot if keep == top else top
            run = self.run_across(abs(bp[1] - tp[1]))
            if run is not None:
                kx, ox = self.node_point(keep)[0], self.node_point(other)[0]
                way = 1 if ox >= kx else -1
                self.move_node(other, kx + way * run - ox)
                moved.add(other)
        for n in sorted(moved, key=str):
            for p in self.ports(n):
                far, d = was[(n, p)]
                left = dot(sub(far, self.node_point(n)), d)      # signed: below 0 once slid past the far end
                if left < LEG + MIN_BLOCK - EPS:
                    raise SchematicError(f"{self.title}: switch {self.nodes[n].get('label')}: drawn as two turnouts, "
                                         f"its track toward leg {p} is left {left:.1f} px"
                                         + (" (it slid past that track's far end)" if left < 0 else "")
                                         + f", under a leg and the least block ({LEG + MIN_BLOCK:g} px)")

    def halves(self, u, v):
        """(top node, its point, bottom node, its point) of the crossover of switches u and v."""
        pu_, pv_ = self.node_point(u), self.node_point(v)
        (top, tp), (bot, bp) = sorted(((u, pu_), (v, pv_)), key=lambda t: t[1][1])
        return top, tp, bot, bp

    def tight_first(self, top, bot):
        """Before the first of two crossovers drawn tight (P.tight_crossovers) is placed: the second one placed for
        now, slid as far from the first as its other track allows (its room toward the first unbounded), so the
        first may take all the room the second can give; the second is placed again after it, up to the first."""
        for n in (top, bot):
            for p in self.through(n):
                got = self.partner(n, p)
                if got is None or got[0] in self.placed:
                    continue
                pair = next((u, v) for _sid, u, v in crossover_pairs(self.band) if got[0] in (u, v))
                ot, otp, ob, obp = self.halves(*pair)
                try:
                    otp, obp, _h = self.crossover_points(got[1], ot, otp, ob, obp, log=False)
                except NoRoom:
                    self.no_room |= {ot, ob}    # (its own turn says so) bounded by its turnouts' legs till then
                    continue
                h = abs(round(obp[0]) - round(otp[0]))
                self.placed[ot], self.placed[ob] = (round(otp[0]), h), (round(obp[0]), h)
                self.provisional.update((ot, ob))

    def partner(self, n, port):
        """(far node, its crossover's label) when the track from crossover half n's leg `port` runs straight to a
        half of a crossover drawn tight with n's (P.tight_crossovers), else None."""
        mine = crossover_name(self.nodes[n].get("label"))
        pairs = self.P.tight_crossovers.get(band_key(self.title), [])
        sid = self.port_strand(n, port)
        s = self.strands[sid]
        far = s["dst"][0] if tuple(s["src"]) == (n, port) else s["src"][0]
        other = crossover_name(self.nodes[far].get("label"))
        halves = self.xlink
        if len(self.away(n, port)) == 2 and far in halves and any({mine, other} == set(p) for p in pairs):
            return far, other
        return None

    def run(self):
        """px across this band's crossovers' diagonals run (P.crossover_run, by band key when a dict), or None."""
        run = self.P.crossover_run
        return run.get(band_key(self.title)) if isinstance(run, dict) else run

    def run_across(self, deep):
        """px across a single crossover `deep` px deep runs: the band's run (run) per row deep, so one two rows deep
        crosses at the same angle as one a row deep; None when the band has no run."""
        run = self.run()
        if run is None:
            return None
        if deep < EPS:
            raise SchematicError(f"{self.title}: a single crossover drawn on one row has no diagonal to run across")
        return run * deep / self.row

    def room_toward(self, n, port):
        """px of track a crossover half at node n may take along its row toward `port` (its leg, and its own move
        that way): its first straight piece that way, less the far switch's leg when the piece runs straight to it,
        and MIN_BLOCK; shared half and half when the far switch is a crossover half that takes its share too."""
        pts = self.away(n, port)
        sid = self.port_strand(n, port)
        s = self.strands[sid]
        far = s["dst"][0] if tuple(s["src"]) == (n, port) else s["src"][0]
        halves = self.xlink
        if self.partner(n, port):       # drawn tight: the track between keeps only its block's least length
            least = max(self.least_of(b) for b in self.blocks_of(sid))
            if far in self.placed:      # up to the end of the other crossover's piece (half a px for rounding)
                fx, fh = self.placed[far]
                way = 1 if self.direction(n, port)[0] > 0 else -1
                return ((fx - way * fh) - pts[0][0]) * way - least - 0.5     # below 0 when it moved past n
            if far in self.no_room:     # drawn as two plain turnouts: up to the end of its leg this way
                way = 1 if self.direction(n, port)[0] > 0 else -1
                return ((self.node_point(far)[0] - way * LEG) - pts[0][0]) * way - least - 0.5
            return math.inf             # the other one is placed after this one (tight_first)
        if len(pts) == 2 and self.nodes[far]["kind"] in ("switch", "dx"):
            reserve, share = (1.5 * LEG, 0.5) if far in halves else (LEG, 1.0)
        else:
            reserve, share = 0.0, 1.0           # a bend first: its arc takes from the run beyond, not this piece
        return max(0.0, (self.first_len(n, port) - reserve - MIN_BLOCK) * share)

    def crossover_points(self, label, top, tp, bot, bp, log=True):
        """(top point, bottom point, h) of a single crossover as JMRI draws one: the run of its diagonal across
        (P.crossover_run per row deep, run_across; else as the sheet draws it) and each track's piece of it h = that run
        either side of its half's point, so A-B and D-C are twice the run (LayoutTurnoutView keeps no other shape: it
        rebuilds the crossover from B and C, or reshapes it, on load). The halves move apart along their rows and the
        crossover may slide along them as one, as far as each half's track on each side has room (room_toward); where no
        slide leaves room for the run asked, it takes the widest that fits (logged here with no crossover run, in whole
        pixels by short_of_run with one). Stops when not even a steep one fits. The sheet is not changed: only the
        Layout Editor drawing of the crossover."""
        dx0, dy = abs(bp[0] - tp[0]), abs(bp[1] - tp[1])
        way = 1 if bp[0] >= tp[0] else -1
        run = self.run_across(dy) if self.run() is not None else dx0
        rooms = {}
        for n in (top, bot):
            for side in (-1, 1):
                ports = [p for p in self.through(n) if self.direction(n, p)[0] * side > 0]
                if len(ports) != 1:
                    raise SchematicError(f"{self.title}: switch {label}: no one leg of the crossover leads that way")
                rooms[(n, side)] = self.room_toward(n, ports[0])

        def slide(m):
            """The (lo, hi) range of the common slide when the halves move m px apart each, or None."""
            h = dx0 + 2 * m
            if h <= 0:
                return None
            # top moves by -way*m + s, bottom by way*m + s; each half's piece takes h + move on the side it moves
            # toward and h - move on the other, within that side's room
            lo = max(h + way * m - rooms[(top, -1)], h - way * m - rooms[(bot, -1)])
            hi = min(rooms[(top, 1)] - h + way * m, rooms[(bot, 1)] - h - way * m)
            return (lo, hi) if lo <= hi + EPS else None

        want = (run - dx0) / 2
        if slide(want) is not None:
            m = want
        else:
            a = 0.5 - dx0 / 2                   # the steepest: a 1 px run
            if slide(a) is None:
                raise NoRoom(f"{self.title}: switch {label}: no room for a crossover JMRI can draw (its track "
                             "pieces would be twice its run across)")
            b = want
            for _ in range(60):
                mid_ = (a + b) / 2
                a, b = (mid_, b) if slide(mid_) is not None else (a, mid_)
            m = a
            got = dx0 + 2 * m
            if log and self.run() is None:      # with a run, crossovers() logs it in whole pixels (short_of_run)
                self.P.log.append(f"{self.title}: switch {label}: crossover drawn {got:.1f} px across, "
                                  f"{math.degrees(math.atan2(dy, got)):.1f} degrees: no room for {run:.1f} px")
        lo, hi = slide(m)
        shift = min(max(0.0, lo), hi)
        for n in (top, bot):            # of two drawn tight: the second placed for now slides as far from the
            for p in self.through(n):   # first as it may (tight_first), the first as usual, the second up to it
                got = self.partner(n, p)
                if got is None or got[0] in self.provisional:
                    continue
                toward = self.direction(n, p)[0] > 0
                shift = (hi if toward else lo) if got[0] in self.placed else (lo if toward else hi)
        return (tp[0] - way * m + shift, tp[1]), (bp[0] + way * m + shift, bp[1]), dx0 + 2 * m

    def double(self, n):
        ends = {}
        for p in "ABCD":
            pts = self.away(n, p)
            dx_ = pts[1][0] - pts[0][0]
            if abs(dx_) < 1e-3:
                raise SchematicError(f"{self.title}: double crossover {self.nodes[n].get('label') or n}: leg {p} "
                                     "leaves straight up or down, so it is on neither side of the crossover")
            if abs(pts[1][1] - pts[0][1]) > EPS:
                self.P.log.append(f"{self.title}: double crossover {self.nodes[n].get('label') or n}: leg {p} "
                                  "does not leave on the level")
            ends[p] = (pts[0], "left" if dx_ < 0 else "right")
        ys = sorted({round(e[0][1], 3) for e in ends.values()})
        if len(ys) != 2:
            raise SchematicError(f"{self.title}: double crossover {self.nodes[n].get('label') or n} is not drawn "
                                 "across two tracks")
        xc = sum(e[0][0] for e in ends.values()) / 4
        if any(abs(e[0][0] - xc) > 0.5 for e in ends.values()):
            raise SchematicError(f"{self.title}: double crossover {self.nodes[n].get('label') or n}: its four legs "
                                 "do not start at one column")
        h = min([0.5 * (ys[1] - ys[0])] + [0.4 * self.first_len(n, p) for p in "ABCD"])
        if self.run() is not None:      # its diagonals run as far across as a single crossover's, where there is room
            # JMRI draws a double crossover's diagonals from 5/8 of the way along each half side (A to the middle of
            # A-B, ...) to the centre, so they run 3/8 of h across per half its height: h = 4/3 of the run. The room
            # each way is its first piece less MIN_BLOCK (known limit: the far switch's leg is not reserved; strand()
            # stops if that leaves a track shorter than its switches' legs)
            label = self.nodes[n].get('label') or n
            room = min(self.first_len(n, p) for p in "ABCD") - MIN_BLOCK
            want = 4 * self.run() / 3
            got = min(want, room)       # the run asked, shorter or longer than the sheet's, as the singles
            if got <= 0:
                raise SchematicError(f"{self.title}: double crossover {label}: no room along its tracks for its "
                                     "diagonals")
            if got < want - EPS:
                self.P.log.append(f"{self.title}: double crossover {label} drawn "
                                  f"{0.75 * got:.1f} px across, "
                                  f"{math.degrees(math.atan2(ys[1] - ys[0], 0.75 * got)):.1f} "
                                  f"degrees: no room for {self.run():.1f} px")
            h = got
        h, xc = round(h), round(xc * 2) / 2     # whole and half pixels: JMRI rebuilds the same four points
        corner = {(ys[0], "left"): "A", (ys[0], "right"): "B", (ys[1], "right"): "C", (ys[1], "left"): "D"}
        conn = {(n, p): corner[(round(e[0][1], 3), e[1])] for p, e in ends.items()}
        if sorted(conn.values()) != list("ABCD"):
            raise SchematicError(f"{self.title}: double crossover {self.nodes[n].get('label') or n}: its legs do not "
                                 "reach four corners")
        pts = {"A": (xc - h, ys[0]), "B": (xc + h, ys[0]), "C": (xc + h, ys[1]), "D": (xc - h, ys[1])}
        if {p: leg for (_n, p), leg in conn.items()} != double_corners(self.band, n, self.turned, self.drawn):
            raise SchematicError(f"{self.title}: double crossover {self.nodes[n].get('label') or n}: its corners "
                                 "differ from double_corners'")     # an invariant: callers name blocks by it
        corners = xover_blocks(self.band, self.names).get(n)
        if not corners:
            self.P.log.append(f"{self.title}: double crossover {self.nodes[n].get('label') or n} is one OS block, "
                              "as named (xover_blocks \"one\"): JMRI records a through path between its two "
                              "legs on one side")
        b = self.os_of(n)
        self.add_turnout([n], "DOUBLE_XOVER", (xc, (ys[0] + ys[1]) / 2), pts, conn,
                         {corner: corners[port] for (_n, port), corner in conn.items()} if corners else
                         {k: b for k in "ABCD"})

    # ---- ends
    def end(self, n):
        d = self.nodes[n]
        port = self.ports(n)[0]
        pts = self.away(n, port)
        sid = self.port_strand(n, port)
        joined = (self.bi, n) in self.joined
        ident = self.P.point("ANCHOR" if joined else "END_BUMPER", pts[0], end=True)
        self.conn[(n, port)] = ident
        self.leg_pt[(n, port)] = pts[0]
        out = unit(sub(pts[0], pts[1]))
        blocks = self.blocks_of(sid)
        at_src = tuple(self.strands[sid]["src"]) == (n, port)
        self.ends[(self.bi, n)] = (ident, sid, out, blocks[0] if at_src else blocks[-1], self.strands[sid]["main"])
        to = (d.get("to") or "").upper()
        side = "left" if out[0] > 0 else "right"
        if d.get("sub") == "helix":
            centre = add(pts[0], out, HELIX_R)
            self.P.shapes.append(dict(ident=self.P.ident("SH"), centre=list(centre), r=HELIX_R, band=self.bi))
            tip = add(centre, out, HELIX_R + 4)
            self.P.label(f"HELIX TO {to}".strip(), (tip[0], tip[1] - LABEL_SIZE / 2 - 1), LABEL_SIZE - 1, anchor=side)
        elif d.get("sub") == "link":        # the connector letter in a circle, where it goes above it
            centre = add(pts[0], out, HELIX_R)
            self.P.shapes.append(dict(ident=self.P.ident("SH"), centre=list(centre), r=HELIX_R, band=self.bi))
            self.P.label(d.get("label") or "", (centre[0], centre[1] - NUMBER_SIZE / 2 - 1), NUMBER_SIZE, True)
            if to:
                self.P.label(f"TO {to}", (centre[0], centre[1] - HELIX_R - LABEL_SIZE - 4), LABEL_SIZE - 2)

    # ---- tracks
    def strand(self, sid):
        s = self.strands[sid]
        (u, pu), (v, pv) = s["src"], s["dst"]
        pts = list(self.poly[sid])
        pts[0], pts[-1] = self.leg_pt[(u, pu)], self.leg_pt[(v, pv)]
        pts = clean(pts)
        if len(pts) < 2:
            raise SchematicError(f"{self.title}: track {s['name'] or sid} is shorter than its switches' legs")
        pieces = rounded(pts)
        blocks = self.blocks_of(sid)
        pieces = split(pieces, len(blocks), f"{self.title}: track {s['name'] or sid}", self.shares_of(sid, blocks),
                       [self.least_of(b) for b in blocks], [self.room_at(a, b) for a, b in zip(blocks, blocks[1:])],
                       self.P.log)
        prev = self.conn[(u, pu)]
        for i, (pc, k) in enumerate(pieces):
            nxt = self.conn[(v, pv)] if i == len(pieces) - 1 else self.P.point("ANCHOR", pc["b"])
            arc = None
            if pc["kind"] == "arc":
                flip = flip_toward(pc["a"], pc["b"], pc["angle"], pc["toward"])
                arc = dict(angle=pc["angle"], flip=flip, drawn=arc_points(pc["a"], pc["b"], pc["angle"], flip))
            seg = self.P.segment(prev, nxt, blocks[k], s["main"], dashed=s.get("hidden", False), arc=arc)
            self.P.strand_segments[(self.bi, sid)].append(seg)
            prev = nxt

    def turnback(self, t):
        ports = self.ports(t)
        a, b = (self.leg_pt[(t, p)] for p in ports)
        sids = [self.port_strand(t, p) for p in ports]
        (a, pa, sa), (b, pb, sb) = sorted(((a, ports[0], sids[0]), (b, ports[1], sids[1])), key=lambda e: e[0][1])
        line = [self.px(p) for p in self.drawn[t]]
        out = 1 if line[1][0] > line[0][0] else -1          # the way the turnback bows
        r = (b[1] - a[1]) / 2
        if r <= EPS:
            raise SchematicError(f"{self.title}: a turnback joins two tracks on one row")
        x = max(a[0], b[0]) if out > 0 else min(a[0], b[0])   # the end further out: the other is run on to it
        apex_id = self.P.point("ANCHOR", (x + out * r, (a[1] + b[1]) / 2))
        segs = []
        for (p, port, sid), first in (((a, pa, sa), True), ((b, pb, sb), False)):
            s = self.strands[sid]
            blocks = self.blocks_of(sid)
            block = blocks[0] if tuple(s["src"]) == (t, port) else blocks[-1]
            here = self.conn[(t, port)]
            if abs(p[0] - x) > 0.01:        # a straight first, so both quarter arcs start level at one column
                q = (x, p[1])
                q_id = self.P.point("ANCHOR", q)
                segs.append(self.P.segment(here, q_id, block, s["main"], dashed=s.get("hidden", False)))
                here, p = q_id, q
            apex = self.P.points[apex_id]["xy"]
            p1, p2 = (p, apex) if first else (apex, p)
            flip = flip_toward(p1, p2, 90.0, (p[0] + out * r, p[1]))
            arc = dict(angle=90.0, flip=flip, drawn=arc_points(p1, p2, 90.0, flip))
            c1, c2 = (here, apex_id) if first else (apex_id, here)
            segs.append(self.P.segment(c1, c2, block, s["main"], dashed=s.get("hidden", False), arc=arc))
        self.P.turnbacks[(self.bi, t)] = segs

    # ---- names on the drawing
    def labels(self):
        P = self.P
        for t in self.mine:
            label = self.nodes[t["nodes"][0]].get("label") or ""
            if not label:
                continue
            cen = t["at"]           # where the drawn legs meet (the centre moves with leg_b)
            if "XOVER" in t["type"]:
                top = min(p[1] for p in t["pts"].values())
                if t["type"] in ("RH_XOVER", "LH_XOVER"):      # a single crossover: its number, not a half's letter
                    label = crossover_name(label)
                P.label(label, (cen[0], top - NUMBER_SIZE - 5), NUMBER_SIZE, True, kind="switch")
                continue
            down = t["pts"]["C"][1] > cen[1] + EPS or t["pts"]["B"][1] > cen[1] + EPS
            y = cen[1] - NUMBER_SIZE - 6 if down else cen[1] + 5
            P.label(label, (cen[0], y), NUMBER_SIZE, True, kind="switch")
        for sid, s in sorted(self.strands.items()):
            if not s["name"] or sid in self.internal or s.get(le_labels.HIDDEN):     # hidden_names: no room
                continue
            pts = self.poly[sid]
            runs = [(a, b) for a, b in zip(pts, pts[1:]) if abs(a[1] - b[1]) < EPS]
            if not runs:
                P.no_name[(self.bi, sid)] = "no level run to keep room for its name on"
                continue
            a, b = max(runs, key=lambda r: (abs(r[1][0] - r[0][0]), -min(r[0][0], r[1][0])))
            text = tidy([s["name"]])[0]
            if room_width(text, LABEL_SIZE) > abs(b[0] - a[0]) * 1.6:
                P.no_name[(self.bi, sid)] = "its longest level run is too short for its name"
                continue
            P.label(text, ((a[0] + b[0]) / 2, a[1] - LABEL_SIZE - 5), kind="name")
            P.labels[-1]["run"] = [list(a), list(b)]        # the mast icons leave this room out (le_masts)
        # station names (the `stations` preference) under the band, or over it for a station on the top side
        ys = [p[1] for pts in self.poly.values() for p in pts]
        by_label = defaultdict(list)
        for t in self.mine:
            for n in t["nodes"]:
                by_label[(self.nodes[n].get("label") or "").rstrip("*")].append(t["at"][0])
        for name, e in stations.entries(self.opts).items():
            xs = [x for sw in e["switches"] for x in by_label.get(str(sw), ())]
            if not xs:
                continue
            y = max(ys) + 2 * LABEL_SIZE if e["side"] == "bottom" else min(ys) - 3 * LABEL_SIZE - 8
            P.label(name.upper(), ((min(xs) + max(xs)) / 2, y), LABEL_SIZE, True, kind="station")


def rounded(pts):
    """The pieces of a polyline with each corner rounded: dicts kind line/arc, a, b (and angle, toward)."""
    out, cur = [], pts[0]
    for i in range(1, len(pts) - 1):
        V = pts[i]
        din, dout = unit(sub(V, pts[i - 1])), unit(sub(pts[i + 1], V))
        theta = math.acos(max(-1.0, min(1.0, dot(din, dout))))
        if theta < 1e-3:
            continue
        t = min(BEND * math.tan(theta / 2), 0.45 * math.dist(pts[i - 1], V), 0.45 * math.dist(V, pts[i + 1]))
        p1, p2 = add(V, din, -t), add(V, dout, t)
        if math.dist(cur, p1) > 0.01:
            out.append(dict(kind="line", a=cur, b=p1))
        out.append(dict(kind="arc", a=p1, b=p2, angle=round(math.degrees(theta), 3), toward=V))
        cur = p2
    if math.dist(cur, pts[-1]) > 0.01 or not out:
        out.append(dict(kind="line", a=cur, b=pts[-1]))
    return out


def piece_len(pc):
    if pc["kind"] == "line":
        return math.dist(pc["a"], pc["b"])
    chord = math.dist(pc["a"], pc["b"])
    th = math.radians(pc["angle"])
    return chord / 2 / math.sin(th / 2) * th


def split(pieces, k, what, shares=None, least=None, room=None, log=None):
    """[(piece, block index)]: the pieces of a strand of k blocks, cut where one block ends and the next begins.
    `shares` (k positive numbers, the blocks' real lengths in any one unit) set where the cuts would fall; without
    them the blocks are equal. Every block is drawn at least MIN_BLOCK px long, or its `least` (px per block) when
    given; on a strand too short for that, its equal share. A cut stands on straight track or at a piece's end,
    never inside an arc. `room` ((before, after) px per cut) is the straight track the icons of the masts at a cut
    need on each side: the cut stands on a straight piece with that room when the others allow it (else it is noted
    in `log` and only kept off arcs). Each cut takes the place nearest its share that leaves every block, before and
    after it, its least length, in order; a strand with no such places stops."""
    total = sum(piece_len(p) for p in pieces)
    if k == 1:
        return [(pc, 0) for pc in pieces]
    shares = list(shares) if shares else [1.0] * k
    floors = [min(f, total / k) for f in (least or [MIN_BLOCK] * k)]
    lens = [total * v / sum(shares) for v in shares]
    short = set()
    for _ in range(k):               # the short blocks take their floor, the others give it up in proportion
        more = {i for i, v in enumerate(lens) if v < floors[i] - EPS} - short
        if not more:
            break
        short |= more
        rest = total - sum(floors[i] for i in short)
        big = sum(shares[i] for i in range(k) if i not in short)
        lens = [floors[i] if i in short else (shares[i] * rest / big if big else 0.0) for i in range(k)]
    targets, acc = [], 0.0
    for v in lens[:-1]:
        acc += v
        targets.append(acc)
    starts, run = [], 0.0
    for pc in pieces:
        starts.append(run)
        run += piece_len(pc)
    # where a cut may stand: on a straight piece, or at the end of any piece (never inside an arc)
    base = [(s0, s0 + piece_len(pc)) for pc, s0 in zip(pieces, starts) if pc["kind"] == "line"] + \
        [(s0, s0) for s0 in starts[1:]]
    allowed = []
    for j in range(k - 1):
        before, after = (room or [(0, 0)] * (k - 1))[j]
        roomy = [(s0 + before, s0 + piece_len(pc) - after) for pc, s0 in zip(pieces, starts)
                 if pc["kind"] == "line" and piece_len(pc) >= before + after] if before or after else base
        if not roomy:
            if log is not None:
                log.append(f"{what}: no straight piece leaves room for the icons at the cut after its block "
                           f"{j + 1} ({before:g} px before, {after:g} px after); that cut is only kept off arcs")
            roomy = base
        allowed.append(roomy)

    def place(sets):
        """The cuts: each the place in its set nearest its target, leaving every block its floor; None if none."""
        latest = [None] * (k - 1)
        bound = total - floors[k - 1]
        for j in reversed(range(k - 1)):
            cand = [min(hi, bound) for lo, hi in sets[j] if lo <= bound + EPS]
            if not cand:
                return None
            latest[j] = max(cand)
            bound = latest[j] - floors[j]
        out, prev = [], 0.0
        for j in range(k - 1):
            lo_, hi_ = prev + floors[j], latest[j]
            cand = [min(max(targets[j], max(lo, lo_)), min(hi, hi_)) for lo, hi in sets[j]
                    if max(lo, lo_) <= min(hi, hi_) + EPS]
            if not cand:
                return None
            prev = min(cand, key=lambda t: (abs(t - targets[j]), t))
            out.append(prev)
        return out
    cuts = place(allowed)
    if cuts is None and room:
        if log is not None:
            log.append(f"{what}: no straight places leave room for the icons at its cuts and every block its least "
                       "length; its cuts are only kept off arcs")
        cuts = place([base] * (k - 1))
    if cuts is None:
        raise SchematicError(f"{what}: too short to draw its {k} blocks in order, each at least "
                             f"{', '.join(f'{f:.0f}' for f in floors)} px, with no cut inside an arc")
    edges = [0.0] + cuts + [total]
    if any(b - a < floors[i] - 1e-6 for i, (a, b) in enumerate(zip(edges, edges[1:]))):
        raise SchematicError(f"{what}: a block drawn shorter than its least length")
    out = []
    for pc, s0 in zip(pieces, starts):
        L = piece_len(pc)
        inner = [c - s0 for c in cuts if s0 + EPS < c < s0 + L - EPS]
        if pc["kind"] == "line" and inner:
            a = pc["a"]
            for c in inner:
                q = add(pc["a"], unit(sub(pc["b"], pc["a"])), c)
                out.append(dict(kind="line", a=a, b=q))
                a = q
            out.append(dict(kind="line", a=a, b=pc["b"]))
        else:
            out.append(pc)
    got, run = [], 0.0
    for pc in out:
        L = piece_len(pc)
        mid_ = run + L / 2
        got.append((pc, sum(mid_ > c for c in cuts)))
        run += L
    if len({i for _, i in got}) != k:
        raise SchematicError(f"{what}: too short to hold its {k} blocks")
    return got
