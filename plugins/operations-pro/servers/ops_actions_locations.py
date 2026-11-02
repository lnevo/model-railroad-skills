"""Actions for locations and tracks."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ops_data import (ALL, ANY, EXCLUDE, EXCLUDE_ROUTES, EXCLUDE_TRAINS, INCLUDE, INTERCHANGE, ROUTES, SPUR, STAGING,
                      TRAINS, YARD)
from ops_store import Refused
from ops_actions import (JAVA_INT, Editor, LOAD_BITS, SPUR_BITS, STAGING_BITS, TRACK_CHILDREN, action, _bool, _indent,
                         _int_field, _mask, _next, _remove_types, _set_list)


# ---- Locations and tracks ---------------------------------------------------------


@action()
def add_location(ed: Editor, name: str, types: list[str] | None = None, directions: str | int = 15,
                 like: str | None = None, comment: str = "") -> str:
    """Add a location. Types come from types, or like, or, as a new location in JMRI does (Location:116-123),
    every car type and every locomotive type, so a train that carries locomotives can end here."""
    name = ed.check_name("location", name)
    if name in [x.get("name") for x in ed.locations()]:
        raise Refused(f"Location {name!r} already exists")
    wanted = types if types is not None else (ed.type_entries(ed.location(like)) if like else
                                              ed.car_types() + [t for t in ed.loco_types() if t not in ed.car_types()])
    number = _next(x.get("id") for x in ed.locations())
    # No ops attribute: Location(Element) never reads it and store() derives it from the tracks.
    element = ET.Element("location", {"id": str(number), "name": name, "dir": str(_mask(directions)),
                                      "switchList": "true", "comment": comment, "switchListComment": ""})
    holder = ed.section(ed.loc_root, "locations")
    holder.append(element)
    for kind in wanted:
        ed.need_type(kind)
        ed.add_type_to(element, kind, 2)
    _indent(holder, 1)
    return f"Added location {name} (id {number})."


@action()
def update_location(ed: Editor, location: str, directions: str | int | None = None, comment: str | None = None,
                    add_types: list[str] | None = None, remove_types: list[str] | None = None) -> str:
    """Change a location's train directions, comment or types."""
    element = ed.location(location)
    if directions is not None:
        element.set("dir", str(_mask(directions)))
    if comment is not None:
        element.set("comment", comment)
    for kind in add_types or []:
        ed.need_type(kind)
        ed.add_type_to(element, kind, 2)
    for kind in remove_types or []:
        users = [t.get("name") for t in element.findall("track") if kind in ed.type_entries(t)]
        if users:
            raise Refused(f"Tracks here still take {kind}: {', '.join(users)}")
        _remove_types(element, (kind,))
    _indent(element, 2)
    return f"Updated location {element.get('name')}."


@action()
def rename_location(ed: Editor, location: str, new: str) -> str:
    """Rename a location. Ids stay; every stored copy of the name follows."""
    element = ed.location(location)
    new = ed.check_name("location", new)
    if new in [x.get("name") for x in ed.locations()]:
        raise Refused(f"Location {new!r} already exists")
    old, identity = element.get("name"), element.get("id")
    element.set("name", new)
    for node in ed.loc_root.iter("destination"):
        if node.get("id") == identity:
            node.set("name", new)
    stops = {}
    for route in ed.routes():
        for stop in route.findall("location"):
            if stop.get("locationId") == identity:
                stop.set("name", new)
                stops[stop.get("id")] = True
    for skip in ed.train_root.iter("location"):
        if skip.get("id") in stops:
            skip.set("name", new)
    return f"Renamed location {old} to {new}."


@action()
def add_track(ed: Editor, location: str, name: str, type: str, length: int, types: list[str] | None = None,
              directions: str | int | None = None, moves: int = 0, **settings) -> str:
    """Add a track. Other location tracks keep their move counts, unlike adding one in JMRI's window.
    Without types it takes the location's types, car and locomotive: a new JMRI track takes every type and
    the location filters them (Track:238-247, 935-943). Its id is never one a deleted track had here, in
    this plan or in a backup set, so a file copied from another state cannot put a car on it."""
    if type not in (SPUR, YARD, INTERCHANGE, STAGING):
        raise Refused(f"type must be {SPUR}, {YARD}, {INTERCHANGE} or {STAGING}")
    place = ed.location(location)
    name = ed.check_name("track", name)
    if name in [t.get("name") for t in place.findall("track")]:
        raise Refused(f"{place.get('name')} already has track {name!r}")
    existing = [t.get("trackType") for t in place.findall("track")]
    if existing and (type == STAGING) != (STAGING in existing):
        raise Refused("JMRI's windows keep staging and other track types at separate locations")
    length = _int_field("length", length)  # Track:2533-2538: anything else loads as 0.
    number = _next([*(t.get("id") for t in place.findall("track")), *ed.retired_tracks(place.get("id"))], "s")
    identity = f"{place.get('id')}s{number}"
    element = ET.Element("track", {"id": identity, "name": name, "trackType": type,
                                   "dir": str(_mask(directions) if directions is not None else place.get("dir", "15")),
                                   "length": str(length), "moves": str(_moves(moves))})
    if type in (INTERCHANGE, STAGING):
        element.set("onlyCarWithFD", "false")
    place.append(element)
    for kind in types if types is not None else ed.type_entries(place):
        ed.need_type(kind)
        ed.add_type_to(place, kind, 2)
        ed.add_type_to(element, kind, 3)
    if moves:
        ed.moves_allowed.add(identity)
    _indent(place, 2)
    if settings:
        update_track(ed, track=identity, **settings)
    return f"Added {type} {name} at {place.get('name')} (id {identity})."


def _option_list(ed: Editor, track: ET.Element, value: dict, option_attr: str, tag: str, item: str,
                 allowed: tuple[str, ...], default: str) -> None:
    option = value.get("option", default)
    if option not in allowed:
        raise Refused(f"option must be one of {', '.join(allowed)}")
    names = value.get("names", [])
    if option == default:
        track.attrib.pop(option_attr, None)
        names = []
    else:
        track.set(option_attr, option)
    _set_list(track, tag, item, names, "name", TRACK_CHILDREN, 3)


def _service(ed: Editor, track: ET.Element, value: dict, option_attr: str, tag: str, item: str) -> None:
    if track.get("trackType") == YARD:
        raise Refused("Yards ignore pickup and set-out lists. JMRI drops them on save.")
    option = value.get("option", ANY)
    if option not in (ANY, TRAINS, ROUTES, EXCLUDE_TRAINS, EXCLUDE_ROUTES):
        raise Refused(f"option must be {ANY}, {TRAINS}, {ROUTES}, {EXCLUDE_TRAINS} or {EXCLUDE_ROUTES}")
    if option == ANY:
        track.attrib.pop(option_attr, None)
        _set_list(track, tag, item, [], "id", TRACK_CHILDREN, 3)
        return
    lookup = ed.train if option in (TRAINS, EXCLUDE_TRAINS) else ed.route
    ids = [lookup(n).get("id") for n in value.get("names", [])]
    track.set(option_attr, option)
    _set_list(track, tag, item, ids, "id", TRACK_CHILDREN, 3)


@action()
def update_track(ed: Editor, track: str, location: str | None = None, length: int | None = None,
                 directions: str | int | None = None, add_types: list[str] | None = None,
                 remove_types: list[str] | None = None, roads: dict | None = None, loads: dict | None = None,
                 ship_loads: dict | None = None, drop: dict | None = None, pickup: dict | None = None,
                 destinations: dict | None = None, only_final_destination: bool | None = None,
                 schedule: str | None = "", schedule_mode: str | None = None, reservation_factor: int | None = None,
                 hold_custom: bool | None = None, alternate: str | None = "", load_options: list[str] | None = None,
                 pool: dict | None = None, ignore_used_percent: int | None = None, priority: str | None = None,
                 blocking_order: int | None = None) -> str:
    """Change one track. List settings take {option, names}. Destinations with option Exclude take the names to exclude."""
    element = ed.track(track, location)
    kind = element.get("trackType")
    place = ed.location_of(element)
    if length is not None:
        element.set("length", str(_int_field("length", length)))
    if directions is not None:
        element.set("dir", str(_mask(directions)))
    for name in add_types or []:
        ed.need_type(name)
        ed.add_type_to(place, name, 2)
        ed.add_type_to(element, name, 3)
    if remove_types:
        _remove_types(element, remove_types)
    if roads is not None:
        _option_list(ed, element, roads, "carRoadOption", "carRoads", "carRoad", (ALL, INCLUDE, EXCLUDE), ALL)
    if loads is not None:
        _option_list(ed, element, loads, "carLoadOption", "carLoads", "carLoad", (ALL, INCLUDE, EXCLUDE), ALL)
    if ship_loads is not None:
        if kind != STAGING:
            raise Refused("Ship load options exist on staging tracks only")
        _option_list(ed, element, ship_loads, "carShipLoadOption", "carShipLoads", "carLoad",
                     (ALL, INCLUDE, EXCLUDE), ALL)
    if drop is not None:
        _service(ed, element, drop, "dropOption", "dropIds", "dropId")
    if pickup is not None:
        _service(ed, element, pickup, "pickupOption", "pickupIds", "pickupId")
    if destinations is not None:
        _destinations(ed, element, destinations)
    if only_final_destination is not None:
        if kind not in (INTERCHANGE, STAGING):
            raise Refused("Only interchange and staging tracks can require a final destination")
        element.set("onlyCarWithFD", _bool(only_final_destination))
    if schedule != "":
        _assign_schedule(ed, element, schedule)
    _schedule_options(element, schedule_mode, reservation_factor, hold_custom)
    if alternate != "":
        _alternate(ed, element, place, alternate)
    if load_options is not None:
        _load_options(element, load_options)
    if pool is not None:
        _pool(element, pool)
    if ignore_used_percent is not None:
        if ignore_used_percent not in (0, 25, 50, 75, 100):
            raise Refused("ignore_used_percent must be 0, 25, 50, 75 or 100")
        element.attrib.pop("ignoreUsedPercentage", None)
        if ignore_used_percent:
            element.set("ignoreUsedPercentage", str(ignore_used_percent))
    if priority is not None:
        if priority not in ("High", "Medium", "Normal", "Low"):
            raise Refused("priority must be High, Medium, Normal or Low")
        element.attrib.pop("trackPriority", None)
        if priority != "Normal":
            element.set("trackPriority", priority)
    if blocking_order is not None:
        blocking_order = _int_field("blocking_order", blocking_order, JAVA_INT[0])  # Track:2551-2556.
        element.attrib.pop("blockingOrder", None)
        if blocking_order:
            element.set("blockingOrder", str(blocking_order))
    _indent(element, 3)
    return f"Updated track {element.get('name')}."


def _destinations(ed: Editor, element: ET.Element, value: dict) -> None:
    if element.get("trackType") not in (INTERCHANGE, STAGING):
        raise Refused("Destinations exist on interchange and staging tracks only")
    option = value.get("option", ALL)
    if option not in (ALL, INCLUDE, EXCLUDE):
        raise Refused("option must be All, Include or Exclude")
    if option == ALL:
        element.attrib.pop("trackDestinationOption", None)
        _set_list(element, "destinations", "destination", [], "id", TRACK_CHILDREN, 3)
        return
    chosen = [ed.location(n).get("id") for n in value.get("names", [])]
    # The file always lists accepted ids; Exclude only changes how JMRI's window shows them.
    every = [x.get("id") for x in ed.locations()]
    ids = chosen if option == INCLUDE else [i for i in every if i not in chosen]
    names = {x.get("id"): x.get("name") for x in ed.locations()}
    element.set("trackDestinationOption", option)
    _set_list(element, "destinations", "destination", ids, "id", TRACK_CHILDREN, 3, names.get)


def _assign_schedule(ed: Editor, element: ET.Element, schedule: str | None) -> None:
    if element.get("trackType") != SPUR:
        raise Refused("Only spurs can have a schedule")
    if schedule is None:
        for attr in ("schedule", "scheduleId", "itemId", "itemCount", "factor", "scheduleMode", "holdCustomLoads"):
            element.attrib.pop(attr, None)
        return
    target = ed.schedule(schedule)
    items = sorted(target.findall("item"), key=lambda i: int(i.get("sequenceId", 0)))
    if not items:
        raise Refused(f"Schedule {target.get('name')} has no lines")
    if element.get("scheduleId") == target.get("id"):
        return
    element.set("schedule", target.get("name"))
    element.set("scheduleId", target.get("id"))
    element.set("itemId", items[0].get("id"))
    element.set("itemCount", "0")
    element.set("factor", element.get("factor", "100"))
    element.set("scheduleMode", element.get("scheduleMode", "0"))
    element.set("holdCustomLoads", element.get("holdCustomLoads", "false"))


def _schedule_options(element: ET.Element, mode: str | None, factor: int | None, hold: bool | None) -> None:
    if mode is None and factor is None and hold is None:
        return
    if not element.get("scheduleId"):
        raise Refused("Schedule options need a schedule on the track")
    if mode is not None:
        if mode not in ("sequential", "match"):
            raise Refused("schedule_mode must be sequential or match")
        element.set("scheduleMode", "0" if mode == "sequential" else "1")
    if factor is not None:
        factor = _int_field("reservation_factor", factor, 0, 10000)
        element.set("factor", str(factor))
    if hold is not None:
        element.set("holdCustomLoads", _bool(hold))


def _alternate(ed: Editor, element: ET.Element, place: ET.Element, alternate: str | None) -> None:
    if alternate is None:
        element.attrib.pop("alternative", None)
        return
    if element.get("trackType") != SPUR:
        raise Refused("Only spurs can have an alternate track")
    target = ed._one(place.findall("track"), alternate, "track at this location")
    if target is element:
        raise Refused("A track cannot be its own alternate")
    if target.get("trackType") == INTERCHANGE:
        raise Refused("An interchange used as an alternate leaves car routing")
    element.set("alternative", target.get("id"))


def _load_options(element: ET.Element, names: list[str]) -> None:
    mask = 0
    for name in names:
        if name not in LOAD_BITS:
            raise Refused(f"Unknown load option {name!r}; use {', '.join(LOAD_BITS)}")
        mask |= LOAD_BITS[name]
    kind = element.get("trackType")
    if mask & STAGING_BITS and kind != STAGING:
        raise Refused("Those load options exist on staging tracks only")
    if mask & LOAD_BITS["disable_load_change"] and kind != SPUR:
        raise Refused("disable_load_change is a spur option")
    # The names replace one group (Track.java:117-125): staging options on staging, spur options
    # elsewhere. Bits of the other group stay as they were.
    group = STAGING_BITS if kind == STAGING else SPUR_BITS
    try:
        old = int(element.get("loadOptions", "0"))
    except ValueError:
        old = 0
    mask |= old & ~group
    element.attrib.pop("loadOptions", None)
    if mask:
        element.set("loadOptions", str(mask))


def _pool(element: ET.Element, value: dict) -> None:
    for attr in ("pool", "minLength", "maxLength"):
        element.attrib.pop(attr, None)
    if value.get("name"):
        element.set("pool", value["name"])
        element.set("minLength", str(_int_field("pool min_length", value.get("min_length", 0))))  # Track:2758.
        if "max_length" in value:
            element.set("maxLength", str(_int_field("pool max_length", value["max_length"])))


@action()
def rename_track(ed: Editor, track: str, new: str, location: str | None = None) -> str:
    """Rename a track. Track names are stored once, so only the track changes."""
    element = ed.track(track, location)
    new = ed.check_name("track", new)
    if new in [t.get("name") for t in ed.location_of(element).findall("track")]:
        raise Refused(f"Track {new!r} already exists there")
    element.set("name", new)
    return f"Renamed track to {new}."


def track_references(ed: Editor, identity: str) -> list[str]:
    found = []
    for track in ed.tracks():
        if track.get("alternative") == identity:
            found.append(f"alternate of {track.get('name')}")
    for item in ed.loc_root.iter("item"):
        if item.get("destTrackId") == identity:
            found.append(f"schedule line {item.get('id')}")
    attrs = ("secLocationId", "secDestinationId", "nextDestTrackId", "rweDestTrackId", "rwlDestTrackId",
             "previousNextDestTrackId", "lastTrackId")
    for car in ed.cars():
        for attr in attrs[:-1]:
            if car.get(attr) == identity:
                found.append(f"car {car.get('id')} ({attr})")
    for engine in ed.engines():
        if identity in (engine.get("secLocationId"), engine.get("secDestinationId")):
            found.append(f"engine {engine.get('id')}")
    for train in ed.trains():
        if identity in (train.get("departureTrack"), train.get("terminationTrack")):
            found.append(f"train {train.get('name')}")
    return found


@action()
def delete_track(ed: Editor, track: str, location: str | None = None) -> str:
    """Delete a track nothing refers to. Anything still pointing at it is listed and the delete refused."""
    element = ed.track(track, location)
    uses = track_references(ed, element.get("id"))
    if uses:
        raise Refused(f"Still used by: {', '.join(uses[:12])}")
    place = ed.location_of(element)
    place.remove(element)
    ed.deleted_tracks.add(element.get("id"))  # Location._IdNumber keeps counting within a session.
    _indent(place, 2)
    return f"Deleted track {element.get('name')}."


@action()
def delete_location(ed: Editor, location: str) -> str:
    """Delete a location with no tracks left and no route or car pointing at it."""
    element = ed.location(location)
    identity = element.get("id")
    if element.findall("track"):
        raise Refused("Delete its tracks first")
    uses = [r.get("name") for r in ed.routes() for s in r.findall("location") if s.get("locationId") == identity]
    uses += [f"schedule line {i.get('id')}" for i in ed.loc_root.iter("item") if i.get("destinationId") == identity]
    uses += [f"track {d.get('id')}" for d in ed.loc_root.iter("destination") if d.get("id") == identity]
    attrs = ("locationId", "destinationId", "nextDestId", "rweDestId", "rwlDestId")
    uses += [f"car {c.get('id')}" for c in ed.cars() if identity in [c.get(a) for a in attrs]]
    # RollingStock:1474 reads locationId for engines too.
    uses += [f"engine {e.get('id')}" for e in ed.engines() if identity in (e.get("locationId"), e.get("destinationId"))]
    if uses:
        raise Refused(f"Still used by: {', '.join(uses[:12])}")
    holder = ed.section(ed.loc_root, "locations")
    holder.remove(element)
    _indent(holder, 1)
    return f"Deleted location {element.get('name')}."


def _moves(value) -> int:
    return _int_field("moves", value, minimum=JAVA_INT[0])


@action()
def set_track_moves(ed: Editor, moves: dict[str, int]) -> str:
    """Set the move counts that bias the builder, by track name or id. The only action that changes them.
    Any whole number: Track.setMoves takes an int, and a negative count makes a track sort first."""
    for name, value in moves.items():
        track = ed.track(name)
        track.set("moves", str(_moves(value)))
        ed.moves_allowed.add(track.get("id"))
    return f"Set moves on {len(moves)} tracks."


@action()
def reset_moves(ed: Editor, location: str | None = None) -> str:
    """Zero move counts at one location or everywhere. Only on request: it changes where traffic goes."""
    tracks = ed.location(location).findall("track") if location else ed.tracks()
    for track in tracks:
        track.set("moves", "0")
        ed.moves_allowed.add(track.get("id"))
    return f"Reset moves on {len(tracks)} tracks."
