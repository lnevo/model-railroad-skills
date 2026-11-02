"""Actions for schedules, and for staging and interchange chains."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ops_data import ALL, ANY, EXCLUDE, INCLUDE, INTERCHANGE, SPUR, STAGING, TRAINS
from ops_store import Refused
from ops_actions import Editor, SCHEDULE_RANDOM, action, _day_id, _indent, _int_field, _next
from ops_actions_locations import add_track, update_track


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
    # ScheduleItem:347-351 parses count and wait with no catch: a value Java cannot read (a fraction, text,
    # or above 2147483647) stops the whole location file loading, so _int_field holds them to Java's int.
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
    """Add a schedule. Each line: type, and any of road, receive, ship, random, wait, count, setout_day, pickup_day, destination, track.
    count and wait are whole numbers up to 2147483647 (Java's int): JMRI cannot load a file holding more."""
    name = ed.check_name("schedule", name)
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
    new = ed.check_name("schedule", new)
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
