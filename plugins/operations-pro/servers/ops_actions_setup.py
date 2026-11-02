"""Actions for setup options, train schedule days and manifest formats."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ops_store import Refused
import ops_paperwork as paper
from ops_actions import (Editor, SETUP_FILE, TRAIN_CHILDREN, TRAIN_ROOT_ORDER, action, declare_fields, _active_nodes, _bool, _day,
                         _day_id, _days, _indent, _insert_ordered, _int_field, _next, _place, _set_active,
                         _set_day_trains)


# ---- Setup ----------------------------------------------------------------------------


# Settings Setup.load parses as numbers (Setup:2306-3016). A value it cannot parse is logged as an error
# and replaced by the default on the next save, so only a number JMRI reads is written.
INT_SETTINGS = {"settings": ("trainDirection", "trainLength", "maxEngines", "scale", "switchTime", "travelTime"),
                "fontSize": ("size",), "tab": ("length", "tab2Length", "tab3Length", "manifestTabLength"),
                "buildOptions": ("numberPasses", "dwellTime"), "buildReport": ("fontSize",)}
DOUBLE_SETTINGS = {"settings": ("hpt",)}


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
    if name in INT_SETTINGS.get(group, ()):
        text = str(_int_field(f"{group}.{name}", value))
    elif name in DOUBLE_SETTINGS.get(group, ()):
        try:
            number = float(value)
            if isinstance(value, bool) or number != number or abs(number) == float("inf"):
                raise ValueError
            text = str(number)
        except (TypeError, ValueError):
            raise Refused(f"{group}.{name} must be a number, not {value!r}") from None
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

# TrainScheduleManager.getDaysOfWeek, English bundle: what the Restore button and a save with no days create.
WEEK_DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
ANY_WORDS = ("any", "ANY")
_KEEP = object()  # A field not given, as opposed to one cleared.


def _day_trains(day: ET.Element) -> list[str]:
    return [i for i in day.get("trainIds", "").split(",") if i]


def _day_name(ed: Editor, name: str, current: ET.Element | None = None) -> str:
    text = name.strip()  # TrainsScheduleEditFrame trims and ignores a blank name.
    if not text:
        raise Refused("A train schedule needs a name")
    if text in ANY_WORDS or text.lower() == "any":
        raise Refused("JMRI accepts a schedule named Any, but here the name would mean two things: set_active_day "
                      "'Any' selects the Any setting (cars go every day), while set_line_days 'Any' would name this "
                      "schedule, and JMRI's build report prints 'Active schedule: Any' for both. Name the schedule "
                      "something else")
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
        if not isinstance(value, str):
            raise Refused(f"{name} must be text, not {value!r}")
        return value
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
    if prefix is not None and not isinstance(prefix, str):
        raise Refused(f"prefix must be text, not {prefix!r}")
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
    if text is not None and not isinstance(text, str):
        raise Refused(f"text must be a string, not {text!r}")
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
        problem = paper.pattern_problem(text, defaults[key], group, key)
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
    for label, value in (("railroad_name", railroad_name), ("logo", logo)):
        if value is not None and not isinstance(value, str):
            raise Refused(f"{label} must be text, not {value!r}")
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


declare_fields("set_manifest_options", list(paper.FIELDS))
