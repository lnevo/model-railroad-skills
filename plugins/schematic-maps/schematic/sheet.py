"""Sheet: the single entry point. Plan graphs plus the layer files in one folder become bands and one SVG page.

    inputs = [("plan_a.json", "yard"), ("plan_b.json", "main")]     # (graph, name of its layer files)
    sheet = build(inputs, data_dir)
    sheet.write("out.svg")

Every input is treated the same way: its layer files are read (layers.py), its plan overrides are applied,
its helix tracks and main route are marked, and a graph that has `levels` in its overrides is cut into one
band per level. The options of the last input also set the page (title, band order, widths), unless a
`sheet.preferences.json` is present, which is merged over them.
"""
import copy
import json
from pathlib import Path

from . import columns, direction, draw, edits, layers, layout
from .core import SchematicError
from .draw import DEFAULTS

ROOM_ROUNDS = 3     # how many times labels may claim more room before the sheet is drawn as it stands


class Sheet:
    def __init__(self, bands, opts, log):
        self.bands, self.opts, self.log = bands, opts, log
        self._svg = None

    def svg(self):
        if self._svg is None:           # drawing is the slow part; the room check and write share one render
            self._svg = draw.page_svg(self.bands, dict(self.opts, title=self.opts.get("system_title", self.opts["title"])))
        return self._svg

    def write(self, out):
        Path(out).write_text(self.svg())

    def faults(self):
        """{band title: [drawing fault text]}: lines that cross or lie on top of each other."""
        return {title: layout.check(band) for title, band, _ in self.bands}


def options(name, data, preferences=True, hints=False):
    return dict(DEFAULTS, **layers.load(name, data, preferences, hints))


def mark_helix(g, opts):
    """Each helix switch named in layer 1 gets its longest track to a track end marked as the helix track."""
    N = g["nodes"]
    for ref, name in opts.get("helix", {}).items():
        sw = edits.by_label(g, ref)
        ends = [(e, e["v"] if e["u"] == sw else e["u"]) for e in g["edges"] if sw in (e["u"], e["v"])]
        ends = [(e, n) for e, n in ends if N[n]["kind"] == "end"]
        if not ends:
            continue
        e, end = max(ends, key=lambda t: t[0]["cm"])
        e["names"], e["main"] = [name], True
        N[end].update(sub="helix", to=opts.get("helix_to", ""), side=opts.get("helix_side", "west"))
    if opts.get("helix_side"):         # helix ends made by an `end` edit take the level's helix side too
        for d in N.values():
            if d["kind"] == "end" and d.get("sub") == "helix" and not d.get("side"):
                d["side"] = opts["helix_side"]


def mark_ways(g, specs):
    """Layer 1 `track_directions`: [from, to] is a track trains run one way on, from switch `from` toward `to`;
    [a, b, "both"] runs both ways. The way rides on the track through the cut into levels and folds."""
    for spec in specs:
        extra = list(spec[2:]) if isinstance(spec, list) else []
        both = extra[:1] == ["both"]
        rest = extra[1:] if both else extra
        port = rest[0] if rest else None
        if not isinstance(spec, list) or len(spec) < 2 or len(rest) > 1 or port not in (None, "A", "B", "C", "D"):
            raise SchematicError('track_directions entry must be [from, to], [from, to, leg] or [a, b, "both"(, leg)], '
                                 f"leg being the switch leg at the first switch (A to D), not {spec!r}")
        e, n0, n1 = edits.edge_between(g, str(spec[0]), str(spec[1]), port, unique=True)
        e["way"] = "both" if both else (n0, n1)


def level_bands(g, opts, level_name):
    """[(title, subgraph)] for one input: cut into levels when layer 1 says how, else one band."""
    if opts.get("levels") and opts["levels"].get("bands"):
        return edits.split_levels(g, opts["levels"])
    return [(opts.get("level_title", level_name.replace("_", " ").capitalize() + " level"), g)]


def build_input(graph, name, opts, tracks, log):
    """The bands of one input: [(title, band, options)]."""
    opts["helix_tracks"] = tracks
    g = copy.deepcopy(graph if isinstance(graph, dict) else json.load(open(graph)))
    edits.apply_edits(g, opts["edits"])
    mark_helix(g, opts)
    if opts.get("main_route"):
        keep = {e["id"] for e in g["edges"] if e["names"] and e["main"]}
        edits.mark_main(g, opts["main_route"])
        for e in g["edges"]:
            e["main"] = e["main"] or e["id"] in keep
    mark_ways(g, opts.get("track_directions", ()))
    rail = {}
    if opts.get("main_route") and (opts.get("facing_letters") or opts.get("direction_arrows")):
        rail, conflicts = direction.east(g, opts["main_route"], lambda r: edits.by_label(g, r))
        line = (f"{name}: main track turns back at " +
                ", ".join(sorted(g["nodes"][n].get("label") or n for n in conflicts)))
        if conflicts and line not in log:   # build_input runs again in each room round: say it once
            log.append(line)
    out = []
    for title, sub in level_bands(g, opts, name):
        w = []
        band = layout.layout(sub, opts, w)
        mine = {n: v for n, v in rail.items() if n in band["nodes"]}
        if opts.get("facing_letters") or opts.get("direction_arrows"):
            band["rail"] = dict(direction.drawn(band, direction.east_left(band, rail)), **mine)
        if opts.get("facing_letters"):
            for n, letter in direction.letters(band["nodes"], band["rail"]).items():
                band["nodes"][n]["facing"] = letter
        out.append((title, band, opts))
        log.append(f"{title}: {len(layout.faults(band))} drawing faults {w}")
    draw.check_control_points(opts, out, name)
    columns.check_run_hints([b for _, b, _ in out], opts)
    return out


def in_order(per_input, optlist):
    """Every input's bands, top to bottom by the last input's `band_order`."""
    rank = {w: i for i, w in enumerate(optlist[-1].get("band_order", []))}
    return sorted((b for bands in per_input for b in bands), key=lambda b: rank.get(draw.band_key(b[0]), 9))


def build_bands(inputs, optlist, log):
    """The drawn bands, top to bottom: [(title, band, options)]."""
    tracks = sorted({v for o in optlist for v in o.get("helix", {}).values()})
    return in_order([build_input(g, name, o, tracks, log) for (g, name), o in zip(inputs, optlist)], optlist)


def build(inputs, data, preferences=True, hints=False):
    """Read and lay out every input. `inputs` is a list of (graph or path to its JSON, layer-file name)."""
    optlist = [options(name, data, preferences, hints) for _, name in inputs]
    sheet_file = Path(data) / "sheet.preferences.json"
    if preferences and sheet_file.exists():        # the sheet's own look reaches every band, not just the last input
        sheet_prefs = json.load(open(sheet_file))
        optlist = [layers.merge(o, sheet_prefs) for o in optlist]
    for o in optlist[:-1]:
        o["helix_style"] = optlist[-1].get("helix_style", "box")
    optlist[-1].setdefault("helix_style", "box")
    tracks = sorted({v for o in optlist for v in o.get("helix", {}).values()})
    logs = [[] for _ in inputs]
    per = [build_input(g, name, o, tracks, logs[i]) for i, ((g, name), o) in enumerate(zip(inputs, optlist))]
    grown = []
    best = None
    for rnd in range(ROOM_ROUNDS + 1):
        # R12: a label with no free position claims a cell on its track, and that input is laid out again.
        sheet = Sheet(in_order(per, optlist), optlist[-1], [line for lg in logs for line in lg] + grown)
        sheet.svg()
        left = sum(len(band.get("unplaced", ())) for bands in per for _, band, _ in bands)
        if best is not None and left >= best[0]:
            break                       # more room did not help: keep the earlier drawing
        best = (left, sheet)
        claims = [{band["strands"][sid]["edge"] for _, band, _ in bands for sid in band.get("short", ())}
                  for bands in per]
        if not left or not any(claims) or rnd == ROOM_ROUNDS:
            break
        for i, edges_ in enumerate(claims):
            if not edges_:
                continue
            room = optlist[i].setdefault("_room", {})
            for e in sorted(edges_):
                room[e] = room.get(e, 0) + 1
            grown.append(f"R12 round {rnd + 1}: {inputs[i][1]} runs lengthened for labels: {', '.join(sorted(edges_))}")
            logs[i] = []
            per[i] = build_input(inputs[i][0], inputs[i][1], optlist[i], tracks, logs[i])
    left, sheet = best
    if left:
        sheet.log.append(f"R12: {left} labels still have no free position")
    return sheet
