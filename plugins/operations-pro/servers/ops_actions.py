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


# Helpers that the schedules and the routes and trains groups call but that belong with later groups:
# train schedule days, then engine models and train power. A group imports what it needs from here,
# since importing a later group would register its actions first.

TRAIN_ROOT_ORDER = ("options", "trains", "manualBuilds", "trainScheduleOptions", "schedules", "automationOptions",
                    "automations")


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


def _set_day_trains(day: ET.Element, ids: list[str]) -> None:
    day.set("trainIds", "".join(f"{i}," for i in ids))  # TrainSchedule.store writes "id," for each.


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


MODEL_FIELDS = {"type": "type", "length": "length", "hp": "hp", "weight_tons": "weightTons", "b_unit": "bUnit"}


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


# Each group registers its actions on import, so this order is the order of ACTIONS. The manual builds
# and automations group wraps actions of earlier groups (delete_track, delete_location, delete_train,
# set_train_route and the renames), so it loads after the others; the extras group (train legs, engine
# moves, delete_load and the pool and stop time checks) wraps actions of every group, so it loads last. Every name a group defines is also a name of this
# module, as it was before the split.
import ops_actions_names  # noqa: E402
import ops_actions_locations  # noqa: E402
import ops_actions_schedules  # noqa: E402
import ops_actions_trains  # noqa: E402
import ops_actions_cars  # noqa: E402
import ops_actions_setup  # noqa: E402
import ops_actions_engines  # noqa: E402
import ops_actions_automations  # noqa: E402
import ops_actions_extras  # noqa: E402

for _group in (ops_actions_names, ops_actions_locations, ops_actions_schedules,
               ops_actions_trains, ops_actions_cars, ops_actions_setup,
               ops_actions_engines, ops_actions_automations, ops_actions_extras):
    for _key, _value in vars(_group).items():
        if not _key.startswith("__") and _key not in globals():
            globals()[_key] = _value
del _group, _key, _value
