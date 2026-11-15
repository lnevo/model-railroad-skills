"""A JMRI Layout Editor panel (XML) drawn from the solved bands: the schematic's own track, with rounded bends.

    P = le.panel(sheet.bands, names)      # turnouts, track segments, anchors, end bumpers, labels, helix circles
    le.write(P, "OUT.xml", "Layout (generated)")

Grid. A schematic grid point (column c, row r) becomes the panel point (cell * c, ROW * r) in pixels, each band moved
below the one before it, so the panel stacks the bands as the sheet does. With the page preference `equal_width`
a narrower band is stretched along its length to the widest band's width (`band_width` shares as on the sheet), so
its slopes lie a little flatter. A band named in `rotate_bands` is turned end for end.

Track. Each strand is a chain of track segments from leg to leg: straight along the drawn line, and every corner
rounded by a circular arc (`arc="yes" circle="yes"` with its angle, at most BEND pixels of radius). A turnback is
a half circle: two quarter arcs joined at an anchor on its far point. A switch is a Layout Editor turnout centred on
its points: right or left hand as drawn, its geometrically straight leg as Layout Editor leg B; when the drawing
puts the switch's leg C on the straight, the legs swap and `continuing="4"` keeps the normal route on the band's
leg B (or the leg the names give as normal). A switch with neither leg straight is a wye. A double crossover is a
DOUBLE_XOVER across its two through tracks; two switches of the same number joined C to C by one track are one
single crossover (RH_XOVER or LH_XOVER by the slope of the joining track), the track between them inside it.

Ends. A track end is an end bumper. Connector letters and helix tracks that appear on two drawn bands are joined by
a hidden track segment between two anchors (the panel stays one connected railroad); a helix end is marked by a
circle, and joined or not, each connector or helix end is labelled where it goes.

Names (optional, by band key, the first word of the band title):
    {"Main": {"turnouts": {node: turnout name}, "os": {node: OS block}, "normal": {node: "B" or "C"},
              "blocks": {strand id: [block, ...]},
              "masts": [{"mast": name, "facing": block, "protects": [block, ...], "kind": ..., "hidden": ...,
                         "icon": [w, h]}],
              "joins": "own" or "other"}}
A strand with several blocks is cut into equal lengths for them, from its first end to its second. Without names
a strand's block is its track name (or the two switch numbers it joins, made unique), a turnback and a joined helix
or connector track share the block of the track they continue, an OS block is "OS <switch number>", and no turnout
is named. Sensors are not placed.

Masts. Each mast in `masts` goes in the slot of that band whose facing block and protected blocks, as JMRI resolves
them (slots.py), are the ones given: an anchor's east or west slot, a turnout leg, or (with `protects` empty) an end
bumper. `kind` ("anchor", "end bumper" or "turnout"), when given, must match too. A buffer-stop mast (`protects`
empty) whose track has no bumper because the panel joins it to another band goes on that join's anchor instead,
facing the same block; it then protects the block of the hidden join (listed in P.moved). With `"joins": "other"`
a band's hidden joins take the other band's block, so its join anchors are block boundaries. A mast with no slot
is not placed and is listed in P.unplaced with the reason. Each placed mast gets a signal mast icon on the right-hand side
of the train it governs, just before the boundary, turned to the direction of travel; `icon` is its upright size in
pixels (default 12 x 17, a dwarf), `hidden` hides it as Layout Editor does.

Fit. With `fit` (width, height) the grid is scaled down until the whole panel, margins, labels and mast icons
included, fits: the row height only as far as the height needs, then the column width as far as the width needs
(so rows keep their room for the labels between tracks), each the largest that fits. Label fonts keep their size so
they stay readable, and the editor's window is the panel plus Layout Editor's own allowance for its frame (CHROME).
"""
import math
import xml.etree.ElementTree as ET
from collections import defaultdict

from . import stations
from .core import SchematicError, tidy
from .draw import band_key
from .layout import paths

CELL = 36           # px per grid column, before `equal_width` stretches a band
ROW = 36            # px per grid row
LEG = 12            # px from a switch's points to the end of a leg
BEND = 18           # largest radius of a rounded corner, px
HELIX_R = 9         # radius of the circle that marks a helix end, px
MARGIN = 60         # px left of and above the drawing
BAND_GAP = 96       # px between one band's lowest track and the next band's highest
TITLE_GAP = 40      # px from a band's title to its highest track
STRETCH_MAX = 2.5   # as the sheet: a band is never stretched more than this
LABEL_SIZE, NUMBER_SIZE, TITLE_SIZE = 10, 9, 13
EPS = 1e-6
CHROME = (18, 60)   # px Layout Editor allows for its frame around the panel (LayoutEditorXml: panel = window - this)
FIT_MIN = 0.25      # `fit` never scales the grid below this

PREFIX = "G"        # in every ident: TOG, TG, AG, EBG; so a generated panel's names never meet another's
LEX = "jmri.jmrit.display.layoutEditor.configurexml."
CLASS = {
    "RH_TURNOUT": LEX + "LayoutRHTurnoutXml",
    "LH_TURNOUT": LEX + "LayoutLHTurnoutXml",
    "WYE_TURNOUT": LEX + "LayoutWyeXml",
    "DOUBLE_XOVER": LEX + "LayoutDoubleXOverXml",
    "RH_XOVER": LEX + "LayoutRHXOverXml",
    "LH_XOVER": LEX + "LayoutLHXOverXml",
    "segment": LEX + "TrackSegmentXml",
    "point": LEX + "PositionablePointXml",
    "shape": LEX + "LayoutShapeXml",
    "options": LEX + "LayoutTrackDrawingOptionsXml",
    "editor": LEX + "LayoutEditorXml",
    "label": "jmri.jmrit.display.configurexml.PositionableLabelXml",
    "mast_icon": "jmri.jmrit.display.configurexml.SignalMastIconXml",
}
# Layout Editor's own defaults for a new panel; main track drawn twice as wide as the rest
EDITOR = dict(sliders="no", scrollable="both", editable="no", positionable="yes", controlling="yes",
              animating="yes", showhelpbar="no", drawgrid="no", snaponadd="yes", snaponmove="no", antialiasing="yes",
              turnoutcircles="yes", tooltipsnotedit="yes", tooltipsinedit="yes", mainlinetrackwidth="4",
              xscale="1.0", yscale="1.0", sidetrackwidth="2", defaulttrackcolor="black",
              defaultoccupiedtrackcolor="red", defaultalternativetrackcolor="white", defaulttextcolor="black",
              turnoutcirclecolor="black", turnoutcirclethrowncolor="red", turnoutcirclesize="2",
              turnoutdrawunselectedleg="yes", turnoutbx="20.0", turnoutcx="20.0", turnoutwid="10.0",
              xoverlong="30.0", xoverhwid="10.0", xovershort="10.0", autoblkgenerate="no", redBackground="255",
              greenBackground="255", blueBackground="255", gridSize="10", gridSize2nd="10", openDispatcher="no",
              useDirectTurnoutControl="no")
OPTIONS = [("mainBallastColor", "#000000"), ("mainBallastWidth", "0"), ("mainBlockLineDashPercentageX10", "0"),
           ("mainBlockLineWidth", "4"), ("mainRailColor", "#000000"), ("mainRailCount", "1"), ("mainRailGap", "0"),
           ("mainRailWidth", "2"), ("mainTieColor", "#000000"), ("mainTieGap", "0"), ("mainTieLength", "0"),
           ("mainTieWidth", "0"), ("sideBallastColor", "#000000"), ("sideBallastWidth", "0"),
           ("sideBlockLineDashPercentageX10", "0"), ("sideBlockLineWidth", "2"), ("sideRailColor", "#000000"),
           ("sideRailCount", "1"), ("sideRailGap", "0"), ("sideRailWidth", "1"), ("sideTieColor", "#000000"),
           ("sideTieGap", "0"), ("sideTieLength", "0"), ("sideTieWidth", "0")]


# ---------------------------------------------------------------- small geometry

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b, k=1.0):
    return (a[0] + k * b[0], a[1] + k * b[1])


def unit(v):
    n = math.hypot(*v)
    if n < EPS:
        raise SchematicError(f"a track of no length at {v}")
    return (v[0] / n, v[1] / n)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def clean(pts):
    out = []
    for p in pts:
        if not out or math.dist(out[-1], p) > 0.01:
            out.append(p)
    return out


def jmri_arc(p1, p2, angle, flip):
    """Layout Editor's circle arc from connect1 at p1 to connect2 at p2 (TrackSegmentView.calculateTrackSegmentAngle):
    (centre, radius, start, extent), angles in radians measured as Java's Arc2D does (y up), the arc running from
    the start (at connect2, or connect1 when flipped) through `extent` back to the other end."""
    a1, a2 = (p2, p1) if flip else (p1, p2)
    half = math.radians(angle) / 2
    a, o = a2[0] - a1[0], a2[1] - a1[1]
    r = math.hypot(a, o) / 2 / math.sin(half)
    start = math.atan2(a, o) - half
    centre = (a2[0] - math.cos(start) * r, a2[1] + math.sin(start) * r)
    return centre, r, start, math.radians(angle)


def arc_points(p1, p2, angle, flip, n=12):
    """Points along the arc as Layout Editor draws it, from connect1 to connect2."""
    c, r, start, ext = jmri_arc(p1, p2, angle, flip)
    pts = [(c[0] + r * math.cos(start + ext * i / n), c[1] - r * math.sin(start + ext * i / n)) for i in range(n + 1)]
    return pts[::-1] if not flip else pts      # the arc runs from a2: connect2, or connect1 when flipped


def flip_toward(p1, p2, angle, toward):
    """The `flip` that bows the arc from p1 to p2 toward the point `toward`."""
    m = arc_points(p1, p2, angle, False, 2)[1]
    return math.dist(m, toward) > math.dist(mid(p1, p2), toward)


def r1(v):
    return f"{round(v, 1):.1f}"


# ---------------------------------------------------------------- the panel

class Panel:
    def __init__(self):
        self.turnouts = []          # dicts: ident, type, cen, pts {leg: xy}, conn {leg: seg}, blocks {leg}, ...
        self.segments = []          # dicts: ident, ends [(ident, type)], block, main, dashed, hidden, arc
        self.points = {}            # ident -> dict(type, xy, conn [seg])
        self.shapes = []            # dicts: ident, centre, r
        self.labels = []            # dicts: text, xy (top left), size, bold
        self.blocks = set()         # block names used
        self.turnout_names = set()
        self.cur = None             # the band being drawn: every object is tagged with it, to move the band later
        self.strand_segments = defaultdict(list)     # (band index, strand id) -> [segment ident]
        self.turnout_of = {}        # (band index, node) -> (turnout ident, {band port: Layout Editor leg})
        self.turnbacks = {}         # (band index, turn node) -> [segment ident]
        self.joins = []             # hidden segment idents between two drawn bands
        self.masts = []             # dicts: mast, kind, ident, slot, icon (x, y, degrees), hidden, size
        self.unplaced = []          # (band title, mast, reason)
        self.moved = []             # (band title, mast, reason): buffer-stop masts placed at a join instead
        self.join_ends = {}         # (band index, anchor ident) -> block of the track that ends there
        self.log = []
        self.size = (0, 0)
        self.scale = (1.0, 1.0)     # the grid's scale across and down when `fit` shrank it
        self.fit = None
        self._n = defaultdict(int)

    def ident(self, kind):
        self._n[kind] += 1
        return f"{kind}{PREFIX}{self._n[kind]}"

    def point(self, kind, xy):
        ident = self.ident("A" if kind == "ANCHOR" else "EB")
        self.points[ident] = dict(type=kind, xy=list(xy), conn=[], band=self.cur)
        return ident

    def segment(self, a, b, block, main, dashed=False, hidden=False, arc=None):
        """A track segment from connection a to b, each (ident, type) or a point ident."""
        ident = self.ident("T")
        ends = []
        for c in (a, b):
            if isinstance(c, str):
                self.points[c]["conn"].append(ident)
                ends.append((c, "POS_POINT"))
            else:
                t, leg = c
                t["conn"][leg] = ident
                ends.append((t["ident"], f"TURNOUT_{leg}"))
        self.segments.append(dict(ident=ident, ends=ends, block=block, main=main, dashed=dashed, hidden=hidden,
                                  arc=arc, band=self.cur))
        self.blocks.add(block)
        return ident

    def label(self, text, xy, size=LABEL_SIZE, bold=False, anchor="centre"):
        w = text_width(text, size)
        x = xy[0] - w / 2 if anchor == "centre" else xy[0] - w if anchor == "right" else xy[0]
        self.labels.append(dict(text=text, xy=[x, xy[1]], size=size, bold=bold, band=self.cur))


def text_width(text, size):
    return 0.6 * size * len(text)


def node_ref(d):
    if d["kind"] in ("switch", "dx") and d.get("label"):
        return d["label"]
    if d.get("sub") == "link" and d.get("label"):
        return "link " + d["label"]
    if d.get("sub") == "helix":
        return "helix"
    return "end"


def partners(bands):
    """{(band index, end node): (band index, end node)}: a connector letter or a helix track on two drawn bands."""
    by = defaultdict(list)
    for bi, (_, band, _) in enumerate(bands):
        for n, d in sorted(band["nodes"].items()):
            if d["kind"] != "end":
                continue
            sid = next(iter(list(d["ins"].values()) + list(d["outs"].values())), None)
            if d.get("sub") == "link" and d.get("label"):
                by[("link", d["label"])].append((bi, n, sid))
            elif d.get("sub") == "helix" and sid and band["strands"][sid]["name"]:
                by[("helix", band["strands"][sid]["name"])].append((bi, n, sid))
    out = {}
    for group in by.values():
        if len(group) == 2 and group[0][0] != group[1][0]:
            a, b = (g[:2] for g in group)
            out[a], out[b] = b, a
    return out


def default_names(bands, joined, taken=()):
    """Block names when none are given: one per track, shared through a turnback and a join, made unique against
    each other and against `taken` (the names given in the names file, and the default OS blocks)."""
    parent = {}

    def find(k):
        while parent.get(k, k) != k:
            k = parent[k]
        return k

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    end_strand = {}
    for bi, (_, band, _) in enumerate(bands):
        nodes, strands = band["nodes"], band["strands"]
        for sid, s in strands.items():
            for n in (s["src"][0], s["dst"][0]):
                if nodes[n]["kind"].startswith("turn"):
                    end_strand.setdefault((bi, n), []).append((bi, sid))
                elif nodes[n]["kind"] == "end":
                    end_strand[(bi, n)] = [(bi, sid)]
    for k, group in end_strand.items():
        for g in group[1:]:
            union(group[0], g)
    for a, b in joined.items():
        union(end_strand[a][0], end_strand[b][0])
    groups = defaultdict(list)
    for bi, (_, band, _) in enumerate(bands):
        for sid in band["strands"]:
            groups[find((bi, sid))].append((bi, sid))
    taken, out = set(taken), {}
    for root in sorted(groups):
        keys = sorted(groups[root])
        name = next((bands[bi][1]["strands"][sid]["name"] for bi, sid in keys if bands[bi][1]["strands"][sid]["name"]),
                    None)
        if not name:
            bi, sid = keys[0]
            s, nodes = bands[bi][1]["strands"][sid], bands[bi][1]["nodes"]
            name = f"{node_ref(nodes[s['src'][0]])}-{node_ref(nodes[s['dst'][0]])}"
        base, i = name, 1
        while name in taken:
            i += 1
            name = f"{base} {i}"
        taken.add(name)
        for k in keys:
            out[k] = [name]
    return out


NAME_KEYS = ("turnouts", "os", "normal", "blocks", "masts", "joins")
MAST_KINDS = ("anchor", "end bumper", "turnout")


def check_names(bands, names):
    """Stop on a names file that names a band, a section, a switch or a track that is not there."""
    keys = {band_key(t): band for t, band, _ in bands}
    unknown = set(names) - set(keys)
    if unknown:
        raise SchematicError(f"names given for {', '.join(sorted(unknown))}, which is not a band "
                             f"(bands: {', '.join(keys)})")
    for key, given in names.items():
        if not isinstance(given, dict):
            raise SchematicError(f"names for {key} must be an object of {', '.join(NAME_KEYS)}")
        bad = set(given) - set(NAME_KEYS)
        if bad:
            raise SchematicError(f"names for {key}: {', '.join(sorted(bad))} is not one of {', '.join(NAME_KEYS)}")
        band = keys[key]
        switches = {n for n, d in band["nodes"].items() if d["kind"] in ("switch", "dx")}
        check_masts(key, given.get("masts") or [])
        if given.get("joins", "own") not in ("own", "other"):
            raise SchematicError(f"names for {key}: joins must be \"own\" or \"other\", not {given['joins']!r}")
        for section in NAME_KEYS[:4]:
            ids = set(given.get(section) or {})
            have = set(band["strands"]) if section == "blocks" else switches
            missing = sorted(ids - have)
            if missing:
                what = "track" if section == "blocks" else "switch"
                raise SchematicError(f"names for {key}: {section} names {', '.join(missing)}, which is no {what} "
                                     "of the band")


def fit_size(text):
    """(width, height) from "WxH" (the --fit option)."""
    try:
        w, h = (int(v) for v in text.lower().split("x"))
    except ValueError:
        raise ValueError(f"{text!r} is not WxH in pixels") from None
    if w <= 0 or h <= 0:
        raise ValueError(f"{text!r}: both sizes must be above zero")
    return w, h


def check_masts(key, masts):
    seen = set()
    for m in masts:
        if not isinstance(m, dict) or not m.get("mast") or not m.get("facing"):
            raise SchematicError(f"names for {key}: each mast needs a mast name and a facing block ({m!r})")
        if m["mast"] in seen:
            raise SchematicError(f"names for {key}: mast {m['mast']!r} given twice")
        seen.add(m["mast"])
        if not isinstance(m.get("protects", []), list):
            raise SchematicError(f"names for {key}: mast {m['mast']}: protects must be a list of blocks")
        if m.get("kind") not in (None, *MAST_KINDS):
            raise SchematicError(f"names for {key}: mast {m['mast']}: kind {m['kind']!r} is not one of "
                                 f"{', '.join(MAST_KINDS)}")


def panel(bands, names=None, cell=CELL, row=ROW, page=None, fit=None):
    """A Panel from [(title, band, options)], bands stacked top to bottom. `page` is the options that set the page
    (equal_width, band_width, rotate_bands); the last band's by default, as the sheet. `fit` (width, height): the
    largest grid, cell and row scaled together, at which the panel fits (see the module text)."""
    if fit is None:
        return draw_panel(bands, names, cell, row, page)
    W, H = fit
    draw = lambda kx, ky: draw_panel(bands, names, cell * kx, row * ky, page)      # noqa: E731
    lo = draw(FIT_MIN, FIT_MIN)
    if lo.size[0] > W or lo.size[1] > H:
        raise SchematicError(f"the panel does not fit {W}x{H} px even with the grid at {FIT_MIN:g} of its size "
                             f"({lo.size[0]}x{lo.size[1]} px)")

    def largest(ok):
        """The largest k in [FIT_MIN, 1] with ok(k) (ok holds at FIT_MIN and, once false, stays false above)."""
        if ok(1.0):
            return 1.0
        a, b = FIT_MIN, 1.0
        while b - a > 1e-3:
            k = (a + b) / 2
            a, b = (k, b) if ok(k) else (a, k)
        return a

    # each axis shrinks only as much as it must: rows keep their room for the labels between tracks
    kx = ky = 1.0
    for _ in range(3):          # a turnback's width follows the row height, so settle the two in turn
        ky = largest(lambda k: draw(kx, k).size[1] <= H)
        kx = largest(lambda k: draw(k, ky).size[0] <= W)
        P = draw(kx, ky)
        if P.size[0] <= W and P.size[1] <= H:
            break
    else:
        P = draw(min(kx, ky), min(kx, ky))
    P.scale, P.fit = (kx, ky), (W, H)
    return P


def draw_panel(bands, names, cell, row, page):
    if not bands:
        raise SchematicError("no band to draw")
    page = page if page is not None else bands[-1][2]
    names = names or {}
    check_names(bands, names)
    joined = partners(bands)
    given = {b for g in names.values() for v in (g.get("blocks") or {}).values()
             for b in ([v] if isinstance(v, str) else v)} | \
        {b for g in names.values() for b in (g.get("os") or {}).values()}
    os_defaults = {f"OS {d.get('label') or n}" for _, band, _ in bands for n, d in band["nodes"].items()
                   if d["kind"] in ("switch", "dx")}
    defaults = default_names(bands, joined, given | os_defaults)
    P = Panel()
    drawn = [paths(band) for _, band, _ in bands]
    widths = []
    for d in drawn:
        xs = [p[0] for v in d.values() for p in v]
        widths.append(max(xs) - min(xs))
    widest = max(w * cell for w in widths)
    ends = {}                   # (band index, end node) -> (point ident, strand id, outward direction, block, main)
    boxes = []
    for bi, (title, band, opts) in enumerate(bands):
        key = band_key(title)
        cellx = cell
        if page.get("equal_width") and widths[bi] > 0:
            share = page.get("band_width", {}).get(key, 1.0)
            cellx = cell * min(STRETCH_MAX, max(1.0, widest * share / (widths[bi] * cell)))
        turned = key in page.get("rotate_bands", ())
        P.cur = bi
        Band(P, bi, title, band, names.get(key, {}), defaults, joined, cellx, row, turned, ends, opts,
             drawn[bi]).build()
        boxes.append(extent(P, bi))
    # move each band into place: its whole box (labels, circles and arcs too) centred on the widest box, each band
    # below the one before, so nothing lies left of or above the margin
    P.cur = None
    full = max(b[2] - b[0] for b in boxes)
    top = MARGIN + TITLE_GAP
    for bi, ((title, _, _), box) in enumerate(zip(bands, boxes)):
        shift(P, bi, MARGIN + (full - (box[2] - box[0])) / 2 - box[0], top - box[1])
        P.label(title.upper(), (MARGIN, top - TITLE_GAP + 4), TITLE_SIZE, True, anchor="left")
        top += box[3] - box[1] + BAND_GAP
    for (bi, n), (bj, m) in sorted(joined.items()):
        if (bi, n) > (bj, m):
            continue
        a, b = ends[(bi, n)], ends[(bj, m)]
        block = b[3] if names.get(band_key(bands[bi][0]), {}).get("joins") == "other" else a[3]
        if names.get(band_key(bands[bj][0]), {}).get("joins") == "other":
            block = a[3]
        P.joins.append(P.segment(a[0], b[0], block, a[4] and b[4], hidden=True))
        P.join_ends[(bi, a[0])] = a[3]
        P.join_ends[(bj, b[0])] = b[3]
    if any(g.get("masts") for g in names.values()):
        place_masts(P, bands, names)
    box = extent(P)
    P.size = (math.ceil(box[2] + MARGIN), math.ceil(box[3] + MARGIN))
    return P


def extent(P, bi=None):
    """(left, top, right, bottom) of everything drawn for band bi (all bands when None): track, arcs, circles and
    labels."""
    mine = lambda o: bi is None or o["band"] == bi      # noqa: E731
    xs, ys = [], []
    for t in P.turnouts:
        if mine(t):
            for p in [t["cen"], *t["pts"].values()]:
                xs.append(p[0])
                ys.append(p[1])
    for p in P.points.values():
        if mine(p):
            xs.append(p["xy"][0])
            ys.append(p["xy"][1])
    for s in P.segments:
        if mine(s) and s["arc"]:
            for q in s["arc"]["drawn"]:
                xs.append(q[0])
                ys.append(q[1])
    for sh in P.shapes:
        if mine(sh):
            xs += [sh["centre"][0] - sh["r"], sh["centre"][0] + sh["r"]]
            ys += [sh["centre"][1] - sh["r"], sh["centre"][1] + sh["r"]]
    for lb in P.labels:
        if mine(lb):
            xs += [lb["xy"][0], lb["xy"][0] + text_width(lb["text"], lb["size"])]
            ys += [lb["xy"][1], lb["xy"][1] + lb["size"]]
    for m in P.masts:
        if mine(m):
            x, y, w, h = m["box"]
            xs += [x, x + w]
            ys += [y, y + h]
    return min(xs), min(ys), max(xs), max(ys)


def place_masts(P, bands, names):
    """Each named mast into the slot of its band that JMRI resolves to its facing and protected blocks."""
    from . import slots
    ix = slots.Index(to_xml(P, "probe"))
    taken = set()
    for bi, (title, _, _) in enumerate(bands):
        want = names.get(band_key(title), {}).get("masts") or []
        if not want:
            continue
        mine = {t["ident"] for t in P.turnouts if t["band"] == bi} | \
            {k for k, p in P.points.items() if p["band"] == bi}
        found = defaultdict(list)
        facing = defaultdict(set)
        for c in ix.candidates():
            if c[1] not in mine:
                continue
            f, pr = ix.blocks(*c)
            if f:
                found[(f, tuple(pr))].append(c)
                facing[f].add(tuple(pr))
        for m in want:
            protects = tuple(m.get("protects") or ())
            cands = [c for c in found.get((m["facing"], protects), []) if c not in taken]
            if m.get("kind"):
                other = [c for c in cands if c[0] != m["kind"]]
                cands = [c for c in cands if c[0] == m["kind"]]
            else:
                other = []
            moved = None
            if not cands and not protects:          # a buffer stop with no bumper: its track runs on through a join
                at = {ident for (b, ident), blk in P.join_ends.items() if b == bi and blk == m["facing"]}
                cands = [c for c in ix.candidates() if c[0] == "anchor" and c[1] in at and c not in taken
                         and ix.blocks(*c)[0] == m["facing"] and ix.blocks(*c)[1]]
                other = []
                if len(cands) == 1:
                    moved = (f"{m['facing']} has no buffer stop: it runs on through a join, so the mast stands at "
                             f"the join, protecting {ix.blocks(*cands[0])[1]}")
                else:
                    cands = []
            if not cands:
                if other:
                    why = f"only {other[0][0]} slots face {m['facing']} and protect {list(protects)}"
                elif facing.get(m["facing"]):
                    why = (f"no slot facing {m['facing']} protects {list(protects) or 'nothing (a buffer stop)'}; "
                           f"slots facing it protect {sorted(list(p) for p in facing[m['facing']])}")
                else:
                    why = f"no slot faces {m['facing']}"
                P.unplaced.append((title, m["mast"], why))
                P.log.append(f"{title}: mast {m['mast']} not placed: {why}")
                continue
            if len(cands) > 1:
                P.log.append(f"{title}: mast {m['mast']}: {len(cands)} slots fit, took {cands[0][0]} {cands[0][1]} "
                             f"{cands[0][2]}")
            kind, ident, slot = cands[0]
            taken.add((kind, ident, slot))
            if moved:
                P.moved.append((title, m["mast"], moved))
                P.log.append(f"{title}: mast {m['mast']}: {moved}")
            p, d = ix.travel(kind, ident, slot)
            size = tuple(m.get("icon") or slots.ICON)
            x, y, deg = slots.icon_place(p, d, size)
            th = math.radians(deg)
            bw = size[0] * abs(math.cos(th)) + size[1] * abs(math.sin(th))
            bh = size[0] * abs(math.sin(th)) + size[1] * abs(math.cos(th))
            P.masts.append(dict(mast=m["mast"], kind=kind, ident=ident, slot=slot, icon=(x, y, deg),
                                hidden=bool(m.get("hidden")), box=(x, y, bw, bh), band=bi))


def shift(P, bi, dx, dy):
    move = lambda p: [p[0] + dx, p[1] + dy]       # noqa: E731
    for t in P.turnouts:
        if t["band"] == bi:
            t["cen"] = move(t["cen"])
            t["pts"] = {k: move(p) for k, p in t["pts"].items()}
    for p in P.points.values():
        if p["band"] == bi:
            p["xy"] = move(p["xy"])
    for s in P.segments:
        if s["band"] == bi and s["arc"]:
            s["arc"]["drawn"] = [move(q) for q in s["arc"]["drawn"]]
    for sh in P.shapes:
        if sh["band"] == bi:
            sh["centre"] = move(sh["centre"])
    for lb in P.labels:
        if lb["band"] == bi:
            lb["xy"] = move(lb["xy"])


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
        self.px = lambda p: (k * (p[0] - x0) * cellx, k * (p[1] - y0) * row)    # noqa: E731
        self.drawn = drawn
        self.poly = {sid: clean([self.px(p) for p in drawn[sid]]) for sid in self.strands}
        for sid, pts in self.poly.items():
            if len(pts) < 2:
                raise SchematicError(f"{title}: track {self.strands[sid]['name'] or sid} is drawn as a single point")
        self.conn = {}          # (node, port) -> connection: (turnout dict, leg) or point ident
        self.leg_pt = {}        # (node, port) -> xy where the strand starts
        self.internal = set()   # strands drawn inside a crossover
        self.mine = []          # this band's turnouts

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

    def os_of(self, n):
        got = self.names.get("os", {}).get(n)
        return got or f"OS {self.nodes[n].get('label') or n}"

    def normal_of(self, n):
        got = self.names.get("normal", {}).get(n, "B")
        if got not in ("B", "C"):
            raise SchematicError(f"{self.title}: switch {self.nodes[n].get('label') or n}: normal leg {got!r} "
                                 "is not B or C")
        return got

    # ---- the drawn line of a strand from one of its ends
    def away(self, n, port):
        sid = self.port_strand(n, port)
        pts = self.poly[sid]
        return pts if tuple(self.strands[sid]["src"]) == (n, port) else pts[::-1]

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
    def add_turnout(self, nodes, ttype, cen, pts, conn_ports, blocks, continuing="2"):
        P = self.P
        t = dict(ident=P.ident("TO"), type=ttype, cen=list(cen), pts={k: list(v) for k, v in pts.items()}, conn={},
                 blocks=blocks, continuing=continuing, ver="2" if "XOVER" in ttype else "1",
                 name=None, nodes=nodes, band=self.bi)
        names = {self.names.get("turnouts", {}).get(n) for n in nodes} - {None}
        if len(names) > 1:
            raise SchematicError(f"{self.title}: one turnout for switches {', '.join(nodes)} given two names "
                                 f"{sorted(names)}")
        if names:
            t["name"] = names.pop()
            if t["name"] in P.turnout_names:
                raise SchematicError(f"{self.title}: turnout name {t['name']!r} given to two separate turnouts "
                                     f"(switch {self.nodes[nodes[0]].get('label') or nodes[0]})")
            P.turnout_names.add(t["name"])
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
        c = self.node_point(n)
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
        if straight:
            B, C = add(c, dirs[straight], L), add(c, dirs[other], L)
            A = add(c, dirs[straight], -L)
            ttype = "RH_TURNOUT" if cross(dirs[straight], dirs[other]) > 0 else "LH_TURNOUT"
            conn = {(n, "A"): "A", (n, straight): "B", (n, other): "C"}
            continuing = "2" if normal == straight else "4"
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
            conn = {(n, "A"): "A", (n, "B"): "B", (n, "C"): "C"}
            continuing = "2" if normal == "B" else "4"
        self.add_turnout([n], ttype, c, {"A": A, "B": B, "C": C}, conn, blocks, continuing)

    def crossovers(self):
        """Two switches of one number joined C to C by a track: one single crossover."""
        for sid, s in sorted(self.strands.items()):
            (u, pu), (v, pv) = s["src"], s["dst"]
            du, dv = self.nodes[u], self.nodes[v]
            if not (u != v and pu == pv == "C" and du["kind"] == dv["kind"] == "switch" and du.get("label")
                    and du.get("label") == dv.get("label")):
                continue
            if (self.bi, u) in self.P.turnout_of or (self.bi, v) in self.P.turnout_of:
                continue
            level = all(abs(self.direction(n, p)[1]) < EPS for n in (u, v) for p in "AB")
            if not level:
                self.P.log.append(f"{self.title}: switches {du['label']} are not drawn on two level tracks; "
                                  "drawn as two turnouts, not a crossover")
                continue
            pu_, pv_ = self.node_point(u), self.node_point(v)
            (top, tp), (bot, bp) = sorted(((u, pu_), (v, pv_)), key=lambda t: t[1][1])
            if abs(tp[1] - bp[1]) < EPS:
                continue
            h = min([1.5 * LEG] + [0.4 * self.first_len(n, p) for n in (u, v) for p in "AB"])
            pts = {"A": (tp[0] - h, tp[1]), "B": (tp[0] + h, tp[1]), "D": (bp[0] - h, bp[1]), "C": (bp[0] + h, bp[1])}
            conn = {}
            for n, left, right in ((top, "A", "B"), (bot, "D", "C")):
                for p in "AB":
                    conn[(n, p)] = left if self.direction(n, p)[0] < 0 else right
                if sorted(conn[(n, p)] for p in "AB") != sorted((left, right)):
                    self.P.log.append(f"{self.title}: switch {du['label']}: both through legs on one side")
                    break
            else:
                ttype = "RH_XOVER" if bp[0] > tp[0] else "LH_XOVER"
                blocks = {"A": self.os_of(top), "B": self.os_of(top), "C": self.os_of(bot), "D": self.os_of(bot)}
                self.add_turnout([top, bot], ttype, mid(tp, bp), pts, conn, blocks)
                self.internal.add(sid)

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
        corner = {(ys[0], "left"): "A", (ys[0], "right"): "B", (ys[1], "right"): "C", (ys[1], "left"): "D"}
        conn = {(n, p): corner[(round(e[0][1], 3), e[1])] for p, e in ends.items()}
        if sorted(conn.values()) != list("ABCD"):
            raise SchematicError(f"{self.title}: double crossover {self.nodes[n].get('label') or n}: its legs do not "
                                 "reach four corners")
        pts = {"A": (xc - h, ys[0]), "B": (xc + h, ys[0]), "C": (xc + h, ys[1]), "D": (xc - h, ys[1])}
        b = self.os_of(n)
        self.add_turnout([n], "DOUBLE_XOVER", (xc, (ys[0] + ys[1]) / 2), pts, conn, {k: b for k in "ABCD"})

    # ---- ends
    def end(self, n):
        d = self.nodes[n]
        port = self.ports(n)[0]
        pts = self.away(n, port)
        sid = self.port_strand(n, port)
        joined = (self.bi, n) in self.joined
        ident = self.P.point("ANCHOR" if joined else "END_BUMPER", pts[0])
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
        pieces = split(pieces, len(blocks), f"{self.title}: track {s['name'] or sid}")
        total = sum(piece_len(p) for p in pieces)
        run = 0.0
        prev = self.conn[(u, pu)]
        for i, pc in enumerate(pieces):
            L = piece_len(pc)
            k = min(len(blocks) - 1, int((run + L / 2) / total * len(blocks)))
            run += L
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
            cen = t["cen"]
            if "XOVER" in t["type"]:
                top = min(p[1] for p in t["pts"].values())
                P.label(label, (cen[0], top - NUMBER_SIZE - 5), NUMBER_SIZE, True)
                continue
            down = t["pts"]["C"][1] > cen[1] + EPS or t["pts"]["B"][1] > cen[1] + EPS
            y = cen[1] - NUMBER_SIZE - 6 if down else cen[1] + 5
            P.label(label, (cen[0], y), NUMBER_SIZE, True)
        for sid, s in sorted(self.strands.items()):
            if not s["name"] or sid in self.internal:
                continue
            pts = self.poly[sid]
            runs = [(a, b) for a, b in zip(pts, pts[1:]) if abs(a[1] - b[1]) < EPS]
            if not runs:
                continue
            a, b = max(runs, key=lambda r: (abs(r[1][0] - r[0][0]), -min(r[0][0], r[1][0])))
            text = tidy([s["name"]])[0]
            if text_width(text, LABEL_SIZE) > abs(b[0] - a[0]) * 1.6:
                continue
            P.label(text, ((a[0] + b[0]) / 2, a[1] - LABEL_SIZE - 5))
        # station names (the `stations` preference) under the band, or over it for a station on the top side
        ys = [p[1] for pts in self.poly.values() for p in pts]
        by_label = defaultdict(list)
        for t in self.mine:
            for n in t["nodes"]:
                by_label[(self.nodes[n].get("label") or "").rstrip("*")].append(t["cen"][0])
        for name, e in stations.entries(self.opts).items():
            xs = [x for sw in e["switches"] for x in by_label.get(str(sw), ())]
            if not xs:
                continue
            y = max(ys) + 2 * LABEL_SIZE if e["side"] == "bottom" else min(ys) - 3 * LABEL_SIZE - 8
            P.label(name.upper(), ((min(xs) + max(xs)) / 2, y), LABEL_SIZE, True)


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


def split(pieces, k, what):
    """Cut straight pieces where a strand of k blocks changes block (k equal lengths)."""
    if k == 1:
        return pieces
    total = sum(piece_len(p) for p in pieces)
    targets = [total * j / k for j in range(1, k)]
    out, run = [], 0.0
    for pc in pieces:
        L = piece_len(pc)
        cuts = [s - run for s in targets if run < s < run + L]
        if pc["kind"] == "line" and cuts:
            a = pc["a"]
            for c in cuts:
                q = add(pc["a"], unit(sub(pc["b"], pc["a"])), c)
                out.append(dict(kind="line", a=a, b=q))
                a = q
            out.append(dict(kind="line", a=a, b=pc["b"]))
        else:
            out.append(pc)
        run += L
    got, run = set(), 0.0
    for pc in out:
        L = piece_len(pc)
        got.add(min(k - 1, int((run + L / 2) / total * k)))
        run += L
    if len(got) != k:
        raise SchematicError(f"{what}: too short to hold its {k} blocks")
    return out


# ---------------------------------------------------------------- XML

def to_xml(P, name, attrs=None, options=None):
    """The panel as a <LayoutEditor> element. `attrs` replace the editor attributes (a template panel's, say);
    `options` is a layoutTrackDrawingOptions element to copy (its name is set to the panel's)."""
    a = dict(EDITOR) if attrs is None else dict(attrs)
    a.pop("class", None)
    if P.fit:
        window = (P.size[0] + CHROME[0], P.size[1] + CHROME[1])
    else:
        window = (min(P.size[0], 1900), min(P.size[1], 1000))
    a.update(name=name, x="0", y="0", panelwidth=str(P.size[0]), panelheight=str(P.size[1]),
             windowwidth=str(window[0]), windowheight=str(window[1]))
    le = ET.Element("LayoutEditor", {"class": CLASS["editor"], **a})
    on_turnout, on_point = defaultdict(dict), defaultdict(dict)
    for m in P.masts:
        (on_turnout if m["kind"] == "turnout" else on_point)[m["ident"]][m["slot"]] = m["mast"]
    if options is not None:
        opts = ET.fromstring(ET.tostring(options))
        opts.set("name", name)
    else:
        opts = ET.Element("layoutTrackDrawingOptions", {"name": name, "class": CLASS["options"]})
        for tag, text in OPTIONS:
            ET.SubElement(opts, tag).text = text
    le.append(opts)
    for t in P.turnouts:
        at = {"ident": t["ident"], "type": t["type"], "hidden": "no", "disabled": "no", "disableWhenOccupied": "yes",
              "continuing": t["continuing"], "xcen": r1(t["cen"][0]), "ycen": r1(t["cen"][1])}
        pts = dict(t["pts"])
        pts.setdefault("D", pts["A"])
        for leg in "ABCD":
            at[f"x{leg.lower()}"], at[f"y{leg.lower()}"] = r1(pts[leg][0]), r1(pts[leg][1])
        at["ver"] = t["ver"]
        at["class"] = CLASS[t["type"]]
        if t["name"]:
            at["turnoutname"] = t["name"]
        at["blockname"] = t["blocks"]["A"]
        for leg in "BCD":
            if t["blocks"].get(leg, t["blocks"]["A"]) != t["blocks"]["A"]:
                at[f"block{leg.lower()}name"] = t["blocks"][leg]
        for leg in "ABCD":
            if leg in t["conn"]:
                at[f"connect{leg.lower()}name"] = t["conn"][leg]
        el = ET.SubElement(le, "layoutturnout", at)
        for leg in "ABCD":
            if leg in on_turnout.get(t["ident"], {}):
                ET.SubElement(el, f"signal{leg}Mast").text = on_turnout[t["ident"]][leg]
    for s in P.segments:
        (c1, t1), (c2, t2) = s["ends"]
        at = {"ident": s["ident"], "blockname": s["block"], "connect1name": c1, "type1": t1, "connect2name": c2,
              "type2": t2, "dashed": "yes" if s["dashed"] else "no", "mainline": "yes" if s["main"] else "no",
              "hidden": "yes" if s["hidden"] else "no"}
        if s["arc"]:
            at.update(arc="yes", flip="yes" if s["arc"]["flip"] else "no", circle="yes",
                      angle=f"{s['arc']['angle']:g}", hideConLines="yes")
        at["class"] = CLASS["segment"]
        le.append(ET.Element("tracksegment", at))
    for ident, p in P.points.items():
        at = {"ident": ident, "type": p["type"], "x": r1(p["xy"][0]), "y": r1(p["xy"][1])}
        for i, seg in enumerate(p["conn"], 1):
            at[f"connect{i}name"] = seg
        for slot, mast in sorted(on_point.get(ident, {}).items()):
            at[f"{slot}boundsignalmast"] = mast
        at["class"] = CLASS["point"]
        le.append(ET.Element("positionablepoint", at))
    for sh in P.shapes:
        el = ET.Element("layoutShape", {"ident": sh["ident"], "type": "Closed", "level": "3", "linewidth": "2",
                                        "lineColor": "#000000", "fillColor": "#FFFFFF", "class": CLASS["shape"]})
        pts = ET.SubElement(el, "points")
        R = sh["r"] / math.cos(math.pi / 8)        # quadratic curves through the mid points draw the circle
        for i in range(8):
            th = math.pi / 8 + i * math.pi / 4
            ET.SubElement(pts, "point", {"type": "Curve", "x": r1(sh["centre"][0] + R * math.cos(th)),
                                         "y": r1(sh["centre"][1] + R * math.sin(th))})
        le.append(el)
    for lb in P.labels:
        le.append(ET.Element("positionablelabel", {
            "x": str(round(lb["xy"][0])), "y": str(round(lb["xy"][1])), "level": "4", "forcecontroloff": "false",
            "hidden": "no", "positionable": "true", "showtooltip": "false", "editable": "false", "text": lb["text"],
            "size": str(lb["size"]), "style": "1" if lb["bold"] else "0", "red": "0", "green": "0", "blue": "0",
            "hasBackground": "no", "justification": "left", "class": CLASS["label"]}))
    for m in P.masts:
        x, y, deg = m["icon"]
        le.append(ET.Element("signalmasticon", {
            "signalmast": m["mast"], "x": str(x), "y": str(y), "level": "9", "forcecontroloff": "false",
            "hidden": "yes" if m["hidden"] else "no", "positionable": "true", "showtooltip": "true",
            "editable": "false", "degrees": str(deg), "clickmode": "0", "litmode": "false", "scale": "1.0",
            "imageset": "default", "class": CLASS["mast_icon"]}))
    return le


def write(P, out, name, attrs=None, options=None):
    el = to_xml(P, name, attrs, options)
    ET.indent(el, "  ")
    text = "<?xml version='1.0' encoding='UTF-8'?>\n" + ET.tostring(el, encoding="unicode") + "\n"
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def summary(P):
    arcs = sum(1 for s in P.segments if s["arc"])
    kinds = defaultdict(int)
    for t in P.turnouts:
        kinds[t["type"]] += 1
    return (f"{len(P.turnouts)} turnouts ({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))}), "
            f"{len(P.segments)} track segments ({arcs} arcs, {len(P.joins)} hidden joins), "
            f"{sum(1 for p in P.points.values() if p['type'] == 'ANCHOR')} anchors, "
            f"{sum(1 for p in P.points.values() if p['type'] == 'END_BUMPER')} end bumpers, {len(P.blocks)} blocks, "
            f"{len(P.labels)} labels"
            + (f", {len(P.masts)} masts" + (f" ({len(P.unplaced)} not placed)" if P.unplaced else "")
               if P.masts or P.unplaced else "")
            + f"; {P.size[0]}x{P.size[1]} px"
            + (f" (grid at {P.scale[0]:.3f} x {P.scale[1]:.3f} to fit)" if P.scale != (1.0, 1.0) else ""))
