"""Capacity: how many cars each yard or stub track holds, and the total for each station.

A track counts when it is not main track, not a short ladder link or connector, and longer than a ladder
link: the sidings, yard tracks and stubs a crew fills. Its length is the measured one when layer 1 lists it
(`track_lengths_in`, by track name, in inches), else the plan's. Cars = length / `car_in` (the preference
`capacity`, default 7.4 in: a 50 ft HO car with couplers), rounded down.
"""
import math

from .core import SchematicError
from .rules import setting


def car_length(opts):
    """Inches per car from the `capacity` preference, or None when capacity is off. `capacity: {}` or `true`
    takes the default."""
    cap = opts.get("capacity")
    if cap is None or cap is False:
        return None
    car_in = cap.get("car_in", 7.4) if isinstance(cap, dict) else 7.4
    if isinstance(car_in, bool) or not isinstance(car_in, (int, float)) or car_in <= 0:
        raise SchematicError(f"capacity car_in must be a length in inches above 0, not {car_in!r}")
    return float(car_in)


def measured_length(measured, name):
    """A measured length for a track name, or for either part of a joined name ("A / B")."""
    for part in [name] + name.split(" / "):
        if part.upper() in measured:
            return measured[part.upper()]
    return None


def tracks(band, opts):
    """[(strand that shows the count, cars, [strands of the track])], one per track. Pieces of one track are
    joined: an unnamed track that switches cut into pieces along one drawn row, and the pieces of a named
    track (all carrying its name). A folded run counts once on its named half, or once per half when its two
    halves carry different names (a loop drawn as two tracks)."""
    car_in = car_length(opts)
    if car_in is None:
        return []
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
    cm = {sid: strands[sid]["cm"] / halves[e] for (e, _), sid in pick.items()}
    parent = {sid: sid for sid in cm}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    at, by_name = {}, {}
    for sid in sorted(cm):
        s = strands[sid]
        if s["name"]:                       # a named track's pieces are one track
            if s["name"] in by_name:
                parent[find(sid)] = find(by_name[s["name"]])
            by_name.setdefault(s["name"], sid)
            continue
        for n in (s["src"][0], s["dst"][0]):
            if nodes[n].get("kind") != "switch":
                continue
            for other in at.get((n, srow.get(sid)), []):
                parent[find(other)] = find(sid)
            at.setdefault((n, srow.get(sid)), []).append(sid)
    groups = {}
    for sid in cm:
        groups.setdefault(find(sid), []).append(sid)
    out = []
    for members in groups.values():
        if max(cm[m] for m in members) <= link_cm:
            continue                        # only short links between switches: ladder, not track
        name = strands[members[0]]["name"] or ""
        inches = measured_length(measured, name) if name else None
        if inches is None:
            inches = sum(cm[m] for m in members) / 2.54
        n = math.floor(inches / car_in)
        if n >= 1:
            show = max(members, key=lambda m: (cm[m], m))
            out.append((show, n, sorted(members)))
    return out


def counts(band, opts):
    """{strand that shows the count: cars}. A detail sheet's band carries the whole sheet's counts in `cars`."""
    if "cars" in band:
        return dict(band["cars"])
    return {show: n for show, n, _ in tracks(band, opts)}


def station_totals(band, opts, x, turned=False):
    """{station: cars}: a track goes to the station of its west end switch (left, or right on a band turned
    end for end), else the next switch along it; any piece of the track may supply that switch."""
    if "station_totals" in band:           # a detail sheet: counted on the whole band, where a track's west end is
        return dict(band["station_totals"])
    nodes, strands = band["nodes"], band["strands"]
    station = {lab: st for st, members in opts.get("stations", {}).items() for lab in members}
    out = {}
    for _, n, members in tracks(band, opts):
        ends = {e for m in members for e in (strands[m]["src"][0], strands[m]["dst"][0])
                if nodes[e].get("kind") == "switch" and nodes[e].get("label") in station}
        if ends:
            west = (max if turned else min)(ends, key=lambda e: x.get(e, 0))
            name = station[nodes[west]["label"]]
            out[name] = out.get(name, 0) + n
    return out
