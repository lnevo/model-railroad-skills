"""Pieces: name every track piece in AnyRail's "export to JMRI" file by its geometry, never by a catalogue name.

The export holds no part numbers, makers or heights, only shapes, so every piece is told by what it is:

- straight: a plain <tracksegment>; its length.
- curve: a segment with arc="yes" and circle="yes"; JMRI keeps the arc's angle, so the radius is
  chord / (2 sin(angle / 2)) and the length radius * angle.
- flex: a segment with bezier="yes"; JMRI draws a Bezier through its end points and control points, so the
  length is measured along the curve, the turn is the change of heading between its ends, and the tightest
  radius is found along it.
- turnout: a <layoutturnout> of type LH_TURNOUT, RH_TURNOUT or WYE_TURNOUT. AnyRail exports each turnout part as a
  short JMRI turnout with one track segment on each leg, out to the part's own end point, so the part's three end
  points are the far ends of those segments. From them: the length of the straight route, the chord of the
  diverging route and the side the diverging leg leaves on. The heading where each leg leaves the part is read
  from the plain or flex track joined beyond its end, and gives the shape (the B leg runs on along its chord on a
  straight turnout, bends toward the diverging leg on a curved one and away from it on a wye; with nothing beyond
  B, the track beyond the points gives the line instead) and the diverging angle, the change of heading between
  the two legs. A straight turnout or wye also gets its frog number, 1 / (2 tan(angle / 2)). With nothing to read
  beyond, the shape is "unknown" and a note says so. AnyRail exports a three-way part as two turnouts.
- double crossover: a DOUBLE_XOVER turnout; its four end points, length and track spacing.
- track end: an END_BUMPER point.

Anything else (a level crossing, a slip, a turntable, an elliptical arc, another turnout type) is listed under
`skipped` with the reason, so nothing is dropped unseen.

Lengths come out in centimetres. The export is in screen pixels; a recent AnyRail export was at 12 px per inch
(`plan_reader.PX_PER_CM`, the default) and older ones smaller, so give `px_per_cm` when a check against AnyRail shows
another size.

Coordinates are the export's: x to the right, y down the screen, headings in degrees clockwise from +x.
"""
import collections
import math
import xml.etree.ElementTree as ET

from .plan_reader import PX_PER_CM, PlanError, cross, number, turnout_point

TURNOUT_TYPES = ("LH_TURNOUT", "RH_TURNOUT", "WYE_TURNOUT")
FROG_SHAPES = ("straight", "wye")     # a curved turnout gets its angle between legs but no frog number
IN_LINE_DEG = 1.5       # a leg within this angle of the line of the points runs straight through (joins are rarely truer)
HEADING_MATCH_DEG = 30  # a heading read beyond an end must lie this close to the leg's own direction
SAMPLES = 400           # steps along a flex piece for its length and tightest radius
CM_PER_IN = 2.54


def _wrap(deg):
    return (deg + 180.0) % 360.0 - 180.0


def _heading(p, q):
    return math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))


def _bezier(points, t):
    """Point on the Bezier with these control points (end points included) at t, by de Casteljau."""
    pts = list(points)
    while len(pts) > 1:
        pts = [((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1]) for a, b in zip(pts, pts[1:])]
    return pts[0]


def _derivative(points):
    n = len(points) - 1
    return [(n * (b[0] - a[0]), n * (b[1] - a[1])) for a, b in zip(points, points[1:])]


def bezier_geometry(points):
    """(length, tightest radius or None when straight) of a Bezier given its control points, end points included."""
    if len(points) < 3:
        raise PlanError(f"a Bezier needs at least one control point between its ends, got {len(points)} points")
    d1 = _derivative(points)
    d2 = _derivative(d1) if len(d1) > 1 else None
    length, prev, tightest = 0.0, points[0], None
    for i in range(SAMPLES + 1):
        t = i / SAMPLES
        if i:
            p = _bezier(points, t)
            length += math.dist(prev, p)
            prev = p
        v = _bezier(d1, t)
        speed = math.hypot(*v)
        if d2 is None or speed < 1e-9:
            continue
        bend = abs(cross(v, _bezier(d2, t)))
        if bend > 1e-12:
            r = speed ** 3 / bend
            tightest = r if tightest is None else min(tightest, r)
    return length, tightest


class Export:
    """The export's elements by ident, with the end point of any connection."""

    def __init__(self, path):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as e:
            raise PlanError(f"{path}: not readable XML ({e})") from None
        except OSError as e:
            raise PlanError(f"{path}: cannot be read ({e.strerror})") from None
        panel = root.find("LayoutEditor") if root.tag != "LayoutEditor" else root
        if panel is None:
            raise PlanError(f"{path}: no <LayoutEditor> panel; is it AnyRail's JMRI export?")
        self.turnouts = self._index(panel, "layoutturnout")
        self.segments = self._index(panel, "tracksegment")
        self.points = self._index(panel, "positionablepoint")
        self.others = [(el.tag, el.get("ident")) for tag in ("levelxing", "layoutSlip", "layoutturntable")
                       for el in panel.iter(tag)]
        if not self.segments and not self.turnouts:
            raise PlanError(f"{path}: the panel holds no track")
        self.at = collections.defaultdict(list)       # element ident -> segments joined to it
        for s in self.segments.values():
            for k in (1, 2):
                name, kind = s.get(f"connect{k}name"), s.get(f"type{k}")
                if not name or not kind:
                    raise PlanError(f"tracksegment {s.get('ident')!r}: connect{k}name or type{k} is missing")
                self.at[name].append(s)

    @staticmethod
    def _index(panel, tag):
        out = {}
        for el in panel.iter(tag):
            ident = el.get("ident")
            if not ident:
                raise PlanError(f"a <{tag}> has no ident")
            if ident in out:
                raise PlanError(f"two <{tag}> elements share the ident {ident!r}")
            out[ident] = el
        return out

    def where(self, name, kind):
        """The px point of a segment end: a positionable point, or a turnout's leg."""
        if kind == "POS_POINT":
            p = self.points.get(name)
            if p is None:
                raise PlanError(f"a track segment joins the point {name!r}, which the export does not have")
            return number(p, "x"), number(p, "y")
        if kind.startswith("TURNOUT_") and len(kind) == 9 and kind[-1] in "ABCD":
            t = self.turnouts.get(name)
            if t is None:
                raise PlanError(f"a track segment joins the turnout {name!r}, which the export does not have")
            return turnout_point(t, kind[-1])
        return None                                    # a crossing, slip or turntable: not read

    def ends(self, s):
        return [(s.get("connect1name"), s.get("type1")), (s.get("connect2name"), s.get("type2"))]

    def far_end(self, s, frm):
        """The (name, kind) at the other end of segment `s` from element `frm`."""
        a, b = self.ends(s)
        return b if a[0] == frm else a

    def path_points(self, s):
        """[end 1, control points..., end 2] in px, or None when an end is on an element not read."""
        e1, e2 = (self.where(*e) for e in self.ends(s))
        if e1 is None or e2 is None:
            return None
        ctrl = []
        for c in s.iter("controlpoint"):
            ctrl.append((int(number(c, "index")), (number(c, "x"), number(c, "y"))))
        ctrl.sort()
        return [e1, *[p for _, p in ctrl], e2]


def _segment_piece(ex, s, scale):
    """A plain, curved or flex segment as a piece, or (None, reason)."""
    pts = ex.path_points(s)
    if pts is None:
        return None, "an end is on a crossing, slip or turntable, which this command does not read"
    chord = math.dist(pts[0], pts[-1]) / scale
    ident = s.get("ident")
    if s.get("arc") == "yes":
        if s.get("circle") != "yes":
            return None, "an elliptical arc (circle is not yes), not a circular curve"
        angle = number(s, "angle")
        if not 0 < angle < 360:
            raise PlanError(f"tracksegment {ident!r}: arc angle {angle} is outside 0 to 360 degrees")
        radius = chord / (2 * math.sin(math.radians(angle) / 2))
        return dict(id=ident, kind="curve", radius_cm=radius, angle_deg=angle,
                    length_cm=radius * math.radians(angle)), None
    if s.get("bezier") == "yes":
        if len(pts) < 3:
            raise PlanError(f"tracksegment {ident!r}: bezier='yes' but no control points")
        length, tight = bezier_geometry(pts)
        turn = _wrap(_heading(pts[-2], pts[-1]) - _heading(pts[0], pts[1]))
        return dict(id=ident, kind="flex", length_cm=length / scale, turn_deg=turn,
                    tightest_radius_cm=None if tight is None else tight / scale), None
    return dict(id=ident, kind="straight", length_cm=chord), None


def _heading_beyond(ex, end_name, end_kind, leg_segment, leg_seen):
    """The heading of the track leaving a part's end point outward, read from the one segment joined beyond it, or
    None: nothing beyond, a curve (its tangent is not read), another turnout's leg (drawn short, not to scale)."""
    if end_kind != "POS_POINT":
        return None
    beyond = [s for s in ex.at[end_name] if s is not leg_segment]
    if len(beyond) != 1 or beyond[0].get("ident") in leg_seen or beyond[0].get("arc") == "yes":
        return None
    pts = ex.path_points(beyond[0])
    if pts is None:
        return None
    if beyond[0].get("connect1name") == end_name:
        return _heading(pts[0], pts[1])
    return _heading(pts[-1], pts[-2])


def _legs(ex, ident, t, legs):
    """{leg: (end px, end name, end kind, the leg's segment or None)} for a turnout."""
    out = {}
    for leg in legs:
        name = t.get(f"connect{leg.lower()}name")
        s = ex.segments.get(name) if name else None
        if name and s is None:
            raise PlanError(f"layoutturnout {ident!r}: leg {leg} joins {name!r}, which is not a track segment")
        if s is None:           # nothing on this leg: the turnout's own leg point is the part's end
            out[leg] = (turnout_point(t, leg), None, None, None)
            continue
        far = ex.far_end(s, ident)
        xy = ex.where(*far)
        if xy is None:
            raise PlanError(f"layoutturnout {ident!r}: leg {leg} runs to {far[0]!r}, a crossing, slip or turntable")
        out[leg] = (xy, far[0], far[1], s)
    return out


def _turnout_piece(ex, ident, t, scale, leg_seen):
    legs = _legs(ex, ident, t, "ABC")
    a, b, c = (legs[k][0] for k in "ABC")
    if min(math.dist(a, b), math.dist(a, c)) < 1e-6:
        raise PlanError(f"layoutturnout {ident!r}: a leg ends on its points end; the turnout has no length")
    heads = {}
    for k in "ABC":
        h = _heading_beyond(ex, legs[k][1], legs[k][2], legs[k][3], leg_seen)
        # a heading far from the leg's own way out is not this leg's track (a reversing curve, a join): not used
        out = _heading(legs["B"][0], a) if k == "A" else _heading(a, legs[k][0])
        heads[k] = h if h is not None and abs(_wrap(h - out)) <= HEADING_MATCH_DEG else None
    side = cross((b[0] - a[0], b[1] - a[1]), (c[0] - a[0], c[1] - a[1]))
    c_side = 1 if side > 0 else -1             # y down the screen: positive is clockwise, to the right
    notes = []
    if heads["B"] is not None:
        # The B leg's way out against its own chord: it runs on along the chord for a straight part, bends toward C
        # on a curved one and away from C on a wye. Read inside the part's two ends, a kinked join at the points
        # does not change it.
        bend = _wrap(heads["B"] - _heading(a, b))
        if abs(bend) <= IN_LINE_DEG:
            shape = "straight"
        else:
            shape = "curved" if (bend > 0) == (c_side > 0) else "wye"
    elif heads["A"] is not None:
        # Nothing to read beyond B: the line of the points is the track joined beyond the points end, and a leg
        # whose end lies within IN_LINE_DEG of it runs straight through.
        line = _wrap(heads["A"] + 180)
        off_b, off_c = _wrap(_heading(a, b) - line), _wrap(_heading(a, c) - line)
        if abs(off_b) <= IN_LINE_DEG:
            shape = "straight"
            heads["B"] = line
        elif abs(off_c) <= IN_LINE_DEG:
            shape = "unknown"
            notes.append("its C leg runs in line with the track beyond its points and B does not")
        else:
            shape = "wye" if (off_b > 0) != (off_c > 0) else "curved"
    else:
        shape = "unknown"
        notes.append("shape not read: no plain or flex track beyond its points or its straight leg; look at the part "
                     "in AnyRail")
    hand = None if shape in ("wye", "unknown") else ("R" if c_side > 0 else "L")
    angle = abs(_wrap(heads["C"] - heads["B"])) if heads["B"] is not None and heads["C"] is not None else None
    frog = frog_number(angle) if angle and shape in FROG_SHAPES else None
    kind_hand = {"LH_TURNOUT": "L", "RH_TURNOUT": "R"}.get(t.get("type"))
    if hand and kind_hand and hand != kind_hand:
        notes.append(f"the export calls it {t.get('type')}, its legs draw a {hand} hand")
    return dict(id=ident, kind="turnout", shape=shape, hand=hand, straight_cm=math.dist(a, b) / scale,
                diverging_chord_cm=math.dist(a, c) / scale, angle_deg=angle, frog_number=frog,
                ends_cm=[[round(v / scale, 2) for v in p] for p in (a, b, c)], notes=notes)


def _crossover_piece(ex, ident, t, scale):
    legs = _legs(ex, ident, t, "ABCD")
    a, b, c, d = (legs[k][0] for k in "ABCD")
    length = math.dist(a, b)
    if length < 1e-6:
        raise PlanError(f"layoutturnout {ident!r}: its A and B ends meet; the double crossover has no length")
    spacing = abs(cross((b[0] - a[0], b[1] - a[1]), (d[0] - a[0], d[1] - a[1]))) / length
    return dict(id=ident, kind="double_crossover", length_cm=length / scale, spacing_cm=spacing / scale,
                ends_cm=[[round(v / scale, 2) for v in p] for p in (a, b, c, d)], notes=[])


def read(path, px_per_cm=PX_PER_CM):
    """{scale_px_per_cm, pieces [...], track_ends, skipped [(ident, reason)]} for an AnyRail JMRI export."""
    if not (isinstance(px_per_cm, (int, float)) and math.isfinite(px_per_cm) and px_per_cm > 0):
        raise PlanError(f"the scale must be a number of px per cm above 0, got {px_per_cm!r}")
    ex = Export(path)
    pieces, skipped = [], []
    leg_seen = set()
    for ident, t in ex.turnouts.items():
        ty = t.get("type")
        if ty in TURNOUT_TYPES or ty == "DOUBLE_XOVER":
            for leg in "ABCD":
                name = t.get(f"connect{leg.lower()}name")
                if name in ex.segments:
                    leg_seen.add(name)
    for ident, t in ex.turnouts.items():
        ty = t.get("type")
        if ty in TURNOUT_TYPES:
            pieces.append(_turnout_piece(ex, ident, t, px_per_cm, leg_seen))
        elif ty == "DOUBLE_XOVER":
            pieces.append(_crossover_piece(ex, ident, t, px_per_cm))
        else:
            skipped.append((ident, f"turnout type {ty}, which this command does not read"))
    for ident, s in ex.segments.items():
        if ident in leg_seen:
            continue
        piece, why = _segment_piece(ex, s, px_per_cm)
        if piece is None:
            skipped.append((ident, why))
        else:
            pieces.append(piece)
    skipped += [(ident, f"a <{tag}>, which this command does not read") for tag, ident in ex.others]
    ends = sum(1 for p in ex.points.values() if p.get("type") == "END_BUMPER")
    named = {p["id"] for p in pieces} | {ident for ident, _ in skipped}
    unread = [i for i in [*ex.turnouts, *ex.segments] if i not in named and i not in leg_seen]
    if unread or len(named) != len(pieces) + len(skipped):
        raise PlanError(f"pieces left unread or read twice (a turnout and a segment sharing an ident?): {unread}")
    return dict(scale_px_per_cm=px_per_cm, pieces=pieces, track_ends=ends, skipped=skipped)


GROUP_CM = 0.25         # two pieces whose sizes differ by no more than this are the same kind of piece
GROUP_DEG = 0.25        # ... and whose angles differ by no more than this


def _sizes(p):
    """(exact part, measured part) of a piece's kind: pieces of one kind share the first and lie within GROUP_CM
    and GROUP_DEG of each other on the second. A turnout's diverging angle is read from the track beyond it, so it
    varies with how well that track was joined, and is reported, not grouped on."""
    if p["kind"] == "turnout":
        return ("turnout", p["shape"], p["hand"]), (p["straight_cm"], p["diverging_chord_cm"])
    if p["kind"] == "curve":
        return ("curve",), (p["radius_cm"], p["angle_deg"])
    if p["kind"] == "double_crossover":
        return ("double_crossover",), (p["length_cm"], p["spacing_cm"])
    return (p["kind"],), ()


def groups(pieces):
    """[(exact part, [pieces])]: pieces of one kind, each within GROUP_CM (GROUP_DEG for a curve's angle) of the
    group's first piece."""
    by_exact = collections.defaultdict(list)
    for p in pieces:
        by_exact[_sizes(p)[0]].append(p)
    out = []
    for exact, ps in by_exact.items():
        tol = (GROUP_CM, GROUP_DEG) if exact[0] == "curve" else (GROUP_CM, GROUP_CM)
        found = []
        for p in sorted(ps, key=lambda p: _sizes(p)[1]):
            v = _sizes(p)[1]
            home = next((g for g in found if all(abs(a - b) <= t for a, b, t in zip(v, _sizes(g[0])[1], tol))), None)
            if home is None:
                found.append([p])
            else:
                home.append(p)
        out += [(exact, g) for g in found]
    return out


def _mid(vals):
    vals = sorted(vals)
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def frog_number(angle_deg):
    """The frog number of a diverging angle: 1 / (2 tan(angle / 2))."""
    return 1 / (2 * math.tan(math.radians(angle_deg) / 2))


def describe(exact, ps):
    """One line for a group of pieces of one kind: its size in cm and inches, and the measured spread."""
    kind = exact[0]
    if kind == "turnout":
        _, shape, hand = exact
        straight, chord = _mid([p["straight_cm"] for p in ps]), _mid([p["diverging_chord_cm"] for p in ps])
        what = (f"{shape} turnout{' ' + hand if hand else ''}, straight route {straight:.1f} cm "
                f"({straight / CM_PER_IN:.2f} in), diverging chord {chord:.1f} cm")
        angles = [p["angle_deg"] for p in ps if p["angle_deg"] is not None]
        if angles:
            a = _mid(angles)
            frog = f"frog number {frog_number(a):.1f}; " if shape in FROG_SHAPES else ""
            what += (f", diverging angle {a:.1f} deg ({frog}{min(angles):.1f} to {max(angles):.1f} deg over "
                     f"{len(angles)} of {len(ps)})")
        else:
            what += ", diverging angle not measured"
        return what
    if kind == "curve":
        r, a = _mid([p["radius_cm"] for p in ps]), _mid([p["angle_deg"] for p in ps])
        return f"curve radius {r:.1f} cm ({r / CM_PER_IN:.2f} in), {a:.1f} deg"
    if kind == "double_crossover":
        length, spacing = _mid([p["length_cm"] for p in ps]), _mid([p["spacing_cm"] for p in ps])
        return f"double crossover {length:.1f} cm long, tracks {spacing:.1f} cm apart"
    total = sum(p["length_cm"] for p in ps)
    what = f"{kind}, {total:.1f} cm in all ({total / CM_PER_IN:.1f} in)"
    if kind == "flex":
        bends = [p["tightest_radius_cm"] for p in ps if p["tightest_radius_cm"] is not None]
        if bends:
            tight = min((p for p in ps if p["tightest_radius_cm"] is not None), key=lambda p: p["tightest_radius_cm"])
            r = tight["tightest_radius_cm"]
            what += f", tightest radius {r:.1f} cm ({r / CM_PER_IN:.2f} in) on {tight['id']}"
    return what


def _ids(ps, n=6):
    return ", ".join(p["id"] for p in ps[:n]) + (f" and {len(ps) - n} more" if len(ps) > n else "")


def report(result):
    """Text lines: the scale, each kind of piece with its count and export idents, the notes, and what was skipped."""
    order = {"turnout": 0, "double_crossover": 1, "curve": 2, "straight": 3, "flex": 4}
    scale = result["scale_px_per_cm"]
    lines = [f"scale: {scale:.4f} px per cm ({scale * CM_PER_IN:.2f} px per inch)",
             f"{len(result['pieces'])} pieces, {result['track_ends']} track ends, {len(result['skipped'])} skipped"]
    def place(g):
        return order[g[0][0]], str(g[0]), [round(v, 1) for v in _sizes(g[1][0])[1]]
    for exact, ps in sorted(groups(result["pieces"]), key=place):
        lines.append(f"{len(ps):4d} x {describe(exact, ps)}: {_ids(ps)}")
    noted = collections.defaultdict(list)
    for p in result["pieces"]:
        for n in p.get("notes", []):
            noted[n].append(p)
    for n, ps in noted.items():
        lines.append(f"note, {len(ps)} piece(s): {n}: {_ids(ps)}")
    for ident, why in result["skipped"]:
        lines.append(f"skipped {ident}: {why}")
    return lines
