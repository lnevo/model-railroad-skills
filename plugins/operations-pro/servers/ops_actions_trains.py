"""Actions for routes and trains."""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

from ops_data import ALL, DIRECTIONS, EXCLUDE, EXCLUDE_ROUTES, EXCLUDE_TRAINS, INCLUDE, ROUTES, TRAINS
from ops_store import Refused
from ops_actions import (Editor, SETUP_FILE, STOP_RANDOM, TRACK_CHILDREN, TRAIN_CHILDREN, action, _bool, _check_train_power, _day,
                         _day_id, _indent, _int_field, _mask, _next, _no_choice, _place, _remove_types, _set_active,
                         _set_day_trains, _set_list, _yes)


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


# Train.AUTO and Train.AUTO_HPT (JmritOperationsTrainsBundle: Auto, Auto HPT). The builder compares the
# count with these exactly and otherwise parses it as a number, so "AUTO HPT" stops the build with a
# NumberFormatException.
AUTO, AUTO_HPT = "Auto", "Auto HPT"
# Train.NO_CABOOSE_OR_FRED, CABOOSE, FRED (Train:184-186): the three Requires buttons in Edit Train.
REQUIRES = {"none": 0, "caboose": 1, "fred": 2}


def _max_engines(ed: Editor) -> int:
    doc = ed.docs.get(SETUP_FILE)
    settings = doc.root.find("./operations/settings") if doc is not None else None
    text = settings.get("maxEngines", "6") if settings is not None else "6"
    return int(text) if text.isdigit() else 6


def _train_value(ed: Editor, key: str, value) -> str:
    """What Edit Train accepts for each field (TrainEditFrame:168-181, 242-245; Train.setDepartureTime;
    TrainEditBuildOptionsFrame:902-907). Anything else is refused rather than written."""
    if key == "engines":
        top = _max_engines(ed)
        text = str(value).strip() if not isinstance(value, bool) else ""
        if text in (AUTO, AUTO_HPT) or (text.isdigit() and int(text) <= top and text == str(int(text))):
            return text
        raise Refused(f"engines must be 0 to {top} (Settings, maximum locomotives), {AUTO} or {AUTO_HPT}, "
                      f"spelled so, not {value!r}")
    if key == "requires":
        if isinstance(value, str) and value.strip().lower() in REQUIRES:
            return str(REQUIRES[value.strip().lower()])
        if not isinstance(value, bool) and str(value).strip() in ("0", "1", "2"):
            return str(value).strip()
        raise Refused(f"requires must be none (0), caboose (1) or fred (2), not {value!r}")
    if key in ("depart_hour", "depart_minute"):
        top = 23 if key == "depart_hour" else 59
        number = _int_field(key, value)
        if number > top:
            raise Refused(f"{key} must be 0 to {top}, not {value!r}")
        return f"{number:02d}"
    if key in ("built_start", "built_end"):
        text = str(value).strip()
        if text and not text.isdigit():
            raise Refused(f"{key} must be a year or blank, not {value!r}")
        return text
    return str(value)


def _train_fields(ed: Editor, element: ET.Element, fields: dict) -> list[str]:
    """Set the fields, then check locomotive model and road on the result. Returns warnings."""
    for key in ("engine_model", "engine_road"):
        if key in fields:
            fields = {**fields, key: _no_choice(ed, key, fields[key])}
    for key, value in fields.items():
        if key in TRAIN_FIELDS:
            element.set(TRAIN_FIELDS[key], _train_value(ed, key, value))
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
    if fields.get("engines") == AUTO_HPT and _departs_staging(ed, element):
        raise Refused(f"Edit Train offers {AUTO_HPT} only for a train that does not depart staging; a staging "
                      "track's locomotives all leave with the train, so give the number on that track, or 0")
    if "engine_model" in fields or "engine_road" in fields:
        return _check_train_power(ed, element)
    return []


def _departs_staging(ed: Editor, train: ET.Element) -> bool:
    link = train.find("route")
    if link is None:
        return False
    stops = sorted(ed.route(link.get("id")).findall("location"), key=lambda e: int(e.get("sequenceId", "0")))
    if not stops:
        return False
    place = next((x for x in ed.locations() if x.get("id") == stops[0].get("locationId")), None)
    return place is not None and any(t.get("trackType") == "Staging" for t in place.findall("track"))


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
