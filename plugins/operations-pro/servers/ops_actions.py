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
                      STAGING, TRAINS, TYPE_AND_LOAD, YARD, DIRECTIONS, split_name)
from ops_store import Doc, FILES, Refused
import ops_paperwork as paper

LOCATIONS, ROUTE_FILE, TRAIN_FILE, CAR_FILE = FILES[0], FILES[1], FILES[2], FILES[3]
SETUP_FILE, ENGINE_FILE = FILES[4], FILES[5]

TRACK_CHILDREN = ("types", "carRoads", "carLoads", "carShipLoads", "dropIds", "pickupIds", "destinations", "comments")
TRAIN_CHILDREN = ("rowColor", "route", "types", "carRoads", "cabooseRoads", "locoRoads", "carLoads", "carOwners",
                  "scripts", "railRoad", "manifestLogo")
LOAD_BITS = {"swap_default": 1, "empty_custom": 2, "generate": 4, "generate_any_spur": 8, "empty_default": 16,
             "generate_any_staging": 32, "disable_load_change": 64, "quick_service": 128}
STAGING_BITS = 1 | 2 | 4 | 8 | 16 | 32
SPUR_BITS = 64 | 128
# What JMRI's windows offer: ScheduleTableModel:412 and RouteEditTableModel:614-621.
SCHEDULE_RANDOM = ("", "50", "30", "25", "20", "15", "10", "5", "2", "1")
STOP_RANDOM = ("Off",) + tuple(str(n) for n in range(10, 101, 10))
# Train attributes that hold a road name: trains/Xml.java:63-72.
TRAIN_ROAD_ATTRS = ("engineRoad", "leg2Road", "leg3Road", "cabooseRoad", "leg2CabooseRoad", "leg3CabooseRoad")
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


def _int_field(name: str, value, minimum: int = 0) -> int:
    """A whole number for a field JMRI parses with Integer.parseInt."""
    if isinstance(value, bool) or not isinstance(value, int):
        text = str(value).strip() if isinstance(value, str) else None
        if text is None or not text.lstrip("-").isdigit():
            raise Refused(f"{name} must be a whole number, not {value!r}")
        value = int(text)
    if value < minimum:
        raise Refused(f"{name} cannot be less than {minimum}")
    return value


def _remove_types(holder: ET.Element, names) -> None:
    """Drop type entries; a holder with no <types> has nothing to drop."""
    types = holder.find("types")
    if types is None:
        return
    for entry in list(types):
        if entry.get("name") in names:
            types.remove(entry)


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
        self.moves_allowed: set[str] = set()  # Track ids whose moves an action was asked to change.

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

    def engines(self) -> list[ET.Element]:
        if ENGINE_FILE not in self.docs:
            return []
        return self.docs[ENGINE_FILE].root.findall("./engines/engine")

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
        if track.get("id") not in editor.moves_allowed and old.get("moves") != track.get("moves"):
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
def add_startup_script(ed: Editor, path: str) -> str:
    """Run a script when JMRI loads the trains, as Trains > Tools > Startup Scripts does."""
    options = ed.train_root.find("options")
    if options is None:
        raise Refused("The train file has no options section")
    scripts = options.find("scripts")
    if scripts is None:
        scripts = ET.SubElement(options, "scripts")
    if any(e.get("name") == path for e in scripts.findall("startUp")):
        return f"{path} is already a startup script."
    ET.SubElement(scripts, "startUp", {"name": path})
    _indent(options, 2)
    return f"JMRI will run {path} when it loads the trains."


@action()
def add_car_type(ed: Editor, name: str, like: str | None = None) -> str:
    """Add a car type. With like, every location, track and train that takes that type takes this too."""
    if name in ed.car_types():
        raise Refused(f"Type {name!r} already exists")
    if name in ed.loco_types():
        raise Refused(f"{name!r} is a locomotive type. Tracks and trains keep one list of type names, "
                      "so a car type and a loco type with one name could not be told apart")
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
    """Rename a road in the road list, track and train filters, train engine and caboose roads, and schedule lines. Refused while a car or engine carries it, since their ids hold the road."""
    if old not in [e.get("name") for e in ed.registered("roads", "road")]:
        raise Refused(f"Unknown road {old!r}")
    if any(c.get("roadName") == old for c in ed.cars()):
        raise Refused(f"Cars still carry road {old}. A car's id contains its road, so rename those in JMRI")
    engines = [e.get("id") for e in ed.engines() if e.get("roadName") == old]
    if engines:
        raise Refused(f"Engines still carry road {old}: {', '.join(engines[:8])}. Rename those in JMRI")
    count = _rename_values(ed.car_root, {"road": ("name",)}, old, new)
    count += _rename_values(ed.loc_root, {"carRoad": ("name",), "item": ("road",)}, old, new)
    count += _rename_values(ed.train_root, {"carRoad": ("name",), "locoRoad": ("name",),
                                            "train": TRAIN_ROAD_ATTRS}, old, new)
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
        if length < 0:
            raise Refused("length cannot be negative")
        element.set("length", str(length))
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


@action()
def set_track_moves(ed: Editor, moves: dict[str, int]) -> str:
    """Set the move counts that bias the builder, by track name or id. The only action that changes them."""
    for name, value in moves.items():
        track = ed.track(name)
        track.set("moves", str(_int_field("moves", value)))
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
    day = lambda text: _day_id(ed, text)  # noqa: E731  An unknown day is refused (train schedule days block).
    random = str(line.get("random", "") or "")
    if random not in SCHEDULE_RANDOM:
        raise Refused(f"random must be blank or one of {', '.join(SCHEDULE_RANDOM[1:])} (percent), not {random!r}")
    # ScheduleItem:347-351 parses count and wait with no catch: a bad value stops the load.
    count = _int_field("count", line.get("count", 1), 1)
    wait = _int_field("wait", line.get("wait", 0))
    element = ET.Element("item", {
        "id": f"{schedule_id}c{number}", "sequenceId": str(sequence), "random": random,
        "trainScheduleId": day(line.get("setout_day")), "pickupTrainScheduleId": day(line.get("pickup_day")),
        "count": str(count), "wait": str(wait), "type": kind,
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
    _no_holders(ed, element)
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


def _no_holders(ed: Editor, schedule: ET.Element) -> None:
    """Refuse while a car's scheduleId points at one of this schedule's lines (C:1202)."""
    ids = {i.get("id") for i in schedule.findall("item")}
    holders = [c.get("id") for c in ed.cars() if c.get("scheduleId") in ids]
    if holders:
        raise Refused(f"Cars are on their way under these lines: {', '.join(holders[:8])}")


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
    """Delete a schedule no track uses and no car is travelling under."""
    element = ed.schedule(schedule)
    users = [t.get("name") for t in ed.tracks() if t.get("scheduleId") == element.get("id")]
    if users:
        raise Refused(f"Still on: {', '.join(users)}")
    _no_holders(ed, element)
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
                         local_route_only: bool = False, any_staging: bool = True, ship_empties: bool = False) -> str:
    """Set a staging track for custom loads: arrivals become the default empty (custom and default loads alike),
    outbound loads are generated, and the ship list refuses the default empty and load. The price: an empty that
    finds no custom load fails the build. ship_empties keeps the default empty on the ship list, so such a car
    leaves as an empty instead."""
    element = ed.track(track, location)
    if element.get("trackType") != STAGING:
        raise Refused(f"{element.get('name')} is not staging")
    # Car.java:935-955: bit 2 strips custom loads only; only swap (1) or empty_default (16) turn a default
    # load into the empty the generators need (TBC:635). Without 16 a loaded arrival is refused by Ship.
    options = ["empty_custom", "empty_default", "generate" if local_route_only else "generate_any_spur"]
    if any_staging:
        options.append("generate_any_staging")
    empty, loaded = ed.defaults()
    if ship_loads:
        names = list(ship_loads) + ([empty] if ship_empties and empty not in ship_loads else [])
        ship = {"option": INCLUDE, "names": sorted(names)}  # JMRI's save sorts the list.
    else:
        ship = {"option": EXCLUDE, "names": [loaded] if ship_empties else sorted([empty, loaded])}
    settings: dict = {"load_options": options, "loads": {"option": ALL}, "ship_loads": ship}
    update_track(ed, element.get("id"), **settings)
    if ship_empties:
        return f"Set {element.get('name')} for custom loads; an empty that finds no load still leaves as {empty}."
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
    # RouteLocation:612-655 parses these with Integer.parseInt and logs an error on anything else.
    for key, attr in (("max_moves", "maxCarMoves"), ("max_length", "maxTrainLength"), ("wait", "wait")):
        if key in stop:
            element.set(attr, str(_int_field(key, stop[key])))
    if "comment" in stop:
        element.set("comment", str(stop["comment"]))
    if "random" in stop:
        random = str(stop["random"])
        if random not in STOP_RANDOM:
            raise Refused(f"random must be Off or 10 to 100 by tens, not {random!r}")
        element.set("randomControl", random)
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
               "loads": ("carLoadOption", "carLoads", "carLoad"), "owners": ("carOwnerOption", "carOwners", "carOwner"),
               # Train.isLocoRoadNameAccepted: filters locomotives as roads does cars (TrainBuilderEngines:45).
               "loco_roads": ("locoRoadOption", "locoRoads", "locoRoad")}


def _train_fields(ed: Editor, element: ET.Element, fields: dict) -> list[str]:
    """Set the fields, then check locomotive model and road on the result. Returns warnings."""
    for key in ("engine_model", "engine_road"):
        if key in fields:
            fields = {**fields, key: _no_choice(ed, key, fields[key])}
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
            _remove_types(element, value)
        else:
            raise Refused(f"Unknown train field {key!r}")
    if "engine_model" in fields or "engine_road" in fields:
        return _check_train_power(ed, element)
    return []


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
    notes = _train_fields(ed, element, fields)
    _indent(holder, 1)
    served = _serve_tracks(ed, element, source) if serve_tracks else 0
    return " ".join([f"Added train {name} (id {identity}); added to {served} track lists.", *notes])


@action()
def update_train(ed: Editor, train: str, **fields) -> str:
    """Change train settings: description, engines, requires, departure, flags, types and road, load and owner lists.
    engine_model and engine_road take what the Edit Train window offers: a roster model, a road of its engines, or blank."""
    element = ed.train(train)
    notes = _train_fields(ed, element, fields)
    _indent(element, 2)
    return " ".join([f"Updated train {element.get('name')}.", *notes])


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
    """Delete a train. It is taken off track lists and day schedules. Refused while a car is assigned to it or an automation names it."""
    element = ed.train(train)
    identity = element.get("id")
    cars = [c.get("id") for c in ed.cars() if c.get("trainId") == identity]
    if cars:
        raise Refused(f"Cars are on it: {', '.join(cars[:8])}")
    # AutomationItem:446 reads trainId; an item left pointing at nothing loses its action.
    automations = [a.get("name") for a in ed.train_root.findall("./automations/automation")
                   if any(i.get("trainId") == identity for i in a.findall("item"))]
    if automations:
        raise Refused(f"Automations still use it: {', '.join(automations[:8])}. Change those in JMRI first")
    # TrainSchedule:120 reads trainIds as a comma list.
    for day in ed.train_root.findall("./schedules/schedule"):
        ids = [i for i in day.get("trainIds", "").split(",") if i]
        if identity in ids:
            _set_day_trains(day, [i for i in ids if i != identity])
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
    """Set the active train schedule (day) by name or id, Any (cars may be picked up any day), or none."""
    # TrainScheduleManager.load reads the root element after TrainManager reads the old one under
    # options, so the root one is what JMRI uses; _set_active writes both where both exist.
    if name and str(name).lower() == "any":
        _set_active(ed, "ANY")
        return "Active day: Any."
    _set_active(ed, _day_id(ed, name))
    return f"Active day: {_day(ed, name).get('name') if name else 'none'}."


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
    # TBB:1213-1231: every car needs a track, one location, and the same split track name.
    homeless = [c.get("id") for c in members if not c.get("secLocationId")]
    if homeless:
        raise Refused(f"Kernel cars need a track; none on: {', '.join(homeless)}")
    names = {t.get("id"): split_name(t.get("name", "")) for t in ed.tracks()}
    places = {(c.get("locationId"), names.get(c.get("secLocationId"))) for c in members}
    if len(places) != 1:
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


# ---- Train schedule days and manifest formats -------------------------------------------
# Checked against JMRI 5.16, trains/schedules and setup. A train schedule ("day") is an id,
# a name, a comment and a list of train ids (TrainSchedule:107-153). The builder reads only
# the active id: a car's pick up day (TrainBuilderBase:960-973) and a schedule line's set out
# day (Schedule.checkScheduleItem, TrainBuilderBase:2286). The train list matters only when
# Apply sets each train's Build box from it (TrainsScheduleTableFrame:370-378,
# ApplyTrainScheduleAction). TrainManagerXml:70-73 writes <trainScheduleOptions activeId> and
# <schedules> at the root of the train file, after trains and manual builds.

TRAIN_ROOT_ORDER = ("options", "trains", "manualBuilds", "trainScheduleOptions", "schedules", "automationOptions",
                    "automations")
# TrainScheduleManager.getDaysOfWeek, English bundle: what the Restore button and a save with no days create.
WEEK_DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
ANY_WORDS = ("any", "ANY")
_KEEP = object()  # A field not given, as opposed to one cleared.


def _insert_ordered(parent: ET.Element, child: ET.Element, order: tuple[str, ...], level: int) -> None:
    """Insert where JMRI writes it, with the indentation of its neighbours."""
    rank = order.index(child.tag)
    position = 0
    for index, sibling in enumerate(parent):
        if sibling.tag in order and order.index(sibling.tag) <= rank:
            position = index + 1
    indent = "\n" + "  " * level
    if position:
        before = parent[position - 1]
        child.tail, before.tail = before.tail, indent
    elif len(parent):
        child.tail = indent
    else:
        parent.text = indent
        child.tail = "\n" + "  " * (level - 1)
    parent.insert(position, child)
    _indent(child, level)


def _days(ed: Editor) -> list[ET.Element]:
    return ed.train_root.findall("./schedules/schedule")


def _day(ed: Editor, text: str) -> ET.Element:
    return ed._one(_days(ed), text, "train schedule")


def _day_id(ed: Editor, text: str | None) -> str:
    """A day named by name or id, as an id; blank for any day. An unknown day is refused, since an id
    no schedule holds never matches the active day at TrainBuilderBase:2286."""
    if not text:
        return ""
    return _day(ed, text).get("id")


def _day_trains(day: ET.Element) -> list[str]:
    return [i for i in day.get("trainIds", "").split(",") if i]


def _set_day_trains(day: ET.Element, ids: list[str]) -> None:
    day.set("trainIds", "".join(f"{i}," for i in ids))  # TrainSchedule.store writes "id," for each.


def _day_name(ed: Editor, name: str, current: ET.Element | None = None) -> str:
    text = name.strip()  # TrainsScheduleEditFrame trims and ignores a blank name.
    if not text:
        raise Refused("A train schedule needs a name")
    if text in ANY_WORDS or text.lower() == "any":
        raise Refused("Any is the active setting that lets cars go every day; name the schedule something else")
    if any(d.get("name") == text and d is not current for d in _days(ed)):
        raise Refused(f"Train schedule {text!r} already exists; JMRI finds schedules by name")
    return text


def _schedules_holder(ed: Editor) -> ET.Element:
    holder = ed.train_root.find("schedules")
    if holder is None:
        holder = ET.Element("schedules")
        _insert_ordered(ed.train_root, holder, TRAIN_ROOT_ORDER, 1)
    return holder


def _new_day(ed: Editor, name: str, comment: str = "") -> ET.Element:
    holder = _schedules_holder(ed)
    identity = str(_next(d.get("id") for d in _days(ed)))  # TrainScheduleManager.register: highest id + 1.
    element = ET.SubElement(holder, "schedule", {"id": identity, "name": name})
    if comment:
        element.set("comment", comment)
    _set_day_trains(element, [])
    _indent(holder, 1)
    return element


def _train_ids(ed: Editor, names: list[str]) -> list[str]:
    ids = []
    for name in names:
        identity = ed.train(name).get("id")
        if identity not in ids:
            ids.append(identity)
    return ids


def _active_nodes(ed: Editor) -> list[ET.Element]:
    nodes = [n for n in (ed.train_root.find("./options/trainScheduleOptions"), ed.train_root.find("trainScheduleOptions"))
             if n is not None]
    return nodes


def _set_active(ed: Editor, identity: str) -> None:
    """Write the root element JMRI reads last, and the old one under options too if the file has it."""
    root = ed.train_root.find("trainScheduleOptions")
    if root is None:
        root = ET.Element("trainScheduleOptions")
        _insert_ordered(ed.train_root, root, TRAIN_ROOT_ORDER, 1)
    for node in _active_nodes(ed):
        node.set("activeId", identity)


def _active(ed: Editor) -> str:
    value = ""
    for node in _active_nodes(ed):
        if node.get("activeId") is not None:
            value = node.get("activeId")
    return value


@action()
def add_day(ed: Editor, name: str, comment: str = "", trains: list[str] | None = None) -> str:
    """Add a train schedule (a day), optionally with the trains that run on it. The list matters when apply_day
    or an Apply step sets each train's Build box; the builder itself reads only the active day."""
    text = _day_name(ed, name)
    empty = not _days(ed)
    element = _new_day(ed, text, comment)
    if trains:
        _set_day_trains(element, _train_ids(ed, trains))
    note = (" The file had no train schedules, so JMRI would have made Sunday to Saturday on its next save; "
            "now it will not.") if empty else ""
    return f"Added train schedule {text} (id {element.get('id')}) with {len(trains or [])} trains.{note}"


@action()
def add_default_days(ed: Editor) -> str:
    """Add Sunday to Saturday where no schedule has that name, as the Restore button does."""
    added = [name for name in WEEK_DAYS if name not in [d.get("name") for d in _days(ed)]]
    for name in added:
        _new_day(ed, name)
    return f"Added {len(added)} train schedules: {', '.join(added) or 'none needed'}."


@action()
def update_day(ed: Editor, day: str, name: str | None = None, comment: str | None = None) -> str:
    """Rename a train schedule or change its comment. Everything else holds its id, so nothing else changes."""
    element = _day(ed, day)
    if name is not None:
        element.set("name", _day_name(ed, name, element))
    if comment is not None:
        element.attrib.pop("comment", None)
        if comment:  # TrainSchedule.store writes the comment only when it is not blank.
            items = list(element.attrib.items())
            element.attrib.clear()
            element.attrib.update(items[:2] + [("comment", comment)] + items[2:])
    return f"Updated train schedule {element.get('name')}."


def _day_users(ed: Editor, identity: str) -> tuple[list[str], list[ET.Element]]:
    """Automation steps and manual build lines that name the day, and schedule lines that do."""
    users = [f"automation {a.get('name')}" for a in ed.train_root.findall("./automations/automation")
             if any(i.get("trainScheduleId") == identity for i in a.findall("item"))]
    for build in ed.train_root.findall("./manualBuilds/manualBuild"):
        if any(i.get("trainScheduleId") == identity for i in build.iter("mbItem")):
            users.append(f"manual build for train {build.get('trainId')}")
    lines = [i for i in ed.loc_root.iter("item")
             if identity in (i.get("trainScheduleId"), i.get("pickupTrainScheduleId"))]
    return users, lines


@action()
def delete_day(ed: Editor, day: str, clear_lines: bool = False) -> str:
    """Delete a train schedule. Refused while an automation or manual build names it, or for the last one (a save
    with none makes Sunday to Saturday). Schedule lines that name it are refused unless clear_lines, which sets
    them to any day; cars waiting for it as their pick up day are freed; if it was active, none is active."""
    element = _day(ed, day)
    identity = element.get("id")
    if len(_days(ed)) == 1:
        raise Refused("This is the last train schedule. With none left, JMRI makes Sunday to Saturday on its next "
                      "save (TrainScheduleManager.getList), so add another first")
    users, lines = _day_users(ed, identity)
    if users:
        raise Refused(f"Still named by: {', '.join(users[:8])}. Change those in JMRI first")
    if lines and not clear_lines:
        names = sorted({next(s.get("name") for s in ed.schedules() if i in s.findall("item")) for i in lines})
        raise Refused(f"Schedule lines use it in: {', '.join(names)}. A line left with a deleted day is never "
                      "used to pick a custom load (TrainBuilderBase:2286), yet still accepts cars on any day "
                      "(Schedule.checkScheduleItem). Pass clear_lines to set them to any day, or change them first")
    for item in lines:
        for attr in ("trainScheduleId", "pickupTrainScheduleId"):
            if item.get(attr) == identity:
                item.set(attr, "")
    # A pick up day no schedule holds lets the car go any day (TrainBuilderBase:965), and a later new day
    # could take the same id, so the car's id is cleared rather than left to point at it.
    freed = [c for c in ed.cars() if c.get("pickupId") == identity]
    for car in freed:
        car.attrib.pop("pickupId")
    was_active = _active(ed) == identity
    if was_active:
        _set_active(ed, "")
    holder = _schedules_holder(ed)
    holder.remove(element)
    _indent(holder, 1)
    return (f"Deleted train schedule {element.get('name')}: {len(lines)} schedule lines set to any day, "
            f"{len(freed)} cars freed of it" + ("; no day is active now." if was_active else "."))


@action()
def set_day_trains(ed: Editor, day: str, trains: list[str] | None = None, add: list[str] | None = None,
                   remove: list[str] | None = None, from_build: bool = False) -> str:
    """Choose the trains that run on a day: trains replaces the list, add and remove change it, from_build
    copies each train's Build box as the Copy button does. Apply them with apply_day."""
    element = _day(ed, day)
    if trains is not None and from_build:
        raise Refused("Give trains or from_build, not both")
    ids = _day_trains(element)
    if from_build:
        ids = [t.get("id") for t in ed.trains() if t.get("build", "true") == "true"]
    if trains is not None:
        ids = _train_ids(ed, trains)
    for identity in _train_ids(ed, add or []):
        if identity not in ids:
            ids.append(identity)
    gone = set(_train_ids(ed, remove or []))
    ids = [i for i in ids if i not in gone]
    _set_day_trains(element, ids)
    return f"{element.get('name')} runs {len(ids)} trains."


@action()
def apply_day(ed: Editor, day: str | None = None) -> str:
    """Set every train's Build box from a day's train list, as Apply does. Defaults to the active day."""
    if day is None:
        identity = _active(ed)
        if identity in ("",) + ANY_WORDS:
            raise Refused("No single day is active; name the day to apply")
        element = next((d for d in _days(ed) if d.get("id") == identity), None)
        if element is None:
            raise Refused(f"The active day id {identity} has no train schedule; name the day to apply")
    else:
        element = _day(ed, day)
    ids = set(_day_trains(element))
    on = 0
    for train in ed.trains():
        train.set("build", _bool(train.get("id") in ids))
        on += train.get("id") in ids
    return f"Applied {element.get('name')}: {on} trains to build, {len(ed.trains()) - on} not."


@action()
def set_line_days(ed: Editor, schedule: str, line: str | int, setout_day=_KEEP, pickup_day=_KEEP) -> str:
    """Change a schedule line's set out day or pick up day by day name, or blank for any day. The line is named by
    id or by position from 1. A car already travelling under the line is still accepted on another day."""
    element = ed.schedule(schedule)
    items = sorted(element.findall("item"), key=lambda i: int(i.get("sequenceId", "0") or 0))
    if isinstance(line, int):
        if not 1 <= line <= len(items):
            raise Refused(f"Schedule has {len(items)} lines")
        item = items[line - 1]
    else:
        item = ed._one(items, line, "schedule line")
    if setout_day is _KEEP and pickup_day is _KEEP:
        raise Refused("Give setout_day or pickup_day")
    if setout_day is not _KEEP:
        item.set("trainScheduleId", _day_id(ed, setout_day))
    if pickup_day is not _KEEP:
        item.set("pickupTrainScheduleId", _day_id(ed, pickup_day))
    return f"Line {item.get('id')} of {element.get('name')}: set out day {item.get('trainScheduleId') or 'any'}, " \
           f"pick up day {item.get('pickupTrainScheduleId') or 'any'}."


# Manifest and switch list formats: fields and checks are in ops_paperwork.

def _setup_root(ed: Editor) -> ET.Element:
    if SETUP_FILE not in ed.docs:
        raise Refused("No Operations.xml here. Start JMRI once to create it.")
    root = ed.docs[SETUP_FILE].root
    operations = root.find("operations")
    if operations is None:
        raise Refused("Operations.xml has no operations section")
    return root


def _setup_node(ed: Editor, tag: str, create: bool = True) -> ET.Element | None:
    operations = _setup_root(ed).find("operations")
    node = operations.find(tag)
    if node is None and create:
        # A new element gets JMRI's default for each setting it holds, as a JMRI save writes it, so no
        # setting falls back on another (Setup.load copies a missing engine colour from the car one).
        node = ET.Element(tag, {attr: default for where, element, attr, kind, default in paper.FIELDS.values()
                                if where == paper.SETUP and element == tag and kind != "path"})
        _insert_ordered(operations, node, paper.SETUP_ORDER, 2)
    return node


def _train_option_node(ed: Editor, tag: str) -> ET.Element:
    options = ed.train_root.find("options")
    if options is None:
        options = ET.Element("options")
        _insert_ordered(ed.train_root, options, TRAIN_ROOT_ORDER, 1)
    node = options.find(tag)
    if node is None:
        node = ET.Element(tag)
        _insert_ordered(options, node, paper.TRAIN_OPTIONS_ORDER, 2)
    return node


def _field_value(ed: Editor, name: str) -> str:
    where, tag, attr, _, default = paper.FIELDS[name]
    if where == paper.SETUP:
        node = _setup_node(ed, tag, create=False)
    else:
        options = ed.train_root.find("options")
        node = options.find(tag) if options is not None else None
    value = node.get(attr) if node is not None else None
    return default if value is None else value


def _checked(name: str, value) -> str:
    kind = paper.FIELDS[name][3]
    if kind == "bool":
        if isinstance(value, str) and value in ("true", "false"):
            return value
        if not isinstance(value, bool):
            raise Refused(f"{name} is true or false")
        return _bool(value)
    if kind == "font_size":
        size = _int_field(name, value)
        if size not in paper.FONT_SIZES:
            raise Refused("font_size must be 5 to 18, the sizes JMRI's print options offer")
        return str(size)
    if kind == "tab":
        return str(_int_field(name, value, 1))
    if kind == "color":
        try:
            return paper.color_name(value)
        except ValueError as exc:
            raise Refused(f"{name}: {exc}") from exc
    if kind == "font":
        if not str(value).strip():
            raise Refused("font needs a font name")
        return str(value)
    if kind in ("text", "path"):
        return str(value)
    if isinstance(kind, dict):
        if value in kind:
            return kind[value]
        if value in kind.values():
            return value
        raise Refused(f"{name} must be one of {', '.join(kind)}, not {value!r}")
    if value not in kind:
        raise Refused(f"{name} must be one of {', '.join(kind)}, not {value!r}")
    return value


def _set_field(ed: Editor, name: str, text: str) -> None:
    where, tag, attr, kind, _ = paper.FIELDS[name]
    if kind == "path" and not text:  # Setup.store writes manifestLogo only when it is set.
        node = _setup_node(ed, tag, create=False)
        if node is not None:
            operations = _setup_root(ed).find("operations")
            operations.remove(node)
            _indent(operations, 1)
        return
    node = _setup_node(ed, tag) if where == paper.SETUP else _train_option_node(ed, tag)
    node.set(attr, text)
    if name == "switch_list_page":  # Setup.store adds pageMode for page per train, for pre 3.11 readers.
        node.attrib.pop("pageMode", None)
        if text == paper.PAGE_FORMATS["per_train"]:
            node.set("pageMode", "true")
    if name == "format":  # Setup.load reads the old columnFormat only when manifestFormat is missing.
        operations = _setup_root(ed).find("operations")
        for old in operations.findall("columnFormat"):
            operations.remove(old)


def _same_as_manifest(ed: Editor) -> bool:
    return _field_value(ed, "switch_list_same_as_manifest") == "true"


def _format_node_values(ed: Editor, line: str) -> tuple[str, str]:
    node = _setup_node(ed, paper.FORMAT_LINES[line][0], create=False)
    prefix, setting = paper.DEFAULT_FORMATS[line]
    if node is not None:
        prefix, setting = node.get("prefix", prefix), node.get("setting", setting)
    return prefix, setting


def _write_format(ed: Editor, line: str, prefix: str, setting: str) -> None:
    node = _setup_node(ed, paper.FORMAT_LINES[line][0])
    node.attrib.clear()
    node.attrib.update({"prefix": prefix, "setting": setting})


def _sync_switch_lists(ed: Editor) -> list[str]:
    """With Same as Manifest on, a JMRI save writes the switch list formats and orientation from the
    manifest ones (Setup.getSwitchList...); write them the same way so nothing changes on that save."""
    if not _same_as_manifest(ed):
        return []
    done = []
    for switch, manifest in paper.SWITCH_LIST_COPIES.items():
        if any(_setup_node(ed, paper.FORMAT_LINES[n][0], create=False) is not None for n in (switch, manifest)):
            wanted = _format_node_values(ed, manifest)
            if _format_node_values(ed, switch) != wanted or \
                    _setup_node(ed, paper.FORMAT_LINES[switch][0], create=False) is None:
                _write_format(ed, switch, *wanted)
                done.append(switch)
    page = _setup_node(ed, "pageOrientation", create=False)
    if page is not None and page.get("switchList") != _field_value(ed, "orientation"):
        page.set("switchList", _field_value(ed, "orientation"))
        done.append("switch_list_orientation")
    return done


@action()
def set_manifest_options(ed: Editor, **fields) -> str:
    """Set manifest, switch list and print options: page (font, font_size, orientation, switch_list_orientation,
    duplex, format standard/two_column/two_column_track, logo, header_line_1-3, save_manifests), colours
    (pickup_color, drop_color, local_color, pickup_engine_color, drop_engine_color), tabs and tab lengths, what
    prints (print_location_comments, print_route_comments, print_loads_and_empties, print_train_schedule,
    use_12hr_format, print_valid, sort_by_track, print_page_header, print_headers, no_page_breaks, truncate,
    use_departure_time, use_editor, print_caboose_load, print_passenger_load, group_car_moves, print_loco_last,
    hazardous_message, missing_car_comment), switch lists (switch_list_same_as_manifest, _real_time, _all_trains,
    _page normal/per_train/per_visit, _route_comments, _track_summary, _departure_time), CSV files (csv_manifest,
    csv_switch_list) and the Trains window's print_preview, print_build_report, open_csv_file, run_csv_file."""
    if not fields:
        raise Refused("Give at least one option")
    unknown = sorted(set(fields) - set(paper.FIELDS))
    if unknown:
        raise Refused(f"Unknown manifest options: {', '.join(unknown)}. Known: {', '.join(paper.FIELDS)}")
    values = {name: _checked(name, value) for name, value in fields.items()}
    same = values.get("switch_list_same_as_manifest", _field_value(ed, "switch_list_same_as_manifest")) == "true"
    if same and "switch_list_orientation" in values:
        raise Refused("With switch lists the same as the manifest, JMRI prints and saves the manifest orientation "
                      "for switch lists. Set switch_list_same_as_manifest false in the same step to give them their "
                      "own")
    for name, text in values.items():
        _set_field(ed, name, text)
    synced = _sync_switch_lists(ed) if {"switch_list_same_as_manifest", "orientation"} & set(values) else []
    note = f" Switch list copies follow the manifest: {', '.join(synced)}." if synced else ""
    return f"Set {len(values)} manifest options: {', '.join(f'{k}={v}' for k, v in values.items())}.{note}"


@action()
def set_manifest_format(ed: Editor, line: str, prefix: str | None = None, fields: list[str] | None = None) -> str:
    """Set the prefix and the fields printed on one manifest or switch list line: pickup_engine, drop_engine,
    pickup_car, drop_car, local, missing_car (no prefix), switch_list_pickup_car, switch_list_drop_car,
    switch_list_local. Fields are JMRI's attribute names, " " for a blank column, Tab, Tab2, Tab3 with tabs on."""
    if line not in paper.FORMAT_LINES:
        raise Refused(f"line must be one of {', '.join(paper.FORMAT_LINES)}")
    if prefix is None and fields is None:
        raise Refused("Give prefix or fields")
    if line == "missing_car" and prefix:
        raise Refused("The missing car line has no prefix: JMRI stores it blank and never reads one")
    if line in paper.SWITCH_LIST_COPIES and _same_as_manifest(ed):
        raise Refused("Switch lists are set to the same format as the manifest, so JMRI prints and saves the "
                      f"manifest's {paper.SWITCH_LIST_COPIES[line]} line here. Set switch_list_same_as_manifest "
                      "false first")
    old_prefix, old_setting = _format_node_values(ed, line)
    setting = old_setting
    if fields is not None:
        known = paper.ENGINE_TOKENS if paper.FORMAT_LINES[line][1] == "engine" else paper.CAR_TOKENS
        if _field_value(ed, "tabs") == "true":
            known = known + paper.TAB_TOKENS
        chosen = []
        for value in fields:
            text = paper.BLANK if str(value).strip() == "" else str(value).strip()
            match = next((k for k in known if k.lower() == text.lower()), None) if text != paper.BLANK else text
            if match is None:
                extra = " Tab fields need tabs on (set_manifest_options tabs)." if text in paper.TAB_TOKENS else ""
                raise Refused(f"{text!r} is not a field JMRI prints on this line; it would print an error "
                              f"instead.{extra} Fields: {', '.join(known)}")
            chosen.append(match)
        if not [c for c in chosen if c != paper.BLANK]:
            raise Refused("A line needs at least one field that prints")
        setting = "".join(f"{c}," for c in chosen)  # Setup.storeXmlMessageFormat.
    new_prefix = old_prefix if prefix is None else prefix
    if line == "missing_car":
        new_prefix = ""
    _write_format(ed, line, new_prefix, setting)
    synced = _sync_switch_lists(ed) if line in paper.SWITCH_LIST_COPIES.values() else []
    note = f" The switch list copy follows: {', '.join(synced)}." if synced else ""
    return f"{line}: prefix {new_prefix!r}, fields {setting.rstrip(',')}.{note}"


@action()
def set_manifest_text(ed: Editor, group: str, key: str, text: str | None = None) -> str:
    """Change one printed phrase: group manifest, switch_list or header, key the phrase's XML name (ops_list
    manifest shows them all with their text). Keep JMRI's {0} arguments you need; write '' for an apostrophe in a
    phrase with arguments. text null or JMRI's own wording puts the default back."""
    if group not in paper.TEXTS:
        raise Refused(f"group must be one of {', '.join(paper.TEXTS)}")
    holder_tag, defaults = paper.TEXTS[group]
    if key not in defaults:
        raise Refused(f"No {group} text {key!r}. Keys: {', '.join(defaults)}")
    root = _setup_root(ed)
    holder = root.find(holder_tag)
    if text is None or text == defaults[key]:  # store() writes only texts that differ from the default.
        if holder is not None:
            for node in holder.findall(key):
                holder.remove(node)
            _indent(holder, 1)
        return f"{group} text {key} is JMRI's default: {defaults[key]!r}."
    if paper.is_pattern(group, key):
        problem = paper.pattern_problem(text, defaults[key])
        if problem:
            raise Refused(f"{group} text {key}: {problem}. JMRI's text is {defaults[key]!r}")
    if holder is None:
        holder = ET.Element(holder_tag)
        _insert_ordered(root, holder, paper.ROOT_ORDER, 1)
    node = holder.find(key)
    if node is None:
        order = tuple(defaults)
        node = ET.Element(key)
        position = sum(1 for n in holder if n.tag in order and order.index(n.tag) < order.index(key))
        holder.insert(position, node)
    node.set("text", text)
    _indent(holder, 1)
    return f"{group} text {key}: {text!r}."


@action()
def set_train_manifest(ed: Editor, train: str, railroad_name: str | None = None, logo: str | None = None,
                       show_times: bool | None = None) -> str:
    """A train's own manifest options, as the train's Manifest Options window sets them: a railroad name and a
    logo printed instead of the railroad's (blank for the railroad's), and whether times print."""
    element = ed.train(train)
    for value, tag in ((railroad_name, "railRoad"), (logo, "manifestLogo")):
        if value is None:
            continue
        for old in element.findall(tag):
            element.remove(old)
        if value:  # Train.store writes each only when it is set.
            _place(element, ET.Element(tag, {"name": value}), TRAIN_CHILDREN)
    if show_times is not None:
        if not isinstance(show_times, bool):
            raise Refused("show_times is true or false")
        element.set("showTimes", _bool(show_times))
    _indent(element, 2)
    return f"Manifest options for train {element.get('name')} set."


# ---- End of train schedule days and manifest formats ------------------------------------


# ---- Engines --------------------------------------------------------------------------
# Checked against JMRI 5.16, rollingstock/engines. JMRI keeps an engine's type, length,
# horsepower, weight and B unit on its model, not on the engine (Engine.java setTypeName,
# setHp, setLength, setWeightTons, setBunit go to EngineModels). The file stores only the
# model names; on load each engine's attributes set its model's, so the last engine read
# wins and the next save writes that value onto every engine of the model. These actions
# keep every engine of a model the same, so nothing changes on a save.

# JmritOperationsEnginesBundle.properties and JmritOperationsBundle.properties: the lists
# JMRI writes into a new engine file, and the values it gives a default model.
DEFAULT_MODELS = dict(zip(
    "E8,FT,F3,F7,F9,GG1,GP20,GP30,GP35,GP38,GP40,GTEL,RS1,RS2,RS3,RS11,RS18,RS27,RSD4,Shay,SD26,SD45,SW1200,"
    "SW1500,SW8,TRAINMASTER,U28B".split(","),
    zip("2250,1350,1500,1500,1750,4620,2000,2250,2500,2000,3000,4500,1000,1500,1600,1800,1800,2400,1600,70,2650,"
        "3600,1200,1500,800,2400,2800".split(","),
        "70,50,50,50,50,80,56,56,56,59,59,80,51,52,51,53,52,57,52,50,61,66,45,45,44,66,60".split(","),
        ("Diesel,Diesel,Diesel,Diesel,Diesel,Electric,Diesel,Diesel,Diesel,Diesel,Diesel,Gas Turbine,Diesel,Diesel,"
         "Diesel,Diesel,Diesel,Diesel,Diesel,Steam,Diesel,Diesel,Diesel,Diesel,Diesel,Diesel,Diesel").split(","),
        "158,115,115,115,115,238,120,130,130,125,122,204,124,115,114,125,118,132,179,50,164,195,124,124,115,188,"
        "126".split(","))))
DEFAULT_ENGINE_TYPES = ("Electric", "Engine", "Diesel", "Gas Turbine", "Steam", "Steam-light", "Steam-heavy",
                        "Steam-pass", "Steam-mixed", "Switcher")
DEFAULT_ENGINE_LENGTHS = tuple("32,34,36,38,40,42,44,45,46,48,50,51,52,53,54,55,56,57,58,59,60,61,65,66,70,75,80,"
                               "85,90".split(","))
ENGINE_SECTIONS = ("models", "types", "lengths", "newConsists", "engines")
MODEL_FIELDS = {"type": "type", "length": "length", "hp": "hp", "weight_tons": "weightTons", "b_unit": "bUnit"}
# RollingStock.store then Engine.store: the order JMRI writes engine attributes in.
ENGINE_ORDER = ("id", "roadName", "roadNumber", "type", "length", "color", "weight", "weightTons", "built",
                "locationId", "routeLocationId", "secLocationId", "destinationId", "routeDestinationId",
                "secDestinationId", "divisionId", "lastRouteId", "clone", "moves", "date", "selected",
                "lastLocationId", "lastTrackId", "train", "trainId", "lastTrain", "lastTrainId", "owner", "value",
                "rfid", "locUnknown", "outOfService", "pickupTime", "setoutTime", "blocking", "comment", "model",
                "hp", "bUnit", "consist", "leadConsist", "consistNum")
ENGINE_FIELDS = {"built": "built", "owner": "owner", "comment": "comment", "value": "value", "rfid": "rfid"}
ENGINE_FLAGS = {"out_of_service": "outOfService", "location_unknown": "locUnknown"}
# Control.java:46 and OperationsXml.checkFileName: what JMRI's edit window accepts as a road number.
ROAD_NUMBER_MAX = 10
RESERVED = '.<>:"\\/|?*'
NEW_ENGINE_FILE = """<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet href="/xml/XSLT/operations-engines.xsl" type="text/xsl"?>
<!DOCTYPE operations-config SYSTEM "/xml/DTD/operations-engines.dtd">
<operations-config>
  <models>
{models}
  </models>
  <types>
{types}
  </types>
  <lengths>
{lengths}
  </lengths>
  <newConsists />
  <engines />
</operations-config>
"""


def _engine_root(ed: Editor) -> ET.Element:
    """The engine file, created the way JMRI 5.16 writes it when it has none: its default lists."""
    if ENGINE_FILE not in ed.docs:
        text = NEW_ENGINE_FILE.format(
            models="\n".join(f'    <model name="{m}" />' for m in DEFAULT_MODELS),
            types="\n".join(f'    <type name="{t}" />' for t in DEFAULT_ENGINE_TYPES),
            lengths="\n".join(f'    <length value="{n}" />' for n in DEFAULT_ENGINE_LENGTHS))
        ed.docs[ENGINE_FILE] = Doc(ed.base / ENGINE_FILE, text.encode("utf-8"))
    return ed.docs[ENGINE_FILE].root


def _engine_section(ed: Editor, tag: str) -> ET.Element:
    root = _engine_root(ed)
    found = root.find(tag)
    if found is None:
        found = ET.Element(tag)
        _place(root, found, ENGINE_SECTIONS)
    return found


def _engine_names(ed: Editor, group: str, tag: str, attr: str = "name") -> list[str]:
    root = _engine_root(ed)
    return [e.get(attr) for e in root.findall(f"./{group}/{tag}")]


def _engine_register(ed: Editor, group: str, tag: str, value: str, attr: str = "name") -> None:
    holder = _engine_section(ed, group)
    if value in [e.get(attr) for e in holder.findall(tag)]:
        return
    entry = ET.Element(tag, {attr: value})
    numbers = [e.get(attr, "") for e in holder.findall(tag)]
    if group == "lengths" and all(n.isdigit() for n in numbers):  # EngineLengths.sort is numeric.
        holder.insert(sum(1 for n in numbers if int(n) < int(value)), entry)
    else:
        holder.append(entry)
    _indent(holder, 1)


def _keep_one(ed: Editor, group: str, tag: str) -> None:
    """RollingStockAttribute.getNames refills an empty list with JMRI's defaults."""
    if len(_engine_names(ed, group, tag)) <= 1:
        raise Refused(f"That would leave no {group}, and JMRI refills an empty list with its own defaults")


def _engine(ed: Editor, text: str) -> ET.Element:
    key = text.replace(" ", "").upper()
    for engine in ed.engines():
        if engine.get("id", "").replace(" ", "").upper() == key:
            return engine
    raise Refused(f"No engine {text!r}")


def _set_ordered(element: ET.Element, values: dict, order: tuple[str, ...]) -> None:
    """Set or remove (value None) attributes, keeping JMRI's store order for a small diff."""
    items = dict(element.attrib)
    for attr, value in values.items():
        items.pop(attr, None)
        if value is not None:
            items[attr] = value
    known = sorted((k for k in items if k in order), key=order.index)
    element.attrib.clear()
    element.attrib.update({k: items[k] for k in known + [k for k in items if k not in order]})


def _whole(name: str, value, minimum: int = 0) -> str:
    if value in (None, ""):
        return ""
    return str(_int_field(name, value, minimum))


def _model_values(ed: Editor, model: str) -> tuple[dict, str]:
    """What JMRI would hold for a model now, and where it comes from."""
    engines = [e for e in ed.engines() if e.get("model") == model]
    if engines:
        last = engines[-1]  # The last engine loaded sets the model.
        return ({key: last.get(attr, "false" if key == "b_unit" else "") for key, attr in MODEL_FIELDS.items()},
                "engines")
    if model in DEFAULT_MODELS:
        hp, length, kind, weight = DEFAULT_MODELS[model]
        return {"type": kind, "length": length, "hp": hp, "weight_tons": weight, "b_unit": "false"}, "default"
    return {}, ""


def _model_fields(ed: Editor, given: dict) -> dict:
    """Check model values and return them as the strings JMRI stores."""
    out = {}
    for key, value in given.items():
        if key == "type":
            if value not in _engine_names(ed, "types", "type"):
                raise Refused(f"Unknown locomotive type {value!r}. Add it first with add_engine_type.")
            out[key] = value
        elif key == "length":
            # EngineLengths.sort parses every length as an integer.
            out[key] = str(_int_field("length", value, 1))
        elif key in ("hp", "weight_tons"):
            # EngineEditFrame:205-211 and RollingStockEditFrame:493-500 parse these as integers.
            out[key] = _whole(key, value)
        elif key == "b_unit":
            if value not in (True, False, "true", "false"):
                raise Refused("b_unit is true or false")
            out[key] = _bool(value in (True, "true"))
    return out


def _apply_model(ed: Editor, element: ET.Element, values: dict) -> None:
    _set_ordered(element, {MODEL_FIELDS[k]: v for k, v in values.items()}, ENGINE_ORDER)
    if values.get("weight_tons") == "":
        element.attrib.pop("weightTons", None)  # RollingStock.store leaves a blank weight out.
    if "length" in values:
        _engine_register(ed, "lengths", "length", values["length"], "value")


def _engine_fields(ed: Editor, element: ET.Element, fields: dict) -> None:
    for key, value in fields.items():
        if key in ENGINE_FIELDS:
            text = str(value)
            _set_ordered(element, {ENGINE_FIELDS[key]: text or None}, ENGINE_ORDER)
            if key == "owner" and text:
                ed.register("owners", "owner", text)
        elif key in ENGINE_FLAGS:
            _set_ordered(element, {ENGINE_FLAGS[key]: "true" if value else None}, ENGINE_ORDER)
        elif key in MODEL_FIELDS:
            raise Refused(f"JMRI keeps {key} on the engine's model, so it is the same for every engine of that "
                          "model. Change it with update_engine_model.")
        else:
            raise Refused(f"Unknown engine field {key!r}. Destinations, trains and build state go through JMRI.")


def _engine_types_at(ed: Editor, element: ET.Element, location: ET.Element, track: ET.Element) -> None:
    kind = element.get("type")
    if kind not in ed.type_entries(location) or kind not in ed.type_entries(track):
        raise Refused(f"{track.get('name')} at {location.get('name')} does not take {kind}. "
                      "Add the type there, or pass force.")


def _engine_free(element: ET.Element) -> None:
    if element.get("trainId") or element.get("destinationId"):
        raise Refused(f"Engine {element.get('id')} is assigned to a train. Reset or terminate that train first.")


def _engine_put(ed: Editor, element: ET.Element, location: str, track: str) -> tuple[ET.Element, ET.Element]:
    place = ed.location(location)
    target = ed._one(place.findall("track"), track, "track")
    _set_ordered(element, {"locationId": place.get("id"), "secLocationId": target.get("id")}, ENGINE_ORDER)
    return place, target


# A train's locomotive model and road, as JMRI's Edit Train window offers and checks them
# (TrainEditFrame:251-261, 573-579, 628-676). Train.NONE is "", shown as a blank first item.
def _offered_models(ed: Editor) -> list[str]:
    """EngineModels.getComboBox: the roster's model list, refilled with JMRI's defaults when empty
    (RollingStockAttribute.getNames), and the defaults when there is no engine file yet."""
    names = []
    if ENGINE_FILE in ed.docs:
        names = [e.get("name") for e in ed.docs[ENGINE_FILE].root.findall("./models/model")]
    return names or list(DEFAULT_MODELS)


def _no_choice(ed: Editor, key: str, value) -> str:
    """Blank is the window's no-choice item. "None" (any case) means the same unless a model or
    road really has that name."""
    text = "" if value is None else str(value)
    real = _offered_models(ed) if key == "engine_model" else [e.get("roadName") for e in ed.engines()]
    return "" if text.strip().lower() == "none" and text not in real else text


def _check_train_power(ed: Editor, train: ET.Element) -> list[str]:
    count, model, road = (train.get("numberEngines", "0"), train.get("engineModel", ""),
                          train.get("engineRoad", ""))
    name = train.get("name")
    if count == "0" and (model or road):
        raise Refused(f"Train {name} needs 0 locomotives, and JMRI's Edit Train window clears the model and road "
                      "then. Set engines first, or leave engine_model and engine_road blank.")
    notes = []
    if model:
        offered = _offered_models(ed)
        if model not in offered:
            raise Refused(f"Unknown locomotive model {model!r}. The Edit Train window offers only the roster's "
                          f"models ({', '.join(offered[:12])}{', ...' if len(offered) > 12 else ''}) or blank for "
                          "any. Add an engine of that model first with add_engine.")
        kind = _model_values(ed, model)[0].get("type")
        if kind not in ed.type_entries(train):
            raise Refused(f"Train {name} does not service locomotive model {model} type ({kind or 'none'}). "
                          "Add that locomotive type to the train, or pick another model.")
        if not any(e.get("model") == model for e in ed.engines()):
            notes.append(f"Warning: no engine of model {model} is in the roster, so the train will not build "
                         "until one is added.")
    if road:
        # EngineManager.updateEngineRoadComboBox: only roads of engines of the chosen model, or of any engine.
        roads = sorted({e.get("roadName") for e in ed.engines() if not model or e.get("model") == model})
        if road not in roads:
            raise Refused(f"No locomotive {'of model ' + model + ' ' if model else ''}has road {road!r}. The Edit "
                          f"Train window offers {', '.join(roads) or 'no roads'}, or blank for any.")
        option = train.get("locoRoadOption", ALL)
        listed = road in [r.get("name") for r in train.findall("./locoRoads/locoRoad")]
        if option != ALL and listed != (option == INCLUDE):
            raise Refused(f"Train {name} does not service locomotives with road {road}; its loco road list "
                          f"({option}) refuses it.")
        types = ed.type_entries(train)
        if not any(e.get("roadName") == road and e.get("type") in types for e in ed.engines()):
            raise Refused(f"No road {road} in the locomotive roster that also meets the locomotive types "
                          f"serviced by train {name}.")
    return notes


@action()
def add_engine_type(ed: Editor, name: str, like: str | None = None) -> str:
    """Add a locomotive type. With like, every location, track and train that takes that loco type takes this too."""
    if not name.strip():
        raise Refused("A type needs a name")
    if name in _engine_names(ed, "types", "type"):
        raise Refused(f"Locomotive type {name!r} already exists")
    if name in ed.car_types():
        raise Refused(f"{name!r} is a car type. Tracks and trains keep one list of type names, "
                      "so a car type and a loco type with one name could not be told apart")
    if like is not None and like not in _engine_names(ed, "types", "type"):
        raise Refused(f"Unknown locomotive type {like!r}")
    _engine_register(ed, "types", "type", name)
    done = [0, 0, 0]
    if like:
        for location in ed.locations():
            if like in ed.type_entries(location):
                done[0] += ed.add_type_to(location, name, 2)
            for track in location.findall("track"):
                if like in ed.type_entries(track):
                    done[1] += ed.add_type_to(track, name, 3)
        for train in ed.trains():
            if like in ed.type_entries(train):
                done[2] += ed.add_type_to(train, name, 2)
    return f"Added locomotive type {name}: {done[0]} locations, {done[1]} tracks, {done[2]} trains."


@action()
def rename_engine_type(ed: Editor, old: str, new: str) -> str:
    """Rename a locomotive type on its engines and on every location, track and train that takes it."""
    if old not in _engine_names(ed, "types", "type"):
        raise Refused(f"Unknown locomotive type {old!r}")
    if not new.strip() or new in _engine_names(ed, "types", "type") or new in ed.car_types():
        raise Refused(f"Type {new!r} already exists or is blank")
    count = _rename_values(_engine_root(ed), {"type": ("name",), "engine": ("type",)}, old, new)
    count += _rename_values(ed.loc_root, {"locoType": ("name",)}, old, new)
    count += _rename_values(ed.train_root, {"locoType": ("name",)}, old, new)
    return f"Renamed locomotive type {old} to {new}: {count} places."


@action()
def delete_engine_type(ed: Editor, name: str) -> str:
    """Delete a locomotive type no engine has. Locations, tracks and trains stop taking it."""
    if name not in _engine_names(ed, "types", "type"):
        raise Refused(f"Unknown locomotive type {name!r}")
    users = [e.get("id") for e in ed.engines() if e.get("type") == name]
    if users:
        raise Refused(f"Engines still have type {name}: {', '.join(users[:8])}")
    _keep_one(ed, "types", "type")
    holder = _engine_section(ed, "types")
    for entry in list(holder.findall("type")):
        if entry.get("name") == name:
            holder.remove(entry)
    _indent(holder, 1)
    count = 0
    for root in (ed.loc_root, ed.train_root):
        for types in root.iter("types"):
            for entry in list(types.findall("locoType")):
                if entry.get("name") == name:
                    types.remove(entry)
                    count += 1
    return f"Deleted locomotive type {name}; {count} locations, tracks and trains no longer list it."


@action()
def add_engine(ed: Editor, road: str, number: str, model: str, type: str | None = None, length: int | None = None,
               hp: int | None = None, weight_tons: int | None = None, b_unit: bool | None = None,
               location: str | None = None, track: str | None = None, force: bool = False, **fields) -> str:
    """Add a locomotive. Type, length, hp, weight and B unit belong to the model: for a model that already has
    engines they come from those engines, and a different value is refused. A JMRI default model starts with
    JMRI's values. Location and track place it, checking the track takes its type unless force."""
    number = str(number)
    if not road.strip() or not number.strip():
        raise Refused("An engine needs a road and a number")
    if len(split_name(number)) > ROAD_NUMBER_MAX or any(c in number for c in RESERVED):
        raise Refused(f"JMRI takes a road number of at most {ROAD_NUMBER_MAX} characters, without {RESERVED}")
    identity = f"{road}{number}"
    if identity in [e.get("id") for e in ed.engines()]:
        raise Refused(f"Engine {identity} already exists")
    if not model.strip():
        raise Refused("An engine needs a model: JMRI keeps its horsepower and weight there and drops them without one")
    if (location is None) != (track is None):
        raise Refused("Give both location and track, or neither")
    given = {k: v for k, v in (("type", type), ("length", length), ("hp", hp), ("weight_tons", weight_tons),
                               ("b_unit", b_unit)) if v is not None}
    wanted = _model_fields(ed, given)
    known, source = _model_values(ed, model)
    if source == "engines":
        clash = [k for k, v in wanted.items() if v != known[k]]
        if clash:
            raise Refused(f"Model {model} has {', '.join(f'{k} {known[k]!r}' for k in clash)} on its engines, and "
                          "JMRI keeps one value per model. Leave those out, or change them all with "
                          "update_engine_model.")
    values = {"b_unit": "false", **known, **wanted}
    if not values.get("type") or not values.get("length"):
        raise Refused(f"Model {model} is new, so give its type and length")
    values = _model_fields(ed, values)
    element = ET.Element("engine", {"id": identity, "roadName": road, "roadNumber": number})
    _set_ordered(element, {"moves": "0", "date": "", "selected": "false", "model": model}, ENGINE_ORDER)
    _apply_model(ed, element, values)
    _engine_register(ed, "models", "model", model)
    ed.register("roads", "road", road)
    holder = _engine_section(ed, "engines")
    holder.append(element)
    if location is not None:
        place, target = _engine_put(ed, element, location, track)
        if not force:
            _engine_types_at(ed, element, place, target)
    _engine_fields(ed, element, fields)
    _indent(holder, 1)
    where = f" on {track}" if track else ""
    return f"Added engine {road} {number}, model {model}{where}."


@action()
def update_engine(ed: Editor, engine: str, model: str | None = None, **fields) -> str:
    """Change an engine's own fields: built, owner, comment, value, rfid, out of service, location unknown, or its
    model. A new model with engines must match this engine's type, length, hp, weight and B unit."""
    element = _engine(ed, engine)
    _engine_free(element)
    if model is not None and model != element.get("model"):
        if not model.strip():
            raise Refused("An engine needs a model")
        mine = {k: element.get(a, "false" if k == "b_unit" else "") for k, a in MODEL_FIELDS.items()}
        known, source = _model_values(ed, model)
        if source == "engines":
            clash = [k for k in MODEL_FIELDS if known[k] != mine[k]]
            if clash:
                raise Refused(f"Model {model} differs in {', '.join(clash)}. JMRI keeps one value per model, "
                              "so change the model's values first with update_engine_model.")
        _set_ordered(element, {"model": model}, ENGINE_ORDER)
        _engine_register(ed, "models", "model", model)
    _engine_fields(ed, element, fields)
    return f"Updated engine {element.get('id')}."


@action()
def update_engine_model(ed: Editor, model: str, type: str | None = None, length: int | None = None,
                        hp: int | None = None, weight_tons: int | None = None, b_unit: bool | None = None) -> str:
    """Change a model's type, length, hp, weight or B unit on every engine of that model, as JMRI does."""
    engines = [e for e in ed.engines() if e.get("model") == model]
    if not engines:
        raise Refused(f"No engine has model {model!r}. JMRI stores only a model's name, so its values live on "
                      "its engines; add an engine with them instead.")
    given = {k: v for k, v in (("type", type), ("length", length), ("hp", hp), ("weight_tons", weight_tons),
                               ("b_unit", b_unit)) if v is not None}
    if not given:
        raise Refused("Nothing to change")
    values = _model_fields(ed, given)
    for element in engines:
        _engine_free(element)
        _apply_model(ed, element, values)
    note = ""
    if "type" in values:
        names = {t.get("id"): t for t in ed.tracks()}
        away = [e.get("id") for e in engines if e.get("secLocationId") in names
                and values["type"] not in ed.type_entries(names[e.get("secLocationId")])]
        if away:
            note = f" These sit on tracks that do not take {values['type']}: {', '.join(away[:8])}."
    return f"Model {model}: {len(engines)} engines changed.{note}"


@action()
def rename_engine_model(ed: Editor, old: str, new: str) -> str:
    """Rename a model on its engines and in the model, second-leg and third-leg model of every train."""
    if old not in _engine_names(ed, "models", "model") and not any(e.get("model") == old for e in ed.engines()):
        raise Refused(f"Unknown model {old!r}")
    if not new.strip() or new in _engine_names(ed, "models", "model"):
        raise Refused(f"Model {new!r} already exists or is blank")
    count = _rename_values(_engine_root(ed), {"model": ("name",), "engine": ("model",)}, old, new)
    # Train.replaceModel: engineModel, leg2Model and leg3Model.
    count += _rename_values(ed.train_root, {"train": ("engineModel", "leg2Model", "leg3Model")}, old, new)
    _engine_register(ed, "models", "model", new)
    return f"Renamed model {old} to {new}: {count} places."


@action()
def delete_engine_model(ed: Editor, model: str) -> str:
    """Delete a model no engine and no train uses."""
    if model not in _engine_names(ed, "models", "model"):
        raise Refused(f"Unknown model {model!r}")
    users = [e.get("id") for e in ed.engines() if e.get("model") == model]
    users += [f"train {t.get('name')}" for t in ed.trains()
              if model in (t.get("engineModel"), t.get("leg2Model"), t.get("leg3Model"))]
    if users:
        raise Refused(f"Still used by: {', '.join(users[:8])}")
    _keep_one(ed, "models", "model")
    holder = _engine_section(ed, "models")
    for entry in list(holder.findall("model")):
        if entry.get("name") == model:
            holder.remove(entry)
    _indent(holder, 1)
    return f"Deleted model {model}."


@action(session=True)
def place_engine(ed: Editor, engine: str, location: str, track: str, force: bool = False) -> str:
    """Set an engine, or a consist by its lead, on a track where it really is. No move is counted. Checks the
    track and location take its type unless force."""
    element = _engine(ed, engine)
    _engine_free(element)
    members = [element]
    if element.get("consist"):
        if element.get("leadConsist") != "true":
            raise Refused(f"{element.get('id')} is in consist {element.get('consist')}. Place the lead.")
        members = [e for e in ed.engines() if e.get("consist") == element.get("consist")]
    place = ed.location(location)
    target = ed._one(place.findall("track"), track, "track")
    for member in members:
        _engine_free(member)
        if not force:
            _engine_types_at(ed, member, place, target)
    for member in members:
        _engine_put(ed, member, location, track)
    return f"Placed {len(members)} engine(s) on {target.get('name')}."


@action()
def delete_engine(ed: Editor, engine: str) -> str:
    """Delete an engine not assigned to a train and not in a consist."""
    element = _engine(ed, engine)
    _engine_free(element)
    if element.get("consist"):
        raise Refused(f"Remove it from consist {element.get('consist')} first")
    holder = _engine_section(ed, "engines")
    holder.remove(element)
    _indent(holder, 1)
    return f"Deleted engine {element.get('id')}."


@action()
def set_consist(ed: Editor, name: str, engines: list[str], lead: str | None = None, number: int = 0) -> str:
    """Make a consist from engines on one track. The builder uses the lead and takes the rest with it, and a train
    needing N engines takes a consist only of exactly N. number is the lead's consist address, 0 for none."""
    if not name.strip():
        raise Refused("A consist needs a name")
    members = [_engine(ed, e) for e in engines]
    if len(members) < 2 or len({id(m) for m in members}) != len(members):
        raise Refused("A consist needs at least two different engines")
    others = [m.get("id") for m in members if m.get("consist") and m.get("consist") != name]
    if others:
        raise Refused(f"Already in another consist: {', '.join(others)}. Clear that consist first")
    homeless = [m.get("id") for m in members if not m.get("secLocationId")]
    if homeless:
        raise Refused(f"Consist engines need a track; none on: {', '.join(homeless)}")
    if len({(m.get("locationId"), m.get("secLocationId")) for m in members}) != 1:
        raise Refused("Consist engines must be on the same track. JMRI's window asks to move them together, and "
                      "the builder sends the others from wherever they are")
    chosen = _engine(ed, lead) if lead else members[0]
    if chosen not in members:
        raise Refused("The lead must be one of the engines")
    address = _int_field("number", number)
    for member in members:
        _engine_free(member)
    for engine in ed.engines():
        if engine.get("consist") == name:
            _set_ordered(engine, {"consist": None, "leadConsist": None, "consistNum": None, "blocking": None},
                         ENGINE_ORDER)
    # EngineEditFrame:192-197: joining a consist sets blocking to the consist size, so the lead is 1.
    ordered = [chosen] + [m for m in members if m is not chosen]
    for position, member in enumerate(ordered, 1):
        _set_ordered(member, {"blocking": str(position), "consist": name}, ENGINE_ORDER)
    _set_ordered(chosen, {"leadConsist": "true", "consistNum": str(address) if address else None}, ENGINE_ORDER)
    holder = _engine_section(ed, "newConsists")
    if name not in [c.get("name") for c in holder.findall("consist")]:
        ET.SubElement(holder, "consist", {"name": name})
        _indent(holder, 1)
    return f"Consist {name}: {len(members)} engines, lead {chosen.get('id')}."


@action()
def clear_consist(ed: Editor, name: str) -> str:
    """Break up a consist and remove its name."""
    count = 0
    for engine in ed.engines():
        if engine.get("consist") == name:
            _engine_free(engine)
            _set_ordered(engine, {"consist": None, "leadConsist": None, "consistNum": None, "blocking": None},
                         ENGINE_ORDER)
            count += 1
    holder = _engine_section(ed, "newConsists")
    found = [c for c in holder.findall("consist") if c.get("name") == name]
    if not found and not count:
        raise Refused(f"No consist {name!r}")
    for entry in found:
        holder.remove(entry)
    _indent(holder, 1)
    return f"Consist {name} removed from {count} engines."


# ---- Divisions ------------------------------------------------------------------------
# Checked against JMRI 5.16, locations/divisions. Divisions live first in the location
# file; locations, cars and engines hold a division id. DivisionManager.register parses
# the id as an integer. Only cars use a home division in the builder (TrainBuilderCars:
# 894-976), and which rule applies depends on the load type of the car's load.

DIVISION_NAME_MAX = 25  # DivisionEditFrame.MAX_NAME_LENGTH, Control.max_len_string_location_name.
LOCATION_ORDER = ("id", "name", "divisionId")
CAR_DIVISION_AFTER = ("id", "roadName", "roadNumber", "type", "length", "color", "weight", "weightTons", "built",
                      "locationId", "routeLocationId", "secLocationId", "destinationId", "routeDestinationId",
                      "secDestinationId", "divisionId")


def _divisions(ed: Editor) -> list[ET.Element]:
    return ed.loc_root.findall("./divisions/division")


def _division(ed: Editor, text: str) -> ET.Element:
    return ed._one(_divisions(ed), text, "division")


def _division_name(ed: Editor, name: str, current: ET.Element | None = None) -> None:
    if not name.strip():
        raise Refused("A division needs a name")
    if len(name) > DIVISION_NAME_MAX:
        raise Refused(f"JMRI takes a division name of at most {DIVISION_NAME_MAX} characters")
    if any(d.get("name") == name and d is not current for d in _divisions(ed)):
        raise Refused(f"Division {name!r} already exists")


def _set_division_attr(element: ET.Element, identity: str | None, order: tuple[str, ...]) -> None:
    items = [(k, v) for k, v in element.attrib.items() if k != "divisionId"]
    if identity:
        position = max((i + 1 for i, (k, _) in enumerate(items) if k in order), default=len(items))
        items.insert(position, ("divisionId", identity))
    element.attrib.clear()
    element.attrib.update(items)


@action()
def add_division(ed: Editor, name: str, comment: str = "") -> str:
    """Add a division. Give it to locations with set_location_division and to cars with set_car_division."""
    _division_name(ed, name)
    holder = ed.loc_root.find("divisions")
    if holder is None:  # LocationManagerXml:47 writes divisions first.
        holder = ET.Element("divisions")
        holder.tail = ed.loc_root.text
        ed.loc_root.insert(0, holder)
    identity = str(_next(d.get("id") for d in _divisions(ed)))
    ET.SubElement(holder, "division", {"id": identity, "name": name, "comment": comment})
    _indent(holder, 1)
    return f"Added division {name} (id {identity})."


@action()
def update_division(ed: Editor, division: str, name: str | None = None, comment: str | None = None) -> str:
    """Rename a division or change its comment. Locations and cars hold its id, so they follow."""
    element = _division(ed, division)
    if name is not None:
        _division_name(ed, name, element)
        element.set("name", name)
    if comment is not None:
        element.set("comment", comment)
    return f"Updated division {element.get('name')}."


@action()
def delete_division(ed: Editor, division: str) -> str:
    """Delete a division. Its locations, cars and engines are left with no division, which changes where those
    cars are routed: a car with no division takes no home division search."""
    element = _division(ed, division)
    identity = element.get("id")
    counts = [0, 0, 0]
    for index, items in enumerate((ed.locations(), ed.cars(), ed.engines())):
        for item in items:
            if item.get("divisionId") == identity:
                item.attrib.pop("divisionId")
                counts[index] += 1
    holder = ed.loc_root.find("divisions")
    holder.remove(element)
    _indent(holder, 1)
    return (f"Deleted division {element.get('name')}: cleared on {counts[0]} locations, {counts[1]} cars, "
            f"{counts[2]} engines.")


@action()
def set_location_division(ed: Editor, division: str | None, locations: list[str]) -> str:
    """Put locations in a division, or take them out with division null. Its tracks are in it too."""
    identity = _division(ed, division).get("id") if division else None
    for name in locations:
        _set_division_attr(ed.location(name), identity, LOCATION_ORDER)
    return f"{len(locations)} locations now in {division or 'no division'}."


@action()
def set_car_division(ed: Editor, division: str | None, cars: list[str]) -> str:
    """Give cars a home division, or clear it with division null. A kernel follows its car, as Set Car does. A car
    with a home division and no final destination is always routed: empties go home, loads by where they are."""
    identity = _division(ed, division).get("id") if division else None
    chosen = []
    for text in cars:
        car = ed.car(text)
        group = [c for c in ed.cars() if c.get("kernel") == car.get("kernel")] if car.get("kernel") else [car]
        chosen += [c for c in group if c not in chosen]
    for car in chosen:
        _free(car)
        _set_division_attr(car, identity, CAR_DIVISION_AFTER)
    return f"{len(chosen)} cars now have home division {division or 'none'}."


@action()
def set_load_type(ed: Editor, load: str, load_type: str, types: list[str] | None = None) -> str:
    """Set whether a custom load counts as Load or Empty, for one or more car types or all that have it. Division
    rules go by this: an Empty goes home, a Load goes by where it is. It also decides the blank Ship flip."""
    if load in ed.defaults():
        raise Refused("A default load's type is fixed: the default empty is Empty and the default load is Load")
    if load_type not in ("Load", "Empty"):
        raise Refused("load_type must be Load or Empty")
    count = 0
    for holder in ed.car_root.findall("./loads/load"):
        if types is None or holder.get("type") in types:
            for entry in holder.findall("carLoad"):
                if entry.get("name") == load:
                    entry.set("loadType", load_type)
                    count += 1
    if not count:
        raise Refused(f"No custom load {load!r}" + (f" for {', '.join(types)}" if types else ""))
    return f"Load {load} is now {load_type} for {count} car types."


# ---- End of engines and divisions ---------------------------------------------------


# ---- Manual builds and automations (start) ------------------------------------------
# Checked against JMRI 5.16: trains/manualtrainbuilder (TrainManualBuild, TrainManualBuildItem,
# the edit window's TrainManualBuildTableModel), trains/trainbuilder/TrainBuilder:310-445, and
# automation (Automation, AutomationItem, AutomationManager, actions/*). Both live in the train
# file, in the order TrainManagerXml:70-73 stores them.

from ops_data import ACTIVATE_DAY, STEP_AUTOMATION, STEP_FAIL, STEP_GOTO, STEP_KINDS, STEP_STOP, STEP_TRAIN  # noqa: E402
from ops_data import Railroad as _Railroad  # noqa: E402

TRAIN_SECTIONS = ("options", "trains", "manualBuilds", "trainScheduleOptions", "schedules", "automationOptions",
                  "automations")
MB_ITEM_ORDER = ("id", "sequenceId", "trainScheduleId", "type", "road", "load", "routeLocationId", "locTrackId",
                 "destinationId", "destTrackId", "count", "warn", "fail", "remove")
MANUAL_FIELDS = {"type", "road", "load", "stop", "track", "destination", "destination_track", "day", "count",
                 "warn", "fail", "remove"}
STEP_FIELDS = {"do", "train", "stop", "automation", "goto", "day", "message", "message_fail", "halt_on_failure"}
AUTOMATION_NAME_MAX = 25  # Control.max_len_string_automation_name, AutomationTableFrame.checkName.
# Steps that open a window or a print dialog on the computer running JMRI (actions/Print*,
# UpdateSwitchListAction with real-time switch lists), and Message Yes or No, which always asks.
DIALOG_STEPS = {"print_train_manifest", "print_train_manifest_if_selected", "print_train_build_report",
                "print_switch_list", "print_switch_list_changes", "update_switch_list", "message_yes_no"}
PROGRAM_STEPS = {"run_train", "run_switch_list", "run_switch_list_changes"}
WAIT_STEPS = {"wait_for_train", "wait_for_train_to_terminate", "wait_for_switch_list", "wait_for_automation"}
PREVIEW_NAMES = {"print_train_manifest": "Preview Train Manifest",
                 "print_train_manifest_if_selected": "Preview Train Manifest if Selected",
                 "print_train_build_report": "Preview Train Build Report",
                 "print_switch_list": "Preview Switch List", "print_switch_list_changes": "Preview Switch List Changes"}
DIALOG_NOTE = ("JMRI shows a step's message in a modal window and waits for someone to press a button. With no one "
               "at that computer, or a headless JMRI, the automation stops there; ops_live_automation then answers "
               "still_running.")


def _train_section(ed: Editor, tag: str) -> ET.Element:
    """A top-level section of the train file, created where JMRI stores it."""
    root = ed.train_root
    found = root.find(tag)
    if found is not None:
        return found
    found = ET.Element(tag)
    rank = TRAIN_SECTIONS.index(tag)
    position = 0
    for index, child in enumerate(root):
        if child.tag in TRAIN_SECTIONS and TRAIN_SECTIONS.index(child.tag) <= rank:
            position = index + 1
    indent = root.text or "\n  "
    if position and position == len(root):
        found.tail = root[position - 1].tail
        root[position - 1].tail = indent
    else:
        found.tail = indent
    root.insert(position, found)
    return found


def _close(holder: ET.Element, level: int = 1) -> None:
    """Re-indent a section; an emptied one is written as JMRI writes it, <tag />."""
    if len(holder):
        _indent(holder, level)
    else:
        holder.text = None


def _bool_field(name: str, value) -> bool:
    if value not in (True, False):
        raise Refused(f"{name} is true or false")
    return value


def _route_stops(ed: Editor, train: ET.Element) -> list[ET.Element]:
    link = train.find("route")
    if link is None or not link.get("id"):
        raise Refused(f"Train {train.get('name')} has no route")
    route = ed.route(link.get("id"))
    return sorted(route.findall("location"), key=lambda s: int(s.get("sequenceId", "0") or 0))


def _stop(ed: Editor, train: ET.Element, stop) -> ET.Element:
    """A stop on the train's route, by location name or by position from 1."""
    stops = _route_stops(ed, train)
    if isinstance(stop, int) and not isinstance(stop, bool):
        if not 1 <= stop <= len(stops):
            raise Refused(f"{train.get('name')}'s route has {len(stops)} stops")
        return stops[stop - 1]
    found = [s for s in stops if s.get("name") == stop or s.get("id") == stop]
    if len(found) != 1:
        raise Refused(f"{'Several stops' if found else 'No stop'} {stop!r} on {train.get('name')}'s route"
                      + ("; give its position from 1" if found else ""))
    return found[0]


def _train_day(ed: Editor, name: str) -> str:
    days = {s.get("name"): s.get("id") for s in ed.train_root.findall("./schedules/schedule")}
    if name not in days:
        raise Refused(f"No train schedule (day) {name!r}")
    return days[name]


def _train_accepts(train: ET.Element, option_attr: str, tag: str, item: str, value: str) -> bool:
    names = [e.get("name") for e in train.findall(f"{tag}/{item}")]
    option = train.get(option_attr, ALL)
    return option == ALL or (value in names) == (option == INCLUDE)


def _car_loads(ed: Editor, kind: str) -> list[str]:
    """CarLoads.getNames(type): the default empty and load, then the type's custom loads."""
    names = list(ed.defaults())
    for holder in ed.car_root.findall("./loads/load"):
        if holder.get("type") == kind:
            names += [e.get("name") for e in holder.findall("carLoad") if e.get("name") not in names]
    return names


def _line_track(ed: Editor, place: ET.Element, text: str, kind: str, road: str, load: str, what: str) -> ET.Element:
    """TrainManualBuildTableModel.filterTracks: no staging, and the track takes the line's type, road and load."""
    track = ed._one(place.findall("track"), text, f"{what} at {place.get('name')}")
    parsed = _Railroad._track(track, place.get("id"))
    if parsed.is_staging:
        raise Refused(f"JMRI's manual build window offers no staging tracks, so {track.get('name')} cannot be a {what}")
    if kind and kind not in ed.type_entries(track):
        raise Refused(f"{track.get('name')} does not take {kind}")
    if road and not parsed.accepts_road(road):
        raise Refused(f"{track.get('name')} does not take road {road}")
    if load and not parsed.accepts_load(load, kind):
        raise Refused(f"{track.get('name')} does not take load {load}")
    return track


def _manual_line(ed: Editor, train: ET.Element, line: dict) -> dict:
    """Check one line as the manual build window allows it, and return its mbItem attributes."""
    unknown = set(line) - MANUAL_FIELDS
    if unknown:
        raise Refused(f"Unknown manual build fields: {', '.join(sorted(unknown))}")
    kind, road, load = (str(line.get(k) or "") for k in ("type", "road", "load"))
    name = train.get("name")
    if kind:
        # getTypeComboBox: car types the train takes.
        if kind not in ed.car_types():
            raise Refused(f"Unknown car type {kind!r}")
        if kind not in ed.type_entries(train):
            raise Refused(f"Train {name} does not take {kind}")
    if road:
        # getRoadComboBox: CarRoads.getNames(type) is the roads of cars of that type, so a line with no type
        # has no road to choose, and the window clears any road it does not list when it opens.
        if not kind:
            raise Refused("A road needs a type: JMRI's window lists only roads of cars of the line's type")
        if not any(c.get("type") == kind and c.get("roadName") == road for c in ed.cars()):
            raise Refused(f"No {kind} car has road {road}, so JMRI's window would clear it")
        if not _train_accepts(train, "carRoadOption", "carRoads", "carRoad", road):
            raise Refused(f"Train {name} does not take road {road}")
    if load:
        if load not in _car_loads(ed, kind):
            raise Refused(f"{load!r} is not a load for {kind or 'a line with no type'}"
                          + ("" if kind else "; only the default empty and load are"))
        if not _train_accepts(train, "carLoadOption", "carLoads", "carLoad", load):
            raise Refused(f"Train {name} does not take load {load}")
    attrs = {"trainScheduleId": "", "type": kind, "road": road, "load": load}
    if line.get("day"):
        attrs["trainScheduleId"] = _train_day(ed, line["day"])
    if line.get("track") and not line.get("stop"):
        raise Refused("A pick up track needs its stop: JMRI reads the track only through the stop")
    if line.get("stop") not in (None, ""):
        stop = _stop(ed, train, line["stop"])
        place = ed.location(stop.get("locationId"))
        # filterRouteLocations: only stops whose location takes the type.
        if kind and kind not in ed.type_entries(place):
            raise Refused(f"{place.get('name')} does not take {kind}")
        attrs["routeLocationId"] = stop.get("id")
        if line.get("track"):
            attrs["locTrackId"] = _line_track(ed, place, line["track"], kind, road, load, "pick up track").get("id")
    if line.get("destination_track") and not line.get("destination"):
        raise Refused("A destination track needs its destination")
    if line.get("destination"):
        place = ed.location(line["destination"])
        if kind and kind not in ed.type_entries(place):
            raise Refused(f"{place.get('name')} does not take {kind}")
        attrs["destinationId"] = place.get("id")
        if line.get("destination_track"):
            attrs["destTrackId"] = _line_track(ed, place, line["destination_track"], kind, road, load,
                                               "destination track").get("id")
    # The window's count column is a plain integer; the builder takes cars only while count > 0, so a line
    # of 0 with remove set only takes its cars out of the build.
    attrs["count"] = str(_int_field("count", line.get("count", 1)))
    warn, fail = (_bool_field(k, line.get(k, False)) for k in ("warn", "fail"))
    if warn and fail:
        raise Refused("warn and fail exclude each other: JMRI's window clears one when the other is set")
    attrs.update(warn=_bool(warn), fail=_bool(fail), remove=_bool(_bool_field("remove", line.get("remove", False))))
    return attrs


def _manual_build(ed: Editor, train: ET.Element) -> ET.Element | None:
    found = ed.train_root.findall("./manualBuilds/manualBuild")
    return next((b for b in found if b.get("trainId") == train.get("id")), None)


@action()
def set_manual_build(ed: Editor, train: str, lines: list[dict], comment: str | None = None) -> str:
    """Set a train's manual build lines, replacing any it has. The builder offers cars to each line in order before
    its normal search. Each line: type, road (needs type), load, stop (route stop name or position), track (a pick up
    track at that stop), destination and destination_track (a final destination the car is routed to), day (train
    schedule), count (default 1), and warn, fail or remove when a line cannot be filled. remove takes every other
    matching car out of the build."""
    element = ed.train(train)
    if not lines:
        raise Refused("Give at least one line, or use delete_manual_build")
    items = [_manual_line(ed, element, dict(line)) for line in lines]
    holder = _train_section(ed, "manualBuilds")
    build = _manual_build(ed, element)
    if build is None:
        identity = str(_next(b.get("id") for b in holder.findall("manualBuild")))
        build = ET.SubElement(holder, "manualBuild", {"id": identity, "trainId": element.get("id"),
                                                      "name": element.get("name"), "comment": ""})
    build.set("name", element.get("name"))
    if comment is not None:
        build.set("comment", comment)
    # TrainManualBuild.register parses the number after "m"; new ids carry on from the highest.
    start = _next((i.get("id", "") for i in build.findall("mbItem")), "m")
    for old in list(build):
        build.remove(old)
    for number, attrs in enumerate(items, 1):
        entry = ET.SubElement(build, "mbItem", {"id": f"{build.get('id')}m{start + number - 1}",
                                                "sequenceId": str(number)})
        _set_ordered(entry, attrs, MB_ITEM_ORDER)
    _indent(holder, 1)
    return f"Train {element.get('name')} now has {len(items)} manual build lines."


@action()
def delete_manual_build(ed: Editor, train: str) -> str:
    """Remove a train's manual build lines, so it builds by the normal search only."""
    element = ed.train(train)
    build = _manual_build(ed, element)
    if build is None:
        raise Refused(f"Train {element.get('name')} has no manual build")
    holder = ed.train_root.find("manualBuilds")
    holder.remove(build)
    _close(holder)
    return f"Removed the manual build of {element.get('name')}."


def _automations(ed: Editor) -> list[ET.Element]:
    return ed.train_root.findall("./automations/automation")


def _automation(ed: Editor, text: str) -> ET.Element:
    return ed._one(_automations(ed), text, "automation")


def _automation_name(ed: Editor, name: str, current: ET.Element | None = None) -> None:
    if not isinstance(name, str) or not name.strip():
        raise Refused("An automation needs a name")
    if len(name) > AUTOMATION_NAME_MAX:
        raise Refused(f"JMRI takes an automation name of at most {AUTOMATION_NAME_MAX} characters")
    # AutomationManager.newAutomation returns the existing one for a name, so names are unique.
    if any(a.get("name") == name and a is not current for a in _automations(ed)):
        raise Refused(f"Automation {name!r} already exists")


def _message_text(name: str, text) -> str:
    """Action.getFormatedMessage runs the text through MessageFormat, which throws on a bad brace."""
    if not isinstance(text, str):
        raise Refused(f"{name} must be text")
    quoted, index = False, 0
    while index < len(text):
        char = text[index]
        if char == "'":
            if text[index + 1:index + 2] == "'":
                index += 2
                continue
            quoted = not quoted
        elif char == "{" and not quoted:
            end = text.find("}", index)
            if end < 0 or not text[index + 1:end].split(",")[0].strip().isdigit():
                raise Refused(f"{name}: JMRI formats it with MessageFormat, so {{ must open an argument such as "
                              "{1} (train) or {2} (stop); quote a literal brace as '{'")
            index = end
        index += 1
    if quoted:
        raise Refused(f"{name}: in MessageFormat a single ' starts quoted text and disappears; write '' for an "
                      "apostrophe")
    return text


def _train_scripts(train: ET.Element) -> list[str]:
    scripts = train.find("scripts")
    return [e.get("name", "") for e in scripts] if scripts is not None else []


def _steps(ed: Editor, automation: ET.Element, steps: list[dict], allow_dialogs: bool) -> tuple[list[dict], list[str]]:
    """Check each step as JMRI keeps it on a save. Returns item attributes plus messages, and warnings."""
    if not isinstance(steps, list) or not steps:
        raise Refused("An automation needs at least one step")
    out, warnings, dialogs = [], [], []
    for number, raw in enumerate(steps, 1):
        step = dict(raw)
        where = f"step {number}"
        unknown = set(step) - STEP_FIELDS
        if unknown:
            raise Refused(f"{where}: unknown fields {', '.join(sorted(unknown))}")
        kind = step.get("do")
        if kind not in STEP_KINDS:
            raise Refused(f"{where}: do must be one of {', '.join(STEP_KINDS)}")
        code = STEP_KINDS[kind][0]
        # AutomationItem.store writes a field only when the step's action uses it (getTrain, getRouteLocation,
        # getAutomationToRun, getGotoAutomationItem, getTrainSchedule), so anything else would be dropped.
        for key, flag in (("train", STEP_TRAIN), ("stop", STEP_STOP), ("automation", STEP_AUTOMATION),
                          ("goto", STEP_GOTO), ("message_fail", STEP_FAIL)):
            if step.get(key) not in (None, "") and not code & flag:
                raise Refused(f"{where}: {kind} takes no {key}, and JMRI drops it on its next save")
        if step.get("day") not in (None, "") and code != ACTIVATE_DAY:
            raise Refused(f"{where}: only activate_train_schedule takes a day")
        entry = {"kind": kind, "code": code, "attrs": {}, "goto": None, "message": "", "message_fail": ""}
        train = None
        if code & STEP_TRAIN:
            if step.get("train") in (None, ""):
                if kind != "message_yes_no":
                    raise Refused(f"{where}: {kind} needs a train; without one it always fails")
            else:
                train = ed.train(step["train"])
                entry["attrs"]["trainId"] = train.get("id")
                if _train_scripts(train):
                    warnings.append(f"{where} uses train {train.get('name')}, which runs scripts "
                                    f"({', '.join(_train_scripts(train)[:3])}). A script that opens a window stops "
                                    "a headless run the same way a message does.")
        if step.get("stop") not in (None, ""):
            if train is None:
                raise Refused(f"{where}: a stop needs the train: JMRI reads it from that train's route")
            entry["attrs"]["routeLocationId"] = _stop(ed, train, step["stop"]).get("id")
        if code & STEP_AUTOMATION:
            if step.get("automation") in (None, ""):
                raise Refused(f"{where}: {kind} needs an automation")
            target = automation if step["automation"] in (automation.get("name"), automation.get("id")) \
                else _automation(ed, step["automation"])
            if target is automation and kind == "wait_for_automation":
                raise Refused(f"{where}: an automation waiting for itself never finishes")
            if target is automation and kind == "run_automation":
                # Automation.run starts again from the first step, so this repeats until something stops it.
                warnings.append(f"{where} runs this automation again from its first step, so it repeats until "
                                "a halt, a failure with halt_on_failure, or a stop.")
            entry["attrs"]["automationId"] = target.get("id")
        if code & STEP_GOTO:
            target = step.get("goto")
            if isinstance(target, bool) or not isinstance(target, int) or not 1 <= target <= len(steps):
                raise Refused(f"{where}: goto is the number of a step in this automation, 1 to {len(steps)}")
            if target == number:
                raise Refused(f"{where}: a GOTO cannot name its own step; JMRI's list leaves it out")
            entry["goto"] = target
        if code == ACTIVATE_DAY and step.get("day") not in (None, ""):
            entry["attrs"]["trainScheduleId"] = _train_day(ed, step["day"])
        for key in ("message", "message_fail"):
            if step.get(key) not in (None, ""):
                entry[key] = _message_text(f"{where} {key}", step[key])
        if kind == "message_yes_no" and not entry["message"]:
            raise Refused(f"{where}: a Message Yes or No step needs a message; without one it asks nothing")
        entry["halt"] = _bool_field(f"{where} halt_on_failure", step.get("halt_on_failure", True))
        if kind in DIALOG_STEPS or entry["message"] or entry["message_fail"]:
            dialogs.append(f"{number} ({kind}{', message' if entry['message'] or entry['message_fail'] else ''})")
        if kind in PROGRAM_STEPS:
            warnings.append(f"{where} ({kind}) starts the outside program set in JMRI's manifest settings.")
        if kind in WAIT_STEPS:
            warnings.append(f"{where} ({kind}) waits for something else to happen; ops_live_automation waits two "
                            "minutes, then answers still_running.")
        out.append(entry)
    if dialogs:
        if not allow_dialogs:
            raise Refused(f"Steps {', '.join(dialogs)} open a window or a print dialog. {DIALOG_NOTE} Pass "
                          "allow_dialogs true if someone will be at that computer to answer it.")
        warnings.insert(0, f"Steps {', '.join(dialogs)} open a window or a print dialog. {DIALOG_NOTE}")
    return out, warnings


def _write_steps(ed: Editor, automation: ET.Element, entries: list[dict]) -> None:
    preview = ed.train_root.find("./options/trainOptions")
    preview = preview is not None and preview.get("printPreview") == "true"
    # Automation.register parses the number after "c"; new ids carry on from the highest.
    start = _next((i.get("id", "") for i in automation.findall("item")), "c")
    for old in list(automation):
        automation.remove(old)
    automation.attrib.pop("currentItem", None)  # The current step may be gone; JMRI starts from the first.
    ids = [f"{automation.get('id')}c{start + n}" for n in range(len(entries))]
    for number, entry in enumerate(entries):
        name = PREVIEW_NAMES.get(entry["kind"], STEP_KINDS[entry["kind"]][1]) if preview else STEP_KINDS[entry["kind"]][1]
        item = ET.SubElement(automation, "item", {
            "id": ids[number], "sequenceId": str(number + 1), "name": name,
            "actionCode": f"0x{entry['code']:x}", "haltFail": _bool(entry["halt"]), "actionRan": "false",
            "actionSuccessful": "false", **entry["attrs"]})
        if entry["goto"] is not None:  # GOTO steps take no day, so store order holds.
            item.set("gotoAutomationId", ids[entry["goto"] - 1])
            item.set("gotoBranched", "false")
        if entry["message"] or entry["message_fail"]:
            messages = ET.SubElement(item, "messages")
            ET.SubElement(messages, "messageOk", {"message": entry["message"]})
            ET.SubElement(messages, "messageFail", {"message": entry["message_fail"]})


def _sort_automations(holder: ET.Element) -> None:
    """AutomationManager.store writes them by name, ignoring case (getAutomationsByNameList)."""
    ordered = sorted(holder.findall("automation"), key=lambda a: a.get("name", "").lower())
    for element in ordered:
        holder.remove(element)
    holder.extend(ordered)
    _indent(holder, 1)


def _summary(text: str, warnings: list[str]) -> str:
    return text + "".join(f" Warning: {w}" for w in warnings)


@action()
def add_automation(ed: Editor, name: str, steps: list[dict], comment: str = "", allow_dialogs: bool = False) -> str:
    """Add an automation: steps JMRI runs in order. Each step: do (build_train, move_train, terminate_train,
    reset_train, activate_train_schedule, apply_train_schedule, run_automation, counter, goto_if_failure, halt and the
    rest of JMRI's list; see ops_list automations for names), plus train, stop (on that train's route), automation,
    goto (a step number here), day, message, message_fail, halt_on_failure (default true). Messages and print steps
    open windows that stop an unattended run, so they are refused unless allow_dialogs."""
    _automation_name(ed, name)
    if not isinstance(comment, str):
        raise Refused("comment must be text")
    holder = _train_section(ed, "automations")
    _train_section(ed, "automationOptions").attrib.setdefault("automationStartupId", "")
    identity = str(_next(a.get("id") for a in _automations(ed)))
    element = ET.Element("automation", {"id": identity, "name": name, "comment": comment})
    entries, warnings = _steps(ed, element, steps, _bool_field("allow_dialogs", allow_dialogs))
    holder.append(element)
    _write_steps(ed, element, entries)
    _sort_automations(holder)
    return _summary(f"Added automation {name} (id {identity}) with {len(entries)} steps.", warnings)


@action()
def update_automation(ed: Editor, automation: str, name: str | None = None, comment: str | None = None,
                      steps: list[dict] | None = None, allow_dialogs: bool = False) -> str:
    """Rename an automation, change its comment, or replace all its steps (same step fields as add_automation).
    Other automations and the startup setting hold its id, so they follow a rename. New steps start not yet run."""
    element = _automation(ed, automation)
    if name is not None:
        _automation_name(ed, name, element)
    warnings: list[str] = []
    if steps is not None:
        entries, warnings = _steps(ed, element, steps, _bool_field("allow_dialogs", allow_dialogs))
        _write_steps(ed, element, entries)
        _indent(element, 2)
    if name is not None:
        element.set("name", name)
        _sort_automations(ed.train_root.find("automations"))
    if comment is not None:
        element.set("comment", str(comment))
    if name is None and comment is None and steps is None:
        raise Refused("Nothing to change")
    return _summary(f"Updated automation {element.get('name')}.", warnings)


@action()
def delete_automation(ed: Editor, automation: str) -> str:
    """Delete an automation no other automation runs, stops, resumes or waits for. If it was the startup
    automation, JMRI runs none at startup afterwards."""
    element = _automation(ed, automation)
    identity = element.get("id")
    users = [a.get("name") for a in _automations(ed) if a is not element
             and any(i.get("automationId") == identity for i in a.findall("item"))]
    if users:
        raise Refused(f"Steps in {', '.join(users[:8])} name it. Change those with update_automation first")
    holder = ed.train_root.find("automations")
    holder.remove(element)
    _close(holder)
    note = ""
    options = ed.train_root.find("automationOptions")
    if options is not None and options.get("automationStartupId") == identity:
        options.set("automationStartupId", "")
        note = " It was the startup automation; there is none now."
    return f"Deleted automation {element.get('name')}.{note}"


@action()
def set_startup_automation(ed: Editor, automation: str | None) -> str:
    """Choose the automation JMRI runs each time it loads the trains (Automation > Startup), or none."""
    identity = _automation(ed, automation).get("id") if automation else ""
    _train_section(ed, "automationOptions").set("automationStartupId", identity)
    if not identity:
        return "No automation runs at startup."
    # TrainManagerXml.readFile:126 runs it after loading, on every JMRI that loads this folder.
    return (f"JMRI will run {automation} each time it loads the trains. Warning: that includes the copies "
            "ops_dry_run and ops_build_check load, so a startup automation that builds or moves trains changes "
            "what they start from.")


# Rename and delete cascades for the existing actions. Wrapped here, so this topic stays in one block.

def _manual_items(ed: Editor) -> list[ET.Element]:
    return ed.train_root.findall("./manualBuilds/manualBuild/mbItem")


def _wrap(name: str, before=None, after=None, note: str = "") -> None:
    entry = ACTIONS[name]
    original = entry["run"]

    def run(ed: Editor, **fields) -> str:
        if before:
            before(ed, **fields)
        text = original(ed, **fields)
        extra = after(ed, **fields) if after else ""
        return text + (f" {extra}" if extra else "")

    entry["run"] = run
    entry["help"] = (entry["help"] + " " + note).strip()


def _lines_naming(ed: Editor, attrs: tuple[str, ...], identity: str) -> list[str]:
    owners = {i: b for b in ed.train_root.findall("./manualBuilds/manualBuild") for i in b.findall("mbItem")}
    names = {t.get("id"): t.get("name") for t in ed.trains()}
    return [f"manual line {i.get('id')} of {names.get(owners[i].get('trainId'), owners[i].get('trainId'))}"
            for i in _manual_items(ed) if identity in [i.get(a) for a in attrs]]


def _refuse_track(ed: Editor, track: str, location: str | None = None) -> None:
    uses = _lines_naming(ed, ("locTrackId", "destTrackId"), ed.track(track, location).get("id"))
    if uses:
        raise Refused(f"Still used by: {', '.join(uses[:12])}. Change those with set_manual_build first")


def _refuse_location(ed: Editor, location: str) -> None:
    uses = _lines_naming(ed, ("destinationId",), ed.location(location).get("id"))
    if uses:
        raise Refused(f"Still used by: {', '.join(uses[:12])}. Change those with set_manual_build first")


def _refuse_train_automations(ed: Editor, train: str) -> None:
    identity = ed.train(train).get("id")
    used = [a.get("name") for a in _automations(ed) if any(i.get("trainId") == identity for i in a.findall("item"))]
    if used:
        raise Refused(f"Automations still use it: {', '.join(used[:8])}. Change their steps with update_automation "
                      "or delete them first")


def _drop_manual_build(ed: Editor, train: str) -> str:
    holder = ed.train_root.find("manualBuilds")
    if holder is None:
        return ""
    # The deleted train is gone from the file now, so find its build by the trains still there.
    ids = {t.get("id") for t in ed.trains()}
    gone = [b for b in holder.findall("manualBuild") if b.get("trainId") not in ids]
    for build in gone:
        holder.remove(build)
    _close(holder)
    # JMRI leaves the build behind (no listener), and a later train given the same id would inherit it.
    return "Its manual build lines were removed too." if gone else ""


def _refuse_route_change(ed: Editor, train: str, route: str) -> None:
    element = ed.train(train)
    link = element.find("route")
    if link is not None and link.get("id") == ed.route(route).get("id"):
        return
    build = _manual_build(ed, element)
    uses = [f"manual line {i.get('id')}" for i in (build.findall("mbItem") if build is not None else [])
            if i.get("routeLocationId")]
    uses += [f"step {i.get('id')} of {a.get('name')}" for a in _automations(ed) for i in a.findall("item")
             if i.get("trainId") == element.get("id") and i.get("routeLocationId")]
    if uses:
        raise Refused(f"These name a stop on the old route: {', '.join(uses[:12])}. JMRI would drop those stops, "
                      "so clear them with set_manual_build or update_automation first, then set them again")


def _rename_train_build(ed: Editor, train: str, new: str) -> str:
    build = _manual_build(ed, ed.train(new))
    if build is not None:
        build.set("name", new)  # TrainManualBuild.store writes the train's name.
    return ""


def _rename_items(attr: str):
    def after(ed: Editor, old: str, new: str, car_type: str | None = None) -> str:
        count = 0
        for item in _manual_items(ed):
            # TrainManualBuildManager.replaceType, replaceRoad and replaceLoad (the last only for the line's type).
            if item.get(attr) == old and (attr != "load" or car_type in (None, item.get("type"))):
                item.set(attr, new)
                count += 1
        return f"Manual build lines changed: {count}." if count else ""
    return after


_wrap("delete_track", before=_refuse_track, note="Refused while a manual build line names it.")
_wrap("delete_location", before=_refuse_location, note="Refused while a manual build line names it.")
_wrap("delete_train", before=_refuse_train_automations, after=_drop_manual_build,
      note="Its manual build lines go with it.")
_wrap("set_train_route", before=_refuse_route_change,
      note="Refused while its manual build lines or automation steps name a stop on the old route.")
_wrap("rename_train", after=_rename_train_build)
_wrap("rename_car_type", after=_rename_items("type"), note="Manual build lines follow.")
_wrap("rename_road", after=_rename_items("road"), note="Manual build lines follow.")
_wrap("rename_load", after=_rename_items("load"), note="Manual build lines follow.")


# ---- Manual builds and automations (end) --------------------------------------------
