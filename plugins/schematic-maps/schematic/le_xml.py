"""The Layout Editor XML of a drawn panel (le.Panel): the <LayoutEditor> element with its turnouts, track segments,
anchors, end bumpers, labels, shapes, masts and block contents icons, as JMRI 5.16 reads them (to_xml, write), and a
one-line summary. Import le, not this module: le imports it once its own names are defined.
"""
import math
import xml.etree.ElementTree as ET
from collections import defaultdict

from . import le_labels
from .core import SchematicError
from .le import (  # le's own names (le imports this module last)
    check_connections, CHROME, r1, written_idents,
)


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
