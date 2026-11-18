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
                         "icon": [w, h], "or_join": ..., "leg": "normal" or "diverging"}],
              "joins": "own", "other" or "none", "leg_b": {node: "B" or "C"}, "shared_turnouts": [turnout name, ...],
              "xover_blocks": {node: {"A": block, "B": block, "C": block, "D": block}},
              "idents": {"turnouts": {node: ident}, "boundaries": [{"blocks": [block, block], "ident": ident}],
                         "ends": {block: ident}, "segments": {block: ident}}}}
A strand with several blocks is cut for them in order from its first end to its second: in proportion to their
real lengths when `lengths` gives one for each (so a short throat block sits at its own end of the track), else into
equal lengths; no block is drawn shorter than MIN_BLOCK px, and no cut falls inside an arc. Without names
a strand's block is its track name (or the two switch numbers it joins, made unique), a turnback and a joined helix
or connector track share the block of the track they continue, an OS block is "OS <switch number>", and no turnout
is named. Sensors are not placed. `xover_blocks` gives a double crossover a block per corner, keyed by the band's
legs A to D (each leg's corner takes its block), in place of its one OS block; the four must differ. With one block,
or two, JMRI 5.16 records a through path between the two tracks on one side (LayoutBlock.addThroughPath keeps a
pair whose turnout lists match both ways, and both ways give the crossover the same state: with one block every
search ends at the crossover with nothing found, with two blocks both boundaries between them carry one state), so
routing and Signal Mast Logic discovery would run a train from leg A to leg D, which no double crossover can. With a
block per corner the A-B and B-D boundaries of corner B carry CLOSED and THROWN, so no corner joins A to D. `leg_b` names the band leg that is Layout Editor leg B (default: the drawn
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
`"joins": "other"` on a band gives its hidden joins the other band's block (on one band of a pair, not both);
`"joins": "none"` draws that band's connector and helix ends unjoined, as ends, so no hidden join reaches it. A
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
from collections import defaultdict

from . import cache, le_labels, le_prefs
from .core import SchematicError, node_ref, tidy
from .draw import band_key
from .layout import paths

CELL = 36           # px per grid column, before `equal_width` stretches a band
ROW = 36            # px per grid row
LEG = 12            # px from a switch's points to the end of a leg
BEND = 18           # largest radius of a rounded corner, px
ROUND_SLACK = 1.5   # px a crossover piece may reach past its room by rounding to whole pixels (logged)
MIN_BLOCK = LEG     # px a block of several on one track is drawn at least (a throat: just clear of its switch)
HELIX_R = 9         # radius of the circle that marks a helix end, px
MARGIN = 60         # px left of and above the drawing
BAND_GAP = 96       # px between one band's lowest track and the next band's highest
TITLE_GAP = 40      # px from a band's title to its highest track
TITLE_DROP = 4      # px the title's top stands below TITLE_GAP above its band
STRETCH_MAX = 2.5   # as the sheet: a band is never stretched more than this
LABEL_SIZE, NUMBER_SIZE, TITLE_SIZE = 10, 9, 13
EPS = 1e-6
CHROME = (18, 60)   # px Layout Editor allows for its frame around the panel (LayoutEditorXml: panel = window - this)
FIT_MIN = 0.25      # `fit` never scales the grid below this

PREFIX = "G"        # in every ident: TOG, TG, AG, EBG; so a generated panel's names never meet another's


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


def double_corners(band, n, turned=False, drawn=None):
    """{band leg: Layout Editor corner} of double crossover `n` as the panel draws it: A top left, B top right, C
    bottom right, D bottom left, from where each leg's drawn track leaves (`turned`: the band is in rotate_bands;
    `drawn`: its paths, default layout.paths). A caller naming `xover_blocks` by corner reads the legs here."""
    drawn = drawn if drawn is not None else paths(band)
    k = -1 if turned else 1
    d = band["nodes"][n]
    ends = {}
    for p in "ABCD":
        sid = d["ins"].get(p) or d["outs"].get(p)
        if sid is None:
            raise SchematicError(f"double crossover {d.get('label') or n}: no track on leg {p}")
        pts = clean([(k * x, k * y) for x, y in drawn[sid]])
        if tuple(band["strands"][sid]["src"]) != (n, p):
            pts = pts[::-1]
        if len(pts) < 2 or abs(pts[1][0] - pts[0][0]) < 1e-3:
            raise SchematicError(f"double crossover {d.get('label') or n}: leg {p} leaves straight up or down, so it "
                                 "is on neither side of the crossover")
        ends[p] = (round(pts[0][1], 3), "left" if pts[1][0] < pts[0][0] else "right")
    ys = sorted({y for y, _ in ends.values()})
    corner = {(ys[0], "left"): "A", (ys[0], "right"): "B", (ys[-1], "right"): "C", (ys[-1], "left"): "D"}
    got = {p: corner.get(e) for p, e in ends.items()}
    if len(ys) != 2 or sorted(got.values(), key=str) != list("ABCD"):
        raise SchematicError(f"double crossover {d.get('label') or n}: its legs do not reach four corners")
    return got


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
        self.tight_crossovers = {}  # band key -> [(label, label)]: crossovers drawn close on their shared track (panel)
        self.split_crossovers = {}  # band key -> [label]: crossovers drawn as two plain turnouts on one name (panel)
        self.split_names = set()    # turnout names of crossovers with no room, drawn as two turnouts (crossovers)
        self.lamps = []             # the caller's lamp boxes the label layer kept clear (le_labels lamp_columns)
        self.band_boxes = []        # (x0, y0, x1, y1) each band was placed by: its drawing with the room for its labels
        self.names_skipped = []     # why each names_last track name was left out (le_labels)
        self.bcis_skipped = []      # why each optional_block_contents icon was left out (le_labels)
        self.no_name = {}           # (band index, strand id) -> why the drawing keeps no room for its name
        self.mast_straights = {}    # mast -> dict: band, seg, ident, kind, run, need (le_masts; mast_room)
        self.widened = {}           # (band index, strand id) -> px let in for mast icons (mast_room), crossover pairs
        self.pair_angles = {}       # "a/b" -> degrees a crossover pair's diagonal crosses at (crossover_pairs)
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
        self.bcis_skipped = [self.text(why) for why in self.bcis_skipped]
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


NAME_KEYS = ("turnouts", "os", "normal", "blocks", "masts", "joins", "lengths", "leg_b", "idents", "shared_turnouts",
             "xover_blocks")
MAST_KINDS = ("anchor", "end bumper", "turnout")
MAST_FIELDS = ("mast", "facing", "protects", "kind", "hidden", "icon", "or_join", "leg")
MAST_LEGS = ("normal", "diverging")
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
        if given.get("joins", "own") not in ("own", "other", "none"):
            raise SchematicError(f"names for {key}: joins must be \"own\", \"other\" or \"none\", not "
                                 f"{given['joins']!r}")
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
        check_xover_blocks(key, given.get("xover_blocks"), band)
        shared = given.get("shared_turnouts", [])
        if not isinstance(shared, list) or not all(text(v) for v in shared) or len(set(shared)) != len(shared):
            raise SchematicError(f"names for {key}: shared_turnouts must be a list of different turnout names")
        stray = sorted(set(shared) - set((given.get("turnouts") or {}).values()))
        if stray:
            raise SchematicError(f"names for {key}: shared_turnouts names {', '.join(stray)}, which no switch of the "
                                 "band is given as its turnout")
        named = {b for v in (given.get("blocks") or {}).values() for b in ([v] if isinstance(v, str) else v)} | \
            set((given.get("os") or {}).values()) | \
            {b for v in (given.get("xover_blocks") or {}).values() for b in v.values()}
        check_idents(key, given.get("idents"), band, switches, named, seen_idents)
        for section in NAME_KEYS[:4]:
            ids = set(given.get(section) or {})
            have = set(band["strands"]) if section == "blocks" else switches
            missing = sorted(ids - have)
            if missing:
                what = "track" if section == "blocks" else "switch"
                raise SchematicError(f"names for {key}: {section} names {', '.join(missing)}, which is no {what} "
                                     "of the band")


def check_xover_blocks(key, given, band):
    """Stop on an `xover_blocks` section that is not an object of double crossover id: {A, B, C, D: four different
    block names} (see the module text for why they must differ)."""
    if given is None:
        return
    what = f"names for {key}: xover_blocks"
    if not isinstance(given, dict):
        raise SchematicError(f"{what} must be an object of double crossover id: corner blocks")
    for n, corners in given.items():
        if band["nodes"].get(n, {}).get("kind") != "dx":
            raise SchematicError(f"{what} names {n}, which is no double crossover of the band")
        if not isinstance(corners, dict) or set(corners) != set("ABCD") or \
                not all(isinstance(b, str) and b.strip() for b in corners.values()):
            raise SchematicError(f"{what} {n}: an object of its legs A, B, C and D: block name, not {corners!r}")
        if len(set(corners.values())) != 4:
            raise SchematicError(f"{what} {n}: its four corners share a block ({corners}); JMRI would then route "
                                 "between the two legs on one side, so each corner needs its own block")


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
        if m.get("leg") is not None and (m["leg"] not in MAST_LEGS or m.get("kind") not in (None, "turnout")):
            raise SchematicError(f"{what}: leg must be one of {', '.join(MAST_LEGS)}, on a turnout mast (to tell "
                                 "apart two masts with one facing and protected block, as at a balloon loop's ends)")
        icon = m.get("icon", [1, 1])
        if not (isinstance(icon, (list, tuple)) and len(icon) == 2 and
                all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in icon)):
            raise SchematicError(f"{what}: icon must be [width, height] in pixels, both above zero")


def panel(bands, names=None, cell=CELL, row=ROW, page=None, fit=None, extras=None, gap=BAND_GAP,
          labels_by_band=False, crossover_run=None, tight_crossovers=None, split_crossovers=None, mast_room=None,
          name_room=None, band_bottoms=None, crossover_pairs=None):
    """A Panel from [(title, band, options)], bands stacked top to bottom. The Layout Editor preferences (le_prefs:
    a band's le_shift and le_longer_straights, the page's le_title_clear, a band's le_labels extra_steps and
    extra_follow; and at a given grid a band's le_crossover_angle, le_tight_crossovers, le_split_crossovers,
    le_crossover_pairs, le_mast_room and le_name_room, which give the arguments of those names) are checked first and applied here.
    `page` is the options that set the page (equal_width, band_width, rotate_bands); the last band's by default, as
    the sheet. `fit` (width, height): the
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
    {band key: px} for the bands it names (the others as drawn). None: as drawn. Known limit: a double crossover's
    room (its first pieces less MIN_BLOCK) does not reserve its far switch's leg; strand() stops if that leaves a track
    too short.
    `tight_crossovers`: {band key: [[switch, switch], ...]}: two single crossovers that share a track (one half of
    each on it, say the two crossovers of one three-way switch) drawn as close together on it as their shapes allow:
    that track keeps only its block's least length (MIN_BLOCK, or a facing mast's icon), the rest of their room
    goes to the two crossovers, and each slides toward the other. Needs `crossover_run`.
    `split_crossovers`: {band key: [switch, ...]}: single crossovers drawn as two plain turnouts on their one turnout
    name, joined by their diagonal track, so each track's throat is one point (a JMRI crossover's pieces run a run
    past its diagonal either way). The half on a track shared with a tight partner (tight_crossovers, which must be
    split too), else the top half, stays; the other slides along its row so the diagonal runs `crossover_run` across.
    Two split crossovers drawn tight have their throats on the shared track 2 LEG and the track's least length apart.
    `crossover_pairs`: {band key: [[switch, switch], ...]}: two plain turnouts of different numbers joined by one
    track, its ends on two rows, that are one crossover on the ground: that track, leg to leg, crosses at
    the band's `crossover_run` (its run across per row deep), however many rows apart they stand. The east one, and
    every switch and end at or east of its column (but the west one), slides along the rows by what that takes, in
    the rounds that let in mast and name room (let_in_mast_room); a slide that would turn a track round or make lines
    cross stops. Each pair's angle is logged. Needs `crossover_run`. Not with `fit`.
    `mast_room`: [band key, ...]: on those bands a mast whose straight track before its boundary is shorter than its
    icon needs (2 GAP and the icon's length, as a block's least length), or whose icon has no clean spot there for a
    reason a longer track can clear, gets room: the band is let out along its rows at that track and the panel drawn
    again (let_in_mast_room, mast_track). The track and the lines across that place grow longer; a sloped line through
    a switch's straight leg keeps its slope (its far end moves too), so no switch changes shape. A track that cannot be
    let out that way keeps its length (logged). P.widened holds the px let in by track. Not with `fit`.
    `name_room`: [band key, ...]: in the same rounds, on those bands a named track whose straight is shorter than its
    name's width and NAME_ROOM_PAD is let out the same way by the difference, west to east, while the band stays no
    wider than the widest band (so the panel keeps its width); a track past that is noted and left. Not with `fit`.
    `band_bottoms`: {band key: px}, how far below the band's box (P.band_boxes) the caller's own items under it
    reach, which the page's le_title_clear counts as drawn for that band (P.gaps holds the gaps it settled on)."""
    if not bands:
        raise SchematicError("no band to draw")
    pg = page if page is not None else bands[-1][2]        # the page's options, for the preferences
    le_prefs.check_page(pg, bands)
    bands = le_labels.hide_names(drawn_bands(bands, page), pg)      # a band's le_labels hidden_names: marked
    band_bottoms = le_prefs.check_bottoms(bands, band_bottoms)
    runs = le_prefs.crossover_runs(bands, pg, row)
    if runs and crossover_run is not None:
        raise SchematicError("crossover_run is given and the preferences hold le_crossover_angle: give one of them")
    if runs and fit is None:
        crossover_run = runs
    clear = le_prefs.title_clear(pg)
    unused = [] if fit is None else [p for p, on in (("le_title_clear", clear is not None and len(bands) > 1),
                                                     ("le_crossover_angle", bool(runs))) if on]
    # a band's le_tight_crossovers, le_split_crossovers, le_mast_room and le_name_room: these arguments, at a grid
    given = dict(tight_crossovers=tight_crossovers, split_crossovers=split_crossovers, mast_room=mast_room,
                 name_room=name_room, crossover_pairs=crossover_pairs)
    prefs, held = le_prefs.grid_options(bands, pg)
    if fit is None:             # a fitted panel draws without them (logged), so only here may the two meet
        both = [arg for arg in held if given[arg]]
        if both:
            raise SchematicError(f"{', '.join(both)} given and the preferences hold le_{', le_'.join(both)}: give one "
                                 "of them")
        given.update(prefs)
    else:
        unused += [f"le_{arg}" for arg in prefs]
    tight_crossovers, split_crossovers = given["tight_crossovers"], given["split_crossovers"]
    mast_room, name_room, crossover_pairs = given["mast_room"], given["name_room"], given["crossover_pairs"]
    tight_crossovers = check_tight(bands, tight_crossovers, crossover_run)
    check_mast_room(bands, mast_room)
    check_mast_room(bands, name_room, "name_room")
    split_crossovers = check_split(bands, split_crossovers, tight_crossovers)
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
    if fit is not None and crossover_run is not None:
        raise SchematicError("crossover_run is for a panel drawn at a given grid, not one fitted to a window")
    if fit is not None and (mast_room or name_room):
        raise SchematicError("mast_room and name_room are for a panel drawn at a given grid, not one fitted to a "
                             "window")
    if fit is not None and crossover_pairs:
        raise SchematicError("crossover_pairs is for a panel drawn at a given grid, not one fitted to a window")
    check_pairs(bands, crossover_pairs, crossover_run)
    # with SCHEMATIC_CACHE set, a panel drawn before from the same arguments and the same code is read back
    # (the key leaves out the title block's fields, which no panel draws: a new revision keeps the panels)
    args = dict(bands=bands, names=names, cell=cell, row=row, page=page, fit=fit, extras=extras, gap=gap,
                labels_by_band=labels_by_band, crossover_run=crossover_run, tight_crossovers=tight_crossovers,
                split_crossovers=split_crossovers, mast_room=mast_room, name_room=name_room, band_bottoms=band_bottoms,
                unused=unused, crossover_pairs=crossover_pairs)
    keyed = dict(args, bands=untitled(bands), page=cache.untitled(page))
    return cache.memo("le-panel", ("le",), keyed, lambda: _panel(**args))


def drawn_bands(bands, page=None):
    """The bands as the panel draws them (le_prefs.drawn_bands): each band's le_shift and le_longer_straights applied
    once. `page` as panel's (None: the last band's options)."""
    if not bands:
        raise SchematicError("no band to draw")
    return le_prefs.drawn_bands(bands, page if page is not None else bands[-1][2])


def stretched(scale, page):
    """((across, down), factor): a grid `scale`, say a fit's, widened by the page's le_stretch factor, and the factor
    (le_prefs.stretched)."""
    return le_prefs.stretched(scale, page)


def with_x(extras, xs):
    """`extras` (a list) with each item in `xs` ({id: x}) given that x: to draw a panel's items where another panel
    stepped them (P.extra_x)."""
    return le_prefs.with_x(extras, xs)


def window(page):
    """(width, height) of the page's le_window, the window a caller's panel opens in (le_prefs.window); stops when
    the page has none."""
    return le_prefs.window(page)


def row(page):
    """The page's le_row in px, the rows a caller draws its panel at (le_prefs.row); ROW when not set."""
    return le_prefs.row(page, ROW)


def check_stretch(size, fit, page):
    """Stop unless a panel of `size` has the shape of the `fit` window's panel area (less CHROME) within the page's
    le_stretch tolerance (le_prefs.check_stretch)."""
    le_prefs.check_stretch(size, fit, CHROME, page)


def untitled(bands):
    """The bands for a cache key: each one's options without the title block's fields (cache.TITLE_FIELDS)."""
    return [(t, b, cache.untitled(o)) for t, b, o in bands]


def _panel(bands, names, cell, row, page, fit, extras, gap, labels_by_band, crossover_run, tight_crossovers,
           split_crossovers, mast_room=None, name_room=None, band_bottoms=None, unused=(), crossover_pairs=None):
    """panel, its arguments checked, without the cache: drawn (at the grid, or fitted), then drawn once more with the
    caller's items that step at their x (le_prefs.extra_steps; P.extra_x)."""
    if fit is None:
        draw = grid_drawer(bands, names, cell, row, page, gap, labels_by_band, crossover_run, tight_crossovers,
                           split_crossovers, mast_room, name_room, band_bottoms or {}, crossover_pairs)
    else:
        draw = fit_drawer(bands, names, cell, row, page, fit, gap, labels_by_band, split_crossovers, unused)
    P = draw(extras)
    opts = le_labels.options(bands, page)
    xs = le_prefs.extra_steps(P, opts, extras)
    if xs:
        stepped = le_prefs.with_x(extras, xs)
        P = draw(stepped)
        le_prefs.check_steps(P, opts, stepped, xs)
    P.extra_x = xs
    return P


def grid_drawer(bands, names, cell, row, page, gap, labels_by_band, crossover_run, tight_crossovers,
                split_crossovers, mast_room, name_room, band_bottoms, crossover_pairs=None):
    """draw(extras): the panel at this grid; with the page's le_title_clear, its gaps settled (settle_gaps)."""
    clear = le_prefs.title_clear(page if page is not None else bands[-1][2])

    def draw(extras, gaps=gap):
        return draw_panel(bands, names, cell, row, page, extras=extras, gap=gaps, labels_by_band=labels_by_band,
                          crossover_run=crossover_run, tight_crossovers=tight_crossovers,
                          split_crossovers=split_crossovers, mast_room=mast_room, name_room=name_room,
                          crossover_pairs=crossover_pairs)

    if clear is None or len(bands) < 2:
        return draw
    return lambda extras: settle_gaps(lambda g: draw(extras, g), bands, gap, clear, band_bottoms)


TITLE_ROUNDS = 4        # times the panel is drawn at most for the page's le_title_clear


def title_gap(P, bi, clear, below=None):
    """The gap below band bi of P that puts the next band's title `clear` px below the lowest thing drawn for band bi
    (extent), or `below` px under the band's box (a caller's items under it) when lower; the title stands TITLE_GAP
    less TITLE_DROP px above its band's box. Whole px, rounded up."""
    low = extent(P, bi)[3] - P.band_boxes[bi][3]
    if below is not None:
        low = max(low, below)
    return math.ceil(max(0.0, low) + TITLE_GAP - TITLE_DROP + clear)


def settle_gaps(draw, bands, gap, clear, bottoms):
    """draw(gaps) again until every gap is title_gap of the panel it gives (the first drawing at `gap`); P.gaps
    holds them. Stops when they do not settle in TITLE_ROUNDS drawings."""
    gaps = band_gaps(gap, len(bands))
    tried = []
    for _ in range(TITLE_ROUNDS):
        P = draw(gaps)
        want = [title_gap(P, bi, clear, bottoms.get(band_key(bands[bi][0]))) for bi in range(len(bands) - 1)]
        if want == gaps:
            P.gaps = gaps
            return P
        tried.append(gaps)
        gaps = want
    raise SchematicError(f"le_title_clear: the gaps between bands do not settle in {TITLE_ROUNDS} drawings "
                         f"(tried {tried}, then {gaps})")


def fit_drawer(bands, names, cell, row, page, fit, gap, labels_by_band, split_crossovers, unused=()):
    """draw(extras): the panel fitted to the `fit` window (see the module text); the grid is searched once. `unused`:
    the preferences for a panel at a given grid that this one has (logged)."""
    W, H = fit[0] - CHROME[0], fit[1] - CHROME[1]           # the panel inside the window's frame
    if W <= 0 or H <= 0:
        raise SchematicError(f"a {fit[0]}x{fit[1]} px window leaves no room for a panel inside its frame")
    fits = lambda Q: Q.size[0] <= W and Q.size[1] <= H      # noqa: E731

    def search(masts):
        draw = lambda kx, ky: draw_panel(bands, names, cell * kx, row * ky, page, masts, labels=False,  # noqa: E731
                                         gap=gap, split_crossovers=split_crossovers)
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
    # The grid it settles on depends on neither the label layer's inputs (extras, labels_by_band) nor what it
    # places, so it is kept apart from the panel (SCHEMATIC_CACHE): a change to those alone draws the panel once
    draw = lambda kx, ky: draw_panel(bands, names, cell * kx, row * ky, page, labels=False, gap=gap,  # noqa: E731
                                     split_crossovers=split_crossovers)
    drawn = {}

    def settle():
        kx, ky = search(False)
        P = draw(kx, ky)
        if not fits(P):
            kx, ky = search(True)
            P = draw(kx, ky)
        drawn[kx, ky] = P
        return kx, ky, fits(P)

    kx, ky, fitted = cache.memo("le-fit", ("le",), dict(bands=untitled(bands), names=names, cell=cell, row=row,
                                                           page=cache.untitled(page), fit=fit, gap=gap,
                                                           split_crossovers=split_crossovers), settle)
    def finish(extras):
        P = drawn.pop((kx, ky), None)
        if P is None:           # a kept grid, or a second drawing: drawn at it, it must fit (or not) as when searched
            P = draw(kx, ky)
            if fits(P) != fitted:
                raise SchematicError(f"the kept fit grid ({kx:g}, {ky:g}) gives a {P.size[0]}x{P.size[1]} px panel "
                                     f"for a {fit[0]}x{fit[1]} px window, not as when it was searched; clear the "
                                     f"cache folder ({cache.ENV})")
        label_layer(P, bands, page, extras, labels_by_band)
        P.scale, P.fit = (kx, ky), tuple(fit)
        for pref in unused:
            P.log.append(f"{pref} is for a panel drawn at a given grid: this one is fitted to a window, so it is not "
                         "used")
        return P

    return finish


def check_tight(bands, tight, crossover_run):
    """{band key: [(label, label)]} of panel's `tight_crossovers` (None: {}), checked: band keys of the bands drawn,
    each pair two labels of single crossovers of that band (two switches of one number joined C to C)."""
    if tight is None or tight == {}:
        return {}
    if crossover_run is None:
        raise SchematicError("tight_crossovers needs crossover_run (the run their diagonals are drawn at; or the "
                             "band's le_crossover_angle)")
    if not isinstance(tight, dict):
        raise SchematicError(f"tight_crossovers must be {{band key: [[switch, switch], ...]}}, not {tight!r}")
    keys = {band_key(t): band for t, band, _o in bands}
    out = {}
    for key, pairs in tight.items():
        if key not in keys:
            raise SchematicError(f"tight_crossovers names {key}, which is no band (bands: {', '.join(keys)})")
        labels = {keys[key]["nodes"][u].get("label") for _sid, u, _v in crossover_pairs(keys[key])}
        got = []
        for pair in pairs if isinstance(pairs, (list, tuple)) else [pairs]:
            if not (isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[0] != pair[1]
                    and all(isinstance(x, str) for x in pair)):
                raise SchematicError(f"tight_crossovers for {key}: {pair!r} is not two switch numbers")
            stray = [x for x in pair if x not in labels]
            if stray:
                raise SchematicError(f"tight_crossovers for {key}: switch {', '.join(stray)} is no single crossover "
                                     "of that band")
            got.append(tuple(pair))
        out[key] = got
    return out


def check_split(bands, split, tight):
    """{band key: set(label)} of panel's `split_crossovers` (None: {}), checked: band keys of the bands drawn, each a
    label of a single crossover of that band; a tight pair (`tight`, checked) is split both or neither."""
    if not split:
        return {}
    if not isinstance(split, dict):
        raise SchematicError(f"split_crossovers must be {{band key: [switch, ...]}}, not {split!r}")
    keys = {band_key(t): band for t, band, _o in bands}
    out = {}
    for key, labels in split.items():
        if key not in keys:
            raise SchematicError(f"split_crossovers names {key}, which is no band (bands: {', '.join(keys)})")
        if not isinstance(labels, (list, tuple, set)) or not all(isinstance(x, str) for x in labels):
            raise SchematicError(f"split_crossovers for {key}: {labels!r} is not a list of switch numbers")
        have = {keys[key]["nodes"][u].get("label") for _sid, u, _v in crossover_pairs(keys[key])}
        stray = sorted(set(labels) - have)
        if stray:
            raise SchematicError(f"split_crossovers for {key}: switch {', '.join(stray)} is no single crossover of "
                                 "that band")
        out[key] = set(labels)
    for key, pairs in tight.items():
        for pair in pairs:
            if len(set(pair) & out.get(key, set())) == 1:
                raise SchematicError(f"split_crossovers for {key}: crossovers {pair[0]} and {pair[1]} are drawn tight, "
                                     "so both or neither are split")
    return out


def check_pairs(bands, pairs, crossover_run):
    """[(band index, node, node, track id, "a/b", run)] of panel's `crossover_pairs` (None: []), `run` the band's
    crossover run (px across per `row` deep), as given,
    checked: band keys of the bands drawn, each pair two different switch numbers of that band, each number one plain
    switch (no half of a single crossover), joined by exactly one track (pair_shortfall stops when its two ends are
    drawn on one row); no switch in two pairs; the band has a crossover run (crossover_run, or its le_crossover_angle)."""
    if not pairs:
        return []
    if not isinstance(pairs, dict):
        raise SchematicError(f"crossover_pairs must be {{band key: [[switch, switch], ...]}}, not {pairs!r}")
    keys = {band_key(t): (bi, band) for bi, (t, band, _o) in enumerate(bands)}
    out = []
    for key, given in pairs.items():
        if key not in keys:
            raise SchematicError(f"crossover_pairs names {key}, which is no band (bands: {', '.join(keys)})")
        bi, band = keys[key]
        run = crossover_run.get(key) if isinstance(crossover_run, dict) else crossover_run
        if run is None:
            raise SchematicError(f"crossover_pairs for {key} needs crossover_run (the run their diagonal is drawn "
                                 "at; or the band's le_crossover_angle)")
        if not isinstance(given, (list, tuple)) or not all(
                isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(x, str) for x in p) and p[0] != p[1]
                for p in given):
            raise SchematicError(f"crossover_pairs for {key}: {given!r} is not a list of [switch, switch] pairs of "
                                 "two different switch numbers")
        halves = {n for _sid, u, v in crossover_pairs(band) for n in (u, v)}
        nodes, seen = band["nodes"], set()
        for a, b in given:
            what = f"crossover_pairs for {key}: switches {a} and {b}"
            if {a, b} & seen:
                raise SchematicError(f"{what}: switch {', '.join(sorted({a, b} & seen))} is in another pair too")
            seen |= {a, b}
            of = {}
            for label in (a, b):
                found = [n for n, d in nodes.items() if d.get("kind") == "switch" and d.get("label") == label]
                if len(found) != 1 or found[0] in halves:
                    raise SchematicError(f"{what}: switch {label} is "
                                         + ("half of a single crossover (its own crossover angle draws it)"
                                            if found and found[0] in halves else
                                            f"drawn as {len(found)} switches on the band, not one plain switch"))
                of[label] = found[0]
            u, v = of[a], of[b]
            joined = [sid for sid, s in band["strands"].items() if {s["src"][0], s["dst"][0]} == {u, v}]
            if len(joined) != 1:
                raise SchematicError(f"{what}: {len(joined)} tracks join them, not one")
            out.append((bi, u, v, joined[0], f"{a}/{b}", run))
    return out


def draw_panel(bands, names, cell, row, page, masts=True, labels=True, extras=None, gap=BAND_GAP,
               labels_by_band=False, crossover_run=None, tight_crossovers=None, split_crossovers=None,
               mast_room=None, name_room=None, crossover_pairs=None):
    """The panel drawn at this grid (see panel). Every message it keeps or stops with names objects by their written
    idents (Panel.text). `labels`: then run the label layer (label_layer). `page` as given: the drawing takes the
    last band's options when it is None (_draw), the labels take none (le_labels.options), so a band's le_labels
    never reach another band, with or without `fit`."""
    if bands:
        le_labels.options(bands, page)      # checked before any drawing (page None: no page-wide label options)
        bands = le_labels.hide_names(bands, page)       # hidden_names marked (once: le.panel may have marked them)
    le_labels.check_extras(extras)
    mast_room = check_mast_room(bands, mast_room)
    name_room = check_mast_room(bands, name_room, "name_room")
    pairs = check_pairs(bands, crossover_pairs, crossover_run)

    def drawn(widen):
        P = Panel()
        P.crossover_run = crossover_run
        P.tight_crossovers = check_tight(bands, tight_crossovers, crossover_run)
        P.split_crossovers = check_split(bands, split_crossovers, P.tight_crossovers)
        try:
            _draw(P, bands, names, cell, row, page, masts, gap, widen)
        except SchematicError as e:
            raise SchematicError(P.text(str(e))) from None
        return P

    P = drawn({})
    if pairs or (masts and (mast_room or name_room)):
        P = let_in_mast_room(P, bands, mast_room if masts else [], drawn, name_room if masts else [],
                             [(bi, u, v, sid, name, run / row) for bi, u, v, sid, name, run in pairs])
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


MAST_ROOM_ROUNDS = 4    # times the panel is drawn again for mast_room, at most
MAST_ROOM_SPARE = 1.0   # px let in past a mast's shortfall, for the icon's whole-pixel place


def check_mast_room(bands, mast_room, what="mast_room"):
    """`mast_room` (or `what`: name_room) checked: a list of band keys, each a band drawn; [] when None."""
    if mast_room is None:
        return []
    keys = [band_key(t) for t, _b, _o in bands]
    if not isinstance(mast_room, (list, tuple)) or not all(isinstance(k, str) for k in mast_room):
        raise SchematicError(f"{what} must be a list of band keys, not {mast_room!r}")
    stray = sorted(set(mast_room) - set(keys))
    if stray:
        raise SchematicError(f"{what} names {', '.join(stray)}, which is no band (bands: {', '.join(keys)})")
    return list(mast_room)


def level_pieces(line):
    """[(column, column)] of a drawn line's level pieces (grid units), in its order."""
    return [(a[0], b[0]) for a, b in zip(line, line[1:]) if abs(a[1] - b[1]) < EPS and abs(a[0] - b[0]) > EPS]


MAST_ROOM_STEP = 4      # px let in at a time for an icon whose straight is long enough but still not clean
MAST_ROOM_MAX = 2       # columns of room let in at most for one track
MAST_ROOM_STALL = 3     # steps with no cheaper icon spot after which a track gets no more (back to its best)
GEOMETRY = {"ink", "turnout", "other", "graze"}     # what a longer track can clear from an icon spot (le_masts)


PAIR_TOLERANCE = 0.25   # px a crossover pair's diagonal may run off its crossover run across (whole-pixel rounding)


def pair_shortfall(P, bands, bi, u, v, sid, slope, name):
    """(px the track `sid` between crossover pair u, v runs short of `slope` px across per px deep, from the leg it
    leaves one switch by to the leg it reaches the other by, negative when it runs further; the east node; its angle
    in degrees) as P draws it. Stops when its two ends are drawn on one row."""
    s = bands[bi][1]["strands"][sid]

    def leg(n):
        ident, legs = P.turnout_of[(bi, n)]
        port = s["src"][1] if s["src"][0] == n else s["dst"][1]
        t = next(x for x in P.turnouts if x["ident"] == ident)
        return t["pts"][legs[port]]
    (ux, uy), (vx, vy) = leg(u), leg(v)
    deep = abs(vy - uy)
    if deep < EPS:
        raise SchematicError(f"crossover pair {name}: the track between them is drawn on one row, so there is no "
                             "diagonal to set")
    across = abs(vx - ux)
    return deep * slope - across, (v if vx >= ux else u), math.degrees(math.atan2(deep, across))


def pair_nodes(band, west, east):
    """The nodes a crossover pair's east switch slides with: itself and every switch and end at or east of its
    column, but its west partner, turnbacks (as le_shift) and whatever stands at the band's east edge, so the band
    keeps its width (a narrower band would be stretched back to the widest band's, moving everything west of the
    pair too) and the tracks into that edge take up the slide."""
    x = band["x"]
    edge = max(x.values())
    return [n for n in x if n != west and x[n] >= x[east] - EPS and x[n] < edge - EPS
            and not le_prefs.is_turnback(band, n)]


def let_in_mast_room(P, bands, keys, drawn, name_keys=(), pairs=()):
    """The panel drawn again with room let in for mast icons on the `keys` bands (panel's mast_room) and for track
    names on the `name_keys` bands (name_room), until it settles. First each mast whose straight is too short gets its
    shortfall and MAST_ROOM_SPARE; then a mast whose icon still has no clean spot for a reason a longer track can clear
    (GEOMETRY: track or a turnout through it, or nearer another track) gets MAST_ROOM_STEP px more at a time while its
    cheapest spot gets cheaper, up to MAST_ROOM_MAX columns; a track whose last steps (MAST_ROOM_STALL) bought nothing
    goes back to its best. Each track is let out where mast_track finds it may be. In the same rounds a named track
    whose straight is shorter than its name and a STEP gets the difference (name_room_wanted), while its band stays
    no wider than the widest band. In the same rounds each crossover pair (`pairs`: [(band index, node, node, track
    id, name, px across per px deep)], le.panel's crossover_pairs) has its east switch and everything at or east of
    it slid along the rows by what its diagonal runs short or long (pair_shortfall, pair_nodes). P.widened, and the
    log, hold what was let in (a pair's track: negative px, drawn shorter); P.pair_angles {name: degrees}."""
    grow, moved, notes = {}, {}, []
    why_grown = defaultdict(set)        # (band index, strand id) -> "its mast icons", "its name"
    named = defaultdict(int)            # (band index, strand id) -> rounds it was let out for its name
    best = {}                   # (band index, strand id) -> (cost, px) of its unclean mast's cheapest spot
    stalls = defaultdict(int)
    done = set()
    for _ in range(MAST_ROOM_ROUNDS + int(MAST_ROOM_MAX * max(P.cellx.values()) / MAST_ROOM_STEP) + 1):
        want = {}
        for m in P.masts:
            st = P.mast_straights.get(m["mast"])
            if st is None or band_key(bands[st["band"]][0]) not in keys:
                continue
            short = st["need"] - st["run"]
            unclean = GEOMETRY & set(m["spot"][2])
            if short <= EPS and not unclean:
                continue
            got = mast_track(P, bands, m, st, notes)
            if got is None:
                continue
            k, nodes = got
            if k in done:
                continue
            moved[k] = nodes
            cap = MAST_ROOM_MAX * P.cellx[k[0]]
            if short > EPS:
                want[k] = max(want.get(k, 0.0), short + MAST_ROOM_SPARE)
                why_grown[k].add("its mast icons")
                continue
            cost = icon_cost(m)
            was = best.get(k)
            if was is None or cost < was[0] - EPS:
                best[k], stalls[k] = (cost, grow.get(k, 0.0)), 0
            else:
                stalls[k] += 1
            if stalls[k] >= MAST_ROOM_STALL or grow.get(k, 0.0) + MAST_ROOM_STEP > cap + EPS:
                done.add(k)
                if best[k][1] != grow.get(k, 0.0):
                    want[k] = best[k][1] - grow.get(k, 0.0)        # back to its best
                notes.append(f"{bands[k[0]][0]}: mast {m['mast']}: no clean icon spot after "
                             f"{grow.get(k, 0.0):.1f} px let in; its track keeps {best[k][1]:.1f} px")
                continue
            want[k] = max(want.get(k, 0.0), MAST_ROOM_STEP)
            why_grown[k].add("its mast icons")
        for k, (px, nodes) in name_room_wanted(P, bands, name_keys, want, moved, notes).items():
            if named[k] >= NAME_ROOM_ROUNDS:     # once: its straight may be measured on another piece
                continue
            named[k] += 1
            moved.setdefault(k, nodes)
            want[k] = max(want.get(k, 0.0), px)
            why_grown[k].add("its name")
        for bi, u, v, sid, name, slope in pairs:
            short, east, _deg = pair_shortfall(P, bands, bi, u, v, sid, slope, name)
            if abs(short) <= PAIR_TOLERANCE:
                continue
            k = (bi, sid)
            moved[k] = pair_nodes(bands[bi][1], u if east == v else v, east)
            want[k] = want.get(k, 0.0) + short
            why_grown[k].add(f"crossover pair {name}'s angle")
        if not want:
            break
        trial = dict(grow)
        for k, px in want.items():
            trial[k] = trial.get(k, 0.0) + px
        for bi in {k[0] for k in want}:         # together, as each was checked alone
            why = let_out_fault(bands[bi][1], shifts_of(trial, moved, P.cellx, bi))
            if why:
                raise SchematicError(f"{bands[bi][0]}: mast_room: the room let in for several masts (and crossover "
                                     f"pairs) together: {why}")
        grow = trial
        P = drawn(grow_shifts(grow, moved, P.cellx))
    else:
        raise SchematicError(P.text("mast_room: the room for the mast icons and crossover pairs does not settle"))
    P.widened = {k: round(px, 1) for k, px in sorted(grow.items()) if abs(px) > EPS}
    for (bi, sid), px in P.widened.items():
        s = bands[bi][1]["strands"][sid]
        where = "its east switch and everything east of it slid" if any(
            (b, t) == (bi, sid) for b, _u, _v, t, _n, _s in pairs) else "the band let out east of its middle"
        notes.append(f"{bands[bi][0]}: track {s.get('name') or sid}: drawn {abs(px):.1f} px "
                     f"{'longer' if px > 0 else 'shorter'} for {' and '.join(sorted(why_grown[(bi, sid)]))} "
                     f"({where}, {len(moved[(bi, sid)])} switches and ends moved)")
    P.pair_angles = {}
    for bi, u, v, sid, name, slope in pairs:
        short, _east, deg = pair_shortfall(P, bands, bi, u, v, sid, slope, name)
        if abs(short) > PAIR_TOLERANCE:         # the loop settled, so this is a fault of the code
            raise SchematicError(P.text(f"crossover pair {name}: its diagonal runs {-short:+.2f} px off its crossover "
                                        "run after the rounds settled"))
        P.pair_angles[name] = round(deg, 1)
        notes.append(f"{bands[bi][0]}: crossover pair {name}: its diagonal crosses at {deg:.1f} degrees")
    P.log += list(dict.fromkeys(notes))         # each noted once
    return P


NAME_ROOM_PAD = 8       # px of straight a named track keeps past its name's width (le_labels.STEP)
NAME_ROOM_ROUNDS = 1    # rounds a track is let out for its name, at most


def name_room_wanted(P, bands, keys, want, moved, notes):
    """{(band index, strand id): (px, nodes)}: on the `keys` bands, each named track whose longest straight (its
    level, unhidden, uncurved segments in a row) is shorter than its name's width and NAME_ROOM_PAD, by how much, and
    the nodes that move to let it out at the middle of its longest level piece (let_out_at), in the order the band
    draws them west to east, while what the band is let out (with `want`, this round's room for masts) leaves it no
    wider than the widest band. A track the drawing keeps no name room for (P.no_name), one that cannot be let out,
    or one past the band's spare width is noted and left."""
    if not keys:
        return {}
    from . import jmri_text
    from .le_masts import PanelView
    view = PanelView(P)
    segs = {sg["ident"]: sg for sg in P.segments}
    widest = max(b[2] - b[0] for b in P.band_boxes)
    out = {}
    for bi, (title, band, _opts) in enumerate(bands):
        if band_key(title) not in keys:
            continue
        spare = widest - (P.band_boxes[bi][2] - P.band_boxes[bi][0]) - \
            sum(px for (b, _sid), px in want.items() if b == bi)
        named = []
        for (b, sid), idents in P.strand_segments.items():
            st = band["strands"][sid] if b == bi else None
            if st is None or not st.get("name") or st.get(le_labels.HIDDEN) or (bi, sid) in P.no_name:
                continue
            run = best = 0.0
            for i in idents:            # the longest run of level straight segments, end to end
                sg = segs[i]
                a, c = (view.xy(e) for e in sg["ends"])
                if sg["arc"] or sg["hidden"] or abs(a[1] - c[1]) > EPS:
                    run = 0.0
                    continue
                run += abs(c[0] - a[0])
                best = max(best, run)
            need = jmri_text.width(tidy([st["name"]])[0], LABEL_SIZE) + NAME_ROOM_PAD
            if best < need - EPS:
                x = min(view.xy(e)[0] for i in idents for e in segs[i]["ends"])
                named.append((x, sid, tidy([st["name"]])[0], need - best))
        no_room = []
        for _x, sid, name, px in sorted(named):
            pieces = level_pieces(paths(band)[sid])
            if not pieces:
                continue
            if px > spare + EPS:
                no_room.append(name)
                continue
            nodes, why = (moved[(bi, sid)], None) if (bi, sid) in moved else \
                let_out_at(P, bi, band, sid, max(pieces, key=lambda pc: abs(pc[1] - pc[0])))
            if why:
                notes.append(f"{title}: track {name}: not let out for its name ({why}; name_room leaves it)")
                continue
            spare -= px
            out[(bi, sid)] = (px, nodes)
        if no_room:
            notes.append(f"{title}: tracks {', '.join(sorted(no_room))}: not let out for their names (the band "
                         "would be wider than the widest band; name_room leaves them)")
    return out


def icon_cost(m):
    """The cost le_masts gave a mast's spot, from its reasons (le_masts.ICON_COST)."""
    from .le_masts import ICON_COST
    return sum(ICON_COST[w] for w in m["spot"][2])


def grow_shifts(grow, moved, cellx):
    """{band index: {node: columns}} from the px let in per track and the nodes each moves."""
    out = {}
    for bi in {k[0] for k in grow}:
        out[bi] = shifts_of(grow, moved, cellx, bi)
    return out


def shifts_of(grow, moved, cellx, bi):
    got = defaultdict(float)
    for k, px in grow.items():
        if k[0] == bi:
            for n in moved[k]:
                got[n] += px / cellx[bi]
    return dict(got)


def mast_track(P, bands, m, st, notes):
    """((band index, strand id), nodes to move) for a mast's track that room may be let into, or None (noted): the
    strand of the segment before its boundary, level where it leaves the mast's turnout, split at the middle of that
    level piece: the nodes east of it move, and with them every node a rigid diagonal joins to one that moves
    (rigid_diagonals: it keeps its slope, so its switches keep their through legs straight; a diagonal that is a plain
    switch's diverging leg at each end lies a little flatter instead). None when the track's west end would move too,
    or when the move would turn a track round, leave one too short for its climbs, or make lines cross or lie on each
    other that did not (let_out_fault, tried at one column)."""
    bi = st["band"]
    title, band, _opts = bands[bi]
    key = next((k for k, segs in P.strand_segments.items() if st["seg"] in segs), None)
    if key is None:
        notes.append(f"{title}: mast {m['mast']}: its track is no drawn strand (mast_room leaves it)")
        return None
    sid = key[1]
    s = band["strands"][sid]
    name = s.get("name") or sid
    line = paths(band)[sid]
    pieces = level_pieces(line)
    mine = {n for (b, n), (ident, _l) in P.turnout_of.items() if b == bi and ident == st["ident"]} \
        if st["kind"] == "turnout" else set()
    at_src, at_dst = s["src"][0] in mine, s["dst"][0] in mine
    # at a turnout's leg the track must leave it level, or no room let in reaches the mast's straight
    if not pieces or (at_src and pieces[0][0] != line[0][0]) or (at_dst and pieces[-1][1] != line[-1][0]):
        notes.append(f"{title}: mast {m['mast']}: its track {name} leaves no level piece at the mast to let room "
                     "into (mast_room leaves it)")
        return None
    piece = pieces[0] if at_src and not at_dst else pieces[-1] if at_dst and not at_src else \
        max(pieces, key=lambda pc: abs(pc[1] - pc[0]))
    nodes, why = let_out_at(P, bi, band, sid, piece)
    if why:
        notes.append(f"{title}: mast {m['mast']}: its track {name} is not let out ({why}; mast_room leaves it)")
        return None
    return key, nodes


def let_out_at(P, bi, band, sid, piece):
    """(nodes to move, None) to let a track out at the middle of its level `piece` (columns): the nodes east of it,
    and every node a rigid diagonal joins to one that moves (rigid_diagonals); (None, why) when the track's west end
    would move too, or when the move would turn a track round, leave one too short for its climbs, or make lines
    cross or lie on each other that did not (let_out_fault, tried at one column)."""
    s = band["strands"][sid]
    nodes = moved_east(band, (piece[0] + piece[1]) / 2, rigid_diagonals(P, bi, band))
    ends = sorted((s["src"][0], s["dst"][0]), key=lambda n: band["x"][n])
    if ends[0] in nodes or ends[1] not in nodes:
        return None, "a rigid diagonal line ties its west end to the nodes east of it"
    why = let_out_fault(band, {n: 1.0 for n in nodes})
    return (None, why) if why else (nodes, None)


def rigid_diagonals(P, bi, band):
    """The band's sloped lines that must keep their slope: the diagonals (layout.paths draws them node to node) and the
    tracks that climb their whole way (no level piece; let out, one would gain a level piece and its switches change
    which leg is straight), every one but those that are a plain switch's diverging leg (Layout Editor leg C) or a
    track end at both their ends."""
    types = {t["ident"]: t["type"] for t in P.turnouts}
    drawn = paths(band)
    sloped = set(band["R"]["diag"]) | {sid for sid, line in drawn.items() if sid in band["strands"] and
                                       len(line) > 1 and not level_pieces(line)}
    out = set()
    for sid in sorted(sloped):
        st = band["strands"].get(sid)
        if st is None:
            continue
        for n, port in (st["src"], st["dst"]):
            got = P.turnout_of.get((bi, n))
            if got and not (types.get(got[0]) in ("RH_TURNOUT", "LH_TURNOUT") and got[1].get(port) == "C"):
                out.add(sid)
    return out


def moved_east(band, col, rigid):
    """The nodes east of column `col`, and every node a `rigid` diagonal line joins to one of them (the closure)."""
    x = band["x"]
    moved = {n for n in x if x[n] > col + EPS}
    diag = [(band["strands"][sid]["src"][0], band["strands"][sid]["dst"][0]) for sid in rigid]
    grown = True
    while grown:
        grown = False
        for u, v in diag:
            if (u in moved) != (v in moved):
                moved |= {u, v}
                grown = True
    return moved


def let_out_fault(band, shifts):
    """Why moving these nodes east ({node: columns}) would spoil the band's drawing, or None: a track turned round
    or too short for its climbs, or lines that cross or lie on each other and did not before (layout.faults)."""
    from .layout import faults
    after = let_out(band, shifts)
    x0, x1 = band["x"], after["x"]
    for sid, st in band["strands"].items():
        u, v = st["src"][0], st["dst"][0]
        if u not in x0 or v not in x0:
            continue
        old, new = x0[v] - x0[u], x1[v] - x1[u]
        if old * new < -EPS or (abs(old) > EPS) != (abs(new) > EPS):
            return f"track {st.get('name') or sid} would be turned round"
        if sid not in band["R"]["diag"]:
            su, sv = band["need"][sid][:2]
            if abs(new) < su + sv - EPS:
                return f"track {st.get('name') or sid} would be too short for its climbs"
    seen = lambda f: (f[0], f[1], f[3])     # noqa: E731
    before = {seen(f) for f in faults(band)}
    new = sorted({seen(f) for f in faults(after)} - before)
    if new:
        return f"lines {new[0][1]} and {new[0][2]} would {'cross' if new[0][0] == 'cross' else 'lie on each other'}"
    return None


def let_out(band, shifts):
    """The band with each node in `shifts` ({node: columns}) moved that many columns east (a copy; as given when
    there are none)."""
    if not shifts:
        return band
    return dict(band, x={n: x + shifts.get(n, 0.0) for n, x in band["x"].items()})


def _draw(P, bands, names, cell, row, page, masts, gap=BAND_GAP, widen=None):
    if not bands:
        raise SchematicError("no band to draw")
    gaps = band_gaps(gap, len(bands))
    page = page if page is not None else bands[-1][2]
    names = names or {}
    check_names(bands, names)
    align = check_band_align(bands, page)
    shared = plan_shared(P, bands, names, page)
    unjoined = {bi for bi, (t, _b, _o) in enumerate(bands) if names.get(band_key(t), {}).get("joins") == "none"}
    pairs = partners(bands)
    for (bi, _n), (bj, _m) in sorted(pairs.items()):
        if bi in unjoined and bj not in unjoined and names.get(band_key(bands[bj][0]), {}).get("joins") == "other":
            raise SchematicError(f"{bands[bi][0]} draws its ends unjoined (joins \"none\") but {bands[bj][0]} asks "
                                 "for the other band's block on their joins (joins \"other\"): there is no join; set "
                                 "both to \"none\", or neither")
    joined = {a: b for a, b in pairs.items() if a[0] not in unjoined and b[0] not in unjoined}
    given = {b for g in names.values() for v in (g.get("blocks") or {}).values()
             for b in ([v] if isinstance(v, str) else v)} | \
        {b for g in names.values() for b in (g.get("os") or {}).values()} | \
        {b for g in names.values() for v in (g.get("xover_blocks") or {}).values() for b in v.values()}
    os_defaults = {f"OS {d.get('label') or n}" for _, band, _ in bands for n, d in band["nodes"].items()
                   if d["kind"] in ("switch", "dx")}
    # a helix or connector track keeps one default block name on both bands even when drawn unjoined (joins none)
    defaults = default_names(bands, pairs, given | os_defaults)
    # mast_room: a band let out along its rows (let_in_mast_room)
    drawn = [paths(let_out(band, (widen or {}).get(bi, {}))) for bi, (_, band, _) in enumerate(bands)]
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
        P.label(title.upper(), (MARGIN, top - TITLE_GAP + TITLE_DROP), TITLE_SIZE, True, anchor="left", kind="title")
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


def check_band_align(bands, page):
    """The page's `band_align`, checked: {band key: "left", "centre" or "right"}, each a band the page knows (one not
    drawn now is allowed and ignored)."""
    align = page.get("band_align") or {}
    known = le_prefs.known_bands(bands, page)
    if not isinstance(align, dict):
        raise SchematicError(f"band_align must be an object of band: \"left\", \"centre\" or \"right\", not {align!r}")
    bad = sorted(f"{k} (no band; bands: {', '.join(known)})" for k in align if k not in known) + \
        sorted(f"{k}: {v!r}" for k, v in align.items() if v not in ("left", "centre", "right"))
    if bad:
        raise SchematicError(f"band_align must be an object of band: \"left\", \"centre\" or \"right\": "
                             f"{', '.join(bad)}")
    return align


class NoRoom(SchematicError):
    """A crossover with no room for the shape JMRI draws: it is drawn as two turnouts instead (logged)."""


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
    undrawn = [k for k in le_prefs.known_bands(bands, page) if k not in {band_key(t) for t, _, _ in bands}]
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
    two turnouts, when its switches are not on two level tracks, would not be), one more for a crossover with no room
    for JMRI's shape, which is drawn as two turnouts on its one turnout on purpose (P.split_names, logged)."""
    drawn = defaultdict(int)
    for t in P.turnouts:
        if t["name"]:
            drawn[t["name"]] += 1
    # a crossover with no room for JMRI's shape is drawn as two turnouts on its one name (logged by Band)
    want = {n: c + (1 if n in P.split_names else 0) for n, c in planned.items()}
    bad = sorted(n for n in set(drawn) | set(want) if drawn.get(n, 0) != want.get(n, 0))
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
    by_ident = {t["ident"]: t for t in P.turnouts}      # the probe holds generated idents, as `mine` below

    def on_leg(c, leg):
        """Whether candidate c is the turnout leg (B or C) its turnout's continuing route makes `leg`."""
        t = by_ident.get(c[1])
        if c[0] != "turnout" or t is None or c[2] not in ("B", "C"):
            return False
        normal = "B" if t["continuing"] == "2" else "C"
        return (c[2] == normal) == (leg == "normal")

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
            if m.get("leg"):            # one of two masts with this facing and protected block: by the leg it is on
                xover = sorted(P.name(c[1]) for c in cands if c[0] == "turnout" and c[1] in by_ident
                               and "XOVER" in by_ident[c[1]]["type"])
                if xover:
                    raise SchematicError(f"{title}: mast {m['mast']}: leg is for a plain turnout's B or C leg; its "
                                         f"slot is on crossover {', '.join(xover)}, whose legs A to D have no "
                                         "normal or diverging leg (leave leg out)")
                other += [c for c in cands if not on_leg(c, m["leg"])]
                cands = [c for c in cands if on_leg(c, m["leg"])]
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
                elif other and m.get("leg"):
                    why = (f"no {m['leg']} turnout leg faces {m['facing']} and protects {list(protects)} (slots: "
                           f"{', '.join(f'{c[1]} {c[2]}' for c in other)})")
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


# The band geometry and the XML writing live in their own modules (split out of this one, unchanged); they
# import this module's names, so they are imported last and their names re-exported here (le.Band, le.to_xml).
from .le_band import Band, piece_len, rounded, split  # noqa: E402,F401
from .le_xml import CLASS, EDITOR, FONT, LEX, OPTIONS, summary, to_xml, write  # noqa: E402,F401
