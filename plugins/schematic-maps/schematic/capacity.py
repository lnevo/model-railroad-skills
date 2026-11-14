"""Capacity: how many cars each yard or stub track holds, and the total for each station.

A track counts when it is not main track, not a short ladder link or connector, and longer than a ladder
link: the sidings, yard tracks and stubs a crew fills. Its length is the measured one when layer 1 lists it
(`track_lengths_in`, by track name, in inches), else the plan's. Cars = length / `car_in` (the preference
`capacity`, default 7.4 in: a 50 ft HO car with couplers), rounded down.
"""
import math

from .rules import setting


def counts(band, opts):
    """{strand: cars}, one per track. An unnamed yard track that switches cut into pieces along one drawn row
    counts once, on its longest piece, from the pieces' summed length; a named track counts on its own. A folded run counts once on its named half,
    or once per half when its two halves carry different names (a loop drawn as two tracks)."""
    cap = opts.get("capacity")
    if not cap:
        return {}
    car_in = float(cap.get("car_in", 7.4)) if isinstance(cap, dict) else 7.4
    measured = {k.upper(): float(v) for k, v in opts.get("track_lengths_in", {}).items()}
    nodes, strands = band["nodes"], band["strands"]
    srow, diag = band["R"]["srow"], band["R"]["diag"]
    link_cm = setting(opts, "ladder_link_max_cm")
    pick = {}                               # (edge, name) -> strand
    for sid, s in sorted(strands.items()):
        ends = [s["src"][0], s["dst"][0]]
        if s["main"] or s["link"] or sid in diag or any(nodes[n].get("sub") in ("link", "helix") for n in ends):
            continue
        if not s["name"] and any(k[0] == s["edge"] for k in pick):
            continue                        # a folded run: its named half carries the count
        if s["name"]:
            pick.pop((s["edge"], ""), None)
        pick.setdefault((s["edge"], s["name"] or ""), sid)
    halves = {}
    for e, _ in pick:
        halves[e] = halves.get(e, 0) + 1
    inches = {sid: measured.get((strands[sid]["name"] or "").upper(), strands[sid]["cm"] / 2.54 / halves[e])
              for (e, _), sid in pick.items()}
    parent = {sid: sid for sid in inches}   # pieces on one row that meet at a switch are one track

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    at = {}
    for sid in sorted(inches):
        s = strands[sid]
        if s["name"]:
            continue                        # a named track is whole already (its measured length covers it)
        for n in (s["src"][0], s["dst"][0]):
            if nodes[n].get("kind") != "switch":
                continue
            for other in at.get((n, srow.get(sid)), []):
                parent[find(other)] = find(sid)
            at.setdefault((n, srow.get(sid)), []).append(sid)
    groups = {}
    for sid in inches:
        groups.setdefault(find(sid), []).append(sid)
    out = {}
    for members in groups.values():
        total = sum(inches[m] for m in members)
        if max(strands[m]["cm"] for m in members) <= link_cm:
            continue                        # only short links between switches: ladder, not track
        n = math.floor(total / car_in)
        if n >= 1:
            show = max(members, key=lambda m: (bool(strands[m]["name"]), strands[m]["cm"], m))
            out[show] = n
    return out


def station_totals(band, opts, cars, x):
    """{station: cars}: each counted track goes to the station of its west (left) end switch, else its east end."""
    nodes, strands = band["nodes"], band["strands"]
    out = {}
    for sid, n in cars.items():
        s = strands[sid]
        ends = sorted((s["src"][0], s["dst"][0]), key=lambda t: x.get(t, 0))
        for e in ends:
            name = next((st for st, members in opts.get("stations", {}).items()
                         if nodes[e].get("kind") == "switch" and nodes[e].get("label") in members), None)
            if name:
                out[name] = out.get(name, 0) + n
                break
    return out
