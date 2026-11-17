"""Binding a CATS panel to the layout's devices: checks on the bindings file, and the blocks, routes and switch names it ties.

Bindings (optional, `panel(bands, bindings=...)`, the command's --bindings FILE.json) tie the panel to the
layout's devices; every name in them must exist in the panel, or it is an error:

    {"switches": {"LABEL" or "LABEL/ALIAS": {"block": "OS name", "normal": "B" or "C", "label": "shown text",
                                              "corners": {"A": block, "B": .., "C": .., "D": .., "X": middle},
                                              "routes": {"B": {"ROUTECOMMAND": IO, "SELECTEDREPORT": IO}, "C": {..}}}},
     "blocks":   {"BLOCK": {"name": "layout name", "station": "..", "discipline": "CTC", "occupied": IO, "unoccupied": IO}},
     "masts":    {"MAST": {"name": "mast user name", "template": "physical signal template", "pantype": "LAMP2",
                           "orient": "LEFT", "RIGHT", "TOP" or "BOTTOM" (optional: the way the lamps point),
                           "location": a SIGLOCATION such as "LEFTLOW" (optional: where in its cell)}}}

IO is one CATS IOSPEC: {"DECADDR": .., "JMRIPREFIX": .., "USER_NAME": .., "command": "close" or "throw"} (also
JMRIDEVICE, EXIT_CMD, DELAY). A switch key is its label (every switch of that number) or label/alias (one of them; a key that
is not a whole label splits at its last /, and labels and aliases compare as text);
switches of one number given different `block`s keep apart. A double crossover's binding moves all four of its
points: route B along each through track, C into the X (normal B unless it says C). Its `corners` (in place of `block`) give it a block per band leg and one for the middle of the X; the X is then drawn two cells deep (a compact panel opens a row between its tracks, other slopes jogging across it) so each corner parts from the middle on a plain edge. BLOCK is the panel's block name after the switches'
`block`s; two blocks given one `name` become one block. MAST is a mast of a band's `signals`
(field or planned; virtual masts are not drawn). It goes on the block boundary nearest where it stands on its run:
on the edge of the block it protects (the side toward the switch or end its move is heading for), facing out of
that block, on the right-hand side of the move.
"""

from collections import defaultdict

from .cats_grid import OPPOSITE
from .cats_px import LOC_XY
from .core import SchematicError

__all__ = [
    "DISCIPLINES", "SIG_PANTYPES", "IOSPEC_KEYS", "ROUTE_TAGS", "node_of", "check_io", "check_bindings",
    "switch_bindings", "bind_blocks", "bind_routes", "number_order", "label_of"
]


DISCIPLINES = ("CTC", "ABS", "APB-2", "APB-3", "DTC", "Unknown")    # the values CATS reads (cats/layout/Discipline.java)
SIG_PANTYPES = ("LAMP1", "LAMP2", "LAMP3", "SEM1", "SEM2", "SEM3")
IOSPEC_KEYS = {"DECADDR", "JMRIPREFIX", "USER_NAME", "JMRIDEVICE", "EXIT_CMD", "DELAY"}
ROUTE_TAGS = ("SELECTEDREPORT", "NOTSELECTEDREPORT", "ROUTECOMMAND")


def node_of(key):
    """(band index, node) of an OS block key."""
    tag, n = key[1].split(":", 1)
    return int(tag[1:]), n


def check_io(io, where):
    """One IOSPEC binding: its attributes and its command."""
    if not isinstance(io, dict):
        raise SchematicError(f"{where}: an IOSPEC is an object with DECADDR, JMRIPREFIX, USER_NAME and command")
    unknown = set(io) - IOSPEC_KEYS - {"command"}
    if unknown:
        raise SchematicError(f"{where}: unknown IOSPEC field {', '.join(sorted(unknown))} "
                             f"(fields: {', '.join(sorted(IOSPEC_KEYS))}, command)")
    if io.get("DECADDR") in (None, ""):
        raise SchematicError(f"{where}: an IOSPEC needs a DECADDR")
    if io.get("command") not in ("close", "throw"):
        raise SchematicError(f"{where}: an IOSPEC command is close or throw, not {io.get('command')!r}")
    return {k: str(v) for k, v in io.items()}


def check_bindings(b):
    """The bindings with every field checked; unknown fields are errors (keys starting with _ are notes)."""
    def fields(obj, allowed, where):
        if not isinstance(obj, dict):
            raise SchematicError(f"{where}: expected an object")
        unknown = {k for k in obj if not k.startswith("_")} - set(allowed)
        if unknown:
            raise SchematicError(f"{where}: unknown field {', '.join(sorted(unknown))} (fields: {', '.join(allowed)})")
        return {k: v for k, v in obj.items() if not k.startswith("_")}
    b = fields(b, ("switches", "blocks", "masts"), "bindings")
    out = {"switches": {}, "blocks": {}, "masts": {}}
    section = lambda name: fields(b.get(name) or {}, [k for k in (b.get(name) or {})], f"bindings {name}")
    for key, e in section("switches").items():
        e = fields(e, ("block", "normal", "routes", "label", "corners"), f"switch {key}")
        if "corners" in e:
            c = fields(e["corners"], ("A", "B", "C", "D", "X"), f"switch {key} corners")
            if set("ABCD") - set(c) or not all(isinstance(v, str) and v.strip() for v in c.values()) or \
                    len(set(c.values())) != len(c):
                raise SchematicError(f"switch {key}: corners names a block for each leg A to D (and X, the middle of "
                                     "the X, if wanted), all different")
            if "block" in e:
                raise SchematicError(f"switch {key}: give corners or block, not both")
            e["corners"] = c
        if "label" in e and (not isinstance(e["label"], str) or not e["label"].strip()):
            raise SchematicError(f"switch {key}: label is the text shown at its points, a non-empty string")
        if e.get("normal", "B") not in ("B", "C"):
            raise SchematicError(f"switch {key}: normal is leg B or C, not {e['normal']!r}")
        routes = fields(e.get("routes", {}), ("B", "C"), f"switch {key} routes")
        e["routes"] = {port: [(tag, check_io(io, f"switch {key} leg {port} {tag}"))
                              for tag, io in fields(r, ROUTE_TAGS, f"switch {key} leg {port}").items()]
                       for port, r in routes.items()}
        out["switches"][key] = e
    for key, e in section("blocks").items():
        e = fields(e, ("name", "station", "discipline", "occupied", "unoccupied"), f"block {key}")
        if e.get("discipline") is not None and e["discipline"] not in DISCIPLINES:
            raise SchematicError(f"block {key}: discipline {e['discipline']!r} is not one CATS reads: "
                                 f"{', '.join(DISCIPLINES)}")
        for f in ("occupied", "unoccupied"):
            if f in e:
                e[f] = check_io(e[f], f"block {key} {f}")
        out["blocks"][key] = e
    for key, e in section("masts").items():
        e = fields(e, ("name", "template", "pantype", "orient", "location"), f"mast {key}")
        if e.get("pantype") is not None and e["pantype"] not in SIG_PANTYPES:
            raise SchematicError(f"mast {key}: pantype is one of {', '.join(SIG_PANTYPES)}")
        if e.get("orient") is not None and e["orient"] not in OPPOSITE:
            raise SchematicError(f"mast {key}: orient is one of {', '.join(OPPOSITE)}")
        if e.get("location") is not None and e["location"] not in LOC_XY:
            raise SchematicError(f"mast {key}: location is one of {', '.join(LOC_XY)}")
        out["masts"][key] = e
    return out


def switch_bindings(bands, switches):
    """{(band index, node): binding} for the switch keys, LABEL or LABEL/ALIAS. A key that names no switch is an
    error, and so is a switch named by two keys."""
    out, owner = {}, {}
    switch_nodes = [(bi, n, str(d.get("label") or ""), str(d.get("alias") or ""), d["kind"])
                    for bi, (_, band, _) in enumerate(bands) for n, d in band["nodes"].items()
                    if d["kind"] in ("switch", "dx")]
    for key, e in switches.items():
        hits = [(bi, n) for bi, n, lb, _, _ in switch_nodes if lb == key]       # the whole key is a label
        if not hits and "/" in key:                                            # else LABEL/ALIAS, at the last /
            label, _, alias = key.rpartition("/")
            hits = [(bi, n) for bi, n, lb, al, _ in switch_nodes if lb == label and al == alias]
        if not hits:
            raise SchematicError(f"bindings name switch {key}, which no drawn band has")
        for h in hits:
            if h in owner:
                d = bands[h[0]][1]["nodes"][h[1]]
                raise SchematicError(f"switch {d.get('label')}/{d.get('alias') or h[1]} is bound by both "
                                     f"{owner[h]} and {key}")
            owner[h] = key
            out[h] = e
    return out


def bind_blocks(P, blocks, switch_named=()):
    """Rename, merge and bind blocks. Blocks the bindings give one name (a block keyed in the bindings, or named by
    switch bindings, keeps its own name) become one block, logged; a rename onto the name of a block the bindings do
    not mention is an error."""
    root_of = {name: root for root, name in P.names.items()}       # block names are unique
    unknown = set(blocks) - set(root_of)
    if unknown:
        raise SchematicError(f"bindings name block {', '.join(sorted(unknown))}, which the panel does not have "
                             f"(blocks: {', '.join(sorted(root_of))})")
    explicit = set(blocks) | set(switch_named)
    groups = defaultdict(list)
    for name, root in sorted(root_of.items()):
        groups[blocks.get(name, {}).get("name") or name].append(name)
    for final, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        loose = [m for m in members if m not in explicit]
        if loose:
            raise SchematicError(f"bindings rename block {', '.join(m for m in members if m in blocks and m != final)} "
                                 f"to {final}, the name of block {', '.join(loose)}, which the bindings do not name")
        for m in members[1:]:
            P.union(root_of[members[0]], root_of[m])
        P.log.append(f"blocks {', '.join(members)} are one block, {final}")
    names, info = {}, {}
    for name, root in sorted(root_of.items()):
        r = P.find(root)
        final = blocks.get(name, {}).get("name") or name
        names[r] = final
        e = blocks.get(name)
        if e:
            have = info.setdefault(r, {})
            for f in ("station", "discipline", "occupied", "unoccupied"):
                if f in e:
                    if f in have and have[f] != e[f]:
                        raise SchematicError(f"blocks merged into {final} are bound with two different {f}s")
                    have[f] = e[f]
    P.names, P.block_info = names, info


def bind_routes(P, sw_bind):
    """Each bound switch's route IOSPECs on its points, by leg."""
    for at, pt in P.points.items():
        e = sw_bind.get(pt.get("node"))
        if not e or not e.get("routes"):
            continue
        P.route_io[at] = {edge: e["routes"].get(port, []) for edge, port in pt["ports"].items()}


def number_order(label):
    digits = "".join(ch for ch in label if ch.isdigit())
    return (int(digits) if digits else 0, label)


def label_of(bands, key):
    tag, n = key[1].split(":", 1)
    band = bands[int(tag[1:])][1]
    return band["nodes"][n].get("label") or ""
