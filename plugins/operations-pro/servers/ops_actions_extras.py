"""Actions for train legs, engine move counts and deleting a custom load, and checks added to earlier
actions: pool minimums, route stop times and renaming a load onto one that exists.

Loaded last by ops_actions, after the manual builds and automations group, so its wrappers sit on
top of every earlier action.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ops_data import TYPE_AND_LOAD
from ops_store import Refused
from ops_actions import (ACTIONS, ENGINE_FILE, SETUP_FILE, Editor, action, _indent, _int_field, _model_values,
                         _no_choice, _offered_models)
from ops_actions_automations import _manual_items, _wrap


# ---- Train legs (start) -------------------------------------------------------------

# Train:128-133. The Edit Train build options window offers one locomotive choice per leg, and a
# caboose choice beside it (TrainEditBuildOptionsFrame:797-880).
LEG_LOCOS = {"none": 0, "change": 1, "helpers": 2, "add": 16, "remove": 32}
# Change caboose (Add caboose when the train has none) saves ADD_CABOOSE | REMOVE_CABOOSE.
LEG_CABOOSE = {"keep": 0, "remove": 8, "change": 12}
LEG_ATTRS = ("Options", "Engines", "Road", "Model", "CabooseRoad", "Start", "End")
AUTO_HPT = "Auto HPT"  # Train.AUTO_HPT, JmritOperationsTrainsBundle AutoHPT.


def _route_stops(ed: Editor, train: ET.Element) -> list[ET.Element]:
    link = train.find("route")
    if link is None or not link.get("id"):
        raise Refused(f"Train {train.get('name')} has no route")
    route = ed.route(link.get("id"))
    return sorted(route.findall("location"), key=lambda s: int(s.get("sequenceId", 0)))


def _stop(stops: list[ET.Element], value, what: str) -> ET.Element:
    """A stop by position from 1, by stop id, or by location name when the route visits it once."""
    if isinstance(value, int) and not isinstance(value, bool):
        if not 1 <= value <= len(stops):
            raise Refused(f"{what}: the route has {len(stops)} stops")
        return stops[value - 1]
    text = str(value)
    found = [s for s in stops if s.get("id") == text] or [s for s in stops if s.get("name") == text]
    if len(found) != 1:
        raise Refused(f"{what}: {'several stops' if found else 'no stop'} {text!r} on this train's route; "
                      "give its position from 1")
    return found[0]


def _max_engines(ed: Editor) -> int:
    """Setup.maxEngineSize, 6 unless Operations.xml says otherwise (Setup:213, 2326)."""
    settings = ed.docs[SETUP_FILE].root.find("./operations/settings") if SETUP_FILE in ed.docs else None
    value = settings.get("maxEngines", "6") if settings is not None else "6"
    return int(value) if value.lstrip("-").isdigit() else 6


def _caboose_roads(ed: Editor) -> list[str]:
    """CarManager.getCabooseRoadNames: the roads of cars flagged caboose, which the window lists."""
    return sorted({c.get("roadName") for c in ed.cars() if c.get("caboose") == "true"})


def _accepts(train: ET.Element, option_attr: str, tag: str, item: str, name: str) -> bool:
    option = train.get(option_attr, "All")
    listed = name in [e.get("name") for e in train.findall(f"./{tag}/{item}")]
    return option == "All" or listed == (option == "Include")


def _leg_values(train: ET.Element, n: int) -> dict:
    return {key: train.get(f"leg{n}{key}") for key in LEG_ATTRS}


def _clear_leg(train: ET.Element, n: int) -> None:
    for key in LEG_ATTRS:
        train.attrib.pop(f"leg{n}{key}", None)


@action()
def set_train_leg(ed: Editor, train: str, leg: int, locos: str = "none", caboose: str = "keep",
                  start: str | int | None = None, end: str | int | None = None, engines: str | int | None = None,
                  model: str = "", road: str = "", caboose_road: str = "") -> str:
    """Set a train's leg 2 or leg 3, as the Edit Train build options window does. locos: none, change (a loco
    change at start), add (more locos from start, optionally set out at end), remove, or helpers (from start to end).
    caboose: keep, remove, or change (add one when the train has none). start and end are route stops, by location
    name, stop id or position from 1. engines is a count or Auto HPT, with optional model and road. locos none and
    caboose keep clears the leg. A train moved to another route loses its legs."""
    element = ed.train(train)
    n = _int_field("leg", leg)
    if n not in (2, 3):
        raise Refused("leg must be 2 or 3: the departure is leg 1 and is set with update_train")
    if locos not in LEG_LOCOS:
        raise Refused(f"locos must be one of {', '.join(LEG_LOCOS)}")
    if caboose not in LEG_CABOOSE:
        raise Refused(f"caboose must be one of {', '.join(LEG_CABOOSE)}")
    if locos == "helpers" and caboose != "keep":
        raise Refused("The window has no caboose choice beside helpers; set the caboose change on the other leg")
    options = LEG_LOCOS[locos] | LEG_CABOOSE[caboose]
    given = {k: v for k, v in (("start", start), ("end", end), ("engines", engines), ("model", model),
                                ("road", road), ("caboose_road", caboose_road)) if v not in (None, "")}
    name = element.get("name")
    if not options:
        if given:
            raise Refused(f"With locos none and caboose keep the leg has no options, and JMRI writes nothing else "
                          f"for it (Train:4549), so {', '.join(given)} would be dropped")
        _clear_leg(element, n)
        return f"Cleared leg {n} of {name}."
    stops = _route_stops(ed, element)
    if start in (None, ""):
        raise Refused("A leg needs start, the stop where it begins (the window's SelectLocationEngChange)")
    first = _stop(stops, start, "start")
    last = None
    if end not in (None, ""):
        if locos not in ("add", "helpers"):
            raise Refused("Only add and helpers set locomotives out at an end stop; the builder ignores end "
                          "otherwise (TrainBuilderEngines:378-386)")
        last = _stop(stops, end, "end")
        if stops.index(last) <= stops.index(first):
            raise Refused(f"end ({last.get('name')}) must come after start ({first.get('name')}) on the route")
    elif locos == "helpers":
        raise Refused("Helpers need end, the stop where they leave the train (the window's SelectLocationEndHelper)")
    if first is stops[0]:
        raise Refused("start is the departure; a leg begins at a later stop. Set departure power with update_train")
    notes = []
    model = _no_choice(ed, "engine_model", model)
    road = _no_choice(ed, "engine_road", road)
    if locos == "none":
        for key in ("engines", "model", "road"):
            if key in given:
                raise Refused(f"A caboose-only leg takes no {key}: the builder reads them only for locomotive "
                              "options")
        count = "0"
    else:
        if engines in (None, ""):
            raise Refused(f"locos {locos} needs engines, the number of locomotives")
        count = str(engines).strip()
        offered = [str(i) for i in range(1, _max_engines(ed) + 1)] + [AUTO_HPT]
        if count not in offered:
            raise Refused(f"engines must be one of {', '.join(offered)} (the window's list, from Settings, maximum "
                          "locomotives). 0 would do nothing, and Auto is not offered for a leg")
        if count == AUTO_HPT and n == 3:
            raise Refused("Auto HPT on leg 3 stops the build with an error when no locomotives are found: "
                          "TrainBuilderEngines reads the leg 3 count as a number there. Give a number")
        if model:
            choices = _offered_models(ed)
            if model not in choices:
                raise Refused(f"Unknown locomotive model {model!r}; the window offers {', '.join(choices[:12])}"
                              f"{', ...' if len(choices) > 12 else ''} or blank for any")
            kind = _model_values(ed, model)[0].get("type")
            if kind not in ed.type_entries(element):
                raise Refused(f"Train {name} does not service locomotive model {model} type ({kind or 'none'}) "
                              "(the window's TrainModelService). Add that locomotive type to the train first")
            if not any(e.get("model") == model for e in ed.engines()):
                notes.append(f"Warning: no engine of model {model} is in the roster, so the train will not build.")
        if road:
            roads = sorted({e.get("roadName") for e in ed.engines() if not model or e.get("model") == model})
            if road not in roads:
                raise Refused(f"No locomotive {'of model ' + model + ' ' if model else ''}has road {road!r}; the "
                              f"window offers {', '.join(roads) or 'no roads'}, or blank for any")
    if caboose_road:
        if caboose != "change":
            raise Refused("caboose_road is read only when the leg changes or adds a caboose")
        roads = _caboose_roads(ed)
        if caboose_road not in roads:
            raise Refused(f"No caboose has road {caboose_road!r}; the window offers {', '.join(roads) or 'none'}, "
                          "or blank for any")
        if not _accepts(element, "cabooseRoadOption", "cabooseRoads", "carRoad", caboose_road):
            raise Refused(f"Train {name} does not service caboose road {caboose_road} (the window's "
                          "TrainNotCabooseRoad). Change its caboose roads first")
    requires_caboose = int(element.get("requires", "0") or 0) & 1 == 1
    if caboose == "remove":
        other = int(element.get("leg2Options", "0") or 0)
        has_one = requires_caboose if n == 2 else (
            (requires_caboose or other & 4 == 4) and not (other & 12 == 8))
        if not has_one:
            raise Refused("The train has no caboose to remove at this leg, so the window offers only Add caboose "
                          "(requires caboose on the train, or a caboose added on leg 2)")
    if locos == "remove":
        departs = ed.location(stops[0].get("locationId"))
        if any(t.get("trackType") == "Staging" for t in departs.findall("track")):
            raise Refused("A train departing staging cannot remove locomotives en route; the window turns that "
                          "choice off")
    other_n = 5 - n
    other_start = element.get(f"leg{other_n}Start") if element.get(f"leg{other_n}Options", "0") != "0" else None
    if other_start:
        ids = [s.get("id") for s in stops]
        if other_start in ids:
            two, three = (first.get("id"), other_start) if n == 2 else (other_start, first.get("id"))
            if ids.index(three) <= ids.index(two):
                raise Refused("Leg 3 must start after leg 2 on the route: the builder ends the first leg at leg 2's "
                              "start and the second at leg 3's (TrainBuilderEngines:358-376)")
    _clear_leg(element, n)
    values = {"Options": str(options), "Engines": count, "Road": road, "Model": model,
              "CabooseRoad": caboose_road, "Start": first.get("id")}
    if last is not None:
        values["End"] = last.get("id")
    for key, value in values.items():
        element.set(f"leg{n}{key}", value)
    where = first.get("name") + (f" to {last.get('name')}" if last is not None else "")
    return " ".join([f"Leg {n} of {name}: locos {locos}, caboose {caboose}, at {where}.", *notes])


def _remember_route(ed: Editor, train: str, route: str) -> None:
    element = ed.train(train)
    link = element.find("route")
    ed.__dict__.setdefault("_legs_route", {})[element.get("id")] = link.get("id") if link is not None else None


def _drop_legs(ed: Editor, train: str, route: str) -> str:
    element = ed.train(train)
    link = element.find("route")
    if ed.__dict__.get("_legs_route", {}).get(element.get("id")) == (link.get("id") if link is not None else None):
        return ""
    legs = [n for n in (2, 3) if element.get(f"leg{n}Options") is not None]
    for n in legs:
        _clear_leg(element, n)
    # Train.setRoute keeps the old stops; on the next load their ids are not on the new route, so
    # JMRI keeps the options with no stop. Clearing says so plainly instead.
    return f"Legs cleared: {', '.join(map(str, legs))}; set them again with set_train_leg." if legs else ""


_wrap("set_train_route", before=_remember_route, after=_drop_legs, note="Its legs are cleared too.")


# ---- Train legs (end) ---------------------------------------------------------------


# ---- Engine move counts (start) -----------------------------------------------------

def _engine(ed: Editor, text: str) -> ET.Element:
    key = str(text).replace(" ", "").upper()
    for engine in ed.engines():
        if engine.get("id", "").replace(" ", "").upper() == key:
            return engine
    raise Refused(f"No engine {text!r}")


@action()
def set_engine_moves(ed: Editor, moves: dict[str, int]) -> str:
    """Set locomotive move counts, by engine id or road and number. The builder takes the lowest count first
    (EngineManager.getAvailableTrainList), so a high count rests a locomotive and a low one puts it to work."""
    if ENGINE_FILE not in ed.docs:
        raise Refused("There is no engine file yet")
    for name, value in moves.items():
        # EnginesTableModel:546 takes any whole number, as Integer.parseInt does.
        _engine(ed, name).set("moves", str(_int_field("moves", value, minimum=-2**31)))
    return f"Set moves on {len(moves)} engines."


# ---- Engine move counts (end) -------------------------------------------------------


# ---- Custom loads (start) -----------------------------------------------------------

def _load_holders(ed: Editor, name: str, car_type: str | None) -> list[ET.Element]:
    return [h for h in ed.car_root.findall("./loads/load") if car_type in (None, h.get("type"))
            and name in [e.get("name") for e in h.findall("carLoad")]]


def _load_users(ed: Editor, name: str, types: set[str], plain_too: bool) -> list[str]:
    """Everything that names the load for one of these types. A plain name in a track or train load list
    names it for every type, so it counts only when no other type keeps the load."""
    uses = [f"car {c.get('id')}" for c in ed.cars() if c.get("type") in types
            and name in (c.get("load"), c.get("rweLoad"), c.get("rwlLoad"), c.get("nextLoad"))]
    for schedule in ed.loc_root.findall("./schedules/schedule"):
        if any(i.get("type") in types and name in (i.get("load"), i.get("ship")) for i in schedule.findall("item")):
            uses.append(f"schedule {schedule.get('name')}")
    for kind, holders in (("track", ed.tracks()), ("train", ed.trains())):
        for holder in holders:
            for tag in ("carLoads", "carShipLoads"):
                for entry in holder.findall(f"./{tag}/carLoad"):
                    value = entry.get("name", "")
                    hit = (value == name and plain_too) or (
                        TYPE_AND_LOAD in value and value.split(TYPE_AND_LOAD, 1) in [[t, name] for t in types])
                    if hit:
                        uses.append(f"{kind} {holder.get('name')} load list")
    uses += [f"manual build line {i.get('id')}" for i in _manual_items(ed)
             if i.get("load") == name and i.get("type") in types]
    return list(dict.fromkeys(uses))


@action()
def delete_load(ed: Editor, name: str, car_type: str | None = None) -> str:
    """Delete a custom load, for one car type or every type that has it. Refused while a car, a schedule line, a track
    or train load list or a manual build line names it: change those first."""
    if name in ed.defaults():
        raise Refused("A default load cannot be deleted; JMRI keeps one empty and one load name for every type")
    holders = _load_holders(ed, name, car_type)
    if not holders:
        raise Refused(f"No load {name!r}{' for ' + car_type if car_type else ''}")
    types = {h.get("type") for h in holders}
    kept = [h for h in ed.car_root.findall("./loads/load") if h.get("type") not in types
            and name in [e.get("name") for e in h.findall("carLoad")]]
    uses = _load_users(ed, name, types, plain_too=not kept)
    if uses:
        raise Refused(f"Still used by: {', '.join(uses[:12])}")
    loads = ed.car_root.find("loads")
    for holder in holders:
        for entry in [e for e in holder.findall("carLoad") if e.get("name") == name]:
            holder.remove(entry)
        if not holder.findall("carLoad"):
            loads.remove(holder)  # CarLoads.store writes no element for a type left with the defaults.
    _indent(loads, 1)
    return f"Deleted load {name} from {', '.join(sorted(types))}."


def _rename_load_checked(previous):
    def run(ed: Editor, merge: bool = False, **fields) -> str:
        old, new, car_type = fields.get("old"), fields.get("new"), fields.get("car_type")
        clashes = [h for h in _load_holders(ed, old, car_type) if new in [e.get("name") for e in h.findall("carLoad")]]
        if clashes and not merge:
            raise Refused(f"{', '.join(h.get('type') for h in clashes)} already has load {new!r}. Renaming would merge "
                          "the two into one, as JMRI's Replace does; pass merge true to do that")
        keep = {id(e) for h in clashes for e in h.findall("carLoad") if e.get("name") == new}
        text = previous(ed, **fields)
        if not clashes:
            return text
        for holder in clashes:
            for entry in holder.findall("carLoad"):
                if entry.get("name") == new and id(entry) not in keep:
                    holder.remove(entry)  # CarLoads.replaceName keeps the existing load's settings.
        for parent in list(ed.loc_root.iter()) + list(ed.train_root.iter()):
            for tag in ("carLoads", "carShipLoads"):
                for holder in parent.findall(tag):
                    seen = set()
                    for entry in list(holder.findall("carLoad")):
                        if entry.get("name") in seen:
                            holder.remove(entry)
                        seen.add(entry.get("name"))
        return f"{text} Merged into the existing {new} for {', '.join(h.get('type') for h in clashes)}."
    return run


ACTIONS["rename_load"]["run"] = _rename_load_checked(ACTIONS["rename_load"]["run"])
ACTIONS["rename_load"]["help"] += (" Refused when the new name already exists for that type, unless merge is true: "
                                   "the two then become one, keeping the existing load's settings.")


# ---- Custom loads (end) -------------------------------------------------------------


# ---- Pool minimums (start) ----------------------------------------------------------

def _whole(text: str | None) -> int:
    return int(text) if text and re.fullmatch(r"-?\d+", text) else 0


def pool_excess(ed: Editor) -> dict[tuple[str, str], tuple[int, int]]:
    """Pools whose minimum lengths add up to more than their tracks' lengths: the window's
    "ERROR: Minimum > Length" (PoolTrackFrame:270). Keyed by location id and pool name."""
    out = {}
    for place in ed.locations():
        pools: dict[str, list[ET.Element]] = {}
        for track in place.findall("track"):
            if track.get("pool"):
                pools.setdefault(track.get("pool"), []).append(track)
        for name, tracks in pools.items():
            minimum = sum(_whole(t.get("minLength")) for t in tracks)
            length = sum(_whole(t.get("length")) for t in tracks)
            if minimum > length:
                out[(place.get("id"), name)] = (minimum, length)
    return out


def _check_pool_values(ed: Editor, **fields) -> None:
    pool = fields.get("pool")
    if isinstance(pool, dict):
        for key in ("min_length", "max_length"):
            if key in pool:
                _int_field(f"pool {key}", pool[key])
    ed.__dict__["_pool_excess"] = pool_excess(ed)


def _refuse_pool_excess(ed: Editor, **fields) -> str:
    before = ed.__dict__.get("_pool_excess", {})
    for (place, name), (minimum, length) in pool_excess(ed).items():
        old = before.get((place, name))
        if old is None or minimum - length > old[0] - old[1]:
            raise Refused(f"Pool {name} at {ed.location(place).get('name')}: its minimum lengths add up to {minimum}, "
                          f"more than its tracks' {length} (JMRI's pool window shows ERROR: Minimum > Length). A pool "
                          "lends length only down to each track's minimum, so lower the minimums or lengthen the "
                          "tracks. Add every pool track first and set the minimums last")
    return ""


for _name in ("add_track", "update_track", "delete_track"):
    _wrap(_name, before=_check_pool_values, after=_refuse_pool_excess,
          note="Refused when a pool's minimum lengths would add up to more than its tracks' lengths.")


# ---- Pool minimums (end) ------------------------------------------------------------


# ---- Route stop times (start) -------------------------------------------------------

def _check_times(stops) -> None:
    for stop in stops:
        value = stop.get("depart_time")
        # RouteEditTableModel.getTimeComboBox: blank, or 00:00 to 23:59.
        if value is not None and value != "" and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(value)):
            raise Refused(f"depart_time must be HH:MM from 00:00 to 23:59, or blank for none, not {value!r}")


_wrap("add_route", before=lambda ed, stops, **_: _check_times(stops),
      note="Stops also take random (Off or 10 to 100), comment, wait (minutes added to the travel time there) and "
           "depart_time (HH:MM; it fixes the manifest time at that stop, and later stops follow from it).")
_wrap("update_stop", before=lambda ed, route, stop, **fields: _check_times([fields]),
      note="Fields: direction, max_moves, max_length, pickups, drops, local_moves, random, comment, wait (minutes "
           "added to the travel time) and depart_time (HH:MM, blank for none; it fixes the manifest time there).")

# ---- Route stop times (end) ---------------------------------------------------------
