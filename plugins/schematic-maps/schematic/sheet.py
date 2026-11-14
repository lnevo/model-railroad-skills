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

from . import draw, edits, layers, layout
from .draw import DEFAULTS


class Sheet:
    def __init__(self, bands, opts, log):
        self.bands, self.opts, self.log = bands, opts, log

    def svg(self):
        return draw.page_svg(self.bands, dict(self.opts, title=self.opts.get("system_title", self.opts["title"])))

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


def level_bands(g, opts, level_name):
    """[(title, subgraph)] for one input: cut into levels when layer 1 says how, else one band."""
    if opts.get("levels") and opts["levels"].get("bands"):
        return edits.split_levels(g, opts["levels"])
    return [(opts.get("level_title", level_name.replace("_", " ").capitalize() + " level"), g)]


def build_bands(inputs, optlist, log):
    """The drawn bands, top to bottom: [(title, band, options)]."""
    bands = []
    tracks = sorted({v for o in optlist for v in o.get("helix", {}).values()})
    for (graph, name), opts in zip(inputs, optlist):
        opts["helix_tracks"] = tracks
        g = copy.deepcopy(graph if isinstance(graph, dict) else json.load(open(graph)))
        edits.apply_edits(g, opts["edits"])
        mark_helix(g, opts)
        if opts.get("main_route"):
            keep = {e["id"] for e in g["edges"] if e["names"] and e["main"]}
            edits.mark_main(g, opts["main_route"])
            for e in g["edges"]:
                e["main"] = e["main"] or e["id"] in keep
        for title, sub in level_bands(g, opts, name):
            w = []
            band = layout.layout(sub, opts, w)
            bands.append((title, band, opts))
            log.append(f"{title}: {len(layout.faults(band))} drawing faults {w}")
    rank = {w: i for i, w in enumerate(optlist[-1].get("band_order", []))}      # top to bottom
    bands.sort(key=lambda b: rank.get(b[0].split()[0], 9))
    return bands


def build(inputs, data, preferences=True, hints=False):
    """Read and lay out every input. `inputs` is a list of (graph or path to its JSON, layer-file name)."""
    optlist = [options(name, data, preferences, hints) for _, name in inputs]
    for o in optlist[:-1]:
        o["helix_style"] = optlist[-1].get("helix_style", "box")
    optlist[-1].setdefault("helix_style", "box")
    sheet_file = Path(data) / "sheet.preferences.json"
    if preferences and sheet_file.exists():
        optlist[-1] = layers.merge(optlist[-1], json.load(open(sheet_file)))
    log = []
    bands = build_bands(inputs, optlist, log)
    return Sheet(bands, optlist[-1], log)
