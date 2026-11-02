"""Actions for engines, engine models, consists and divisions."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ops_data import split_name
from ops_store import Doc, Refused
from ops_actions import (DEFAULT_ENGINE_LENGTHS, DEFAULT_ENGINE_TYPES, DEFAULT_MODELS, ENGINE_FILE, Editor,
                         MODEL_FIELDS, action, _bool, _indent, _int_field, _model_values, _next, _place)
from ops_actions_names import _rename_values
from ops_actions_cars import _free


# ---- Engines --------------------------------------------------------------------------
# Checked against JMRI 5.16, rollingstock/engines. JMRI keeps an engine's type, length,
# horsepower, weight and B unit on its model, not on the engine (Engine.java setTypeName,
# setHp, setLength, setWeightTons, setBunit go to EngineModels). The file stores only the
# model names; on load each engine's attributes set its model's, so the last engine read
# wins and the next save writes that value onto every engine of the model. These actions
# keep every engine of a model the same, so nothing changes on a save.

ENGINE_SECTIONS = ("models", "types", "lengths", "newConsists", "engines")
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
