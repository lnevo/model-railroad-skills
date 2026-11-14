"""Stations: the `stations` preference read into one shape, whichever way each entry is written.

An entry is a list of switch numbers, or an object `{"switches": [...], "tracks": [...], "side": "top"}`:

    switches   the station's switches (layer 1: which part of the railroad it is)
    tracks     optional: only these tracks count toward the station's car total (layer 1). `[]` counts none, as for
               a station that is only an interlocking. Without it a station counts the tracks that run from its switches
    side       "top" or "bottom": which side of the band its bar stands on (the look)

The look can also be given by name in the preferences, `station_side: {"West Yard": "top"}`, which wins over an
entry's own `side`. Stations may overlap: a switch may be in two of them. The track scope may also be given by name, `station_tracks: {name: [tracks]}`, a layer 1 key that survives a later layer writing the station as a plain list.
"""
from .core import SchematicError

SIDES = ("top", "bottom")


def entries(opts):
    """{name: {"switches": [str], "tracks": None or set of upper-case names, "side": "top"|"bottom"}}, in listed order.
    `station_tracks` (layer 1) and `station_side` (the look) name stations by name; one that names a station this
    input does not have is ignored here, since a sheet-wide preference reaches every input (`check` looks for names
    that match no input at all)."""
    sides = opts.get("station_side") or {}
    scoped = opts.get("station_tracks") or {}
    out = {}
    for name, e in (opts.get("stations") or {}).items():
        if isinstance(e, dict):
            unknown = set(e) - {"switches", "tracks", "side"}
            if unknown or "switches" not in e:
                raise SchematicError(f"station {name}: an object needs `switches` and may have `tracks` and `side`, "
                                     f"not {', '.join(sorted(unknown)) or 'nothing else'}")
            switches, tracks, side = e["switches"], e.get("tracks"), e.get("side")
        elif isinstance(e, (list, tuple)):
            switches, tracks, side = e, None, None
        else:
            raise SchematicError(f"station {name} must be a list of switches or an object, not {e!r}")
        if not isinstance(switches, (list, tuple)):
            raise SchematicError(f"station {name}: switches must be a list of switch numbers, not {switches!r}")
        tracks = scoped.get(name, tracks)
        side = sides.get(name, side) or "bottom"
        if side not in SIDES:
            raise SchematicError(f"station {name}: side must be top or bottom, not {side!r}")
        if tracks is not None and not isinstance(tracks, (list, tuple)):
            raise SchematicError(f"station {name}: tracks must be a list of track names")
        out[name] = dict(switches=[str(s) for s in switches],
                         tracks=None if tracks is None else {str(t).upper() for t in tracks}, side=side)
    return out


def check(all_opts):
    """Checks across every input's options: a `station_side` or `station_tracks` name must match a station in some
    input, and a station defined in several inputs must have the same switches and tracks in each."""
    seen = {}
    for o in all_opts:
        for name, e in entries(o).items():
            key = (sorted(e["switches"]), None if e["tracks"] is None else sorted(e["tracks"]))
            if seen.setdefault(name, key) != key:
                raise SchematicError(f"station {name} is defined differently in two inputs (switches or tracks)")
    for o in all_opts:
        for key in ("station_side", "station_tracks"):
            unknown = set(o.get(key) or ()) - set(seen)
            if unknown:
                raise SchematicError(f"{key} names {', '.join(sorted(unknown))}, which is not a station "
                                     f"(stations: {', '.join(seen) or 'none'})")


def members(opts):
    """{name: [switch numbers]}."""
    return {name: e["switches"] for name, e in entries(opts).items()}


def track_names(strand_name):
    """The upper-case names a strand's track goes by: its whole name and each part of a joined "A / B" name."""
    full = (strand_name or "").strip().upper()
    return ({full} | {p.strip() for p in full.split(" / ") if p.strip()}) if full else set()


def listed_strands(band, entry):
    """The strands of the tracks a station lists that touch one of its switches: the tracks its car total counts and
    its bar spans. A named track is all the strands that carry its name."""
    nodes, strands = band["nodes"], band["strands"]
    if not entry["tracks"]:
        return []
    by_track = {}
    for sid, s in strands.items():
        if s["name"]:
            by_track.setdefault(s["name"], []).append(sid)
    out = []
    for sids in by_track.values():
        if not track_names(strands[sids[0]]["name"]) & entry["tracks"]:
            continue
        labels = {nodes[n].get("label") for sid in sids for n in (strands[sid]["src"][0], strands[sid]["dst"][0])
                  if nodes[n].get("kind") == "switch"}
        if labels & set(entry["switches"]):
            out += sids
    return out


def plain(entry):
    """An entry as a station object, as `entries` would give it back (used to hand a station on unchanged)."""
    tracks = entry["tracks"]
    return {"switches": list(entry["switches"]), "side": entry["side"],
            **({} if tracks is None else {"tracks": sorted(tracks)})}
