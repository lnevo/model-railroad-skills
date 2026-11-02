"""Actions for cars and kernels."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ops_data import split_name
from ops_store import Refused
from ops_actions import Editor, action, _indent


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
