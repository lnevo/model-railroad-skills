"""Railroad-level changes to the Operations XML files. Each action stays inside what
JMRI itself would write: settings a track type ignores are refused, not stored, because
JMRI drops them on its next save.

Fields JMRI derives are never set here. guard() checks that afterwards, independently.
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

from ops_data import (ALL, ANY, EXCLUDE, EXCLUDE_ROUTES, EXCLUDE_TRAINS, INCLUDE, INTERCHANGE, ROUTES, SPUR,
                      STAGING, TRAINS, TYPE_AND_LOAD, YARD, DIRECTIONS)
from ops_store import Doc, FILES, Refused

LOCATIONS, ROUTE_FILE, TRAIN_FILE, CAR_FILE = FILES[0], FILES[1], FILES[2], FILES[3]
SETUP_FILE, ENGINE_FILE = FILES[4], FILES[5]

TRACK_CHILDREN = ("types", "carRoads", "carLoads", "carShipLoads", "dropIds", "pickupIds", "destinations", "comments")
TRAIN_CHILDREN = ("rowColor", "route", "types", "carRoads", "cabooseRoads", "locoRoads", "carLoads", "carOwners",
                  "scripts", "railRoad", "manifestLogo")
LOAD_BITS = {"swap_default": 1, "empty_custom": 2, "generate": 4, "generate_any_spur": 8, "empty_default": 16,
             "generate_any_staging": 32, "disable_load_change": 64, "quick_service": 128}
STAGING_BITS = 1 | 2 | 4 | 8 | 16 | 32
DIRECTION_BITS = {name.lower(): bit for bit, name in DIRECTIONS.items()}
# Car attributes that only a build, a move or JMRI's own logic may set.
CAR_DERIVED = ("destinationId", "secDestinationId", "routeLocationId", "routeDestinationId", "train", "trainId",
               "scheduleId", "previousNextDestId", "previousNextDestTrackId", "previousScheduleId", "lastRouteId",
               "loadFromStaging", "clone", "nextLoad")
TRAIN_STATE = ("built", "status", "statusCode", "oldStatusCode", "current", "leadEngine", "departureTrack",
               "terminationTrack", "printed", "modified", "buildFailed", "buildFailedMessage")

ACTIONS: dict[str, dict] = {}


def action(session: bool = False):
    def wrap(fn):
        ACTIONS[fn.__name__] = {"run": fn, "session": session, "help": (fn.__doc__ or "").strip()}
        return fn
    return wrap


def _bool(value) -> str:
    return "true" if value else "false"


def _yes(value) -> str:
    return "yes" if value else "no"


def _mask(value) -> int:
    if isinstance(value, int):
        return value
    total = 0
    for part in str(value).replace(",", "/").split("/"):
        key = part.strip().lower()
        if key not in DIRECTION_BITS:
            raise Refused(f"Unknown direction {part!r}; use East, West, North, South")
        total |= DIRECTION_BITS[key]
    return total


def _next(ids, split: str | None = None) -> int:
    numbers = []
    for text in ids:
        tail = text.split(split)[-1] if split else text
        if tail.isdigit():
            numbers.append(int(tail))
    return max(numbers, default=0) + 1


def _indent(element: ET.Element, level: int) -> None:
    ET.indent(element, "  ", level)


def _place(parent: ET.Element, child: ET.Element, order: tuple[str, ...]) -> None:
    """Insert where JMRI's store() would put it."""
    rank = order.index(child.tag)
    position = 0
    for index, sibling in enumerate(parent):
        if sibling.tag in order and order.index(sibling.tag) <= rank:
            position = index + 1
    parent.insert(position, child)


def _set_list(parent: ET.Element, tag: str, item: str, values: list[str], attr: str, order, level: int,
              extra=None) -> None:
    old = parent.find(tag)
    if old is not None:
        parent.remove(old)
    if values:
        holder = ET.Element(tag)
        for value in values:
            entry = ET.SubElement(holder, item, {attr: value})
            if extra:
                entry.set("name", extra(value))
        _place(parent, holder, order)
    _indent(parent, level)


class Editor:
    def __init__(self, base: Path):
        self.base = base
        self.docs = {n: Doc(base / n) for n in FILES if (base / n).is_file()}
        self.moves_touched = False

    # File sections.
    @property
    def loc_root(self):
        return self.docs[LOCATIONS].root

    @property
    def route_root(self):
        return self.docs[ROUTE_FILE].root

    @property
    def train_root(self):
        return self.docs[TRAIN_FILE].root

    @property
    def car_root(self):
        return self.docs[CAR_FILE].root

    def section(self, root: ET.Element, tag: str, after: tuple[str, ...] = ()) -> ET.Element:
        found = root.find(tag)
        if found is None:
            found = ET.Element(tag)
            position = 0
            for index, child in enumerate(root):
                if child.tag in after:
                    position = index + 1
            root.insert(position, found)
        return found

    # Lookups by name or id.
    def _one(self, elements, text: str, kind: str) -> ET.Element:
        found = [e for e in elements if text in (e.get("id"), e.get("name"))]
        if len(found) != 1:
            raise Refused(f"{'Several' if found else 'No'} {kind} {text!r}")
        return found[0]

    def locations(self) -> list[ET.Element]:
        return self.loc_root.findall("./locations/location")

    def tracks(self) -> list[ET.Element]:
        return self.loc_root.findall("./locations/location/track")

    def location(self, text: str) -> ET.Element:
        return self._one(self.locations(), text, "location")

    def track(self, text: str, location: str | None = None) -> ET.Element:
        pool = self.location(location).findall("track") if location else self.tracks()
        return self._one(pool, text, "track")

    def location_of(self, track: ET.Element) -> ET.Element:
        return next(x for x in self.locations() if track in x.findall("track"))

    def schedules(self) -> list[ET.Element]:
        return self.loc_root.findall("./schedules/schedule")

    def schedule(self, text: str) -> ET.Element:
        return self._one(self.schedules(), text, "schedule")

    def routes(self) -> list[ET.Element]:
        return self.route_root.findall("./routes/route")

    def route(self, text: str) -> ET.Element:
        return self._one(self.routes(), text, "route")

    def trains(self) -> list[ET.Element]:
        return self.train_root.findall("./trains/train")

    def train(self, text: str) -> ET.Element:
        return self._one(self.trains(), text, "train")

    def cars(self) -> list[ET.Element]:
        return self.car_root.findall("./cars/car")

    def car(self, text: str) -> ET.Element:
        key = text.replace(" ", "").upper()
        for car in self.cars():
            if car.get("id", "").replace(" ", "").upper() == key:
                return car
        raise Refused(f"No car {text!r}")

    # Name registers in the car file.
    def registered(self, group: str, tag: str) -> list[ET.Element]:
        return self.car_root.findall(f"./{group}/{tag}")

    def register(self, group: str, tag: str, value: str, attr: str = "name") -> None:
        if not value:
            return
        holder = self.section(self.car_root, group)
        if value not in [e.get(attr) for e in holder.findall(tag)]:
            ET.SubElement(holder, tag, {attr: value})
            _indent(holder, 1)

    def car_types(self) -> list[str]:
        return [e.get("name") for e in self.registered("types", "type")]

    def loco_types(self) -> list[str]:
        if ENGINE_FILE not in self.docs:
            return []
        return [e.get("name") for e in self.docs[ENGINE_FILE].root.findall("./types/type")]

    def defaults(self) -> tuple[str, str]:
        d = self.car_root.find("./loads/defaults")
        return (d.get("empty", "E"), d.get("load", "L")) if d is not None else ("E", "L")

    def need_type(self, name: str) -> None:
        if name not in self.car_types() and name not in self.loco_types():
            raise Refused(f"Unknown type {name!r}. Add it first with add_car_type.")

    def type_entries(self, holder: ET.Element) -> list[str]:
        types = holder.find("types")
        return [e.get("name") for e in types] if types is not None else []

    def add_type_to(self, holder: ET.Element, name: str, level: int) -> bool:
        types = holder.find("types")
        if types is None:
            types = ET.Element("types")
            holder.insert(0, types)
        if name in self.type_entries(holder):
            return False
        tag = "locoType" if name in self.loco_types() and name not in self.car_types() else "carType"
        ET.SubElement(types, tag, {"name": name})
        _indent(holder, level)
        return True

    def run(self, actions: list[dict], session_only: bool = False) -> list[str]:
        lines = []
        for number, item in enumerate(actions, 1):
            item = dict(item)
            name = item.pop("action", "")
            entry = ACTIONS.get(name)
            if entry is None:
                raise Refused(f"Action {number}: unknown action {name!r}")
            if session_only and not entry["session"]:
                raise Refused(f"Action {number}: {name} is a setup change, so it needs ops_plan first")
            try:
                lines.append(entry["run"](self, **item))
            except TypeError as exc:
                raise Refused(f"Action {number} ({name}): {exc}") from exc
            except Refused as exc:
                raise Refused(f"Action {number} ({name}): {exc}") from exc
        return lines


def guard(editor: Editor, allowed_cars: tuple[str, ...] = ()) -> None:
    """Compare against the files on disk: derived fields must not have moved."""
    before = Editor(editor.base)
    old_tracks = {t.get("id"): t for t in before.tracks()}
    for track in editor.tracks():
        old = old_tracks.get(track.get("id"))
        if old is None:
            continue
        if not editor.moves_touched and old.get("moves") != track.get("moves"):
            raise Refused(f"Internal check: moves on {track.get('name')} would change")
    old_cars = {c.get("id"): c for c in before.cars()}
    for car in editor.cars():
        old = old_cars.get(car.get("id"))
        if old is None or car.get("id") in allowed_cars:
            continue
        for attr in CAR_DERIVED:
            if old.get(attr) != car.get(attr):
                raise Refused(f"Internal check: {attr} on car {car.get('id')} would change")
    old_trains = {t.get("id"): t for t in before.trains()}
    for train in editor.trains():
        old = old_trains.get(train.get("id"))
        if old is not None:
            for attr in TRAIN_STATE:
                if old.get(attr) != train.get(attr):
                    raise Refused(f"Internal check: {attr} on train {train.get('name')} would change")


# ---- Names and types ------------------------------------------------------------


@action()
def add_car_type(ed: Editor, name: str, like: str | None = None) -> str:
    """Add a car type. With like, every location, track and train that takes that type takes this too."""
    if name in ed.car_types():
        raise Refused(f"Type {name!r} already exists")
    ed.register("types", "type", name)
    done = [0, 0, 0]
    if like:
        ed.need_type(like)
        for location in ed.locations():
            if like in ed.type_entries(location):
                done[0] += ed.add_type_to(location, name, 2)
            for track in location.findall("track"):
                if like in ed.type_entries(track):
                    done[1] += ed.add_type_to(track, name, 3)
        for train in ed.trains():
            if like in ed.type_entries(train):
                done[2] += ed.add_type_to(train, name, 2)
    return f"Added type {name}: {done[0]} locations, {done[1]} tracks, {done[2]} trains."


@action()
def add_load(ed: Editor, name: str, types: list[str], load_type: str = "Load", priority: str | None = None,
             hazardous: bool = False, pickup_comment: str = "", drop_comment: str = "") -> str:
    """Add a custom load to car types. load_type is Load or Empty. It is only a label for routing."""
    if name in ed.defaults():
        raise Refused(f"{name!r} is a default load name")
    if load_type not in ("Load", "Empty"):
        raise Refused("load_type must be Load or Empty")
    if priority not in (None, "Low", "Medium", "High"):
        raise Refused("priority must be Low, Medium or High")
    loads = ed.section(ed.car_root, "loads", ("owners", "lengths", "colors", "types", "roads"))
    for kind in types:
        if kind not in ed.car_types():
            raise Refused(f"Unknown car type {kind!r}")
        holder = next((e for e in loads.findall("load") if e.get("type") == kind), None)
        if holder is None:
            holder = ET.SubElement(loads, "load", {"type": kind})
        if name in [e.get("name") for e in holder.findall("carLoad")]:
            raise Refused(f"{kind} already has load {name!r}")
        attrs = {"name": name}
        if priority and priority != "Low":
            attrs["priority"] = priority
        if hazardous:
            attrs["hazardous"] = "true"
        if pickup_comment:
            attrs["pickupComment"] = pickup_comment
        if drop_comment:
            attrs["dropComment"] = drop_comment
        attrs["loadType"] = load_type
        ET.SubElement(holder, "carLoad", attrs)
    _indent(loads, 1)
    return f"Added load {name} for {', '.join(types)}."


def _rename_values(element: ET.Element, tags: dict[str, tuple[str, ...]], old: str, new: str) -> int:
    count = 0
    for node in element.iter():
        for attr in tags.get(node.tag, ()):
            if node.get(attr) == old:
                node.set(attr, new)
                count += 1
    return count


@action()
def rename_car_type(ed: Editor, old: str, new: str) -> str:
    """Rename a car type everywhere it is used, including type and load pairs."""
    if old not in ed.car_types():
        raise Refused(f"Unknown type {old!r}")
    if new in ed.car_types():
        raise Refused(f"Type {new!r} already exists")
    count = _rename_values(ed.car_root, {"type": ("name",), "load": ("type",), "car": ("type",)}, old, new)
    count += _rename_values(ed.loc_root, {"carType": ("name",), "item": ("type",)}, old, new)
    count += _rename_values(ed.train_root, {"carType": ("name",)}, old, new)
    prefix = f"{old}{TYPE_AND_LOAD}"
    for root in (ed.loc_root, ed.train_root):
        for node in root.iter("carLoad"):
            if node.get("name", "").startswith(prefix):
                node.set("name", f"{new}{TYPE_AND_LOAD}{node.get('name')[len(prefix):]}")
                count += 1
    return f"Renamed type {old} to {new}: {count} places."


@action()
def rename_load(ed: Editor, old: str, new: str, car_type: str | None = None) -> str:
    """Rename a custom load, for one type or all, through cars, schedules, tracks and trains."""
    if old in ed.defaults():
        raise Refused("Rename a default load from JMRI: it is one name shared by every type")
    if new in ed.defaults():
        raise Refused(f"{new!r} is a default load name")
    count = 0
    for holder in ed.car_root.findall("./loads/load"):
        if car_type in (None, holder.get("type")):
            for entry in holder.findall("carLoad"):
                if entry.get("name") == old:
                    entry.set("name", new)
                    count += 1
    if not count:
        raise Refused(f"No load {old!r}")
    match = lambda kind: car_type in (None, kind)  # noqa: E731
    for car in ed.cars():
        if match(car.get("type")):
            for attr in ("load", "rweLoad", "rwlLoad"):
                if car.get(attr) == old:
                    car.set(attr, new)
                    count += 1
    for item in ed.loc_root.iter("item"):
        if match(item.get("type")):
            for attr in ("load", "ship"):
                if item.get(attr) == old:
                    item.set(attr, new)
                    count += 1
    for root in (ed.loc_root, ed.train_root):
        for node in root.iter("carLoad"):
            value = node.get("name", "")
            if value == old and car_type is None:
                node.set("name", new)
                count += 1
            elif TYPE_AND_LOAD in value:
                kind, load = value.split(TYPE_AND_LOAD, 1)
                if load == old and match(kind):
                    node.set("name", f"{kind}{TYPE_AND_LOAD}{new}")
                    count += 1
    return f"Renamed load {old} to {new}: {count} places."


@action()
def rename_road(ed: Editor, old: str, new: str) -> str:
    """Rename a road in the road list, track and train filters and schedule lines. Cars keep theirs, since a car's id holds its road."""
    if old not in [e.get("name") for e in ed.registered("roads", "road")]:
        raise Refused(f"Unknown road {old!r}")
    if any(c.get("roadName") == old for c in ed.cars()):
        raise Refused(f"Cars still carry road {old}. A car's id contains its road, so rename those in JMRI")
    count = _rename_values(ed.car_root, {"road": ("name",)}, old, new)
    count += _rename_values(ed.loc_root, {"carRoad": ("name",), "item": ("road",)}, old, new)
    count += _rename_values(ed.train_root, {"carRoad": ("name",)}, old, new)
    return f"Renamed road {old} to {new}: {count} places."


# ---- Locations and tracks ---------------------------------------------------------


@action()
def add_location(ed: Editor, name: str, types: list[str] | None = None, directions: str | int = 15,
                 like: str | None = None, comment: str = "") -> str:
    """Add a location. Types come from types, or like, or every car type."""
    if name in [x.get("name") for x in ed.locations()]:
        raise Refused(f"Location {name!r} already exists")
    wanted = types if types is not None else (ed.type_entries(ed.location(like)) if like else ed.car_types())
    number = _next(x.get("id") for x in ed.locations())
    element = ET.Element("location", {"id": str(number), "name": name, "ops": "Normal", "dir": str(_mask(directions)),
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
        types = element.find("types")
        for entry in list(types):
            if entry.get("name") == kind:
                types.remove(entry)
    _indent(element, 2)
    return f"Updated location {element.get('name')}."


@action()
def rename_location(ed: Editor, location: str, new: str) -> str:
    """Rename a location. Ids stay; every stored copy of the name follows."""
    element = ed.location(location)
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
    """Add a track. Other location tracks keep their move counts, unlike adding one in JMRI's window."""
    if type not in (SPUR, YARD, INTERCHANGE, STAGING):
        raise Refused(f"type must be {SPUR}, {YARD}, {INTERCHANGE} or {STAGING}")
    place = ed.location(location)
    if name in [t.get("name") for t in place.findall("track")]:
        raise Refused(f"{place.get('name')} already has track {name!r}")
    existing = [t.get("trackType") for t in place.findall("track")]
    if existing and (type == STAGING) != (STAGING in existing):
        raise Refused("JMRI's windows keep staging and other track types at separate locations")
    if length < 0:
        raise Refused("length cannot be negative")
    number = _next((t.get("id") for t in place.findall("track")), "s")
    identity = f"{place.get('id')}s{number}"
    element = ET.Element("track", {"id": identity, "name": name, "trackType": type,
                                   "dir": str(_mask(directions) if directions is not None else place.get("dir", "15")),
                                   "length": str(length), "moves": str(moves)})
    if type in (INTERCHANGE, STAGING):
        element.set("onlyCarWithFD", "false")
    place.append(element)
    for kind in types if types is not None else ed.type_entries(place):
        ed.need_type(kind)
        ed.add_type_to(place, kind, 2)
        ed.add_type_to(element, kind, 3)
    if moves:
        ed.moves_touched = True
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
        if length < 0:
            raise Refused("length cannot be negative")
        element.set("length", str(length))
    if directions is not None:
        element.set("dir", str(_mask(directions)))
    for name in add_types or []:
        ed.need_type(name)
        ed.add_type_to(place, name, 2)
        ed.add_type_to(element, name, 3)
    for name in remove_types or []:
        holder = element.find("types")
        for entry in list(holder):
            if entry.get("name") == name:
                holder.remove(entry)
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
        if not 0 <= factor <= 10000:
            raise Refused("reservation_factor must be 0 to 10000")
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
    element.attrib.pop("loadOptions", None)
    if mask:
        element.set("loadOptions", str(mask))


def _pool(element: ET.Element, value: dict) -> None:
    for attr in ("pool", "minLength", "maxLength"):
        element.attrib.pop(attr, None)
    if value.get("name"):
        element.set("pool", value["name"])
        element.set("minLength", str(value.get("min_length", 0)))
        if "max_length" in value:
            element.set("maxLength", str(value["max_length"]))


@action()
def rename_track(ed: Editor, track: str, new: str, location: str | None = None) -> str:
    """Rename a track. Track names are stored once, so only the track changes."""
    element = ed.track(track, location)
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
    if ENGINE_FILE in ed.docs:
        for engine in ed.docs[ENGINE_FILE].root.findall("./engines/engine"):
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
    if uses:
        raise Refused(f"Still used by: {', '.join(uses[:12])}")
    holder = ed.section(ed.loc_root, "locations")
    holder.remove(element)
    _indent(holder, 1)
    return f"Deleted location {element.get('name')}."


@action()
def set_track_moves(ed: Editor, moves: dict[str, int]) -> str:
    """Set the move counts that bias the builder, by track name or id. The only action that changes them."""
    for name, value in moves.items():
        ed.track(name).set("moves", str(int(value)))
    ed.moves_touched = True
    return f"Set moves on {len(moves)} tracks."


@action()
def reset_moves(ed: Editor, location: str | None = None) -> str:
    """Zero move counts at one location or everywhere. Only on request: it changes where traffic goes."""
    tracks = ed.location(location).findall("track") if location else ed.tracks()
    for track in tracks:
        track.set("moves", "0")
    ed.moves_touched = True
    return f"Reset moves on {len(tracks)} tracks."


# ---- Schedules --------------------------------------------------------------------


def _line(ed: Editor, schedule_id: str, number: int, sequence: int, line: dict) -> ET.Element:
    unknown = set(line) - {"type", "road", "receive", "ship", "random", "wait", "count", "setout_day", "pickup_day",
                           "destination", "track", "comment"}
    if unknown:
        raise Refused(f"Unknown schedule line fields: {', '.join(sorted(unknown))}")
    kind = line["type"]
    if kind not in ed.car_types():
        raise Refused(f"Unknown car type {kind!r}")
    destination = line.get("destination")
    place = ed.location(destination) if destination else None
    if line.get("track") and place is None:
        raise Refused("A schedule line's track needs a destination too")
    track = ed._one(place.findall("track"), line["track"], "track") if line.get("track") else None
    if place is not None and place.findall("track") and all(
            t.get("trackType") == STAGING for t in place.findall("track")):
        raise Refused("JMRI's schedule window does not offer staging as a ship destination")
    days = {s.get("name"): s.get("id") for s in ed.train_root.findall("./schedules/schedule")}
    day = lambda text: days.get(text, text) if text else ""  # noqa: E731
    element = ET.Element("item", {
        "id": f"{schedule_id}c{number}", "sequenceId": str(sequence), "random": str(line.get("random", "")),
        "trainScheduleId": day(line.get("setout_day")), "pickupTrainScheduleId": day(line.get("pickup_day")),
        "count": str(line.get("count", 1)), "wait": str(line.get("wait", 0)), "type": kind,
        "road": line.get("road", ""), "load": line.get("receive", ""), "ship": line.get("ship", ""),
        "comment": line.get("comment", ""), "hits": "0"})
    if place is not None:
        element.set("destinationId", place.get("id"))
    if track is not None:
        element.set("destTrackId", track.get("id"))
    return element


@action()
def add_schedule(ed: Editor, name: str, lines: list[dict], comment: str = "") -> str:
    """Add a schedule. Each line: type, and any of road, receive, ship, random, wait, count, setout_day, pickup_day, destination, track."""
    if name in [s.get("name") for s in ed.schedules()]:
        raise Refused(f"Schedule {name!r} already exists; JMRI would share one schedule by name")
    if not lines:
        raise Refused("A schedule needs at least one line")
    holder = ed.section(ed.loc_root, "schedules", ("locations", "divisions"))
    identity = str(_next(s.get("id") for s in ed.schedules()))
    element = ET.SubElement(holder, "schedule", {"id": identity, "name": name, "comment": comment})
    for index, line in enumerate(lines, 1):
        element.append(_line(ed, identity, index, index, line))
    _indent(holder, 1)
    return f"Added schedule {name} with {len(lines)} lines (id {identity})."


@action()
def replace_schedule_lines(ed: Editor, schedule: str, lines: list[dict]) -> str:
    """Replace a schedule's lines. Refused while a car holds a line. Tracks restart at line one; moves stay."""
    element = ed.schedule(schedule)
    if not lines:
        raise Refused("A schedule needs at least one line")
    old = {i.get("id") for i in element.findall("item")}
    holders = [c.get("id") for c in ed.cars() if c.get("scheduleId") in old]
    if holders:
        raise Refused(f"Cars are on their way under these lines: {', '.join(holders[:8])}")
    identity = element.get("id")
    start = _next((i for i in old), "c")
    for item in element.findall("item"):
        element.remove(item)
    for index, line in enumerate(lines):
        element.append(_line(ed, identity, start + index, index + 1, line))
    _indent(element, 2)
    first = f"{identity}c{start}"
    for track in ed.tracks():
        if track.get("scheduleId") == identity:
            track.set("itemId", first)
            track.set("itemCount", "0")
    return f"Replaced lines in schedule {element.get('name')}: {len(lines)} lines."


@action()
def rename_schedule(ed: Editor, schedule: str, new: str) -> str:
    """Rename a schedule and the name copy each track keeps."""
    element = ed.schedule(schedule)
    if new in [s.get("name") for s in ed.schedules()]:
        raise Refused(f"Schedule {new!r} already exists")
    element.set("name", new)
    for track in ed.tracks():
        if track.get("scheduleId") == element.get("id"):
            track.set("schedule", new)
    return f"Renamed schedule to {new}."


@action()
def delete_schedule(ed: Editor, schedule: str) -> str:
    """Delete a schedule no track uses."""
    element = ed.schedule(schedule)
    users = [t.get("name") for t in ed.tracks() if t.get("scheduleId") == element.get("id")]
    if users:
        raise Refused(f"Still on: {', '.join(users)}")
    holder = ed.section(ed.loc_root, "schedules")
    holder.remove(element)
    _indent(holder, 1)
    return f"Deleted schedule {element.get('name')}."


@action()
def add_industry(ed: Editor, location: str, name: str, length: int, lines: list[dict], types: list[str] | None = None,
                 mode: str = "match", alternate: str | None = None, hold_custom: bool = False,
                 directions: str | int | None = None) -> str:
    """Add a spur and its schedule in one step. Types default to those in the lines."""
    wanted = types if types is not None else sorted({line["type"] for line in lines})
    schedule = f"{name} Schedule"
    add_schedule(ed, schedule, lines)
    add_track(ed, location, name, SPUR, length, types=wanted, directions=directions)
    settings: dict = {"schedule": schedule, "schedule_mode": mode, "hold_custom": hold_custom}
    if alternate:
        settings["alternate"] = alternate
    update_track(ed, name, location=location, **settings)
    return f"Added industry {name} at {location} with schedule {schedule}."


@action()
def mirror_schedule(ed: Editor, spur: str, sources: list[str] | None = None, location: str | None = None,
                    name: str | None = None) -> str:
    """Give a storage spur a schedule that receives what source spurs ship and ships what they receive."""
    target = ed.track(spur, location)
    if target.get("trackType") != SPUR:
        raise Refused(f"{target.get('name')} is not a spur")
    chosen = [ed.track(s) for s in sources] if sources else [
        t for t in ed.tracks() if t.get("scheduleId") and t is not target]
    seen, lines = set(), []
    for track in chosen:
        if not track.get("scheduleId"):
            raise Refused(f"{track.get('name')} has no schedule")
        for item in ed.schedule(track.get("scheduleId")).findall("item"):
            pair = (item.get("type"), item.get("ship", ""), item.get("load", ""))
            if pair in seen or (not pair[1] and not pair[2]):
                continue
            seen.add(pair)
            lines.append({"type": pair[0], "receive": pair[1], "ship": pair[2]})
    if not lines:
        raise Refused("The source schedules have no loads to mirror")
    for line in lines:
        if line["type"] not in ed.type_entries(target):
            update_track(ed, target.get("id"), add_types=[line["type"]])
    title = name or f"{target.get('name')} Mirror"
    add_schedule(ed, title, lines)
    update_track(ed, target.get("id"), schedule=title, schedule_mode="match")
    return f"Mirrored {len(chosen)} spurs onto {target.get('name')}: {len(lines)} lines."


# ---- Staging and interchange chains ------------------------------------------------


@action()
def setup_custom_staging(ed: Editor, track: str, location: str | None = None, ship_loads: list[str] | None = None,
                         local_route_only: bool = False, any_staging: bool = True) -> str:
    """Set a staging track for custom loads: empty arrivals, generate outbound loads, and ship only those loads."""
    element = ed.track(track, location)
    if element.get("trackType") != STAGING:
        raise Refused(f"{element.get('name')} is not staging")
    options = ["empty_custom", "generate" if local_route_only else "generate_any_spur"]
    if any_staging:
        options.append("generate_any_staging")
    defaults = list(ed.defaults())
    settings: dict = {"load_options": options, "loads": {"option": ALL},
                      "ship_loads": {"option": INCLUDE, "names": ship_loads} if ship_loads
                      else {"option": EXCLUDE, "names": defaults}}
    update_track(ed, element.get("id"), **settings)
    return (f"Set {element.get('name')} for custom loads. An empty that finds no load now fails the build, "
            "because the ship list refuses it; the audit's staging rules show what to check.")


@action()
def setup_interchange(ed: Editor, track: str, location: str | None = None, set_out_by: list[str] | None = None,
                      pulled_by: list[str] | None = None, routed_only: bool | None = None,
                      destinations: list[str] | None = None) -> str:
    """Set an interchange's trains in, trains out, Routed flag and destinations in one step."""
    element = ed.track(track, location)
    if element.get("trackType") != INTERCHANGE:
        raise Refused(f"{element.get('name')} is not an interchange")
    settings: dict = {}
    if set_out_by is not None:
        settings["drop"] = {"option": TRAINS, "names": set_out_by} if set_out_by else {"option": ANY}
    if pulled_by is not None:
        settings["pickup"] = {"option": TRAINS, "names": pulled_by} if pulled_by else {"option": ANY}
    if routed_only is not None:
        settings["only_final_destination"] = routed_only
    if destinations is not None:
        settings["destinations"] = {"option": INCLUDE, "names": destinations} if destinations else {"option": ALL}
    update_track(ed, element.get("id"), **settings)
    return f"Set interchange {element.get('name')}."


# ---- Routes and trains --------------------------------------------------------------


STOP_FIELDS = {"direction", "max_moves", "max_length", "pickups", "drops", "local_moves", "random", "wait",
               "depart_time", "comment"}


def _stop_values(element: ET.Element, stop: dict) -> None:
    unknown = set(stop) - STOP_FIELDS - {"location"}
    if unknown:
        raise Refused(f"Unknown stop fields: {', '.join(sorted(unknown))}")
    if "direction" in stop:
        mask = _mask(stop["direction"])
        if mask not in DIRECTIONS:
            raise Refused("A route stop has one direction")
        element.set("trainDirection", str(mask))
    plain = {"max_moves": "maxCarMoves", "max_length": "maxTrainLength", "wait": "wait", "comment": "comment"}
    for key, attr in plain.items():
        if key in stop:
            element.set(attr, str(stop[key]))
    if "random" in stop:
        element.set("randomControl", str(stop["random"]))
    if "depart_time" in stop:
        element.set("departTime", stop["depart_time"])
    for key, attr in (("pickups", "pickups"), ("drops", "drops"), ("local_moves", "localMoves")):
        if key in stop:
            element.set(attr, _yes(stop[key]))


def _new_stop(ed: Editor, route: ET.Element, number: int, sequence: int, stop: dict) -> ET.Element:
    place = ed.location(stop["location"])
    element = ET.Element("location", {
        "id": f"{route.get('id')}r{number}", "name": place.get("name"), "locationId": place.get("id"),
        "sequenceId": str(sequence), "trainDirection": "1", "maxTrainLength": "1000", "grade": "0.0",
        "maxCarMoves": "5", "randomControl": "Off", "pickups": "yes", "drops": "yes", "localMoves": "yes",
        "wait": "0", "departTime": "", "order": "0", "trainIconX": "0", "trainIconY": "0",
        "commentColor": "black", "comment": ""})
    _stop_values(element, stop)
    return element


@action()
def add_route(ed: Editor, name: str, stops: list[dict], comment: str = "") -> str:
    """Add a route. Each stop: location, and any of direction, max_moves, max_length, pickups, drops, local_moves."""
    if name in [r.get("name") for r in ed.routes()]:
        raise Refused(f"Route {name!r} already exists")
    if not stops:
        raise Refused("A route needs at least one stop")
    holder = ed.section(ed.route_root, "routes")
    identity = str(_next(r.get("id") for r in ed.routes()))
    element = ET.SubElement(holder, "route", {"id": identity, "name": name, "comment": comment})
    for index, stop in enumerate(stops, 1):
        element.append(_new_stop(ed, element, index, index, stop))
    _indent(holder, 1)
    return f"Added route {name} with {len(stops)} stops (id {identity})."


@action()
def update_stop(ed: Editor, route: str, stop: str | int, **fields) -> str:
    """Change a route stop, named by location or by position from 1. A location the route revisits needs the position."""
    element = ed.route(route)
    stops = sorted(element.findall("location"), key=lambda s: int(s.get("sequenceId", 0)))
    if isinstance(stop, int):
        if not 1 <= stop <= len(stops):
            raise Refused(f"Route has {len(stops)} stops")
        target = stops[stop - 1]
    else:
        found = [s for s in stops if s.get("name") == stop]
        if len(found) != 1:
            raise Refused(f"{'Several stops' if found else 'No stop'} named {stop!r}; use a position")
        target = found[0]
    _stop_values(target, fields)
    return f"Updated stop {target.get('name')} on {element.get('name')}."


@action()
def rename_route(ed: Editor, route: str, new: str) -> str:
    """Rename a route and the name copy each train keeps."""
    element = ed.route(route)
    if new in [r.get("name") for r in ed.routes()]:
        raise Refused(f"Route {new!r} already exists")
    element.set("name", new)
    for train in ed.trains():
        link = train.find("route")
        if link is not None and link.get("id") == element.get("id"):
            link.set("name", new)
    return f"Renamed route to {new}."


@action()
def delete_route(ed: Editor, route: str) -> str:
    """Delete a route no train or track list uses."""
    element = ed.route(route)
    identity = element.get("id")
    uses = [t.get("name") for t in ed.trains() if t.find("route") is not None and t.find("route").get("id") == identity]
    for track in ed.tracks():
        for option, tag, item in (("dropOption", "dropIds", "dropId"), ("pickupOption", "pickupIds", "pickupId")):
            if track.get(option) in (ROUTES, EXCLUDE_ROUTES) and identity in [
                    e.get("id") for e in track.findall(f"{tag}/{item}")]:
                uses.append(track.get("name"))
    uses += [c.get("id") for c in ed.cars() if c.get("lastRouteId") == identity]
    if uses:
        raise Refused(f"Still used by: {', '.join(uses[:12])}")
    holder = ed.section(ed.route_root, "routes")
    holder.remove(element)
    _indent(holder, 1)
    return f"Deleted route {element.get('name')}."


TRAIN_DEFAULTS = {
    "description": "", "departHour": "00", "departMinute": "00", "builtStartYear": "", "builtEndYear": "",
    "numberEngines": "0", "engineRoad": "", "engineModel": "", "requires": "0", "cabooseRoad": "",
    "buildNormal": "false", "toTerminal": "false", "allowLocalMoves": "true", "allowReturn": "false",
    "allowThroughCars": "true", "serviceAll": "false", "sendCustomStaging": "false", "buildConsist": "false",
    "built": "false", "build": "true", "buildFailed": "false", "buildFailedMessage": "", "printed": "false",
    "modified": "false", "switchListStatus": "", "status": "Train reset", "TerminationDate": "",
    "RequestedCars": "0", "statusCode": "0", "oldStatusCode": "0", "comment": "", "showTimes": "true"}
TRAIN_FIELDS = {"description": "description", "engines": "numberEngines", "engine_road": "engineRoad",
                "engine_model": "engineModel", "requires": "requires", "caboose_road": "cabooseRoad",
                "depart_hour": "departHour", "depart_minute": "departMinute", "built_start": "builtStartYear",
                "built_end": "builtEndYear", "comment": "comment"}
TRAIN_FLAGS = {"build": "build", "build_normal": "buildNormal", "to_terminal": "toTerminal",
               "allow_local_moves": "allowLocalMoves", "allow_return": "allowReturn",
               "allow_through_cars": "allowThroughCars", "service_all": "serviceAll",
               "send_custom_staging": "sendCustomStaging"}
TRAIN_LISTS = {"roads": ("carRoadOption", "carRoads", "carRoad"), "caboose_roads": ("cabooseRoadOption", "cabooseRoads", "carRoad"),
               "loads": ("carLoadOption", "carLoads", "carLoad"), "owners": ("carOwnerOption", "carOwners", "carOwner")}


def _train_fields(ed: Editor, element: ET.Element, fields: dict) -> None:
    for key, value in fields.items():
        if key in TRAIN_FIELDS:
            element.set(TRAIN_FIELDS[key], str(value))
        elif key in TRAIN_FLAGS:
            element.set(TRAIN_FLAGS[key], _bool(value))
        elif key in TRAIN_LISTS:
            attr, tag, item = TRAIN_LISTS[key]
            option = value.get("option", ALL)
            if option not in (ALL, INCLUDE, EXCLUDE):
                raise Refused("option must be All, Include or Exclude")
            element.attrib.pop(attr, None)
            names = value.get("names", []) if option != ALL else []
            if option != ALL:
                element.set(attr, option)
            _set_list(element, tag, item, names, "name", TRAIN_CHILDREN, 2)
        elif key == "add_types":
            for kind in value:
                ed.need_type(kind)
                ed.add_type_to(element, kind, 2)
        elif key == "remove_types":
            holder = element.find("types")
            for entry in list(holder):
                if entry.get("name") in value:
                    holder.remove(entry)
        else:
            raise Refused(f"Unknown train field {key!r}")


def _serve_tracks(ed: Editor, train: ET.Element, like: ET.Element | None) -> int:
    """Lists hold train ids, so a new train is silently barred until it is added to each one."""
    link = train.find("route")
    stops = {s.get("locationId") for s in ed.route(link.get("id")).findall("location")}
    count = 0
    for place in ed.locations():
        if place.get("id") not in stops:
            continue
        for track in place.findall("track"):
            for option, tag, item in (("dropOption", "dropIds", "dropId"), ("pickupOption", "pickupIds", "pickupId")):
                if track.get(option) != TRAINS:
                    continue
                holder = track.find(tag)
                ids = [e.get("id") for e in holder.findall(item)] if holder is not None else []
                if like is not None and like.get("id") not in ids:
                    continue
                if holder is None:
                    holder = ET.Element(tag)
                    _place(track, holder, TRACK_CHILDREN)
                ET.SubElement(holder, item, {"id": train.get("id")})
                _indent(track, 3)
                count += 1
    return count


@action()
def add_train(ed: Editor, name: str, route: str, like: str | None = None, serve_tracks: bool = True, **fields) -> str:
    """Add a train and, by default, put it on every train list at its route's tracks. With like, copy that train's settings and lists."""
    if name in [t.get("name") for t in ed.trains()]:
        raise Refused(f"Train {name!r} already exists")
    target = ed.route(route)
    holder = ed.section(ed.train_root, "trains", ("options",))
    identity = str(_next(t.get("id") for t in ed.trains()))
    source = ed.train(like) if like else None
    if source is not None:
        element = copy.deepcopy(source)
        for attr in ("current", "leadEngine", "departureTrack", "terminationTrack"):
            element.attrib.pop(attr, None)
        for attr in ("built", "buildFailed", "printed", "modified", "statusCode", "oldStatusCode", "status",
                     "buildFailedMessage", "TerminationDate", "switchListStatus", "RequestedCars"):
            if attr in TRAIN_DEFAULTS:
                element.set(attr, TRAIN_DEFAULTS[attr])
        element.set("id", identity)
        element.set("name", name)
        old = element.find("route")
        if old is not None:
            element.remove(old)
    else:
        element = ET.Element("train", {"id": identity, "name": name, **TRAIN_DEFAULTS})
        ET.SubElement(element, "rowColor", {"name": "", "resetRowColor": ""})
    _place(element, ET.Element("route", {"name": target.get("name"), "id": target.get("id")}), TRAIN_CHILDREN)
    holder.append(element)
    if source is None:
        for kind in ed.car_types() + ed.loco_types():
            ed.add_type_to(element, kind, 2)
    _train_fields(ed, element, fields)
    _indent(holder, 1)
    served = _serve_tracks(ed, element, source) if serve_tracks else 0
    return f"Added train {name} (id {identity}); added to {served} track lists."


@action()
def update_train(ed: Editor, train: str, **fields) -> str:
    """Change train settings: description, engines, requires, departure, flags, types and road, load and owner lists."""
    element = ed.train(train)
    _train_fields(ed, element, fields)
    _indent(element, 2)
    return f"Updated train {element.get('name')}."


@action()
def set_train_route(ed: Editor, train: str, route: str) -> str:
    """Move a train to another route. Its skips belong to the old route, so they are cleared."""
    element = ed.train(train)
    target = ed.route(route)
    link = element.find("route")
    if link is None:
        link = ET.Element("route")
        _place(element, link, TRAIN_CHILDREN)
    for child in list(link):
        link.remove(child)
    link.set("name", target.get("name"))
    link.set("id", target.get("id"))
    _indent(element, 2)
    return f"{element.get('name')} now runs {target.get('name')}; skips cleared."


@action()
def set_train_skips(ed: Editor, train: str, stops: list[str]) -> str:
    """Set the route stops this train skips, by location name."""
    element = ed.train(train)
    link = element.find("route")
    route = ed.route(link.get("id"))
    for child in list(link):
        link.remove(child)
    if stops:
        skips = ET.SubElement(link, "skips")
        for name in stops:
            stop = ed._one(route.findall("location"), name, "stop")
            ET.SubElement(skips, "location", {"name": stop.get("name"), "id": stop.get("id")})
    _indent(element, 2)
    return f"{element.get('name')} skips {len(stops)} stops."


@action()
def rename_train(ed: Editor, train: str, new: str) -> str:
    """Rename a train. Track lists hold ids, so they keep working."""
    element = ed.train(train)
    if new in [t.get("name") for t in ed.trains()]:
        raise Refused(f"Train {new!r} already exists")
    element.set("name", new)
    return f"Renamed train to {new}."


@action()
def delete_train(ed: Editor, train: str) -> str:
    """Delete a train. It is taken off track lists. Refused while a car is assigned to it."""
    element = ed.train(train)
    identity = element.get("id")
    cars = [c.get("id") for c in ed.cars() if c.get("trainId") == identity]
    if cars:
        raise Refused(f"Cars are on it: {', '.join(cars[:8])}")
    for track in ed.tracks():
        for option, tag, item in (("dropOption", "dropIds", "dropId"), ("pickupOption", "pickupIds", "pickupId")):
            holder = track.find(tag)
            if holder is not None and track.get(option) in (TRAINS, EXCLUDE_TRAINS):
                for entry in list(holder.findall(item)):
                    if entry.get("id") == identity:
                        holder.remove(entry)
                _indent(track, 3)
    holder = ed.section(ed.train_root, "trains")
    holder.remove(element)
    _indent(holder, 1)
    return f"Deleted train {element.get('name')}."


@action()
def set_active_day(ed: Editor, name: str | None) -> str:
    """Set the active train schedule (day), or none."""
    ids = {s.get("name"): s.get("id") for s in ed.train_root.findall("./schedules/schedule")}
    if name and name not in ids:
        raise Refused(f"No train schedule {name!r}")
    options = ed.section(ed.train_root, "options")
    node = options.find("trainScheduleOptions")
    if node is None:
        node = ET.SubElement(options, "trainScheduleOptions")
        _indent(options, 1)
    node.set("activeId", ids[name] if name else "")
    return f"Active day: {name or 'none'}."


# ---- Rolling stock ------------------------------------------------------------------


CAR_FIELDS = {"length": "length", "color": "color", "weight": "weight", "weight_tons": "weightTons", "built": "built",
              "owner": "owner", "comment": "comment", "rfid": "rfid", "value": "value", "blocking": "blocking"}
CAR_FLAGS = {"out_of_service": "outOfService", "location_unknown": "locUnknown", "passenger": "passenger",
             "hazardous": "hazardous", "caboose": "caboose", "fred": "fred", "utility": "utility"}


def _car_fields(ed: Editor, element: ET.Element, fields: dict) -> None:
    for key, value in fields.items():
        if key in CAR_FIELDS:
            attr = CAR_FIELDS[key]
            text = str(value)
            element.attrib.pop(attr, None)
            if text and text != "0":
                element.set(attr, text)
            elif key == "length":
                element.set(attr, text)
            if key == "color":
                ed.register("colors", "color", text)
            if key == "owner":
                ed.register("owners", "owner", text)
            if key == "length":
                ed.register("lengths", "length", text, "value")
        elif key in CAR_FLAGS:
            attr = CAR_FLAGS[key]
            element.attrib.pop(attr, None)
            if value:
                element.set(attr, "true")
        elif key == "type":
            if value not in ed.car_types():
                raise Refused(f"Unknown car type {value!r}")
            element.set("type", value)
        elif key == "load":
            _car_load(ed, element, value)
        elif key in ("return_when_empty", "return_when_loaded"):
            _return_when(ed, element, "rwe" if key == "return_when_empty" else "rwl", value)
        else:
            raise Refused(f"Unknown car field {key!r}. Destinations, trains and schedule state go through JMRI.")


def _car_load(ed: Editor, element: ET.Element, load: str) -> None:
    kind = element.get("type")
    custom = [e.get("name") for h in ed.car_root.findall("./loads/load") if h.get("type") == kind
              for e in h.findall("carLoad")]
    if load not in custom and load not in ed.defaults():
        raise Refused(f"{kind} has no load {load!r}. Add it with add_load.")
    element.set("load", load)


def _return_when(ed: Editor, element: ET.Element, prefix: str, value: dict | None) -> None:
    for attr in ("DestId", "DestTrackId", "Load"):
        element.attrib.pop(prefix + attr, None)
    if not value:
        return
    place = ed.location(value["destination"])
    element.set(f"{prefix}DestId", place.get("id"))
    if value.get("track"):
        track = ed._one(place.findall("track"), value["track"], "track")
        element.set(f"{prefix}DestTrackId", track.get("id"))
    if value.get("load"):
        element.set(f"{prefix}Load", value["load"])


@action()
def add_car(ed: Editor, road: str, number: str, type: str, length: int, location: str | None = None,
            track: str | None = None, **fields) -> str:
    """Add a car. New roads, colours, owners and lengths are registered too."""
    identity = f"{road}{number}"
    if identity in [c.get("id") for c in ed.cars()]:
        raise Refused(f"Car {identity} already exists")
    if type not in ed.car_types():
        raise Refused(f"Unknown car type {type!r}")
    ed.register("roads", "road", road)
    empty = ed.defaults()[0]
    element = ET.Element("car", {"id": identity, "roadName": road, "roadNumber": str(number), "type": type,
                                 "length": str(length)})
    holder = ed.section(ed.car_root, "cars")
    holder.append(element)
    ed.register("lengths", "length", str(length), "value")
    element.set("load", empty)
    if location:
        _put(ed, element, location, track)
    _car_fields(ed, element, fields)
    _indent(holder, 1)
    return f"Added car {road} {number}."


@action(session=True)
def update_car(ed: Editor, car: str, **fields) -> str:
    """Change a car's plain fields: length, colour, owner, load, flags, out of service, return-when-empty or loaded. Refused while it is on a train."""
    element = ed.car(car)
    _free(element)
    _car_fields(ed, element, fields)
    return f"Updated car {element.get('id')}."


def _free(element: ET.Element) -> None:
    if element.get("trainId") or element.get("destinationId"):
        raise Refused(f"Car {element.get('id')} is assigned to a train. Reset or terminate that train first.")


def _put(ed: Editor, element: ET.Element, location: str, track: str | None) -> None:
    place = ed.location(location)
    element.set("locationId", place.get("id"))
    element.attrib.pop("secLocationId", None)
    if track:
        element.set("secLocationId", ed._one(place.findall("track"), track, "track").get("id"))


@action(session=True)
def place_car(ed: Editor, car: str, location: str, track: str, force: bool = False) -> str:
    """Set a car where it really is. No schedule runs and no move is counted. Use JMRI's Set Car to apply a schedule."""
    element = ed.car(car)
    _free(element)
    if element.get("kernel") and element.get("leadKernel") != "true":
        raise Refused(f"{element.get('id')} is in kernel {element.get('kernel')}. Place the lead.")
    place = ed.location(location)
    target = ed._one(place.findall("track"), track, "track")
    members = [element]
    if element.get("kernel"):
        members = [c for c in ed.cars() if c.get("kernel") == element.get("kernel")]
    if not force:
        kinds = ed.type_entries(target)
        for member in members:
            if member.get("type") not in kinds or member.get("type") not in ed.type_entries(place):
                raise Refused(f"{target.get('name')} does not take {member.get('type')}")
    for member in members:
        _free(member)
        _put(ed, member, location, track)
    return f"Placed {len(members)} car(s) on {target.get('name')}."


@action(session=True)
def clear_final_destination(ed: Editor, car: str) -> str:
    """Remove a car's final destination, the first step in freeing a stuck car."""
    element = ed.car(car)
    _free(element)
    for attr in ("nextDestId", "nextDestTrackId", "routePath"):
        element.attrib.pop(attr, None)
    return f"Cleared the final destination on {element.get('id')}."


@action()
def set_kernel(ed: Editor, name: str, cars: list[str], lead: str | None = None) -> str:
    """Make a kernel from cars. They must share a track, or the build fails. Replaces the kernel's members."""
    members = [ed.car(c) for c in cars]
    if len(members) < 2:
        raise Refused("A kernel needs at least two cars")
    tracks = {c.get("secLocationId") for c in members}
    if len(tracks) != 1:
        raise Refused("Kernel cars must be on the same track: a split kernel fails the whole build")
    for car in ed.cars():
        if car.get("kernel") == name:
            car.attrib.pop("kernel", None)
            car.attrib.pop("leadKernel", None)
    chosen = ed.car(lead) if lead else members[0]
    if chosen not in members:
        raise Refused("The lead must be one of the cars")
    for car in members:
        _free(car)
        car.set("kernel", name)
        car.attrib.pop("leadKernel", None)
    chosen.set("leadKernel", "true")
    holder = ed.section(ed.car_root, "newKernels", ("options", "loads"))
    if name not in [k.get("name") for k in holder.findall("kernel")]:
        ET.SubElement(holder, "kernel", {"name": name})
        _indent(holder, 1)
    return f"Kernel {name}: {len(members)} cars, lead {chosen.get('id')}."


@action()
def clear_kernel(ed: Editor, name: str) -> str:
    """Break up a kernel."""
    count = 0
    for car in ed.cars():
        if car.get("kernel") == name:
            _free(car)
            car.attrib.pop("kernel", None)
            car.attrib.pop("leadKernel", None)
            count += 1
    holder = ed.car_root.find("newKernels")
    if holder is not None:
        for kernel in list(holder.findall("kernel")):
            if kernel.get("name") == name:
                holder.remove(kernel)
        _indent(holder, 1)
    return f"Kernel {name} removed from {count} cars."


@action()
def delete_car(ed: Editor, car: str) -> str:
    """Delete a car not assigned to a train."""
    element = ed.car(car)
    _free(element)
    if element.get("kernel"):
        raise Refused(f"Remove it from kernel {element.get('kernel')} first")
    holder = ed.section(ed.car_root, "cars")
    holder.remove(element)
    _indent(holder, 1)
    return f"Deleted car {element.get('id')}."


# ---- Setup ----------------------------------------------------------------------------


@action()
def set_option(ed: Editor, group: str, name: str, value: str | bool | int) -> str:
    """Set an existing Operations.xml setting, such as group router, name carRoutingViaYards."""
    if SETUP_FILE not in ed.docs:
        raise Refused("No Operations.xml here. Start JMRI once to create it.")
    node = ed.docs[SETUP_FILE].root.find(f"./operations/{group}")
    if node is None or name not in node.attrib:
        raise Refused(f"No setting {group}.{name} in this file. JMRI writes every setting it knows, "
                      "so this name is wrong or from another version.")
    text = _bool(value) if isinstance(value, bool) else str(value)
    if node.get(name) in ("true", "false") and text not in ("true", "false"):
        raise Refused(f"{group}.{name} is true or false")
    node.set(name, text)
    return f"Set {group}.{name} to {text}."
