"""Actions for car types, loads, roads and startup scripts."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ops_data import TYPE_AND_LOAD
from ops_store import Refused
from ops_actions import Editor, TRAIN_ROAD_ATTRS, action, _indent, _names, _text


# ---- Names and types ------------------------------------------------------------


@action()
def add_startup_script(ed: Editor, path: str) -> str:
    """Run a script when JMRI loads the trains, as Trains > Tools > Startup Scripts does."""
    path = _text("path", path, blank=False).strip()
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
    name = ed.check_name("type", name)
    if name in ed.car_types():
        raise Refused(f"Type {name!r} already exists")
    if name in ed.loco_types():
        raise Refused(f"{name!r} is a locomotive type. Tracks and trains keep one list of type names, "
                      "so a car type and a loco type with one name could not be told apart")
    ed.register("types", "type", name)
    done = [0, 0, 0]
    if like is not None:
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
    name = ed.check_name("load", name)
    if name in ed.defaults():
        raise Refused(f"{name!r} is a default load name")
    if load_type not in ("Load", "Empty"):
        raise Refused("load_type must be Load or Empty")
    if priority not in (None, "Low", "Medium", "High"):
        raise Refused("priority must be Low, Medium or High")
    types = _names("types", types, empty=False)
    _text("pickup_comment", pickup_comment)
    _text("drop_comment", drop_comment)
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
    new = ed.check_name("type", new)
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
    _text("A load name", old, blank=False)
    if car_type is not None:
        _text("car_type", car_type)
    if old in ed.defaults():
        raise Refused("Rename a default load from JMRI: it is one name shared by every type")
    new = ed.check_name("load", new)
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
            elif value.endswith(f"{TYPE_AND_LOAD}{old}"):
                # A type and load pair. Matched on the end, not split at the first " & ": a type an older
                # file holds may contain " & " itself, and JMRI compares the whole pair (Track:1190).
                kind = value[:-len(f"{TYPE_AND_LOAD}{old}")]
                if match(kind):
                    node.set("name", f"{kind}{TYPE_AND_LOAD}{new}")
                    count += 1
    return f"Renamed load {old} to {new}: {count} places."


@action()
def rename_road(ed: Editor, old: str, new: str) -> str:
    """Rename a road in the road list, track and train filters, train engine and caboose roads, and schedule lines. Refused while a car or engine carries it, since their ids hold the road."""
    if old not in [e.get("name") for e in ed.registered("roads", "road")]:
        raise Refused(f"Unknown road {old!r}")
    new = ed.check_name("road", new)
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
