"""Actions for an engine's division, the control limits in Operations.xml, the manifest and switch list
creator paths, and the Trains window's build messages and table action.

Checked against JMRI 5.16: RollingStock.store (divisionId), setup/Control.java (store and load),
trains/excel/TrainCustomCommon.java (store and load) and trains/TrainManager.java (trainOptions).
Loaded after the extras group, so it can use that group's engine lookup.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import ops_paperwork as paper
from ops_store import Refused
from ops_actions import SETUP_FILE, Editor, action, _bool, _indent, _insert_ordered, _int_field
from ops_actions_engines import ENGINE_ORDER, _division, _set_division_attr
from ops_actions_extras import _engine
from ops_actions_setup import _set_field, _setup_root, _train_option_node


# ---- Engine division ----------------------------------------------------------------

@action()
def set_engine_division(ed: Editor, division: str | None, engines: list[str]) -> str:
    """Give locomotives a home division, or clear it with division null; engines are ids or road and number. JMRI
    stores an engine's division and shows it, but the builder only uses a car's (a locomotive takes no home
    division search), so this is bookkeeping and the Division column of a manifest."""
    if not ed.engines():
        raise Refused("There are no engines")
    identity = _division(ed, division).get("id") if division else None
    chosen = []
    for text in engines:
        engine = _engine(ed, text)
        if engine not in chosen:
            chosen.append(engine)
    before = ENGINE_ORDER[:ENGINE_ORDER.index("divisionId")]
    for engine in chosen:
        _set_division_attr(engine, identity, before)
    return f"{len(chosen)} engines now have home division {division or 'none'}."


# ---- Control limits -----------------------------------------------------------------

def _control(ed: Editor) -> ET.Element:
    """<control> as Control.store writes it: every child, with JMRI's defaults for what the file lacks."""
    root = _setup_root(ed)
    node = root.find("control")
    if node is None:
        node = ET.SubElement(root, "control")
    return node


def _control_child(node: ET.Element, path: str, attr: str, default: str) -> ET.Element:
    parent_tag, _, child_tag = path.partition("/")
    parent = node.find(parent_tag)
    if parent is None:
        parent = ET.Element(parent_tag)
        _insert_ordered(node, parent, paper.CONTROL_ORDER, 2)
        if parent_tag == "maximumStringLengths":
            for tag, value in paper.CONTROL_LENGTH_DEFAULTS.items():
                ET.SubElement(parent, tag, {"length": value})
        elif not child_tag:
            parent.set(attr, default)
    if not child_tag:
        return parent
    child = parent.find(child_tag)
    if child is None:
        child = ET.SubElement(parent, child_tag, {attr: default})
    return child


@action()
def set_control_limits(ed: Editor, **fields) -> str:
    """Set the control values JMRI keeps in Operations.xml under control. Field lengths the edit windows enforce
    (max_len_attribute for types, loads and roads, max_len_road_number, max_len_print_road_number,
    max_len_location_name, max_len_track_name, max_len_track_length, max_len_length, max_len_weight,
    max_len_built, max_len_train_name, max_len_route_name, max_len_automation_name), report_font_size (5 to 18),
    report_font_name, excel_wait_time (seconds), disable_print_if_custom, speed_hpt (the mph used for
    horsepower per ton), show_clones and days (the length of the train schedule cycle). JMRI keeps no maximum
    cars, length or weight on a train or location in a file: a stop's max_length and max_moves (update_stop),
    a track's length (update_track) and Operations.xml trainLength and maxEngines (set_option) are the limits."""
    if not fields:
        raise Refused("Give at least one control value")
    known = {**paper.CONTROL_LENGTHS, **paper.CONTROL_OTHER}
    unknown = sorted(set(fields) - set(known))
    if unknown:
        raise Refused(f"Unknown control values: {', '.join(unknown)}. Known: {', '.join(known)}")
    values = {}
    for name, value in fields.items():
        if name in paper.CONTROL_LENGTHS:
            # Control.load parses these with Integer.parseInt and does not catch a bad one.
            values[name] = str(_int_field(name, value, 1))
            continue
        kind = paper.CONTROL_OTHER[name][2]
        if kind == "bool":
            if not isinstance(value, bool):
                raise Refused(f"{name} is true or false")
            values[name] = _bool(value)
        elif kind == "int":
            minimum = 5 if name == "report_font_size" else 1 if name in ("speed_hpt", "days") else 0
            number = _int_field(name, value, minimum)
            if name == "report_font_size" and number not in paper.FONT_SIZES:
                raise Refused("report_font_size must be 5 to 18, the sizes JMRI's print options offer")
            values[name] = str(number)
        else:
            values[name] = str(value)
    node = _control(ed)
    for name, text in values.items():
        if name in paper.CONTROL_LENGTHS:
            tag = paper.CONTROL_LENGTHS[name]
            _control_child(node, f"maximumStringLengths/{tag}", "length", paper.CONTROL_LENGTH_DEFAULTS[tag]).set(
                "length", text)
        else:
            tag, attr, _, default = paper.CONTROL_OTHER[name]
            _control_child(node, tag, attr, default).set(attr, text)
    _indent(node, 1)
    return f"Set {len(values)} control values: {', '.join(f'{k}={v}' for k, v in values.items())}."


# ---- Manifest and switch list creators ----------------------------------------------

def _creator_name(label: str, value, folder: bool) -> str:
    text = str(value).strip()
    if not text:
        raise Refused(f"{label} cannot be blank")
    bad = ("/" in text or "\\" in text or ":" in text) if not folder else (
        text.startswith(("/", "\\")) or ":" in text or ".." in text.replace("\\", "/").split("/"))
    if bad:
        raise Refused(f"{label} {text!r} must {'stay inside' if folder else 'be a plain file name in'} the "
                      "Operations folder: JMRI joins it to that folder")
    return text


@action()
def set_manifest_creator(ed: Editor, creator: str = "manifest", directory: str | None = None,
                         program: str | None = None, common_file: str | None = None) -> str:
    """Set where JMRI's Manifest Creator (creator manifest) or Switch List Creator (creator switch_list) looks:
    directory (inside the Operations folder, where the CSV files are written; csvManifests or csvSwitchLists),
    program (the spreadsheet or program file JMRI starts there, MC4JMRI.xls) and common_file (the list of CSV
    files to process, CSVFilesFile.txt). Only the paths are stored; the CSV files come at the next build."""
    if creator not in paper.CREATORS:
        raise Refused(f"creator must be one of {', '.join(paper.CREATORS)}")
    given = {"directory": directory, "program": program, "common_file": common_file}
    if all(v is None for v in given.values()):
        raise Refused("Give at least one of directory, program or common_file")
    tag, children = paper.CREATORS[creator]
    checked = {key: _creator_name(key, value, key == "directory") for key, value in given.items() if value is not None}
    node = _train_option_node(ed, tag)
    # TrainCustomCommon.store writes all three, in this order, so a node made here holds all three.
    for child, (key, default) in children.items():
        element = node.find(child)
        if element is None:
            element = ET.Element(child, {"name": default})
            node.append(element)
        if key in checked:
            element.set("name", checked[key])
    node[:] = sorted(node, key=lambda e: list(children).index(e.tag) if e.tag in children else 99)
    _indent(node, 2)
    return f"Set the {creator} creator: " + ", ".join(f"{k}={v}" for k, v in checked.items()) + "."


# ---- Trains window options ----------------------------------------------------------

@action()
def set_train_options(ed: Editor, build_messages: bool | None = None, train_action: str | None = None) -> str:
    """Set the Trains window's Build messages box (build_messages, true shows JMRI's dialogs for a failed build and
    the staging prompts) and the table button's train_action: Move, Reset, Terminate or Conductor."""
    if build_messages is None and train_action is None:
        raise Refused("Give build_messages or train_action")
    done = []
    if build_messages is not None:
        if not isinstance(build_messages, bool):
            raise Refused("build_messages is true or false")
        _set_field(ed, "build_messages", _bool(build_messages))
        done.append(f"build_messages={_bool(build_messages)}")
    if train_action is not None:
        # TrainManager.load keeps its default for any other word.
        if train_action not in paper.FIELDS["train_action"][3]:
            raise Refused(f"train_action must be one of {', '.join(paper.FIELDS['train_action'][3])}")
        _set_field(ed, "train_action", train_action)
        done.append(f"train_action={train_action}")
    return "Set " + ", ".join(done) + "."
