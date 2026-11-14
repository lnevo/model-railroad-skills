"""Stations: the `stations` preference read into one shape, whichever way each entry is written.

An entry is a list of switch numbers, or an object `{"switches": [...], "tracks": [...], "side": "top"}`:

    switches   the station's switches (layer 1: which part of the railroad it is)
    tracks     optional: only these tracks count toward the station's car total (layer 1). `[]` counts none, as for
               a station that is only an interlocking. Without it a station counts the tracks that run from its switches
    side       "top" or "bottom": which side of the band its bar stands on (the look)

The look can also be given by name in the preferences, `station_side: {"West Yard": "top"}`, which wins over an
entry's own `side`. Stations may overlap: a switch may be in two of them.
"""
from .core import SchematicError

SIDES = ("top", "bottom")


def entries(opts):
    """{name: {"switches": [str], "tracks": None or set of upper-case names, "side": "top"|"bottom"}}, in listed order."""
    sides = opts.get("station_side") or {}
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
        side = sides.get(name, side) or "bottom"
        if side not in SIDES:
            raise SchematicError(f"station {name}: side must be top or bottom, not {side!r}")
        if tracks is not None and not isinstance(tracks, (list, tuple)):
            raise SchematicError(f"station {name}: tracks must be a list of track names")
        out[name] = dict(switches=[str(s) for s in switches],
                         tracks=None if tracks is None else {str(t).upper() for t in tracks}, side=side)
    unknown = set(sides) - set(out)
    if unknown:
        raise SchematicError(f"station_side names {', '.join(sorted(unknown))}, which is not a station "
                             f"(stations: {', '.join(out) or 'none'})")
    return out


def members(opts):
    """{name: [switch numbers]}."""
    return {name: e["switches"] for name, e in entries(opts).items()}


def track_names(strand_name):
    """The upper-case names a strand's track goes by: each part of a joined "A / B" name."""
    return {p.strip().upper() for p in (strand_name or "").split(" / ") if p.strip()}


def plain(entry):
    """An entry as a station object, as `entries` would give it back (used to hand a station on unchanged)."""
    tracks = entry["tracks"]
    return {"switches": list(entry["switches"]), "side": entry["side"],
            **({} if tracks is None else {"tracks": sorted(tracks)})}
