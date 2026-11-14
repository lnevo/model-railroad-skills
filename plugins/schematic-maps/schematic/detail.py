"""Detail sheets: one station, or a named group of switches, cut out of the solved overall sheet.

The cut is a rule, not a hand drawing. The band that holds the station is solved first, exactly as for the
overall sheet; this module keeps the station's own switches, every track that touches one of them, and the
track ends and turnbacks those tracks reach. A track that runs on to a switch outside the station is cut a
short way (`DETAIL_REACH` cells) past its last station switch and finishes in an open arrow reading
"TO <station>" (the station that owns the far switch) or "TO SW <number>" (a switch no station owns). Every
column, row, slope, length, capacity count and mast is the overall sheet's, so the two agree; the sheet is only
drawn larger (`detail_max_scale`, a layer 3 preference).
"""
import copy

from . import capacity, columns, draw
from .core import JUNCTION, SchematicError

DETAIL_REACH = 2.0          # cells of a leaving track that stay on the sheet
DETAIL_SCALE = 2.0          # the most a detail sheet is enlarged beyond the overall sheet's drawing size
KEEP_SETTINGS = ("band_legend", "track_arrows", "rotate_bands")     # band settings that carry over to the detail


def find_band(bands, members):
    """(title, band, options) of the band holding every member switch. Stops on a missing or split group."""
    want = {str(m) for m in members}
    found = []
    for title, band, opts in bands:
        have = {d["label"] for d in band["nodes"].values() if d["kind"] in JUNCTION and d.get("label") in want}
        if have:
            found.append((title, band, opts, have))
    got = set().union(*(f[3] for f in found)) if found else set()
    if want - got:
        raise SchematicError(f"switch {', '.join(sorted(want - got))} is not on any band")
    if len(found) > 1:
        raise SchematicError("switches " + ", ".join(sorted(want)) + " are on more than one band ("
                             + ", ".join(f[0] for f in found) + "); a detail sheet is cut from one band")
    title, band, opts, _ = found[0]
    return title, band, opts


def owners(all_opts):
    """{switch label: station name} over every station of every input."""
    out = {}
    for o in all_opts:
        for name, members in o.get("stations", {}).items():
            for m in members:
                out.setdefault(str(m), name)
    return out


def destination(nodes, n, owner, name):
    """What a cut track says it runs to: the station that owns the far switch, else the switch."""
    label = nodes[n].get("label") or ""
    st = owner.get(label)
    return "TO " + (st if st and st != name else f"SW {label}").upper()


def cut(band, members, opts, name, owner, reach=DETAIL_REACH):
    """A band holding only the station: nodes, strands, rows and columns copied from the solved band, plus an
    open end at each place a track leaves. Capacity counts and masts are cut with it, from the whole band's."""
    want = {str(m) for m in members}
    nodes, strands, R, x, need = (band[k] for k in ("nodes", "strands", "R", "x", "need"))
    keep = {n for n, d in nodes.items() if d["kind"] in JUNCTION and d.get("label") in want}
    take = {sid for sid, s in strands.items() if s["src"][0] in keep or s["dst"][0] in keep}
    turns = {n for sid in take for n in (strands[sid]["src"][0], strands[sid]["dst"][0])
             if nodes[n]["kind"].startswith("turn")}
    take |= {sid for sid, s in strands.items() if s["src"][0] in turns or s["dst"][0] in turns}
    inside = keep | turns

    sub_nodes = {n: copy.deepcopy(nodes[n]) for n in nodes if n in inside}
    sub_strands, sub_need = {}, {}
    srow, nrow = {}, {}
    sub_x = {n: x[n] for n in inside}
    for n in inside:
        if n in R["nrow"]:
            nrow[n] = R["nrow"][n]
    diag = set()
    for sid in sorted(take):
        s = copy.deepcopy(strands[sid])
        u, v = s["src"][0], s["dst"][0]
        su, sv, third = need[sid]
        end_ids = [n for n in (u, v) if n not in inside and nodes[n]["kind"] in JUNCTION]
        for n in (u, v):
            if n not in inside and nodes[n]["kind"] not in JUNCTION:
                sub_nodes[n] = copy.deepcopy(nodes[n])        # a track end or connector the track reaches
                sub_x[n] = x[n]
                if n in R["nrow"]:
                    nrow[n] = R["nrow"][n]
                inside = inside | {n}
        if end_ids:
            far = end_ids[0]
            cid = f"CUT:{sid}"
            kept_is_src = u not in end_ids
            dest = destination(nodes, far, owner, name)
            if sid in R["diag"]:             # a slope into an outside switch: the arrow stands where the slope ends
                cx, cr = x[far], R["nrow"][far]
                diag.add(sid)
            else:
                r = R["srow"][sid]
                lo, hi = x[u] + su, x[v] - sv
                room = max(reach, columns.name_cells((s["name"] + " (00)").upper(), opts) + 1) if s["name"] else reach
                cx = min(lo + room, max(hi, lo)) if kept_is_src else max(hi - room, min(lo, hi))
                cr = r
                run = max(hi - lo, 1e-9)
                got = abs(cx - (lo if kept_is_src else hi))
                s["cut_cm"] = s["cm"] * min(1.0, got / run) if hi > lo else s["cm"]
            sub_nodes[cid] = dict(kind="end", sub="open", label=dest, to=None, sig=0,
                                  ins={} if kept_is_src is False else {"E": sid},
                                  outs={"E": sid} if kept_is_src is False else {})
            sub_x[cid], nrow[cid] = cx, cr
            if kept_is_src:
                s["dst"] = (cid, "E")
                sub_need[sid] = (su, 0, third)
            else:
                s["src"] = (cid, "E")
                sub_need[sid] = (0, sv, third)
            s["cut_from"] = far
        else:
            sub_need[sid] = (su, sv, third)
        sub_strands[sid] = s
        if sid in R["diag"]:
            diag.add(sid)
        elif sid in R["srow"]:
            srow[sid] = R["srow"][sid]
    for n in sub_nodes:
        if n in R["srow"]:
            srow[n] = R["srow"][n]               # turnbacks carry a row of their own
    for sid, s in sub_strands.items():
        if sid in diag:
            srow.setdefault(sid, R["srow"].get(sid, 0))
    sub = dict(nodes=sub_nodes, strands=sub_strands, R=dict(srow=srow, nrow=nrow, diag=diag, cost=R.get("cost", 0.0)),
               x=sub_x, need=sub_need, turnbacks=band.get("turnbacks", set()),
               short=set(), unplaced=[])
    for n in sub_nodes:                          # each node's ins and outs name only strands that are on the sheet
        for side in ("ins", "outs"):
            sub_nodes[n][side] = {p: sid for p, sid in sub_nodes[n][side].items() if sid in sub_strands}
    if "rail" in band:
        sub["rail"] = {n: v for n, v in band["rail"].items() if n in sub_nodes}
    sub["cars"], sub["station_totals"] = cars_and_totals(band, opts, take, name, want)
    return sub


def cars_and_totals(band, opts, take, name, want):
    """The whole band's capacity counts (by strand) and the group's total, so the detail agrees with the overall sheet
    even where a track runs off the cut."""
    cars = {}
    for show, n, members in capacity.tracks(band, opts):
        here = [m for m in members if m in take]
        if here:
            cars[show if show in take else max(here, key=lambda m: (band["strands"][m]["cm"], m))] = n
    stations = dict(opts.get("stations", {}))
    stations.setdefault(name, sorted(want))
    totals = capacity.station_totals(band, dict(opts, stations=stations), band["x"])
    return cars, {name: totals[name]} if totals.get(name) else {}


def cut_signals(opts, sub):
    """The masts that stand on the cut band: a mast on a track that is cut short is kept only if it stands on the
    part that is drawn and faces a station switch."""
    out = []
    cut_edges = {s["edge"]: s for s in sub["strands"].values() if "cut_cm" in s}
    on = {s["edge"] for s in sub["strands"].values()}
    for sg in opts.get("signals", ()):
        if not on & {sg["_edge"], sg["_edge"] + "x", sg["_edge"] + "y"}:
            continue
        s = cut_edges.get(sg["_edge"])
        if s is not None and (sg["_toward_node"] not in sub["nodes"] or sg["cm_from_toward"] > s["cut_cm"] + 0.5):
            continue
        out.append(sg)
    return out


def detail_options(opts, title, name, members, sub, scale=None):
    """The options of one detail sheet: the band's own look, its title block, and only this band's settings."""
    key = draw.band_key(title)
    out = dict(opts)
    for k in draw.BAND_SETTINGS:
        v = out.get(k)
        if isinstance(v, dict):
            out[k] = {b: w for b, w in v.items() if b == key} if k in KEEP_SETTINGS else {}
        elif isinstance(v, (list, tuple)):
            out[k] = [b for b in v if b == key] if k in KEEP_SETTINGS else []
    out.pop("system_title", None)
    out.update(stations={name: [str(m) for m in members]}, equal_width=False, sheet=None,
               title=[name, "Station detail sheet", title],
               max_scale=scale or opts.get("detail_max_scale", DETAIL_SCALE),
               signals=cut_signals(opts, sub))
    return out


def sheet_svg(bands, members, name, all_opts):
    """The SVG of one detail sheet, cut from the solved `bands` ([(title, band, options)])."""
    title, band, opts = find_band(bands, members)
    sub = cut(band, members, opts, name, owners(all_opts))
    o = detail_options(opts, title, name, members, sub)
    return draw.page_svg([(title, sub, o)], o), sub


def selections(opts_list, stations=None, switches=None, name=None):
    """[(name, members)] to draw: a named group from `switches`, else the chosen stations (all when none chosen)
    from the `stations` preference."""
    known = {}
    for o in opts_list:
        for st, members in o.get("stations", {}).items():
            known.setdefault(st, [str(m) for m in members])
    if switches:
        if not name:
            raise SchematicError("a group of switches needs a name (--name)")
        return [(name, [str(s) for s in switches])]
    chosen = stations or list(known)
    lower = {k.lower(): k for k in known}
    out = []
    for st in chosen:
        if st.lower() not in lower:
            raise SchematicError(f"no station {st!r} in the stations preference (stations: {', '.join(known) or 'none'})")
        out.append((lower[st.lower()], known[lower[st.lower()]]))
    if not out:
        raise SchematicError("no stations in the preferences: name the switches with --switches and --name")
    return out
