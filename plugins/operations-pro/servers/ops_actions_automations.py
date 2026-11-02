"""Actions for manual builds and automations. This group wraps actions from earlier groups, so it loads last."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ops_data import ALL, INCLUDE
from ops_store import Refused
from ops_actions import ACTIONS, Editor, action, _bool, _indent, _int_field, _next
from ops_actions_engines import _set_ordered


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
    if comment is not None and not isinstance(comment, str):
        raise Refused("comment must be text")
    if not isinstance(lines, list) or not all(isinstance(x, dict) for x in lines):
        raise Refused(f"lines must be a list of objects such as {{\"type\": ...}}, not {lines!r}")
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
        if not isinstance(raw, dict):
            raise Refused(f"step {number} must be an object such as {{\"do\": ...}}, not {raw!r}")
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
    if automation is not None and not isinstance(automation, str):
        raise Refused(f"An automation must be given by name or id as text, not {automation!r}")
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
