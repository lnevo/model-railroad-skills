"""Signal reader: masts as layer 1 facts, generated from the Layout Editor panel, never typed by hand (rule R13).

For every mast bound on the panel (at a turnout leg, an anchor or an end bumper) this finds the run of
track it stands on and the switch or track end its governed movement is heading for, then finds the same
run in the schematic graph (the plan plus the plan overrides), matched by the switch numbers at its ends,
the leg ports and the track names. One entry per mast:

  {"mast": "12R", "toward": "7", "run": ["7", "9"], "names": ["Main"], "cm_from_toward": 0,
   "edge_cm": 551.9, "dir": "east", "kind": "field", "heads": 1, "source": "le_panel"}

cm_from_toward and edge_cm are both the panel's lengths, so their ratio is the mast's share of the run; the
drawing applies that share to the run as drawn.

Where the masts are bound (JMRI's own model):
  - a turnout's signalAMast .. signalDMast: a mast standing on that leg, governing movement toward the turnout;
  - a positionable point's east and west bound masts: the mast governs movement in that direction;
    which side of the anchor is east follows JMRI's isAtWestEndOfAnchor rule (east_side below);
  - an end bumper's bound mast governs the move away from the buffer stop.

kind: field (a mast with signal heads), virtual (exists for Dispatcher only; not drawn) or planned (named in
the overrides' "signals_planned": placeholders with no hardware). Direction comes from the binding (the
anchor's slot); for a mast on a turnout leg it comes from the leg's direction on the panel, and may be set by
a name rule: the overrides' "mast_dir_pattern" is a regular expression whose first group is L or R (R for
east), "mast_prefix" is text dropped from the front of each mast's name. A name that disagrees with its
binding is reported. Masts that cannot be placed are listed under "unplaced" and left out.
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from . import edits, panel_reader


def east_side(pp, segs, coords):
    """The segment on the east side of an anchor, by JMRI's own rule (LayoutEditorTools.isAtWestEndOfAnchor):
    compare the far ends of the two segments; mostly horizontal track: east is larger x; mostly vertical:
    east is larger y (south); otherwise horizontal."""
    s1, s2 = pp.get("connect1name"), pp.get("connect2name")
    far = []
    for s in (s1, s2):
        t = segs[s]
        other = t.get("connect2name") if t.get("connect1name") == pp.get("ident") else t.get("connect1name")
        typ = t.get("type2") if t.get("connect1name") == pp.get("ident") else t.get("type1")
        far.append(coords(other, typ))
    dx, dy = far[0][0] - far[1][0], far[0][1] - far[1][1]
    if abs(dy) > 2 * abs(dx):
        return s1 if dy > 0 else s2
    return s1 if dx > 0 else s2


def read(tables, graph, overrides, numbers=None, lengths=None, panel_name=None):
    """The signals file as a dict. `graph` is the schematic graph (dict), `overrides` the plan overrides (dict)."""
    root = ET.parse(tables).getroot()
    panel = panel_reader.find_panel(root, panel_name)
    le = panel_reader.read(tables, numbers, lengths, panel_name)
    LN = le["nodes"]
    tos = {t.get("ident"): t for t in panel.iter("layoutturnout")}
    segs = {s.get("ident"): s for s in panel.iter("tracksegment")}
    pps = {p.get("ident"): p for p in panel.iter("positionablepoint")}

    def coords(ident, typ):
        if typ.startswith("TURNOUT"):
            t = tos[ident]
            leg = typ[-1].lower()
            return float(t.get("x" + leg)), float(t.get("y" + leg))
        p = pps[ident]
        return float(p.get("x")), float(p.get("y"))

    # what each mast is
    masts = {}
    for m in root.iter("signalmast"):
        name = m.findtext("userName")
        masts[name] = dict(kind="field", heads=max(1, len(re.findall(r"\(IH", m.findtext("systemName") or ""))))
    for m in root.iter("virtualsignalmast"):
        masts[m.findtext("userName")] = dict(kind="virtual", heads=1)

    ov = overrides
    planned = set(ov.get("signals_planned", []))
    prefix = ov.get("mast_prefix", "")
    dir_pattern = re.compile(ov["mast_dir_pattern"]) if ov.get("mast_dir_pattern") else None

    # where each mast is on the panel's graph: (edge, toward node, cm from that node)
    edge_at = {}
    for e in le["edges"]:
        edge_at[(e["u"], e["up"])] = e
        edge_at[(e["v"], e["vp"])] = e
    portmap = {}
    for ident, t in tos.items():
        if t.get("type") == "DOUBLE_XOVER":
            for leg in "ABCD":
                portmap[(ident, leg)] = (ident, leg)
        elif t.get("type") in ("RH_XOVER", "LH_XOVER"):
            rh = t.get("type") == "RH_XOVER"
            top, bot = (("A", "B"), ("C", "D")) if rh else (("B", "A"), ("D", "C"))
            for half, (pl, nl) in (("a", top), ("b", bot)):
                portmap[(ident, pl)] = (ident + half, "A")
                portmap[(ident, nl)] = (ident + half, "B")
        else:
            for leg in "ABC":
                portmap[(ident, leg)] = (ident, leg)

    found, problems = [], []
    for ident, t in tos.items():
        for leg in "ABCD":
            name = t.findtext(f"signal{leg}Mast")
            if not name:
                continue
            node, port = portmap[(ident, leg)]
            e = edge_at.get((node, port))
            if e is None:
                problems.append(f"{name}: no track at {ident} leg {leg}")
                continue
            found.append((name, e, node, 0.0, None))
    anchor_edge = {}
    for e in le["edges"]:
        for a, cm, seg_u, seg_v in e.get("anchors", []):
            anchor_edge[a] = (e, cm, seg_u, seg_v)
    for ident, p in pps.items():
        for slot in ("east", "west"):
            name = p.get(slot + "boundsignalmast")
            if not name:
                continue
            if p.get("type") == "END_BUMPER":     # a mast at a buffer stop governs the move away from it
                e = next((x for x in le["edges"] if x["v"] == "END:" + ident or x["u"] == "END:" + ident), None)
                if e is None:
                    problems.append(f"{name}: bumper {ident} not on the graph")
                    continue
                toward = e["u"] if e["v"] == "END:" + ident else e["v"]
                found.append((name, e, toward, e["cm"], slot))
                continue
            if ident not in anchor_edge:
                problems.append(f"{name}: anchor {ident} not on the graph")
                continue
            e, cm, seg_u, seg_v = anchor_edge[ident]
            east = east_side(p, segs, coords)
            going_east = slot == "east"
            heading_v = (east == seg_v) == going_east       # travel toward v's side of the anchor
            toward = e["v"] if heading_v else e["u"]
            found.append((name, e, toward, (e["cm"] - cm) if heading_v else cm, slot))

    # the same runs on the schematic graph
    g = json.loads(json.dumps(graph))
    edits.apply_edits(g, ov.get("edits", []))
    SN = g["nodes"]
    # a switch the overrides moved is labelled with a star (7*) on the schematic but not on the panel
    lab = lambda N, n: (N[n].get("label") or "").rstrip("*") if N[n]["kind"] != "end" else ""
    clean = lambda names: {re.sub(r"^Track ", "", x) for x in names}

    def match(e, toward):
        """The schematic run for a panel run. Returns (run, node it heads for, tie)."""
        want = sorted((lab(LN, e["u"]), lab(LN, e["v"])))
        names = clean(e["names"])
        scored = []
        for s in g["edges"]:
            have = sorted((lab(SN, s["u"]), lab(SN, s["v"])))
            if have != want:
                continue
            ports = {(lab(SN, s["u"]), s["up"]), (lab(SN, s["v"]), s["vp"])}
            same = len(ports & {(lab(LN, e["u"]), e["up"]), (lab(LN, e["v"]), e["vp"])})
            scored.append((same + len(names & clean(s["names"])) - abs(s["cm"] - e["cm"]) / 1000, s))
        if not scored:
            return None, None, False
        scored.sort(key=lambda t: -t[0])
        tie = len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 1e-9
        s = scored[0][1]
        t = lab(LN, toward)
        tn = s["u"] if lab(SN, s["u"]) == t else s["v"]
        if lab(SN, s["u"]) == lab(SN, s["v"]):      # both ends carry the same number: keep the panel's sense
            tn = s["u"] if toward == e["u"] else s["v"]
        return s, tn, tie

    rows = []
    for name, e, toward, cm, slot in found:
        short = name[len(prefix):] if prefix and name.startswith(prefix) else name
        info = masts.get(name, dict(kind="field", heads=1))
        kind = "planned" if short in planned else info["kind"]
        m = dir_pattern.match(short) if dir_pattern else None
        named = {"R": "east", "L": "west"}[m.group(1)] if m else None
        d = slot or named or leg_dir(LN, e, toward)
        if named and slot and named != slot:
            problems.append(f"{short}: name says {named}, binding says {slot}")
        s, tn, tie = match(e, toward)
        if s is None:
            problems.append(f"{short}: run {lab(LN, e['u']) or 'end'}-{lab(LN, e['v']) or 'end'} not in the schematic")
            continue
        if tie:
            problems.append(f"{short}: run {lab(LN, e['u']) or 'end'}-{lab(LN, e['v']) or 'end'} matches more than one run; "
                            "the first was taken. Name the tracks in the overrides to tell them apart")
        far = s["v"] if tn == s["u"] else s["u"]
        rows.append(dict(mast=short, toward=lab(SN, tn) or SN[tn].get("label", ""), run=[lab(SN, tn), lab(SN, far)],
                         names=s["names"], edge_cm=e["cm"], cm_from_toward=round(min(cm, e["cm"]), 1), dir=d,
                         kind=kind, heads=info["heads"], source="le_panel", _edge=s["id"], _toward_node=tn))
    rows.sort(key=lambda r: (_num(r["mast"]), r["mast"]))
    return dict(schema="schematic.signals/1", source=Path(tables).name, signals=rows, unplaced=problems)


def _num(name):
    m = re.match(r"\d+", name)
    return int(m.group()) if m else 10 ** 9


def leg_dir(LN, e, toward):
    """East or west for a mast on a turnout leg, from the way the leg points on the panel (the move runs
    toward the turnout): mostly horizontal, east is larger x; mostly vertical, east is larger y (JMRI's rule)."""
    n = LN[toward]
    port = e["up"] if e["u"] == toward else e["vp"]
    d = n.get("dirs", {}).get(port)
    if not d:
        return "east"
    dx, dy = -d[0], -d[1]
    if abs(dy) > 2 * abs(dx):
        return "east" if dy > 0 else "west"
    return "east" if dx >= 0 else "west"


def write(path, signals):
    Path(path).write_text(json.dumps(signals, indent=1))
