"""Why a car will or will not move in JMRI OperationsPro, and whole-railroad checks.

why_not walks the build gates in the order JMRI 5.16 applies them, tables A to G.
Everything here reads a Railroad and changes nothing. A gate that depends on what
happens during a build (random draws, timing against other trains, moves already
used) cannot be decided from files and reports not_checked rather than guessing.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import replace

import ops_router
from ops_data import (
    ALL, ANY, MATCH, QUICK_SERVICE, DISABLE_LOAD_CHANGE, REQUIRES_CABOOSE, REQUIRES_FRED, TRAINS, ROUTES, ANY_DAY, GENERATE,
    GENERATE_ANY_SPUR, EXCLUDE_ROUTES, EXCLUDE_TRAINS, ADD_CABOOSE, REMOVE_CABOOSE,
    Car, Location, Railroad, ScheduleItem, Stop, Track, Train, built_year, directions, split_name,
)

PASS, FAIL, NOT_CHECKED = "pass", "fail", "not_checked"
CLONE_MARK = "-(Clone)"  # RollingStock.CLONE: a quick service copy carries this after its number.
JAVA_INT = re.compile(r"[+-]?\d+")  # What Integer.parseInt accepts.


def _jdiv(a: int, b: int) -> int:
    """Java integer division, which truncates toward zero."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


class Extras:
    """Attributes the gates need that ops_data does not read, taken from the same files once.

    Only plain attribute dictionaries: departure times, leg starts, manual build lines, pool
    limits, divisions, clone flags and engine fields. A railroad changed in memory is not seen here.
    """

    def __init__(self, directory) -> None:
        self.train: dict[str, dict] = {}
        self.manual: dict[str, list[dict]] = {}
        self.loco_roads: dict[str, list[str]] = {}
        self.loco_types: dict[str, list[str]] = {}
        self.stop: dict[str, dict] = {}
        self.track: dict[str, dict] = {}
        self.types: dict[str, set[str]] = {}  # location or track id: car and locomotive types
        self.divisions: set[str] | None = None
        self.car: dict[str, dict] = {}
        self.engine: dict[str, dict] = {}
        self.roads: list[str] = []

        def root(name: str):
            path = directory / name
            try:
                return ET.parse(path).getroot() if path.is_file() else None
            except (ET.ParseError, OSError):
                return None

        trains = root("OperationsTrainRoster.xml")
        if trains is not None:
            for e in trains.findall("./trains/train"):
                self.train[e.get("id", "")] = dict(e.attrib)
                self.loco_types[e.get("id", "")] = [t.get("name", "") for t in e.findall("./types/locoType")]
                roads = e.find("locoRoads")
                self.loco_roads[e.get("id", "")] = [] if roads is None else [
                    r.get("name", "") for r in roads.findall("locoRoad")]
            for build in trains.findall("./manualBuilds/manualBuild"):
                items = [dict(i.attrib) for i in build.findall("mbItem")]
                items.sort(key=lambda i: int(i.get("sequenceId", "0")) if JAVA_INT.fullmatch(
                    i.get("sequenceId", "0")) else 0)
                self.manual[build.get("trainId", "")] = items
        routes = root("OperationsRouteRoster.xml")
        if routes is not None:
            for e in routes.findall("./routes/route/location"):
                self.stop[e.get("id", "")] = dict(e.attrib)
        locations = root("OperationsLocationRoster.xml")
        if locations is not None:
            for e in locations.findall("./locations/location"):
                for holder in [e, *e.findall("track")]:
                    self.types[holder.get("id", "")] = {
                        t.get("name", "") for t in holder.findall("./types/*") if t.tag in ("carType", "locoType")}
            for e in locations.findall("./locations/location/track"):
                self.track[e.get("id", "")] = dict(e.attrib)
            divisions = locations.find("divisions")
            if divisions is not None:
                self.divisions = {d.get("id", "") for d in divisions.findall("division")}
        cars = root("OperationsCarRoster.xml")
        if cars is not None:
            for e in cars.findall("./cars/car"):
                self.car[e.get("id", "")] = dict(e.attrib)
            self.roads = [r.get("name", "") for r in cars.findall("./roads/road")]
        engines = root("OperationsEngineRoster.xml")
        if engines is not None:
            for e in engines.findall("./engines/engine"):
                self.engine[e.get("id", "")] = dict(e.attrib)

# Failures here hold the car whichever train or chain of trains is tried.
ANY_TRAIN = {"B1", "B2", "B3", "B15", "B16", "B18", *(f"E{n}" for n in range(1, 11)),
             *(f"F{n}" for n in range(1, 6))}

CAR, CAR_SET = "Edit Car", "Set Car"
ENGINE_SET = "Set Locomotive"
TRAIN, BUILD_OPTIONS = "Edit Train", "Edit Train > Train Build Options"
TRAIN_ROADS, TRAIN_LOADS = "Edit Train > Train Road Options", "Edit Train > Train Load Options"
ROUTE, LOCATION = "Edit Route", "Edit Location"
TRACK, TRACK_LOADS = "Edit Location > track", "Edit Location > track > Load Options"
TRACK_ROADS, TRACK_DESTS = "Edit Location > track > Road Options", "Edit Location > track > Track Destinations"
SCHEDULE, SETTINGS = "Edit Schedule for the spur", "OperationsPro Settings"

# code: (what the gate tests, screen that fixes it, setting). Order is code order.
GATES: dict[str, tuple[str, str, str]] = {
    "A1": ("Train build enabled", "Trains", "Build checkbox (only Build All and automations honour it)"),
    "A2": ("On-time build order", SETTINGS, "Build on time, train departure times"),
    "A3": ("Route exists and resolves", TRAIN, "Route"),
    "A4": ("Every route stop still exists", ROUTE, "Replace the deleted location"),
    "A5": ("Stop usable: not skipped, not staging mid-route", TRAIN, "Skip list, or route order"),
    "A6": ("Random move reduction", ROUTE, "Random"),
    "A7": ("Terminal staging has a free track", TRACK,
           "Set outs list; for trains that swap staging tracks, planned pick ups (Ignore used track %) on those "
           "tracks, so a full track counts as leaving; or empty a track. When the reason is a type, road or load: "
           "what the staging track and its location take, or Settings, staging restriction"),
    "A8": ("Departure staging has a track this train can take whole", TRACK,
           "what the reason names for each track: the Pick ups list; a car or locomotive the train does not take "
           "(Edit Train types, roads, loads, owners, built dates); a locomotive count other than the number on the "
           "track (ask for that number, or 0); the track direction; Moves and Max Length at the first stop"),
    "A9": ("Locomotives the train asks for are found", TRAIN,
           "Locomotives: count, model and road; then where the engines are, their type, road, owner, built dates "
           "and Out of Service, and that the terminal takes their type (ops_audit engine-no-train)"),
    "B0": ("Car at a stop on this route and free to be picked", CAR_SET, "Location, or Route stops"),
    "B1": ("Car has a track", CAR_SET, "Track"),
    "B2": ("Location known", CAR_SET, "Location Unknown"),
    "B3": ("In service", CAR_SET, "Out of Service"),
    "B4": ("Car's destination on this route", CAR_SET, "Destination"),
    "B5": ("FRED or caboose only to the terminal", CAR_SET, "Destination"),
    "B6": ("Interchange: not set out by this same route", TRACK, "Pick ups: name trains or routes rather than any"),
    "B7": ("Track pick up list admits this train", TRACK, "Pick ups list"),
    "B8": ("Interchange filter has an exit on this route", TRACK_DESTS, "Accept the route's locations, or give the car a final destination"),
    "B9": ("Train takes this road", TRAIN_ROADS, "Road option; caboose road for a caboose"),
    "B10": ("Train takes this type", TRAIN, "Car types"),
    "B11": ("Train takes this owner", BUILD_OPTIONS, "Owner option"),
    "B12": ("Built inside the train's years, both ends exclusive", BUILD_OPTIONS, "Built dates"),
    "B13": ("Train takes this load", TRAIN_LOADS, "Load option"),
    "B14": ("FRED car only on a train that needs FRED", TRAIN, "Requires FRED"),
    "B15": ("Pick up day matches the active train schedule", "Train Schedules", "Active schedule, or the car's pick up day"),
    "B16": ("No wait count", CAR_SET, "Wait, which falls as trains that can serve the car build"),
    "B17": ("Caboose and FRED handled first", TRAIN,
            "Requires; when a caboose or FRED car is there, what refused it is the cause (often B6 or C9)"),
    "B18": ("Kernel together on one track", CAR, "Kernel, or move the members together"),
    "B19": ("Manual build lines", TRAIN, "Manual build lines"),
    "B20": ("Departure staging: every car on the track must leave", "the stuck car's own refusals",
            "each car on a departure staging track needs a destination on this train, so fix what refused it "
            "(its story names the gate)"),
    "C1": ("Pick up stop not skipped", TRAIN, "Skip list"),
    "C2": ("Pick ups or local moves on at the stop", ROUTE, "Pick ups?, Local moves?"),
    "C3": ("Staging pick ups only at the start of the route", ROUTE, "Route order"),
    "C4": ("Stop direction served by the location", LOCATION, "Train direction, or the stop's direction in Edit Route"),
    "C5": ("Moves requested at the stop", ROUTE, "Moves"),
    "C6": ("Pick ups on, unless local move or final destination here", ROUTE, "Pick ups?"),
    "C7": ("Second pass rule for local moves", ROUTE, "Local moves?"),
    "C8": ("Pick up rules repeat at each stop", TRACK, "Pick ups list"),
    "C9": ("Stop direction served by the car's track", TRACK, "Train direction"),
    "C10": ("Staging ships this load", TRACK, "Ship load options on the staging track"),
    "C11": ("Quick service timing", TRACK, "Quick service"),
    "C12": ("Home division", CAR, "Division; or put a location this train reaches in the car's home division "
                                  "(Edit Location, Division)"),
    "D1": ("A later stop at the destination with set outs on", ROUTE, "A stop after the car's, Set outs?"),
    "D2": ("Destination stop not skipped", TRAIN, "Skip list"),
    "D3": ("Moves available at the destination stop", ROUTE, "Moves"),
    "D4": ("Not the same split location, unless a switcher", BUILD_OPTIONS,
           "Local switcher route, or Allow cars to return to staging; or, for a car that should ride out and come "
           "back (a buffer or LCL car), Edit Car, Passenger, which exempts it"),
    "D5": ("Local moves on, for a final destination at the same location", ROUTE, "Local moves? at both stops"),
    "D6": ("Departure track's filter admits this location", TRACK_DESTS, "Accept the destination on the car's current track"),
    "D7": ("Location takes this type", LOCATION, "Car types"),
    "D8": ("Stop direction served by the destination", LOCATION, "Train direction"),
    "D9": ("Train length through the leg", ROUTE, "Max Length"),
    "D10": ("Through cars allowed, origin to terminal", BUILD_OPTIONS, "Allow cars to travel from origin to terminal"),
    "D11": ("Send to terminal rule", BUILD_OPTIONS, "Send all car pick ups to terminal"),
    "D12": ("Terminal staging track is free", TRACK, "Empty the staging track"),
    "D13": ("Not the same split track name", TRACK, "Track name"),
    "D14": ("Stop direction served by the track", TRACK, "Train direction"),
    "D15": ("Track set out list admits this train", TRACK, "Set outs list"),
    "D16": ("Car passes table E", TRACK, "See gates E1 to E10"),
    "D17": ("Length failure can fall to the spur's alternate", TRACK, "Alternate track"),
    "D18": ("Timing against pulls by other trains", TRAIN, "Departure time"),
    "D19": ("Local switcher track-to-track rule", SETTINGS, "Switcher Service Options"),
    "E1": ("Track is at the location", CAR_SET, "Track"),
    "E2": ("Location takes this type", LOCATION, "Car types"),
    "E3": ("Track takes this type", TRACK, "Car types"),
    "E4": ("Track takes this road", TRACK_ROADS, "Road option"),
    "E5": ("Car length is a number", CAR, "Length"),
    "E6": ("Track filter admits the final destination", TRACK_DESTS, "Accept the final destination"),
    "E7": ("Track that takes only routed cars", TRACK, "Routed"),
    "E8": ("Track takes this load", TRACK_LOADS, "Load option, plain or type & load"),
    "E9": ("Room on the track", TRACK,
           "Length; or, when cars there are being pulled, planned pick ups (Ignore used track %) so they count as "
           "leaving, aggressive mode so a later pass sees the room, and route Moves at that stop that cover the "
           "set outs plus the pick ups"),
    "E10": ("Schedule admits the car", SCHEDULE, "A line for this car, or a schedule for a custom load"),
    "F1": ("Line's set out day", SCHEDULE, "Delivery day"),
    "F2": ("Line's type", SCHEDULE, "Type"),
    "F3": ("Line's road", SCHEDULE, "Road"),
    "F4": ("Line's receive load", SCHEDULE, "Receive"),
    "F5": ("Line's random", SCHEDULE, "Random"),
    "G1": ("Train can carry: type, load, built, owner, road", TRAIN, "Car types and road and load options"),
    "G2": ("Car's location and destination on the route", ROUTE, "Stops; a staging destination must be the last"),
    "G3": ("Moves and pick ups at the car's stop", ROUTE, "Moves, Pick ups?, Local moves?"),
    "G4": ("Direction at the car's location and track", TRACK, "Train direction"),
    "G5": ("Track pick up list admits this train", TRACK, "Pick ups list"),
    "G6": ("Destination stop: set outs, moves, not skipped", ROUTE, "Set outs?, Moves"),
    "G7": ("Direction at the destination location", LOCATION, "Train direction"),
    "G8": ("Destination track direction and set out list", TRACK, "Train direction, Set outs list"),
    "G9": ("Terminal, local, return and through rules", BUILD_OPTIONS, "Terminal and through options"),
    "G10": ("Train length before the destination", ROUTE, "Max Length"),
    "G11": ("Only active trains", SETTINGS, "Car Routing Options"),
    "G12": ("Router can chain trains to the destination", SETTINGS, "Car Routing Options, and connecting interchanges"),
}


def _custom(rr: Railroad, car: Car) -> bool:
    return not rr.is_default_load(car.load)


def _exempt(car: Car) -> bool:
    """Passenger cars, cabooses and FRED cars skip the same-place rules."""
    return car.passenger or car.caboose or car.fred


class Gates:
    def __init__(self, railroad: Railroad):
        self.rr = railroad
        self._extras: Extras | None = None

    @property
    def x(self) -> Extras:
        if self._extras is None:
            self._extras = Extras(self.rr.directory)
        return self._extras

    # Rolling stock state the builder keeps in memory, rebuilt from the files as JMRI does on load.
    def _is_clone(self, car: Car) -> bool:
        return self.x.car.get(car.id, {}).get("clone") == "true" or CLONE_MARK in car.number

    def _train_types(self, train: Train) -> list[str]:
        """Train.getTypeNames: car types and locomotive types together."""
        return train.types + [t for t in self.x.loco_types.get(train.id, []) if t not in train.types]

    def _engine_length(self, engine) -> int:
        return int(engine.length) + self.rr.coupler if engine.length.isdigit() else 0

    def _engine_dest_track(self, engine) -> str:
        return self.x.engine.get(engine.id, {}).get("secDestinationId", "")

    def _reserved(self, track: Track) -> int:
        """Track.getReserved: set outs coming in, less pick ups going out in aggressive mode. Clones never reserve."""
        rr = self.rr
        total = sum(rr.car_length(c) or 0 for c in rr.cars.values()
                    if c.dest_track_id == track.id and not self._is_clone(c))
        total += sum(self._engine_length(e) for e in rr.engines.values() if self._engine_dest_track(e) == track.id)
        if rr.option("buildOptions", "aggressive"):
            cars, engines = rr.rolling_stock_on(track)
            total -= sum(rr.car_length(c) or 0 for c in cars if c.destination_id and not self._is_clone(c))
            total -= sum(self._engine_length(e) for e in engines
                         if self.x.engine.get(e.id, {}).get("destinationId"))
        return total

    def loaded_moves(self) -> dict[str, int]:
        """Track.getMoves after a load: the stored count plus one for each car and engine destined to the
        track. Loading sets each destination again (RS:1490), Track.addDropRS bumps moves (TR:818), and
        Store writes moves less those drops (TR:2840)."""
        rr = self.rr
        moves = {t.id: t.moves for t in rr.tracks.values()}
        destined = [(c.destination_id, c.dest_track_id) for c in rr.cars.values()]
        destined += [(self.x.engine.get(e.id, {}).get("destinationId", ""), self._engine_dest_track(e))
                     for e in rr.engines.values()]
        for location_id, track_id in destined:
            track = rr.tracks.get(track_id)
            if track is not None and location_id and track.location_id == location_id:
                moves[track.id] += 1
        return moves

    def _setouts(self, track: Track) -> int:
        """Track.getReservedLengthSetouts: every car and engine destined to the track, clones included."""
        rr = self.rr
        return (sum(rr.car_length(c) or 0 for c in rr.cars.values() if c.dest_track_id == track.id)
                + sum(self._engine_length(e) for e in rr.engines.values() if self._engine_dest_track(e) == track.id))

    def _available(self, track: Track) -> int:
        """Track.getAvailableTrackSpace, with the planned pick ups percentage."""
        used, reserved, ignore = self.rr.used_length(track), self._reserved(track), track.ignore_used
        available = track.length - (_jdiv(used * (100 - ignore), 100) + reserved)
        available = min(available, track.length + _jdiv(track.length * ignore, 100) - used - reserved)
        return min(available, track.length - self._setouts(track))

    def _pool(self, track: Track) -> list[Track]:
        location = self.rr.locations.get(track.location_id)
        return [t for t in location.tracks if t.pool == track.pool] if location and track.pool else []

    def _pool_lends(self, track: Track, need: int) -> bool:
        """Pool.requestTrackLength: another track in the pool gives up enough length."""
        limit = self.x.track.get(track.id, {}).get("maxLength", "")
        used, reserved = self.rr.used_length(track), self._reserved(track)
        if JAVA_INT.fullmatch(limit) and used + reserved + need > int(limit):
            return False
        extra = used + reserved + need - track.length
        for other in self._pool(track):
            if other is track:
                continue
            minimum = self.x.track.get(other.id, {}).get("minLength", "0")
            minimum = int(minimum) if JAVA_INT.fullmatch(minimum) else 0
            taken = self.rr.used_length(other) + self._reserved(other)
            if taken + extra <= other.length and other.length - extra >= minimum:
                return True
            spare = min(other.length - taken, other.length - minimum)
            if spare > 0:
                extra -= spare
        return False

    @staticmethod
    def _gate(code: str, status: str | bool, reason: str = "") -> dict:
        if isinstance(status, bool):
            status = PASS if status else FAIL
        title, screen, setting = GATES[code]
        result = {"gate": code, "status": status, "tests": title, "reason": reason}
        if status != PASS:
            result["fix"] = {"screen": screen, "setting": setting}
        return result

    def _is_switcher(self, train: Train) -> bool:
        stops = self.rr.stops(train)
        return bool(stops) and len({s.split for s in stops}) == 1

    def _is_turn(self, train: Train) -> bool:
        stops = self.rr.stops(train)
        return bool(stops) and not self._is_switcher(train) and stops[0].split == stops[-1].split

    def _mid_staging(self, train: Train, stop: Stop) -> bool:
        stops = self.rr.stops(train)
        location = self.rr.locations.get(stop.location_id)
        return bool(location) and location.is_staging and stop is not stops[0] and stop is not stops[-1]

    # The train as the builder holds it: moves and length per stop (TBB:443-530, 1595-1615, TBC:1946-1993).
    def _start_moves(self, train: Train, stop: Stop) -> tuple[int, int] | None:
        """Moves free at a stop when cars start being placed, as (fewest, most). None: the draw fails the build.

        Skipped stops and staging in mid-route start with every move used. A random value of N takes
        between 0 and max*N/100 moves (Java integer arithmetic).
        """
        if stop.id in train.skips or self._mid_staging(train, stop):
            return 0, 0
        if stop.random == "Off" or stop.max_moves <= 0:
            return stop.max_moves, stop.max_moves
        if not JAVA_INT.fullmatch(stop.random):
            return None
        taken = max(0, _jdiv(stop.max_moves * int(stop.random), 100))
        return stop.max_moves - taken, stop.max_moves

    def _bad_random(self, train: Train) -> list[Stop]:
        """Worked stops whose random value Integer.parseInt refuses: buildErrorRandomControl."""
        return [s for s in self.rr.stops(train) if s.id not in train.skips and not self._mid_staging(train, s)
                and s.max_moves > 0 and s.random != "Off" and not JAVA_INT.fullmatch(s.random)]

    def _can_join(self, other: Car, train: Train) -> bool:
        """A cheap superset of the cars the build could add: placed, in service, a type the train takes."""
        return (bool(other.track_id) and not other.out_of_service and not other.unknown
                and other.type in train.types and (not other.train_id or other.train_id == train.id))

    def _move_competitors(self, car: Car, train: Train, stops: list[Stop], origin: Stop, stop: Stop) -> int:
        """Most other cars that can take a move at stop before this car is placed.

        The builder works the route in order, so only cars standing at the car's stop or earlier are
        placed first, and each stop gives out at most its moves in pick ups.
        """
        rr = self.rr
        dest = rr.locations.get(stop.location_id)
        upto = stops[:stops.index(origin) + 1]
        places = {s.location_id for s in upto}
        count = sum(1 for c in rr.cars.values() if c.id != car.id and c.location_id in places
                    and self._can_join(c, train) and (dest is None or c.type in dest.types))
        cap = sum(max(0, (self._start_moves(train, s) or (0, 0))[1]) for s in upto)
        return min(count, cap)

    def _length_bounds(self, car: Car, train: Train, stops: list[Stop], index: int) -> tuple[int, int, str]:
        """(least, most) length the train already has leaving stops[index] when this car is offered.

        Least: the locomotives and a required caboose or FRED car, which go in before any car and stay
        to the end of their leg; only counted when no leg changes them. Most: those plus, for each stop
        up to here, the longest cars standing there up to that stop's moves.
        """
        rr = self.rr
        raw = self.x.train.get(train.id, {})
        legs = train.leg2_options or train.leg3_options
        first = rr.locations.get(stops[0].location_id)
        notes = []
        least = most = 0
        count = int(train.engines) if train.engines.isdigit() else None
        model = raw.get("engineModel", "")
        at_start = [e for e in rr.engines.values() if first and e.location_id == first.id
                    and (not model or self.x.engine.get(e.id, {}).get("model") == model)]
        lengths = sorted(self._engine_length(e) for e in at_start)
        if count and lengths and not legs:
            least += count * lengths[0]
            notes.append(f"{count} locomotive{'s' if count > 1 else ''} at least {count * lengths[0]}")
        every = [self._engine_length(e) for e in rr.engines.values()]
        most += count * max(lengths or every or [0]) if count is not None else sum(every)
        if count is not None and first is not None and first.is_staging:
            most += sum(self._engine_length(e) for e in rr.engines.values() if e.location_id == first.id)
        for flag, kind in ((REQUIRES_CABOOSE, "caboose"), (REQUIRES_FRED, "fred")):
            if not train.requires & flag or legs:
                continue
            pool = [c for c in rr.cars.values() if c.location_id == stops[0].location_id and getattr(c, kind)
                    and (not train.caboose_road or c.road == train.caboose_road) and c.id != car.id]
            if pool:
                shortest = min(rr.car_length(c) or 0 for c in pool)
                least += shortest
                notes.append(f"{'caboose' if kind == 'caboose' else 'FRED car'} at least {shortest}")
        for s in stops[:index + 1]:
            here = [rr.car_length(c) or 0 for c in rr.cars.values()
                    if c.id != car.id and c.location_id == s.location_id and self._can_join(c, train)]
            moves = max(0, (self._start_moves(train, s) or (0, 0))[1])
            most += sum(sorted(here, reverse=True)[:moves])
        return least, most, ", ".join(notes) or "no locomotive or caboose known"

    def _leg_length(self, car: Car, train: Train, stops: list[Stop], start: int, end: int,
                    gate_code: str) -> dict:
        """Train length through stops[start:end] with this car aboard (checkTrainLength, isTrainLengthOkay)."""
        length = self.rr.kernel_length(car)
        unsure = []
        for index in range(start, end):
            stop = stops[index]
            least, most, note = self._length_bounds(car, train, stops, index)
            if least + length > stop.max_length:
                return self._gate(gate_code, FAIL, f"leaving {stop.name}: car or kernel {length} plus {note} "
                                                   f"exceeds max length {stop.max_length}")
            if most + length > stop.max_length:
                unsure.append(f"{stop.name} (max {stop.max_length}, train may already hold {most})")
        if unsure:
            return self._gate(gate_code, NOT_CHECKED, f"car or kernel {length} fits alone, but other cars placed "
                                                      f"first may fill the train: {'; '.join(unsure)}")
        return self._gate(gate_code, PASS, f"car or kernel {length} fits with every car the train could hold")

    # Table E and F: Car.checkDestination, Track.isRollingStockAccepted, Track.checkSchedule.
    def check_destination(self, car: Car, location: Location, track: Track, building: bool = True) -> list[dict]:
        """building: the answer during a build, where quick service may wait on other trains' pulls."""
        rr, gate = self.rr, self._gate
        out = [gate("E1", track.location_id == location.id, f"{track.name} at {location.name}")]
        out.append(gate("E2", car.type in location.types, f"{location.name}: type {car.type}"))
        out.append(gate("E3", car.type in location.types and car.type in track.types,
                        f"{track.name}: type {car.type}"))
        out.append(gate("E4", track.accepts_road(car.road), f"{track.name} {track.road_option}: road {car.road}"))
        length = rr.car_length(car)
        out.append(gate("E5", length is not None, f"length {car.length}"))
        fd_name = rr.locations[car.fd_id].name if car.fd_id in rr.locations else "none"
        out.append(gate("E6", track.accepts_destination(car.fd_id or None),
                        f"{track.name} {track.destination_option}: final destination {fd_name}"))
        out.append(gate("E7", not track.only_fd or bool(car.fd_id) or car.caboose or car.fred,
                        f"car has final destination {fd_name}; only routed cars: {track.only_fd}"))
        out.append(gate("E8", track.accepts_load(car.load, car.type),
                        f"{track.name} {track.load_option}: {car.type} {car.load}"))
        out.append(self._space(car, track, building))
        out.extend(self._schedule(car, track))
        return out

    def _space(self, car: Car, track: Track, building: bool = True) -> dict:
        """Track.isRollingStockAccepted, length part (TR:1631-1660)."""
        rr = self.rr
        if track.id in (car.track_id, car.dest_track_id):
            return self._gate("E9", PASS, "car already belongs to this track")
        used, reserved, setouts = rr.used_length(track), self._reserved(track), self._setouts(track)
        need = rr.kernel_length(car)
        room = f"needs {need}, used {used}, reserved {reserved}, set outs {setouts}, length {track.length}"
        if used + reserved + need <= track.length and setouts + need <= track.length:
            return self._gate("E9", PASS, room)
        if track.pool and self._pool_lends(track, need):
            return self._gate("E9", PASS, f"{room}; pool {track.pool} lends the length")
        if track.ignore_used and self._available(track) >= need:
            return self._gate("E9", PASS, f"{room}; planned pick ups {track.ignore_used}% leave "
                                          f"{self._available(track)} available")
        pool_length = sum(t.length for t in self._pool(track))
        if (not track.pool and track.length < need) or (track.pool and pool_length < need):
            return self._gate("E9", FAIL, f"car is longer than the track{' pool' if track.pool else ''}: {room}")
        # checkQuickServiceTrack runs only while a train builds in on-time mode, against pull times.
        if building and track.load_options & QUICK_SERVICE and rr.option("buildOptions", "onTime"):
            return self._gate("E9", NOT_CHECKED, f"{room}; quick service may free room after earlier pulls")
        # In aggressive mode a car the building train pulls off the track gives back its length at once
        # (Track.addPickupRS), so room can open during the build.
        if building and rr.option("buildOptions", "aggressive"):
            staying = [c for c in rr.rolling_stock_on(track)[0] if not c.destination_id and c.id != car.id]
            freed = sum(rr.car_length(c) or 0 for c in staying)
            if staying and used + reserved - freed + need <= track.length and setouts + need <= track.length:
                return self._gate("E9", NOT_CHECKED, f"{room}; aggressive mode: room opens if the build pulls "
                                                     f"some of the {len(staying)} cars on the track first")
        return self._gate("E9", FAIL, f"track is full: {room}")

    def _line(self, car: Car, item: ScheduleItem, track: Track) -> list[dict]:
        rr, gate = self.rr, self._gate
        day = item.setout_day
        day_ok = car.schedule_item == item.id or not day or day == rr.active_schedule \
            or day not in rr.train_schedules
        out = [gate("F1", day_ok, f"line {item.id} set out day {rr.train_schedules.get(day, day or 'any')}, "
                                  f"active {rr.train_schedules.get(rr.active_schedule, rr.active_schedule or 'any')}")]
        out.append(gate("F2", car.type == item.type, f"line {item.id} wants type {item.type}, car is {car.type}"))
        out.append(gate("F3", not item.road or car.road == item.road, f"line {item.id} road {item.road or 'any'}"))
        out.append(gate("F4", not item.receive or car.load == item.receive,
                        f"line {item.id} receives {item.receive or 'any load'}, car has {car.load}"))
        # Schedule.checkScheduleItem: the draw is skipped when the car's final destination track is this
        # spur or the car already holds the line. Only a blank means no draw; "0" is drawn and never passes.
        drawn = item.random != "" and car.schedule_item != item.id and car.fd_track_id != track.id
        if not drawn:
            out.append(gate("F5", PASS, "no random draw"))
        elif not re.fullmatch(r"-?\d+", item.random):
            out.append(gate("F5", FAIL, f"line {item.id} random {item.random!r} is not a number, so the draw never passes"))
        else:
            out.append(gate("F5", NOT_CHECKED, f"line {item.id} random {item.random}%"))
        return out

    def _schedule(self, car: Car, track: Track) -> list[dict]:
        rr, gate = self.rr, self._gate
        passing = [gate(c, PASS, "no schedule line applies") for c in ("F1", "F2", "F3", "F4", "F5")]
        if car.dest_track_id == track.id:
            return [gate("E10", PASS, "car is already destined here"), *passing]
        if not track.is_spur:
            return [gate("E10", PASS, f"{track.type} tracks do not use schedules"), *passing]
        schedule = rr.schedules.get(track.schedule_id)
        if schedule is None:
            custom = _custom(rr, car)
            reason = (f"spur has no schedule, so it refuses custom load {car.load}"
                      if custom else "no schedule and a default load")
            return [gate("E10", not custom, reason), *passing]
        if not schedule.items:
            return [gate("E10", FAIL, f"schedule {schedule.name} has no lines"), *passing]
        if track.schedule_mode == MATCH:
            items = schedule.items
        else:
            items = [i for i in schedule.items if i.id == track.item_id] or schedule.items[:1]
        lines = [self._line(car, item, track) for item in items]
        lines.sort(key=lambda gates: sum(g["status"] == FAIL for g in gates))
        best = lines[0]
        ok = not any(g["status"] == FAIL for g in best)
        mode = "match, any line" if track.schedule_mode == MATCH else f"sequential, current line {items[0].id} only"
        return [gate("E10", ok, f"schedule {schedule.name} ({mode})"), *best]

    def destination_status(self, car: Car, location: Location, track: Track,
                           building: bool = False) -> tuple[bool, str]:
        """Same answer as Car.checkDestination, by default outside a build: first failing gate, or OK."""
        for result in self.check_destination(car, location, track, building):
            if result["status"] == FAIL:
                return False, result["gate"]
        return True, ""

    # Table G: Train.isServiceable, as the router sees a car. dest is the what-if destination.
    def _can_carry(self, car: Car, train: Train) -> bool:
        road = train.accepts_caboose_road(car.road) if car.caboose else train.accepts_road(car.road)
        return (car.type in train.types and train.accepts_load(car.load, car.type)
                and train.accepts_built(car.built) and train.accepts_owner(car.owner) and road)

    def serviceable(self, car: Car, train: Train, dest: Location | None = None,
                    dest_track: Track | None = None, building: bool = False) -> list[dict]:
        """Train.isServiceable. building: the train is the one being built, so moves and length count."""
        rr, gate = self.rr, self._gate
        out: list[dict] = []
        dest_id = dest.id if dest else car.destination_id
        dest_track = dest_track or rr.tracks.get(car.dest_track_id)
        out.append(gate("G1", self._can_carry(car, train), f"{train.name}: {car.type} {car.load}, {car.road}, "
                                                           f"owner {car.owner}, built {car.built}"))
        stops = rr.stops(train)
        here = rr.locations.get(car.location_id)
        track = rr.tracks.get(car.track_id)
        on_route = any(s.location_id == car.location_id for s in stops)
        dest_loc = rr.locations.get(dest_id)
        dest_ok = dest_loc is None or (any(s.location_id == dest_id for s in stops) and (
            not dest_loc.is_staging or stops[-1].location_id == dest_id))
        ok = bool(stops) and here is not None and track is not None and on_route and dest_ok
        out.append(gate("G2", ok, f"route {train.route_id or 'none'}; staging must be the last stop"))
        if not ok:
            return out
        local = dest_loc is not None and dest_loc.split == here.split
        switcher = self._is_switcher(train)
        best: list[dict] = []
        for start, stop in enumerate(stops):
            if stop.location_id != car.location_id:
                continue
            moves = stop.max_moves > 0 and stop.id not in train.skips
            allowed = stop.local if local else stop.pickups
            attempt = [gate("G3", moves and allowed, f"{stop.id}: moves {stop.max_moves}, pick ups {stop.pickups}")]
            way = switcher or (stop.direction & here.dir and stop.direction & track.dir)
            attempt.append(gate("G4", bool(way), f"{stop.id} {directions(stop.direction)}; "
                                                 f"location {directions(here.dir)}, track {directions(track.dir)}"))
            attempt.append(gate("G5", track.accepts_pickup(train), f"{track.name}: {track.pickup_option}"))
            if not any(g["status"] == FAIL for g in attempt):
                if dest_loc is None:
                    return out + attempt
                attempt += self._serviceable_dest(car, train, stops, start, dest_loc, dest_track, local, building)
                if not any(g["status"] == FAIL for g in attempt):
                    return out + attempt
            if not best or len(attempt) > len(best):
                best = attempt
        return out + best

    def _serviceable_dest(self, car: Car, train: Train, stops: list[Stop], start: int, dest: Location,
                          dest_track: Track | None, local: bool, building: bool = False) -> list[dict]:
        rr, gate = self.rr, self._gate
        best: list[dict] = []
        switcher = self._is_switcher(train)
        for index in range(start, len(stops)):
            stop = stops[index]
            if stop.location_id != dest.id:
                continue
            ok = (stop.local if local else stop.drops) and stop.max_moves > 0 and stop.id not in train.skips
            if rr.option("router", "checkCarDestination"):
                ok = ok and rr.tracks[car.track_id].accepts_destination(dest.id)
            attempt = [gate("G6", bool(ok), f"{stop.id}: drops {stop.drops}, moves {stop.max_moves}")]
            attempt.append(gate("G7", bool(switcher or stop.direction & dest.dir),
                                f"{stop.id} {directions(stop.direction)}, {dest.name} {directions(dest.dir)}"))
            tracks = [dest_track] if dest_track else dest.tracks
            def fits(t: Track) -> bool:
                return bool(switcher or stop.direction & t.dir) and t.accepts_drop(train)
            # With no destination track, Train uses track.isRollingStockAccepted, which has no schedule test.
            usable = [t for t in tracks if fits(t) and (
                dest_track or self._accepts_ignoring_length(car, dest, t, schedule=False))]
            attempt.append(gate("G8", bool(usable), f"{len(usable)} of {len(tracks)} tracks at {dest.name}"))
            attempt.append(self._g9(car, train, stops, stops[start], stop, dest, building))
            # isTrainLengthOkay and isRouteMovesAvailable test only the train that is building.
            if building:
                attempt.append(self._leg_length(car, train, stops, start, index, "G10"))
            else:
                attempt.append(gate("G10", PASS, "length is tested only for the train being built"))
            if not any(g["status"] == FAIL for g in attempt):
                return attempt
            best = best or attempt
        return best or [gate("G6", FAIL, f"no stop at {dest.name} from the car's stop onward")]

    def _g9(self, car: Car, train: Train, stops: list[Stop], origin: Stop, stop: Stop, dest: Location,
            building: bool = False) -> dict:
        rr = self.rr
        here = rr.locations.get(car.location_id)
        track = rr.tracks[car.track_id]
        local = dest.split == here.split
        reasons = []
        if train.to_terminal and not local and here.split != stops[0].split and dest.split != stops[-1].split:
            reasons.append("train sends every later pick up to the terminal")
        if not self._is_turn(train) and track.is_staging and dest.id == here.id:
            reasons.append("no local move inside staging")
        # Train.isServiceableDestination returns true here, before the local-move, through-car and moves tests.
        if not reasons and train.allow_return and track.is_staging and dest.id == here.id:
            return self._gate("G9", PASS, "the train may return the car to its own staging")
        switcher = self._is_switcher(train)
        if local and not switcher and not _exempt(car) and not (
                train.local_moves and origin.local and stop.local):
            reasons.append("local moves are off for this train or stop")
        if (not train.through_cars and origin.split == stops[0].split and stop.split == stops[-1].split
                and stops[0].split != stops[-1].split and not switcher and not _exempt(car)):
            reasons.append("through cars are off")
        if building and not reasons and (self._start_moves(train, stop) or (0, 0))[1] <= 0:
            reasons.append(f"no moves left at {stop.name} while the train builds")
        return self._gate("G9", not reasons, "; ".join(reasons) or "terminal, local and through rules allow it")

    def _accepts_ignoring_length(self, car: Car, location: Location, track: Track, schedule: bool = True) -> bool:
        """Table E with a length failure tolerated; schedule=False also drops E10 and the F lines."""
        skipped = {"E9"} if schedule else {"E9", "E10", "F1", "F2", "F3", "F4", "F5"}
        results = self.check_destination(car, location, track)
        return not any(r["status"] == FAIL and r["gate"] not in skipped for r in results)

    # Tables A to D, one train, one car, one track.
    def _train_gates(self, train: Train) -> tuple[list[dict], list[Stop]]:
        rr, gate = self.rr, self._gate
        out = [gate("A1", train.build, f"{train.name} build {train.build}{_day_note(rr, train)}")]
        out.append(self._build_order(train))
        stops = rr.stops(train)
        out.append(gate("A3", bool(stops), f"route {train.route_id or 'none'} has {len(stops)} stops"))
        missing = [s.name for s in stops if s.location_id not in rr.locations]
        out.append(gate("A4", not missing, ", ".join(missing) or "all stops exist"))
        return out, stops

    def depart_minutes(self, train: Train) -> int | None:
        """Train.getDepartTimeMinutes: the first stop's departure time if set, else the train's. None if unreadable."""
        stops = self.rr.stops(train)
        stop = self.x.stop.get(stops[0].id, {}) if stops else {}
        raw = self.x.train.get(train.id, {})
        if stop.get("departTime"):
            day, (hour, _, minute) = stop.get("departDay", "0"), stop["departTime"].partition(":")
        elif "departHour" in raw and "departMinute" in raw:
            day, hour, minute = raw.get("departDay", "0"), raw["departHour"], raw["departMinute"]
        else:
            day, hour, minute = "0", "0", "0"
        if not all(JAVA_INT.fullmatch(v) for v in (day, hour, minute)):
            return None
        return int(day) * 24 * 60 + int(hour) * 60 + int(minute)

    def _build_order(self, train: Train) -> dict:
        """TrainManager.checkBuildOrder: in on-time mode a train may not depart before the last train built."""
        if not self.rr.option("buildOptions", "onTime"):
            return self._gate("A2", PASS, "build on time is off")
        mine = self.depart_minutes(train)
        built = [(self.depart_minutes(t), t) for t in self.rr.trains.values() if t.built]
        built = [(m, t) for m, t in built if m is not None and m > 0]
        if mine is None:
            return self._gate("A2", NOT_CHECKED, f"{train.name} departure time cannot be read")
        if not built:
            return self._gate("A2", PASS, "no train with a departure time is built; another train still "
                                          "building would only delay this one")
        last, other = max(built, key=lambda pair: pair[0])
        return self._gate("A2", mine >= last, f"{train.name} departs at minute {mine}; last built train "
                                              f"{other.name} departs at minute {last}")

    def build_blockers(self, train: Train) -> list[dict]:
        """Gates that fail this train's whole build, whichever car is asked about.

        A1 is left out: it only keeps a train out of Build All. Cars stuck in departure staging and
        locomotive assignment are decided during the build and are not covered.
        """
        out, stops = self._train_gates(train)
        out = [g for g in out if g["gate"] != "A1"]
        if stops:
            out.append(self._random_gate(train, []))
            out += self._staging_gates(train, stops)
            out.append(self._manual_short(train, stops))
        return [g for g in out if g["status"] == FAIL]

    def staging_problems(self, train: Train, track: Track) -> list[str]:
        """Why this staging track cannot depart on this train (checkDepartureStagingTrack)."""
        rr = self.rr
        stops = rr.stops(train)
        first = stops[0]
        cars, engines = rr.rolling_stock_on(track)
        problems = []
        if not track.accepts_pickup(train):
            problems.append("pick up list refuses the train")
        if not cars and not engines and first.max_moves > 0:
            problems.append("track is empty")
        if rr.used_length(track) > first.max_length:
            problems.append(f"{rr.used_length(track)} long, route allows {first.max_length}")
        if len(cars) > first.max_moves:
            problems.append(f"{len(cars)} cars, route allows {first.max_moves} moves")
        if train.engines.isdigit() and int(train.engines) and int(train.engines) != len(engines):
            problems.append(f"{len(engines)} locomotives, train needs {train.engines}")
        if not track.dir & first.direction:
            problems.append("track direction does not match the route")
        problems.extend(self._staging_engines(train, engines))
        caboose = fred = False
        for car in cars:
            if self._is_clone(car) or (car.kernel and not rr.is_kernel_lead(car)):
                continue
            problems.extend(self._staging_car(car, train, track))
            right_road = not train.caboose_road or train.caboose_road == car.road
            caboose = caboose or (car.caboose and right_road)
            fred = fred or (car.fred and right_road)
        if train.requires & REQUIRES_CABOOSE and not caboose:
            problems.append(f"no caboose of road {train.caboose_road or 'any'}")
        if train.requires & REQUIRES_FRED and not fred:
            problems.append(f"no FRED car of road {train.caboose_road or 'any'}")
        return problems

    def staging_doubts(self, train: Train, track: Track) -> list[str]:
        """What the files cannot settle about departing this staging track, once staging_problems is empty."""
        rr = self.rr
        doubts = []
        if not train.engines.isdigit():
            doubts.append(f"locomotive count {train.engines} is worked out during the build")
        if track.pool and self.x.track.get(track.id, {}).get("serviceOrder", "Normal") != "Normal" \
                and rr.rolling_stock_on(track)[0]:
            doubts.append(f"pool {track.pool} departs its tracks in arrival order")
        return doubts

    def _staging_engines(self, train: Train, engines: list) -> list[str]:
        """checkStagingEngines (TBB:1777-1846): every locomotive on the track must suit the train."""
        raw = self.x.train.get(train.id, {})
        model, road = raw.get("engineModel", ""), raw.get("engineRoad", "")
        loco_option = raw.get("locoRoadOption", ALL)
        loco_roads = self.x.loco_roads.get(train.id, [])
        problems = []
        for engine in engines:
            e = self.x.engine.get(engine.id, {})
            name = f"{engine.road} {engine.number}"
            if CLONE_MARK in engine.number or e.get("clone") == "true":
                continue
            if e.get("routeLocationId") or (e.get("trainId") and e.get("trainId") != train.id):
                problems.append(f"locomotive {name} is assigned to another train")
            elif e.get("type", "") not in self._train_types(train):
                problems.append(f"train does not take locomotive {name} type {e.get('type', '')}")
            elif model and e.get("model", "") != model:
                problems.append(f"train needs model {model}, locomotive {name} is {e.get('model', '')}")
            elif train.road_option != ALL and road and road != engine.road:
                problems.append(f"train needs locomotive road {road}, {name} is {engine.road}")
            elif not road and loco_option != ALL and (engine.road in loco_roads) != (loco_option == "Include"):
                problems.append(f"train does not take locomotive road {engine.road}")
            elif not train.accepts_owner(e.get("owner", "")):
                problems.append(f"train does not take locomotive {name} owner {e.get('owner', '')}")
            elif not train.accepts_built(e.get("built", "")):
                problems.append(f"train does not take locomotive {name} built {e.get('built', '')}")
        return problems

    def _staging_car(self, car: Car, train: Train, track: Track) -> list[str]:
        problems = []
        if self.x.car.get(car.id, {}).get("routeLocationId"):
            problems.append(f"{car} is already in a built train")
        elif car.train_id and car.train_id != train.id:
            problems.append(f"{car} is assigned to another train")
        if car.type not in train.types:
            problems.append(f"train does not take {car} type {car.type}")
        if not car.caboose and not train.accepts_road(car.road):
            problems.append(f"train does not take {car} road {car.road}")
        generated = car.load == self.rr.default_empty and track.generates_loads
        if not car.caboose and not car.passenger and not generated and not train.accepts_load(car.load, car.type):
            problems.append(f"train does not take {car} load {car.load}")
        if not train.accepts_owner(car.owner):
            problems.append(f"train does not take {car} owner {car.owner}")
        if not train.accepts_built(car.built):
            problems.append(f"train does not take {car} built {car.built}")
        if car.destination_id and not problems and any(
                g["status"] == FAIL for g in self.serviceable(car, train, building=True)):
            problems.append(f"train cannot take {car} to its destination {car.destination_id}")
        return problems

    def terminal_track_problems(self, train: Train, track: Track) -> list[str]:
        """Why this staging track cannot take the train at its terminal (checkTerminateStagingTrack, TBB:2037-2156)."""
        rr = self.rr
        if not track.accepts_drop(train):
            return ["set out list refuses the train"]
        problems = []
        cars, engines = rr.rolling_stock_on(track)
        count = len(cars) + len(engines)
        leaving = sum(1 for c in cars if c.destination_id) + sum(
            1 for e in engines if self.x.engine.get(e.id, {}).get("destinationId"))
        quick = bool(track.load_options & QUICK_SERVICE)
        free_when_leaving = rr.option("buildOptions", "aggressive") and rr.option("buildOptions", "stagingTrackAvail")
        occupied = count and (not free_when_leaving or quick or count != leaving)
        if occupied and not track.ignore_used:
            reason = "" if not free_when_leaving else ", not all of them leaving" if count != leaving else \
                ", and quick service tracks must be empty"
            problems.append(f"occupied by {len(cars)} cars and {len(engines)} locomotives{reason}")
        pending = [c for c in rr.cars.values() if c.dest_track_id == track.id] + [
            e for e in rr.engines.values() if self._engine_dest_track(e) == track.id]
        if pending and not (rr.option("buildOptions", "onTime") and quick):
            problems.append(f"{len(pending)} cars or locomotives already destined here")
        if problems or track.drop_option in (TRAINS, ROUTES):
            return problems  # A track that names the train or route skips the train checks.
        if rr.option("buildOptions", "stagingRestrictionEnabled", True):
            problems.extend(self._staging_restrictions(train, track))
        return problems

    def _staging_restrictions(self, train: Train, track: Track) -> list[str]:
        """checkTerminateStagingTrackRestrictions: the track must take everything the train can carry."""
        rr = self.rr
        location = rr.locations[track.location_id]
        loco = set(self.x.loco_types.get(train.id, []))
        for kind in self._train_types(train):
            # Locomotive types are read here from the files; car types from the railroad, which may be edited.
            at_location = location.types if kind not in loco else self.x.types.get(location.id, set())
            at_track = track.types if kind not in loco else self.x.types.get(track.id, set())
            if kind not in at_location:
                return [f"{location.name} does not take type {kind}, which the train carries"]
            if kind not in at_track:
                return [f"track does not take type {kind}, which the train carries"]
        if train.road_option == ALL and track.road_option != ALL:
            return ["train takes all roads, the track does not"]
        roads = self.x.roads or sorted({c.road for c in rr.cars.values()})
        for road in roads:
            if train.accepts_road(road) and not track.accepts_road(road):
                return [f"track does not take road {road}, which the train carries"]
        if train.load_option == ALL and track.load_option != ALL:
            return ["train takes all loads, the track does not"]
        for kind in self._train_types(train):
            names = [x.name for x in rr.loads.get(kind, [])] or [rr.default_empty, rr.default_load]
            for load in names:
                if train.accepts_load(load, kind) and not track.accepts_load(load, kind):
                    return [f"track does not take {kind} {load}, which the train carries"]
        return []

    def _staging_gates(self, train: Train, stops: list[Stop]) -> list[dict]:
        rr, gate = self.rr, self._gate
        out = []
        last = rr.locations.get(stops[-1].location_id)
        first = rr.locations.get(stops[0].location_id)
        returning = (first is last and rr.option("buildOptions", "aggressive")
                     and rr.option("buildOptions", "stagingTrackAvail"))
        if last is None or not last.is_staging or len(stops) < 2:
            out.append(gate("A7", PASS, "train does not end in staging"))
        elif returning:
            out.append(gate("A7", PASS, "aggressive mode with staging immediately available: the train returns "
                                        "to its own departure track and no terminal track is picked"))
        else:
            tracks = [t for t in last.tracks if t.is_staging]
            usable = [t for t in tracks if not self.terminal_track_problems(train, t)]
            reason = (f"free at {last.name}: {', '.join(t.name for t in usable)}" if usable else
                      "; ".join(f"{t.name}: {', '.join(self.terminal_track_problems(train, t))}" for t in tracks))
            out.append(gate("A7", bool(usable), reason))
        if first is not None and first.is_staging:
            tracks = [t for t in first.tracks if t.is_staging]
            report = {t.name: self.staging_problems(train, t) for t in tracks}
            good = [t for t in tracks if not report[t.name]]
            sure = [t for t in good if not self.staging_doubts(train, t)]
            if sure or not good:
                reason = (f"can depart from {', '.join(t.name for t in sure)}" if sure else
                          "; ".join(f"{name}: {', '.join(problems)}" for name, problems in report.items()))
                out.append(gate("A8", bool(sure), reason))
            else:
                out.append(gate("A8", NOT_CHECKED, "; ".join(
                    f"{t.name}: {', '.join(self.staging_doubts(train, t))}" for t in good)))
        else:
            out.append(gate("A8", PASS, "train does not start in staging"))
        out.append(self._engine_gate(train))
        return out

    def _engine_gate(self, train: Train) -> dict:
        """A9: buildErrorEngines (TrainBuilderEngines:405-443) when no locomotive the train asks for is found.
        Which ones the builder takes is decided in the build, so a candidate leaves it not_checked."""
        count = self.x.train.get(train.id, {}).get("numberEngines", "0")
        if count == "0":
            return self._gate("A9", PASS, "asks for no locomotives")
        audit = Audit(self)
        engines = [e for e in audit._engines() if not e.out_of_service]
        if any(not audit._loco_refusal(train, e) for e in engines):
            return self._gate("A9", NOT_CHECKED, f"asks for {count}; the build picks among the locomotives it can take")
        reasons = "; ".join(f"{e.road} {e.number}: {audit._loco_refusal(train, e)}" for e in engines[:4])
        return self._gate("A9", FAIL, f"asks for {count} and takes none of the locomotives" + (f" ({reasons})" if
                                                                                             reasons else ": there are none"))

    def _car_list_gates(self, car: Car, train: Train, stops: list[Stop], target: Track | None) -> list[dict]:
        rr, gate = self.rr, self._gate
        track = rr.tracks.get(car.track_id)
        here = rr.locations.get(car.location_id)
        placed = [s for s in stops if s.location_id == car.location_id]
        last = stops[-1] if stops else None
        at_last_only = bool(placed) and len(stops) > 1 and placed == [last] and not (
            last.local and here is not None and not here.is_staging)
        free = not car.train_id or car.train_id == train.id
        out = [gate("B0", bool(placed) and not at_last_only and free and here is not None,
                    f"car at {here.name if here else 'no location'}; "
                    f"{'not on this route' if not placed else 'last stop' if at_last_only else 'on route'}; "
                    f"assigned train {car.train_id or 'none'}")]
        out.append(gate("B1", track is not None, track.name if track else "no track set"))
        out.append(gate("B2", not car.unknown, f"location unknown {car.unknown}"))
        out.append(gate("B3", not car.out_of_service, f"out of service {car.out_of_service}"))
        on_route = not car.destination_id or any(s.location_id == car.destination_id for s in stops)
        out.append(gate("B4", on_route, f"car destination {car.destination_id or 'none'}"))
        # createCarList tests only the car's assigned destination, never a what-if target. A caboose is
        # let through when a leg option adds or removes the caboose along the route.
        held = car.fred or (car.caboose and not train.changes_caboose)
        if not held:
            out.append(gate("B5", PASS, "only FRED cars and cabooses are held to the terminal"))
        elif not car.destination_id:
            out.append(gate("B5", PASS, "the car has no assigned destination; the target asked about is not one"))
        else:
            terminal = bool(stops) and car.destination_id == stops[-1].location_id
            out.append(gate("B5", terminal, f"assigned destination {car.destination_id}, "
                                            f"terminal {stops[-1].location_id if stops else 'none'}"))
        same_route = bool(track) and track.is_interchange and track.pickup_option == ANY \
            and car.last_route_id == train.route_id
        out.append(gate("B6", not same_route, f"last route {car.last_route_id or 'none'}, this route {train.route_id}"))
        pulled = track is None or not (track.is_interchange or track.is_spur) or track.accepts_pickup(train)
        out.append(gate("B7", pulled, f"{track.name}: {track.pickup_option}" if track else "no track"))
        exit_ok = True
        if track and track.is_interchange and track.destination_option != ALL and not car.fd_id:
            exit_ok = any(track.accepts_destination(s.location_id) for s in stops)
        out.append(gate("B8", exit_ok, f"{track.name}: {track.destination_option}" if track else "no track"))
        road = train.accepts_caboose_road(car.road) if car.caboose else train.accepts_road(car.road)
        out.append(gate("B9", road, f"{train.name} {train.road_option}: road {car.road}"))
        out.append(gate("B10", car.type in train.types, f"{train.name}: type {car.type}"))
        out.append(gate("B11", train.accepts_owner(car.owner), f"{train.name}: owner {car.owner}"))
        years = f"{train.built_start or 'any'} < {built_year(car.built)} < {train.built_end or 'any'}"
        out.append(gate("B12", train.accepts_built(car.built), years))
        on_departure = bool(stops) and bool(track) and track.is_staging and car.location_id == stops[0].location_id
        load_ok = car.caboose or car.passenger or on_departure or train.accepts_load(car.load, car.type)
        out.append(gate("B13", load_ok, f"{train.name} {train.load_option}: {car.type} {car.load}"))
        out.append(gate("B14", on_departure or not car.fred or bool(train.requires & REQUIRES_FRED),
                        f"FRED {car.fred}; train requires {train.requires}"))
        day = car.pickup_day
        day_ok = on_departure or not day or rr.active_schedule == ANY_DAY or day == rr.active_schedule \
            or day not in rr.train_schedules
        out.append(gate("B15", day_ok, f"pick up day {rr.train_schedules.get(day, day or 'any')}, "
                                       f"active {rr.train_schedules.get(rr.active_schedule, rr.active_schedule or 'any')}"))
        out.append(gate("B16", on_departure or car.wait <= 0, f"wait {car.wait}"))
        out.append(self._caboose_or_fred(car, train, stops, target))
        out.append(self._kernel(car))
        out.append(self._manual_build(car, train, stops, target))
        out.append(self._departure_track(car, train, stops))
        return out

    def _leg_ends(self, train: Train, stops: list[Stop]) -> list[tuple[Stop, Stop, str]]:
        """(pick up stop, set out stop, caboose road) for each caboose leg (TB:255-300). Empty if unreadable."""
        raw = self.x.train.get(train.id, {})
        by_id = {s.id: s for s in stops}
        legs = [(stops[0], train.caboose_road)]
        ends = []
        for n, options in ((2, train.leg2_options), (3, train.leg3_options)):
            if options & (ADD_CABOOSE | REMOVE_CABOOSE):
                start = by_id.get(raw.get(f"leg{n}Start", ""))
                if start is None:
                    return []
                ends.append(start)
                if options & ADD_CABOOSE:
                    legs.append((start, raw.get(f"leg{n}CabooseRoad", "")))
        out = []
        for start, road in legs:
            later = [e for e in ends if stops.index(e) > stops.index(start)]
            out.append((start, later[0] if later else stops[-1], road))
        return out

    def _caboose_or_fred(self, car: Car, train: Train, stops: list[Stop], target: Track | None) -> dict:
        """B17: addCabooseOrFredToTrain places the cabooses and FRED cars the train needs, then
        removeCaboosesAndCarsWithFred drops every other one from the build (TB:104-106, TBC:42-268)."""
        rr, gate = self.rr, self._gate
        if not (car.caboose or car.fred):
            return gate("B17", PASS, "not a caboose or FRED car")
        track = rr.tracks.get(car.track_id)
        if stops and track and track.is_staging and car.location_id == stops[0].location_id:
            return gate("B17", PASS, "leaves with the train from departure staging; A8 and B20 decide")
        if not stops:
            return gate("B17", NOT_CHECKED, "no route")
        kind = "caboose" if car.caboose else "FRED car"
        if car.caboose:
            legs = self._leg_ends(train, stops)
            if not legs:
                return gate("B17", NOT_CHECKED, "a caboose change has no readable leg start")
            if not train.requires & REQUIRES_CABOOSE:
                legs = legs[1:]  # The departure caboose is only taken when the train requires one.
        else:
            if not train.requires & REQUIRES_FRED:
                return gate("B17", FAIL, "the train needs no FRED car, so the builder drops this one")
            end = (self._leg_ends(train, stops) or [(stops[0], stops[-1], "")])[0][1]
            legs = [(stops[0], end, train.caboose_road)]
        for start, end, road in legs:
            if start.location_id != car.location_id:
                continue
            if road and road != car.road:
                return gate("B17", FAIL, f"the {kind} taken at {start.name} must be road {road}")
            dest_id = target.location_id if target else car.destination_id
            if dest_id and dest_id != end.location_id:
                return gate("B17", FAIL, f"a {kind} taken at {start.name} rides to {end.name}, the end of its leg")
            rivals = [c for c in rr.cars.values() if c.id != car.id and c.location_id == car.location_id
                      and (c.caboose if car.caboose else c.fred) and (not road or c.road == road)
                      and self._can_join(c, train)]
            if rivals:
                return gate("B17", NOT_CHECKED, f"{len(rivals) + 1} {kind}s qualify at {start.name}; the builder "
                                                "takes one" + (" and prefers the lead locomotive's road"
                                                               if car.caboose else ""))
            return gate("B17", PASS, f"the train takes this {kind} at {start.name} to {end.name}")
        if not legs:
            return gate("B17", FAIL, f"the train needs no {kind}, so the builder drops this one")
        where = ", ".join(s.name for s, _, _ in legs)
        return gate("B17", FAIL, f"the train takes a {kind} only at {where}, so the builder drops this one")

    def _mb_matches(self, item: dict, other: Car, stops: list[Stop]) -> bool:
        """TrainBuilder.checkItem, for a car in the train's car list (on the route, no train, no destinations)."""
        rr = self.rr
        if other.train_id or other.destination_id or other.fd_id or not other.track_id:
            return False
        if not any(s.location_id == other.location_id for s in stops):
            return False
        stop = next((s for s in stops if s.id == item.get("routeLocationId", "")), None)
        if stop is None and item.get("routeLocationId"):
            return False
        day = rr.active_schedule if rr.active_schedule in rr.train_schedules else ""
        return ((not item.get("type") or other.type == item["type"])
                and (not item.get("road") or other.road == item["road"])
                and (not item.get("load") or other.load == item["load"])
                and (stop is None or other.location_id == stop.location_id)
                and (not item.get("locTrackId") or other.track_id == item["locTrackId"])
                and (not day or not item.get("trainScheduleId") or item["trainScheduleId"] not in rr.train_schedules
                     or item["trainScheduleId"] == day))

    @staticmethod
    def _mb_count(item: dict) -> int:
        text = item.get("count", "0")
        return int(text) if JAVA_INT.fullmatch(text) else 0

    def _manual_short(self, train: Train, stops: list[Stop]) -> dict:
        """Manual lines set to fail the build that more cars than can match them (mbuildFail)."""
        short = [i for i in self.x.manual.get(train.id, []) if i.get("fail") == "true" and self._mb_count(i) > 0
                 and sum(self._mb_matches(i, c, stops) and self._can_join(c, train)
                         for c in self.rr.cars.values()) < self._mb_count(i)]
        reason = ("manual line " + ", ".join(i.get("id", "?") for i in short) +
                  " asks for more cars than match it and is set to fail the build") if short else ""
        return self._gate("B19", not short, reason or "no manual line can fail the build for want of cars")

    def _manual_build(self, car: Car, train: Train, stops: list[Stop], target: Track | None) -> dict:
        """B19: manualBuild offers cars to each line in turn before the general search (TB:310-443)."""
        rr, gate = self.rr, self._gate
        items = self.x.manual.get(train.id, [])
        if not items:
            return gate("B19", PASS, "the train has no manual build lines")
        short = self._manual_short(train, stops)
        if short["status"] == FAIL:
            return short

        def matches(item: dict, other: Car) -> bool:
            return self._mb_matches(item, other, stops)

        count = self._mb_count
        for item in items:
            if not matches(item, car):
                continue
            line = f"manual line {item.get('id', '?')}"
            dest = item.get("destinationId", "")
            dest_track = item.get("destTrackId", "")
            if count(item) <= 0:
                note = f"{line} matches but asks for no cars"
            elif dest and target and (dest != target.location_id or dest_track not in ("", target.id)):
                where = ", ".join(x.name for x in (rr.locations.get(dest), rr.tracks.get(dest_track)) if x) or dest
                if item.get("remove") == "true":
                    return gate("B19", FAIL, f"{line} sends the car to {where} and removes it from the build "
                                             "if that fails")
                return gate("B19", NOT_CHECKED, f"{line} tries the car for {where} first; only if that fails does "
                                                "the general build see it")
            else:
                rivals = sum(matches(item, c) and self._can_join(c, train) for c in rr.cars.values())
                if item.get("remove") == "true" and rivals > count(item):
                    return gate("B19", NOT_CHECKED, f"{rivals} cars match {line}, which takes {count(item)} and "
                                                    "removes the rest from the build")
                return gate("B19", PASS, f"{line} takes the car first" + (
                    ", with a final destination of this target" if dest else ", by the normal destination search"))
            if item.get("remove") == "true":
                return gate("B19", FAIL, f"{note}, and removes it from the build")
        return gate("B19", PASS, "no manual line matches this car")

    def _kernel(self, car: Car) -> dict:
        if not car.kernel:
            return self._gate("B18", PASS, "not in a kernel")
        # checkKernel: a lead that is in service, every member at one location with a track, and the
        # track names equal once split.
        rr = self.rr
        members = [c for c in rr.cars.values() if c.kernel == car.kernel]
        leads = [c for c in members if rr.is_kernel_lead(c) and not c.out_of_service]
        places = {(c.location_id, rr.tracks[c.track_id].split if c.track_id in rr.tracks else None)
                  for c in members}
        ok = bool(leads) and len(places) == 1 and None not in {p[1] for p in places}
        return self._gate("B18", ok, f"kernel {car.kernel}: {len(leads)} lead in service, {len(places)} track "
                                     "names. A split kernel fails the whole build, not only the car.")

    def _departure_track(self, car: Car, train: Train, stops: list[Stop]) -> dict:
        rr = self.rr
        track = rr.tracks.get(car.track_id)
        if not stops or track is None or not track.is_staging or car.location_id != stops[0].location_id:
            return self._gate("B20", PASS, "car is not on departure staging")
        problems = self.staging_problems(train, track)
        return self._gate("B20", not problems, ", ".join(problems) or f"{track.name} can depart")

    def _pickup_gates(self, car: Car, train: Train, stops: list[Stop], stop: Stop | None,
                      goal: Stop | None, target: Track | None = None) -> list[dict]:
        rr, gate = self.rr, self._gate
        codes = [f"C{n}" for n in range(1, 13)]
        track = rr.tracks.get(car.track_id)
        here = rr.locations.get(car.location_id)
        if stop is None or track is None or here is None:
            return [gate(c, NOT_CHECKED, "no pick up stop on this route") for c in codes]
        local = goal is not None and goal.split == stop.split
        switcher = self._is_switcher(train)
        out = [gate("C1", stop.id not in train.skips, f"stop {stop.id}")]
        out.append(gate("C2", stop.pickups or stop.local, f"pick ups {stop.pickups}, local {stop.local}"))
        out.append(gate("C3", not here.is_staging or stop is stops[0], f"{here.name} staging {here.is_staging}"))
        out.append(gate("C4", switcher or bool(stop.direction & here.dir),
                        f"{stop.id} {directions(stop.direction)}, {here.name} {directions(here.dir)}"))
        out.append(gate("C5", stop.max_moves > 0, f"moves {stop.max_moves}"))
        out.append(gate("C6", stop.pickups or local or car.fd_id == stop.location_id, f"pick ups {stop.pickups}"))
        out.append(self._second_pass(car, train, stop))
        out.append(self._pickup_repeat(car, train, track))
        out.append(gate("C9", switcher or bool(stop.direction & track.dir),
                        f"{stop.id} {directions(stop.direction)}, {track.name} {directions(track.dir)}"))
        # The ship check runs whenever both generators fail. A generator only replaces a default empty with
        # no destination or final destination, and only when the type has a custom load to give.
        if track.ships_load(car.load, car.type):
            out.append(gate("C10", PASS, f"{track.ship_option}: {car.load}"))
        elif (track.is_staging and track.generates_loads and car.load == rr.default_empty
              and not car.destination_id and not car.fd_id and rr.custom_loads(car.type)):
            out.append(gate("C10", NOT_CHECKED, f"{track.ship_option}: {car.load}; fails the build if load "
                                                "generation finds nothing"))
        else:
            out.append(gate("C10", FAIL, f"{track.ship_option}: {car.load}, and no generator replaces it"))
        out.append(self._quick_departure(car, track, stop))
        out.append(self._home_division(car, train, stops, track, goal, target))
        return out

    def _second_pass(self, car: Car, train: Train, stop: Stop) -> dict:
        """C7: the extra pass in aggressive mode retries only cars whose final destination is this stop,
        and only with local moves on there (TB:599-612, TBC:465-485). It adds a chance and never takes one
        away, so the gate cannot fail; it says whether the car gets that second try."""
        fd = self.rr.locations.get(car.fd_id)
        if fd is None or fd.name != stop.name:
            return self._gate("C7", PASS, "only cars with a final destination here get a second pass; the first "
                                          "pass decides this car")
        if not self.rr.option("buildOptions", "aggressive"):
            return self._gate("C7", PASS, "normal build: one pass, no second try")
        if not stop.local:
            return self._gate("C7", PASS, f"local moves are off at {stop.name}, so there is no second try")
        return self._gate("C7", PASS, f"a second pass at {stop.name} retries the car if the first pass "
                                      "placed any car there")

    def _pickup_repeat(self, car: Car, train: Train, track: Track) -> dict:
        """C8: checkPickupInterchangeOrSpur again at the stop (TBC:522), with the car's track at that moment."""
        if track.is_interchange and track.pickup_option == ANY and car.last_route_id == train.route_id:
            return self._gate("C8", FAIL, f"{track.name}: this route set the car out and pick ups are Any")
        if (track.is_interchange or track.is_spur) and not track.accepts_pickup(train):
            return self._gate("C8", FAIL, f"{track.name}: {track.pickup_option} refuses the train")
        return self._gate("C8", PASS, f"{track.name}: {track.type}, {track.pickup_option}")

    def _quick_departure(self, car: Car, track: Track, stop: Stop) -> dict:
        """C11: checkQuickServiceDeparting (TBB:3097-3145). Only a car whose clone a built train set out
        on this quick service track waits on that train's set out time."""
        if not track.load_options & QUICK_SERVICE:
            return self._gate("C11", PASS, "no quick service")
        number = car.number.split(CLONE_MARK)[0]
        clones = [c for c in self.rr.cars.values() if self._is_clone(c) and c.road == car.road
                  and c.number.split(CLONE_MARK)[0] == number and c.dest_track_id == track.id]
        if not clones:
            return self._gate("C11", PASS, "quick service track, but no clone of the car waits on a set out")
        if self.x.car.get(car.id, {}).get("routeDestinationId") == stop.id:
            return self._gate("C11", FAIL, f"the car was set out at stop {stop.id}, the same stop that would "
                                           "pull it")
        clone = clones[-1]
        trains = {t.id: t.name for t in self.rr.trains.values()}
        return self._gate("C11", NOT_CHECKED, f"clone {clone} is set out by {trains.get(clone.train_id, 'a train')}; "
                                              "the pull must come after that set out time")

    def _load_type(self, car: Car) -> str:
        for load in self.rr.loads.get(car.type, []):
            if load.name == car.load:
                return load.load_type
        return "Empty" if car.load == self.rr.default_empty else "Load"

    def _home_division(self, car: Car, train: Train, stops: list[Stop], track: Track, goal: Stop | None,
                       target: Track | None = None) -> dict:
        """C12: findDestinationsForCarsWithHomeDivision (TBC:894-1035). A car with a division and no
        destination gets a final destination from a fixed order of track types; none found holds it."""
        rr = self.rr
        defined = self.x.divisions
        if not car.division_id or (defined is not None and car.division_id not in defined):
            return self._gate("C12", PASS, "no home division")
        if car.destination_id or car.fd_id:
            return self._gate("C12", PASS, "the car already has a destination, so division rules do not run")
        candidates, kinds = self.division_candidates(car, stops, track)
        if not candidates:
            return self._gate("C12", FAIL, f"no track takes the car in the order {kinds}, so it is held")
        names = ", ".join(t.name for t in candidates[:4]) + (" and more" if len(candidates) > 4 else "")
        if target is not None and not self._division_leads_to(car, candidates, target):
            # The search sets one of these as the final destination (TBC:950-1035), and the router then
            # moves the car only towards it, so a destination off every path is never given.
            return self._gate("C12", FAIL, f"the car gets a final destination from {names} ({kinds}), and "
                                           f"{rr.locations[target.location_id].name} is not one of them or on the "
                                           "way to one")
        return self._gate("C12", NOT_CHECKED, f"the car gets a final destination from {names} ({kinds}); "
                                              "the router and room then pick one")

    def division_candidates(self, car: Car, stops: list[Stop], track: Track) -> tuple[list[Track], str]:
        """The tracks findDestinationsForCarsWithHomeDivision (TBC:894-1035) may give as the final
        destination, in its order of track types, and that order in words."""
        rr = self.rr
        here = rr.locations.get(car.location_id)
        home = bool(here) and here.division_id == car.division_id
        last = rr.locations.get(stops[-1].location_id)
        staged = bool(last) and last.is_staging and len(stops) > 1
        empty = self._load_type(car) == "Empty"
        if empty:
            order = ([("Staging", True), ("Spur", True)] if staged else [("Spur", True), ("Staging", True)]) \
                if track.is_yard and home else (
                [("Staging", True), ("Yard", True), ("Spur", True)] if staged else
                [("Yard", True), ("Staging", True), ("Spur", True)])
        else:
            order = [("Staging", not home), ("Spur", not home)] if staged else [("Spur", not home), ("Staging", not home)]
        candidates = []
        for kind, need_home in order:
            for t in rr.tracks.values():
                location = rr.locations[t.location_id]
                if t.type != kind or (need_home and location.division_id != car.division_id):
                    continue
                if not track.accepts_destination(location.id) or t.id == car.track_id:
                    continue
                if location.split == here.split and t.split == track.split:
                    continue
                if t.is_staging and location.id == car.location_id:
                    continue
                if self._accepts_ignoring_length(car, location, t):
                    candidates.append(t)
        kinds = " then ".join(f"{k.lower()}{' in the home division' if h else ''}" for k, h in order)
        return candidates, kinds

    def _division_leads_to(self, car: Car, candidates: list[Track], target: Track) -> bool:
        """Is the target a home division final destination, or the first hop of a route to one?"""
        rr = self.rr
        if any(t.location_id == target.location_id for t in candidates):
            return True
        where = rr.locations[target.location_id].name
        for t in candidates:
            routed = replace(car, fd_id=t.location_id, fd_track_id=t.id)
            path = self.route_path(routed, t)
            if path and path[0]["to"].split(", ")[0] == where:
                return True
        return False

    def _drop_gates(self, car: Car, train: Train, stops: list[Stop], origin: Stop | None, stop: Stop | None,
                    dest: Location, track: Track) -> list[dict]:
        rr, gate = self.rr, self._gate
        here_track = rr.tracks.get(car.track_id)
        here = rr.locations.get(car.location_id)
        if stop is None or origin is None or here_track is None or here is None:
            reason = f"no stop at {dest.name} after the car's stop on this route"
            first = gate("D1", FAIL, reason)
            return [first] + [gate(f"D{n}", NOT_CHECKED, reason) for n in range(2, 20)]
        exempt = _exempt(car)
        switcher = self._is_switcher(train)
        same = origin.split == stop.split
        out = [gate("D1", stop.drops or car.fred or car.caboose, f"drops {stop.drops}")]
        out.append(gate("D2", stop.id not in train.skips, f"stop {stop.id}"))
        out.append(self._moves_left(car, train, stops, origin, stop))
        returning = (train.allow_return or rr.option("buildOptions", "allowReturnStaging")) and dest.is_staging
        d4 = not same or switcher or exempt or returning
        out.append(gate("D4", d4, f"{origin.split} to {stop.split}, switcher {switcher}" + (
            "" if d4 else "; a car flagged passenger, caboose or FRED is exempt (TrainBuilderCars:1748-1754)")))
        out.append(gate("D5", not same or not car.fd_id or exempt or (stop.local and origin.local),
                        f"local {origin.local} and {stop.local}"))
        out.append(gate("D6", here_track.accepts_destination(dest.id), self._filter_reason(here_track, dest)))
        out.append(gate("D7", car.type in dest.types, f"{dest.name}: type {car.type}"))
        out.append(gate("D8", switcher or bool(stop.direction & dest.dir),
                        f"{stop.id} {directions(stop.direction)}, {dest.name} {directions(dest.dir)}"))
        out.append(self._leg_length(car, train, stops, stops.index(origin), stops.index(stop), "D9"))
        through = (not train.through_cars and not switcher and not exempt and here.split == stops[0].split
                   and stop.split == stops[-1].split and stops[0].split != stops[-1].split)
        out.append(gate("D10", not through, f"allow through cars {train.through_cars}"))
        terminal = train.to_terminal and origin.split != stops[0].split and stop.split != stops[-1].split
        out.append(gate("D11", not terminal, f"send to terminal {train.to_terminal}"))
        # The train terminates only on a track A7 accepts; there tryStaging refuses a local switcher's own
        # track and otherwise answers through car.checkDestination (D16).
        staged = dest.is_staging and stop is stops[-1] and track.is_staging
        problems = self.terminal_track_problems(train, track) if staged else []
        if staged and switcher and not exempt and car.track_id == track.id:
            problems.append("a switcher cannot set the car out on its own staging track")
        out.append(gate("D12", not problems, "; ".join(problems) or (
            "the train can terminate here; table E decides" if staged else "not terminal staging")))
        same_name = here.split == dest.split and here_track.split == track.split and not exempt
        out.append(gate("D13", not same_name, f"{here_track.name} to {track.name}"))
        final = rr.tracks.get(car.fd_track_id)
        shared = not (final and final.alternate_id == track.id and not track.dir & final.dir)
        out.append(gate("D14", (switcher or bool(stop.direction & dest.dir & track.dir)) and shared,
                        f"{stop.id} {directions(stop.direction)}, {track.name} {directions(track.dir)}"))
        listed = not (track.is_interchange or track.is_spur) or track.accepts_drop(train)
        out.append(gate("D15", listed, f"{track.name}: {track.drop_option}"))
        table_e = self.check_destination(car, dest, track)
        bad = [r["gate"] for r in table_e if r["status"] == FAIL]
        out.append(gate("D16", not bad, f"fails {', '.join(bad)}" if bad else "passes table E"))
        alternate = rr.tracks.get(track.alternate_id)
        full = any(r["gate"] == "E9" and r["status"] == FAIL and "full" in r["reason"] for r in table_e)
        if full and alternate:
            # checkForAlternate: the alternate must take the train and pass table E for the car, which
            # depends on its own space at that moment in the build.
            out.append(gate("D17", NOT_CHECKED, f"track is full; the car goes to alternate {alternate.name} "
                                                "only if that track takes the train and the car during the build"))
        else:
            out.append(gate("D17", PASS, "no alternate needed" if not full else "track is full and has no alternate"))
        out.append(self._timing(car, train, track))
        allowed = self._local_track_rule(car, train, here_track, track)
        out.append(gate("D19", allowed, f"switcher {switcher}: {here_track.type} to {track.type}"))
        return out

    def _moves_left(self, car: Car, train: Train, stops: list[Stop], origin: Stop, stop: Stop) -> dict:
        """D3: rld.getCarMoves() < rld.getMaxCarMoves() when the car is offered (TBC:1735)."""
        start = self._start_moves(train, stop)
        if start is None:
            return self._gate("D3", FAIL, f"random {stop.random!r} at {stop.name} fails the build")
        low, high = start
        if high <= 0:
            why = ("staging in mid-route uses all its moves" if self._mid_staging(train, stop) else
                   f"{stop.name} is skipped" if stop.id in train.skips else f"moves {stop.max_moves}")
            return self._gate("D3", FAIL, why)
        rivals = self._move_competitors(car, train, stops, origin, stop)
        moves = f"{low} of {stop.max_moves}" if low == high else f"{low} to {high} of {stop.max_moves} after random"
        if low - rivals >= 1:
            return self._gate("D3", PASS, f"{moves} moves at {stop.name}; at most {rivals} other cars are placed "
                                          "before this one")
        return self._gate("D3", NOT_CHECKED, f"{moves} moves at {stop.name}, and up to {rivals} other cars placed "
                                             "first may use them")

    def _timing(self, car: Car, train: Train, track: Track) -> dict:
        """D18: checkReserved (TBB:2487-2536). Timing matters only when the track lacks room counting the
        reserved length, and a car on it belongs to another train whose pull comes after this arrival."""
        rr = self.rr
        if car.track_id == track.id:
            return self._gate("D18", PASS, "car returns to its own track")
        need = rr.kernel_length(car)
        if need <= self._available(track) + self._reserved(track):
            return self._gate("D18", PASS, "room on the track without counting pulls")
        others = [c for c in rr.cars.values() if c.track_id == track.id and c.train_id and c.train_id != train.id]
        if not others:
            return self._gate("D18", PASS, "no car on the track belongs to another train, so no pull timing applies")
        names = sorted({rr.trains[c.train_id].name if c.train_id in rr.trains else c.train_id for c in others})
        return self._gate("D18", NOT_CHECKED, f"{len(others)} cars on the track leave with {', '.join(names)}; "
                                              "the set out fails if they are pulled after this train arrives")

    def _local_track_rule(self, car: Car, train: Train, here: Track, there: Track) -> bool:
        if not self._is_switcher(train):
            return True
        options = self.rr.option
        spur = options("buildOptions", "allowLocalSpur", options("buildOptions", "allowLocalSiding"))
        if not spur and here.is_spur and there.is_spur:
            return False
        if (not options("buildOptions", "allowLocalYard") and here.is_yard and there.is_yard
                and not car.caboose and not car.fred):
            return False
        return options("buildOptions", "allowLocalInterchange") or not (here.is_interchange and there.is_interchange)

    def _router_gates(self, car: Car, train: Train, dest: Location, track: Track) -> list[dict]:
        rr, gate = self.rr, self._gate
        codes = [f"G{n}" for n in range(1, 11)]
        if not (car.fd_id or _custom(rr, car) or car.division_id):
            return [gate(c, PASS, "router not used: default load and no final destination") for c in codes]
        results = {r["gate"]: r for r in self.serviceable(car, train, dest, track, building=True)}
        return [results.get(c) or gate(c, NOT_CHECKED, "stopped at an earlier G gate") for c in codes]

    def evaluate(self, car: Car, train: Train, dest: Location, track: Track) -> list[dict]:
        """Every gate in code order for one train and one destination track."""
        out, stops = self._train_gates(train)
        if not stops:
            head = [self._gate(c, NOT_CHECKED, "no route") for c in ("A5", "A6", "A7", "A8", "A9")]
            return out + head + self._rest(car, train, stops, None, None, dest, track)
        switcher = self._is_switcher(train)
        pickups = [s for s in stops if s.location_id == car.location_id]
        pairs = [(a, b) for a in pickups for b in stops
                 if b.location_id == dest.id and (stops.index(b) > stops.index(a) or (switcher and a is b))]
        if not pairs:
            pairs = [(pickups[0] if pickups else None, None)]
        best = None
        for pickup, drop in pairs:
            used = [s for s in (pickup, drop) if s]
            bad = [s.name for s in used if s.id in train.skips or self._mid_staging(train, s)]
            head = [self._gate("A5", not bad, ", ".join(bad) or "stops in use are worked")]
            head.append(self._random_gate(train, used))
            head += self._staging_gates(train, stops)
            attempt = head + self._rest(car, train, stops, pickup, drop, dest, track)
            # Equal move ratios go to the later stop: the saved stop wins only if strictly lower (TBC:1885).
            if best is None or _rank(attempt) < _rank(best) or (_rank(attempt) == _rank(best) == (0, -len(attempt))):
                best = attempt
        return out + best

    def _random_gate(self, train: Train, used: list[Stop]) -> dict:
        """A6: showAndInitializeTrainRoute draws the random reduction at every worked stop (TBB:510-530)."""
        bad = self._bad_random(train)
        if bad:
            return self._gate("A6", FAIL, "random is not a whole number at " + ", ".join(
                f"{s.name} ({s.random!r})" for s in bad) + ", so the build fails")
        notes, unsure = [], False
        for stop in used:
            if stop.random == "Off":
                continue
            low, high = self._start_moves(train, stop) or (0, 0)
            notes.append(f"{stop.name} random {stop.random}%: at least {low} of {high} moves remain")
            unsure = unsure or (low < 1 <= high)
        if not notes:
            return self._gate("A6", PASS, "random off at these stops")
        return self._gate("A6", NOT_CHECKED if unsure else PASS, "; ".join(notes))

    def _rest(self, car: Car, train: Train, stops: list[Stop], pickup: Stop | None, drop: Stop | None,
              dest: Location, track: Track) -> list[dict]:
        out = self._car_list_gates(car, train, stops, track)
        out += self._pickup_gates(car, train, stops, pickup, drop, track)
        out += self._drop_gates(car, train, stops, pickup, drop, dest, track)
        out += self.check_destination(car, dest, track)
        out += self._router_gates(car, train, dest, track)
        out.append(self._g11(train))
        return out

    def _g11(self, train: Train) -> dict:
        """TrainManager.getTrainForCar skips trains with build off when only active trains are used."""
        if not self.rr.option("router", "onlyActiveTrains"):
            return self._gate("G11", PASS, "option off")
        return self._gate("G11", train.build, f"{train.name} build {train.build}")

    # Router: ops_router ports JMRI's Router.setDestination.
    def route_path(self, car: Car, target: Track, check_target: bool = True) -> list[dict] | None:
        """Trains chaining the car to the target, or None, as JMRI's router finds them with no train named."""
        return ops_router.route_path(self, car, target, check_target)

    def routing_mode(self, car: Car) -> str:
        if car.fd_id:
            return "final destination: the router may chain up to seven trains"
        if car.division_id:
            return "home division: gets a final destination, then the router runs"
        if _custom(self.rr, car):
            return "custom load: global search of scheduled spurs, then staging, then this train's route"
        return "default load: only the building train's own route, the router never runs"

    def why_not(self, car: str | Car, destination: str | Location, track: str | Track | None = None,
                train: str | Train | None = None) -> dict:
        rr = self.rr
        car = rr.find_car(car) if isinstance(car, str) else car
        dest = rr.find_location(destination) if isinstance(destination, str) else destination
        tracks = [rr.find_track(track, dest) if isinstance(track, str) else track] if track else self.track_order(dest)
        trains = [rr.find_train(train) if isinstance(train, str) else train] if train else list(rr.trains.values())
        if not trains:
            raise ValueError("The railroad has no trains")
        if not tracks:
            raise ValueError(f"{dest.name} has no tracks")
        table = []
        for candidate in trains:
            for target in tracks:
                gates = self.evaluate(car, candidate, dest, target)
                gates.append(self._g12(car, target))
                table.append((candidate, target, gates))
        table.sort(key=lambda row: _rank(row[2]))  # Stable: equal rows keep JMRI's track order.
        chosen_train, chosen_track, gates = table[0]
        failed = [g for g in gates if g["status"] == FAIL and g["gate"] != "G12"]
        path = self.route_path(car, chosen_track) if self._router_eligible(car) else None
        # A home division the destination is not in (C12) holds the car whichever train or chain is tried.
        stuck = [g["gate"] for g in failed if g["gate"] in ANY_TRAIN or g["gate"] == "C12"]
        return {
            "car": str(car), "type": car.type, "load": car.load,
            "at": self._where(car), "destination": dest.name, "track": chosen_track.name,
            "train": chosen_train.name, "can_move": not failed or (bool(path) and not stuck),
            "direct": not failed, "routing": self.routing_mode(car), "router_path": path,
            "router": ops_router.router_detail(self, car, chosen_track, chosen_train),
            "first_failure": failed[0] if failed else None,
            "gates": gates,
            "other_trains": [
                {"train": t.name, "track": k.name, "first_failure": _first(g)} for t, k, g in table[1:]],
            **({} if track else {"track_order": [t.name for t in tracks],
                                 "track_note": "No track was named, so the first that passes in the default search's "
                                               "order is shown: tracks with a schedule first, then the lowest move "
                                               "count, ties by id (Location.getTracksByMoves); alternates last, as "
                                               "they are never chosen directly. Between two stops at the same "
                                               "location the later one wins a tie (TrainBuilderCars:1885)."}),
            "note": "Files only. Disk can lag a running JMRI by a minute or two, and gates marked "
                    "not_checked depend on the build itself.",
        }

    def _filter_reason(self, track: Track, dest: Location) -> str:
        """The Destinations filter as the window shows it. The ids are always the accepted ones (Exclude
        only inverts the checkboxes), so the list named is what the track lets cars go to."""
        if track.destination_option == ALL:
            return f"{track.name} accepts all destinations"
        names = [self.rr.locations[i].name for i in track.destination_ids if i in self.rr.locations]
        listed = ", ".join(names) or "none"
        verdict = "is on it" if track.accepts_destination(dest.id) else "is not"
        return f"{track.name} {track.destination_option} filter lets cars go only to {listed}; {dest.name} {verdict}"

    def track_order(self, location: Location) -> list[Track]:
        """Location.getTracksByMoves(null) (Location:925-956), the order the default search tries tracks in:
        ids sorted as text, then lowest moves first keeping that order on ties, tracks with a schedule moved
        to the front. JMRI drops alternate tracks; they go last here so they can still be explained."""
        alternates = {t.alternate_id for t in location.tracks if t.alternate_id}
        moves = self.loaded_moves()
        ordered = sorted(sorted(location.tracks, key=lambda t: t.id), key=lambda t: moves.get(t.id, t.moves))
        main = [t for t in ordered if t.id not in alternates]
        scheduled = [t for t in main if t.schedule_id and t.is_spur]  # Only spurs have a schedule (TR:1906).
        return (scheduled + [t for t in main if t not in scheduled]
                + [t for t in ordered if t.id in alternates])

    def _router_eligible(self, car: Car) -> bool:
        return bool(car.fd_id or car.division_id or _custom(self.rr, car))

    def _where(self, car: Car) -> str:
        location = self.rr.locations.get(car.location_id)
        track = self.rr.tracks.get(car.track_id)
        return ", ".join(x.name for x in (location, track) if x) or "nowhere"

    def _g12(self, car: Car, target: Track) -> dict:
        if not self._router_eligible(car):
            return self._gate("G12", PASS, "router not used: default load and no final destination")
        if car.track_id not in self.rr.tracks:
            return self._gate("G12", NOT_CHECKED, "car has no track")
        path = self.route_path(car, target)
        reason = " then ".join(f"{p['train']} to {p['to']}" for p in path) if path else "no chain of trains found"
        return self._gate("G12", path is not None, reason)

    def audit(self) -> dict:
        findings: list[dict] = []
        for rule in Audit(self).rules():
            findings.extend(rule())
        order = {"error": 0, "warning": 1, "info": 2}
        findings.sort(key=lambda f: order[f["severity"]])
        counts = {name: sum(f["severity"] == name for f in findings) for name in order}
        return {"railroad": self.rr.name, "counts": counts, "findings": findings,
                "load_warnings": self.rr.warnings}


def _rank(gates: list[dict]) -> tuple[int, int]:
    """Fewer failures first, then the failure furthest down the gates."""
    fails = [i for i, g in enumerate(gates) if g["status"] == FAIL]
    return (len(fails), -(fails[0] if fails else len(gates)))


def _first(gates: list[dict]) -> str | None:
    for g in gates:
        if g["status"] == FAIL:
            return f"{g['gate']}: {g['reason']}"
    return None


def _finding(rule: str, severity: str, subject: str, message: str, screen: str, setting: str) -> dict:
    return {"rule": rule, "severity": severity, "subject": subject, "message": message,
            "fix": {"screen": screen, "setting": setting}}


class Audit:
    """Whole-railroad checks. Each rule yields findings and stands alone."""

    def __init__(self, gates: Gates):
        self.g = gates
        self.rr = gates.rr

    def rules(self) -> list:
        return [getattr(self, name) for name in dir(self) if name.startswith("rule_")]

    def _fed_types(self) -> set[str]:
        return {car.type for car in self.rr.cars.values()}

    def rule_files(self):
        """A file the audit read as empty because it is missing or will not parse (Railroad tolerant).
        JMRI logs an error for such a file, loads nothing from it and carries on, and its next save
        writes the empty roster over the file."""
        for name, problem in sorted(getattr(self.rr, "broken", {}).items()):
            rule = "file-missing" if problem == "missing" else "file-unreadable"
            yield _finding(rule, "error", name,
                           f"{name} is {problem}, so this audit read it as empty. JMRI would load nothing from it "
                           "and could save the empty roster over it. Keep JMRI closed.", "Backups",
                           "ops_backups, then ops_restore with file to put this one file back")

    def rule_file_numbers(self):
        """A number JMRI's loader parses with no catch (ScheduleItem:335-375: sequenceId, count, wait, hits).
        Integer.parseInt throws, LocationManagerXml stops part-way, and the half-loaded roster stays in use:
        a later save writes it over the file, losing every schedule from that line on and the tracks'
        schedule assignments."""
        for name, subject, value in getattr(self.rr, "unloadable", []):
            yield _finding("file-number", "error", f"{name}: {subject}",
                           f"{value} is not a whole number Java can read (at most 2147483647), so JMRI cannot "
                           f"load {name}, and its next save would erase schedules. Keep JMRI closed and fix the "
                           "value first.", "Backups",
                           "replace_schedule_lines with a smaller count or wait, or ops_restore a backup set")

    def rule_leg_stops(self):
        """A leg 2 or 3 whose start or end is not a stop on the train's route. Train.load resolves them
        against the route (Train:4249-4263), keeps the options with no stop, and a caboose or locomotive
        change then fails the build ("change location missing", TrainBuilder:272-274)."""
        for train in self.rr.trains.values():
            route = self.rr.routes.get(train.route_id)
            stops = {s.id for s in route.stops} if route else set()
            for leg in train.legs:
                for end in ("start", "end"):
                    if leg[end] and leg[end] not in stops:
                        yield _finding("leg-stop", "error", train.name,
                                       f"Leg {leg['leg']} {end} {leg[end]} is not a stop on this train's route, "
                                       "so JMRI drops it and the leg's change fails the build.", BUILD_OPTIONS,
                                       "Leg 2 and leg 3: set_train_leg again")

    def rule_type_carriage(self):
        rr = self.rr
        for kind in sorted(self._fed_types()):
            if not any(kind in t.types for t in rr.trains.values()):
                yield _finding("type-no-train", "error", kind, f"No train takes car type {kind}.",
                               TRAIN, "Car types")
            if not any(kind in t.types and kind in rr.locations[t.location_id].types for t in rr.tracks.values()):
                yield _finding("type-no-track", "error", kind, f"No track takes car type {kind}.",
                               TRACK, "Car types, and the location's car types")

    def rule_load_carriage(self):
        rr = self.rr
        for kind in sorted(rr.loads):
            for load in rr.custom_loads(kind):
                if not any(kind in t.types and t.accepts_load(load.name, kind) for t in rr.trains.values()):
                    yield _finding("load-no-train", "error", f"{kind} {load.name}",
                                   f"No train takes {kind} with {load.name}.", TRAIN_LOADS, "Load option")
                if not any(self._track_takes(track, kind, load.name) for track in rr.tracks.values()):
                    yield _finding("load-no-track", "error", f"{kind} {load.name}",
                                   f"No track can take {kind} with {load.name}.", SCHEDULE,
                                   "A receive line on a spur, or a yard that takes the load")

    def _track_takes(self, track: Track, kind: str, load: str) -> bool:
        if kind not in track.types or kind not in self.rr.locations[track.location_id].types:
            return False
        if not track.accepts_load(load, kind):
            return False
        if not track.is_spur:
            return True
        schedule = self.rr.schedules.get(track.schedule_id)
        return bool(schedule) and any(i.type == kind and i.receive in ("", load) for i in schedule.items)

    def _spur_lines(self):
        for track in self.rr.tracks.values():
            schedule = self.rr.schedules.get(track.schedule_id)
            if track.is_spur and schedule:
                for item in schedule.items:
                    yield track, schedule, item

    def rule_load_balance(self):
        rr = self.rr
        lines = list(self._spur_lines())
        seen: set[tuple[str, str, str]] = set()
        for track, schedule, item in lines:
            if not item.ship or rr.is_default_load(item.ship) or item.destination_id:
                continue
            if item.ship not in {x.name for x in rr.loads.get(item.type, [])}:
                continue
            # A blank Receive takes any load (Schedule.java:490-494), so the custom-load search
            # (TBC:1070-1096) sends cars there too. It skips only the car's own track (TBC:1074-1076):
            # a car loaded on this spur cannot be sent back to it, so the shipper never counts.
            receivers = [t for t, _, other in lines if t is not track and other.type == item.type
                         and (other.receive == item.ship
                              or (other.receive == "" and self._track_takes(t, item.type, item.ship)))]
            if not receivers:
                yield _finding("load-no-receiver", "error", f"{item.type} {item.ship}",
                               f"{schedule.name} ships {item.ship} and no schedule on another spur receives it.",
                               SCHEDULE,
                               "A receive line for this load on another spur")
                continue
            if len({t.id for t in receivers}) == 1:
                yield _finding("single-receiver-load", "info", f"{item.type} {item.ship}",
                               f"Only {receivers[0].name} receives {item.ship}, so cars hold when it is full.",
                               SCHEDULE, "A second receiver, or an alternate track")
            for target in receivers:
                if (track.id, target.id, item.ship) in seen:
                    continue
                seen.add((track.id, target.id, item.ship))
                car = rr.at(self._sample(item.type, item.ship), track.location_id, track.id)
                # A sequential schedule's pointer moves, so ask only whether trains connect.
                if self.g.route_path(car, target, check_target=False) is None:
                    yield _finding("routing-gap", "error", f"{item.type} {item.ship}",
                                   f"No chain of trains takes {item.ship} from {track.name} to {target.name}.",
                                   ROUTE, "A train serving both ends, or a connecting interchange")

    def _sample(self, kind: str, load: str) -> Car:
        for car in self.rr.cars.values():
            if car.type == kind:
                return replace(car, load=load, fd_id="", fd_track_id="", last_route_id="")
        return Car(id="sample", road="", number="0", type=kind, length="40", load=load)

    def rule_schedule_destinations(self):
        rr = self.rr
        used = {t.schedule_id for t in rr.tracks.values()}
        for schedule in rr.schedules.values():
            if schedule.id not in used:
                yield _finding("schedule-unused", "info", schedule.name, "No track uses this schedule.",
                               "Schedules", "Assign it or delete it")
            dests = {i.destination_id for i in schedule.items}
            if not (schedule.items and len(dests) == 1 and "" not in dests):
                continue
            # A line with a destination is skipped by the load-balance rules, so check it here:
            # one fixed destination is fine unless nothing there takes the load or no train reaches it.
            dest = rr.locations.get(next(iter(dests)))
            where = dest.name if dest else "one place"
            owners = [t for t in rr.tracks.values() if t.schedule_id == schedule.id]
            for item in schedule.items:
                if not item.ship or rr.is_default_load(item.ship):
                    continue
                takers = [t for t in rr.tracks.values() if t.location_id == (dest.id if dest else "")
                          and self._track_takes(t, item.type, item.ship)]
                if not takers:
                    yield _finding("single-destination-schedule", "warning", schedule.name,
                                   f"Every line sends cars to {where}, and no track there takes "
                                   f"{item.type} with {item.ship}, so they cannot be delivered.", SCHEDULE,
                                   "Leave Destination blank on a line so the search picks one, or let a track there take the load")
                    break
                reachable = any(self.g.route_path(rr.at(self._sample(item.type, item.ship), o.location_id, o.id),
                                                  target, check_target=False) is not None
                                for o in owners for target in takers)
                if owners and not reachable:
                    yield _finding("single-destination-schedule", "warning", schedule.name,
                                   f"Every line sends cars to {where}, and no chain of trains takes "
                                   f"{item.ship} there.", ROUTE,
                                   "A train serving both ends, or leave Destination blank on a line")
                    break

    def rule_track_traps(self):
        rr = self.rr
        for t in rr.tracks.values():
            if t.is_yard and t.raw_pickup_option != ANY:
                yield _finding("yard-pickup-list", "warning", t.name,
                               "Yards ignore the pick up list, so every train can pull here. JMRI drops it at the next save.", TRACK,
                               "Make it an interchange, or use a train's own restrictions")
            if t.is_yard and t.raw_drop_option != ANY:
                yield _finding("yard-drop-list", "warning", t.name,
                               "Yards ignore the set out list, so every train can drop here. JMRI drops it at the next save.", TRACK,
                               "Make it an interchange, or use a train's own restrictions")
            if not (t.is_interchange or t.is_staging) and t.raw_destination_option != ALL:
                yield _finding("destinations-ignored", "warning", t.name,
                               "Track Destinations work only on interchange and staging tracks. JMRI drops them at the next save.", TRACK_DESTS,
                               "Move the filter to an interchange or staging track")
            if not (t.is_interchange or t.is_staging) and t.raw_only_fd:
                yield _finding("only-fd-ignored", "warning", t.name,
                               "Routed works only on interchange and staging tracks. JMRI drops it at the next save.",
                               TRACK, "Remove it")
            if not t.is_staging and t.raw_ship_option != ALL:
                yield _finding("ship-option-ignored", "warning", t.name,
                               "Ship load options work only on staging tracks. JMRI drops them at the next save.", TRACK, "Remove them")
            if not t.is_spur and t.schedule_id:
                yield _finding("schedule-on-non-spur", "warning", t.name,
                               "Only spurs use schedules, so this one does nothing here. JMRI drops it at the next save.", TRACK, "Move it to a spur")
            if not t.is_spur and t.raw_alternate_id:
                yield _finding("alternate-ignored", "warning", t.name,
                               "Only spurs have alternate tracks. JMRI drops this one at the next save.", TRACK, "Remove it")
            target = rr.tracks.get(t.alternate_id)
            if target and target.is_interchange:
                yield _finding("interchange-as-alternate", "warning", target.name,
                               f"{target.name} is the alternate for {t.name}. The router skips every alternate "
                               "track, so it is no longer a connection between trains, and with pick ups set to "
                               "Any the train that overflows a car onto it cannot pull that car back on the same "
                               "route.", TRACK, "Use a yard as the alternate")

    def rule_interchange_exit(self):
        """A Destinations filter on an interchange lets a car leave only for a location it admits. With no
        such stop on any pulling train, nothing leaves; per car type and load, as Check Destinations warns,
        a type or load that none of the admitted stops takes stays too."""
        rr = self.rr
        fed = self._fed_types()
        for t in rr.tracks.values():
            if not t.is_interchange or t.destination_option == ALL:
                continue
            exits = [(train, stop) for train in rr.trains.values() if t.accepts_pickup(train)
                     for stop in self._stops_after(train, t.location_id)
                     if t.accepts_destination(stop.location_id) and stop.location_id != t.location_id]
            if not exits:
                yield _finding("interchange-no-exit", "error", t.name,
                               "The destination filter admits no place any train from here goes, so cars stick.",
                               TRACK_DESTS, "Accept a location a pulling train serves")
                continue
            here = rr.locations[t.location_id]
            kinds = sorted(k for k in fed if k in t.types and k in here.types)
            dead = [k for k in kinds if not any(k in train.types and self._location_takes(stop.location_id, k, "")
                                                for train, stop in exits)]
            cars, _ = rr.rolling_stock_on(t)
            loads = sorted({(c.type, c.load) for c in cars if c.type not in dead and not any(
                c.type in train.types and train.accepts_load(c.load, c.type)
                and self._location_takes(stop.location_id, c.type, c.load) for train, stop in exits)})
            if dead or loads:
                what = ", ".join(dead + [f"{k} with {load}" for k, load in loads])
                yield _finding("interchange-no-exit", "warning", t.name,
                               f"The destination filter admits only places where no track takes {what}, so such "
                               "cars stick here.", TRACK_DESTS,
                               "Accept a location that takes them, or remove the type from this track")

    def _location_takes(self, location_id: str, kind: str, load: str) -> bool:
        rr = self.rr
        location = rr.locations.get(location_id)
        if location is None or kind not in location.types:
            return False
        for track in location.tracks:
            if kind not in track.types:
                continue
            if not load or (rr.is_default_load(load) and track.accepts_load(load, kind)):
                return True
            if load and self._track_takes(track, kind, load):
                return True
        return False

    def _stops_after(self, train: Train, location_id: str) -> list[Stop]:
        stops = self.rr.stops(train)
        calls = [i for i, s in enumerate(stops) if s.location_id == location_id]
        return stops[calls[0] + 1:] if calls else []

    def rule_load_types(self):
        rr = self.rr
        emptyish = re.compile(r"\b(e|mt|mty|empty|empties)\b", re.I)
        for kind, loads in rr.loads.items():
            for load in loads:
                if rr.is_default_load(load.name):
                    continue
                if emptyish.search(load.name) and load.load_type != "Empty":
                    yield _finding("custom-empty-flagged-load", "warning", f"{kind} {load.name}",
                                   "Looks like an empty but has Load Type Load, so a blank Ship flips it to the "
                                   "default empty rather than the default load.", "Edit Car Loads", "Load Type")
                elif load.load_type == "Empty" and not emptyish.search(load.name):
                    yield _finding("load-flagged-empty", "warning", f"{kind} {load.name}",
                                   "Has Load Type Empty but does not look like an empty; check blank Ship "
                                   "flips, weight and division rules.", "Edit Car Loads", "Load Type")
                for default in (rr.default_empty, rr.default_load):
                    if load.name.lower() == default.lower():
                        yield _finding("renamed-default-collision", "warning", f"{kind} {load.name}",
                                       f"Differs from the default {default} only by case. Names are case "
                                       "sensitive, so both exist and reports look alike.", "Edit Car Loads",
                                       "Rename the custom load")

    def rule_blank_receive(self):
        rr = self.rr
        for track, schedule, item in self._spur_lines():
            if item.receive:
                continue
            fed = [t.name for t in rr.tracks.values() if t.is_staging and self._feeds(t, track)]
            if fed:
                yield _finding("blank-receive-on-staging-fed-spur", "warning", track.name,
                               f"{schedule.name} line {item.id} has a blank Receive, and {fed[0]} generates "
                               "loads. Generation ignores blank lines.", SCHEDULE, "Set a custom Receive load")

    def _feeds(self, staging: Track, spur: Track) -> bool:
        if staging.load_options & GENERATE_ANY_SPUR:
            return True
        if not staging.load_options & GENERATE:
            return False
        return any(s.location_id == spur.location_id
                   for r in self.rr.routes.values() if r.stops and r.stops[0].location_id == staging.location_id
                   for s in r.stops)

    def rule_generators(self):
        rr = self.rr
        for t in rr.tracks.values():
            if not t.is_staging or not t.generates_loads:
                continue
            for kind in sorted({c.type for c in rr.rolling_stock_on(t)[0]}):
                wanted = [i for spur, _, i in self._spur_lines() if i.type == kind and i.receive
                          and not rr.is_default_load(i.receive) and self._feeds(t, spur)]
                if not wanted:
                    yield _finding("generator-no-target", "info", t.name,
                                   f"Generates loads, but no spur it can reach wants a custom load in a {kind}.",
                                   TRACK, "Custom Receive line, or widen the generate option")

    def rule_staging_ship(self):
        rr = self.rr
        for t in rr.tracks.values():
            empties = [c for c in rr.rolling_stock_on(t)[0] if c.load == rr.default_empty]
            if t.is_staging and empties and not t.ships_load(rr.default_empty, empties[0].type):
                yield _finding("staging-ship-excludes-empty", "warning", t.name,
                               f"Ship options refuse {rr.default_empty}, so any such car a generator cannot "
                               "fill stays and fails the build.", TRACK, "Ship load options")

    def _departures(self):
        """(train, staging location, stops) for each train with Build on whose route starts in staging.
        A train with Build off is built only by hand or by an automation, often on purpose with an empty track."""
        rr = self.rr
        for train in rr.trains.values():
            stops = rr.stops(train)
            first = rr.locations.get(stops[0].location_id) if stops else None
            if train.build and first is not None and first.is_staging:
                yield train, first, stops

    def rule_staging_departure(self):
        """checkDepartureStagingTrack (A8) for each track, then every car on a track that can depart: each
        must get a destination on this train or the build fails (B20, TBB:1380-1393). A car whose type or
        home division is the cause is left to staging-type-unserved and staging-division-unreachable."""
        for train, first, stops in self._departures():
            tracks = [t for t in first.tracks if t.is_staging]
            report = {t.name: self.g.staging_problems(train, t) for t in tracks}
            if tracks and all(report.values()):
                text = "; ".join(f"{k}: {', '.join(v)}" for k, v in report.items())
                yield _finding("staging-departure-blocked", "error", train.name,
                               f"No track at {first.name} can depart, so the build will fail. {text}",
                               TRACK, "Pick ups and the cars on the track")
                continue
            stuck = {t.name: self._stuck_cars(train, stops, t) for t in tracks if not report[t.name]}
            if not stuck or not any(stuck.values()):
                continue
            text = "; ".join(f"{k}: {', '.join(v[:3])}" for k, v in stuck.items() if v)
            if all(stuck.values()):
                yield _finding("staging-departure-blocked", "error", train.name,
                               f"Every track at {first.name} that can depart holds a car with no destination on "
                               f"this train, so the build will fail. {text}", TRACK,
                               "What refused each car: ops_why_not for it, then that gate's fix")
            else:
                yield _finding("staging-departure-blocked", "warning", train.name,
                               f"If JMRI departs from one of these tracks the build fails, since a car there has "
                               f"no destination on this train. {text}", TRACK,
                               "What refused each car: ops_why_not for it, then that gate's fix")

    SKIP_FOR_STUCK = {"A6", "A7", "A8", "A9", "B20", "C12", "D3", "D9", "E9"}  # session or build state, or own rules

    def _stuck_cars(self, train: Train, stops: list[Stop], track: Track) -> list[str]:
        rr = self.rr
        cars, _ = rr.rolling_stock_on(track)
        unserved = self._unserved_types(train, stops)
        out, seen = [], {}
        for car in cars:
            if self.g._is_clone(car) or (car.kernel and not rr.is_kernel_lead(car)) or car.type in unserved:
                continue
            if car.division_id and not car.destination_id and not car.fd_id:
                continue  # staging-division-unreachable decides these
            key = (car.type, car.load, car.road, car.owner, car.built, car.fd_id, car.fd_track_id,
                   car.destination_id, car.passenger, car.caboose, car.fred, car.length, car.kernel)
            if key not in seen:
                seen[key] = self._first_refusal(car, train, stops)
            if seen[key]:
                out.append(f"{car} ({seen[key]})")
        return out

    def _first_refusal(self, car: Car, train: Train, stops: list[Stop]) -> str:
        """Empty when some track at a later stop passes every gate the files decide; else the first refusal."""
        first = ""
        for location_id in dict.fromkeys(s.location_id for s in stops[1:]):
            location = self.rr.locations.get(location_id)
            if location is None:
                continue
            for target in self.g.track_order(location):
                fails = [g for g in self.g.evaluate(car, train, location, target)
                         if g["status"] == FAIL and g["gate"] not in self.SKIP_FOR_STUCK]
                if not fails:
                    return ""
                first = first or f"{fails[0]['gate']} at {target.name}: {fails[0]['reason']}"
        return first or "no stop after the departure"

    def _unserved_types(self, train: Train, stops: list[Stop]) -> set[str]:
        """Car types no track at a later stop of this train takes (with its location)."""
        rr = self.rr
        later = {s.location_id for s in stops[1:]}
        served = {kind for lid in later if lid in rr.locations for t in rr.locations[lid].tracks
                  for kind in t.types if kind in rr.locations[lid].types}
        return set(rr.car_types) - served

    def rule_staging_types(self):
        """A car on departure staging must leave, so a type that no track on any departing train's route
        takes fails every build from there (B20, D7, E3)."""
        rr = self.rr
        leaving: dict[str, list] = {}
        for train, first, stops in self._departures():
            leaving.setdefault(first.id, []).append((train, stops))
        for location_id, trains in leaving.items():
            for track in (t for t in rr.locations[location_id].tracks if t.is_staging):
                cars, _ = rr.rolling_stock_on(track)
                for kind in sorted({c.type for c in cars}):
                    if all(kind in self._unserved_types(train, stops) for train, stops in trains):
                        names = ", ".join(str(c) for c in cars if c.type == kind)
                        yield _finding("staging-type-unserved", "error", track.name,
                                       f"{names} ({kind}) must leave with the train, and no track on the route of "
                                       f"{', '.join(t.name for t, _ in trains)} takes {kind}, so the build fails.",
                                       TRACK, "Car types on a track (and its location) the train sets out at")

    def rule_staging_division(self):
        """A car with a home division and no destination gets a final destination in that division
        (TBC:894-1035) and the router must reach it; from staging the car must leave, so none reachable
        fails the build. JMRI applies the rule to a load generated in staging too."""
        rr = self.rr
        for train, first, stops in self._departures():
            for track in (t for t in first.tracks if t.is_staging):
                bad = []
                for car in rr.rolling_stock_on(track)[0]:
                    if not car.division_id or car.destination_id or car.fd_id or self.g._is_clone(car):
                        continue
                    if self.g.x.divisions is not None and car.division_id not in self.g.x.divisions:
                        continue
                    candidates, _ = self.g.division_candidates(car, stops, track)
                    if not any(self.g.route_path(replace(car, fd_id=t.location_id, fd_track_id=t.id), t)
                               for t in candidates):
                        bad.append(car)
                if bad:
                    division = rr.divisions.get(bad[0].division_id, bad[0].division_id)
                    yield _finding("staging-division-unreachable", "error", f"{train.name}, {track.name}",
                                   f"{', '.join(map(str, bad[:5]))} have home division {division}, and no track in "
                                   f"that division that takes them can be reached from {first.name}, so the "
                                   "build fails.", LOCATION,
                                   "Division: put a location this train or a connecting train reaches in that "
                                   "division, or clear the cars' division")

    def rule_terminal_staging(self):
        """checkTerminateStagingTrackRestrictions (TBB:2108-2156, on by default): a train ending in staging
        needs a track there that takes every type, road and load it carries. A track whose set out list
        names the train or its route skips the check. A train whose Build box is off is left out."""
        rr = self.rr
        if not rr.option("buildOptions", "stagingRestrictionEnabled", True):
            return
        for train in rr.trains.values():
            stops = rr.stops(train)
            last = rr.locations.get(stops[-1].location_id) if len(stops) > 1 else None
            if not train.build or last is None or not last.is_staging:
                continue
            first = rr.locations.get(stops[0].location_id)
            if first is last and rr.option("buildOptions", "aggressive") and rr.option("buildOptions", "stagingTrackAvail"):
                continue
            report = {}
            for t in (t for t in last.tracks if t.is_staging):
                if not t.accepts_drop(train):
                    report[t.name] = ["set out list refuses the train"]
                elif t.drop_option not in (TRAINS, ROUTES):
                    report[t.name] = self.g._staging_restrictions(train, t)
                else:
                    report[t.name] = []
            if report and all(report.values()):
                text = "; ".join(f"{k}: {', '.join(v)}" for k, v in report.items())
                yield _finding("terminal-staging-refuses-train", "error", train.name,
                               f"No staging track at {last.name} takes everything the train carries, so the build "
                               f"fails (A7). {text}", TRACK,
                               "Car and locomotive types, roads and loads on the track and its location, or the "
                               "train's own types; or Settings, staging track restrictions "
                               "(buildOptions stagingRestrictionEnabled)")

    def rule_caboose_traps(self):
        """Two ways a train that needs a caboose (or FRED car) cannot find one at its departure (B17):
        the caboose track is an interchange with Pick ups Any at both ends of a turn, so the caboose it sets
        back there is refused next time by the same route (B6, TBB:1528); or no such train's departing stop
        runs a direction the caboose track serves (C9, TBC:115)."""
        rr = self.rr
        for flag, bit, label in (("caboose", REQUIRES_CABOOSE, "caboose"), ("fred", REQUIRES_FRED, "FRED car")):
            kinds = {c.type for c in rr.cars.values() if getattr(c, flag)}
            needing = [t for t in rr.trains.values() if t.requires & bit]
            for train in needing:
                stops = rr.stops(train)
                if len(stops) < 2 or stops[0].split != stops[-1].split:
                    continue
                for track in rr.locations[stops[-1].location_id].tracks if stops[-1].location_id in rr.locations else []:
                    if track.is_interchange and track.raw_pickup_option == ANY and track.accepts_drop(train) \
                            and any(k in track.types for k in kinds):
                        yield _finding("caboose-interchange-same-route", "warning", f"{train.name}, {track.name}",
                                       f"{train.name} starts and ends at {stops[0].name} and needs a {label}. When it "
                                       f"sets one out on interchange {track.name}, Pick ups Any bars the same route "
                                       "from taking it again (B6), so the cabooses run out after a few sessions.",
                                       TRACK, "Pick ups: name the train or route, or keep cabooses on a yard track")
            for track in rr.tracks.values():
                held = [c for c in rr.rolling_stock_on(track)[0] if getattr(c, flag)]
                departing = [t for t in needing if rr.stops(t) and rr.stops(t)[0].location_id == track.location_id]
                if not held or not departing:
                    continue
                if not any(self.g._is_switcher(t) or rr.stops(t)[0].direction & track.dir for t in departing):
                    yield _finding("caboose-track-direction", "warning", track.name,
                                   f"Holds {', '.join(map(str, held[:4]))}, and no train that needs a {label} "
                                   f"departs here in a direction this track serves ({directions(track.dir)}), so "
                                   "they are never picked up (C9).", TRACK, "Train direction")

    def rule_schedule_not_applied(self):
        """A schedule applies when a car is delivered, or by Set Car to a new track (CarSetFrame:600-630);
        nothing revisits a parked car. A car on a scheduled spur still holding the load a line receives,
        where that line ships something else, was there before the schedule or was placed by hand."""
        rr = self.rr
        for car in rr.cars.values():
            track = rr.tracks.get(car.track_id)
            schedule = rr.schedules.get(track.schedule_id) if track and track.is_spur else None
            if schedule is None or car.wait or car.train_id or car.destination_id or \
                    track.load_options & DISABLE_LOAD_CHANGE:
                continue
            lines = [i for i in schedule.items if i.type == car.type and i.receive == car.load
                     and i.ship and i.ship != car.load]
            ships = {i.ship for i in schedule.items if i.type == car.type}
            if lines and car.load not in ships:
                yield _finding("schedule-not-applied", "warning", str(car),
                               f"Sits on {track.name} with {car.load}, which {schedule.name} line {lines[0].id} "
                               f"receives to ship {lines[0].ship}, but no line was applied, so it leaves with "
                               f"{car.load}.", CAR_SET,
                               "ops_session update_car load, or ops_deliver_car to another track and back")

    def rule_caboose(self):
        rr = self.rr
        # getCaboose looks only at the stop it is given (TBC:113, 148, 175): the departure, or a leg's
        # start for a caboose change (TrainBuilder:289-304); none there throws buildErrorReqDepature.
        for train in rr.trains.values():
            stops = rr.stops(train)
            if not stops:
                continue
            by_id = {s.id: s for s in stops}
            needs = []
            if train.requires & REQUIRES_CABOOSE and train.caboose_road:
                needs.append((train.caboose_road, stops[0], "departure"))
            for leg in train.legs:
                start = by_id.get(leg["start"])
                if leg["options"] & ADD_CABOOSE and leg["caboose_road"] and start:
                    needs.append((leg["caboose_road"], start, f"leg {leg['leg']} start"))
            for road, stop, where in needs:
                if not any(c.caboose and c.road == road and c.location_id == stop.location_id
                           for c in rr.cars.values()):
                    yield _finding("caboose-road-mismatch", "error", train.name,
                                   f"Requires a {road} caboose at {stop.name} ({where}) and none is there; the "
                                   "builder looks only at that stop, not along the route.",
                                   TRAIN, "Caboose road")

    def rule_directions(self):
        rr = self.rr
        for route in rr.routes.values():
            for stop in route.stops:
                location = rr.locations.get(stop.location_id)
                if location and not stop.direction & location.dir and len({s.split for s in route.stops}) > 1:
                    yield _finding("route-direction-mismatch", "error", f"{route.name}, {stop.name}",
                                   f"Stop runs {directions(stop.direction)}, the location serves "
                                   f"{directions(location.dir)}, so no work happens there.",
                                   LOCATION, "Train direction, or the stop's direction")
        served = {s.direction for r in rr.routes.values() for s in r.stops}
        # A local switcher ignores track direction for pick ups and set outs (TBB:1479-1482, 1618-1622).
        switched = {s.location_id for r in rr.routes.values() if r.stops and len({s.split for s in r.stops}) == 1
                    for s in r.stops}
        for t in rr.tracks.values():
            location = rr.locations[t.location_id]
            if location.id in switched:
                continue
            live = {s.direction for r in rr.routes.values() for s in r.stops if s.location_id == location.id}
            if live and not any(d & t.dir for d in live) and served:
                yield _finding("track-direction-unserved", "warning", t.name,
                               f"Serves {directions(t.dir)}, and no stop at {location.name} runs that way.",
                               TRACK, "Train direction")

    def rule_route_stops(self):
        rr = self.rr
        for route in rr.routes.values():
            for stop in route.stops:
                if stop.max_moves <= 0 or not (stop.pickups or stop.drops or stop.local):
                    yield _finding("route-stop-dead", "warning", f"{route.name}, {stop.name}",
                                   "No moves are possible at this stop.", ROUTE, "Moves, Pick ups, Drops")

    def rule_lists(self):
        rr = self.rr
        for t in rr.tracks.values():
            for option, ids, label in ((t.raw_drop_option, t.drop_ids, "set out"),
                                       (t.raw_pickup_option, t.pickup_ids, "pick up")):
                if option == ANY:
                    continue
                known = rr.trains if option in (TRAINS, EXCLUDE_TRAINS) else rr.routes
                for stale in [i for i in ids if i not in known]:
                    yield _finding("list-stale-id", "error", t.name,
                                   f"The {label} list names id {stale}, which no longer exists.", TRACK,
                                   f"{label.capitalize()} list")
                if t.is_yard or option in (EXCLUDE_TRAINS, EXCLUDE_ROUTES):
                    continue
                for train in rr.trains.values():
                    calls = any(s.location_id == t.location_id for s in rr.stops(train))
                    member = train.id in ids if option == TRAINS else train.route_id in ids
                    if calls and not member:
                        yield _finding("train-not-on-list", "info", t.name,
                                       f"{train.name} calls at this location and is not on the {label} list.",
                                       TRACK, f"{label.capitalize()} list")

    def rule_built_boundary(self):
        rr = self.rr
        for train in rr.trains.values():
            bounds = {train.built_start, train.built_end} - {""}
            for car in rr.cars.values():
                if str(built_year(car.built)) in bounds:
                    yield _finding("built-boundary", "warning", str(car),
                                   f"Built {car.built}, exactly {train.name}'s limit. Both ends are "
                                   "exclusive, so the train refuses it.", BUILD_OPTIONS, "Built dates")

    def rule_stale_days(self):
        """A day id no train schedule holds. JMRI treats it as any day (B15 and F1 pass it, TrainBuilderBase 965,
        Schedule.checkScheduleItem), but a spur line with a stale set out day is never used to pick a custom
        load (TBB:2288-2303 tests only the set out day; the pick up day is not on that path)."""
        rr = self.rr
        gone = lambda day: bool(day) and day != ANY_DAY and day not in rr.train_schedules
        tails = {"set out": ", and load generation never uses a line with a missing set out day.",
                 "pick up": "; load generation does not read the pick up day, so the line is still used."}
        for schedule in rr.schedules.values():
            for item in schedule.items:
                for label, day in (("set out", item.setout_day), ("pick up", item.pickup_day)):
                    if gone(day):
                        yield _finding("day-stale-id", "warning", f"{schedule.name} line {item.id}",
                                       f"The {label} day is id {day}, which no train schedule holds. It behaves as "
                                       f"any day{tails[label]}",
                                       SCHEDULE, f"Clear the {label} day or set a real one")
        for car in rr.cars.values():
            if gone(car.pickup_day):
                yield _finding("day-stale-id", "warning", str(car),
                               f"The pick up day is id {car.pickup_day}, which no train schedule holds. It "
                               "behaves as any day, so the car can leave on every day.", CAR,
                               "Clear the pick up day or set a real one")

    def rule_rwe(self):
        rr = self.rr
        for car in rr.cars.values():
            target = rr.tracks.get(car.rwe_track_id)
            if car.rwe_load and not rr.is_default_load(car.rwe_load) and target and target.is_spur \
                    and not target.schedule_id:
                yield _finding("rwe-to-unscheduled-spur", "warning", str(car),
                               f"Return-when-empty sends custom load {car.rwe_load} to {target.name}, a spur "
                               "with no schedule, which refuses custom loads.", CAR,
                               "Return when empty destination or load")

    def rule_kernels(self):
        rr = self.rr
        for kernel in sorted({c.kernel for c in rr.cars.values() if c.kernel}):
            members = [c for c in rr.cars.values() if c.kernel == kernel]
            places = {(c.location_id, rr.tracks[c.track_id].split if c.track_id in rr.tracks else None)
                      for c in members}
            # With no leadKernel flag the first member loaded leads (RollingStockGroup.java:40-42).
            leads = [c for c in members if c.lead] or members[:1]
            if len(places) > 1:
                yield _finding("kernel-split", "error", kernel,
                               "Members are on different tracks. Any train that sees them fails to build.",
                               CAR, "Move the members together")
            elif all(c.out_of_service for c in leads):
                yield _finding("kernel-split", "error", kernel,
                               "No lead car in service. Any train that sees the kernel fails to build.",
                               CAR, "Lead car, or Out of Service on the lead")

    def rule_cars(self):
        rr = self.rr
        for car in rr.cars.values():
            track = rr.tracks.get(car.track_id)
            if not car.location_id or not track:
                yield _finding("car-unplaced", "warning", str(car), "Car has no location or no track, so no "
                               "train will see it.", CAR_SET, "Location and track")
            elif car.type not in track.types:
                yield _finding("car-on-refusing-track", "warning", str(car),
                               f"Sits on {track.name}, which does not take type {car.type}.", CAR_SET, "Track")
            elif car.location_id in rr.locations and car.type not in rr.locations[car.location_id].types:
                # Track.isTypeNameAccepted asks the location first (Track.java:977-982).
                yield _finding("car-on-refusing-track", "warning", str(car),
                               f"Sits on {track.name}, and its location {rr.locations[car.location_id].name} does "
                               f"not take type {car.type}.", CAR_SET, "Track, or the location's car types")

    def rule_service(self):
        rr = self.rr
        served = {s.location_id for r in rr.routes.values() for s in r.stops}
        for location in rr.locations.values():
            if location.id not in served:
                yield _finding("location-unserved", "warning", location.name, "No route stops here.",
                               ROUTE, "Add a stop")
        names = {split_name(x.name) for x in rr.locations.values()}
        for location in rr.locations.values():
            head = location.name.split("-")[0].strip()
            if "-" in location.name and location.split == location.name and head in names:
                yield _finding("hyphen-no-split", "warning", location.name,
                               f"Only a hyphen followed by a number or ( splits a name, so this is not part "
                               f"of {head}.", LOCATION, f"Name it {head}-(north) or {head}-2")

    def rule_switchers(self):
        rr = self.rr
        spur = rr.option("buildOptions", "allowLocalSpur", rr.option("buildOptions", "allowLocalSiding"))
        off = [n for n, v in (("spur", spur), ("yard", rr.option("buildOptions", "allowLocalYard")),
                              ("interchange", rr.option("buildOptions", "allowLocalInterchange"))) if not v]
        if not off:
            return
        for train in rr.trains.values():
            if self.g._is_switcher(train):
                yield _finding("switcher-local-off", "info", train.name,
                               f"A local switcher, but {', '.join(off)} moves to the same kind of track are off.",
                               SETTINGS, "Switcher Service Options")

    # ---- Locomotives against acceptance (JMRI 5.16) ----------------------------------
    # Locomotive types are read from the files (Extras), as the staging checks do: ops_data keeps
    # only car types on locations, tracks and trains.
    def _engines(self) -> list:
        return [e for e in self.rr.engines.values()
                if CLONE_MARK not in e.number and self.g.x.engine.get(e.id, {}).get("clone") != "true"]

    def _track_takes_loco(self, track: Track, kind: str) -> bool:
        """Track.isTypeNameAccepted (Track:977): the location must take the type too."""
        return kind in self.g.x.types.get(track.location_id, set()) and kind in self.g.x.types.get(track.id, set())

    def _loco_slots(self, train: Train) -> list[tuple[str, str]]:
        """(model, road) for each locomotive request the builder makes (TrainBuilderEngines:388-480):
        the departure, and each leg whose options change, add, help or remove locomotives. A request
        for 0 still takes every locomotive on a departure staging track (getEngines:154-160)."""
        raw = self.g.x.train.get(train.id, {})
        stops = self.rr.stops(train)
        first = self.rr.locations.get(stops[0].location_id) if stops else None
        slots = []
        if raw.get("numberEngines", "0") != "0" or (first is not None and first.is_staging):
            slots.append((raw.get("engineModel", ""), raw.get("engineRoad", "")))
        for leg, options in (("leg2", train.leg2_options), ("leg3", train.leg3_options)):
            if options & (1 | 2 | 16 | 32) and raw.get(f"{leg}Engines", "0") != "0":
                slots.append((raw.get(f"{leg}Model", ""), raw.get(f"{leg}Road", "")))
        return slots

    def _loco_refusal(self, train: Train, engine) -> str:
        """Why this train never takes this locomotive: getAndRemoveEnginesFromList (TBE:31-67) for
        type, loco road, owner and built, then getEngines (TBE:201-211) for the model and road it names.
        Empty when the train can take it."""
        e = self.g.x.engine.get(engine.id, {})
        raw = self.g.x.train.get(train.id, {})
        if engine.type not in self.g._train_types(train):
            return f"type {engine.type}"
        option = raw.get("locoRoadOption", ALL)
        if option != ALL and (engine.road in self.g.x.loco_roads.get(train.id, [])) != (option == "Include"):
            return f"locomotive road {engine.road}"
        if not train.accepts_owner(e.get("owner", "")):
            return f"owner {e.get('owner', '')}"
        if not train.accepts_built(e.get("built", "")):
            return f"built {e.get('built', '')}"
        slots = self._loco_slots(train)
        if not slots:
            return "asks for no locomotives"
        if not any(model in ("", engine.model) and road in ("", engine.road) for model, road in slots):
            return "needs " + " or ".join(" ".join(x for x in (road, model) if x) for model, road in slots)
        return ""

    def _model_types(self) -> dict[str, str]:
        """EngineModels: the last engine loaded sets each model's type (Engine.java:448)."""
        return {e.model: e.type for e in self._engines() if e.model and e.type}

    def rule_model_types(self):
        rr = self.rr
        for model, kind in sorted(self._model_types().items()):
            if not any(kind in self.g._train_types(t) for t in rr.trains.values()):
                yield _finding("model-type-no-train", "error", model,
                               f"Model {model} is type {kind}, and no train takes {kind}, so no train uses these "
                               "locomotives.", TRAIN, "Locomotive types")
            if not any(self._track_takes_loco(t, kind) for t in rr.tracks.values()):
                yield _finding("model-type-no-track", "error", model,
                               f"Model {model} is type {kind}, and no track takes {kind}, so a train cannot set "
                               "these locomotives out anywhere.", TRACK,
                               "Locomotive types serviced by this track, and the location's")

    def rule_engine_trains(self):
        rr = self.rr
        carried = {kind for t in rr.trains.values() for kind in self.g._train_types(t)}
        for engine in self._engines():
            # A type no train takes is model-type-no-train; out of service is the owner's choice.
            if engine.out_of_service or engine.type not in carried:
                continue
            reasons = [(t.name, self._loco_refusal(t, engine)) for t in rr.trains.values()]
            if all(r for _, r in reasons):
                text = "; ".join(f"{n}: {r}" for n, r in reasons[:4]) + ("; ..." if len(reasons) > 4 else "")
                yield _finding("engine-no-train", "error", f"{engine.road} {engine.number}",
                               f"No train takes this locomotive. {text}.", TRAIN,
                               "Locomotive roads (Train Road Options), owners and built dates (Train Build "
                               "Options), or the locomotive count, model and road")

    def rule_engine_places(self):
        rr = self.rr
        for engine in self._engines():
            location, track = rr.locations.get(engine.location_id), rr.tracks.get(engine.track_id)
            if location is None or track is None:
                continue
            name = f"{engine.road} {engine.number}"
            if engine.type not in self.g.x.types.get(location.id, set()):
                yield _finding("engine-location-refuses-type", "warning", name,
                               f"Sits at {location.name}, which does not take type {engine.type}. Set Locomotive "
                               "refuses the spot without force, and no train sets it out there.", LOCATION,
                               "Select the rolling stock serviced by this location")
            elif not self._track_takes_loco(track, engine.type):
                yield _finding("engine-on-refusing-track", "warning", name,
                               f"Sits on {track.name}, which does not take type {engine.type}. Set Locomotive "
                               "refuses the spot without force, and no train sets it out there.", TRACK,
                               "Locomotive types serviced by this track")

    def rule_consists(self):
        rr = self.rr
        for consist in sorted({e.consist for e in self._engines() if e.consist}):
            members = [e for e in self._engines() if e.consist == consist]
            places = {(e.location_id, e.track_id) for e in members}
            if len(places) > 1:
                where = ", ".join(f"{e.road} {e.number} on " + (rr.tracks[e.track_id].name if e.track_id in
                                                                 rr.tracks else "no track") for e in members)
                yield _finding("consist-split", "warning", consist,
                               f"Members are on different tracks ({where}). A train that takes the lead adds the "
                               "others at the lead's stop, wherever they sit (TrainBuilderEngines addEngineToTrain).",
                               ENGINE_SET, "Location and track, and answer yes to move the whole consist")
    # ---- End of locomotives against acceptance ---------------------------------------


# ---- Train schedule days and manifest formats ---------------------------------------
def _day_note(rr: Railroad, train: Train) -> str:
    """The builder reads only the Build box; a day's train list sets it when Apply runs
    (TrainsScheduleTableFrame:370-378, ApplyTrainScheduleAction), so say when they disagree."""
    day = getattr(rr, "days", {}).get(rr.active_schedule)
    if day is None or (train.id in day.trains) == train.build:
        return ""
    turn = "off" if train.build else "on"
    listed = "does not list it" if train.build else "lists it"
    return f"; active day {day.name} {listed}, so Apply (apply_day) would turn Build {turn}"
# ---- End of train schedule days and manifest formats --------------------------------


# ---- Pool minimums (start) ----------------------------------------------------------
def _rule_pool_minimums(self):
    """PoolTrackFrame:270 shows ERROR: Minimum > Length when a pool's minimums add up to more than its
    tracks' lengths. Track.load (Track:2754-2768) reads the minimums without that check, so JMRI loads such
    a pool silently; Pool.requestTrackLength then lends length only down to each track's minimum."""
    for location in self.rr.locations.values():
        pools: dict[str, list[Track]] = {}
        for track in location.tracks:
            if track.pool:
                pools.setdefault(track.pool, []).append(track)
        for name, tracks in sorted(pools.items()):
            minimum = 0
            for track in tracks:
                value = self.g.x.track.get(track.id, {}).get("minLength", "0")
                minimum += int(value) if JAVA_INT.fullmatch(value) else 0
            length = sum(t.length for t in tracks)
            if minimum > length:
                yield _finding("pool-minimum-over-length", "warning", f"{location.name}, {name}",
                               f"Pool minimum lengths add up to {minimum}, more than its tracks' {length} "
                               f"({', '.join(t.name for t in tracks)}). JMRI's pool window shows ERROR: Minimum > "
                               "Length, and the pool lends length only down to each track's minimum.",
                               "Edit Location > track > Pool", "Lower the minimums, or lengthen the tracks")


Audit.rule_pool_minimums = _rule_pool_minimums
# ---- Pool minimums (end) ------------------------------------------------------------
