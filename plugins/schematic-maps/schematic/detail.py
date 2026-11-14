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
    """{switch label: station name} over every station of every input. A switch in two stations has no one
    owner, so it stops the run."""
    out = {}
    for o in all_opts:
        for name, members in o.get("stations", {}).items():
            for m in map(str, members):
                if out.setdefault(m, name) != name:
                    raise SchematicError(f"switch {m} is in both {out[m]} and {name}; a station owns its switches alone")
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
            room = max(reach, columns.name_cells((s["name"] + " (00)").upper(), opts) + 1) if s["name"] else reach
            if sid in R["diag"]:             # a slope is cut like a level track: along its columns, the row following
                (xa, xb), (ra, rb) = (x[u], x[v]), (R["nrow"][u], R["nrow"][v])
                frac = min(1.0, room / (xb - xa)) if xb > xa else 1.0
                cx, cr = (xa + (xb - xa) * frac, ra + (rb - ra) * frac) if kept_is_src else \
                         (xb - (xb - xa) * frac, rb - (rb - ra) * frac)
                diag.add(sid)
            else:
                lo, hi = x[u] + su, x[v] - sv
                cx = min(lo + room, max(hi, lo)) if kept_is_src else max(hi - room, min(lo, hi))
                cr = R["srow"][sid]
                frac = min(1.0, abs(cx - (lo if kept_is_src else hi)) / (hi - lo)) if hi > lo else 1.0
            whole = s["cm"] / 2 if sid.endswith((".0", ".1")) else s["cm"]    # a fold half's cm is its whole run's
            s["cut_cm"] = whole * frac
            sub_nodes[cid] = dict(kind="end", sub="open", label=dest, to=None, sig=0,
                                  ins={"E": sid} if kept_is_src else {}, outs={} if kept_is_src else {"E": sid})
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
    sub["take"] = take
    return sub


def precomputed(band, opts, take, name, members, turned):
    """The capacity counts and the group's total, counted on the whole band exactly as the overall sheet draws them
    (including a band turned end for end), so the detail agrees with it even where a track runs off the cut."""
    cars = {}
    for show, n, tracks in capacity.tracks(band, opts):
        here = [m for m in tracks if m in take]
        if here:
            cars[show if show in take else max(here, key=lambda m: (band["strands"][m]["cm"], m))] = n
    stations = dict(opts.get("stations", {}))
    stations.setdefault(name, [str(m) for m in members])
    totals = capacity.station_totals(band, dict(opts, stations=stations), band["x"], turned)
    return {"cars": cars, "totals": {name: totals[name]} if totals.get(name) else {}}


def cut_signals(opts, sub):
    """The masts that stand on the cut band. A mast on a track that was cut stays only if it faces a station switch;
    how far along the drawn part it stands is then `mast_piece`'s to judge, from the track's `cut_cm`."""
    edges = {}
    for s in sub["strands"].values():
        edges.setdefault(s["edge"], []).append(s)
    out = []
    for sg in opts.get("signals", ()):
        pieces = [s for e in (sg["_edge"], sg["_edge"] + "x", sg["_edge"] + "y") for s in edges.get(e, ())]
        if not pieces:
            continue
        if any("cut_cm" in s for s in pieces) and sg["_toward_node"] not in sub["nodes"]:
            continue
        out.append(sg)
    return out


def detail_options(opts, title, name, members, sub, pre):
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
               max_scale=opts.get("detail_max_scale", DETAIL_SCALE), precomputed=pre,
               signals=cut_signals(opts, sub))
    return out


def sheet_svg(bands, members, name, owner):
    """(SVG, cut band) of one detail sheet, cut from the solved `bands` ([(title, band, options)]). `owner` is
    `owners(...)` of every input's options."""
    title, band, opts = find_band(bands, members)
    sub = cut(band, members, opts, name, owner)
    turned = draw.band_key(title) in opts.get("rotate_bands", ())
    pre = precomputed(band, opts, sub.pop("take"), name, members, turned)
    sub["precomputed"] = pre
    o = detail_options(opts, title, name, members, sub, pre)
    return draw.page_svg([(title, sub, o)], o), sub


def sheets(bands, picks):
    """[(name, members, SVG)] for each pick; the station owners are worked out once."""
    owner = owners([o for _, _, o in bands])
    return [(name, members, sheet_svg(bands, members, name, owner)[0]) for name, members in picks]


def selections(opts_list, stations=None, switches=None, name=None):
    """[(name, members)] to draw: a named group from `switches`, else the chosen stations (all when none chosen)
    from the `stations` preference."""
    if switches and stations:
        raise SchematicError("--station and --switches are two ways to choose; use one")
    known = {}
    for o in opts_list:
        for st, members in o.get("stations", {}).items():
            members = [str(m) for m in members]
            if known.setdefault(st, members) != members:
                raise SchematicError(f"station {st} is defined differently in two inputs")
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
