"""The labels of a generated Layout Editor panel: switch numbers, track names, block contents icons and station names,
each in the first clean spot near what it names, sized as JMRI draws it.

    opts = le_labels.options(bands, page)       # le.draw_panel, before any drawing: checked, one dict per band
    bands = le_labels.hide_names(bands, page)   # le.panel and draw_panel, first: a band's hidden_names marked
    le_labels.place(P, bands, opts)             # le.label_layer, last: the grid settled, every mast icon placed

The drawing (le) keeps room for switch numbers, track names and station names at fixed offsets; that room is part
of the approved geometry (band places, panel size, mast icon spots), so the drawing keeps it, and place drops those
room labels and places the real ones. It changes nothing else: le.label_layer stops if any track, turnout, point,
shape, mast icon or the panel's size differs afterwards. Items, placed in this order, each against everything placed
before it (and the mast icons, band titles, helix and connector labels and circles, which stay where they are):
  switch numbers   one per turnout: the switch's label (a single crossover's: its crossover number, once), with
                   `switch_prefix` before it, around where its legs meet
                   (first on the side away from its diverging leg); a plain turnout's also in its frog and stacked
                   past a mast icon or label that stands by it
  track names      one per named track, beside its track, as near the track's middle as is clean
  block contents   with `block_contents` (on by default), one BlockContentsIcon per block on the panel, which shows
                   the train in the block: a track block's beside its own track (first on the side its track's name
                   did not take), or, only when no spot beside it is clean, on its own block's track (the box's
                   middle on the rail, its own block's lines then no obstacle; logged); an OS block's around its
                   turnout, clear of the control circle (a single crossover's two OS blocks each around their own
                   half). An icon with no clean spot for its full reserve, beside or on its track, tries them all
                   again with the `block_contents_short` reserve (logged). Names and switch numbers have no
                   fallback.
  caller's items  `extras` (le.panel(..., extras=[{"id", "block", "size": [w, h]}]), checked up front: unique ids,
                   blocks the panel draws), each placed by its block as a block contents icon is (beside its track,
                   on it at last; no shorter size), before the icons; P.extras holds them. No XML is written for
                   them: the caller writes its own elements there
  station names    the `stations` preference, under the band or over it for side "top", centred on their switches

Sizes. A label's box is the one JMRI gives it (PositionableLabel: FontMetrics stringWidth x getHeight), its stored
whole-pixel x, y the top left: jmri_text holds the Dialog font's sizes, and every label is written in Dialog so the
table is the font JMRI draws. A block contents icon is empty until a train is in its block, so its box is reserved
for `block_contents_text` at `block_contents_size`: by default "OCS-1234" at 13 plain, eight characters of a
typical train name (three letters, a dash, four digits; 68 px), so a name of that length never covers its
neighbours. Only an icon with no clean spot at that size (beside or on its track) is tried again, the same way, at
`block_contents_short` ("OCS-1" by default: five characters, 44 px), which must be narrower, once every other item
stands. It is written with no background: JMRI 5.16 (MemoryIcon.displayState) shows the block's value as text, and
its default icon (a small red X) while the block has none; a background would paint the whole box even then, over
the rail for one standing on its track.

Spots. Each item tries spots in ranked order and takes the first clean one. Around a turnout: above and below it
(centred, then a quarter and half a box either way), then left and right of it, AROUND px out, nearest first. A
plain turnout's switch number (not a crossover's) tries two more kinds after those of each distance, ranked by the
same distance (the box's gap from where the legs meet, or from the leg it stands against): in its frog, the wedge
between its two legs past where they meet, the box against either leg FROG_GAPS px off it and FROG_ALONG px along
it; then stacked past a mast icon or label that stands above or below the turnout in the column the number would
take, PAD px further out than it (centred on the turnout, shifted as above, or over the obstacle), first on the
side tried first. Both are judged as any spot: a frog spot over the other leg, or nearer another turnout, is not
clean.
Beside a track: above and below it, then left and right of it, GAPS px from its line, from the middle of its length
outward STEP px at a time, the box centred on the spot or reaching on from it either way (a curve or a short track
takes whatever part is clean); only when none of those is clean, a block's icon may stand REACH px past its own
block, beside the rest of its track (a short throat block at a crowded yard ladder). A station: under (or over) the
band, STATION_GAPS px out, sliding along it STEP px at a time. A spot is clean when its box
  - lies inside the panel: right of and below its margin, within its width and height (P.size, set by the drawing),
  - is CLEAR px from every drawn track line and turnout leg and TURNOUT_R px from every turnout's centre (its
    control circle, where a click throws it) and from each single crossover half's middle (where a caller puts
    that half's own lamp),
  - is PAD px from every other label, block contents icon, mast icon box and circle,
  - reads as its own: a track name or track block icon is no nearer any other line than its own track (the whole
    track the block is part of); a switch number or OS block icon is no nearer another turnout than its own.
Items that found no clean spot are placed first in another round (up to ROUNDS), so a crowded spot goes to the item
with the fewest other choices. Only when no order of rounds places every block contents icon at full size, they run
again with each icon that found none at full size taking the short reserve from then on, and the icons still
without one trying it after each round (each logged). An item left
with none stops with SchematicError, naming it and counting why its spots were not clean. A spot more than LOG_MOVE
px from the item's first spot is logged, with why the first was not clean.

Check. Once all are placed, every label, block contents icon and mast icon box is checked again from scratch: no
two overlap, and no label or block contents icon lies on a track line, a turnout leg or a control circle. Mast icons
among themselves and against the band titles and end labels are le_masts' to judge (it logs an icon with no clean
spot). Any failure stops.

Sets P.labels[*]["box"] and ["kind"] ("title", "end", "switch", "name", "station"), P.bcis (dicts: block, kind
"track" or "os", xy, size, box, on_track, short), P.extras (id, block, xy, band, box, on_track) and
P.labels_unplaced; every box is (x, y, width, height) as for
the mast icons. With strict=False (for a caller looking at what does not fit) an item with no clean spot is listed
in P.labels_unplaced and left out instead of stopping, and the check is not run; le always places strictly.

Known costs: a panel that needs the short reserve runs every round at full size first; verify builds its own index
of the track lines rather than reusing Layer's (it checks from scratch).

Options, a band's `le_labels` over the page's (all optional; unknown keys stop):
    {"switch_prefix": "", "switch_size": 9, "switch_bold": true,
     "block_contents": true, "block_contents_size": 13, "block_contents_text": "OCS-1234",
     "block_contents_short": "OCS-1", "names_last": false, "name_columns": [], "name_steps": [], "lamp_columns": [],
     "lamp_size": [10, 10], "numbers_below": [], "optional_block_contents": [], "crowded_block_contents": [], "extra_steps": [],
     "extra_follow": [], "hidden_names": []}
A band's options, each over the one before: DEFAULTS, the page's `le_labels`, the band's own `le_labels`, and its
entry of the band preference `le_band_labels` ({band key: le_labels object}, le_prefs: for one preferences file that
sets the page and several bands, where a flat le_labels reaches them all); a key in both of the band's own stops.
In such a file the flat le_labels is the page's and each of those bands' own at once, so a key is set either there
(every band) or per band in le_band_labels, never both.
`hidden_names` (a band's: track names): the Layout Editor panel draws no name for those tracks (hide_names marks
them before le.panel draws: no label, no room kept, name_room passes them by); the name itself stays, for block
names and helix joins. A name on no track of the band stops.
`extra_steps` and `extra_follow` (a band's own, like names_last): caller's items that step along one slope, which le
places through le_prefs.extra_steps (see there); this module only checks them.
`optional_block_contents` (a band's: blocks that band draws): blocks whose block contents icon is left out (logged,
P.bcis_skipped) when it finds no clean spot at either reserve, instead of stopping: for a block too short and
crowded to read, say once the caller's masts stand around it. It is never put first in a later round nor counted
when the best round is chosen. Every other icon still stops when it has no spot.
`numbers_below`: switch numbers (the switches' labels, no prefix; a single crossover by its crossover number or
either half's label) whose number tries the spots below its turnout
first (a crossover's number tries above first, a plain switch's the side away from its diverging leg).
`lamp_columns` (a band's): groups of track names whose caller's lamps (lamp_size) stand on one centre x, on each
track there, the same x as name_columns would give; their boxes are kept clear before anything is placed, and
P.lamps holds them ({band, track, box}) for the caller to put its lamps in.
`name_columns` (a band's): groups of track names whose labels stand on one centre x, the middle of where the
group's tracks all run level side by side (a yard's tracks between its ladders); each such name tries only spots at
that x, above then below its track, and stops if it has none.
`name_steps` (a band's): groups of track names whose labels step with their tracks' west ends (a fan of tracks
ending one after another, an engine house's): each name is centred the same distance in from the west end of its
track's level run, half the shortest such run in the group, and tries only spots at that x, above then below its
track, and stops if it has none. A name is in name_columns or name_steps, not both.
`names_last` (a band's): that band's track names are placed after every other item of the panel (block contents
icons and caller's items included), and a name with no clean spot then is left out and logged (P.names_skipped)
instead of stopping: for a crowded band where every block's icon matters more than its name. It is the band's own
le_labels key only: the page's le_labels may not set it. A name left out is then tried again first (LEAD_TRIES):
one at a time, in the order they were left out, each put before every other item, and kept there when every item
that must be placed still finds a spot (a block contents icon perhaps at the short reserve, logged) and fewer items
are left out than before; else it stays left out. An optional block contents icon left out
(`optional_block_contents`) is tried again the same way.
"""
import copy
import itertools
import math
from collections import defaultdict

from . import jmri_text, le_prefs, stations
from .core import SchematicError, crossover_name, tidy
from .label_check import _pt_seg as pt_seg, boxes_overlap

CLEAR = 3           # px from a track line's middle to a box (a main line is 4 px wide)
PAD = 2             # px between two boxes
TURNOUT_R = 8       # px around a turnout's centre: its control circle (as le_masts.TURNOUT_R)
AROUND = (3, 6, 10, 15, 21, 28, 36, 46, 58, 72)       # px out from a turnout
GAPS = (4, 8, 13, 19, 26, 34, 43)                   # px out from a track's line
STATION_GAPS = (16, 22, 28, 36, 46, 58, 72)   # px out from the band's outermost track
STEP = 8            # px between the spots tried along a track or a band
END = 4             # px a box reaching on along its track keeps over the spot it was tried at
REACH = (8, 16, 24, 32, 40)     # px past the spot a block's icon may stand, beside the rest of its track, at last
STATION_SLIDE = 240     # px a station's name may slide either way from the middle of its switches
FROG_GAPS = (3, 6, 10, 15, 21, 28)                  # px off a leg's line, in a turnout's frog
FROG_ALONG = tuple(range(0, 49, 4))                 # px along the leg from where the legs meet, in its frog
ROUNDS = 8          # rounds of placing, each with the items that found no spot before put first
LOG_MOVE = 12       # px from its first spot past which a spot taken is logged
OVERLAP = 0.5       # px two boxes must overlap by to count, in the check
GRID = 64           # px per cell of the indexes

DEFAULTS = {"switch_prefix": "", "switch_size": 9, "switch_bold": True,
            "block_contents": True, "block_contents_size": 13, "block_contents_text": "OCS-1234",
            "block_contents_short": "OCS-1", "names_last": False, "name_columns": [], "name_steps": [],
            "lamp_columns": [],
            "lamp_size": [10, 10], "numbers_below": [], "optional_block_contents": [], "crowded_block_contents": [], "extra_steps": [],
            "extra_follow": [], "hidden_names": []}
# a band's own le_labels keys: the page's may not set them
BAND_ONLY = ("names_last", "extra_steps", "extra_follow", "hidden_names")
BCI_CLASS = "jmri.jmrit.display.configurexml.BlockContentsIconXml"


# ---------------------------------------------------------------- options

def _check(where, o):
    if not isinstance(o, dict):
        raise SchematicError(f"{where}: le_labels must be an object of {', '.join(DEFAULTS)}")
    unknown = sorted(set(o) - set(DEFAULTS))
    if unknown:
        raise SchematicError(f"{where}: le_labels: unknown key {', '.join(unknown)} (keys: {', '.join(DEFAULTS)})")
    for k, v in o.items():
        if k == "lamp_size":
            if not (isinstance(v, list) and len(v) == 2 and
                    all(isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0 for n in v)):
                raise SchematicError(f"{where}: le_labels: lamp_size must be [width, height] in px above zero, "
                                     f"not {v!r}")
        elif k in ("name_columns", "name_steps", "lamp_columns"):
            if not isinstance(v, list) or not all(isinstance(g, list) and len(g) > 1 and
                                                  all(isinstance(n, str) and n.strip() for n in g) for g in v):
                raise SchematicError(f"{where}: le_labels: {k} must be a list of lists of two or more track "
                                     f"names, not {v!r}")
            names = [n for g in v for n in g]
            if len(names) != len(set(names)):
                raise SchematicError(f"{where}: le_labels: {k} names a track twice")
            other = "name_steps" if k == "name_columns" else "name_columns" if k == "name_steps" else None
            both = sorted(set(names) & {n for g in o.get(other) or [] if isinstance(g, list) for n in g}) \
                if other else []
            if both:
                raise SchematicError(f"{where}: le_labels: {', '.join(both)} in both name_columns and name_steps")
        elif k == "extra_steps":
            if not isinstance(v, list) or not all(isinstance(g, list) and len(g) > 1 and
                                                  all(isinstance(n, str) and n.strip() for n in g) for g in v):
                raise SchematicError(f"{where}: le_labels: extra_steps must be a list of lists of two or more extra "
                                     f"ids, not {v!r}")
            ids = [n for g in v for n in g]
            if len(ids) != len(set(ids)):
                raise SchematicError(f"{where}: le_labels: extra_steps names an extra twice")
        elif k == "extra_follow":
            if not isinstance(v, list) or not all(isinstance(g, list) and len(g) == 2 and g[0] != g[1] and
                                                  all(isinstance(n, str) and n.strip() for n in g) for g in v):
                raise SchematicError(f"{where}: le_labels: extra_follow must be a list of [leader, follower] extra "
                                     f"ids, not {v!r}")
            stepped = {n for g in o.get("extra_steps", []) if isinstance(g, list) for n in g[2:]}
            followers = [g[1] for g in v]
            if len(followers) != len(set(followers)) or stepped & set(followers):
                raise SchematicError(f"{where}: le_labels: extra_follow places an extra that another entry or "
                                     "extra_steps places too")
            moving = sorted((stepped | set(followers)) & {g[0] for g in v})
            if moving:
                raise SchematicError(f"{where}: le_labels: extra_follow's leader {', '.join(moving)} is itself "
                                     "stepped or follows; a leader must stand where the label layer puts it")
        elif k in ("numbers_below", "optional_block_contents", "crowded_block_contents", "hidden_names"):
            what = {"numbers_below": "switch numbers", "optional_block_contents": "block names",
                    "crowded_block_contents": "block names", "hidden_names": "track names"}[k]
            if not isinstance(v, list) or not all(isinstance(n, str) and n.strip() for n in v):
                raise SchematicError(f"{where}: le_labels: {k} must be a list of {what}, not {v!r}")
            if k == "hidden_names" and len(set(v)) != len(v):
                raise SchematicError(f"{where}: le_labels: hidden_names names a track twice: {v!r}")
        elif k in ("switch_bold", "block_contents", "names_last"):
            if not isinstance(v, bool):
                raise SchematicError(f"{where}: le_labels: {k} must be true or false, not {v!r}")
        elif k.endswith("_size"):
            if isinstance(v, bool) or not isinstance(v, int) or v not in jmri_text.SIZES:
                raise SchematicError(f"{where}: le_labels: {k} must be a whole font size from "
                                     f"{jmri_text.SIZES.start} to {jmri_text.SIZES.stop - 1}, not {v!r}")
        elif not isinstance(v, str) or (k.startswith("block_contents_") and not v.strip()):
            raise SchematicError(f"{where}: le_labels: {k} must be {'a' if k == 'switch_prefix' else 'a non-empty'} "
                                 f"string, not {v!r}")


def options(bands, page):
    """[{option: value}] per band, each checked (and each band's `stations`) before anything is drawn. In this order,
    each over the one before: DEFAULTS, the page's `le_labels`, the band's own `le_labels`, then the band's entry of
    its `le_band_labels` (le_prefs.band_entries: {band key: le_labels object}, read from the band's own
    preferences). A key in both the band's own `le_labels` and its `le_band_labels` entry stops: both are that
    band's, so set it in one. The BAND_ONLY keys come from the band's two only, never the page's."""
    page = page or {}
    if "le_labels" in page:
        _check("page", page["le_labels"])
        own = any(page is opts for _t, _b, opts in bands)       # the page is a band's own options: allowed there
        for k in BAND_ONLY:
            if k in page["le_labels"] and not own:
                raise SchematicError(f"page: le_labels: {k} is a band's own option; set it in that band's "
                                     "le_labels or le_band_labels, not the page's")
    keyed = le_prefs.band_entries(bands, page, "le_band_labels")
    out = []
    for bi, (title, _band, opts) in enumerate(bands):
        opts = opts or {}
        if "le_labels" in opts:
            _check(title, opts["le_labels"])
        stations.entries(opts)
        flat, by_band = opts.get("le_labels", {}), keyed.get(bi, {})
        both = sorted(set(flat) & set(by_band))
        if both:
            raise SchematicError(f"{title}: {', '.join(both)} set in both its le_labels and its le_band_labels "
                                 f"for {le_prefs.band_key(title)}; set each in one of them")
        mine = {**flat, **by_band}                              # the band's own, from either
        o = {**DEFAULTS, **page.get("le_labels", {}), **mine}
        for k in BAND_ONLY:                                     # the band's own, never the page's
            o[k] = mine.get(k, DEFAULTS[k])
        if jmri_text.width(o["block_contents_short"], o["block_contents_size"]) >= \
                jmri_text.width(o["block_contents_text"], o["block_contents_size"]):
            raise SchematicError(f"{title}: le_labels: block_contents_short {o['block_contents_short']!r} must be "
                                 f"narrower than block_contents_text {o['block_contents_text']!r}")
        out.append(o)
    return out


HIDDEN = "le_name_hidden"     # set on a strand whose name the Layout Editor panel leaves off (hide_names)


def hide_names(bands, page):
    """`bands` with each band's `hidden_names` (options) marked: a copy in which those tracks carry HIDDEN, so the
    Layout Editor panel draws no name for them (no label, no room kept for one, le.panel's name_room passes them
    by). The name itself stays, so block names, helix joins and messages read as before, and every other output
    keeps it. A name matches a track's name as given or as the panel writes it (tidy: "Track Y-1" as "Y-1"). Stops
    when a listed name is on no track of that band. The bands given are not changed; a band with nothing hidden is
    returned as it is, and marking twice changes nothing (le.panel and draw_panel both call this)."""
    out = []
    for (title, band, o), opts in zip(bands, options(bands, page)):
        hidden = opts["hidden_names"]
        if not hidden:
            out.append((title, band, o))
            continue
        strands = band["strands"]
        named = defaultdict(set)
        for sid, s in strands.items():
            if s.get("name"):
                named[s["name"]].add(sid)
                named[tidy([s["name"]])[0]].add(sid)
        missing = [n for n in hidden if n not in named]
        if missing:
            raise SchematicError(f"{title}: le_labels: hidden_names {', '.join(missing)}: no track of the band "
                                 "has that name")
        gone = {sid for n in hidden for sid in named[n] if not strands[sid].get(HIDDEN)}
        if gone:
            band = dict(band, strands={sid: dict(s, **{HIDDEN: True}) if sid in gone else s
                                       for sid, s in strands.items()})
        out.append((title, band, o))
    return out


# ---------------------------------------------------------------- geometry

def box_of(x, y, w, h):
    return (x, y, x + w, y + h)


def point_gap(box, p):
    return math.hypot(max(box[0] - p[0], 0, p[0] - box[2]), max(box[1] - p[1], 0, p[1] - box[3]))


def touches(a, b, box):
    """Whether segment ab meets the box (Liang-Barsky clipping)."""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - box[0]), (dx, box[2] - a[0]), (-dy, a[1] - box[1]), (dy, box[3] - a[1])):
        if p == 0:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def seg_gap(a, b, box):
    """px from segment ab to the box (0 when they meet): apart, the nearest pair has an end or a corner in it."""
    if touches(a, b, box):
        return 0.0
    corners = ((box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3]))
    return min(point_gap(box, a), point_gap(box, b), *(pt_seg(c, a, b) for c in corners))


def within(a, b, box, r):
    """Whether segment ab comes nearer the box than r px (a quick test of the box grown by r first)."""
    return touches(a, b, (box[0] - r, box[1] - r, box[2] + r, box[3] + r)) and seg_gap(a, b, box) < r


def centre(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def cells(box, r=0.0):
    return [(i, j) for i in range(int((box[0] - r) // GRID), int((box[2] + r) // GRID) + 1)
            for j in range(int((box[1] - r) // GRID), int((box[3] + r) // GRID) + 1)]


class Grid:
    """Things with a box, found by the cells their box covers."""

    def __init__(self):
        self.cell, self.items = defaultdict(list), []

    def add(self, box, thing):
        i = len(self.items)
        self.items.append((box, thing))
        for c in cells(box):
            self.cell[c].append(i)

    def near(self, box, r):
        seen = set()
        for c in cells(box, r):
            for i in self.cell.get(c, ()):
                if i not in seen:
                    seen.add(i)
                    yield self.items[i]


def label_box(lb):
    """(x0, y0, x1, y1) JMRI gives a label: its whole-pixel x, y and the Dialog font's width and height."""
    x, y = round(lb["xy"][0]), round(lb["xy"][1])
    return box_of(x, y, jmri_text.width(lb["text"], lb["size"], lb["bold"]), jmri_text.height(lb["size"], lb["bold"]))


# ---------------------------------------------------------------- the panel as drawn

class Layer:
    """The drawn panel the labels go around (indexes built once), and the labels placed so far."""

    def __init__(self, P, bands, opts):
        from . import le_masts
        from .le import LABEL_SIZE, MARGIN
        self.P, self.bands, self.opts = P, bands, opts
        self.kept = None            # what earlier bands placed, standing (place by band); None: nothing yet
        self.reserved = []          # the caller's lamp boxes (lamp_columns): {band, track, box}
        self.margin, self.name_size = MARGIN, LABEL_SIZE
        view = le_masts.PanelView(P)
        self.world = world = le_masts.World(view)
        self.turnouts = view.turnouts
        self.ink = Grid()                   # every drawn line: ((a, b), owner), owner ("seg" or "to", ident)
        self.pieces = defaultdict(list)     # owner -> [(a, b)]
        for sid, pieces in world.track.items():
            for a, b in pieces:
                self._ink((a, b), ("seg", sid))
        for tid, (_cen, lines) in world.bodies.items():
            for a, b in lines:
                self._ink((a, b), ("to", tid))
        self.circles = Grid()               # turnout centres (control circles)
        self.marks = Grid()                 # (turnout ident, half or None): where a turnout reads as itself
        for t in P.turnouts:
            cen = tuple(t["cen"])
            self.circles.add(box_of(cen[0], cen[1], 0, 0), t["ident"])
            for key, p in self.halves(t).items():
                self.marks.add(box_of(p[0], p[1], 0, 0), (t["ident"], key))
                if key:         # a single crossover's half: kept clear as a circle too (its OS block's lamp)
                    self.circles.add(box_of(p[0], p[1], 0, 0), t["ident"])
        self.track_of = {}                  # segment ident -> the segments of its whole track (strand or turnback)
        for idents in list(P.strand_segments.values()) + list(P.turnbacks.values()):
            for i in idents:
                self.track_of[i] = idents
        self.reset()

    def reset(self):
        """Nothing placed yet: the boxes to clear are the labels le drew itself, the mast icons and the circles; and,
        once a band's labels stand (place by band), those (self.kept)."""
        P = self.P
        self.notes = []                     # log lines of this round
        if self.kept is not None:
            self.boxes = copy.deepcopy(self.kept)
            return
        self.boxes = Grid()                 # (box, (what, kind)) of every label, icon and circle to clear
        for lb in P.labels:
            self.boxes.add(label_box(lb), (f"label {lb['text']!r}", "a label"))
        for m in P.masts:
            self.boxes.add(box_of(*m["box"]), (f"mast {m['mast']}'s icon", "a mast icon"))
        for sh in P.shapes:
            (cx, cy), r = sh["centre"], sh["r"]
            self.boxes.add((cx - r, cy - r, cx + r, cy + r), ("a circle", "a circle"))
        for lamp in self.reserved:          # a caller's lamp (lamp_columns): kept clear from the start
            self.boxes.add(box_of(*lamp["box"]), (f"lamp of {lamp['track']}", "a lamp"))

    def band_of(self, owner):
        kind, ident = owner
        return self.turnouts[ident]["band"] if kind == "to" else self.world.ctx.segs[ident]["band"]

    def _ink(self, seg, owner):
        a, b = seg
        self.ink.add((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])), (seg, owner))
        self.pieces[owner].append(seg)

    @staticmethod
    def halves(t):
        """{key: point} where a turnout reads as itself: its legs' meeting point; a single crossover's two halves
        (A-B and D-C) by their middles; a double crossover's centre."""
        p = t["pts"]
        if t["type"] in ("RH_XOVER", "LH_XOVER"):
            return {"AB": ((p["A"][0] + p["B"][0]) / 2, (p["A"][1] + p["B"][1]) / 2),
                    "DC": ((p["D"][0] + p["C"][0]) / 2, (p["D"][1] + p["C"][1]) / 2)}
        return {None: tuple(t["at"] if t["type"] != "DOUBLE_XOVER" else t["cen"])}

    # ---- a spot's faults
    def fault(self, box, item, on=False):
        """(kind, in full) of why a box is not a clean spot for item, or None. `on`: a block contents icon on its own
        block's track, whose lines are then no obstacle (and it reads as that block's by standing on it)."""
        if box[0] < self.margin or box[1] < self.margin or box[2] > self.P.size[0] or box[3] > self.P.size[1]:
            return ("outside the panel",) * 2
        for _b, ((a, b), owner) in self.ink.near(box, CLEAR):
            if on and owner in item["block_owners"]:    # on its own block's line, which it stands on
                continue
            if within(a, b, box, CLEAR):
                return ("on a turnout's legs",) * 2 if owner[0] == "to" else ("on a track",) * 2
        for bx, _tid in self.circles.near(box, TURNOUT_R):
            if point_gap(box, bx[:2]) < TURNOUT_R:
                return ("on a turnout's control circle",) * 2
        for other, (what, kind) in self.boxes.near(box, PAD):
            if boxes_overlap(box, other, PAD):
                return f"over {kind}", f"over {what}"
        why = None if on else self.reads_other(box, item)
        return (why, why) if why else None

    def reads_other(self, box, item):
        """Why the box reads as another track's or turnout's, or None. A station's name reads by its band."""
        if item["own_lines"]:
            d = min(seg_gap(a, b, box) for a, b in item["own_lines"])
            for _b, ((a, b), owner) in self.ink.near(box, d):
                if owner not in item["owners"] and within(a, b, box, d - 0.5):
                    return "nearer another track"
            return None
        if not item["own_marks"]:
            return None
        d = min(point_gap(box, p) for p in item["own_marks"])
        for bx, key in self.marks.near(box, d):
            if key not in item["marks"] and point_gap(box, bx[:2]) < d - 0.5:
                return "nearer another turnout"
        return None

    # ---- taking a spot
    def take(self, item, spots):
        """(box, None) of item's first clean spot, which it then holds; (None, why) when it has none. A spot is
        (x, y), (x, y, True) for a block contents icon on its own block's track, or (x, y, on, w) for one with the
        short reserve, w px wide (item["on_track"] and item["short"] say which was taken)."""
        why = defaultdict(int)
        first = first_why = None
        seen = set()
        for spot in spots:
            x, y, on = round(spot[0]), round(spot[1]), len(spot) > 2 and spot[2]
            w = spot[3] if len(spot) > 3 else item["w"]
            if (x, y, on, w) in seen:
                continue
            seen.add((x, y, on, w))
            box = box_of(x, y, w, item["h"])
            if first is None:
                first = (x, y)
            f = self.fault(box, item, on)
            if f is None:
                moved = math.dist(first, (x, y))
                short = w != item["w"]
                if short:
                    where = " on its own block's track" if on else ""
                    self.notes.append(f"{item['what']}: no clean spot at the full reserve {item['reserve']!r}; "
                                      f"placed{where} with the short reserve {item['short_reserve']!r}")
                elif on:
                    self.notes.append(f"{item['what']}: no clean spot beside its track ({first_why}); it stands on "
                                      "its own block's track")
                elif moved > LOG_MOVE:
                    self.notes.append(f"{item['what']}: placed {moved:.0f} px from its first spot ({first_why})")
                self.boxes.add(box, (item["what"], item["kind"]))
                item["on_track"], item["short"] = on, short
                return box, None
            first_why = first_why or f[1]
            why[f[0]] += 1
        reasons = ", ".join(f"{n} {w}" for w, n in sorted(why.items(), key=lambda kv: (-kv[1], kv[0])))
        return None, f"{item['what']}: no clean spot for it among {len(seen)} tried ({reasons or 'none to try'})"

    # ---- the items
    def item(self, kind, what, text, size, bold, w=None, owners=(), marks=(), block_owners=(), h=None):
        """An item to place: `kind` names it among the reasons ("a track name"), `what` in full. `owners`: the
        lines of its own track (a box must be no nearer any other line); `marks`: the turnouts (and halves) it
        belongs to (no other may be nearer); `block_owners`: its own block's lines, which a block contents icon
        standing on its track may cover."""
        own_lines = [s for o in owners for s in self.pieces.get(o, [])]
        own_marks = [p for (tid, key) in marks for k, p in self.halves(self.turnouts[tid]).items() if k == key]
        if owners and not own_lines:
            raise SchematicError(f"{what}: nothing of it is drawn to place it by")
        return dict(kind=kind, what=what, text=text, size=size, bold=bold, owners=set(owners), own_lines=own_lines,
                    block_owners=set(block_owners),
                    marks=set(marks), own_marks=own_marks,
                    w=jmri_text.width(text, size, bold) if w is None else w,
                    h=jmri_text.height(size, bold) if h is None else h)


def around(region, w, h, up_first, dists=AROUND, more=None):
    """Top-left corners of a w x h box around region (x0, y0, x1, y1): above and below (centred, then a quarter
    and half a box either way), then left and right, each distance out in turn; then more(d)'s spots, if given, for
    that distance (switch_spots)."""
    x0, y0, x1, y1 = region
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for d in dists:
        for up in (up_first, not up_first):
            y = y0 - d - h if up else y1 + d
            for dx in (0, -w / 4, w / 4, -w / 2, w / 2):
                yield cx - w / 2 + dx, y
        for left in (False, True):
            x = x0 - d - w if left else x1 + d
            for y in (cy - h / 2, y0 - h - d / 2, y1 + d / 2):
                yield x, y
        if more is not None:
            yield from more(d)


def frog_of(t):
    """(points, unit along leg B, unit along leg C) of a plain turnout or wye: the wedge between its two legs, past
    where they meet. None for a crossover (its number goes around the whole crossover) or legs drawn on one line
    (no wedge between them). Stops on a leg missing or drawn with no length."""
    if "XOVER" in t["type"]:
        return None
    at = tuple(t["at"])
    units = []
    for k in "BC":
        p = t["pts"].get(k)
        if p is None:
            raise SchematicError(f"turnout {t['ident']} ({t['type']}): no leg {k} drawn")
        L = math.dist(at, p)
        if L < 1e-6:
            raise SchematicError(f"turnout {t['ident']}: its leg {k} ends where its legs meet")
        units.append(((p[0] - at[0]) / L, (p[1] - at[1]) / L))
    cross = units[0][0] * units[1][1] - units[0][1] * units[1][0]
    if abs(cross) < 1e-6:
        return None
    return at, units[0], units[1]


def frog_spots(frog, w, h):
    """[(band, (x, y))]: top-left corners of a w x h box in the wedge between the legs of `frog` (frog_of), past
    where they meet: against each leg in turn, FROG_GAPS px off its line on the other leg's side, FROG_ALONG px
    along it, the box's corner nearest that line on the spot, so the whole box stands on the wedge's side of it.
    `band` is the AROUND distance (the first not under the gap) the spot ranks with; nearest first."""
    at, legs = frog[0], (frog[1], frog[2])
    out = []
    for i, u in enumerate(legs):
        other = legs[1 - i]
        n = (-u[1], u[0])
        if n[0] * other[0] + n[1] * other[1] < 0:
            n = (u[1], -u[0])
        # the box's corner least far along n (ties: least far along u), as an offset from its top left
        corner = min(((0, 0), (w, 0), (0, h), (w, h)),
                     key=lambda c: (round(c[0] * n[0] + c[1] * n[1], 9), c[0] * u[0] + c[1] * u[1]))
        for g in FROG_GAPS:
            for s in FROG_ALONG:
                q = (at[0] + u[0] * s + n[0] * g, at[1] + u[1] * s + n[1] * g)
                band = next(d for d in AROUND if d >= g)       # FROG_GAPS stay within AROUND
                out.append((band, math.hypot(s, g), (q[0] - corner[0], q[1] - corner[1])))
    out.sort(key=lambda o: (o[0], o[1]))
    return [(band, xy) for band, _dist, xy in out]


def beyond_spots(at, w, h, obstacles):
    """[(band, up, (x, y))]: top-left corners of a w x h box stacked past each box in `obstacles` (x0, y0, x1, y1)
    that stands wholly above or below the point `at` and spans the column a box near it would take (within w px of
    it either way): PAD px further out than the obstacle on its side, centred on `at`, a quarter and half a box
    either way, then over the obstacle (centred, flush with either end). `band` is the AROUND distance the spot
    ranks with, the first not under the box's gap from `at`; a spot further out than AROUND's last is not given."""
    x, y = at
    out = []
    for ob in obstacles:
        if ob[2] <= ob[0] or ob[3] <= ob[1]:
            raise SchematicError(f"le labels: an obstacle box {ob!r} has no width or height")
        if ob[2] < x - w or ob[0] > x + w:          # not in the column a box near `at` takes
            continue
        if ob[3] <= y:
            up, top = True, ob[1] - PAD - 1 - h
            gap = y - (top + h)
        elif ob[1] >= y:
            up, top = False, ob[3] + PAD + 1
            gap = top - y
        else:                                       # across the point's own line: nothing to stack past
            continue
        if gap > AROUND[-1]:
            continue
        band = next(d for d in AROUND if d >= gap)
        for left in [x - w / 2 + dx for dx in (0, -w / 4, w / 4, -w / 2, w / 2)] + \
                [(ob[0] + ob[2] - w) / 2, ob[0], ob[2] - w]:
            out.append((band, up, (left, top)))
    out.sort(key=lambda o: o[0])
    return out


def switch_spots(at, w, h, up_first, frog=None, obstacles=()):
    """Top-left corners of a w x h switch number around a plain turnout's points `at`: around's spots, ranked as
    there, and after those of each distance the new kinds of that distance (their band): in its frog (frog_spots,
    when `frog` is given), then stacked past a mast icon or label that stands there (beyond_spots), on the side
    tried first, then the other."""
    frogs = frog_spots(frog, w, h) if frog else []
    stacks = beyond_spots(at, w, h, obstacles)

    def more(d):
        yield from (xy for band, xy in frogs if band == d)
        yield from (xy for band, up, xy in stacks if band == d and up == up_first)
        yield from (xy for band, up, xy in stacks if band == d and up != up_first)
    return around((*at, *at), w, h, up_first, more=more)


def spots_along(lines):
    """Points along lines [(a, b)] taken end to end, from the middle of their length outward STEP px at a time."""
    lens = [math.dist(a, b) for a, b in lines]
    total = sum(lens)
    marks = sorted({min(total, max(0.0, total / 2 + k * STEP)) for k in range(-int(total / STEP) - 1,
                                                                               int(total / STEP) + 2)},
                   key=lambda s: (abs(s - total / 2), s))
    pts = []
    for s in marks:
        for (a, b), L in zip(lines, lens):
            if s <= L or (a, b) == lines[-1]:
                t = 0 if L == 0 else min(1, s / L)
                pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                break
            s -= L
    return pts


def along(lines, w, h, first):
    """Top-left corners of a w x h box beside a track drawn as lines [(a, b)]: on side `first` ("above" or
    "below"), then the other, then left and right of it, GAPS px out, from the middle of its length outward; above
    or below, the box centred on the spot, then reaching on from it either way; only when none of those is clean,
    standing REACH px past the spot, beside the rest of its track (a short block's icon, crowded at a yard throat)."""
    pts = spots_along(lines)
    sides = (first, "below" if first == "above" else "above")
    near = (-w / 2, -END, -w + END)                 # centred on the spot, then reaching on from it either way
    far = tuple(x for k in REACH for x in (k, -w - k))      # standing beside the rest of the track, k px on
    for offsets in (near, far):
        for g in GAPS:
            for side in sides:
                for p in pts:
                    for dx in offsets:
                        yield p[0] + dx, (p[1] - g - h if side == "above" else p[1] + g)
    for g in GAPS:
        for left in (True, False):
            for p in pts:
                yield (p[0] - g - w if left else p[0] + g), p[1] - h / 2


def on_track(lines, w, h):
    """(x, y, True) top-left corners of a w x h box standing on its own block's track drawn as lines [(a, b)]: its
    middle on the rail, from the middle of the block outward STEP px at a time."""
    for p in spots_along(lines):
        yield p[0] - w / 2, p[1] - h / 2, True


# ---------------------------------------------------------------- placing

def side(box, lines):
    """"above" or "below": the side of its nearest line a box stands on."""
    c = centre(box)
    a, b = min(lines, key=lambda ab: pt_seg(c, *ab))
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / L2))
    return "above" if c[1] < a[1] + t * dy else "below"


def diverges_down(t):
    """A plain turnout or wye whose legs B or C run down the panel from where its legs meet."""
    return any(t["pts"][k][1] > t["at"][1] + 1e-6 for k in "BC")


def place(P, bands, opts, strict=True, extras=None, by_band=False):
    """Every switch number, track name, block contents icon and station name, then the check (module text). Items
    that find no clean spot are placed first in another round (up to ROUNDS): a crowded spot goes to what needs it
    most. Only when no order places every block contents icon at full size, the rounds run again with each icon
    that found no spot at full size taking the short reserve from then on, and after each round the icons still
    without one trying it against everything placed; the first round that places everything stands, else the one
    that leaves the fewest. With `by_band`, each band's items go through those rounds on their own, top band first,
    and what a band placed stands for the bands after it (so a band's labels do not depend on the bands below it).
    Strict, an item left with none stops; else it is listed in P.labels_unplaced."""
    P.labels = [lb for lb in P.labels if lb["kind"] in FIXED]     # the rest only kept their room in the drawing
    settle_end_labels(P)
    L = Layer(P, bands, opts)
    extras = check_extras(extras, P.blocks)
    items = specs(P, bands, opts, L, extras)
    # a band's names_last: its track names go after everything else and may be left out
    skip_names = {k for k, _m in items if k[0] == "name" and opts[k[1]]["names_last"]}
    items = [it for it in items if it[0] not in skip_names] + [it for it in items if it[0] in skip_names]
    skip_bcis = optional_icons(P, L, bands, opts)
    if by_band:
        band = item_bands(P, L, items, extras)
        groups = [[it for it in items if band[it[0]] == bi] for bi in sorted(set(band.values()))]
    else:
        groups = [items]
    done, failed, skipped, notes = [], [], [], []
    for group in groups:
        g_done, g_failed, g_skipped = place_items(L, group, skip_names, skip_bcis)
        done += g_done
        failed += g_failed
        skipped += g_skipped
        notes += L.notes
        L.kept = copy.deepcopy(L.boxes)         # this band's labels stand for the next
    L.kept = None
    crowded = {("bci", b) for o in opts for b in o["crowded_block_contents"]}
    makers = dict(items)
    for key in [k for k, _msg in failed if k in crowded]:     # drawn anyway, at its first spot, overlaps allowed
        it, spots, keep = makers[key](dict(number_side={}, name_side={}))
        spot = next(iter(spots))
        w = spot[3] if len(spot) > 3 else it["w"]
        it.update(on_track=False, short=w != it["w"])
        kind, d = keep(box_of(round(spot[0]), round(spot[1]), w, it["h"]))
        d["crowded"] = True
        done.append((kind, d))
        notes.append(f"{it['what']}: no clean spot; drawn at its first spot anyway (crowded_block_contents)")
    failed = [(k, msg) for k, msg in failed if k not in crowded]
    P.log += [n for n in notes if n.endswith("(crowded_block_contents)")]
    notes = [n for n in notes if not n.endswith("(crowded_block_contents)")]
    if failed and strict:
        raise SchematicError(failed[0][1] + (f" (and {len(failed) - 1} more)" if len(failed) > 1 else ""))
    P.labels_unplaced = [(k, msg) for k, msg in failed]
    P.lamps = list(L.reserved)
    P.names_skipped = [msg for k, msg in skipped if k[0] == "name"]
    P.bcis_skipped = [msg for k, msg in skipped if k[0] == "bci"]
    P.log += notes + [f"{msg} (names_last: left out)" for msg in P.names_skipped] + \
        [f"{msg} (optional_block_contents: left out)" for msg in P.bcis_skipped]
    P.bcis, P.extras = [], []
    for kind, d in done:
        {"bci": P.bcis, "extra": P.extras}.get(kind, P.labels).append(d)
    for lb in P.labels:
        if "box" not in lb:
            x0, y0, x1, y1 = label_box(lb)
            lb["box"] = (x0, y0, x1 - x0, y1 - y0)
    if strict:              # not strict, items may be missing: the caller only looks at what does not fit
        verify(P)


def optional_icons(P, L, bands, opts):
    """{("bci", block)}: the block contents icons a band's `optional_block_contents` lets be left out, each only for
    a block that band draws. A listed block drawn on another band is not that band's (logged, when its options are
    the other band's too); one drawn nowhere here is logged and ignored, since a panel drawn with `--band` does not
    draw every band the options were written for."""
    places = block_places(P, L)
    by_band = defaultdict(set)
    for block in P.blocks:
        by_band[block_band(L, places, block)].add(block)
    out = set()
    for bi, o in enumerate(opts):
        for block in o["optional_block_contents"]:
            if block in by_band[bi]:
                out.add(("bci", block))
            elif block not in P.blocks:
                P.log.append(f"{bands[bi][0]}: optional_block_contents: block {block} is not drawn on this panel "
                             "(ignored)")
    return out


def item_bands(P, L, items, extras):
    """{item key: band index} for place's items: a switch number's turnout's band, a track or station name's own,
    a block contents icon's or caller's item's block's (block_band)."""
    places = block_places(P, L)
    turnout_band = {t["ident"]: t["band"] for t in P.turnouts}
    extra_block = {e["id"]: e["block"] for e in extras}
    out = {}
    for key, _make in items:
        kind = key[0]
        if kind == "switch":
            out[key] = turnout_band[key[1]]
        elif kind in ("name", "station"):
            out[key] = key[1]
        elif kind == "bci":
            out[key] = block_band(L, places, key[1])
        elif kind == "extra":
            out[key] = block_band(L, places, extra_block[key[1]])
        else:
            raise SchematicError(f"le labels: no band known for an item of kind {kind}")
    return out


def place_items(L, items, skip_names, skip_bcis):
    """(done, failed, skipped) of placing `items` in rounds (place_rounds); then each item left out (skipped) tried
    again first, one at a time (module text, names_last): it leads when every item that must be placed still finds a
    spot and fewer are left out. An item with no clean spot even with nothing else placed (against the drawing, the
    mast icons and what stands already) is not tried. The panel's labels stand as in the outcome returned."""
    got = place_rounds(L, items, skip_names, skip_bcis, [])
    if got[1] or not got[2]:
        return got
    makers = dict(items)

    def free(key):
        """Whether the item has a clean spot with no other item placed (at the short reserve, for an icon)."""
        L.reset()
        made = makers[key](dict(number_side={}, name_side={}), short=key[0] == "bci")
        return bool(made) and L.take(made[0], made[1])[0] is not None

    lead, last = [], None
    for key in [k for k, _why in got[2] if free(k)][:LEAD_TRIES]:
        trial = place_rounds(L, items, skip_names, skip_bcis, lead + [key])
        last = lead + [key]
        if not trial[1] and len(trial[2]) < len(got[2]):
            lead, got = last, trial
    if last != lead:                    # the labels as in the outcome kept (L.reset above too): its round, again
        got = place_rounds(L, items, skip_names, skip_bcis, lead)
    return got


LEAD_TRIES = 24     # items left out tried again first, at most


def place_rounds(L, items, skip_names, skip_bcis, lead):
    """(done, failed, skipped) of placing `items` in rounds (place): every icon at full size if any order of rounds
    allows it; only then the short reserve. `skip_names` (names_last) and `skip_bcis` (optional_block_contents) may
    be left out (skipped): a name as soon as it has no spot, an icon once it has none at the short reserve either.
    Neither is ever put first in a later round, nor counted when choosing the best round, except those in `lead`,
    which every round places first (place_items)."""
    makers = dict(items)
    skipped = []

    def attempt(first, short):
        """One round in that order; with `short`, the block contents icons in `first` (they found no spot at full
        size in an earlier round) take the short reserve in their turn, and each icon left without a spot then tries
        it against everything placed. An optional name (names_last) that finds no spot is set aside in `skipped`,
        never put first in a later round."""
        L.reset()
        done, failed, state = place_round(L, items, first, set(first) if short else ())
        skipped[:] = [(k, why) for k, why in failed if k in skip_names]
        failed = [(k, why) for k, why in failed if k not in skip_names]
        still = []
        for key, why in failed:                     # only what failed at full size gets the short reserve
            got = makers[key](state, short=True) if short else None
            box = L.take(got[0], got[1])[0] if got else None
            if box is None:
                still.append((key, why))
            else:
                done.append(got[2](box))
        return done, failed, still

    def needed(still):
        return [x for x in still if x[0] not in skip_bcis]

    for short in (False, True):
        first, tried, best = list(lead), set(), None
        for _ in range(ROUNDS):
            done, failed, still = attempt(first, short)
            if best is None or len(needed(still)) < best[0]:
                best = (len(needed(still)), list(first))
            if not needed(still):
                break
            again = [k for k, _msg in failed if k not in skip_bcis and k not in lead]
            order = tuple(list(lead) + again + [k for k in first if k not in again and k not in lead])
            if order in tried:                      # this order again: more rounds will not help
                break
            tried.add(order)
            first = list(order)
        if needed(still) and first != best[1]:      # the round that left the fewest, again
            done, failed, still = attempt(best[1], short)
        if not still:                               # an optional icon left over still tries the short reserve
            break
    # an optional block contents icon (optional_block_contents) left with no spot at either reserve is left out
    return done, needed(still), list(skipped) + [x for x in still if x[0] in skip_bcis]


def place_round(L, items, first, again=()):
    """([(kind, placed dict)], [(key, why)], state): one round, the keys in `first` placed first, then the rest in
    order; a block contents icon in `again` (it found no spot at full size before) tries the short reserve."""
    rank = {k: i for i, k in enumerate(first)}
    order = sorted(range(len(items)), key=lambda i: (rank.get(items[i][0], len(rank)), i))
    state = dict(number_side={}, name_side={})
    done, failed = [], []
    for i in order:
        key, make = items[i]
        item, spots, commit = make(state, short=key[0] == "bci" and key in again)
        box, why = L.take(item, spots)
        if box is None:
            failed.append((key, why))
        else:
            done.append(commit(box))
    return done, failed, state


def _boxed(box):
    return (box[0], box[1], box[2] - box[0], box[3] - box[1])


def specs(P, bands, opts, L, extras=()):
    """[(key, make)] in the default order: switch numbers, track names, block contents icons, station names.
    make(state) gives (item, its spots, commit(box) -> ("label" or "bci", the dict P keeps)); `state` carries the
    side each number and name took, for the icons placed after them."""
    out = []
    # a crossover drawn as two turnouts on its one name (P.split_names) has one number: by its lower turnout when
    # the switch is in numbers_below, else by its upper one
    numbered = {}

    def raw_label(t):
        return bands[t["band"]][1]["nodes"][t["nodes"][0]].get("label") or ""

    # numbers_below names a single crossover by its number or either half's label: below when any of them is listed
    halves = defaultdict(set)
    for t in P.turnouts:
        if t["name"] in P.split_names:
            halves[(t["band"], t["name"])].add(raw_label(t))

    def below_first(t, xover):
        nb = opts[t["band"]]["numbers_below"]
        raws = halves.get((t["band"], t["name"])) or {raw_label(t)}
        return any(r in nb or (xover and crossover_name(r) in nb) for r in raws)

    for t in P.turnouts:
        if t["name"] in P.split_names:
            below = below_first(t, True)
            key = (t["band"], t["name"])
            best = numbered.get(key)
            if best is None or (t["at"][1] > best["at"][1] if below else t["at"][1] < best["at"][1]):
                numbered[key] = t
    for t in P.turnouts:
        o = opts[t["band"]]
        label = raw_label(t)
        # a single crossover, drawn as one or as two turnouts on its one name: its number, not a half's letter
        xover = t["type"] in ("RH_XOVER", "LH_XOVER") or t["name"] in P.split_names
        if xover:
            label = crossover_name(label)
        if t["name"] in P.split_names and numbered[(t["band"], t["name"])] is not t:
            continue
        if label:
            out.append((("switch", t["ident"]), _switch_number(L, t, o["switch_prefix"] + label, o,
                                                               below_first(t, xover))))
    named = []
    for (bi, sid), idents in sorted(P.strand_segments.items()):
        st = bands[bi][1]["strands"][sid]
        name = st["name"]
        mine = [i for i in idents if i in L.world.track]
        if not name or not mine or st.get(HIDDEN):     # hidden_names: no name drawn, nothing logged
            continue
        if (bi, sid) in P.no_name:          # the drawing keeps no room for it: as before the label layer, no name
            P.log.append(f"{bands[bi][0]}: track {tidy([name])[0]}: no name placed ({P.no_name[(bi, sid)]})")
            continue
        named.append((bi, sid, tidy([name])[0], mine))
    column = name_column_x(L, bands, opts, named)
    column.update(name_step_x(L, bands, opts, named))
    L.reserved = lamp_boxes(L, opts, named, name_column_x(L, bands, opts, named, "lamp_columns"))
    for bi, sid, text, mine in named:
        out.append((("name", bi, sid), _track_name(L, bi, text, mine, column.get((bi, text)))))
    places = block_places(P, L)
    out += _extras(L, places, extras)       # before the icons: bigger, and rarer
    out += _bcis(P, L, places)
    for bi, (title, _band, bopts) in enumerate(bands):
        out += _stations(P, L, bi, title, bopts or {})
    return out


def _label_dict(it, box, kind, bi):
    return "label", dict(text=it["text"], xy=[box[0], box[1]], size=it["size"], bold=it["bold"], band=bi, kind=kind,
                         box=_boxed(box))


def _switch_number(L, t, text, o, below=False):
    """`below`: the switch is in `numbers_below`, so its number is tried below its turnout first."""
    what = f"{L.bands[t['band']][0]}: switch number {text}"
    if "XOVER" in t["type"]:
        pts = list(t["pts"].values())
        region = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        up = not below
    else:
        region = (*t["at"], *t["at"])
        up = not below and diverges_down(t)     # the side away from the diverging leg first
    marks = [(t["ident"], k) for k in L.halves(t)]
    frog = frog_of(t)

    def make(state, short=False):
        if short is True:
            return None
        it = L.item("a switch number", what, text, o["switch_size"], o["switch_bold"], marks=marks)
        if "XOVER" in t["type"]:
            spots = around(region, it["w"], it["h"], up)
        else:       # a plain turnout's: also in its frog, and stacked past the mast icons and labels standing by it
            here = box_of(*t["at"], 0, 0)
            obstacles = [b for b, (_what, kind) in L.boxes.near(here, AROUND[-1] + it["w"] + it["h"])
                         if kind != "a circle"]
            spots = switch_spots(tuple(t["at"]), it["w"], it["h"], up, frog, obstacles)

        def commit(box):
            state["number_side"][t["ident"]] = "above" if centre(box)[1] < (region[1] + region[3]) / 2 else "below"
            return _label_dict(it, box, "switch", t["band"])
        return it, spots, commit
    return make


def level_span(lines):
    """(x0, x1) of the level pieces of a track drawn as lines [(a, b)], or None when none is level."""
    xs = [x for a, b in lines if abs(a[1] - b[1]) < 1e-6 for x in (a[0], b[0])]
    return (min(xs), max(xs)) if xs else None


def name_column_x(L, bands, opts, named, key="name_columns"):
    """{(band, name): centre x} for each name of a band's `name_columns` (or `key`): the middle of the x range where
    every track of its group runs level. Stops on a name that is no named track of the band, or a group with no such
    range."""
    out = {}
    by = {(bi, text): mine for bi, _sid, text, mine in named}
    for bi, (title, _band, _opts) in enumerate(bands):
        for group in opts[bi][key]:
            spans = []
            for text in group:
                if (bi, text) not in by:
                    raise SchematicError(f"{title}: le_labels: {key} names {text}, which is no named track "
                                         "with a name placed on the band")
                span = level_span([pc for i in by[(bi, text)] for pc in L.pieces.get(("seg", i), [])])
                if span is None:
                    raise SchematicError(f"{title}: le_labels: {key}: track {text} runs level nowhere")
                spans.append(span)
            lo, hi = max(s[0] for s in spans), min(s[1] for s in spans)
            if lo >= hi:
                raise SchematicError(f"{title}: le_labels: {key} {group}: the tracks run level side by side "
                                     "nowhere")
            for text in group:
                out[(bi, text)] = (lo + hi) / 2
    return out


def west_level_run(lines):
    """(x0, x1) of a track's westmost level run (its level pieces joined end to end on one row, from the westmost),
    or None when none is level."""
    pieces = sorted((min(a[0], b[0]), max(a[0], b[0]), a[1]) for a, b in lines
                    if abs(a[1] - b[1]) < 1e-6 and abs(a[0] - b[0]) > 1e-6)
    if not pieces:
        return None
    lo, hi, y = pieces[0]
    for p0, p1, py in pieces[1:]:
        if abs(py - y) < 1e-6 and p0 <= hi + 1e-6:
            hi = max(hi, p1)
        else:
            break
    return lo, hi


def name_step_x(L, bands, opts, named):
    """{(band, name): centre x} for each name of a band's `name_steps`: the west end of its track's westmost level
    run plus half the shortest such run of its group. Stops on a name that is no named track of the band, one that
    runs level nowhere, or one the band's merged options also put in name_columns."""
    out = {}
    by = {(bi, text): mine for bi, _sid, text, mine in named}
    for bi, (title, _band, _opts) in enumerate(bands):
        both = sorted({n for g in opts[bi]["name_steps"] for n in g} &
                      {n for g in opts[bi]["name_columns"] for n in g})
        if both:
            raise SchematicError(f"{title}: le_labels: {', '.join(both)} in both name_columns and name_steps (from "
                                 "the page's and the band's options together)")
        for group in opts[bi]["name_steps"]:
            spans = {}
            for text in group:
                if (bi, text) not in by:
                    raise SchematicError(f"{title}: le_labels: name_steps names {text}, which is no named track "
                                         "with a name placed on the band")
                span = west_level_run([pc for i in by[(bi, text)] for pc in L.pieces.get(("seg", i), [])])
                if span is None:
                    raise SchematicError(f"{title}: le_labels: name_steps: track {text} runs level nowhere")
                spans[text] = span
            inset = min(hi - lo for lo, hi in spans.values()) / 2
            for text, (lo, _hi) in spans.items():
                out[(bi, text)] = lo + inset
    return out


def lamp_boxes(L, opts, named, xs):
    """[{band, track, box}] of each lamp_columns track's lamp: lamp_size centred on its column's x, on the level
    piece of its track there."""
    by = {(bi, text): mine for bi, _sid, text, mine in named}
    out = []
    for (bi, text), cx in sorted(xs.items()):
        w, h = opts[bi]["lamp_size"]
        ys = [a[1] for i in by[(bi, text)] for a, b in L.pieces.get(("seg", i), [])
              if abs(a[1] - b[1]) < 1e-6 and min(a[0], b[0]) <= cx <= max(a[0], b[0])]
        if not ys:
            raise SchematicError(f"{L.bands[bi][0]}: lamp_columns: track {text} has no level piece at x {cx:g} to "
                                 "stand its lamp on")
        out.append(dict(band=bi, track=text, box=(round(cx - w / 2), round(ys[0] - h / 2), w, h)))
    return out


def column(lines, w, h, cx):
    """Top-left corners of a w x h box centred on x = cx beside the level piece of a track (lines) that spans cx,
    above then below it, GAPS px out."""
    ys = [a[1] for a, b in lines if abs(a[1] - b[1]) < 1e-6 and min(a[0], b[0]) <= cx <= max(a[0], b[0])]
    for g in GAPS:
        for y in ys[:1]:
            yield cx - w / 2, y - g - h
            yield cx - w / 2, y + g


def _track_name(L, bi, text, mine, cx=None):
    """make(state, short) for a track's name: beside its track (along), or, with `cx` (name_columns, name_steps),
    only centred on that x."""
    what = f"{L.bands[bi][0]}: track name {text}"

    def make(state, short=False):
        if short is True:
            return None
        it = L.item("a track name", what, text, L.name_size, False, owners=[("seg", i) for i in mine])

        def commit(box):
            state["name_side"].update({i: side(box, it["own_lines"]) for i in mine})
            return _label_dict(it, box, "name", bi)
        spots = along(it["own_lines"], it["w"], it["h"], "above") if cx is None else \
            column(it["own_lines"], it["w"], it["h"], cx)
        return it, spots, commit
    return make


def shorter(spots, w):
    """The same spots for the short reserve, w px wide: (x, y, on, w)."""
    for spot in spots:
        yield spot[0], spot[1], len(spot) > 2 and spot[2], w


def reserves(spots, w, short):
    """A block-tied item's spots at the short reserve (short) or at full size; spots(width) gives them for one
    width, w is (full px, short px, ...)."""
    return shorter(spots(w[1]), w[1]) if short else spots(w[0])


def block_places(P, L):
    """({block: [(turnout, half key)]} for the OS blocks, {block: [segment ident]} for the drawn track blocks)."""
    os_of = defaultdict(list)
    for t in P.turnouts:
        for key in L.halves(t):
            legs = key or "ABCD"
            for blk in sorted({t["blocks"].get(leg, t["blocks"]["A"]) for leg in legs if leg in t["pts"]}):
                os_of[blk].append((t, key))
    segs_of = defaultdict(list)
    for s in P.segments:
        if s["ident"] in L.world.track:
            segs_of[s["block"]].append(s["ident"])
    return os_of, segs_of


def by_block(L, places, block, new_item, w, done):
    """make(state, short) for an item tied to a block: an OS block's around its turnout (or its half of a single
    crossover), first on the side its switch number did not take; a track block's beside its track, first on the
    side its name did not take (below by default), then on its own block's track. new_item(**kw) makes the item,
    w is (full px, short px, ...) and done(box, it, kind) what is kept."""
    os_of, segs_of = places
    if os_of.get(block):
        on = os_of[block]
        marks = [(t["ident"], key) for t, key in on]

        def make(state, short=False):
            it = new_item(marks=marks)
            rings = []
            for t, key in on:
                if key:                     # a single crossover's half: around its own track, A-B or D-C
                    (ax, ay), (bx, by) = (t["pts"][k] for k in key)
                    rings.append(((min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)), key == "AB"))
                    continue
                p = L.halves(t)[None]
                num = state["number_side"].get(t["ident"])
                if num:
                    up = num == "below"
                elif t["type"] == "DOUBLE_XOVER":
                    up = True
                else:
                    up = not diverges_down(t)
                rings.append(((*p, *p), up))

            def spots(width):
                return (xy for region, up in rings for xy in around(region, width, it["h"], up))
            return it, reserves(spots, w, short), lambda box: done(box, it, "os")
        return make
    # a block drawn on two bands (a helix track joined as one block): only its own band's track (block_band), so the
    # item stands in that band and counts there (extent, le_title_clear)
    bi = block_band(L, places, block)
    idents = [i for i in segs_of[block] if L.world.ctx.segs[i]["band"] == bi]
    track = sorted({j for i in idents for j in L.track_of.get(i, [i]) if j in L.world.track} | set(idents))
    lines = [pc for i in idents for pc in L.pieces[("seg", i)]]

    def make(state, short=False):
        it = new_item(owners=[("seg", i) for i in track], block_owners=[("seg", i) for i in idents])
        first = "above" if {state["name_side"][i] for i in idents if i in state["name_side"]} == {"below"} \
            else "below"

        def spots(width):                       # beside the track, then on it
            return itertools.chain(along(lines, width, it["h"], first), on_track(lines, width, it["h"]))
        return it, reserves(spots, w, short), lambda box: done(box, it, "track")
    return make


def block_band(L, places, block):
    """The band a block is drawn on; stops when nothing of it is drawn."""
    os_of, segs_of = places
    if os_of.get(block):
        return os_of[block][0][0]["band"]
    if segs_of.get(block):
        return L.world.ctx.segs[segs_of[block][0]]["band"]
    raise SchematicError(f"block {block}: nothing of it is drawn to place its block contents icon or items by")


def _bcis(P, L, places):
    """[(key, make)]: one block contents icon per block (by_block), first at its full reserve."""
    out = []
    for block in sorted(P.blocks):
        bi = block_band(L, places, block)
        o = L.opts[bi]
        if not o["block_contents"]:
            continue
        size = o["block_contents_size"]
        w = (jmri_text.width(o["block_contents_text"], size), jmri_text.width(o["block_contents_short"], size),
             o["block_contents_text"], o["block_contents_short"])
        what = f"{L.bands[bi][0]}: block contents of {block}"

        def new_item(what=what, size=size, w=w, **kw):
            it = L.item("a block contents icon", what, "", size, False, w=w[0], **kw)
            it.update(reserve=w[2], short_reserve=w[3])
            return it

        def done(box, it, kind, block=block, size=size, bi=bi):
            return "bci", dict(block=block, kind=kind, xy=[box[0], box[1]], size=size, band=bi, box=_boxed(box),
                               on_track=it["on_track"], short=it["short"])
        out.append((("bci", block), by_block(L, places, block, new_item, w, done)))
    return out


def _extras(L, places, extras):
    """[(key, make)]: each caller's item (check_extras) by its block as a block contents icon goes, no shorter."""
    out = []
    for e in extras:
        bi = block_band(L, places, e["block"])
        w, h = e["size"]
        what = f"{L.bands[bi][0]}: item {e['id']} (block {e['block']})"

        def new_item(what=what, w=w, h=h, **kw):
            return L.item("an item", what, "", 10, False, w=w, h=h, **kw)

        def done(box, it, _kind, e=e, bi=bi):
            return "extra", dict(id=e["id"], block=e["block"], xy=[box[0], box[1]], band=bi, box=_boxed(box),
                                 on_track=it["on_track"])
        maker = by_block(L, places, e["block"], new_item, (w, w), done)
        if "x" in e:                # the caller's x: only spots with the box's left edge there
            maker = at_x(maker, e["x"], w, h)
        out.append((("extra", e["id"]), lambda state, short=False, maker=maker: None if short else maker(state)))
    return out


def at_x(maker, x, w, h):
    """make(state) like `maker`'s, its spots only those with the box's left edge at `x`: beside its own track where
    a piece of it spans the box's middle (above, then below, GAPS px out), then on it."""
    def make(state):
        it, _spots, commit = maker(state)
        cx = x + w / 2
        ys = []
        for a, b in it["own_lines"]:
            if min(a[0], b[0]) <= cx <= max(a[0], b[0]) and abs(b[0] - a[0]) > 1e-6:
                ys.append(a[1] + (b[1] - a[1]) * (cx - a[0]) / (b[0] - a[0]))

        def spots():
            for g in GAPS:
                for y in ys:
                    yield x, y - g - h
                    yield x, y + g
            for y in ys:
                yield x, y - h / 2, True
        return it, spots(), commit
    return make


def check_extras(extras, blocks=None):
    """The caller's block-tied items, checked: a list of {"id": non-empty text, unique; "block": a block name (one
    the panel draws, once `blocks` is known); "size": [w, h] px above zero; optionally "x": the box's left edge, px
    (at_x)}; nothing else."""
    if extras is None:
        return []
    if not isinstance(extras, (list, tuple)):
        raise SchematicError("extras must be a list of {id, block, size}")
    seen = set()
    for i, e in enumerate(extras):
        where = f"extras[{i}]"
        if not isinstance(e, dict):
            raise SchematicError(f"{where} must be an object of id, block and size, not {e!r}")
        if not {"id", "block", "size"} <= set(e) <= {"id", "block", "size", "x"}:
            raise SchematicError(f"{where}: needs id, block and size (and may give x), not "
                                 f"{', '.join(sorted(e)) or 'none'}")
        if not isinstance(e["id"], str) or not e["id"].strip():
            raise SchematicError(f"{where}: id must be non-empty text, not {e['id']!r}")
        if e["id"] in seen:
            raise SchematicError(f"{where}: id {e['id']!r} is given twice")
        seen.add(e["id"])
        if not isinstance(e["block"], str) or not e["block"]:
            raise SchematicError(f"extra {e['id']}: block must be a block name, not {e['block']!r}")
        size = e["size"]
        if not (isinstance(size, (list, tuple)) and len(size) == 2 and
                all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in size)):
            raise SchematicError(f"extra {e['id']}: size must be [width, height] in px, both above zero")
        if "x" in e and (isinstance(e["x"], bool) or not isinstance(e["x"], (int, float)) or
                         not math.isfinite(e["x"])):
            raise SchematicError(f"extra {e['id']}: x must be a number of px, not {e['x']!r}")
        if blocks is not None and e["block"] not in blocks:
            raise SchematicError(f"extra {e['id']}: block {e['block']!r} is not on the panel")
    return list(extras)


def _stations(P, L, bi, title, bopts):
    """[(key, make)]: each station's name under its band (over it for side "top"), centred on its switches, sliding
    along the band."""
    entries = stations.entries(bopts)
    if not entries:
        return []
    by_label = defaultdict(list)
    for t in P.turnouts:
        if t["band"] == bi:
            for n in t["nodes"]:
                by_label[(L.bands[bi][1]["nodes"][n].get("label") or "").rstrip("*")].append(t["at"][0])
    ys = [p[1] for owner, lines in L.pieces.items() if L.band_of(owner) == bi for seg in lines for p in seg]
    slide = sorted(range(-STATION_SLIDE, STATION_SLIDE + 1, STEP), key=lambda d: (abs(d), d))
    out = []
    for name, e in entries.items():
        xs = [x for sw in e["switches"] for x in by_label.get(str(sw), ())]
        if not xs:
            P.log.append(f"{title}: station {name}: none of its switches ({', '.join(e['switches'])}) is drawn, so "
                         "its name is not placed")
            continue
        text = name.upper()
        mid = (min(xs) + max(xs)) / 2
        top = e["side"] == "top"

        def make(state, short=False, text=text, mid=mid, top=top):
            if short is True:
                return None
            it = L.item("a station name", f"{title}: station name {text}", text, L.name_size, True)
            spots = ((mid - it["w"] / 2 + d, min(ys) - g - it["h"] if top else max(ys) + g)
                     for g in STATION_GAPS for d in slide)
            return it, spots, lambda box: _label_dict(it, box, "station", bi)
        out.append((("station", bi, name), make))
    return out


# ---------------------------------------------------------------- the check

FIXED = ("title", "end")        # the labels le draws itself (band titles; helix and connector ends)


def track_ink(P, world=None):
    """A Grid of every drawn track line, turnout leg and control circle: (a, b, what, block); b is None for a
    circle, block None but for a track line."""
    from . import le_masts
    world = world or le_masts.World(le_masts.PanelView(P))
    block_of = {s["ident"]: s["block"] for s in P.segments}
    ink = Grid()
    for sid, pieces in world.track.items():
        for a, b in pieces:
            ink.add((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])), (a, b, "a track",
                                                                                        block_of[sid]))
    for cen, lines in world.bodies.values():
        for a, b in lines:
            ink.add((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])),
                    (a, b, "a turnout's legs", None))
        ink.add(box_of(cen[0], cen[1], 0, 0), (cen, None, "a turnout's control circle", None))
    return ink


def fixed_on_line(ink, box):
    """What line a fixed label's box lies on (verify's test for a label le drew itself), or None."""
    for _b, (a, b, on, _blk) in ink.near(box, max(1.0, TURNOUT_R)):
        if b is not None and within(a, b, box, 1.0):
            return on
    return None


END_LABEL_GAP = 1   # px between a helix circle and its label moved above or below it


def end_label_spots(lb):
    """Above, then below the circle `lb["around"]` (centre, radius): the label centred on it as JMRI draws it, a
    gap clear of the circle."""
    (cx, cy), r = lb["around"]
    x0, y0, x1, y1 = label_box(lb)
    w, h = x1 - x0, y1 - y0
    return [[cx - w / 2, cy - r - END_LABEL_GAP - h], [cx - w / 2, cy + r + END_LABEL_GAP]]


def settle_end_labels(P):
    """An end's label that lies on a track at its own spot (a helix end's beside its circle) takes the first of its
    other spots (end_label_spots: above, then below its circle) that lies inside the panel, on no track, and over
    no other label le drew itself or mast icon, logged. One with no clear spot stays, and the check names it.
    Labels with no circle are not touched, and a label clear at its own spot stays, so such panels draw as before."""
    if not any(lb.get("around") for lb in P.labels):
        return
    ink = track_ink(P)
    for lb in P.labels:
        around = lb.pop("around", None)
        if not around or fixed_on_line(ink, label_box(lb)) is None:
            continue
        others = [label_box(o) for o in P.labels if o is not lb] + [box_of(*m["box"]) for m in P.masts]
        for xy in end_label_spots(dict(lb, around=around)):
            box = label_box(dict(lb, xy=list(xy)))
            inside = box[0] >= 0 and box[1] >= 0 and box[2] <= P.size[0] and box[3] <= P.size[1]
            if inside and fixed_on_line(ink, box) is None and not any(boxes_overlap(box, o, -OVERLAP) for o in others):
                P.log.append(f"label {lb['text']!r} lay on a track beside its end: drawn at {round(xy[0])}, "
                             f"{round(xy[1])} instead")
                lb["xy"] = list(xy)
                break


def verify(P):
    """From scratch: every label and block contents icon lies inside the panel, and none le_labels placed over a
    helix or connector circle; no two of the labels, block contents
    icons and mast icon boxes overlap (mast icons among themselves and against the labels le drew itself aside:
    le_masts judges and logs those); and no label or block contents icon lies on a drawn track line, a turnout leg
    or a control circle (a band title or an end's label: on a line only; an icon standing on its own block's track:
    on that block's lines it may). Stops on the first fault."""
    from . import le_masts
    world = le_masts.World(le_masts.PanelView(P))
    things = [(box_of(*lb["box"]), f"label {lb['text']!r}", "fixed" if lb["kind"] in FIXED else "label")
              for lb in P.labels]
    things += [(box_of(*b["box"]), f"block contents of {b['block']}", "crowded" if b.get("crowded") else "bci")
               for b in P.bcis]
    things += [(box_of(*e["box"]), f"item {e['id']}", "bci") for e in getattr(P, "extras", [])]
    things += [(box_of(*lp["box"]), f"lamp of {lp['track']}", "lamp") for lp in getattr(P, "lamps", [])]
    for box, what, kind in things:
        if kind != "mast" and (box[0] < 0 or box[1] < 0 or box[2] > P.size[0] or box[3] > P.size[1]):
            raise SchematicError(f"le labels: {what} lies outside the {P.size[0]}x{P.size[1]} px panel")
    standing = {f"block contents of {b['block']}": b["block"] for b in P.bcis if b.get("on_track")}
    standing.update({f"item {e['id']}": e["block"] for e in getattr(P, "extras", []) if e.get("on_track")})
    things += [(box_of(*m["box"]), f"mast {m['mast']}'s icon", "mast") for m in P.masts]
    seen = Grid()
    for i, (box, what, kind) in enumerate(things):
        for other, j in seen.near(box, 0):
            if {kind, things[j][2]} <= {"mast", "fixed"}:     # placed before the labels: le_masts judges those
                continue
            if "crowded" in (kind, things[j][2]):              # crowded_block_contents: overlaps allowed
                continue
            if boxes_overlap(box, other, -OVERLAP):
                raise SchematicError(f"le labels: {what} overlaps {things[j][1]}")
        seen.add(box, i)
    ink = track_ink(P, world)
    shapes = [(tuple(sh["centre"]), sh["r"]) for sh in P.shapes]
    for box, what, kind in things:
        if kind in ("mast", "lamp", "crowded"):     # a lamp stands on its own track on purpose
            continue
        if kind != "fixed":                 # a connector's letter stands in its circle on purpose
            for c, r in shapes:
                if point_gap(box, c) < r:
                    raise SchematicError(f"le labels: {what} lies over a circle (helix or connector end)")
        clear = 1.0 if kind == "fixed" else CLEAR - 0.01
        for _b, (a, b, on, blk) in ink.near(box, max(clear, TURNOUT_R)):
            if blk is not None and standing.get(what) == blk:     # a block contents icon on its own block's track
                continue
            if b is None:
                if kind != "fixed" and point_gap(box, a) < TURNOUT_R - 0.01:
                    raise SchematicError(f"le labels: {what} lies on {on}")
            elif within(a, b, box, clear):
                raise SchematicError(f"le labels: {what} lies on {on}")


# ---------------------------------------------------------------- XML

def bci_elements(P):
    """The <BlockContentsIcon> elements, one per placed block contents icon (le.to_xml)."""
    import xml.etree.ElementTree as ET
    return [ET.Element("BlockContentsIcon", {
        "blockcontents": b["block"], "x": str(b["xy"][0]), "y": str(b["xy"][1]), "level": "4",
        "forcecontroloff": "false", "hidden": "no", "positionable": "true", "showtooltip": "true",
        "editable": "true", "size": str(b["size"]), "style": "0", "red": "0", "green": "0", "blue": "0",
        "hasBackground": "no", "justification": "left", "selectable": "no", "fontFamily": "Dialog",
        "fontname": "Dialog", "class": BCI_CLASS}) for b in P.bcis]
