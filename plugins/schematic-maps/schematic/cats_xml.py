"""Writing a CATS panel as Designer XML."""

import copy
import xml.etree.ElementTree as ET

from .cats_bind import DISCIPLINES
from .cats_grid import EDGE_ORDER, ENDS, neighbour
from .core import SchematicError

__all__ = [
    "boundaries", "dangling", "lone_blocks", "HEADER_FONTS", "header_from", "set_io", "to_xml", "write"
]


def boundaries(P):
    """{(cell, edge): block root} of every edge where one block ends and another (or a joined end) begins."""
    out = {}
    for cell, tracks in P.cells.items():
        for edge in EDGE_ORDER:
            mine = {P.find(b) for t, b in tracks.items() if edge in ENDS[t]}
            if not mine:
                continue
            far, fedge = P.shared.get((cell, edge)) or neighbour(cell, edge)
            theirs = {P.find(b) for t, b in P.cells.get(far, {}).items() if fedge in ENDS[t]}
            if theirs and mine != theirs:
                if (cell, edge) in P.points or (cell, edge) in P.crossings or len(mine) > 1:
                    raise SchematicError(f"cell {cell} edge {edge}: a block boundary on switch points or a crossing; "
                                         "CATS would drop the points")
                out[(cell, edge)] = next(iter(mine))
    return out


def dangling(P, cell, edge):
    """True when no track continues across this edge of `cell`: a track end."""
    if (cell, edge) in P.shared:
        return False
    far, fedge = neighbour(cell, edge)
    return not any(fedge in ENDS[t] for t in P.cells.get(far, {}))


def lone_blocks(P, bounds):
    """{(cell, edge): block root} naming each block that has no boundary at one of its track ends."""
    have = set(bounds.values())
    out = {}
    for cell in sorted(P.cells, key=lambda c: (c[1], c[0])):
        for edge in EDGE_ORDER:
            blks = {P.find(b) for t, b in P.cells[cell].items() if edge in ENDS[t]}
            if len(blks) == 1 and dangling(P, cell, edge):
                blk = next(iter(blks))
                if blk not in have:
                    out[(cell, edge)] = blk
                    have.add(blk)
    missing = set(P.names) - have
    if missing:
        raise SchematicError("blocks with no boundary and no track end to name them on: " +
                             ", ".join(sorted(P.names[b] for b in missing)))
    return out


HEADER_FONTS = [
    ("FONT_LABEL", "Grid Labels", "-1", "11", "PLAIN"),
    ("FONT_TRAIN", "Train Identities", "-1", "11", "PLAIN"),
    ("ONCALL", "On Call Train", "-4144960", "11", "PLAIN"),
    ("ACTIVE", "Active Train", "-14336", "11", "PLAIN"),
    ("SELECTED", "Selected Train", "-16711681", "11", "PLAIN"),
    ("TIEDUP", "Tied Down Train", "-65281", "11", "PLAIN"),
    ("FONT_TITLE", "Panel Title", "-1", "13", "BOLD"),
]


def header_from(path):
    """The SIGNALTEMPLATE, JMRINAME and COLORDEFINITION elements of an existing CATS panel, to copy into a generated
    one: the physical signal templates its masts name, the JMRI device prefixes its IOSPECs use, and its colours.
    The colours matter for blocks with no occupancy sensors: CATS paints such dark territory in the DARK colour,
    grey unless the panel says otherwise (cats/layout/items/Track.java setBlock, gui/PaletteFactory.java)."""
    try:
        src = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        raise SchematicError(f"{path}: cannot read it as a CATS panel ({e})") from None
    if src.tag != "DOCUMENT":
        raise SchematicError(f"{path}: not a CATS panel (its root is {src.tag})")
    return [el for el in src if el.tag in ("SIGNALTEMPLATE", "JMRINAME", "COLORDEFINITION")]


def set_io(parent, tag, io):
    io = dict(io)
    ET.SubElement(ET.SubElement(parent, tag), "IOSPEC", **{k: v for k, v in io.items() if k != "command"}).text = \
        io["command"]


def to_xml(P, discipline="CTC", header=(), window=None):
    """The panel as a CATS Designer document (an ElementTree root). `header`: SIGNALTEMPLATE and JMRINAME
    elements to copy in (header_from). `window`: (width, height) in pixels of the window CATS opens the panel in,
    placed at the screen's top left; CATS has no zoom, so a window smaller than the panel crops it."""
    cols, rows = P.size()
    root = ET.Element("DOCUMENT", VERSION="3.1")
    if window:
        w, h = window
        if w < 1 or h < 1:
            raise SchematicError(f"window {w}x{h}: both sides must be at least 1 pixel")
        root.set("WIDTH", str(int(w)))
        root.set("HEIGHT", str(int(h)))
        root.set("X", "0")
        root.set("Y", "0")
    for key, name, color, size, style in HEADER_FONTS:
        ET.SubElement(root, "FONTDEFINITION", FONTKEY=key, FONTNAME=name, FONTCOLOR=color, FONTSIZE=size,
                      FONTSTYLE=style)
    for el in header:
        if el.tag == "COLORDEFINITION":
            root.append(copy.deepcopy(el))
    templates = set()
    for el in header:
        if el.tag == "SIGNALTEMPLATE":
            root.append(copy.deepcopy(el))
            templates.add(el.get("TEMPLATENAME"))
    missing = sorted({s["template"] for s in P.signals.values() if s["template"]} - templates)
    if missing:
        raise SchematicError(f"masts name signal template {', '.join(missing)}, which the panel has no "
                             "SIGNALTEMPLATE for (copy them in from a panel that has them)")
    ET.SubElement(root, "COMPRESSIONTAG")      # present = Compress Screen off
    ET.SubElement(root, "ROWWRAPTAG")          # present = Automatic Wrapping off
    for el in header:
        if el.tag == "JMRINAME":
            root.append(copy.deepcopy(el))
    plan = ET.SubElement(root, "TRACKPLAN", COLUMNS=str(cols), ROWS=str(rows))
    if discipline not in DISCIPLINES:
        raise SchematicError(f"discipline {discipline!r} is not one CATS reads: {', '.join(DISCIPLINES)}")
    bounds = boundaries(P)
    bounds.update(lone_blocks(P, bounds))
    stray = sorted(set(P.signals) - set(bounds))
    if stray:
        raise SchematicError("masts " + ", ".join(P.signals[s]["mast"] for s in stray) + " are not on a block boundary")
    for cell in sorted(set(P.cells) | set(P.labels), key=lambda c: (c[1], c[0])):
        sec = ET.SubElement(plan, "SECTION", X=str(cell[0]), Y=str(cell[1]))
        tracks = P.cells.get(cell, {})
        if tracks:
            grp = ET.SubElement(sec, "TRACKGROUP")
            for t in sorted(tracks, key=list(ENDS).index):
                ET.SubElement(grp, "TRACK").text = t
            for edge in EDGE_ORDER:
                if not any(edge in ENDS[t] for t in tracks):
                    continue
                se = ET.SubElement(sec, "SEC_EDGE", EDGE=edge)
                if (cell, edge) in P.signals:
                    sg = P.signals[(cell, edge)]
                    ss = ET.SubElement(se, "SECSIGNAL")
                    ss.text = sg["name"]
                    ET.SubElement(ss, "PANELSIGNAL", SIGLOCATION=sg["loc"], SIGORIENT=sg["orient"],
                                  SIGPANTYPE=sg["pantype"])
                    if sg["template"]:
                        ET.SubElement(ss, "PHYSIGNAL").text = sg["template"]
                if (cell, edge) in bounds:
                    if (cell, edge) in P.points or (cell, edge) in P.crossings:
                        raise SchematicError(f"cell {cell} edge {edge}: a block on switch points or a crossing")
                    # every boundary edge names its block in full: CATS keeps one Block per name (Block.findBlock)
                    blk = bounds[(cell, edge)]
                    bi = P.block_info.get(blk, {})
                    b = ET.SubElement(se, "BLOCK", NAME=P.names[blk])
                    if bi.get("station"):
                        b.set("STATION", bi["station"])
                    b.set("DISCIPLINE", bi.get("discipline") or discipline)
                    b.set("VISIBLE", "true")
                    if bi.get("occupied"):
                        set_io(b, "OCCUPIEDSPEC", bi["occupied"])
                    if bi.get("unoccupied"):
                        set_io(b, "UNOCCUPIEDSPEC", bi["unoccupied"])
                elif (cell, edge) in P.points:
                    sp = ET.SubElement(se, "SWITCHPOINTS")
                    io = P.route_io.get((cell, edge), {})
                    for rid, normal in P.points[(cell, edge)]["routes"]:
                        ri = ET.SubElement(sp, "ROUTEINFO", ROUTEID=rid)
                        if normal:
                            ri.set("NORMAL", "true")
                        for tag, spec in io.get(rid, []):
                            set_io(ri, tag, spec)
                elif (cell, edge) in P.crossings:
                    others = sorted(ENDS[t][1] if ENDS[t][0] == edge else ENDS[t][0] for t in tracks if edge in ENDS[t])
                    ET.SubElement(se, "CROSSINGEDGE", **{o: "NO_BLOCK" for o in others})
                if (cell, edge) in P.shared:
                    (fx, fy), fedge = P.shared[(cell, edge)]
                    ET.SubElement(se, "SHARED", X=str(fx), Y=str(fy)).text = fedge
        if cell in P.labels:
            text, loc, font = P.labels[cell]
            ET.SubElement(sec, "SEC_NAME", LOC_NAME=loc, NAME=text, FONT_NAME=font)
    ET.indent(root, "  ")
    return root


def write(P, out, discipline="CTC", header=(), window=None):
    root = to_xml(P, discipline, header, window)
    text = "<?xml version='1.0' encoding='UTF-8'?>\n" + ET.tostring(root, encoding="unicode") + "\n"
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    return text
