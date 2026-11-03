"""Read the six JMRI OperationsPro XML files. Standard library only, and read-only.

Field names follow the XML. Derived state that JMRI does not store (used length,
reserved length) is rebuilt here from the car and engine files, as JMRI does on load.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

REQUIRED = ("OperationsLocationRoster.xml", "OperationsRouteRoster.xml",
            "OperationsTrainRoster.xml", "OperationsCarRoster.xml")
OPTIONAL = ("Operations.xml", "OperationsEngineRoster.xml")
# The six files JMRI 5.16 writes when it saves a railroad with nothing in it (a headless save of an
# empty folder), less the "Written by" comment. A folder with none of the four rosters starts from these.
BLANK = Path(__file__).with_name("blank")
# What JMRI keeps beside the files in its operations folder, so such a folder still counts as empty.
OPERATIONS_ITEMS = {"backups", "autoBackups", "buildstatus", "manifests", "switchLists", "csvManifests",
                    "csvSwitchLists", "logger", "jython", ".DS_Store"}


def blank_file(name: str) -> bytes:
    return (BLANK / name).read_bytes()


def operations_folder(directory: str | Path) -> Path:
    """The folder that holds, or will hold, the Operations files. Reads none of them."""
    base = Path(directory).expanduser()
    if (base / "operations").is_dir() and not (base / REQUIRED[0]).exists():
        return base / "operations"
    if _is_profile(base) and not any((base / n).exists() for n in REQUIRED + OPTIONAL):
        return base / "operations"  # A JMRI profile whose Operations were never saved: JMRI writes there.
    return base


def _is_profile(base: Path) -> bool:
    return (base / "profile.properties").is_file() or (base / "profile").is_dir()


def is_fresh(base: Path) -> bool:
    """No roster file at all: a railroad that has never been saved, not a damaged one."""
    return not any((base / n).is_file() for n in REQUIRED)


def _check_fresh(base: Path) -> None:
    """Starting from nothing writes six files here, so the folder must look like an Operations folder."""
    if not base.is_dir():
        if base.name == "operations" and _is_profile(base.parent):
            return
        raise FileNotFoundError(f"{base} is not a folder. Make it, or give the folder holding the Operations files")
    if base.name.lower() == "operations":
        return
    others = sorted(p.name for p in base.iterdir() if p.name not in OPERATIONS_ITEMS and p.name not in OPTIONAL)
    if others:
        raise FileNotFoundError(
            f"{base} has no Operations files and holds other things ({', '.join(others[:5])}). Give the "
            "operations folder of a JMRI profile, or an empty folder, to start a railroad from nothing")

ALL, INCLUDE, EXCLUDE = "All", "Include", "Exclude"
ANY, TRAINS, ROUTES, EXCLUDE_TRAINS, EXCLUDE_ROUTES = (
    "Any", "trains", "routes", "excludeTrains", "excludeRoutes")
SPUR, YARD, INTERCHANGE, STAGING = "Spur", "Yard", "Interchange", "Staging"
SEQUENTIAL, MATCH = 0, 1
EAST, WEST, NORTH, SOUTH = 1, 2, 4, 8
DIRECTIONS = {EAST: "East", WEST: "West", NORTH: "North", SOUTH: "South"}
# Track loadOptions bits.
SWAP_DEFAULT, EMPTY_CUSTOM, GENERATE, GENERATE_ANY_SPUR, EMPTY_DEFAULT = 1, 2, 4, 8, 16
GENERATE_ANY_STAGING, DISABLE_LOAD_CHANGE, QUICK_SERVICE = 32, 64, 128
REQUIRES_CABOOSE, REQUIRES_FRED = 1, 2
CHANGE_ENGINES, ADD_CABOOSE, REMOVE_CABOOSE, REMOVE_ENGINES = 1, 4, 8, 32  # Train leg option bits (Train.java:128-133).
ANY_DAY = "ANY"
TYPE_AND_LOAD = " & "
# JMRI writes these option values from its Bundle, so a non-English file holds other words.
# The comparisons here use the English ones; the loader warns when a value is not known.
OPTION_WORDS = (ALL, INCLUDE, EXCLUDE)
SERVICE_WORDS = (ANY, TRAINS, ROUTES, EXCLUDE_TRAINS, EXCLUDE_ROUTES)
LOAD_TYPES = ("Load", "Empty")
LENGTH_UNITS = ("Feet", "Meters")


def directions(mask: int) -> str:
    names = [name for bit, name in DIRECTIONS.items() if mask & bit]
    return "/".join(names) or "none"


@lru_cache(maxsize=4096)
def split_name(name: str) -> str:
    """JMRI splits only on a hyphen followed by an integer or a left parenthesis."""
    parts = name.split("-")
    while len(parts) > 1 and not parts[-1]:  # Java's split drops trailing empties.
        parts.pop()
    if len(parts) > 1 and not parts[1].startswith("(") and not re.fullmatch(r"[+-]?\d+", parts[1]):
        return name.strip()
    return parts[0].strip()


JAVA_INT_MIN, JAVA_INT_MAX = -2 ** 31, 2 ** 31 - 1
UNCAUGHT_ITEM_NUMBERS = ("sequenceId", "count", "wait", "hits")
_JAVA_INT_TEXT = re.compile(r"[+-]?[0-9]+")


_JAVA_DECODE_TEXT = re.compile(r"[+-]?(?:(0[xX]|#)([0-9a-fA-F]+)|(0[0-7]+)|(0|[1-9][0-9]*))")


def java_decode(value: str | None) -> int | None:
    """What Integer.decode makes of an attribute: decimal, 0x or # hex, or 0 octal, inside Java's int
    range. None where Java throws NumberFormatException."""
    match = _JAVA_DECODE_TEXT.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    number = int(match[2], 16) if match[2] else int(match[3], 8) if match[3] else int(match[4])
    number = -number if value.startswith("-") else number
    return number if JAVA_INT_MIN <= number <= JAVA_INT_MAX else None


def java_int(value: str | None) -> int | None:
    """What Integer.parseInt makes of an attribute: digits with an optional sign, inside Java's int
    range. None where Java throws NumberFormatException."""
    if not isinstance(value, str) or not _JAVA_INT_TEXT.fullmatch(value):
        return None
    number = int(value)
    return number if JAVA_INT_MIN <= number <= JAVA_INT_MAX else None


def _int(value: str | None, default: int = 0) -> int:
    """JMRI's reading of a number attribute: its default where Integer.parseInt fails, as for 12.5,
    true or 3000000000 (Track:2533-2538 and the other loaders catch the error and keep the default)."""
    number = java_int(value)
    return default if number is None else number


def loose_car_match(ids: list[str], text: str) -> list[str]:
    """Car ids that match text when case and spaces are ignored."""
    key = text.replace(" ", "").upper()
    return [i for i in ids if i.replace(" ", "").upper() == key]


def _track_comment(track: ET.Element) -> str:
    """Track.load: the old attribute, then the <comments> form, which wins (Track:2566, 2790-2794)."""
    held = track.find("comments/track")
    return held.get("comment", "") if held is not None else track.get("comment", "")


def _names(parent: ET.Element | None, tag: str, attr: str = "name") -> list[str]:
    if parent is None:
        return []
    return [e.get(attr, "") for e in parent.findall(tag)]


def _accepts(option: str, members: list[str], *values: str) -> bool:
    found = any(v in members for v in values)
    if option == ALL:
        return True
    return found if option == INCLUDE else not found


@dataclass
class ScheduleItem:
    id: str
    sequence: int
    type: str
    road: str = ""
    receive: str = ""
    ship: str = ""
    random: str = ""
    wait: int = 0
    count: int = 1
    setout_day: str = ""
    pickup_day: str = ""
    destination_id: str = ""
    dest_track_id: str = ""


@dataclass
class Schedule:
    id: str
    name: str
    items: list[ScheduleItem] = field(default_factory=list)


@dataclass
class Track:
    id: str
    name: str
    type: str
    location_id: str
    length: int = 0
    moves: int = 0
    dir: int = 15
    types: list[str] = field(default_factory=list)
    loco_types: list[str] = field(default_factory=list)
    road_option: str = ALL
    roads: list[str] = field(default_factory=list)
    load_option: str = ALL
    loads: list[str] = field(default_factory=list)
    raw_ship_option: str = ALL
    ship_loads: list[str] = field(default_factory=list)
    raw_drop_option: str = ANY
    drop_ids: list[str] = field(default_factory=list)
    raw_pickup_option: str = ANY
    pickup_ids: list[str] = field(default_factory=list)
    raw_destination_option: str = ALL
    destination_ids: list[str] = field(default_factory=list)
    raw_only_fd: bool = False
    schedule_id: str = ""
    item_id: str = ""
    schedule_mode: int = SEQUENTIAL
    hold_custom: bool = False
    raw_alternate_id: str = ""
    load_options: int = 0
    pool: str = ""
    pool_min_length: int = 0  # The track's minimum in the pool (Track minLength).
    pool_max_length: int = 0  # Zero means no maximum (Track maxLength).
    comment: str = ""
    ignore_used: int = 0
    factor: int = 100

    is_spur = property(lambda self: self.type == SPUR)
    is_yard = property(lambda self: self.type == YARD)
    is_interchange = property(lambda self: self.type == INTERCHANGE)
    is_staging = property(lambda self: self.type == STAGING)
    split = property(lambda self: split_name(self.name))

    # JMRI ignores these settings on the wrong track type, so the effective
    # value is what the gates must use (Track.getDropOption and friends).
    @property
    def drop_option(self) -> str:
        return ANY if self.is_yard else self.raw_drop_option

    @property
    def pickup_option(self) -> str:
        return ANY if self.is_yard else self.raw_pickup_option

    @property
    def destination_option(self) -> str:
        return self.raw_destination_option if self.is_interchange or self.is_staging else ALL

    @property
    def only_fd(self) -> bool:
        return (self.is_interchange or self.is_staging) and self.raw_only_fd

    @property
    def ship_option(self) -> str:
        return self.raw_ship_option if self.is_staging else ALL

    @property
    def alternate_id(self) -> str:
        return self.raw_alternate_id if self.is_spur else ""

    @property
    def generates_loads(self) -> bool:
        return bool(self.load_options & (GENERATE | GENERATE_ANY_SPUR | GENERATE_ANY_STAGING))

    @property
    def modifies_loads(self) -> bool:
        return bool(self.load_options & (SWAP_DEFAULT | EMPTY_CUSTOM | EMPTY_DEFAULT)) or self.generates_loads

    def accepts_road(self, road: str) -> bool:
        return _accepts(self.road_option, self.roads, road)

    def accepts_load(self, load: str, car_type: str) -> bool:
        return _accepts(self.load_option, self.loads, load, f"{car_type}{TYPE_AND_LOAD}{load}")

    def ships_load(self, load: str, car_type: str) -> bool:
        return _accepts(self.ship_option, self.ship_loads, load, f"{car_type}{TYPE_AND_LOAD}{load}")

    def accepts_destination(self, location_id: str | None) -> bool:
        # The list always holds accepted ids. Exclude only inverts the checkboxes in the GUI.
        return self.destination_option == ALL or location_id is None or location_id in self.destination_ids

    def _service(self, option: str, ids: list[str], train: "Train") -> bool:
        if option == ANY:
            return True
        if option in (TRAINS, EXCLUDE_TRAINS):
            return (train.id in ids) == (option == TRAINS)
        return (train.route_id in ids) == (option == ROUTES)

    def accepts_drop(self, train: "Train") -> bool:
        return self._service(self.drop_option, self.drop_ids, train)

    def accepts_pickup(self, train: "Train") -> bool:
        return self._service(self.pickup_option, self.pickup_ids, train)


@dataclass
class Location:
    id: str
    name: str
    dir: int = 15
    types: list[str] = field(default_factory=list)
    tracks: list[Track] = field(default_factory=list)
    division_id: str = ""

    split = property(lambda self: split_name(self.name))
    is_staging = property(lambda self: any(t.is_staging for t in self.tracks))


@dataclass
class Stop:
    id: str
    name: str
    location_id: str
    direction: int = EAST
    max_length: int = 1000
    max_moves: int = 5
    pickups: bool = True
    drops: bool = True
    local: bool = True
    random: str = "Off"
    wait: int = 0  # Minutes added to the travel time here (RouteLocation:650).
    depart_time: str = ""  # HH:MM that fixes the manifest time here, blank for none (RouteLocation:660).
    split = property(lambda self: split_name(self.name))


@dataclass
class Route:
    id: str
    name: str
    stops: list[Stop] = field(default_factory=list)


@dataclass
class Train:
    id: str
    name: str
    route_id: str = ""
    skips: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    road_option: str = ALL
    roads: list[str] = field(default_factory=list)
    caboose_road_option: str = ALL
    caboose_roads: list[str] = field(default_factory=list)
    load_option: str = ALL
    loads: list[str] = field(default_factory=list)
    owner_option: str = ALL
    owners: list[str] = field(default_factory=list)
    built_start: str = ""
    built_end: str = ""
    requires: int = 0
    caboose_road: str = ""
    engines: str = "0"
    build: bool = True
    built: bool = False
    to_terminal: bool = False
    local_moves: bool = True
    through_cars: bool = True
    allow_return: bool = False
    send_custom_staging: bool = False
    service_all: bool = False  # Service all cars with a final destination (Train.java 3056).
    leg2_options: int = 0
    leg3_options: int = 0
    # Leg 2 and leg 3 as Train.store writes them (Train:4549-4573): only legs with options, stops by id.
    legs: list[dict] = field(default_factory=list)
    # The staging track a built train was sent to, kept until the train is reset (Train:4274-4281, 4385).
    termination_track_id: str = ""
    description: str = ""
    comment: str = ""
    depart_hour: str = "00"
    depart_minute: str = "00"
    engine_road: str = ""
    engine_model: str = ""

    @property
    def changes_caboose(self) -> bool:
        return bool((self.leg2_options | self.leg3_options) & (ADD_CABOOSE | REMOVE_CABOOSE))

    def accepts_road(self, road: str) -> bool:
        return _accepts(self.road_option, self.roads, road)

    def accepts_caboose_road(self, road: str) -> bool:
        return _accepts(self.caboose_road_option, self.caboose_roads, road)

    def accepts_owner(self, owner: str) -> bool:
        return _accepts(self.owner_option, self.owners, owner)

    def accepts_load(self, load: str, car_type: str) -> bool:
        return _accepts(self.load_option, self.loads, load, f"{car_type}{TYPE_AND_LOAD}{load}")

    def accepts_built(self, built: str) -> bool:
        """Both ends are exclusive: start < built < end."""
        if not self.built_start and not self.built_end:
            return True
        start = _int(self.built_start, 0)
        end = _int(self.built_end, 99999)
        return start < built_year(built) < end


def _legs(e: ET.Element) -> list[dict]:
    """Each leg with options, as the train file holds it: Train.load reads these attributes (Train:4099-4150)."""
    out = []
    for n in (2, 3):
        options = _int(e.get(f"leg{n}Options"))
        if options:
            out.append({"leg": n, "options": options, "engines": e.get(f"leg{n}Engines", "0"),
                        "model": e.get(f"leg{n}Model", ""), "road": e.get(f"leg{n}Road", ""),
                        "caboose_road": e.get(f"leg{n}CabooseRoad", ""), "start": e.get(f"leg{n}Start", ""),
                        "end": e.get(f"leg{n}End", "")})
    return out


def built_year(text: str) -> int:
    parts = text.split("-")
    if len(parts) == 2 and parts[1].isdigit():
        year = int(parts[1])
        return year + 1900 if year < 100 else year
    if text.isdigit():
        year = int(text)
        return year + 1900 if year < 100 else year
    return -1900


@dataclass
class Car:
    id: str
    road: str
    number: str
    type: str
    length: str = "0"
    built: str = ""
    owner: str = ""
    load: str = ""
    location_id: str = ""
    track_id: str = ""
    destination_id: str = ""
    dest_track_id: str = ""
    fd_id: str = ""
    fd_track_id: str = ""
    train_id: str = ""
    last_route_id: str = ""
    kernel: str = ""
    lead: bool = False
    out_of_service: bool = False
    unknown: bool = False
    passenger: bool = False
    caboose: bool = False
    fred: bool = False
    wait: int = 0
    pickup_day: str = ""
    schedule_item: str = ""
    division_id: str = ""
    rwe_dest_id: str = ""
    rwe_track_id: str = ""
    rwe_load: str = ""
    rwl_dest_id: str = ""
    rwl_track_id: str = ""
    rwl_load: str = ""
    clone: bool = False  # RollingStock.isClone: counted in the track clone length, not its used length.

    def __str__(self) -> str:
        return f"{self.road} {self.number}"


@dataclass
class Engine:
    id: str
    road: str
    number: str
    length: str = "0"
    location_id: str = ""
    track_id: str = ""
    # JMRI keeps type, length, horsepower, weight and B unit on the model (EngineModels).
    model: str = ""
    type: str = ""
    hp: str = ""
    weight_tons: str = ""
    b_unit: bool = False
    consist: str = ""
    lead: bool = False
    train_id: str = ""
    destination_id: str = ""
    division_id: str = ""
    out_of_service: bool = False
    moves: int = 0  # The builder takes the lowest count first (EngineManager.getAvailableTrainList).
    clone: bool = False  # RollingStock.isClone: counted in the track's clone length, not its used length.


@dataclass
class Load:
    name: str
    load_type: str = "Load"


# ---- Train schedule days and manifest formats ----------------------------------------
@dataclass
class TrainDay:
    """A train schedule. Its trains are the ones Apply turns Build on for; the builder never reads them."""
    id: str
    name: str
    comment: str = ""
    trains: list[str] = field(default_factory=list)  # Train ids.
    active: bool = False


@dataclass
class ManifestSetting:
    name: str
    value: object  # Text, or for a format line {"prefix", "fields"}, or a train's own manifest settings.
    in_file: bool  # False: the file does not hold it, so JMRI uses this default.


@dataclass
class TrainManifest:
    train: str
    railroad_name: str = ""
    logo: str = ""
    show_times: bool = True
# ---- End of train schedule days and manifest formats ---------------------------------


class Railroad:
    """Everything in one operations directory, with lookups by id or name."""

    def __init__(self, directory: str | Path, tolerant: bool = False):
        """An empty folder reads as the empty railroad JMRI writes. A folder that lost some files is
        refused, since writing to it would lose what they held, unless tolerant: then each missing or
        unreadable file reads as empty and is named in broken, for the audit to report."""
        base = operations_folder(directory)
        self.fresh = is_fresh(base)
        self.tolerant = tolerant
        self.broken: dict[str, str] = {}  # File name to what is wrong with it.
        self._blank: set[str] = set()  # Files read from the blank set.
        missing = [name for name in REQUIRED if not (base / name).is_file()]
        if self.fresh:
            _check_fresh(base)
            self._blank = {name for name in REQUIRED + OPTIONAL if not (base / name).is_file()}
        elif missing:
            if not tolerant:
                raise FileNotFoundError(
                    f"{base} is missing {', '.join(missing)}. The other files refer to what it held, so restore "
                    "it from a backup set first: ops_backups lists them, and ops_restore with file puts one back")
            self.broken.update({name: "missing" for name in missing})
            self._blank.update(missing)
        self.directory = base
        self.warnings: list[str] = []
        # (file, subject, attribute=value) for numbers a JMRI loader parses with no catch: JMRI cannot load
        # that file at all, and a later save writes what it did load over it.
        self.unloadable: list[tuple[str, str, str, str]] = []
        if self.fresh:
            self.warnings.append("No Operations files here yet, so this is the empty railroad JMRI 5.16 writes. "
                                 "The first ops_apply writes all six files.")
        self.name = ""
        self.setup: dict[str, dict[str, str]] = {}
        self.locations: dict[str, Location] = {}
        self.tracks: dict[str, Track] = {}
        self.schedules: dict[str, Schedule] = {}
        self.routes: dict[str, Route] = {}
        self.trains: dict[str, Train] = {}
        self.train_schedules: dict[str, str] = {}
        self.active_schedule = ""
        self.cars: dict[str, Car] = {}
        self.engines: dict[str, Engine] = {}
        self.engine_models: list[str] = []
        self.engine_types: list[str] = []
        self.consists: list[str] = []
        self.divisions: dict[str, str] = {}  # Division id to name.
        self.car_types: list[str] = []
        self.loads: dict[str, list[Load]] = {}
        self.default_empty = "E"
        self.default_load = "L"
        for name in OPTIONAL:
            if not (base / name).is_file() and not self.fresh:
                self.warnings.append(f"{name} not found; using JMRI defaults for what it holds")
        self._read_setup()
        self._read_locations()
        self._read_routes()
        self._read_trains()
        self._read_cars()
        self._read_engines()
        self._read_days_and_paperwork()
        self._check_option_words()

    def _check_option_words(self) -> None:
        """Warn about option values JMRI wrote in another language: the gates would misread them."""
        def check(subject: str, setting: str, value: str, known: tuple[str, ...]) -> None:
            if value not in known:
                self.warnings.append(f"{subject}: {setting} is {value!r}, not one of {', '.join(known)}. "
                                     "JMRI writes these words in its own language, so the file may be from a "
                                     "non-English JMRI and this option may read the wrong way round here")
        unit = self.setup.get("settings", {}).get("lengthUnit")
        if unit is not None:
            check("Operations.xml", "lengthUnit", unit, LENGTH_UNITS)
        for t in self.tracks.values():
            name = f"track {t.name}"
            for setting, value in (("carRoadOption", t.road_option), ("carLoadOption", t.load_option),
                                   ("carShipLoadOption", t.raw_ship_option),
                                   ("trackDestinationOption", t.raw_destination_option)):
                check(name, setting, value, OPTION_WORDS)
            for setting, value in (("dropOption", t.raw_drop_option), ("pickupOption", t.raw_pickup_option)):
                check(name, setting, value, SERVICE_WORDS)
        for train in self.trains.values():
            name = f"train {train.name}"
            for setting, value in (("carRoadOption", train.road_option), ("cabooseRoadOption", train.caboose_road_option),
                                   ("carLoadOption", train.load_option), ("carOwnerOption", train.owner_option)):
                check(name, setting, value, OPTION_WORDS)
        for kind, loads in self.loads.items():
            for load in loads:
                check(f"load {kind} {load.name}", "loadType", load.load_type, LOAD_TYPES)

    def _root(self, name: str) -> ET.Element | None:
        if name in self._blank:
            return ET.fromstring(blank_file(name))
        path = self.directory / name
        if not path.is_file():
            return None
        try:
            return ET.parse(path).getroot()
        except ET.ParseError as exc:
            if not self.tolerant:
                raise ET.ParseError(f"{path}: {exc}. Restore it from a backup set: ops_backups lists them, "
                                    "and ops_restore with file puts one back") from exc
            self.broken[name] = f"unreadable ({exc})"
            return ET.fromstring(blank_file(name))

    def _read_setup(self) -> None:
        root = self._root("Operations.xml")
        operations = root.find("operations") if root is not None else None
        if operations is None:
            return
        road = operations.find("railRoad")
        self.name = road.get("name", "") if road is not None else ""
        self.setup = {child.tag: dict(child.attrib) for child in operations}

    def option(self, group: str, name: str, default: bool = False) -> bool:
        value = self.setup.get(group, {}).get(name)
        return default if value is None else value == "true"

    @property
    def coupler(self) -> int:
        unit = self.setup.get("settings", {}).get("lengthUnit", "Feet")
        return 4 if unit == "Feet" else 1

    def _read_locations(self) -> None:
        root = self._root(REQUIRED[0])
        for element in root.findall("./divisions/division"):
            self.divisions[element.get("id", "")] = element.get("name", "")
        for element in root.findall("./locations/location"):
            location = Location(
                id=element.get("id", ""), name=element.get("name", ""),
                dir=_int(element.get("dir"), 15),
                types=_names(element.find("types"), "carType"),
                division_id=element.get("divisionId", ""))
            for child in element.findall("track"):
                track = self._track(child, location.id)
                location.tracks.append(track)
                self.tracks[track.id] = track
            self.locations[location.id] = location
        for element in root.findall("./schedules/schedule"):
            schedule = Schedule(element.get("id", ""), element.get("name", ""))
            for item in element.findall("item"):
                for attr in UNCAUGHT_ITEM_NUMBERS:  # ScheduleItem:335-375: a bad one stops the whole file loading.
                    value = item.get(attr)
                    if value is not None and java_int(value) is None:
                        self.unloadable.append((REQUIRED[0], f"schedule {schedule.name} line {item.get('id', '')}",
                                                f"{attr}={value!r}", "schedules"))
                schedule.items.append(ScheduleItem(
                    id=item.get("id", ""), sequence=_int(item.get("sequenceId")),
                    type=item.get("type", ""), road=item.get("road", ""),
                    receive=item.get("load", ""), ship=item.get("ship", ""),
                    random=item.get("random", ""), wait=_int(item.get("wait")),
                    count=_int(item.get("count"), 1),
                    setout_day=item.get("trainScheduleId", ""),
                    pickup_day=item.get("pickupTrainScheduleId", ""),
                    destination_id=item.get("destinationId", ""),
                    dest_track_id=item.get("destTrackId", "")))
            schedule.items.sort(key=lambda i: i.sequence)
            self.schedules[schedule.id] = schedule

    @staticmethod
    def _track(e: ET.Element, location_id: str) -> Track:
        kind = e.get("trackType") or e.get("locType") or SPUR
        return Track(
            id=e.get("id", ""), name=e.get("name", ""), location_id=location_id,
            type=SPUR if kind == "Siding" else kind,
            length=_int(e.get("length")), moves=_int(e.get("moves")), dir=_int(e.get("dir"), 15),
            types=_names(e.find("types"), "carType"), loco_types=_names(e.find("types"), "locoType"),
            road_option=e.get("carRoadOption", e.get("carRoadOperation", ALL)),
            roads=_names(e.find("carRoads"), "carRoad"),
            load_option=e.get("carLoadOption", ALL), loads=_names(e.find("carLoads"), "carLoad"),
            raw_ship_option=e.get("carShipLoadOption", ALL),
            ship_loads=_names(e.find("carShipLoads"), "carLoad"),
            raw_drop_option=e.get("dropOption", ANY),
            drop_ids=_names(e.find("dropIds"), "dropId", "id"),
            raw_pickup_option=e.get("pickupOption", ANY),
            pickup_ids=_names(e.find("pickupIds"), "pickupId", "id"),
            raw_destination_option=e.get("trackDestinationOption", ALL),
            destination_ids=_names(e.find("destinations"), "destination", "id"),
            raw_only_fd=e.get("onlyCarWithFD") == "true",
            pool_min_length=_int(e.get("minLength")), pool_max_length=_int(e.get("maxLength")),
            comment=_track_comment(e),
            schedule_id=e.get("scheduleId", ""), item_id=e.get("itemId", ""),
            schedule_mode=_int(e.get("scheduleMode"), SEQUENTIAL),
            hold_custom=e.get("holdCustomLoads") == "true",
            raw_alternate_id=e.get("alternative", ""),
            load_options=_int(e.get("loadOptions")), pool=e.get("pool", ""),
            ignore_used=_int(e.get("ignoreUsedPercentage")), factor=_int(e.get("factor"), 100))

    def _read_routes(self) -> None:
        for element in self._root(REQUIRED[1]).findall("./routes/route"):
            route = Route(element.get("id", ""), element.get("name", ""))
            ordered = sorted(element.findall("location"), key=lambda e: _int(e.get("sequenceId")))
            for stop in ordered:
                route.stops.append(Stop(
                    id=stop.get("id", ""), name=stop.get("name", ""),
                    location_id=stop.get("locationId", ""),
                    direction=_int(stop.get("trainDirection"), EAST),
                    max_length=_int(stop.get("maxTrainLength"), 1000),
                    max_moves=_int(stop.get("maxCarMoves"), 5),
                    pickups=stop.get("pickups", "yes") == "yes",
                    drops=stop.get("drops", "yes") == "yes",
                    local=stop.get("localMoves", "yes") == "yes",
                    random=stop.get("randomControl", "Off"), wait=_int(stop.get("wait")),
                    depart_time=stop.get("departTime", "")))
            self.routes[route.id] = route

    def _check_train_file_numbers(self, root: ET.Element) -> None:
        """TrainManagerXml:106-111 reads trains, manual builds, train schedules, then automations, and neither
        TrainManualBuildItem:312, 339 nor AutomationItem:432 catches a bad number."""
        def check(item: ET.Element, attrs: tuple[str, ...], subject: str, lost: str) -> None:
            for attr in attrs:
                value = item.get(attr)
                if value is not None and java_int(value) is None:
                    self.unloadable.append((REQUIRED[2], subject, f"{attr}={value!r}", lost))

        for build in root.findall("./manualBuilds/manualBuild"):
            for item in build.findall("mbItem"):
                check(item, ("sequenceId", "count"), f"manual build {build.get('id', '')} line {item.get('id', '')}",
                      "manual builds, train schedules and automations")
        for automation in root.findall("./automations/automation"):
            for item in automation.findall("item"):
                subject = f"automation {automation.get('name', '')} step {item.get('id', '')}"
                check(item, ("sequenceId",), subject, "automations")
                code = item.get("actionCode")  # AutomationItem:435 reads this with Integer.decode.
                if code is not None and java_decode(code) is None:
                    self.unloadable.append((REQUIRED[2], subject, f"actionCode={code!r}", "automations"))

    def _read_trains(self) -> None:
        root = self._root(REQUIRED[2])
        self._check_train_file_numbers(root)
        for e in root.findall("./trains/train"):
            route = e.find("route")
            skips = route.find("skips") if route is not None else None
            train = Train(
                id=e.get("id", ""), name=e.get("name", ""),
                route_id=route.get("id", "") if route is not None else e.get("routeId", ""),
                skips=_names(skips, "location", "id"),
                types=_names(e.find("types"), "carType"),
                road_option=e.get("carRoadOption", e.get("carRoadOperation", ALL)),
                roads=_names(e.find("carRoads"), "carRoad"),
                caboose_road_option=e.get("cabooseRoadOption", ALL),
                caboose_roads=_names(e.find("cabooseRoads"), "carRoad"),
                load_option=e.get("carLoadOption", ALL), loads=_names(e.find("carLoads"), "carLoad"),
                owner_option=e.get("carOwnerOption", ALL), owners=_names(e.find("carOwners"), "carOwner"),
                built_start=e.get("builtStartYear", ""), built_end=e.get("builtEndYear", ""),
                requires=_int(e.get("requires")), caboose_road=e.get("cabooseRoad", ""),
                engines=e.get("numberEngines", "0"), build=e.get("build", "true") == "true",
                built=e.get("built") == "true", to_terminal=e.get("toTerminal") == "true",
                local_moves=e.get("allowLocalMoves", "true") == "true",
                through_cars=e.get("allowThroughCars", "true") == "true",
                allow_return=e.get("allowReturn") == "true",
                send_custom_staging=e.get("sendCustomStaging") == "true",
                service_all=e.get("serviceAll") == "true",
                leg2_options=_int(e.get("leg2Options")), leg3_options=_int(e.get("leg3Options")),
                legs=_legs(e),
                termination_track_id=e.get("terminationTrack", ""),
                description=e.get("description", ""), comment=e.get("comment", ""),
                depart_hour=e.get("departHour", "00"), depart_minute=e.get("departMinute", "00"),
                engine_road=e.get("engineRoad", ""), engine_model=e.get("engineModel", ""))
            self.trains[train.id] = train
        for schedule in root.findall("./schedules/schedule"):
            self.train_schedules[schedule.get("id", "")] = schedule.get("name", "")
        # TrainManager.load reads the old place under options first (TrainManager:1320), then
        # TrainScheduleManager.load reads the root element JMRI writes now, so the root one wins.
        self.active_schedule = ""
        for active in (root.find("./options/trainScheduleOptions"), root.find("trainScheduleOptions")):
            if active is not None and active.get("activeId") is not None:
                self.active_schedule = active.get("activeId")

    def _read_cars(self) -> None:
        root = self._root(REQUIRED[3])
        self.car_types = _names(root.find("types"), "type")
        defaults = root.find("./loads/defaults")
        if defaults is not None:
            self.default_empty = defaults.get("empty", self.default_empty)
            self.default_load = defaults.get("load", self.default_load)
        for element in root.findall("./loads/load"):
            self.loads[element.get("type", "")] = [
                Load(e.get("name", ""), e.get("loadType", "Load")) for e in element.findall("carLoad")]
        for e in root.findall("./cars/car"):
            car = Car(
                id=e.get("id", ""), road=e.get("roadName", ""), number=e.get("roadNumber", ""),
                type=e.get("type", ""), length=e.get("length", "0"), built=e.get("built", ""),
                owner=e.get("owner", ""), load=e.get("load", self.default_empty),
                location_id=e.get("locationId", ""), track_id=e.get("secLocationId", ""),
                destination_id=e.get("destinationId", ""), dest_track_id=e.get("secDestinationId", ""),
                fd_id=e.get("nextDestId", ""), fd_track_id=e.get("nextDestTrackId", ""),
                train_id=e.get("trainId", ""), last_route_id=e.get("lastRouteId", ""),
                kernel=e.get("kernel", ""), lead=e.get("leadKernel") == "true",
                out_of_service=e.get("outOfService") == "true", unknown=e.get("locUnknown") == "true",
                passenger=e.get("passenger") == "true", caboose=e.get("caboose") == "true",
                fred=e.get("fred") == "true", wait=_int(e.get("wait")), pickup_day=e.get("pickupId", ""),
                schedule_item=e.get("scheduleId", ""), division_id=e.get("divisionId", ""),
                rwe_dest_id=e.get("rweDestId", ""), rwe_track_id=e.get("rweDestTrackId", ""),
                rwe_load=e.get("rweLoad", ""), rwl_dest_id=e.get("rwlDestId", ""),
                rwl_track_id=e.get("rwlDestTrackId", ""), rwl_load=e.get("rwlLoad", ""),
                clone=e.get("clone") == "true" or "-(Clone)" in e.get("roadNumber", ""))
            self.cars[car.id] = car

    def _read_engines(self) -> None:
        root = self._root("OperationsEngineRoster.xml")
        if root is None:
            return
        self.engine_models = _names(root.find("models"), "model")
        self.engine_types = _names(root.find("types"), "type")
        self.consists = _names(root.find("newConsists"), "consist")
        for e in root.findall("./engines/engine"):
            engine = Engine(e.get("id", ""), e.get("roadName", ""), e.get("roadNumber", ""),
                            e.get("length", "0"), e.get("locationId", ""), e.get("secLocationId", ""),
                            model=e.get("model", ""), type=e.get("type", ""), hp=e.get("hp", ""),
                            weight_tons=e.get("weightTons", ""), b_unit=e.get("bUnit") == "true",
                            consist=e.get("consist", ""), lead=e.get("leadConsist") == "true",
                            train_id=e.get("trainId", ""), destination_id=e.get("destinationId", ""),
                            division_id=e.get("divisionId", ""), out_of_service=e.get("outOfService") == "true",
                            moves=_int(e.get("moves")),
                            clone=e.get("clone") == "true" or "-(Clone)" in e.get("roadNumber", ""))
            self.engines[engine.id] = engine

    # ---- Train schedule days and manifest formats ----------------------------------
    def _read_days_and_paperwork(self) -> None:
        """Train schedules with their trains (TrainSchedule:107-125), and the manifest and switch list
        settings JMRI reads back (ops_paperwork), each with JMRI's default where the file has none."""
        import ops_paperwork as paper
        self.days: dict[str, TrainDay] = {}
        trains = self._root(REQUIRED[2])
        for e in trains.findall("./schedules/schedule"):
            ids = [i for i in e.get("trainIds", "").split(",") if i]
            self.days[e.get("id", "")] = TrainDay(e.get("id", ""), e.get("name", ""), e.get("comment", ""), ids,
                                                  e.get("id", "") == self.active_schedule)
        setup = self._root("Operations.xml")
        operations = setup.find("operations") if setup is not None else None
        options = trains.find("options")
        self.manifest: dict[str, ManifestSetting] = {}
        for name, (where, tag, attr, _, default) in paper.FIELDS.items():
            parent = operations if where == paper.SETUP else options
            node = parent.find(tag) if parent is not None else None
            value = node.get(attr) if node is not None else None
            if value is None and node is not None and attr in ("pickupEngineColor", "dropEngineColor"):
                # Setup.load: engine colours older than 5.11.3 take the car colour.
                value = node.get(attr.replace("Engine", ""))
            self.manifest[name] = ManifestSetting(name, default if value is None else value, value is not None)
        for name, (tag, _) in paper.FORMAT_LINES.items():
            node = operations.find(tag) if operations is not None else None
            prefix, setting = paper.DEFAULT_FORMATS[name]
            if node is not None:
                prefix, setting = node.get("prefix", prefix), node.get("setting", setting)
            self.manifest[name] = ManifestSetting(name, {"prefix": prefix, "fields": paper.tokens(setting)},
                                                  node is not None)
        for which, (tag, children) in paper.CREATORS.items():
            node = options.find(tag) if options is not None else None
            values, held = {}, False
            for child, (key, default) in children.items():
                found = node.find(child) if node is not None else None
                held = held or found is not None
                values[key] = found.get("name", default) if found is not None else default
            self.manifest[f"creator {which}"] = ManifestSetting(f"creator {which}", values, held)
        control = setup.find("control") if setup is not None else None
        for key, tag in paper.CONTROL_LENGTHS.items():
            found = control.find(f"maximumStringLengths/{tag}") if control is not None else None
            value = found.get("length") if found is not None else None
            self.manifest[f"control {key}"] = ManifestSetting(
                f"control {key}", paper.CONTROL_LENGTH_DEFAULTS[tag] if value is None else value, value is not None)
        for key, (tag, attr, _, default) in paper.CONTROL_OTHER.items():
            found = control.find(tag) if control is not None else None
            value = found.get(attr) if found is not None else None
            self.manifest[f"control {key}"] = ManifestSetting(f"control {key}", default if value is None else value,
                                                              value is not None)
        self.manifest_texts: dict[str, dict[str, str]] = {}
        for group, (holder, defaults) in paper.TEXTS.items():
            node = setup.find(holder) if setup is not None else None
            texts = self.manifest_texts[group] = {}
            for tag, text in defaults.items():
                stored = node.find(tag) if node is not None else None
                texts[tag] = stored.get("text", text) if stored is not None else text
                self.manifest[f"text {group} {tag}"] = ManifestSetting(f"text {group} {tag}", texts[tag],
                                                                       stored is not None)
        self.train_manifests: dict[str, TrainManifest] = {}
        for e in trains.findall("./trains/train"):
            road, logo = e.find("railRoad"), e.find("manifestLogo")
            entry = self.train_manifests[e.get("id", "")] = TrainManifest(
                e.get("name", ""), road.get("name", "") if road is not None else "",
                logo.get("name", "") if logo is not None else "", e.get("showTimes", "true") == "true")
            self.manifest[f"train {entry.train}"] = ManifestSetting(
                f"train {entry.train}", {"railroad_name": entry.railroad_name, "logo": entry.logo,
                                         "show_times": entry.show_times}, True)
    # ---- End of train schedule days and manifest formats ---------------------------

    # Lookups. Each accepts an id or a name, ignoring case and spaces in car ids.
    def find_car(self, text: str) -> Car:
        """By exact id, as JMRI keys cars, or exactly as JMRI shows one ("BVR 1001"). Case counts; a near
        miss is named in the error."""
        if text in self.cars:
            return self.cars[text]
        shown = next((c for c in self.cars.values() if f"{c.road} {c.number}" == text), None)
        if shown is not None:  # As JMRI shows a car: road, a space, number.
            return shown
        loose = loose_car_match(list(self.cars), text)
        raise KeyError(f"No car {text!r}" + (f". Did you mean {', '.join(loose[:4])}? Give the id exactly: road "
                                            "then number, case and spaces as JMRI holds them" if loose else ""))

    def find_location(self, text: str) -> Location:
        for location in self.locations.values():
            if text in (location.id, location.name):
                return location
        raise KeyError(f"No location {text!r}")

    def find_track(self, text: str, location: Location | None = None) -> Track:
        pool = location.tracks if location else self.tracks.values()
        matches = [t for t in pool if text in (t.id, t.name)]
        if len(matches) == 1:
            return matches[0]
        where = f" at {location.name}" if location else ""
        raise KeyError(f"{'Several tracks' if matches else 'No track'} {text!r}{where}")

    def find_train(self, text: str) -> Train:
        for train in self.trains.values():
            if text in (train.id, train.name):
                return train
        raise KeyError(f"No train {text!r}")

    # Derived state.
    def stops(self, train: Train) -> list[Stop]:
        route = self.routes.get(train.route_id)
        return route.stops if route else []

    def is_default_load(self, load: str) -> bool:
        return load in (self.default_empty, self.default_load)

    def custom_loads(self, car_type: str) -> list[Load]:
        return [x for x in self.loads.get(car_type, []) if not self.is_default_load(x.name)]

    def car_length(self, car: Car) -> int | None:
        """Length with couplers, or None if the stored length is not a number."""
        try:
            return int(car.length) + self.coupler
        except ValueError:
            return None

    def is_kernel_lead(self, car: Car) -> bool:
        """Kernel.isLead after a load: the last member read with leadKernel, else the first member read
        (Car:1179-1180, RollingStockGroup.add:40-42)."""
        if not car.kernel:
            return False
        members = [c for c in self.cars.values() if c.kernel == car.kernel]
        if not any(m.id == car.id for m in members):
            return car.lead  # A copy outside the roster keeps its own flag.
        flagged = [m for m in members if m.lead]
        lead = flagged[-1] if flagged else members[0]
        return lead.id == car.id

    def kernel_length(self, car: Car) -> int:
        """A kernel lead counts for the whole kernel; other cars count alone."""
        members = [car]
        if car.kernel and self.is_kernel_lead(car):
            members = [c for c in self.cars.values() if c.kernel == car.kernel]
        return sum(self.car_length(c) or 0 for c in members)

    def rolling_stock_on(self, track: Track) -> tuple[list[Car], list[Engine]]:
        return ([c for c in self.cars.values() if c.track_id == track.id],
                [e for e in self.engines.values() if e.track_id == track.id])

    def used_length(self, track: Track, clones: bool = False) -> int:
        """Track.getUsedLength: rolling stock on the track, clones left out (Track.addRS, TR:749-760).
        clones=True gives getUsedCloneLength alone; the sum is getTotalUsedLength."""
        cars, engines = self.rolling_stock_on(track)
        total = sum(self.car_length(c) or 0 for c in cars if c.clone == clones)
        return total + sum(int(e.length or 0) + self.coupler for e in engines if e.length.isdigit() and e.clone == clones)

    def reserved_length(self, track: Track) -> int:
        return sum(self.car_length(c) or 0 for c in self.cars.values()
                   if c.dest_track_id == track.id and c.track_id != track.id)

    def at(self, car: Car, location_id: str, track_id: str = "") -> Car:
        """A copy of a car placed elsewhere, for what-if routing."""
        return replace(car, location_id=location_id, track_id=track_id, destination_id="",
                       dest_track_id="", kernel="", lead=False)


def load(directory: str | Path, tolerant: bool = False) -> Railroad:
    return Railroad(directory, tolerant)


# ---- Manual builds and automations (start) ------------------------------------------
# Both live in the train file (TrainManagerXml:70-73). Checked against JMRI 5.16:
# trains/manualtrainbuilder and automation. Plain dictionaries, read straight from the file.

# Automation step kinds: (JMRI code, English name). Codes are ActionCodes.java: an upper byte
# for the action plus flag bits that say which fields the step keeps on a save.
STEP_TRAIN, STEP_STOP, STEP_OK, STEP_FAIL, STEP_AUTOMATION, STEP_GOTO, STEP_OTHER = 1, 2, 4, 8, 16, 32, 64
_T, _TR, _TF = STEP_TRAIN | STEP_OK | STEP_FAIL, STEP_TRAIN | STEP_STOP | STEP_OK | STEP_FAIL, STEP_OK | STEP_FAIL
STEP_KINDS: dict[str, tuple[int, str]] = {
    "nothing": (0x0000 | STEP_OK, "Do Nothing"),
    "build_train": (0x0100 | _T, "Build Train"),
    "build_train_if_selected": (0x0200 | _T, "Build Train if Selected"),
    "print_train_manifest": (0x0300 | _T, "Print Train Manifest"),
    "print_train_manifest_if_selected": (0x0400 | _T, "Print Train Manifest if Selected"),
    "move_train": (0x0500 | _TR, "Move Train"),
    "terminate_train": (0x0600 | _T, "Terminate Train"),
    "wait_for_train": (0x0700 | _TR, "Wait for Train"),
    "reset_train": (0x0800 | _T, "Reset Train"),
    "run_train": (0x0900 | _T, "Run Excel for Train"),
    "select_train": (0x0A00 | _T, "Select Train (Build)"),
    "deselect_train": (0x0B00 | _T, "Deselect Train (Build)"),
    "wait_for_train_to_terminate": (0x0C00 | _T, "Wait for Train to Terminate"),
    "is_train_en_route": (0x0D00 | _TR, "Is Train En-Route?"),
    "print_train_build_report": (0x0E00 | _T, "Print Train Build Report"),
    "update_switch_list": (0x1000 | STEP_OK, "Update Switch List"),
    "print_switch_list": (0x1100 | STEP_OK, "Print Switch List"),
    "wait_for_switch_list": (0x1200 | STEP_OK, "Wait for Switch List Change"),
    "run_switch_list_changes": (0x1300 | _TF, "Run Excel Switch List Changes"),
    "run_switch_list": (0x1400 | _TF, "Run Excel Switch List"),
    "print_switch_list_changes": (0x1500 | STEP_OK, "Print Switch List Changes"),
    "generate_switch_list_changes": (0x1600 | _TF, "Generate Switch List Changes"),
    "generate_switch_list": (0x1700 | _TF, "Generate Switch List"),
    "reset_switch_lists": (0x1800 | STEP_OK, "Reset Switch Lists"),
    "activate_train_schedule": (0x2000 | STEP_OK | STEP_OTHER, "Activate Train Schedule"),
    "apply_train_schedule": (0x2100 | _TF, "Apply Train Schedule"),
    "run_automation": (0x3100 | _TF | STEP_AUTOMATION, "Run Automation"),
    "stop_automation": (0x3200 | _TF | STEP_AUTOMATION, "Stop Automation"),
    "resume_automation": (0x3300 | _TF | STEP_AUTOMATION, "Resume Automation"),
    "wait_for_automation": (0x3400 | _TF | STEP_AUTOMATION, "Wait for Automation"),
    "counter": (0x4000 | STEP_OK, "Counter"),
    "down_counter": (0x4100 | STEP_OK, "Down Counter"),
    "message_yes_no": (0x4200 | STEP_TRAIN | STEP_STOP | STEP_OK, "Message Yes or No"),
    "goto": (0x5000 | _TF | STEP_GOTO, "GOTO"),
    "goto_if_success": (0x5100 | _TF | STEP_GOTO, "If Success GOTO"),
    "goto_if_failure": (0x5200 | _TF | STEP_GOTO, "If Failure GOTO"),
    "halt": (0xFF00 | STEP_OK, "Halt"),
}
STEP_BY_CODE = {code: kind for kind, (code, _) in STEP_KINDS.items()}
ACTIVATE_DAY = STEP_KINDS["activate_train_schedule"][0]


def step_code(text: str | None) -> int:
    """AutomationItem:435 reads the code with Integer.decode; an unknown code becomes Do Nothing."""
    code = java_decode(text or "0")
    return code if code in STEP_BY_CODE else STEP_KINDS["nothing"][0]


def _train_root(directory: str | Path) -> ET.Element | None:
    path = Path(directory) / REQUIRED[2]
    return ET.parse(path).getroot() if path.is_file() else None


def read_manual_builds(directory: str | Path) -> list[dict]:
    """Each train's manual build lines, in sequence order, as TrainManualBuild reads them."""
    root = _train_root(directory)
    if root is None:
        return []
    names = {t.get("id", ""): t.get("name", "") for t in root.findall("./trains/train")}
    out = []
    for build in root.findall("./manualBuilds/manualBuild"):
        lines = []
        for item in build.findall("mbItem"):
            stop = item.get("routeLocationId", "")
            destination = item.get("destinationId", "")
            lines.append({
                "id": item.get("id", ""), "sequence": _int(item.get("sequenceId")),
                "type": item.get("type", ""), "road": item.get("road", ""), "load": item.get("load", ""),
                # TrainManualBuildItem:347-356: a track is kept only with its stop or destination.
                "stop_id": stop, "track_id": item.get("locTrackId", "") if stop else "",
                "destination_id": destination,
                "destination_track_id": item.get("destTrackId", "") if destination else "",
                "day_id": item.get("trainScheduleId", ""), "count": _int(item.get("count"), 1),
                "warn": item.get("warn") == "true", "fail": item.get("fail") == "true",
                "remove": item.get("remove") == "true"})
        lines.sort(key=lambda line: line["sequence"])
        out.append({"id": build.get("id", ""), "train_id": build.get("trainId", ""),
                    "train": names.get(build.get("trainId", ""), ""), "comment": build.get("comment", ""),
                    "lines": lines})
    return out


def read_automations(directory: str | Path) -> list[dict]:
    """Automations with their steps in sequence order, keeping only what AutomationItem.store keeps."""
    root = _train_root(directory)
    if root is None:
        return []
    options = root.find("automationOptions")
    startup = options.get("automationStartupId", "") if options is not None else ""
    out = []
    for automation in root.findall("./automations/automation"):
        steps = []
        for item in automation.findall("item"):
            code = step_code(item.get("actionCode"))
            train = item.get("trainId", "") if code & STEP_TRAIN else ""
            messages = item.find("messages")
            ok = messages.find("messageOk") if messages is not None else None
            fail = messages.find("messageFail") if messages is not None else None
            steps.append({
                "id": item.get("id", ""), "sequence": _int(item.get("sequenceId")),
                "do": STEP_BY_CODE[code], "code": code, "train_id": train,
                "stop_id": item.get("routeLocationId", "") if train and code & STEP_STOP else "",
                "automation_id": item.get("automationId", "") if code & STEP_AUTOMATION else "",
                "goto_id": item.get("gotoAutomationId", "") if code & STEP_GOTO else "",
                "day_id": item.get("trainScheduleId", "") if code == ACTIVATE_DAY else "",
                "halt_on_failure": item.get("haltFail", "true") == "true",
                "message": ok.get("message", "") if ok is not None else "",
                "message_fail": fail.get("message", "") if fail is not None else "",
                "ran": item.get("actionRan") == "true", "successful": item.get("actionSuccessful") == "true"})
        steps.sort(key=lambda step: step["sequence"])
        out.append({"id": automation.get("id", ""), "name": automation.get("name", ""),
                    "comment": automation.get("comment", ""), "startup": automation.get("id") == startup,
                    "current_step": automation.get("currentItem", ""), "steps": steps})
    return out


# ---- Manual builds and automations (end) --------------------------------------------
