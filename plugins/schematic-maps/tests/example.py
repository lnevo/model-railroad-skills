"""A made-up railroad, track only, written out as the files the tool reads.

The Pine Hollow & Eastern is invented for the tests and has nothing to do with any real plan. It has:

  - a yard ladder (switches 11, 12, 13) off a lead from switch 1,
  - a double crossover (6) between a main and a passing track,
  - a switch the plan does not hold, added by the plan overrides (8, with an engine spur),
  - a switch in the plan that was never built (T18, removed by the plan overrides),
  - a loop (switch 5, a balloon track that returns to its own switch),
  - two levels, joined by a rise (cut into connector A), and a helix track named Summit at the end of each,
  - masts on a turnout leg, on an anchor, and on a ladder link that is drawn all slope.

`write(folder)` writes the plan export (plan.xml), the plan parts (parts.json), the Layout Editor panel
(panel.xml), the two CSV files that give the panel's switch numbers and block lengths, and the layer files.
Everything is computed from the table below, so the files can be regenerated and compared.

Coordinates are centimetres, y down. A switch faces east (points on its west side) or west. The diverging
leg C leaves on the right of travel from A to B for hand R and on the left for hand L.
"""
import csv
import json
import math
from pathlib import Path

PX = 120 / 25.4       # AnyRail's export is 120 px per inch of plan
HALF, SIDE = 12.0, 6.0

# id: (label after the plan overrides, plan part index, centre, facing, hand, height)
SWITCHES = {
    "S1": ("1", 10, (100, 300), "E", "R", 0),
    "S2": ("2", 12, (260, 300), "E", "R", 0),
    "S3": ("3", 16, (520, 300), "W", "L", 0),
    "S7": ("7", 18, (330, 308), "E", "R", 0),        # in the plan, never built
    "S4": ("4", 20, (680, 300), "E", "R", 0),
    "S5": ("5", 22, (760, 340), "E", "R", 0),
    "L11": ("11", 40, (190, 390), "E", "R", 0),
    "L12": ("12", 42, (230, 410), "E", "R", 0),
    "L13": ("13", 44, (270, 430), "E", "R", 0),
    "U1": ("21", 30, (900, 300), "E", "R", 15),
    "U2": ("22", 32, (1100, 300), "E", "L", 15),
}
DX = ("DX", ("6", 14, (400, 306), 0))      # a double crossover: centre, corner B at +20,-6, corner C at +20,+6

# tracks: (a, leg, b, leg, block name, section, extra points)
TRACKS = [
    ("W", "E", "S1", "A", "West Lead", "Mainline", []),
    ("S1", "B", "S2", "A", "Main West", "Mainline", []),
    ("S1", "C", "L11", "A", "Yard Lead", "Branch", []),
    ("S2", "B", "DX", "A", "Main", "Mainline", []),
    ("S2", "C", "S7", "A", "Passing", "Branch", [(300, 340)]),
    ("S7", "B", "DX", "D", "Passing", "Branch", [(360, 345)]),
    ("S7", "C", "RS", "E", "Runaround Spur", "Branch", []),
    ("DX", "B", "S3", "B", "Main", "Mainline", []),
    ("DX", "C", "S3", "C", "Passing", "Branch", [(465, 335)]),
    ("S3", "A", "S4", "A", "Main East", "Mainline", []),
    ("S4", "B", "U1", "A", "Rise", "Mainline", []),
    ("S4", "C", "S5", "A", "Loop Lead", "Mainline", []),
    ("S5", "B", "LP1", "E", "Loop", "Mainline", [(900, 340), (900, 520)]),
    ("S5", "C", "LP2", "E", "Loop", "Mainline", [(772, 520)]),
    ("L11", "B", "Y1", "E", "Y-1", "Branch", []),
    ("L11", "C", "L12", "A", "Link 11-12", "Branch", []),
    ("L12", "B", "Y2", "E", "Y-2", "Branch", []),
    ("L12", "C", "L13", "A", "Link 12-13", "Branch", []),
    ("L13", "B", "Y3", "E", "Y-3", "Branch", []),
    ("L13", "C", "Y4", "E", "Y-4", "Branch", []),
    ("U1", "B", "U2", "A", "Upper Main", "Mainline", []),
    ("U1", "C", "UB", "E", "Spur", "Branch", []),
    ("U2", "B", "UH", "E", "Upper East", "Mainline", []),
    ("U2", "C", "US", "E", "Siding", "Branch", []),
]
ENDS = {      # track ends: id -> position
    "W": (0, 300), "RS": (360, 330), "LP1": (900, 520), "LP2": (900, 520.5),
    "Y1": (400, 390), "Y2": (450, 410), "Y3": (500, 430), "Y4": (520, 450),
    "UB": (990, 330), "UH": (1300, 300), "US": (1220, 280),
}


def _unit(facing):
    return (1.0, 0.0) if facing == "E" else (-1.0, 0.0)


def leg(node, name):
    """Position of a leg of a switch (A points, B straight, C diverging) or of a double crossover corner."""
    if node == "DX":
        cx, cy = DX[1][2]
        return {"B": (cx + 20, cy - 6), "C": (cx + 20, cy + 6), "A": (cx - 20, cy - 6), "D": (cx - 20, cy + 6)}[name]
    _, _, (cx, cy), facing, hand, _ = SWITCHES[node]
    ux, uy = _unit(facing)
    nx, ny = -uy, ux                      # right of travel on a y-down screen
    sign = 1 if hand == "R" else -1
    a, b = (cx - ux * HALF, cy - uy * HALF), (cx + ux * HALF, cy + uy * HALF)
    return {"A": a, "B": b, "C": (b[0] + nx * SIDE * sign, b[1] + ny * SIDE * sign)}[name]


def where(node, name):
    return ENDS[node] if node in ENDS else leg(node, name)


def cm(track):
    a, la, b, lb, _, _, extra = track
    pts = [where(a, la)] + extra + [where(b, lb)]
    chord = math.dist(pts[0], pts[-1])
    return (chord + sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))) / 2


def px(p):
    return f"{p[0] * PX:.2f}"


# ---------------------------------------------------------------- the plan export
UPPER_NODES = {"U1", "U2", "UB", "UH", "US"}


def plan_xml():
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<layout-config>", '<LayoutEditor name="Plan">']
    for node, (label, idx, (cx, cy), facing, hand, z) in SWITCHES.items():
        b, c = leg(node, "B"), leg(node, "C")
        ty = "RH_TURNOUT" if hand == "R" else "LH_TURNOUT"
        out.append(f'<layoutturnout ident="{node}" type="{ty}" blockname="Track_0_{"Upper" if z else "Lower"}" '
                   f'xcen="{cx * PX:.2f}" ycen="{cy * PX:.2f}" xb="{b[0] * PX:.2f}" yb="{b[1] * PX:.2f}" '
                   f'xc="{c[0] * PX:.2f}" yc="{c[1] * PX:.2f}"/>')
    cx, cy = DX[1][2]
    b, c = leg("DX", "B"), leg("DX", "C")
    out.append(f'<layoutturnout ident="DX" type="DOUBLE_XOVER" blockname="Track_0_Lower" xcen="{cx * PX:.2f}" '
               f'ycen="{cy * PX:.2f}" xb="{b[0] * PX:.2f}" yb="{b[1] * PX:.2f}" xc="{c[0] * PX:.2f}" yc="{c[1] * PX:.2f}"/>')
    for i, t in enumerate(TRACKS):
        a, la, bn, lb, name, sect, extra = t
        c1 = (a, "TURNOUT_" + la) if a in SWITCHES or a == "DX" else (a, "POSITIONABLE_POINT")
        c2 = (bn, "TURNOUT_" + lb) if bn in SWITCHES or bn == "DX" else (bn, "POSITIONABLE_POINT")
        level = "Upper" if (UPPER_NODES & {a, bn}) and name != "Rise" else "Lower"
        ctrl = "".join(f'<controlpoint index="{k}" x="{p[0] * PX:.2f}" y="{p[1] * PX:.2f}"/>' for k, p in enumerate(extra))
        out.append(f'<tracksegment ident="TS{i}" blockname="Track_{i + 1}_{level}{sect}" connect1name="{c1[0]}" '
                   f'type1="{c1[1]}" connect2name="{c2[0]}" type2="{c2[1]}" dashed="no" '
                   f'mainline="{"yes" if sect == "Mainline" else "no"}">{ctrl}</tracksegment>')
    for pid, (x, y) in ENDS.items():
        seg = next(i for i, t in enumerate(TRACKS) if pid in (t[0], t[2]))
        out.append(f'<positionablepoint ident="{pid}" type="END_BUMPER" x="{x * PX:.2f}" y="{y * PX:.2f}" '
                   f'connect1name="TS{seg}"/>')
    out += ["</LayoutEditor>", "</layout-config>"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- plan parts (heights and part numbers)
def parts_json():
    """One entry per plan part: a switch has three or more end points (a double crossover four), a plain
    piece of track two. A switch's third point sits at its centre, so the average of its points is the centre."""
    nodes = {}
    for node, (label, idx, c, facing, hand, z) in SWITCHES.items():
        nodes[idx] = (z, [leg(node, "A"), leg(node, "B"), c])
    nodes[DX[1][1]] = (0, [leg("DX", k) for k in "ABCD"])
    parts = []
    for i in range(50):
        if i in nodes:
            z, pts = nodes[i]
            parts.append({"eps": [{"x": p[0], "y": p[1], "z": float(z)} for p in pts]})
        else:
            parts.append({"eps": [{"x": 3000.0 + i, "y": 0.0, "z": 0.0}, {"x": 3010.0 + i, "y": 0.0, "z": 0.0}]})
    return parts


# ---------------------------------------------------------------- the Layout Editor panel (lower level only)
# user name: (system name, binding). Heads are the (IHn) parts of the system name.
MASTS = {
    "M1A": ("IF$shsm:basic:one-searchlight(IH1)", ("switch", "S1", "A")),            # on a turnout leg
    "M2E": ("IF$shsm:basic:two-searchlight(IH2)(IH3)", ("anchor", "PPmid", "east")),  # on an anchor, bound east
    "M12C": ("IF$shsm:basic:one-searchlight(IH4)", ("switch", "L12", "C")),           # on a ladder link
    "M13B": ("IF$shsm:basic:one-searchlight(IH5)", ("switch", "L13", "B")),           # one of two stubs off switch 13
}
VIRTUAL = {"V2": ("IF$vsm:basic:one-searchlight", ("switch", "S2", "A"))}
NOT_ON_PANEL = {"S7", "RS", "LP1", "LP2", "U1", "U2", "UB", "UH", "US", "S4B"}


def panel_tracks():
    """The lower level's tracks as the panel has them: switch 7 was never built, so the passing track runs
    straight through; the rise and the upper level are on another panel; the loop has an anchor in it."""
    out = []
    for t in TRACKS:
        a, la, b, lb, name, sect, extra = t
        if {a, b} & {"S7", "RS", "LP1", "LP2"} or UPPER_NODES & {a, b}:
            continue
        out.append(t)
    out.append(("S2", "C", "DX", "D", "Passing", "Branch", []))
    return out


def panel_xml():
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<layout-config>", "<signalmasts>"]
    for name, (sysname, _) in MASTS.items():
        out.append(f"<signalmast><systemName>{sysname}</systemName><userName>{name}</userName></signalmast>")
    out.append("</signalmasts><virtualsignalmasts>")
    for name, (sysname, _) in VIRTUAL.items():
        out.append(f"<virtualsignalmast><systemName>{sysname}</systemName><userName>{name}</userName></virtualsignalmast>")
    out += ["</virtualsignalmasts>", '<LayoutEditor name="Panel">']
    ident = lambda n: "TO6" if n == "DX" else f"TO{SWITCHES[n][0]}"
    for node, (label, idx, c, facing, hand, z) in SWITCHES.items():
        if node in NOT_ON_PANEL:
            continue
        a, b, cc = leg(node, "A"), leg(node, "B"), leg(node, "C")
        kids = "".join(f"<signal{lg}Mast>{m}</signal{lg}Mast>" for m, (_, (kind, n, lg)) in {**MASTS, **VIRTUAL}.items()
                       if kind == "switch" and n == node)
        out.append(f'<layoutturnout ident="{ident(node)}" type="{"RH" if hand == "R" else "LH"}_TURNOUT" xcen="{c[0]}" '
                   f'ycen="{c[1]}" xa="{a[0]}" ya="{a[1]}" xb="{b[0]}" yb="{b[1]}" xc="{cc[0]}" yc="{cc[1]}">{kids}</layoutturnout>')
    cx, cy = DX[1][2]
    out.append(f'<layoutturnout ident="TO6" type="DOUBLE_XOVER" xcen="{cx}" ycen="{cy}" '
               + " ".join(f'x{k.lower()}="{leg("DX", k)[0]}" y{k.lower()}="{leg("DX", k)[1]}"' for k in "ABCD") + "/>")

    def ref(n, lg):
        return (ident(n), "TURNOUT_" + lg) if n in SWITCHES or n == "DX" else (f"PP{n}", "POSITIONABLE_POINT")

    segs, anchors, bumpers = [], [], []
    for t in panel_tracks():
        a, la, b, lb, name, sect, extra = t
        if name == "Main West":         # an anchor splits the run into two blocks
            mid = ((where(a, la)[0] + where(b, lb)[0]) / 2, where(a, la)[1])
            segs.append((f"{name} 1", ref(a, la), ("PPmid", "POSITIONABLE_POINT"), sect))
            segs.append((f"{name} 2", ("PPmid", "POSITIONABLE_POINT"), ref(b, lb), sect))
            anchors.append(("PPmid", mid, f"TS{len(segs) - 2}", f"TS{len(segs) - 1}", "M2E"))
        else:
            segs.append((name, ref(a, la), ref(b, lb), sect))
        for n in (a, b):
            if n in ENDS:
                bumpers.append(n)
    segs.append(("Loop 1", ref("S5", "B"), ("PPloop", "POSITIONABLE_POINT"), "Mainline"))
    segs.append(("Loop 2", ("PPloop", "POSITIONABLE_POINT"), ref("S5", "C"), "Mainline"))
    anchors.append(("PPloop", (900, 520), f"TS{len(segs) - 2}", f"TS{len(segs) - 1}", None))
    for i, (name, c1, c2, sect) in enumerate(segs):
        out.append(f'<tracksegment ident="TS{i}" blockname="{name}" connect1name="{c1[0]}" type1="{c1[1]}" '
                   f'connect2name="{c2[0]}" type2="{c2[1]}" mainline="{"yes" if sect == "Mainline" else "no"}"/>')
    for pid, (x, y), s1, s2, mast in anchors:
        east = f' eastboundsignalmast="{mast}"' if mast else ""
        out.append(f'<positionablepoint ident="{pid}" type="ANCHOR" x="{x}" y="{y}" connect1name="{s1}" connect2name="{s2}"{east}/>')
    for n in dict.fromkeys(bumpers):
        i = next(i for i, s in enumerate(segs) if f"PP{n}" in (s[1][0], s[2][0]))
        out.append(f'<positionablepoint ident="PP{n}" type="END_BUMPER" x="{ENDS[n][0]}" y="{ENDS[n][1]}" connect1name="TS{i}"/>')
    out += ["</LayoutEditor>", "</layout-config>"]
    return "\n".join(out) + "\n"


def numbers_rows():
    """The panel's switch numbers: ident to number."""
    rows = [("le_ident", "switch")]
    rows += [(f"TO{v[0]}", v[0]) for k, v in SWITCHES.items() if k not in NOT_ON_PANEL]
    return rows + [("TO6", "6")]


def lengths_rows():
    """Block lengths in inches for every block on the panel, from the track's own length."""
    rows, cms = [("user_name", "inches")], {}
    for t in panel_tracks():
        cms[t[4]] = cms.get(t[4], 0) + cm(t)
    cms["Loop"] = cm(next(t for t in TRACKS if t[4] == "Loop")) + cm(TRACKS[13])
    for name, c in cms.items():
        if name == "Main West":
            rows += [("Main West 1", round(c / 2 / 2.54, 1)), ("Main West 2", round(c / 2 / 2.54, 1))]
        elif name == "Loop":
            rows += [("Loop 1", round(c / 2 / 2.54, 1)), ("Loop 2", round(c / 2 / 2.54, 1))]
        else:
            rows.append((name, round(c / 2.54, 1)))
    return rows


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)


# ---------------------------------------------------------------- layer files
OVERRIDES = {
    "_layer": 1,
    "left_end": None,
    "helix": {"1": "Summit", "22": "Summit"},
    "helix_side": "west",
    "helix_to": "the other level",
    "level_title": "Lower level",
    "mast_dir_pattern": None,
    "signals_planned": [],
    "levels": {"bands": [{"name": "Lower level", "below": 5}, {"name": "Upper level", "below": 99}]},
    "edits": [
        {"op": "relabel", "map": {"T10": "1", "T12": "2", "T14": "6", "T16": "3", "T18": "7", "T20": "4", "T22": "5",
                                  "T40": "11", "T42": "12", "T44": "13", "T30": "21", "T32": "22"}},
        {"op": "remove", "switches": ["7"]},
        {"op": "switch", "label": "8", "hand": "R", "on": ["3", "4"], "cm_from_first": 60, "points_toward": "4",
         "c": {"end": "Engine Spur", "cm": 70}, "source": "owner", "why": "built after the plan was drawn"},
        {"op": "name", "tracks": [["1", "2", "Main West"], ["2", "6", "Main", "B", "main"], ["2", "6", "Passing", "C"],
                                  ["6", "3", "Main", "B", "main"], ["6", "3", "Passing", "C"],
                                  ["1", "11", "Yard Lead"], ["4", "21", "Rise", "B", "main"],
                                  ["21", "22", "Upper Main"], ["11", "12", "Link 11-12"], ["12", "13", "Link 12-13"],
                                  ["4", "5", "Loop Lead"], ["5", "5", "Loop"]]},
        {"op": "end", "ends": [["11", "B", "Y-1", "bumper", None], ["12", "B", "Y-2", "bumper", None],
                               ["13", "B", "Y-3", "bumper", None], ["13", "C", "Y-4", "bumper", None],
                               ["21", "C", "Spur", "bumper", None], ["22", "C", "Siding", "bumper", None]]},
    ],
    "main_route": [["Summit", "1"], ["1", "2", "direct"], ["2", "6"], ["6", "3"], ["3", "8"],
                   ["8", "4"], ["4", "21", "direct"], ["21", "22", "direct"], ["22", "Summit"]],
}

PREFERENCES = {"_layer": 3, "title": ["Pine Hollow & Eastern", "Schematic diagram", "Made-up example"],
               "system_title": ["Pine Hollow & Eastern", "Both levels", "Made-up example"], "num_px": 6.5,
               "band_order": ["Upper", "Lower"], "equal_width": True}


def write(folder):
    """Write every fixture file into `folder` and return their paths by name."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    texts = {"plan.xml": plan_xml(), "parts.json": json.dumps(parts_json()), "panel.xml": panel_xml(),
             "example.plan_overrides.json": json.dumps({k: v for k, v in OVERRIDES.items() if v is not None}, indent=1),
             "example.preferences.json": json.dumps(PREFERENCES, indent=1)}
    for name, text in texts.items():
        (folder / name).write_text(text)
    write_csv(folder / "numbers.csv", numbers_rows())
    write_csv(folder / "lengths.csv", lengths_rows())
    return {p.name: p for p in folder.iterdir()}
