"""Manifest and switch list settings: what the Operations files hold and JMRI 5.16 reads.

Checked against JMRI 5.16 (tag v5.16): setup/Setup.java store() and load(),
trains/TrainManifestText.java, TrainSwitchListText.java, TrainManifestHeaderText.java,
trains/TrainManager.java (trainOptions) and trains/Train.java (railRoad, manifestLogo,
showTimes). Both ops_data (reading) and ops_actions (writing) use these tables.
"""
from __future__ import annotations

import re

SETUP, TRAINS = "setup", "trains"

# Setup.store() writes the children of <operations> in this order.
SETUP_ORDER = (
    "railRoad", "setup", "settings", "pickupEngFormat", "dropEngFormat", "pickupCarFormat", "dropCarFormat",
    "localFormat", "missingCarFormat", "switchList", "switchListPickupCarFormat", "switchListDropCarFormat",
    "switchListLocalFormat", "panel", "fontName", "fontSize", "pageOrientation", "printDuplex", "manifestColors",
    "tab", "manifest", "manifestFormat", "headerLines", "manifestLogo", "manifestFileOptions", "buildOptions",
    "buildReport", "router", "logger", "owner", "iconColor", "comments", "display", "vsd", "CATS",
    "dayNameMapping")
# OperationsSetupXml writes these after <operations>.
ROOT_ORDER = ("operations", "manifestHeaderTextStrings", "manifestTextStrings", "switchListTextStrings", "control")
TRAIN_OPTIONS_ORDER = ("trainOptions", "conductorOptions", "rowColorOptions", "manifestCreator", "switchlistCreator")

# Setup.ORIENTATION and Setup.store: the English names JMRI writes (JmritOperationsSetupBundle).
ORIENTATIONS = {"portrait": "Portrait", "landscape": "Landscape", "half_page": "4.25 x 11", "hand_held": "3.25 x 11"}
# Setup.store writes Sides.toString(); load compares with JobAttributes.SidesType names.
DUPLEX = ("one-sided", "two-sided-long-edge", "two-sided-short-edge")
MANIFEST_FORMATS = {"standard": "0", "two_column": "1", "two_column_track": "2"}  # setup/Xml.java:169-171
PAGE_FORMATS = {"normal": "pageNormal", "per_train": "pagePerTrain", "per_visit": "pagePerVisit"}
# ColorUtil.stringToColor names and the java.awt.Color values ColorUtil.colorToColorName maps back to them.
COLORS = {"black": (0, 0, 0), "darkGray": (64, 64, 64), "gray": (128, 128, 128), "lightGray": (192, 192, 192),
          "white": (255, 255, 255), "red": (255, 0, 0), "pink": (255, 175, 175), "orange": (255, 200, 0),
          "yellow": (255, 255, 0), "green": (0, 255, 0), "blue": (0, 0, 255), "magenta": (255, 0, 255),
          "cyan": (0, 255, 255), "brown": (102, 51, 0)}
FONT_SIZES = range(5, 19)  # OperationsPanel.loadFontSizeComboBox offers 5 to 18.

# name: (file, element, attribute, kind, JMRI's default as it writes it). Kinds: bool, int, text, color,
# or a dict / tuple of allowed values. Only settings Setup.load or TrainManager.load reads back.
FIELDS: dict[str, tuple] = {
    # Page and print.
    "font": (SETUP, "fontName", "name", "font", "Monospaced"),
    "font_size": (SETUP, "fontSize", "size", "font_size", "10"),
    "orientation": (SETUP, "pageOrientation", "manifest", ORIENTATIONS, "Portrait"),
    "switch_list_orientation": (SETUP, "pageOrientation", "switchList", ORIENTATIONS, "Portrait"),
    "duplex": (SETUP, "printDuplex", "name", DUPLEX, "one-sided"),
    "format": (SETUP, "manifestFormat", "value", MANIFEST_FORMATS, "0"),
    "logo": (SETUP, "manifestLogo", "name", "path", ""),
    "save_manifests": (SETUP, "manifestFileOptions", "manifestSave", "bool", "false"),
    "header_line_1": (SETUP, "headerLines", "printHeaderLine1", "bool", "true"),
    "header_line_2": (SETUP, "headerLines", "printHeaderLine2", "bool", "true"),
    "header_line_3": (SETUP, "headerLines", "printHeaderLine3", "bool", "true"),
    # Colours.
    "pickup_engine_color": (SETUP, "manifestColors", "pickupEngineColor", "color", "black"),
    "drop_engine_color": (SETUP, "manifestColors", "dropEngineColor", "color", "black"),
    "pickup_color": (SETUP, "manifestColors", "pickupColor", "color", "black"),
    "drop_color": (SETUP, "manifestColors", "dropColor", "color", "black"),
    "local_color": (SETUP, "manifestColors", "localColor", "color", "black"),
    # Tabs.
    "tabs": (SETUP, "tab", "enabled", "bool", "false"),
    "tab_length": (SETUP, "tab", "length", "tab", "12"),
    "tab2_length": (SETUP, "tab", "tab2Length", "tab", "6"),
    "tab3_length": (SETUP, "tab", "tab3Length", "tab", "8"),
    "manifest_tab_length": (SETUP, "tab", "manifestTabLength", "tab", "4"),
    # Manifest content.
    "print_location_comments": (SETUP, "manifest", "printLocComments", "bool", "false"),
    "print_route_comments": (SETUP, "manifest", "printRouteComments", "bool", "false"),
    "print_loads_and_empties": (SETUP, "manifest", "printLoadsEmpties", "bool", "false"),
    "print_train_schedule": (SETUP, "manifest", "printTimetable", "bool", "false"),
    "use_12hr_format": (SETUP, "manifest", "use12hrFormat", "bool", "false"),
    "print_valid": (SETUP, "manifest", "printValid", "bool", "true"),
    "sort_by_track": (SETUP, "manifest", "sortByTrack", "bool", "false"),
    "print_page_header": (SETUP, "manifest", "printPageHeader", "bool", "true"),
    "print_headers": (SETUP, "manifest", "printHeaders", "bool", "false"),
    "no_page_breaks": (SETUP, "manifest", "printNoPageBreaks", "bool", "true"),
    "truncate": (SETUP, "manifest", "truncate", "bool", "false"),
    "use_departure_time": (SETUP, "manifest", "useDepartureTime", "bool", "false"),
    "use_editor": (SETUP, "manifest", "useEditor", "bool", "false"),
    "print_caboose_load": (SETUP, "manifest", "printCabooseLoad", "bool", "false"),
    "print_passenger_load": (SETUP, "manifest", "printPassengerLoad", "bool", "false"),
    "group_car_moves": (SETUP, "manifest", "groupCarMoves", "bool", "false"),
    "print_loco_last": (SETUP, "manifest", "printLocoLast", "bool", "false"),
    "hazardous_message": (SETUP, "manifest", "hazardousMsg", "text", "(Hazardous)"),
    "missing_car_comment": (SETUP, "comments", "misplacedCars", "text",
                            "The following cars are currently misplaced, please contact the dispatcher if found"),
    # Switch lists.
    "switch_list_same_as_manifest": (SETUP, "switchList", "sameAsManifest", "bool", "true"),
    "switch_list_real_time": (SETUP, "switchList", "realTime", "bool", "true"),
    "switch_list_all_trains": (SETUP, "switchList", "allTrains", "bool", "true"),
    "switch_list_page": (SETUP, "switchList", "pageFormat", PAGE_FORMATS, "pageNormal"),
    "switch_list_route_comments": (SETUP, "switchList", "printRouteLocation", "bool", "true"),
    "switch_list_track_summary": (SETUP, "switchList", "trackSummary", "bool", "true"),
    "switch_list_departure_time": (SETUP, "switchList", "useDepartureTime", "bool", "false"),
    # CSV files written at build.
    "csv_manifest": (SETUP, "buildOptions", "generateCsvManifest", "bool", "false"),
    "csv_switch_list": (SETUP, "buildOptions", "generateCsvSwitchList", "bool", "false"),
    # Trains window print options, in the train file.
    "print_preview": (TRAINS, "trainOptions", "printPreview", "bool", "false"),
    "print_build_report": (TRAINS, "trainOptions", "buildReport", "bool", "false"),
    "open_csv_file": (TRAINS, "trainOptions", "openFile", "bool", "false"),
    "run_csv_file": (TRAINS, "trainOptions", "runFile", "bool", "false"),
    # TrainManager.store: the Trains window's build messages box and its table button action.
    "build_messages": (TRAINS, "trainOptions", "buildMessages", "bool", "true"),
    "train_action": (TRAINS, "trainOptions", "trainAction", ("Move", "Reset", "Terminate", "Conductor"), "Move"),
}

# Manifest and switch list creators: TrainCustomCommon.store writes <directory>, <runFile>, <commonFile>, each
# with a name attribute, under manifestCreator or switchlistCreator in the train file's <options>.
# name: (element, {child: (attribute name in the action, JMRI's default)}).
CREATORS = {
    "manifest": ("manifestCreator", {"directory": ("directory", "csvManifests"), "runFile": ("program", "MC4JMRI.xls"),
                                      "commonFile": ("common_file", "CSVFilesFile.txt")}),
    "switch_list": ("switchlistCreator", {"directory": ("directory", "csvSwitchLists"),
                                           "runFile": ("program", "MC4JMRI.xls"),
                                           "commonFile": ("common_file", "CSVFilesFile.txt")}),
}

# Control.store: <control> under the root of Operations.xml. name: (child element, attribute, kind, default).
CONTROL_LENGTHS = {
    "max_len_attribute": "max_len_string_attibute", "max_len_road_number": "max_len_string_road_number",
    "max_len_print_road_number": "max_len_string_print_road_number",
    "max_len_location_name": "max_len_string_location_name", "max_len_track_name": "max_len_string_track_name",
    "max_len_track_length": "max_len_string_track_length_name", "max_len_length": "max_len_string_length_name",
    "max_len_weight": "max_len_string_weight_name", "max_len_built": "max_len_string_built_name",
    "max_len_train_name": "max_len_string_train_name", "max_len_route_name": "max_len_string_route_name",
    "max_len_automation_name": "max_len_string_automation_name"}
CONTROL_LENGTH_DEFAULTS = {"max_len_string_attibute": "12", "max_len_string_road_number": "10",
                           "max_len_string_print_road_number": "6", "max_len_string_location_name": "25",
                           "max_len_string_track_name": "25", "max_len_string_track_length_name": "5",
                           "max_len_string_length_name": "4", "max_len_string_weight_name": "4",
                           "max_len_string_built_name": "5", "max_len_string_train_name": "25",
                           "max_len_string_route_name": "25", "max_len_string_automation_name": "25"}
CONTROL_OTHER = {
    "report_font_size": ("reports", "fontSize", "int", "10"),
    "report_font_name": ("reports", "fontName", "text", ""),
    "excel_wait_time": ("actions", "excelWaitTime", "int", "120"),
    "disable_print_if_custom": ("printOptions", "disablePrintIfCustom", "bool", "false"),
    "speed_hpt": ("speedHpt", "MPH", "int", "36"),
    "show_clones": ("display", "showClones", "bool", "true"),
    "days": ("days", "length", "int", "31"),
}
CONTROL_ORDER = ("maximumStringLengths", "reports", "actions", "printOptions", "speedHpt", "display", "days")

# Message format lines: name -> (element, kind). Setup.store writes prefix and setting; the
# missing car line has no prefix. Engine lines take engine attributes, the rest car attributes.
FORMAT_LINES = {
    "pickup_engine": ("pickupEngFormat", "engine"), "drop_engine": ("dropEngFormat", "engine"),
    "pickup_car": ("pickupCarFormat", "car"), "drop_car": ("dropCarFormat", "car"), "local": ("localFormat", "car"),
    "missing_car": ("missingCarFormat", "car"),
    "switch_list_pickup_car": ("switchListPickupCarFormat", "car"),
    "switch_list_drop_car": ("switchListDropCarFormat", "car"),
    "switch_list_local": ("switchListLocalFormat", "car"),
}
# With Same as Manifest on, Setup.get...SwitchList... returns the manifest value, so a save
# writes these switch list elements from the manifest ones.
SWITCH_LIST_COPIES = {"switch_list_pickup_car": "pickup_car", "switch_list_drop_car": "drop_car",
                      "switch_list_local": "local"}
# The words Setup.store writes for each attribute: Bundle.getMessage(Locale.ROOT, key) of
# Setup.CAR_ATTRIBUTES and ENGINE_ATTRIBUTES. " " is a blank column.
CAR_TOKENS = ("Road", "Number", "Type", "Length", "Weight", "Load", "Load Type", "Hazardous", "Color", "Kernel",
              "Kernel Size", "Owner", "Division", "Track", "Location", "Destination", "Dest&Track", "Final Dest",
              "FD&Track", "Block Order", "Comment", "SetOut Msg", "PickUp Msg", "RWE", "Last Train", "Last Moved",
              "Last Location")
ENGINE_TOKENS = ("Road", "Number", "Type", "Model", "Length", "Weight", "HP", "Consist", "Owner", "Track",
                 "Location", "Destination", "Comment", "DCC Address", "Last Train", "Last Moved", "Last Location")
TAB_TOKENS = ("Tab", "Tab2", "Tab3")  # Offered only while tabs are on (Setup.getCarMessageComboBox).
BLANK = " "
DEFAULT_FORMATS = {
    "pickup_engine": (" [ ] Pick up", "Road,Number, ,Model, , ,Location,Comment,"),
    "drop_engine": (" [ ] Set out", "Road,Number, ,Model, , ,Destination,Comment,"),
    "pickup_car": (" [ ] Pick up", "Road,Number,Type,Length,Color,Load,Hazardous,Location,Comment,PickUp Msg,"),
    "drop_car": (" [ ] Set out", "Road,Number,Type,Length,Color,Load,Hazardous,Destination,Comment,SetOut Msg,"),
    "local": (" [ ] Move", "Road,Number,Type,Length,Color,Load,Hazardous,Location,Destination,Comment,"),
    "missing_car": ("", "Road,Number,Type,Length,Color,Comment,"),
    "switch_list_pickup_car": (" [ ] Pick up",
                               "Road,Number,Type,Length,Color,Load,Hazardous,Location,Comment,PickUp Msg,"),
    "switch_list_drop_car": (" [ ] Set out",
                             "Road,Number,Type,Length,Color,Load,Hazardous,Destination,Comment,SetOut Msg,"),
    "switch_list_local": (" [ ] Move", "Road,Number,Type,Length,Color,Load,Hazardous,Location,Destination,Comment,"),
}

# Text strings: group -> (root element, {tag: English default}). Each class's store() writes a
# tag only when the text differs from the default, so a missing tag means the default.
TEXTS = {
    "manifest": ("manifestTextStrings", {
        "manifestForTrain": "Manifest for train ({0}) {1}",
        "valid": "Valid {0}",
        "scheduledWork": "Scheduled work at {0}",
        "workDepartureTime": "Scheduled work at {0}, departure time {1}",
        "workArrivalTime": "Scheduled work at {0}, arrival time {1}",
        "noScheduledWork": "No work at {0}",
        "noScheduledWorkRouteComment": "{0}, {1}",
        "departTime": ", departure time {0}",
        "trainDepartsCars": "Train departs {0} {1}bound with {2} cars, {3} {4}, {5} tons",
        "trainDepartsLoads": "Train departs {0} {1}bound with {2} loads, {3} empties, {4} {5}, {6} tons",
        "trainTerminates": "Train terminates in {0}",
        "destination": "destination",
        "from": "from",
        "to": "to",
        "dest": "->",
        "Final_Dest": "->",
        "addHelpers": "Add helpers at {0}",
        "removeHelpers": "Remove helpers at {0}",
        "locoChange": "Locomotive change at {0}",
        "cabooseChange": "Caboose change at {0}",
        "locoCabooseChange": "Locomotive and caboose change at {0}",
    }),
    "switch_list": ("switchListTextStrings", {
        "switchListFor": "Switch List for {0}",
        "scheduledWorkTrain": "Scheduled work for train ({0}) {1}",
        "trainVisits": "Train ({0}) visits {1} {2} times",
        "departsAt": "Departs {0} {1}bound at {2}",
        "departsExpectedArrival": "Departs {0} at {1} expected arrival {2}, arrives {3}bound",
        "departedExpected": "Departed {0}, expect to arrive in {1}, arrives {2}bound",
        "visitNumber": "Visit number {0} for train ({1}) expected arrival {2}, arrives {3}bound",
        "visitNumberDeparted": "Visit number {0} for train ({1}) expect to arrive in {2}, arrives {3}bound",
        "visitNumberTerminates": "Visit number {0} for train ({1}) expected arrival {2}, terminates {3}",
        "visitNumberTerminatesDeparted": "Visit number {0} for train ({1}) expect to arrive in {2}, terminates {3}",
        "visitNumberDone": "Visit number {0} for train ({1})",
        "trainDirectionChange": "Train ({0}) direction change, departs {1}bound",
        "noCarPickUps": "No car pick ups for train ({0}) at this location",
        "noCarSetOuts": "No car set outs for train ({0}) at this location",
        "trainDone": "Train ({0}) has serviced this location",
        "trainDepartsCars": "Train departs {0} {1}bound with {2} cars, {3} {4}, {5} tons",
        "trainDepartsLoads": "Train departs {0} {1}bound with {2} loads, {3} empties, {4} {5}, {6} tons",
        "switchListTrack": "Switch List by Track",
        "holdCar": "Hold {0} {1} {2}",
    }),
    "header": ("manifestHeaderTextStrings", {
        "road": "Road", "number": "Number", "engineNumber": "Number", "type": "Type", "model": "Model",
        "hp": "HP", "length": "Length", "weight": "Weight", "load": "Load", "load_type": "Load Type",
        "color": "Color", "track": "Track", "destination": "Destination", "dest_Track": "Dest&Track",
        "Final_Dest": "Final Dest", "fd_Track": "FD&Track", "location": "Location", "consist": "Consist",
        "dcc_addr": "DCC Address", "kernel": "Kernel", "owner": "Owner", "division": "Division", "rwe": "RWE:",
        "Comment": "Comment", "setOut_msg": "SetOut Msg", "pickUp_msg": "PickUp Msg", "hazardous": "Hazardous",
        "last_train": "Last Train", "last_moved": "Last Moved", "last_location": "Last Location",
    }),
}
# Texts printed through MessageFormat.format (TrainManifest, TrainSwitchLists, TrainCommon): every
# one whose default has an argument, and the switch list by track title.
PLACEHOLDER = re.compile(r"\{(\d+)\}")


def is_pattern(group: str, tag: str) -> bool:
    return group != "header" and (bool(PLACEHOLDER.search(TEXTS[group][1][tag])) or tag == "switchListTrack")


def pattern_problem(text: str, default: str) -> str | None:
    """Why MessageFormat would refuse this text or print it differently from what was typed, or None.

    MessageFormat.applyPattern: a single quote starts quoted text, '' is one quote, and an
    unmatched brace throws, which JMRI prints on the manifest as an illegal argument error.
    """
    allowed = {int(n) for n in PLACEHOLDER.findall(default)}
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'":
            if text[index + 1:index + 2] == "'":
                index += 2
                continue
            if text[index:index + 3] in ("'{'", "'}'"):
                index += 3
                continue
            return "a single ' starts quoted text in JMRI's message format; write '' for an apostrophe"
        if char == "{":
            match = re.match(r"\{(\d+)\}", text[index:])
            if not match:
                return "a { must open a numbered argument such as {0}; quote a literal brace as '{'"
            if int(match.group(1)) not in allowed:
                used = ", ".join(f"{{{n}}}" for n in sorted(allowed)) or "none"
                return f"JMRI fills only {used} in this text, so {match.group(0)} would print as typed"
            index += len(match.group(0))
            continue
        index += 1
    return None


def color_name(value: str) -> str:
    """The name or #RRGGBB JMRI will write back (ColorUtil.colorToColorName), or raise ValueError."""
    text = str(value).strip()
    for name in COLORS:
        if text.lower() == name.lower():
            return name
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
        rgb = tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))
        named = next((n for n, v in COLORS.items() if v == rgb), None)
        return named or text.upper()
    raise ValueError(f"colour must be one of {', '.join(COLORS)} or #RRGGBB, not {value!r}")


def tokens(setting: str) -> list[str]:
    """Java String.split(","): trailing empty pieces are dropped."""
    parts = setting.split(",")
    while parts and parts[-1] == "":
        parts.pop()
    return parts
