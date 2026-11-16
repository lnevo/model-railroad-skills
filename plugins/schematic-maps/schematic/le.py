"""A JMRI Layout Editor panel (XML) drawn from the solved bands: the schematic's own track, with rounded bends.

    P = le.panel(sheet.bands, names)      # turnouts, track segments, anchors, end bumpers, labels, helix circles
    le.write(P, "OUT.xml", "Layout (generated)")

Grid. A schematic grid point (column c, row r) becomes the panel point (cell * c, ROW * r) in pixels, each band moved
below the one before it (`gap` px apart), so the panel stacks the bands as the sheet does: each centred on the
widest, or against its left or right edge as the page's `band_align` says ({band key: "left", "centre" or
"right"}, as on the sheet), so a band can keep the place it has when drawn alone. With the page preference `equal_width`
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
              "blocks": {strand id: [block, ...]}, "lengths": {block: real length, any one unit},
              "masts": [{"mast": name, "facing": block, "protects": [block, ...], "kind": ..., "hidden": ...,
                         "icon": [w, h], "or_join": ...}],
              "joins": "own" or "other", "leg_b": {node: "B" or "C"}, "shared_turnouts": [turnout name, ...],
              "idents": {"turnouts": {node: ident}, "boundaries": [{"blocks": [block, block], "ident": ident}],
                         "ends": {block: ident}, "segments": {block: ident}}}}
A strand with several blocks is cut for them in order from its first end to its second: in proportion to their
real lengths when `lengths` gives one for each (so a short throat block sits at its own end of the track), else into
equal lengths; no block is drawn shorter than MIN_BLOCK px, and no cut falls inside an arc. Without names
a strand's block is its track name (or the two switch numbers it joins, made unique), a turnback and a joined helix
or connector track share the block of the track they continue, an OS block is "OS <switch number>", and no turnout
is named. Sensors are not placed. `leg_b` names the band leg that is Layout Editor leg B (default: the drawn
straight one); a drawn diverging leg B puts the centre midway between legs A and B, where Layout Editor finds point
A. `idents` gives drawn objects an older panel's idents once the track is drawn (give_idents): a switch's
turnout, the one anchor between two blocks, the one end bumper of a block, the one segment of a block; the rest keep
generated idents, whose form (G after the prefix) no given ident may take. A turnout name is given to one
turnout, unless it is in `shared_turnouts` of each band that draws it: one turnout drawn as two Layout Editor
turnouts (a crossover whose halves are not drawn as one single crossover, or stand on two bands), which JMRI throws
together. The given idents are an alias layer:
the Panel's own lookups keep the generated idents (P.name maps one), and the XML and every message (the log,
P.unplaced and P.moved reasons, errors) name objects by the idents written (Panel.text).

Masts. Each mast in `masts` goes in the slot of that band whose facing block and protected blocks, as JMRI resolves
them (slots.py), are the ones given: an anchor's east or west slot, a turnout leg, or (with `protects` empty) an end
bumper. `kind` ("anchor", "end bumper" or "turnout"), when given, must match too. A buffer-stop mast (`protects`
empty) with `"or_join": true`, whose track has no bumper slot because the panel joins it to another band, goes on
that join's anchor instead, facing the same block and protecting the hidden join's block (an anchor, not an end
bumper: listed in P.moved). That anchor is a block boundary only when the join carries the other band's block:
`"joins": "other"` on a band gives its hidden joins the other band's block (on one band of a pair, not both). A
mast with no slot is not placed and is listed in P.unplaced with the reason. Each placed mast gets a signal mast icon on the right-hand side
of the train it governs, before the boundary, turned to the direction of travel; `icon` is its upright size in pixels
(default 12 x 17, a dwarf), `hidden` hides it as Layout Editor does. Then the CATS mast rules (le_masts): the anchors
of one control point's masts slide along their own straight track into one column per direction (P.gantries,
P.anchors_moved), each icon takes its clearest spot off turnouts, track, labels and other icons, and a track's name
No mast changes slot or blocks.

Labels (le_labels). The drawing keeps room for switch numbers, track names and station names (room_width: part of
the approved geometry, so it stays). Last, once the grid is settled (label_layer), those are replaced by labels placed
in clean spots sized as JMRI draws them in the Dialog font (jmri_text), with one block contents icon per block; the
layer changes nothing else (checked: geometry before and after), and no clean spot stops. Options: a band's or the
page's `le_labels`. P.labels and P.bcis hold what was placed, each with its box.

Fit. `fit` (width, height) is the window the panel opens in at 100% zoom. The panel must fit inside it less Layout
Editor's own allowance for the frame (CHROME), so the grid is scaled down until the whole panel, margins, labels
and mast icons included, fits that: the row height only as far as the height needs, then the column width as far as
the width needs (so rows keep their room for the labels between tracks), each the largest that fits. Label fonts
keep their size so they stay readable. The panel's window is the panel plus CHROME, within `fit`.
"""
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

from . import le_labels, stations
from .core import SchematicError, node_ref, tidy
from .draw import band_key
from .layout import paths

CELL = 36           # px per grid column, before `equal_width` stretches a band
ROW = 36            # px per grid row
LEG = 12            # px from a switch's points to the end of a leg
BEND = 18           # largest radius of a rounded corner, px
MIN_BLOCK = LEG     # px a block of several on one track is drawn at least (a throat: just clear of its switch)
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
FONT = {"fontFamily": "Dialog", "fontname": "Dialog"}      # every label: the font jmri_text measures
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
    """The panel being drawn. Its lookups hold generated idents, given idents or not: the idents of turnouts,
    segments (and their ends), points (the keys), shapes, masts[*].ident, turnout_of, strand_segments, turnbacks,
    joins, join_ends, gantries, anchors_moved and anchors_from. idents_given maps a generated ident to the one the
    names give it (the alias layer) and name(ident) gives the ident an object is written under. to_xml writes the
    given idents, and text() puts them into every message: P.log, the reasons in P.unplaced and P.moved, and each
    SchematicError that le.panel() or to_xml raises."""

    def __init__(self):
        self.turnouts = []          # dicts: ident, type, cen, pts {leg: xy}, conn {leg: seg}, blocks {leg}, ...
        self.segments = []          # dicts: ident, ends [(ident, type)], block, main, dashed, hidden, arc
        self.points = {}            # ident -> dict(type, xy, conn [seg])
        self.shapes = []            # dicts: ident, centre, r
        self.labels = []            # dicts: text, xy (top left), size, bold; a track's name: run (its level run)
        self.blocks = set()         # block names used
        self.turnout_names = set()
        self.cur = None             # the band being drawn: every object is tagged with it, to move the band later
        self.strand_segments = defaultdict(list)     # (band index, strand id) -> [segment ident]
        self.turnout_of = {}        # (band index, node) -> (turnout ident, {band port: Layout Editor leg})
        self.turnbacks = {}         # (band index, turn node) -> [segment ident]
        self.joins = []             # hidden segment idents between two drawn bands
        self.masts = []             # dicts: mast, kind, ident, slot, icon (x, y, degrees), hidden, size, box, spot
        self.unplaced = []          # (band title, mast, reason)
        self.moved = []             # (band title, mast, reason): buffer-stop masts placed at a join instead
        self.join_ends = {}         # (band index, anchor ident) -> block of the track that ends there
        self.gantries = []          # lists of P.masts entries whose boundaries stand in one column (le_masts)
        self.anchors_moved = []     # (mast, anchor ident, px) boundary anchors slid along their track into a gantry
        self.length_strands = {}    # block -> {(band index, strand id)} drawn at their given lengths
        self.anchors_from = {}      # anchor ident -> where it stood before it slid
        self.bcis = []              # dicts: block, kind (track, os), xy, size, band, box, on_track (le_labels)
        self.extras = []            # dicts: id, block, xy, band, box, on_track: the caller's items (le_labels)
        self.labels_unplaced = []   # (item, reason): items le_labels left out (strict=False only)
        self.crossover_run = None   # px across every single crossover's diagonal runs (panel), None: as drawn
        self.lamps = []             # the caller's lamp boxes the label layer kept clear (le_labels lamp_columns)
        self.band_boxes = []        # (x0, y0, x1, y1) each band was placed by: its drawing with the room for its labels
        self.names_skipped = []     # why each names_last track name was left out (le_labels)
        self.no_name = {}           # (band index, strand id) -> why the drawing keeps no room for its name
        self.cellx = {}             # band index -> px per grid column as drawn
        self.idents_given = {}      # generated ident -> the ident the names give it (give_idents): the alias layer
        self.log = []
        self.size = (0, 0)
        self.scale = (1.0, 1.0)     # the grid's scale across and down when `fit` shrank it
        self.fit = None
        self._n = defaultdict(int)

    def ident(self, kind):
        self._n[kind] += 1
        return f"{kind}{PREFIX}{self._n[kind]}"

    def name(self, ident):
        """The ident an object is written under: the one the names give it, else its generated one."""
        return self.idents_given.get(ident, ident)

    def text(self, s):
        """A message with every generated ident that has a given one replaced by it (whole idents only)."""
        if not self.idents_given:
            return s
        return GENERATED_WORD.sub(lambda m: self.idents_given.get(m.group(0), m.group(0)), s)

    def final_text(self):
        """Every message the panel keeps, in written idents: run when the panel is drawn and after its labels are
        placed (a written ident is never a generated one, so running it twice changes nothing)."""
        self.log = [self.text(line) for line in self.log]
        self.unplaced = [(t, m, self.text(why)) for t, m, why in self.unplaced]
        self.moved = [(t, m, self.text(why)) for t, m, why in self.moved]
        self.names_skipped = [self.text(why) for why in self.names_skipped]
        self.labels_unplaced = [(k, self.text(why)) for k, why in self.labels_unplaced]

    def point(self, kind, xy, end=False):
        """A point's ident: AG<n> for an anchor, EBG<n> for an end bumper; a track's end joined to another band
        (`end`, an anchor) is numbered among the end bumpers, AGE<n>, so whether a band's ends are joined renumbers
        nothing else of it."""
        if kind == "ANCHOR" and end:
            self._n["EB"] += 1
            ident = f"A{PREFIX}E{self._n['EB']}"
        else:
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

    def label(self, text, xy, size=LABEL_SIZE, bold=False, anchor="centre", kind="end"):
        """A label drawn with the track: `kind` "title" or "end" stays; "switch", "name" and "station" keep the
        room the drawing makes for them, and le_labels then places them for real."""
        w = room_width(text, size)
        x = xy[0] - w / 2 if anchor == "centre" else xy[0] - w if anchor == "right" else xy[0]
        self.labels.append(dict(text=text, xy=[x, xy[1]], size=size, bold=bold, band=self.cur, kind=kind))


def room_width(text, size):
    """The room the drawing keeps for a label (0.6 of its size per character): part of the approved geometry (band
    places, mast icon spots), so it stays. What JMRI really draws is jmri_text.width."""
    return 0.6 * size * len(text)



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


NAME_KEYS = ("turnouts", "os", "normal", "blocks", "masts", "joins", "lengths", "leg_b", "idents", "shared_turnouts")
MAST_KINDS = ("anchor", "end bumper", "turnout")
MAST_FIELDS = ("mast", "facing", "protects", "kind", "hidden", "icon", "or_join")
IDENT_KEYS = ("turnouts", "boundaries", "ends", "segments")
# the kind of object each section's idents must be found as by JMRI (jmri_kind)
IDENT_KIND = {"turnouts": "turnout", "boundaries": "point", "ends": "point", "segments": "segment"}
GENERATED = re.compile(r"(?:(TO|T|A|EB|SH)" + PREFIX + r"|A" + PREFIX + r"E)\d+")     # AGE<n>: a joined end
GENERATED_WORD = re.compile(r"(?<![A-Za-z0-9_-])" + GENERATED.pattern + r"(?![A-Za-z0-9_-])")   # as in a message


def jmri_kind(name):
    """The kind of object Layout Editor looks a connection name up as, by the rules and in the order of
    LayoutEditorFindItems.findObjectByName (JMRI 5.16): "turnout", "point" (anchor, end bumper or edge connector),
    "xing", "slip", "turntable", "traverser", "segment", or None (JMRI logs an unknown prefix and leaves the
    connection empty)."""
    if name.startswith("TO"):
        return "turnout"
    if name.startswith(("A", "EB", "EC")) or re.fullmatch(r"F\d+-A-\d+", name):
        return "point"
    for prefix, kind in (("X", "xing"), ("SL", "slip"), ("TUR", "turntable"), ("TRV", "traverser")):
        if name.startswith(prefix):
            return kind
    if name.startswith("T") or re.fullmatch(r"F\d+-S-\d+", name):
        return "segment"
    if name.endswith("-EB"):
        return "point"
    return None


def crossover_pairs(band):
    """[(track id, switch, switch)]: two switches of one number joined C to C by one track, drawn as one single
    crossover (when both stand on level track; else as two turnouts, and the log says so)."""
    nodes, out = band["nodes"], []
    for sid, st in sorted(band["strands"].items()):
        (u, pu), (v, pv) = st["src"], st["dst"]
        du, dv = nodes[u], nodes[v]
        if u != v and pu == pv == "C" and du["kind"] == dv["kind"] == "switch" and du.get("label") \
                and du.get("label") == dv.get("label"):
            out.append((sid, u, v))
    return out


def check_names(bands, names):
    """Stop on a names file that names a band, a section, a switch or a track that is not there."""
    keys = {band_key(t): band for t, band, _ in bands}
    seen_masts, seen_idents = {}, {}
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
        check_masts(key, given.get("masts") or [], seen_masts)
        text = lambda v: isinstance(v, str) and v.strip()      # noqa: E731
        for section in NAME_KEYS[:4]:
            got = given.get(section)
            if got is None:
                continue
            if not isinstance(got, dict) or not all(isinstance(k, str) for k in got):
                raise SchematicError(f"names for {key}: {section} must be an object keyed by "
                                     f"{'track' if section == 'blocks' else 'switch'} id")
            for k, v in got.items():
                ok = (text(v) or isinstance(v, list) and v and all(text(b) for b in v)) if section == "blocks" \
                    else text(v)
                if not ok:
                    raise SchematicError(f"names for {key}: {section} {k}: "
                                         + ("a block name or a non-empty list of block names" if section == "blocks"
                                            else "a name as text") + f", not {v!r}")
        lengths = given.get("lengths", {})
        if not isinstance(lengths, dict) or not all(
                isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                and v > 0 for k, v in lengths.items()):
            raise SchematicError(f"names for {key}: lengths must be an object of block name: length above zero")
        named = {b for v in (given.get("blocks") or {}).values() for b in ([v] if isinstance(v, str) else v)}
        stray = sorted(set(lengths) - named)
        if stray:
            raise SchematicError(f"names for {key}: lengths given for {', '.join(stray)}, which no track's blocks name")
        if given.get("joins", "own") not in ("own", "other"):
            raise SchematicError(f"names for {key}: joins must be \"own\" or \"other\", not {given['joins']!r}")
        leg_b = given.get("leg_b", {})
        if not isinstance(leg_b, dict) or any(v not in ("B", "C") for v in leg_b.values()):
            raise SchematicError(f"names for {key}: leg_b must be an object of switch id: \"B\" or \"C\"")
        stray = sorted(set(leg_b) - {n for n in switches if band["nodes"][n]["kind"] == "switch"})
        if stray:
            raise SchematicError(f"names for {key}: leg_b names {', '.join(stray)}, which is no plain switch of the "
                                 "band")
        halves = sorted(set(leg_b) & {n for _sid, u, v in crossover_pairs(band) for n in (u, v)})
        if halves:
            raise SchematicError(f"names for {key}: leg_b names {', '.join(halves)}, half of a single crossover, "
                                 "whose legs are the crossover's (A to D), not a plain turnout's")
        shared = given.get("shared_turnouts", [])
        if not isinstance(shared, list) or not all(text(v) for v in shared) or len(set(shared)) != len(shared):
            raise SchematicError(f"names for {key}: shared_turnouts must be a list of different turnout names")
        stray = sorted(set(shared) - set((given.get("turnouts") or {}).values()))
        if stray:
            raise SchematicError(f"names for {key}: shared_turnouts names {', '.join(stray)}, which no switch of the "
                                 "band is given as its turnout")
        named = {b for v in (given.get("blocks") or {}).values() for b in ([v] if isinstance(v, str) else v)} | \
            set((given.get("os") or {}).values())
        check_idents(key, given.get("idents"), band, switches, named, seen_idents)
        for section in NAME_KEYS[:4]:
            ids = set(given.get(section) or {})
            have = set(band["strands"]) if section == "blocks" else switches
            missing = sorted(ids - have)
            if missing:
                what = "track" if section == "blocks" else "switch"
                raise SchematicError(f"names for {key}: {section} names {', '.join(missing)}, which is no {what} "
                                     "of the band")


def check_idents(key, idents, band, switches, named, seen):
    """Stop on an `idents` section that is not well formed, before anything is drawn: each ident a name JMRI looks
    up as its kind of object (jmri_kind), never one the panel generates itself (so a given and a generated ident
    never meet), used once across every band (`seen`) but by the two switches of one single crossover; each block
    one the names give (`named`: the band's `blocks` and `os`). Whether a boundary or end is drawn as exactly one
    anchor or bumper can only be checked once drawn (give_idents)."""
    if idents is None:
        return
    what = f"names for {key}: idents"
    if not isinstance(idents, dict):
        raise SchematicError(f"{what} must be an object of {', '.join(IDENT_KEYS)}")
    bad = set(idents) - set(IDENT_KEYS)
    if bad:
        raise SchematicError(f"{what}: {', '.join(sorted(bad))} is not one of {', '.join(IDENT_KEYS)}")
    partner = {}
    for _sid, u, v in crossover_pairs(band):
        partner[u], partner[v] = v, u

    def ident(section, v, where):
        if not (isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]+", v)):
            raise SchematicError(f"{what}: {section} {where}: {v!r} is no Layout Editor name (letters, digits, - "
                                 "or _)")
        if jmri_kind(v) != IDENT_KIND[section]:
            raise SchematicError(f"{what}: {section} {where}: JMRI would look {v!r} up as "
                                 f"{jmri_kind(v) or 'nothing (an unknown prefix)'}, not a {IDENT_KIND[section]} "
                                 "(LayoutEditorFindItems.findObjectByName)")
        if GENERATED.fullmatch(v):
            raise SchematicError(f"{what}: {section} {where}: {v!r} has the form the panel gives its own objects "
                                 f"({PREFIX} after the prefix); pick another")
        if v in seen and seen[v] != (key, section, where):
            raise SchematicError(f"{what}: {v!r} given twice ({seen[v][1]} {seen[v][2]} and {section} {where})")
        seen[v] = (key, section, where)

    def block(section, b, where):
        if b not in named:
            raise SchematicError(f"{what}: {section} {where}: {b!r} is no block the names give this band (give the "
                                 "tracks' blocks in \"blocks\")")

    for section in ("turnouts", "ends", "segments"):
        got = idents.get(section, {})
        if not isinstance(got, dict) or not all(isinstance(k, str) and k.strip() for k in got):
            raise SchematicError(f"{what}: {section} must be an object keyed by "
                                 f"{'switch id' if section == 'turnouts' else 'block name'}")
        for k, v in sorted(got.items()):
            if section == "turnouts":
                if k not in switches:
                    raise SchematicError(f"{what}: turnouts names {k}, which is no switch of the band")
                if partner.get(k) in got and got[partner[k]] == v and partner[k] < k:
                    continue            # the other switch of its crossover gave the same ident
            else:
                block(section, k, k)
            ident(section, v, k)
    got = idents.get("boundaries", [])
    if not isinstance(got, list):
        raise SchematicError(f"{what}: boundaries must be a list of {{\"blocks\": [block, block], \"ident\": name}}")
    pairs = set()
    for b in got:
        if not (isinstance(b, dict) and set(b) == {"blocks", "ident"} and isinstance(b["blocks"], list)
                and len(b["blocks"]) == 2 and all(isinstance(x, str) and x.strip() for x in b["blocks"])
                and b["blocks"][0] != b["blocks"][1]):
            raise SchematicError(f"{what}: boundaries: each entry is {{\"blocks\": [two different block names], "
                                 f"\"ident\": name}}, not {b!r}")
        pair = frozenset(b["blocks"])
        if pair in pairs:
            raise SchematicError(f"{what}: boundaries: {' | '.join(sorted(pair))} given twice")
        pairs.add(pair)
        for x in b["blocks"]:
            block("boundaries", x, " | ".join(sorted(pair)))
        ident("boundaries", b["ident"], " | ".join(sorted(pair)))


def check_masts(key, masts, seen):
    """Stop on a mast entry that is not well formed, or a mast named twice (in this band or another: `seen`)."""
    if not isinstance(masts, list):
        raise SchematicError(f"names for {key}: masts must be a list")
    text = lambda v: isinstance(v, str) and v.strip()      # noqa: E731
    for m in masts:
        if not isinstance(m, dict) or not text(m.get("mast")) or not text(m.get("facing")):
            raise SchematicError(f"names for {key}: each mast needs a mast name and a facing block, as text ({m!r})")
        what = f"names for {key}: mast {m['mast']}"
        bad = set(m) - set(MAST_FIELDS)
        if bad:
            raise SchematicError(f"{what}: {', '.join(sorted(bad))} is not one of {', '.join(MAST_FIELDS)}")
        if m["mast"] in seen:
            raise SchematicError(f"{what} given twice (also in {seen[m['mast']]})")
        seen[m["mast"]] = key
        protects = m.get("protects", [])
        if not isinstance(protects, list) or not all(text(b) for b in protects):
            raise SchematicError(f"{what}: protects must be a list of block names")
        if m.get("kind") not in (None, *MAST_KINDS):
            raise SchematicError(f"{what}: kind {m['kind']!r} is not one of {', '.join(MAST_KINDS)}")
        for flag in ("hidden", "or_join"):
            if not isinstance(m.get(flag, False), bool):
                raise SchematicError(f"{what}: {flag} must be true or false")
        if m.get("or_join") and (protects or m.get("kind") not in (None, "end bumper")):
            raise SchematicError(f"{what}: or_join is for a buffer-stop mast (no protects, kind end bumper)")
        icon = m.get("icon", [1, 1])
        if not (isinstance(icon, (list, tuple)) and len(icon) == 2 and
                all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in icon)):
            raise SchematicError(f"{what}: icon must be [width, height] in pixels, both above zero")


def panel(bands, names=None, cell=CELL, row=ROW, page=None, fit=None, extras=None, gap=BAND_GAP,
          labels_by_band=False, crossover_run=None):
    """A Panel from [(title, band, options)], bands stacked top to bottom. `page` is the options that set the page
    (equal_width, band_width, rotate_bands); the last band's by default, as the sheet. `fit` (width, height): the
    window the panel must open in at 100% zoom; the grid shrinks until the panel and its frame fit (see the module
    text). `extras`: the caller's items tied to blocks, [{"id", "block", "size": [w, h]}], placed by the label layer
    beside their block's track (P.extras); the plugin writes nothing for them. `gap`: px between one band's lowest
    drawing and the next band's highest (BAND_GAP), say to keep room under a band for what the caller adds there;
    or a list, one per pair of bands, top first.
    `labels_by_band`: the label layer places each band's labels in rounds of their own, top band first, each band's
    standing for the next (le_labels.place), so a band's labels are the same whatever bands are drawn below it.
    `crossover_run`: px across that every single crossover's diagonal runs (its two halves' points that far apart
    along the rows, about their middle), so all cross at one angle however each band is stretched; a double
    crossover's diagonals run as far across. A crossover with no room for it (its track beside each half, or each leg,
    keeps MIN_BLOCK px past its legs) takes what there is, and the log gives its angle. A number for every band, or
    {band key: px} for the bands it names (the others as drawn). None: as drawn."""
    if not isinstance(labels_by_band, bool):
        raise SchematicError(f"labels_by_band must be true or false, not {labels_by_band!r}")
    runs = crossover_run.values() if isinstance(crossover_run, dict) else [crossover_run]
    if crossover_run is not None and any(isinstance(r, bool) or not isinstance(r, (int, float)) or
                                         not math.isfinite(r) or r <= 0 for r in runs):
        raise SchematicError(f"crossover_run must be a number of px above zero, or one per band key, not "
                             f"{crossover_run!r}")
    if isinstance(crossover_run, dict):
        keys = [band_key(t) for t, _b, _o in bands]
        stray = sorted(set(crossover_run) - set(keys))
        if stray:
            raise SchematicError(f"crossover_run names {', '.join(stray)}, which is no band (bands: {', '.join(keys)})")
    if fit is None:
        return draw_panel(bands, names, cell, row, page, extras=extras, gap=gap, labels_by_band=labels_by_band,
                          crossover_run=crossover_run)
    if crossover_run is not None:
        raise SchematicError("crossover_run is for a panel drawn at a given grid, not one fitted to a window")
    W, H = fit[0] - CHROME[0], fit[1] - CHROME[1]           # the panel inside the window's frame
    if W <= 0 or H <= 0:
        raise SchematicError(f"a {fit[0]}x{fit[1]} px window leaves no room for a panel inside its frame")
    fits = lambda Q: Q.size[0] <= W and Q.size[1] <= H      # noqa: E731

    def search(masts):
        draw = lambda kx, ky: draw_panel(bands, names, cell * kx, row * ky, page, masts, labels=False,  # noqa: E731
                                         gap=gap)
        lo = draw(FIT_MIN, FIT_MIN)
        if not fits(lo):
            raise SchematicError(f"the panel does not fit a {fit[0]}x{fit[1]} px window even with the grid at "
                                 f"{FIT_MIN:g} of its size ({lo.size[0]}x{lo.size[1]} px)")

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
            if fits(draw(kx, ky)):
                return kx, ky
        k = min(kx, ky)
        if fits(draw(k, k)):
            return k, k
        raise SchematicError(f"no grid scale settles to fit a {fit[0]}x{fit[1]} px window")

    # search on the track and labels alone (masts are placed once at the end); masts sit beside the track, but if
    # their icons push the panel past the window, search again with them
    # (the label layer comes last, once the grid is settled: it changes nothing else and keeps inside the panel)
    kx, ky = search(False)
    P = draw_panel(bands, names, cell * kx, row * ky, page, labels=False, gap=gap)
    if not fits(P):
        kx, ky = search(True)
        P = draw_panel(bands, names, cell * kx, row * ky, page, labels=False, gap=gap)
    label_layer(P, bands, page, extras, labels_by_band)
    P.scale, P.fit = (kx, ky), tuple(fit)
    return P


def draw_panel(bands, names, cell, row, page, masts=True, labels=True, extras=None, gap=BAND_GAP,
               labels_by_band=False, crossover_run=None):
    """The panel drawn at this grid (see panel). Every message it keeps or stops with names objects by their written
    idents (Panel.text). `labels`: then run the label layer (label_layer). `page` as given: the drawing takes the
    last band's options when it is None (_draw), the labels take none (le_labels.options), so a band's le_labels
    never reach another band, with or without `fit`."""
    if bands:
        le_labels.options(bands, page)      # checked before any drawing (page None: no page-wide label options)
    le_labels.check_extras(extras)
    P = Panel()
    P.crossover_run = crossover_run
    try:
        _draw(P, bands, names, cell, row, page, masts, gap)
    except SchematicError as e:
        raise SchematicError(P.text(str(e))) from None
    P.final_text()
    if labels:
        label_layer(P, bands, page, extras, labels_by_band)
    return P


def geometry(P):
    """{(kind, ident): what JMRI reads of it}: every turnout, track segment, anchor and end bumper, shape and mast
    (its slot and icon), and the panel's size."""
    out = {("panel", "size"): tuple(P.size)}
    for t in P.turnouts:
        out[("turnout", t["ident"])] = (t["type"], tuple(t["cen"]), tuple(sorted((k, tuple(v)) for k, v in
                                                                                   t["pts"].items())))
    for s in P.segments:
        arc = s["arc"] and (s["arc"]["angle"], s["arc"]["flip"], tuple(map(tuple, s["arc"]["drawn"])))
        out[("track segment", s["ident"])] = (tuple(map(tuple, s["ends"])), s["block"], arc, s["hidden"])
    for k, p in P.points.items():
        out[("point", k)] = (p["type"], tuple(p["xy"]), tuple(p["conn"]))
    for sh in P.shapes:
        out[("shape", sh["ident"])] = (tuple(sh["centre"]), sh["r"])
    for m in P.masts:
        out[("mast", m["mast"])] = (m["kind"], m["ident"], m["slot"], tuple(m.get("icon") or ()))
    return out


def label_layer(P, bands, page, extras=None, by_band=False):
    """le_labels.place, then the check that it changed nothing of the drawing: every turnout, track segment, point,
    shape and mast icon, and the panel's size, as before it ran (the labels adapt to the approved geometry, never
    the reverse). Stops naming the first thing that differs."""
    before = geometry(P)
    try:
        le_labels.place(P, bands, le_labels.options(bands, page), extras=extras, by_band=by_band)
    except SchematicError as e:
        raise SchematicError(P.text(str(e))) from None
    P.final_text()
    after = geometry(P)
    for key in sorted(set(before) | set(after), key=str):
        if before.get(key) != after.get(key):
            raise SchematicError(P.text(f"the label layer changed the drawing: {key[0]} {key[1]} was "
                                        f"{before.get(key)}, now {after.get(key)}"))


def band_gaps(gap, n):
    """[px] between each band and the next of `n` bands: `gap` (a number for all, or a list of one per pair of
    bands, top first), each a number of px, 0 or more."""
    ok = lambda g: not isinstance(g, bool) and isinstance(g, (int, float)) and math.isfinite(g) and g >= 0  # noqa: E731
    if isinstance(gap, (list, tuple)):
        if len(gap) != max(n - 1, 0) or not all(ok(g) for g in gap):
            raise SchematicError(f"the gaps between bands must be {max(n - 1, 0)} numbers of px, 0 or more (one "
                                 f"per pair of bands), not {gap!r}")
        return list(gap)
    if not ok(gap):
        raise SchematicError(f"the gap between bands must be a number of px, 0 or more, not {gap!r}")
    return [gap] * max(n - 1, 0)


def _draw(P, bands, names, cell, row, page, masts, gap=BAND_GAP):
    if not bands:
        raise SchematicError("no band to draw")
    gaps = band_gaps(gap, len(bands))
    page = page if page is not None else bands[-1][2]
    names = names or {}
    check_names(bands, names)
    align = check_band_align(bands, page)
    shared = plan_shared(P, bands, names, page)
    joined = partners(bands)
    given = {b for g in names.values() for v in (g.get("blocks") or {}).values()
             for b in ([v] if isinstance(v, str) else v)} | \
        {b for g in names.values() for b in (g.get("os") or {}).values()}
    os_defaults = {f"OS {d.get('label') or n}" for _, band, _ in bands for n, d in band["nodes"].items()
                   if d["kind"] in ("switch", "dx")}
    defaults = default_names(bands, joined, given | os_defaults)
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
        P.cellx[bi] = cellx
        Band(P, bi, title, band, names.get(key, {}), defaults, joined, cellx, row, turned, ends, opts,
             drawn[bi]).build()
        boxes.append(extent(P, bi, room=True))
    # move each band into place: its whole box (labels, circles and arcs too) centred on the widest box, each band
    # below the one before, so nothing lies left of or above the margin
    P.cur = None
    full = max(b[2] - b[0] for b in boxes)
    top = MARGIN + TITLE_GAP
    for bi, ((title, _, _), box) in enumerate(zip(bands, boxes)):
        room = full - (box[2] - box[0])
        left = {"left": 0, "right": room}.get(align.get(band_key(title), "centre"), room / 2)
        shift(P, bi, MARGIN + left - box[0], top - box[1])
        P.band_boxes.append((MARGIN + left, top, MARGIN + left + box[2] - box[0], top + box[3] - box[1]))
        P.label(title.upper(), (MARGIN, top - TITLE_GAP + 4), TITLE_SIZE, True, anchor="left", kind="title")
        top += box[3] - box[1] + (gaps[bi] if bi < len(gaps) else 0)
    for (bi, n), (bj, m) in sorted(joined.items()):
        if (bi, n) > (bj, m):
            continue
        a, b = ends[(bi, n)], ends[(bj, m)]
        mine, theirs = (names.get(band_key(bands[k][0]), {}).get("joins") == "other" for k in (bi, bj))
        if mine and theirs:
            raise SchematicError(f"{bands[bi][0]} and {bands[bj][0]} both give their joins the other band's block: "
                                 "set \"joins\": \"other\" on one of them")
        block = b[3] if mine else a[3]
        P.joins.append(P.segment(a[0], b[0], block, a[4] and b[4], hidden=True))
        P.join_ends[(bi, a[0])] = a[3]
        P.join_ends[(bj, b[0])] = b[3]
    check_shared(P, shared)
    if any(g.get("idents") for g in names.values()):
        give_idents(P, bands, names)        # before the masts, so the alias is known for all they say
    if masts and any(g.get("masts") for g in names.values()):
        place_masts(P, bands, names)
    box = extent(P)
    P.size = (math.ceil(box[2] + MARGIN), math.ceil(box[3] + MARGIN))


def page_bands(bands, page):
    """The band keys the page knows: the bands drawn, and every band its `band_order` lists (so `--band` may draw
    part of a page whose settings name all its bands)."""
    order = page.get("band_order") or []
    return [band_key(t) for t, _, _ in bands] + [k for k in order if isinstance(k, str)
                                                 and k not in {band_key(t) for t, _, _ in bands}]


def check_band_align(bands, page):
    """The page's `band_align`, checked: {band key: "left", "centre" or "right"}, each a band the page knows (one not
    drawn now is allowed and ignored)."""
    align = page.get("band_align") or {}
    known = page_bands(bands, page)
    if not isinstance(align, dict):
        raise SchematicError(f"band_align must be an object of band: \"left\", \"centre\" or \"right\", not {align!r}")
    bad = sorted(f"{k} (no band; bands: {', '.join(known)})" for k in align if k not in known) + \
        sorted(f"{k}: {v!r}" for k, v in align.items() if v not in ("left", "centre", "right"))
    if bad:
        raise SchematicError(f"band_align must be an object of band: \"left\", \"centre\" or \"right\": "
                             f"{', '.join(bad)}")
    return align


def plan_shared(P, bands, names, page):
    """{turnout name: how many turnouts carry it} from the names, checked before drawing (the one place the rule
    lives): a name on more than one turnout must be in `shared_turnouts` of every band that gives it; a shared name
    is on two turnouts, or on one when a band the page knows is not drawn (its other half may be there; logged), never
    more than two. The two switches of one single crossover given one name are one turnout."""
    count, bands_of = defaultdict(int), defaultdict(list)
    for bi, (title, band, _) in enumerate(bands):
        given = (names.get(band_key(title)) or {}).get("turnouts") or {}
        partner = {}
        for _sid, u, v in crossover_pairs(band):
            if given.get(u) is not None and given.get(u) == given.get(v):
                partner[u], partner[v] = v, u
        done = set()
        for n, name in sorted(given.items()):
            if n in done:
                continue
            done |= {n, partner.get(n, n)}
            count[name] += 1
            bands_of[name].append(bi)
    undrawn = [k for k in page_bands(bands, page) if k not in {band_key(t) for t, _, _ in bands}]
    for bi, (title, _, _) in enumerate(bands):
        listed = (names.get(band_key(title)) or {}).get("shared_turnouts") or []
        for name in sorted(count):
            if count[name] > 1 and bi in bands_of[name] and name not in listed:
                raise SchematicError(f"{title}: turnout name {name!r} is given to {count[name]} turnouts, but this "
                                     "band does not list it in shared_turnouts (list it in each band if they are one "
                                     "turnout drawn twice)")
        for name in listed:
            if count[name] > 2:
                raise SchematicError(f"{title}: shared_turnouts names {name!r}, which is given to {count[name]} "
                                     "turnouts; one turnout is drawn at most twice")
            if count[name] == 1:
                if not undrawn:
                    raise SchematicError(f"{title}: shared_turnouts names {name!r}, which is drawn as 1 turnout; it "
                                         "shares nothing")
                P.log.append(f"{title}: shared turnout {name!r} is drawn once here; its other half may be on a band "
                             f"not drawn ({', '.join(undrawn)})")
    return dict(count)


def check_shared(P, planned):
    """After drawing: each turnout name is on as many turnouts as plan_shared counted (a single crossover drawn as
    two turnouts, when its switches are not on two level tracks, would not be)."""
    drawn = defaultdict(int)
    for t in P.turnouts:
        if t["name"]:
            drawn[t["name"]] += 1
    bad = sorted(n for n in set(drawn) | set(planned) if drawn.get(n, 0) != planned.get(n, 0))
    if bad:
        raise SchematicError("turnout names on a different number of turnouts than the names give: " +
                             ", ".join(f"{n} ({drawn.get(n, 0)} drawn, {planned.get(n, 0)} given)" for n in bad))


def give_idents(P, bands, names):
    """The idents the names ask for (an older panel's, say), as an alias layer over the generated ones, once the
    track is drawn and joined (masts move no track, so they cannot change what these find): a switch's turnout; the
    anchor between two blocks (the pair must be drawn as exactly one anchor); the end bumper of a block (the block must
    end at exactly one bumper); a block's one track segment (used only when the block is drawn as one segment, else
    logged). The rest keep their generated idents, which no given ident can take (check_idents). Sets
    P.idents_given {generated: given}, filled as it goes (so a message raised part way names what is given so far);
    nothing is renamed: to_xml writes P.name(ident) and every message goes through P.text."""
    rename = P.idents_given = {}

    def take(old, new, what):
        if old in rename and rename[old] != new:
            raise SchematicError(f"{what}: its object is already named {rename[old]}")
        if new in rename.values() and rename.get(old) != new:
            raise SchematicError(f"{what}: ident {new} given to two separate objects")
        rename[old] = new

    seg_of = {s["ident"]: s for s in P.segments}
    for bi, (title, _, _) in enumerate(bands):
        idents = names.get(band_key(title), {}).get("idents") or {}
        if not idents:
            continue
        mine_pts = {k: p for k, p in P.points.items() if p["band"] == bi}
        for n, new in sorted((idents.get("turnouts") or {}).items()):
            got = P.turnout_of.get((bi, n))
            if got is None:
                raise SchematicError(f"{title}: idents: switch {n} is drawn as no turnout")
            take(got[0], new, f"{title}: idents: switch {n}")
        between = defaultdict(list)
        ends = defaultdict(list)
        for ident, p in sorted(mine_pts.items()):
            blocks = [seg_of[c]["block"] for c in p["conn"]]
            if p["type"] == "END_BUMPER":
                ends[blocks[0]].append(ident)
            elif len(blocks) == 2 and blocks[0] != blocks[1]:
                between[frozenset(blocks)].append(ident)
        for b in idents.get("boundaries") or []:
            pair = frozenset(b["blocks"])
            got = between.get(pair, [])
            if len(got) != 1:
                raise SchematicError(f"{title}: idents: the boundary {' | '.join(sorted(pair))} ({b['ident']}) is "
                                     f"drawn at {len(got)} anchors{': ' + ', '.join(got) if got else ''}; it must "
                                     "be exactly one")
            take(got[0], b["ident"], f"{title}: idents: boundary {' | '.join(sorted(pair))}")
        for block, new in sorted((idents.get("ends") or {}).items()):
            got = ends.get(block, [])
            if len(got) != 1:
                raise SchematicError(f"{title}: idents: block {block} ends at {len(got)} end bumpers; an end "
                                     "ident needs exactly one")
            take(got[0], new, f"{title}: idents: end of {block}")
        segs = defaultdict(list)            # the band's own drawn segments; a hidden join keeps its generated ident
        for s in P.segments:
            if s["band"] == bi:
                segs[s["block"]].append(s["ident"])
        for block, new in sorted((idents.get("segments") or {}).items()):
            got = segs.get(block, [])
            if not got:
                raise SchematicError(f"{title}: idents: segment {new}: no track of block {block} is drawn")
            if len(got) != 1:
                P.log.append(f"{title}: idents: block {block} is drawn as {len(got)} track segments, so segment "
                             f"ident {new} is not used (they keep generated idents)")
                continue
            take(got[0], new, f"{title}: idents: segment of {block}")
    written_idents(P)                   # every object written under one ident, each given ident used once


def written_idents(P):
    """{generated ident: written ident} for every object to_xml writes (turnouts, track segments, points, shapes),
    checked: no generated ident is two objects, every given ident names one drawn object, and no two objects are
    written under one ident."""
    out, kind = {}, {}
    for what, idents in (("turnout", [t["ident"] for t in P.turnouts]),
                         ("track segment", [s["ident"] for s in P.segments]),
                         ("point", list(P.points)), ("shape", [sh["ident"] for sh in P.shapes])):
        for i in idents:
            if i in out:
                raise SchematicError(f"idents: a {kind[i]} and a {what} are drawn under one generated ident")
            out[i], kind[i] = P.name(i), what
    lost = sorted(v for k, v in P.idents_given.items() if k not in out)
    if lost:
        raise SchematicError(f"idents: given to nothing drawn: {', '.join(lost)}")
    seen = defaultdict(list)
    for i, n in out.items():
        seen[n].append(kind[i])
    dup = sorted(n for n, v in seen.items() if len(v) > 1)
    if dup:
        raise SchematicError("idents: " + "; ".join(f"{n} would name {len(seen[n])} objects ({', '.join(seen[n])})"
                                                   for n in dup))
    return out


def check_connections(P):
    """Stop unless every ident a part of the panel names is an object of it, of the right kind: segment ends,
    turnout legs, points' tracks, masts' slots, and the Panel's own lookups (all generated idents)."""
    turnouts = {t["ident"] for t in P.turnouts}
    segs = {s["ident"] for s in P.segments}
    bad = []
    for s in P.segments:
        for i, typ in s["ends"]:
            if i not in (P.points if typ == "POS_POINT" else turnouts):
                bad.append(f"segment {s['ident']} ends at {i} ({typ})")
    for t in P.turnouts:
        bad += [f"turnout {t['ident']} leg {leg}: {v}" for leg, v in t["conn"].items() if v not in segs]
    for k, p in P.points.items():
        bad += [f"point {k}: {c}" for c in p["conn"] if c not in segs]
    for m in P.masts:
        if m["ident"] not in (turnouts if m["kind"] == "turnout" else P.points):
            bad.append(f"mast {m['mast']} on {m['ident']}")
    bad += [f"strand {k}: {i}" for k, v in P.strand_segments.items() for i in v if i not in segs]
    bad += [f"switch {k}: {v[0]}" for k, v in P.turnout_of.items() if v[0] not in turnouts]
    bad += [f"turnback {k}: {i}" for k, v in P.turnbacks.items() for i in v if i not in segs]
    bad += [f"join {i}" for i in P.joins if i not in segs]
    bad += [f"join end {i}" for (_b, i) in P.join_ends if i not in P.points]
    if bad:
        raise SchematicError("idents: these name nothing on the panel: " + "; ".join(bad[:8]))


ROOM = ("switch", "name", "station")     # the labels the drawing only keeps room for (le_labels places them)


def extent(P, bi=None, room=False):
    """(left, top, right, bottom) of everything drawn for band bi (all bands when None): track, arcs, circles,
    labels, mast and block contents icons. A label counts as JMRI draws it (le_labels.label_box), or as placed;
    the room kept for one not yet placed counts as that room. `room`: every label as its room (room_width), as the
    bands were always placed by it (the approved geometry)."""
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
            if room or ("box" not in lb and lb["kind"] in ROOM):    # the room the drawing keeps for it
                xs += [lb["xy"][0], lb["xy"][0] + room_width(lb["text"], lb["size"])]
                ys += [lb["xy"][1], lb["xy"][1] + lb["size"]]
            else:                               # as JMRI draws it (or placed)
                x0, y0, x1, y1 = le_labels.label_box(lb)
                xs += [x0, x1]
                ys += [y0, y1]
    for m in P.masts + P.bcis:
        if mine(m):
            x, y, w, h = m["box"]
            xs += [x, x + w]
            ys += [y, y + h]
    return min(xs), min(ys), max(xs), max(ys)


def place_masts(P, bands, names):
    """Each named mast into the slot of its band that JMRI resolves to its facing and protected blocks."""
    from . import slots
    ix = slots.Index(to_xml(P, "probe", probe=True))
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
            moved = join_why = None
            if not cands and not other and m.get("or_join"):
                # a buffer stop asked for, with no bumper slot on its track: the track runs on through a join, so
                # the mast may stand on the join's anchor, facing its block and protecting the join's own block
                at = sorted(ident for (b, ident), blk in P.join_ends.items() if b == bi and blk == m["facing"])
                joins = [c for c in ix.candidates() if c[0] == "anchor" and c[1] in at and c not in taken
                         and ix.blocks(*c)[0] == m["facing"]]
                beyond = [c for c in joins if ix.blocks(*c)[1] and ix.blocks(*c)[1] != [m["facing"]]]
                if len(beyond) == 1:
                    cands = beyond
                    moved = (f"{m['facing']} has no buffer stop: it runs on through the join at {beyond[0][1]}, so "
                             f"the mast stands there (an anchor, not an end bumper), protecting "
                             f"{ix.blocks(*beyond[0])[1]}")
                elif beyond:
                    join_why = f"{m['facing']} runs through {len(beyond)} joins: {', '.join(c[1] for c in beyond)}"
                elif at:
                    join_why = (f"the join at {', '.join(at)} carries {m['facing']} on both sides, so it is no block "
                                "boundary (give one band \"joins\": \"other\")")
            if not cands:
                if join_why:
                    why = f"no buffer stop for {m['facing']}, and {join_why}"
                elif other:
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
            P.masts.append(dict(mast=m["mast"], kind=kind, ident=ident, slot=slot, hidden=bool(m.get("hidden")),
                                size=tuple(m.get("icon") or slots.ICON), band=bi))
    # the CATS rules for where a mast reads best, carried over (le_masts): gantries, then each icon's clearest spot
    from . import le_masts
    le_masts.place(P, bands, ix)


def shift(P, bi, dx, dy):
    move = lambda p: [p[0] + dx, p[1] + dy]       # noqa: E731
    for t in P.turnouts:
        if t["band"] == bi:
            t["cen"] = move(t["cen"])
            t["at"] = move(t["at"])
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
            if "run" in lb:
                lb["run"] = [move(q) for q in lb["run"]]


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
    def add_turnout(self, nodes, ttype, cen, pts, conn_ports, blocks, continuing="2", at=None):
        """`at`: where the drawn legs meet, when the centre stands elsewhere (leg_b); labels go by it."""
        P = self.P
        t = dict(ident=P.ident("TO"), type=ttype, cen=list(cen), at=list(at if at is not None else cen),
                 pts={k: list(v) for k, v in pts.items()}, conn={},
                 blocks=blocks, continuing=continuing, ver="2" if "XOVER" in ttype else "1",
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

    def crossovers(self):
        """Two switches of one number joined C to C by a track: one single crossover."""
        for sid, u, v in crossover_pairs(self.band):
            du = self.nodes[u]
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
            if self.run() is not None:
                tp, bp = self.crossover_points(du["label"], top, tp, bot, bp, h)
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

    def run(self):
        """px across this band's crossovers' diagonals run (P.crossover_run, by band key when a dict), or None."""
        run = self.P.crossover_run
        return run.get(band_key(self.title)) if isinstance(run, dict) else run

    def room_toward(self, n, port, h):
        """px a crossover half at node n may move along its row toward `port`: its first straight piece that way,
        less its own leg (h), the far switch's leg when the piece runs straight to it, and MIN_BLOCK; shared half
        and half when the far switch is a crossover half that may move toward it too."""
        pts = self.away(n, port)
        sid = self.port_strand(n, port)
        s = self.strands[sid]
        far = s["dst"][0] if tuple(s["src"]) == (n, port) else s["src"][0]
        halves = {x for _sid, u, v in crossover_pairs(self.band) for x in (u, v)}
        if len(pts) == 2 and self.nodes[far]["kind"] in ("switch", "dx"):
            reserve, share = (1.5 * LEG, 0.5) if far in halves else (LEG, 1.0)
        else:
            reserve, share = 0.0, 1.0           # a bend first: its arc takes from the run beyond, not this piece
        return max(0.0, (self.first_len(n, port) - h - reserve - MIN_BLOCK) * share)

    def crossover_points(self, label, top, tp, bot, bp, h):
        """(top point, bottom point) of a single crossover drawn P.crossover_run px across, about its middle: each
        half moves along its own row, as far as its track on that side has room (room_toward); where that leaves less
        than the run asked, the crossover takes what there is (logged with its angle)."""
        dx0, dy = abs(bp[0] - tp[0]), abs(bp[1] - tp[1])
        way = 1 if bp[0] >= tp[0] else -1
        move = (self.run() - dx0) / 2          # px each half moves apart (negative: together)
        if abs(move) < EPS:
            return tp, bp
        room = []
        for n, sign in ((top, -way), (bot, way)):        # the side each half moves toward
            side = 1 if move * sign > 0 else -1
            ports = [p for p in "AB" if self.direction(n, p)[0] * side > 0]
            if len(ports) != 1:
                raise SchematicError(f"{self.title}: switch {label}: no one leg of the crossover leads that way")
            room.append(self.room_toward(n, ports[0], h))
        step = math.copysign(min(abs(move), *room), move)
        if abs(step - move) > EPS:
            run = dx0 + 2 * step
            self.P.log.append(f"{self.title}: switch {label}: crossover drawn {run:.1f} px across, "
                              f"{math.degrees(math.atan2(dy, run)):.1f} degrees: no room for "
                              f"{self.run():.1f} px")
        mid_x = (tp[0] + bp[0]) / 2
        half = (dx0 + 2 * step) / 2
        return (mid_x - way * half, tp[1]), (mid_x + way * half, bp[1])

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
            room = min(self.first_len(n, p) for p in "ABCD") - MIN_BLOCK
            want = self.run() / 2
            got = max(h, min(want, room))
            if got < want - EPS:
                self.P.log.append(f"{self.title}: double crossover {self.nodes[n].get('label') or n} drawn "
                                  f"{2 * got:.1f} px across, {math.degrees(math.atan2(ys[1] - ys[0], 2 * got)):.1f} "
                                  f"degrees: no room for {self.run():.1f} px")
            h = got
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
                P.label(label, (cen[0], top - NUMBER_SIZE - 5), NUMBER_SIZE, True, kind="switch")
                continue
            down = t["pts"]["C"][1] > cen[1] + EPS or t["pts"]["B"][1] > cen[1] + EPS
            y = cen[1] - NUMBER_SIZE - 6 if down else cen[1] + 5
            P.label(label, (cen[0], y), NUMBER_SIZE, True, kind="switch")
        for sid, s in sorted(self.strands.items()):
            if not s["name"] or sid in self.internal:
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


# ---------------------------------------------------------------- XML

def to_xml(P, name, attrs=None, options=None, probe=False):
    """The panel as a <LayoutEditor> element. `attrs` replace the editor attributes (a template panel's, say);
    `options` is a layoutTrackDrawingOptions element to copy (its name is set to the panel's). `probe`: for reading
    the slots while the masts are being placed, without their icons and under the generated idents (the Panel's
    own); otherwise a mast with no icon stops, and every ident is written as P.name gives it, each object's checked
    to be one only it has (written_idents)."""
    try:
        return _xml(P, name, attrs, options, probe)
    except SchematicError as e:
        raise SchematicError(P.text(str(e))) from None


def _xml(P, name, attrs, options, probe):
    a = dict(EDITOR) if attrs is None else dict(attrs)
    a.pop("class", None)
    if P.fit:           # the panel was fitted inside this window less CHROME, so the window fits
        window = (P.size[0] + CHROME[0], P.size[1] + CHROME[1])
    else:
        window = (min(P.size[0], 1900), min(P.size[1], 1000))
    a.update(name=name, x="0", y="0", panelwidth=str(P.size[0]), panelheight=str(P.size[1]),
             windowwidth=str(window[0]), windowheight=str(window[1]))
    le = ET.Element("LayoutEditor", {"class": CLASS["editor"], **a})
    if probe:
        n = str
    else:
        check_connections(P)
        written = written_idents(P)
        n = written.__getitem__         # every ident written resolves through the one mapping
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
        at = {"ident": n(t["ident"]), "type": t["type"], "hidden": "no", "disabled": "no", "disableWhenOccupied": "yes",
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
                at[f"connect{leg.lower()}name"] = n(t["conn"][leg])
        el = ET.SubElement(le, "layoutturnout", at)
        for leg in "ABCD":
            if leg in on_turnout.get(t["ident"], {}):
                ET.SubElement(el, f"signal{leg}Mast").text = on_turnout[t["ident"]][leg]
    for s in P.segments:
        (c1, t1), (c2, t2) = s["ends"]
        at = {"ident": n(s["ident"]), "blockname": s["block"], "connect1name": n(c1), "type1": t1,
              "connect2name": n(c2), "type2": t2, "dashed": "yes" if s["dashed"] else "no",
              "mainline": "yes" if s["main"] else "no",
              "hidden": "yes" if s["hidden"] else "no"}
        if s["arc"]:
            at.update(arc="yes", flip="yes" if s["arc"]["flip"] else "no", circle="yes",
                      angle=f"{s['arc']['angle']:g}", hideConLines="yes")
        at["class"] = CLASS["segment"]
        le.append(ET.Element("tracksegment", at))
    for ident, p in P.points.items():
        at = {"ident": n(ident), "type": p["type"], "x": r1(p["xy"][0]), "y": r1(p["xy"][1])}
        for i, seg in enumerate(p["conn"], 1):
            at[f"connect{i}name"] = n(seg)
        for slot, mast in sorted(on_point.get(ident, {}).items()):
            at[f"{slot}boundsignalmast"] = mast
        at["class"] = CLASS["point"]
        le.append(ET.Element("positionablepoint", at))
    for sh in P.shapes:
        el = ET.Element("layoutShape", {"ident": n(sh["ident"]), "type": "Closed", "level": "3", "linewidth": "2",
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
            "hasBackground": "no", "justification": "left", **FONT, "class": CLASS["label"]}))
    le.extend(le_labels.bci_elements(P))
    for m in P.masts:
        if probe:                       # slots only, while the masts are being placed
            continue
        if not m.get("icon"):
            raise SchematicError(f"mast {m['mast']} has no icon placed")
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
            f"{len(P.labels)} labels, {len(P.bcis)} block contents icons"
            + (f", {len(P.masts)} masts" + (f" ({len(P.unplaced)} not placed)" if P.unplaced else "")
               if P.masts or P.unplaced else "")
            + f"; {P.size[0]}x{P.size[1]} px"
            + (f" (grid at {P.scale[0]:.3f} x {P.scale[1]:.3f} to fit)" if P.scale != (1.0, 1.0) else ""))
